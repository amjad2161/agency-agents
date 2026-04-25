# Amjad Jarvis - Troubleshooting & FAQ

## ❓ Frequently Asked Questions

### Q: Does Amjad Jarvis break the existing agency-agents system?
**A:** No. Jarvis is completely opt-in and non-intrusive.
- Existing `agency run` commands work unchanged
- Jarvis is accessed via `agency amjad run` or programmatically
- No changes to existing runtime, skills, or tools
- Full backward compatibility maintained

---

### Q: Can I use Jarvis without customizing my profile?
**A:** Yes. Jarvis creates a sensible default profile on first run:
```bash
python scripts/deploy_amjad_jarvis.py
```
The default profile includes:
- Name: Amjad
- Role: Founder & Tech Lead
- Safe trust mode: `on-my-machine`
- All standard permissions enabled

You can customize it later without breaking anything.

---

### Q: How much does context injection cost (in tokens)?
**A:** Negligible—about 200-300 tokens per request.

Better: It's **cached** after first request using Claude's prompt caching, so:
- First request: +300 tokens
- All subsequent requests: ~0 additional tokens (cached)

---

### Q: Can agents see each other's outputs in workflows?
**A:** Currently, no—agents execute independently in parallel.

To implement cross-agent visibility:
1. Capture all results
2. Create a synthesis agent
3. Pass all results to synthesis agent
4. Return combined output

See `examples/amjad_workflows.py` for synthesis patterns.

---

### Q: How do I reset my profile to factory defaults?
**A:** Delete the profile file:
```bash
rm ~/.agency/amjad-profile.json
```

Next run will recreate it with defaults:
```bash
python scripts/deploy_amjad_jarvis.py
```

---

### Q: Can Jarvis work with other LLM providers (not just Claude)?
**A:** Currently, no—it's built on `AnthropicLLM`.

To add OpenAI, Gemini, etc.:
1. Create `XyzLLM` class matching `AnthropicLLM` interface
2. Update `MetaOrchestratorConfig.llm_client`
3. Override in initialization:
```python
j = init_jarvis(config=MetaOrchestratorConfig(llm_client=your_llm))
```

---

### Q: What happens if the LLM API is down?
**A:** Jarvis falls back to keyword-based routing:
1. Try LLM-based routing
2. Catch `LLMError`
3. Use top keyword match
4. Return result with rationale: "LLM unavailable, fell back to keyword match"

The system still works, just less intelligently.

---

### Q: Can I use Jarvis in a production deployment?
**A:** Yes, and it's recommended. The system includes:
- ✅ Comprehensive error handling
- ✅ Graceful fallbacks
- ✅ Performance optimization
- ✅ Session persistence
- ✅ Extensive test coverage
- ✅ Production-level logging

Deploy with trust mode `on-my-machine` for safe production use.

---

### Q: How do I give shell access only for specific agents?
**A:** Currently, permissions are global. To implement per-agent permissions:

1. Modify `_create_context_aware_executor()` in `amjad_jarvis_meta_orchestrator.py`
2. Add permission override in context injection:
```python
if skill.slug in ["devops-engineer", "security-engineer"]:
    context += "\n[PERMISSION OVERRIDE]\nShell: ENABLED"
```

---

### Q: Can Jarvis handle very long requests or large files?
**A:** Yes, but with token limits:
- Claude 3.5 Sonnet: 200K token context window
- Typical request: 2-5K tokens
- Large file: 10-50K tokens
- Safe maximum: 150K tokens (leaving buffer)

For files > 150K tokens:
1. Summarize the file first
2. Pass summary to Jarvis
3. Include link to full file for reference

---

### Q: How do I monitor Jarvis execution in production?
**A:** Enable verbose logging:
```python
j = init_jarvis(config=MetaOrchestratorConfig(verbose_logging=True))

# Or via CLI
agency amjad profile set verbose_logging true
```

This logs:
- Agent selection rationale
- Context injection details
- Execution timing
- Error traces

---

