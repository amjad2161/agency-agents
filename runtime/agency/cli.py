"""Agency runtime CLI: list, run, debug, serve."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from .amjad_jarvis_cli import amjad_group
from .executor import Executor
from .llm import AnthropicLLM, LLMConfig, LLMError
from .logging import configure as configure_logging
from .memory import MemoryStore, Session
from .planner import Planner
from .lessons import (
    ensure_default_lessons,
    lessons_path,
    load_lessons_text,
)
from .profile import (
    ensure_default_profile,
    load_profile_text,
    profile_path,
)
from .skills import SkillRegistry, discover_repo_root
from .jarvis_greeting import get_startup_banner, get_farewell, get_greeting


def _registry(repo: Path | None) -> SkillRegistry:
    root = repo if repo else discover_repo_root()
    return SkillRegistry.load(root)


@click.group()
@click.option("--repo", type=click.Path(file_okay=False, exists=True, path_type=Path),
              help="Path to the Agency repo root. Defaults to autodetect.")
@click.option("-v", "--verbose", count=True,
              help="-v=INFO, -vv=DEBUG. Or set AGENCY_LOG=info/debug.")
@click.pass_context
def main(ctx: click.Context, repo: Path | None, verbose: int) -> None:
    """Agency runtime: orchestrate the persona library as runnable skills."""
    ctx.ensure_object(dict)
    ctx.obj["repo"] = repo
    if verbose >= 2:
        configure_logging("DEBUG")
    elif verbose == 1:
        configure_logging("INFO")
    else:
        configure_logging()  # respects AGENCY_LOG env var; default WARNING


main.add_command(amjad_group, "amjad")


@main.command("list")
@click.option("--category", help="Filter to a single category (e.g., engineering).")
@click.option("--search", help="Keyword search across name/description.")
@click.pass_context
def list_cmd(ctx: click.Context, category: str | None, search: str | None) -> None:
    """List loaded skills."""
    registry = _registry(ctx.obj["repo"])
    skills = registry.search(search) if search else registry.all()
    if category:
        skills = [s for s in skills if s.category == category]
    if not skills:
        click.echo("No skills matched.")
        return
    click.echo(f"{len(skills)} skill(s):")
    for s in skills:
        click.echo(f"  {s.slug:55s}  {s.summary()}")


@main.command("plan")
@click.argument("request")
@click.option("--skill", "skill_slug", help="Force a specific skill slug (skips planner).")
@click.pass_context
def plan_cmd(ctx: click.Context, request: str, skill_slug: str | None) -> None:
    """Show which skill the planner would pick for REQUEST."""
    registry = _registry(ctx.obj["repo"])
    llm = _maybe_llm()
    planner = Planner(registry, llm=llm)
    plan = planner.plan(request, hint_slug=skill_slug)
    click.echo(f"Picked: {plan.skill.slug} — {plan.skill.name}")
    click.echo(f"Reason: {plan.rationale}")
    if len(plan.candidates) > 1:
        click.echo("Shortlist:")
        for c in plan.candidates:
            marker = "*" if c.slug == plan.skill.slug else " "
            click.echo(f"  {marker} {c.slug} — {c.name}")


@main.command("run")
@click.argument("request")
@click.option("--skill", "skill_slug", help="Force a specific skill slug (skips planner).")
@click.option("--session", "session_id", help="Session id to load/save (enables memory).")
@click.option("--workdir", type=click.Path(file_okay=False, path_type=Path),
              help="Workdir for tool calls. Defaults to current directory.")
@click.option("--show-usage/--no-show-usage", default=False,
              help="Print token usage after the run.")
@click.pass_context
def run_cmd(ctx: click.Context, request: str, skill_slug: str | None,
            session_id: str | None, workdir: Path | None,
            show_usage: bool) -> None:
    """Run REQUEST through the planner and execute it."""
    # Show JARVIS greeting banner on startup
    click.echo(get_startup_banner({"mode": "supreme_brainiac", "systems_ok": 21, "systems_total": 21}), err=True)
    registry = _registry(ctx.obj["repo"])
    try:
        llm = _require_llm()
    except LLMError as e:
        raise click.ClickException(str(e))

    planner = Planner(registry, llm=llm)
    plan = planner.plan(request, hint_slug=skill_slug)
    click.echo(f"→ {plan.skill.emoji} {plan.skill.name} ({plan.skill.slug}) — {plan.rationale}", err=True)

    # Memory + persistence is opt-in: only wire them up when the user passes
    # --session, so ad-hoc runs don't accumulate files or enable the plan tool.
    memory: MemoryStore | None = None
    session: Session | None = None
    sid: str | None = None
    if session_id:
        sid = session_id
        memory = MemoryStore(Path.home() / ".agency" / "sessions")
        session = memory.load(sid) or Session(session_id=sid, skill_slug=plan.skill.slug)

    executor = Executor(registry, llm, memory=memory, workdir=workdir)
    result = executor.run(plan.skill, request, session=session)
    click.echo(result.text)
    if show_usage:
        u = result.usage
        click.echo(
            f"\n[usage] input={u.input_tokens} output={u.output_tokens} "
            f"cache_write={u.cache_creation_input_tokens} "
            f"cache_read={u.cache_read_input_tokens} turns={result.turns}",
            err=True,
        )
    if session_id:
        click.echo(f"\n[session saved: {sid}]", err=True)
    click.echo(get_farewell(), err=True)


@main.command("debug")
@click.argument("request")
@click.option("--skill", "skill_slug", help="Force a specific skill slug.")
@click.pass_context
def debug_cmd(ctx: click.Context, request: str, skill_slug: str | None) -> None:
    """Run REQUEST and print every event (text, tool_use, tool_result)."""
    registry = _registry(ctx.obj["repo"])
    try:
        llm = _require_llm()
    except LLMError as e:
        raise click.ClickException(str(e))
    planner = Planner(registry, llm=llm)
    plan = planner.plan(request, hint_slug=skill_slug)
    click.echo(f"→ skill: {plan.skill.slug} ({plan.rationale})")
    executor = Executor(registry, llm)
    result = executor.run(plan.skill, request)
    for ev in result.events:
        if ev.kind == "text":
            click.echo(f"[text] {ev.payload}")
        elif ev.kind == "tool_use":
            click.echo(f"[tool_use] {ev.payload['name']}({ev.payload['input']})")
        elif ev.kind == "tool_result":
            tag = "tool_error" if ev.payload["is_error"] else "tool_result"
            preview = ev.payload["content"][:400]
            click.echo(f"[{tag}] {ev.payload['name']}: {preview}")
        elif ev.kind == "stop":
            click.echo(f"[stop] {ev.payload}")
    click.echo(f"\nturns: {result.turns}")


@main.command("init")
@click.argument("slug")
@click.option("--name", help="Human-readable name (default: derived from slug).")
@click.option("--category", default="specialized", show_default=True,
              help="Category folder under the repo root.")
@click.option("--emoji", default="🤖", show_default=True)
@click.option("--description", default="A specialized agent.", show_default=True)
@click.pass_context
def init_cmd(ctx: click.Context, slug: str, name: str | None, category: str,
             emoji: str, description: str) -> None:
    """Scaffold a new persona markdown file at <category>/<slug>.md."""
    root = ctx.obj["repo"] if ctx.obj["repo"] else discover_repo_root()
    target_dir = root / category
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{slug}.md"
    if path.exists():
        raise click.ClickException(f"{path} already exists.")
    nice_name = name or slug.replace("-", " ").title()
    body = (
        f"---\n"
        f"name: {nice_name}\n"
        f"description: {description}\n"
        f"color: cyan\n"
        f"emoji: {emoji}\n"
        f"vibe: Purpose-built specialist. Edit this file to shape its voice.\n"
        f"---\n\n"
        f"# {nice_name} Agent Personality\n\n"
        f"You are **{nice_name}**. {description}\n\n"
        f"## 🧠 Your Identity & Memory\n"
        f"- **Role**: [fill in]\n"
        f"- **Personality**: [fill in]\n\n"
        f"## 🎯 Your Core Mission\n"
        f"- [fill in]\n\n"
        f"## 🚨 Critical Rules You Must Follow\n"
        f"- [fill in]\n"
    )
    path.write_text(body, encoding="utf-8")
    click.echo(f"Created {path.relative_to(root)}")


@main.group("trust", invoke_without_command=True)
@click.pass_context
def trust_cmd(ctx: click.Context) -> None:
    """Show or persist the active trust mode.

    Bare `agency trust` prints the active gate. Subcommands:
      set <mode>   — write `~/.agency/trust.conf` so this machine
                     uses <mode> on every run, no env var needed.
                     Values: off | on-my-machine | yolo.
      clear        — delete `~/.agency/trust.conf` (back to env-var
                     resolution + `off` default).
      path         — print the config file path.

    Resolution order: AGENCY_TRUST_MODE env var → `~/.agency/trust.conf`
    → `off`. The default stays conservative so a fresh clone in CI or a
    shared environment doesn't silently grant the agent everything.
    Personal machines opt in.
    """
    if ctx.invoked_subcommand is not None:
        return
    from .trust import current, gate, trust_conf_path

    mode = current()
    g = gate()
    click.echo(f"trust mode: {mode.value}")
    click.echo()
    click.echo(f"  allow_shell (default)     : {g.allow_shell}")
    click.echo(f"  shell allowlist enforced  : {g.enforce_shell_allowlist}")
    click.echo(f"  shell denylist enforced   : {g.enforce_shell_denylist}")
    click.echo(f"  workdir sandbox enforced  : {g.sandbox_paths_to_workdir}")
    click.echo(f"  block private/loopback IPs: {g.block_private_ip_fetches}")
    click.echo(f"  block metadata endpoints  : {g.block_metadata_fetches}")
    conf = trust_conf_path()
    click.echo()
    click.echo(f"  persistent config         : {conf} {'(present)' if conf.exists() else '(none)'}")


@trust_cmd.command("set")
@click.argument("mode", type=click.Choice(["off", "on-my-machine", "yolo"]))
def trust_set_cmd(mode: str) -> None:
    """Persist the trust mode in `~/.agency/trust.conf`.

    After `agency trust set yolo`, every subsequent run on this machine
    uses YOLO without any env var. Override per-shell with
    `AGENCY_TRUST_MODE=...`.
    """
    from .trust import trust_conf_path

    path = trust_conf_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"# Agency trust mode for this machine.\n"
        f"# Values: off | on-my-machine | yolo. Lines starting with # are\n"
        f"# ignored; the first non-blank, non-comment line wins.\n"
        f"{mode}\n"
    )
    path.write_text(body, encoding="utf-8")
    click.echo(f"Wrote {path} ({mode})")
    if mode == "yolo":
        click.echo(
            "  YOLO is on for this machine. The agent now runs with no shell denylist,\n"
            "  no workdir sandbox, no SSRF block, and no metadata-IP block.\n"
            "  This is the right setting for a laptop you trust; it's the wrong setting\n"
            "  for a shared or production host.",
            err=True,
        )


@trust_cmd.command("clear")
def trust_clear_cmd() -> None:
    """Delete `~/.agency/trust.conf` so resolution falls back to env var + `off`."""
    from .trust import trust_conf_path

    path = trust_conf_path()
    if not path.exists():
        click.echo(f"{path} does not exist; nothing to clear.")
        return
    path.unlink()
    click.echo(f"Deleted {path}")


@trust_cmd.command("path")
def trust_path_cmd() -> None:
    """Print the resolved config path."""
    from .trust import trust_conf_path

    click.echo(str(trust_conf_path()))


@main.command("doctor")
@click.pass_context
def doctor_cmd(ctx: click.Context) -> None:
    """Diagnose the runtime: show what's loaded, enabled, and missing."""
    import os

    from .diagnostics import optional_deps_status
    from .tools import ToolContext

    click.echo("=== Agency Runtime Doctor ===\n")

    # Repo + skills
    try:
        root = ctx.obj["repo"] if ctx.obj["repo"] else discover_repo_root()
        click.echo(f"repo root: {root}")
    except FileNotFoundError as e:
        click.echo(f"repo root: ERROR — {e}")
        return
    try:
        registry = SkillRegistry.load(root)
    except Exception as e:  # noqa: BLE001
        click.echo(f"skills: ERROR — {type(e).__name__}: {e}")
        return

    click.echo(f"skills loaded: {len(registry)}")
    for cat in registry.categories():
        count = len(registry.by_category(cat))
        click.echo(f"  {cat:22s}  {count}")

    # API key
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    click.echo(f"\nANTHROPIC_API_KEY: {'set ('+str(len(key))+' chars)' if key else 'NOT SET'}")

    # Env flags
    flags = [
        "AGENCY_MODEL", "AGENCY_PLANNER_MODEL", "AGENCY_MAX_TOKENS",
        "AGENCY_TASK_BUDGET", "AGENCY_MCP_SERVERS",
        "AGENCY_ENABLE_WEB_SEARCH", "AGENCY_ENABLE_CODE_EXECUTION",
        "AGENCY_ENABLE_COMPUTER_USE", "AGENCY_ALLOW_SHELL", "AGENCY_NO_NETWORK",
    ]
    click.echo("\nenv flags:")
    for f in flags:
        val = os.environ.get(f)
        click.echo(f"  {f:32s}  {val or '—'}")

    # Optional deps (shared with /api/health via agency.diagnostics)
    click.echo("\noptional deps:")
    for group, info in optional_deps_status().items():
        bracket = f"[{group}]"
        if info["installed"]:
            status = "ok"
        else:
            # Show both — a group can have some missing AND some broken at once
            # (e.g. PIL not installed + pyautogui imports but raises on no DISPLAY).
            parts = []
            if info["missing"]:
                parts.append(f"missing: {', '.join(info['missing'])}")
            if info["errors"]:
                parts.append("broken: " + "; ".join(
                    f"{k}: {v}" for k, v in info["errors"].items()
                ))
            status = "; ".join(parts)
        click.echo(f"  {bracket:12s}  {status}")

    # Tool context defaults
    tc = ToolContext.from_env()
    click.echo(
        f"\ntool context:\n"
        f"  allow_shell={tc.allow_shell}  "
        f"allow_network={tc.allow_network}  "
        f"allow_computer_use={tc.allow_computer_use}  "
        f"timeout={tc.timeout_s}s"
    )

    # Trust mode
    from .trust import current as _trust_current
    click.echo(f"\nAGENCY_TRUST_MODE: {_trust_current().value}")

    click.echo("\nDone.")


