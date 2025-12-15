# memory/graph_store.py
import time
from copy import deepcopy
from typing import Any, Dict, List, Optional

def new_graph() -> Dict[str, Any]:
    return {"nodes": [], "edges": [], "events": []}

def apply_patch(g: Dict[str, Any], patch_ops: List[Dict[str, Any]]) -> Dict[str, Any]:
    g = deepcopy(g)
    now = int(time.time())
    node_index = {n.get("id"): n for n in g.get("nodes", [])}

    for op in patch_ops or []:
        typ = (op or {}).get("op")
        if typ == "add_node":
            node = {
                "id": op.get("id"),
                "type": op.get("type", "Unknown"),
                "props": op.get("props", {}),
                "last_updated": now
            }
            g.setdefault("nodes", []).append(node)
            node_index[node["id"]] = node

        elif typ == "add_edge":
            edge = {
                "id": op.get("id"),
                "type": op.get("type", "REL"),
                "from": op.get("from"),
                "to": op.get("to"),
                "props": op.get("props", {}),
                "last_updated": now
            }
            g.setdefault("edges", []).append(edge)

        elif typ == "update_node":
            nid = op.get("id")
            node = node_index.get(nid)
            if node is None:
                node = {"id": nid, "type": "Unknown", "props": {}, "last_updated": now}
                g.setdefault("nodes", []).append(node)
                node_index[nid] = node
            node["props"] = {**node.get("props", {}), **(op.get("props", {}) or {})}
            node["last_updated"] = now

        elif typ == "append_event":
            ev = op.get("event", {})
            g.setdefault("events", []).append({**ev, "ts": now})

    return g

def keyword_search(g: Dict[str, Any], q: str, topk: int = 30) -> List[Dict[str, Any]]:
    if not q.strip():
        return []
    q = q.lower()
    hits = []
    for n in g.get("nodes", []):
        blob = f"{n.get('id','')} {n.get('type','')} {n.get('props',{})}".lower()
        if q in blob:
            hits.append({"kind": "node", "id": n.get("id"), "type": n.get("type"), "props": n.get("props", {})})
    for e in g.get("edges", []):
        blob = f"{e.get('id','')} {e.get('type','')} {e.get('from','')} {e.get('to','')} {e.get('props',{})}".lower()
        if q in blob:
            hits.append({"kind": "edge", "id": e.get("id"), "type": e.get("type"),
                         "from": e.get("from"), "to": e.get("to"), "props": e.get("props", {})})
    return hits[:topk]

def _get_node(g: Dict[str, Any], node_id: str) -> Dict[str, Any]:
    for n in g.get("nodes", []) or []:
        if n.get("id") == node_id:
            return n
    return {}

def _get_nodes_by_type_prefix(g: Dict[str, Any], typ: str, id_prefix: str) -> List[Dict[str, Any]]:
    out = []
    for n in g.get("nodes", []) or []:
        if n.get("type") == typ and str(n.get("id", "")).startswith(id_prefix):
            out.append(n)
    return out

def summarize(g: Dict[str, Any], max_events: int = 8) -> Dict[str, Any]:
    """
    固定字段摘要：给 Router/MemoryRetriever 用，避免把整张图塞 LLM。
    """
    g = deepcopy(g or {})
    nodes = g.get("nodes", []) or []
    events = (g.get("events", []) or [])[-max_events:]

    profile = _get_node(g, "profile:basic").get("props", {})
    goal = _get_node(g, "goal:primary").get("props", {})
    pref_diet = _get_node(g, "pref:diet").get("props", {})
    pref_train = _get_node(g, "pref:training").get("props", {})
    c_time = _get_node(g, "constraint:time").get("props", {})
    c_eq = _get_node(g, "constraint:equipment").get("props", {})

    injuries = []
    for n in _get_nodes_by_type_prefix(g, "Injury", "injury:"):
        props = n.get("props", {}) or {}
        if props.get("status", "active") != "resolved":
            injuries.append({"id": n.get("id"), "name": props.get("name", ""), "severity": props.get("severity", ""), "avoid": props.get("avoid_motions", [])})

    symptoms = []
    for n in _get_nodes_by_type_prefix(g, "Symptom", "symptom:"):
        props = n.get("props", {}) or {}
        if props.get("status", "active") != "resolved":
            symptoms.append({"id": n.get("id"), "name": props.get("name", ""), "severity": props.get("severity", ""), "trigger": props.get("trigger", "")})

    return {
        "profile": profile,
        "goal_primary": goal,
        "preferences": {
            "diet": pref_diet,
            "training": pref_train
        },
        "constraints": {
            "time": c_time,
            "equipment": c_eq
        },
        "special": {
            "injuries_active": injuries[:8],
            "symptoms_active": symptoms[:8]
        },
        "recent_events": events
    }