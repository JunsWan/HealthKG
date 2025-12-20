# recommender.py

from datetime import datetime, timedelta
from collections import Counter, defaultdict
from query import ExerciseKGQuery
import random

# =========================
# Real physical equipment
# =========================
REAL_EQUIPMENT = {
    "Barbell",
    "Dumbbell",
    "Cable",
    "Smith",
    "Lever",
    "Suspended",
    "Sled",
    "Band Resistive",
}

# =========================
# Equipment subtype mapping
# =========================
EQUIPMENT_PARENT = {
    "Lever (plate loaded)": "Lever",
    "Lever (selectorized)": "Lever",
    "Sled (plate loaded)": "Sled",
    "Sled (selectorized)": "Sled",
    "Suspension": "Suspended",
}




# ============================================================
# History-based scoring
# ============================================================
from datetime import datetime
from collections import Counter, defaultdict


def muscle_time_penalty(days_ago: float) -> float:
    """Piecewise time decay penalty"""
    if days_ago < 1:
        return 2.0
    elif days_ago < 3:
        return 1.5
    elif days_ago < 7:
        return 0.5
    else:
        return 0.0


def score_exercises(candidates, history):
    """
    candidates: List of dicts
      {
        "id": str,
        "body_part": str,
        "target_muscles": List[str]
      }

    history: List of dicts
      {
        "exercise_id": str,
        "timestamp": str,
        "target_muscles": List[str]
      }
    """

    now = datetime.now()

    # === Long-term statistics ===
    exercise_freq = Counter()
    muscle_freq = Counter()

    # === Recent muscle usage ===
    muscle_recent_penalty = defaultdict(float)
    exercise_recent_penalty = defaultdict(float)

    for h in history:
        eid = h.get("id")
        ts = h.get("timestamp")
        muscles = h.get("target_muscles", [])

        if eid:
            exercise_freq[eid] += 1

        if not ts:
            continue

        try:
            t = datetime.fromisoformat(ts)
        except Exception:
            continue

        days_ago = (now - t).total_seconds() / 86400.0

        # 动作级冷却（更强）
        if eid:
            exercise_recent_penalty[eid] += muscle_time_penalty(days_ago)

        # 肌肉级疲劳
        for m in muscles:
            muscle_freq[m] += 1
            muscle_recent_penalty[m] += muscle_time_penalty(days_ago)

    # === Score candidates ===
    scores = {}

    for ev in candidates:
        score = 0.0
        ev_id = ev["id"]
        ev_muscles = ev.get("target_muscles", [])

        # 1️⃣ 长期偏好（肌肉频次）
        for m in ev_muscles:
            score += muscle_freq.get(m, 0) * 0.3

        # 2️⃣ 动作级冷却惩罚
        score -= exercise_recent_penalty.get(ev_id, 0.0)

        # 3️⃣ 肌肉级疲劳惩罚（取最大，避免过度惩罚）
        if ev_muscles:
            max_penalty = max(
                muscle_recent_penalty.get(m, 0.0)
                for m in ev_muscles
            )
            score -= max_penalty

        scores[ev_id] = score

    return scores


def is_exercise_feasible(exercise_equipment, user_equipment):
    """
    判断一个动作在用户设备条件下是否可做

    exercise_equipment: List[str]  # 来自 KG
    user_equipment: Set[str]       # 用户真实拥有的器械
    """

    if not exercise_equipment:
        # 没声明任何 equipment → 默认可做
        return True

    for eq in exercise_equipment:
        parent = EQUIPMENT_PARENT.get(eq, eq)

        # 只在「真实器械」且用户没有时排除
        if parent in REAL_EQUIPMENT and parent not in user_equipment:
            return False

    return True


# ============================================================
# Main recommendation pipeline
# ============================================================
def recommend_exercises(
    user_profile: dict,
    kg_query,
    top_k: int = 10
):
    """
    user_profile example:
    {
      "target_body_part": "Chest",
      "injury_body_part": "Neck",
      "available_equipment": ["Barbell", "Dumbbell"],
      "history": [...]
    }
    """

    # =========================
    # Step 0️⃣ 用户输入准备
    # =========================
    target_body_part = user_profile.get("target_body_part")
    injury_body_part = user_profile.get("injury_body_part")

    user_equipment = set(user_profile.get("available_equipment", []))
    history = user_profile.get("history", [])

    # =========================
    # Step 1️⃣ KG 初筛（只做硬约束）
    # =========================
    candidates = kg_query.fetch_candidates(
        target_body_part=target_body_part,
        injury_body_part=injury_body_part,
        available_equipment=[],  # ❗这里不再做 equipment 硬过滤
    )

    if not candidates:
        return []

    # =========================
    # Step 2️⃣ 设备可行性过滤（Python 层）
    # =========================
    feasible = [
        ev for ev in candidates
        if is_exercise_feasible(
            ev.get("equipment", []),
            user_equipment
        )
    ]

    if not feasible:
        return []

    # =========================
    # Step 3️⃣ 基于历史的打分
    # =========================
    scores = score_exercises(feasible, history)

    # =========================
    # Step 4️⃣ 排序 & Top-K（同分随机，return 不变）
    # =========================

    # 按 score 分组
    score_buckets = defaultdict(list)
    for ev in feasible:
        score = scores.get(ev["id"], 0.0)
        score_buckets[score].append(ev)

    # 对每个 score 内部随机打散
    for evs in score_buckets.values():
        random.shuffle(evs)

    # 按 score 降序拼接
    ranked = []
    for score in sorted(score_buckets.keys(), reverse=True):
        ranked.extend(score_buckets[score])

    # 🔽 新增：过滤 instructions 为 None / 空 的动作
    ranked = [
        ev for ev in ranked
        if ev.get("instructions")  # None、"" 都会被过滤
    ]

    # ⚠️ return 方式与原来完全一致
    return ranked[:top_k]


