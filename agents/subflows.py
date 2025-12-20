# agents/subflows.py
from typing import Any, Dict, Tuple, List
from agents.runner import run_agent
from core.config import get_cfg
from core.llm import chat

from tools.exercise_recommender import recommend_exercise_tool
from tools.kg_retrieval import retrieve_nutrition_kg # 饮食保持原样
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

# --- 辅助函数：提取 Patch Ops (修复保存失败问题) ---
def _extract_patch_ops(agent_output: Any) -> List[Dict]:
    """兼容直接返回 List 或返回 {'ops': List} 的情况"""
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


import json
from core.llm import chat

# 1. 定义你的标准部位集合 (作为常量)
VALID_BODY_PARTS = [
    'Chest', 'Arm', 'Neck', 'Waist', 'Calf', 'ForeArm', 
    'Hips', 'Should', 'Thigh', 'Back'
]

def _extract_search_criteria(user_text: str) -> dict:
    """
    升级版：提取结构化搜索条件 (包含目标部位、包含词、排除词)
    """
    # 将列表转为字符串放入 Prompt
    valid_parts_str = ", ".join(VALID_BODY_PARTS)
    
    sys_prompt = (
        f"You are a query parser for an exercise database. "
        f"The database only accepts these specific body parts: [{valid_parts_str}].\n"
        "Your task:\n"
        "1. Identify the target body part from user input and map it to ONE of the valid parts above. "
        "(e.g., 'Legs' -> 'Thigh' or 'Calf' based on context, usually 'Thigh'; 'Abs' -> 'Waist').\n"
        "2. Identify any specific exercise names the user mentions (e.g., 'Squat', 'Bench Press').\n"
        "3. Identify negative constraints (what they want to AVOID).\n"
        "4. Return a JSON object with keys: 'target_part', 'keywords_include', 'keywords_exclude'.\n\n"
        "Examples:\n"
        "User: '我想练胸' -> {\"target_part\": \"Chest\", \"keywords_include\": [], \"keywords_exclude\": []}\n"
        "User: '我想练腿，但不想做深蹲' -> {\"target_part\": \"Thigh\", \"keywords_include\": [], \"keywords_exclude\": [\"Squat\"]}\n"
        "User: '推荐几个哑铃二头动作' -> {\"target_part\": \"Arm\", \"keywords_include\": [\"Dumbbell\", \"Biceps\"], \"keywords_exclude\": []}\n"
        "User: '背部训练' -> {\"target_part\": \"Back\", \"keywords_include\": [], \"keywords_exclude\": []}\n"
    )

    try:
        # 强制要求 JSON 格式
        resp = chat(instruction=sys_prompt, user_message=user_text, response_format={"type": "json_object"})
        criteria = json.loads(resp)
        return criteria
    except Exception as e:
        print(f"[Query Extraction Failed] {e}")
        return {"target_part": None, "keywords_include": [], "keywords_exclude": []}

# ==========================================
# 修改：FAQ Subflow (适配新的结构化查询)
# ==========================================
# def subflow_faq_exercise(state: Dict[str, Any], exercise_kg: Dict[str, Any]) -> Dict[str, Any]:
#     user_input = state["user_input"]
    
#     # 1. 结构化提取
#     criteria = _extract_search_criteria(user_input)
#     print(f"[FAQ] Criteria: {criteria}")
    
#     target_part = criteria.get("target_part")
#     excludes = criteria.get("keywords_exclude", [])
    
#     evid = []
#     try:
#         # 2. 调用 Neo4j (需要修改 simple_neo4j_search 接受这些参数)
#         if target_part:
#             # 这里我们需要稍微改一下 _simple_neo4j_search 的传参
#             evid = _simple_neo4j_search(target_part, excludes=excludes)
#         print(evid)
#         if not evid:
#             # Fallback
#             from tools.kg_retrieval import retrieve_exercise_kg as mock_retrieve
#             evid = mock_retrieve({"query": user_input, "topk": 5}, exercise_kg)
            
#     except Exception as e:
#         print(f"[FAQ] Search failed: {e}")
#         from tools.kg_retrieval import retrieve_exercise_kg as mock_retrieve
#         evid = mock_retrieve({"query": user_input, "topk": 5}, exercise_kg)

