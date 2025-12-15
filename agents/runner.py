# agents/runner.py
import time  # 新增
from typing import Any, Dict, Optional
from core.json_utils import safe_json_loads
from core.llm import chat
from agents.message_builder import build_user_message_for_agent

def run_agent(
    name: str,
    instruction: str,
    state: Dict[str, Any],
    trace: list,
    *,
    response_format: Optional[dict] = None,
) -> Any:
    # 1. 开始计时
    start_ts = time.time()
    
    user_message = build_user_message_for_agent(name, state)

    out_text = chat(
        instruction=instruction,
        user_message=user_message,
        model=state.get("cfg", {}).get("model", "gpt-4.1"),
        response_format=response_format,
    )

    out = safe_json_loads(out_text)
    
    # 2. 结束计时
    end_ts = time.time()
    duration_ms = int((end_ts - start_ts) * 1000)

    # 3. 写入带 step 和 ms 的完整 trace
    trace.append({
        "step": len(trace) + 1,  # 自动计算这是第几步
        "agent": name,
        "ms": duration_ms,       # 记录耗时
        "raw": out_text,
        "parsed": out,
        "response_format": response_format
    })
    
    return out