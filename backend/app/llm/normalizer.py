from app.llm.types import LLMMessage


def extract_system(messages: list[LLMMessage]) -> tuple[str | None, list[LLMMessage]]:
    system_messages = [message.content for message in messages if message.role == "system"]
    non_system_messages = [message for message in messages if message.role != "system"]
    system_prompt = "\n".join(system_messages) if system_messages else None
    return system_prompt, non_system_messages


def to_openai_format(messages: list[LLMMessage]) -> list[dict]:
    return [{"role": message.role, "content": message.content} for message in messages]


def to_anthropic_format(messages: list[LLMMessage]) -> list[dict]:
    return [
        {"role": message.role, "content": message.content}
        for message in messages
        if message.role != "system"
    ]


def to_gemini_format(messages: list[LLMMessage]) -> list[dict]:
    return [
        {
            "role": "model" if message.role == "assistant" else message.role,
            "parts": [{"text": message.content}],
        }
        for message in messages
        if message.role != "system"
    ]
