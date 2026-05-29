# External GitHub Opportunities

This document records high-value open-source projects discovered through GitHub search on 2026-05-29.

The goal is not to clone every repository. The goal is to convert the best external ideas into a license-aware, architecture-safe upgrade path for Singularity 2030.

## Adoption modes

| Mode | Meaning |
| --- | --- |
| `direct-integration` | Normal dependency use is acceptable when the technical fit is proven. |
| `adapter-integration` | Integrate through an API, SDK, sidecar, webhook, or bounded plugin seam. |
| `pattern-adaptation` | Study the design and reimplement the relevant pattern in our own code. |
| `research-only` | Treat as conceptual reference only unless a separate license strategy is approved. |

## Highest-leverage candidates

| Candidate | Why it matters | Adoption |
| --- | --- | --- |
| `langchain-ai/langgraph` | Durable graph/state model for resilient agent workflows. | Adapter/pattern |
| `open-telemetry/opentelemetry-collector` | Neutral traces, metrics, and logs for every autonomous module. | Adapter |
| `langfuse/langfuse` | LLM traces, evals, prompts, costs, and quality visibility. | Adapter, license review |
| `temporalio/temporal` | Long-running, retryable, auditable workflows. | Adapter after contracts stabilize |
| `hummingbot/hummingbot` | Trading connector, paper-trading, and strategy isolation patterns. | Pattern adaptation |
| `PX4/PX4-Autopilot` | Serious drone simulator/autopilot reference for SkyCore. | Adapter/simulator |
| `run-llama/llama_index` | Document/OCR/RAG adapters for skills, timesheets, and knowledge bases. | Adapter |
| `backstage/backstage` | Service catalog and scorecard ideas for repository governance. | Pattern adaptation |

## Layer-by-layer upgrade thesis

### Agent runtime

Use `langgraph`, `crewai`, `openai-agents-python`, and `microsoft-agent-framework` to sharpen the internal agent vocabulary:

- graph state
- handoffs
- guardrails
- typed tools
- role/task/team contracts

Do not replace the current runtimes immediately. Add adapters and tests first.

### Knowledge and retrieval

Use `llama_index` and `haystack` as reference points for:

- ACL-aware retrieval
- document ingestion
- OCR
- pipeline routing
- evaluation datasets

The first implementation should be a small ingestion adapter, not a global dependency in every app.

### Observability and evaluation

Use OpenTelemetry as the neutral event contract. LLM observability systems such as Langfuse and Phoenix can sit behind that contract.

Required event families:

- agent plan created
- tool call requested
- tool call approved
- tool call completed
- policy gate blocked
- human approval granted
- workflow retry scheduled
- model cost recorded
- evaluation passed/failed

### Durable workflows

Temporal is the 2030-grade answer for long-running, retryable, auditable workflows. Prefect is a lighter Python-native option for schedules, backtests, sync jobs, and health probes.

Do not introduce both for the same responsibility. Use the manifest to decide:

- Temporal: mission-critical long-running state machines
- Prefect: Python-native operational flows and scheduled checks
- Airflow/Dagster: data-heavy batch and lineage use cases if they become real

### Trading

Use Hummingbot and HFTBacktest to improve TradingCore before live execution:

- exchange connector isolation
- paper trading by default
- strategy lifecycle boundaries
- latency-aware backtesting
- order-book realism

Freqtrade is useful research, but GPL source should remain research-only unless the licensing posture changes.

### Drones

Use PX4 and MAVSDK to mature SkyCore:

- SITL-first verification
- mission simulation
- MAVLink adapter seams
- telemetry contracts
- safety-critical operator gates

ArduPilot is valuable research, but GPL source should remain research-only unless intentionally adopted under compatible terms.

### Developer experience

Use Backstage as the pattern for repository scorecards and service ownership. Start with the existing manifest and health probes before deploying a full portal.

## Non-negotiable rules

1. Do not copy source from `other`, `GPL`, `AGPL`, or `CC-BY` projects without explicit license review.
2. Do not add a heavyweight platform until the manifest proves the integration contract.
3. Do not let workflow automation bypass policy gates.
4. Do not let research-only repositories become production dependencies.
5. Do not let visual builders become the only source of truth; the manifest remains canonical.

## Next implementation increments

1. Add `opportunities --top` review to the PR checklist.
2. Add health probes per local module.
3. Add OpenTelemetry semantic conventions for agent events.
4. Add a `policy-gates.json` manifest for shell, trading, drones, proxying, and secrets.
5. Prototype one adapter each:
   - LangGraph graph runner around Mythos
   - OpenTelemetry trace emitter in Agency runtime
   - Hummingbot-inspired paper-trading contract for TradingCore
   - PX4/MAVSDK simulator contract for SkyCore
