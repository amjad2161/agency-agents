"""Enumerate persona counts across all known domain directories."""
import sys
from pathlib import Path

sys.path.insert(0, ".")
from agents.loader import load_agents

DIRS = [
    "academic", "design", "engineering", "examples", "game-development",
    "integrations", "marketing", "paid-media", "product",
    "project-management", "sales", "spatial-computing", "specialized",
    "strategy", "support", "testing", "jarvis", "finance",
]


def main() -> int:
    total = 0
    rows = []
    for d in DIRS:
        p = Path(d)
        if not p.exists():
            rows.append((d, "MISSING", 0))
            continue
        try:
            agents = load_agents(p)
            rows.append((d, "OK", len(agents)))
            total += len(agents)
        except Exception as exc:  # pragma: no cover - diagnostic
            rows.append((d, f"ERR:{exc}", 0))
    width = max(len(r[0]) for r in rows)
    for name, status, count in rows:
        print(f"{name:<{width}}  {status:<10}  {count}")
    print(f"\nTOTAL personas loaded: {total}")
    print(f"Domain dirs present: {sum(1 for _, s, _ in rows if s == 'OK')}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
