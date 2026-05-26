"""
JARVIS UNIFIED BUILD SCRIPT
============================
Scans every project on the computer, merges all JARVIS-related code
into C:\Users\Mobar\JARVIS_UNIFIED\, and creates a complete index.

Run: python build_unified.py

Projects unified:
  1. C:\Users\Mobar\jarvis-brainiac\           ← PRIMARY (source of truth)
  2. C:\Users\Mobar\OneDrive\Desktop\jarvis brainiac\  ← SECONDARY (older)
  3. C:\Users\Mobar\SkyCore\                   ← DRONE SYSTEM (integrated)
  4. C:\Users\Mobar\kidgenius-academy\          ← EDUCATIONAL PLATFORM
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─── Configuration ─────────────────────────────────────────────────────────────

UNIFIED_ROOT = Path("C:/Users/Mobar/JARVIS_UNIFIED")

SOURCES: list[dict] = [
    {
        "name": "jarvis-brainiac (PRIMARY)",
        "path": Path("C:/Users/Mobar/jarvis-brainiac"),
        "priority": 1,
        "dest_prefix": "",          # goes to root of JARVIS_UNIFIED
        "include_all": True,
    },
    {
        "name": "Desktop JARVIS (SECONDARY)",
        "path": Path("C:/Users/Mobar/OneDrive/Desktop/jarvis brainiac"),
        "priority": 2,
        "dest_prefix": "_archive/desktop_jarvis",
        "include_all": False,       # only unique files not in primary
    },
    {
        "name": "SkyCore (DRONE SYSTEM)",
        "path": Path("C:/Users/Mobar/SkyCore"),
        "priority": 3,
        "dest_prefix": "skycore",
        "include_all": True,
    },
    {
        "name": "KidGenius Academy",
        "path": Path("C:/Users/Mobar/kidgenius-academy"),
        "priority": 4,
        "dest_prefix": "kidgenius",
        "include_all": True,
    },
]

# Directories to ALWAYS skip (noise, not source)
SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".cache",
    "dist", "build", ".next", ".nuxt", "target", "bin", "obj",
    ".idea", ".vs", ".vscode", "blobs", "*.egg-info",
}

# File extensions to skip (binary/model blobs)
SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".gguf", ".bin", ".pt", ".pth", ".safetensors",
    ".onnx", ".exe", ".msi", ".dll", ".so", ".dylib",
    ".zip", ".tar", ".gz", ".7z", ".rar",  # archive files
    ".mp4", ".avi", ".mkv", ".mov",         # video files
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico",  # images
    ".pdf",                                  # PDFs (keep .md, .txt)
}

MAX_FILE_SIZE_MB = 10  # skip files larger than this

# ─── Stats ─────────────────────────────────────────────────────────────────────

stats = {
    "scanned": 0,
    "copied": 0,
    "skipped_size": 0,
    "skipped_ext": 0,
    "skipped_dir": 0,
    "duplicate": 0,
    "errors": 0,
    "files_by_source": {},
}

# Track copied hashes to detect duplicates
_copied_hashes: dict[str, str] = {}  # hash → first dest path


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def should_skip_dir(dirname: str) -> bool:
    return dirname.startswith(".") or dirname in SKIP_DIRS


def should_skip_file(path: Path) -> tuple[bool, str]:
    ext = path.suffix.lower()
    if ext in SKIP_EXTENSIONS:
        return True, "extension"
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        return True, "size"
    return False, ""


def copy_source(source: dict, manifest: list[dict]) -> None:
    src_root = source["path"]
    dest_prefix = source["dest_prefix"]
    name = source["name"]

    if not src_root.exists():
        print(f"  ⚠️  Source not found: {src_root}")
        return

    print(f"\n{'='*60}")
    print(f"  Source: {name}")
    print(f"  From:   {src_root}")
    print(f"  To:     {UNIFIED_ROOT / dest_prefix}")
    print(f"{'='*60}")

    file_count = 0
    stats["files_by_source"][name] = 0

    for dirpath, dirnames, filenames in os.walk(src_root):
        # Filter directories in-place (affects os.walk recursion)
        dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]

        for filename in filenames:
            src_file = Path(dirpath) / filename
            stats["scanned"] += 1

            # Compute relative path from source root
            rel = src_file.relative_to(src_root)
            if dest_prefix:
                dest_file = UNIFIED_ROOT / dest_prefix / rel
            else:
                dest_file = UNIFIED_ROOT / rel

            # Check skip conditions
            try:
                skip, reason = should_skip_file(src_file)
            except Exception:
                stats["errors"] += 1
                continue

            if skip:
                if reason == "extension":
                    stats["skipped_ext"] += 1
                else:
                    stats["skipped_size"] += 1
                continue

            # Duplicate check
            try:
                h = file_hash(src_file)
            except Exception:
                stats["errors"] += 1
                continue

            if h in _copied_hashes and source["priority"] > 1:
                stats["duplicate"] += 1
                manifest.append({
                    "action": "DUPLICATE",
                    "source": str(src_file),
                    "original": _copied_hashes[h],
                    "hash": h[:12],
                })
                continue

            # Copy file
            try:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src_file), str(dest_file))
                _copied_hashes[h] = str(dest_file)
                stats["copied"] += 1
                stats["files_by_source"][name] = stats["files_by_source"].get(name, 0) + 1
                file_count += 1
                manifest.append({
                    "action": "COPY",
                    "source": str(src_file),
                    "dest": str(dest_file),
                    "hash": h[:12],
                    "size_kb": round(src_file.stat().st_size / 1024, 1),
                })
                if file_count % 100 == 0:
                    print(f"  ... {file_count} files copied from {name}")
            except Exception as e:
                stats["errors"] += 1
                manifest.append({
                    "action": "ERROR",
                    "source": str(src_file),
                    "error": str(e),
                })

    print(f"  ✅ {file_count} files from {name}")


def scan_additional_jarvis_docs() -> list[dict]:
    """Scan for any additional JARVIS/AI related documents not in main projects."""
    additional = []
    search_dirs = [
        Path("C:/Users/Mobar/OneDrive"),
        Path("C:/Users/Mobar/Downloads"),
    ]
    jarvis_patterns = re.compile(
        r'jarvis|brainiac|singularity|agency|skycore|gane|mythos|kidgenius',
        re.IGNORECASE
    )

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(search_dir):
                dirnames[:] = [d for d in dirnames if not should_skip_dir(d)]
                depth = len(Path(dirpath).relative_to(search_dir).parts)
                if depth > 4:  # limit depth to avoid crawling everything
                    dirnames.clear()
                    continue
                for filename in filenames:
                    if any(filename.endswith(ext) for ext in ['.md', '.txt', '.py', '.ps1']):
                        if jarvis_patterns.search(filename) or jarvis_patterns.search(dirpath):
                            fp = Path(dirpath) / filename
                            if fp.stat().st_size < 5 * 1024 * 1024:
                                additional.append({
                                    "path": str(fp),
                                    "filename": filename,
                                    "dir": dirpath,
                                })
        except PermissionError:
            pass

    return additional


def build_full_index(manifest: list[dict]) -> str:
    """Build a full text index of all source Python files for requirement mining."""
    index_lines = []
    index_lines.append("# JARVIS UNIFIED — Full Python Module Index")
    index_lines.append(f"# Generated: {datetime.now(timezone.utc).isoformat()}")
    index_lines.append("")

    for root_dir, prefix in [
        (UNIFIED_ROOT, ""),
        (UNIFIED_ROOT / "skycore", "skycore/"),
        (UNIFIED_ROOT / "kidgenius", "kidgenius/"),
    ]:
        if not root_dir.exists():
            continue
        py_files = sorted(root_dir.rglob("*.py"))
        for py_file in py_files:
            rel = py_file.relative_to(UNIFIED_ROOT)
            index_lines.append(f"- {rel}")

    return "\n".join(index_lines)


def main():
    print("\n" + "🚀 " * 20)
    print("JARVIS UNIFIED BUILD SCRIPT")
    print("Merging all projects into one directory...")
    print("🚀 " * 20 + "\n")

    # Create unified root
    UNIFIED_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"✅ Created: {UNIFIED_ROOT}")

    # Create knowledge/ directory
    knowledge_dir = UNIFIED_ROOT / "knowledge"
    knowledge_dir.mkdir(exist_ok=True)

    manifest: list[dict] = []

    # Phase 1: Copy all sources
    for source in SOURCES:
        copy_source(source, manifest)

    # Phase 2: Copy requirements_master.md and other key docs
    key_docs = [
        Path("C:/Users/Mobar/jarvis-brainiac/memory/requirements_master.md"),
        Path("C:/Users/Mobar/jarvis-brainiac/UNIFIED_MANIFEST.md"),
        Path("C:/Users/Mobar/jarvis-brainiac/JARVIS_STATUS.md"),
        Path("C:/Users/Mobar/jarvis-brainiac/.antigravity_rules"),
    ]
    print("\n📋 Copying key documents to knowledge/...")
    for doc in key_docs:
        if doc.exists():
            dest = knowledge_dir / doc.name
            shutil.copy2(str(doc), str(dest))
            print(f"  ✅ {doc.name}")

    # Phase 3: Scan for additional JARVIS-related files
    print("\n🔍 Scanning for additional JARVIS documents...")
    additional = scan_additional_jarvis_docs()
    if additional:
        extra_dir = UNIFIED_ROOT / "_additional_finds"
        extra_dir.mkdir(exist_ok=True)
        for item in additional:
            src = Path(item["path"])
            dest = extra_dir / item["filename"]
            if not dest.exists():
                try:
                    shutil.copy2(str(src), str(dest))
                except Exception:
                    pass
        print(f"  ✅ Found {len(additional)} additional JARVIS-related files")

    # Phase 4: Save manifest
    manifest_path = UNIFIED_ROOT / "_MERGE_MANIFEST.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
            "files": manifest,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n✅ Manifest saved: {manifest_path}")

    # Phase 5: Build full index
    index_content = build_full_index(manifest)
    index_path = UNIFIED_ROOT / "knowledge" / "module_index.md"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_content)
    print(f"✅ Module index: {index_path}")

    # Phase 6: Create JARVIS_UNIFIED/README.md
    readme_content = f"""# JARVIS UNIFIED — Complete Merged Project
Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}

