# tools/kg_retrieval.py
import re
from typing import Any, Dict, List
from core.json_utils import dumps

def _simple_keyword_retrieve(kg: Dict[str, Any], query: str, topk: int = 8) -> List[Dict[str, Any]]:
    if not query:
        return []
    terms = [t.strip().lower() for t in re.split(r"[,\s/;，。]+", query) if t.strip()]
    scored = []
    for n in kg.get("nodes", []) or []:
        blob = (n.get("id","") + " " + n.get("type","") + " " + dumps(n.get("props", {}))).lower()
        score = sum(1 for t in terms if t and t in blob)
        if score > 0:
            scored.append((score, n))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for score, n in scored[:topk]:
        props = n.get("props", {}) or {}
        out.append({
            "id": n.get("id"),
            "type": n.get("type", "entity"),
            "name": props.get("name") or props.get("title") or n.get("id"),
            "props": props,
            "score": score,
            "source": "local_demo_kg"
        })
    return out

def retrieve_exercise_kg(args: Dict[str, Any], exercise_kg: Dict[str, Any]) -> List[Dict[str, Any]]:
    # TODO: 替换为真实检索（Neo4j / SPARQL / 向量检索 / 规则检索）
    q = (args or {}).get("query", "")
    topk = int((args or {}).get("topk", 8))
    if exercise_kg.get("nodes") and q:
        return _simple_keyword_retrieve(exercise_kg, q, topk)
    return []

def retrieve_nutrition_kg(args: Dict[str, Any], nutrition_kg: Dict[str, Any]) -> List[Dict[str, Any]]:
    q = (args or {}).get("query", "")
    topk = int((args or {}).get("topk", 12))
    if nutrition_kg.get("nodes") and q:
        return _simple_keyword_retrieve(nutrition_kg, q, topk)
    return []