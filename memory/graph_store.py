# memory/graph_store.py
import time
import re
from copy import deepcopy
from datetime import datetime, timedelta
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
            nid = op.get("id")
            if nid and nid not in node_index:
                node = {"id": nid, "type": op.get("type", "Unknown"), "props": op.get("props", {}), "last_updated": now}
                g.setdefault("nodes", []).append(node)
                node_index[nid] = node
        elif typ == "update_node":
            nid = op.get("id")
            node = node_index.get(nid)
            if node is None:
                node = {"id": nid, "type": op.get("type", "Unknown"), "props": {}, "last_updated": now}
                g.setdefault("nodes", []).append(node)
                node_index[nid] = node
            node["props"] = {**node.get("props", {}), **(op.get("props", {}) or {})}
            node["last_updated"] = now
        elif typ == "add_edge":
            g.setdefault("edges", []).append({"id": op.get("id"), "type": op.get("type", "REL"), "from": op.get("from"), "to": op.get("to"), "props": op.get("props", {}), "last_updated": now})
        elif typ == "append_event":
            ev = op.get("event", {})
            if "ts" not in ev: ev["ts"] = now
            g.setdefault("events", []).append(ev)
    return g

def _get_node_props(g: Dict[str, Any], node_id: str) -> Dict[str, Any]:
    for n in g.get("nodes", []) or []:
        if n.get("id") == node_id: return n.get("props", {})
    return {}

