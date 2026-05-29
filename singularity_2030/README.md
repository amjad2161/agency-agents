# Singularity 2030

Singularity 2030 is a small control-plane project that turns the attached repositories into one composable system map.

It does not merge codebases or erase repository boundaries. Instead, it gives every repo a contract:

- what it is for
- which layer it belongs to
- which capabilities it contributes
- how it can run alone
- how it can be wired into a larger autonomous stack
- which risks must be gated before production use

## North star

Build a modular autonomous operating system for agents, tools, domains, and humans.

The common denominator across the workspace is not a single framework. It is a pattern:

1. Agentic systems plan, delegate, and reflect.
2. Domain systems execute bounded work in the real world.
3. Prompt, skill, SDK, and plugin repos make the system portable across harnesses.
4. Risky domains such as trading, drones, shell execution, and proxies need explicit safety contracts.
5. Every module must be useful alone and deterministic when composed.

## Project layout

```text
singularity_2030/
  singularity_nexus/
    catalog/repositories.json   # canonical repo/module manifest
    catalog/__init__.py         # loader and validator
    models.py                   # typed contracts
    orchestrator.py             # profiles, capability map, common vision
    cli.py                      # command line inspector
  docs/
    architecture.md
    integration-map.md
  tests/
```

## Usage

```bash
cd singularity_2030
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"

singularity-nexus summary
singularity-nexus summary --format json
singularity-nexus modules --capability agent-orchestration
singularity-nexus capabilities --format json
singularity-nexus profile full-stack-ai-ops
singularity-nexus profile real-world-autonomy
singularity-nexus profile research-to-runtime

pytest
```

Without installation, run from this directory with:

```bash
python3 -m singularity_nexus summary --format json
```

## Execution profiles

### Full Stack AI Operations

The safest default composition. It starts with quality and workflow gates, then adds personas, skills, SDKs, agent runtimes, application APIs, creative workflows, local dev proxying, and the timesheet product.

### Real World Autonomy

For drones, trading, and physical/financial automation. This profile is intentionally operator-approved: simulation, backtesting, policy gates, and rollback plans are part of the contract.

### Research to Runtime

For turning prompts, mirrored code, SDKs, and quickstarts into legal, tested, production-safe implementation patterns. Research archives stay read-only.

## Design principle

Singularity 2030 is a manifest-first architecture. The manifest is the stable seam. Code can evolve inside each repo while the control plane keeps the integration vocabulary consistent.
