from __future__ import annotations

import argparse
import json
from typing import Any

from .catalog import load_catalog
from .external import load_external_opportunities
from .orchestrator import PROFILES, SingularityOrchestrator


def _emit(payload: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    for key, value in payload.items():
        if isinstance(value, (list, tuple)):
            print(f"{key}:")
            for item in value:
                print(f"  - {item}")
        elif isinstance(value, dict):
            print(f"{key}: {json.dumps(value, sort_keys=True)}")
        else:
            print(f"{key}: {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="singularity-nexus",
        description="Inspect and compose the Singularity 2030 repository control plane.",
    )
    parser.add_argument("--catalog", help="Optional path to a catalog JSON file")

    subparsers = parser.add_subparsers(dest="command", required=True)

    summary = subparsers.add_parser("summary", help="Print system-wide summary")
    summary.add_argument("--catalog", help="Optional path to a catalog JSON file")
    summary.add_argument("--format", choices=("text", "json"), default="text")

    modules = subparsers.add_parser("modules", help="List catalog modules")
    modules.add_argument("--catalog", help="Optional path to a catalog JSON file")
    modules.add_argument("--capability", help="Filter by capability slug")
    modules.add_argument("--format", choices=("text", "json"), default="text")

    capabilities = subparsers.add_parser("capabilities", help="Group modules by capability")
    capabilities.add_argument("--catalog", help="Optional path to a catalog JSON file")
    capabilities.add_argument("--format", choices=("text", "json"), default="text")

    profile = subparsers.add_parser("profile", help="Print an execution profile")
    profile.add_argument("--catalog", help="Optional path to a catalog JSON file")
    profile.add_argument("slug", choices=sorted(PROFILES))
    profile.add_argument("--format", choices=("text", "json"), default="text")

    opportunities = subparsers.add_parser("opportunities", help="List GitHub enhancement opportunities")
    opportunities.add_argument("--catalog", help="Optional path to an external opportunities JSON file")
    opportunities.add_argument("--module", help="Filter by local module slug")
    opportunities.add_argument("--layer", help="Filter by strengthened local layer")
    opportunities.add_argument("--top", type=int, help="Return the top N usable opportunities")
    opportunities.add_argument("--format", choices=("text", "json"), default="text")

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.command == "opportunities":
        external = load_external_opportunities(args.catalog)
        selected = external.opportunities
        if args.module:
            selected = tuple(item for item in selected if args.module in item.relevant_modules)
        if args.layer:
            selected = tuple(item for item in selected if args.layer in item.strengthens_layers)
        if args.top is not None:
            usable = [item for item in selected if item.adoption_mode != "research-only"]
            selected = tuple(sorted(usable, key=lambda item: (-item.priority_score, -item.stars, item.slug))[: args.top])

        payload = {
            "source": external.source,
            "searched_at": external.searched_at,
            "opportunities": [item.to_dict() for item in selected],
        }
        _emit(payload, args.format)
        return

    catalog = load_catalog(args.catalog)
    orchestrator = SingularityOrchestrator(catalog)

    if args.command == "summary":
        _emit(orchestrator.summary(), args.format)
        return

    if args.command == "modules":
        selected = catalog.modules
        if args.capability:
            selected = tuple(module for module in selected if args.capability in module.capabilities)
        payload = {
            "modules": [
                {
                    "slug": module.slug,
                    "name": module.name,
                    "layer": module.layer,
                    "maturity": module.maturity,
                    "capabilities": list(module.capabilities),
                }
                for module in selected
            ]
        }
        _emit(payload, args.format)
        return

    if args.command == "capabilities":
        _emit(orchestrator.capability_map(), args.format)
        return

    if args.command == "profile":
        _emit(orchestrator.profile(args.slug).to_dict(), args.format)
        return

    raise SystemExit(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    main()
