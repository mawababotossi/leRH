from openai.types.chat.chat_completion import ChatCompletion

data = {
    "id": "chatcmpl-1",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "reasoning_content": "Bonjour !"},
            "finish_reason": "stop",
        }
    ],
    "created": 123,
    "model": "qwen",
    "object": "chat.completion",
}

comp = ChatCompletion.model_validate(data)
print("content:", comp.choices[0].message.content)
print("hasattr reasoning_content:", hasattr(comp.choices[0].message, "reasoning_content"))
print("model_extra:", getattr(comp.choices[0].message, "model_extra", None))
