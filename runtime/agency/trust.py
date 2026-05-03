"""Trust modes for the runtime.

Single source of truth that every tool consults to know how much rope it has.

  off              (default) — current behavior. Allowlists, sandboxes, opt-ins.
  on-my-machine    — agent gets your reach. Shell on (denylist instead of
                     allowlist). web_fetch hits private IPs. Workdir sandbox
                     lifted (paths can be anywhere). Network access on by
                     default (`AGENCY_NO_NETWORK` still honored as opt-out).
  yolo             — same as on-my-machine, plus an empty shell denylist.
                     If the model emits `rm -rf /`, it runs.

Why even `on-my-machine` keeps a tiny shell denylist: not because you can't be
trusted with `rm -rf /` (you obviously can on your own machine), but because
LLMs hallucinate variables. `rm -rf $UNDEFINED/path` expands to `rm -rf /path`.
The denylist catches the catastrophic-typo set so a single confidently-wrong
token doesn't take your home down. If you want even that gone, use `yolo`.

Resolution order for the active mode:
  1. `AGENCY_TRUST_MODE` env var (if set to a recognized value).
  2. `~/.agency/trust.conf` (if it exists). One line, the mode name. Lets
     you mark a personal machine as `yolo` once and forget about it,
     without leaking that choice into shell-rc files or shared configs.
  3. Default `off`.

The default stays `off` so a fresh clone in CI / Docker / a shared box
doesn't silently grant the agent everything. Personal machines opt in.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Pattern


class TrustMode(str, Enum):
    OFF = "off"
    ON_MY_MACHINE = "on-my-machine"
    YOLO = "yolo"


# The persistent-mode file. Override with AGENCY_TRUST_CONF if you need to
# point at a different path (e.g. for tests or alternate XDG layouts).
def trust_conf_path() -> Path:
    """Return the path to the persistent trust-mode config file."""
    override = os.environ.get("AGENCY_TRUST_CONF")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".agency" / "trust.conf"


def _coerce_mode_name(raw: str | None) -> TrustMode | None:
    """Turn a raw string into a TrustMode, or None if unrecognized."""
    if raw is None:
        return None
    raw = raw.strip().lower()
    if raw in ("on-my-machine", "machine", "trust"):
        return TrustMode.ON_MY_MACHINE
    if raw in ("yolo", "no-guards"):
        return TrustMode.YOLO
    if raw in ("off", "default", "safe"):
        return TrustMode.OFF
    return None


def _read_trust_conf() -> TrustMode | None:
    """Read the persistent-mode file. Returns None if missing/unreadable."""
    path = trust_conf_path()
    try:
        # Take the first non-blank, non-comment line so users can leave
        # notes in the file without breaking parsing.
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            return _coerce_mode_name(line)
        return None
    except (FileNotFoundError, IsADirectoryError, PermissionError, OSError):
        return None


def current() -> TrustMode:
    """Resolve the active trust mode.

    Env var wins (so a one-off shell can override). Falls through to
    `~/.agency/trust.conf` for the persistent personal-machine setting.
    """
    env = _coerce_mode_name(os.environ.get("AGENCY_TRUST_MODE"))
    if env is not None:
        return env
    persistent = _read_trust_conf()
    if persistent is not None:
        return persistent
    return TrustMode.OFF


# ----- shell denylist for on-my-machine ------------------------------------
# Each pattern matches a *normalized* command line: tokens joined by single
# spaces, leading/trailing whitespace stripped, lowercased. The list is
# deliberately small. It catches catastrophic-typo / fork-bomb / wipe-disk
# forms, not "anything that could be destructive."

_DENY_ON_MACHINE: tuple[Pattern[str], ...] = (
    # rm -rf / and rm -rf /* and rm -fr / etc. Anchors to "/" specifically;
    # rm -rf ./foo / ~/Trash / arbitrary-relative-path is fine.
    re.compile(r"\brm\s+-(?:rf|fr|r\s+-f|f\s+-r)\s+/(?:\s|$|\*)"),
    # Classic fork bomb.
    re.compile(r":\(\)\s*\{\s*:\|:\&\s*\}\s*;\s*:"),
    # mkfs against any device — formats a filesystem in place.
    re.compile(r"\bmkfs(?:\.\w+)?\s+/dev/"),
    # dd writing to a raw block device.
    re.compile(r"\bdd\b[^|]*\bof=/dev/"),
    # chmod 000 / chmod -R 000 on /, locks you out of your own machine.
    # Lowercase `r` because shell_command_is_denied normalizes to lowercase
    # before matching — an uppercase `R?` here was a no-op and let
    # `chmod -R 000 /` slip through.
    re.compile(r"\bchmod\s+-?r?\s*000\s+/(?:\s|$)"),
)


@dataclass(frozen=True)
class TrustGate:
    """Per-tool capability snapshot derived from `current()`."""

    mode: TrustMode
    allow_shell: bool
    enforce_shell_allowlist: bool   # if True, allowlist semantics (default)
    enforce_shell_denylist: bool    # if True, run unless command matches denylist
    sandbox_paths_to_workdir: bool  # if False, paths anywhere are allowed
    block_private_ip_fetches: bool  # if False, web_fetch can hit loopback / RFC1918
    # Cloud metadata endpoints (169.254.169.254, fd00:ec2::254, GCE/Azure
    # variants) leak instance credentials. We block them even in
    # `on-my-machine` because there's almost no legitimate reason for an
    # agent to read your IAM creds — and on a dev box that *is* an EC2
    # instance, lifting this would be a credential-exfil pathway. Only
    # `yolo` lifts it.
    block_metadata_fetches: bool

    @classmethod
    def for_mode(cls, mode: TrustMode) -> "TrustGate":
        if mode is TrustMode.OFF:
            return cls(
                mode=mode,
                allow_shell=False,           # opt-in via AGENCY_ALLOW_SHELL
                enforce_shell_allowlist=True,
                enforce_shell_denylist=False,
                sandbox_paths_to_workdir=True,
                block_private_ip_fetches=True,
                block_metadata_fetches=True,
            )
        if mode is TrustMode.ON_MY_MACHINE:
            return cls(
                mode=mode,
                allow_shell=True,
                enforce_shell_allowlist=False,
                enforce_shell_denylist=True,  # tiny catastrophic-typo denylist
                sandbox_paths_to_workdir=False,
                block_private_ip_fetches=False,
                block_metadata_fetches=True,  # see field comment above
            )
        # YOLO
        return cls(
            mode=mode,
            allow_shell=True,
            enforce_shell_allowlist=False,
            enforce_shell_denylist=False,
            sandbox_paths_to_workdir=False,
            block_private_ip_fetches=False,
            block_metadata_fetches=False,
        )


def gate() -> TrustGate:
    """Return the TrustGate for the current active trust mode."""
    return TrustGate.for_mode(current())


def shell_command_is_denied(command: str) -> tuple[bool, str | None]:
    """Return (denied, matched_pattern_repr) for a shell command line.

    Only consulted when the active TrustGate has `enforce_shell_denylist=True`
    (i.e. on-my-machine, not yolo). Normalizes whitespace, strips shell quotes
    via shlex round-trip, and lowercases before matching — so quoted variants
    like `rm -rf "/"` or `dd of='/dev/sda'` match the same patterns as their
    unquoted forms.
    """
    import shlex as _shlex

    norm = re.sub(r"\s+", " ", command.strip()).lower()
    try:
        # shlex.split removes quotes/backslash escapes; join back into a flat
        # token stream so the regex doesn't have to know about shell quoting.
        norm = " ".join(_shlex.split(norm))
    except ValueError:
        # Malformed quoting — fall through and match against the raw form.
        pass
    for pat in _DENY_ON_MACHINE:
        if pat.search(norm):
            return True, pat.pattern
    return False, None
