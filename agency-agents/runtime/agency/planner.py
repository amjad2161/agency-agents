"""Pick the right skill for a user request.

Two-stage:
1. Pre-filter via the SkillRegistry's keyword search (fast, free).
2. Ask the planner LLM to pick the best slug from the shortlist.

If the LLM is unavailable we fall back to the top keyword match.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .llm import AnthropicLLM, LLMError
from .logging import get_logger
from .skills import Skill, SkillRegistry
from .jarvis_brain import SupremeJarvisBrain


@dataclass
class PlanResult:
    skill: Skill
    rationale: str
    candidates: list[Skill]


PLANNER_SYSTEM = (
    "You route user requests to specialized AI agents. "
    "You will be given a request and a numbered list of candidate agents. "
    "Reply with ONLY a JSON object: "
    '{"choice": <number>, "rationale": "<one short sentence>"} '
    "Pick the single best agent for the request. No prose, no code fences."
)


class Planner:
    def __init__(self, registry: SkillRegistry, llm: AnthropicLLM | None = None,
                 shortlist_size: int = 8):
        self.registry = registry
        self.llm = llm
        self.shortlist_size = shortlist_size

    def plan(self, request: str, hint_slug: str | None = None) -> PlanResult:
        log = get_logger()
        if hint_slug:
            skill = self.registry.by_slug(hint_slug)
            if skill is None:
                raise ValueError(f"Unknown skill slug: {hint_slug}")
            log.info("plan.hint slug=%s", hint_slug)
            return PlanResult(skill=skill, rationale="explicit user choice", candidates=[skill])

        # Use SupremeJarvisBrain for keyword-weighted routing first.
        try:
            brain = SupremeJarvisBrain(self.registry)
            top_results = brain.top_k(request, k=self.shortlist_size)
            candidates = [skill for skill, _ in top_results]
        except Exception as exc:  # noqa: BLE001
            log.warning("plan.brain_unavailable falling back to keyword match: %s", exc)
            candidates = []
        # Fall back to naive search if brain returns nothing.
        if not candidates:
            candidates = self.registry.search(request, limit=self.shortlist_size)
        if not candidates:
            candidates = self.registry.all()[: self.shortlist_size]

        if len(candidates) == 1 or self.llm is None:
            picked = candidates[0]
            reason = "top keyword match" if self.llm is None else "only candidate"
            log.info("plan.picked slug=%s reason=%r candidates=%d",
                     picked.slug, reason, len(candidates))
            return PlanResult(skill=picked, rationale=reason, candidates=candidates)

        try:
            choice_idx, rationale = self._ask_llm(request, candidates)
        except LLMError:
            log.warning("plan.llm_unavailable falling back to keyword match")
            return PlanResult(
                skill=candidates[0],
                rationale="LLM unavailable, fell back to top keyword match",
                candidates=candidates,
            )
        if choice_idx < 0 or choice_idx >= len(candidates):
            choice_idx = 0
        picked = candidates[choice_idx]
        log.info("plan.picked slug=%s reason=%r candidates=%d",
                 picked.slug, rationale, len(candidates))
        return PlanResult(skill=picked, rationale=rationale, candidates=candidates)

    def _ask_llm(self, request: str, candidates: list[Skill]) -> tuple[int, str]:
        assert self.llm is not None
        lines = [f"{i+1}. {c.name} ({c.category}) — {c.description}" for i, c in enumerate(candidates)]
        prompt = f"Request:\n{request}\n\nCandidates:\n" + "\n".join(lines)
        resp = self.llm.messages_create(
            system=PLANNER_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            model=self.llm.config.planner_model,
            max_tokens=200,
        )
        text = _first_text(resp)
        return _parse_choice(text)


def _first_text(resp) -> str:
    for block in getattr(resp, "content", []):
        if getattr(block, "type", None) == "text":
            return block.text
    return ""


# Non-greedy match — if the LLM wraps its JSON in commentary that itself
# contains `{...}` (e.g. an example), a greedy `\{.*\}` would span the
# whole region and fail to parse. Non-greedy stops at the first `}`,
# and we fall back to scanning all candidates if the first doesn't
# decode cleanly.
_JSON_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _parse_choice(text: str) -> tuple[int, str]:
    """Parse the planner's JSON. Tolerant of stray prose around the JSON."""
    candidates = _JSON_RE.findall(text)
    if not candidates:
        return 0, "could not parse planner response"
    data = None
    for blob in candidates:
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "choice" in parsed:
            data = parsed
            break
    if data is None:
        # No candidate had `choice`; fall back to the first that decoded.
        for blob in candidates:
            try:
                data = json.loads(blob)
                break
            except json.JSONDecodeError:
                continue
    if data is None:
        return 0, "could not decode planner JSON"
    choice = data.get("choice", 1)
    try:
        idx = int(choice) - 1
    except (TypeError, ValueError):
        idx = 0
    rationale = str(data.get("rationale", "no rationale provided")).strip()
    return idx, rationale
