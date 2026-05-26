# SATELLITE REPOS — Integration Decision Matrix

**Date**: 2026-05-01 · **Operator**: Amjad (`mobarsham@gmail.com`)
**Context**: User listed 11 third-party URLs for integration into JARVIS BRAINIAC. Below is the verdict per repo: **PULL** / **REFERENCE** / **SKIP**, with rationale, license check, and integration plan.

---

## Decision Framework

| Verdict | Meaning | Action |
|---------|---------|--------|
| **PULL** | Useful primary or sub-component; integrate directly into the agency tree | `git submodule add` → wire into `external_repos/` + adapter in `integrations/` |
| **REFERENCE** | Useful idea/code-pattern, but full integration would bloat or conflict | Document API + capabilities in `docs/`; cite when relevant |
| **SKIP** | Out of scope, license conflict, or already covered by an existing module | Note rationale; don't pull |

---

## Per-Repo Verdicts

### 1. `1jehuang/jcode`
- **URL**: https://github.com/1jehuang/jcode
- **Stated role**: Code-generation utility
- **Verdict**: **REFERENCE** (uncertainty: MEDIUM — repo content not deeply audited in this session)
- **Rationale**: Agency already has `engineering/code-reviewer.md`, `engineering/senior-developer.md`, and `runtime/agency/` for code-gen orchestration. Pull only if jcode offers a unique pattern (e.g., AST-aware diff editing) not already covered.
- **Integration plan**: Add a stub `integrations/jcode/README.md` describing how to call jcode CLI from a JARVIS engineering agent if the user opts-in.

