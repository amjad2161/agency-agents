"""GitHub import: clone repo, scan for skills/agents, integrate into singularity."""
from __future__ import annotations
import subprocess, shutil, re
from pathlib import Path


class GitHubImporter:
    def __init__(self, root: Path, memory, skills):
        self.root = Path(root)
        self.memory = memory
        self.skills = skills
        self.imports_dir = self.root / "imports"
        self.imports_dir.mkdir(parents=True, exist_ok=True)

    def clone(self, url: str, name: str | None = None) -> Path | None:
        """Clone a GitHub repo into imports/<name>/."""
        if not name:
            m = re.search(r'/([^/]+?)(\.git)?$', url)
            name = m.group(1) if m else "import"
        target = self.imports_dir / name
        if target.exists():
            # Pull latest
            try:
                subprocess.run(["git", "-C", str(target), "pull"], check=False, capture_output=True, timeout=120)
            except Exception:
                pass
        else:
            try:
                subprocess.run(["git", "clone", "--depth", "1", url, str(target)],
                               check=True, capture_output=True, timeout=300)
            except Exception as e:
                return None
        return target

    def integrate(self, repo_path: Path) -> dict:
        """Scan a cloned repo for agents (.md), Python modules, register them."""
        stats = {"agents_found": 0, "py_files": 0, "registered": 0}
        if not repo_path.exists():
            return stats
        # Find any .md that looks like an agent definition
        for md in repo_path.rglob("*.md"):
            text = md.read_text(encoding='utf-8', errors='ignore')[:2000]
            if any(k in text.lower() for k in ["agent", "skill", "specialty"]):
                name = md.stem
                desc = text.split("\n")[0][:300] if text else ""
                self.memory.register_skill(name, f"imported/{repo_path.name}", str(md), desc)
                stats["agents_found"] += 1
                stats["registered"] += 1
        # Index Python files for context
        for py in repo_path.rglob("*.py"):
            stats["py_files"] += 1
            try:
                snippet = py.read_text(encoding='utf-8', errors='ignore')[:500]
                self.memory.index_file(str(py), "", py.stat().st_size, snippet)
            except Exception:
                pass
        return stats

    def clone_and_integrate(self, url: str) -> dict:
        repo = self.clone(url)
        if not repo:
            return {"error": "clone failed", "url": url}
        stats = self.integrate(repo)
        stats["url"] = url
        stats["path"] = str(repo)
        return stats
