import json
from pathlib import Path

import pytest

from singularity_nexus.catalog import load_catalog


def test_catalog_contains_every_attached_repository():
    catalog = load_catalog()

    expected = {
        "agency-agents",
        "amjad2161",
        "anthropic-quickstarts",
        "anthropic-sdk-typescript",
        "auto-save-sync",
        "autonomous-trading-engine",
        "claude-code",
        "claude-code-abc",
        "comfyui",
        "cors-anywhere",
        "dji-owner",
        "everything-claude-code",
        "mythos",
        "skills",
        "superagi",
        "system-prompts-and-models-of-ai-tools",
        "tradingboy",
    }

    assert {module.slug for module in catalog.modules} == expected


def test_catalog_modules_are_actionable():
    catalog = load_catalog()

    for module in catalog.modules:
        assert module.name
        assert module.vision
        assert module.layer
        assert module.capabilities, module.slug
        assert module.integration_modes, module.slug
        assert module.run_profiles, module.slug


def test_catalog_repo_paths_resolve_from_project_root():
    catalog = load_catalog()
    project_root = Path(__file__).resolve().parents[1]

    for module in catalog.modules:
        assert (project_root / module.repo_path).resolve().exists(), module.slug


def test_catalog_relationships_reference_known_modules():
    catalog = load_catalog()
    known = {module.slug for module in catalog.modules}

    for edge in catalog.integration_edges:
        assert edge.source in known
        assert edge.target in known
        assert edge.mode
        assert edge.contract


def test_catalog_rejects_unknown_run_profiles(tmp_path):
    catalog = load_catalog()
    payload = {
        "modules": [
            {
                **catalog.modules[0].__dict__,
                "stack": list(catalog.modules[0].stack),
                "capabilities": list(catalog.modules[0].capabilities),
                "integration_modes": list(catalog.modules[0].integration_modes),
                "run_profiles": ["missing-profile"],
                "commands": list(catalog.modules[0].commands),
                "risks": list(catalog.modules[0].risks),
            }
        ],
        "integration_edges": [],
    }
    path = tmp_path / "bad-profile.json"
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="unknown run profiles"):
        load_catalog(path)


def test_catalog_rejects_string_fields_that_should_be_lists(tmp_path):
    catalog = load_catalog()
    module = {
        **catalog.modules[0].__dict__,
        "stack": list(catalog.modules[0].stack),
        "capabilities": "agent-orchestration",
        "integration_modes": list(catalog.modules[0].integration_modes),
        "run_profiles": list(catalog.modules[0].run_profiles),
        "commands": list(catalog.modules[0].commands),
        "risks": list(catalog.modules[0].risks),
    }
    path = tmp_path / "bad-field.json"
    path.write_text(json.dumps({"modules": [module], "integration_edges": []}))

    with pytest.raises(TypeError, match="must be a list of strings"):
        load_catalog(path)
