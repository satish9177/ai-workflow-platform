from app.tools.base import BaseTool, ToolResult


class ToolRegistry:
    _tools: dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool: BaseTool) -> None:
        cls._tools[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> BaseTool | None:
        return cls._tools.get(name)

    @classmethod
    def all_names(cls) -> list[str]:
        return list(cls._tools.keys())

    @classmethod
    async def execute(
        cls,
        tool_name: str,
        action: str,
        params: dict,
        credentials: dict,
    ) -> ToolResult:
        tool = cls.get(tool_name)
        if tool is None:
            return ToolResult(success=False, error=f"Tool not found: {tool_name}")

        try:
            return await tool.execute(action, params, credentials)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


def _register_all() -> None:
    from app.tools.http_request import HttpRequestTool
    from app.tools.integrations.discord import DiscordTool
    from app.tools.integrations.email_tool import EmailTool
    from app.tools.integrations.slack import SlackTool
    from app.tools.smtp_email import SmtpEmailTool
    from app.tools.whatsapp import WhatsAppTool

    ToolRegistry.register(HttpRequestTool())
    ToolRegistry.register(SmtpEmailTool())
    ToolRegistry.register(WhatsAppTool())
    ToolRegistry.register(SlackTool())
    ToolRegistry.register(DiscordTool())
    ToolRegistry.register(EmailTool())


_register_all()
