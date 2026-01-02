# agents/subflows.py
import json
import time
from typing import Any, Dict, Tuple, List
from datetime import datetime

from agents.runner import run_agent
from core.config import get_cfg
from core.llm import chat

# === 工具导入 ===
from tools.exercise_recommender import recommend_exercise_tool
# [NEW] 引入新的饮食工具
from tools.diet_tools.diet_recommender import diet_recommendation_tool
from tools.diet_tools.query import DietKGQuery 

from memory.graph_store import summarize, apply_patch
from agents.prompts import (
    INTENT_PARSER_SYS,
    MEMORY_RETRIEVER_SYS,
    PLAN_DRAFT_SYS,
    KNOWLEDGE_RETRIEVER_SYS,
    REASONER_SYS,
    MEMORY_UPDATER_SYS,
)
from agents.schemas import (
    INTENT_PARSER_RESPONSE_FORMAT,
    MEMORY_RETRIEVER_RESPONSE_FORMAT,
    PLAN_DRAFT_RESPONSE_FORMAT,
    KNOWLEDGE_RETRIEVER_RESPONSE_FORMAT,
    REASONER_RESPONSE_FORMAT,
    MEMORY_UPDATER_RESPONSE_FORMAT,
)

# === 常量定义 ===
VALID_BODY_PARTS = [
    'Chest', 'Arm', 'Neck', 'Waist', 'Calf', 'ForeArm', 
    'Hips', 'Should', 'Thigh', 'Back'
]
GYM_PRESET = ["Barbell", "Dumbbell", "Cable", "Lever", "Smith Machine", "Sled", "Weighted", "Suspended"]


# ============================================================
# Helpers
# ============================================================

def _extract_patch_ops(agent_output: Any) -> List[Dict]:
    if isinstance(agent_output, dict) and "ops" in agent_output:
        return agent_output["ops"]
    if isinstance(agent_output, list):
        return agent_output
    return []

def ensure_pipeline_state(user_input: str, user_graph: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "user_input": user_input,
        "user_memory_graph": user_graph,
        "memory_summary": summarize(user_graph),
        "task_frame": {},
        "memory_retrieval": {},
        "draft_plan": {},
        "kg_evidence": {"exercise_kg": [], "nutrition_kg": []},
        "kg_evidence_normalized": {"exercise_kg": [], "nutrition_kg": []},
        "support_map": [],
        "decision": {},
        "memory_patch": []
    }

def _extract_search_criteria(user_text: str) -> dict:
    """提取运动搜索关键词"""
    valid_parts_str = ", ".join(VALID_BODY_PARTS)
    sys_prompt = (
        f"You are a query parser for an exercise database.\n"
        f"The database only accepts these specific body parts: [{valid_parts_str}].\n\n"
        "Your task:\n"
        "1. Identify the target body part from user input and map it to ONE of the valid parts above. "
        "(e.g., 'Legs' -> 'Thigh' or 'Calf'; 'Abs' -> 'Waist').\n"
        "2. Identify specific exercise names (keywords_include).\n"
        "3. Identify negative constraints (keywords_exclude).\n\n"
        "Output strictly in the following JSON format:\n"
        "{\n"
        '  "target_part": "",\n'
        '  "keywords_include": [],\n'
        '  "keywords_exclude": []\n'
        "}"
    )

    try:
        resp = chat(instruction=sys_prompt, user_message=user_text, response_format={"type": "json_object"})
        return json.loads(resp)
    except Exception as e:
        print(f"[Query Extraction Failed] {e}")
        return {"target_part": None, "keywords_include": [], "keywords_exclude": []}


