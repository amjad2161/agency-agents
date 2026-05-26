import pathlib, json, sys

root = pathlib.Path('.')

# 1. Navigation modules
nav_root = root / 'runtime' / 'agency' / 'navigation'
nav_stats = {}
nav_total = 0
if nav_root.exists():
    for f in sorted(nav_root.glob('*.py')):
        lines = f.read_text(encoding='utf-8', errors='replace').split('\n')
        classes = [l.split('(')[0].replace('class ','').strip() for l in lines if l.startswith('class ')]
        nav_stats[f.stem] = len(classes)
        nav_total += len(classes)
print("NAVIGATION:", nav_total, "classes")
for k, v in nav_stats.items():
    print(f"  {k}: {v} classes")

# 2. Agent divisions (YAML files per folder)
print("\nAGENT DIVISIONS:")
divisions = ['engineering','design','marketing','sales','ai','finance',
             'game-development','academic','testing','specialized','spatial-computing','support',
             'science','strategy','product','project-management','paid-media']
total_agents = 0
for div in divisions:
    d = root / div
    if d.exists():
        agents = list(d.rglob('*.md')) + list(d.rglob('*.yaml')) + list(d.rglob('*.yml'))
        count = len([a for a in agents if a.stat().st_size > 200])
        total_agents += count
        if count > 0:
            print(f"  {div}: {count} agents")
print(f"  TOTAL: ~{total_agents} agents")

# 3. Runtime packages
print("\nRUNTIME PACKAGES:")
runtime = root / 'runtime' / 'agency'
if runtime.exists():
    for d in sorted(runtime.iterdir()):
        if d.is_dir() and (d / '__init__.py').exists():
            py_files = list(d.rglob('*.py'))
            print(f"  {d.name}: {len(py_files)} py files")

# 4. Key system files
print("\nKEY SYSTEM FILES:")
key_files = [
    'JARVIS_SUPREME.py',
    'JARVIS_BRAINIAC.py',
    'singularity_bootstrap.py',
    'jarvis_brainiac/__init__.py',
    'jarvis_brainiac/memory.py',
    'jarvis_brainiac/heartbeat.py',
    'jarvis_brainiac/agent_forge.py',
    'jarvis_brainiac/agent_registry.py',
    'jarvis_brainiac/orchestrator.py',
    'godskill_server/server.py',
    'jarvis_singularity/__init__.py',
    'jarvis_os/__init__.py',
    'runtime/agency/singularity_core.py',
]
for kf in key_files:
    p = root / kf
    if p.exists():
        lines = len(p.read_text(encoding='utf-8', errors='replace').split('\n'))
        size = p.stat().st_size
        print(f"  {kf}: {lines} lines, {size//1024}KB")

# 5. GitHub repos cloned
print("\nCLONED REPOS:")
clones = root / 'github_clones'
if clones.exists():
    repos = [d for d in clones.iterdir() if d.is_dir()]
    print(f"  {len(repos)} repositories")
    for r in repos[:10]:
        print(f"    - {r.name}")

# 6. Subsystems from JARVIS_SUPREME
print("\nSUBSYSTEMS (from JARVIS_SUPREME):")
sup = (root / 'JARVIS_SUPREME.py').read_text(encoding='utf-8', errors='replace')
import re
subs = re.findall(r'Subsystem\("([^"]+)"', sup)
for s in subs:
    print(f"  - {s}")