### Q: Can I schedule Jarvis tasks to run on a timer?
**A:** Use APScheduler or similar:
```python
from apscheduler.schedulers.background import BackgroundScheduler
from agency.amjad_jarvis_meta_orchestrator import jarvis

j = jarvis()

def scheduled_task():
    result = j.execute_unified_request("Daily security audit")
    print(result.text)

scheduler = BackgroundScheduler()
scheduler.add_job(scheduled_task, 'cron', hour=2, minute=0)  # 2 AM daily
scheduler.start()
```

---

### Q: How do I integrate Jarvis with Slack/Discord/etc?
**A:** Create a bot handler:
```python
from agency.amjad_jarvis_meta_orchestrator import jarvis
from slack_bolt import App

app = App(token=SLACK_BOT_TOKEN)
j = jarvis()

@app.message(".*")
def handle_message(message, say):
    request = message['text']
    result = j.execute_unified_request(request)
    say(result.text)

app.start(port=3000)
```

---

## 🔧 Troubleshooting Guide

### Problem: "ModuleNotFoundError: No module named 'agency.amjad_jarvis_meta_orchestrator'"

**Cause**: Package not installed properly

**Solution**:
```bash
# Reinstall the package
pip install -e .

# Verify installation
python -c "from agency.amjad_jarvis_meta_orchestrator import jarvis; print('✓')"
```

---

### Problem: "FileNotFoundError: ~/.agency/amjad-profile.json"

**Cause**: Profile not initialized

**Solution**:
```bash
# Initialize profile
python scripts/deploy_amjad_jarvis.py

# Or manually create
mkdir -p ~/.agency
echo '{"name":"Amjad"}' > ~/.agency/amjad-profile.json
```

---

### Problem: "PermissionError: [Errno 13] Permission denied"

**Cause**: Trust mode too restrictive or insufficient permissions

**Solution**:
```python
# Option 1: Increase trust
j.set_trust_mode("on-my-machine")

# Option 2: Enable specific permission
j.enable_shell(True)
j.enable_code_execution(True)

# Option 3: Via CLI
agency amjad trust on-my-machine
```

---

### Problem: "LLMError: API call failed"

**Cause**: Anthropic API error or credentials

**Solution**:
```bash
# Check API key
echo $ANTHROPIC_API_KEY

# If missing, set it
export ANTHROPIC_API_KEY="your-key-here"

# Test connectivity
python -c "from agency.llm import AnthropicLLM; print(AnthropicLLM().client.api_key[:10] + '...')"
```

---

### Problem: "No agent found for request"

**Cause**: Request doesn't match any skill keywords

**Solution**:
```python
# Option 1: Be more specific
# Bad: "Help me"
# Good: "Debug this Python error: IndexError"

# Option 2: Provide agent hint
result = j.execute_unified_request(
    "Do something",
    agent_slug="backend-architect"  # Explicit agent
)

# Option 3: Check available agents
from agency.skills import SkillRegistry
registry = SkillRegistry.discover()
for skill in registry.all():
    print(f"{skill.slug}: {skill.name}")
```

---

### Problem: "Tests failing with 'Mock' errors"

**Cause**: Environment not set up for testing

**Solution**:
```bash
# Install test dependencies
pip install pytest pytest-cov pytest-mock

# Run with full output
pytest tests/test_amjad_jarvis.py -vv -s

# Run specific test
pytest tests/test_amjad_jarvis.py::TestAmjadProfile::test_profile_creation -vv

# Check coverage
pytest tests/test_amjad_jarvis.py --cov=agency.amjad_jarvis_meta_orchestrator --cov-report=html
```

---

### Problem: "CLI command 'agency amjad' not recognized"

**Cause**: CLI not integrated into main agency CLI

**Solution**:
```bash
# Re-run integration script
python scripts/integrate_amjad_jarvis_cli.py

# Verify integration
agency amjad profile show

# If still not working, manually add to cli.py:
# 1. Add import: from .amjad_jarvis_cli import amjad_group
# 2. Add command: main.add_command(amjad_group.amjad)
```

---

### Problem: "Memory/context not persisting between sessions"

**Cause**: Different session IDs or memory store issue

**Solution**:
```python
# Use same session ID
session_id = "my_persistent_session"

# First request
r1 = j.execute_unified_request("Task 1", session_id=session_id)

# Second request (same session)
r2 = j.execute_unified_request("Task 2", session_id=session_id)
# r2 will have context from r1

# Check memory store
from agency.memory import MemoryStore
store = MemoryStore()
history = store.get_history(session_id)
print(history)
```

