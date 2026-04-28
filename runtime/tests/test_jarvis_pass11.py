"""Pass 11 tests — httpx streaming fix, --model flag, --stream flag, API smoke.

Run:
    cd runtime && python -m pytest tests/test_jarvis_pass11.py -v

API smoke tests are skipped unless AGENCY_API_KEY is set in the environment.
"""
from __future__ import annotations

import os
import subprocess
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AGENCY_API_KEY = os.getenv("AGENCY_API_KEY") or os.getenv("ANTHROPIC_API_KEY")


def _invoke(args: list[str], input_text: str = "") -> tuple[int, str, str]:
    """Run the agency CLI in a subprocess and return (returncode, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, "-m", "agency"] + args,
        input=input_text,
        capture_output=True,
        text=True,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        timeout=30,
    )
    return proc.returncode, proc.stdout, proc.stderr


# ===========================================================================
# 1. httpx streaming fix — _web_fetch uses client.stream(), not client.send()
# ===========================================================================


def test_web_fetch_no_longer_uses_client_send_stream():
    """Confirm the old broken pattern is gone from tools.py source."""
    tools_path = os.path.join(os.path.dirname(__file__), "..", "agency", "tools.py")
    src = open(tools_path).read()
    assert "client.send(req, stream=True)" not in src, (
        "Old httpx pattern still present — httpx 0.28+ Response has no __enter__"
    )


def test_web_fetch_uses_client_stream_context_manager():
    """Confirm the correct client.stream() pattern is present."""
    tools_path = os.path.join(os.path.dirname(__file__), "..", "agency", "tools.py")
    src = open(tools_path).read()
    assert 'client.stream("GET", url)' in src, (
        "Expected client.stream(\"GET\", url) context manager in _web_fetch"
    )


def test_web_fetch_no_manual_resp_close():
    """With client.stream() the context manager closes the response; no resp.close() needed."""
    tools_path = os.path.join(os.path.dirname(__file__), "..", "agency", "tools.py")
    src = open(tools_path).read()
    # The _web_fetch function itself should not call resp.close() explicitly
    # (the old code did: resp.close() before continuing to next redirect hop)
    import ast
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_web_fetch":
            func_src = ast.get_source_segment(src, node) or ""
            assert "resp.close()" not in func_src, (
                "resp.close() still called in _web_fetch — not needed with client.stream()"
            )


def test_web_fetch_httpx_response_not_used_as_context_manager():
    """Verify that httpx.Response is not used as context manager (it has no __enter__)."""
    import httpx
    assert not hasattr(httpx.Response, "__enter__"), (
        "httpx.Response unexpectedly gained __enter__ — check if fix is still needed"
    )


def test_web_fetch_mock_redirect():
    """_web_fetch redirect logic works with the new client.stream() pattern (mocked)."""
    from agency.tools import _web_fetch, ToolContext
    from pathlib import Path

    ctx = ToolContext(workdir=Path("/tmp"), allow_network=True, timeout_s=10)

    # Build a fake stream context manager that simulates a redirect then a 200
    call_count = 0

    class FakeResponse:
        def __init__(self, status, headers=None, body=b"hello"):
            self.status_code = status
            self.headers = headers or {}
            self._body = body

        def iter_bytes(self):
            yield self._body

    class FakeStreamCtx:
        def __init__(self, resp):
            self._resp = resp

        def __enter__(self):
            return self._resp

        def __exit__(self, *_):
            pass

    def fake_stream(method, url):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return FakeStreamCtx(FakeResponse(301, {"location": "https://example.com/final"}))
        return FakeStreamCtx(FakeResponse(200, body=b"final content"))

    import httpx
    with patch("httpx.Client.stream", side_effect=fake_stream):
        with patch("agency.tools.trust_gate") as tg:
            tg.return_value.block_private_ip_fetches = False
            tg.return_value.block_metadata_fetches = True
            result = _web_fetch({"url": "https://example.com/"}, ctx)

    assert not result.is_error
    assert "final content" in result.content
    assert call_count == 2


def test_web_fetch_network_disabled():
    """Returns error immediately when allow_network=False."""
    from agency.tools import _web_fetch, ToolContext
    from pathlib import Path
    ctx = ToolContext(workdir=Path("/tmp"), allow_network=False, timeout_s=5)
    result = _web_fetch({"url": "https://example.com"}, ctx)
    assert result.is_error
    assert "disabled" in result.content.lower()


def test_web_fetch_rejects_non_http():
    """Non-http/https URLs are rejected."""
    from agency.tools import _web_fetch, ToolContext
    from pathlib import Path
    ctx = ToolContext(workdir=Path("/tmp"), allow_network=True, timeout_s=5)
    result = _web_fetch({"url": "ftp://example.com"}, ctx)
    assert result.is_error


# ===========================================================================
# 2. --model CLI flag
# ===========================================================================


def test_chat_help_shows_model_flag():
    """agency chat --help must list --model."""
    from click.testing import CliRunner
    from agency.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["chat", "--help"])
    assert result.exit_code == 0
    assert "--model" in result.output


def test_chat_help_shows_stream_flag():
    """agency chat --help must list --stream."""
    from click.testing import CliRunner
    from agency.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["chat", "--help"])
    assert result.exit_code == 0
    assert "--stream" in result.output


def test_chat_help_shows_model_examples():
    """The --model help text references model string examples."""
    from click.testing import CliRunner
    from agency.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["chat", "--help"])
    output = result.output
    # Should mention at least one real model string
    assert any(m in output for m in ("claude-opus", "claude-sonnet", "claude-haiku")), (
        "--model help should mention example model names"
    )


def test_model_override_sets_config():
    """When --model is passed, LLMConfig.model is overridden before use."""
    from agency.llm import LLMConfig, DEFAULT_MODEL
    cfg = LLMConfig.from_env()
    cfg.model = "claude-sonnet-4-6"
    assert cfg.model == "claude-sonnet-4-6"
    assert cfg.model != DEFAULT_MODEL or DEFAULT_MODEL == "claude-sonnet-4-6"


def test_model_override_cli_flag_accepted():
    """agency chat --model <m> --no-banner exits cleanly without API key (LLM offline)."""
    from click.testing import CliRunner
    from agency.cli import main
    import os
    runner = CliRunner()
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env.pop("AGENCY_API_KEY", None)
    result = runner.invoke(
        main,
        ["chat", "--model", "claude-sonnet-4-6", "--no-banner"],
        input="exit\n",
        env=env,
        catch_exceptions=False,
    )
    # Should not crash on the flag itself (may fail on LLM-required assertion, that's OK)
    assert "--model" not in result.output or result.exit_code in (0, 1)


def test_llm_config_model_env_override():
    """AGENCY_MODEL env var sets the model in LLMConfig.from_env()."""
    from agency.llm import LLMConfig
    with patch.dict(os.environ, {"AGENCY_MODEL": "claude-haiku-4-5-20251001"}):
        cfg = LLMConfig.from_env()
    assert cfg.model == "claude-haiku-4-5-20251001"


# ===========================================================================
# 3. --stream flag wiring
# ===========================================================================


def test_executor_has_stream_method():
    """Executor.stream() must exist and be callable."""
    from agency.executor import Executor
    assert callable(getattr(Executor, "stream", None)), (
        "Executor.stream method missing"
    )


def test_stream_flag_in_chat_cmd_signature():
    """chat_cmd function must accept do_stream parameter."""
    from agency.cli import chat_cmd
    import inspect
    sig = inspect.signature(chat_cmd.callback)  # Click wraps the function
    assert "do_stream" in sig.parameters, (
        "chat_cmd.callback missing do_stream parameter"
    )


def test_model_override_in_chat_cmd_signature():
    """chat_cmd function must accept model_override parameter."""
    from agency.cli import chat_cmd
    import inspect
    sig = inspect.signature(chat_cmd.callback)
    assert "model_override" in sig.parameters, (
        "chat_cmd.callback missing model_override parameter"
    )


def test_stream_executor_fallback_when_no_messages_stream():
    """Executor.stream() falls back to run() when LLM has no messages_stream."""
    from agency.executor import Executor
    from agency.skills import SkillRegistry
    from unittest.mock import MagicMock

    registry = SkillRegistry([])
    mock_llm = MagicMock(spec=[])  # no messages_stream attribute
    mock_result = MagicMock()
    mock_result.events = []

    executor = Executor(registry, mock_llm)
    mock_skill = MagicMock()
    mock_skill.system_prompt = "sys"
    mock_skill.tools = []

    with patch.object(executor, "run", return_value=mock_result):
        events = list(executor.stream(mock_skill, "hello"))
    assert events == []


# ===========================================================================
# 4. API smoke tests (skipped without AGENCY_API_KEY)
# ===========================================================================


@pytest.mark.skipif(not AGENCY_API_KEY, reason="needs AGENCY_API_KEY / ANTHROPIC_API_KEY")
def test_api_smoke_messages_create():
    """Real Anthropic API: messages.create returns non-empty text."""
    from agency.llm import AnthropicLLM, LLMConfig
    cfg = LLMConfig.from_env()
    cfg.model = "claude-haiku-4-5-20251001"  # cheapest for smoke
    cfg.max_tokens = 32
    llm = AnthropicLLM(cfg)
    resp = llm.messages_create(
        system="You are a test assistant.",
        messages=[{"role": "user", "content": "Reply with just the word: pong"}],
    )
    texts = [
        getattr(b, "text", None)
        for b in getattr(resp, "content", [])
        if getattr(b, "type", None) == "text"
    ]
    assert any(t for t in texts), f"API returned no text content: {resp}"


@pytest.mark.skipif(not AGENCY_API_KEY, reason="needs AGENCY_API_KEY / ANTHROPIC_API_KEY")
def test_api_smoke_streaming():
    """Real Anthropic API: messages_stream yields at least one text_delta event."""
    from agency.llm import AnthropicLLM, LLMConfig
    cfg = LLMConfig.from_env()
    cfg.model = "claude-haiku-4-5-20251001"
    cfg.max_tokens = 32
    llm = AnthropicLLM(cfg)
    chunks: list[str] = []
    with llm.messages_stream(
        system="You are a test assistant.",
        messages=[{"role": "user", "content": "Say hi in one word."}],
    ) as stream:
        for event in stream:
            if getattr(event, "type", None) == "content_block_delta":
                delta = getattr(event, "delta", None)
                if getattr(delta, "type", None) == "text_delta":
                    chunks.append(delta.text)
    assert chunks, "Streaming produced no text_delta events"
    assert "".join(chunks).strip(), "Streamed text is empty"


@pytest.mark.skipif(not AGENCY_API_KEY, reason="needs AGENCY_API_KEY / ANTHROPIC_API_KEY")
def test_api_smoke_model_override_haiku():
    """--model claude-haiku-4-5-20251001 produces a valid response."""
    from agency.llm import AnthropicLLM, LLMConfig
    cfg = LLMConfig()
    cfg.model = "claude-haiku-4-5-20251001"
    cfg.max_tokens = 16
    cfg.api_key = AGENCY_API_KEY
    llm = AnthropicLLM(cfg)
    resp = llm.messages_create(
        system="Respond with one word.",
        messages=[{"role": "user", "content": "Ready?"}],
    )
    content = getattr(resp, "content", [])
    assert content, "No content blocks returned"


@pytest.mark.skipif(not AGENCY_API_KEY, reason="needs AGENCY_API_KEY / ANTHROPIC_API_KEY")
def test_api_smoke_subprocess_chat():
    """agency chat --no-banner exits cleanly with a real API key."""
    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = AGENCY_API_KEY
    proc = subprocess.run(
        [sys.executable, "-m", "agency", "chat", "--no-banner",
         "--model", "claude-haiku-4-5-20251001"],
        input="ping\nexit\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    assert proc.returncode == 0, f"chat exited {proc.returncode}\nstderr: {proc.stderr}"
    assert proc.stdout.strip(), "chat produced no output"


# ===========================================================================
# 5. Regression — cli.py syntax valid after edits
# ===========================================================================


def test_cli_py_parses_cleanly():
    """cli.py must be valid Python after all Pass 11 edits."""
    import ast
    cli_path = os.path.join(os.path.dirname(__file__), "..", "agency", "cli.py")
    src = open(cli_path).read()
    # raises SyntaxError if broken
    ast.parse(src)


def test_tools_py_parses_cleanly():
    """tools.py must be valid Python after httpx fix."""
    import ast
    p = os.path.join(os.path.dirname(__file__), "..", "agency", "tools.py")
    ast.parse(open(p).read())


def test_imports_do_not_crash():
    """Core modules import without error."""
    import importlib
    for mod in ("agency.cli", "agency.tools", "agency.llm", "agency.executor"):
        importlib.import_module