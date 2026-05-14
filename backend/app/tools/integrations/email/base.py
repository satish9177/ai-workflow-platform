from abc import ABC, abstractmethod
from typing import Optional


class BaseEmailProvider(ABC):
    @abstractmethod
    async def send(
        self,
        to: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> dict:
        """Send an email. Returns dict with success and message_id."""
        ...

    @abstractmethod
    async def test_connection(self) -> dict:
        """Verify credentials without sending. Returns {success, message}."""
        ...