#     state["kg_evidence"]["exercise_kg"] = evid
#     return state

# 定义标准健身房器械列表
GYM_PRESET = ["Barbell", "Dumbbell", "Cable", "Lever", "Smith Machine", "Sled", "Weighted", "Suspended"]

def subflow_faq_exercise(state: Dict[str, Any], exercise_kg: Dict[str, Any]) -> Dict[str, Any]:
    """
    升级版 FAQ: 智能设备感知 (Smart Equipment Awareness)
    """
    user_input = state["user_input"]
    
    # 1. 准备个性化数据
    mem_sum = state.get("memory_summary", {})
    user_injuries = mem_sum.get("special", {}).get("injuries_active", [])
    
    # 提取器械 (防御性读取)
    user_equip = (
        mem_sum.get("constraints", {}).get("equipment") or 
        mem_sum.get("preferences", {}).get("equipment") or 
        []
    )
    
    # 提取历史 (用于计算疲劳)
    raw_events = state["user_memory_graph"].get("events", [])
    workout_history = []
    for e in raw_events:
        if e.get("type") == "WorkoutLog":
            props = e.get("props", {})
            if "timestamp" not in props and "ts" in e:
                from datetime import datetime
                props["timestamp"] = datetime.fromtimestamp(e["ts"]).isoformat()
            workout_history.append(props)

    # 2. 解析查询意图
    criteria = _extract_search_criteria(user_input)
    target_part = criteria.get("target_part")
    excludes = criteria.get("keywords_exclude", [])
    
    print(f"[FAQ] Analysis -> Target: {target_part}, Excludes: {excludes}")

    evid = []
    
    # ====================================================
    # 3. 分支策略
    # ====================================================
    if target_part:
        print(f"[FAQ] Detected body part '{target_part}', using Recommendation Tool...")
        
        # ★★★ 新增：智能器械兜底 (Smart Fallback) ★★★
        # 如果不知道用户有什么器械，FAQ 流程不打断，而是默认给“全套”，
        # 这样用户至少能看到“杠铃卧推”这样的经典动作，而不是查不到数据。
        current_equip_context = user_equip
        equip_warning = False
        
        if not current_equip_context:
            print("[FAQ] No equipment found in memory. Defaulting to GYM PRESET.")
            current_equip_context = GYM_PRESET
            equip_warning = True

        try:
            tool_args = {
                "target_body_part": target_part,
                "injury_body_part": user_injuries[0] if user_injuries else None,
                "available_equipment": current_equip_context, # 使用兜底后的列表
                "history": workout_history,
                "topk": 5
            }
            
            recs = recommend_exercise_tool(tool_args)
            
            # 手动执行 Excludes 过滤
            if excludes:
                filtered_recs = []
                for r in recs:
                    if not any(ex.lower() in r.get("name", "").lower() for ex in excludes):
                        filtered_recs.append(r)
                evid = filtered_recs
            else:
                evid = recs
            
            # ★ 如果使用了默认器械，我们在 Evidence 里注入一条“系统提示”
            # 这样 ResponseGenerator 生成回复时，有机会告诉用户“这是基于健身房条件的推荐”
            if equip_warning and evid:
                # 这是一个 Hack，把提示作为一条特殊的 Evidence 塞进去
                evid.insert(0, {
                    "source": "SYSTEM_NOTE",
                    "name": "Note",
                    "summary": "【注意】因暂无您的器械记录，以下推荐默认基于「健身房全器械」环境。如需「居家/徒手」推荐，请告知我您的器械。",
                    "fields": {}
                })
                
        except Exception as e:
            print(f"[FAQ] Recommend tool failed: {e}")
            evid = []

    # 分支 B: 关键词搜索 (Fallback)
    if not evid:
        search_kw = target_part if target_part else _extract_search_keyword(user_input)
        if search_kw:
            print(f"[FAQ] Falling back to Keyword Search for: {search_kw}")
            evid = _simple_neo4j_search(search_kw, excludes=excludes)
    
    # 分支 C: Mock 兜底
    if not evid:
        from tools.kg_retrieval import retrieve_exercise_kg as mock_retrieve
        evid = mock_retrieve({"query": user_input, "topk": 5}, exercise_kg)

    state["kg_evidence"]["exercise_kg"] = evid
    return state