@main.group("profile", invoke_without_command=True)
@click.pass_context
def profile_cmd(ctx: click.Context) -> None:
    """Manage the always-on user profile (~/.agency/profile.md by default).

    Anything in this file is sent to every agent as background context.
    Run `agency profile show` (or just `agency profile`) to view it,
    `agency profile path` to print where it lives, `agency profile edit`
    to open it in $EDITOR, and `agency profile clear` to delete it.
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(profile_show_cmd)


@profile_cmd.command("show")
def profile_show_cmd() -> None:
    """Print the current profile, or report why nothing is loaded."""
    p = profile_path()
    text = load_profile_text(p)
    if text is None:
        # Distinguish "no file at all" from "exists but empty/unreadable" so the
        # user knows whether to create or fix.
        if not p.exists():
            click.echo(f"No profile file at {p}.")
            click.echo("Create one with `agency profile edit`.")
        else:
            click.echo(f"Profile at {p} is empty or unreadable.")
            click.echo("Open it with `agency profile edit` to add content.")
        return
    click.echo(text)


@profile_cmd.command("path")
def profile_path_cmd() -> None:
    """Print the path the runtime would read."""
    click.echo(str(profile_path()))


@profile_cmd.command("edit")
def profile_edit_cmd() -> None:
    """Open the profile in $EDITOR (creating a starter template if needed)."""
    p = ensure_default_profile()
    click.edit(filename=str(p))


@profile_cmd.command("clear")
def profile_clear_cmd() -> None:
    """Delete the profile file (the runtime will then send no profile context)."""
    p = profile_path()
    if not p.exists():
        click.echo(f"No profile at {p}; nothing to remove.")
        return
    if not p.is_file():
        raise click.ClickException(
            f"Profile path is not a regular file and cannot be removed: {p}"
        )
    try:
        p.unlink()
    except OSError as e:
        raise click.ClickException(f"Could not remove profile {p}: {e}") from e
    click.echo(f"Removed {p}.")


@main.group("lessons", invoke_without_command=True)
@click.pass_context
def lessons_cmd(ctx: click.Context) -> None:
    """Manage the cross-session lessons journal (~/.agency/lessons.md).

    The lessons file is read at the start of every agent run — it's the
    durable cross-session memory that lets the agent carry context
    forward without re-training. Subcommands:
      show / (bare)   — print current lessons
      path            — print the resolved file path
      edit            — open in $EDITOR (creates a starter if missing)
      add <line>      — append a one-liner with a timestamp
      clear           — delete the file
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(lessons_show_cmd)


@lessons_cmd.command("show")
def lessons_show_cmd() -> None:
    """Print the current lessons journal."""
    p = lessons_path()
    text = load_lessons_text(p)
    if text is None:
        if not p.exists():
            click.echo(f"No lessons file at {p}.")
            click.echo("Create one with `agency lessons edit` or `agency lessons add ...`.")
        else:
            click.echo(f"Lessons at {p} is empty or unreadable.")
        return
    click.echo(text)


@lessons_cmd.command("path")
def lessons_path_cmd() -> None:
    """Print the path the runtime would read."""
    click.echo(str(lessons_path()))


@lessons_cmd.command("edit")
def lessons_edit_cmd() -> None:
    """Open the lessons journal in $EDITOR (creating a starter if needed)."""
    p = ensure_default_lessons()
    click.edit(filename=str(p))


@lessons_cmd.command("add")
@click.argument("text", nargs=-1, required=True)
def lessons_add_cmd(text: tuple[str, ...]) -> None:
    """Append a one-liner lesson with a timestamp.

    Quote multi-word lessons or pass them as separate args; the runtime
    joins them with a single space.
    """
    from datetime import datetime, timezone

    p = ensure_default_lessons()
    line = " ".join(text).strip()
    if not line:
        raise click.ClickException("Lesson text cannot be empty.")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with p.open("a", encoding="utf-8") as f:
        f.write(f"\n## {stamp} · quick note\n\n{line}\n")
    click.echo(f"Appended to {p}.")


