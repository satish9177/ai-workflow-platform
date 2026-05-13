import html
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

import aiosmtplib
from aiosmtplib import SMTPAuthenticationError, SMTPConnectError, SMTPDataError, SMTPRecipientsRefused

from app.tools.integrations.email.base import BaseEmailProvider


class SmtpEmailProvider(BaseEmailProvider):
    def __init__(self, credentials: dict[str, Any]):
        self.host = str(credentials.get("host") or "")
        self.port = int(credentials.get("port") or 587)
        self.username = str(credentials.get("username") or "")
        self.password = str(credentials.get("password") or "")
        use_tls = credentials.get("use_tls", True)
        self.use_tls = str(use_tls).lower() not in {"false", "0", "no", "off"} if isinstance(use_tls, str) else bool(use_tls)
        self.from_email = str(credentials.get("from_email") or self.username)
        self.from_name = str(credentials.get("from_name") or "Workflow Bot")

    def _make_html(self, text: str) -> str:
        escaped = html.escape(text).replace("\n", "<br>")
        return f"<html><body><p>{escaped}</p></body></html>"

    def _sanitize_header(self, value: Optional[str]) -> str:
        return str(value or "").replace("\n", "").replace("\r", "").strip()

    async def send(
        self,
        to: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        reply_to: Optional[str] = None,
    ) -> dict:
        clean_to = self._sanitize_header(to)
        clean_subject = self._sanitize_header(subject)
        clean_reply_to = self._sanitize_header(reply_to) if reply_to else None
        if "@" not in clean_to:
            raise ValueError("Invalid recipient address")

        message = MIMEMultipart("alternative")
        message["From"] = f"{self.from_name} <{self.from_email}>"
        message["To"] = clean_to
        message["Subject"] = clean_subject
        if clean_reply_to:
            message["Reply-To"] = clean_reply_to

        message.attach(MIMEText(body_text, "plain", "utf-8"))
        message.attach(MIMEText(body_html or self._make_html(body_text), "html", "utf-8"))

        try:
            await aiosmtplib.send(
                message,
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                use_tls=self.use_tls,
            )
        except SMTPAuthenticationError as exc:
            raise RuntimeError("Email authentication failed. Check your password or App Password.") from exc
        except SMTPRecipientsRefused as exc:
            raise RuntimeError("Recipient address rejected by the mail server.") from exc
        except SMTPConnectError as exc:
            raise RuntimeError(f"Could not connect to {self.host}:{self.port}. Check SMTP host and port.") from exc
        except SMTPDataError as exc:
            raise RuntimeError("Mail server rejected the message.") from exc
        except TimeoutError as exc:
            raise RuntimeError("Connection timed out while sending email.") from exc
        except Exception as exc:
            raise RuntimeError(f"Email send failed: {str(exc)[:200]}") from exc

        return {"success": True, "detail": f"Email sent to {clean_to}"}

    async def test_connection(self) -> dict:
        try:
            smtp = aiosmtplib.SMTP(hostname=self.host, port=self.port, use_tls=self.use_tls)
            await smtp.connect()
            await smtp.login(self.username, self.password)
            await smtp.quit()
            return {"success": True, "message": "Connected successfully"}
        except SMTPAuthenticationError:
            return {"success": False, "message": "Authentication failed. Check your password or App Password."}
        except (ConnectionRefusedError, SMTPConnectError):
            return {"success": False, "message": f"Could not connect to {self.host}:{self.port}. Check SMTP settings."}
        except Exception as exc:
            return {"success": False, "message": f"Connection failed: {str(exc)[:200]}"}
