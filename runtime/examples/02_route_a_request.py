"""Show which skill the planner routes a request to. No execution.

No API key needed (planner falls back to keyword search when no key is set).

    python runtime/examples/02_route_a_request.py "review my SQL queries"
"""

from __future__ import annotations

import sys

from agency.llm import AnthropicLLM, LLMConfig, LLMError
from agency.planner import Planner
from agency.skills import SkillRegistry


def main(request: str) -> None:
    reg = SkillRegistry.load()

    llm: AnthropicLLM | None = None
    try:
        llm = AnthropicLLM(LLMConfig.from_env())
        llm._ensure_client()  # noqa: SLF001
    except LLMError:
        # No API key: planner uses keyword search instead.
        llm = None

    planner = Planner(reg, llm=llm)
    plan = planner.plan(request)

    print(f"Request: {request!r}\n")
    print(f"→ {plan.skill.emoji} {plan.skill.name} ({plan.skill.slug})")
    print(f"  reason: {plan.rationale}\n")
    if len(plan.candidates) > 1:
        print("Shortlist:")
        for c in plan.candidates:
            mark = "*" if c.slug == plan.skill.slug else " "
            print(f"  {mark} {c.slug:55s} — {c.name}")


if __name__ == "__main__":
    request = " ".join(sys.argv[1:]) or "build me a React component"
    main(request)