def subflow_faq_food(state: Dict[str, Any], nutrition_kg: Dict[str, Any]) -> Dict[str, Any]:
    evid = retrieve_nutrition_kg({"query": state["user_input"], "topk": 12}, nutrition_kg)
    state["kg_evidence"]["nutrition_kg"] = evid
    return state

def subflow_query_memory(state: Dict[str, Any], trace: list) -> Dict[str, Any]:
    state["memory_retrieval"] = run_agent(
        "MemoryRetriever", MEMORY_RETRIEVER_SYS, state, trace,
        response_format=MEMORY_RETRIEVER_RESPONSE_FORMAT
    )
    return state

# agents/subflows.py

def subflow_plan_full(state: Dict[str, Any], trace: list,
                      exercise_kg: Dict[str, Any], nutrition_kg: Dict[str, Any],
                      route_name: str = "plan_both") -> Dict[str, Any]:
    """
    升级版 Plan Flow (Final Fix):
    1. 上下文拼接 (Context Stitching): 解决多轮对话信息丢失问题
    2. 徒手逻辑 (Body Weight): 解决“没器械”导致的死循环
    3. 器械拦截: 只有真·不知道且没说徒手时才拦截
    """
    
    # === 0. 设置逻辑开关 ===
    need_exercise = route_name in ["plan_workout", "plan_both"]
    need_diet = route_name in ["plan_diet", "plan_both"]
    
    # 准备历史记录
    workout_history = []
    if need_exercise:
        raw_events = state["user_memory_graph"].get("events", [])
        for e in raw_events:
            if e.get("type") == "WorkoutLog":
                props = e.get("props", {})
                if "timestamp" not in props and "ts" in e:
                    from datetime import datetime
                    props["timestamp"] = datetime.fromtimestamp(e["ts"]).isoformat()
                workout_history.append(props)

    # 1. 意图解析 & 记忆检索
    state["task_frame"] = run_agent("IntentParser", INTENT_PARSER_SYS, state, trace, response_format=INTENT_PARSER_RESPONSE_FORMAT)
    task_frame = state["task_frame"]
    state["memory_retrieval"] = run_agent("MemoryRetriever", MEMORY_RETRIEVER_SYS, state, trace, response_format=MEMORY_RETRIEVER_RESPONSE_FORMAT)

    # ============================================================
    # ★ 全局上下文构建 (Context Stitching)
    # ============================================================
    # 把它提到最前面，供 equipment 和 muscles 共同使用
    # 拼接最近 3 条 User 消息 + 当前 Input
    recent_user_msgs = []
    for t in reversed(trace):
        if t["role"] == "user":
            recent_user_msgs.append(t["content"])
        if len(recent_user_msgs) >= 3: break
    
    context_text = " ".join(reversed(recent_user_msgs))
    if state["user_input"] not in context_text:
        context_text += " " + state["user_input"]
    
    print(f"[Plan] Full Context: {context_text}")

    # ============================================================
    # ★ Step 2.5: 主动预检索 (Pre-retrieval)
    # ============================================================
    recommended_candidates = []
    
    if need_exercise:
        # --- A. 智能器械提取 (Fix: 上下文 + 徒手判定) ---
        
        # 1. 收集来源
        current_equip = task_frame.get("constraints", {}).get("equipment", [])
        if not isinstance(current_equip, list): current_equip = []
        
        mem_constraints = state.get("memory_summary", {}).get("constraints", {})
        stored_equip = mem_constraints.get("equipment", [])
        if not isinstance(stored_equip, list): stored_equip = []

        # 2. 合并
        combined_equip = list(set(current_equip + stored_equip))
        
        # 3. [关键修复] 如果合并后还是空的，利用 Context 再次检查
        if not combined_equip:
            # 这里的逻辑是：如果 IntentParser 没提取到，我们用简单的规则在 Context 里找找漏网之鱼
            # 场景一：用户说了 "我有哑铃" 但被漏掉了
            common_gear = ["哑铃", "Dumbbell", "弹力带", "Band", "壶铃", "Kettlebell", "杠铃", "Barbell"]
            for gear in common_gear:
                if gear in context_text or gear.lower() in context_text.lower():
                    # 简单映射回标准名 (这里只做简单示例，IntentParser 应该做好的)
                    if "哑" in gear: combined_equip.append("Dumbbell")
                    if "弹" in gear: combined_equip.append("Resistance Band")
            
            # 场景二：用户说了 "没器械"、"在家" -> 视为 Body Weight
            # 这样就不会触发拦截器了！
            negative_keywords = ["没器械", "没有器械", "徒手", "nothing", "none", "bodyweight", "无器械"]
            # 如果包含否定词，或者只包含 "在家" 且没提其他器械
            is_no_gear = any(kw in context_text.lower() for kw in negative_keywords)
            
            if is_no_gear:
                print("[Plan] Detected 'No Equipment' context -> Setting to Body Weight.")
                combined_equip = ["Body Weight"]

        # 4. 再次检查拦截器
        if not combined_equip:
            print("[Plan] Critical Info Missing: Equipment. Triggering clarification.")
            clarification_msg = (
                "为了定制最合适的计划，还需要确认您的训练环境：\n\n"
                "❓ **请问您家里有哪些可用器械？**\n"
                "- 例如：哑铃、弹力带、瑜伽垫\n"
                "- **如果完全没有器械，也请说明（我会为您安排徒手训练）**\n\n"
                "确认后，我会为您生成详细清单。"
            )
            state["decision"] = {"response": clarification_msg, "thought": "缺少器械信息，发起追问"}
            state["draft_plan"] = {} 
            state["kg_evidence"] = {}
            return state

        # 通过拦截，赋值
        user_equip = combined_equip
        print(f"[Plan] Final Equipment List: {user_equip}")

        # --- B. 提取目标部位 (使用 Context) ---
        target_muscles = task_frame.get("entities", {}).get("muscle_groups", [])
        user_injuries = task_frame.get("constraints", {}).get("injury", [])
        
        if not target_muscles:
            # 使用之前构建好的 context_text 进行提取
            print(f"[Plan] Extracting muscle criteria from Context...")
            criteria = _extract_search_criteria(context_text) 
            if criteria.get("target_part"):
                target_muscles = [criteria["target_part"]]
        
        # --- C. 兜底策略 ---
        if not target_muscles:
            print("[Plan] No specific muscle detected. Defaulting to FULL BODY.")
            target_muscles = ["Chest", "Back", "Thigh"]

        # --- D. 循环调用推荐工具 ---
        for muscle in target_muscles:
            args = {
                "target_body_part": muscle,
                "injury_body_part": user_injuries[0] if user_injuries else None,
                "available_equipment": user_equip,
                "history": workout_history,
                "topk": 5
            }
            try:
                recs = recommend_exercise_tool(args)
                recommended_candidates.extend(recs)
            except Exception as e:
                print(f"[Plan] Recommend failed for {muscle}: {e}")

    state["kg_evidence"]["exercise_kg"] = recommended_candidates

    # ============================================================
    # 3. 生成草案 (PlanDraft)
    # ============================================================
    task_instruction = ""
    if route_name == "plan_workout":
        task_instruction = "当前任务：仅生成【训练计划】。Workout部分必须优先使用 KG Evidence 中的推荐动作。"
    elif route_name == "plan_diet":
        task_instruction = "当前任务：仅生成【饮食计划】。"
    else:
        task_instruction = "当前任务：生成【训练+饮食】综合方案。Workout部分必须优先使用 KG Evidence 中的推荐动作。"

    current_prompt = PLAN_DRAFT_SYS + f"\n\n### 动态指令\n{task_instruction}"

    state["draft_plan"] = run_agent("PlanDraft", current_prompt, state, trace, response_format=PLAN_DRAFT_RESPONSE_FORMAT)

    # ============================================================
    # 4. 补充知识检索 (KnowledgeRetriever)
    # ============================================================
    kout1 = run_agent("KnowledgeRetriever#1", KNOWLEDGE_RETRIEVER_SYS, state, trace, response_format=KNOWLEDGE_RETRIEVER_RESPONSE_FORMAT)
    tool_calls = kout1.get("tool_calls", []) if isinstance(kout1, dict) else []
    
    if tool_calls:
        for call in tool_calls:
            tool = call.get("tool")
            args = call.get("args", {})
            if tool == "retrieve_exercise_kg" and need_exercise:
                args["history"] = workout_history
                state["kg_evidence"]["exercise_kg"].extend(recommend_exercise_tool(args))
            elif tool == "retrieve_nutrition_kg" and need_diet:
                state["kg_evidence"]["nutrition_kg"].extend(retrieve_nutrition_kg(args, nutrition_kg))
        
        kout2 = run_agent("KnowledgeRetriever#2", KNOWLEDGE_RETRIEVER_SYS, state, trace, response_format=KNOWLEDGE_RETRIEVER_RESPONSE_FORMAT)
        state["kg_evidence_normalized"] = kout2.get("evidence_cards", state["kg_evidence_normalized"])
    else:
        state["kg_evidence_normalized"] = kout1.get("evidence_cards", state["kg_evidence_normalized"])

    # 5. 推理决策
    state["decision"] = run_agent("Reasoner", REASONER_SYS, state, trace, response_format=REASONER_RESPONSE_FORMAT)
    
    return state

