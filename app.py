# app.py
import os
import time
import streamlit as st
from core.config import get_cfg
from datetime import datetime
from memory.persistence import load_graph, save_graph
from memory.graph_store import new_graph, summarize
from agents.router import route
from agents.subflows import (
    ensure_pipeline_state,
    subflow_faq_exercise, subflow_faq_food, subflow_query_memory,
    subflow_log_update,
    # 引入修改后的两个函数
    subflow_plan_full, subflow_commit_plan
)
from agents.response_generator import render_response

st.set_page_config(page_title="Multi-Agent Demo", layout="wide")
cfg = get_cfg()

DATA_DIR = os.getenv("DATA_DIR", "./data")
PATH_USER = os.path.join(DATA_DIR, "user_memory_graph.json")
PATH_EX = os.path.join(DATA_DIR, "exercise_kg.json")
PATH_NU = os.path.join(DATA_DIR, "nutrition_kg.json")

# === Session Init ===
if "messages" not in st.session_state:
    st.session_state.messages = []
if "trace" not in st.session_state:
    st.session_state.trace = []
if "user_memory_graph" not in st.session_state:
    st.session_state.user_memory_graph = load_graph(PATH_USER, new_graph())
if "exercise_kg" not in st.session_state:
    st.session_state.exercise_kg = load_graph(PATH_EX, new_graph())
if "nutrition_kg" not in st.session_state:
    st.session_state.nutrition_kg = load_graph(PATH_NU, new_graph())

# ★★★ 新增：暂存待确认的计划 ★★★
if "pending_plan" not in st.session_state:
    st.session_state.pending_plan = None 

st.title("多智能体健身饮食助手")

def _fmt_ts(ts: int) -> str:
    if not ts:
        return ""
    # 你服务器时区不一定是 JST，这里按本地时间显示；想固定日本可改 timezone(timedelta(hours=9))
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M")

def _infer_last_record(events: list) -> dict:
    if not events:
        return {"ts": 0, "type": "", "summary": ""}
    last = max(events, key=lambda x: int(x.get("ts", 0) or 0))
    return {
        "ts": int(last.get("ts", 0) or 0),
        "type": str(last.get("type", "") or ""),
        "summary": str((last.get("props", {}) or {}).get("summary", "") or "")
    }

def generate_greeting(user_graph: dict) -> str:
    s = summarize(user_graph)
    profile = s.get("profile", {}) or {}
    goal = s.get("goal_primary", {}) or {}
    prefs = s.get("preferences", {}) or {}
    special = s.get("special", {}) or {}
    events = (user_graph.get("events", []) or [])

    name = profile.get("name") or profile.get("nickname") or ""
    last = _infer_last_record(events)
    last_time = _fmt_ts(last["ts"])
    last_type = last["type"]

    # 判断是不是“新用户”：没有任何事件 + 关键字段都空
    looks_new = (len(events) == 0) and (not name) and (not goal.get("goal_type")) and (not prefs.get("diet")) and (not prefs.get("training"))

    if looks_new:
        return (
            "你好，我是你的多智能体健身/饮食助手。\n\n"
            "我可以帮你做这些事：\n"
            "- **咨询**：动作练哪里、怎么做、注意事项；食物的营养/搭配思路\n"
            "- **生成方案**：训练计划 / 饮食模板 / 综合一周安排\n"
            "- **查记录**：你之前练了什么、吃了什么、指标变化\n"
            "- **记住偏好与特殊情况**：比如器械条件、作息、伤病/不适\n\n"
            "你可以直接在输入框说需求（比如“给我一周四练计划”“我今天胸推练了这些，帮我记录”）。\n"
            "如果还没配置模型，请先去 **Settings** 填写 API Key 和 Base URL。"
        )

    # 老用户问候
    goal_text = ""
    if goal.get("goal_type") or goal.get("target_weight_kg"):
        gt = goal.get("goal_type", "")
        tw = goal.get("target_weight_kg", 0) or 0
        goal_text = f"目标：{gt}" + (f"，目标体重 {tw}kg" if tw else "")

    injury_cnt = len((special.get("injuries_active") or []))
    symptom_cnt = len((special.get("symptoms_active") or []))
    special_text = ""
    if injury_cnt or symptom_cnt:
        special_text = f"（我记得你有 {injury_cnt} 个伤病 / {symptom_cnt} 个不适需要留意）"

    who = f"{name}，" if name else ""
    last_line = f"你上次记录是在 **{last_time}**" if last_time else "我看到你之前有一些记录"
    if last_type:
        last_line += f"（{last_type}）"

    return (
        f"欢迎回来，{who}{last_line}。\n"
        f"{goal_text}{special_text}\n\n"
        "你今天想：\n"
        "- 直接**咨询一个问题**（动作/食物/恢复）\n"
        "- **查一下历史记录**\n"
        "- 或者**生成一个训练/饮食方案**？"
    )

