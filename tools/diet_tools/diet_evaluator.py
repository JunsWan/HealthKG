# code/tools/diet_evaluator.py

from typing import List, Dict, Any
from itertools import combinations
from datetime import datetime, timedelta
import math
from tools.diet_tools.query import *
from collections import defaultdict
import time
import numpy


MEAL_RATIOS = {
    "breakfast": 0.25,
    "lunch": 0.35,
    "dinner": 0.30,
    "snack": 0.10,
    "brunch": 0.30
}

ACTIVITY_FACTOR = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "high": 1.725,
    "extreme": 1.9
}


def compute_tdee(user):
    # 计算每日静止能量需求
    if user["demographics"]["gender"] == "male":
        bmr = (
            10 * user["demographics"]["weight_kg"]
            + 6.25 * user["demographics"]["height_cm"]
            - 5 * user["demographics"]["age"]
            + 5
        )
    else:
        bmr = (
            10 * user["demographics"]["weight_kg"]
            + 6.25 * user["demographics"]["height_cm"]
            - 5 * user["demographics"]["age"]
            - 161
        )
    tdee = bmr * ACTIVITY_FACTOR[user["activity"]["activity_level"]]
    goal = user["activity"].get("user_goal", "maintenance")
    if goal == "bulking":
        tdee *= 1.12
    elif goal == "cutting":
        tdee *= 0.85

    return tdee


def remaining_calories_today(user, tdee):
    eaten = sum(
        m.get("calories", 0)
        for m in user["current_context"].get("today_intake", [])
        if m.get("status") != "skipped"
    )
    return max(tdee - eaten, 0)


def ingredient_preference_score(recipe, user):
    liked = {
        i.lower()
        for i in user["diet_profile"].get("preferred_ingredients", [])
    }
    disliked = {
        i.lower()
        for i in user["diet_profile"].get("disliked_ingredients", [])
    }

    ingredients = set()

    for ing in recipe.get("ingredients", []):
        if isinstance(ing, dict):
            name = ing.get("name")
            if name:
                ingredients.add(name.lower())
        elif isinstance(ing, str):
            ingredients.add(ing.lower())

    score = 0.0
    score += len(ingredients & liked) * 1.0
    score -= len(ingredients & disliked) * 1.5

    return score


def history_penalty(candidate_names: List[str], history: List[Dict[str, Any]]) -> float:
    """
    [Fixed] 适配 Graph Event 结构的历史惩罚计算
    history: list of events (from Neo4j graph)
    candidate_names: list of recipe names (from KG candidates)
    """
    now = datetime.now()
    penalty = 0.0
    
    # 预处理 candidates 为小写，加速匹配
    candidates_lower = [n.lower() for n in candidate_names if n]

    for h in history:
        # 1. 过滤非饮食事件
        if h.get("type") not in ["DietLog", "MealLog"]:
            continue
            
        # 2. 解析时间 (Unix Timestamp)
        ts = h.get("ts", 0)
        try:
            log_time = datetime.fromtimestamp(ts)
        except:
            continue
            
        days = (now - log_time).days
        
        # 优化：只惩罚最近 7 天的重复，太久的无所谓
        if days > 7:
            continue

        # 3. 提取日志内容 (props.summary / props.description / props.foods)
        props = h.get("props", {})
        
        # 拼接所有可能的文本字段进行模糊匹配
        # 例如: summary="午餐", description="吃了番茄炒蛋", foods=["Tomato Egg"]
        content_text = (
            str(props.get("summary", ""))
        ).lower()

        # 4. 计算惩罚
        # 如果候选菜名出现在了最近的日志里
        for cand in candidates_lower:
            if cand in content_text:
                # 距离今天越近，惩罚越大 (1/(days+1))
                # 昨天吃的: 1/2 = 0.5
                # 今天吃的: 1/1 = 1.0
                penalty += 1.0 / max(days + 1, 1)

    return penalty


