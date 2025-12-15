# agents/subflows.py
from typing import Any, Dict, Tuple, List
from agents.runner import run_agent
from tools.kg_retrieval import retrieve_exercise_kg, retrieve_nutrition_kg
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

def subflow_faq_exercise(state: Dict[str, Any], exercise_kg: Dict[str, Any]) -> Dict[str, Any]:
    evid = retrieve_exercise_kg({"query": state["user_input"], "topk": 8}, exercise_kg)
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

# --- 辅助函数：提取 Patch Ops ---
def _extract_patch_ops(agent_output: Any) -> List[Dict]:
    """兼容直接返回 List 或返回 {'ops': List} 的情况"""
    if isinstance(agent_output, dict) and "ops" in agent_output:
        return agent_output["ops"]
    if isinstance(agent_output, list):
        return agent_output
    return []

def subflow_plan_full(state: Dict[str, Any], trace: list,
                      exercise_kg: Dict[str, Any], nutrition_kg: Dict[str, Any]) -> Dict[str, Any]:
    state["task_frame"] = run_agent(
        "IntentParser", INTENT_PARSER_SYS, state, trace,
        response_format=INTENT_PARSER_RESPONSE_FORMAT
    )
    state["memory_retrieval"] = run_agent(
        "MemoryRetriever", MEMORY_RETRIEVER_SYS, state, trace,
        response_format=MEMORY_RETRIEVER_RESPONSE_FORMAT
    )
    state["draft_plan"] = run_agent(
        "PlanDraft", PLAN_DRAFT_SYS, state, trace,
        response_format=PLAN_DRAFT_RESPONSE_FORMAT
    )

    kout1 = run_agent(
        "KnowledgeRetriever#1", KNOWLEDGE_RETRIEVER_SYS, state, trace,
        response_format=KNOWLEDGE_RETRIEVER_RESPONSE_FORMAT
    )
    tool_calls = kout1.get("tool_calls", []) if isinstance(kout1, dict) else []
    if tool_calls:
        for call in tool_calls:
            tool = call.get("tool")
            args = call.get("args", {})
            if tool == "retrieve_exercise_kg":
                state["kg_evidence"]["exercise_kg"].extend(retrieve_exercise_kg(args, exercise_kg))
            elif tool == "retrieve_nutrition_kg":
                state["kg_evidence"]["nutrition_kg"].extend(retrieve_nutrition_kg(args, nutrition_kg))
        kout2 = run_agent(
            "KnowledgeRetriever#2", KNOWLEDGE_RETRIEVER_SYS, state, trace,
            response_format=KNOWLEDGE_RETRIEVER_RESPONSE_FORMAT
        )
        state["kg_evidence_normalized"] = kout2.get("evidence_cards", state["kg_evidence_normalized"])
        state["support_map"] = kout2.get("support_map", [])
    else:
        state["kg_evidence_normalized"] = kout1.get("evidence_cards", state["kg_evidence_normalized"])
        state["support_map"] = kout1.get("support_map", [])

    state["decision"] = run_agent(
        "Reasoner", REASONER_SYS, state, trace,
        response_format=REASONER_RESPONSE_FORMAT
    )

    # [FIX] 使用辅助函数提取 ops
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
    # [FIX] 使用辅助函数提取 ops
    raw_updater_out = run_agent(
        "MemoryUpdater", MEMORY_UPDATER_SYS, state, trace,
        response_format=MEMORY_UPDATER_RESPONSE_FORMAT
    )
    patch_ops = _extract_patch_ops(raw_updater_out)

    state["memory_patch"] = patch_ops
    updated = apply_patch(state["user_memory_graph"], patch_ops)
    state["user_memory_graph_updated"] = updated
    return state