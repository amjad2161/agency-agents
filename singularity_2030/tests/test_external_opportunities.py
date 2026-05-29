from singularity_nexus.catalog import load_catalog
from singularity_nexus.external import load_external_opportunities


def test_external_opportunities_are_license_aware_and_actionable():
    catalog = load_external_opportunities()

    assert len(catalog.opportunities) >= 20
    for opportunity in catalog.opportunities:
        assert opportunity.name_with_owner
        assert opportunity.url.startswith("https://github.com/")
        assert opportunity.license_key
        assert opportunity.adoption_mode in {
            "direct-integration",
            "adapter-integration",
            "pattern-adaptation",
            "research-only",
        }
        assert opportunity.strengthens_layers
        assert opportunity.relevant_modules
        assert opportunity.recommendation
        assert opportunity.risks


def test_top_candidates_prioritize_safe_high_value_projects():
    catalog = load_external_opportunities()
    top = catalog.top_candidates(limit=5)

    assert top[0].priority_score >= top[-1].priority_score
    assert any(item.slug == "langgraph" for item in top)
    assert all(item.adoption_mode != "research-only" for item in top[:3])


def test_opportunities_can_be_filtered_by_module_and_layer():
    catalog = load_external_opportunities()

    trading = catalog.for_module("autonomous-trading-engine")
    assert {"hummingbot", "hftbacktest"}.issubset({item.slug for item in trading})

    real_world = catalog.for_layer("domain-application")
    assert {"px4-autopilot", "mavsdk", "hummingbot"}.issubset({item.slug for item in real_world})


def test_external_layers_and_capabilities_match_local_catalog_vocabulary():
    local = load_catalog()
    local_layers = {module.layer for module in local.modules}
    local_capabilities = {capability for module in local.modules for capability in module.capabilities}
    external = load_external_opportunities()

    for opportunity in external.opportunities:
        assert set(opportunity.strengthens_layers).issubset(local_layers), opportunity.slug
        assert set(opportunity.strengthens_capabilities).issubset(local_capabilities), opportunity.slug
