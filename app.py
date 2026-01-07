# app.py
import os
import time
import json
import streamlit as st
from core.config import get_cfg
from typing import Dict, Any, List
from datetime import datetime, date, timedelta, timezone
from memory.persistence import load_graph, save_graph
from memory.graph_store import new_graph, summarize
from agents.router import route
from agents.subflows import (
    ensure_pipeline_state,
    subflow_faq_exercise, subflow_faq_food, subflow_query_memory,
    subflow_log_update,
    subflow_plan_full, subflow_commit_plan
)
from agents.response_generator import render_response

TZ_CN = timezone(timedelta(hours=8))

# 布局设置
st.set_page_config(page_title="Multi-Agent Fitness", layout="wide")
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
if "pending_plan" not in st.session_state:
    st.session_state.pending_plan = None 

# ============================================================
# Helper Functions
# ============================================================
def _fmt_ts(ts: int) -> str:
    if not ts: return ""
    dt = datetime.fromtimestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M")

def _infer_last_record(events: list) -> dict:
    if not events: return {"ts": 0, "type": "", "summary": ""}
    last = max(events, key=lambda x: int(x.get("ts", 0) or 0))
    return {
        "ts": int(last.get("ts", 0) or 0),
        "type": str(last.get("type", "") or ""),
        "summary": str((last.get("props", {}) or {}).get("summary", "") or "")
    }

def generate_greeting(ug: Dict[str, Any]) -> str:
    """
    智能开场白生成器 (修复版)：
    1. 新人引导: 独占的详细介绍。
    2. 老友模式: 
       - 头部: 伤病关怀 / 缺席回归 / 常规问候 (三选一)
       - 尾部: 统一的功能菜单 (保留可选功能提示)
    """
    mem_sum = summarize(ug)
    profile = mem_sum.get("profile", {})
    goal = mem_sum.get("goal_primary", {})
    prefs = mem_sum.get("preferences", {})
    events = ug.get("events", [])
    
    name = profile.get("name")
    
    # === 1. 新人判定 (保持不变，独立返回) ===
    looks_new = (len(events) == 0) and (not name) and (not goal.get("goal_type")) and (not prefs.get("diet")) and (not prefs.get("training"))

    if looks_new:
        return (
            "👋 **你好，我是你的多智能体健身/饮食助手。**\n\n"
            "我可以帮你做这些事：\n"
            "- **💡 咨询**：动作练哪里、怎么做、注意事项；食物的营养/搭配思路\n"
            "- **📝 生成方案**：训练计划 / 饮食模板 / 综合一周安排\n"
            "- **📊 查记录**：你之前练了什么、吃了什么、指标变化\n"
            "- **🧠 记住偏好**：比如器械条件、作息、伤病/不适\n\n"
            "你可以直接在输入框说需求（比如“给我一周四练计划”、“我今天胸推练了这些，帮我记录”）。\n"
            "*(如果还没配置模型，请先去 Settings 填写 API Key)*"
        )

    # === 2. 老用户 - 头部文案生成 (Opening) ===
    display_name = name if name else "User"
    now = datetime.now(TZ_CN)
    opening_text = ""
    
    # A. 伤病关怀逻辑
    active_injuries = []
    if not opening_text:
        for n in ug.get("nodes", []):
            if n.get("type") == "Injury" or str(n.get("id")).startswith("injury:"):
                props = n.get("props", {})
                if props.get("status") == "active":
                    last_ts = n.get("last_updated", 0)
                    diff_days = (now.timestamp() - last_ts) / 86400
                    active_injuries.append((props.get("name"), diff_days))
        
        if active_injuries:
            # 找最久没更新的一个
            active_injuries.sort(key=lambda x: x[1], reverse=True)
            target_injury, days = active_injuries[0]
            if days > 3: 
                opening_text = (f"嗨 {display_name}。距离上次你说【{target_injury}】不舒服已经过几天了，"
                                f"现在感觉好些了吗？如果已经痊愈，请告诉我，我更新一下档案。")

    # B. 时间间隔逻辑
    if not opening_text and events:
        last_event = events[-1]
        last_ts = last_event.get("ts", 0)
        last_date = datetime.fromtimestamp(last_ts, TZ_CN).date()
        current_date = now.date()
        days_gap = (current_date - last_date).days
        
        if days_gap > 1:
            if days_gap > 7:
                opening_text = f"好久不见 {display_name}！最近一周过得怎么样？今天准备恢复训练吗？"
            else:
                opening_text = f"欢迎回来 {display_name}！昨天没看到你，有按计划饮食或运动吗？需要补录一下记录吗？"

    # C. 常规时间段问候 (兜底)
    if not opening_text:
        hour = now.hour
        if 5 <= hour < 11:
            opening_text = f"早安 {display_name}！新的一天，准备好动起来了吗？"
        elif 11 <= hour < 14:
            opening_text = f"中午好 {display_name}，午饭吃得怎么样？记得补充优质蛋白。"
        elif 14 <= hour < 18:
            opening_text = f"下午好 {display_name}，如果感觉困倦，可以起来活动一下。"
        else:
            active_plan = mem_sum.get("active_workout_plan", {})
            if active_plan.get("is_active") and not active_plan.get("is_today_done"):
                opening_text = f"晚上好 {display_name}。今天的训练任务还没完成，要开始吗？"
            else:
                opening_text = f"晚上好 {display_name}。"

    # === 3. 统一功能菜单 (Menu Suffix) ===
    # 始终拼接在问候语后面，提示用户可以做什么
    menu_options = (
        "\n\n你今天想：\n"
        "- 直接**咨询一个问题**（动作/食物/恢复）\n"
        "- **查一下历史记录**\n"
        "- 或者**生成/调整计划**？"
    )

    return f"{opening_text}{menu_options}"

