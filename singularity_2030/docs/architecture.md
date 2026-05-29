# Singularity 2030 Architecture

## Architectural thesis

The workspace wants to become a modular autonomous operating system, not a monolith.

The repositories already divide into natural layers:

1. Quality harness: repeatable workflows, hooks, tests, review, security, and CI discipline.
2. Skill and persona layer: portable instructions, specialized agents, memory, routing, and orchestration.
3. SDK and reference layer: official clients, quickstarts, prompt archives, and research mirrors.
4. Agent runtime layer: goal planning, tool execution, memory, vector stores, workflows, and APIs.
5. Domain execution layer: timesheets, trading, drones, media generation, dashboards, and real-world operations.
6. Infrastructure layer: local proxying, Docker stacks, observability, and deployment support.

Each layer can be replaced independently. Composition happens through manifests and contracts, not hidden imports.

## Core contracts

### Repo module

Every repository is represented as a `RepoModule` with:

- stable slug
- repo path
- layer
- maturity
- vision
- stack
- capabilities
- integration modes
- runnable commands
- risks

This makes high-level orchestration testable without importing every project.

### Integration edge

Every cross-repo connection is represented as an `IntegrationEdge`:

- source
- target
- mode
- contract

Edges describe how modules should cooperate. They do not imply code-level coupling.

### Execution profile

An execution profile selects ordered modules and invariants for a scenario:

- `full-stack-ai-ops`
- `real-world-autonomy`
- `research-to-runtime`

Profiles are intentionally explicit. Hidden all-repo bootstrapping would be unsafe because some modules can trade money, move drones, run shell commands, or expose proxies.

## Safety model

The control plane treats autonomy as a spectrum:

- `analysis-first`: research, prompt comparison, SDK examples, and dry-run plans
- `supervised-autonomous`: agent workflows execute with quality gates and human review
- `operator-approved`: real-world actions require simulation/backtest evidence and explicit approval

This is the difference between a useful singular system and a dangerous pile of automation.

## Integration rule

Prefer adapters and manifests over shared mutable state.

Examples:

- SuperAGI should call BRAINIAC as an HTTP tool instead of importing internal modules directly.
- Mythos should operate the trading engine through bounded commands or APIs, not direct database mutation.
- ComfyUI should receive workflow JSON from agents instead of embedding itself into every app.
- Research-only repositories should produce tests, contracts, and documentation, not copied proprietary source.

## 2030-ready engineering posture

The target standard is:

- observable by default
- reversible by design
- modular at repo and capability boundaries
- policy-gated for physical, financial, shell, and proxy operations
- testable at manifest, adapter, and workflow levels
- portable across Claude Code, Cursor, CLI, web apps, Docker stacks, and future harnesses
