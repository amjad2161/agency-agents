"""Smoke test: Router scores agents for representative queries."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "runtime"))

from runtime.agency.router import Router  # noqa: E402

r = Router()

queries = [
    "help me with WCAG accessibility audit for a React app",
    "build a financial model and analyze quarterly P&L",
    "fine-tune a large language model with RLHF",
    "design a marketing campaign for a B2B SaaS launch",
    "write SQL queries and optimize a postgres schema",
]

for q in queries:
    hits = r.route(q, k=3)
    print(f"\nQ: {q}")
    for h in hits:
        print(f"  {h.score:5.2f}  [{h.domain:18s}] {h.name}  -- {','.join(h.reasons[:3])}")
    assert hits, f"no hits for: {q}"

print("\nOK")
