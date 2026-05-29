# Integration Map

## Common denominator

All attached repositories orbit the same idea: autonomous systems need a reliable way to turn intent into bounded execution.

The shared vocabulary is:

- agents
- skills
- tools
- prompts
- workflows
- memory
- observability
- domain adapters
- safety gates

## Layer map

| Layer | Repositories | Role |
| --- | --- | --- |
| Quality harness | `everything-claude-code`, `claude-code` | Workflow discipline, plugins, hooks, review, CI, settings |
| Skill/persona standard | `agency-agents`, `skills` | Specialist catalog, SKILL.md standards, cross-harness portability |
| SDK/reference | `anthropic-sdk-typescript`, `anthropic-quickstarts` | Production API dependency and working examples |
| Research archives | `system-prompts-and-models-of-ai-tools`, `claude-code-abc` | Research-only prompt/tool/architecture study |
| Agent runtime | `Mythos`, `SuperAGI`, `amjad2161` | Planning, tools, memory, workflows, APIs, specialized modules |
| Domain apps | `auto-save-sync`, `autonomous-trading-engine`, `Dji-owner`, `ComfyUI`, `tradingboy` | Timesheets, trading, drones, media generation, future bot shell |
| Infrastructure | `cors-anywhere` | Controlled local dev proxying |

## High-value edges

1. `everything-claude-code` -> `agency-agents`
   - ECC governs quality.
   - Agency supplies specialists.

2. `skills` -> `everything-claude-code`
   - Agent Skills provide portable file format discipline.
   - ECC operationalizes the workflows.

3. `anthropic-sdk-typescript` -> `anthropic-quickstarts`
   - SDK is the dependency.
   - Quickstarts are living examples.

4. `mythos` -> `autonomous-trading-engine`
   - Mythos can run analysis and backtest workflows.
   - Trading execution remains behind operator gates.

5. `amjad2161` -> `Dji-owner`
   - BRAINIAC contributes navigation, telemetry, satellite, and security intelligence.
   - SkyCore owns mission execution and hardware adapters.

6. `SuperAGI` -> `ComfyUI`
   - SuperAGI plans and delegates.
   - ComfyUI executes media workflows.

7. `cors-anywhere` -> web apps
   - Local development helper only.
   - Never an open production proxy.

## Non-negotiable boundaries

- Do not merge all source trees into one import graph.
- Do not use leaked or proprietary archives as production source.
- Do not let shell, trading, drones, or open proxies run without policy gates.
- Do not make Supabase or exchange credentials part of the unified manifest.
- Do not hide repo-specific tests behind a single green "all good" result.

## Next integration increments

1. Add per-repo health probes that run the safest documented command for each repo.
2. Add adapter specs for HTTP tools: BRAINIAC, SkyCore, ComfyUI, Supabase edge functions.
3. Add policy gate definitions for shell, trading, drones, secrets, and proxies.
4. Add a local dashboard that renders the catalog, profile graph, and health status.
