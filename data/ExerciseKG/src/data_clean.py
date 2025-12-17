import json
from openai import OpenAI
from tqdm import tqdm
import os
import re
client = OpenAI(
    api_key="",
    base_url="https://api.deepseek.com")

TOP_BODY_PARTS = [
    "Arm", "Back", "Calf", "Chest",
    "ForeArm", "Hips", "Neck",
    "Shoulder", "Thigh", "Waist"
]

PROMPT_TEMPLATE = """
You are an expert in exercise biomechanics and injury prevention.

Your task is to analyze the following exercise instructions
(including preparation and execution steps)
and determine which body parts are actively involved or stressed
during the performance of this exercise.

IMPORTANT RULES:
1. You must ONLY choose body parts from the following predefined list:
{body_parts}

2. If the instructions mention movements, support, stabilization,
or load that involve a body region, include that body part.

3. If a body part is NOT involved, do NOT include it.

4. Do NOT invent new body parts.
Use ONLY the exact names from the list above.

5. If no body part from the list is involved, return an empty list.

Return the result in the following JSON format ONLY:

{{
  "involved_body_parts": []
}}

Exercise Instructions:
\"\"\"
{instructions}
\"\"\"
"""

def safe_parse_llm_json(text: str):
    """
    尝试从 LLM 输出中解析 JSON
    返回 (parsed_dict, success_flag)
    """
    if not isinstance(text, str):
        return None, False

    text = text.strip()

    # ---------- 1️⃣ 直接尝试 ----------
    try:
        return json.loads(text), True
    except Exception:
        pass

    # ---------- 2️⃣ 提取 ```json ... ``` ----------
    code_block = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1)), True
        except Exception:
            pass

    # ---------- 3️⃣ 提取第一个 {...} ----------
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group()), True
        except Exception:
            pass

    return None, False



def extract_body_parts(instructions: str):
    prompt = PROMPT_TEMPLATE.format(
        body_parts=TOP_BODY_PARTS,
        instructions=instructions
    )

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        stream=False
    )

    raw_text = response.choices[0].message.content

    parsed, success = safe_parse_llm_json(raw_text)

    # ---------- 兜底 ----------
    if success and isinstance(parsed, dict):
        parts = parsed.get("involved_body_parts", [])
        if isinstance(parts, list):
            parts = [p for p in parts if p in TOP_BODY_PARTS]
        else:
            parts = []
    else:
        parts = []

    return {
        "involved_body_parts": parts,
        "raw_output": raw_text,
        "parse_success": success
    }


def process_dataset(input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in tqdm(data, desc="Extracting instruction body parts"):
        instructions = item.get("Instructions", "")
        result = extract_body_parts(instructions)
        item["Instruction_BodyPart"] = result["involved_body_parts"]

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ Saved to {output_path}")


if __name__ == "__main__":
    process_dataset(
        input_path="../data/exrx_full_dataset.json",
        output_path="../data/exrx_final.json"
    )
