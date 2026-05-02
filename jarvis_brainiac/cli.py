"""
JARVIS BRAINIAC CLI — single entry point.

Usage:
    python -m jarvis_brainiac health
    python -m jarvis_brainiac route "build me a startup MVP"
    python -m jarvis_brainiac plan  "review this repo for security"
    python -m jarvis_brainiac sync pull
    python -m jarvis_brainiac sync push -m "wip"
    python -m jarvis_brainiac memory remember semantic "user prefers OMEGA_NEXUS"
    python -m jarvis_brainiac memory recall "OMEGA"
    python -m jarvis_brainiac stats
    python -m jarvis_brainiac agents  --division engineering
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import AgentRegistry, Orchestrator, CloudSync, UnifiedMemory
from .cloud_sync import GitHubBackend


def _root() -> Path:
    # Heuristic: the dir containing this package
    return Path(__file__).resolve().parent.parent


def cmd_health(args) -> int:
    orch = Orchestrator(_root())
    print(json.dumps(orch.health(), indent=2, ensure_ascii=False))
    return 0


def cmd_route(args) -> int:
    orch = Orchestrator(_root())
    decision = orch.route(args.request)
    print(json.dumps(decision.to_dict(), indent=2, ensure_ascii=False))
    return 0


def cmd_plan(args) -> int:
    orch = Orchestrator(_root())
    print(json.dumps(orch.plan(args.request), indent=2, ensure_ascii=False))
    return 0


def cmd_sync(args) -> int:
    backend = None
    if args.repo:
        backend = GitHubBackend(args.repo, args.branch)
    sync = CloudSync(_root(), backend=backend)
    if args.action == "pull":
        print(json.dumps(sync.pull(), indent=2))
    elif args.action == "push":
        print(json.dumps(sync.push(args.message), indent=2))
    elif args.action == "status":
        print(json.dumps(sync.status(), indent=2))
    elif args.action == "drain":
        print(json.dumps(sync.drain_queue(), indent=2))
    else:
        print("unknown sync action", file=sys.stderr)
        return 2
    return 0


def cmd_memory(args) -> int:
    mem = UnifiedMemory(_root())
    if args.action == "remember":
        e = mem.remember(args.kind, args.content, tags=args.tags or [])
        print(json.dumps(e.to_dict(), indent=2, ensure_ascii=False))
    elif args.action == "recall":
        entries = mem.recall(args.query, kind=args.kind, limit=args.limit)
        print(json.dumps([e.to_dict() for e in entries],
                         indent=2, ensure_ascii=False))
    elif args.action == "stats":
        print(json.dumps(mem.stats(), indent=2))
    return 0


def cmd_stats(args) -> int:
    reg = AgentRegistry(_root()); reg.discover()
    mem = UnifiedMemory(_root())
    out = {
        "registry": reg.stats(),
        "memory": mem.stats(),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_agents(args) -> int:
    reg = AgentRegistry(_root()); reg.discover()
    if args.division:
        agents = list(reg.by_division(args.division))
    elif args.search:
        agents = reg.find(args.search, top_k=args.limit)
    else:
        agents = list(reg.agents.values())[: args.limit]
    out = [
        {"name": a.name, "division": a.division, "path": a.path,
         "description": a.description[:140]}
        for a in agents
    ]
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser("jarvis-brainiac")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health").set_defaults(fn=cmd_health)

    pr = sub.add_parser("route");  pr.add_argument("request"); pr.set_defaults(fn=cmd_route)
    pl = sub.add_parser("plan");   pl.add_argument("request"); pl.set_defaults(fn=cmd_plan)

    ps = sub.add_parser("sync")
    ps.add_argument("action", choices=["pull", "push", "status", "drain"])
    ps.add_argument("--repo", help="git remote URL (omit to use existing remote)")
    ps.add_argument("--branch", default="main")
    ps.add_argument("-m", "--message", default=None)
    ps.set_defaults(fn=cmd_sync)

    pm = sub.add_parser("memory")
    msub = pm.add_subparsers(dest="action", required=True)
    pmr = msub.add_parser("remember")
    pmr.add_argument("kind", choices=["episodic", "semantic", "procedural", "reference"])
    pmr.add_argument("content")
    pmr.add_argument("--tags", nargs="*")
    pmrec = msub.add_parser("recall")
    pmrec.add_argument("query")
    pmrec.add_argument("--kind", choices=["episodic", "semantic", "procedural", "reference"])
    pmrec.add_argument("--limit", type=int, default=10)
    msub.add_parser("stats")
    pm.set_defaults(fn=cmd_memory)

    sub.add_parser("stats").set_defaults(fn=cmd_stats)

    pa = sub.add_parser("agents")
    pa.add_argument("--division")
    pa.add_argument("--search")
    pa.add_argument("--limit", type=int, default=20)
    pa.set_defaults(fn=cmd_agents)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
