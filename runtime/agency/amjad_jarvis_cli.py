"""
Amjad Jarvis CLI Integration

Adds these commands:
  agency amjad profile show     - Display Amjad's profile
  agency amjad profile set      - Update profile
  agency amjad profile edit     - Edit in $EDITOR
  agency amjad trust <mode>     - Set trust mode (off/on-my-machine/yolo)
  agency amjad shell <on|off>   - Control shell access
  agency amjad run <REQUEST>    - Execute with full context
  agency amjad workflow <name>  - Run multi-agent workflows
  agency amjad status           - Show system status
"""

from __future__ import annotations

import click
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .amjad_jarvis_meta_orchestrator import (
    jarvis,
    AmjadProfile,
)
from .logging import get_logger


@click.group()
def amjad_group():
    """Amjad Jarvis Meta-Orchestrator commands."""
    pass


@amjad_group.group()
def profile():
    """Manage Amjad's profile and preferences."""
    pass


@profile.command("show")
def profile_show():
    """Display Amjad's complete profile."""
    j = jarvis()
    click.echo("\n" + "=" * 70)
    click.echo("🧠 AMJAD JARVIS PROFILE")
    click.echo("=" * 70)
    click.echo(j.amjad.to_system_prompt_prefix())
    click.echo("\n" + "=" * 70)
    click.echo("⚙️  PREFERENCES")
    click.echo("=" * 70)
    click.echo(json.dumps(j.amjad.preferences, indent=2))
    click.echo("\n" + "=" * 70)
    click.echo("🔒 CONSTRAINTS")
    click.echo("=" * 70)
    click.echo(json.dumps(j.amjad.constraints, indent=2))
    click.echo("=" * 70 + "\n")


@profile.command("edit")
@click.option("--editor", default=None, help="Editor to use (default: $EDITOR)")
def profile_edit(editor: str | None):
    """Edit Amjad's profile in your default editor."""
    j = jarvis()
    profile_path = Path.home() / ".agency" / "amjad-profile.json"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({
            "name": j.amjad.name,
            "role": j.amjad.role,
            "personality_traits": j.amjad.personality_traits,
            "technical_stack": j.amjad.technical_stack,
            "work_values": j.amjad.work_values,
            "known_projects": j.amjad.known_projects,
            "known_skills": j.amjad.known_skills,
            "known_teams": j.amjad.known_teams,
            "constraints": j.amjad.constraints,
            "preferences": j.amjad.preferences,
        }, f, indent=2)
        temp_path = f.name

    try:
        editor_cmd = editor or os.environ.get("EDITOR", "vim")
        subprocess.run([editor_cmd, temp_path], check=False)

        if Path(temp_path).exists():
            updated = json.loads(Path(temp_path).read_text())
            j.amjad = AmjadProfile(**updated)
            j.amjad.save(profile_path)
            click.echo(f"✓ Profile saved to {profile_path}")
    finally:
        Path(temp_path).unlink(missing_ok=True)


@profile.command("set")
@click.argument("key")
@click.argument("value")
def profile_set(key: str, value: str):
    """Set a profile preference."""
    j = jarvis()

    try:
        parsed_value = json.loads(value)
    except json.JSONDecodeError:
        parsed_value = value

    if key in j.amjad.preferences:
        j.amjad.preferences[key] = parsed_value
        j.amjad.save()
        click.echo(f"✓ {key} = {parsed_value}")
    elif key in j.amjad.constraints:
        j.amjad.constraints[key] = parsed_value
        j.amjad.save()
        click.echo(f"✓ {key} = {parsed_value}")
    else:
        click.echo(f"✗ Unknown profile key: {key}")


@amjad_group.command("trust")
@click.argument("mode", type=click.Choice(["off", "on-my-machine", "yolo"]))
def set_trust_mode(mode: str):
    """Set the trust mode."""
    j = jarvis()
    j.set_trust_mode(mode)
    click.echo(f"\n✓ Trust mode: {mode}")
    if mode == "off":
        click.echo("  • Shell access: disabled (sandboxed)")
        click.echo("  • File access: restricted to workdir")
        click.echo("  • Web fetch: blocked on private IPs")
    elif mode == "on-my-machine":
        click.echo("  • Shell access: enabled (denylist active)")
        click.echo("  • File access: full filesystem access")
        click.echo("  • Web fetch: unrestricted")
    else:  # yolo
        click.echo("  • Shell access: enabled (no guards)")
        click.echo("  • File access: unrestricted")
        click.echo("  • Web fetch: unrestricted")
    click.echo()


