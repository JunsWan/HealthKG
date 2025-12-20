# pages/2_User_Memory.py
import streamlit as st
import pandas as pd
import json
import os
import time
from datetime import datetime, timezone, timedelta
from memory.persistence import load_graph, save_graph
from memory.graph_store import new_graph, summarize

# === Config ===
DATA_DIR = os.getenv("DATA_DIR", "./data")
PATH_USER = os.path.join(DATA_DIR, "user_memory_graph.json")

# ★★★ 定义东八区时区 ★★★
TZ_CN = timezone(timedelta(hours=8))

st.set_page_config(page_title="记忆图谱管理", page_icon="🧠", layout="wide")

# === Helper: Update Node Props ===
def update_node_prop(graph, node_id, new_props, merge=True):
    """直接修改图谱中的节点属性 (Admin模式)"""
    found = False
    for n in graph.get("nodes", []):
        if n.get("id") == node_id:
            if merge:
                n["props"] = {**n.get("props", {}), **new_props}
            else:
                n["props"] = new_props
            n["last_updated"] = int(time.time())
            found = True
            break
    
    if not found and node_id in ["profile:basic", "goal:primary", "constraint:equipment", "pref:diet", "pref:training"]:
        graph.setdefault("nodes", []).append({
            "id": node_id,
            "type": "Unknown",
            "props": new_props,
            "last_updated": int(time.time())
        })
        return True
    return found

# === Load Data ===
if "user_memory_graph" not in st.session_state:
    st.session_state.user_memory_graph = load_graph(PATH_USER, new_graph())

ug = st.session_state.user_memory_graph
mem_sum = summarize(ug)

st.title("🧠 记忆图谱控制台")
st.caption("管理助手的长期记忆、计划与历史记录。")

# === Tabs Layout ===
tab_profile, tab_workout, tab_diet_plan, tab_diet_log, tab_sys_log, tab_json = st.tabs([
    "👤 个人档案", 
    "🏋️ 运动计划", 
    "🥗 饮食计划", 
    "🍽️ 饮食记录", 
    "📜 系统日志",
    "🔍 元数据"
])

# -----------------------------------------------------------------------------
# Tab 1: Profile Editor
# -----------------------------------------------------------------------------
with tab_profile:
    st.subheader("📝 编辑个人信息")
    
    profile = mem_sum.get("profile", {})
    goal = mem_sum.get("goal_primary", {})
    constraints = mem_sum.get("constraints", {})
    
    with st.form("edit_profile_form"):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("##### 基础信息")
            new_name = st.text_input("称呼 (Nickname)", value=profile.get("name", ""))
            c_age, c_gender = st.columns(2)
            new_age = c_age.number_input("年龄", value=int(profile.get("age", 25)), step=1)
            new_gender = c_gender.selectbox("性别", ["male", "female"], index=0 if profile.get("gender")=="male" else 1)
            
            c_h, c_w = st.columns(2)
            new_height = c_h.number_input("身高 (cm)", value=float(profile.get("height", 170.0)))
            new_weight = c_w.number_input("体重 (kg)", value=float(profile.get("weight", 65.0)))

        with col2:
            st.markdown("##### 目标与偏好")
            new_goal = st.text_input("主要目标", value=goal.get("goal_type", "健康"))
            
            curr_equips = constraints.get("equipment", [])
            curr_equips_str = ", ".join(curr_equips) if isinstance(curr_equips, list) else str(curr_equips)
            new_equips_str = st.text_area("可用器械 (逗号分隔)", value=curr_equips_str, help="如: 哑铃, 弹力带")
            
            st.info(f"🚑 当前伤病记录: {', '.join(mem_sum.get('special', {}).get('injuries_active', []) or ['无'])}")

        st.markdown("---")
        if st.form_submit_button("💾 保存修改", type="primary"):
            update_node_prop(ug, "profile:basic", {"name": new_name, "age": new_age, "gender": new_gender, "height": new_height, "weight": new_weight})
            update_node_prop(ug, "goal:primary", {"goal_type": new_goal})
            eq_list = [x.strip() for x in new_equips_str.replace("，", ",").split(",") if x.strip()]
            update_node_prop(ug, "constraint:equipment", {"items": eq_list})
            
            save_graph(PATH_USER, ug)
            st.session_state.user_memory_graph = ug
            st.toast("✅ 档案已更新！")
            time.sleep(1)
            st.rerun()

