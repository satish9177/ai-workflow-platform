from dataclasses import dataclass, field
from typing import Literal


@dataclass
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMRequest:
    messages: list[LLMMessage]
    model: str
    max_tokens: int = 1000
    temperature: float = 0.3


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    usage: LLMUsage = field(default_factory=LLMUsage)
    raw: dict = field(default_factory=dict)
