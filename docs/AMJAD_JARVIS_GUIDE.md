# Amjad Jarvis Meta-Orchestrator Architecture Guide

## Overview

**Amjad Jarvis** is a unified meta-orchestrator that transforms the 144+ agent system into a single cohesive intelligence that IS Amjad's extended mind.

Instead of routing to individual agents, Jarvis understands Amjad completely—his personality, technical stack, constraints, and values—and injects this context into every single agent interaction. The result: agents that think like Amjad and coordinate seamlessly.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│     AMJAD JARVIS META-ORCHESTRATOR (jarvis.py)              │
│  ├─ AmjadProfile (personality + constraints)               │
│  ├─ AmjadJarvisMetaOrchestrator (unified brain)            │
│  └─ Global singleton (jarvis())                            │
└────────────┬─────────────────────────────────────────────────┘
             │
    ┌────────┼────────┐
    │        │        │
    v        v        v
┌────────┐ ┌──────┐ ┌───────────┐
│Executor│ │LLM   │ │SkillReg   │
│(Runtime)│ │(API) │ │(155+ Agents)
└────────┘ └──────┘ └───────────┘
    │
    v
┌─────────────────────────────────────────┐
│  PERSONALITY INJECTION                  │
│  (Profile → System Prompt Enhancement)  │
└─────────────────────────────────────────┘
    │
    v
┌─────────────────────────────────────────┐
│  144+ SPECIALIST AGENTS                 │
│  (Now thinking like Amjad)              │
└─────────────────────────────────────────┘
```

---

## Core Components

### 1. **AmjadProfile** (`amjad_jarvis_meta_orchestrator.py`)

Represents Amjad's complete context:

```python
@dataclass
class AmjadProfile:
    name: str = "Amjad"
    role: str = "Founder & Tech Lead"
    personality_traits: list[str]  # Direct, iterative, results-oriented, etc.
    technical_stack: list[str]     # Python, TypeScript, FastAPI, etc.
    work_values: list[str]         # No artificial limits, evidence>claims, etc.
    known_projects: list[str]      # Your projects
    constraints: dict              # No security breaches, respect APIs, etc.
    preferences: dict              # Shell access, web search, trust modes, etc.
```

**Methods:**
- `to_system_prompt_prefix()` — Generates the personality injection text
- `save()` — Persists to `~/.agency/amjad-profile.json`
- `load_or_create()` — Loads from disk or creates default

### 2. **AmjadJarvisMetaOrchestrator** (`amjad_jarvis_meta_orchestrator.py`)

The unified execution engine:

```python
class AmjadJarvisMetaOrchestrator:
    def execute_unified_request(request, agent_slug=None, session_id=None)
        # Auto-routes to best agent with Amjad's context injected
    
    def execute_multi_agent_workflow(workflow_name, request, parallel=True)
        # Coordinates multiple agents in parallel or sequence
    
    def _create_context_aware_executor(skill)
        # Injects Amjad's profile into agent's system prompt
    
    def set_trust_mode(mode)      # off / on-my-machine / yolo
    def enable_shell(bool)
    def enable_web_search(bool)
    def enable_code_execution(bool)
    def enable_computer_use(bool)
```

**Key Design:**
- One instance per session (though a global singleton exists)
- Lazy-loads skills registry and LLM client
- Injects profile into every agent automatically
- Supports both single and multi-agent workflows
- Dynamic permission management

### 3. **CLI Integration** (`amjad_jarvis_cli.py`)

Commands accessible via `agency amjad <subcommand>`:

```bash
agency amjad profile show              # Display full profile
agency amjad profile edit              # Edit in $EDITOR
agency amjad profile set KEY VALUE     # Update single setting
agency amjad trust {off|on-my-machine|yolo}  # Set trust mode
agency amjad shell {on|off|status}     # Control shell access
agency amjad web-search {on|off}       # Control web search
agency amjad code-exec {on|off}        # Control code execution
agency amjad computer-use {on|off}     # Control computer use
agency amjad run <REQUEST>             # Execute request
agency amjad status                    # Show system status
```

---

## How It Works

### Flow: Single Request

```python
# 1. User creates/gets Jarvis instance
jarvis = jarvis()  # or init_jarvis(config)

