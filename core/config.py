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
            "model": model,
            "neo4j_uri": os.environ.get("NEO4J_URI", "neo4j+s://7222f7ba.databases.neo4j.io"),
            "neo4j_user": os.environ.get("NEO4J_USER", "neo4j"),
            "neo4j_password": os.environ.get("NEO4J_PASSWORD", "flF6YWcBHUAR3GFOvDHyo4-ZbpU-NrLhqccto15uoBU"),
        }

    return st.session_state.cfg