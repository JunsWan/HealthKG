# pages/1_Trace.py
import streamlit as st
from core.json_utils import dumps

st.title("Multi-Agent Trace")

# 获取 session 中的 trace
trace = st.session_state.get("trace", [])

if not trace:
    st.info("暂无 trace。先去主页面聊一句。")
else:
    # 倒序展示，最新的在最上面
    for item in trace[::-1]:
        # 兼容旧数据的兜底写法 (get 方法)
        step = item.get("step", "?")
        agent = item.get("agent", "Unknown Agent")
        ms = item.get("ms", 0)
        
        # 关键修正：这里要取 "parsed"
        content_to_show = item.get("parsed") 
        if content_to_show is None:
             # 如果解析失败或者旧数据只有 raw，就取 raw
            content_to_show = item.get("raw", "No content")

        with st.expander(f"Step {step} - {agent} ({ms} ms)"):
            st.code(dumps(content_to_show), language="json")