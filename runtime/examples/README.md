# Runtime examples

Runnable scripts that exercise the runtime's programmatic API. Run them
from the repo root with the runtime installed (`pip install -e runtime`).

| Script | What it shows | API key needed? |
|---|---|---|
| [`01_list_skills.py`](01_list_skills.py) | Walk the loaded `SkillRegistry`, group skills by category. | No |
| [`02_route_a_request.py`](02_route_a_request.py) | Ask the planner which skill it would pick for a given prompt. | No (falls back to keyword match) |
| [`03_run_with_streaming.py`](03_run_with_streaming.py) | Stream a complete agent run via the `Executor` event stream. | Yes |
| [`04_delegate_between_skills.py`](04_delegate_between_skills.py) | Drive multi-agent delegation; one skill hands off to another. | Yes |

Tip: enable structured logging to see what's happening under the hood.

```bash
AGENCY_LOG=info python runtime/examples/03_run_with_streaming.py "..."
```

…or via the CLI:

```bash
agency -v run "review my SQL queries"
```
