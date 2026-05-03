"""
ReAct Loop for JARVIS BRAINIAC
==============================
Infinite autonomous loop: Observe → Reason → Decide → Act → Reflect → Learn.

Architecture:
    1. OBSERVE: Listen to user (voice / text / vision)
    2. REASON:  Analyze with local LLM
    3. DECIDE:  Choose action (code / shell / search / ask / speak / move / done)
    4. ACT:     Execute action via subsystems
    5. REFLECT: Evaluate result (success, error, partial)
    6. LEARN:   Store in vector memory, self-heal if error

The loop runs on a background thread until a shutdown signal is received.
"""

import time
import threading
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants & Configuration
# ---------------------------------------------------------------------------

DEFAULT_STEP_TIMEOUT: float = 120.0          # seconds per step
DEFAULT_LOOP_SLEEP: float = 0.5              # seconds between iterations
DEFAULT_SLEEP_JITTER: float = 0.4              # ± jitter on sleep


class State(Enum):
    """Finite-state-machine states for the ReAct loop."""
    IDLE     = "IDLE"
    OBSERVE  = "OBSERVE"
    REASON   = "REASON"
    DECIDE   = "DECIDE"
    ACT      = "ACT"
    REFLECT  = "REFLECT"
    LEARN    = "LEARN"


class Action(Enum):
    """Allowed actions the agent can decide to take."""
    WRITE_CODE    = "WRITE_CODE"
    EXECUTE_SHELL = "EXECUTE_SHELL"
    SEARCH_GITHUB = "SEARCH_GITHUB"
    ASK_USER      = "ASK_USER"
    MOVE_MOUSE    = "MOVE_MOUSE"
    SPEAK         = "SPEAK"
    DONE          = "DONE"


_ALLOWED_ACTIONS: Tuple[str, ...] = tuple(a.value for a in Action)


# ---------------------------------------------------------------------------
# ReActLoop
# ---------------------------------------------------------------------------