# -----------------------------------------------------------------------------
# Tab 2: Workout Plan
# -----------------------------------------------------------------------------
with tab_workout:
    active_workout = mem_sum.get("active_workout_plan", {})
    if active_workout and active_workout.get("is_active"):
        st.subheader(f"🏋️ {active_workout.get('title', '训练计划')}")
        
        c1, c2, c3 = st.columns([1,1,2])
        c1.metric("周目标", f"{active_workout.get('target_count')} 次")
        c2.metric("本周已练", f"{active_workout.get('done_count')} 次")
        c3.progress(active_workout.get("progress_pct", 0.0), text="本周进度")
        
        st.markdown("### 📝 计划摘要")
        st.info(active_workout.get("summary", "暂无摘要"))
        
        st.markdown("### 👇 下次训练内容")
        st.markdown("---")
        
        items = active_workout.get("current_items", [])
        if items:
            for idx, item in enumerate(items):
                if isinstance(item, dict):
                    ex_name = item.get("exercise") or item.get("name") or "动作"
                    sets = item.get("sets", "-")
                    reps = item.get("reps", "-")
                    note = item.get("notes", "")
                    if isinstance(note, list): note = "; ".join(note)
                    st.markdown(f"**{idx+1}. {ex_name}**")
                    st.caption(f"{sets}组 x {reps}  {f' | 💡 {note}' if note else ''}")
                elif isinstance(item, list):
                    if len(item) > 0 and isinstance(item[0], dict):
                        st.markdown(f"**{idx+1}. ⚡ 组合训练 (Superset)**")
                        for sub_item in item:
                            if isinstance(sub_item, dict):
                                s_name = sub_item.get("exercise") or sub_item.get("name") or "动作"
                                s_sets = sub_item.get("sets", "-")
                                s_reps = sub_item.get("reps", "-")
                                st.caption(f"• **{s_name}**: {s_sets}组 x {s_reps}")
                    else:
                        ex_name = str(item[0]) if len(item) > 0 else "动作"
                        details = " ".join([str(x) for x in item[1:]])
                        st.markdown(f"**{idx+1}. {ex_name}**")
                        if details: st.caption(details)
                elif isinstance(item, str):
                    st.markdown(f"**{idx+1}. {item}**")
                st.divider()
        else:
            st.caption("自由训练或休息日")
    else:
        st.info("暂无执行中的训练计划。")

# -----------------------------------------------------------------------------
# Tab 3: Diet Plan
# -----------------------------------------------------------------------------
with tab_diet_plan:
    active_diet = mem_sum.get("active_diet_plan", {})
    
    if active_diet and active_diet.get("is_active"):
        st.subheader(f"🥗 {active_diet.get('title', '饮食指南')}")
        st.caption(f"制定日期: {active_diet.get('start_date')}")
        
        st.markdown("### 💡 核心策略")
        details = active_diet.get("details", {})
        macro = {}
        if isinstance(details, dict):
            macro = details.get("macro_target") or details.get("diet_plan", {}).get("macro_target", {})
        
        if macro:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("🔥 每日热量", f"{macro.get('kcal', '-')}", "kcal")
            c2.metric("🥩 蛋白质", f"{macro.get('protein_g', '-')}", "g")
            c3.metric("🍚 碳水", f"{macro.get('carb_g', '-')}", "g")
            c4.metric("🥑 脂肪", f"{macro.get('fat_g', '-')}", "g")
        
        st.info(active_diet.get("summary", "暂无文字摘要"))

        st.markdown("### 🍽️ 参考餐单")
        if isinstance(details, list): 
            for meal in details:
                with st.expander(f"{meal.get('meal_time','').title()} (约{meal.get('actual_calories',0):.0f} kcal)"):
                    for r in meal.get("recipes", []):
                        st.write(f"- **{r.get('recipe_name')}**")
                        st.caption(", ".join([i['text'] for i in r.get('ingredients', [])[:4]]))
        elif isinstance(details, dict):
            meals = details.get("meal_templates") or details.get("diet_plan", {}).get("meal_templates", [])
            if meals:
                for m in meals:
                    with st.expander(f"{m.get('name', '餐')}"):
                        st.write(", ".join(m.get("items", [])))
                        if m.get("notes"):
                            st.caption("; ".join(m.get("notes")))
            else:
                st.json(details)
    else:
        st.info("暂无饮食计划。")

