"""RobotBrain — master coordinator for the JARVIS humanoid robot.

Ties together:
* SimulationBridge  — physics engine / hardware interface
* STTEngine         — voice → text
* NLPMotionParser   — text → motion command
* RobotVision       — camera perception
* LongTermMemory    — persistent memory (imported from agency core)

CLI subcommands are registered in agency/cli.py.

Usage
-----
    from agency.robotics.robot_brain import RobotBrain
    from agency.robotics.simulation import SimulationBackend
    from agency.robotics.stt import STTBackend

    brain = RobotBrain(sim_backend=SimulationBackend.MOCK,
                       stt_backend=STTBackend.MOCK,
                       use_vision=False)
    brain.start()
    brain.execute_text_command("walk forward 2 meters")
    print(brain.status())
    brain.emergency_stop()
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

from ..logging import get_logger
from .simulation import SimulationBridge, SimulationBackend
from .stt import STTEngine, STTBackend
from .nlp_to_motion import NLPMotionParser
from .vision_perception import RobotVision

log = get_logger()


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------

def _audit(event: str, payload: Dict[str, Any]) -> None:
    try:
        from ..audit import append as _append
        _append(event, payload)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# RobotBrain
# ---------------------------------------------------------------------------

class RobotBrain:
    """Master controller — voice → parse → motion, with memory & vision.

    Parameters
    ----------
    sim_backend:
        Simulation backend to use. Default MOCK (no physics lib required).
    stt_backend:
        STT backend. Default MOCK (no microphone required).
    use_vision:
        If True, starts RobotVision (webcam + object detection).
    use_llm_fallback:
        Allow NLPMotionParser to call the LLM for unrecognised commands.
    """

    def __init__(
        self,
        sim_backend: SimulationBackend = SimulationBackend.MOCK,
        stt_backend: STTBackend = STTBackend.MOCK,
        use_vision: bool = False,
        use_llm_fallback: bool = False,
    ) -> None:
        self.sim    = SimulationBridge(sim_backend)
        self.stt    = STTEngine(backend=stt_backend)
        self.parser = NLPMotionParser(use_llm_fallback=use_llm_fallback)
        self.vision: Optional[RobotVision] = RobotVision(use_mock=True) if use_vision else None

        # Long-term memory (best-effort import)
        try:
            from ..long_term_memory import LongTermMemory
            self.memory: Any = LongTermMemory()
        except Exception:
            self.memory = None

        self.running    = False
        self._start_time: Optional[float] = None
        self._voice_thread: Optional[threading.Thread] = None
        self._command_count = 0
        self._last_command  = ""

    # --- lifecycle ---

    def start(self) -> None:
        """Initialise simulation and vision."""
        self.sim.load_humanoid()
        if self.vision:
            self.vision.start()
        self.running    = True
        self._start_time = time.monotonic()
        _audit("robot.brain.start", {"sim": self.sim.backend, "vision": self.vision is not None})
        log.info("RobotBrain started")

    def stop(self) -> None:
        """Graceful shutdown."""
        self.running = False
        if self.vision:
            self.vision.stop()
        self.sim.disconnect()
        _audit("robot.brain.stop", {})
        log.info("RobotBrain stopped")

    # --- voice control loop ---

    def start_voice_control(self) -> None:
        """Run listen→parse→execute in a blocking loop.

        Stops when self.running = False.
        """
        log.info("RobotBrain entering voice control mode")
        while self.running:
            text = self.stt.listen(timeout=5.0)
            if text:
                self.execute_text_command(text)

    def start_voice_control_async(self) -> None:
        """Start voice control in a background thread."""
        self._voice_thread = threading.Thread(
            target=self.start_voice_control, daemon=True
        )
        self._voice_thread.start()

    # --- command execution ---

    def execute_text_command(self, text: str) -> bool:
        """Parse *text* and execute the resulting motion command.

        Returns True on success, False if unrecognised or execution failed.
        """
        log.info("RobotBrain.execute_text_command text=%r", text)
        cmd = self.parser.parse(text)
        if cmd is None:
            log.warning("RobotBrain: unrecognised command %r", text)
            _audit("robot.brain.unrecognised", {"text": text})
            return False

        _audit("robot.brain.command", {
            "skill": cmd.skill_name,
            "params": str(cmd.params),
            "confidence": cmd.confidence,
        })

        # Optionally record to long-term memory
        if self.memory:
            try:
                self.memory.remember(
                    f"robot.cmd.{self._command_count}",
                    f"{cmd.skill_name} {cmd.params}",
                    tags=["robotics", "command"],
                )
            except Exception:
                pass

        self._command_count += 1
        self._last_command = text

        success = self.parser.execute(cmd, self.sim)
        log.info("RobotBrain.execute result=%s skill=%s", success, cmd.skill_name)
        return success

    # --- status ---

    def status(self) -> Dict[str, Any]:
        """Return current brain status snapshot."""
        uptime = time.monotonic() - self._start_time if self._start_time else 0.0
        joint_states = self.sim.get_joint_states() if self.running else {}
        return {
            "running":        self.running,
            "uptime_s":       round(uptime, 1),
            "sim_backend":    str(self.sim.backend),
            "stt_backend":    "mock" if self.stt.is_mock else "real",
            "vision_active":  self.vision is not None,
            "command_count":  self._command_count,
            "last_command":   self._last_command,
            "joint_states":   joint_states,
        }

    # --- emergency ---

    def emergency_stop(self) -> None:
        """Immediately halt all motion and log an audit event."""
        log.warning("RobotBrain EMERGENCY STOP")
        _audit("robot.brain.emergency_stop", {"command_count": self._command_count})
        try:
            from .motion_skills import stand_still
            stand_still(self.sim)
        except Exception as exc:
            log.error("emergency_stop motion failed: %s", exc)

    # --- context manager ---

    def __enter__(self) -> "RobotBrain":
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop()
