"""Background file indexer - feeds all singularity files into memory."""
from __future__ import annotations
import threading, hashlib
from pathlib import Path


class FileIndexer:
    def __init__(self, root: Path, memory):
        self.root = Path(root)
        self.memory = memory
        self._running = False

    def index_all(self, max_files: int = 200000, max_bytes: int = 500_000):
        """Index up to max_files; skip binaries; snippet first 1KB."""
        count = 0
        skip_dirs = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache",
                     "imports", "memory_data", "chroma"}
        text_exts = {".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".ini",
                     ".html", ".css", ".js", ".ts", ".jsx", ".tsx", ".sh", ".ps1",
                     ".bat", ".cmd", ".rs", ".go", ".java", ".c", ".cpp", ".h"}
        for p in self.root.rglob("*"):
            if count >= max_files:
                break
            if not p.is_file():
                continue
            if any(part in skip_dirs for part in p.parts):
                continue
            if p.suffix.lower() not in text_exts:
                continue
            try:
                size = p.stat().st_size
                if size > max_bytes:
                    continue
                content = p.read_text(encoding='utf-8', errors='ignore')
                snippet = content[:1024]
                rel = str(p.relative_to(self.root))
                sha = hashlib.sha256(content.encode('utf-8', errors='ignore')).hexdigest()[:16]
                self.memory.index_file(rel, sha, size, snippet)
                count += 1
            except Exception:
                continue
        return count

    def start_background(self):
        if self._running: return
        self._running = True
        t = threading.Thread(target=self.index_all, daemon=True)
        t.start()
