import atexit
import time
import threading
import logging
from pathlib import Path

log = logging.getLogger("jarvis.heartbeat")

class SingularityHeartbeat:
    """
    The Autonomous Living Loop of JARVIS BRAINIAC.
    Periodically awakens, queries its own memory, performs self-reflection,
    and runs maintenance without user prompt.

    Imports are intentionally lazy (inside methods) to avoid circular import chains:
        heartbeat → singularity_core → agent_forge → singularity_core
    """
    def __init__(self, root_path):
        self.root_path = Path(root_path)
        self._omni = None   # lazy-loaded
        self._memory = None # lazy-loaded
        self.running = False
        self.thread = None

    # ── lazy loaders ──────────────────────────────────────────────────────────
    def _get_omni(self):
        """CR-004 FIX: Use FreeLLM instead of dead OmniModelSingularity.
        OmniModelSingularity was Claude-based and was removed in REQ-063.
        FreeLLM is the correct 100%-free replacement.
        """
        if self._omni is None:
            try:
                from jarvis_brainiac.free_llm import get_llm
                self._omni = get_llm()
                log.info("[HEARTBEAT] FreeLLM loaded as reflection engine")
            except Exception as e:
                log.warning("[HEARTBEAT] Could not load FreeLLM: %s", e)
        return self._omni

    def _get_memory(self):
        if self._memory is None:
            try:
                from jarvis_brainiac.memory import UnifiedMemory
                self._memory = UnifiedMemory(self.root_path)
            except Exception as e:
                log.warning("[HEARTBEAT] Could not load UnifiedMemory: %s", e)
        return self._memory

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start(self, interval_seconds=300):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(
            target=self._loop,
            args=(interval_seconds,),
            daemon=True,
            name="singularity_heartbeat"
        )
        self.thread.start()
        log.info("Singularity Heartbeat started (interval=%ds). Agent is now autonomous.", interval_seconds)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    # ── internal loop ─────────────────────────────────────────────────────────
    def _loop(self, interval):
        while self.running:
            try:
                time.sleep(interval)
                self._reflect()
            except Exception as e:
                log.error("[HEARTBEAT] Loop error: %s", e, exc_info=True)

    def _reflect(self):
        log.info("[HEARTBEAT] Awakening for autonomous self-reflection...")
        memory = self._get_memory()
        if not memory:
            log.warning("[HEARTBEAT] Memory unavailable — skipping reflection.")
            return

        # MR-005 FIX: empty string → memory.recall returns latest N entries by recency
        try:
            recent = memory.recall("", limit=5)

        except Exception as e:
            log.warning("[HEARTBEAT] recall() failed: %s", e)
            return

        if not recent:
            log.info("[HEARTBEAT] No recent memories to reflect on.")
            return

        omni = self._get_omni()
        if not omni:
            log.warning("[HEARTBEAT] OmniModel unavailable — skipping reflection.")
            return

        context = "\n".join([f"- {r.content}" for r in recent])
        query = (
            "INTERNAL REFLECTION: Review these recent memories and summarize "
            f"any pending tasks or insights:\n{context}"
        )

        try:
            # CR-004 FIX: FreeLLM.chat() returns LLMResponse with .text attribute
            llm_resp = omni.chat(
                query,
                system="You are JARVIS, an autonomous AI. Reflect concisely on pending tasks."
            )
            insight = llm_resp.text if hasattr(llm_resp, "text") else str(llm_resp)

            log.info("[HEARTBEAT] Self-Reflection complete (%d bytes).", len(insight))

            # Store insight back into episodic memory
            memory.remember(
                kind="episodic",
                content=insight[:2000],  # cap at 2KB
                tags=["self-reflection", "autonomous"]
            )
        except Exception as e:
            log.warning("[HEARTBEAT] Reflection failed: %s", e, exc_info=True)


# ── module-level singleton ────────────────────────────────────────────────────
_heartbeat: SingularityHeartbeat | None = None

def start_heartbeat(root_path, interval: int = 300) -> None:
    global _heartbeat
    if _heartbeat is None:
        _heartbeat = SingularityHeartbeat(root_path)
        _heartbeat.start(interval)
        # LR-004 FIX: register stop() with atexit for clean shutdown
        atexit.register(_heartbeat.stop)
