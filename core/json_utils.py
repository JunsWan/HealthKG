# core/json_utils.py
import json
import re
from typing import Any

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)

def strip_code_fence(text: str) -> str:
    m = _JSON_FENCE_RE.search(text or "")
    return m.group(1).strip() if m else (text or "").strip()

def safe_json_loads(text: str) -> Any:
    raw = strip_code_fence(text)
    try:
        return json.loads(raw)
    except Exception:
        pass

    l, r = raw.find("{"), raw.rfind("}")
    if l != -1 and r != -1 and r > l:
        try:
            return json.loads(raw[l:r+1])
        except Exception:
            pass

    l, r = raw.find("["), raw.rfind("]")
    if l != -1 and r != -1 and r > l:
        try:
            return json.loads(raw[l:r+1])
        except Exception:
            pass

    raise ValueError(f"Cannot parse JSON from model output:\n{raw[:500]}...")

def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)