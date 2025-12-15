# memory/persistence.py
import json
import os
import tempfile
from typing import Any, Dict

def ensure_graph(g: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(g, dict):
        g = {}
    g.setdefault("nodes", [])
    g.setdefault("edges", [])
    g.setdefault("events", [])
    return g

def load_graph(path: str, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return ensure_graph(default)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return ensure_graph(data)

def save_graph(path: str, graph: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    graph = ensure_graph(graph)

    # atomic write: write temp then replace
    fd, tmp_path = tempfile.mkstemp(prefix="tmp_", suffix=".json", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(graph, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass