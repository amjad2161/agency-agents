"""Tests for jarvis_brain.memory"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jarvis_brain.memory import Memory


def test_chat_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        m = Memory(Path(td))
        m.add_chat("user", "hello", "en")
        m.add_chat("assistant", "hi sir", "en")
        h = m.recent_chat(10)
        assert len(h) == 2
        assert h[0]["role"] == "user"
        assert h[0]["content"] == "hello"


def test_facts():
    with tempfile.TemporaryDirectory() as td:
        m = Memory(Path(td))
        m.remember("name", "Amjad")
        assert m.recall("name") == "Amjad"
        m.remember("name", "Tony")  # upsert
        assert m.recall("name") == "Tony"
        assert m.recall("missing") is None


def test_files():
    with tempfile.TemporaryDirectory() as td:
        m = Memory(Path(td))
        m.index_file("src/main.py", "abc123", 1024, "def main():")
        rows = m.search_files("main")
        assert len(rows) == 1
        assert rows[0]["path"] == "src/main.py"


def test_skills():
    with tempfile.TemporaryDirectory() as td:
        m = Memory(Path(td))
        m.register_skill("sql-pro", "engineering", "/path", "SQL expert")
        rows = m.search_skills("SQL")
        assert len(rows) == 1
        m.mark_skill_used("sql-pro")


if __name__ == "__main__":
    test_chat_roundtrip(); print("[OK] chat")
    test_facts(); print("[OK] facts")
    test_files(); print("[OK] files")
    test_skills(); print("[OK] skills")
    print("ALL TESTS PASS")
