"""Drive a multi-skill workflow: one skill delegates to another.

Forces the run through `engineering-software-architect` and lets it call
`delegate_to_skill` to hand off implementation work to a specialist.

Requires ANTHROPIC_API_KEY.

    python runtime/examples/04_delegate_between_skills.py
"""

from __future__ import annotations

from agency.executor import Executor
from agency.llm import AnthropicLLM, LLMConfig
from agency.skills import SkillRegistry


REQUEST = (
    "Plan a small Flask API that returns weather for a city. "
    "If you decide implementation specifics fall outside your specialty, "
    "use delegate_to_skill to hand the implementation to a backend skill — "
    "list_skills first if you need to see the options."
)


def main() -> None:
    reg = SkillRegistry.load()
    skill = reg.by_slug("engineering-software-architect")
    if skill is None:
        # Fall back to any architecture-flavored skill if the slug changes.
        skill = next((s for s in reg if "architect" in s.slug), reg.all()[0])

    llm = AnthropicLLM(LLMConfig.from_env())
    result = Executor(reg, llm).run(skill, REQUEST)
    print(result.text)
    print(
        f"\n[turns={result.turns} "
        f"in={result.usage.input_tokens} out={result.usage.output_tokens}]"
    )


if __name__ == "__main__":
    main()
