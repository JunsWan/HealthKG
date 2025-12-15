# agents/message_builder.py
import json
from typing import Any, Dict

def build_user_message_for_agent(name: str, state: Dict[str, Any]) -> str:
    # 通用字段（多数 agent 都能用到）
    base = {
        "user_input": state.get("user_input", ""),
        "route": state.get("route", ""),
        "chat_context": state.get("chat_context", ""),
        "memory_summary": state.get("memory_summary", {}),
        "task_frame": state.get("task_frame", {}),
        "memory_retrieval": state.get("memory_retrieval", {}),
        "draft_plan": state.get("draft_plan", {}),
        "kg_evidence": state.get("kg_evidence", {}),
        "kg_evidence_normalized": state.get("kg_evidence_normalized", {}),
        "support_map": state.get("support_map", []),
        "decision": state.get("decision", {}),
    }

    # 按 agent 裁剪，避免塞太多导致跑偏/超长
    if name == "Router":
        payload = {
            "user_input": base["user_input"],
            "chat_context": base["chat_context"],
            "memory_summary": base["memory_summary"],
        }
    elif name == "IntentParser":
        payload = {
            "user_input": base["user_input"],
            "memory_summary": base["memory_summary"],
        }
    elif name.startswith("MemoryRetriever"):
        payload = {
            "user_input": base["user_input"],
            "task_frame": base["task_frame"],
            "user_memory_graph": state.get("user_memory_graph", {}),
        }
    elif name.startswith("PlanDraft"):
        payload = {
            "user_input": base["user_input"],
            "task_frame": base["task_frame"],
            "memory_retrieval": base["memory_retrieval"],
        }
    elif name.startswith("KnowledgeRetriever"):
        payload = {
            "draft_plan": base["draft_plan"],
            "kg_evidence": base["kg_evidence"],
        }
    elif name == "Reasoner":
        payload = {
            "task_frame": base["task_frame"],
            "memory_retrieval": base["memory_retrieval"],
            "draft_plan": base["draft_plan"],
            "evidence_cards": base["kg_evidence_normalized"],
            "support_map": base["support_map"],
        }
    elif name == "MemoryUpdater":
        payload = {
            "user_input": base["user_input"],
            "task_frame": base["task_frame"],
            "final_plan": (base.get("decision", {}) or {}).get("final_plan", {}),
            "user_memory_graph": state.get("user_memory_graph", {}),
        }
    else:
        payload = base

    return json.dumps(payload, ensure_ascii=False, indent=2)