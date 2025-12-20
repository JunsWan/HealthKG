# agents/response_generator.py
from typing import Dict, Any
from core.llm import chat
from core.json_utils import dumps
from agents.prompts import RESPONSE_GENERATOR_SYS

def render_response(route: str, state: Dict[str, Any], memory_summary: Dict[str, Any]) -> str:
    """
    输入：route + state（含 decision/evidence/memory_retrieval 等）
    输出：Markdown（给用户看的）
    """

    if route == "faq_exercise":
        evidences = state.get("kg_evidence", {}).get("exercise_kg", [])
        user_input = state.get("user_input", "")
        
        # 构造一个强约束的 Prompt
        system_prompt = (
            "你是一个基于Neo4j知识图谱的运动专家。请根据提供的【检索证据】回答用户问题。\n"
            "原则：\n"
            "1. **必须显式引用**：在提到动作时，说明“我从专业的运动知识图谱中找到了下面这些动作”。\n"
            "2. **拒绝幻觉**：如果检索结果里没有某个动作，就不要硬编动作，只说检索到了什么。\n"
            "3. **结构化**：列出动作名称、涉及的主要肌肉、主要内容（从fields中获取）。\n"
            "4. **如果检索结果为空**：诚实地说图谱里暂时没找到相关动作，但可以推荐一些常规的动作。\n"
            "4. **态度友好、乐于助人**：请你以“作为运动专家，我为你查询一下相关的专业知识。”开头，然后再介绍引用的图谱内容，最后给出一些总结和额外的建议。请你既保持专业性，同时也要保持乐于助人的感觉，给出温暖的回复。\n"
        )
        
        # 把证据转成字符串喂给它
        evidence_text = "\n".join([
            f"- 动作ID: {e.get('name')} (来源: {e.get('source')})\n"
            f"  描述: {e.get('summary')}\n"
            f"  属性: {e.get('fields')}"
            for e in evidences
        ])
        
        if not evidences:
            evidence_text = "（知识图谱未返回任何结果）"

        # 调用 LLM 生成回复
        return chat(
            instruction=system_prompt,
            user_message=f"用户问题：{user_input}\n\n检索到的图谱数据：\n{evidence_text}"
        )

    else:
        payload = {
            "route": route,
            "state": state,
            "memory_summary": memory_summary
        }
        return chat(RESPONSE_GENERATOR_SYS, dumps(payload))