# ============================================================
# Right Panel Renderer
# ============================================================
def render_right_panel(container):
    with container:
        ug = st.session_state.user_memory_graph
        mem_sum = summarize(ug)
        
        # ★★★ 修改点：只获取 active_workout_plan ★★★
        active_plan = mem_sum.get("active_workout_plan", {})

        # --- 直接显示计划进度 (移除了 Profile) ---
        if active_plan and active_plan.get("is_active"):
            title = active_plan.get("title", "训练计划")
            st.subheader(f"📅 {title}")
            
            st.caption(f"开始于: {active_plan.get('start_date', '未知')}")
            
            # 状态读取
            done = active_plan.get("done_count", 0)
            target = active_plan.get("target_count", 3)
            pct = active_plan.get("progress_pct", 0.0)
            next_sess = active_plan.get("next_session", "自由训练")
            is_today_done = active_plan.get("is_today_done", False)
            current_items = active_plan.get("current_items", [])

            # 进度条
            st.progress(pct, text=f"本周进度: {done}/{target} 天")

            # 今日状态逻辑
            if is_today_done:
                st.success(f"✅ **今日已打卡**")
                st.caption("好好休息，明天继续！")
                # 这里的按钮只是视觉占位，禁用状态
                st.button("今日任务已完成", disabled=True, key="btn_disabled")
            else:
                st.markdown(f"### 👇 今日任务: {next_sess}")
                
                # 动作清单渲染 (保持之前的鲁棒性逻辑)
                if current_items:
                    # 直接展开显示，不需要 Expander 了，因为右边现在空间很足
                    st.markdown("---")
                    for idx, item in enumerate(current_items):
                        
                        # Case A: 标准字典 (符合 Schema)
                        if isinstance(item, dict):
                            ex_name = item.get("exercise") or item.get("name") or "动作"
                            sets = item.get("sets", "-")
                            reps = item.get("reps", "-")
                            note = item.get("notes", "")
                            
                            # 处理 note 可能是 list 的情况 (Schema定义是 array<string>)
                            if isinstance(note, list):
                                note = "; ".join(note)
                                
                            note_str = f" *({note})*" if note else ""
                            
                            st.markdown(f"**{idx+1}. {ex_name}**")
                            st.caption(f"{sets}组 x {reps}{note_str}")
                            
                        # Case B: 纯字符串 (兼容旧数据)
                        elif isinstance(item, str):
                            st.markdown(f"**{idx+1}. {item}**")
                            
                        # Case C: 列表 (兼容超级组或幻觉数据)
                        elif isinstance(item, list):
                            # C1: 超级组 [Dict, Dict]
                            if len(item) > 0 and isinstance(item[0], dict):
                                st.markdown(f"**{idx+1}. 组合训练**")
                                for sub_item in item:
                                    if isinstance(sub_item, dict):
                                        s_name = sub_item.get("exercise") or sub_item.get("name") or "动作"
                                        s_sets = sub_item.get("sets", "-")
                                        s_reps = sub_item.get("reps", "-")
                                        st.caption(f"• {s_name}: {s_sets}组 x {s_reps}")
                            # C2: 纯文本列表 ["深蹲", "3组"]
                            else:
                                ex_name = str(item[0]) if len(item) > 0 else "动作"
                                details = " ".join([str(x) for x in item[1:]])
                                st.markdown(f"**{idx+1}. {ex_name}**")
                                if details: st.caption(details)
                    st.markdown("---")
                else:
                    st.info("（今日建议休息，或按计划说明执行）")

                # 打卡按钮
                if st.button("💪 完成今日打卡", key="btn_checkin_right", type="primary", use_container_width=True):
                    new_event = {
                        "type": "WorkoutLog",
                        "props": {
                            "summary": f"完成计划打卡: {next_sess}",
                            "plan_id": "current_active", 
                            "automatic_log": True
                        },
                        "ts": int(time.time())
                    }
                    updated_graph = st.session_state.user_memory_graph
                    if "events" not in updated_graph: updated_graph["events"] = []
                    updated_graph["events"].append(new_event)
                    st.session_state.user_memory_graph = updated_graph
                    save_graph(PATH_USER, updated_graph)
                    
                    st.toast("打卡成功！")
                    time.sleep(1)
                    st.rerun()
                
        else:
            # 空状态
            st.subheader("📅 暂无训练计划")
            st.info("👋 你还没有正在执行的运动计划。")
            st.caption("在左侧告诉我想练什么，我会为你生成。")