# 2. 新增一个专门用于【保存】的 Subflow
def subflow_commit_plan(state: Dict[str, Any], trace: list, accepted_plan_text: str) -> Dict[str, Any]:
    """
    当用户点击“采纳”后调用的函数：
    强行调用 MemoryUpdater，把确认的计划写入图谱
    """
    
    # 我们需要构造一个临时的 state 或 prompt，告诉 MemoryUpdater：用户已经同意了这个计划
    # 把计划内容注入到 user_input 或者作为 system prompt 的背景
    
    # 这里的 trick 是：我们伪造一条 trace，让 Updater 以为这是刚刚发生的对话结论
    # 或者直接把 plan 放在 state["decision"]["response"] 里，Updater 会去读它
    
    # 确保 state 里有 plan
    state["decision"]["response"] = accepted_plan_text
    
    print("[System] Committing plan to memory...")

    # 运行 MemoryUpdater
    raw_updater_out = run_agent(
        "MemoryUpdater", MEMORY_UPDATER_SYS, state, trace,
        response_format=MEMORY_UPDATER_RESPONSE_FORMAT
    )
    
    # 提取 Ops 并应用
    patch_ops = _extract_patch_ops(raw_updater_out)
    state["memory_patch"] = patch_ops
    updated = apply_patch(state["user_memory_graph"], patch_ops)
    state["user_memory_graph_updated"] = updated
    
    return state

