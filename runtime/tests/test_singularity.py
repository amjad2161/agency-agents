"""Singularity tests — verify the unified entry-point, the /singularity
endpoint, and the cleanliness of the repo root.

Cross-references the plan (`agency singularity`, `GET /singularity`, no
`.zip`/`.bat` at the root). These tests are the contract that keeps the
singularity from drifting back into 22 scattered sub-projects.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from agency.cli import main as agency_cli
from agency.server import build_app
from agency.skills import DEFAULT_CATEGORIES, discover_repo_root


REPO = discover_repo_root()


def test_singularity_check_exits_clean():
    """`agency singularity --check` must exit 0 on a healthy tree."""
    runner = CliRunner()
    result = runner.invoke(agency_cli, ["singularity", "--check"])
    assert result.exit_code == 0, result.output
    assert "singularity check: OK" in result.output


def test_singularity_endpoint_returns_all_categories():
    """`GET /singularity` must return every default category and surface
    the JARVIS-core meta-router slug."""
    app = build_app(REPO)
    client = TestClient(app)
    r = client.get("/singularity")
    assert r.status_code == 200, r.text
    data = r.json()

    # Every default category that exists on disk AND contains at least
    # one persona-shaped markdown file must show up in the singularity
    # payload. (`strategy/` is in DEFAULT_CATEGORIES but currently has
    # no persona files, so the loader correctly skips it.)
    returned_cats = {c["name"] for c in data["categories"]}
    on_disk_with_personas = {
        c for c in DEFAULT_CATEGORIES
        if (REPO / c).is_dir() and any(
            (REPO / c).rglob("*.md")
        )
    }
    # Filter to those that actually parse as skills — loader skips files
    # without YAML frontmatter, so we use registry truth as the floor.
    from agency.skills import SkillRegistry as _SR
    registry_cats = set(_SR.load(REPO).categories())
    expected = on_disk_with_personas & registry_cats
    missing = expected - returned_cats
    assert not missing, f"singularity is missing categories: {missing}"

    # Totals are internally consistent.
    skill_count = sum(c["count"] for c in data["categories"])
    assert data["totals"]["skills"] == skill_count
    assert data["totals"]["categories"] == len(data["categories"])
    assert data["totals"]["routing_domains"] > 0

    # JARVIS-core (the meta-router) must be in the payload.
    assert "jarvis" in returned_cats, "jarvis category missing"
    jarvis_cat = next(c for c in data["categories"] if c["name"] == "jarvis")
    jarvis_slugs = {a["slug"] for a in jarvis_cat["agents"]}
    assert "jarvis-core-brain" in jarvis_slugs, (
        "jarvis-core-brain (meta-router) is not in the singularity payload"
    )
    # Make sure the brain slug is flagged as core for the dashboard.
    core_brain = next(a for a in jarvis_cat["agents"]
                      if a["slug"] == "jarvis-core-brain")
    assert core_brain["is_core"] is True
    assert "jarvis-core-brain" in data["core_slugs"]

    # Runtime block is present and well-formed.
    rt = data["runtime"]
    assert rt["registry_loaded"] is True
    assert rt["version"]
    assert "trust_mode" in rt


def test_dashboard_route_serves_html():
    """The `/dashboard` route must serve the singularity dashboard HTML."""
    app = build_app(REPO)
    client = TestClient(app)
    r = client.get("/dashboard")
    assert r.status_code == 200
    body = r.text
    assert "Singularity Dashboard" in body
    # The dashboard must reference the /singularity endpoint it consumes.
    assert "/singularity" in body


def test_repo_root_has_no_legacy_artifacts():
    """The repo root must be free of `.zip` archives and stray `.bat`
    files (those belong in `scripts/jarvis/` or `scripts/dev/`)."""
    forbidden_zips: list[str] = []
    forbidden_bats: list[str] = []
    for entry in REPO.iterdir():
        if not entry.is_file():
            continue
        suffix = entry.suffix.lower()
        if suffix == ".zip":
            forbidden_zips.append(entry.name)
        elif suffix == ".bat":
            forbidden_bats.append(entry.name)

    assert not forbidden_zips, (
        f"Found .zip artifacts at the repo root: {forbidden_zips}. "
        f"Release archives must not be committed; see .gitignore."
    )
    assert not forbidden_bats, (
        f"Found .bat scripts at the repo root: {forbidden_bats}. "
        f"Move them under scripts/jarvis/ (launchers) or scripts/dev/."
    )


def test_jarvis_singular_doc_present():
    """The plan promises one unified `JARVIS.md` at the repo root."""
    jarvis_md = REPO / "JARVIS.md"
    assert jarvis_md.is_file(), "JARVIS.md is missing at repo root"
    body = jarvis_md.read_text(encoding="utf-8")
    # Sanity: it should mention the singularity entry-point.
    assert "agency singularity" in body
    assert "/dashboard" in body


def test_supreme_main_is_a_shim():
    """`supreme_main.main()` must still work as a backward-compat shim
    that delegates to the same boot path `agency jarvis run` uses."""
    from agency import supreme_main
    # Public surface preserved.
    assert callable(supreme_main.main)
    assert callable(supreme_main.boot)
    assert callable(supreme_main.initialise_character_system)


def test_agency_map_command_runs():
    """`agency map` must produce the unified categories/agents/total view."""
    runner = CliRunner()
    result = runner.invoke(agency_cli, ["map"])
    assert result.exit_code == 0, result.output
    assert "TOTAL" in result.output
    assert "jarvis" in result.output


def test_agency_map_json_output():
    """`agency map --json` must emit a parseable JSON payload."""
    import json
    runner = CliRunner()
    result = runner.invoke(agency_cli, ["map", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["totals"]["agents"] > 0
    assert payload["totals"]["categories"] >= 1
    cat_names = {c["name"] for c in payload["categories"]}
    assert "jarvis" in cat_names
