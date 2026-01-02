# core/llm.py
from openai import OpenAI
from core.config import get_cfg

def get_client() -> OpenAI:
    cfg = get_cfg()
    if not cfg["api_key"]:
        raise RuntimeError("Missing API key. Please set it in Settings page.")
    return OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])

def chat(instruction, user_message, model="gpt-4.1", response_format=None):
    client = get_client()
    messages = [
        {"role": "system", "content": instruction},
        {"role": "user", "content": user_message},
    ]
    last_e = None
    for _ in range(5):
        try:
            kwargs = {}
            if response_format is not None:
                kwargs["response_format"] = response_format  # OpenAI chat.completions 支持
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                **kwargs
            )
            return resp.choices[0].message.content
        except Exception as e:
            last_e = e
            continue
    print(instruction)
    raise RuntimeError(f"LLM request failed after retries: {last_e}")