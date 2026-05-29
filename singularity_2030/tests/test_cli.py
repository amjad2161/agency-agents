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
