"""Email client module for JARVIS Pass 17.

Provides:
  read_inbox(host, user, password, limit=10)  → list[EmailMessage]
  send_email(to, subject, body, ...)          → bool

Configuration (preferred over passing args each time)
------------------------------------------------------
~/.agency/config.toml:
  [email]
  imap_host = "imap.gmail.com"
  smtp_host = "smtp.gmail.com"
  smtp_port = 587
  user      = "you@example.com"

Password: AGENCY_EMAIL_PASSWORD env var — never stored on disk.

Security
--------
- TLS/SSL for IMAP, STARTTLS for SMTP
- Password sourced exclusively from env var (not from config file)
- No plaintext storage of credentials
"""

from __future__ import annotations

import email as _email_stdlib
import email.header as _email_header
import imaplib
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config integration
# ---------------------------------------------------------------------------
_CONFIG_SECTION = "email"


def _load_email_config() -> dict[str, Any]:
    """Load [email] section from ~/.agency/config.toml, if present."""
    try:
        from .config import agency_dir
        cfg_path = agency_dir() / "config.toml"
        if not cfg_path.exists():
            return {}
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore
            except ImportError:
                return {}
        with open(cfg_path, "rb") as f:
            data = tomllib.load(f)
        return data.get(_CONFIG_SECTION, {})
    except Exception as exc:
        log.debug("email_config load failed: %s", exc)
        return {}


def _get_password() -> str | None:
    """Return email password from env var only."""
    return os.environ.get("AGENCY_EMAIL_PASSWORD")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class EmailMessage:
    uid: str = ""
    subject: str = ""
    sender: str = ""
    recipients: list[str] = field(default_factory=list)
    date: str = ""
    body: str = ""
    is_html: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "subject": self.subject,
            "sender": self.sender,
            "recipients": self.recipients,
            "date": self.date,
            "body": self.body[:2000],
            "is_html": self.is_html,
        }


# ---------------------------------------------------------------------------
# Header decoding
# ---------------------------------------------------------------------------
def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    parts = _email_header.decode_header(value)
    decoded = []
    for part, enc in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    return " ".join(decoded).strip()


def _get_body(msg: Any) -> tuple[str, bool]:
    """Extract plain-text or HTML body from an email.Message."""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if "attachment" in disp:
                continue
            if ct == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset("utf-8")
                return payload.decode(charset, errors="replace"), False
            if ct == "text/html":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset("utf-8")
                return payload.decode(charset, errors="replace"), True
    else:
        payload = msg.get_payload(decode=True)
        ct = msg.get_content_type()
        if payload:
            charset = msg.get_content_charset("utf-8")
            return payload.decode(charset, errors="replace"), ct == "text/html"
    return "", False


# ---------------------------------------------------------------------------
# IMAP reader
# ---------------------------------------------------------------------------
def read_inbox(
    host: str | None = None,
    user: str | None = None,
    password: str | None = None,
    limit: int = 10,
    mailbox: str = "INBOX",
    port: int | None = None,
    use_ssl: bool = True,
) -> list[dict[str, Any]]:
    """Read the most recent *limit* emails from INBOX.

    Parameters are resolved: explicit arg → config file → env var.

    Returns
    -------
    List of EmailMessage dicts (newest first).
    """
    cfg = _load_email_config()
    host = host or cfg.get("imap_host") or os.environ.get("AGENCY_IMAP_HOST", "")
    user = user or cfg.get("user") or os.environ.get("AGENCY_EMAIL_USER", "")
    password = password or _get_password() or ""
    port = port or int(cfg.get("imap_port", 993 if use_ssl else 143))

    if not host:
        raise ValueError("IMAP host required: set imap_host in config or pass host=")
    if not user:
        raise ValueError("Email user required: set user in config or pass user=")
    if not password:
        raise ValueError("Email password required: set AGENCY_EMAIL_PASSWORD env var")

    context = ssl.create_default_context()
    if use_ssl:
        imap = imaplib.IMAP4_SSL(host, port, ssl_context=context)
    else:
        imap = imaplib.IMAP4(host, port)
        imap.starttls(ssl_context=context)

    messages: list[dict[str, Any]] = []
    try:
        imap.login(user, password)
        imap.select(mailbox, readonly=True)

        status, data = imap.search(None, "ALL")
        if status != "OK":
            return messages

        uids = data[0].split()
        # Newest first — take last `limit` UIDs
        recent_uids = uids[-limit:][::-1]

        for uid in recent_uids:
            try:
                status, raw = imap.fetch(uid, "(RFC822)")
                if status != "OK" or not raw or raw[0] is None:
                    continue
                raw_bytes = raw[0][1]  # type: ignore[index]
                parsed = _email_stdlib.message_from_bytes(raw_bytes)
                body, is_html = _get_body(parsed)
                em = EmailMessage(
                    uid=uid.decode(),
                    subject=_decode_header(parsed.get("Subject")),
                    sender=_decode_header(parsed.get("From")),
                    recipients=[_decode_header(r) for r in parsed.get_all("To", [])],
                    date=parsed.get("Date", ""),
                    body=body,
                    is_html=is_html,
                )
                messages.append(em.to_dict())
            except Exception as exc:
                log.warning("read_inbox: skipping message uid=%s: %s", uid, exc)
    finally:
        try:
            imap.logout()
        except Exception:
            pass

    return messages


# ---------------------------------------------------------------------------
# SMTP sender
# ---------------------------------------------------------------------------
def send_email(
    to: str | list[str],
    subject: str,
    body: str,
    from_addr: str | None = None,
    host: str | None = None,
    user: str | None = None,
    password: str | None = None,
    port: int | None = None,
    html: bool = False,
) -> bool:
    """Send an email via SMTP with STARTTLS.

    Parameters are resolved: explicit arg → config file → env var.

    Returns True on success, raises on error.
    """
    cfg = _load_email_config()
    host = host or cfg.get("smtp_host") or os.environ.get("AGENCY_SMTP_HOST", "")
    user = user or cfg.get("user") or os.environ.get("AGENCY_EMAIL_USER", "")
    from_addr = from_addr or user
    password = password or _get_password() or ""
    port = port or int(cfg.get("smtp_port", 587))

    if not host:
        raise ValueError("SMTP host required: set smtp_host in config or pass host=")
    if not user:
        raise ValueError("Email user required: set user in config or pass user=")
    if not password:
        raise ValueError("Email password required: set AGENCY_EMAIL_PASSWORD env var")

    recipients = [to] if isinstance(to, str) else to

    msg = MIMEMultipart("alternative") if html else MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = from_addr or user
    msg["To"] = ", ".join(recipients)

    mime_type = "html" if html else "plain"
    msg.attach(MIMEText(body, mime_type, "utf-8"))

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=30) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(user, password)
        server.sendmail(from_addr or user, recipients, msg.as_string())

    log.info("email sent: to=%s subject=%r", recipients, subject)
    return True


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------
def cli_email_inbox(args: Any) -> None:
    import json as _json
    import sys
    limit = getattr(args, "limit", 10)
    try:
        msgs = read_inbox(limit=limit)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    for i, m in enumerate(msgs, 1):
        print(f"\n[{i}] From: {m['sender']}\n    Subject: {m['subject']}\n    Date: {m['date']}")
        snippet = m["body"].strip().replace("\n", " ")[:120]
        print(f"    {snippet}…" if len(m["body"]) > 120 else f"    {snippet}")


def cli_email_send(args: Any) -> None:
    import sys
    try:
        ok = send_email(
            to=args.to,
            subject=args.subject,
            body=args.body,
        )
        if ok:
            print(f"Email sent to {args.to}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
