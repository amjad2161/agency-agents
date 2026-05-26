"""Skill registry — scans agents/ tree + invokes via agency runtime."""
from __future__ import annotations
from pathlib import Path
import re


class SkillRegistry:
    def __init__(self, root: Path, memory):
        self.root = Path(root)
        self.memory = memory
        self.agents_dir = self.root / "agents"
        self._scanned = False

    def scan_all(self) -> int:
        """Scan agents/ tree, register every .md as a skill."""
        if not self.agents_dir.exists():
            return 0
        count = 0
        for division_dir in self.agents_dir.iterdir():
            if not division_dir.is_dir():
                continue
            division = division_dir.name
            for f in division_dir.glob("*.md"):
                name = f.stem
                desc = self._extract_description(f)
                self.memory.register_skill(name, division, str(f), desc)
                count += 1
        self._scanned = True
        return count

    def _extract_description(self, path: Path) -> str:
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')[:3000]
            # Grab description from frontmatter or first heading
            m = re.search(r'description:\s*(.+)', text)
            if m:
                return m.group(1).strip()[:300]
            m = re.search(r'^#\s+(.+)', text, re.MULTILINE)
            if m:
                return m.group(1).strip()[:300]
            return text[:300].replace('\n', ' ')
        except Exception:
            return ""

    def find_skill(self, query: str) -> list[dict]:
        if not self._scanned:
            self.scan_all()
        return self.memory.search_skills(query, n=5)

    def invoke(self, skill_name: str, prompt: str = "") -> str:
        """Try to invoke via agency CLI; fallback to returning skill description."""
        self.memory.mark_skill_used(skill_name)
        try:
            import agency
            run = getattr(agency, 'run', None) or getattr(agency, 'route', None)
            if run:
                return str(run(f"@{skill_name} {prompt}"))
        except Exception:
            pass
        # Fallback - read the skill md
        rows = self.memory.search_skills(skill_name, n=1)
        if rows:
            try:
                return Path(rows[0]['path']).read_text(encoding='utf-8', errors='ignore')[:2000]
            except Exception:
                return rows[0].get('description', '')
        return f"Skill '{skill_name}' not found"