# 2. Execute a request
result = jarvis.execute_unified_request(
    "Audit security and deploy fixes"
)
```

**Behind the scenes:**
1. ✅ Load Amjad's profile from `~/.agency/amjad-profile.json`
2. ✅ Planner auto-selects best agent (Security Engineer in this case)
3. ✅ Create context-aware executor
4. ✅ Inject Amjad's profile into agent's system prompt
5. ✅ Execute agent with full context
6. ✅ Return unified result

### Flow: Multi-Agent Workflow

```python
results = jarvis.execute_multi_agent_workflow(
    workflow_name="product_discovery",
    primary_request="Should we build X?",
    agent_sequence=["trend-researcher", "backend-architect", "ux-researcher"],
    parallel=True
)
```

**Behind the scenes:**
1. ✅ Identify all relevant agents
2. ✅ Create context-aware executors for each
3. ✅ Execute in parallel (if safe) with thread pool
4. ✅ Collect results from all agents
5. ✅ Synthesize into one output
6. ✅ Return coordination results

### Context Injection Mechanism

Every agent receives Amjad's context prepended to their system prompt:

```
[AMJAD'S CONTEXT]
You are part of Amjad's unified agency. You understand him as:
- Name: Amjad | Role: Founder & Tech Lead
- Personality: Direct, results-oriented, iterative...
- Stack: Python, TypeScript, FastAPI...
- Values: No artificial limits, ownership mindset...
- Trust Mode: on-my-machine
- Permissions: shell ✓, web-search ✓, code-exec ✓...

[AGENT'S ORIGINAL SYSTEM PROMPT]
You are the Security Engineer. Your mission is...
```

Result: The agent knows who it's serving and what Amjad cares about.

---

## Trust Modes

### Mode: `off` (Sandbox)
- Shell access: Disabled
- File system: Workdir only
- Web fetch: Blocked on private IPs
- Code execution: Allowed (restricted)
- Use case: Development/testing

### Mode: `on-my-machine` (Default)
- Shell access: Enabled (denylist active)
- File system: Full read/write
- Web fetch: Unrestricted
- Code execution: Full Python
- Use case: Production, trusted environment

### Mode: `yolo` (Unrestricted)
- Shell access: Enabled (no guards)
- File system: Unrestricted
- Web fetch: Unrestricted
- Code execution: Full execution
- Use case: Fully trusted scenarios

---

## Integration Points

### With Existing Runtime

Jarvis plugs into existing systems:
- ✅ Uses `Executor` for tool execution
- ✅ Uses `SkillRegistry` for all 144+ agents
- ✅ Uses `AnthropicLLM` for model calls
- ✅ Uses `MemoryStore` for session persistence
- ✅ Respects all existing trust/permission modes (PR #10)
- ✅ Compatible with all 12+ builtin tools

### With Memory Store

Persistent context across sessions:

```python
# Session 1: Product discovery
result1 = jarvis.execute_unified_request(
    "Analyze market opportunity for X",
    session_id="product_research_q1"
)

# Session 2: Agent remembers previous analysis
result2 = jarvis.execute_unified_request(
    "Now create launch plan for X",
    session_id="product_research_q1"  # Same session
)

# Agent2 has full context from Agent1
```

---

## Usage Patterns

### Pattern 1: Simple Auto-Routing

```python
from agency.amjad_jarvis_meta_orchestrator import jarvis

j = jarvis()
result = j.execute_unified_request("Review this code for security issues")
print(result.text)
```

### Pattern 2: Explicit Agent Selection

```python
result = j.execute_unified_request(
    "Build a landing page",
    primary_agent_slug="engineering-frontend-developer"
)
```

### Pattern 3: Multi-Agent Workflow (Parallel)

```python
results = j.execute_multi_agent_workflow(
    workflow_name="product_launch",
    primary_request="Launch new product",
    parallel=True
)

for agent_slug, result in results.items():
    print(f"{agent_slug}: {result.text}")
```

### Pattern 4: Multi-Agent Workflow (Sequential)

```python
results = j.execute_multi_agent_workflow(
    workflow_name="feature_development",
    primary_request="Build passwordless auth",
    agent_sequence=["backend-architect", "database-optimizer", "frontend-dev"],
    parallel=False  # Each agent waits for prior
)
```

### Pattern 5: Dynamic Permission Control

```python
j.set_trust_mode("yolo")
j.enable_shell(True)
j.enable_code_execution(True)

# Now execute with full capabilities
result = j.execute_unified_request("Deploy production fixes")
```

---

## Performance Characteristics

| Scenario | Behavior | Time |
|----------|----------|------|
| Single agent request | Auto-route + execute | ~5-30s |
| Multi-agent (parallel) | N agents in parallel | ~5-30s |
| Multi-agent (sequential) | N agents, one after next | ~5s × N |
| Profile load | From disk | <1ms |
| Context injection | String concat | <1ms |
| Permission change | Update env vars | <1ms |

**Bottleneck:** LLM API calls (5-30 seconds typical)

---

## Extension Points

### Add New Workflow

```python
def workflow_custom():
    j = jarvis()
    results = j.execute_multi_agent_workflow(
        workflow_name="my_workflow",
        primary_request="Do something",
        agent_sequence=["agent1", "agent2"],
        parallel=True
    )
    return results
```

### Customize Profile

Edit `~/.agency/amjad-profile.json`:

```json
{
  "name": "Amjad",
  "personality_traits": ["Direct", "..."],
  "constraints": {"no_real_security_breaches": true},
  "preferences": {"trust_mode": "on-my-machine"}
}
```

### Hook Into Execution

```python
from agency.amjad_jarvis_meta_orchestrator import jarvis

j = jarvis()

# Before execution
j.amjad.preferences["trust_mode"] = "yolo"

# Execute
result = j.execute_unified_request("Do something")

# After execution
print(f"Turns: {result.turns}, Tokens: {result.usage.output_tokens}")
```

---

## Testing

Comprehensive test suite in `tests/test_amjad_jarvis.py`:

```bash
# Run all tests
pytest tests/test_amjad_jarvis.py -v

# Run specific test class
pytest tests/test_amjad_jarvis.py::TestAmjadProfile -v

# Run with coverage
pytest tests/test_amjad_jarvis.py --cov=agency.amjad_jarvis_meta_orchestrator
```

**Coverage:**
- ✅ Profile creation, persistence, system prompt generation
- ✅ Trust mode switching
- ✅ Permission management
- ✅ Orchestrator initialization
- ✅ Context injection
- ✅ Multi-agent workflows
- ✅ Integration scenarios

---

## FAQ

**Q: Does this break existing runtime?**
A: No. Jarvis is opt-in. Existing `agency run` still works. Jarvis is accessed via `agency amjad run` or programmatically.

**Q: Can I use Jarvis without a profile?**
A: Yes. It creates a default profile automatically on first use.

**Q: How much does context injection cost?**
A: Negligible—it's cached after first request due to Claude's prompt caching.

**Q: Can agents see each other's outputs in workflows?**
A: Currently no—they execute independently. See "Extension Points" to implement cross-agent visibility.

**Q: How do I reset to factory settings?**
A: Delete `~/.agency/amjad-profile.json`. Jarvis will recreate it with defaults on next run.

---

## Next Steps

1. **Try the CLI:**
   ```bash
   agency amjad profile show
   agency amjad trust on-my-machine
   agency amjad run "audit code"
   ```

2. **Run example workflows:**
   ```bash
   python -m examples.amjad_workflows product_discovery
   python -m examples.amjad_workflows feature_development
   ```

3. **Run tests:**
   ```bash
   pytest tests/test_amjad_jarvis.py -v
   ```

4. **Integrate into your workflows:**
   ```python
   from agency.amjad_jarvis_meta_orchestrator import jarvis
   j = jarvis()
   result = j.execute_unified_request("your request")
   ```

---

**You now have a system where every agent thinks, communicates, and acts like you.**
