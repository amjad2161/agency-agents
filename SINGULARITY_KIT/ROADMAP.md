# JARVIS SINGULARITY - ROADMAP

Post-merge next steps. Each block is independent — pick what matters.

## P0 — Validate the unification

```cmd
:: Confirm structure + run smoke imports
LAUNCH_VERIFY.cmd

:: Bootstrap Python venv + install runtime + smoke test
LAUNCH_POST_MERGE_SETUP.cmd
```

Expected: PASS on agents/, runtime/, jarvis_brainiac/, jarvis_os/, godskill_server/, JARVIS_OMEGA/. Smoke imports of `jarvis_brainiac`, `jarvis_os`, `agency` should all return [OK].

## P1 — Wire to GitHub

```cmd
cd C:\Users\User\JARVIS_SINGULARITY
git remote add origin https://github.com/<your-handle>/jarvis-singularity.git
git branch -M main
git push -u origin main
```

If repo doesn't exist yet, create it first via gh CLI:
```cmd
gh repo create jarvis-singularity --private --source . --push
```

## P2 — Resolve the embedded JARVIS_SINGULARITY/ from Kimi audit

The Kimi audit had its own historical `JARVIS_SINGULARITY/` folder. After merge, `C:\Users\User\JARVIS_SINGULARITY\JARVIS_SINGULARITY\` exists as a nested archive. Decide:
- **Keep** as historical reference (recommended)
- **Promote** anything unique into top-level
- **Archive** to `_archive/kimi_singularity_v1/`

## P3 — Reconcile duplicate jarvis_brainiac entries

Top level has both `jarvis_brainiac/` (active package) and `.jarvis_brainiac/` (dotfile from agency). Keep the package, decide what `.jarvis_brainiac/` is — likely runtime state. Move to `var/state/.jarvis_brainiac/` if it's runtime-mutable.

## P4 — Index the 144+ agent personas

Generate `AGENT_INDEX.md` with a single navigable list across all 12 agency divisions. Helps anyone (and Claude) find personas fast.

```powershell
# Quick generator
$divs = 'design','engineering','marketing','sales','support','testing','product','project-management','strategy','spatial-computing','academic','science','specialized','finance','game-development','paid-media'
$root = 'C:\Users\User\JARVIS_SINGULARITY\agents'
$out  = 'C:\Users\User\JARVIS_SINGULARITY\AGENT_INDEX.md'
"# Agent Index" | Out-File $out -Encoding utf8
foreach ($d in $divs) {
    $p = Join-Path $root $d
    if (Test-Path $p) {
        "" | Add-Content $out
        "## $d" | Add-Content $out
        Get-ChildItem $p -File -Filter *.md | Sort-Object Name | ForEach-Object {
            "- [$($_.BaseName)](agents/$d/$($_.Name))" | Add-Content $out
        }
    }
}
```

## P5 — Test the runtime end-to-end

```cmd
.\.venv\Scripts\Activate.ps1
agency list                          :: should show 340+ skills
agency run "say hello"               :: smoke route
agency serve                         :: chat UI on http://127.0.0.1:8765
```

## P6 — Validate godskill_nav_v11 tier READMEs

Check each tier (1-7) has its README + concrete implementation files:

```powershell
$tiers = 'tier1_satellite','tier2_indoor','tier3_underwater','tier4_denied','tier5_fusion','tier6_ai','tier7_offline_data'
foreach ($t in $tiers) {
    $path = "C:\Users\User\JARVIS_SINGULARITY\JARVIS_OMEGA\godskill_navigation\$t"
    if (Test-Path $path) {
        $files = Get-ChildItem $path -File
        Write-Host "$t : $($files.Count) files"
    } else {
        Write-Host "$t : MISSING" -ForegroundColor Red
    }
}
```

## P7 — Bridges import audit

`bridges/` contains integrations to Blender, Dobot, Instagram, Lyra2, gitnexus, metaverse, neural_avatar, rtk_ai, scifi_ui, etc. Verify each imports cleanly under unified PYTHONPATH.

```python
# bridges_audit.py
import importlib, traceback, sys
bridges = ['blender','dobot','instagram','lyra2','gitnexus','metaverse','neural_avatar','rtk_ai','scifi_ui','cubesandbox','cadam','jarvs','matrix_wallpaper','personas','working_demos']
for b in bridges:
    try:
        importlib.import_module(f'jarvis_brainiac.bridges.{b}')
        print(f'[OK]   {b}')
    except Exception as e:
        print(f'[FAIL] {b}: {e}')
```

## P8 — Lock the freeze point

Tag the post-merge state:
```cmd
cd C:\Users\User\JARVIS_SINGULARITY
git tag -a v0.1.0-singularity -m "Post-merge unified baseline"
```

## P9 — Clean source folders (optional)

After confirming JARVIS_SINGULARITY is fully functional:
- Archive sources to `D:\archive\jarvis_sources_pre_unify_2026-05-03\`
- Or leave them — they're idempotent inputs to the merge
- Do NOT delete until verify + setup pass cleanly

## P10 — Continuous singularity

Add a scheduled task to re-run merge nightly:
```cmd
schtasks /create /tn "JARVIS_Singularity_Sync" /tr "powershell -ExecutionPolicy Bypass -File 'C:\Users\User\OneDrive\מסמכים\Claude\Projects\jarvis brainiac\SINGULARITY_KIT\MERGE_SINGULARITY.ps1'" /sc daily /st 03:00
```