def normalize_nutrients(nutrients):
    """
    将 nutrient list 转为 dict:
    - key: nutrient name（如 carbs, protein）
    - value: quantity（float）

    原则：
    - 缺失 / 非法 quantity -> 直接跳过
    - 不强行补 0，避免误导推荐与生成
    """
    if not nutrients:
        return {}

    result = {}

    for n in nutrients:
        if not isinstance(n, dict):
            continue

        # 使用 name（如 CHOCDF / PROCNT）或 label（如 Carbs）
        raw_key = n.get("name") or n.get("label")
        if not raw_key:
            continue

        try:
            quantity = float(n.get("quantity"))
        except (TypeError, ValueError):
            continue  # ❗️关键：直接跳过，而不是置 0

        clean_key = (
            str(raw_key)
            .lower()
            .strip()
            .replace(" ", "_")
            .replace("-", "_")
        )

        result[clean_key] = round(quantity, 2)

    return result


def nutrient_match_score(plan_nutrients, user):
    """
    user["diet_profile"]["nutrient_targets"] 例子：
    {
        "protein_g": [90, 130],
        "fat_g": [40, 70],
        "carbs_g": [150, 250]
    }
    """
    targets = user["diet_profile"].get("nutrient_targets", {})
    score = 0.0

    for k, (low, high) in targets.items():
        v = plan_nutrients.get(k, 0)

        if low <= v <= high:
            score += 1.0
        else:
            # 超出越多，惩罚越大（线性）
            dist = min(abs(v - low), abs(v - high))
            score -= dist / max(high, 1)

    return score


def normalize_ingredients(ingredients):
    """
    ingredient 规范化：
    - 不伪造 quantity
    - 保留 text 以供 LLM 生成使用
    """
    if not ingredients:
        return []

    normalized = []

    for i in ingredients:
        if not isinstance(i, dict):
            continue

        name = i.get("name")
        if not name:
            continue

        normalized.append({
            "name": name,
            "quantity": i.get("quantity"),          # 允许 None
            "measure": i.get("measure") or "",
            "weight_g": round(i.get("weight") or 0, 1),
            "text": i.get("text") or ""
        })

    return normalized


