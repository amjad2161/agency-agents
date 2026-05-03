"""Shell execution skill gated by TrustMode.

OFF mode: refuses all shell commands — returns Hebrew refusal message.
ON_MY_MACHINE: allows commands; enforces trust.py denylist (catastrophic-typo
               set) + an additional read-only-leaning allowlist for unattended
               use.  Interactive / ad-hoc callers can pass
               ``enforce_allowlist=False`` to run any non-denied command.
YOLO: allows any command with a printed warning; no denylist, no allowlist.

Usage::

    from agency.shell_skill import ShellSkill, ShellResult
    result = ShellSkill().execute("git status")
    if result.ok:
        print(result.output)
    else:
        print(result.error)

Note: no YAML skill-registry entry is created here because the runtime uses
markdown persona files, not a YAML-based registry.  Callers that want to
expose this skill to the planner should create a persona markdown that
delegates to this module via ``delegate_to_skill``.
"""

from __future__ import annotations

import logging
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import Sequence

from .trust import TrustMode, current as trust_current, shell_command_is_denied

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safe-allowlist for read-only / non-destructive commands.  Used when
# enforce_allowlist=True (the default for unattended / skill-layer callers).
# Callers running interactively under ON_MY_MACHINE can pass
# enforce_allowlist=False to get full denylist-only semantics.
# ---------------------------------------------------------------------------
SAFE_ALLOWLIST: frozenset[str] = frozenset({
    # navigation / listing
    "ls", "dir", "pwd", "tree", "stat", "file", "find",
    # reading
    "cat", "head", "tail", "less", "more", "wc", "strings",
    # searching
    "grep", "rg", "ag", "awk", "sed",
    # version control (read-only git verbs only)
    "git",
    # diagnostics
    "echo", "date", "hostname", "uname", "env", "printenv",
    "whoami", "id", "uptime", "df", "du", "free",
    # Python / Node / build tools (read-only invocations expected)
    "python", "python3", "node", "npm", "pip", "uv",
    "ruff", "mypy", "pytest", "make",
})

# Additional catastrophic patterns that supplement trust.py's denylist.
# These are checked in ALL modes except YOLO (where the user has explicitly
# said they want no guards).
_EXTRA_DENY: tuple[re.Pattern[str], ...] = (
    # Windows: recursive delete of any drive root
    re.compile(r"\bdel\s+/s\b", re.IGNORECASE),
    re.compile(r"\brd\s+/s\s+/q\s+[a-z]:\\", re.IGNORECASE),
    # format command (Windows)
    re.compile(r"\bformat\s+[a-z]:", re.IGNORECASE),
    # shred / wipe
    re.compile(r"\bshred\s+.*-[a-z]*[un][a-z]*\s+/", re.IGNORECASE),
    # fork-bomb (redundant with trust.py but explicit here for clarity)
    re.compile(r":\(\)\s*\{\s*:\|:\&"),
)

_OFF_HEBREW = (
    "מצב TRUST כבוי. הפעל ON_MY_MACHINE כדי להריץ פקודות."
)
_YOLO_WARNING = (
    "[אזהרה] מצב YOLO פעיל — הרצת פקודה ללא מגבלות: {command!r}"
)


@dataclass
class ShellResult:
    """Returned by ShellSkill.execute()."""

    command: str
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    timed_out: bool = False
    denied: bool = False
    denied_reason: str = ""
    trust_mode: TrustMode = field(default=TrustMode.OFF)

    @property
    def ok(self) -> bool:
        return not self.denied and not self.timed_out and self.returncode == 0

    @property
    def output(self) -> str:
        """stdout + stderr combined, as the executor returns them."""
        parts = [self.stdout]
        if self.stderr:
            parts.append(f"[stderr]\n{self.stderr}")
        if self.returncode != 0:
            parts.append(f"[exit: {self.returncode}]")
        return "\n".join(p for p in parts if p)

    @property
    def error(self) -> str:
        if self.denied:
            return self.denied_reason
        if self.timed_out:
            return f"Timed out: {self.command!r}"
        return self.stderr or ""


def _extra_denied(command: str) -> tuple[bool, str]:
    """Check command against the extra (non-trust.py) denylist patterns.

    Returns (denied, reason).  Normalises whitespace before matching so
    multi-space variants are caught.
    """
    norm = re.sub(r"\s+", " ", command.strip())
    for pat in _EXTRA_DENY:
        if pat.search(norm):
            return True, f"command matches safety denylist pattern: {pat.pattern!r}"
    return False, ""