def subflow_log_update(state: Dict[str, Any], trace: list) -> Dict[str, Any]:
    # 同样应用辅助函数
    raw_updater_out = run_agent(
        "MemoryUpdater", MEMORY_UPDATER_SYS, state, trace,
        response_format=MEMORY_UPDATER_RESPONSE_FORMAT
    )
    patch_ops = _extract_patch_ops(raw_updater_out)
    
    state["memory_patch"] = patch_ops
    updated = apply_patch(state["user_memory_graph"], patch_ops)
    state["user_memory_graph_updated"] = updated
    return state

def _simple_neo4j_search(target_part: str, excludes: list = None):
    """
    Wrapper: 连接 Neo4j 并执行搜索
    """
    from tools.exercise_tools.query import ExerciseKGQuery
    cfg = get_cfg()
    
    # 防止 None 传进去报错
    if excludes is None:
        excludes = []

    kg = ExerciseKGQuery(
        cfg["neo4j_uri"], 
        (cfg["neo4j_user"], cfg["neo4j_password"])
    )
    
    try:
        # ★★★ 关键点：这里把 excludes 传下去 ★★★
        results = kg.search_exercises(keyword=target_part, excludes=excludes, limit=5)
    except Exception as e:
        print(f"[Neo4j Error] {e}")
        return []
    finally:
        kg.close()
        
    # 格式化结果 (和之前一样)
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
            "source": "Neo4j_Search"
        })
    return evidences