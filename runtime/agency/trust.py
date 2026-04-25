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
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Pattern


class TrustMode(str, Enum):
    OFF = "off"
    ON_MY_MACHINE = "on-my-machine"
    YOLO = "yolo"


def current() -> TrustMode:
    """Read AGENCY_TRUST_MODE. Unknown values quietly fall back to OFF."""
    raw = (os.environ.get("AGENCY_TRUST_MODE") or "").strip().lower()
    if raw in ("on-my-machine", "machine", "trust"):
        return TrustMode.ON_MY_MACHINE
    if raw in ("yolo", "no-guards"):
        return TrustMode.YOLO
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
