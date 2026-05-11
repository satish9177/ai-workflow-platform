from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    success: bool
    data: dict[str, Any] | list[Any] | str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    name: str = ""
    display_name: str = ""
    description: str = ""

    @abstractmethod
    async def execute(
        self,
        action: str,
        params: dict[str, Any],
        credentials: dict[str, Any],
    ) -> ToolResult:
        raise NotImplementedError

    async def test_connection(self, credentials: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True)
