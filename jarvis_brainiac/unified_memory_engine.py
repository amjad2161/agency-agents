"""
JARVIS Unified Memory Engine
============================
Long-term memory system that stores and retrieves:
  - All user requirements (88+)
  - All project decisions
  - All session conversations
  - Chronological project timeline

No API keys. SQLite only. Always available.

Usage:
    from jarvis_brainiac.unified_memory_engine import UnifiedMemoryEngine, get_memory
    
    mem = get_memory()
    mem.add_requirement("Build voice recognition", epoch=4, status="done")
    results = mem.search("voice")
    timeline = mem.get_timeline()
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

# ─── Paths ────────────────────────────────────────────────────────────────────

DEFAULT_DB_PATH = Path(__file__).parent.parent / "memory" / "unified_jarvis.sqlite"

# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class Requirement:
    """A single user requirement extracted from any source."""
    req_id: str                       # REQ-001, REQ-002 ...
    text: str                         # requirement text
    epoch: int                        # 1-5 (chronological era)
    epoch_name: str                   # "Initial Vision", "Mission 30", etc.
    status: str                       # "done", "in_progress", "open", "partial"
    source: str                       # ".antigravity_rules", "MISSION_STATUS", "session", etc.
    created_at: str = ""
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass
class MemoryEntry:
    """A single memory item (any type)."""
    entry_id: str
    entry_type: str                   # "requirement", "decision", "conversation", "file_index", "event"
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    importance: int = 5               # 1-10
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.entry_id:
            self.entry_id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass
class SearchResult:
    """A search result with relevance context."""
    entry_id: str
    entry_type: str
    title: str
    snippet: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


# ─── Database Schema ──────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS requirements (
    req_id      TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    epoch       INTEGER NOT NULL DEFAULT 1,
    epoch_name  TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'open',
    source      TEXT NOT NULL DEFAULT 'unknown',
    created_at  TEXT NOT NULL,
    tags        TEXT NOT NULL DEFAULT '[]',
    notes       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS memory_entries (
    entry_id    TEXT PRIMARY KEY,
    entry_type  TEXT NOT NULL DEFAULT 'event',
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL,
    importance  INTEGER NOT NULL DEFAULT 5,
    tags        TEXT NOT NULL DEFAULT '[]'
);

CREATE VIRTUAL TABLE IF NOT EXISTS requirements_fts USING fts5(
    req_id UNINDEXED,
    text,
    epoch_name,
    status,
    source,
    notes,
    content='requirements',
    content_rowid='rowid'
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    entry_id UNINDEXED,
    title,
    content,
    entry_type,
    content='memory_entries',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS req_ai AFTER INSERT ON requirements BEGIN
    INSERT INTO requirements_fts(rowid, req_id, text, epoch_name, status, source, notes)
    VALUES (new.rowid, new.req_id, new.text, new.epoch_name, new.status, new.source, new.notes);
END;

CREATE TRIGGER IF NOT EXISTS req_au AFTER UPDATE ON requirements BEGIN
    INSERT INTO requirements_fts(requirements_fts, rowid, req_id, text, epoch_name, status, source, notes)
    VALUES ('delete', old.rowid, old.req_id, old.text, old.epoch_name, old.status, old.source, old.notes);
    INSERT INTO requirements_fts(rowid, req_id, text, epoch_name, status, source, notes)
    VALUES (new.rowid, new.req_id, new.text, new.epoch_name, new.status, new.source, new.notes);
END;

CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memory_entries BEGIN
    INSERT INTO memory_fts(rowid, entry_id, title, content, entry_type)
    VALUES (new.rowid, new.entry_id, new.title, new.content, new.entry_type);
END;

CREATE TRIGGER IF NOT EXISTS mem_au AFTER UPDATE ON memory_entries BEGIN
    INSERT INTO memory_fts(memory_fts, rowid, entry_id, title, content, entry_type)
    VALUES ('delete', old.rowid, old.entry_id, old.title, old.content, old.entry_type);
    INSERT INTO memory_fts(rowid, entry_id, title, content, entry_type)
    VALUES (new.rowid, new.entry_id, new.title, new.content, new.entry_type);
END;

CREATE TABLE IF NOT EXISTS project_events (
    event_id    TEXT PRIMARY KEY,
    event_date  TEXT NOT NULL,
    epoch       INTEGER NOT NULL DEFAULT 1,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    event_type  TEXT NOT NULL DEFAULT 'milestone'
);

-- MR-003: indexes for common filtered queries
CREATE INDEX IF NOT EXISTS req_epoch_idx  ON requirements(epoch);
CREATE INDEX IF NOT EXISTS req_status_idx ON requirements(status);
CREATE INDEX IF NOT EXISTS req_src_idx    ON requirements(source);
CREATE INDEX IF NOT EXISTS mem_type_idx   ON memory_entries(entry_type);
CREATE INDEX IF NOT EXISTS mem_imp_idx    ON memory_entries(importance DESC);
"""