# Show chat history
# 只在第一次进入、且聊天记录为空时插入欢迎语
if len(st.session_state.messages) == 0:
    greet = generate_greeting(st.session_state.user_memory_graph)
    st.session_state.messages.append({"role": "assistant", "content": greet})

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# === Input Handling ===
user_text = st.chat_input("输入你的问题/需求...")

if user_text:
    if not cfg["api_key"]:
        st.error("请先配置 API Key")
        st.stop()

    # ★★★ 关键逻辑：用户只要一说话，就视为“未采纳/想修改”，清空旧的待确认计划
    if st.session_state.pending_plan:
        st.session_state.pending_plan = None
    
    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    trace = st.session_state.trace
    user_graph = st.session_state.user_memory_graph

    with st.spinner("Router 思考中..."):
        r = route(user_text, st.session_state.messages, user_graph, trace)

    if r.get("need_clarify"):
        qs = r.get("clarify_questions", [])
        reply = "我还需要确认几件事：\n" + "\n".join([f"- {q}" for q in qs])
        st.session_state.messages.append({"role": "assistant", "content": reply})
        with st.chat_message("assistant"):
            st.markdown(reply)
        st.stop()

    route_name = r.get("route", "other")
    state = ensure_pipeline_state(user_text, user_graph)

    # === Subflows Execution ===
    if route_name == "faq_exercise":
        state = subflow_faq_exercise(state, st.session_state.exercise_kg)
    
    elif route_name == "faq_food":
        state = subflow_faq_food(state, st.session_state.nutrition_kg)
    
    elif route_name == "query_memory":
        state = subflow_query_memory(state, trace)
    
    elif route_name in ("plan_workout", "plan_diet", "plan_both"):
        # 1. 运行计划生成 (不保存)
        state = subflow_plan_full(
            state, trace, 
            st.session_state.exercise_kg, 
            st.session_state.nutrition_kg, 
            route_name=route_name
        )
        # 2. 生成回复文本
        with st.spinner("生成方案中..."):
            reply = render_response(route_name, state, state.get("memory_summary", {}))
        
        # 3. ★★★ 修复：增加判断条件 ★★★
        # 只有当 decision 有回复，并且 draft_plan 也有内容时，才视为有效计划
        # (因为如果是器械拦截，draft_plan 会被置空，这里就不会进入 pending 状态)
        has_response = state.get("decision", {}).get("response")
        has_draft = state.get("draft_plan")  # 关键检查点
        
        if has_response and has_draft:
            st.session_state.pending_plan = {
                "state": state,
                "trace": list(trace),
                "text": reply
            }
            # 强制刷新页面
            st.rerun()

    elif route_name == "log_update":
        state = subflow_log_update(state, trace)
        if "user_memory_graph_updated" in state:
            updated = state["user_memory_graph_updated"]
            st.session_state.user_memory_graph = updated
            save_graph(PATH_USER, updated)

    # === Render Reply (Non-Plan routes) ===
    # 只有非 plan 路由，或者 plan 生成失败时，才在这里直接显示
    # 如果是 plan 路由且成功，上面已经 rerun 了
    if route_name not in ("plan_workout", "plan_diet", "plan_both"):
        with st.spinner("生成回复..."):
            reply = render_response(route_name, state, state.get("memory_summary", {}))
        st.session_state.messages.append({"role": "assistant", "content": reply})
        with st.chat_message("assistant"):
            st.markdown(reply)

# ============================================================
# ★★★ 待确认计划区域 (Always Render Check) ★★★
# ============================================================

# 如果有暂存的计划，先显示助手回复，再显示按钮
if st.session_state.pending_plan:
    plan_data = st.session_state.pending_plan
    
    # 1. 把刚才生成的计划补显示在聊天流里 (如果还没显示的话)
    # 检查最后一条消息是不是这个计划，如果不是，就append进去
    last_msg = st.session_state.messages[-1] if st.session_state.messages else {}
    if last_msg.get("content") != plan_data["text"]:
        st.session_state.messages.append({"role": "assistant", "content": plan_data["text"]})
        with st.chat_message("assistant"):
            st.markdown(plan_data["text"])
    
    # 2. 渲染操作按钮
    with st.container():
        st.info("💡 这是一个新生成的计划。请确认是否采纳：")
        col1, col2 = st.columns([1, 5])
        with col1:
            if st.button("✅ 采纳此计划", type="primary", key="btn_accept"):
                # A. 调用 Commit Subflow
                with st.spinner("正在将计划写入长期记忆..."):
                    final_state = subflow_commit_plan(
                        plan_data["state"], 
                        plan_data["trace"], 
                        plan_data["text"]
                    )
                
                # B. 更新全局 Session
                if "user_memory_graph_updated" in final_state:
                    st.session_state.user_memory_graph = final_state["user_memory_graph_updated"]
                    save_graph(PATH_USER, final_state["user_memory_graph_updated"])
                
                # C. 清理状态
                st.session_state.pending_plan = None
                st.success("已保存！我会监督你执行的。")
                time.sleep(1)
                st.rerun()
        
        with col2:
            st.caption("如果不满意，请直接在下方输入框告诉我怎么修改（例如：'太难了，换简单的'），我会重新生成。")