"""Supreme entry point — boots JARVIS with full character system active.

Initialises the persona engine, character state, and Amjad memory, then
prints the JARVIS startup banner before handing off to the runtime loop.

Run with::

    python -m agency.supreme_main
    # or (if installed)
    agency-supreme
"""

from __future__ import annotations

import argparse
import datetime
import signal
import sys
import threading
import time
from typing import Any

from .amjad_memory import AmjadMemory, get_amjad_memory
from .character_state import CharacterState
from .jarvis_greeting import get_farewell, get_startup_banner
from .logging import configure, get_logger
from .persona_engine import PersonaEngine

log = get_logger()


class BootedSystem:
    """Container for all JARVIS subsystems after a successful boot.

    Attributes
    ----------
    persona:
        :class:`PersonaEngine` — voice and mode management.
    character:
        :class:`CharacterState` — live runtime state singleton.
    memory:
        :class:`AmjadMemory` — owner knowledge base.
    """

    def __init__(
        self,
        persona: PersonaEngine,
        character: CharacterState,
        memory: AmjadMemory,
    ) -> None:
        self.persona = persona
        self.character = character
        self.memory = memory

    def status(self) -> dict[str, Any]:
        """Return a health-check dict suitable for the startup banner."""
        snap = self.character.snapshot()
        subsystems = {
            "persona_engine": {"healthy": True, "detail": f"mode={self.character.current_mode}"},
            "character_state": {"healthy": True, "detail": f"interactions={snap['total_interactions']}"},
            "amjad_memory": {"healthy": True, "detail": f"owner={self.memory.owner_name()}"},
        }
        return {
            "ok": True,
            "mode": self.character.current_mode,
            "systems_ok": len(subsystems),
            "systems_total": len(subsystems),
            "subsystems": subsystems,
        }

    def process(self, request: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Process a request through JARVIS persona.

        Detects mode, records interaction, and formats response with
        the JARVIS voice.

        Parameters
        ----------
        request:
            The raw user query.
        context:
            Optional dict with keys like ``"response"`` (raw LLM text),
            ``"domain"`` (routing domain), ``"mode"`` (override mode).

        Returns
        -------
        dict
            Result dict with ``"response"``, ``"persona_mode"``, and
            passthrough context keys.
        """
        ctx = context or {}
        raw_response = ctx.get("response", "")
        mode = ctx.get("mode") or self.persona.detect_mode(request)

        # Format with JARVIS voice
        formatted = self.persona.format_response(raw_response, mode) if raw_response else ""

        # Record the interaction
        self.character.record_interaction(domain=ctx.get("domain", "general"))
        self.character.add_context("user", request)
        if formatted:
            self.character.add_context("assistant", formatted)

        result = dict(ctx)
        result.update(
            {
                "request": request,
                "response": formatted or raw_response,
                "persona_mode": mode,
            }
        )
        return result


def initialise_character_system() -> BootedSystem:
    """Construct and wire all JARVIS character subsystems.

    Returns
    -------
    BootedSystem
        Container holding persona, character, and memory.
    """
    persona = PersonaEngine()
    character = CharacterState.get_instance(force_new=False)
    memory = get_amjad_memory()
    return BootedSystem(persona=persona, character=character, memory=memory)


def boot(
    *,
    mode: str = "supreme_brainiac",
    start_server: bool = False,
    host: str = "127.0.0.1",
    port: int = 8001,
) -> int:
    """Boot the JARVIS runtime. Returns process exit code."""
    configure()

    system = initialise_character_system()
    system.character.set_mode(mode)
    status = system.status()

    # Print JARVIS banner
    banner = get_startup_banner(status)
    print(banner)

    stop = threading.Event()

    def _on_signal(signum: int, _frame: Any) -> None:
        stop.set()

    signal.signal(signal.SIGINT, _on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _on_signal)

    if start_server:
        try:
            import uvicorn  # type: ignore
            from .server import build_app  # type: ignore

            app = build_app()
            config = uvicorn.Config(app, host=host, port=port, log_level="info")
            server = uvicorn.Server(config)
            thread = threading.Thread(target=server.run, daemon=True)
            thread.start()
            while not stop.is_set() and thread.is_alive():
                time.sleep(0.5)
            server.should_exit = True
            thread.join(timeout=5.0)
        except Exception as exc:
            log.error("control server failed: %s", exc)
            return 1
    else:
        while not stop.is_set():
            time.sleep(0.5)

    print(get_farewell(system.memory.owner_name()))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agency-supreme")
    parser.add_argument(
        "--mode",
        default="supreme_brainiac",
        choices=["supreme_brainiac", "academic", "executor", "guardian", "casual"],
        help="JARVIS persona mode to boot with",
    )
    parser.add_argument(
        "--serve", action="store_true", help="start the FastAPI control server"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args(argv)
    return boot(
        mode=args.mode,
        start_server=args.serve,
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
