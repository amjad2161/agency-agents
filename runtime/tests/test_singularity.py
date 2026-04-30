"""Singularity tests — verify Stage 1-6 deliverables of JARVIS One.

These tests are the gate that ``agency singularity --check`` is wired up,
the ``/singularity`` endpoint returns every category, and the repository
root stays free of the artifacts the cleanup plan removed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from agency.cli import main as agency_cli
from agency.server import build_app


REPO = Path(__file__).resolve().parents[2]


# ----------------------------------------------------------------------
# Stage 1 — clean repo root
# ----------------------------------------------------------------------
def test_no_zip_archives_at_repo_root() -> None:
    leftovers = sorted(p.name for p in REPO.iterdir() if p.suffix.lower() == ".zip")
    assert leftovers == [], f"unexpected .zip archives at root: {leftovers}"


def test_no_jarvis_push_scripts_at_repo_root() -> None:
    forbidden = {"JARVIS_COMMIT_PUSH.bat", "JARVIS_FINAL_PUSH.bat",
                 "JARVIS_GIT_PUSH.ps1", "JARVIS_PUSH.bat",
                 "JARVIS_PUSH_P3.ps1", "JARVIS_SETUP.bat",
                 "JARVIS_START.bat", "JARVIS_DASHBOARD_PREVIEW.html"}
    found = {p.name for p in REPO.iterdir()} & forbidden
    assert found == set(), f"forbidden setup/push scripts present: {sorted(found)}"


def test_dashboard_html_lives_under_runtime_static() -> None:
    assert (REPO / "runtime" / "agency" / "static" / "dashboard.html").is_file()


# ----------------------------------------------------------------------
# Stage 5 — single master document
# ----------------------------------------------------------------------
def test_jarvis_md_exists_at_root() -> None:
    p = REPO / "JARVIS.md"
    assert p.is_file()
    body = p.read_text(encoding="utf-8")
    for needle in ("agency singularity", "GOD-MODE", "/dashboard",
                   "JARVISInterface"):
        assert needle in body, f"JARVIS.md missing reference to {needle!r}"


def test_readme_points_to_jarvis_md() -> None:
    body = (REPO / "README.md").read_text(encoding="utf-8")
    assert "JARVIS.md" in body


def test_old_status_capabilities_archived() -> None:
    # The stage-5 plan says: not deleted, just moved out of the root.
    archive = REPO / "docs" / "archive"
    assert (archive / "JARVIS_STATUS.md").is_file()
    assert (archive / "JARVIS_CAPABILITIES.md").is_file()
    assert not (REPO / "JARVIS_STATUS.md").exists()
    assert not (REPO / "JARVIS_CAPABILITIES.md").exists()


# ----------------------------------------------------------------------
# Stage 2 — single CLI entry point
# ----------------------------------------------------------------------
def test_agency_singularity_check_exits_zero() -> None:
    runner = CliRunner()
    result = runner.invoke(agency_cli, ["singularity", "--check"])
    assert result.exit_code == 0, result.output
    assert "singularity check" in result.output.lower() or "skills" in result.output.lower()


def test_agency_jarvis_subgroup_registered() -> None:
    runner = CliRunner()
    result = runner.invoke(agency_cli, ["jarvis", "--help"])
    assert result.exit_code == 0
    for cmd in ("ask", "create", "chat", "run", "status", "personas"):
        assert cmd in result.output


def test_agency_map_lists_categories_and_total() -> None:
    runner = CliRunner()
    result = runner.invoke(agency_cli, ["map", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    # Production shape: {categories: [...], totals: {...}, jarvis_core: [...]}
    assert "categories" in data and "totals" in data
    assert data["totals"]["agents"] > 0
    cat_names = [c["name"] for c in data["categories"]]
    assert len(cat_names) >= 10
    assert "jarvis" in cat_names


def test_supreme_main_still_imports_and_boots() -> None:
    """Backward compatibility — the legacy entry point must still work."""
    from agency import supreme_main
    assert callable(supreme_main.boot)


# ----------------------------------------------------------------------
# Stage 3 + 4 — registry endpoint + dashboard
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(build_app())


def test_singularity_endpoint_exposes_all_categories(client: TestClient) -> None:
    r = client.get("/singularity")
    assert r.status_code == 200
    data = r.json()
    # Production shape: totals, runtime, categories, routing_table, core_slugs, lessons
    assert {"totals", "runtime", "categories", "routing_table",
            "core_slugs"}.issubset(data)
    assert data["totals"]["skills"] > 0
    assert data["totals"]["categories"] >= 10
    cat_names = {c["name"] for c in data["categories"]}
    assert "jarvis" in cat_names
    # JARVIS-core meta-router is flagged.
    assert data["totals"]["jarvis_specialists"] > 0


def test_dashboard_endpoint_serves_html(client: TestClient) -> None:
    r = client.get("/dashboard")
    assert r.status_code == 200
    body = r.text
    # Dashboard pulls the singularity snapshot and renders the agent grid.
    assert "/singularity" in body
    assert "JARVIS" in body


def test_jarvis_ask_endpoint(client: TestClient) -> None:
    r = client.post("/api/jarvis/ask", json={"message": "hello jarvis"})
    assert r.status_code == 200
    data = r.json()
    assert "response" in data and data["response"]
    assert "persona" in data
    assert "decision" in data


def test_jarvis_create_endpoint_returns_artifacts(client: TestClient) -> None:
    r = client.post("/api/jarvis/create",
                    json={"request": "design overview", "want": ["text", "diagram"]})
    assert r.status_code == 200
    data = r.json()
    kinds = sorted(a["kind"] for a in data["artifacts"])
    assert kinds == ["diagram", "text"]
