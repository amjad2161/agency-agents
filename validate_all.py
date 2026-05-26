"""
AST Validation script — validates all new Python files are syntactically correct
Run: python validate_all.py
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parent

FILES_TO_VALIDATE = [
    "jarvis_brainiac/unified_memory_engine.py",
    "godskill_server/server.py",
    "tests/test_unified_memory.py",
    "build_unified.py",
]

print("=" * 60)
print("JARVIS UNIFIED — AST Validation")
print("=" * 60)

all_ok = True
for rel in FILES_TO_VALIDATE:
    path = ROOT / rel
    if not path.exists():
        print(f"❌ MISSING: {rel}")
        all_ok = False
        continue
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        
        # Count functions and classes
        funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        
        print(f"✅ {rel}")
        print(f"   Lines: {len(src.splitlines())}  Functions: {len(funcs)}  Classes: {len(classes)}")
        if classes:
            print(f"   Classes: {', '.join(classes)}")
    except SyntaxError as e:
        print(f"❌ SYNTAX ERROR in {rel}: {e}")
        all_ok = False
    except Exception as e:
        print(f"❌ ERROR in {rel}: {e}")
        all_ok = False

print()
print("=" * 60)

# Check requirements_master.md
req_file = ROOT / "memory" / "requirements_master.md"
if req_file.exists():
    content = req_file.read_text(encoding="utf-8")
    req_count = content.count("REQ-")
    print(f"✅ memory/requirements_master.md — {req_count} requirement IDs")
else:
    print("❌ memory/requirements_master.md MISSING")
    all_ok = False

# Check UNIFIED_MANIFEST.md
manifest = ROOT / "UNIFIED_MANIFEST.md"
if manifest.exists():
    print(f"✅ UNIFIED_MANIFEST.md — {manifest.stat().st_size} bytes")
else:
    print("❌ UNIFIED_MANIFEST.md MISSING")
    all_ok = False

# Check BUILD_JARVIS_UNIFIED.ps1
ps1 = ROOT / "BUILD_JARVIS_UNIFIED.ps1"
if ps1.exists():
    print(f"✅ BUILD_JARVIS_UNIFIED.ps1 — {ps1.stat().st_size} bytes")
else:
    print("❌ BUILD_JARVIS_UNIFIED.ps1 MISSING")
    all_ok = False

# Validate unified_memory_engine has 105+ requirements
ume_path = ROOT / "jarvis_brainiac" / "unified_memory_engine.py"
if ume_path.exists():
    src = ume_path.read_text(encoding="utf-8")
    req_entries = src.count('"req_id":')
    epoch_entries = src.count('"epoch":')
    print(f"✅ unified_memory_engine.py — {req_entries} built-in requirements, {len(src.splitlines())} lines")
    if req_entries < 100:
        print(f"  ⚠️  Expected 105+ requirements, found {req_entries}")

# Validate server.py has all 7 unified endpoints
server_path = ROOT / "godskill_server" / "server.py"
if server_path.exists():
    src = server_path.read_text(encoding="utf-8")
    unified_endpoints = [
        "api_unified_stats", "api_unified_requirements", "api_unified_search",
        "api_unified_timeline", "api_unified_remember", "api_unified_add_requirement",
        "api_unified_export"
    ]
    missing = [ep for ep in unified_endpoints if ep not in src]
    if missing:
        print(f"❌ server.py missing endpoints: {missing}")
        all_ok = False
    else:
        print(f"✅ server.py — all 7 unified endpoints present")

print()
print("=" * 60)
if all_ok:
    print("✅ ALL VALIDATIONS PASSED")
else:
    print("❌ SOME VALIDATIONS FAILED")
print("=" * 60)
sys.exit(0 if all_ok else 1)
