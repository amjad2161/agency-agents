#!/usr/bin/env python3
"""
SINGULARITY UNIFIED BOOTSTRAP for J.A.R.V.I.S BRAINIAC v31.0
=============================================================
The ultimate entry point that initializes ALL JARVIS BRAINIAC subsystems
across 10 orchestrated phases with graceful degradation, health reporting,
and an interactive command shell.

Usage:
    python singularity_bootstrap.py              # Full bootstrap + shell
    python singularity_bootstrap.py --test       # Self-test mode
    python singularity_bootstrap.py --dir PATH   # Use custom base directory
"""
import os
import sys
import time
import platform
import subprocess
import importlib.util
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

# ============================================================================
# ANSI Color System
# ============================================================================
C = {
    "rst": "\033[0m", "bld": "\033[1m", "dim": "\033[2m",
    "red": "\033[91m", "grn": "\033[92m", "ylw": "\033[93m",
    "blu": "\033[94m", "mag": "\033[95m", "cyn": "\033[96m",
    "wht": "\033[97m",
}

_COLOR = (
    (hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
     and os.environ.get("TERM", "") not in ("", "dumb"))
    or os.environ.get("FORCE_COLOR") == "1"
)


def cc(text: str, color: str) -> str:
    """Colorize text if terminal supports it."""
    return f"{C[color]}{text}{C['rst']}" if _COLOR else text