# 计算运动计划进度的辅助函数 (保持不变，够健壮)
def _calculate_plan_progress(events: List[Dict], plan_props: Dict) -> Dict[str, Any]:
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    monday = now - timedelta(days=now.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    monday_ts = monday.timestamp()

    done_dates = set()
    is_today_done = False
    for e in events:
        if e.get("type") == "WorkoutLog" and e.get("ts", 0) >= monday_ts:
            log_date = datetime.fromtimestamp(e.get("ts")).strftime("%Y-%m-%d")
            done_dates.add(log_date)
            if log_date == today_str: is_today_done = True
    done_count = len(done_dates)

    # 优先找 workout_plan 字段，其次找 details
    wp = plan_props.get("workout_plan", {})
    dt = plan_props.get("details", {})
    
    sessions = []
    if "sessions" in wp: sessions = wp["sessions"]
    elif "sessions" in dt: sessions = dt["sessions"]
    elif "sessions" in plan_props: sessions = plan_props["sessions"]
    
    schedule_text = ""
    if "schedule" in wp: schedule_text = wp["schedule"]
    elif "schedule" in dt: schedule_text = dt["schedule"]
    elif "schedule" in plan_props: schedule_text = plan_props.get("schedule", "")
    else: schedule_text = plan_props.get("summary", "")

    target_match = re.search(r"每周(\d+)[次天]", schedule_text)
    if not target_match: target_match = re.search(r"(\d+)\s*times/week", schedule_text)
    target_count = int(target_match.group(1)) if target_match else 3

    next_session_name = "自由训练"
    current_items = []
    
    if sessions:
        idx = done_count % len(sessions)
        if done_count >= target_count and is_today_done:
             next_session_name = "🎉 本周目标达成"
             current_items = []
        else:
            s = sessions[idx]
            next_session_name = s.get("name", f"Session {idx+1}")
            if "focus" in s: next_session_name += f" ({s['focus']})"
            current_items = s.get("items", [])

    return {
        "done_count": done_count,
        "target_count": target_count,
        "progress_pct": min(1.0, done_count / target_count) if target_count > 0 else 0,
        "next_session": next_session_name,
        "is_today_done": is_today_done,
        "current_items": current_items
    }

def summarize(g: Dict[str, Any]) -> Dict[str, Any]:
    """
    核心修改：分别提取 Active Workout Plan 和 Active Diet Plan
    """
    g = deepcopy(g or {})
    nodes = g.get("nodes", []) or []
    events = g.get("events", []) or []

    # Nodes
    profile = _get_node_props(g, "profile:basic")
    goal = _get_node_props(g, "goal:primary")
    prefs = {"diet": _get_node_props(g, "pref:diet"), "training": _get_node_props(g, "pref:training")}
    c_eq_props = _get_node_props(g, "constraint:equipment")
    raw_eq = c_eq_props.get("items") or c_eq_props.get("equipment") or []
    if isinstance(raw_eq, str): raw_eq = [raw_eq]
    constraints = {"time": _get_node_props(g, "constraint:time"), "equipment": raw_eq}

    injuries_active, symptoms_active = [], []
    for n in nodes:
        props = n.get("props", {})
        if props.get("status") == "resolved": continue
        if n.get("type") == "Injury" or str(n.get("id")).startswith("injury:"):
            injuries_active.append(props.get("name") or str(n.get("id")).replace("injury:", ""))
        if n.get("type") == "Symptom" or str(n.get("id")).startswith("symptom:"):
            symptoms_active.append(props.get("name") or str(n.get("id")).replace("symptom:", ""))

    # ★★★ 核心修改：分离运动和饮食计划 ★★★
    active_workout = {}
    active_diet = {}
    
    # 倒序遍历，找到最新的“含运动”的计划和“含饮食”的计划
    # 它们可能是同一个 Event，也可能是不同的
    found_workout = False
    found_diet = False
    
    for e in reversed(events):
        if e.get("type") == "Plan":
            p_props = e.get("props", {})
            p_type = p_props.get("plan_type", "").lower()
            
            s_date = p_props.get("created_at")
            if not s_date and e.get("ts"):
                s_date = datetime.fromtimestamp(e["ts"]).strftime("%Y-%m-%d")

            # --- 提取运动计划 ---
            # 条件：还没找到最新 && (类型包含workout 或 有workout_plan字段 或 有sessions字段)
            has_workout_data = "workout_plan" in p_props or "sessions" in p_props.get("details", {}) or "sessions" in p_props
            is_workout_type = "workout" in p_type or "训练" in p_type
            
            if not found_workout and (has_workout_data or is_workout_type):
                # 计算进度
                progress_data = _calculate_plan_progress(events, p_props)
                
                # 如果是 Plan Both，提取 workout_plan 里的 summary；否则用顶层 summary
                w_summary = p_props.get("workout_plan", {}).get("summary") or p_props.get("summary", "")
                
                active_workout = {
                    "is_active": True,
                    "title": "训练计划", # 统一显示名称
                    "start_date": s_date,
                    "summary": w_summary,
                    # 进度相关
                    "next_session": progress_data["next_session"],
                    "done_count": progress_data["done_count"],
                    "target_count": progress_data["target_count"],
                    "progress_pct": progress_data["progress_pct"],
                    "is_today_done": progress_data["is_today_done"],
                    "current_items": progress_data["current_items"]
                }
                found_workout = True

            # --- 提取饮食计划 ---
            # 条件：还没找到最新 && (类型包含diet 或 有diet_plan字段)
            has_diet_data = "diet_plan" in p_props
            is_diet_type = "diet" in p_type or "饮食" in p_type or "nutrition" in p_type
            
            if not found_diet and (has_diet_data or is_diet_type):
                d_summary = p_props.get("diet_plan", {}).get("summary") or p_props.get("summary", "")
                d_details = p_props.get("diet_plan", {}) or p_props # 如果是纯饮食计划，props本身就是detail
                
                active_diet = {
                    "is_active": True,
                    "title": "饮食建议",
                    "start_date": s_date,
                    "summary": d_summary,
                    "details": d_details # 仅作存储引用
                }
                found_diet = True
        
        if found_workout and found_diet:
            break

    return {
        "profile": profile, "goal_primary": goal, "preferences": prefs, "constraints": constraints,
        "special": {"injuries_active": injuries_active, "symptoms_active": symptoms_active},
        
        # 返回分离的计划
        "active_workout_plan": active_workout,
        "active_diet_plan": active_diet,
        
        # 兼容旧代码 (可选，如果还有地方用 active_plan)
        "active_plan": active_workout if active_workout else active_diet, 
        
        "recent_events": events[-10:]
    }