# core/config.py
import os
import streamlit as st

DEFAULT_BASE_URL = "https://api.ai-gaochao.cn/v1"
DEFAULT_MODEL = "gpt-4.1"

def get_cfg() -> dict:
    """
    只用：session_state（前端填写） + env（可选） + 默认值
    不使用 st.secrets，避免没有 secrets.toml 时直接报错
    """
    if "cfg" not in st.session_state:
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL)
        model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)

        st.session_state.cfg = {
            "api_key": api_key,
            "base_url": base_url,
            "model": model
        }

    return st.session_state.cfg