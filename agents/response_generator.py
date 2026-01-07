# agents/response_generator.py
import json
from typing import Dict, Any
from core.llm import chat
from core.json_utils import dumps
from agents.prompts import RESPONSE_GENERATOR_SYS

def render_response(route: str, state: Dict[str, Any], memory_summary: Dict[str, Any]) -> str:
    """
    输入：route + state（含 decision/evidence/memory_retrieval 等）
    输出：Markdown（给用户看的）
    Elena 修改：增加了对 final_plan 的显式渲染逻辑，防止 Reasoner 没吐文字导致前端空白。
    """

    # =======================================================
    # Case 1: 问答/科普 (FAQ)
    # =======================================================
    if route in ["faq_exercise", "faq_food"]:
        evidences = state.get("kg_evidence", {}).get("exercise_kg", [])
        if route == "faq_food":
            evidences = state.get("kg_evidence", {}).get("nutrition_kg", [])
            
        user_input = state.get("user_input", "")
        
        system_prompt = (
            "你是一个基于知识图谱的健康专家。请根据提供的【检索证据】回答用户问题。\n"
            "原则：\n"
            "1. **基于事实**：只回答检索到的内容，不在证据中的信息必须明确说明“未在知识图谱中找到”。\n"
            "2. **结构化输出**：\n"
            "   - 如果涉及【动作推荐 / 食物推荐】，必须使用 **Markdown 表格** 输出。\n"
            "   - 表格应包含：名称、核心作用、适用部位/人群、动作描述、注意事项（如有）。\n"
            "   - 其中动作描述来源描述，但是你尽可能将其中的准备动作以及动作分解出来描述"
            "3. **引用来源**：每一行推荐条目都必须在最后一列或描述中标注 (来源: Neo4j/KG)。\n"
            "4. **温暖专业**：语气鼓励、专业、简洁，不进行医疗诊断。\n"
        )

        
        # 序列化证据
        evidence_text = "（无检索结果，请根据通用知识谨慎回答，并告知用户图谱中暂时没有相关数据）"
        if evidences:
            evidence_text = "\n".join([
                f"- 名称: {e.get('name')}\n"
                f"  描述: {str(e.get('summary', ''))[:1000]}...\n"
                f"  属性: {e.get('fields')}"
                for e in evidences[:10] # 限制数量防止 Context 爆炸
            ])

        return chat(
            instruction=system_prompt,
            user_message=f"用户问题：{user_input}\n\n检索到的图谱数据：\n{evidence_text}"
        )

    # =======================================================
    # Case 2: 计划生成 (Plan) - 核心修改部分
    # =======================================================
    elif route in ["plan_workout", "plan_diet", "plan_both"]:
        decision = state.get("decision", {})
        final_plan = decision.get("final_plan")
        user_input = state.get("user_input", "")

        # 情况 A: Reasoner 还没生成计划，可能是在追问（澄清）
        # 或者 Reasoner 只给了 response 文本
        if not final_plan:
            # 直接把现有信息丢给 LLM 润色
            return chat(RESPONSE_GENERATOR_SYS, dumps({
                "route": route,
                "user_input": user_input,
                "decision_response": decision.get("response", "（请根据意图生成回复）"),
                "thought": decision.get("thought", "")
            }))

        # 情况 B: Reasoner 生成了 JSON Plan (final_plan 存在)
        # 无论 Reasoner 有没有写 summary，我们都强制用 Generator 重新渲染一遍，保证格式统一
        
        # 构造渲染专用的 Prompt
        render_prompt = (
            "你是一个专业的健身/营养教练。你的任务是将后台生成的 JSON 计划数据，渲染成用户易读的 Markdown 格式。\n\n"
            "要求：\n"
            "1. **开头**：简单寒暄，告诉用户计划已生成（一两句即可）。\n"
            "2. **计划正文**：\n"
            "   - 如果是训练计划：按 Day 1, Day 2... 使用 Markdown 表格展示（动作、组数、次数、间歇）。\n"
            "   - 如果是饮食计划：按餐次列出推荐。\n"
            "3. **注意事项**：将 `notes` 里的内容整理成 Bullet Points。\n"
            "4. **结尾**：不包含任何 JSON 代码块，只输出 Markdown 文本。\n"
            "5. **语气**：清晰、专业、鼓励。\n"
        )
        
        # 提取关键数据喂给 LLM
        plan_data_str = json.dumps(final_plan, ensure_ascii=False, indent=2)
        
        return chat(
            instruction=render_prompt,
            user_message=f"用户需求：{user_input}\n\n生成的 JSON 计划数据：\n{plan_data_str}"
        )

    # =======================================================
    # Case 3: 其他 (Memory / Log / Other)
    # =======================================================
    else:
        # 通用兜底
        payload = {
            "route": route,
            "user_input": state.get("user_input"),
            "memory_summary": memory_summary,
            "decision": state.get("decision"),
            "memory_retrieval": state.get("memory_retrieval")
        }
        return chat(RESPONSE_GENERATOR_SYS, dumps(payload))