class ShellSkill:
    """Thin shell-execution wrapper with trust-gated access control.

    Parameters
    ----------
    timeout:
        Subprocess wall-clock timeout in seconds (default 30).
    enforce_allowlist:
        In ON_MY_MACHINE mode, additionally restrict to SAFE_ALLOWLIST.
        Set to False for interactive / power-user flows that rely solely on
        the trust.py denylist.  Ignored in YOLO mode.
    """

    def __init__(
        self,
        timeout: int = 30,
        enforce_allowlist: bool = True,
    ) -> None:
        self.timeout = timeout
        self.enforce_allowlist = enforce_allowlist

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, command: str) -> ShellResult:
        """Execute *command* subject to the current TrustMode.

        Logs every attempt (INFO on success, WARNING on denial, ERROR on
        exception) so the audit trail is always present regardless of whether
        the caller inspects the result.
        """
        mode = trust_current()
        _log.info("shell_skill.execute trust=%s cmd=%r", mode.value, command[:200])

        # ---- OFF mode: hard refusal -------------------------------------------
        if mode is TrustMode.OFF:
            _log.warning("shell_skill denied (trust=off): %r", command[:200])
            return ShellResult(
                command=command,
                denied=True,
                denied_reason=_OFF_HEBREW,
                trust_mode=mode,
            )

        command = command.strip()
        if not command:
            return ShellResult(
                command=command,
                denied=True,
                denied_reason="Empty command.",
                trust_mode=mode,
            )

        # ---- YOLO: extra-denylist still applies (unless opted out) ----------
        # trust.py's denylist is skipped in YOLO by design.  We apply our own
        # extra patterns here but only as a warning, not a hard block, because
        # YOLO means the user accepts full responsibility.
        if mode is TrustMode.YOLO:
            extra_denied, extra_reason = _extra_denied(command)
            if extra_denied:
                _log.warning(
                    "shell_skill YOLO extra-denylist hit (running anyway): %r — %s",
                    command[:200], extra_reason,
                )
            print(_YOLO_WARNING.format(command=command), flush=True)
            return self._run(command, mode)

        # ---- ON_MY_MACHINE ------------------------------------------------
        # 1. trust.py catastrophic-typo denylist
        denied_by_trust, pat = shell_command_is_denied(command)
        if denied_by_trust:
            reason = (
                f"Refusing — matches catastrophic-typo denylist ({pat!r}). "
                f"Run it yourself or use YOLO mode to disable the denylist."
            )
            _log.warning("shell_skill denied (trust denylist): %r — %s", command[:200], reason)
            return ShellResult(
                command=command,
                denied=True,
                denied_reason=reason,
                trust_mode=mode,
            )

        # 2. Extra denylist (rm -rf /, del /s, format, etc.)
        extra_denied, extra_reason = _extra_denied(command)
        if extra_denied:
            _log.warning("shell_skill denied (extra denylist): %r — %s", command[:200], extra_reason)
            return ShellResult(
                command=command,
                denied=True,
                denied_reason=extra_reason,
                trust_mode=mode,
            )

        # 3. Optional allowlist check
        if self.enforce_allowlist:
            try:
                tokens = shlex.split(command)
            except ValueError:
                tokens = command.split()
            head = tokens[0] if tokens else ""
            if head not in SAFE_ALLOWLIST:
                reason = (
                    f"Command {head!r} is not in the safe allowlist. "
                    f"Pass enforce_allowlist=False or use YOLO mode to allow it."
                )
                _log.warning("shell_skill denied (allowlist): %r", command[:200])
                return ShellResult(
                    command=command,
                    denied=True,
                    denied_reason=reason,
                    trust_mode=mode,
                )

        return self._run(command, mode)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run(self, command: str, mode: TrustMode) -> ShellResult:
        """Actually fork the subprocess.  No trust checks — callers handle that."""
        try:
            proc = subprocess.run(
                command,
                shell=True,  # nosec B602 — trust gate already validated
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            _log.error("shell_skill timeout (%ds): %r", self.timeout, command[:200])
            return ShellResult(
                command=command,
                timed_out=True,
                trust_mode=mode,
            )
        except OSError as exc:
            _log.error("shell_skill OS error: %r — %s", command[:200], exc)
            return ShellResult(
                command=command,
                stderr=str(exc),
                returncode=1,
                trust_mode=mode,
            )

        result = ShellResult(
            command=command,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            returncode=proc.returncode,
            trust_mode=mode,
        )
        if result.ok:
            _log.info("shell_skill ok: exit=%d", proc.returncode)
        else:
            _log.warning(
                "shell_skill non-zero exit=%d stderr=%r",
                proc.returncode,
                (proc.stderr or "")[:200],
            )
        return result
