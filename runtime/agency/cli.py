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


def _shared_context_manager():
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


def _shared_knowledge_expansion():
    global _KE_SINGLETON
    if _KE_SINGLETON is None:
        from .knowledge_expansion import KnowledgeExpansion
        _KE_SINGLETON = KnowledgeExpansion()
    return _KE_SINGLETON


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
