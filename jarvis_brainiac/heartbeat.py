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
        if self._omni is None:
            try:
                from runtime.agency.singularity_core import OmniModelSingularity
                self._omni = OmniModelSingularity(enable_caching=False)
            except Exception as e:
                log.warning("[HEARTBEAT] Could not load OmniModelSingularity: %s", e)
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

        # Recall recent memories (query="" returns latest rows by recency)
        try:
            recent = memory.recall("jarvis", limit=5)
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
            # route_request() returns SingularityResponse, not a dict
            resp = omni.route_request(query)
            result = resp.result
            if hasattr(result, "to_dict"):
                result_dict = result.to_dict()
                insight = (result_dict.get("final_output")
                           or result_dict.get("conclusion")
                           or result_dict.get("answer")
                           or str(result_dict))
            else:
                insight = str(result) if result else "No insights generated."

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
