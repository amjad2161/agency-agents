# Agency Runtime — Architecture

## Overview

A multi-domain agent orchestration runtime. Loads ~300 persona Markdown
files across 18 domains (jarvis, engineering, marketing, finance, …),
indexes them in a registry, scores them against free-text tasks via a
keyword router, and dispatches them through per-domain engines. Tracing,
KPI, ledger, and a daemon scheduler form the cross-cutting backbone. A
stdlib-only HTTP control plane exposes everything as JSON.

```
                      ┌───────────────────────────────┐
                      │      control_server.py        │  JSON HTTP
                      │  /agents /route /run /traces  │  (stdlib only)
                      └───────────┬───────────────────┘
                                  │
            ┌─────────────────────┼─────────────────────┐
            ▼                     ▼                     ▼
        engines.py           router.py             registry.py
   (per-domain dispatch)  (keyword scoring)   (loads 18 domains)
            │                     │                     │
            └─────────────────────┴─────────────────────┘
                                  │
                          agents/loader.py
                  (YAML-frontmatter persona parser)
                                  │
                          jarvis/ marketing/ engineering/ ...
                              ~300 .md persona files

  cross-cutting:
    trace_logger.py  pipelines/  ledger/  kpi.py  daemon.py  wealth.py
```

## Modules

### `agents/loader.py`

- `Agent(name, slug, system_prompt, metadata: dict, source_path)` dataclass.
- `load_agents(directory) -> dict[slug, Agent]` parses YAML frontmatter
  from every `*.md` file in `directory`. The body becomes `system_prompt`;
  frontmatter goes into `metadata` (color, description, emoji, vibe, …).

### `runtime/agency/trace_logger.py`

- `TraceLogger()`: span tree → JSONL at `~/.agency/traces/{ts}.jsonl`.
- API: `start_span(name, parent_id=None, **attrs)`,
  `end_span(sid, **attrs)`, classmethod `tail(n)`.

### `runtime/agency/kpi.py`

- Thread-safe singleton `Registry` with three metric types.
- Functional API: `counter(name).inc()`, `gauge(name).set(v)`,
  `with timer(name): ...`, `snapshot(name)` writes JSONL to
  `~/.agency/kpi/{name}.jsonl`, `registry.export()` returns a dict.

### `pipelines/`

- `Pipeline.of(name, *stages)` builds a sync/async DAG of context
  transforms. Each stage opens a span; pipeline opens a parent span.
  Errors propagate; spans are end-tagged with `error=...`.

### `ledger/`

- Append-only journal with double-entry validation. Persists to JSONL.
- `Transaction(date, memo, postings=[(account, side, Decimal)])`.
- `balanced` invariant: `Σ debits == Σ credits`. Negative amounts rejected.

### `runtime/agency/daemon.py`

- Lightweight scheduler. Registers jobs with cadence; ticks deterministically
  in tests. Emits per-job KPI counters and timers; spans per tick.

### `runtime/agency/wealth.py`

- Composes ledger + daemon + KPI into a P&L / balance-sheet engine.
- Publishes KPI gauges (`wealth.bs.*`, `wealth.pnl.*`) on each cycle.

### `runtime/agency/registry.py`

- `AgentRegistry().load()` walks `DOMAIN_DIRS` (18 directories), loads
  each domain's personas via `agents.loader`, stamps `metadata['domain']`,
  indexes by name and by domain.
- Lookups: `get(name)`, `by_domain(d)`, `by_color(c)`, `all()`,
  `domains()`, `stats()`.
- Emits gauges `registry.agents.{domain}`, `registry.agents.total`,
  `registry.domains.total` on load.
- 302 unique agents across 18 domains (304 raw — 2 cross-domain name
  collisions deduped by first-wins).

### `runtime/agency/router.py`

- `Router(registry).route(query, k=5) -> list[RouteHit]`.
- Pure stdlib scoring (no embeddings):
  - `+3.0` per name token overlap
  - `+1.5` if domain name is in query
  - `+1.0 × min(5, |overlap|)` over description tokens
  - `+0.5 × min(4, |overlap|)` over first 2KB of system prompt
  - `+0.25` if a color hint matches
- Times each call (`router.route` timer); counts queries.

### `runtime/agency/engines.py`

- `DomainEngine` base + `MarketingEngine`, `EngineeringEngine`,
  `SalesEngine`, `ProductEngine`.
- API: `agents()`, `suggest(query, k)` (router results filtered to the
  engine's domain), `run(slug, payload) -> EngineResult`.
- `run` is a deterministic stub (echoes payload, emits span + counters).
  Real LLM dispatch lives in higher-level pipelines.

### `runtime/agency/control_server.py`

- Stdlib `ThreadingHTTPServer` + `BaseHTTPRequestHandler`. No third-party
  deps. Bound to `127.0.0.1:8765` by default.
- Endpoints:
  - `GET  /healthz`
  - `GET  /agents[?domain=…&color=…]`
  - `GET  /kpi`
  - `GET  /traces[?n=20]`
  - `POST /route   {"query":…, "k":5}`
  - `POST /run     {"domain":…, "slug":…, "payload":{…}}`

> Note: a separate `runtime/agency/server.py` (FastAPI) hosts the chat
> UI / skills / planner / executor. The control plane here is intentionally
> dependency-free for smoke testing and headless operation.

## Data flow — a single request

1. Client `POST /route {"query":"optimize a postgres index"}`.
2. Server warms `default_registry()` (lazy singleton, loads all 18 domains
   on first call) and constructs a `Router`.
3. Router tokenizes the query and scores every agent. Top-k returned.
4. Client `POST /run {"domain":"engineering","slug":<top-hit slug>}`.
5. Engine opens a span `engine:engineering:run`, looks up the agent,
   bumps `engine.engineering.dispatch`, returns `EngineResult`.
6. Trace JSONL and KPI counters are observable via `GET /traces`,
   `GET /kpi`.

## Domain inventory

| domain              | personas |
|---------------------|---------:|
| academic            |        5 |
| design              |        9 |
| engineering         |       36 |
| examples            |        6 |
| finance             |        6 |
| game-development    |        5 |
| integrations        |        2 |
| jarvis              |      109 |
| marketing           |       30 |
| paid-media          |        7 |
| product             |        6 |
| project-management  |        6 |
| sales               |        8 |
| spatial-computing   |        6 |
| specialized         |       44 |
| strategy            |        3 |
| support             |        7 |
| testing             |        9 |
| **total raw**       |  **304** |
| **unique by name**  |  **302** |

## Smoke harness

`scripts/smoke_all.py` runs every `scripts/smoke_*.py` as a subprocess:

```
smoke_control_server.py  OK
smoke_daemon.py          OK
smoke_engines.py         OK
smoke_ledger.py          OK
smoke_pipelines.py       OK
smoke_registry.py        OK
smoke_router.py          OK
smoke_wealth.py          OK
8/8 green
```

## Conventions

- All modules byte-compile cleanly (`python -m py_compile <file>`).
- Cross-module sys.path bootstrap: prepend repo root and `runtime/`.
- KPI naming: `{system}.{component}.{event}` (e.g. `engine.engineering.dispatch`,
  `router.queries`, `registry.agents.total`).
- Persistence root: `~/.agency/{traces,kpi,ledger}/...` (JSONL).
- Persona color/emoji/etc. live in `Agent.metadata`, not as direct attrs.