# ============================================================
# [NEW] Diet Profile Adapter
# ============================================================
def _construct_diet_user_profile(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 MAS 的扁平记忆结构转换为 Diet Recommender 需要的复杂 User Profile
    """
    mem = state.get("memory_summary", {})
    profile = mem.get("profile", {})
    goal = mem.get("goal_primary", {})
    pref_diet = mem.get("preferences", {}).get("diet", {})
    
    # 1. 基础信息 (Demographics)
    demographics = {
        "gender": profile.get("gender", "female"), # 默认值保守一点
        "age": int(profile.get("age", 30)),
        "height_cm": float(profile.get("height", 165)),
        "weight_kg": float(profile.get("weight", 60)),
        "nationality": profile.get("nationality", "chinese")
    }
    
    # 2. 目标与活动 (Activity)
    # 映射 goal_type 到 recommender 接受的枚举
    raw_goal = goal.get("goal_type", "health")
    user_goal = "maintenance"
    if "增肌" in raw_goal or "muscle" in raw_goal.lower():
        user_goal = "bulking"
    elif "减脂" in raw_goal or "weight loss" in raw_goal.lower() or "cutting" in raw_goal.lower():
        user_goal = "cutting"
        
    activity = {
        "activity_level": profile.get("activity_level", "moderate"), # sedentary, light, moderate, high
        "user_goal": user_goal
    }
    
    # 3. 饮食偏好 (Diet Profile)
    # 假设 pref:diet 节点存储了 props: { "labels": [...], "dislikes": [...] }
    diet_profile = {
        "diet_labels": pref_diet.get("labels", []), # Low-Carb, High-Protein etc.
        "health_preferences": pref_diet.get("health_preferences", []), # Gluten-Free etc.
        "forbidden_cautions": pref_diet.get("allergies", []), # Shellfish etc.
        "preferred_ingredients": pref_diet.get("likes", []),
        "disliked_ingredients": pref_diet.get("dislikes", [])
    }
    
    # 4. 上下文 (Context)
    # 获取当天的摄入记录
    raw_events = state["user_memory_graph"].get("events", [])
    today_intake = []
    history = []
    
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    for e in raw_events:
        if e.get("type") in ["DietLog", "MealLog"]:
            props = e.get("props", {})
            ts = e.get("ts", 0)
            date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            
            item = {
                "meal_time": props.get("meal_type", "snack"),
                "calories": props.get("calories", 0),
                "timestamp": datetime.fromtimestamp(ts).isoformat(),
                "recipes": [{"recipe_name": props.get("summary", "Unknown")}]
            }
            
            history.append(item)
            if date_str == today_str:
                today_intake.append(item)

    current_context = {
        "meal_time": "dinner", # 默认推荐晚餐，或者根据当前时间判断
        "today_intake": today_intake
    }
    
    # 简单的时间判断
    hour = now.hour
    if 5 <= hour < 10: current_context["meal_time"] = "breakfast"
    elif 10 <= hour < 15: current_context["meal_time"] = "lunch"
    else: current_context["meal_time"] = "dinner"

    return {
        "user_id": profile.get("name", "user_001"),
        "demographics": demographics,
        "activity": activity,
        "diet_profile": diet_profile,
        "current_context": current_context,
        "history": history
    }


# ============================================================
# Subflows
# ============================================================

def subflow_faq_exercise(state: Dict[str, Any], exercise_kg: Dict[str, Any]) -> Dict[str, Any]:
    """升级版 FAQ: 智能设备感知"""
    user_input = state["user_input"]
    mem_sum = state.get("memory_summary", {})
    print(mem_sum)
    user_injuries = mem_sum.get("special", {}).get("injuries_active", [])
    print(user_injuries)
    user_equip = (mem_sum.get("constraints", {}).get("equipment") or 
                  mem_sum.get("preferences", {}).get("equipment") or [])
    
    raw_events = state["user_memory_graph"].get("events", [])
    workout_history = [e.get("props", {}) for e in raw_events if e.get("type") == "WorkoutLog"]

    criteria = _extract_search_criteria(user_input)
    target_part = criteria.get("target_part")
    excludes = criteria.get("keywords_exclude", [])
    
    print(f"[FAQ-Ex] Target: {target_part}, Excludes: {excludes}")

    evid = []
    
    if target_part:
        current_equip_context = user_equip
        equip_warning = False
        if not current_equip_context:
            current_equip_context = GYM_PRESET
            equip_warning = True

        try:
            tool_args = {
                "target_body_part": target_part,
                "injury_body_part": user_injuries if user_injuries else [],
                "available_equipment": current_equip_context,
                "history": workout_history,
                "topk": 5
            }
            recs = recommend_exercise_tool(tool_args)
            
            if excludes:
                evid = [r for r in recs if not any(ex.lower() in r.get("name", "").lower() for ex in excludes)]
            else:
                evid = recs
            
            print(evid)
            if equip_warning and evid:
                evid.insert(0, {
                    "source": "SYSTEM_NOTE",
                    "name": "Note",
                    "summary": "【注意】因暂无您的器械记录，以下推荐默认基于「健身房全器械」环境。",
                    "fields": {}
                })
        except Exception as e:
            print(f"[FAQ-Ex] Tool failed: {e}")

    if not evid:
        search_kw = target_part if target_part else user_input
        evid = _simple_neo4j_search(search_kw, excludes=excludes)

    state["kg_evidence"]["exercise_kg"] = evid
    return state


# agents/subflows.py -> subflow_faq_food

def subflow_faq_food(state: Dict[str, Any], nutrition_kg: Dict[str, Any]) -> Dict[str, Any]:
    """
    [Upgrade] 升级版 FAQ Food: 意图提取 -> 翻译 -> 搜索
    """
    user_input = state["user_input"]
    print(f"[FAQ-Food] Raw Input: {user_input}")
    
    # 1. 意图提取 (提取纯食物名，去除 "100g", "热量多少" 等修饰词)
    # 我们临时跑一次 IntentParser 来清洗实体
    # (如果之前的流程已经跑过且存了 task_frame，可以直接用，但为了稳健这里强制分析一次)
    try:
        parsed = run_agent("IntentParser", INTENT_PARSER_SYS, state, [], response_format=INTENT_PARSER_RESPONSE_FORMAT)
        foods_cn = parsed.get("entities", {}).get("foods", [])
    except Exception as e:
        print(f"[FAQ-Food] Intent parsing failed: {e}")
        foods_cn = []

    # 兜底：如果没提取到，可能用户只输了"番茄"，那就用原词
    if not foods_cn:
        # 简单清洗一下数字
        import re
        clean_input = re.sub(r'\d+[a-zA-Z\u4e00-\u9fa5]*', '', user_input).strip() # 去掉 100g 等
        if clean_input:
            foods_cn = [clean_input]
        else:
            foods_cn = [user_input] # 实在没办法就用原句

    print(f"[FAQ-Food] Extracted Entities (CN): {foods_cn}")

    # 2. 翻译 (CN -> EN)
    foods_en = _translate_keywords(foods_cn)
    print(f"[FAQ-Food] Translated Keywords (EN): {foods_en}")

    evid = []
    
    # 3. 搜索 KG
    if foods_en:
        # 去重
        unique_foods = list(set(foods_en))
        for f in unique_foods:
            # 搜索
            try:
                # 这里的 _simple_diet_search 已经包含了你之前改好的配置读取逻辑
                recs = _simple_diet_search(f, top_k=3)
                evid.extend(recs)
            except Exception as e:
                print(f"[FAQ-Food] Search error for '{f}': {e}")
    
    # 4. 结果回填
    if not evid:
        # 如果搜不到，生成一个占位符告诉 LLM 没数据，让它用常识回答
        evid.append({
            "evidence_id": "NOT_FOUND",
            "name": "Search Failed",
            "summary": "No matching records in Diet KG. Please answer based on general nutrition knowledge.",
            "source": "System"
        })

    state["kg_evidence"]["nutrition_kg"] = evid
    return state

def subflow_query_memory(state: Dict[str, Any], trace: list) -> Dict[str, Any]:
    """
    [Fixed] 补充丢失的记忆查询流程
    """
    state["memory_retrieval"] = run_agent(
        "MemoryRetriever", MEMORY_RETRIEVER_SYS, state, trace,
        response_format=MEMORY_RETRIEVER_RESPONSE_FORMAT
    )
    return state
def subflow_plan_full(state: Dict[str, Any], trace: list,
                      exercise_kg: Dict[str, Any], nutrition_kg: Dict[str, Any],
                      route_name: str = "plan_both",
                      chat_history: list = None) -> Dict[str, Any]:
    """
    升级版 Plan Flow: 集成 Exercise 和 Diet 的真实推荐
    """
    if chat_history is None:
        chat_history = []
    
    need_exercise = route_name in ["plan_workout", "plan_both"]
    need_diet = route_name in ["plan_diet", "plan_both"]
    
    # 准备历史 (Exercise用)
    workout_history = []
    if need_exercise:
        raw_events = state["user_memory_graph"].get("events", [])
        for e in raw_events:
            if e.get("type") == "WorkoutLog":
                props = e.get("props", {})
                workout_history.append(props)

    # 1. 意图解析 & 记忆检索
    state["task_frame"] = run_agent("IntentParser", INTENT_PARSER_SYS, state, trace, response_format=INTENT_PARSER_RESPONSE_FORMAT)
    task_frame = state["task_frame"]
    state["memory_retrieval"] = run_agent("MemoryRetriever", MEMORY_RETRIEVER_SYS, state, trace, response_format=MEMORY_RETRIEVER_RESPONSE_FORMAT)

    # Context Stitching
    recent_user_msgs = [msg.get("content", "") for msg in reversed(chat_history) if msg.get("role") == "user"][:3]
    context_text = " ".join(reversed(recent_user_msgs))
    if state["user_input"] not in context_text:
        context_text += " " + state["user_input"]
    
    print(f"[Plan] Full Context: {context_text}")

    # ============================================================
    # ★ Step 2.5: 主动预检索 (Pre-retrieval)
    # ============================================================
    
    # --- A. 运动推荐 (Exercise Recommendation) ---
    if need_exercise:
        recommended_candidates = []
        # 1. 器械提取
        current_equip = task_frame.get("constraints", {}).get("equipment", []) or []
        stored_equip = state.get("memory_summary", {}).get("constraints", {}).get("equipment", []) or []
        combined_equip = list(set(current_equip + stored_equip))
        
        # 2. Context 兜底
        if not combined_equip:
            common_gear = ["哑铃", "Dumbbell", "弹力带", "Band", "壶铃"]
            for gear in common_gear:
                if gear in context_text or gear.lower() in context_text.lower():
                    if "哑" in gear: combined_equip.append("Dumbbell")
                    if "弹" in gear: combined_equip.append("Resistance Band")
            
            negative_keywords = ["没器械", "没有器械", "徒手", "bodyweight", "无器械"]
            if any(kw in context_text.lower() for kw in negative_keywords):
                print("[Plan] Detected 'No Equipment' context -> Body Weight.")
                combined_equip = ["Body Weight"]

        # 3. 拦截
        if not combined_equip:
            clarification_msg = "为了定制计划，请确认您的训练环境：\n❓ **您有哪些可用器械？** (例如哑铃、弹力带，或说明是徒手)"
            state["decision"] = {"response": clarification_msg, "thought": "缺少器械信息"}
            state["draft_plan"] = {}
            return state

        user_equip = combined_equip
        target_muscles = task_frame.get("entities", {}).get("muscle_groups", [])
        
        # 部位兜底
        if not target_muscles:
            criteria = _extract_search_criteria(context_text) 
            if criteria.get("target_part"):
                target_muscles = [criteria["target_part"]]
        if not target_muscles:
            target_muscles = ["Chest", "Back", "Thigh"]

        # 执行推荐
        for muscle in target_muscles:
            args = {
                "target_body_part": muscle,
                "injury_body_part": task_frame.get("constraints", {}).get("injury", []),
                "available_equipment": user_equip,
                "history": workout_history,
                "topk": 5
            }
            try:
                recs = recommend_exercise_tool(args)
                recommended_candidates.extend(recs)
            except Exception as e:
                print(f"[Plan] Ex-Rec failed: {e}")
        
        state["kg_evidence"]["exercise_kg"] = recommended_candidates

    # --- B. [NEW] 饮食推荐 (Diet Recommendation) ---
    if need_diet:
        print("[Plan] Starting Diet Recommendation...")
        try:
            # 1. 构造复杂 User Profile
            diet_user_profile = _construct_diet_user_profile(state)
            
            # 2. 调用 Diet Recommender
            # 这会返回 [ {meal_time: dinner, recipes: [...]}, ... ]
            diet_plans = diet_recommendation_tool(diet_user_profile)
            
            # 3. 格式化为 Evidence 供 LLM 阅读
            diet_evidence = []
            for plan in diet_plans:
                meal_time = plan.get("meal_time", "meal")
                score = plan.get("score", 0)
                cal_target = plan.get("target_calories", 0)
                cal_actual = plan.get("actual_calories", 0)
                
                for r in plan.get("recipes", []):
                    # 提取主要食材文本
                    ings = r.get("ingredients", [])
                    ing_text = ", ".join([i.get("text", i.get("name")) for i in ings[:5]])
                    
                    evidence_item = {
                        "evidence_id": r.get("recipe_name"), # 使用名称作为ID
                        "name": r.get("recipe_name"),
                        "summary": (
                            f"【推荐理由】评分:{score:.2f}, 匹配餐段:{meal_time}。\n"
                            f"热量:{r.get('calories', 0):.1f}kcal (目标:{cal_target:.0f})。\n"
                            f"主要食材: {ing_text}"
                        ),
                        "fields": {
                            "calories": r.get("calories"),
                            "cuisine": r.get("cuisine_type"),
                            "nutrients": r.get("nutrients") # 包含详细营养素
                        },
                        "source": "Diet_Recommender"
                    }
                    diet_evidence.append(evidence_item)
            
            state["kg_evidence"]["nutrition_kg"] = diet_evidence
            print(f"[Plan] Diet Rec success. Generated {len(diet_evidence)} items.")
            
        except Exception as e:
            print(f"[Plan] Diet Rec failed: {e}")
            state["kg_evidence"]["nutrition_kg"] = []

    # ============================================================
    # 3. 生成草案 (PlanDraft)
    # ============================================================
    task_instruction = "当前任务：生成综合方案。"
    if route_name == "plan_workout":
        task_instruction = "当前任务：仅生成【训练计划】。"
    elif route_name == "plan_diet":
        task_instruction = "当前任务：仅生成【饮食计划】。请优先使用 Nutrition Evidence 中的推荐食谱。"
    
    current_prompt = PLAN_DRAFT_SYS + f"\n\n### 动态指令\n{task_instruction}"
    state["draft_plan"] = run_agent("PlanDraft", current_prompt, state, trace, response_format=PLAN_DRAFT_RESPONSE_FORMAT)

    # ============================================================
    # 4. 补充知识检索 (Diet 部分已通过 Pre-retrieval 完成，这里主要补漏)
    # ============================================================
    # 这里我们只保留 Exercise 的补充检索，因为 Diet Recommender 是一次性生成全餐，不需要按词检索
    # 如果 LLM 觉得还需要查某些食材的具体信息，可以由 KnowledgeRetriever 发起 query
    
    # kout1 = run_agent("KnowledgeRetriever#1", KNOWLEDGE_RETRIEVER_SYS, state, trace, response_format=KNOWLEDGE_RETRIEVER_RESPONSE_FORMAT)
    # ... (KnowledgeRetriever loop logic same as before) ...
    
    # 5. 推理决策
    state["decision"] = run_agent("Reasoner", REASONER_SYS, state, trace, response_format=REASONER_RESPONSE_FORMAT)
    
    return state


# ============================================================
# Search Wrappers
# ============================================================
def subflow_commit_plan(state: Dict[str, Any], trace: list, accepted_plan_text: str, task_frame: Dict = None) -> Dict[str, Any]:
    """
    [Fixed] 接受 task_frame 参数，并在采纳计划时强制更新 User Profile 节点。
    """
    from datetime import datetime
    
    # 1. 构造 Prompt：显式指令，告诉 MemoryUpdater 必须更新哪些 Node
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # 基础指令：记录 Plan Event
    plan_context = (
        f"【系统指令】用户已采纳以下计划，请执行记忆写入。\n"
        f"当前时间: {current_date}\n\n"
        f"1. **必须**创建一个 Event (type='Plan')，props包含 plan_type, summary, created_at。\n"
        f"2. **必须**根据下方 TaskFrame 更新用户画像 Node (Profile/Constraints)。\n"
        f"   - 如果没有对应的 Node，请使用 update_node 自动创建。\n\n"
        f"=== Task Frame (用户信息) ===\n{task_frame}\n\n"
        f"=== 采纳的计划详情 ===\n{accepted_plan_text[:800]}..." # 截断防止 token 溢出
    )
    
    # 2. ★★★ 关键：强制注入更新指令 (Force Node Updates) ★★★
    if task_frame:
        constraints = task_frame.get("constraints", {})
        equips = constraints.get("equipment", [])
        injuries = constraints.get("injury", [])
        
        plan_context += "\n\n【强制操作列表 (必须生成对应 op)】:\n"
        
        # 强制更新器械节点 (constraint:equipment)
        if equips:
            # 明确告诉它 ID 是 constraint:equipment
            plan_context += f"- update_node(id='constraint:equipment', props={{'items': {equips}}})\n"
        else:
            # 如果确认是无器械，也要更新状态，防止 UI 显示 Unknown
            # 只有当 task_frame 明确包含 equipment 字段（哪怕是空列表）时才更新，避免覆盖
            if "equipment" in constraints:
                 plan_context += f"- update_node(id='constraint:equipment', props={{'items': ['Body Weight']}})\n"

        # 强制更新伤病节点
        for inj in injuries:
            plan_context += f"- update_node(id='injury:{inj}', type='Injury', props={{'name': '{inj}', 'status': 'active'}})\n"

    # 3. 伪造/覆盖 decision response，让 Updater 认为这是结论
    state["decision"]["response"] = plan_context
    
    print("[System] Committing plan & FORCING profile update...")

    # 4. 运行 MemoryUpdater
    raw_updater_out = run_agent(
        "MemoryUpdater", MEMORY_UPDATER_SYS, state, trace,
        response_format=MEMORY_UPDATER_RESPONSE_FORMAT
    )
    
    patch_ops = _extract_patch_ops(raw_updater_out)
    state["memory_patch"] = patch_ops
    updated = apply_patch(state["user_memory_graph"], patch_ops)
    state["user_memory_graph_updated"] = updated
    
    return state

def subflow_log_update(state: Dict[str, Any], trace: list) -> Dict[str, Any]:
    raw_updater_out = run_agent("MemoryUpdater", MEMORY_UPDATER_SYS, state, trace, response_format=MEMORY_UPDATER_RESPONSE_FORMAT)
    patch_ops = _extract_patch_ops(raw_updater_out)
    state["memory_patch"] = patch_ops
    updated = apply_patch(state["user_memory_graph"], patch_ops)
    state["user_memory_graph_updated"] = updated
    return state

def _simple_neo4j_search(
    target_part: str,
    exercise_text: str = None,
    excludes: list = None,
    limit: int = 5
):
    """
    正确逻辑：
    1. target_part 作为硬约束（TrainingBodyPart）
    2. exercise_text 作为模糊匹配（name / muscle）
    """
    from tools.exercise_tools.query import ExerciseKGQuery
    from core.config import get_cfg

    cfg = get_cfg()
    if excludes is None:
        excludes = []

    kg = ExerciseKGQuery(
        cfg["neo4j_uri"],
        (cfg["neo4j_user"], cfg["neo4j_password"])
    )

    try:
        results = kg.search_exercises(
            target_part=target_part,
            exercise_text=exercise_text,
            excludes=excludes,
            limit=limit
        )
    except Exception as e:
        print(f"[Neo4j Error] {e}")
        return []
    finally:
        kg.close()

    evidences = []
    for r in results:
        evidences.append({
            "evidence_id": r.get("id"),
            "name": r.get("name"),
            "summary": (r.get("instructions") or "")[:200] + "...",
            "fields": {
                "utility": r.get("utility"),
                "mechanics": r.get("mechanics")
            },
            "body_part": r.get("body_part", ""),
            "target_muscles": r.get("target_muscles", []),
            "source": "Neo4j_Search"
        })

    return evidences


# agents/subflows.py -> _simple_diet_search

def _simple_diet_search(keyword: str, top_k: int = 5) -> List[Dict]:
    """
    [Fixed] 使用正确的 Diet KG 配置连接数据库
    """
    cfg = get_cfg()
    from tools.diet_tools.query import DietKGQuery 
    
    # ★★★ 关键修改：使用 diet_neo4j_xxx 配置 ★★★
    # 如果 cfg 里没有 diet_ 配置，说明 config 还没更新，这里做个 fallback 防止报错
    uri = cfg.get("diet_neo4j_uri", "neo4j+ssc://88f8ccae.databases.neo4j.io")
    user = cfg.get("diet_neo4j_user", "neo4j")
    pwd = cfg.get("diet_neo4j_password", "_BAD-vDc9fZjk17xTHjAUWaNPoxGxhh1X9oz2-fDffM")

    kg = DietKGQuery(uri, (user, pwd))
    
    try:
        # 调用之前修好的 search_items
        records = kg.search_items(keyword=keyword, limit=top_k)
        
        evidences = []
        for rec in records:
            # ... (后续处理逻辑不变) ...
            evidences.append({
                "evidence_id": str(rec.get("id")),
                "name": rec.get("name"),
                "summary": f"{rec.get('type')}: {rec.get('cal', 0)} kcal",
                "fields": rec,
                "source": "Diet_KG_Search"
            })
            
        return evidences
    except Exception as e:
        print(f"[Diet Search Error] {e}")
        return []
    finally:
        if hasattr(kg, "close"):
            kg.close()
# [Import needed] 确保引入了新定义的 Prompt 和 Schema
from agents.prompts import DIET_LOGGER_SYS,LOG_INTENT_ANALYZER_SYS
from agents.schemas import DIET_LOGGER_RESPONSE_FORMAT,LOG_INTENT_ANALYZER_RESPONSE_FORMAT

def subflow_log_update(
    state: Dict[str, Any],
    trace: list,
    chat_history: list = None
) -> Dict[str, Any]:
    """
    Final Version:
    - LLM only analyzes behavior intent
    - KG determines factual entities
    - WorkoutLog / DietLog strictly separated
    """
    if chat_history is None:
        chat_history = []

    user_input = state["user_input"]

    # ============================================================
    # 1. Context Stitching
    # ============================================================
    context_msgs = []
    for msg in reversed(chat_history):
        role = "User" if msg["role"] == "user" else "Assistant"
        context_msgs.append(f"{role}: {msg['content']}")
        if len(context_msgs) >= 3:
            break

    context_summary = "\n".join(reversed(context_msgs))
    full_context = f"{context_summary}\nUser (Current): {user_input}"

    print(f"[LogUpdate] Context:\n{full_context}")

    # ============================================================
    # 2. LLM: Log Intent Analyzer
    # ============================================================
    temp_state = state.copy()
    temp_state["user_input"] = full_context

    intent_out = run_agent(
        "LogIntentAnalyzer",
        LOG_INTENT_ANALYZER_SYS,
        temp_state,
        trace,
        response_format=LOG_INTENT_ANALYZER_RESPONSE_FORMAT
    )

    events = intent_out.get("events", [])
    if not events:
        state["decision"] = {"response": "我暂时没有检测到需要记录的行为。"}
        return state

    patch_ops = []

    print(events)
    # ============================================================
    # 3. Handle Each Event
    # ============================================================
    for evt in events:

        # --------------------------------------------------------
        # A. Workout Event → Exercise KG → WorkoutLog
        # --------------------------------------------------------
        if evt["event_type"] == "workout":
            body_part_hint = evt.get("body_part_hint")
            exercise_text = evt.get("exercise_text")
            if not exercise_text:
                continue

            try:
                # 模糊检索 Exercise KG
                kg_results = _simple_neo4j_search(
                    target_part=body_part_hint,
                    exercise_text = exercise_text,
                    excludes=[]
                )
            except Exception as e:
                print(f"[Workout KG Search Failed] {e}")
                continue

            if not kg_results:
                continue

            best = kg_results[0]
            print(best)
            workout_event = {
                "type": "WorkoutLog",
                "props": {
                    "summary": f"完成 {best.get('name')}",
                    "exercise_id": best.get("evidence_id"),
                    "body_part": best.get("body_part", ""),
                    "target_muscles": best.get("target_muscles", []),
                    "plan_id": "current_active",
                    "automatic_log": True
                }
            }

            patch_ops.append({"op": "append_event", "event": workout_event})

        # --------------------------------------------------------
        # B. Diet Event → Diet KG → DietLog
        # --------------------------------------------------------
        elif evt["event_type"] == "diet":
            food_texts = evt.get("food_texts") or []
            if not food_texts:
                continue

            # 中文 → 英文
            foods_en = _translate_keywords(food_texts)

            kg_context = ""
            for f in set(foods_en):
                recs = _simple_diet_search(f, top_k=3)
                for r in recs:
                    kg_context += f"- {r['name']}: {r.get('summary', '')}\n"

            if not kg_context:
                kg_context = "(No KG matches found, estimate based on general knowledge.)"

            logger_prompt = (
                f"{DIET_LOGGER_SYS}\n\n"
                f"### Knowledge Graph Data\n{kg_context}\n\n"
                f"### Conversation Context\n{context_summary}\n\n"
                f"### Current User Input\n{user_input}"
            )

            logger_out = run_agent(
                "DietLogger",
                logger_prompt,
                state,
                trace,
                response_format=DIET_LOGGER_RESPONSE_FORMAT
            )

            if logger_out.get("status") == "clarify":
                state["decision"] = {
                    "response": logger_out.get("feedback_response", "请补充饮食信息。")
                }
                return state

            log_data = logger_out.get("log_data", {})
            if not log_data:
                continue

            diet_event = {
                "type": "DietLog",
                "props": {
                    "summary": log_data.get("summary"),
                    "description": f"包含: {', '.join(log_data.get('foods', []))}",
                    "calories": log_data.get("total_calories", 0),
                    "protein": log_data.get("macros", {}).get("protein", 0),
                    "carb": log_data.get("macros", {}).get("carb", 0),
                    "fat": log_data.get("macros", {}).get("fat", 0),
                    "meal_type": log_data.get("meal_type", "snack"),
                    "automatic_log": True
                }
            }

            patch_ops.append({"op": "append_event", "event": diet_event})

    # ============================================================
    # 4. Commit Memory
    # ============================================================
    if not patch_ops:
        state["decision"] = {"response": "未能生成可记录的行为日志。"}
        return state

    state["memory_patch"] = patch_ops
    state["user_memory_graph_updated"] = apply_patch(
        state["user_memory_graph"],
        patch_ops
    )

    state["decision"] = {"response": "✅ 已为你记录本次行为。"}
    return state


# [NEW] 简单的翻译辅助函数
def _translate_keywords(keywords: List[str]) -> List[str]:
    if not keywords: 
        return []
    
    # 构造简单的翻译指令
    sys_prompt = (
        "You are a fitness translator. Translate the following food/exercise keywords from Chinese to English "
        "for database query. Keep it concise (e.g., '番茄炒蛋' -> 'Tomato Scrambled Eggs'). "
        "Output JSON: {\"translated\": [\"item1_en\", \"item2_en\"]}"
    )
    
    try:
        resp = chat(
            instruction=sys_prompt, 
            user_message=json.dumps(keywords, ensure_ascii=False), 
            response_format={"type": "json_object"}
        )
        data = json.loads(resp)
        return data.get("translated", [])
    except Exception as e:
        print(f"[Translation Failed] {e}")
        return keywords # 兜底返回原词