"""Integration tests for the 13 JARVIS modules.

All tests use the in-memory / no-deps fallbacks where possible so they
run cleanly in CI without external services.
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from agency.aios_bridge import AIOSBridge
from agency.evals import (
    Contains,
    EvalCase,
    EvalSuite,
    ExactMatch,
    LatencyCheck,
    LengthCheck,
    LLMJudge,
    TokenOverlap,
)
from agency.llm_router import LLMProvider, LLMRouter, LLMRouterError
from agency.multi_agent import AgentPool, Graph, Pipeline
from agency.prompt_optimizer import (
    BootstrapFewShot,
    PromptCache,
    PromptModule,
    PromptSignature,
)
from agency.sandbox import SubprocessSandbox, get_sandbox
from agency.semantic_router import Route, SemanticRouter, default_router as default_semantic_router
from agency.streaming import (
    SSEEmitter,
    StreamBuffer,
    StreamEvent,
    async_stream_response,
    stream_response,
)
from agency.tool_registry import ToolRegistry, get_registry
from agency.tracing import Tracer, get_tracer, reset_tracer
from agency.tui import JarvisConsole, RichLoggingHandler
from agency.unified_bridge import UnifiedBridge
from agency.vector_store import (
    AgentMemory,
    TFIDFVectorStore,
    VectorEntry,
    get_vector_store,
)


# ---------------------------------------------------------------------------
# LLMRouter
# ---------------------------------------------------------------------------


class TestLLMRouter:
    def _echo(self, name: str, priority: int = 0, cost: float = 0.0) -> LLMProvider:
        return LLMProvider(
            name=name,
            model="echo",
            priority=priority,
            cost_per_1k_tokens=cost,
            backend="echo",
        )

    def test_echo_provider_completes(self):
        router = LLMRouter([self._echo("a")])
        out = router.complete("hello")
        assert "hello" in out
        assert router.last_provider is not None
        assert router.last_provider.name == "a"

    def test_fallback_chain(self):
        # primary "anthropic" with no key will fail; echo fallback wins
        bad = LLMProvider(name="bad", model="claude-x", priority=0, backend="anthropic", api_key_env="DOES_NOT_EXIST")
        good = self._echo("good", priority=1)
        router = LLMRouter([bad, good])
        out = router.complete("ping")
        assert "ping" in out
        assert router.last_provider.name == "good"
        assert router.failures.get("bad", 0) == 1

    def test_all_fail_raises(self):
        bad1 = LLMProvider(name="b1", model="x", priority=0, backend="anthropic", api_key_env="NOPE_1")
        bad2 = LLMProvider(name="b2", model="x", priority=1, backend="openai", api_key_env="NOPE_2")
        router = LLMRouter([bad1, bad2])
        with pytest.raises(LLMRouterError):
            router.complete("hi")

    def test_cheapest_provider(self):
        a = self._echo("a", priority=0, cost=0.005)
        b = self._echo("b", priority=1, cost=0.001)
        router = LLMRouter([a, b])
        assert router.cheapest_provider().name == "b"

    def test_cost_estimate(self):
        a = self._echo("a", priority=0, cost=0.002)
        router = LLMRouter([a])
        # 1000 prompt + 1000 completion = 2.0 * 0.002 = 0.004
        assert router.cost_estimate(1000, 1000) == pytest.approx(0.004)

    def test_priority_order(self):
        low = self._echo("low", priority=10)
        high = self._echo("high", priority=0)
        router = LLMRouter([low, high])
        out = router.complete("x")
        assert router.last_provider.name == "high"


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------


class TestTracing:
    def setup_method(self):
        reset_tracer()

    def test_start_end_span(self):
        t = Tracer(backend="log")
        s = t.start_span("op", {"k": "v"})
        assert s.status == "running"
        assert s.span_id in t.spans
        ended = t.end_span(s.span_id, "ok")
        assert ended is not None
        assert ended.status == "ok"
        assert ended.duration_ms is not None

    def test_context_manager(self):
        t = Tracer(backend="log")
        with t.span("ctx") as s:
            assert s.status == "running"
        finished = t.get_span(s.span_id)
        assert finished.status == "ok"
        assert finished.end_time is not None

    def test_context_manager_error(self):
        t = Tracer(backend="log")
        with pytest.raises(ValueError):
            with t.span("bad") as s:
                raise ValueError("boom")
        assert t.get_span(s.span_id).status == "error"

    def test_decorator(self):
        t = Tracer(backend="log")

        @t.trace("decorated")
        def add(a, b):
            return a + b

        assert add(2, 3) == 5
        names = [s.name for s in t.all_spans()]
        assert "decorated" in names

    def test_get_trace_returns_related_spans(self):
        t = Tracer(backend="log")
        with t.span("parent") as p:
            with t.span("child"):
                pass
        spans = t.get_trace(p.span_id)
        assert len(spans) == 2
        assert {s.name for s in spans} == {"parent", "child"}

    def test_singleton(self):
        t1 = get_tracer()
        t2 = get_tracer()
        assert t1 is t2


# ---------------------------------------------------------------------------
# VectorStore
# ---------------------------------------------------------------------------


class TestVectorStore:
    def test_store_and_search(self):
        m = get_vector_store("tfidf")
        m.store("python is a great programming language", agent_id="a1")
        m.store("the cat sat on the mat", agent_id="a1")
        m.store("python snakes are reptiles", agent_id="a1")
        results = m.search("python language", agent_id="a1", top_k=2)
        assert len(results) == 2
        assert "python" in results[0].content.lower()

    def test_delete(self):
        m = get_vector_store("tfidf")
        id1 = m.store("hello world")
        assert m.delete(id1) is True
        assert m.delete(id1) is False

    def test_ttl_expiry(self):
        m = get_vector_store("tfidf")
        m.store("transient", ttl=0.05)
        m.store("durable")
        time.sleep(0.1)
        expired = m.expire_old()
        assert expired == 1

    def test_tfidf_similarity_ranking(self):
        store = TFIDFVectorStore()
        store.add(VectorEntry(id="1", content="machine learning models"))
        store.add(VectorEntry(id="2", content="cooking recipes for dinner"))
        store.add(VectorEntry(id="3", content="machine vision and learning"))
        results = store.query("machine learning", top_k=3)
        # The two ML entries should rank above the cooking entry
        ids_in_order = [r[0].id for r in results]
        assert ids_in_order.index("2") > ids_in_order.index("1")
        assert ids_in_order.index("2") > ids_in_order.index("3")

    def test_agent_namespacing(self):
        m = get_vector_store("tfidf")
        m.store("alpha note", agent_id="A")
        m.store("alpha note", agent_id="B")
        a_results = m.search("alpha", agent_id="A", top_k=5)
        b_results = m.search("alpha", agent_id="B", top_k=5)
        assert len(a_results) == 1
        assert len(b_results) == 1
        assert all(e.agent_id == "A" for e in a_results)
        assert all(e.agent_id == "B" for e in b_results)

    def test_metadata_filter(self):
        store = TFIDFVectorStore()
        store.add(VectorEntry(id="1", content="alpha", metadata={"kind": "x"}))
        store.add(VectorEntry(id="2", content="alpha", metadata={"kind": "y"}))
        results = store.query("alpha", top_k=5, metadata_filter={"kind": "x"})
        assert len(results) == 1
        assert results[0][0].id == "1"


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def test_register_and_list(self):
        reg = ToolRegistry()

        @reg.tool()
        def add(a: int, b: int) -> int:
            """Add two integers."""
            return a + b

        assert "add" in reg.names()
        assert reg.get("add") is not None

    def test_execute(self):
        reg = ToolRegistry()

        @reg.tool()
        def mul(a: int, b: int) -> int:
            return a * b

        assert reg.execute("mul", a=3, b=4) == 12

    def test_unknown_raises(self):
        reg = ToolRegistry()
        with pytest.raises(KeyError):
            reg.execute("nope")

    def test_openai_schema_format(self):
        reg = ToolRegistry()

        @reg.tool(description="Greet the user")
        def greet(name: str, formal: bool = False) -> str:
            return name

        schemas = reg.openai_schema()
        assert len(schemas) == 1
        s = schemas[0]
        assert s["type"] == "function"
        assert s["function"]["name"] == "greet"
        params = s["function"]["parameters"]
        assert params["type"] == "object"
        assert "name" in params["properties"]
        assert params["properties"]["name"]["type"] == "string"
        assert params["properties"]["formal"]["type"] == "boolean"
        assert "name" in params["required"]
        assert "formal" not in params["required"]

    def test_type_introspection_optional(self):
        reg = ToolRegistry()

        @reg.tool()
        def search(query: str, top_k: int = 5, tags: list = None):
            return query

        tool = reg.get("search")
        names_to_types = {p.name: p.type for p in tool.parameters}
        assert names_to_types["query"] == "string"
        assert names_to_types["top_k"] == "integer"
        assert names_to_types["tags"] == "array"

    def test_singleton_registry(self):
        a = get_registry()
        b = get_registry()
        assert a is b


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


class TestStreaming:
    def test_sse_format(self):
        e = StreamEvent(event_type="token", data="hi")
        wire = e.to_sse()
        assert "event: token" in wire
        assert "data: hi" in wire
        assert wire.endswith("\n\n")

    def test_buffer_put_get(self):
        buf = StreamBuffer()
        buf.put("a")
        buf.put("b")
        buf.close()
        items = list(buf)
        assert items == ["a", "b"]

    def test_done_event(self):
        wire = SSEEmitter.emit_done()
        assert "event: done" in wire
        assert "[DONE]" in wire

    def test_stream_response_wraps_generator(self):
        def gen():
            yield "hello"
            yield "world"

        chunks = list(stream_response(gen()))
        assert len(chunks) == 3  # 2 tokens + done
        assert "hello" in chunks[0]
        assert "world" in chunks[1]
        assert "[DONE]" in chunks[2]

    def test_async_stream_response(self):
        async def agen():
            yield "x"
            yield "y"

        async def collect():
            out = []
            async for chunk in async_stream_response(agen()):
                out.append(chunk)
            return out

        result = asyncio.run(collect())
        assert len(result) == 3
        assert "x" in result[0]
        assert "y" in result[1]


# ---------------------------------------------------------------------------
# Evals
# ---------------------------------------------------------------------------


class TestEvals:
    def test_exact_match(self):
        m = ExactMatch()
        c = EvalCase(input="x", expected_output="hello", actual_output="hello")
        assert m.score(c) == 1.0
        c2 = EvalCase(input="x", expected_output="hello", actual_output="goodbye")
        assert m.score(c2) == 0.0

    def test_contains(self):
        m = Contains()
        c = EvalCase(input="x", expected_output="alpha", actual_output="this is alpha bravo")
        assert m.score(c) == 1.0

    def test_length_check(self):
        m = LengthCheck(min_chars=5, max_chars=10)
        ok = EvalCase(input="x", actual_output="abcdef")
        bad = EvalCase(input="x", actual_output="abc")
        assert m.score(ok) == 1.0
        assert m.score(bad) == 0.0

    def test_token_overlap(self):
        m = TokenOverlap()
        c = EvalCase(input="x", expected_output="the cat sat", actual_output="cat sat here")
        s = m.score(c)
        # tokens: {the, cat, sat} & {cat, sat, here} = 2 ; union = 4 -> 0.5
        assert s == pytest.approx(0.5, abs=0.01)

    def test_full_suite_run(self):
        suite = EvalSuite(threshold=0.5)
        suite.add_metric(ExactMatch())
        suite.add_metric(Contains())
        cases = [
            EvalCase(input="a", expected_output="hello", actual_output="hello"),
            EvalCase(input="b", expected_output="world", actual_output="world!"),
        ]
        report = suite.run(cases)
        assert report.overall_pass
        assert "exact_match" in report.scores
        assert "contains" in report.scores
        assert report.summary["case_count"] == 2

    def test_llm_judge_heuristic(self):
        m = LLMJudge()
        c = EvalCase(input="q", expected_output="alpha bravo", actual_output="alpha bravo")
        assert m.score(c) == pytest.approx(1.0)

    def test_latency_check(self):
        m = LatencyCheck(max_ms=100)
        ok = EvalCase(input="x", actual_output="y", latency_ms=50.0)
        bad = EvalCase(input="x", actual_output="y", latency_ms=200.0)
        assert m.score(ok) == 1.0
        assert m.score(bad) == 0.0


# ---------------------------------------------------------------------------
# SemanticRouter
# ---------------------------------------------------------------------------


class TestSemanticRouter:
    def test_add_route(self):
        r = SemanticRouter()
        r.add_route(Route(name="weather", utterances=["what's the weather", "is it raining"]))
        assert len(r.routes) == 1

    def test_route_query(self):
        r = SemanticRouter()
        r.add_route(Route(name="weather", utterances=["what's the weather today", "forecast for tomorrow"]))
        r.add_route(Route(name="sports", utterances=["who won the game", "score of the match"]))
        route, conf = r.route("what's the weather like")
        assert route.name == "weather"
        assert conf > 0

    def test_confidence_threshold(self):
        r = SemanticRouter()
        r.add_route(Route(name="x", utterances=["alpha bravo"]))
        _, conf_match = r.route("alpha bravo")
        _, conf_off = r.route("zebra elephant")
        assert conf_match > conf_off

    def test_jarvis_routes_match(self):
        r = default_semantic_router()
        assert r.route_name("write a python function for me") == "code"
        assert r.route_name("solve this equation") == "math"

    def test_route_name_helper(self):
        r = default_semantic_router()
        name = r.route_name("research papers about ML")
        assert isinstance(name, str)


# ---------------------------------------------------------------------------
# PromptOptimizer
# ---------------------------------------------------------------------------


class TestPromptOptimizer:
    def test_compile_signature(self):
        sig = PromptSignature(
            input_fields=["question"],
            output_fields=["answer"],
            instructions="Answer concisely.",
        )
        m = PromptModule(sig)
        compiled = m.compile()
        assert "Answer concisely" in compiled
        assert "question" in compiled
        assert "answer" in compiled

    def test_call_substitutes_inputs(self):
        sig = PromptSignature(input_fields=["q"], output_fields=["a"])
        m = PromptModule(sig)
        m.compile()
        out = m({"q": "what is 2+2?"})
        assert "what is 2+2?" in out

    def test_cache_hits(self):
        cache = PromptCache()
        sig = PromptSignature(input_fields=["x"], output_fields=["y"])
        m = PromptModule(sig, cache=cache)
        m.compile([{"x": "1", "y": "1"}])
        assert len(cache) == 1
        m.compile([{"x": "1", "y": "1"}])  # same → cache hit
        assert len(cache) == 1

    def test_bootstrap_fewshot(self):
        sig = PromptSignature(input_fields=["q"], output_fields=["a"])
        m = PromptModule(sig)
        train = [
            {"q": "alpha", "a": "1"},
            {"q": "bravo", "a": "2"},
            {"q": "charlie", "a": "3"},
            {"q": "delta", "a": "4"},
        ]
        opt = BootstrapFewShot(max_demos=2, seed=42)
        # Score = number of unique a-values in selected demos
        def metric(mod, ex):
            return float(len({e["a"] for e in mod.examples}))

        opt.optimize(m, train, metric, iterations=5)
        assert 1 <= len(m.examples) <= 2

    def test_add_example(self):
        sig = PromptSignature(input_fields=["q"], output_fields=["a"])
        m = PromptModule(sig)
        m.add_example({"q": "x", "a": "y"})
        compiled = m.compile()
        assert "Example 1" in compiled


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------


class TestSandbox:
    def test_python_exec_success(self):
        sb = SubprocessSandbox()
        r = sb.execute_python("print('hello')")
        assert r.success
        assert "hello" in r.stdout
        assert r.exit_code == 0

    def test_python_exec_error(self):
        sb = SubprocessSandbox()
        r = sb.execute_python("raise SystemExit(2)")
        assert not r.success
        assert r.exit_code == 2

    def test_bash_or_skip(self):
        sb = get_sandbox("subprocess")
        r = sb.execute_bash("echo hi")
        # Skip if no shell is available on this host
        if r.exit_code == 127 and "no shell" in r.stderr.lower():
            pytest.skip("no shell available")
        assert r.success
        assert "hi" in r.stdout

    def test_timeout(self):
        sb = SubprocessSandbox()
        r = sb.execute_python("import time; time.sleep(5)", timeout=0.5)
        assert r.timed_out
        assert not r.success

    def test_env_sanitization(self):
        sb = SubprocessSandbox()
        os.environ["FAKE_API_KEY"] = "should-not-leak"
        try:
            r = sb.execute_python(
                "import os; print('LEAK' if os.environ.get('FAKE_API_KEY') else 'CLEAN')"
            )
            assert "CLEAN" in r.stdout
        finally:
            os.environ.pop("FAKE_API_KEY", None)


# ---------------------------------------------------------------------------
# TUI
# ---------------------------------------------------------------------------


class TestTUI:
    def test_console_methods_dont_raise(self):
        c = JarvisConsole(force_plain=True)
        c.success("done")
        c.error("oops")
        c.warn("careful")
        c.info("fyi")
        with c.thinking("loading"):
            pass

    def test_status_table_plain(self):
        c = JarvisConsole(force_plain=True)
        rendered = c.agent_status_table(
            [
                {"name": "a", "status": "ok", "queue": 0, "last": "now"},
                {"name": "b", "status": "busy", "queue": 3, "last": "1s ago"},
            ]
        )
        assert "name" in rendered
        assert "a" in rendered
        assert "b" in rendered

    def test_print_plan_plain(self):
        c = JarvisConsole(force_plain=True)
        c.print_plan(["step 1", "step 2", "step 3"])  # no exception

    def test_logging_handler(self):
        import logging

        c = JarvisConsole(force_plain=True)
        h = RichLoggingHandler(c)
        rec = logging.LogRecord("t", logging.INFO, "f", 1, "hello", None, None)
        h.emit(rec)  # no exception


# ---------------------------------------------------------------------------
# MultiAgent
# ---------------------------------------------------------------------------


class TestMultiAgent:
    def test_pipeline(self):
        p = Pipeline()
        p.add_step("upper", lambda x: x.upper())
        p.add_step("excl", lambda x: x + "!")
        out = p.run("hi")
        assert out["output"] == "HI!"
        assert out["upper"] == "HI"

    def test_pipeline_failure(self):
        p = Pipeline()
        p.add_step("ok", lambda x: x)

        def bad(x):
            raise ValueError("nope")

        p.add_step("bad", bad)
        out = p.run("x")
        assert "_failed_at" in out
        assert out["_failed_at"] == "bad"

    def test_graph_dag_parallel(self):
        g = Graph(max_workers=4)
        g.add_node("a", lambda input: input + "_a")
        g.add_node("b", lambda input: input + "_b")
        g.add_node("c", lambda inputs: f"{inputs['a']}+{inputs['b']}", dependencies=["a", "b"])
        out = g.run("seed")
        assert out["a"] == "seed_a"
        assert out["b"] == "seed_b"
        assert out["c"] == "seed_a+seed_b"
        assert "c" in out["_completed"]

    def test_graph_skips_on_failure(self):
        g = Graph()

        def bad(x):
            raise RuntimeError("x")

        g.add_node("a", bad)
        g.add_node("b", lambda inputs: inputs, dependencies=["a"])
        out = g.run("seed")
        assert "a" in out["_failed"]
        # b skipped because a failed
        assert isinstance(out.get("b"), dict) and "skipped" in out["b"]

    def test_pool_parallel_dispatch(self):
        pool = AgentPool(max_workers=4)
        pool.add_agent("a", lambda t: f"a:{t}")
        pool.add_agent("b", lambda t: f"b:{t}")
        results = pool.dispatch_all(["1", "2", "3", "4"])
        assert len(results) == 4
        # round-robin: first hits agent a, second b, etc.
        assert any(r.startswith("a:") for r in results)
        assert any(r.startswith("b:") for r in results)


# ---------------------------------------------------------------------------
# UnifiedBridge
# ---------------------------------------------------------------------------


class TestUnifiedBridge:
    def test_process_returns_route_and_memory(self):
        ub = UnifiedBridge()
        out = ub.process("write me a python function to sort a list")
        assert "route" in out
        assert "confidence" in out
        assert "memory" in out
        assert "latency_ms" in out

    def test_status_report(self):
        ub = UnifiedBridge()
        s = ub.status()
        assert "llm_router" in s
        assert "semantic_router" in s
        assert "memory" in s
        assert "tools" in s

    def test_process_stores_memory(self):
        ub = UnifiedBridge()
        before = len(ub.memory)
        ub.process("alpha bravo charlie")
        assert len(ub.memory) >= before + 1

    def test_routing_dispatch(self):
        ub = UnifiedBridge()
        out = ub.process("solve this differential equation x'' + x = 0")
        assert out["route"] in {"math", "analysis", "research"}

    def test_process_with_tool_match(self):
        ub = UnifiedBridge()

        # Register a tool whose name matches a route name so the bridge
        # invokes it during pipeline step 3.
        @ub.tools.tool(name="conversation")
        def conversation_tool(request: str) -> str:
            return f"chat:{request[:20]}"

        out = ub.process("good morning, how are you?")
        if out["route"] == "conversation":
            assert out["tool_result"] is not None
            assert "chat:" in out["tool_result"]


# ---------------------------------------------------------------------------
# AIOSBridge
# ---------------------------------------------------------------------------


class TestAIOSBridge:
    def test_register_and_list(self):
        b = AIOSBridge(workers=1)
        try:
            b.register_agent("echo", "echoes input", lambda task: f"echo:{task}")
            agents = b.list_agents()
            assert any(a["name"] == "echo" for a in agents)
        finally:
            b.shutdown()

    def test_submit_and_get_result(self):
        b = AIOSBridge(workers=1)
        try:
            b.register_agent("echo", "echo", lambda task: f"got:{task}")
            tid = b.submit_task("hello", priority=1)
            # Wait for completion
            deadline = time.time() + 3.0
            res = {}
            while time.time() < deadline:
                res = b.get_result(tid)
                if res.get("status") == "ok":
                    break
                time.sleep(0.05)
            assert res.get("status") == "ok"
            assert res.get("result") == "got:hello"
        finally:
            b.shutdown()

    def test_no_agent_returns_error(self):
        b = AIOSBridge(workers=1)
        try:
            tid = b.submit_task("orphan task", priority=5)
            deadline = time.time() + 3.0
            res = {}
            while time.time() < deadline:
                res = b.get_result(tid)
                if res.get("status") in {"ok", "error"}:
                    break
                time.sleep(0.05)
            assert res.get("status") == "error"
        finally:
            b.shutdown()

    def test_status(self):
        b = AIOSBridge(workers=1)
        try:
            b.register_agent("e", "e", lambda t: t)
            s = b.status()
            assert "agents" in s
            assert s["agents"] == 1
            assert "workers" in s
        finally:
            b.shutdown()
