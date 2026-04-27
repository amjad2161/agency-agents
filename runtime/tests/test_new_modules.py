"""Tests for the seven new capability modules + the four CLI commands.

Each module has its own test class; the CLI commands have their own
class that uses Click's CliRunner. The expert-domain-routing class at
the end exercises the integration between SelfLearnerEngine,
CapabilityEvolver, and ContextManager — that's the path the runtime
takes when it picks which domain to specialize on a given request.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from agency.autonomous_loop import AutonomousLoop, LoopStatus
from agency.capability_evolver import (
    CapabilityEvolver,
    DomainProfile,
    _compute_proficiency,
)
from agency.context_manager import ContextEntry, ContextManager
from agency.knowledge_expansion import (
    KnowledgeChunk,
    KnowledgeExpansion,
    _extract_tags,
)
from agency.meta_reasoner import (
    MetaReasoningEngine,
    ReasoningStep,
)
from agency.multimodal import (
    ModalityType,
    MultimodalInput,
    MultimodalProcessor,
)
from agency.self_learner_engine import (
    Lesson,
    SelfLearnerEngine,
)


# ---------------------------------------------------------------------------
# SelfLearnerEngine
# ---------------------------------------------------------------------------


class TestSelfLearnerEngine:
    def test_record_writes_jsonl_row(self, tmp_path: Path):
        eng = SelfLearnerEngine(tmp_path / "lessons.jsonl")
        l = eng.record_interaction(
            context="ctx1", outcome="success",
            insight="x is faster than y", confidence=0.9,
            applies_to=("engineering",),
        )
        assert l.confidence == 0.9
        assert l.applies_to == ("engineering",)
        body = (tmp_path / "lessons.jsonl").read_text(encoding="utf-8")
        assert body.count("\n") == 1
        parsed = json.loads(body)
        assert parsed["insight"] == "x is faster than y"
        assert parsed["applies_to"] == ["engineering"]

    def test_load_round_trip(self, tmp_path: Path):
        eng = SelfLearnerEngine(tmp_path / "lessons.jsonl")
        eng.record_interaction(context="a", outcome="success", insight="ins-a",
                               confidence=0.5)
        eng.record_interaction(context="b", outcome="failure", insight="ins-b",
                               confidence=0.2)
        # Force fresh-from-disk load.
        eng2 = SelfLearnerEngine(tmp_path / "lessons.jsonl")
        loaded = eng2.load_lessons()
        assert len(loaded) == 2
        assert {l.insight for l in loaded} == {"ins-a", "ins-b"}

    def test_record_rejects_invalid_outcome(self, tmp_path: Path):
        eng = SelfLearnerEngine(tmp_path / "lessons.jsonl")
        with pytest.raises(ValueError, match="outcome"):
            eng.record_interaction(
                context="c", outcome="weird", insight="x", confidence=0.5
            )

    def test_record_rejects_invalid_confidence(self, tmp_path: Path):
        eng = SelfLearnerEngine(tmp_path / "lessons.jsonl")
        with pytest.raises(ValueError, match="confidence"):
            eng.record_interaction(
                context="c", outcome="success", insight="x", confidence=2.0
            )

    def test_top_insights_ranks_by_confidence_and_recency(self, tmp_path: Path):
        eng = SelfLearnerEngine(tmp_path / "lessons.jsonl")
        # Old high confidence vs new low confidence — recency × conf wins.
        old = Lesson(timestamp=time.time() - 86400 * 100,
                     context="o", outcome="success", insight="old",
                     confidence=0.95, applies_to=("d",))
        new = Lesson(timestamp=time.time(),
                     context="n", outcome="success", insight="new",
                     confidence=0.4, applies_to=("d",))
        eng.save_lessons([old, new])
        top = eng.top_insights(2, domain="d")
        assert top[0].insight in {"new", "old"}
        # Compute expected order programmatically.
        scores = sorted(
            [(l.confidence * 0.5 ** (((time.time() - l.timestamp) / 86400) / 30.0), l)
             for l in [old, new]],
            key=lambda x: x[0], reverse=True,
        )
        assert top[0].insight == scores[0][1].insight

    def test_top_insights_filters_by_domain(self, tmp_path: Path):
        eng = SelfLearnerEngine(tmp_path / "lessons.jsonl")
        eng.record_interaction(context="c", outcome="success", insight="A",
                               confidence=0.9, applies_to=("alpha",))
        eng.record_interaction(context="c", outcome="success", insight="B",
                               confidence=0.9, applies_to=("beta",))
        out = eng.top_insights(5, domain="alpha")
        assert {l.insight for l in out} == {"A"}

    def test_apply_corrections_returns_unique_high_confidence(self, tmp_path: Path):
        eng = SelfLearnerEngine(tmp_path / "lessons.jsonl")
        eng.record_interaction(
            context="c", outcome="success", insight="low",
            confidence=0.3, applies_to=("d",),
            routing_correction="should-not-show",
        )
        eng.record_interaction(
            context="c", outcome="success", insight="hi",
            confidence=0.9, applies_to=("d",),
            routing_correction="prefer route X",
        )
        eng.record_interaction(
            context="c", outcome="success", insight="hi-dup",
            confidence=0.95, applies_to=("d",),
            routing_correction="prefer route X",  # dup
        )
        out = eng.apply_corrections("d")
        assert out == ["prefer route X"]

    def test_load_skips_malformed_rows(self, tmp_path: Path):
        p = tmp_path / "lessons.jsonl"
        p.write_text(
            '{"timestamp":1.0,"context":"a","outcome":"success",'
            '"insight":"ok","confidence":0.5}\n'
            'this is not json\n',
            encoding="utf-8",
        )
        eng = SelfLearnerEngine(p)
        out = eng.load_lessons()
        assert len(out) == 1
        assert out[0].insight == "ok"


# ---------------------------------------------------------------------------
# MetaReasoningEngine
# ---------------------------------------------------------------------------


class TestMetaReasoningEngine:
    def test_default_executor_terminates(self):
        eng = MetaReasoningEngine()
        steps = eng.reason("solve thing", max_iterations=3)
        assert len(steps) == 3
        assert all(isinstance(s, ReasoningStep) for s in steps)

    def test_high_confidence_breaks_early(self):
        def fast_executor(thought, *, history):
            return ("act", "great obs", 0.99)
        eng = MetaReasoningEngine(fast_executor, confidence_threshold=0.85)
        steps = eng.reason("g", max_iterations=10)
        assert len(steps) == 1

    def test_avg_confidence_matches(self):
        def stub(t, *, history):
            return ("a", "o", 0.5)
        eng = MetaReasoningEngine(stub, confidence_threshold=1.1)
        eng.reason("g", max_iterations=4)
        assert eng.avg_confidence() == pytest.approx(0.5)

    def test_critique_flags_low_confidence_steps(self):
        def stub(t, *, history):
            return ("a", "o", 0.1)
        eng = MetaReasoningEngine(stub)
        steps = eng.reason("g", max_iterations=2)
        crit = eng.critique(steps)
        assert "low-confidence" in crit
        assert "below" in crit

    def test_critique_flags_action_loop(self):
        def stub(t, *, history):
            return ("same", "o", 0.5)
        eng = MetaReasoningEngine(stub, confidence_threshold=1.1)
        steps = eng.reason("g", max_iterations=4)
        crit = eng.critique(steps)
        assert "repeat" in crit

    def test_refine_appends_one_step(self):
        def stub(t, *, history):
            return ("a", "o", 0.4)
        eng = MetaReasoningEngine(stub, confidence_threshold=1.1)
        steps = eng.reason("g", max_iterations=2)
        refined = eng.refine(steps, critique="weak")
        assert len(refined) == len(steps) + 1
        assert "refine" in refined[-1].thought

    def test_invalid_max_iterations(self):
        eng = MetaReasoningEngine()
        with pytest.raises(ValueError):
            eng.reason("g", max_iterations=0)


# ---------------------------------------------------------------------------
# CapabilityEvolver
# ---------------------------------------------------------------------------


class TestCapabilityEvolver:
    def test_record_creates_profile(self, tmp_path: Path):
        ev = CapabilityEvolver(tmp_path / "cap.json")
        p = ev.record_outcome("eng", success=True, confidence=0.8)
        assert p.slug == "eng"
        assert p.total_requests == 1
        assert p.successful == 1
        assert p.failed == 0

    def test_record_persists_across_instances(self, tmp_path: Path):
        path = tmp_path / "cap.json"
        CapabilityEvolver(path).record_outcome("eng", success=True, confidence=0.5)
        ev2 = CapabilityEvolver(path)
        prof = ev2.get("eng")
        assert prof is not None
        assert prof.total_requests == 1

    def test_running_average_confidence(self, tmp_path: Path):
        ev = CapabilityEvolver(tmp_path / "cap.json")
        ev.record_outcome("d", success=True, confidence=1.0)
        ev.record_outcome("d", success=True, confidence=0.0)
        prof = ev.get("d")
        assert prof.avg_confidence == pytest.approx(0.5)

    def test_weakest_excludes_zero_request_domains(self, tmp_path: Path):
        ev = CapabilityEvolver(tmp_path / "cap.json")
        ev.record_outcome("a", success=True, confidence=0.9)
        ev.record_outcome("b", success=False, confidence=0.1)
        weakest = ev.weakest_domains(5)
        assert weakest[0].slug == "b"
        assert {p.slug for p in weakest} == {"a", "b"}

    def test_growth_report_summary(self, tmp_path: Path):
        ev = CapabilityEvolver(tmp_path / "cap.json")
        for _ in range(3):
            ev.record_outcome("a", success=True, confidence=0.9)
        ev.record_outcome("b", success=False, confidence=0.2)
        rep = ev.growth_report()
        assert rep["domains_tracked"] == 2
        assert rep["total_requests"] == 4
        assert "a" in rep["strongest"]
        assert "b" in rep["weakest"]

    def test_proficiency_formula(self):
        p = DomainProfile(slug="x", total_requests=10, successful=8, failed=2,
                          avg_confidence=0.5)
        score = _compute_proficiency(p)
        # 0.6*0.8 + 0.3*0.5 + 0.1*(10/50) = 0.48 + 0.15 + 0.02 = 0.65
        assert score == pytest.approx(0.65)


# ---------------------------------------------------------------------------
# ContextManager
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_store_and_recall(self):
        cm = ContextManager()
        cm.store("k", "v", domain="d")
        assert cm.recall("k", domain="d") == "v"

    def test_domains_are_isolated(self):
        cm = ContextManager()
        cm.store("k", "alpha", domain="A")
        cm.store("k", "beta", domain="B")
        assert cm.recall("k", domain="A") == "alpha"
        assert cm.recall("k", domain="B") == "beta"

    def test_ttl_expiry_evicts(self, monkeypatch):
        cm = ContextManager()
        cm.store("k", "v", domain="d", ttl_seconds=1)
        # Advance "time" past TTL.
        future = time.time() + 5
        monkeypatch.setattr("agency.context_manager.time.time", lambda: future)
        assert cm.recall("k", domain="d") is None
        # Key should be evicted.
        assert "k" not in cm.dump_domain("d")

    def test_ttl_zero_means_never(self, monkeypatch):
        cm = ContextManager()
        cm.store("k", "v", domain="d", ttl_seconds=0)
        future = time.time() + 10**9
        monkeypatch.setattr("agency.context_manager.time.time", lambda: future)
        assert cm.recall("k", domain="d") == "v"

    def test_recall_recent_returns_newest_first(self):
        cm = ContextManager()
        cm.store("a", 1, domain="d")
        cm.store("b", 2, domain="d")
        cm.store("c", 3, domain="d")
        recent = cm.recall_recent(domain="d", n=2)
        assert [e.key for e in recent] == ["c", "b"]

    def test_overwrite_promotes_recency(self):
        cm = ContextManager()
        cm.store("a", 1, domain="d")
        cm.store("b", 2, domain="d")
        cm.store("a", 99, domain="d")  # rewrite a
        recent = cm.recall_recent(domain="d", n=2)
        assert [e.key for e in recent] == ["a", "b"]
        assert recent[0].value == 99

    def test_forget_returns_status(self):
        cm = ContextManager()
        cm.store("k", "v", domain="d")
        assert cm.forget("k", domain="d") is True
        assert cm.forget("k", domain="d") is False


# ---------------------------------------------------------------------------
# AutonomousLoop
# ---------------------------------------------------------------------------


class TestAutonomousLoop:
    def test_runs_until_done(self):
        loop = AutonomousLoop()
        calls = {"n": 0}

        def exec_fn(payload, i):
            calls["n"] = i
            return (f"out-{i}", i >= 3)

        loop.register_executor("count", exec_fn)
        result = loop.run({"executor": "count", "payload": None}, max_iterations=10)
        assert result.status is LoopStatus.DONE
        assert result.iterations == 3
        assert result.last_output == "out-3"

    def test_hits_max_iter(self):
        loop = AutonomousLoop()
        loop.register_executor("never", lambda payload, i: (f"x{i}", False))
        result = loop.run(
            {"executor": "never"}, max_iterations=4
        )
        assert result.status is LoopStatus.MAX_ITER
        assert result.iterations == 4

    def test_stop_interrupts(self):
        loop = AutonomousLoop()

        def slow(payload, i):
            return (f"x{i}", False)

        loop.register_executor("slow", slow)

        # Pre-set stop so the very first iteration terminates.
        loop.stop()
        result = loop.run({"executor": "slow"}, max_iterations=10)
        assert result.status is LoopStatus.INTERRUPTED


# ---------------------------------------------------------------------------
# KnowledgeExpansion
# ---------------------------------------------------------------------------


class TestKnowledgeExpansion:
    def test_ingest_text_persists(self, tmp_path: Path):
        ke = KnowledgeExpansion(tmp_path / "k.jsonl")
        chunk = ke.ingest_text("hello #world bigger doc",
                               domain="d", source="src1")
        assert chunk.id
        assert "world" in chunk.tags
        # Reload.
        ke2 = KnowledgeExpansion(tmp_path / "k.jsonl")
        all_chunks = ke2._load(refresh=True)
        assert len(all_chunks) == 1
        assert all_chunks[0].content.startswith("hello")

    def test_search_ranks_by_overlap(self, tmp_path: Path):
        ke = KnowledgeExpansion(tmp_path / "k.jsonl")
        ke.ingest_text("the quick brown fox jumps", domain="d", source="a")
        ke.ingest_text("nothing relevant here at all",
                       domain="d", source="b")
        ke.ingest_text("brown fox brown fox brown fox",
                       domain="d", source="c")
        hits = ke.search("brown fox", domain="d", top_k=3)
        assert len(hits) == 2
        assert hits[0].source == "c"

    def test_search_empty_query_returns_empty(self, tmp_path: Path):
        ke = KnowledgeExpansion(tmp_path / "k.jsonl")
        ke.ingest_text("anything", domain="d")
        assert ke.search("   ") == []
        assert ke.search("aa") == []  # term len 2 → filtered


# ---------------------------------------------------------------------------
# MultimodalProcessor
# ---------------------------------------------------------------------------


class TestMultimodalProcessor:
    def test_from_text(self):
        inp = MultimodalProcessor.from_text("hello")
        assert inp.modality is ModalityType.TEXT
        assert inp.payload == "hello"

    def test_from_text_rejects_non_str(self):
        with pytest.raises(TypeError):
            MultimodalProcessor.from_text(123)  # type: ignore[arg-type]

    def test_from_file_text(self, tmp_path: Path):
        p = tmp_path / "f.txt"
        p.write_text("body")
        inp = MultimodalProcessor.from_file(p)
        assert inp.modality is ModalityType.TEXT
        assert inp.payload == "body"

    def test_from_file_image_keeps_bytes(self, tmp_path: Path):
        p = tmp_path / "f.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10)
        inp = MultimodalProcessor.from_file(p)
        assert inp.modality is ModalityType.IMAGE
        assert isinstance(inp.payload, (bytes, bytearray))

    def test_from_base64_text(self):
        import base64 as b64
        encoded = b64.b64encode(b"hi").decode("ascii")
        inp = MultimodalProcessor.from_base64(encoded, "text/plain")
        assert inp.modality is ModalityType.TEXT
        assert inp.payload == "hi"

    def test_from_base64_invalid_raises(self):
        with pytest.raises(ValueError):
            MultimodalProcessor.from_base64("not!base64!", "text/plain")

    def test_from_structured_serializes(self):
        inp = MultimodalProcessor.from_structured({"a": 1, "b": [1, 2]})
        assert inp.modality is ModalityType.STRUCTURED
        loaded = json.loads(inp.payload)
        assert loaded == {"a": 1, "b": [1, 2]}

    def test_extract_text_from_blob(self):
        inp = MultimodalInput(
            modality=ModalityType.IMAGE,
            payload=b"\xff" * 12,
            mime_type="image/png",
        )
        out = MultimodalProcessor.extract_text(inp)
        assert "image" in out and "blob" in out

    def test_combine_joins_text(self):
        a = MultimodalProcessor.from_text("alpha")
        b = MultimodalProcessor.from_text("beta")
        out = MultimodalProcessor.combine([a, b])
        assert out.modality is ModalityType.TEXT
        assert "alpha" in out.payload and "beta" in out.payload

    def test_combine_empty_raises(self):
        with pytest.raises(ValueError):
            MultimodalProcessor.combine([])


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


class TestCLICommands:
    def _runner(self):
        from click.testing import CliRunner
        return CliRunner()

    def test_learn_records(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("AGENCY_LESSONS_JSONL", str(tmp_path / "l.jsonl"))
        from agency.cli import main
        result = self._runner().invoke(
            main, ["learn", "x is fast", "--domain", "eng",
                   "--confidence", "0.8"],
        )
        assert result.exit_code == 0, result.output
        assert "recorded lesson" in result.output

    def test_learn_invalid_outcome(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("AGENCY_LESSONS_JSONL", str(tmp_path / "l.jsonl"))
        from agency.cli import main
        result = self._runner().invoke(
            main, ["learn", "x", "--outcome", "weird"],
        )
        assert result.exit_code != 0

    def test_reason_offline_runs(self, tmp_path: Path):
        from agency.cli import main
        result = self._runner().invoke(
            main, ["reason", "solve a problem", "--iterations", "2"],
        )
        assert result.exit_code == 0, result.output
        assert "avg_confidence" in result.output

    def test_reason_with_plan(self, tmp_path: Path):
        from agency.cli import main
        result = self._runner().invoke(
            main, ["reason", "g", "--plan"],
        )
        assert result.exit_code == 0, result.output

    def test_context_store_and_recall(self):
        from agency.cli import main
        runner = self._runner()
        # Click's CliRunner spins a fresh process-like invocation each
        # time but our singleton ContextManager is held in module state,
        # so the second invoke can read what the first stored.
        store = runner.invoke(
            main, ["context", "store", "k", "hello", "--ttl", "10"],
        )
        assert store.exit_code == 0, store.output
        assert "stored" in store.output
        recall = runner.invoke(main, ["context", "recall", "k"])
        assert recall.exit_code == 0, recall.output
        assert "hello" in recall.output

    def test_context_recall_missing(self):
        from agency.cli import main
        result = self._runner().invoke(
            main, ["context", "recall", "definitely-missing-xyzzy"],
        )
        assert result.exit_code != 0

    def test_expand_ingest_and_search(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("AGENCY_KNOWLEDGE_JSONL", str(tmp_path / "k.jsonl"))
        from agency.cli import main
        runner = self._runner()
        ingest = runner.invoke(main, [
            "expand", "the quick brown fox jumps over lazy dog",
            "--domain", "test",
        ])
        assert ingest.exit_code == 0, ingest.output
        assert "ingested" in ingest.output
        search = runner.invoke(main, [
            "expand", "stub", "--domain", "test",
            "--search", "brown fox",
        ])
        assert search.exit_code == 0, search.output
        assert "fox" in search.output.lower()

    def test_expand_search_no_matches(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("AGENCY_KNOWLEDGE_JSONL", str(tmp_path / "k.jsonl"))
        from agency.cli import main
        result = self._runner().invoke(main, [
            "expand", "x", "--search", "nothing",
        ])
        assert result.exit_code == 0
        assert "no matches" in result.output


# ---------------------------------------------------------------------------
# Expert-domain routing — integration across the new modules
# ---------------------------------------------------------------------------


class TestExpertDomainRouting:
    """Cross-module integration: lessons + capabilities steer routing."""

    def test_correction_surfaces_after_recording(self, tmp_path: Path):
        eng = SelfLearnerEngine(tmp_path / "lessons.jsonl")
        eng.record_interaction(
            context="ctx", outcome="success",
            insight="prefer haiku for simple summaries",
            applies_to=("ai-ml",),
            confidence=0.92,
            routing_correction="prefer-haiku-for-summaries",
        )
        out = eng.apply_corrections("ai-ml")
        assert "prefer-haiku-for-summaries" in out

    def test_weakest_domain_drives_focus(self, tmp_path: Path):
        ev = CapabilityEvolver(tmp_path / "cap.json")
        # Engineering: solid.
        for _ in range(20):
            ev.record_outcome("engineering", success=True, confidence=0.9)
        # Quantum: shaky.
        for _ in range(5):
            ev.record_outcome("quantum-computing", success=False, confidence=0.2)
        weakest = ev.weakest_domains(1)
        assert weakest[0].slug == "quantum-computing"

    def test_context_holds_routing_decision_across_steps(self):
        cm = ContextManager()
        cm.store("active_domain", "ai-ml", domain="routing", ttl_seconds=0)
        # Simulate a later reasoning step asking for the active domain.
        assert cm.recall("active_domain", domain="routing") == "ai-ml"
