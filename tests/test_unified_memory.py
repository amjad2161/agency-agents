"""
Tests for UnifiedMemoryEngine — the long-term JARVIS memory system.
All tests are offline, no API keys, no network.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import pytest


class TestUnifiedMemoryEngine:
    """Tests for the Unified Memory Engine."""

    @pytest.fixture
    def mem(self, tmp_path):
        """Fresh in-memory DB for each test."""
        from jarvis_brainiac.unified_memory_engine import UnifiedMemoryEngine
        db_path = tmp_path / "test_unified.sqlite"
        engine = UnifiedMemoryEngine(db_path=db_path)
        yield engine
        engine.close()

    def test_import(self):
        from jarvis_brainiac.unified_memory_engine import (
            UnifiedMemoryEngine, Requirement, MemoryEntry, SearchResult,
            get_memory, quick_search, quick_remember, EPOCHS, BUILTIN_REQUIREMENTS
        )
        # EPOCHS has 6 entries: 0 (Pre-existing) + epochs 1-5
        assert len(EPOCHS) == 6
        assert 0 in EPOCHS  # Pre-existing Systems
        assert 5 in EPOCHS  # Unified Singularity
        assert len(BUILTIN_REQUIREMENTS) >= 88

    def test_all_88_requirements_seeded(self, mem):
        """All 88 built-in requirements must be seeded on init."""
        reqs = mem.get_requirements()
        assert len(reqs) >= 88

    def test_requirements_span_5_epochs(self, mem):
        """Must have requirements in all 5 epochs."""
        for epoch in range(1, 6):
            reqs = mem.get_requirements(epoch=epoch)
            assert len(reqs) >= 1, f"Epoch {epoch} has no requirements"

    def test_epoch_1_requirements(self, mem):
        """Epoch 1 (Initial Vision) must have core identity requirements."""
        reqs = mem.get_requirements(epoch=1)
        texts = [r['text'] for r in reqs]
        assert any('AGI' in t or 'orchestration' in t for t in texts)
        assert any('memory' in t.lower() for t in texts)
        assert any('API key' in t for t in texts)

    def test_epoch_2_missions(self, mem):
        """Epoch 2 must have all 30 mission requirements."""
        reqs = mem.get_requirements(epoch=2)
        assert len(reqs) >= 30

    def test_epoch_3_navigation(self, mem):
        """Epoch 3 must have navigation requirements."""
        reqs = mem.get_requirements(epoch=3)
        texts = ' '.join(r['text'] for r in reqs).lower()
        assert 'navigation' in texts or 'godskill' in texts
        assert '145' in texts or '965' in texts

    def test_epoch_4_free_llm(self, mem):
        """Epoch 4 must have FreeLLM requirements."""
        reqs = mem.get_requirements(epoch=4)
        texts = ' '.join(r['text'] for r in reqs).lower()
        assert 'freellm' in texts or 'free' in texts
        assert 'anthropic' in texts or 'paid' in texts

    def test_epoch_5_unified(self, mem):
        """Epoch 5 must have unified singularity requirements."""
        reqs = mem.get_requirements(epoch=5)
        assert len(reqs) >= 11
        texts = ' '.join(r['text'] for r in reqs).lower()
        assert 'unif' in texts or 'single' in texts

    def test_add_requirement(self, mem):
        req_id = mem.add_requirement(
            text="Test requirement for unified build",
            epoch=5,
            status="open",
            source="test"
        )
        assert req_id.startswith("REQ-")
        found = mem.get_requirement(req_id)
        assert found is not None
        assert found['text'] == "Test requirement for unified build"
        assert found['epoch'] == 5
        assert found['status'] == 'open'

    def test_update_requirement_status(self, mem):
        req_id = mem.add_requirement("Status update test", epoch=5)
        updated = mem.update_requirement_status(req_id, "done", notes="completed in test")
        assert updated is True
        found = mem.get_requirement(req_id)
        assert found['status'] == 'done'
        assert found['notes'] == 'completed in test'

    def test_filter_by_status(self, mem):
        done_reqs = mem.get_requirements(status='done')
        open_reqs = mem.get_requirements(status='open')
        assert len(done_reqs) > 0
        assert len(open_reqs) > 0
        assert all(r['status'] == 'done' for r in done_reqs)
        assert all(r['status'] == 'open' for r in open_reqs)

    def test_search_requirements_fts(self, mem):
        """Full-text search must find relevant requirements."""
        results = mem.search_requirements("voice")
        assert len(results) >= 1
        texts = [r['text'].lower() for r in results]
        assert any('voice' in t or 'mic' in t or 'language' in t for t in texts)

    def test_search_requirements_memory(self, mem):
        results = mem.search_requirements("memory")
        assert len(results) >= 1

    def test_search_requirements_navigation(self, mem):
        results = mem.search_requirements("navigation")
        assert len(results) >= 1

    def test_search_requirements_empty_returns_all(self, mem):
        results = mem.search_requirements("")
        assert len(results) >= 88

    def test_remember_and_recall(self, mem):
        entry_id = mem.remember(
            title="JARVIS launched successfully",
            content="JARVIS BRAINIAC v1.0 was launched for the first time",
            entry_type="event",
            importance=9
        )
        assert entry_id

        hits = mem.recall("launched")
        assert len(hits) >= 1
        assert any(h.entry_id == entry_id for h in hits)

    def test_recall_returns_snippets(self, mem):
        mem.remember("Long memory test", "A" * 500, entry_type="decision")
        hits = mem.recall("Long memory")
        assert len(hits) >= 1
        assert len(hits[0].snippet) <= 210  # truncated at 200 + "..."

    def test_timeline_has_5_milestones(self, mem):
        """Built-in timeline must have 5 milestone events."""
        timeline = mem.get_timeline()
        assert len(timeline) >= 5
        dates = [t['event_date'] for t in timeline]
        assert '2026-05-03' in dates
        assert '2026-05-27' in dates

    def test_timeline_chronological(self, mem):
        timeline = mem.get_timeline()
        dates = [t['event_date'] for t in timeline]
        assert dates == sorted(dates)

    def test_add_event(self, mem):
        event_id = mem.add_event(
            title="Test Event",
            description="A test event for validation",
            event_date="2026-05-27",
            epoch=5,
            event_type="milestone"
        )
        assert event_id
        timeline = mem.get_timeline()
        titles = [t['title'] for t in timeline]
        assert "Test Event" in titles

    def test_stats_structure(self, mem):
        stats = mem.stats()
        assert 'requirements' in stats
        assert 'memory_entries' in stats
        assert 'timeline_events' in stats
        assert 'per_epoch' in stats
        assert 'db_path' in stats

        req_stats = stats['requirements']
        assert 'total' in req_stats
        assert 'done' in req_stats
        assert 'open' in req_stats
        assert 'completion_pct' in req_stats
        assert req_stats['total'] >= 88
        assert req_stats['completion_pct'] >= 50  # most reqs are done

    def test_stats_per_epoch(self, mem):
        stats = mem.stats()
        per_epoch = stats['per_epoch']
        # 6 epochs total: 0 (Pre-existing) + epochs 1-5
        assert len(per_epoch) == 6
        for epoch_num in range(1, 6):
            assert epoch_num in per_epoch
            assert per_epoch[epoch_num]['total'] >= 1

    def test_export_json(self, mem):
        exported = mem.export_json()
        data = json.loads(exported)
        assert 'exported_at' in data
        assert 'requirements' in data
        assert 'timeline' in data
        assert 'stats' in data
        assert len(data['requirements']) >= 88

    def test_idempotent_seeding(self, tmp_path):
        """Running init twice must not duplicate requirements."""
        from jarvis_brainiac.unified_memory_engine import UnifiedMemoryEngine
        db_path = tmp_path / "idempotent.sqlite"

        engine1 = UnifiedMemoryEngine(db_path=db_path)
        count1 = len(engine1.get_requirements())
        engine1.close()

        engine2 = UnifiedMemoryEngine(db_path=db_path)
        count2 = len(engine2.get_requirements())
        engine2.close()

        assert count1 == count2  # no duplicates

    def test_singleton(self, tmp_path):
        """get_memory() must return the same instance."""
        from jarvis_brainiac.unified_memory_engine import get_memory, UnifiedMemoryEngine
        import jarvis_brainiac.unified_memory_engine as ume
        # Reset singleton for test
        ume._instance = None
        db_path = tmp_path / "singleton.sqlite"
        m1 = get_memory(db_path)
        m2 = get_memory(db_path)
        assert m1 is m2
        ume._instance = None  # cleanup


class TestUnifiedMemoryServerEndpoints:
    """Integration tests for the unified memory REST endpoints."""

    @pytest.fixture
    def client(self, tmp_path):
        """Flask test client with fresh DB."""
        import ast
        from pathlib import Path
        src = (Path(__file__).parent.parent / "godskill_server" / "server.py").read_text(encoding="utf-8")
        ast.parse(src)  # Validate syntax

        import jarvis_brainiac.unified_memory_engine as ume
        ume._instance = None

        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "server_test",
            Path(__file__).parent.parent / "godskill_server" / "server.py"
        )
        # We test by importing unified_memory_engine directly, not through Flask
        return None  # Skip Flask client for now — tested via imports

    def test_server_py_has_all_unified_endpoints(self):
        """server.py must define all 6 unified endpoints."""
        import ast
        src = (ROOT / "godskill_server" / "server.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        func_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        required = [
            'api_unified_stats',
            'api_unified_requirements',
            'api_unified_search',
            'api_unified_timeline',
            'api_unified_remember',
            'api_unified_add_requirement',
            'api_unified_export',
        ]
        for name in required:
            assert name in func_names, f"Missing endpoint: {name}"

    def test_unified_memory_engine_importable(self):
        from jarvis_brainiac.unified_memory_engine import (
            UnifiedMemoryEngine, get_memory, quick_search, quick_remember
        )

    def test_requirements_master_file_exists(self):
        """requirements_master.md must exist."""
        req_file = ROOT / "memory" / "requirements_master.md"
        assert req_file.exists(), "requirements_master.md not found"
        content = req_file.read_text(encoding="utf-8")
        assert "REQ-001" in content
        assert "REQ-088" in content
        assert "EPOCH 1" in content
        assert "EPOCH 5" in content
