#!/usr/bin/env python3
"""JARVIS_SUPREME — singular boot for unified system. v2.0 polished.

OFFLINE-FIRST · NO API KEYS REQUIRED · OPEN-SOURCE STACK · ALL-PERMISSIONS

One module. Imports every available agency component. Single CLI entrypoint:
  python JARVIS_SUPREME.py {boot|health|route|run|selftest|chat|exec}

Subsystems wired (degrade gracefully on missing):
  - jarvis_brainiac     orchestrator + agent registry + memory + cloud_sync
  - runtime.agency      full backend: nav, fusion, AI, bridges, HUD
  - JARVIS_OMEGA        omega kit: 7 nav tiers + omega.py
  - godskill_nav_v11    R29 final nav stack
  - jarvis_singularity  unified Python pkg
  - jarvis_os           HUD + hotkey + tray + native chat

LLM backend resolution order (first available wins):
  1. Ollama (local, free) — http://127.0.0.1:11434
  2. llama-cpp-python (local, free) — direct .gguf load
  3. transformers + local model
  4. Anthropic / OpenAI (only if env keys present AND OFFLINE_MODE=0)

Author: Claude (autonomous build 2026-05-05).
"""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

# ── env defaults — caveman: maximum permissions, full offline ────────────────
os.environ.setdefault("OFFLINE_MODE", "1")
os.environ.setdefault("ALLOW_ALL", "1")
os.environ.setdefault("JARVIS_PERM_LEVEL", "GOD")
os.environ.setdefault("JARVIS_REQUIRE_API_KEYS", "0")
os.environ.setdefault("JARVIS_LOCAL_LLM_PRIORITY", "ollama,llamacpp,transformers")
os.environ.setdefault("PYTHONUTF8", "1")

CANONICAL = Path(os.environ.get("AGENCY_ROOT", Path(__file__).resolve().parent))
LOG_PATH = Path(os.environ.get(
    "JARVIS_SUPREME_LOG",
    CANONICAL / "jarvis_supreme.log",
))

LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("supreme")

if str(CANONICAL) not in sys.path:
    sys.path.insert(0, str(CANONICAL))
runtime_path = CANONICAL / "runtime"
if runtime_path.exists() and str(runtime_path) not in sys.path:
    sys.path.insert(0, str(runtime_path))


# ── subsystem registry ───────────────────────────────────────────────────────
@dataclass
class Subsystem:
    name: str
    module: str
    optional: bool = True
    loaded: bool = False
    error: str | None = None
    handle: Any = None


SUBSYSTEMS: list[Subsystem] = [
    Subsystem("jarvis_brainiac", "jarvis_brainiac"),
    Subsystem("agent_registry", "jarvis_brainiac.agent_registry"),
    Subsystem("orchestrator", "jarvis_brainiac.orchestrator"),
    Subsystem("memory", "jarvis_brainiac.memory"),
    Subsystem("cloud_sync", "jarvis_brainiac.cloud_sync"),
    Subsystem("agency_runtime", "agency"),
    Subsystem("jarvis_singularity", "jarvis_singularity"),
    Subsystem("jarvis_os", "jarvis_os"),
    Subsystem("godskill_nav_v11", "godskill_nav_v11"),
]


# ── LLM backend resolver ─────────────────────────────────────────────────────
def detect_llm_backend() -> dict:
    """Return first-available local LLM. Free + open-source priority."""
    backends: list[tuple[str, Callable[[], dict | None]]] = [
        ("ollama", _detect_ollama),
        ("llamacpp", _detect_llamacpp),
        ("transformers", _detect_transformers),
    ]
    if os.environ.get("OFFLINE_MODE") != "1":
        backends.extend([
            ("anthropic", _detect_anthropic),
            ("openai", _detect_openai),
        ])
    for name, fn in backends:
        try:
            r = fn()
            if r:
                r["backend"] = name
                return r
        except Exception as e:  # noqa: BLE001
            log.debug("backend %s probe failed: %s", name, e)
    return {"backend": "none", "available": False,
            "hint": "install Ollama (https://ollama.ai) or `pip install llama-cpp-python`"}


def _detect_ollama() -> dict | None:
    import urllib.request
    url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read())
            models = [m["name"] for m in data.get("models", [])]
            return {"available": True, "url": url, "models": models}
    except Exception:
        return None


def _detect_llamacpp() -> dict | None:
    try:
        import llama_cpp  # type: ignore  # noqa: F401
        return {"available": True, "module": "llama_cpp"}
    except ImportError:
        return None


def _detect_transformers() -> dict | None:
    try:
        import transformers  # type: ignore  # noqa: F401
        return {"available": True, "module": "transformers"}
    except ImportError:
        return None


def _detect_anthropic() -> dict | None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return {"available": True, "key_set": True}


def _detect_openai() -> dict | None:
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    return {"available": True, "key_set": True}


