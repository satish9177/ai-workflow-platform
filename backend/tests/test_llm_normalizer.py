from app.llm.normalizer import (
    extract_system,
    to_anthropic_format,
    to_gemini_format,
    to_openai_format,
)
from app.llm.types import LLMMessage


def test_extract_system():
    messages = [
        LLMMessage(role="system", content="Be concise."),
        LLMMessage(role="user", content="Hello"),
    ]

    system, remaining = extract_system(messages)

    assert system == "Be concise."
    assert remaining == [LLMMessage(role="user", content="Hello")]


def test_extract_system_merges_multiple_system_messages():
    messages = [
        LLMMessage(role="system", content="Rule one."),
        LLMMessage(role="user", content="Hello"),
        LLMMessage(role="system", content="Rule two."),
        LLMMessage(role="assistant", content="Hi"),
    ]

    system, remaining = extract_system(messages)

    assert system == "Rule one.\nRule two."
    assert remaining == [
        LLMMessage(role="user", content="Hello"),
        LLMMessage(role="assistant", content="Hi"),
    ]


def test_to_openai_format():
    messages = [
        LLMMessage(role="system", content="Be concise."),
        LLMMessage(role="user", content="Hello"),
    ]

    assert to_openai_format(messages) == [
        {"role": "system", "content": "Be concise."},
        {"role": "user", "content": "Hello"},
    ]


def test_to_anthropic_format_excludes_system():
    messages = [
        LLMMessage(role="system", content="Be concise."),
        LLMMessage(role="user", content="Hello"),
        LLMMessage(role="assistant", content="Hi"),
    ]

    assert to_anthropic_format(messages) == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
    ]


def test_to_gemini_format_maps_assistant_to_model():
    messages = [
        LLMMessage(role="system", content="Be concise."),
        LLMMessage(role="user", content="Hello"),
        LLMMessage(role="assistant", content="Hi"),
    ]

    assert to_gemini_format(messages) == [
        {"role": "user", "parts": [{"text": "Hello"}]},
        {"role": "model", "parts": [{"text": "Hi"}]},
    ]