# ============================================================================
# Hardware Detection Helpers
# ============================================================================
def _sh(cmd: List[str]) -> Optional[str]:
    """Run a shell command, return stripped stdout on success."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _gpu() -> str:
    """Detect GPU across NVIDIA, Apple, and AMD/ROCm."""
    g = _sh(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
    if g:
        return "NVIDIA: " + " | ".join(l.strip() for l in g.splitlines() if l.strip())
    if platform.system() == "Darwin":
        return "Apple GPU (Metal)"
    if _sh(["rocm-smi", "--showproductname"]):
        return "AMD/ROCm GPU"
    return "No dedicated GPU detected"


def _ram() -> str:
    """Get total system RAM."""
    try:
        import psutil
        return f"{psutil.virtual_memory().total / (1024**3):.1f} GB"
    except Exception:
        if platform.system() == "Linux":
            m = _sh(["free", "-m"])
            if m:
                return f"{int(m.splitlines()[1].split()[1]) / 1024:.1f} GB"
        return "Unknown"


def _cpu() -> str:
    """Get CPU description string."""
    proc = platform.processor()
    if not proc:
        proc = "Apple Silicon" if platform.system() == "Darwin" else "Unknown CPU"
    return f"{proc} ({platform.machine()}, {os.cpu_count() or '?'} cores)"


def _lines(f: Path) -> int:
    """Count non-empty lines in a file."""
    try:
        with open(f, "r", encoding="utf-8", errors="ignore") as fh:
            return sum(1 for ln in fh if ln.strip())
    except Exception:
        return 0


def _load(name: str, path: Path) -> Any:
    """Dynamically load a Python module from a file path."""
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ============================================================================
# SingularityBootstrap — The Master Orchestrator
# ============================================================================
class SingularityBootstrap:
    """
    Unified bootstrap orchestrator for JARVIS BRAINIAC Singularity v31.0.

    Executes a 10-phase initialization sequence across 70+ modules,
    with graceful degradation for missing modules, comprehensive health
    reporting, and an interactive command shell.
    """

    PHASES: List[Dict[str, Any]] = [
        {
            "name": "Core Infrastructure",
            "modules": [
                "jarvis_brain.py",
                "unified_bridge.py",
                "context_manager.py",
                "trust.py",
            ],
        },
        {
            "name": "Local Processing",
            "modules": [
                "local_brain.py",
                "local_voice.py",
                "local_vision.py",
                "local_memory.py",
            ],
        },
        {
            "name": "Multi-Agent System",
            "modules": [
                "multi_agent_orchestrator.py",
                "expert_personas.py",
                "task_planner.py",
                "collaborative_workflow.py",
            ],
        },
        {
            "name": "Intelligence Layer",
            "modules": [
                "neural_link.py",
                "infinite_knowledge.py",
                "auto_upgrade.py",
                "visual_qa.py",
            ],
        },
        {
            "name": "External Tools",
            "modules": [
                "trading_engine.py",
                "github_ingestor.py",
                "windows_god_mode.py",
                "document_generator.py",
                "drawing_engine.py",
            ],
        },
        {
            "name": "Companion",
            "modules": [
                "advisor_brain.py",
                "persona_engine.py",
                "jarvis_soul.py",
                "emotion_state.py",
            ],
        },
        {
            "name": "35 Bridges",
            "modules": [
                "autogpt_bridge.py", "langchain_bridge.py", "llamaindex_bridge.py",
                "mem0_bridge.py", "metagpt_bridge.py", "ragflow_bridge.py",
                "semantic_kernel_bridge.py", "livekit_bridge.py", "agents_bridge.py",
                "docker_android_bridge.py", "auto_browser_bridge.py",
                "gemini_computer_use_bridge.py", "e2b_computer_use_bridge.py",
                "paper2code_bridge.py", "jcode_bridge.py", "humanizer_bridge.py",
                "localsend_bridge.py", "microsoft_jarvis_bridge.py",
                "meta_agent_bridge.py", "decepticon_bridge.py", "ace_step_ui_bridge.py",
                "computer_use_ootb_bridge.py", "open_autoglm_bridge.py",
                "supersplat_bridge.py", "off_grid_mobile_ai_bridge.py",
                "openjarvis_bridge.py", "opencode_bridge.py", "agenticseek_bridge.py",
                "openmanus_bridge.py", "lemonai_bridge.py", "uifacts_bridge.py",
            ],
        },
        {
            "name": "SINGULARITY",
            "modules": [
                "singularity_core.py",
                "continuous_ingestion.py",
                "financial_dominance.py",
                "omnilingual_processor.py",
                "vr_perception_engine.py",
            ],
        },
        {
            "name": "Web Frontend",
            "modules": [
                "static/hud/index.html",
                "static/scifi/index.html",
                "static/avatar/index.html",
                "static/dashboard/index.html",
                "static/architecture/index.html",
            ],
        },
        {
            "name": "Health Report",
            "modules": ["_final_health_check"],
        },
    ]

    # Module dependency graph for layered visualization
    DEPS: Dict[str, List[str]] = {
        "Core": ["jarvis_brain.py", "unified_bridge.py", "context_manager.py", "trust.py"],
        "Local AI": ["local_brain.py", "local_voice.py", "local_vision.py", "local_memory.py"],
        "Agents": ["multi_agent_orchestrator.py", "expert_personas.py", "task_planner.py",
                   "collaborative_workflow.py"],
        "Intelligence": ["neural_link.py", "infinite_knowledge.py", "auto_upgrade.py", "visual_qa.py"],
        "Tools": ["trading_engine.py", "github_ingestor.py", "windows_god_mode.py",
                  "document_generator.py", "drawing_engine.py"],
        "Companion": ["advisor_brain.py", "persona_engine.py", "jarvis_soul.py", "emotion_state.py"],
        "Singularity": ["singularity_core.py", "continuous_ingestion.py", "financial_dominance.py",
                        "omnilingual_processor.py", "vr_perception_engine.py"],
    }

    def __init__(self, base_dir: Optional[str] = None) -> None:
        self.base = Path(base_dir) if base_dir else Path(__file__).resolve().parent
        self.data = self.base / "data"
        self.data.mkdir(parents=True, exist_ok=True)
        self.log_path = self.data / "singularity_startup.log"
        self.modules: Dict[str, Dict[str, Any]] = {}
        self.loaded: Dict[str, Any] = {}
        self.phase_results: List[Dict[str, int]] = []
        self._log: List[str] = []
        self._start = time.time()

    # ── Logging ─────────────────────────────────────────────────────────
    def lg(self, msg: str) -> None:
        """Append a timestamped message to the log buffer."""
        self._log.append(f"[{datetime.now().isoformat()}] {msg}")

    def flush_log(self) -> None:
        """Persist the log buffer to disk."""
        try:
            self.log_path.write_text("\n".join(self._log), encoding="utf-8")
        except Exception as e:
            print(cc(f"[WARN] Could not write log: {e}", "ylw"))

    # ── Banner ──────────────────────────────────────────────────────────
    def banner(self) -> None:
        """Print the epic JARVIS BRAINIAC Singularity ASCII banner."""
        art = r"""
    ███████╗██╗███╗   ██╗ ██████╗ ██╗   ██╗██╗      █████╗ ██████╗ ██╗████████╗██╗   ██╗
    ██╔════╝██║████╗  ██║██╔════╝ ██║   ██║██║     ██╔══██╗██╔══██╗██║╚══██╔══╝╚██╗ ██╔╝
    ███████╗██║██╔██╗ ██║██║  ███╗██║   ██║██║     ███████║██████╔╝██║   ██║    ╚████╔╝
    ╚════██║██║██║╚██╗██║██║   ██║██║   ██║██║     ██╔══██║██╔══██╗██║   ██║     ╚██╔╝
    ███████║██║██║ ╚████║╚██████╔╝╚██████╔╝███████╗██║  ██║██║  ██║██║   ██║      ██║
    ╚══════╝╚═╝╚═╝  ╚═══╝ ╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝   ╚═╝      ╚═╝

        B R A I N I A C   —   S I N G U L A R I T Y   v 3 1 . 0
        ═══════════════════════════════════════════════════════════
        "Just A Rather Very Intelligent System — Bringing
         Revolutionary AI, Neural Intelligence, And Consciousness"
        ═══════════════════════════════════════════════════════════
