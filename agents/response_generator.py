# agents/response_generator.py
from typing import Dict, Any
from core.llm import chat
from core.json_utils import dumps
from agents.prompts import RESPONSE_GENERATOR_SYS

def render_response(route: str, state: Dict[str, Any], memory_summary: Dict[str, Any]) -> str:
    """
    输入：route + state（含 decision/evidence/memory_retrieval 等）
    输出：Markdown（给用户看的）
    """
    payload = {
        "route": route,
        "state": state,
        "memory_summary": memory_summary
    }
    return chat(RESPONSE_GENERATOR_SYS, dumps(payload))