# agents/router.py
from typing import Dict, Any
from agents.runner import run_agent
from agents.prompts import ROUTER_SYS
from memory.graph_store import summarize
from agents.schemas import ROUTER_RESPONSE_FORMAT

def route(user_input: str, messages: list, user_graph: Dict[str, Any], trace: list) -> Dict[str, Any]:
    # 给 Router 的上下文：最近几轮对话 + 记忆摘要
    recent = messages[-15:] if len(messages) > 15 else messages
    state = {
        "user_input": user_input,
        "chat_context": recent,
        "memory_summary": summarize(user_graph),
    }
    return run_agent("Router", ROUTER_SYS, state, trace, response_format=ROUTER_RESPONSE_FORMAT)