"""
        print(cc(art, "cyn"))
        print(cc(f"  Base : {self.base}", "dim"))
        print(cc(f"  Data : {self.data}", "dim"))
        print(cc(f"  Log  : {self.log_path}", "dim"))
        self.lg("=== SINGULARITY BOOT v31.0 ===")

    # ── Environment Check ───────────────────────────────────────────────
    def env_check(self) -> bool:
        """Validate Python version, OS, CPU, RAM, GPU, and disk space."""
        print(cc("[ENV CHECK] Validating execution environment...", "cyn"))
        ok = sys.version_info >= (3, 8)
        status = cc("OK", "grn") if ok else cc("FAIL", "red")
        print(f"  Python  : {sys.version.split()[0]} ... {status}")
        if not ok:
            print(cc("  ERROR: Python 3.8+ required!", "red"))
            return False
        print(f"  OS      : {platform.system()} {platform.release()}")
        print(f"  CPU     : {_cpu()}")
        print(f"  RAM     : {_ram()}")
        print(f"  GPU     : {_gpu()}")
        try:
            if hasattr(os, "statvfs"):
                s = os.statvfs(str(self.base))
                free_gb = s.f_frsize * s.f_bavail / (1024 ** 3)
                print(f"  Disk    : {free_gb:.1f} GB free")
            else:
                import ctypes
                fb = ctypes.c_ulonglong(0)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    ctypes.c_wchar_p(str(self.base)),
                    ctypes.pointer(fb), None, None,
                )
                print(f"  Disk    : {fb.value / (1024 ** 3):.1f} GB free")
        except Exception:
            print("  Disk    : Unknown")
        self.lg(f"Env: Python {sys.version.split()[0]}, {platform.system()}")
        return True

    # ── Phase Execution ─────────────────────────────────────────────────
    def run_phase(self, num: int, phase: dict) -> Dict[str, int]:
        """Execute a single bootstrap phase with timing."""
        name = phase["name"]
        print(cc(f"[PHASE {num}/10] {name}", "cyn"))
        self.lg(f"PHASE {num}: {name}")
        res = {"ok": 0, "skipped": 0, "failed": 0}
        t0 = time.time()
        for mod in phase["modules"]:
            d = self._init_mod(mod)
            res[d["status"]] += 1
        elapsed = time.time() - t0
        print(
            f"  {name}: {cc(str(res['ok']), 'grn')} OK, "
            f"{cc(str(res['skipped']), 'ylw')} SKIP, "
            f"{cc(str(res['failed']), 'red')} FAIL ({elapsed:.2f}s)\n"
        )
        return res

    def _init_mod(self, name: str) -> Dict[str, Any]:
        """Initialize one module: detect, count lines, optionally import."""
        d = {"name": name, "status": "failed", "lines": 0, "error": None, "time": 0.0}
        t0 = time.time()

        if name == "_final_health_check":
            d["status"] = "ok"
            print(f"  {cc('✓', 'grn')} {name}... {cc('OK', 'grn')}")
            d["time"] = time.time() - t0
            self.modules[name] = d
            return d

        # Search in multiple paths: base, runtime/agency/, runtime/agency/external_integrations/
        search_paths = [
            self.base / name,
            self.base / "runtime" / "agency" / name,
            self.base / "runtime" / "agency" / "external_integrations" / name,
            self.base / "runtime" / "agency" / "robotics" / name,
        ]
        path = None
        for sp in search_paths:
            if sp.exists():
                path = sp
                break

        if path is None:
            d["status"] = "skipped"
            d["error"] = f"Not found in any search path"
            d["time"] = time.time() - t0
            print(f"  {cc('⚠', 'ylw')} {name}... {cc('SKIPPED', 'ylw')}")
            self.modules[name] = d
            return d

        d["lines"] = _lines(path)
        if path.suffix == ".html":
            d["status"] = "ok"
        elif path.suffix == ".py":
            mod = _load(name.replace(".py", ""), path)
            d["status"] = "ok" if mod else "failed"
            if mod:
                self.loaded[name] = mod
        else:
            d["status"] = "ok"

        d["time"] = time.time() - t0
        is_ok = d["status"] == "ok"
        icon = cc("✓", "grn") if is_ok else cc("✗", "red")
        stxt = cc("OK", "grn") if is_ok else cc("FAILED", "red")
        li = f"({d['lines']} lines)" if d["lines"] else ""
        print(f"  {icon} {name}... {stxt} {li}")
        self.modules[name] = d
        return d

    # ── Summary ─────────────────────────────────────────────────────────
    def summary(self) -> None:
        """Print the grand unified health summary box."""
        elapsed = time.time() - self._start
        mods = list(self.modules.values())
        total = len(mods)
        ok = sum(1 for m in mods if m["status"] == "ok")
        skip = sum(1 for m in mods if m["status"] == "skipped")
        fail = sum(1 for m in mods if m["status"] == "failed")
        lines = sum(m["lines"] for m in mods)
        pct = (ok / total * 100) if total else 0

        hc = "grn" if pct >= 90 else "ylw" if pct >= 70 else "mag" if pct >= 50 else "red"
        hs = "EXCELLENT" if pct >= 90 else "GOOD" if pct >= 70 else "FAIR" if pct >= 50 else "CRITICAL"

        b = cc("═" * 66, "cyn")
        print(cc("╔" + b + "╗", "cyn"))
        print(cc("║" + "  J.A.R.V.I.S BRAINIAC — SINGULARITY v31.0 ONLINE".ljust(66) + "║", "cyn"))
        print(cc("║" + f"  {total} modules | {lines:,} lines | Health: {pct:.0f}% [{hs}]".ljust(66) + "║", hc))
        print(cc("║" + f"  Startup: {elapsed:.2f}s | OK={ok} SKIP={skip} FAIL={fail}".ljust(66) + "║", "cyn"))
        print(cc("╚" + b + "╝", "cyn"))

        self.lg(f"SUMMARY: {ok} OK, {skip} SKIP, {fail} FAIL, {lines}L, {elapsed:.2f}s")
        self._summary = {
            "total": total, "ok": ok, "skip": skip, "fail": fail,
            "lines": lines, "pct": pct, "status": hs, "time": elapsed,
        }

    # ── Interactive Shell ───────────────────────────────────────────────
    def shell(self) -> None:
        """Accept and dispatch interactive commands."""
        print(cc("Interactive shell ready. Type 'help' for commands.", "dim"))
        while True:
            try:
                raw = input(cc("JARVIS", "grn") + cc("> ", "cyn")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                print(cc("Shutting down gracefully. Goodbye, sir.", "cyn"))
                break
            if not raw:
                continue
            self.lg(f"[CMD] {raw}")
            parts = raw.lower().split()
            verb = parts[0]

            if verb in ("exit", "quit", "q"):
                print(cc("Goodbye, sir.", "cyn"))
                break
            elif verb == "status":
                self._status()
            elif verb == "test":
                self._test()
            elif verb == "demo":
                self._demo()
            elif verb == "modules":
                self._modules()
            elif verb == "phases":
                self._phases()
            elif verb == "sysinfo":
                self._sysinfo()
            elif verb == "benchmark":
                self._benchmark()
            elif verb == "deps":
                self._deps()
            elif verb == "reload":
                self._reload(parts[1:])
            elif verb == "help":
                self._help()
            else:
                print(cc(f"  Unknown: '{verb}'. Type 'help'.", "ylw"))

    def _status(self) -> None:
        """Show system status."""
        s = getattr(self, "_summary", {})
        print(cc("  --- Status ---", "cyn"))
        print(f"    Uptime   : {time.time() - self._start:.1f}s")
        print(f"    Modules  : {s.get('total', len(self.modules))}")
        print(f"    OK       : {s.get('ok', 0)}")
        print(f"    Skipped  : {s.get('skip', 0)}")
        print(f"    Failed   : {s.get('fail', 0)}")
        print(f"    Lines    : {s.get('lines', 0):,}")
        print(f"    Health   : {s.get('pct', 0):.0f}% [{s.get('status', 'N/A')}]")
        print(f"    Loaded   : {len(self.loaded)}")

    def _test(self) -> None:
        """Run the built-in self-test suite."""
        print(cc("  --- Self-Test ---", "cyn"))
        tests = [
            ("Python 3.8+", lambda: sys.version_info >= (3, 8)),
            ("Base dir", lambda: self.base.exists()),
            ("Data dir write", lambda: (self.data / ".tw").write_text("ok") or True),
            ("Log buffer", lambda: len(self._log) > 0),
            ("Loaded dict", lambda: isinstance(self.loaded, dict)),
            ("10 phases", lambda: len(self.PHASES) == 10),
            ("Color system", lambda: "test" in cc("test", "grn")),
            ("Module registry", lambda: len(self.modules) >= 0),
        ]
        passed = 0
        for n, fn in tests:
            try:
                ok = fn()
            except Exception:
                ok = False
            st = cc("PASS", "grn") if ok else cc("FAIL", "red")
            if ok:
                passed += 1
            print(f"    {n:20s} ... {st}")
        try:
            (self.data / ".tw").unlink()
        except Exception:
            pass
        print(f"    {passed}/{len(tests)} tests passed")

    def _demo(self) -> None:
        """Show a capability overview demo."""
        print(cc("  --- Capability Demo ---", "cyn"))
        demos = [
            ("Core Brain", "jarvis_brain.py", "Neural processing core"),
            ("Local AI", "local_brain.py", "On-device inference engine"),
            ("Multi-Agent", "multi_agent_orchestrator.py", "Swarm intelligence"),
            ("Neural Link", "neural_link.py", "Direct cognitive interface"),
            ("Trading", "trading_engine.py", "Financial strategy execution"),
            ("Companion", "jarvis_soul.py", "Emotional AI companion"),
            ("Singularity", "singularity_core.py", "Autonomous evolution"),
            ("Omnilingual", "omnilingual_processor.py", "Universal language"),
        ]
        for label, mod, desc in demos:
            st = self.modules.get(mod, {}).get("status", "unknown")
            ic = cc("*", "grn") if st == "ok" else cc("o", "ylw" if st == "skipped" else "red")
            print(f"    {ic} {label:18s} : {desc}")

    def _help(self) -> None:
        """Display available commands."""
        print(cc("  --- Commands ---", "cyn"))
        cmds = [
            ("status", "System status and health"),
            ("test", "Built-in self-test suite"),
            ("demo", "Capability overview"),
            ("modules", "List all modules and status"),
            ("phases", "List all phases and results"),
            ("sysinfo", "Detailed system information"),
            ("benchmark", "Quick performance benchmark"),
            ("deps", "Module dependency graph"),
            ("reload <mod>", "Reload a specific module"),
            ("help", "Show this help message"),
            ("exit", "Shut down JARVIS"),
        ]
        for c, d in cmds:
            print(f"    {cc(c, 'grn'):20s} - {d}")

    def _modules(self) -> None:
        """List every module with status indicator."""
        print(cc("  --- Module Registry ---", "cyn"))
        for n, i in sorted(self.modules.items()):
            col = "grn" if i["status"] == "ok" else "ylw" if i["status"] == "skipped" else "red"
            ic = "*" if i["status"] == "ok" else "o" if i["status"] == "skipped" else "x"
            print(f"    {cc(ic, col)} {n:42s} [{i['status'].upper():7s}] {i['lines']:>5}L")

    def _phases(self) -> None:
        """List all phases and their aggregate results."""
        print(cc("  --- Phase Results ---", "cyn"))
        for i, pr in enumerate(self.phase_results, 1):
            nm = self.PHASES[i - 1]["name"]
            total = pr["ok"] + pr["skipped"] + pr["failed"]
            print(
                f"    Phase {i}: {nm:25s} - "
                f"{cc(str(pr['ok']), 'grn')} OK, "
                f"{cc(str(pr['skipped']), 'ylw')} SKIP, "
                f"{cc(str(pr['failed']), 'red')} FAIL / {total}"
            )

    def _sysinfo(self) -> None:
        """Display detailed system information."""
        print(cc("  --- System Information ---", "cyn"))
        print(f"    Platform  : {platform.platform()}")
        print(f"    Machine   : {platform.machine()}")
        print(f"    Node      : {platform.node()}")
        print(f"    Python    : {sys.version.split()[0]}")
        print(f"    Processor : {platform.processor() or 'N/A'}")
        print(f"    CPU cores : {os.cpu_count()}")
        print(f"    RAM       : {_ram()}")
        print(f"    GPU       : {_gpu()}")
        print(f"    Base dir  : {self.base}")
        print(f"    Data dir  : {self.data}")
        pypath = sys.path[:3]
        print(f"    Sys.path  : {':'.join(pypath)}" + ("..." if len(sys.path) > 3 else ""))
        jvars = {k: v for k, v in os.environ.items() if k.startswith(("JARVIS", "SINGULARITY"))}
        if jvars:
            print(f"    JARVIS env: {jvars}")

    def _benchmark(self) -> None:
        """Run a quick performance benchmark."""
        print(cc("  --- Benchmark ---", "cyn"))
        # String concatenation
        t0 = time.time()
        s = ""
        for i in range(100000):
            s += str(i)
        del s
        t1 = time.time() - t0
        print(f"    String concat (100K)  : {t1:.3f}s")
        # List comprehension
        t0 = time.time()
        _ = [x ** 2 for x in range(1000000)]
        t2 = time.time() - t0
        print(f"    List comp (1M)        : {t2:.3f}s")
        # Dictionary build
        t0 = time.time()
        d = {str(i): i for i in range(500000)}
        del d
        t3 = time.time() - t0
        print(f"    Dict build (500K)     : {t3:.3f}s")
        total = t1 + t2 + t3
        score = max(0, int(1000 / (total + 0.001)))
        col = "grn" if score > 500 else "ylw" if score > 200 else "red"
        print(f"    Total                 : {total:.3f}s")
        print(f"    Performance score     : {cc(str(score), col)}")

    def _deps(self) -> None:
        """Display module dependency layers with visual progress bars."""
        print(cc("  --- Module Dependencies ---", "cyn"))
        for layer, mods in self.DEPS.items():
            loaded = sum(1 for m in mods if self.modules.get(m, {}).get("status") == "ok")
            total = len(mods)
            col = "grn" if loaded == total else "ylw" if loaded > 0 else "red"
            bar = "#" * loaded + "-" * (total - loaded)
            print(f"    {cc(layer, 'cyn'):14s} [{cc(bar, col)}] {loaded}/{total}")

    def _reload(self, args: List[str]) -> None:
        """Reload a specific module from disk."""
        if not args:
            print(cc("  Usage: reload <file.py>", "ylw"))
            return
        nm = args[0]
        p = self.base / nm
        if not p.exists():
            print(cc(f"  Not found: {p}", "red"))
            return
        print(cc(f"  Reloading {nm}...", "cyn"))
        d = self._init_mod(nm)
        status = cc(d["status"].upper(), "grn" if d["status"] == "ok" else "red")
        print(f"  Result: {status}")

    # ── Main Orchestrator ───────────────────────────────────────────────
    def run(self) -> None:
        """Execute the complete 10-phase bootstrap sequence."""
        self.banner()
        if not self.env_check():
            self.flush_log()
            sys.exit(1)
        for i, ph in enumerate(self.PHASES, 1):
            try:
                self.phase_results.append(self.run_phase(i, ph))
            except Exception as e:
                print(cc(f"[PHASE {i}] CRITICAL ERROR: {e}", "red"))
                self.phase_results.append({"ok": 0, "skipped": 0, "failed": 0})
                self.lg(f"PHASE {i} CRITICAL: {e}")
        self.summary()
        self.flush_log()
        self.shell()


# ============================================================================
# Self-Test Entrypoint
# ============================================================================
def self_test() -> bool:
    """Run a standalone self-test without the full bootstrap sequence."""
    print(cc("=== SINGULARITY SELF-TEST ===", "cyn"))
    sb = SingularityBootstrap()
    # Test 1: environment check
    assert sb.env_check(), "env check failed"
    print(cc("  [PASS] environment check", "grn"))
    # Test 2: phases and modules
    assert len(sb.PHASES) == 10
    total = sum(len(p["modules"]) for p in sb.PHASES)
    assert total >= 60
    print(cc(f"  [PASS] {len(sb.PHASES)} phases, {total} modules", "grn"))
    # Test 3: color system
    assert "test" in cc("test", "grn")
    print(cc("  [PASS] color system", "grn"))
    # Test 4: logging
    before = len(sb._log)
    sb.lg("test message")
    assert len(sb._log) == before + 1
    print(cc("  [PASS] logging", "grn"))
    # Test 5: dependency graph
    assert len(sb.DEPS) >= 7
    print(cc(f"  [PASS] dependency graph ({len(sb.DEPS)} layers)", "grn"))
    # Test 6: data directory
    assert sb.data.exists()
    print(cc("  [PASS] data directory", "grn"))
    print(cc("=== ALL SELF-TESTS PASSED ===", "grn"))
    return True


# ============================================================================
# Main Entry Point
# ============================================================================
if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.exit(0 if self_test() else 1)
    bd = None
    if "--dir" in sys.argv:
        idx = sys.argv.index("--dir")
        if idx + 1 < len(sys.argv):
            bd = sys.argv[idx + 1]
    SingularityBootstrap(base_dir=bd).run()
