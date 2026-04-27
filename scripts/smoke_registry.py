"""Smoke test: AgentRegistry indexes all 18 domains."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "runtime"))

from runtime.agency.registry import AgentRegistry, DOMAIN_DIRS  # noqa: E402

reg = AgentRegistry().load()
stats = reg.stats()
print(f"Total agents: {len(reg)}")
print(f"Domains:      {len(reg.domains())}/{len(DOMAIN_DIRS)}")
for d, n in stats.items():
    print(f"  {d:22s} {n}")

# Spot checks
some = reg.all()[:3]
for a in some:
    print(f"sample: {a.name} domain={a.metadata.get('domain','?')} color={a.metadata.get('color','?')}")

# by_color spot check
blues = reg.by_color("blue")
print(f"by_color(blue): {len(blues)}")

assert len(reg) > 0
assert len(reg.domains()) == 18
print("OK")
