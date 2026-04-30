"""Unit tests for individual JARVIS One subsystems.

Covers the 13 GOD-MODE methods plus the inspired-by reference modules.
All tests are hermetic — no network, no heavy deps, no side effects.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from agency.jarvis_one import build_default_interface


REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def jarvis():
    return build_default_interface(repo=REPO)


# ---------------------------------------------------------------- 13 methods
def test_ask_routes_through_persona(jarvis):
    ans = jarvis.ask("Draft a software consulting contract")
    assert ans.persona  # always picks a persona
    assert ans.response
    assert ans.decision is not None


def test_chat_appends_to_log_and_memory(jarvis):
    before = len(jarvis.chat_log())
    turn = jarvis.chat("שלום, איך אתה?")
    assert turn.assistant
    assert turn.persona
    assert len(jarvis.chat_log()) == before + 1


def test_create_emits_text_and_diagram(jarvis):
    bundle = jarvis.create("hello world", want=["text", "diagram"])
    kinds = {a.kind for a in bundle.artifacts}
    assert kinds == {"text", "diagram"}
    diag = bundle.by_kind("diagram")
    assert diag and diag.payload.startswith("<svg")


def test_orchestrate_splits_and_assigns(jarvis):
    res = jarvis.orchestrate(
        "1. Draft a contract\n2. Architect the system\n3. Build the marketing plan"
    )
    assert len(res.jobs) == 3
    assert all(j.result for j in res.jobs)
    assert res.summary.count("•") == 3


def test_plan_topo_orders_with_critical_path(jarvis):
    plan = jarvis.plan("ship v2")
    assert plan.makespan > 0
    assert plan.critical_path
    assert plan.tasks[0].start == 0


def test_collaborate_supports_all_patterns(jarvis):
    for pattern in ("peer-review", "brainstorm", "debate",
                    "sequential", "parallel"):
        t = jarvis.collaborate(pattern, f"topic-{pattern}")
        assert t.pattern == pattern
        assert t.contributions


def test_react_loop_terminates(jarvis):
    trace = jarvis.react("respond with hello", max_steps=3)
    assert trace.completed
    assert trace.steps


def test_route_returns_decision(jarvis):
    d = jarvis.route("design a flowchart")
    assert d.confidence >= 0


def test_remember_recall_roundtrip(jarvis, tmp_path, monkeypatch):
    note = "preferred deployment is GitHub Actions"
    jarvis.remember(note, tag="prefs")
    hits = jarvis.recall("deployment", top_k=3)
    assert any(note in h["text"] for h in hits)


def test_status_snapshot(jarvis):
    snap = jarvis.status()
    assert snap["skills"]["count"] > 0
    assert snap["personas"]["count"] == 6
    assert "subsystems" in snap


def test_personas_catalog(jarvis):
    cat = jarvis.personas()
    assert len(cat) == 6
    assert all(p["domain_count"] >= 20 for p in cat)


def test_gesture_dispatch(jarvis):
    out = jarvis.gesture(b"fake-frame")
    assert "gesture" in out and "intent" in out


def test_reload_returns_snapshot(jarvis):
    snap = jarvis.reload()
    assert snap["count"] > 0
    assert "jarvis" in snap["categories"]


# ---------------------------------------------------------------- inspired modules
def test_llm_router_falls_back_through_chain():
    from agency.jarvis_one.llm_router import LLMRouter
    r = LLMRouter()
    out = r.complete("hello")
    assert out["text"]
    assert r.total_cost() >= 0


def test_tracing_span_tree():
    from agency.jarvis_one.tracing import Tracer
    t = Tracer()
    with t.span("outer", phase="boot") as outer:
        outer.set(extra=1)
        with t.span("inner") as inner:
            inner.add_event("hit", n=2)
    spans = t.export()
    assert len(spans) == 2
    assert spans[1]["parent_id"] == spans[0]["span_id"]


def test_vector_store_collection_filtering(tmp_path):
    from agency.jarvis_one.vector_store import VectorStore
    vs = VectorStore(root=tmp_path)
    col = vs.collection("notes")
    col.add("learn rust", lang="rust")
    col.add("learn python", lang="python")
    hits = col.query("learn", where={"lang": "rust"})
    assert len(hits) == 1 and "rust" in hits[0]["text"]


def test_tool_registry_inferred_schema_and_call():
    from agency.jarvis_one.tool_registry import ToolRegistry
    reg = ToolRegistry()

    @reg.register("add", description="add two ints")
    def _add(a: int, b: int = 0) -> int:
        return a + b

    tools = reg.list_tools()
    assert tools[0]["name"] == "add"
    assert tools[0]["parameters"]["properties"]["a"]["type"] == "integer"
    assert reg.call("add", a=2, b=3) == 5


def test_evals_metrics():
    from agency.jarvis_one.evals import EvalCase, Evaluator
    ev = Evaluator()
    rep = ev.evaluate(EvalCase(
        question="what is rust", expected="rust is a systems language",
        actual="rust is a systems language",
    ))
    assert rep.scores["relevance"] > 0
    assert rep.scores["factuality_overlap"] > 0
    assert rep.overall > 0


def test_semantic_router_picks_best_route():
    from agency.jarvis_one.semantic_router import Route, SemanticRouter
    r = SemanticRouter([
        Route("greet", ("hello hi shalom",)),
        Route("billing", ("invoice payment receipt",)),
    ])
    assert r.route("invoice please").name == "billing"
    assert r.route("hello there").name == "greet"


def test_prompt_optimizer_picks_a_winner():
    from agency.jarvis_one.prompt_optimizer import (
        FewShotExample, PromptOptimizer,
    )

    def gen(prompt: str) -> str:
        return prompt[-30:]

    def score(actual: str, expected: str) -> float:
        return 1.0 if expected in actual else 0.0

    opt = PromptOptimizer(score_fn=score, gen_fn=gen)
    examples = [
        FewShotExample(input="2+2", output="4"),
        FewShotExample(input="1+1", output="2"),
        FewShotExample(input="3+3", output="6"),
        FewShotExample(input="5+5", output="10"),
    ]
    res = opt.optimize("Solve:", examples, k=2, max_candidates=4)
    assert res.best is not None


def test_sandbox_dry_run_by_default():
    from agency.jarvis_one.sandbox import Sandbox
    sb = Sandbox(dry_run=True)
    res = sb.run("python", "print('hi')")
    assert not res.executed
    assert res.error and "dry-run" in res.error


def test_tui_table_renders_rows():
    from agency.jarvis_one.tui import Table
    t = Table(columns=["a", "b"])
    t.add_row("1", "2")
    rendered = t.render()
    assert "a" in rendered and "1" in rendered


def test_multi_agent_dag_runs_to_end():
    from agency.jarvis_one.multi_agent_dag import MultiAgentGraph
    g = MultiAgentGraph()
    g.add_node("inc", lambda s: {**s, "n": s.get("n", 0) + 1})
    g.add_node("done", lambda s: {**s, "ok": True})
    g.set_entry_point("inc")
    g.add_conditional_edges("inc", lambda s: "done" if s["n"] >= 3 else "inc")
    g.add_edge("done", g.END)
    out = g.run({"n": 0})
    assert out["ok"] and out["n"] == 3
    assert out["__terminated__"]


def test_aios_bridge_ping_and_unknown_syscall():
    from agency.jarvis_one.aios_bridge import AIOSBridge, Syscall
    br = AIOSBridge()
    ok = br.call(Syscall("ping"))
    assert ok.ok and ok.value == "pong"
    err = br.call(Syscall("nope"))
    assert not err.ok and "unknown" in (err.error or "")


def test_channels_registry_and_mock_broadcast():
    from agency.jarvis_one.channels import ChannelRegistry
    reg = ChannelRegistry()
    listed = reg.list_channels()
    slugs = [c["slug"] for c in listed]
    for required in ("dingtalk-deap", "lark-openclaw", "weibo-openclaw",
                     "wecom-openclaw", "weixin-openclaw", "qqbot-openclaw"):
        assert required in slugs
    deliveries = reg.broadcast("hello world")
    assert all(d.delivered for d in deliveries)


def test_robotics_mock_walks():
    from agency.jarvis_one.robotics import HumanoidSimulator
    sim = HumanoidSimulator(simulator="mock")
    sim.reset()
    for _ in range(5):
        sim.step(dt=0.05)
    assert sim.pose().position[0] > 0  # moved forward
    assert "person" in {d["label"] for d in sim.detect_objects()}


def test_advisor_brain_crisis_safety_net():
    from agency.jarvis_one.advisor_brain import AdvisorBrain
    a = AdvisorBrain()
    out = a.respond("I'm thinking about suicide")
    assert out.crisis is True
    assert "988" in out.advisor_response or "1201" in out.advisor_response


def test_decision_engine_clarifies_when_unsure():
    from agency.jarvis_one.decision_engine import DecisionEngine
    from agency.skills import SkillRegistry, discover_repo_root
    reg = SkillRegistry.load(discover_repo_root())
    eng = DecisionEngine(reg, threshold=0.99)  # impossible threshold
    d = eng.route("שלום עולם")
    assert d.needs_clarification
    assert "לא בטוח" in d.clarification


def test_task_executor_drain_runs_in_order():
    from agency.jarvis_one.task_executor import TaskExecutor
    ex = TaskExecutor(workers=0)
    out: list[int] = []
    for i in range(3):
        ex.submit(lambda n=i: out.append(n))
    ex.drain()
    assert sorted(out) == [0, 1, 2]


def test_world_model_decay_removes_stale():
    import time
    from agency.jarvis_one.world_model import WorldModel
    w = WorldModel(half_life=0.001)
    w.upsert("ball", position=(1, 2, 3))
    time.sleep(0.05)
    w.decay()
    assert w.get("ball") is None


def test_context_manager_scopes_isolated():
    from agency.jarvis_one.context_manager import (
        get, scope, set_value, reset, snapshot,
    )
    reset()
    set_value("a", 1)
    with scope(b=2):
        assert get("a") == 1
        assert get("b") == 2
        assert "trace_id" in snapshot()
    assert get("b") is None


def test_hot_reload_detects_new_file(tmp_path):
    from agency.jarvis_one.hot_reload import HotReloadConfig, HotReloadWatcher
    seen: list[Path] = []
    w = HotReloadWatcher(HotReloadConfig(paths=[tmp_path]),
                         on_change=seen.append)
    # Prime so first diff is empty.
    list(w.diff())
    new_file = tmp_path / "x.md"
    new_file.write_text("hello", encoding="utf-8")
    diff = list(w.diff())
    assert new_file in diff
