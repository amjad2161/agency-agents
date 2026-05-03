# JARVIS Satellite Repos — External Reference Repositories

This folder mirrors 5 external GitHub repos used by JARVIS for capability extension:
patterns, skills, and reference implementations.

## Inventory

| Repo | Files | Purpose | Source |
|---|---:|---|---|
| `decepticon/` | 686 | PurpleAILAB AI red-team patterns | github.com/PurpleAILAB/decepticon |
| `docker-android/` | 39 | HQarroum dockerized Android emulator | github.com/HQarroum/docker-android |
| `gane/` | 19 | amjad2161 navigation primitives | github.com/amjad2161/gane |
| `paper2code/` | 67 | PrathamLearnsToCode paper→code | github.com/PrathamLearnsToCode/paper2code |
| `saymotion/` | 21 | amjad2161 3D animation primitives | github.com/amjad2161/saymotion |

**Total** — 832 files, ~41 MB

## Sync from local mirror

If `C:\Users\User\Downloads\jarvis brainiac\integrations\external_repos\` already
contains these (it does, from the v26 build), run:

```powershell
$src = "C:\Users\User\Downloads\jarvis brainiac\integrations\external_repos"
$dst = "C:\Users\User\agency\integrations\external_repos"
foreach ($r in 'decepticon','docker-android','gane','paper2code','saymotion') {
    robocopy "$src\$r" "$dst\$r" /MIR /NFL /NDL /NP /R:1 /W:1
}
```

Or run the bundled `SYNC_SATELLITES.ps1` in this folder.

## Re-clone from GitHub

```powershell
$dst = "C:\Users\User\agency\integrations\external_repos"
git clone https://github.com/PurpleAILAB/decepticon       "$dst\decepticon"
git clone https://github.com/HQarroum/docker-android      "$dst\docker-android"
git clone https://github.com/amjad2161/gane               "$dst\gane"
git clone https://github.com/PrathamLearnsToCode/paper2code "$dst\paper2code"
git clone https://github.com/amjad2161/saymotion          "$dst\saymotion"
```

## Provenance

Originally pulled in V26 build (session `local_04c5be85-c7f9-436b-ac8d-73130ac82fa3`).
Re-mirrored 2026-05-03 during 100% audit verification.
