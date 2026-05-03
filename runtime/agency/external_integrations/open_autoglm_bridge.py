#!/usr/bin/env python3
"""
Open-AutoGLM Integration Bridge for Jarvis Runtime Agency.

This module provides a unified adapter interface for integrating the
Open-AutoGLM phone agent framework (https://github.com/zai-org/Open-AutoGLM)
into the Jarvis agency runtime. It exposes both Android/HarmonyOS and iOS
agent capabilities through a consistent Bridge pattern.

Usage:
    from open_autoglm_bridge import OpenAutoGLMBridge, DevicePlatform

    bridge = OpenAutoGLMBridge.create(
        platform=DevicePlatform.ANDROID,
        model_base_url="http://localhost:8000/v1",
        model_name="autoglm-phone-9b-multilingual",
    )
    result = bridge.execute_task("Open eBay and search for wireless earphones")
    print(result.final_message)

Dependencies:
    - phone-agent (pip install -e . from Open-AutoGLM repo)
    - Pillow>=12.0.0
    - openai>=2.9.0
    - requests>=2.31.0 (for iOS)
"""

from __future__ import annotations

import logging
import os
import traceback
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Literal, Optional, Protocol

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types & Protocols
# ---------------------------------------------------------------------------


class DevicePlatform(Enum):
    """Supported mobile device platforms."""

    ANDROID = auto()
    HARMONYOS = auto()
    IOS = auto()


