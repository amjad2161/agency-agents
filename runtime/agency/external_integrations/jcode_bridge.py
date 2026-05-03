"""
jcode_bridge.py — JARVIS Integration Adapter for jcode
======================================================
Wraps the key features of the jcode coding agent harness
(https://github.com/1jehuang/jcode) so that JARVIS can:

  • Launch jcode in headless, server, or one-shot (run) modes
  • Execute shell / bash commands through jcode's tool harness
  • Perform file I/O (read, write, edit, patch) via jcode's safe edit tools
  • Run web fetch / web search through jcode's built-in web tools
  • Query / store jcode's semantic memory graph
  • Spawn and coordinate swarm agents
  • Interact with MCP servers that jcode manages
  • Resume named sessions and extract transcripts
  • Run browser automation via jcode's Firefox Agent Bridge
  • Authenticate with 30+ LLM providers

Architecture
------------
  jcode is a Rust binary.  It exposes three interaction surfaces useful to
  JARVIS:

  1. CLI  (sub-process)   – `jcode run`, `jcode serve`, `jcode --resume`
  2. Server / WebSocket   – `jcode serve` + `jcode connect` (multi-client)
  3. Config / State files – TOML/JSON in ~/.jcode/ and .jcode/

  This adapter prefers the CLI surface for one-shot operations and a
  long-lived server process for interactive sessions.

  All public methods are async and return structured JSON-compatible dicts
  so they can be dropped straight into JARVIS message bus payloads.

Usage
-----
    import asyncio
    from jcode_bridge import JCodeBridge

    bridge = JCodeBridge()
    await bridge.start_server()

    # One-shot bash
    result = await bridge.bash("cargo test --lib")

    # Read a file via jcode's read tool
    result = await bridge.read_file("src/main.rs")

    # Memory
    await bridge.memory_store("user_prefers_tabs_over_spaces", "User likes tabs")
    hits = await bridge.memory_query("indentation preference")

    # Swarm
    swarm = await bridge.swarm_spawn(
        repo="/home/dev/myapp",
        agents=[{"name":"frontend","prompt":"Build the UI"},
                {"name":"backend","prompt":"Build the API"}]
    )

    await bridge.shutdown()

Environment
-----------
  JCODE_BIN        – Path to `jcode` binary (default: first on PATH)
  JCODE_HOME       – Config directory (default: ~/.jcode)
  JCODE_LOG_LEVEL  – Passed through to jcode RUST_LOG
  JCODE_PROVIDER   – Default provider slug (claude, openai, gemini, …)
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

JCODE_BIN = os.getenv("JCODE_BIN", shutil.which("jcode") or "jcode")
JCODE_HOME = pathlib.Path(os.getenv("JCODE_HOME", pathlib.Path.home() / ".jcode"))
JCODE_PROVIDER = os.getenv("JCODE_PROVIDER", "")


def _env() -> Dict[str, str]:
    e = os.environ.copy()
    lvl = os.getenv("JCODE_LOG_LEVEL")
    if lvl:
        e["RUST_LOG"] = lvl
    return e


def _jcode_base_args() -> List[str]:
    """Common CLI args injected before sub-command."""
    return []


# ---------------------------------------------------------------------------
# Structured return types
# ---------------------------------------------------------------------------

@dataclass
class JCodeResult:
    ok: bool = True
    stdout: str = ""
    stderr: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    exit_code: int = 0
    elapsed_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _result_from_proc(proc: subprocess.CompletedProcess, elapsed: float) -> JCodeResult:
    ok = proc.returncode == 0
    return JCodeResult(
        ok=ok,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
        exit_code=proc.returncode,
        elapsed_ms=round(elapsed * 1000, 2),
        error=(proc.stderr or "") if not ok else None,
    )


# ---------------------------------------------------------------------------
# Low-level runner
# ---------------------------------------------------------------------------

async def _run(
    *cmd: str,
    cwd: Optional[str] = None,
    input_data: Optional[str] = None,
    timeout: float = 300.0,
    capture: bool = True,
) -> JCodeResult:
    """Run a jcode sub-command asynchronously."""
    full_cmd = [JCODE_BIN, *_jcode_base_args(), *cmd]
    stdin = subprocess.PIPE if input_data is not None else None
    t0 = time.monotonic()
    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                *full_cmd,
                cwd=cwd,
                stdin=stdin,
                stdout=subprocess.PIPE if capture else None,
                stderr=subprocess.PIPE if capture else None,
                env=_env(),
            ),
            timeout=timeout,
        )
        stdout_data, stderr_data = b"", b""
        if input_data is not None:
            stdout_data, stderr_data = await proc.communicate(input_data.encode())
        else:
            stdout_data, stderr_data = await proc.communicate()
        elapsed = time.monotonic() - t0
        cp = subprocess.CompletedProcess(
            args=full_cmd,
            returncode=proc.returncode or 0,
            stdout=stdout_data.decode(errors="replace"),
            stderr=stderr_data.decode(errors="replace"),
        )
        return _result_from_proc(cp, elapsed)
    except asyncio.TimeoutError:
        return JCodeResult(
            ok=False,
            error=f"Command timed out after {timeout}s: {' '.join(full_cmd)}",
            elapsed_ms=round((time.monotonic() - t0) * 1000, 2),
        )
    except Exception as exc:
        return JCodeResult(
            ok=False,
            error=f"Exception running jcode: {exc}",
            elapsed_ms=round((time.monotonic() - t0) * 1000, 2),
        )


# ---------------------------------------------------------------------------
# JCodeBridge — high-level API
# ---------------------------------------------------------------------------

class JCodeBridge:
    """Adapter that exposes jcode capabilities to JARVIS."""

    def __init__(
        self,
        bin_path: Optional[str] = None,
        home_dir: Optional[pathlib.Path] = None,
        default_provider: Optional[str] = None,
    ):
        self.bin = bin_path or JCODE_BIN
        self.home = home_dir or JCODE_HOME
        self.default_provider = default_provider or JCODE_PROVIDER
        self._server_proc: Optional[asyncio.subprocess.Process] = None
        self._server_port: int = 0
        self._session_name: Optional[str] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def health_check(self) -> JCodeResult:
        """Verify jcode binary is available and responsive."""
        return await _run("--version")

    async def start_server(
        self,
        port: int = 0,
        bind: str = "127.0.0.1",
        resume: Optional[str] = None,
    ) -> JCodeResult:
        """
        Launch `jcode serve` as a background persistent server.
        If *port* is 0, jcode picks an ephemeral port.
        If *resume* is set, resume the named session on launch.
        """
        if self._server_proc is not None:
            return JCodeResult(ok=False, error="Server already running")

        args = ["serve", "--bind", bind]
        if port:
            args += ["--port", str(port)]
        if resume:
            args += ["--resume", resume]
        if self.default_provider:
            args += ["--provider", self.default_provider]

        proc = await asyncio.create_subprocess_exec(
            self.bin,
            *args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_env(),
        )
        self._server_proc = proc
        # Give server a moment to print its listening address
        await asyncio.sleep(1.5)
        # Try to infer port from stdout (jcode typically prints "Listening on 127.0.0.1:PORT")
        # Non-blocking read of what is buffered so far
        port_guess = port
        if proc.stdout:
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=2.0)
                text = line.decode(errors="replace")
                m = re.search(r":(\d+)", text)
                if m:
                    port_guess = int(m.group(1))
            except asyncio.TimeoutError:
                pass
        self._server_port = port_guess
        return JCodeResult(
            ok=True,
            data={"pid": proc.pid, "port": self._server_port, "resume": resume},
        )

    async def stop_server(self) -> JCodeResult:
        """Gracefully terminate the background server."""
        if self._server_proc is None:
            return JCodeResult(ok=False, error="No server running")
        self._server_proc.terminate()
        try:
            await asyncio.wait_for(self._server_proc.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            self._server_proc.kill()
        self._server_proc = None
        self._server_port = 0
        return JCodeResult(ok=True)

    async def shutdown(self) -> JCodeResult:
        """Clean shutdown: stop server, clear state."""
        r = await self.stop_server()
        self._session_name = None
        return r

    # ------------------------------------------------------------------
    # One-shot execution
    # ------------------------------------------------------------------

    async def run(
        self,
        prompt: str,
        cwd: Optional[str] = None,
        timeout: float = 300.0,
    ) -> JCodeResult:
        """
        Non-interactive one-shot: `jcode run "<prompt>"`.
        Returns the full stdout/stderr from the harness.
        """
        return await _run("run", prompt, cwd=cwd, timeout=timeout)

    async def run_with_file_input(
        self,
        prompt: str,
        file_path: Union[str, pathlib.Path],
        cwd: Optional[str] = None,
        timeout: float = 300.0,
    ) -> JCodeResult:
        """
        One-shot where the *contents* of *file_path* are piped into jcode as
        stdin (useful for passing large context without shell-quoting).
        """
        path = pathlib.Path(file_path)
        content = path.read_text(encoding="utf-8") if path.exists() else ""
        return await _run(
            "run", prompt,
            cwd=cwd,
            input_data=content,
            timeout=timeout,
        )

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def resume(self, name: str) -> JCodeResult:
        """Resume a named session.  If a server is running, sends connect/resume."""
        self._session_name = name
        if self._server_proc is not None:
            # Server already running — issue a connect/resume via CLI
            return await _run("connect", "--resume", name)
        return await _run("--resume", name)

    async def list_sessions(self) -> JCodeResult:
        """List resumable sessions (parses jcode's session storage)."""
        # jcode stores session metadata in ~/.jcode/sessions/
        sess_dir = self.home / "sessions"
        if not sess_dir.exists():
            return JCodeResult(ok=True, data={"sessions": []})
        sessions = []
        for p in sess_dir.iterdir():
            if p.is_dir():
                meta = p / "session.json"
                info = {"name": p.name, "path": str(p)}
                if meta.exists():
                    try:
                        info["meta"] = json.loads(meta.read_text())
                    except Exception:
                        pass
                sessions.append(info)
        return JCodeResult(ok=True, data={"sessions": sessions})

    async def export_transcript(
        self,
        session_name: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> JCodeResult:
        """
        Export session transcript to *output_path*.
        If no session name is given, uses the active session.
        """
        name = session_name or self._session_name
        if not name:
            return JCodeResult(ok=False, error="No session name provided")
        out = output_path or str(tempfile.mktemp(suffix=".md"))
        # jcode replay / export is evolving; fallback to reading session dir
        sess_dir = self.home / "sessions" / name
        transcript = sess_dir / "transcript.jsonl"
        if transcript.exists():
            lines = transcript.read_text().strip().splitlines()
            messages = [json.loads(line) for line in lines if line.strip()]
            pathlib.Path(out).write_text(
                json.dumps(messages, indent=2), encoding="utf-8"
            )
            return JCodeResult(ok=True, data={"path": out, "messages": len(messages)})
        return JCodeResult(
            ok=False, error=f"Transcript not found for session '{name}'"
        )

    # ------------------------------------------------------------------
    # Tool wrappers — File I/O
    # ------------------------------------------------------------------

    async def read_file(
        self,
        path: Union[str, pathlib.Path],
        offset: int = 0,
        limit: int = 0,
    ) -> JCodeResult:
        """
        Use jcode's native `read` tool to fetch file contents.
        Because `jcode run` can execute the read tool inline via prompt,
        we construct a harness prompt and parse the returned text block.
        """
        p = pathlib.Path(path)
        prompt = f"Read the file at '{p}' and return its full contents inside a markdown code block."
        if offset or limit:
            prompt += f" Only lines {offset} to {offset+limit if limit else 'end'}."
        r = await self.run(prompt)
        # Best-effort extraction of code block contents
        txt = r.stdout
        m = re.search(r"```(?:\w+)?\n(.*?)```", txt, re.DOTALL)
        if m:
            r.data["content"] = m.group(1)
        else:
            r.data["content"] = txt
        return r

    async def write_file(
        self,
        path: Union[str, pathlib.Path],
        content: str,
    ) -> JCodeResult:
        """Use jcode's `write` tool via one-shot prompt."""
        p = pathlib.Path(path)
        prompt = (
            f"Write the following content to the file at '{p}'. "
            "Do not ask for confirmation.\n\n"
            f"```\n{content}\n```"
        )
        return await self.run(prompt)

    async def edit_file(
        self,
        path: Union[str, pathlib.Path],
        old_string: str,
        new_string: str,
    ) -> JCodeResult:
        """Use jcode's `edit` tool (search/replace block)."""
        p = pathlib.Path(path)
        prompt = (
            f"In file '{p}', replace the exact text block below. Do not ask for confirmation.\n\n"
            f"OLD:\n```\n{old_string}\n```\n\n"
            f"NEW:\n```\n{new_string}\n```"
        )
        return await self.run(prompt)

    async def apply_patch(
        self,
        patch_content: str,
        cwd: Optional[str] = None,
    ) -> JCodeResult:
        """Use jcode's `apply_patch` tool to apply a unified diff."""
        prompt = (
            "Apply the following patch. Do not ask for confirmation.\n\n"
            f"```diff\n{patch_content}\n```"
        )
        return await self.run(prompt, cwd=cwd)

    # ------------------------------------------------------------------
    # Tool wrappers — Shell / Bash
    # ------------------------------------------------------------------

    async def bash(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: float = 300.0,
    ) -> JCodeResult:
        """
        Execute a bash command through jcode's bash tool.
        jcode streams output and has a progress parser; we capture it all.
        """
        prompt = (
            f"Run the following bash command and show me the full output. "
            f"Do not truncate. Command: {command}"
        )
        return await self.run(prompt, cwd=cwd, timeout=timeout)

    async def bash_batch(
        self,
        commands: List[str],
        cwd: Optional[str] = None,
        timeout: float = 300.0,
    ) -> JCodeResult:
        """Run multiple bash commands via jcode's batch tool."""
        cmds = "\n".join(commands)
        prompt = (
            "Run the following bash commands in batch and return each output:\n\n"
            f"```bash\n{cmds}\n```"
        )
        return await self.run(prompt, cwd=cwd, timeout=timeout)

    # ------------------------------------------------------------------
    # Tool wrappers — Search
    # ------------------------------------------------------------------

    async def grep(
        self,
        pattern: str,
        path: Optional[Union[str, pathlib.Path]] = None,
        cwd: Optional[str] = None,
    ) -> JCodeResult:
        """Use jcode's agentgrep (structure-aware grep)."""
        loc = f" in '{path}'" if path else ""
        prompt = f"Search for the pattern '{pattern}'{loc} using grep and show file structure context."
        return await self.run(prompt, cwd=cwd)

    async def code_search(
        self, query: str, cwd: Optional[str] = None) -> JCodeResult:
        """Use jcode's codesearch tool."""
        prompt = f"Search the codebase for: {query}"
        return await self.run(prompt, cwd=cwd)

    async def session_search(self, query: str) -> JCodeResult:
        """Search previous jcode sessions."""
        return await _run("run", f"Search previous sessions for: {query}")

    # ------------------------------------------------------------------
    # Tool wrappers — Browser Automation
    # ------------------------------------------------------------------

    async def browser_setup(self) -> JCodeResult:
        """Run `jcode browser setup` to configure Firefox Agent Bridge."""
        return await _run("browser", "setup")

    async def browser_status(self) -> JCodeResult:
        """Check browser automation readiness."""
        return await _run("browser", "status")

    async def browser_open(self, url: str) -> JCodeResult:
        """Open a URL via jcode's browser tool."""
        return await self.run(f"Open the URL {url} in the browser and show me the page snapshot.")

    async def browser_snapshot(self, url: Optional[str] = None) -> JCodeResult:
        """Get a compact snapshot of the current page or a new URL."""
        prompt = "Get a browser snapshot"
        if url:
            prompt += f" after opening {url}"
        return await self.run(prompt + ".")

    async def browser_click(self, selector: str) -> JCodeResult:
        return await self.run(f"Click the element '{selector}' in the browser.")

    async def browser_type(self, selector: str, text: str) -> JCodeResult:
        return await self.run(f"Type '{text}' into the browser element '{selector}'.")

    async def browser_screenshot(self, output_path: Optional[str] = None) -> JCodeResult:
        prompt = "Take a browser screenshot"
        if output_path:
            prompt += f" and save it to '{output_path}'"
        return await self.run(prompt + ".")

    async def browser_eval(self, js_code: str) -> JCodeResult:
        return await self.run(f"Evaluate the following JS in the browser: {js_code}")

    # ------------------------------------------------------------------
    # Tool wrappers — Web Fetch / Search
    # ------------------------------------------------------------------

    async def web_fetch(self, url: str) -> JCodeResult:
        """Fetch URL content via jcode's webfetch tool."""
        return await self.run(f"Fetch and summarize the content of {url}")

    async def web_search(self, query: str) -> JCodeResult:
        """Search the web via jcode's websearch tool."""
        return await self.run(f"Search the web for: {query}")

    # ------------------------------------------------------------------
    # Memory Graph
    # ------------------------------------------------------------------

    async def memory_store(
        self,
        key: str,
        content: str,
        tags: Optional[List[str]] = None,
    ) -> JCodeResult:
        """
        Store an explicit memory entry via jcode's memory tool.
        jcode embeds this into its semantic memory graph.
        """
        tag_str = " ".join(f"#{t}" for t in (tags or []))
        prompt = (
            f"Store the following memory under key '{key}' {tag_str}:\n"
            f"{content}\n\nDo not ask for confirmation."
        )
        return await self.run(prompt)

    async def memory_query(self, query: str, limit: int = 5) -> JCodeResult:
        """Query the semantic memory graph for related entries."""
        prompt = (
            f"Search my memory graph for entries related to: {query}. "
            f"Return up to {limit} results with relevance scores."
        )
        return await self.run(prompt)

    async def memory_consolidate(self) -> JCodeResult:
        """Trigger ambient memory consolidation."""
        return await self.run(
            "Run ambient memory consolidation to reorganize and deduplicate memories."
        )

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    async def skill_list(self) -> JCodeResult:
        """List currently loaded skills."""
        return await self.run("List all currently loaded skills and their descriptions.")

    async def skill_activate(self, skill_name: str) -> JCodeResult:
        """Activate a skill by name (via slash command or skill tool)."""
        return await self.run(f"Activate the skill '{skill_name}'.")

    async def skill_reload(self) -> JCodeResult:
        """Hot-reload skills from disk without restarting jcode."""
        return await _run("run", "Reload skills from disk.")

    # ------------------------------------------------------------------
    # MCP (Model Context Protocol)
    # ------------------------------------------------------------------

    async def mcp_list(self) -> JCodeResult:
        """List connected MCP servers."""
        return await self.run("List all connected MCP servers and their available tools.")

    async def mcp_connect(
        self,
        name: str,
        command: str,
        args: List[str],
        env: Optional[Dict[str, str]] = None,
    ) -> JCodeResult:
        """
        Connect a new MCP server at runtime.
        Example:  await bridge.mcp_connect("filesystem", "npx", ["-y", "@anthropic/mcp-server-filesystem", "/workspace"])
        """
        arg_str = " ".join(args)
        prompt = (
            f"Connect a new MCP server named '{name}' using command `{command} {arg_str}`. "
            "Do not ask for confirmation."
        )
        if env:
            env_str = " ".join(f"{k}={v}" for k, v in env.items())
            prompt += f" With environment: {env_str}."
        return await self.run(prompt)

    async def mcp_disconnect(self, name: str) -> JCodeResult:
        return await self.run(f"Disconnect the MCP server '{name}'.")

    async def mcp_reload(self) -> JCodeResult:
        return await self.run("Reload all MCP servers.")

    async def mcp_import_claude(self) -> JCodeResult:
        """Import MCP servers from Claude's config if available."""
        claude_mcp = pathlib.Path.home() / ".claude" / "mcp.json"
        if claude_mcp.exists():
            data = json.loads(claude_mcp.read_text())
            # jcode auto-imports on first run, but we can force re-import by writing to ~/.jcode/mcp.json
            jcode_mcp = self.home / "mcp.json"
            jcode_mcp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return JCodeResult(ok=True, data={"imported_from": str(claude_mcp)})
        return JCodeResult(ok=False, error="No ~/.claude/mcp.json found")

    # ------------------------------------------------------------------
    # Swarm / Multi-Agent
    # ------------------------------------------------------------------

    async def swarm_spawn(
        self,
        repo: str,
        agents: List[Dict[str, str]],
        headless: bool = True,
    ) -> JCodeResult:
        """
        Spawn multiple agents in the same repo for native collaboration.
        *agents* is a list of dicts: [{"name": "...", "prompt": "..."}, ...]
        """
        agents_block = "\n".join(
            f"- {a['name']}: {a.get('prompt','')}" for a in agents
        )
        mode = "headless" if headless else "headed"
        prompt = (
            f"Spawn a swarm of {len(agents)} agents in repo '{repo}' ({mode}):\n"
            f"{agents_block}\n\n"
            "Start them and report their PIDs / session names."
        )
        return await self.run(prompt)

    async def swarm_message(
        self,
        agent_name: str,
        message: str,
        target: Optional[str] = None,
    ) -> JCodeResult:
        """
        Send a message to an agent in the swarm.
        *target* can be another agent name, "broadcast", or omitted for repo-wide.
        """
        to = f" to {target}" if target else ""
        return await self.run(f"Send a message from {agent_name}{to}: {message}")

    async def swarm_status(self) -> JCodeResult:
        """Get swarm coordination status."""
        return await self.run("Report the status of all active swarm agents.")

    # ------------------------------------------------------------------
    # Provider / Auth
    # ------------------------------------------------------------------

    async def provider_login(
        self,
        provider: str,
        headless: bool = False,
        print_auth_url: bool = False,
    ) -> JCodeResult:
        """
        Authenticate with a provider.
        Supported: claude, openai, gemini, copilot, azure, fireworks, minimax,
        alibaba-coding-plan, openrouter, openai-compatible, ollama, lmstudio, …
        """
        args = ["login", "--provider", provider]
        if headless:
            args.append("--no-browser")
        if print_auth_url:
            args += ["--print-auth-url", "--json"]
        return await _run(*args)

    async def provider_test(self, provider: Optional[str] = None) -> JCodeResult:
        """Test a provider's auth.  If none given, tests all configured."""
        if provider:
            return await _run("auth-test", "--provider", provider)
        return await _run("auth-test", "--all-configured")

    async def provider_switch(self, provider: str) -> JCodeResult:
        """Switch active provider/account."""
        return await self.run(f"Switch my active provider/account to {provider}.")

    # ------------------------------------------------------------------
    # Self-Dev
    # ------------------------------------------------------------------

    async def selfdev_start(self) -> JCodeResult:
        """Enter self-development mode (agent modifies its own source)."""
        return await self.run("Enter self-dev mode. You may edit the jcode source code.")

    async def selfdev_build(self) -> JCodeResult:
        """Trigger a self-dev build via jcode's build tool."""
        return await self.run("Build the jcode source using the self-dev build tool.")

    async def selfdev_test(self) -> JCodeResult:
        """Run tests in self-dev mode."""
        return await self.run("Run cargo test for the jcode project in self-dev mode.")

    # ------------------------------------------------------------------
    # Side Panel / UI
    # ------------------------------------------------------------------

    async def side_panel_load(self, path: Union[str, pathlib.Path]) -> JCodeResult:
        """Load a file into the jcode side panel."""
        return await self.run(f"Load the file '{path}' into the side panel.")

    async def side_panel_write(self, content: str) -> JCodeResult:
        """Write auxiliary content to the side panel."""
        return await self.run(
            f"Write the following to the side panel:\n\n```\n{content}\n```"
        )

    # ------------------------------------------------------------------
    # Dictation / Voice
    # ------------------------------------------------------------------

    async def dictate(self, audio_path: Optional[str] = None) -> JCodeResult:
        """Send voice input. If *audio_path* provided, could be used for STT piping."""
        if audio_path:
            # jcode dictate reads from configured STT command; we can't easily pipe
            # an arbitrary file through the CLI, so we note it.
            return JCodeResult(
                ok=False,
                error="Direct audio file dictation not supported via CLI; configure STT command in jcode instead.",
            )
        return await _run("dictate")

    # ------------------------------------------------------------------
    # Replay / Export
    # ------------------------------------------------------------------

    async def replay_start(self, session_name: str) -> JCodeResult:
        """Start a replay of a previous session."""
        return await _run("replay", "--session", session_name)

    # ------------------------------------------------------------------
    # Config / State helpers (direct filesystem, no jcode proc)
    # ------------------------------------------------------------------

    def read_config(self) -> Dict[str, Any]:
        """Read ~/.jcode/config.toml if it exists."""
        cfg = self.home / "config.toml"
        if cfg.exists():
            import tomli
            return tomli.loads(cfg.read_text(encoding="utf-8"))
        return {}

    def write_config(self, data: Dict[str, Any]) -> None:
        """Write ~/.jcode/config.toml (overwrites)."""
        import tomli_w
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "config.toml").write_text(
            tomli_w.dumps(data), encoding="utf-8"
        )

    def read_mcp_config(self) -> Dict[str, Any]:
        """Read ~/.jcode/mcp.json ."""
        mcp = self.home / "mcp.json"
        if mcp.exists():
            return json.loads(mcp.read_text(encoding="utf-8"))
        return {}

    def write_mcp_config(self, data: Dict[str, Any]) -> None:
        """Write ~/.jcode/mcp.json ."""
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "mcp.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )

    def provider_env_path(self, provider: str) -> pathlib.Path:
        """Return the env file path for a custom provider."""
        # e.g. openai-compatible -> ~/.config/jcode/openai-compatible.env
        return pathlib.Path.home() / ".config" / "jcode" / f"{provider}.env"


# ---------------------------------------------------------------------------
# Synchronous convenience wrapper (for non-async callers)
# ---------------------------------------------------------------------------

class JCodeBridgeSync:
    """Thin sync wrapper around JCodeBridge for JARVIS components that are not async-native."""

    def __init__(self, **kwargs: Any):
        self._bridge = JCodeBridge(**kwargs)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def _run(self, coro: Any) -> JCodeResult:
        loop = self._ensure_loop()
        if loop.is_running():
            # If we're inside an already-running loop, schedule it
            future = asyncio.ensure_future(coro)
            # This is tricky in general, but for JARVIS we assume the caller
            # handles the event loop.  For safety we return the future itself
            # and let the caller await it.
            return future  # type: ignore[return-value]
        return loop.run_until_complete(coro)

    def health_check(self) -> JCodeResult:
        return self._run(self._bridge.health_check())

    def start_server(self, **kwargs: Any) -> JCodeResult:
        return self._run(self._bridge.start_server(**kwargs))

    def stop_server(self) -> JCodeResult:
        return self._run(self._bridge.stop_server())

    def shutdown(self) -> JCodeResult:
        return self._run(self._bridge.shutdown())

    def run(self, *args: Any, **kwargs: Any) -> JCodeResult:
        return self._run(self._bridge.run(*args, **kwargs))

    def bash(self, *args: Any, **kwargs: Any) -> JCodeResult:
        return self._run(self._bridge.bash(*args, **kwargs))

    def read_file(self, *args: Any, **kwargs: Any) -> JCodeResult:
        return self._run(self._bridge.read_file(*args, **kwargs))

    def write_file(self, *args: Any, **kwargs: Any) -> JCodeResult:
        return self._run(self._bridge.write_file(*args, **kwargs))

    def edit_file(self, *args: Any, **kwargs: Any) -> JCodeResult:
        return self._run(self._bridge.edit_file(*args, **kwargs))

    def grep(self, *args: Any, **kwargs: Any) -> JCodeResult:
        return self._run(self._bridge.grep(*args, **kwargs))

    def web_fetch(self, *args: Any, **kwargs: Any) -> JCodeResult:
        return self._run(self._bridge.web_fetch(*args, **kwargs))

    def web_search(self, *args: Any, **kwargs: Any) -> JCodeResult:
        return self._run(self._bridge.web_search(*args, **kwargs))

    def memory_store(self, *args: Any, **kwargs: Any) -> JCodeResult:
        return self._run(self._bridge.memory_store(*args, **kwargs))

    def memory_query(self, *args: Any, **kwargs: Any) -> JCodeResult:
        return self._run(self._bridge.memory_query(*args, **kwargs))

    def provider_login(self, *args: Any, **kwargs: Any) -> JCodeResult:
        return self._run(self._bridge.provider_login(*args, **kwargs))

    def mcp_connect(self, *args: Any, **kwargs: Any) -> JCodeResult:
        return self._run(self._bridge.mcp_connect(*args, **kwargs))

    def swarm_spawn(self, *args: Any, **kwargs: Any) -> JCodeResult:
        return self._run(self._bridge.swarm_spawn(*args, **kwargs))

    def read_config(self) -> Dict[str, Any]:
        return self._bridge.read_config()

    def write_config(self, data: Dict[str, Any]) -> None:
        self._bridge.write_config(data)


# ---------------------------------------------------------------------------
# Module-level smoke test
# ---------------------------------------------------------------------------

async def _smoke() -> None:
    b = JCodeBridge()
    print("health:", await b.health_check())
    print("bash:", await b.bash("echo hello from jcode_bridge"))


if __name__ == "__main__":
    asyncio.run(_smoke())
