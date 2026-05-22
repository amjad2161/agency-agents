"""Run a request end-to-end, streaming text deltas to stdout.

Requires ANTHROPIC_API_KEY.

    python runtime/examples/03_run_with_streaming.py "summarize the README"
"""

from __future__ import annotations

import sys

from agency.executor import Executor
from agency.llm import AnthropicLLM, LLMConfig
from agency.planner import Planner
from agency.skills import SkillRegistry


def main(request: str) -> None:
    reg = SkillRegistry.load()
    llm = AnthropicLLM(LLMConfig.from_env())

    plan = Planner(reg, llm=llm).plan(request)
    print(f"→ {plan.skill.emoji} {plan.skill.name} — {plan.rationale}\n", flush=True)

    executor = Executor(reg, llm)
    for ev in executor.stream(plan.skill, request):
        if ev.kind == "text_delta":
            print(ev.payload, end="", flush=True)
        elif ev.kind == "tool_use":
            print(f"\n[tool] {ev.payload['name']}({ev.payload['input']})", flush=True)
        elif ev.kind == "tool_result":
            tag = "tool_error" if ev.payload["is_error"] else "tool_result"
            preview = str(ev.payload["content"])[:200]
            print(f"\n[{tag}] {preview}", flush=True)
        elif ev.kind == "stop":
            print(f"\n\n[stop: {ev.payload}]", flush=True)
        elif ev.kind == "usage":
            u = ev.payload
            print(
                f"\n[usage] in={u['input_tokens']} out={u['output_tokens']} "
                f"cache_w={u['cache_creation_input_tokens']} "
                f"cache_r={u['cache_read_input_tokens']}",
                flush=True,
            )


if __name__ == "__main__":
    request = " ".join(sys.argv[1:]) or "say hi"
    main(request)