## Statistics
- **Files copied:** {stats['copied']}
- **Sources merged:** {len(SOURCES)}
- **Duplicates skipped:** {stats['duplicate']}
- **Errors:** {stats['errors']}

## Sources Merged
| Source | Files |
|--------|-------|
""" + "\n".join(
        f"| {name} | {count} |"
        for name, count in stats["files_by_source"].items()
    ) + f"""

## Structure
```
JARVIS_UNIFIED/
├── jarvis_brainiac/         ← Core Python package
├── godskill_server/         ← REST API (18 endpoints)
├── tests/                   ← All tests
├── skycore/                 ← Drone system (253 modules)
├── kidgenius/               ← Educational platform
├── knowledge/               ← Requirements + index
│   ├── requirements_master.md  ← 88 requirements
│   └── module_index.md         ← All Python files
├── _archive/                ← Historical versions
├── _additional_finds/       ← Extra discovered files
└── _MERGE_MANIFEST.json     ← Full merge log
```

## Quick Start
```powershell
cd C:\\Users\\Mobar\\JARVIS_UNIFIED
python -m pytest tests/ -v
python godskill_server/server.py
```
"""
    readme_path = UNIFIED_ROOT / "README_UNIFIED.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)

    # Final report
    print("\n" + "=" * 60)
    print("✅ JARVIS UNIFIED BUILD COMPLETE")
    print("=" * 60)
    print(f"📁 Location:    {UNIFIED_ROOT}")
    print(f"📄 Files:       {stats['copied']}")
    print(f"🔁 Duplicates:  {stats['duplicate']}")
    print(f"⏭️  Skipped:     {stats['skipped_ext'] + stats['skipped_size']}")
    print(f"❌ Errors:      {stats['errors']}")
    print("")
    print("Per-source breakdown:")
    for name, count in stats["files_by_source"].items():
        print(f"  {name}: {count} files")
    print("")
    print(f"🧠 Requirements: {UNIFIED_ROOT / 'knowledge' / 'requirements_master.md'}")
    print(f"📋 Manifest:     {UNIFIED_ROOT / '_MERGE_MANIFEST.json'}")
    print(f"📖 README:       {readme_path}")


if __name__ == "__main__":
    main()