@amjad_group.command("shell")
@click.argument("action", type=click.Choice(["on", "off", "status"]))
def control_shell(action: str):
    """Control shell access."""
    j = jarvis()
    if action == "on":
        j.enable_shell(True)
        click.echo("✓ Shell access enabled")
    elif action == "off":
        j.enable_shell(False)
        click.echo("✓ Shell access disabled")
    else:
        status = "enabled" if j.amjad.preferences.get("shell_access") else "disabled"
        click.echo(f"Shell: {status}")


@amjad_group.command("web-search")
@click.argument("action", type=click.Choice(["on", "off", "status"]))
def control_web_search(action: str):
    """Control web search."""
    j = jarvis()
    if action == "on":
        j.enable_web_search(True)
        click.echo("✓ Web search enabled")
    elif action == "off":
        j.enable_web_search(False)
        click.echo("✓ Web search disabled")
    else:
        status = "enabled" if j.amjad.preferences.get("web_search") else "disabled"
        click.echo(f"Web search: {status}")


@amjad_group.command("code-exec")
@click.argument("action", type=click.Choice(["on", "off", "status"]))
def control_code_exec(action: str):
    """Control code execution."""
    j = jarvis()
    if action == "on":
        j.enable_code_execution(True)
        click.echo("✓ Code execution enabled")
    elif action == "off":
        j.enable_code_execution(False)
        click.echo("✓ Code execution disabled")
    else:
        status = "enabled" if j.amjad.preferences.get("code_execution") else "disabled"
        click.echo(f"Code execution: {status}")


@amjad_group.command("computer-use")
@click.argument("action", type=click.Choice(["on", "off", "status"]))
def control_computer_use(action: str):
    """Control computer use."""
    j = jarvis()
    if action == "on":
        j.enable_computer_use(True)
        click.echo("✓ Computer use enabled")
    elif action == "off":
        j.enable_computer_use(False)
        click.echo("✓ Computer use disabled")
    else:
        status = "enabled" if j.amjad.preferences.get("computer_use") else "disabled"
        click.echo(f"Computer use: {status}")


@amjad_group.command("run")
@click.argument("request", nargs=-1, required=True)
@click.option("--agent", "-a", default=None, help="Explicit agent slug (auto-select if omitted)")
@click.option("--session", "-s", default=None, help="Session ID for memory persistence")
@click.option("--workflow", "-w", default=None, help="Workflow name for multi-agent coordination")
def run_request(request: tuple[str, ...], agent: str | None, session: str | None, workflow: str | None):
    """Execute a request with Amjad's full context."""
    j = jarvis()
    request_text = " ".join(request)

    click.echo(f"\n🧠 Executing: {request_text}\n")

    if workflow:
        results = j.execute_multi_agent_workflow(
            workflow_name=workflow,
            primary_request=request_text,
            parallel=True,
        )
        click.echo("Agents executed:")
        for agent_slug, result in results.items():
            preview = result.text[:150].replace("\n", " ") + "..." if len(result.text) > 150 else result.text
            click.echo(f"\n  {agent_slug}:")
            click.echo(f"    {preview}")
    else:
        result = j.execute_unified_request(
            request_text,
            primary_agent_slug=agent,
            session_id=session,
        )
        click.echo(result.text)
        click.echo(f"\n[{result.turns} turns | {result.usage.input_tokens}→{result.usage.output_tokens} tokens]")


@amjad_group.command("status")
def show_status():
    """Show current system status."""
    j = jarvis()
    click.echo("\n" + "=" * 70)
    click.echo("🧠 AMJAD JARVIS STATUS")
    click.echo("=" * 70)
    click.echo(f"Profile: {j.amjad.name} ({j.amjad.role})")
    click.echo(f"Agents loaded: {len(list(j.registry.all()))}")
    click.echo(f"Trust mode: {j.amjad.preferences.get('trust_mode', 'on-my-machine')}")
    click.echo(f"Shell: {'✓ enabled' if j.amjad.preferences.get('shell_access') else '✗ disabled'}")
    click.echo(f"Web search: {'✓ enabled' if j.amjad.preferences.get('web_search') else '✗ disabled'}")
    click.echo(f"Code execution: {'✓ enabled' if j.amjad.preferences.get('code_execution') else '✗ disabled'}")
    click.echo(f"Computer use: {'✓ enabled' if j.amjad.preferences.get('computer_use') else '✗ disabled'}")
    click.echo("=" * 70 + "\n")


__all__ = ["amjad_group"]