class AgentStatus(Enum):
    """Current status of the bridge agent."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    ERROR = "error"


@dataclass
class TaskResult:
    """Result of executing a task through the bridge."""

    success: bool
    final_message: str
    steps_taken: int
    actions: list[dict[str, Any]]
    thinking_log: list[str]
    platform: DevicePlatform
    device_id: str | None
    timing_ms: dict[str, float] = field(default_factory=dict)


@dataclass
class BridgeConfig:
    """Configuration for the OpenAutoGLMBridge."""

    # Model configuration
    base_url: str = "http://localhost:8000/v1"
    api_key: str = "EMPTY"
    model_name: str = "autoglm-phone-9b"
    max_tokens: int = 3000
    temperature: float = 0.0
    top_p: float = 0.85
    frequency_penalty: float = 0.2
    extra_body: dict[str, Any] = field(default_factory=dict)

    # Agent configuration
    max_steps: int = 100
    device_id: str | None = None
    lang: Literal["cn", "en"] = "en"
    verbose: bool = True

    # iOS-specific
    wda_url: str = "http://localhost:8100"
    session_id: str | None = None

    # Callbacks
    confirmation_callback: Callable[[str], bool] | None = None
    takeover_callback: Callable[[str], None] | None = None

    @classmethod
    def from_env(cls) -> BridgeConfig:
        """Load configuration from environment variables."""
        return cls(
            base_url=os.getenv("PHONE_AGENT_BASE_URL", "http://localhost:8000/v1"),
            api_key=os.getenv("PHONE_AGENT_API_KEY", "EMPTY"),
            model_name=os.getenv("PHONE_AGENT_MODEL", "autoglm-phone-9b"),
            max_steps=int(os.getenv("PHONE_AGENT_MAX_STEPS", "100")),
            device_id=os.getenv("PHONE_AGENT_DEVICE_ID"),
            wda_url=os.getenv("PHONE_AGENT_WDA_URL", "http://localhost:8100"),
            lang=os.getenv("PHONE_AGENT_LANG", "en"),  # type: ignore[arg-type]
        )


class ModelClientProtocol(Protocol):
    """Protocol for model client interaction."""

    def request(self, messages: list[dict[str, Any]]) -> Any: ...


class AgentProtocol(Protocol):
    """Protocol for phone agent interaction."""

    def run(self, task: str) -> str: ...
    def step(self, task: str | None = None) -> Any: ...
    def reset(self) -> None: ...


# ---------------------------------------------------------------------------
# Bridge Implementation
# ---------------------------------------------------------------------------


class OpenAutoGLMBridge:
    """
    Bridge adapter for Open-AutoGLM phone agent framework.

    Provides a unified interface for Android, HarmonyOS, and iOS automation
    through the Open-AutoGLM vision-language agent system.

    Attributes:
        platform: Target device platform.
        config: Bridge configuration.
        status: Current agent status.
        agent: Underlying Open-AutoGLM agent instance.
    """

    def __init__(
        self,
        platform: DevicePlatform,
        config: BridgeConfig,
        agent: AgentProtocol | None = None,
    ) -> None:
        self.platform = platform
        self.config = config
        self._agent = agent
        self._status = AgentStatus.IDLE
        self._step_count = 0
        self._action_history: list[dict[str, Any]] = []
        self._thinking_log: list[str] = []
        self._last_result: str | None = None

        # Internal references (lazy-loaded on first use)
        self._model_config_cls: Any = None
        self._agent_config_cls: Any = None
        self._agent_cls: Any = None

    # -- Factory methods ----------------------------------------------------

    @classmethod
    def create(
        cls,
        platform: DevicePlatform,
        model_base_url: str = "http://localhost:8000/v1",
        model_name: str | None = None,
        device_id: str | None = None,
        **kwargs: Any,
    ) -> OpenAutoGLMBridge:
        """
        Factory method to create a bridge for the specified platform.

        Args:
            platform: Target device platform (ANDROID, HARMONYOS, IOS).
            model_base_url: URL of the OpenAI-compatible model API.
            model_name: Model identifier (defaults to platform-appropriate).
            device_id: ADB/HDC device ID or iOS UDID.
            **kwargs: Additional config overrides.

        Returns:
            Configured OpenAutoGLMBridge instance.
        """
        default_models = {
            DevicePlatform.ANDROID: "autoglm-phone-9b",
            DevicePlatform.HARMONYOS: "autoglm-phone-9b",
            DevicePlatform.IOS: "autoglm-phone-9b-multilingual",
        }

        config = BridgeConfig.from_env()
        config.base_url = model_base_url
        config.model_name = model_name or default_models.get(
            platform, "autoglm-phone-9b"
        )
        if device_id:
            config.device_id = device_id

        # Apply additional overrides
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)

        bridge = cls(platform=platform, config=config)
        bridge._initialize()
        return bridge

    @classmethod
    def create_from_config(cls, config: BridgeConfig, platform: DevicePlatform) -> OpenAutoGLMBridge:
        """Create bridge from an existing BridgeConfig."""
        bridge = cls(platform=platform, config=config)
        bridge._initialize()
        return bridge

    # -- Properties ---------------------------------------------------------

    @property
    def status(self) -> AgentStatus:
        """Current bridge/agent status."""
        return self._status

    @property
    def step_count(self) -> int:
        """Number of steps executed in current/last task."""
        return self._step_count

    @property
    def action_history(self) -> list[dict[str, Any]]:
        """History of actions executed."""
        return self._action_history.copy()

    @property
    def thinking_log(self) -> list[str]:
        """Log of agent thinking/reasoning."""
        return self._thinking_log.copy()

    @property
    def is_initialized(self) -> bool:
        """Whether the underlying agent has been initialized."""
        return self._agent is not None

    # -- Initialization -----------------------------------------------------

    def _initialize(self) -> None:
        """Lazy-initialize the underlying Open-AutoGLM agent."""
        if self._agent is not None:
            return

        try:
            self._import_dependencies()
            self._build_agent()
            logger.info(
                "OpenAutoGLMBridge initialized for %s with model %s",
                self.platform.name,
                self.config.model_name,
            )
        except ImportError as e:
            logger.error(
                "Failed to import Open-AutoGLM dependencies. "
                "Ensure phone-agent is installed: %s",
                e,
            )
            raise
        except Exception as e:
            logger.error("Failed to initialize OpenAutoGLMBridge: %s", e)
            raise

    def _import_dependencies(self) -> None:
        """Import Open-AutoGLM modules (fail gracefully if not installed)."""
        try:
            from phone_agent.model.client import ModelConfig

            self._model_config_cls = ModelConfig

            if self.platform == DevicePlatform.IOS:
                from phone_agent.agent_ios import IOSAgentConfig, IOSPhoneAgent

                self._agent_config_cls = IOSAgentConfig
                self._agent_cls = IOSPhoneAgent
            else:
                from phone_agent.agent import AgentConfig, PhoneAgent

                self._agent_config_cls = AgentConfig
                self._agent_cls = PhoneAgent

        except ImportError as e:
            raise ImportError(
                f"Open-AutoGLM not installed. Install with: "
                f"git clone https://github.com/zai-org/Open-AutoGLM.git && "
                f"cd Open-AutoGLM && pip install -e ."
            ) from e

    def _build_agent(self) -> None:
        """Construct the underlying agent with current configuration."""
        model_config = self._model_config_cls(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            model_name=self.config.model_name,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            frequency_penalty=self.config.frequency_penalty,
            extra_body=self.config.extra_body,
            lang=self.config.lang,
        )

        if self.platform == DevicePlatform.IOS:
            agent_config = self._agent_config_cls(
                max_steps=self.config.max_steps,
                wda_url=self.config.wda_url,
                session_id=self.config.session_id,
                device_id=self.config.device_id,
                lang=self.config.lang,
                verbose=self.config.verbose,
            )
        else:
            agent_config = self._agent_config_cls(
                max_steps=self.config.max_steps,
                device_id=self.config.device_id,
                lang=self.config.lang,
                verbose=self.config.verbose,
            )

        self._agent = self._agent_cls(
            model_config=model_config,
            agent_config=agent_config,
            confirmation_callback=self.config.confirmation_callback,
            takeover_callback=self.config.takeover_callback,
        )

    # -- Core execution API -------------------------------------------------

    def execute_task(self, task_description: str) -> TaskResult:
        """
        Execute a natural language task on the connected device.

        Args:
            task_description: Natural language description of the task,
                e.g. "Open eBay and search for wireless earphones".

        Returns:
            TaskResult with full execution details.

        Raises:
            RuntimeError: If agent is not initialized.
        """
        if not self.is_initialized:
            self._initialize()

        self._reset_state()
        self._status = AgentStatus.RUNNING
        logger.info("Executing task: %s", task_description)

        try:
            # Wrap step() to capture intermediate state
            final_message = self._run_with_tracking(task_description)
            self._status = AgentStatus.FINISHED
            success = True
        except Exception as e:
            logger.error("Task execution failed: %s", e)
            traceback.print_exc()
            self._status = AgentStatus.ERROR
            final_message = f"Task failed: {e}"
            success = False

        return TaskResult(
            success=success,
            final_message=final_message,
            steps_taken=self._step_count,
            actions=self._action_history.copy(),
            thinking_log=self._thinking_log.copy(),
            platform=self.platform,
            device_id=self.config.device_id,
        )

    def execute_step(self, task_description: str | None = None) -> dict[str, Any]:
        """
        Execute a single agent step (for manual/stepwise control).

        Args:
            task_description: Task description (required for first step only).

        Returns:
            Dictionary with step result details.
        """
        if not self.is_initialized:
            self._initialize()

        self._status = AgentStatus.RUNNING
        raw_result = self._agent.step(task_description)

        # Track state
        self._step_count += 1
        if hasattr(raw_result, "action") and raw_result.action:
            self._action_history.append(raw_result.action)
        if hasattr(raw_result, "thinking") and raw_result.thinking:
            self._thinking_log.append(raw_result.thinking)

        if getattr(raw_result, "finished", False):
            self._status = AgentStatus.FINISHED

        return {
            "success": getattr(raw_result, "success", False),
            "finished": getattr(raw_result, "finished", False),
            "action": getattr(raw_result, "action", None),
            "thinking": getattr(raw_result, "thinking", ""),
            "message": getattr(raw_result, "message", None),
            "step_number": self._step_count,
        }

    def run_interactive(self) -> None:
        """
        Start an interactive session with the agent.

        Reads tasks from stdin until the user exits.
        """
        if not self.is_initialized:
            self._initialize()

        print(f"\n{'='*50}")
        print(f"  Open-AutoGLM Bridge - {self.platform.name}")
        print(f"  Model: {self.config.model_name}")
        print(f"  Device: {self.config.device_id or 'auto-detect'}")
        print(f"{'='*50}\n")

        while True:
            try:
                task = input("Task> ").strip()
                if task.lower() in ("exit", "quit", "q"):
                    break
                if not task:
                    continue

                result = self.execute_task(task)
                print(f"\nResult: {result.final_message}")
                print(f"Steps: {result.steps_taken}, Success: {result.success}\n")

            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except EOFError:
                break

    # -- Device management --------------------------------------------------

    def check_system_requirements(self) -> dict[str, Any]:
        """
        Check if the system meets all requirements for the platform.

        Returns:
            Dictionary with check results for each requirement.
        """
        results: dict[str, Any] = {}

        if self.platform in (DevicePlatform.ANDROID, DevicePlatform.HARMONYOS):
            results["adb_installed"] = self._check_command("adb")
            results["hdc_installed"] = self._check_command("hdc")
            results["device_connected"] = self._check_device_connected()
        elif self.platform == DevicePlatform.IOS:
            results["libimobiledevice"] = self._check_command("idevice_id")
            results["wda_running"] = self._check_wda()

        results["python_deps"] = self._check_python_deps()
        results["model_reachable"] = self._check_model_reachable()

        return results

    # -- Lifecycle ----------------------------------------------------------

    def reset(self) -> None:
        """Reset the agent state for a new task."""
        self._reset_state()
        if self._agent:
            self._agent.reset()
        self._status = AgentStatus.IDLE
        logger.info("Bridge state reset")

    def shutdown(self) -> None:
        """Release resources and shutdown the bridge."""
        self._agent = None
        self._status = AgentStatus.IDLE
        logger.info("OpenAutoGLMBridge shutdown")

    # -- Internal helpers ---------------------------------------------------

    def _reset_state(self) -> None:
        """Clear execution tracking state."""
        self._step_count = 0
        self._action_history.clear()
        self._thinking_log.clear()
        self._last_result = None

    def _run_with_tracking(self, task: str) -> str:
        """
        Execute task while tracking step-level information.

        Open-AutoGLM's PhoneAgent.run() is a high-level method that
        internally loops until completion. We monkey-patch step tracking
        onto the agent to capture intermediate state.
        """
        # For full step-level tracking, use stepwise execution
        final_message = ""
        step_idx = 0

        while step_idx < self.config.max_steps:
            step_result = self._agent.step(task if step_idx == 0 else None)
            step_idx += 1

            if hasattr(step_result, "action") and step_result.action:
                self._action_history.append(step_result.action)
            if hasattr(step_result, "thinking") and step_result.thinking:
                self._thinking_log.append(step_result.thinking)
            if hasattr(step_result, "message") and step_result.message:
                final_message = step_result.message

            if getattr(step_result, "finished", False):
                self._step_count = step_idx
                return final_message or "Task completed"

        self._step_count = step_idx
        return final_message or "Max steps reached"

    @staticmethod
    def _check_command(cmd: str) -> bool:
        """Check if a system command is available."""
        import shutil

        return shutil.which(cmd) is not None

    def _check_device_connected(self) -> bool:
        """Check if at least one device is connected via ADB/HDC."""
        import subprocess

        try:
            tool = "hdc" if self.platform == DevicePlatform.HARMONYOS else "adb"
            result = subprocess.run(
                [tool, "devices"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
            return len(lines) > 1  # Header line + at least one device
        except Exception:
            return False

    def _check_wda(self) -> bool:
        """Check if WebDriverAgent is running."""
        import urllib.request

        try:
            req = urllib.request.Request(
                f"{self.config.wda_url}/status",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _check_python_deps(self) -> dict[str, bool]:
        """Check if required Python packages are installed."""
        deps = {}
        for pkg in ("phone_agent", "PIL", "openai", "requests"):
            try:
                __import__(pkg)
                deps[pkg] = True
            except ImportError:
                deps[pkg] = False
        return deps

    def _check_model_reachable(self) -> bool:
        """Check if the model API endpoint is reachable."""
        import urllib.request

        try:
            req = urllib.request.Request(
                self.config.base_url.replace("/v1", "/health"),
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=5):
                return True
        except Exception:
            # Try models endpoint as fallback
            try:
                req = urllib.request.Request(
                    f"{self.config.base_url}/models",
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=5):
                    return True
            except Exception:
                return False

    # -- Convenience methods for agency integration -------------------------

    def to_tool_schema(self) -> dict[str, Any]:
        """
        Return an OpenAI-style tool schema for agency function-calling.

        Returns:
            JSON schema dict representing the bridge as a callable tool.
        """
        return {
            "type": "function",
            "function": {
                "name": "open_autoglm_execute",
                "description": (
                    f"Execute a task on a {self.platform.name} mobile device "
                    "using the Open-AutoGLM AI phone agent. The agent uses "
                    "vision-language models to understand screen content and "
                    "automatically perform actions like tapping, typing, "
                    "swiping, and launching apps to complete the requested task."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_description": {
                            "type": "string",
                            "description": (
                                "Natural language description of the task to perform "
                                "on the phone, e.g. 'Open eBay and search for "
                                "wireless earphones' or 'Send a WhatsApp message "
                                "to John saying hello'"
                            ),
                        },
                    },
                    "required": ["task_description"],
                },
            },
        }

    def get_health(self) -> dict[str, Any]:
        """
        Get comprehensive health status of the bridge and dependencies.

        Returns:
            Dictionary with status of all components.
        """
        checks = self.check_system_requirements()
        return {
            "initialized": self.is_initialized,
            "status": self.status.value,
            "platform": self.platform.name,
            "model_name": self.config.model_name,
            "model_base_url": self.config.base_url,
            "device_id": self.config.device_id,
            "checks": checks,
            "all_checks_pass": all(
                v if isinstance(v, bool) else v.get("device_connected", True)
                for v in checks.values()
            ),
        }


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point for testing the bridge."""
    import argparse

    parser = argparse.ArgumentParser(description="Open-AutoGLM Bridge")
    parser.add_argument(
        "--platform",
        choices=["android", "harmonyos", "ios"],
        default="android",
        help="Device platform",
    )
    parser.add_argument("--model-url", default="http://localhost:8000/v1", help="Model API URL")
    parser.add_argument("--model-name", default=None, help="Model name")
    parser.add_argument("--device-id", default=None, help="Device ID")
    parser.add_argument("--task", default=None, help="Single task to execute")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--check", action="store_true", help="Run health check only")
    args = parser.parse_args()

    platform_map = {
        "android": DevicePlatform.ANDROID,
        "harmonyos": DevicePlatform.HARMONYOS,
        "ios": DevicePlatform.IOS,
    }

    bridge = OpenAutoGLMBridge.create(
        platform=platform_map[args.platform],
        model_base_url=args.model_url,
        model_name=args.model_name,
        device_id=args.device_id,
    )

    if args.check:
        import json

        health = bridge.get_health()
        print(json.dumps(health, indent=2, default=str))
        return

    if args.task:
        result = bridge.execute_task(args.task)
        print(f"\nFinal message: {result.final_message}")
        print(f"Steps: {result.steps_taken}")
        print(f"Actions: {len(result.actions)}")
        print(f"Success: {result.success}")
    elif args.interactive:
        bridge.run_interactive()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