### 2. `cobalt.tools` (cobalt-tools/cobalt)
- **URL**: https://cobalt.tools/ → https://github.com/imputnet/cobalt
- **Stated role**: Media (video/audio) downloader
- **Verdict**: **REFERENCE** (license: AGPLv3 — viral copyleft)
- **Rationale**: AGPLv3 forces same license on any project that links it. Integrating into JARVIS would force the entire project to AGPL. Use as **external service** (call cobalt's hosted API) instead.
- **Integration plan**: `runtime/agency/media_downloader.py` adapter that POSTs to `https://api.cobalt.tools/api/json` — no source-level dependency.

### 3. `PurpleAILAB/Decepticon`
- **URL**: https://github.com/PurpleAILAB/Decepticon
- **Stated role**: AI red-teaming / adversarial agents
- **Verdict**: **PULL** as submodule (uncertainty: LOW — well-aligned with `engineering/llm-red-teamer.md`)
- **Rationale**: Direct fit for agency's existing Red Team and Prompt Injection Defender agents. Adds proven adversarial test suite.
- **Integration plan**:
  ```bash
  git submodule add https://github.com/PurpleAILAB/Decepticon external_repos/decepticon
  # Wire to engineering/llm-red-teamer.md via integrations/decepticon/adapter.py
  ```

### 4. `localsend/localsend`
- **URL**: https://github.com/localsend/localsend
- **Stated role**: Cross-device file sharing (Apache-2.0)
- **Verdict**: **REFERENCE**
- **Rationale**: Useful for the "cloud + local sync as one unit" requirement, but it's an end-user app, not a library. Use its protocol (LocalSend Protocol v2) as inspiration for `cloud_sync.py` peer-to-peer mode.
- **Integration plan**: Document protocol in `docs/SYNC_PROTOCOLS.md`. Optional future: implement LocalSend-compatible endpoint in `cloud_sync.py` for LAN device sync.

### 5. `blader/humanizer`
- **URL**: https://github.com/blader/humanizer
- **Stated role**: AI text → "humanized" output
- **Verdict**: **SKIP** (uncertainty: LOW)
- **Rationale**: Conflicts with brand-voice integrity. Agency's `brand-voice-enforcement` skill is the canonical voice layer. Adding a "humanizer" creates two competing voice transformations and risks evasion-of-detection use cases that violate platform ToS.

### 6. `fspecii/ace-step-ui`
- **URL**: https://github.com/fspecii/ace-step-ui
- **Stated role**: Music generation UI (likely a Gradio/Streamlit wrapper around ACE-Step model)
- **Verdict**: **REFERENCE**
- **Rationale**: Useful as creative-suite extension, but heavyweight (model weights + GPU). Better wired as an optional service (`docker run`) than embedded.
- **Integration plan**: `docs/CREATIVE_SUITE.md` documents how to launch ace-step-ui Docker container and invoke from a JARVIS music-production agent.

### 7. `HQarroum/docker-android`
- **URL**: https://github.com/HQarroum/docker-android
- **Stated role**: Containerized Android emulator
- **Verdict**: **PULL** as submodule
- **Rationale**: Required for `engineering/mobile-app-builder.md` (Android testing) and `automation` agents (mobile RPA).
- **Integration plan**:
  ```bash
  git submodule add https://github.com/HQarroum/docker-android external_repos/docker-android
  # docs/MOBILE_TESTING.md: docker compose up + adb bridge to JARVIS
  ```
- **Note**: Already referenced in `audit_artifacts/from_zip3/` per prior singularity audit.

### 8. `playcanvas/supersplat`
- **URL**: https://github.com/playcanvas/supersplat
- **Stated role**: 3D Gaussian Splatting editor
- **Verdict**: **REFERENCE**
- **Rationale**: Niche tool for the spatial-computing division. Useful for `xr-immersive-developer.md` workflows but not core. Embedding it would bloat repo with WebGL/three.js bundle.
- **Integration plan**: `spatial-computing/playcanvas-supersplat-adapter.md` documents API for invoking via web UI.

### 9. `PrathamLearnsToCode/paper2code`
- **URL**: https://github.com/PrathamLearnsToCode/paper2code
- **Stated role**: Convert academic papers → runnable code
- **Verdict**: **PULL** as submodule
- **Rationale**: Strong fit with `science/`, `academic/`, `bio-research/` divisions. Already noted in prior singularity audit (`workspace_live/jarvis/external_repos/paper2code`).
- **Integration plan**:
  ```bash
  git submodule add https://github.com/PrathamLearnsToCode/paper2code external_repos/paper2code
  # academic/paper2code-engineer.md (new agent)
  ```

### 10. `skills.sh/browserbase/skills/autobrowse`
- **URL**: https://skills.sh/browserbase/skills/autobrowse
- **Stated role**: Browserbase autonomous web-browsing skill
- **Verdict**: **REFERENCE** (it's a skill catalog entry, not a repo)
- **Rationale**: Already covered by Anthropic's Claude-in-Chrome MCP (this conversation has access). Add a pointer in `integrations/browserbase/README.md` for users who prefer Browserbase over Chrome MCP.

### 11. `LycidPsyche/auto-browser`
- **URL**: https://github.com/LycidPsyche/auto-browser
- **Stated role**: Headless browser automation
- **Verdict**: **REFERENCE**
- **Rationale**: Same niche as Browserbase / Playwright / Chrome MCP. Pick one as primary; the rest are alternates. Agency's `runtime/agency/browser.py` already provides browser primitives.
- **Integration plan**: Mention in `docs/BROWSER_AUTOMATION.md` as alternative for users without Chrome MCP.

---

## Summary

| Repo | Verdict |
|------|---------|
| jcode | REFERENCE |
| cobalt.tools | REFERENCE (API only — AGPL avoidance) |
| Decepticon | **PULL** |
| localsend | REFERENCE |
| humanizer | **SKIP** |
| ace-step-ui | REFERENCE |
| docker-android | **PULL** |
| supersplat | REFERENCE |
| paper2code | **PULL** |
| autobrowse | REFERENCE |
| auto-browser | REFERENCE |

**3 PULLs**, **7 REFERENCEs**, **1 SKIP**. Total submodule additions queued: 3 (Decepticon, docker-android, paper2code). Each is gated behind operator approval before actual `git submodule add` runs (license + size review).

---

## Operator Approval Required

To execute the **PULL** verdicts, run from the repo root:

```bash
# After review:
git submodule add https://github.com/PurpleAILAB/Decepticon         external_repos/decepticon
git submodule add https://github.com/HQarroum/docker-android        external_repos/docker-android
git submodule add https://github.com/PrathamLearnsToCode/paper2code external_repos/paper2code
git submodule update --init --recursive
git commit -m "feat: integrate satellite repos (Decepticon, docker-android, paper2code)"
```

> ⚠️ This session does NOT execute the submodule adds automatically — that's an irreversible cloud-write that needs your explicit go-ahead.
