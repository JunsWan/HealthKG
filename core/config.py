# core/config.py
import os
import streamlit as st

DEFAULT_BASE_URL = "https://api.ai-gaochao.cn/v1"
DEFAULT_MODEL = "gpt-5"

def get_cfg() -> dict:
    if "cfg" not in st.session_state:
        # LLM Config
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL)
        model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)

        # === 1. 运动图谱配置 (Exercise KG) ===
        # 你的 7222f7ba 库
        ex_uri = os.environ.get("NEO4J_URI", "neo4j+ssc://7222f7ba.databases.neo4j.io")
        ex_user = os.environ.get("NEO4J_USER", "neo4j")
        ex_pass = os.environ.get("NEO4J_PASSWORD", "flF6YWcBHUAR3GFOvDHyo4-ZbpU-NrLhqccto15uoBU")

        # === 2. 饮食图谱配置 (Diet KG) ===
        # 你的 88f8ccae 库 (注意这里把硬编码的搬过来，或者设环境变量)
        diet_uri = os.environ.get("DIET_NEO4J_URI", "neo4j+ssc://88f8ccae.databases.neo4j.io")
        diet_user = os.environ.get("DIET_NEO4J_USER", "neo4j")
        diet_pass = os.environ.get("DIET_NEO4J_PASSWORD", "_BAD-vDc9fZjk17xTHjAUWaNPoxGxhh1X9oz2-fDffM")

        st.session_state.cfg = {
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
            
            # 运动图谱 (默认)
            "neo4j_uri": ex_uri,
            "neo4j_user": ex_user,
            "neo4j_password": ex_pass,
            
            # 饮食图谱 (专用)
            "diet_neo4j_uri": diet_uri,
            "diet_neo4j_user": diet_user,
            "diet_neo4j_password": diet_pass,
        }

    return st.session_state.cfg