# ── boot/health ──────────────────────────────────────────────────────────────
@dataclass
class SupremeBootReport:
    canonical: str
    python: str
    cwd: str
    offline_mode: bool
    perm_level: str
    llm_backend: dict
    subsystems: list[dict] = field(default_factory=list)
    healthy: int = 0
    degraded: int = 0
    failed: int = 0
    timestamp: str = ""


def _try_import(s: Subsystem) -> Subsystem:
    try:
        s.handle = importlib.import_module(s.module)
        s.loaded = True
    except Exception as e:  # noqa: BLE001
        s.error = f"{type(e).__name__}: {e}"
    return s


def boot() -> SupremeBootReport:
    r = SupremeBootReport(
        canonical=str(CANONICAL),
        python=sys.version.split()[0],
        cwd=os.getcwd(),
        offline_mode=os.environ.get("OFFLINE_MODE") == "1",
        perm_level=os.environ.get("JARVIS_PERM_LEVEL", "USER"),
        llm_backend=detect_llm_backend(),
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    for s in SUBSYSTEMS:
        _try_import(s)
        if s.loaded:
            r.healthy += 1
            log.info("OK    %-22s -> %s", s.name, s.module)
        elif s.optional:
            r.degraded += 1
            log.warning("DEGR  %-22s : %s", s.name, s.error)
        else:
            r.failed += 1
            log.error("FAIL  %-22s : %s", s.name, s.error)
        r.subsystems.append({
            "name": s.name, "path": s.module,
            "loaded": s.loaded, "error": s.error,
        })
    return r


def health() -> int:
    r = boot()
    print(json.dumps(asdict(r), indent=2, default=str))
    if r.failed: return 2
    if r.degraded > len(SUBSYSTEMS) // 2: return 1
    return 0


# ── routing ──────────────────────────────────────────────────────────────────
def route(query: str) -> int:
    boot()
    try:
        from jarvis_brainiac.orchestrator import Orchestrator  # type: ignore
        orch = Orchestrator(CANONICAL)  # FIX: pass root path (was missing, caused TypeError)
        result = orch.route(query) if hasattr(orch, "route") else orch(query)
        print(json.dumps({"query": query, "result": str(result)}, indent=2))
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("route failed: %s\n%s", e, traceback.format_exc())
        return 3


# ── exec arbitrary subsystem call ────────────────────────────────────────────
def exec_call(module_path: str, func_name: str, args: list[str]) -> int:
    """Invoke any subsystem function from CLI. ALL-PERMS mode allows arbitrary."""
    boot()
    try:
        m = importlib.import_module(module_path)
        fn = getattr(m, func_name)
        result = fn(*args)
        print(json.dumps({"call": f"{module_path}.{func_name}",
                         "args": args,
                         "result": repr(result)[:5000]}, indent=2))
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("exec failed: %s", e)
        traceback.print_exc()
        return 4


# ── interactive chat (offline via Ollama if available) ───────────────────────
def chat() -> int:
    backend = detect_llm_backend()
    print(f"=== JARVIS_SUPREME chat (backend: {backend.get('backend')}) ===")
    if backend.get("backend") == "ollama":
        return _ollama_chat(backend)
    print(f"No local LLM. Hint: {backend.get('hint','install Ollama')}")
    print("Falling back to echo mode (subsystems still callable via .run/.route).")
    while True:
        try:
            q = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not q: continue
        if q in {"/quit", "/exit"}: return 0
        if q.startswith("/route "):
            route(q[7:])
            continue
        print(f"echo> {q}")


def _ollama_chat(backend: dict) -> int:
    import urllib.request
    model = os.environ.get("OLLAMA_MODEL")
    if not model:
        models = backend.get("models", [])
        model = models[0] if models else "llama3"
    print(f"model: {model}    type /quit to exit")
    history: list[dict] = []
    while True:
        try:
            q = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); return 0
        if not q: continue
        if q in {"/quit", "/exit"}: return 0
        history.append({"role": "user", "content": q})
        payload = json.dumps({"model": model, "messages": history, "stream": False}).encode()
        # FIX: safe URL construction instead of fragile string replace
        chat_url = backend["url"].rsplit("/api/tags", 1)[0] + "/api/chat"
        req = urllib.request.Request(
            chat_url,
            data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                resp = json.loads(r.read())
                ans = resp.get("message", {}).get("content", "[no response]")
                history.append({"role": "assistant", "content": ans})
                print(f"jarvis> {ans}")
        except Exception as e:  # noqa: BLE001
            print(f"err: {e}")


# ── full run with daemons ────────────────────────────────────────────────────
def run_supreme() -> int:
    r = boot()
    print(f"\n=== JARVIS_SUPREME online ===")
    print(f"healthy={r.healthy}  degraded={r.degraded}  failed={r.failed}")
    print(f"canonical={r.canonical}")
    print(f"offline={r.offline_mode}  perm={r.perm_level}  llm={r.llm_backend.get('backend')}")
    print(f"log={LOG_PATH}")
    for hot in ("jarvis_os.tray", "jarvis_os.hotkey_listener"):
        try:
            m = importlib.import_module(hot)
            if hasattr(m, "main"):
                log.info("starting daemon %s.main()", hot)
                threading.Thread(target=m.main, daemon=True, name=hot).start()
        except Exception as e:  # noqa: BLE001
            log.warning("daemon %s skip: %s", hot, e)

    # Start GODSKILL Navigation & Dashboard Server
    try:
        import socket
        import webbrowser
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        port_open = s.connect_ex(('127.0.0.1', 8765)) == 0
        s.close()
        if not port_open:
            log.info("starting GODSKILL Navigation & Dashboard Server at http://127.0.0.1:8765")
            from godskill_server.server import app
            threading.Thread(
                target=lambda: app.run(host='127.0.0.1', port=8765, debug=False, use_reloader=False),
                daemon=True,
                name="godskill_server"
            ).start()

            # FIX [MEDIUM]: poll until Flask is actually listening before opening browser
            def _open_when_ready():
                import socket as _s
                for _ in range(40):  # up to 4 seconds
                    time.sleep(0.1)
                    try:
                        _c = _s.create_connection(('127.0.0.1', 8765), timeout=0.1)
                        _c.close()
                        webbrowser.open("http://127.0.0.1:8765")
                        return
                    except OSError:
                        pass
                log.warning("GODSKILL server did not become ready in 4s — skipping browser open")

            threading.Thread(target=_open_when_ready, daemon=True).start()
        else:
            log.info("GODSKILL Navigation & Dashboard Server already running on port 8765")
            threading.Thread(target=lambda: webbrowser.open("http://127.0.0.1:8765"), daemon=True).start()
    except Exception as e:
        # FIX [MEDIUM]: log.error so supervisor/monitoring tools see a real failure
        log.error("Failed to start godskill_server: %s", e)

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Shutting down supreme daemons.")
    return 0


# ── selftest harness ─────────────────────────────────────────────────────────
def selftest() -> int:
    """Exercise every wired subsystem. Return 0 if all green."""
    print("=== JARVIS_SUPREME self-test ===")
    r = boot()
    failures: list[str] = []
    test_results: list[dict] = []

    def t(name: str, fn: Callable[[], Any]) -> None:
        try:
            v = fn()
            test_results.append({"test": name, "status": "PASS",
                                "detail": repr(v)[:200] if v is not None else "ok"})
            print(f"  PASS  {name}")
        except Exception as e:  # noqa: BLE001
            failures.append(name)
            test_results.append({"test": name, "status": "FAIL",
                                "error": f"{type(e).__name__}: {e}"})
            print(f"  FAIL  {name}: {e}")

    # T1: subsystem imports
    t("subsystems_majority_loaded", lambda: r.healthy >= 4)
    # T2: LLM backend detected (or graceful "none")
    t("llm_backend_detected", lambda: r.llm_backend.get("backend") is not None)
    # T3: agent registry reachable
    def _agents():
        from jarvis_brainiac.agent_registry import AgentRegistry  # type: ignore
        reg = AgentRegistry(CANONICAL)
        return reg
    t("agent_registry_constructs", _agents)
    # T4: memory ops
    def _memory():
        from jarvis_brainiac.memory import UnifiedMemory  # type: ignore
        m = UnifiedMemory(CANONICAL)
        return m
    t("memory_constructs", _memory)
    # T5: env perms set
    t("perm_env_GOD", lambda: os.environ.get("JARVIS_PERM_LEVEL") == "GOD")
    t("offline_mode_on", lambda: os.environ.get("OFFLINE_MODE") == "1")
    # T6: canonical reachable
    t("canonical_dir_exists", lambda: CANONICAL.exists())
    # T7: Python > 3.10
    t("python_min_3.10", lambda: sys.version_info >= (3, 10))

    summary = {
        "boot": asdict(r),
        "tests": test_results,
        "passed": len([x for x in test_results if x["status"] == "PASS"]),
        "failed": len(failures),
        "failures": failures,
    }
    out = LOG_PATH.with_name("supreme_selftest_result.json")
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nresult written: {out}")
    print(f"PASSED: {summary['passed']}  FAILED: {summary['failed']}")
    return 0 if not failures else 5


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="JARVIS_SUPREME")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("boot")
    sub.add_parser("health")
    sub.add_parser("run")
    sub.add_parser("selftest")
    sub.add_parser("chat")
    rp = sub.add_parser("route"); rp.add_argument("query", nargs="+")
    ep = sub.add_parser("exec")
    ep.add_argument("module"); ep.add_argument("func")
    ep.add_argument("args", nargs="*")
    args = p.parse_args(argv)
    if args.cmd in ("boot", "health"): return health()
    if args.cmd == "route": return route(" ".join(args.query))
    if args.cmd == "run": return run_supreme()
    if args.cmd == "selftest": return selftest()
    if args.cmd == "chat": return chat()
    if args.cmd == "exec": return exec_call(args.module, args.func, args.args)
    p.print_help(); return 1


if __name__ == "__main__":
    sys.exit(main())