class ReActLoop:
    """
    ReAct autonomous loop for JARVIS BRAINIAC.

    Methods
    -------
    start() / stop()
        Background thread lifecycle.
    step() -> dict
        Execute a single ReAct iteration (useful for synchronous callers).
    observe() / reason() / decide() / act() / reflect() / learn()
        Individual pipeline stages with full instrumentation.
    self_heal() -> bool
        Attempt to recover from execution errors automatically.
    get_state() / get_stats()
        Introspection helpers.
    """

    def __init__(
        self,
        brain: Any = None,
        voice: Any = None,
        vision: Any = None,
        memory: Any = None,
        os_controller: Any = None,
        skills: Any = None,
        github: Any = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Accept all subsystem instances and prepare the loop.

        Parameters
        ----------
        brain : Any
            Local LLM / reasoning engine. Expected interface:
            - `generate(prompt: str, **kwargs) -> str`
            - `heal_code(error: str, context: dict) -> str`
        voice : Any
            Voice I/O subsystem. Expected interface:
            - `is_listening() -> bool`
            - `get_transcript() -> str`
            - `synthesize(text: str) -> bool`
        vision : Any
            Camera / vision subsystem. Expected interface:
            - `is_active() -> bool`
            - `describe_frame() -> str`
        memory : Any
            Vector memory store. Expected interface:
            - `store(text: str, metadata: dict) -> bool`
            - `search(query: str, k: int) -> List[dict]`
        os_controller : Any
            OS-level execution controller. Expected interface:
            - `run_command(cmd: str, timeout: float) -> dict`
            - `write_file(path: str, content: str) -> bool`
            - `move_mouse(x: int, y: int) -> bool`
        skills : Any
            Skill / code generation registry. Expected interface:
            - `generate_code(description: str, context: dict) -> str`
            - `register_skill(name: str, code: str) -> bool`
        github : Any
            GitHub integration. Expected interface:
            - `search_repos(query: str, limit: int) -> List[dict]`
        config : dict, optional
            Override default loop constants.
        """
        # -- Subsystems --------------------------------------------------------
        self.brain = brain
        self.voice = voice
        self.vision = vision
        self.memory = memory
        self.os_controller = os_controller
        self.skills = skills
        self.github = github

        # -- Configuration -----------------------------------------------------
        cfg = config or {}
        self.step_timeout: float = cfg.get("step_timeout", DEFAULT_STEP_TIMEOUT)
        self.loop_sleep: float = cfg.get("loop_sleep", DEFAULT_LOOP_SLEEP)
        self.sleep_jitter: float = cfg.get("sleep_jitter", DEFAULT_SLEEP_JITTER)
        self.verbose: bool = cfg.get("verbose", True)
        self.max_consecutive_errors: int = cfg.get("max_consecutive_errors", 5)
        self.auto_heal: bool = cfg.get("auto_heal", True)

        # -- State machine -----------------------------------------------------
        self._state: State = State.IDLE
        self._lock = threading.Lock()

        # -- Threading ---------------------------------------------------------
        self._thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()
        self._running: bool = False

        # -- Statistics ---------------------------------------------------------
        self._stats: Dict[str, Any] = {
            "iterations": 0,
            "errors": 0,
            "heals": 0,
            "skills_learned": 0,
            "started_at": None,
            "last_step_at": None,
        }
        self._consecutive_errors: int = 0

        # -- Step cache (for introspection / resumability) ----------------------
        self._last_step_result: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the infinite loop in a background daemon thread."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._shutdown_event.clear()
            self._stats["started_at"] = datetime.utcnow().isoformat()

        self._thread = threading.Thread(target=self._run, name="ReActLoop", daemon=True)
        self._thread.start()

        if self.verbose:
            print(f"[ReActLoop] Started at {self._stats['started_at']}")

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the loop to stop and join the thread with a timeout."""
        with self._lock:
            if not self._running:
                return
            self._running = False

        self._shutdown_event.set()

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                print("[ReActLoop] WARNING: Thread did not terminate within timeout.")

        self._set_state(State.IDLE)
        if self.verbose:
            print("[ReActLoop] Stopped.")

    def _run(self) -> None:
        """Internal infinite runner."""
        while not self._shutdown_event.is_set():
            try:
                self.step()
            except Exception as exc:
                self._stats["errors"] += 1
                self._consecutive_errors += 1
                print(f"[ReActLoop] Unhandled exception in loop: {exc}")
                if self._consecutive_errors >= self.max_consecutive_errors:
                    print("[ReActLoop] Max consecutive errors reached. Halting.")
                    break

            # Configurable sleep with jitter to prevent busy-wait patterns
            jitter = (self.sleep_jitter * (hash(time.time()) % 3 - 1)) / 1.0
            sleep_time = max(0.01, self.loop_sleep + jitter)
            time.sleep(sleep_time)

    # ------------------------------------------------------------------
    # Single-step execution (synchronous API)
    # ------------------------------------------------------------------

    def step(self) -> Dict[str, Any]:
        """
        Execute **one** full ReAct iteration.

        Returns
        -------
        dict
            {
                "observation": {...},
                "thought":     "...",
                "action":      "...",
                "result":      {...},
                "reflection":  "...",
                "learned":     bool,
            }
        """
        start_ts = time.time()
        self._stats["iterations"] += 1
        self._consecutive_errors = 0

        # ---- OBSERVE --------------------------------------------------------
        self._set_state(State.OBSERVE)
        observation = self._with_timeout(self.observe, timeout=self.step_timeout)

        # If nothing is happening, skip the rest of the cycle to save energy
        if observation.get("content") in (None, "", "silence"):
            result = {
                "observation": observation,
                "thought": "No input detected. Idling.",
                "action": "DONE",
                "result": {"status": "idle", "detail": "no_input"},
                "reflection": "Nothing to do.",
                "learned": False,
            }
            self._last_step_result = result
            self._stats["last_step_at"] = datetime.utcnow().isoformat()
            self._set_state(State.IDLE)
            return result

        # ---- REASON ---------------------------------------------------------
        self._set_state(State.REASON)
        reasoning = self._with_timeout(
            self.reason, observation, timeout=self.step_timeout
        )

        # ---- DECIDE -----------------------------------------------------------
        self._set_state(State.DECIDE)
        action_name = self.decide(reasoning)
        payload = reasoning.get("payload", "")
        confidence = reasoning.get("confidence", 0.0)

        # ---- ACT --------------------------------------------------------------
        self._set_state(State.ACT)
        action_result = self._with_timeout(
            self.act, action_name, payload, timeout=self.step_timeout
        )

        # ---- REFLECT ----------------------------------------------------------
        self._set_state(State.REFLECT)
        reflection = self.reflect(action_name, action_result)

        # ---- LEARN ------------------------------------------------------------
        self._set_state(State.LEARN)
        learned = self.learn(reflection)

        # ---- Assemble result --------------------------------------------------
        result = {
            "observation": observation,
            "thought": reasoning.get("thought", ""),
            "action": action_name,
            "result": action_result,
            "reflection": reflection.get("summary", ""),
            "learned": learned,
        }
        self._last_step_result = result
        self._stats["last_step_at"] = datetime.utcnow().isoformat()
        self._set_state(State.IDLE)

        if self.verbose:
            elapsed = time.time() - start_ts
            print(
                f"[ReActLoop] Step #{self._stats['iterations']}: "
                f"{action_name} in {elapsed:.2f}s | learned={learned}"
            )

        return result

    # ------------------------------------------------------------------
    # Pipeline Stages
    # ------------------------------------------------------------------

    def observe(self) -> Dict[str, Any]:
        """
        Gather input from all sensors.

        Priority: Voice > Vision > Text (can be reordered via config).

        Returns
        -------
        dict
            {"source": "voice|vision|text", "content": "...", "confidence": float}
        """
        # -- Voice sensor -------------------------------------------------------
        if self.voice is not None and hasattr(self.voice, "is_listening"):
            try:
                if self.voice.is_listening():
                    transcript = ""
                    if hasattr(self.voice, "get_transcript"):
                        transcript = self.voice.get_transcript() or ""
                    if transcript:
                        return {
                            "source": "voice",
                            "content": transcript,
                            "confidence": 0.95,
                        }
            except Exception as exc:
                if self.verbose:
                    print(f"[ReActLoop] Voice observe error: {exc}")

        # -- Vision sensor ------------------------------------------------------
        if self.vision is not None and hasattr(self.vision, "is_active"):
            try:
                if self.vision.is_active():
                    description = ""
                    if hasattr(self.vision, "describe_frame"):
                        description = self.vision.describe_frame() or ""
                    if description:
                        return {
                            "source": "vision",
                            "content": description,
                            "confidence": 0.85,
                        }
            except Exception as exc:
                if self.verbose:
                    print(f"[ReActLoop] Vision observe error: {exc}")

        # -- Text sensor (default / fallback) -----------------------------------
        return {"source": "text", "content": "", "confidence": 0.0}

    def reason(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send the observation to the local LLM for reasoning.

        Returns
        -------
        dict
            {
                "thought":    str,
                "action":     "WRITE_CODE|...",
                "payload":    str,
                "confidence": float,
            }
        """
        if self.brain is None or not hasattr(self.brain, "generate"):
            # Fallback: echo the observation back with a safe default action
            return {
                "thought": f"No brain available. Observation: {observation.get('content', '')}",
                "action": "ASK_USER",
                "payload": "I don't have a reasoning engine right now. What should I do?",
                "confidence": 0.1,
            }

        prompt = self._build_reasoning_prompt(observation)
        try:
            raw = self.brain.generate(prompt, max_tokens=512, temperature=0.3)
            parsed = self._parse_reasoning_output(raw)
            return parsed
        except Exception as exc:
            if self.verbose:
                print(f"[ReActLoop] Reasoning error: {exc}")
            return {
                "thought": f"Reasoning failed: {exc}",
                "action": "ASK_USER",
                "payload": "My reasoning engine encountered an error. Can you rephrase?",
                "confidence": 0.0,
            }

    def decide(self, reasoning: Dict[str, Any]) -> str:
        """
        Convert reasoning to a validated action name.

        Returns
        -------
        str
            One of the allowed action strings.
        """
        raw_action = reasoning.get("action", "ASK_USER")
        action_name = raw_action.strip().upper()
        if action_name not in _ALLOWED_ACTIONS:
            action_name = "ASK_USER"
        return action_name

    def act(self, action: str, payload: str) -> Dict[str, Any]:
        """
        Execute the chosen action.

        Supported actions:
            WRITE_CODE    → skills.generate_code → os.write_file → os.run_command
            EXECUTE_SHELL → os.run_command
            SEARCH_GITHUB → github.search_repos
            ASK_USER      → voice.synthesize
            MOVE_MOUSE    → os.move_mouse
            SPEAK         → voice.synthesize
            DONE          → no-op success

        Returns
        -------
        dict
            {"status": "success|error|partial", "output": Any, "error": str|None}
        """
        result: Dict[str, Any] = {"status": "error", "output": None, "error": None}

        try:
            if action == Action.WRITE_CODE.value:
                result = self._act_write_code(payload)
            elif action == Action.EXECUTE_SHELL.value:
                result = self._act_execute_shell(payload)
            elif action == Action.SEARCH_GITHUB.value:
                result = self._act_search_github(payload)
            elif action == Action.ASK_USER.value:
                result = self._act_ask_user(payload)
            elif action == Action.MOVE_MOUSE.value:
                result = self._act_move_mouse(payload)
            elif action == Action.SPEAK.value:
                result = self._act_speak(payload)
            elif action == Action.DONE.value:
                result = {"status": "success", "output": "done", "error": None}
            else:
                result = {
                    "status": "error",
                    "output": None,
                    "error": f"Unknown action: {action}",
                }
        except Exception as exc:
            result = {"status": "error", "output": None, "error": str(exc)}

        return result

    def reflect(self, action: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate the action result.

        Returns
        -------
        dict
            {
                "summary":     str,
                "success":     bool,
                "error":       str|None,
                "confidence":  float,
                "plan_fix":    str|None,
            }
        """
        status = result.get("status", "error")
        error_msg = result.get("error")
        output = result.get("output")

        if status == "success":
            return {
                "summary": f"Action '{action}' completed successfully. Output: {output}",
                "success": True,
                "error": None,
                "confidence": 1.0,
                "plan_fix": None,
            }

        if status == "partial":
            return {
                "summary": f"Action '{action}' partially succeeded. Review needed.",
                "success": False,
                "error": error_msg,
                "confidence": 0.5,
                "plan_fix": "Review partial output and refine payload.",
            }

        # status == "error"
        fix_plan = None
        if self.auto_heal:
            fix_plan = f"Trigger self_heal for error: {error_msg}"

        return {
            "summary": f"Action '{action}' failed: {error_msg}",
            "success": False,
            "error": error_msg,
            "confidence": 0.0,
            "plan_fix": fix_plan,
        }

    def learn(self, reflection: Dict[str, Any]) -> bool:
        """
        Store the reflection in vector memory and trigger self-healing if needed.

        Returns
        -------
        bool
            True if new knowledge was persisted or a healing attempt was made.
        """
        learned = False

        # -- Persist to memory --------------------------------------------------
        if self.memory is not None and hasattr(self.memory, "store"):
            try:
                summary = reflection.get("summary", "")
                meta = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "success": reflection.get("success", False),
                    "error": reflection.get("error"),
                }
                self.memory.store(summary, metadata=meta)
                learned = True
            except Exception as exc:
                if self.verbose:
                    print(f"[ReActLoop] Memory store error: {exc}")

        # -- Self-heal on error ------------------------------------------------
        error_msg = reflection.get("error")
        if error_msg and self.auto_heal:
            healed = self.self_heal(
                error=error_msg,
                context={
                    "reflection_summary": reflection.get("summary", ""),
                    "last_step": self._last_step_result,
                },
            )
            if healed:
                learned = True

        # -- Update skill registry if new capability ----------------------------
        if self.skills is not None and hasattr(self.skills, "register_skill"):
            # A placeholder hook: in a real system this would be driven by
            # the LLM detecting a genuinely novel pattern.
            pass

        return learned

    # ------------------------------------------------------------------
    # Self-healing
    # ------------------------------------------------------------------

    def self_heal(self, error: str, context: Dict[str, Any]) -> bool:
        """
        Attempt to recover from an execution error automatically.

        Sequence:
            1. Analyze error with local LLM
            2. Generate fix
            3. Validate fix
            4. Apply fix
            5. Re-run the failed action

        Returns
        -------
        bool
            True if the error was successfully healed.
        """
        self._stats["heals"] += 1

        if self.brain is None or not hasattr(self.brain, "heal_code"):
            if self.verbose:
                print(f"[ReActLoop] No healing engine available for: {error}")
            return False

        try:
            # 1. Analyze & 2. Generate fix (delegated to brain)
            fix = self.brain.heal_code(error, context)

            # 3. Validate fix (lightweight: non-empty and plausible)
            if not fix or not isinstance(fix, str):
                if self.verbose:
                    print("[ReActLoop] Heal produced empty fix.")
                return False

            # 4. Apply fix — write to a scratch file via OS controller
            if self.os_controller is not None and hasattr(self.os_controller, "write_file"):
                scratch_path = "/tmp/jarvis_heal_fix.py"
                self.os_controller.write_file(scratch_path, fix)

            # 5. Re-run action if the last step is available
            if self._last_step_result is not None:
                action = self._last_step_result.get("action", "DONE")
                payload = self._last_step_result.get("result", {}).get("output", "")
                rerun = self.act(action, payload)
                if rerun.get("status") == "success":
                    if self.verbose:
                        print("[ReActLoop] Self-heal succeeded on re-run.")
                    return True

            if self.verbose:
                print("[ReActLoop] Self-heal fix generated but re-run not validated.")
            return False

        except Exception as exc:
            if self.verbose:
                print(f"[ReActLoop] Self-heal failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_state(self) -> str:
        """Return the current FSM state as a string."""
        with self._lock:
            return self._state.value

    def get_stats(self) -> Dict[str, Any]:
        """
        Return loop statistics.

        Returns
        -------
        dict
            {
                "iterations": int,
                "errors": int,
                "heals": int,
                "skills_learned": int,
                "uptime_seconds": float,
                "started_at": str|None,
                "last_step_at": str|None,
            }
        """
        stats = dict(self._stats)
        started = stats.get("started_at")
        if started:
            try:
                started_dt = datetime.fromisoformat(started)
                uptime = (datetime.utcnow() - started_dt).total_seconds()
            except ValueError:
                uptime = 0.0
        else:
            uptime = 0.0
        stats["uptime_seconds"] = round(uptime, 2)
        return stats

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set_state(self, state: State) -> None:
        with self._lock:
            self._state = state

    def _with_timeout(self, func, *args, timeout: float = DEFAULT_STEP_TIMEOUT, **kwargs):
        """Execute ``func`` with a hard timeout using threading."""
        result_container: List[Any] = [None]
        exception_container: List[Exception] = []

        def _target():
            try:
                result_container[0] = func(*args, **kwargs)
            except Exception as exc:
                exception_container.append(exc)

        t = threading.Thread(target=_target)
        t.start()
        t.join(timeout=timeout)

        if t.is_alive():
            raise TimeoutError(f"Step {func.__name__} exceeded {timeout}s timeout.")

        if exception_container:
            raise exception_container[0]

        return result_container[0]

    @staticmethod
    def _build_reasoning_prompt(observation: Dict[str, Any]) -> str:
        """Compose a structured prompt for the reasoning LLM."""
        content = observation.get("content", "")
        source = observation.get("source", "text")
        return (
            "You are JARVIS BRAINIAC, an autonomous AI agent.\n"
            "Observation:\n"
            f"  Source: {source}\n"
            f"  Content: {content}\n\n"
            "Reason step-by-step, then pick exactly ONE action:\n"
            "  WRITE_CODE    – generate and write code to a file\n"
            "  EXECUTE_SHELL – run a shell command\n"
            "  SEARCH_GITHUB – search GitHub repositories\n"
            "  ASK_USER      – ask the user for clarification\n"
            "  MOVE_MOUSE    – move the mouse cursor\n"
            "  SPEAK         – speak a response aloud\n"
            "  DONE          – nothing more to do this cycle\n\n"
            "Respond in this exact format:\n"
            "THOUGHT: <your reasoning>\n"
            "ACTION: <ONE action from the list>\n"
            "PAYLOAD: <arguments for the action>\n"
            "CONFIDENCE: <0.0-1.0>\n"
        )

    @staticmethod
    def _parse_reasoning_output(raw: str) -> Dict[str, Any]:
        """Parse the LLM's structured reasoning response."""
        thought = ""
        action = "ASK_USER"
        payload = ""
        confidence = 0.0

        for line in raw.strip().splitlines():
            line = line.strip()
            if line.startswith("THOUGHT:"):
                thought = line[len("THOUGHT:"):].strip()
            elif line.startswith("ACTION:"):
                action = line[len("ACTION:"):].strip().upper()
            elif line.startswith("PAYLOAD:"):
                payload = line[len("PAYLOAD:"):].strip()
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line[len("CONFIDENCE:"):].strip())
                except ValueError:
                    confidence = 0.0

        return {
            "thought": thought or raw,
            "action": action,
            "payload": payload,
            "confidence": max(0.0, min(1.0, confidence)),
        }

    # -- Action implementations -----------------------------------------

    def _act_write_code(self, payload: str) -> Dict[str, Any]:
        """Generate code, write to file, optionally run."""
        if self.skills is None or not hasattr(self.skills, "generate_code"):
            return {"status": "error", "output": None, "error": "No skills subsystem"}

        try:
            code = self.skills.generate_code(payload, context={})
            if self.os_controller is not None and hasattr(self.os_controller, "write_file"):
                # Infer a reasonable scratch path from payload or use default
                path = "/tmp/jarvis_generated.py"
                self.os_controller.write_file(path, code)

                # Try to run if os_controller supports it
                if hasattr(self.os_controller, "run_command"):
                    run_res = self.os_controller.run_command(f"python {path}", timeout=30.0)
                    return {
                        "status": "success" if run_res.get("returncode") == 0 else "partial",
                        "output": run_res.get("stdout", code),
                        "error": run_res.get("stderr"),
                    }

            return {"status": "success", "output": code, "error": None}
        except Exception as exc:
            return {"status": "error", "output": None, "error": str(exc)}

    def _act_execute_shell(self, payload: str) -> Dict[str, Any]:
        """Run a shell command via the OS controller."""
        if self.os_controller is None or not hasattr(self.os_controller, "run_command"):
            return {"status": "error", "output": None, "error": "No OS controller"}

        try:
            res = self.os_controller.run_command(payload, timeout=60.0)
            rc = res.get("returncode", -1)
            return {
                "status": "success" if rc == 0 else "error",
                "output": res.get("stdout"),
                "error": res.get("stderr") if rc != 0 else None,
            }
        except Exception as exc:
            return {"status": "error", "output": None, "error": str(exc)}

    def _act_search_github(self, payload: str) -> Dict[str, Any]:
        """Search GitHub repositories."""
        if self.github is None or not hasattr(self.github, "search_repos"):
            return {"status": "error", "output": None, "error": "No GitHub subsystem"}

        try:
            repos = self.github.search_repos(payload, limit=5)
            return {"status": "success", "output": repos, "error": None}
        except Exception as exc:
            return {"status": "error", "output": None, "error": str(exc)}

    def _act_ask_user(self, payload: str) -> Dict[str, Any]:
        """Ask the user via voice synthesis."""
        if self.voice is None or not hasattr(self.voice, "synthesize"):
            return {"status": "error", "output": None, "error": "No voice subsystem"}

        try:
            ok = self.voice.synthesize(payload)
            return {
                "status": "success" if ok else "partial",
                "output": payload,
                "error": None if ok else "Voice synthesis failed",
            }
        except Exception as exc:
            return {"status": "error", "output": None, "error": str(exc)}

    def _act_move_mouse(self, payload: str) -> Dict[str, Any]:
        """Move mouse cursor. Payload expected as 'x,y' or JSON."""
        if self.os_controller is None or not hasattr(self.os_controller, "move_mouse"):
            return {"status": "error", "output": None, "error": "No OS controller"}

        try:
            # Simple parser: supports "x,y" or plain ints
            parts = payload.replace(" ", "").split(",")
            x, y = int(parts[0]), int(parts[1])
            ok = self.os_controller.move_mouse(x, y)
            return {
                "status": "success" if ok else "error",
                "output": {"x": x, "y": y},
                "error": None if ok else "move_mouse returned False",
            }
        except Exception as exc:
            return {"status": "error", "output": None, "error": str(exc)}

    def _act_speak(self, payload: str) -> Dict[str, Any]:
        """Speak a response aloud (delegates to voice synthesize)."""
        return self._act_ask_user(payload)


# ---------------------------------------------------------------------------
# MockReActLoop
# ---------------------------------------------------------------------------

class MockReActLoop(ReActLoop):
    """
    Simulation-only ReAct loop.

    Same interface as ReActLoop, but every action returns synthetic success
    without touching real subsystems. Useful for testing loop logic,
    benchmarking, and CI pipelines.
    """

    def __init__(
        self,
        brain: Any = None,
        voice: Any = None,
        vision: Any = None,
        memory: Any = None,
        os_controller: Any = None,
        skills: Any = None,
        github: Any = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        # Prevent real subsystem wiring — the mock does everything itself
        super().__init__(
            brain=None,
            voice=None,
            vision=None,
            memory=None,
            os_controller=None,
            skills=None,
            github=None,
            config=config,
        )
        self._mock_brain = brain
        self._mock_memory: List[Dict[str, Any]] = []

    def observe(self) -> Dict[str, Any]:
        """Return a synthetic observation."""
        return {"source": "text", "content": "mock_user_input", "confidence": 0.99}

    def reason(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """Return deterministic mock reasoning."""
        content = observation.get("content", "")
        if "code" in content.lower():
            return {
                "thought": "User wants code. I will generate it.",
                "action": "WRITE_CODE",
                "payload": "print('Hello, JARVIS!')",
                "confidence": 0.95,
            }
        if "shell" in content.lower() or "run" in content.lower():
            return {
                "thought": "User wants a shell command.",
                "action": "EXECUTE_SHELL",
                "payload": "echo mock",
                "confidence": 0.9,
            }
        return {
            "thought": "Generic mock reasoning.",
            "action": "SPEAK",
            "payload": "This is a mock response.",
            "confidence": 0.8,
        }

    def act(self, action: str, payload: str) -> Dict[str, Any]:
        """Return synthetic success for every action."""
        return {
            "status": "success",
            "output": f"mock_output_for_{action}",
            "error": None,
        }

    def reflect(self, action: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Always reflect positively in mock mode."""
        return {
            "summary": f"Mock reflection: {action} succeeded.",
            "success": True,
            "error": None,
            "confidence": 1.0,
            "plan_fix": None,
        }

    def learn(self, reflection: Dict[str, Any]) -> bool:
        """Record mock memory entries."""
        self._mock_memory.append(reflection)
        return True

    def self_heal(self, error: str, context: Dict[str, Any]) -> bool:
        """Pretend to heal — always succeeds in mock mode."""
        self._stats["heals"] += 1
        return True


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_LOOP_REGISTRY: Dict[str, Any] = {
    "react": ReActLoop,
    "mock": MockReActLoop,
}


def get_react_loop(
    variant: str = "react",
    brain: Any = None,
    voice: Any = None,
    vision: Any = None,
    memory: Any = None,
    os_controller: Any = None,
    skills: Any = None,
    github: Any = None,
    config: Optional[Dict[str, Any]] = None,
) -> ReActLoop:
    """
    Factory that returns a ReActLoop or MockReActLoop instance.

    Parameters
    ----------
    variant : str
        "react"  → full ReActLoop (requires real subsystems)
        "mock"   → MockReActLoop (simulation, no side effects)
    **kwargs
        Passed through to the chosen constructor.

    Returns
    -------
    ReActLoop
    """
    cls = _LOOP_REGISTRY.get(variant.lower(), ReActLoop)
    return cls(
        brain=brain,
        voice=voice,
        vision=vision,
        memory=memory,
        os_controller=os_controller,
        skills=skills,
        github=github,
        config=config,
    )