@lessons_cmd.command("clear")
def lessons_clear_cmd() -> None:
    """Delete the lessons file (the runtime will then send no lessons context)."""
    p = lessons_path()
    if not p.exists():
        click.echo(f"No lessons at {p}; nothing to remove.")
        return
    if not p.is_file():
        raise click.ClickException(
            f"Lessons path is not a regular file and cannot be removed: {p}"
        )
    try:
        p.unlink()
    except OSError as e:
        raise click.ClickException(f"Could not remove lessons {p}: {e}") from e
    click.echo(f"Removed {p}.")


@main.command("serve")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8765, type=int)
@click.pass_context
def serve_cmd(ctx: click.Context, host: str, port: int) -> None:
    """Start the FastAPI web UI."""
    try:
        import uvicorn
    except ImportError as e:
        raise click.ClickException("uvicorn not installed. Install runtime deps.") from e
    from .server import build_app

    repo = ctx.obj["repo"]
    app = build_app(repo)
    click.echo(f"Agency runtime listening on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


@main.command("hud")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8765, type=int)
@click.option("--no-browser", is_flag=True,
              help="Don't auto-open the browser.")
@click.pass_context
def hud_cmd(ctx: click.Context, host: str, port: int, no_browser: bool) -> None:
    """Launch the GRAVIS HUD — same as `agency serve` but opens
    a browser at the chat URL after the server binds the port."""
    try:
        import uvicorn
    except ImportError as e:
        raise click.ClickException("uvicorn not installed. Install runtime deps.") from e
    from .server import build_app

    repo = ctx.obj["repo"]
    app = build_app(repo)
    url = f"http://{host}:{port}"
    click.echo(f"GRAVIS HUD launching on {url}")

    if not no_browser:
        # Spawn a one-shot thread that polls the port and opens the
        # browser only once the server is actually listening — avoids
        # the "site can't be reached" race.
        import socket
        import threading
        import time
        import webbrowser

        def _open_when_ready() -> None:
            for _ in range(40):  # ~10s budget @ 250ms each
                time.sleep(0.25)
                try:
                    with socket.create_connection((host, port), timeout=0.5):
                        webbrowser.open(url)
                        return
                except OSError:
                    continue

        threading.Thread(target=_open_when_ready, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")


@main.command("evolve")
@click.option("--rewrite/--bench-only", default=True,
              help="If --bench-only, only measure timings; don't ask the "
                   "LLM to rewrite slow tools. Default: --rewrite.")
@click.option("--dry-run", is_flag=True,
              help="Generate rewrites but don't replace files on disk.")
@click.pass_context
def evolve_cmd(ctx: click.Context, rewrite: bool, dry_run: bool) -> None:
    """Benchmark every tool under ~/.agency/tools/ and rewrite the slow ones.

    Walks each *.py file with a BENCH list, runs its run() function 3
    times per case, and (with --rewrite) asks the LLM to produce a
    faster version. Replaces the file only if the new version both
    passes BENCH and is at least as fast as the original at the median.
    Original is backed up to <name>.py.bak.<timestamp>.
    """
    from .daemons.tool_evolver import evolve_all, tools_dir

    d = tools_dir()
    if not d.is_dir():
        click.echo(f"No tools directory at {d}.")
        click.echo(f"Create one and drop *.py files with run(input) + BENCH "
                   f"defined to enable evolution.")
        return

    llm = None
    if rewrite:
        try:
            llm = _require_llm()
        except LLMError as e:
            click.echo(f"--rewrite requested but no LLM available: {e}",
                       err=True)
            click.echo("Falling back to bench-only.", err=True)
            llm = None

    found = 0
    for report in evolve_all(llm=llm, dry_run=dry_run):
        found += 1
        line = f"  {report.path.name:30s}  median={report.median_elapsed_s*1000:7.1f}ms"
        if report.skipped_reason:
            click.echo(f"{line}  · skipped: {report.skipped_reason}")
        elif report.rewrite_succeeded:
            tag = "(dry-run)" if dry_run else "REWROTE"
            click.echo(f"{line}  · {tag} ({report.rewrite_diff_lines:+d} lines)")
        elif report.rewrite_attempted:
            click.echo(f"{line}  · rewrite attempted but not applied")
        elif report.is_slow:
            click.echo(f"{line}  · slow but rewrite disabled")
        else:
            click.echo(f"{line}  · ok")
    if found == 0:
        click.echo(f"No *.py tool files found in {d}.")


# Wire the Amjad-Jarvis subcommand group into the main CLI as `agency amjad …`.
# The group lives in its own module so the orchestrator-specific code stays
# isolated from the core CLI; this just gives it a stable entry point.
try:
    from .amjad_jarvis_cli import amjad_group as _amjad_group
    main.add_command(_amjad_group, name="amjad")
except ImportError:
    # The amjad_jarvis module is optional — if it (or one of its
    # dependencies) isn't installed, skip wiring the subcommand. Other
    # import-time errors (SyntaxError, attribute lookups, etc.) are
    # bugs and should still surface instead of being silently swallowed.
    pass


# ----- learn / reason / context / expand commands -----------------------------
#
# These four commands surface the new capability modules
# (self_learner_engine, meta_reasoner, context_manager, knowledge_expansion)
# at the CLI without forcing the user to drop into a Python REPL.
# They share the same persistent storage as the lazy getters in
# `agency.__init__`, so what you record here shows up in every later
# `agency run` / `agency reason` invocation.


@main.command("learn")
@click.argument("request")
@click.option("--response", default="",
              help="What JARVIS replied. Empty = routing-only record.")
@click.option("--feedback", default=None,
              help="Optional human feedback ('good', 'wrong domain', etc.). "
                   "Drives outcome + confidence inference.")
@click.option("--routed-to", "routed_to", default=None,
              help="Domain slug the request was routed to.")
@click.option("--correct-slug", "correct_slug", default=None,
              help="If routing was wrong, the slug it should have used.")
def learn_cmd(request: str, response: str, feedback: str | None,
              routed_to: str | None, correct_slug: str | None) -> None:
    """Record a structured lesson into the lessons JSONL.

    Different from `agency lessons add`: that one writes free-text to
    lessons.md. This one writes a typed `Lesson` row that the runtime
    can surface later for routing corrections and growth reports.
    """
    from .self_learner_engine import SelfLearnerEngine
    engine = SelfLearnerEngine()
    lesson = engine.record_interaction(
        request=request,
        response=response,
        feedback=feedback,
        routed_to=routed_to,
        correct_slug=correct_slug,
    )
    click.echo(f"recorded lesson @ {lesson.timestamp}")
    click.echo(f"  context     : {lesson.context}")
    click.echo(f"  insight     : {lesson.insight}")
    click.echo(f"  outcome     : {lesson.outcome}")
    click.echo(f"  confidence  : {lesson.confidence:.2f}")
    if lesson.applies_to:
        click.echo(f"  applies_to  : {', '.join(lesson.applies_to)}")
    if lesson.routing_correction:
        click.echo(f"  correction  : {lesson.routing_correction}")


@main.command("reason")
@click.argument("goal")
@click.option("--iterations", type=click.IntRange(1, 32), default=5,
              show_default=True, help="Max ReAct loop iterations.")
@click.option("--plan", "do_plan", is_flag=True, default=False,
              help="Emit a markdown execution plan instead of raw steps.")
def reason_cmd(goal: str, iterations: int, do_plan: bool) -> None:
    """Run a multi-step reasoning loop against a goal.

    Without an LLM wired in, the engine produces a deterministic
    decomposition of the goal into thought / action / observation
    triples. Useful for verifying the loop machinery and for offline
    planning before a real LLM call.
    """
    from .meta_reasoner import MetaReasoningEngine
    engine = MetaReasoningEngine()
    if do_plan:
        click.echo(engine.plan_and_execute(goal))
        return
    steps = engine.reason(goal, max_iterations=iterations)
    for s in steps:
        action = s.action or "(no action)"
        observation = (s.observation or "")[:120]
        click.echo(
            f"  #{s.step_id} [{s.confidence:.2f}] {action}: {observation}"
        )
    click.echo(f"avg_confidence={engine.avg_confidence():.3f} steps={len(steps)}")


@main.group("context", invoke_without_command=True)
@click.pass_context
def context_cmd(ctx: click.Context) -> None:
    """Working-context store: short-lived domain-scoped key/value memory."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@context_cmd.command("store")
@click.argument("key")
@click.argument("value")
@click.option("--domain", default="default", show_default=True)
@click.option("--ttl", "ttl_seconds", type=int, default=3600,
              show_default=True, help="Seconds before expiry. 0 = never.")
def context_store_cmd(key: str, value: str, domain: str,
                      ttl_seconds: int) -> None:
    from .context_manager import ContextManager
    cm = _shared_context_manager()
    cm.store(key, value, domain=domain, ttl_seconds=ttl_seconds)
    click.echo(f"stored {domain}:{key} (ttl={ttl_seconds}s)")


@context_cmd.command("recall")
@click.argument("key")
@click.option("--domain", default="default", show_default=True)
def context_recall_cmd(key: str, domain: str) -> None:
    cm = _shared_context_manager()
    val = cm.recall(key, domain=domain)
    if val is None:
        click.echo(f"no live entry for {domain}:{key}", err=True)
        sys.exit(1)
    click.echo(val)


@context_cmd.command("list")
@click.option("--domain", default=None,
              help="Restrict to one domain. Default: list all domains.")
def context_list_cmd(domain: str | None) -> None:
    cm = _shared_context_manager()
    if domain is None:
        for d in cm.all_domains():
            click.echo(f"{d}: {len(cm.dump_domain(d))} entries")
        return
    body = cm.dump_domain(domain)
    if not body:
        click.echo(f"(no live entries in {domain})")
        return
    for k, v in sorted(body.items()):
        click.echo(f"{k}: {v}")


# Shared in-process context manager — survives across click commands
# inside the same `agency` invocation. (CLI processes are short-lived
# so cross-invocation persistence belongs in the durable stores.)
_CTX_MANAGER_SINGLETON: "object | None" = None


def _shared_context_manager() -> Any:
    global _CTX_MANAGER_SINGLETON
    if _CTX_MANAGER_SINGLETON is None:
        from .context_manager import ContextManager
        _CTX_MANAGER_SINGLETON = ContextManager()
    return _CTX_MANAGER_SINGLETON


@main.command("expand")
@click.argument("source")
@click.option("--domain", default="default", show_default=True)
@click.option("--url", "is_url", is_flag=True, default=False,
              help="Treat SOURCE as a URL to fetch instead of literal text.")
@click.option("--search", "search_query", default=None,
              help="Don't ingest — search the existing store for this query.")
@click.option("--top-k", "top_k", type=int, default=5, show_default=True)
def expand_cmd(source: str, domain: str, is_url: bool,
               search_query: str | None, top_k: int) -> None:
    """Ingest text/URL into the knowledge store, or search it.

    Without --search, ingests SOURCE (literal text by default, or a URL
    with --url). With --search, treats SEARCH_QUERY as a substring/tag
    query and prints the top matches.
    """
    ke = _shared_knowledge_expansion()
    if search_query is not None:
        hits = ke.search(search_query, domain=domain, top_k=top_k)
        if not hits:
            click.echo("(no matches)")
            return
        for h in hits:
            preview = h.text[:160].replace("\n", " ")
            click.echo(f"[{h.chunk_id}] {h.source} :: {preview}")
        return
    try:
        if is_url:
            chunks = ke.ingest_url(source, domain=domain)
        else:
            chunks = ke.ingest_text(source, source="cli", domain=domain)
    except (ValueError, RuntimeError, PermissionError) as e:
        click.echo(f"ingest failed: {e}", err=True)
        sys.exit(1)
    total_chars = sum(len(c.text) for c in chunks)
    click.echo(f"ingested {len(chunks)} chunk(s) ({total_chars} chars, "
               f"domain={domain})")
    for c in chunks:
        if c.tags:
            click.echo(f"  [{c.chunk_id}] tags: {', '.join(c.tags)}")
        else:
            click.echo(f"  [{c.chunk_id}]")


# Shared in-process knowledge expansion — survives across click commands
# inside the same `agency` invocation. KnowledgeExpansion holds chunks in
# memory only; without a singleton, ingest + search across two `agency
# expand` calls in the same Click runner would see different stores.
_KE_SINGLETON: "object | None" = None


def _shared_knowledge_expansion() -> Any:
    global _KE_SINGLETON
    if _KE_SINGLETON is None:
        from .knowledge_expansion import KnowledgeExpansion
        _KE_SINGLETON = KnowledgeExpansion()
    return _KE_SINGLETON


# ---------------------------------------------------------------------------
# `agency history` — list / replay saved chat sessions
# ---------------------------------------------------------------------------

@main.group("history", invoke_without_command=True)
@click.pass_context
def history_cmd(ctx: click.Context) -> None:
    """List or replay saved chat sessions from ~/.agency/history/.

    Subcommands:
      list   — show the N most recent sessions (default)
      show N — print the Nth session (1 = most recent)
      dir    — print the history directory path
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(history_list_cmd, limit=10)


@history_cmd.command("list")
@click.option("--limit", default=10, show_default=True, type=int,
              help="Number of recent sessions to show.")
def history_list_cmd(limit: int) -> None:
    """List the most recent chat sessions."""
    from .history import list_sessions, session_summary
    sessions = list_sessions(limit=limit)
    if not sessions:
        click.echo("No chat history found. Start a session with `agency chat`.")
        return
    click.echo(f"Recent chat sessions ({len(sessions)} shown):")
    for i, p in enumerate(sessions, 1):
        click.echo(f"  {i:3d}.  {session_summary(p)}")


@history_cmd.command("show")
@click.argument("n", type=int, default=1)
def history_show_cmd(n: int) -> None:
    """Replay session N (1 = most recent) to stdout."""
    from .history import list_sessions, read_session
    sessions = list_sessions(limit=n)
    if not sessions or n > len(sessions):
        click.echo(f"No session #{n} found.", err=True)
        raise SystemExit(1)
    path = sessions[n - 1]
    click.echo(f"=== {path.stem} ===")
    for msg in read_session(path):
        role = msg.get("role", "?").upper()
        ts = msg.get("timestamp", "")[:19]
        content = msg.get("content", "")
        click.echo(f"\n[{role}] {ts}\n{content}")


@history_cmd.command("dir")
def history_dir_cmd() -> None:
    """Print the history directory path."""
    from .history import history_dir
    click.echo(str(history_dir()))


# ---------------------------------------------------------------------------
# `agency stats` — cumulative token usage
# ---------------------------------------------------------------------------

@main.command("stats")
@click.option("--reset", is_flag=True, default=False,
              help="Zero out all accumulated stats.")
@click.option("--json", "as_json", is_flag=True, default=False,
              help="Output raw JSON.")
def stats_cmd(reset: bool, as_json: bool) -> None:
    """Show cumulative token usage stored in ~/.agency/stats.json."""
    import json as _json
    from .stats import get_stats, reset_stats, format_stats
    if reset:
        reset_stats()
        click.echo("Stats reset.")
        return
    data = get_stats()
    if as_json:
        click.echo(_json.dumps(data, indent=2))
    else:
        click.echo(format_stats(data))


def _maybe_llm() -> AnthropicLLM | None:
    """Return an LLM client if configured, else None (for offline planning)."""
    try:
        llm = AnthropicLLM(LLMConfig.from_env())
        llm._ensure_client()  # noqa: SLF001 — surface error early
        return llm
    except LLMError:
        return None


def _require_llm() -> AnthropicLLM:
    llm = AnthropicLLM(LLMConfig.from_env())
    llm._ensure_client()  # noqa: SLF001
    return llm


if __name__ == "__main__":
    sys.exit(main())


# ---------------------------------------------------------------------------
# `agency chat` — interactive REPL with JARVIS soul + greeting
# ---------------------------------------------------------------------------

@main.command("chat")
@click.option("--session", "session_id", default=None,
              help="Session ID for persistent memory across chat turns.")
@click.option("--mode", "persona_mode", default="supreme_brainiac", show_default=True,
              help="Persona mode (supreme_brainiac, technical, casual, …).")
@click.option("--no-banner", is_flag=True, default=False,
              help="Skip the startup banner.")
@click.option("--model", "model_override", default=None,
              help="Model to use, e.g. claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001.")
@click.option("--stream", "do_stream", is_flag=True, default=False,
              help="Stream tokens to stdout as they arrive.")
@click.pass_context
def chat_cmd(
    ctx: click.Context,
    session_id: str | None,
    persona_mode: str,
    no_banner: bool,
    model_override: str | None,
    do_stream: bool,
) -> None:
    """Interactive JARVIS chat — greeting, REPL loop, Ctrl+C to exit.

    Routes every message through the skill planner (LLM-backed if
    ANTHROPIC_API_KEY is set, deterministic otherwise), then filters
    the response through the JARVIS soul to strip forbidden phrases.
    """
    import sys

    from .jarvis_greeting import get_startup_banner, get_greeting, get_farewell
    from .jarvis_soul import filter_response
    from .jarvis_brain import SupremeJarvisBrain

    # ---- startup ---------------------------------------------------------
    registry = _registry(ctx.obj.get("repo"))
    # Build LLM with optional model override from --model flag.
    try:
        cfg = LLMConfig.from_env()
        if model_override:
            cfg.model = model_override
        llm: AnthropicLLM | None = AnthropicLLM(cfg)
        llm._ensure_client()  # noqa: SLF001
    except LLMError:
        llm = None
    planner = Planner(registry, llm=llm)
    brain = SupremeJarvisBrain(registry)

    memory_store: MemoryStore | None = None
    sid: str | None = session_id
    if sid:
        memory_store = MemoryStore(Path.home() / ".agency" / "sessions")

    if not no_banner:
        n_skills = len(registry)
        banner = get_startup_banner({
            "mode": persona_mode,
            "systems_ok": n_skills,
            "systems_total": n_skills,
        })
        click.echo(banner)
        click.echo()

    click.echo(get_greeting())
    click.echo()
    llm_status = "LLM: online" if llm else "LLM: offline (deterministic routing)"
    click.echo(f"[{llm_status} | {len(registry)} skills | Ctrl+C to exit]\n")

    # ---- REPL loop (wrapped in HistoryWriter) ----------------------------
    from .history import HistoryWriter
    with HistoryWriter() as hw:
        click.echo(f"[session saved → {hw.path}]", err=True)
        while True:
            try:
                raw = click.prompt("Amjad", prompt_suffix=" ❯ ", default="", show_default=False)
            except click.Abort:
                # Ctrl+C or Ctrl+D
                click.echo()
                click.echo(get_farewell())
                break

            request = raw.strip()
            if not request:
                continue

            # Handle built-in meta-commands
            if request.lower() in ("exit", "quit", "bye", "!q"):
                click.echo(get_farewell())
                break
            if request.lower() in ("help", "?"):
                click.echo(
                    "Commands: exit/quit/bye — end session | "
                    "!skills — list loaded skills | "
                    "!route <text> — show routing only"
                )
                continue
            if request.lower() == "!skills":
                for s in registry.all()[:20]:
                    click.echo(f"  {s.slug:<50}  {s.name}")
                if len(registry) > 20:
                    click.echo(f"  … and {len(registry) - 20} more")
                continue
            if request.lower().startswith("!route "):
                query = request[7:].strip()
                result = brain.skill_for(query)
                click.echo(f"→ {result.skill.slug} (score={result.score:.1f}) — {result.rationale}")
                continue

            # Record user turn
            hw.append("user", request)

            # Route and execute
            try:
                plan = planner.plan(request)
                click.echo(
                    f"  → {plan.skill.emoji} {plan.skill.name} ({plan.skill.slug})",
                    err=True,
                )

                session_obj = None
                if sid and memory_store:
                    session_obj = memory_store.load(sid) or Session(
                        session_id=sid, skill_slug=plan.skill.slug
                    )

                assert llm is not None, "LLM required for chat; set ANTHROPIC_API_KEY"
                executor = Executor(registry, llm, memory=memory_store)

                if do_stream:
                    # Stream tokens as they arrive; collect for soul filter.
                    text_buf: list[str] = []
                    for event in executor.stream(plan.skill, request, session=session_obj):
                        if event.type == "text_delta":
                            click.echo(event.data, nl=False)
                            text_buf.append(event.data)
                    raw_text = "".join(text_buf)
                    # Apply soul filter to the final assembled text (print diff if any).
                    filtered = filter_response(raw_text)
                    if filtered != raw_text:
                        click.echo("\n" + filtered)
                    else:
                        click.echo()  # newline after streamed output
                    hw.append("assistant", filtered)
                else:
                    run_result = executor.run(plan.skill, request, session=session_obj)
                    # Filter through JARVIS soul before display
                    output = filter_response(run_result.text)
                    click.echo(output)
                    hw.append("assistant", output)

            except KeyboardInterrupt:
                click.echo()
                click.echo(get_farewell())
                break
            except Exception as exc:  # noqa: BLE001
                click.echo(f"[JARVIS ERROR] {type(exc).__name__}: {exc}", err=True)

            click.echo()

            try:
                raw = click.prompt("Amjad", prompt_suffix=" ❯ ", default="", show_default=False)
            except click.Abort:
                click.echo()
                click.echo(get_farewell())
                break

            request = raw.strip()
            if not request:
                continue

            if request.lower() in ("exit", "quit", "bye", "!q"):
                click.echo(get_farewell())
                break
            if request.lower() in ("help", "?"):
                click.echo(
                    "Commands: exit/quit/bye — end session | "
                    "!skills — list loaded skills | "
                    "!route <text> — show routing only"
                )
                continue
            if request.lower() == "!skills":
                for s in registry.all()[:20]:
                    click.echo(f"  {s.slug:<50}  {s.name}")
                if len(registry) > 20:
                    click.echo(f"  … and {len(registry) - 20} more")
                continue
            if request.lower().startswith("!route "):
                query = request[7:].strip()
                result = brain.skill_for(query)
                click.echo(f"→ {result.skill.slug} (score={result.score:.1f}) — {result.rationale}")
                continue

            hw.append("user", request)

            try:
                plan = planner.plan(request)
                click.echo(
                    f"  → {plan.skill.emoji} {plan.skill.name} ({plan.skill.slug})",
                    err=True,
                )

                session_obj = None
                if sid and memory_store:
                    session_obj = memory_store.load(sid) or Session(
                        session_id=sid, skill_slug=plan.skill.slug
                    )

                assert llm is not None, "LLM required for chat; set ANTHROPIC_API_KEY"
                executor = Executor(registry, llm, memory=memory_store)

                if do_stream:
                    text_buf: list[str] = []
                    for event in executor.stream(plan.skill, request, session=session_obj):
                        if event.type == "text_delta":
                            click.echo(event.data, nl=False)
                            text_buf.append(event.data)
                    raw_text = "".join(text_buf)
                    filtered = filter_response(raw_text)
                    if filtered != raw_text:
                        click.echo("\n" + filtered)
                    else:
                        click.echo()
                    hw.append("assistant", filtered)
                else:
                    run_result = executor.run(plan.skill, request, session=session_obj)
                    output = filter_response(run_result.text)
                    click.echo(output)
                    hw.append("assistant", output)

            except KeyboardInterrupt:
                click.echo()
                click.echo(get_farewell())
                break
            except Exception as exc:  # noqa: BLE001
                click.echo(f"[JARVIS ERROR] {type(exc).__name__}: {exc}", err=True)

            click.echo()




# ---------------------------------------------------------------------------
# `agency batch` — run a script file of prompts
# ---------------------------------------------------------------------------

@main.command("batch")
@click.argument("script", type=click.Path(exists=True, path_type=Path))
@click.option("--parallel", default=1, type=int, show_default=True,
              help="Number of concurrent workers (1 = sequential).")
@click.option("--skill", "skill_slug", default=None,
              help="Force a specific skill slug for every prompt.")
@click.pass_context
def batch_cmd(
    ctx: click.Context,
    script: Path,
    parallel: int,
    skill_slug: str | None,
) -> None:
    """Run every prompt in SCRIPT through JARVIS and write <script>.output.md."""
    from .batch import BatchRunner

    registry = _registry(ctx.obj["repo"])
    try:
        llm = _require_llm()
    except LLMError as e:
        raise click.ClickException(str(e))

    planner = Planner(registry, llm=llm)
    executor = Executor(registry, llm)

    def _handler(prompt: str) -> str:
        plan = planner.plan(prompt, hint_slug=skill_slug)
        result = executor.run(plan.skill, prompt)
        return result.text

    def _progress(i: int, total: int, prompt: str) -> None:
        click.echo(f"[{i}/{total}] Processing: {prompt[:60]}…", err=True)

    runner = BatchRunner(handler=_handler, progress_cb=_progress)
    run = runner.run_file(script, parallel=parallel)

    click.echo(
        f"\nBatch complete: {run.succeeded}/{run.total} ok"
        + (f", {run.failed} failed" if run.failed else ""),
        err=True,
    )
    click.echo(f"Output: {run.output_path}")


# ---------------------------------------------------------------------------
# `agency export` — export a chat session
# ---------------------------------------------------------------------------

@main.command("export")
@click.argument("session_id", required=False, default=None)
@click.option("--format", "fmt",
              type=click.Choice(["md", "html", "json"]),
              default="md", show_default=True,
              help="Output format.")
@click.option("--output", "output_path",
              type=click.Path(path_type=Path), default=None,
              help="Output file path. Defaults to ~/Desktop/<session_id>.<ext>.")
def export_cmd(
    session_id: str | None,
    fmt: str,
    output_path: Path | None,
) -> None:
    """Export a chat session to Markdown, HTML, or JSON.

    SESSION_ID is the session stem (e.g. 2025-01-15_143022).
    Omit to export the most recent session.
    """
    from .export import export_session

    try:
        out = export_session(
            session_id=session_id,
            fmt=fmt,  # type: ignore[arg-type]
            output_path=output_path,
        )
    except FileNotFoundError as e:
        raise click.ClickException(str(e))

    click.echo(f"Exported → {out}")


# ---------------------------------------------------------------------------
# `agency dlq` — dead-letter queue management
# ---------------------------------------------------------------------------

@main.group("dlq", invoke_without_command=True)
@click.pass_context
def dlq_cmd(ctx: click.Context) -> None:
    """Manage the dead-letter queue (~/.agency/dlq.jsonl).

    Subcommands:
      list    -- show failed entries (default)
      retry   -- retry all retryable entries
      clear   -- delete the DLQ file
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(dlq_list_cmd)


@dlq_cmd.command("list")
@click.option("--all", "show_all", is_flag=True, default=False,
              help="Include dead (exhausted) entries.")
def dlq_list_cmd(show_all: bool) -> None:
    """List failed items in the dead-letter queue."""
    from .dlq import DeadLetterQueue

    dlq = DeadLetterQueue()
    entries = dlq.list_entries(include_dead=show_all)
    if not entries:
        click.echo("Dead-letter queue is empty.")
        return
    summary = dlq.summary()
    click.echo(
        f"DLQ: {summary.get('total', 0)} entries  "
        f"(failed={summary.get('failed', 0)} "
        f"dead={summary.get('dead', 0)} "
        f"resolved={summary.get('resolved', 0)})"
    )
    click.echo()
    for e in entries:
        from datetime import datetime
        ts = datetime.fromtimestamp(e.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        retries = f"retries={e.retry_count}/3"
        status_icon = "\U0001f480" if e.is_dead else ("✅" if e.status == "resolved" else "❌")
        click.echo(f"  {status_icon} [{e.entry_id}] {ts}  {retries}  {e.status}")
        click.echo(f"       input : {e.input[:80]}")
        click.echo(f"       error : {e.error[:80]}")
        click.echo()


@dlq_cmd.command("retry")
@click.pass_context
def dlq_retry_cmd(ctx: click.Context) -> None:
    """Retry all retryable failed items."""
    from .dlq import DeadLetterQueue

    registry = _registry(ctx.obj["repo"])
    try:
        llm = _require_llm()
    except LLMError as e:
        raise click.ClickException(str(e))

    planner = Planner(registry, llm=llm)
    executor = Executor(registry, llm)

    def _handler(prompt: str) -> None:
        plan = planner.plan(prompt)
        executor.run(plan.skill, prompt)

    dlq = DeadLetterQueue()
    resolved, dead = dlq.retry_all(_handler)
    click.echo(f"DLQ retry: {resolved} resolved, {dead} moved to dead.")


@dlq_cmd.command("clear")
@click.confirmation_option(prompt="Clear the entire dead-letter queue?")
def dlq_clear_cmd() -> None:
    """Delete all entries from the dead-letter queue."""
    from .dlq import DeadLetterQueue

    dlq = DeadLetterQueue()
    n = dlq.clear()
    click.echo(f"Cleared {n} entries.")


# ---------------------------------------------------------------------------
# Pass 14 additions — plugin system, Flask API server, rate limiter stats
# ---------------------------------------------------------------------------

# Patch stats_cmd to support --rate flag
@main.command("rate-status")
def rate_status_cmd() -> None:
    """Show current token-bucket rate limiter level."""
    from .rate_limiter import get_bucket
    bucket = get_bucket()
    level = bucket.get_level()
    click.echo(f"Rate bucket: {level:.1f}/{bucket.max_tokens:.0f} tokens available "
               f"(refill {bucket.refill_rate:.1f}/s)")


# ------------------------------------------------------------------
# agency plugin
# ------------------------------------------------------------------

@main.group("plugin")
def plugin_group() -> None:
    """Manage Agency plugins."""


@plugin_group.command("install")
@click.argument("name")
@click.option("--source", default=None,
              help="Path to a skill YAML or Python module to copy in.")
@click.option("--version", default="0.1.0", show_default=True)
@click.option("--description", default="", help="Short description.")
def plugin_install(name: str, source: str | None, version: str, description: str) -> None:
    """Install a plugin by NAME (optionally copying a --source file)."""
    from .plugins import plugin_install_cmd
    plugin_install_cmd(name, source, version, description)


@plugin_group.command("list")
def plugin_list() -> None:
    """List installed plugins."""
    from .plugins import plugin_list_cmd
    plugin_list_cmd()


@plugin_group.command("remove")
@click.argument("name")
def plugin_remove(name: str) -> None:
    """Remove a plugin by NAME."""
    from .plugins import plugin_remove_cmd
    plugin_remove_cmd(name)


# ------------------------------------------------------------------
# agency serve-api  (Flask minimal REST server)
# ------------------------------------------------------------------

@main.command("serve-api")
@click.option("--host", default="127.0.0.1", show_default=True,
              help="Bind host.")
@click.option("--port", default=8080, show_default=True, type=int,
              help="Bind port.")
@click.pass_context
def serve_api_cmd(ctx: click.Context, host: str, port: int) -> None:
    """Start the minimal Flask REST API server.

    Endpoints: GET /health, GET /skills, GET /stats, POST /chat
    Set AGENCY_API_TOKEN env var to require Bearer auth.
    """
    from .simple_server import run_server
    repo = ctx.obj.get("repo")
    run_server(host=host, port=port, repo=repo)


# ------------------------------------------------------------------
# agency webhook  — webhook management commands
# ------------------------------------------------------------------

@main.group("webhook")
def webhook_group() -> None:
    """Webhook notification management."""


@webhook_group.command("test")
@click.option("--url", default=None, help="Webhook URL (overrides config).")
@click.option("--secret", default=None, help="HMAC secret (overrides config).")
def webhook_test_cmd(url: str | None, secret: str | None) -> None:
    """Send a test ping to the configured (or supplied) webhook URL."""
    from .webhooks import WebhookConfig, WebhookDispatcher, load_webhook_config

    cfg = load_webhook_config()
    if url:
        cfg = WebhookConfig(url=url, secret=secret or (cfg.secret if cfg else ""), events=[])
    elif cfg is None:
        click.echo("No webhook URL configured. Set [webhooks] url in ~/.agency/config.toml "
                   "or pass --url.", err=True)
        raise SystemExit(1)

    dispatcher = WebhookDispatcher(cfg)
    click.echo(f"Sending test ping to {cfg.url} …")
    ok = dispatcher.dispatch_sync("ping", {"source": "agency webhook test"})
    if ok:
        click.echo("✅ Webhook delivered successfully.")
    else:
        click.echo("❌ Webhook delivery failed (check URL and connectivity).", err=True)
        raise SystemExit(1)


# ------------------------------------------------------------------
# agency update  — manual update check
# ------------------------------------------------------------------

@main.command("update")
def update_cmd() -> None:
    """Check PyPI for a newer agency version and show the changelog URL."""
    from .updater import check_update, CURRENT_VERSION, get_changelog_url

    click.echo(f"Current version : {CURRENT_VERSION}")
    click.echo("Checking PyPI …")
    newer = check_update(force=True)
    if newer:
        click.echo(f"⚠️  New version available: {newer}")
        click.echo(f"Run: pip install --upgrade agency")
    else:
        click.echo("✅ You are on the latest version.")
    click.echo(f"Changelog: {get_changelog_url()}")


# ------------------------------------------------------------------
# Improved agency doctor  (replaces the original)
# ------------------------------------------------------------------

def _ok(cond: bool, warn: bool = False) -> str:
    if cond:
        return "✅"
    return "⚠️ " if warn else "❌"


@main.command("doctor2")
@click.pass_context
def doctor2_cmd(ctx: click.Context) -> None:
    """Comprehensive diagnostic table: Python, API key, config, skills, history, stats, webhook."""
    import os
    import sys
    import pathlib

    from .config import AgencyConfig, config_path_toml

    rows: list[tuple[str, str, str]] = []  # (check, status, detail)

    # Python version
    vi = sys.version_info
    py_ok = vi >= (3, 10)
    rows.append((
        "Python version",
        _ok(py_ok),
        f"{vi.major}.{vi.minor}.{vi.micro} {'(≥3.10 ✓)' if py_ok else '(need ≥3.10)'}",
    ))

    # API key
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    key_ok = bool(key)
    rows.append(("API key", _ok(key_ok), f"set ({len(key)} chars)" if key_ok else "NOT SET"))

    # Config file
    cfg_path = config_path_toml()
    cfg_exists = cfg_path.exists()
    cfg_valid = False
    cfg_detail = "not found"
    if cfg_exists:
        try:
            AgencyConfig.load(cfg_path)
            cfg_valid = True
            cfg_detail = str(cfg_path)
        except Exception as exc:
            cfg_detail = f"parse error: {exc}"
    rows.append(("Config file", _ok(cfg_valid, warn=not cfg_exists), cfg_detail))

    # Skills dir
    try:
        root = ctx.obj.get("repo") or discover_repo_root()
        registry = SkillRegistry.load(root)
        n_skills = len(registry)
        rows.append(("Skills dir", _ok(True), f"{n_skills} skills in {root}"))
    except Exception as exc:
        rows.append(("Skills dir", _ok(False), str(exc)))

    # History dir
    hist_dir = pathlib.Path.home() / ".agency" / "history"
    hist_exists = hist_dir.exists()
    if hist_exists:
        sessions = list(hist_dir.glob("*.jsonl"))
        rows.append(("History dir", _ok(True), f"{len(sessions)} sessions in {hist_dir}"))
    else:
        rows.append(("History dir", _ok(False, warn=True), f"not found ({hist_dir})"))

    # Stats file
    stats_file = pathlib.Path.home() / ".agency" / "stats.json"
    rows.append((
        "Stats file",
        _ok(stats_file.exists(), warn=True),
        str(stats_file) if stats_file.exists() else "not found",
    ))

    # Webhook
    from .webhooks import load_webhook_config
    wh_cfg = load_webhook_config()
    rows.append((
        "Webhook",
        _ok(wh_cfg is not None, warn=True),
        f"url={wh_cfg.url}" if wh_cfg else "not configured (optional)",
    ))

    # Print table
    click.echo("\n=== Agency Doctor ===\n")
    col_w = max(len(r[0]) for r in rows) + 2
    for check, status, detail in rows:
        click.echo(f"  {check:<{col_w}}  {status}  {detail}")
    click.echo()


# ===========================================================================
# Pass 16 — structured logging, tracing, profiling, audit log
# ===========================================================================

# ---------------------------------------------------------------------------
# agency traces
# ---------------------------------------------------------------------------

@main.group("traces")
@click.pass_context
def traces_cmd(ctx: click.Context) -> None:
    """View request traces."""


@traces_cmd.command("list")
@click.option("--date", default=None, help="Date YYYY-MM-DD (default: today).")
@click.option("--limit", "-n", default=20, show_default=True, help="Max spans to show.")
def traces_list_cmd(date: str | None, limit: int) -> None:
    """List recent spans from the trace log."""
    from .tracing import load_spans, list_trace_dates

    if date is None:
        dates = list_trace_dates()
        if not dates:
            click.echo("No trace files found in ~/.agency/traces/")
            return
        date = dates[0]

    spans = load_spans(date=date, limit=limit)
    if not spans:
        click.echo(f"No spans found for {date}.")
        return

    click.echo(f"\n=== Traces — {date} (last {len(spans)}) ===\n")
    for sp in spans:
        dur = f"{sp.duration_ms:.1f}ms" if sp.duration_ms is not None else "open"
        err = f" ❌ {sp.error}" if sp.error else ""
        tags = " ".join(f"{k}={v}" for k, v in sp.tags.items())
        tag_part = f"  {tags}" if tags else ""
        click.echo(f"  {sp.name:<30}  {dur:>10}{tag_part}{err}")
    click.echo()


@traces_cmd.command("show")
@click.option("--date", default=None, help="Date YYYY-MM-DD (default: today).")
@click.option("--limit", "-n", default=50, show_default=True)
@click.option("--as-json", is_flag=True)
def traces_show_cmd(date: str | None, limit: int, as_json: bool) -> None:
    """Show span detail (optionally as JSON)."""
    from .tracing import load_spans, list_trace_dates
    import json as _json

    if date is None:
        dates = list_trace_dates()
        date = dates[0] if dates else None

    spans = load_spans(date=date, limit=limit)
    if as_json:
        click.echo(_json.dumps([s.to_dict() for s in spans], indent=2))
    else:
        for sp in spans:
            click.echo(_json.dumps(sp.to_dict(), indent=2))


# ---------------------------------------------------------------------------
# agency profile
# ---------------------------------------------------------------------------

@main.group("profile-perf")
@click.pass_context
def profile_perf_cmd(ctx: click.Context) -> None:
    """Performance profiling commands."""


@profile_perf_cmd.command("show")
@click.option("--top", "-n", default=10, show_default=True, help="Show N slowest ops.")
def profile_show_perf_cmd(top: int) -> None:
    """Show the slowest operations from this session."""
    from .profiler import top_slowest

    ops = top_slowest(top)
    if not ops:
        click.echo("No profiling data collected yet (run some commands first).")
        return
    click.echo(f"\n=== Slowest operations (top {top}) ===\n")
    click.echo(f"  {'Operation':<45}  {'Avg ms':>8}  {'Max ms':>8}  {'Count':>6}")
    click.echo("  " + "-" * 75)
    for s in ops:
        cnt = s.tags.get("count", 1)
        mx  = s.tags.get("max_ms", s.duration_ms)
        click.echo(f"  {s.operation:<45}  {s.duration_ms:>8.1f}  {mx:>8.1f}  {cnt:>6}")
    click.echo()


@profile_perf_cmd.command("flamegraph")
@click.option("--output", "-o", default=None, help="Output path (default: ~/.agency/profile.json).")
def profile_flamegraph_cmd(output: str | None) -> None:
    """Export a Speedscope-compatible flamegraph JSON."""
    from pathlib import Path as _P
    from .profiler import export_speedscope

    out = _P(output) if output else None
    path = export_speedscope(path=out)
    click.echo(f"Flamegraph written to: {path}")
    click.echo("Open at: https://speedscope.app  (drag & drop the file)")


# ---------------------------------------------------------------------------
# agency audit
# ---------------------------------------------------------------------------

@main.group("audit")
@click.pass_context
def audit_cmd(ctx: click.Context) -> None:
    """Audit log commands."""


@audit_cmd.command("show")
@click.option("--tail", "-n", default=20, show_default=True, help="Show last N entries.")
@click.option("--as-json", is_flag=True)
def audit_show_cmd(tail: int, as_json: bool) -> None:
    """Show recent audit log entries."""
    import json as _json
    from .audit import load_entries

    entries = load_entries(tail=tail)
    if not entries:
        click.echo("No audit log entries found (~/.agency/audit.jsonl).")
        return

    if as_json:
        click.echo(_json.dumps(entries, indent=2))
        return

    click.echo(f"\n=== Audit log (last {len(entries)}) ===\n")
    for e in entries:
        ts = e.get("timestamp", "?")[:19]
        ev = e.get("event", "?")
        pl = e.get("payload", {})
        summary = " ".join(f"{k}={v}" for k, v in pl.items())
        click.echo(f"  {ts}  {ev:<22}  {summary}")
    click.echo()


@audit_cmd.command("verify")
def audit_verify_cmd() -> None:
    """Verify chain integrity of the audit log."""
    from .audit import verify_integrity

    ok, errors = verify_integrity()
    if ok:
        click.echo("✅ Audit log integrity verified — chain hashes are consistent.")
    else:
        click.echo(f"❌ Audit log integrity check FAILED ({len(errors)} error(s)):")
        for err in errors:
            click.echo(f"   {err}")
        raise SystemExit(1)


@audit_cmd.command("path")
def audit_path_cmd() -> None:
    """Print path to the audit log file."""
    from .audit import audit_path
    click.echo(audit_path())


# ===========================================================================
# Pass 19 — Humanoid Robot Brain CLI
# ===========================================================================

@main.group("robotics")
def robotics_cmd() -> None:
    """JARVIS humanoid robot brain commands (Pass 19)."""


@robotics_cmd.command("start")
@click.option(
    "--sim",
    "sim_backend",
    default="mock",
    type=click.Choice(["mock", "pybullet", "mujoco"], case_sensitive=False),
    show_default=True,
    help="Simulation backend.",
)
@click.option(
    "--stt",
    "stt_backend",
    default="mock",
    type=click.Choice(["mock", "whisper", "google"], case_sensitive=False),
    show_default=True,
    help="Speech-to-text backend.",
)
@click.option("--vision/--no-vision", default=False, show_default=True,
              help="Enable camera-based object detection.")
def robotics_start_cmd(sim_backend: str, stt_backend: str, vision: bool) -> None:
    """Start the robot brain (initialise sim + vision)."""
    from .robotics.simulation import SimulationBackend
    from .robotics.stt import STTBackend
    from .robotics.robot_brain import RobotBrain

    sim = SimulationBackend(sim_backend)
    stt = STTBackend(stt_backend)
    brain = RobotBrain(sim_backend=sim, stt_backend=stt, use_vision=vision)
    brain.start()
    click.echo(f"✅ RobotBrain started — sim={sim_backend} stt={stt_backend} vision={vision}")
    st = brain.status()
    click.echo(f"   uptime={st['uptime_s']}s  joints={len(st['joint_states'])}")
    brain.stop()


@robotics_cmd.command("stop")
def robotics_stop_cmd() -> None:
    """Stop the robot brain (cleanup / disconnect simulation)."""
    click.echo("RobotBrain: sending stop signal (use Ctrl-C in listen mode).")


@robotics_cmd.command("status")
@click.option("--sim", "sim_backend", default="mock",
              type=click.Choice(["mock", "pybullet", "mujoco"], case_sensitive=False))
def robotics_status_cmd(sim_backend: str) -> None:
    """Print robot status (joint states, uptime, mode)."""
    from .robotics.simulation import SimulationBackend
    from .robotics.stt import STTBackend
    from .robotics.robot_brain import RobotBrain

    brain = RobotBrain(
        sim_backend=SimulationBackend(sim_backend),
        stt_backend=STTBackend.MOCK,
    )
    brain.start()
    st = brain.status()
    brain.stop()

    click.echo("=== RobotBrain Status ===")
    for k, v in st.items():
        if k != "joint_states":
            click.echo(f"  {k:20s}: {v}")
    click.echo(f"  {'joint_count':20s}: {len(st.get('joint_states', {}))}")


@robotics_cmd.command("exec")
@click.argument("command_text")
@click.option("--sim", "sim_backend", default="mock",
              type=click.Choice(["mock", "pybullet", "mujoco"], case_sensitive=False))
def robotics_exec_cmd(command_text: str, sim_backend: str) -> None:
    """Execute a natural-language motion command.

    Examples:\n
      agency robotics exec "walk forward 2 meters"\n
      agency robotics exec "turn left 45 degrees"\n
      agency robotics exec "wave right hand"
    """
    from .robotics.simulation import SimulationBackend
    from .robotics.stt import STTBackend
    from .robotics.robot_brain import RobotBrain

    brain = RobotBrain(
        sim_backend=SimulationBackend(sim_backend),
        stt_backend=STTBackend.MOCK,
    )
    brain.start()
    ok = brain.execute_text_command(command_text)
    brain.stop()
    if ok:
        click.echo(f"✅ Executed: {command_text!r}")
    else:
        click.echo(f"❌ Unrecognised or failed: {command_text!r}")
        raise SystemExit(1)


@robotics_cmd.command("listen")
@click.option("--sim", "sim_backend", default="mock",
              type=click.Choice(["mock", "pybullet", "mujoco"], case_sensitive=False))
@click.option("--stt", "stt_backend", default="mock",
              type=click.Choice(["mock", "whisper", "google"], case_sensitive=False))
@click.option("--steps", default=5, show_default=True,
              help="Number of listen cycles (mock) or run indefinitely (real STT).")
def robotics_listen_cmd(sim_backend: str, stt_backend: str, steps: int) -> None:
    """Enter voice-control mode (STT → parse → execute loop)."""
    from .robotics.simulation import SimulationBackend
    from .robotics.stt import STTBackend
    from .robotics.robot_brain import RobotBrain

    brain = RobotBrain(
        sim_backend=SimulationBackend(sim_backend),
        stt_backend=STTBackend(stt_backend),
    )
    brain.start()
    click.echo(f"🎙  Voice control mode — stt={stt_backend}  (Ctrl-C to stop)")
    try:
        count = 0
        while brain.running:
            text = brain.stt.listen(timeout=5.0)
            if text:
                click.echo(f"  Heard: {text!r}")
                brain.execute_text_command(text)
            count += 1
            if stt_backend == "mock" and count >= steps:
                break
    except KeyboardInterrupt:
        pass
    finally:
        brain.stop()
    click.echo("Voice control stopped.")


@robotics_cmd.command("train")
@click.option("--episodes", default=10, show_default=True, help="RL training episodes.")
@click.option("--sim", "sim_backend", default="mock",
              type=click.Choice(["mock", "pybullet", "mujoco"], case_sensitive=False))
@click.option("--save", "save_path", default=None, help="Path to save trained policy.")
def robotics_train_cmd(episodes: int, sim_backend: str, save_path: str | None) -> None:
    """Train a walking policy via Reinforcement Learning (requires torch)."""
    from .robotics.simulation import SimulationBridge, SimulationBackend
    from .robotics.rl_trainer import RLTrainer

    sim     = SimulationBridge(SimulationBackend(sim_backend))
    trainer = RLTrainer(sim=sim)
    click.echo(f"🏋  RL training: episodes={episodes} sim={sim_backend}")
    rewards = trainer.train_walking_policy(episodes=episodes, save_path=save_path)
    if rewards:
        click.echo(f"✅ Training complete. Mean reward (last 10): "
                   f"{sum(rewards[-10:]) / len(rewards[-10:]):.2f}")
    else:
        click.echo("⚠️  Training returned no rewards (torch may not be installed).")


# ===========================================================================
# Pass 22 — Face Recognition / Gesture / Telegram / TTS CLI commands
# ===========================================================================

@main.command("face")
@click.argument("image_path")
def face_cmd(image_path: str) -> None:
    """Identify a person in IMAGE_PATH using FaceRecognizer."""
    from .face_recognition import FaceRecognizer
    rec = FaceRecognizer()
    result = rec.identify_person(image_path)
    click.echo(f"זוהה: {result}")


@main.group("gesture")
def gesture_cmd() -> None:
    """Gesture recognition commands."""


@gesture_cmd.command("camera")
@click.option("--duration", "-d", default=0, help="Run for N seconds (0 = indefinite).")
def gesture_camera_cmd(duration: int) -> None:
    """Start live camera gesture recognition loop."""
    import time as _time
    from .robotics.gesture import GestureRecognizer

    rec = GestureRecognizer()
    click.echo(f"[Pass 22] מזהה מחוות (backend={rec.backend_name}) — Ctrl+C לעצירה")

    results = []

    def _cb(res):
        click.echo(f"  {res.gesture_name} ({res.confidence:.2f}) → skill: {res.skill_slug}")
        results.append(res)

    rec.start_camera_loop(_cb)
    try:
        if duration > 0:
            _time.sleep(duration)
        else:
            while True:
                _time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        rec.stop()
    click.echo("עצור.")


@main.group("telegram")
def telegram_cmd() -> None:
    """Telegram bot commands."""


@telegram_cmd.command("start")
@click.option("--token", envvar="TELEGRAM_BOT_TOKEN", default="", help="Bot token.")
def telegram_start_cmd(token: str) -> None:
    """Start the JARVIS Telegram bot."""
    from .telegram_bot import JarvisTelegramBot
    bot = JarvisTelegramBot(token=token or None)
    click.echo(f"[Pass 22] מפעיל Telegram bot (backend={bot.backend_name})…")
    try:
        bot.start()
    except KeyboardInterrupt:
        bot.stop()
    click.echo("Bot עצר.")


@main.command("tts")
@click.argument("text")
@click.option("--lang", "-l", default="he", show_default=True, help="Language code.")
def tts_cmd(text: str, lang: str) -> None:
    """Speak TEXT using the TTS engine."""
    from .tts_engine import TTSEngine
    engine = TTSEngine()
    click.echo(f"[Pass 22] מדבר (backend={engine.backend_name}): {text}")
    engine.speak(text, lang=lang)


# ===========================================================================
# Pass 23 — NLU, SecureConfig, NetworkMonitor CLI commands
# ===========================================================================

@main.command("nlu")
@click.argument("text")
def nlu_cmd(text: str) -> None:
    """Parse TEXT with NLUEngine and print JSON result."""
    import json
    from .nlu_engine import NLUEngine

    engine = NLUEngine()
    result = engine.parse(text)
    click.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


@main.group("secret")
def secret_cmd() -> None:
    """Manage JARVIS encrypted secrets (AES-256 via machine-ID key)."""


@secret_cmd.command("set")
@click.argument("key")
@click.argument("value")
def secret_set_cmd(key: str, value: str) -> None:
    """Store KEY=VALUE in the encrypted secrets store."""
    from .secure_config import SecureConfig
    cfg = SecureConfig()
    cfg.set_secret(key, value)
    click.echo(f"✓ מפתח '{key}' נשמר בהצלחה")


@secret_cmd.command("get")
@click.argument("key")
def secret_get_cmd(key: str) -> None:
    """Retrieve KEY from the encrypted secrets store."""
    from .secure_config import SecureConfig
    cfg = SecureConfig()
    val = cfg.get_secret(key)
    if val is None:
        click.echo(f"✗ מפתח '{key}' לא נמצא", err=True)
        raise SystemExit(1)
    click.echo(val)


@secret_cmd.command("list")
def secret_list_cmd() -> None:
    """List all stored secret keys (not values)."""
    from .secure_config import SecureConfig
    cfg = SecureConfig()
    keys = cfg.list_keys()
    if not keys:
        click.echo("אין מפתחות שמורים")
    else:
        for k in keys:
            click.echo(f"  • {k}")


@secret_cmd.command("delete")
@click.argument("key")
def secret_delete_cmd(key: str) -> None:
    """Delete KEY from the secrets store."""
    from .secure_config import SecureConfig
    cfg = SecureConfig()
    ok = cfg.delete_key(key)
    if ok:
        click.echo(f"✓ מפתח '{key}' נמחק")
    else:
        click.echo(f"✗ מפתח '{key}' לא נמצא", err=True)
        raise SystemExit(1)


@main.command("netcheck")
@click.option("--anthropic/--no-anthropic", "check_anthropic", default=True,
              help="Also measure latency to api.anthropic.com.")
def netcheck_cmd(check_anthropic: bool) -> None:
    """Check network connectivity and DNS status."""
    from .network_monitor import NetworkMonitor

    click.echo("בודק קישוריות...")
    mon = NetworkMonitor()
    result = mon.check_connectivity()

    status = "✓ מחובר" if result.online else "✗ לא מחובר"
    click.echo(f"  {status}")
    click.echo(f"  DNS:     {'✓' if result.dns_ok else '✗'}")
    click.echo(f"  השהייה:  {result.latency_ms:.1f} ms")
    click.echo(f"  ספק:     {result.isp}")

    if check_anthropic and result.online:
        lat = mon.get_latency_to_anthropic()
        label = f"{lat:.1f} ms" if lat > 0 else "לא נגיש"
        click.echo(f"  Anthropic API: {label}")


# ---------------------------------------------------------------------------
# Pass 24: gateway, task, hotreload commands
# ---------------------------------------------------------------------------

@main.command("gateway")
@click.argument("text")
def gateway_cmd(text: str) -> None:
    """Process TEXT through the APIGateway and print GatewayResponse as JSON."""
    import json
    from .api_gateway import APIGateway
    gw = APIGateway()
    resp = gw.process(text)
    click.echo(json.dumps(resp.to_dict(), ensure_ascii=False, indent=2))


@main.group("task")
def task_group() -> None:
    """Robot task management commands."""
    pass


@task_group.command("queue")
@click.argument("description")
@click.option("--priority", default=3, show_default=True, type=click.IntRange(1, 5))
def task_queue_cmd(description: str, priority: int) -> None:
    """Queue a robot task for execution."""
    from .robotics.task_executor import TaskExecutor, make_task
    executor = TaskExecutor()
    task = make_task(description, priority=priority)
    task_id = executor.queue_task(task)
    click.echo(f"✓ משימה בתור: {task_id}  (עדיפות {priority})")


@task_group.command("status")
def task_status_cmd() -> None:
    """Show current TaskExecutor status."""
    from .robotics.task_executor import TaskExecutor
    executor = TaskExecutor()
    status = executor.get_status()
    click.echo(f"סטטוס: {status.value}")


@main.group("hotreload")
def hotreload_group() -> None:
    """Hot-reload file watcher commands."""
    pass


@hotreload_group.command("start")
@click.option("--path", "paths", multiple=True, default=["runtime/agency"],
              show_default=True, help="Paths to watch (can repeat).")
def hotreload_start_cmd(paths: tuple) -> None:
    """Start watching paths for changes and reload modules automatically."""
    import time
    from .hot_reload import HotReloader

    def on_change(changed_path: str) -> None:
        click.echo(f"Reloaded: {changed_path}")

    reloader = HotReloader()
    reloader.watch(list(paths), on_change)
    click.echo(f"מאזין לשינויים ב: {', '.join(paths)}")
    click.echo("לחץ Ctrl+C לעצירה.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        reloader.stop()
        click.echo("\nHot-reload עצר.")
