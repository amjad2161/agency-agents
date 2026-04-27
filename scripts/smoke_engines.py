"""Smoke test: per-domain engines route + dispatch within their domain."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "runtime"))

from runtime.agency.engines import ENGINES, engine_for  # noqa: E402

cases = {
    "marketing": "launch a B2B SaaS product with content marketing",
    "engineering": "optimize a slow postgres query and add an index",
    "sales": "build a discovery call playbook for enterprise prospects",
    "product": "write a PRD for a new onboarding flow",
}

for domain, query in cases.items():
    eng = engine_for(domain)
    ags = eng.agents()
    sugg = eng.suggest(query, k=3)
    print(f"\n[{domain}] agents={len(ags)} suggestions={len(sugg)}")
    for h in sugg:
        print(f"  {h.score:5.2f}  {h.name}")
    assert ags, f"no agents in {domain}"
    if sugg:
        res = eng.run(sugg[0].slug, {"task": query})
        print(f"  run.ok={res.ok}  agent={res.output.get('agent')}")
        assert res.ok, res.error

print("\nOK")
