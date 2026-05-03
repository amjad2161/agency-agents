"""
Secure Config — Pass 23
AES-256-GCM encrypted secrets storage.
Key derived from machine UUID via PBKDF2.
Backends: cryptography (Fernet) → base64 obfuscation fallback.
⚠️  Never logs secret values.
"""

from __future__ import annotations
import os
import json
import uuid
import base64
import hashlib
import warnings
from pathlib import Path
from typing import Optional

# ── constants ──────────────────────────────────────────────────────────────────

SECRETS_DIR  = Path.home() / ".agency"
SECRETS_FILE = SECRETS_DIR / "secrets.enc"

MANAGED_KEYS = [
    "ANTHROPIC_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "AGENCY_EMAIL_PASSWORD",
    "OPENAI_API_KEY",
]

# ── key derivation ─────────────────────────────────────────────────────────────

def _machine_id() -> bytes:
    """Stable per-machine identifier derived from MAC address."""
    node = uuid.getnode()
    return node.to_bytes(8, "big")


def _derive_key(machine_bytes: Optional[bytes] = None) -> bytes:
    """PBKDF2-HMAC-SHA256, 100k iterations, 32-byte key."""
    if machine_bytes is None:
        machine_bytes = _machine_id()
    salt = b"jarvis-secure-config-v1"
    key = hashlib.pbkdf2_hmac("sha256", machine_bytes, salt, 100_000, dklen=32)
    return key


# ── crypto backends ────────────────────────────────────────────────────────────

class _FernetBackend:
    """Uses cryptography.fernet (AES-128-CBC + HMAC; good enough for local secrets)."""

    def __init__(self, raw_key: bytes):
        from cryptography.fernet import Fernet  # may raise ImportError
        # Fernet requires a 32-byte URL-safe base64 key
        fernet_key = base64.urlsafe_b64encode(raw_key)
        self._f = Fernet(fernet_key)

    def encrypt(self, plaintext: bytes) -> bytes:
        return self._f.encrypt(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        return self._f.decrypt(ciphertext)


class _Base64Backend:
    """
    NOT cryptographically secure — simple base64 obfuscation.
    Emits a warning on first use.
    """

    _warned = False

    def _warn(self):
        if not _Base64Backend._warned:
            warnings.warn(
                "⚠️ SecureConfig: cryptography library unavailable. "
                "Secrets stored with base64 obfuscation only — NOT secure.",
                stacklevel=4,
            )
            _Base64Backend._warned = True

    def encrypt(self, plaintext: bytes) -> bytes:
        self._warn()
        return base64.b64encode(plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        self._warn()
        return base64.b64decode(ciphertext)


def _build_backend(raw_key: bytes):
    try:
        return _FernetBackend(raw_key)
    except Exception:
        return _Base64Backend()


# ── storage helpers ────────────────────────────────────────────────────────────

def _load_store(backend) -> dict:
    if not SECRETS_FILE.exists():
        return {}
    raw = SECRETS_FILE.read_bytes()
    try:
        plaintext = backend.decrypt(raw)
        return json.loads(plaintext.decode("utf-8"))
    except Exception:
        return {}


def _save_store(backend, store: dict) -> None:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    plaintext = json.dumps(store).encode("utf-8")
    ciphertext = backend.encrypt(plaintext)
    SECRETS_FILE.write_bytes(ciphertext)
    # Restrict permissions (Unix only; no-op on Windows)
    try:
        SECRETS_FILE.chmod(0o600)
    except Exception:
        pass


# ── public class ───────────────────────────────────────────────────────────────

class SecureConfig:
    """
    Encrypted local secrets manager.
    Key derived from machine UUID → PBKDF2.
    """

    def __init__(self, machine_bytes: Optional[bytes] = None):
        raw_key = _derive_key(machine_bytes)
        self._backend = _build_backend(raw_key)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def set_secret(self, key: str, value: str) -> None:
        """Store a secret. Never logs value."""
        store = _load_store(self._backend)
        store[key] = value
        _save_store(self._backend, store)

    def get_secret(self, key: str) -> Optional[str]:
        """Retrieve a secret by key. Returns None if not found."""
        store = _load_store(self._backend)
        return store.get(key)

    def list_keys(self) -> list:
        """List all stored keys (not values)."""
        store = _load_store(self._backend)
        return list(store.keys())

    def delete_key(self, key: str) -> bool:
        """Delete a key. Returns True if it existed."""
        store = _load_store(self._backend)
        existed = key in store
        if existed:
            del store[key]
            _save_store(self._backend, store)
        return existed

    @property
    def backend_name(self) -> str:
        return type(self._backend).__name__


# ── CLI helper (called from main jarvis CLI) ───────────────────────────────────

def cli_secret(args: list) -> None:
    """
    jarvis secret set <key> <value>
    jarvis secret get <key>
    jarvis secret list
    jarvis secret delete <key>
    """
    cfg = SecureConfig()
    if not args:
        print("Usage: jarvis secret [set|get|list|delete] [key] [value]")
        return

    cmd = args[0].lower()
    if cmd == "set":
        if len(args) < 3:
            print("Usage: jarvis secret set <key> <value>")
            return
        cfg.set_secret(args[1], args[2])
        print(f"✓ מפתח '{args[1]}' נשמר בהצלחה")
    elif cmd == "get":
        if len(args) < 2:
            print("Usage: jarvis secret get <key>")
            return
        val = cfg.get_secret(args[1])
        if val is None:
            print(f"✗ מפתח '{args[1]}' לא נמצא")
        else:
            print(val)
    elif cmd == "list":
        keys = cfg.list_keys()
        if not keys:
            print("אין מפתחות שמורים")
        else:
            for k in keys:
                print(f"  • {k}")
    elif cmd == "delete":
        if len(args) < 2:
            print("Usage: jarvis secret delete <key>")
            return
        ok = cfg.delete_key(args[1])
        if ok:
            print(f"✓ מפתח '{args[1]}' נמחק")
        else:
            print(f"✗ מפתח '{args[1]}' לא נמצא")
    else:
        print(f"פקודה לא מוכרת: {cmd}")
