from __future__ import annotations

import argparse
import json
from typing import Any

from .catalog import load_catalog
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

    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
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
