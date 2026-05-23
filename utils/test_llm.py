from agents.llm_client import LLMClient, LLMClientError

client = LLMClient()

def test_llm_chat_text():
    messages = [
        {"role": "system", "content": "你是一个有帮助的助手。"},
        {"role": "user", "content": "请简单介绍一下自己。"},
    ]
    try:
        response = client.chat_text(messages)
        print("LLM chat_text 响应：", response)
    except LLMClientError as exc:
        print("LLM 调用失败：", exc)

def test_llm_chat_json():
    messages = [
        {"role": "system", "content": "你是一个有帮助的助手。"},
        {"role": "user", "content": "请以 JSON 格式介绍一下自己，包含 name、version 和 description 字段。"},
    ]
    try:
        response = client.chat_json(messages)
        print("LLM chat_json 响应：", response)
    except LLMClientError as exc:
        print("LLM 调用失败：", exc)

if __name__ == "__main__":
    test_llm_chat_text()
    print("\n" + "="*80 + "\n")
    test_llm_chat_json()