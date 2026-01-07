import streamlit as st
from core.config import get_cfg

st.title("Settings（前端填写）")
cfg = get_cfg()

cfg["api_key"] = st.text_input("API Key", value=cfg.get("api_key",""), type="password")
cfg["base_url"] = st.text_input("Base URL", value=cfg.get("base_url","https://api.ai-gaochao.cn/v1"))
cfg["model"] = st.text_input("Model", value=cfg.get("model","gpt-4.1"))

if st.button("保存设置"):
    st.session_state.cfg = cfg
    st.success("已保存到本次会话（session）")