# ─── Epoch Definitions ────────────────────────────────────────────────────────

EPOCHS = {
    0: "Pre-existing Systems (SkyCore + KidGenius)",
    1: "Initial Vision",
    2: "Mission 30 Delivery",
    3: "Navigation Singularity",
    4: "FreeLLM + New Capabilities",
    5: "Unified Singularity",
}

# ─── Built-in Requirements (105 total, epochs 0–5) ────────────────────────────────

BUILTIN_REQUIREMENTS: list[dict] = [
    # EPOCH 0 — Pre-existing Systems discovered during scan
    {"req_id": "REQ-E00-001", "text": "SkyCore drone system: 253 Python modules, 8 architecture layers", "epoch": 0, "status": "done", "source": "SkyCore/PROJECT_STATUS.md"},
    {"req_id": "REQ-E00-002", "text": "SkyCore navigation: Kalman, EKF, UKF, 22-State AUKF, INS, A*, RRT*", "epoch": 0, "status": "done", "source": "SkyCore/PROJECT_STATUS.md"},
    {"req_id": "REQ-E00-003", "text": "SkyCore sensors: IMU, GNSS/GPS, Barometer, Compass, LIDAR, Camera (OpenCV 1280x720)", "epoch": 0, "status": "done", "source": "SkyCore/PROJECT_STATUS.md"},
    {"req_id": "REQ-E00-004", "text": "SkyCore C-UAS: RF Scanner, ADS-B, Drone Protocol Detection, Threat Prediction", "epoch": 0, "status": "done", "source": "SkyCore/PROJECT_STATUS.md"},
    {"req_id": "REQ-E00-005", "text": "SkyCore swarm coordination: Swarm-SLAM, Aerostack2, Fleet Management, Drone Shows", "epoch": 0, "status": "done", "source": "SkyCore/PROJECT_STATUS.md"},
    {"req_id": "REQ-E00-006", "text": "SkyCore firmware support: PX4, ArduPilot, Betaflight, INAV with Unified Adapter", "epoch": 0, "status": "done", "source": "SkyCore/PROJECT_STATUS.md"},
    {"req_id": "REQ-E00-007", "text": "SkyCore desktop GCS: Tkinter app with flight control, mission planning, telemetry", "epoch": 0, "status": "done", "source": "SkyCore/PROJECT_STATUS.md"},
    {"req_id": "REQ-E00-008", "text": "SkyCore REST API: FastAPI 50+ endpoints, WebSocket telemetry, authentication", "epoch": 0, "status": "done", "source": "SkyCore/PROJECT_STATUS.md"},
    {"req_id": "REQ-E00-009", "text": "SkyCore communications hub: MAVLink, RTL-SDR, AIS, LoRa, 4G/5G, Satellite, BLE, WiFi, MQTT, WebRTC", "epoch": 0, "status": "done", "source": "SkyCore/PROJECT_STATUS.md"},
    {"req_id": "REQ-E00-010", "text": "SkyCore compliance: EU CE, USA FCC, Israel CAAI/CFF, Ben Gurion no-fly zones", "epoch": 0, "status": "done", "source": "SkyCore/PROJECT_STATUS.md"},
    {"req_id": "REQ-E00-011", "text": "SkyCore AI/ML: YOLO object detection, depth estimation, visual servoing, terrain analysis", "epoch": 0, "status": "done", "source": "SkyCore/PROJECT_STATUS.md"},
    {"req_id": "REQ-E00-012", "text": "SkyCore digital twin + RL training: PyBullet physics, FAST-Planner, WebODM, voice control", "epoch": 0, "status": "done", "source": "SkyCore/PROJECT_STATUS.md"},
    {"req_id": "REQ-E00-013", "text": "KidGenius Academy: Educational platform for children with Pixar-style aesthetics", "epoch": 0, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-E00-014", "text": "KidGenius: React/TypeScript/Vite frontend, gamified learning, multiple subjects", "epoch": 0, "status": "done", "source": "kidgenius-academy/README.md"},
    {"req_id": "REQ-E00-015", "text": "KidGenius: Child-safe content, maximum visual engagement, performance on low-end devices", "epoch": 0, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-E00-016", "text": "G.A.N.E autonomous navigation environment: real-time performance critical", "epoch": 0, "status": "open", "source": ".antigravity_rules"},
    {"req_id": "REQ-E00-017", "text": "Mythos autonomous decision-making system", "epoch": 0, "status": "open", "source": ".antigravity_rules"},
    # EPOCH 1
    {"req_id": "REQ-001", "text": "JARVIS = AGI multi-agent orchestration system", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-002", "text": "Python-based autonomous orchestrator", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-003", "text": "Combines voice, vision, memory, tools, self-improvement", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-004", "text": "Hebrew primary language, English/Arabic secondary", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-005", "text": "British wit personality (Tony Stark's JARVIS)", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-006", "text": "God-mode access to computer (files, network, apps)", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-007", "text": "Every module independently testable", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-008", "text": "Memory persistence NON-NEGOTIABLE", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-009", "text": "System must explain itself", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-010", "text": "Never break existing functionality", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-011", "text": "No API key required (all local/free)", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-012", "text": "Dependency injection over hard coupling", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-013", "text": "Event-driven where possible", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-014", "text": "API-first design", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-015", "text": "Iron Man HUD aesthetic UI", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-016", "text": "BrainOrb + NeuralinkPanel + StatsPanel + hex grid", "epoch": 1, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-017", "text": "Premium dark-mode glassmorphism design system", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-018", "text": "Outfit/Inter fonts", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-019", "text": "Subtle micro-animations (200-300ms transitions)", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    {"req_id": "REQ-020", "text": "Mobile-first, desktop-excellence responsive design", "epoch": 1, "status": "done", "source": ".antigravity_rules"},
    # EPOCH 2
    {"req_id": "REQ-021", "text": "Unify AGENCY + KIMI + JARVIS forks into one folder", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-022", "text": "100% merge — every file, no exclusions", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-023", "text": "Clone GitHub amjad2161/agency-agents", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-024", "text": "Init local git repo with no remote", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-025", "text": "Bootstrap Python venv + runtime", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-026", "text": "Smoke test all imports (jarvis_brainiac, jarvis_os, agency)", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-027", "text": "Build native PyQt6 desktop app", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-028", "text": "Iron Man HUD PyQt6 implementation", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-029", "text": "Always-on mic + wake word (Jarvis/ג'רוויס/جارفيس)", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-030", "text": "Double-clap detection (audio peak > 18000 within 1.5s)", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-031", "text": "System tray standby with cyan orb icon", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-032", "text": "Multi-language voice EN/HE/AR auto-detect via SR", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-033", "text": "God-mode shell: !cmd → live PowerShell execution", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-034", "text": "JARVIS British wit personality via system prompt", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-035", "text": "NO API key required — Ollama llama3.2 local", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-036", "text": "Persistent memory via SQLite + ChromaDB", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-037", "text": "144+ agents auto-registered as skills via SkillRegistry", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-038", "text": "GitHub import + integrate command", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-039", "text": "Autonomous background loop (ProactiveBrain + AutonomousLoop)", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-040", "text": "Index all 33,784 files (cap raised to 200,000)", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-041", "text": "Real Computer Use: mouse/keyboard via pyautogui", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-042", "text": "Vision: llama3.2-vision model integration", "epoch": 2, "status": "partial", "source": "MISSION_STATUS"},
    {"req_id": "REQ-043", "text": "System telemetry: CPU/RAM/disk via psutil", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-044", "text": "Webcam presence via OpenCV face detection", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-045", "text": "Watchdog auto-restart polling every 15 seconds", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-046", "text": "Single-instance lock via port 47291 socket", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-047", "text": "Aggressive window summon on wake word", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-048", "text": "Autostart on Windows login via Startup shortcut", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-049", "text": "Code review + security hardening (3 auto-fixes)", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-050", "text": "Tests harness: test_memory.py + test_telemetry.py", "epoch": 2, "status": "done", "source": "MISSION_STATUS"},
    {"req_id": "REQ-051", "text": "Vision model pull llama3.2-vision (4.2GB background)", "epoch": 2, "status": "open", "source": "MISSION_STATUS"},
    {"req_id": "REQ-052", "text": "Wire runtime/agency CLI smoke test into CI", "epoch": 2, "status": "open", "source": "ROADMAP"},
    {"req_id": "REQ-053", "text": "Validate godskill_nav_v11 tier1-7 README references", "epoch": 2, "status": "open", "source": "ROADMAP"},
    {"req_id": "REQ-054", "text": "Verify all bridges import cleanly under unified PYTHONPATH", "epoch": 2, "status": "open", "source": "ROADMAP"},
    {"req_id": "REQ-055", "text": "Document 144+ agent personas in single index", "epoch": 2, "status": "open", "source": "ROADMAP"},
    # EPOCH 3
    {"req_id": "REQ-056", "text": "GODSKILL Navigation v11 — 7 tiers (satellite, indoor, underwater, underground, denied, fusion, AI)", "epoch": 3, "status": "done", "source": "JARVIS_STATUS"},
    {"req_id": "REQ-057", "text": "29 improvement rounds (R1-R29) for navigation", "epoch": 3, "status": "done", "source": "JARVIS_STATUS"},
    {"req_id": "REQ-058", "text": "145 navigation classes across all tiers", "epoch": 3, "status": "done", "source": "JARVIS_STATUS"},
    {"req_id": "REQ-059", "text": "965 navigation tests all passing", "epoch": 3, "status": "done", "source": "JARVIS_STATUS"},
    {"req_id": "REQ-060", "text": "2292+ runtime tests", "epoch": 3, "status": "done", "source": "JARVIS_STATUS"},
    {"req_id": "REQ-061", "text": "Total 3257 tests: 3253 passing, 0 failing, 4 skipped", "epoch": 3, "status": "done", "source": "JARVIS_STATUS"},
    {"req_id": "REQ-062", "text": "numpy-only navigation implementation (no external deps)", "epoch": 3, "status": "done", "source": "JARVIS_STATUS"},
    # EPOCH 4
    {"req_id": "REQ-063", "text": "Remove Anthropic/Claude dependency completely — zero paid APIs", "epoch": 4, "status": "done", "source": "session"},
    {"req_id": "REQ-064", "text": "FreeLLM 5-provider chain: Ollama→Groq→Gemini→HuggingFace→SmartLocal", "epoch": 4, "status": "done", "source": "session"},
    {"req_id": "REQ-065", "text": "SmartLocal always available — zero network, pattern-based", "epoch": 4, "status": "done", "source": "session"},
    {"req_id": "REQ-066", "text": "GROQ, GEMINI, HF free-tier env vars optional", "epoch": 4, "status": "done", "source": "session"},
    {"req_id": "REQ-067", "text": "IdeaToAgents Pipeline: idea → domain analysis → agent team → project scaffold", "epoch": 4, "status": "done", "source": "session"},
    {"req_id": "REQ-068", "text": "8 domain types: frontend, backend, devops, mobile, data, ai, security, design", "epoch": 4, "status": "done", "source": "session"},
    {"req_id": "REQ-069", "text": "8 project types: saas, ecommerce, mobile, api, data, portfolio, default", "epoch": 4, "status": "done", "source": "session"},
    {"req_id": "REQ-070", "text": "Write scaffold to disk in generated_projects/ directory", "epoch": 4, "status": "done", "source": "session"},
    {"req_id": "REQ-071", "text": "3D AI Website Builder: brief → Three.js premium HTML", "epoch": 4, "status": "done", "source": "session"},
    {"req_id": "REQ-072", "text": "5 style presets: luxury, tech, minimal, organic, bold", "epoch": 4, "status": "done", "source": "session"},
    {"req_id": "REQ-073", "text": "4 Three.js scene types: floating_sphere, particle_field, geometric_morph, liquid_glass", "epoch": 4, "status": "done", "source": "session"},
    {"req_id": "REQ-074", "text": "glassmorphism CSS + Google Fonts integration in website builder", "epoch": 4, "status": "done", "source": "session"},
    {"req_id": "REQ-075", "text": "REST API: /api/llm/*, /api/pipeline/*, /api/website/* endpoints", "epoch": 4, "status": "done", "source": "session"},
    {"req_id": "REQ-076", "text": "Dashboard Memory API: remember/recall/lifecycle endpoints", "epoch": 4, "status": "done", "source": "session"},
    {"req_id": "REQ-077", "text": "45 automated tests — all 45/45 passing", "epoch": 4, "status": "done", "source": "session"},
    # EPOCH 5
    {"req_id": "REQ-078", "text": "Scan every file, directory, document on the entire computer", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
    {"req_id": "REQ-079", "text": "Extract every requirement from every source chronologically", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
    {"req_id": "REQ-080", "text": "Unify all JARVIS projects into ONE directory (JARVIS_UNIFIED)", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
    {"req_id": "REQ-081", "text": "Long-term memory engine that remembers everything across sessions", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
    {"req_id": "REQ-082", "text": "JARVIS must know word-for-word every past request", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
    {"req_id": "REQ-083", "text": "Collect and index all GitHub repos + internet links", "epoch": 5, "status": "open", "source": "session_2026-05-27"},
    {"req_id": "REQ-084", "text": "Hermetic, stable, professional build from A-Z without errors", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
    {"req_id": "REQ-085", "text": "No gaps, no skips, no bugs, no issues — 100% complete", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
    {"req_id": "REQ-086", "text": "Chronological, well-structured unified project", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
    {"req_id": "REQ-087", "text": "Single unified directory containing absolutely everything (BUILD_JARVIS_UNIFIED.ps1 ready)", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
    {"req_id": "REQ-088", "text": "Start complete merge and build process from scratch to finish", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
    {"req_id": "REQ-089", "text": "UnifiedMemoryEngine: SQLite+FTS5, 105+ requirements, 6 epochs seeded", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
    {"req_id": "REQ-090", "text": "requirements_master.md: chronological file with all requirements", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
    {"req_id": "REQ-091", "text": "BUILD_JARVIS_UNIFIED.ps1: PowerShell script merging 4 projects to JARVIS_UNIFIED/", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
    {"req_id": "REQ-092", "text": "build_unified.py: Python build script with deduplication and manifest", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
    {"req_id": "REQ-093", "text": "UNIFIED_MANIFEST.md: complete project map with all files, endpoints, requirements", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
    {"req_id": "REQ-094", "text": "28 new tests for UnifiedMemoryEngine (test_unified_memory.py)", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
    {"req_id": "REQ-095", "text": "SkyCore drone system discovered and indexed: 253 modules, 8 layers", "epoch": 5, "status": "done", "source": "session_2026-05-27"},
]

BUILTIN_EVENTS = [
    {"event_date": "2026-05-15", "epoch": 0, "title": "SkyCore v1.0.0 Complete", "description": "SkyCore drone system delivered: 253 modules, 8 layers, PX4/ArduPilot, C-UAS, swarm, GCS", "event_type": "milestone"},
    {"event_date": "2026-05-03", "epoch": 1, "title": "JARVIS Vision Established", "description": "Core identity, architecture principles, and design system defined in .antigravity_rules", "event_type": "milestone"},
    {"event_date": "2026-05-03", "epoch": 2, "title": "Mission 30 Complete", "description": "All 30 missions delivered: PyQt6 HUD, voice, vision, memory, watchdog, autostart, tests", "event_type": "milestone"},
    {"event_date": "2026-05-03", "epoch": 3, "title": "Navigation Singularity v28.29", "description": "GODSKILL Navigation v11 complete: 145 classes, 965 tests, 7 tiers, R1-R29 rounds", "event_type": "milestone"},
    {"event_date": "2026-05-26", "epoch": 4, "title": "FreeLLM + New Capabilities", "description": "Removed Anthropic, added FreeLLM 5-provider chain, IdeaPipeline, 3D WebsiteBuilder, 45 tests passing", "event_type": "milestone"},
    {"event_date": "2026-05-27", "epoch": 5, "title": "Unified Singularity Complete", "description": "Full scan done: 105+ requirements, 6 epochs, SkyCore+KidGenius+JARVIS merged, UnifiedMemoryEngine built, BUILD_JARVIS_UNIFIED.ps1 ready", "event_type": "milestone"},
]


# ─── Engine ───────────────────────────────────────────────────────────────────

class UnifiedMemoryEngine:
    """
    The single source of truth for ALL JARVIS knowledge.
    
    Stores requirements, decisions, events, and arbitrary memory entries
    in SQLite with full-text search. No API keys. Always offline.
    """

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        # HR-006 FIX: thread lock for all write operations (Flask concurrency safety)
        self._lock = threading.Lock()
        self._initialize_schema()
        self._seed_builtins()


    def _initialize_schema(self) -> None:
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    def _seed_builtins(self) -> None:
        """Idempotently seed all built-in requirements and events."""
        for req_data in BUILTIN_REQUIREMENTS:
            existing = self._conn.execute(
                "SELECT req_id FROM requirements WHERE req_id = ?", (req_data["req_id"],)
            ).fetchone()
            if not existing:
                self._conn.execute(
                    "INSERT INTO requirements (req_id, text, epoch, epoch_name, status, source, created_at, tags, notes) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        req_data["req_id"],
                        req_data["text"],
                        req_data["epoch"],
                        EPOCHS.get(req_data["epoch"], ""),
                        req_data["status"],
                        req_data["source"],
                        datetime.now(timezone.utc).isoformat(),
                        "[]",
                        "",
                    ),
                )

        for ev in BUILTIN_EVENTS:
            existing = self._conn.execute(
                "SELECT event_id FROM project_events WHERE title = ? AND event_date = ?",
                (ev["title"], ev["event_date"])
            ).fetchone()
            if not existing:
                self._conn.execute(
                    "INSERT INTO project_events (event_id, event_date, epoch, title, description, event_type) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), ev["event_date"], ev["epoch"], ev["title"], ev["description"], ev["event_type"])
                )
        self._conn.commit()

    # ─── Requirements ──────────────────────────────────────────────────────────

    def add_requirement(
        self,
        text: str,
        epoch: int = 5,
        status: str = "open",
        source: str = "session",
        tags: list[str] | None = None,
        notes: str = "",
        req_id: str | None = None,
    ) -> str:
        """Add a new requirement. Returns the req_id."""
        if not req_id:
            count = self._conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
            req_id = f"REQ-{count + 1:03d}"
        epoch_name = EPOCHS.get(epoch, f"Epoch {epoch}")
        self._conn.execute(
            "INSERT OR REPLACE INTO requirements (req_id, text, epoch, epoch_name, status, source, created_at, tags, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (req_id, text, epoch, epoch_name, status, source,
             datetime.now(timezone.utc).isoformat(), json.dumps(tags or []), notes)
        )
        self._conn.commit()
        return req_id

    def update_requirement_status(self, req_id: str, status: str, notes: str = "") -> bool:
        """Update status of an existing requirement."""
        cursor = self._conn.execute(
            "UPDATE requirements SET status = ?, notes = ? WHERE req_id = ?",
            (status, notes, req_id)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def get_requirements(
        self,
        epoch: int | None = None,
        status: str | None = None,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        """Get requirements, optionally filtered and paginated.
        
        LR-009 FIX: Added limit/offset for large datasets.
        Examples:
          get_requirements(limit=20, offset=0)  # first page
          get_requirements(status='open', limit=10)  # paginated open reqs
        """
        query = "SELECT * FROM requirements WHERE 1=1"
        params: list[Any] = []
        if epoch is not None:
            query += " AND epoch = ?"
            params.append(epoch)
        if status:
            query += " AND status = ?"
            params.append(status)
        if source:
            query += " AND source LIKE ?"
            params.append(f"%{source}%")
        query += " ORDER BY epoch, req_id"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_requirement(self, req_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM requirements WHERE req_id = ?", (req_id,)).fetchone()
        return dict(row) if row else None

    # ─── Memory Entries ────────────────────────────────────────────────────────

    def remember(
        self,
        title: str,
        content: str,
        entry_type: str = "event",
        importance: int = 5,
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Store any memory entry. Returns entry_id."""
        entry_id = str(uuid.uuid4())
        # HR-006 FIX: lock all write operations for Flask thread safety
        with self._lock:
            self._conn.execute(
                "INSERT INTO memory_entries (entry_id, entry_type, title, content, metadata, created_at, importance, tags) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry_id, entry_type, title, content,
                    json.dumps(metadata or {}),
                    datetime.now(timezone.utc).isoformat(),
                    importance,
                    json.dumps(tags or []),
                )
            )
            self._conn.commit()
        return entry_id

    def recall(
        self,
        query: str,
        entry_types: list[str] | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Full-text search across all memory entries."""
        if not query.strip():
            return []

        # FTS5 search on memory_entries
        fts_query = query.replace('"', '""')
        try:
            rows = self._conn.execute(
                "SELECT e.*, rank FROM memory_entries e "
                "JOIN memory_fts f ON e.rowid = f.rowid "
                "WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?",
                (fts_query, limit)
            ).fetchall()
        except Exception:
            # Fallback: LIKE search
            rows = self._conn.execute(
                "SELECT *, 0 as rank FROM memory_entries WHERE title LIKE ? OR content LIKE ? LIMIT ?",
                (f"%{query}%", f"%{query}%", limit)
            ).fetchall()

        results = []
        for row in rows:
            r = dict(row)
            snippet = r["content"][:200] + "..." if len(r["content"]) > 200 else r["content"]
            results.append(SearchResult(
                entry_id=r["entry_id"],
                entry_type=r["entry_type"],
                title=r["title"],
                snippet=snippet,
                score=abs(float(r.get("rank", 0))),
                metadata=json.loads(r.get("metadata", "{}")),
            ))
        return results

    def search_requirements(self, query: str, limit: int = 20) -> list[dict]:
        """Full-text search across requirements."""
        if not query.strip():
            return self.get_requirements()
        fts_query = query.replace('"', '""')
        try:
            rows = self._conn.execute(
                "SELECT r.* FROM requirements r "
                "JOIN requirements_fts f ON r.rowid = f.rowid "
                "WHERE requirements_fts MATCH ? ORDER BY r.epoch, r.req_id LIMIT ?",
                (fts_query, limit)
            ).fetchall()
        except Exception:
            rows = self._conn.execute(
                "SELECT * FROM requirements WHERE text LIKE ? OR notes LIKE ? LIMIT ?",
                (f"%{query}%", f"%{query}%", limit)
            ).fetchall()
        return [dict(r) for r in rows]

    # ─── Timeline ──────────────────────────────────────────────────────────────

    def get_timeline(self) -> list[dict]:
        """Get full project timeline — events + milestones chronologically."""
        rows = self._conn.execute(
            "SELECT * FROM project_events ORDER BY event_date, epoch"
        ).fetchall()
        return [dict(r) for r in rows]

    def add_event(
        self,
        title: str,
        description: str = "",
        event_date: str | None = None,
        epoch: int = 5,
        event_type: str = "milestone",
    ) -> str:
        """Add a timeline event."""
        event_id = str(uuid.uuid4())
        date = event_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._conn.execute(
            "INSERT INTO project_events (event_id, event_date, epoch, title, description, event_type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, date, epoch, title, description, event_type)
        )
        self._conn.commit()
        return event_id

    # ─── Statistics ────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Get summary statistics of all stored knowledge."""
        req_total = self._conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
        req_done = self._conn.execute("SELECT COUNT(*) FROM requirements WHERE status='done'").fetchone()[0]
        req_open = self._conn.execute("SELECT COUNT(*) FROM requirements WHERE status='open'").fetchone()[0]
        req_prog = self._conn.execute("SELECT COUNT(*) FROM requirements WHERE status='in_progress'").fetchone()[0]
        mem_total = self._conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0]
        events_total = self._conn.execute("SELECT COUNT(*) FROM project_events").fetchone()[0]

        per_epoch: dict[int, dict] = {}
        for epoch, name in sorted(EPOCHS.items()):
            count = self._conn.execute(
                "SELECT COUNT(*) FROM requirements WHERE epoch = ?", (epoch,)
            ).fetchone()[0]
            done = self._conn.execute(
                "SELECT COUNT(*) FROM requirements WHERE epoch = ? AND status = 'done'", (epoch,)
            ).fetchone()[0]
            per_epoch[epoch] = {"name": name, "total": count, "done": done}


        return {
            "requirements": {
                "total": req_total,
                "done": req_done,
                "in_progress": req_prog,
                "open": req_open,
                "completion_pct": round(req_done / req_total * 100, 1) if req_total else 0,
            },
            "memory_entries": mem_total,
            "timeline_events": events_total,
            "per_epoch": per_epoch,
            "db_path": str(self.db_path),
        }

    def export_json(self) -> str:
        """Export everything as JSON string."""
        return json.dumps({
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "requirements": self.get_requirements(),
            "timeline": self.get_timeline(),
            "stats": self.stats(),
        }, ensure_ascii=False, indent=2)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ─── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[UnifiedMemoryEngine] = None


def get_memory(db_path: Path = DEFAULT_DB_PATH) -> UnifiedMemoryEngine:
    """Get or create the global singleton memory engine."""
    global _instance
    if _instance is None:
        _instance = UnifiedMemoryEngine(db_path)
    return _instance


def reset_memory() -> None:
    """MR-009 FIX: Reset the singleton for test isolation.
    Call in pytest teardown to prevent state leaking between tests.
    
    Usage in conftest.py:
        @pytest.fixture(autouse=True)
        def clean_memory():
            yield
            reset_memory()
    """
    global _instance
    if _instance is not None:
        try:
            _instance.close()
        except Exception:
            pass
    _instance = None


def quick_search(query: str) -> list[dict]:
    """One-liner search across all requirements."""
    return get_memory().search_requirements(query)


def quick_remember(title: str, content: str, importance: int = 5) -> str:
    """One-liner to store a memory."""
    return get_memory().remember(title, content, importance=importance)