def jaccard_similarity(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def diversity_penalty(
    combo_recipes: list[str],
    selected_solutions: list[list[str]],
    alpha: float = 1.0
) -> float:
    """
    对当前方案与已选方案的最大相似度进行惩罚
    """
    if not selected_solutions:
        return 0.0

    combo_set = set(combo_recipes)

    max_sim = 0.0
    for sol in selected_solutions:
        sim = jaccard_similarity(combo_set, set(sol))
        max_sim = max(max_sim, sim)

    return alpha * max_sim


def recommend_meals(user, kg: "DietKGQuery", top_k=3):
    start_time = time.time()
    tdee = compute_tdee(user)
    meal = user["current_context"]["meal_time"]

    # ---------- 目标热量 ----------
    if user["current_context"]["today_intake"]:
        remaining = remaining_calories_today(user, tdee)
        if meal == "breakfast":
            target_cal = remaining * 0.25
        elif meal == "lunch" or meal == "brunch":
            target_cal = remaining * 0.55
        elif meal == "dinner":
            target_cal = remaining
        else:
            target_cal = remaining * MEAL_RATIOS.get(meal, 0.1)
    else:
        target_cal = tdee * MEAL_RATIOS.get(meal, 0.3)

    # ---------- dish 约束 ----------
    dish_constraint = {
        "breakfast": ["bread", "egg", "cereals"],
        "lunch": ["main course", "salad", "soup"],
        "dinner": ["main course", "salad", "soup"],
        "snack": ["snack", "desserts", "drinks"],
        "brunch": ["main course", "salad"]
    }

    # ---------- KG 查询 ----------
    candidates = kg.fetch_candidates_with_detail(
        meal_type=meal if meal != "lunch" else "lunch/dinner",
        dish_types=dish_constraint[meal],
        diet_labels=user["diet_profile"]["diet_labels"],
        health_labels=user["diet_profile"]["health_preferences"],
        forbidden_cautions=user["diet_profile"]["forbidden_cautions"]
    )

    print("符合条件的候选数量有：", len(candidates))
    print("搜索到候选的时间为：", time.time() - start_time)

    # ---------- 1️⃣ 枚举所有组合，计算 base_score ----------
    scored_plans = []

    for k in (1, 2, 3):
        for combo in combinations(candidates, k):
            total_cal = sum(
                r["calories"] / max(r["servings"], 1)
                for r in combo
            )

            plan_nutrients = defaultdict(float)
            ingredient_score = 0.0

            for r in combo:
                factor = 1.0 / max(r["servings"], 1)
                nutrients = normalize_nutrients(r["nutrients"])
                for nk, nv in nutrients.items():
                    plan_nutrients[nk] += nv * factor

                ingredient_score += ingredient_preference_score(r, user)

            score = 0.0

            # 热量匹配
            score += max(
                0, 1 - abs(total_cal - target_cal) / max(target_cal, 1)
            ) * 0.4

            # 增肌蛋白偏好
            if user["activity"].get("user_goal") == "bulking":
                score += sum(
                    "High-Protein" in r.get("diet_labels", [])
                    for r in combo
                ) * 0.2

            # 健康标签
            score += sum(
                len(set(r["health_labels"]) & set(user["diet_profile"]["health_preferences"]))
                for r in combo
            ) * 0.2

            # 菜系偏好
            nationality = user["demographics"].get("nationality", "chinese")
            score += sum(
                1 for r in combo if nationality in r["cuisine_type"]
            ) * 0.1

            # 食材偏好
            score += ingredient_score
            
            # 营养适配
            score += nutrient_match_score(
                plan_nutrients, user
            ) 

            # 历史惩罚
            score -= history_penalty(
                [r["recipe_name"] for r in combo],
                user.get("history", []) 
            ) * 0.15

            plan_recipes = []
            plan_nutrients = defaultdict(float)

            for r in combo:
                per_serving_factor = 1.0 / max(r["servings"], 1)
                nutrients = normalize_nutrients(r["nutrients"])

                for k2, v2 in nutrients.items():
                    plan_nutrients[k2] += v2 * per_serving_factor

                plan_recipes.append({
                    "recipe_name": r["recipe_name"],
                    "servings_used_ratio": per_serving_factor,
                    "calories": round(r["calories"] * per_serving_factor, 1),
                    "cuisine_type": r["cuisine_type"],
                    "dish_type": r["dish_type"],
                })

            scored_plans.append({
                "meal_time": meal,
                "target_calories": round(target_cal, 1),
                "actual_calories": round(total_cal, 1),
                "base_score": round(score, 4),
                "recipes": plan_recipes,
            })

    # ---------- 2️⃣ 按 base_score 排序 ----------
    scored_plans.sort(key=lambda x: x["base_score"], reverse=True)

    # ---------- 3️⃣ 多样性约束：逐个选 Top-K ----------
    selected = []
    selected_recipe_sets = []

    ALPHA = 0.4   # ⭐ 多样性惩罚强度（推荐 0.3–0.6）

    while len(selected) < top_k and scored_plans:
        best_plan = None
        best_final_score = -1e9

        for plan in scored_plans:
            recipe_names = [r["recipe_name"] for r in plan["recipes"]]

            penalty = diversity_penalty(
                recipe_names,
                selected_recipe_sets,
                alpha=ALPHA
            )

            final_score = plan["base_score"] - penalty

            if final_score > best_final_score:
                best_final_score = final_score
                best_plan = plan

        if best_plan is None:
            break

        # 记录最终 score
        best_plan["score"] = round(best_final_score, 4)
        selected.append(best_plan)
        selected_recipe_sets.append(
            [r["recipe_name"] for r in best_plan["recipes"]]
        )

        # 移除已选方案，避免重复
        scored_plans = [
            p for p in scored_plans if p is not best_plan
        ]

    print("全部评分 + 多样性筛选完成，用时：", time.time() - start_time)
    return selected