# -----------------------------------------------------------------------------
# Tab 4: Diet Logs (Updated with Timezone & Stats)
# -----------------------------------------------------------------------------
with tab_diet_log:
    st.subheader("🍽️ 饮食记录本")
    
    events = ug.get("events", [])
    diet_logs = [e for e in reversed(events) if e.get("type") in ["DietLog", "MealLog"]]
    
    # --- 1. 计算今日统计 (使用 UTC+8) ---
    today_str = datetime.now(TZ_CN).strftime("%Y-%m-%d")
    daily_stats = {"kcal": 0.0, "p": 0.0, "c": 0.0, "f": 0.0}
    
    # 辅助函数：安全转浮点数
    def safe_float(v):
        try:
            return float(v)
        except:
            return 0.0

    for e in diet_logs:
        ts = e.get("ts", 0)
        # 将 timestamp 转为 UTC+8 时间对象
        dt_cn = datetime.fromtimestamp(ts, TZ_CN)
        if dt_cn.strftime("%Y-%m-%d") == today_str:
            props = e.get("props", {})
            daily_stats["kcal"] += safe_float(props.get("calories"))
            daily_stats["p"] += safe_float(props.get("protein"))
            daily_stats["c"] += safe_float(props.get("carb"))
            daily_stats["f"] += safe_float(props.get("fat"))
            
    # 展示今日指标
    st.markdown(f"##### 📅 今日摄入统计 ({today_str})")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🔥 总热量", f"{daily_stats['kcal']:.0f}", "kcal")
    m2.metric("🥩 蛋白质", f"{daily_stats['p']:.1f}", "g")
    m3.metric("🍚 碳水", f"{daily_stats['c']:.1f}", "g")
    m4.metric("🥑 脂肪", f"{daily_stats['f']:.1f}", "g")
    
    st.divider()

    # --- 2. 展示列表 ---
    if not diet_logs:
        st.info("暂无饮食记录。")
    else:
        st.caption(f"共记录 {len(diet_logs)} 条数据")
        log_data = []
        for e in diet_logs:
            ts = e.get("ts", 0)
            # ★★★ 时间显示修正为 UTC+8 ★★★
            dt_str = datetime.fromtimestamp(ts, TZ_CN).strftime("%Y-%m-%d %H:%M")
            
            props = e.get("props", {})
            content = props.get("summary") or props.get("food") or props.get("description") or "未知食物"
            
            # 数值美化
            kcal = safe_float(props.get("calories"))
            p = safe_float(props.get("protein"))
            c = safe_float(props.get("carb"))
            f = safe_float(props.get("fat"))
            
            meal_type = props.get("meal_type", "-")
            
            # 构造详情字符串 (P:20g C:30g F:10g)
            macros_str = []
            if p > 0: macros_str.append(f"P:{p:.0f}")
            if c > 0: macros_str.append(f"C:{c:.0f}")
            if f > 0: macros_str.append(f"F:{f:.0f}")
            macros_display = " | ".join(macros_str) if macros_str else "-"

            log_data.append({
                "时间 (CN)": dt_str,
                "餐别": meal_type,
                "内容": content,
                "热量 (kcal)": f"{kcal:.0f}" if kcal > 0 else "-",
                "三大素 (g)": macros_display
            })
            
        st.dataframe(pd.DataFrame(log_data), width='stretch', hide_index=True)

# -----------------------------------------------------------------------------
# Tab 5: System Logs
# -----------------------------------------------------------------------------
with tab_sys_log:
    st.subheader("📜 系统交互日志")
    events = ug.get("events", [])
    sys_logs = [e for e in reversed(events) if e.get("type") not in ["DietLog", "MealLog"]]
    
    if sys_logs:
        data = []
        for e in sys_logs:
            ts = e.get("ts", 0)
            # ★★★ 时间显示修正为 UTC+8 ★★★
            dt_str = datetime.fromtimestamp(ts, TZ_CN).strftime("%m-%d %H:%M")
            
            props = e.get("props", {})
            summary = props.get("summary") or props.get("answer") or str(props)
            if len(summary) > 100: summary = summary[:100] + "..."
            
            data.append({
                "时间 (CN)": dt_str,
                "类型": e.get("type"),
                "详情": summary
            })
        st.dataframe(pd.DataFrame(data), width='stretch', hide_index=True)
    else:
        st.caption("暂无日志")

# -----------------------------------------------------------------------------
# Tab 6: JSON Metadata
# -----------------------------------------------------------------------------
with tab_json:
    st.caption("原始数据，仅供调试")
    with st.expander("Nodes"): st.json(ug.get("nodes", []))
    with st.expander("Edges"): st.json(ug.get("edges", []))
    with st.expander("Events"): st.json(ug.get("events", []))