# ============================================================
# Main Layout Construction
# ============================================================
st.title("多智能体健身饮食助手")

col_chat, col_info = st.columns([0.7, 0.3], gap="large")

# 1. 渲染右侧面板
render_right_panel(col_info)

with col_chat:
# 2. 渲染左侧聊天记录
# ============================================================
    # ★★★ 新增：饮食计划置顶卡片 (Pinned Diet Plan) ★★★
    # ============================================================
    # 从记忆中读取最新的饮食计划
    mem_sum = summarize(st.session_state.user_memory_graph)
    active_diet = mem_sum.get("active_diet_plan", {})
    
    if active_diet and active_diet.get("is_active"):
    # 侧边栏折叠卡片
        with st.expander(f"🥗 **当前饮食 ({active_diet.get('start_date')})**", expanded=False):
            # 1. 显示摘要或目标
            summary = active_diet.get("summary", "暂无摘要")
            st.caption(f"💡 {summary[:60]}..." if len(summary)>60 else summary)
            
            details = active_diet.get("details", {})
            
            # 2. 显示核心指标 (Macro)
            macro = details.get("macro_target", {})
            if macro:
                # 紧凑显示：2000kcal | P:150 C:180 F:55
                kcal = macro.get("kcal", "-")
                p = macro.get("protein_g", "-")
                c = macro.get("carb_g", "-")
                f = macro.get("fat_g", "-")
                st.markdown(f"**🔥 {kcal} kcal**")
                st.caption(f"🥩 P:{p}g | 🍚 C:{c}g | 🥑 F:{f}g")
                st.divider()

            # 3. 显示简易餐单 (Templates)
            meal_templates = details.get("meal_templates", [])
            if meal_templates:
                for m in meal_templates:
                    m_name = m.get("name", "餐")
                    # 侧边栏只显示第一项食物，避免太长
                    first_item = m.get("items", [""])[0] if m.get("items") else ""
                    if len(m.get("items", [])) > 1:
                        first_item += f" 等{len(m['items'])}项"
                    
                    st.markdown(f"**{m_name}**")
                    if first_item:
                        st.caption(f"• {first_item}")
            else:
                # 兼容旧版本或 Recommender 生成的列表结构
                if isinstance(details, list):
                    for m in details:
                        st.markdown(f"**{m.get('meal_time','').title()}**")
                else:
                    st.caption("暂无结构化菜单")

    # ============================================================
    # 原有的聊天记录渲染
    # ============================================================
    
    if len(st.session_state.messages) == 0:
        # ★★★ 这里调用新的 generate_greeting ★★★
        greet = generate_greeting(st.session_state.user_memory_graph)
        st.session_state.messages.append({"role": "assistant", "content": greet})

    # 循环显示历史消息
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if st.session_state.pending_plan:
        plan_data = st.session_state.pending_plan
        
        last_msg = st.session_state.messages[-1] if st.session_state.messages else {}
        if last_msg.get("content") != plan_data["text"]:
            st.session_state.messages.append({"role": "assistant", "content": plan_data["text"]})
            with st.chat_message("assistant"):
                st.markdown(plan_data["text"])
        
        st.info("💡 这是一个新生成的计划。请确认是否采纳：")
        c1, c2 = st.columns([1, 4])
        with c1:
            if st.button("✅ 采纳此计划", type="primary", key="btn_accept_main"):
                with st.spinner("正在写入记忆..."):
                    print(plan_data)
                    final_state = subflow_commit_plan(
                        plan_data["state"], 
                        plan_data["trace"], 
                        plan_data["text"],
                        task_frame=plan_data.get("task_frame")
                    )
                print(final_state['user_memory_graph_updated'])
                if "user_memory_graph_updated" in final_state:
                    st.session_state.user_memory_graph = final_state["user_memory_graph_updated"]
                    save_graph(PATH_USER, final_state["user_memory_graph_updated"])
                
                st.session_state.pending_plan = None
                st.success("已保存！右侧面板已更新。")
                time.sleep(1)
                st.rerun()
        with c2:
            st.caption("如果不满意，请直接输入修改意见。")


