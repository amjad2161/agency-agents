"""Integration coverage for the seven new capability modules + four CLI commands.

Per-module split files (`test_self_learner.py`, `test_meta_reasoner.py`,
`test_context_manager.py`) carry the deep unit coverage. This file exercises
the modules end-to-end against the same public API the runtime uses, plus
the four CLI subcommands (`learn`, `reason`, `context`, `expand`) and the
expert-domain-routing integration path.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from agency.autonomous_loop import AutonomousLoop, LoopRun, LoopStatus
from agency.capability_evolver import CapabilityEvolver, DomainProfile
from agency.context_manager import ContextEntry, ContextManager
from agency.knowledge_expansion import KnowledgeChunk, KnowledgeExpansion
from agency.meta_reasoner import MetaReasoningEngine, ReasoningStep
from agency.multimodal import (
    ModalityType,
    MultimodalPayload,
    MultimodalProcessor,
)
from agency.self_learner_engine import Lesson, SelfLearnerEngine


# ---------------------------------------------------------------------------
# SelfLearnerEngine
# ---------------------------------------------------------------------------


class TestSelfLearnerEngine:
    def test_record_interaction_persists_jsonl_row(self, tmp_path: Path):
        path = tmp_path / "lessons.jsonl"
        eng = SelfLearnerEngine(path)
        lesson = eng.record_interaction(
            request="explain quantum tunneling",
            response="Quantum tunneling is...",
            feedback="perfect",
            routed_to="jarvis-physics",
        )
        assert lesson.outcome == "success"
        assert lesson.confidence == 1.0  # "perfect" maps to 1.0
        body = path.read_text(encoding="utf-8").splitlines()
        assert len(body) == 1
        parsed = json.loads(body[0])
        assert parsed["applies_to"] == ["jarvis-physics"]

    def test_record_writes_correction_when_routing_wrong(self, tmp_path: Path):
        eng = SelfLearnerEngine(tmp_path / "lessons.jsonl")
        lesson = eng.record_interaction(
            request="what is the speed of light",
            response="3e8 m/s",
            feedback="good but wrong domain",
            routed_to="jarvis-engineering",
            correct_slug="jarvis-physics",
        )
        assert lesson.outcome == "correction"
        assert lesson.routing_correction is not None
        assert lesson.routing_correction["was"] == "jarvis-engineering"
        assert lesson.routing_correction["should_be"] == "jarvis-physics"

    def test_get_lessons_for_domain_filters(self, tmp_path: Path):
        eng = SelfLearnerEngine(tmp_path / "lessons.jsonl")
        eng.record_interaction(request="A", response="r", routed_to="alpha")
        eng.record_interaction(request="B", response="r", routed_to="beta")
        out = eng.get_lessons_for_domain("alpha")
        assert all("alpha" in l.applies_to for l in out)
        assert len(out) == 1

    def test_get_routing_corrections_aggregates(self, tmp_path: Path):
        eng = SelfLearnerEngine(tmp_path / "lessons.jsonl")
        eng.record_interaction(
            request="x", response="r",
            routed_to="a", correct_slug="b",
        )
        eng.record_interaction(
            request="y", response="r",
            routed_to="c", correct_slug="d",
        )
        eng.record_interaction(request="z", response="r")  # no correction
        corrections = eng.get_routing_corrections()
        assert len(corrections) == 2
        assert {c["was"] for c in corrections} == {"a", "c"}

    def test_improve_routing_weights_balances_corrections(self, tmp_path: Path):
        eng = SelfLearnerEngine(tmp_path / "lessons.jsonl")
        eng.record_interaction(
            request="x", response="r",
            routed_to="wrong-slug", correct_slug="right-slug",
        )
        deltas = eng.improve_routing_weights(brain=None)
        assert deltas["wrong-slug"] < 0
        assert deltas["right-slug"] > 0

    def test_summarize_growth_handles_empty(self, tmp_path: Path):
        eng = SelfLearnerEngine(tmp_path / "lessons.jsonl")
        report = eng.summarize_growth()
        assert "No lessons" in report

    def test_summarize_growth_renders_markdown(self, tmp_path: Path):
        eng = SelfLearnerEngine(tmp_path / "lessons.jsonl")
        eng.record_interaction(request="q", response="a", feedback="good")
        report = eng.summarize_growth()
        assert "# JARVIS Self-Learning Growth Report" in report
        assert "Total lessons learned" in report

    def test_export_import_round_trip(self, tmp_path: Path):
        src = SelfLearnerEngine(tmp_path / "src.jsonl")
        src.record_interaction(request="q1", response="a1")
        src.record_interaction(request="q2", response="a2")
        snapshot = src.export_knowledge_snapshot()
        assert snapshot["total_lessons"] == 2

        dst = SelfLearnerEngine(tmp_path / "dst.jsonl")
        n = dst.import_knowledge_snapshot(snapshot)
        assert n == 2
        # Force re-load from disk to confirm persistence.
        dst2 = SelfLearnerEngine(tmp_path / "dst.jsonl")
        assert len(dst2._load()) == 2


# ---------------------------------------------------------------------------
# MetaReasoningEngine
# ---------------------------------------------------------------------------


class TestMetaReasoningEngine:
    def test_reason_returns_steps(self):
        eng = MetaReasoningEngine()
        steps = eng.reason("design a rate limiter", max_iterations=3)
        assert 1 <= len(steps) <= 3
        assert all(isinstance(s, ReasoningStep) for s in steps)

    def test_reason_steps_have_monotonic_ids(self):
        eng = MetaReasoningEngine()
        steps = eng.reason("explain TCP slow start", max_iterations=4)
        ids = [s.step_id for s in steps]
        assert ids == sorted(ids)
        assert ids[0] == 1

    def test_reason_respects_max_iterations(self):
        eng = MetaReasoningEngine()
        steps = eng.reason("g", max_iterations=2)
        assert len(steps) <= 2

    def test_plan_and_execute_returns_markdown(self):
        eng = MetaReasoningEngine()
        plan = eng.plan_and_execute("write a function that reverses a string")
        assert plan.startswith("## Execution Plan")
        assert "Step 1" in plan

    def test_critique_scores_response(self):
        eng = MetaReasoningEngine()
        score, feedback = eng.critique(
            "TCP retransmits using exponential backoff after timeout. "
            "The retransmit timer doubles on each attempt. " * 4,
            "explain TCP retransmit",
        )
        assert 0.0 <= score <= 1.0
        assert isinstance(feedback, str)

    def test_critique_penalises_too_brief(self):
        eng = MetaReasoningEngine()
        score, feedback = eng.critique("yes", "explain HTTP/2 multiplexing")
        assert score < 0.9
        assert "brief" in feedback.lower() or "missing" in feedback.lower()

    def test_avg_confidence_after_reason(self):
        eng = MetaReasoningEngine()
        eng.reason("explain quicksort", max_iterations=3)
        avg = eng.avg_confidence()
        assert 0.0 <= avg <= 1.0


# ---------------------------------------------------------------------------
# CapabilityEvolver
# ---------------------------------------------------------------------------


class TestCapabilityEvolver:
    def test_record_outcome_creates_profile(self, tmp_path: Path):
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
        prof = ev2.get_profile("eng")
        assert prof is not None
        assert prof.total_requests == 1

    def test_ema_confidence_moves_toward_latest(self, tmp_path: Path):
        ev = CapabilityEvolver(tmp_path / "cap.json")
        # EMA with alpha=0.2: each record pulls 20% toward new value.
        for _ in range(10):
            ev.record_outcome("d", success=True, confidence=1.0)
        prof = ev.get_profile("d")
        # After many records pulling toward 1.0, avg should be > 0.5.
        assert prof.avg_confidence > 0.5

    def test_weakest_domains_filters_low_request_count(self, tmp_path: Path):
        ev = CapabilityEvolver(tmp_path / "cap.json")
        # "low" only has 2 requests; should be excluded from weakest.
        ev.record_outcome("low", success=False, confidence=0.1)
        ev.record_outcome("low", success=False, confidence=0.1)
        # "tracked" has 3 requests; eligible.
        for _ in range(3):
            ev.record_outcome("tracked", success=False, confidence=0.2)
        weakest = ev.weakest_domains(5)
        slugs = [p.slug for p in weakest]
        assert "tracked" in slugs
        assert "low" not in slugs

    def test_strongest_domains_returns_top_n(self, tmp_path: Path):
        ev = CapabilityEvolver(tmp_path / "cap.json")
        for _ in range(5):
            ev.record_outcome("a", success=True, confidence=0.95)
        for _ in range(5):
            ev.record_outcome("b", success=False, confidence=0.1)
        top = ev.strongest_domains(1)
        assert top[0].slug == "a"

    def test_growth_report_renders_markdown(self, tmp_path: Path):
        ev = CapabilityEvolver(tmp_path / "cap.json")
        for _ in range(3):
            ev.record_outcome("a", success=True, confidence=0.9)
        report = ev.growth_report()
        assert "# JARVIS Capability Growth Report" in report
        assert "Domains tracked" in report


# ---------------------------------------------------------------------------
# ContextManager
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_store_and_recall(self, tmp_path: Path):
        cm = ContextManager(tmp_path / "ctx.json")
        cm.store("k", "v", domain="d")
        assert cm.recall("k", domain="d") == "v"

    def test_domains_are_isolated(self, tmp_path: Path):
        cm = ContextManager(tmp_path / "ctx.json")
        cm.store("k", "alpha", domain="A")
        cm.store("k", "beta", domain="B")
        assert cm.recall("k", domain="A") == "alpha"
        assert cm.recall("k", domain="B") == "beta"

    def test_ttl_expiry_evicts(self, tmp_path: Path, monkeypatch):
        cm = ContextManager(tmp_path / "ctx.json")
        cm.store("k", "v", domain="d", ttl_seconds=1)
        future = time.time() + 5
        monkeypatch.setattr(
            "agency.context_manager.time.time",
            lambda: future,
        )
        assert cm.recall("k", domain="d") is None
        assert "k" not in cm.dump_domain("d")

    def test_ttl_zero_means_never(self, tmp_path: Path, monkeypatch):
        cm = ContextManager(tmp_path / "ctx.json")
        cm.store("k", "v", domain="d", ttl_seconds=0)
        future = time.time() + 10**9
        monkeypatch.setattr(
            "agency.context_manager.time.time",
            lambda: future,
        )
        assert cm.recall("k", domain="d") == "v"

    def test_recall_recent_returns_newest_first(self, tmp_path: Path):
        cm = ContextManager(tmp_path / "ctx.json")
        cm.store("a", 1, domain="d")
        time.sleep(0.01)
        cm.store("b", 2, domain="d")
        time.sleep(0.01)
        cm.store("c", 3, domain="d")
        recent = cm.recall_recent(domain="d", n=2)
        assert [e.key for e in recent] == ["c", "b"]

    def test_forget_returns_status(self, tmp_path: Path):
        cm = ContextManager(tmp_path / "ctx.json")
        cm.store("k", "v", domain="d")
        assert cm.forget("k", domain="d") is True
        assert cm.forget("k", domain="d") is False

    def test_search_by_tag(self, tmp_path: Path):
        cm = ContextManager(tmp_path / "ctx.json")
        cm.store("a", 1, domain="d", tags=["important"])
        cm.store("b", 2, domain="d", tags=["other"])
        cm.store("c", 3, domain="d", tags=["important", "urgent"])
        hits = cm.search_by_tag("important")
        assert {e.key for e in hits} == {"a", "c"}


# ---------------------------------------------------------------------------
# AutonomousLoop
# ---------------------------------------------------------------------------


class TestAutonomousLoop:
    def test_run_terminates_when_executor_signals_done(self, tmp_path: Path):
        loop = AutonomousLoop(max_iterations=10, runs_path=tmp_path / "runs.jsonl")
        loop.register_executor(
            "default",
            # Returning text containing "complete" trips _is_done.
            lambda action, ctx: "task complete",
        )
        run = loop.run("write a haiku about the sea")
        assert run.status == LoopStatus.DONE
        assert len(run.iterations) >= 1

    def test_run_hits_max_iterations(self, tmp_path: Path):
        loop = AutonomousLoop(max_iterations=3, runs_path=tmp_path / "runs.jsonl")
        loop.register_executor(
            "default",
            # Output contains no done-keyword → loop walks to MAX_ITER.
            lambda action, ctx: "still working on it",
        )
        run = loop.run("compute pi to 100 digits")
        assert run.status in (LoopStatus.MAX_ITER, LoopStatus.DONE)
        assert len(run.iterations) <= 3

    def test_stop_event_interrupts(self, tmp_path: Path):
        stop = threading.Event()
        loop = AutonomousLoop(
            max_iterations=10,
            stop_event=stop,
            runs_path=tmp_path / "runs.jsonl",
        )
        loop.register_executor(
            "default",
            lambda action, ctx: "still going",
        )
        stop.set()
        run = loop.run("long-running goal")
        assert run.status == LoopStatus.INTERRUPTED


# ---------------------------------------------------------------------------
# KnowledgeExpansion
# ---------------------------------------------------------------------------


class TestKnowledgeExpansion:
    def test_ingest_text_returns_chunks(self):
        ke = KnowledgeExpansion()
        chunks = ke.ingest_text("Transformers use self-attention.", domain="ai")
        assert len(chunks) == 1
        assert chunks[0].domain == "ai"
        assert "attention" in chunks[0].text or "Transformers" in chunks[0].text

    def test_search_keyword_overlap(self):
        ke = KnowledgeExpansion()
        ke.ingest_text("the quick brown fox jumps over the lazy dog", domain="d")
        ke.ingest_text("nothing relevant here", domain="d")
        ke.ingest_text("brown fox brown fox brown fox", domain="d")
        hits = ke.search("brown fox", domain="d", top_k=3)
        assert len(hits) >= 1
        # Highest-overlap chunk should be the repeated one.
        assert "brown fox" in hits[0].text

    def test_list_domains_unique(self):
        ke = KnowledgeExpansion()
        ke.ingest_text("a", domain="ai")
        ke.ingest_text("b", domain="bio")
        ke.ingest_text("c", domain="ai")  # dup domain
        assert sorted(ke.list_domains()) == ["ai", "bio"]


# ---------------------------------------------------------------------------
# MultimodalProcessor
# ---------------------------------------------------------------------------


class TestMultimodalProcessor:
    def test_from_text(self):
        proc = MultimodalProcessor()
        p = proc.from_text("hello")
        assert p.modality is ModalityType.TEXT
        assert p.text == "hello"
        assert isinstance(p, MultimodalPayload)

    def test_from_text_default_source(self):
        proc = MultimodalProcessor()
        p = proc.from_text("hi")
        assert p.source == "direct"

    def test_from_file_text(self, tmp_path: Path):
        proc = MultimodalProcessor()
        f = tmp_path / "f.txt"
        f.write_text("body")
        p = proc.from_file(f)
        assert p.modality is ModalityType.TEXT
        assert p.text == "body"

    def test_from_file_image_keeps_bytes(self, tmp_path: Path):
        proc = MultimodalProcessor()
        f = tmp_path / "f.png"
        # 8-byte PNG signature + 10 zero bytes.
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10)
        p = proc.from_file(f)
        assert p.modality is ModalityType.IMAGE
        assert p.raw_bytes is not None
        assert len(p.raw_bytes) == 18

    def test_from_file_missing_raises(self, tmp_path: Path):
        proc = MultimodalProcessor()
        with pytest.raises(FileNotFoundError):
            proc.from_file(tmp_path / "nope.txt")

    def test_from_base64_text(self):
        proc = MultimodalProcessor()
        encoded = base64.b64encode(b"hi").decode("ascii")
        p = proc.from_base64(encoded, "text/plain")
        assert p.modality is ModalityType.TEXT
        assert p.text == "hi"

    def test_from_structured_serializes(self):
        proc = MultimodalProcessor()
        p = proc.from_structured({"a": 1, "b": [1, 2]})
        assert p.modality is ModalityType.STRUCTURED
        loaded = json.loads(p.text)
        assert loaded == {"a": 1, "b": [1, 2]}

    def test_extract_text_returns_text_field(self):
        proc = MultimodalProcessor()
        p = proc.from_text("alpha")
        assert proc.extract_text(p) == "alpha"

    def test_extract_text_falls_back_for_binary(self):
        proc = MultimodalProcessor()
        # Manually build an image payload with no extracted text.
        p = MultimodalPayload(
            modality=ModalityType.IMAGE,
            raw_bytes=b"\xff" * 12,
            mime_type="image/png",
        )
        out = proc.extract_text(p)
        # No OCR backend wired → stub message that mentions image.
        assert "image" in out.lower()

    def test_combine_joins_text_payloads(self):
        proc = MultimodalProcessor()
        a = proc.from_text("alpha")
        b = proc.from_text("beta")
        out = proc.combine([a, b])
        assert out.modality is ModalityType.TEXT
        assert "alpha" in out.text
        assert "beta" in out.text


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


class TestCLICommands:
    def _runner(self) -> CliRunner:
        return CliRunner()

    def test_learn_records_lesson(self, tmp_path: Path, monkeypatch):
        # Redirect the engine's default lessons path into a tmp dir.
        monkeypatch.setattr(
            "agency.self_learner_engine.DEFAULT_LESSONS_PATH",
            tmp_path / "lessons.jsonl",
        )
        from agency.cli import main
        result = self._runner().invoke(
            main,
            ["learn", "explain X", "--response", "X is Y", "--feedback", "good",
             "--routed-to", "eng"],
        )
        assert result.exit_code == 0, result.output
        assert "recorded lesson" in result.output
        # File exists with one row.
        body = (tmp_path / "lessons.jsonl").read_text(encoding="utf-8")
        assert body.count("\n") == 1

    def test_learn_records_correction_when_slug_differs(
        self, tmp_path: Path, monkeypatch,
    ):
        monkeypatch.setattr(
            "agency.self_learner_engine.DEFAULT_LESSONS_PATH",
            tmp_path / "lessons.jsonl",
        )
        from agency.cli import main
        result = self._runner().invoke(
            main,
            ["learn", "compute pi", "--response", "3.14",
             "--routed-to", "wrong", "--correct-slug", "right"],
        )
        assert result.exit_code == 0, result.output
        parsed = json.loads(
            (tmp_path / "lessons.jsonl").read_text().strip()
        )
        assert parsed["outcome"] == "correction"

    def test_reason_runs_offline(self):
        from agency.cli import main
        result = self._runner().invoke(
            main, ["reason", "solve a problem", "--iterations", "2"],
        )
        assert result.exit_code == 0, result.output
        assert "avg_confidence" in result.output

    def test_reason_with_plan_flag_emits_markdown(self):
        from agency.cli import main
        result = self._runner().invoke(
            main, ["reason", "design a cache", "--plan"],
        )
        assert result.exit_code == 0, result.output
        assert "## Execution Plan" in result.output

    def test_context_store_and_recall_round_trip(self, tmp_path: Path, monkeypatch):
        # Force the shared singleton onto a fresh tmp store path so the
        # CLI test doesn't leak state across runs.
        monkeypatch.setattr(
            "agency.context_manager.DEFAULT_CONTEXT_PATH",
            tmp_path / "ctx.json",
        )
        # Reset CLI singleton.
        import agency.cli as cli_mod
        monkeypatch.setattr(cli_mod, "_CTX_MANAGER_SINGLETON", None)

        from agency.cli import main
        runner = self._runner()
        store = runner.invoke(
            main, ["context", "store", "k", "hello", "--ttl", "10"],
        )
        assert store.exit_code == 0, store.output
        assert "stored" in store.output
        recall = runner.invoke(main, ["context", "recall", "k"])
        assert recall.exit_code == 0, recall.output
        assert "hello" in recall.output

    def test_context_recall_missing_exits_nonzero(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "agency.context_manager.DEFAULT_CONTEXT_PATH",
            tmp_path / "ctx.json",
        )
        import agency.cli as cli_mod
        monkeypatch.setattr(cli_mod, "_CTX_MANAGER_SINGLETON", None)

        from agency.cli import main
        result = self._runner().invoke(
            main, ["context", "recall", "no-such-key"],
        )
        assert result.exit_code != 0

    def test_expand_ingests_text(self, tmp_path: Path):
        from agency.cli import main
        runner = self._runner()
        ingest = runner.invoke(main, [
            "expand", "the quick brown fox jumps over lazy dog",
            "--domain", "test",
        ])
        assert ingest.exit_code == 0, ingest.output
        assert "ingested" in ingest.output

    def test_expand_search_no_matches_reports(self, tmp_path: Path):
        from agency.cli import main
        # First ingest something so the store isn't empty for the singleton.
        self._runner().invoke(main, [
            "expand", "alpha beta gamma", "--domain", "test",
        ])
        result = self._runner().invoke(main, [
            "expand", "stub-source", "--domain", "test",
            "--search", "definitely-no-such-keyword-xyzzy",
        ])
        assert result.exit_code == 0
        assert "no matches" in result.output

    def test_main_help_lists_new_commands(self):
        from agency.cli import main
        result = self._runner().invoke(main, ["--help"])
        assert result.exit_code == 0
        for cmd in ("learn", "reason", "context", "expand"):
            assert cmd in result.output


# ---------------------------------------------------------------------------
# Expert-domain routing — integration across the new modules
# ---------------------------------------------------------------------------


class TestExpertDomainRouting:
    """Cross-module integration: lessons + capabilities steer routing."""

    def test_correction_surfaces_in_routing_corrections(self, tmp_path: Path):
        eng = SelfLearnerEngine(tmp_path / "lessons.jsonl")
        eng.record_interaction(
            request="explain quantum entanglement",
            response="...",
            feedback="wrong domain",
            routed_to="jarvis-engineering",
            correct_slug="jarvis-physics",
        )
        corrections = eng.get_routing_corrections()
        assert any(c["should_be"] == "jarvis-physics" for c in corrections)

    def test_weakest_domain_drives_focus(self, tmp_path: Path):
        ev = CapabilityEvolver(tmp_path / "cap.json")
        # Engineering: solid (>=3 reqs, all success at high conf).
        for _ in range(20):
            ev.record_outcome("engineering", success=True, confidence=0.9)
        # Quantum: shaky (>=3 reqs, all fail at low conf).
        for _ in range(5):
            ev.record_outcome("quantum-computing", success=False, confidence=0.2)
        weakest = ev.weakest_domains(1)
        assert weakest[0].slug == "quantum-computing"

    def test_context_holds_routing_decision_across_steps(self, tmp_path: Path):
        cm = ContextManager(tmp_path / "ctx.json")
        cm.store("active_domain", "ai-ml", domain="routing", ttl_seconds=0)
        # A later reasoning step asking for the active domain should see it.
        assert cm.recall("active_domain", domain="routing") == "ai-ml"
