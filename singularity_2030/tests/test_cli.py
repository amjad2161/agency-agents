import json
import subprocess
import sys

from singularity_nexus.catalog import load_catalog


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "singularity_nexus", *args],
        check=True,
        text=True,
        capture_output=True,
    )


def test_cli_summary_outputs_machine_readable_contract():
    result = run_cli("summary", "--format", "json")
    payload = json.loads(result.stdout)

    assert payload["modules"] == 17
    assert payload["edges"] >= 10
    assert "agentic orchestration" in payload["common_denominator"]["themes"]


def test_cli_profile_outputs_ordered_modules():
    result = run_cli("profile", "full-stack-ai-ops", "--format", "json")
    payload = json.loads(result.stdout)

    assert payload["slug"] == "full-stack-ai-ops"
    assert payload["modules"][0] == "everything-claude-code"
    assert "superagi" in payload["modules"]


def test_cli_accepts_catalog_after_subcommand(tmp_path):
    catalog = load_catalog()
    path = tmp_path / "catalog.json"
    path.write_text(
        json.dumps(
            {
                "modules": [
                    {
                        **catalog.modules[0].__dict__,
                        "stack": list(catalog.modules[0].stack),
                        "capabilities": list(catalog.modules[0].capabilities),
                        "integration_modes": list(catalog.modules[0].integration_modes),
                        "run_profiles": list(catalog.modules[0].run_profiles),
                        "commands": list(catalog.modules[0].commands),
                        "risks": list(catalog.modules[0].risks),
                    }
                ],
                "integration_edges": [],
            }
        )
    )

    result = run_cli("summary", "--catalog", str(path), "--format", "json")
    payload = json.loads(result.stdout)

    assert payload["modules"] == 1


def test_cli_opportunities_filters_by_module():
    result = run_cli("opportunities", "--module", "autonomous-trading-engine", "--format", "json")
    payload = json.loads(result.stdout)
    slugs = {item["slug"] for item in payload["opportunities"]}

    assert {"hummingbot", "hftbacktest"}.issubset(slugs)


def test_cli_opportunities_top_is_applied_after_module_filter():
    result = run_cli("opportunities", "--module", "autonomous-trading-engine", "--top", "1", "--format", "json")
    payload = json.loads(result.stdout)

    assert [item["slug"] for item in payload["opportunities"]] == ["temporal"]


def test_cli_opportunities_accepts_external_catalog_after_subcommand(tmp_path):
    payload = {
        "source": "test",
        "searched_at": "2026-05-29T09:00:00Z",
        "opportunities": [
            {
                "slug": "test-opportunity",
                "name_with_owner": "owner/repo",
                "url": "https://github.com/owner/repo",
                "description": "Test opportunity",
                "stars": 1,
                "license_key": "mit",
                "license_name": "MIT License",
                "updated_at": "2026-05-29T09:00:00Z",
                "domain": "test",
                "strengthens_layers": ["agent-runtime"],
                "strengthens_capabilities": ["agent-orchestration"],
                "relevant_modules": ["mythos"],
                "adoption_mode": "pattern-adaptation",
                "recommendation": "Use only in tests.",
                "risks": ["None in test fixture"],
                "tags": ["test"],
                "priority_score": 1,
            }
        ],
    }
    path = tmp_path / "external.json"
    path.write_text(json.dumps(payload))

    result = run_cli("opportunities", "--catalog", str(path), "--format", "json")
    output = json.loads(result.stdout)

    assert output["opportunities"][0]["slug"] == "test-opportunity"