---

### Problem: "Slow execution (> 30 seconds)"

**Cause**: LLM API latency or large requests

**Solution**:
```python
# Option 1: Enable caching (after first request)
j.amjad.preferences["cache_enabled"] = True
j.amjad.save()

# Option 2: Use simpler requests
# Bad: Long rambling question with 20 files
# Good: Focused question with essential info

# Option 3: Use specific agent (skip routing delay)
result = j.execute_unified_request(
    "...",
    agent_slug="backend-architect"  # Skip planner
)

# Option 4: Profile execution
import time
start = time.time()
result = j.execute_unified_request("...")
print(f"Took {time.time() - start:.1f}s")
```

---

### Problem: "Agent behaving differently than expected"

**Cause**: Profile context not properly injected

**Solution**:
```python
# Option 1: Check profile
print(j.amjad)
print(json.dumps(j.amjad.__dict__, indent=2))

# Option 2: Verify context injection
result = j.execute_unified_request("Who am I?")
# Should mention your name, role, personality

# Option 3: Check agent selection
result = j.execute_unified_request("...")
print(f"Selected agent: {result.selected_agent}")
print(f"Rationale: {result.rationale}")

# Option 4: Update profile
j.amjad.personality_traits.append("More Direct")
j.amjad.save()
```

---

## 📊 Debugging Tools

### Check System Status
```bash
agency amjad status
```

Output shows:
- ✓ Profile loaded
- ✓ LLM configured
- ✓ Skills registry ready
- ✓ Trust mode: on-my-machine
- ✓ Permissions: shell ✓, web ✓, code ✓
- ✓ Memory store connected

### View Full Profile
```bash
agency amjad profile show
```

### Test Agent Routing
```python
from agency.planner import Planner
from agency.skills import SkillRegistry

registry = SkillRegistry.discover()
planner = Planner(registry)

result = planner.plan("Your request")
print(f"Selected: {result.skill.name}")
print(f"Rationale: {result.rationale}")
print(f"Candidates: {[s.name for s in result.candidates]}")
```

### Monitor Execution
```python
import logging
logging.basicConfig(level=logging.DEBUG)

result = j.execute_unified_request("...")
# All debug logs will print
```

### Profile Validation
```python
from agency.amjad_jarvis_meta_orchestrator import AmjadProfile

profile = AmjadProfile.load_or_create()
errors = profile.validate()  # Returns list of issues
if errors:
    for error in errors:
        print(f"✗ {error}")
else:
    print("✓ Profile is valid")
```

---

## 🚀 Performance Optimization

### Reduce LLM API Calls
```python
# Option 1: Use explicit agent (skip routing)
result = j.execute_unified_request(
    request, 
    agent_slug="backend-architect"  # No planner needed
)

# Option 2: Batch requests
# Bad: 10 separate requests
for i in range(10):
    j.execute_unified_request(f"Task {i}")

# Good: One batch request
result = j.execute_unified_request(
    "Execute these 10 tasks in parallel:\n1. ...\n2. ..."
)
```

### Enable Caching
```python
j.amjad.preferences["cache_enabled"] = True
j.amjad.save()

# First request: ~30s (full execution)
r1 = j.execute_unified_request("...")

# Subsequent requests: ~10s (cached prompt)
r2 = j.execute_unified_request("...")
r3 = j.execute_unified_request("...")
```

### Parallel Execution
```python
# Execute 4 agents in parallel instead of sequentially
results = j.execute_multi_agent_workflow(
    workflow_name="full_audit",
    primary_request="Full security & performance audit",
    parallel=True  # All agents run simultaneously
)
# Time: ~15s (instead of ~60s sequentially)
```

---

## 📚 Additional Resources

- **Quick Start**: `docs/QUICKSTART.md`
- **Architecture**: `docs/AMJAD_JARVIS_GUIDE.md`
- **API Reference**: `docs/REFERENCE.md`
- **Examples**: `examples/amjad_workflows.py`
- **Tests**: `tests/test_amjad_jarvis.py`

---

**Can't find your issue? Check the test suite for usage examples or create a GitHub issue.**
