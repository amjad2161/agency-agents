"""Email client: IMAP read + SMTP send, with mock fallback."""

from __future__ import annotations

import email as email_lib
import os
import smtplib
import uuid
from email.mime.text import MIMEText
from typing import Optional


_MOCK_INBOX = [
    {
        "from": "alice@example.com",
        "subject": "Hello from JARVIS",
        "date": "Mon, 01 May 2026 10:00:00 +0000",
        "snippet": "This is a mock email for testing.",
        "uid": 1001,
        "read": False,
    },
    {
        "from": "bob@example.com",
        "subject": "Meeting tomorrow",
        "date": "Sun, 30 Apr 2026 15:30:00 +0000",
        "snippet": "Can we schedule a call for tomorrow?",
        "uid": 1002,
        "read": False,
    },
]


class EmailClient:
    """SMTP/IMAP email client with mock mode when credentials are absent."""

    def __init__(self, config: Optional[dict] = None) -> None:
        cfg = config or {}
        self._user = cfg.get("user") or os.environ.get("JARVIS_EMAIL_USER", "")
        self._password = cfg.get("password") or os.environ.get("JARVIS_EMAIL_PASSWORD", "")
        self._smtp_host = cfg.get("smtp_host") or os.environ.get("JARVIS_SMTP_HOST", "")
        self._smtp_port = int(cfg.get("smtp_port") or os.environ.get("JARVIS_SMTP_PORT", "587"))
        self._imap_host = cfg.get("imap_host") or os.environ.get("JARVIS_IMAP_HOST", "")

        self._mock = not (self._user and self._password and self._smtp_host)
        # Local copy of mock inbox for state mutations
        self._mock_inbox: list[dict] = [dict(m) for m in _MOCK_INBOX]

    @property
    def mode(self) -> str:
        return "mock" if self._mock else "live"

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def send(self, to: str, subject: str, body: str) -> dict:
        """Send an email. Returns {status, message_id} or {status: 'mock', ...}."""
        msg_id = f"<{uuid.uuid4()}@jarvis>"
        if self._mock:
            return {"status": "mock", "message_id": msg_id, "to": to, "subject": subject}
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = self._user
            msg["To"] = to
            msg["Message-ID"] = msg_id
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=10) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(self._user, self._password)
                smtp.sendmail(self._user, [to], msg.as_string())
            return {"status": "sent", "message_id": msg_id}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    # ------------------------------------------------------------------
    # Receive
    # ------------------------------------------------------------------

    def fetch_inbox(self, limit: int = 10, unread_only: bool = True) -> list[dict]:
        """Fetch inbox messages. Returns mock data when not configured."""
        if self._mock:
            msgs = self._mock_inbox
            if unread_only:
                msgs = [m for m in msgs if not m.get("read", False)]
            return msgs[:limit]
        return self._fetch_imap(limit, unread_only)

    def _fetch_imap(self, limit: int, unread_only: bool) -> list[dict]:
        try:
            import imaplib

            criteria = "UNSEEN" if unread_only else "ALL"
            with imaplib.IMAP4_SSL(self._imap_host) as imap:
                imap.login(self._user, self._password)
                imap.select("INBOX")
                _, data = imap.search(None, criteria)
                uids = data[0].split()[-limit:]
                results = []
                for uid in reversed(uids):
                    _, msg_data = imap.fetch(uid, "(RFC822)")
                    raw = msg_data[0][1]
                    msg = email_lib.message_from_bytes(raw)
                    snippet = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                snippet = part.get_payload(decode=True).decode("utf-8", errors="replace")[:200]
                                break
                    else:
                        snippet = msg.get_payload(decode=True).decode("utf-8", errors="replace")[:200]
                    results.append({
                        "from": msg.get("From", ""),
                        "subject": msg.get("Subject", ""),
                        "date": msg.get("Date", ""),
                        "snippet": snippet,
                        "uid": int(uid),
                    })
            return results
        except Exception as exc:
            return [{"error": str(exc)}]

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def mark_read(self, uid: int) -> bool:
        """Mark a message as read. Returns True on success."""
        if self._mock:
            for msg in self._mock_inbox:
                if msg["uid"] == uid:
                    msg["read"] = True
                    return True
            return False
        try:
            import imaplib
            with imaplib.IMAP4_SSL(self._imap_host) as imap:
                imap.login(self._user, self._password)
                imap.select("INBOX")
                imap.store(str(uid), "+FLAGS", "\\Seen")
            return True
        except Exception:
            return False

    def delete(self, uid: int) -> bool:
        """Delete a message by uid. Returns True on success."""
        if self._mock:
            before = len(self._mock_inbox)
            self._mock_inbox = [m for m in self._mock_inbox if m["uid"] != uid]
            return len(self._mock_inbox) < before
        try:
            import imaplib
            with imaplib.IMAP4_SSL(self._imap_host) as imap:
                imap.login(self._user, self._password)
                imap.select("INBOX")
                imap.store(str(uid), "+FLAGS", "\\Deleted")
                imap.expunge()
            return True
        except Exception:
            return False