# ============================================================
# Input Handling
# ============================================================
user_text = st.chat_input("输入你的问题/需求...")

if user_text:
    if not cfg["api_key"]:
        st.error("请先配置 API Key")
        st.stop()

    if st.session_state.pending_plan:
        st.session_state.pending_plan = None
    
    st.session_state.messages.append({"role": "user", "content": user_text})
    with col_chat:
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
        with col_chat:
            with st.chat_message("assistant"):
                st.markdown(reply)
        st.stop()

    route_name = r.get("route", "other")
    state = ensure_pipeline_state(user_text, user_graph)

    # === Subflows (ADDED SPINNERS HERE) ===
    if route_name == "faq_exercise":
        with st.spinner("正在检索动作知识图谱..."):
            state = subflow_faq_exercise(state, st.session_state.exercise_kg)
            
    elif route_name == "faq_food":
        with st.spinner("正在检索营养数据库..."):
            state = subflow_faq_food(state, st.session_state.nutrition_kg)
            
    elif route_name == "query_memory":
        with st.spinner("正在查询历史记忆..."):
            state = subflow_query_memory(state, trace)
            
    elif route_name in ("plan_workout", "plan_diet", "plan_both"):
        # 1. 运行计划生成 (最耗时的部分)
        with st.spinner("正在规划方案 (Intent -> Retrieval -> Draft -> Reasoner)..."):
            try:
                state = subflow_plan_full(
                    state, trace, 
                    st.session_state.exercise_kg, 
                    st.session_state.nutrition_kg, 
                    route_name=route_name,
                    chat_history=st.session_state.messages 
                )
            except Exception as e:
                st.error(f"💥 计划生成阶段出错: {str(e)}")
                print(f"[Error] Plan Gen: {e}")
                st.stop()
        
        # 2. 生成回复文本 (渲染阶段)
        reply = ""
        with st.spinner("渲染方案中..."):
            try:
                reply = render_response(route_name, state, state.get("memory_summary", {}))
            except Exception as e:
                print(f"[Error] Render failed: {e}")
                # 兜底回复，防止因为渲染失败导致整个流程断掉
                reply = "✅ **计划已生成！** \n\n(注：由于方案过长，AI 总结文本渲染超时，但不影响计划数据的完整性。请直接确认下方详情。)"
        
        # 3. 结果校验与状态流转
        decision = state.get("decision", {})
        has_final_plan = decision.get("final_plan")
        has_draft = state.get("draft_plan")
        has_response = decision.get("response") # 模型生成的回复（可能是追问，也可能是闲聊）
        
        # === 修复逻辑 ===
        # Case A: 成功生成了计划
        if has_final_plan or has_draft:
            if not reply:
                reply = "✅ 计划已就绪，请查阅。"
            
            st.session_state.pending_plan = {
                "state": state,
                "trace": list(trace),
                "text": reply,
                "task_frame": state.get("task_frame", {})
            }
            st.rerun()
            
        # Case B: 没有计划，但是有回复 (说明触发了追问/拦截逻辑)
        elif has_response:
            # 直接显示模型的追问（比如“请问您有什么器械？”），不报错
            st.session_state.messages.append({"role": "assistant", "content": has_response})
            with st.chat_message("assistant"):
                st.markdown(has_response)
                
        # Case C: 既没计划也没回复 (真正的失败)
        else:
            st.error("😓 生成失败：模型未能产出有效的计划结构。")
            with st.expander("查看调试详情"):
                st.write("Decision:", decision)
                st.write("Draft:", has_draft)

    # app.py

    elif route_name == "log_update":
        with st.spinner("正在分析饮食记录..."):
            # ★★★ 修改：传入 chat_history ★★★
            state = subflow_log_update(
                state, 
                trace, 
                chat_history=st.session_state.messages
            )
        
        # Case A: 成功写入 (有 graph 更新)
        if "user_memory_graph_updated" in state:
            updated = state["user_memory_graph_updated"]
            st.session_state.user_memory_graph = updated
            save_graph(PATH_USER, updated)
            
            # 获取 DietLogger 生成的反馈语
            feedback = state.get("decision", {}).get("response", "已记录。")
            
            # 1. 弹窗提示
            st.toast(f"✅ {feedback}")
            
            # 2. 写入聊天历史 (这样刷新后还在)
            st.session_state.messages.append({"role": "assistant", "content": feedback})
            
            # 3. 稍作停顿后刷新，让 Tab 里的记录更新
            time.sleep(1.5)
            st.rerun()
            
        # Case B: 需要追问 (没有 graph 更新，但有 decision.response)
        elif state.get("decision", {}).get("response"):
            # 这是一个追问，直接显示给用户
            # 代码会走到下面的 "if route_name not in ..." 块去渲染 response，所以这里不用做特殊处理
            pass

    # === Final Reply Render (Non-Plan) ===
    if route_name not in ("plan_workout", "plan_diet", "plan_both"):
        with st.spinner("生成回复..."):
            reply = render_response(route_name, state, state.get("memory_summary", {}))
        st.session_state.messages.append({"role": "assistant", "content": reply})
        with col_chat:
            with st.chat_message("assistant"):
                st.markdown(reply)