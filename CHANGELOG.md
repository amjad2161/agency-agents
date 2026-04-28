# Changelog

All notable changes to the JARVIS / Agency runtime are documented here.

---

## [Pass 10-C] — 2026-04-28

### Summary
Mission C deep audit pass: type-annotation hardening, dependency review,
memory persistence verification, session-ID design confirmation, and
comprehensive regression test coverage.

### Added
- `runtime/tests/test_jarvis_pass10c.py` — 35 regression tests across 8
  categories: MemoryStore persistence, Session/TurnRecord model, SkillRegistry,
  Skill properties, tool-policy enforcement, Planner JSON parsing,
  `_parse_tool_list`, and offline Planner routing.
- `.github/dependabot.yml` — weekly automated dependency PRs for pip (runtime/)
  and GitHub Actions; anthropic SDK major versions pinned for manual review.
- `CHANGELOG.md` — this file.

### Changed
**Type annotations (mypy `--disallow-untyped-defs`):**
- `agency/logging.py` — `configure()` `stream` param annotated `Any`;
  `timed()` return type `Generator[dict[str, Any], None, None]`; added
  `Generator` to typing imports.
- `agency/supervisor.py` — `_drain()` annotated `(Any, list[str]) -> None`.
- `agency/server.py` — nested `gen()` annotated `-> Any`.
- `agency/cli.py` — `_shared_context_manager()` and
  `_shared_knowledge_expansion()` annotated `-> Any`; added `assert llm is not
  None` guard before `Executor` construction; restored truncated `except`
  handler body.
- `agency/managed_agents.py` — `_get_client()` annotated `-> "Anthropic"`;
  `_ensure_agent()` and `_ensure_env()` use walrus operator for mypy narrowing.
- `agency/planner.py` — `_first_text(resp: Any) -> str` fully annotated; added
  `from typing import Any`.
- `agency/skills.py` — `_parse_tool_list(raw: Any)` and `__iter__` annotated;
  added `Any, Iterable, Iterator` to typing imports.
- `agency/executor.py` — `_run_tool` and `_block_to_dict` annotated; delta
  None guard fixed.
- `agency/amjad_jarvis_cli.py` — all Click command functions annotated `-> None`;
  `editor_cmd` type narrowed; `__all__` restored after script truncation.

### Fixed
- Multiple files truncated by linter post-edit hook (logging.py, supervisor.py,
  server.py, cli.py, amjad_jarvis_cli.py, planner.py): restored in all cases.
- `tools.py` httpx context-manager errors (`__enter__`/`__exit__`) are
  pre-existing upstream API changes — tracked but not modified.

### Security
- Dependency audit: all packages current as of 2026-04-28. No CVEs detected
  against anthropic>=0.39.0, pydantic>=2.6.0, fastapi>=0.111.0,
  httpx>=0.27.0, click>=8.1.0. Loose `>=` bounds appropriate for a runtime
  library; upper bounds withheld intentionally.

---

## [Pass 10-B] — prior

*See git log for earlier pass history.*
