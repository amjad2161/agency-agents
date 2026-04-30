"""CLI bindings for JARVIS One (`agency jarvis`, `agency map`,
`agency singularity`).

Kept in its own module so :mod:`agency.cli` only needs to import the
top-level groups. Stage 2 of the singularity plan: a single entry point.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from . import build_default_interface
from .. import __version__
from . import tui


def _interface(ctx: click.Context):
    if "jarvis_one" not in ctx.obj:
        ctx.obj["jarvis_one"] = build_default_interface(repo=ctx.obj.get("repo"))
    return ctx.obj["jarvis_one"]


# ----------------------------------------------------------------------
# `agency jarvis ...` subcommands
# ----------------------------------------------------------------------
@click.group("jarvis", invoke_without_command=True)
@click.pass_context
def jarvis_group(ctx: click.Context) -> None:
    """JARVIS One — unified GOD-MODE interface.

    Replaces the old ``supreme_main.py`` entry point. With no
    sub-command, prints a short status snapshot.
    """
    ctx.ensure_object(dict)
    if ctx.invoked_subcommand is None:
        jarvis = _interface(ctx)
        snap = jarvis.status()
        click.echo(tui.panel(
            f"version: {snap['version']}\n"
            f"skills:  {snap['skills']['count']} across "
            f"{len(snap['skills']['categories'])} categories\n"
            f"personas:{snap['personas']['count']} senior expert personas",
            title="J.A.R.V.I.S One — status",
        ))


@jarvis_group.command("ask")
@click.argument("message", nargs=-1, required=True)
@click.option("--persona", "persona_slug", default=None,
              help="Force a specific senior expert persona.")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
@click.pass_context
def jarvis_ask(ctx: click.Context, message: tuple[str, ...],
               persona_slug: str | None, as_json: bool) -> None:
    """Ask JARVIS One a single question."""
    jarvis = _interface(ctx)
    text = " ".join(message)
    ans = jarvis.ask(text, persona_slug=persona_slug)
    if as_json:
        click.echo(json.dumps(ans.to_dict(), ensure_ascii=False, indent=2))
        return
    click.echo(ans.response)


@jarvis_group.command("create")
@click.argument("request", nargs=-1, required=True)
@click.option("--want", multiple=True,
              type=click.Choice(["text", "diagram", "audio", "document"]),
              default=("text", "diagram", "document"))
@click.option("--out", "out_dir", type=click.Path(file_okay=False, path_type=Path),
              default=None, help="Write artefacts to this directory.")
@click.option("--format", "doc_format", default="markdown",
              type=click.Choice(["markdown", "html", "pdf", "docx", "pptx", "xlsx"]))
@click.pass_context
def jarvis_create(ctx: click.Context, request: tuple[str, ...],
                  want: tuple[str, ...], out_dir: Path | None,
                  doc_format: str) -> None:
    """Generate a multimodal artefact bundle for REQUEST."""
    jarvis = _interface(ctx)
    text = " ".join(request)
    bundle = jarvis.create(text, want=want, document_format=doc_format)
    if out_dir is None:
        for art in bundle.artifacts:
            click.echo(f"== {art.kind} ({art.mime}, {art.meta}) ==")
            click.echo(art.payload[:400] + ("…" if len(art.payload) > 400 else ""))
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    for art in bundle.artifacts:
        ext = {
            "text/plain": "txt", "image/svg+xml": "svg",
            "audio/wav": "wav", "text/markdown": "md",
            "text/html": "html", "application/pdf": "pdf",
        }.get(art.mime, "bin")
        path = out_dir / f"{art.kind}.{ext}"
        if art.meta.get("binary") or art.kind == "audio":
            import base64
            path.write_bytes(base64.b64decode(art.payload))
        else:
            path.write_text(art.payload, encoding="utf-8")
        click.echo(f"wrote {path}")


@jarvis_group.command("chat")
@click.option("--turns", default=0, type=int,
              help="Stop after N turns (0 = until EOF).")
@click.pass_context
def jarvis_chat(ctx: click.Context, turns: int) -> None:
    """Interactive chat REPL through JARVIS One."""
    jarvis = _interface(ctx)
    click.echo(tui.panel("Type your message and press enter. EOF (Ctrl-D) to exit.",
                          title="J.A.R.V.I.S One — chat"))
    n = 0
    try:
        while True:
            try:
                line = input("you> ").strip()
            except EOFError:
                break
            if not line:
                continue
            turn = jarvis.chat(line)
            click.echo(f"[{turn.persona} | {turn.sentiment}]")
            click.echo(turn.assistant)
            n += 1
            if turns and n >= turns:
                break
    except KeyboardInterrupt:
        pass


@jarvis_group.command("run")
@click.option("--mode", default="supreme_brainiac")
@click.option("--serve/--no-serve", default=False)
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8765, type=int)
@click.pass_context
def jarvis_run(ctx: click.Context, mode: str, serve: bool, host: str,
               port: int) -> None:
    """Boot the legacy supreme_main runtime (kept for backward-compat)."""
    from ..supreme_main import boot
    sys.exit(boot(mode=mode, start_server=serve, host=host, port=port))


@jarvis_group.command("status")
@click.pass_context
def jarvis_status(ctx: click.Context) -> None:
    """Print a JSON status snapshot."""
    click.echo(json.dumps(_interface(ctx).status(), ensure_ascii=False, indent=2))


@jarvis_group.command("personas")
@click.pass_context
def jarvis_personas(ctx: click.Context) -> None:
    """List the senior expert personas."""
    click.echo(tui.render_personas(_interface(ctx).personas()))


# ----------------------------------------------------------------------
# `agency map` — Stage 3 unified registry view
# ----------------------------------------------------------------------
@click.command("map")
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def map_cmd(ctx: click.Context, as_json: bool) -> None:
    """Show the unified agent registry: <categories> | <agents-per-category> | <total>."""
    jarvis = _interface(ctx)
    snap = jarvis.status()
    if as_json:
        click.echo(json.dumps({
            "categories": snap["skills"]["categories"],
            "by_category": snap["skills"]["by_category"],
            "total": snap["skills"]["count"],
            "personas": snap["personas"]["catalog"],
        }, ensure_ascii=False, indent=2))
        return
    click.echo(tui.render_categories(snap["skills"]["by_category"]))
    click.echo()
    click.echo(tui.render_personas(snap["personas"]["catalog"]))
    click.echo()
    click.echo(tui.style(
        f"JARVIS-core meta-router routes across {snap['skills']['count']} skills "
        f"in {len(snap['skills']['categories'])} categories.",
        fg="cyan", bold=True,
    ))


# ----------------------------------------------------------------------
# `agency singularity` — Stage 2 mega command
# ----------------------------------------------------------------------
@click.command("singularity")
@click.option("--check", is_flag=True,
              help="Verify the singularity boots without launching the server / chat.")
@click.option("--no-browser", is_flag=True,
              help="Don't open a browser tab.")
@click.option("--no-chat", is_flag=True,
              help="Don't drop into the chat REPL after boot.")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8765, type=int)
@click.pass_context
def singularity_cmd(ctx: click.Context, check: bool, no_browser: bool,
                    no_chat: bool, host: str, port: int) -> None:
    """Boot the entire JARVIS One singularity in a single command.

    1. Loads every skill via the unified registry.
    2. Prints a bilingual greeting + status banner.
    3. Optionally launches the dashboard server and opens a browser.
    4. Optionally drops into the chat REPL.

    Use ``--check`` for a hermetic boot test (CI-friendly).
    """
    jarvis = _interface(ctx)
    snap = jarvis.status()

    # 2. Bilingual greeting.
    banner = (
        f"שלום אמג'ד, JARVIS One מוכן לפעולה.\n"
        f"Hello Amjad, JARVIS One is ready.\n\n"
        f"Skills loaded:    {snap['skills']['count']}\n"
        f"Categories:       {len(snap['skills']['categories'])}\n"
        f"Senior personas:  {snap['personas']['count']}\n"
        f"Version:          {snap['version']}"
    )
    click.echo(tui.panel(banner, title="J.A.R.V.I.S  ONE  —  Singularity"))

    if check:
        # Just print and exit 0/1 based on whether anything loaded.
        if snap["skills"]["count"] == 0:
            raise click.ClickException("no skills loaded")
        click.echo(tui.style("singularity check: OK", fg="green", bold=True))
        return

    # 3. Launch dashboard server.
    try:
        import uvicorn
    except ImportError as exc:
        raise click.ClickException("uvicorn not installed.") from exc
    from ..server import build_app

    app = build_app(ctx.obj.get("repo"))
    url = f"http://{host}:{port}/dashboard"
    click.echo(tui.style(f"Dashboard: {url}", fg="cyan"))

    if not no_browser:
        import socket
        import threading
        import time
        import webbrowser

        def _open() -> None:
            for _ in range(40):
                time.sleep(0.25)
                try:
                    with socket.create_connection((host, port), timeout=0.5):
                        webbrowser.open(url)
                        return
                except OSError:
                    continue

        threading.Thread(target=_open, daemon=True).start()

    if no_chat:
        uvicorn.run(app, host=host, port=port, log_level="info")
        return

    # 4. Run server in a background thread, drop into chat REPL.
    import threading
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    try:
        ctx.invoke(jarvis_chat, turns=0)
    finally:
        server.should_exit = True
        t.join(timeout=2.0)
