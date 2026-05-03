"""
Gemini Computer Use Bridge - Integration Adapter for Agent Frameworks
=====================================================================

A production-ready bridge wrapping the Google Gemini Computer Use Preview reference
implementation (https://github.com/google-gemini/computer-use-preview) for integration
into agent orchestration frameworks.

Provides:
- Programmatic API (not CLI-bound)
- Async/sync dual-mode operation
- Event streaming for real-time UI updates
- Headless-safe configurable safety handling
- Custom function injection
- Automatic resource lifecycle management
- Structured logging and comprehensive error handling

Author: JARVIS Runtime Agency
License: Apache-2.0
"""

from __future__ import annotations

import abc
import asyncio
import base64
import logging
import os
import sys
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Coroutine,
    Generator,
    Generic,
    Literal,
    Optional,
    TypeVar,
    Union,
)

# ---------------------------------------------------------------------------
# Optional dependency handling
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

_HAS_GOOGLE_GENAI = False
_HAS_PLAYWRIGHT = False
_HAS_BROWSERBASE = False
_HAS_PYDANTIC = False
_HAS_RICH = False

try:
    from google import genai
    from google.genai import types as genai_types
    from google.genai.types import (
        Candidate,
        Content,
        FunctionResponse,
        GenerateContentConfig,
        Part,
    )

    _HAS_GOOGLE_GENAI = True
except ImportError:
    logger.warning("google-genai not installed. Bridge will not function.")

try:
    import playwright.sync_api as pw_sync
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    logger.debug("playwright not installed. Local browser backend unavailable.")

try:
    import browserbase

    _HAS_BROWSERBASE = True
except ImportError:
    logger.debug("browserbase not installed. Cloud browser backend unavailable.")

try:
    import pydantic

    _HAS_PYDANTIC = True
except ImportError:
    logger.warning("pydantic not installed. Required for EnvState.")

try:
    from rich.console import Console
    from rich.table import Table

    _HAS_RICH = True
except ImportError:
    Console = None  # type: ignore[misc,assignment]
    Table = None  # type: ignore[misc,assignment]

import termcolor

# ---------------------------------------------------------------------------
# Constants & Configuration
# ---------------------------------------------------------------------------

MAX_RECENT_TURN_WITH_SCREENSHOTS = 3
PREDEFINED_COMPUTER_USE_FUNCTIONS = [
    "open_web_browser",
    "click_at",
    "hover_at",
    "type_text_at",
    "scroll_document",
    "scroll_at",
    "wait_5_seconds",
    "go_back",
    "go_forward",
    "search",
    "navigate",
    "key_combination",
    "drag_and_drop",
]

DEFAULT_MODEL = "gemini-2.5-computer-use-preview-10-2025"
DEFAULT_SCREEN_SIZE = (1440, 900)
DEFAULT_TEMPERATURE = 1.0
DEFAULT_TOP_P = 0.95
DEFAULT_TOP_K = 40
DEFAULT_MAX_OUTPUT_TOKENS = 8192
DEFAULT_MAX_RETRIES = 5
DEFAULT_BASE_DELAY_S = 1

PLAYWRIGHT_KEY_MAP = {
    "backspace": "Backspace",
    "tab": "Tab",
    "return": "Enter",
    "enter": "Enter",
    "shift": "Shift",
    "control": "ControlOrMeta",
    "alt": "Alt",
    "escape": "Escape",
    "space": "Space",
    "pageup": "PageUp",
    "pagedown": "PageDown",
    "end": "End",
    "home": "Home",
    "left": "ArrowLeft",
    "up": "ArrowUp",
    "right": "ArrowRight",
    "down": "ArrowDown",
    "insert": "Insert",
    "delete": "Delete",
    "command": "Meta",
}

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class BridgeEventType(str, Enum):
    """Event types emitted by the bridge during agent execution."""

    REASONING = "reasoning"          # Model's chain-of-thought text
    ACTION = "action"                # Structured function call
    ACTION_RESULT = "action_result"  # Result of executed action
    SCREENSHOT = "screenshot"        # Base64-encoded PNG screenshot
    ERROR = "error"                  # Error/exception info
    SAFETY_PROMPT = "safety_prompt"  # Safety confirmation required
    SAFETY_RESOLVED = "safety_resolved"  # Safety decision made
    COMPLETE = "complete"            # Agent loop finished
    TURN_START = "turn_start"        # New iteration started
    TURN_END = "turn_end"            # Iteration completed


@dataclass
class BridgeEvent:
    """A structured event emitted by the bridge during execution."""

    event_type: BridgeEventType
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def reasoning_text(self) -> Optional[str]:
        return self.payload.get("reasoning")

    @property
    def action_name(self) -> Optional[str]:
        return self.payload.get("action_name")

    @property
    def action_args(self) -> Optional[dict]:
        return self.payload.get("action_args")

    @property
    def screenshot_b64(self) -> Optional[str]:
        return self.payload.get("screenshot_b64")

    @property
    def current_url(self) -> Optional[str]:
        return self.payload.get("url")

    @property
    def error_message(self) -> Optional[str]:
        return self.payload.get("error")


@dataclass
class GeminiComputerUseConfig:
    """Configuration for the Gemini Computer Use bridge."""

    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    top_p: float = DEFAULT_TOP_P
    top_k: int = DEFAULT_TOP_K
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    api_key: Optional[str] = None
    use_vertexai: bool = False
    vertexai_project: Optional[str] = None
    vertexai_location: Optional[str] = None
    max_retries: int = DEFAULT_MAX_RETRIES
    base_delay_s: int = DEFAULT_BASE_DELAY_S
    screen_size: tuple[int, int] = DEFAULT_SCREEN_SIZE
    initial_url: str = "https://www.google.com"
    highlight_mouse: bool = False
    verbose: bool = True
    safety_mode: Literal["interactive", "auto_allow", "auto_deny"] = "interactive"
    max_turns: int = 50  # Safety limit to prevent infinite loops
    excluded_predefined_functions: list[str] = field(default_factory=list)
    custom_functions: list[Any] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "GeminiComputerUseConfig":
        """Create configuration from environment variables."""
        return cls(
            model=os.environ.get("GEMINI_COMPUTER_USE_MODEL", DEFAULT_MODEL),
            api_key=os.environ.get("GEMINI_API_KEY"),
            use_vertexai=os.environ.get("USE_VERTEXAI", "0").lower()
            in ("true", "1"),
            vertexai_project=os.environ.get("VERTEXAI_PROJECT"),
            vertexai_location=os.environ.get("VERTEXAI_LOCATION"),
            highlight_mouse=os.environ.get("GEMINI_HIGHLIGHT_MOUSE", "0").lower()
            in ("true", "1"),
            safety_mode=Literal[  # type: ignore[arg-type]
                "interactive", "auto_allow", "auto_deny"
            ](os.environ.get("GEMINI_SAFETY_MODE", "interactive")),
            max_turns=int(os.environ.get("GEMINI_MAX_TURNS", "50")),
        )


# ---------------------------------------------------------------------------
# Computer Abstractions (mirror upstream for self-containment)
# ---------------------------------------------------------------------------


class EnvState(pydantic.BaseModel if _HAS_PYDANTIC else object):  # type: ignore[no-redef]
    """Current state of the browser environment."""

    screenshot: bytes = b""
    url: str = ""

    if not _HAS_PYDANTIC:

        def __init__(self, screenshot: bytes = b"", url: str = "") -> None:
            self.screenshot = screenshot
            self.url = url


class Computer(abc.ABC):
    """Abstract interface for browser environments."""

    @abc.abstractmethod
    def screen_size(self) -> tuple[int, int]:
        """Return (width, height) of the browser viewport."""
        ...

    @abc.abstractmethod
    def open_web_browser(self) -> EnvState:
        ...

    @abc.abstractmethod
    def click_at(self, x: int, y: int) -> EnvState:
        ...

    @abc.abstractmethod
    def hover_at(self, x: int, y: int) -> EnvState:
        ...

    @abc.abstractmethod
    def type_text_at(
        self,
        x: int,
        y: int,
        text: str,
        press_enter: bool = False,
        clear_before_typing: bool = True,
    ) -> EnvState:
        ...

    @abc.abstractmethod
    def scroll_document(
        self, direction: Literal["up", "down", "left", "right"]
    ) -> EnvState:
        ...

    @abc.abstractmethod
    def scroll_at(
        self,
        x: int,
        y: int,
        direction: Literal["up", "down", "left", "right"],
        magnitude: int = 800,
    ) -> EnvState:
        ...

    @abc.abstractmethod
    def wait_5_seconds(self) -> EnvState:
        ...

    @abc.abstractmethod
    def go_back(self) -> EnvState:
        ...

    @abc.abstractmethod
    def go_forward(self) -> EnvState:
        ...

    @abc.abstractmethod
    def search(self) -> EnvState:
        ...

    @abc.abstractmethod
    def navigate(self, url: str) -> EnvState:
        ...

    @abc.abstractmethod
    def key_combination(self, keys: list[str]) -> EnvState:
        ...

    @abc.abstractmethod
    def drag_and_drop(
        self, x: int, y: int, destination_x: int, destination_y: int
    ) -> EnvState:
        ...

    @abc.abstractmethod
    def current_state(self) -> EnvState:
        ...


# ---------------------------------------------------------------------------
# PlaywrightComputer Implementation
# ---------------------------------------------------------------------------


class PlaywrightComputer(Computer):
    """Local browser automation via Playwright."""

    def __init__(
        self,
        screen_size: tuple[int, int] = DEFAULT_SCREEN_SIZE,
        initial_url: str = "https://www.google.com",
        search_engine_url: str = "https://www.google.com",
        highlight_mouse: bool = False,
    ):
        if not _HAS_PLAYWRIGHT:
            raise ImportError(
                "playwright is required for PlaywrightComputer. "
                "Install: pip install playwright && playwright install chrome"
            )
        self._screen_size = screen_size
        self._initial_url = initial_url
        self._search_engine_url = search_engine_url
        self._highlight_mouse = highlight_mouse
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    def _handle_new_page(self, new_page: Any) -> None:
        new_url = new_page.url
        new_page.close()
        self._page.goto(new_url)

    def __enter__(self) -> "PlaywrightComputer":
        logger.info("Starting Playwright browser session...")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            args=[
                "--disable-extensions",
                "--disable-file-system",
                "--disable-plugins",
                "--disable-dev-shm-usage",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-sync",
            ],
            headless=bool(os.environ.get("PLAYWRIGHT_HEADLESS", False)),
        )
        self._context = self._browser.new_context(
            viewport={"width": self._screen_size[0], "height": self._screen_size[1]}
        )
        self._page = self._context.new_page()
        self._page.goto(self._initial_url)
        self._context.on("page", self._handle_new_page)
        logger.info("Playwright session ready at %s", self._initial_url)
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> None:
        logger.info("Shutting down Playwright session...")
        if self._context:
            self._context.close()
        try:
            if self._browser:
                self._browser.close()
        except Exception as e:
            if "Connection closed while reading from the driver" not in str(e):
                logger.warning("Browser close error: %s", e)
        if self._playwright:
            self._playwright.stop()

    def screen_size(self) -> tuple[int, int]:
        if self._page and self._page.viewport_size:
            return (
                self._page.viewport_size["width"],
                self._page.viewport_size["height"],
            )
        return self._screen_size

    def open_web_browser(self) -> EnvState:
        return self.current_state()

    def click_at(self, x: int, y: int) -> EnvState:
        self._highlight(x, y)
        self._page.mouse.click(x, y)
        self._page.wait_for_load_state()
        return self.current_state()

    def hover_at(self, x: int, y: int) -> EnvState:
        self._highlight(x, y)
        self._page.mouse.move(x, y)
        self._page.wait_for_load_state()
        return self.current_state()

    def type_text_at(
        self,
        x: int,
        y: int,
        text: str,
        press_enter: bool = False,
        clear_before_typing: bool = True,
    ) -> EnvState:
        self._highlight(x, y)
        self._page.mouse.click(x, y)
        self._page.wait_for_load_state()
        if clear_before_typing:
            if sys.platform == "darwin":
                self.key_combination(["Command", "A"])
            else:
                self.key_combination(["Control", "A"])
            self.key_combination(["Delete"])
        self._page.keyboard.type(text)
        self._page.wait_for_load_state()
        if press_enter:
            self.key_combination(["Enter"])
        self._page.wait_for_load_state()
        return self.current_state()

    def scroll_document(
        self, direction: Literal["up", "down", "left", "right"]
    ) -> EnvState:
        if direction == "down":
            return self.key_combination(["PageDown"])
        elif direction == "up":
            return self.key_combination(["PageUp"])
        elif direction in ("left", "right"):
            amount = self.screen_size()[0] // 2
            sign = "-" if direction == "left" else ""
            self._page.evaluate(f"window.scrollBy({sign}{amount}, 0);")
            self._page.wait_for_load_state()
            return self.current_state()
        else:
            raise ValueError(f"Unsupported direction: {direction}")

    def scroll_at(
        self,
        x: int,
        y: int,
        direction: Literal["up", "down", "left", "right"],
        magnitude: int = 800,
    ) -> EnvState:
        self._highlight(x, y)
        self._page.mouse.move(x, y)
        self._page.wait_for_load_state()
        dx = dy = 0
        if direction == "up":
            dy = -magnitude
        elif direction == "down":
            dy = magnitude
        elif direction == "left":
            dx = -magnitude
        elif direction == "right":
            dx = magnitude
        else:
            raise ValueError(f"Unsupported direction: {direction}")
        self._page.mouse.wheel(dx, dy)
        self._page.wait_for_load_state()
        return self.current_state()

    def wait_5_seconds(self) -> EnvState:
        time.sleep(5)
        return self.current_state()

    def go_back(self) -> EnvState:
        self._page.go_back()
        self._page.wait_for_load_state()
        return self.current_state()

    def go_forward(self) -> EnvState:
        self._page.go_forward()
        self._page.wait_for_load_state()
        return self.current_state()

    def search(self) -> EnvState:
        return self.navigate(self._search_engine_url)

    def navigate(self, url: str) -> EnvState:
        normalized = url if url.startswith(("http://", "https://")) else f"https://{url}"
        self._page.goto(normalized)
        self._page.wait_for_load_state()
        return self.current_state()

    def key_combination(self, keys: list[str]) -> EnvState:
        normalized = [PLAYWRIGHT_KEY_MAP.get(k.lower(), k) for k in keys]
        for key in normalized[:-1]:
            self._page.keyboard.down(key)
        self._page.keyboard.press(normalized[-1])
        for key in reversed(normalized[:-1]):
            self._page.keyboard.up(key)
        return self.current_state()

    def drag_and_drop(
        self, x: int, y: int, destination_x: int, destination_y: int
    ) -> EnvState:
        self._highlight(x, y)
        self._page.mouse.move(x, y)
        self._page.wait_for_load_state()
        self._page.mouse.down()
        self._page.wait_for_load_state()
        self._highlight(destination_x, destination_y)
        self._page.mouse.move(destination_x, destination_y)
        self._page.wait_for_load_state()
        self._page.mouse.up()
        return self.current_state()

    def current_state(self) -> EnvState:
        self._page.wait_for_load_state()
        time.sleep(0.5)
        png = self._page.screenshot(type="png", full_page=False)
        return EnvState(screenshot=png, url=self._page.url)

    def _highlight(self, x: int, y: int) -> None:
        if not self._highlight_mouse:
            return
        self._page.evaluate(
            f"""
            () => {{
                const el = document.createElement('div');
                el.id = 'cu-bridge-highlight';
                el.style.cssText = 'pointer-events:none;border:4px solid red;"""
            f"""border-radius:50%;width:20px;height:20px;position:fixed;zIndex:9999;';
                document.body.appendChild(el);
                el.style.left = '{x - 10}px';
                el.style.top = '{y - 10}px';
                setTimeout(() => el.remove(), 2000);
            }}
            """
        )
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# BrowserbaseComputer Implementation
# ---------------------------------------------------------------------------


class BrowserbaseComputer(PlaywrightComputer):
    """Cloud browser automation via Browserbase (extends PlaywrightComputer)."""

    def __init__(
        self,
        screen_size: tuple[int, int] = DEFAULT_SCREEN_SIZE,
        initial_url: str = "https://www.google.com",
    ):
        if not _HAS_BROWSERBASE:
            raise ImportError("browserbase package required. Install: pip install browserbase")
        super().__init__(screen_size=screen_size, initial_url=initial_url)
        self._bb: Any = None
        self._session: Any = None

    def __enter__(self) -> "BrowserbaseComputer":
        logger.info("Creating Browserbase session...")
        self._playwright = sync_playwright().start()
        self._bb = browserbase.Browserbase(api_key=os.environ["BROWSERBASE_API_KEY"])
        self._session = self._bb.sessions.create(
            project_id=os.environ["BROWSERBASE_PROJECT_ID"],
            browser_settings={
                "fingerprint": {
                    "screen": {
                        "maxWidth": 1920,
                        "maxHeight": 1080,
                        "minWidth": 1024,
                        "minHeight": 768,
                    }
                },
                "viewport": {
                    "width": self._screen_size[0],
                    "height": self._screen_size[1],
                },
            },
        )
        self._browser = self._playwright.chromium.connect_over_cdp(self._session.connect_url)
        self._context = self._browser.contexts[0]
        self._page = self._context.pages[0]
        self._page.goto(self._initial_url)
        self._context.on("page", self._handle_new_page)
        logger.info(
            "Browserbase session ready: https://browserbase.com/sessions/%s",
            self._session.id,
        )
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> None:
        logger.info("Closing Browserbase session...")
        if self._page:
            self._page.close()
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()


# ---------------------------------------------------------------------------
# Bridge Agent
# ---------------------------------------------------------------------------

FunctionResponseT = Union[EnvState, dict]


class GeminiComputerUseBridge:
    """Production-ready bridge for Gemini Computer Use integration.

    Wraps the reference implementation with:
    - Event streaming for real-time observability
    - Configurable safety handling (interactive / auto-allow / auto-deny)
    - Custom function injection
    - Async and sync APIs
    - Automatic resource cleanup

    Example (sync):
        config = GeminiComputerUseConfig.from_env()
        with GeminiComputerUseBridge(config) as bridge:
            for event in bridge.run_stream("Go to Google and search for AI news"):
                print(event.event_type, event.payload)

    Example (async):
        async with GeminiComputerUseBridge(config) as bridge:
            async for event in bridge.run_stream_async("Search for Python tutorials"):
                await websocket.send(event.to_json())
    """

    def __init__(self, config: Optional[GeminiComputerUseConfig] = None):
        if not _HAS_GOOGLE_GENAI:
            raise ImportError(
                "google-genai>=1.0.0 is required. Install: pip install google-genai"
            )
        self.config = config or GeminiComputerUseConfig.from_env()
        self._computer: Optional[Computer] = None
        self._client = genai.Client(
            api_key=self.config.api_key or os.environ.get("GEMINI_API_KEY"),
            vertexai=self.config.use_vertexai,
            project=self.config.vertexai_project,
            location=self.config.vertexai_location,
        )
        self._contents: list[Content] = []
        self._turn_count = 0
        self._completed_reasoning: Optional[str] = None
        self._callbacks: list[Callable[[BridgeEvent], None]] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def set_computer(self, computer: Computer) -> "GeminiComputerUseBridge":
        """Attach a browser computer backend (required before run)."""
        self._computer = computer
        return self

    def __enter__(self) -> "GeminiComputerUseBridge":
        return self

    def __exit__(self, *args: Any) -> None:
        self.shutdown()

    async def __aenter__(self) -> "GeminiComputerUseBridge":
        return self

    async def __aexit__(self, *args: Any) -> None:
        self.shutdown()

    def shutdown(self) -> None:
        """Release resources and reset state."""
        self._contents.clear()
        self._turn_count = 0
        logger.info("Bridge shutdown complete.")

    # ------------------------------------------------------------------
    # Callbacks / Observability
    # ------------------------------------------------------------------

    def on_event(self, callback: Callable[[BridgeEvent], None]) -> "GeminiComputerUseBridge":
        """Register an event callback for real-time monitoring."""
        self._callbacks.append(callback)
        return self

    def _emit(self, event: BridgeEvent) -> None:
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                logger.exception("Event callback error")

    # ------------------------------------------------------------------
    # Core Agent Logic
    # ------------------------------------------------------------------

    def _build_config(self) -> GenerateContentConfig:
        tools: list[Any] = [
            genai_types.Tool(
                computer_use=genai_types.ComputerUse(
                    environment=genai_types.Environment.ENVIRONMENT_BROWSER,
                    excluded_predefined_functions=self.config.excluded_predefined_functions,
                )
            )
        ]
        if self.config.custom_functions:
            tools.append(
                genai_types.Tool(function_declarations=self.config.custom_functions)
            )
        return GenerateContentConfig(
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            top_k=self.config.top_k,
            max_output_tokens=self.config.max_output_tokens,
            tools=tools,
            thinking_config=genai_types.ThinkingConfig(include_thoughts=True),
        )

    def _denormalize_x(self, x: int) -> int:
        if self._computer is None:
            raise RuntimeError("No computer backend attached. Call set_computer() first.")
        return int(x / 1000 * self._computer.screen_size()[0])

    def _denormalize_y(self, y: int) -> int:
        if self._computer is None:
            raise RuntimeError("No computer backend attached. Call set_computer() first.")
        return int(y / 1000 * self._computer.screen_size()[1])

    def _handle_action(self, action: genai_types.FunctionCall) -> FunctionResponseT:
        if self._computer is None:
            raise RuntimeError("No computer backend attached.")
        name = action.name
        args = action.args or {}

        logger.debug("Action: %s(%s)", name, args)

        if name == "open_web_browser":
            return self._computer.open_web_browser()
        elif name == "click_at":
            return self._computer.click_at(
                self._denormalize_x(args["x"]), self._denormalize_y(args["y"])
            )
        elif name == "hover_at":
            return self._computer.hover_at(
                self._denormalize_x(args["x"]), self._denormalize_y(args["y"])
            )
        elif name == "type_text_at":
            return self._computer.type_text_at(
                x=self._denormalize_x(args["x"]),
                y=self._denormalize_y(args["y"]),
                text=args["text"],
                press_enter=args.get("press_enter", False),
                clear_before_typing=args.get("clear_before_typing", True),
            )
        elif name == "scroll_document":
            return self._computer.scroll_document(args["direction"])
        elif name == "scroll_at":
            mag = args.get("magnitude", 800)
            direction = args["direction"]
            if direction in ("up", "down"):
                mag = self._denormalize_y(mag)
            elif direction in ("left", "right"):
                mag = self._denormalize_x(mag)
            return self._computer.scroll_at(
                self._denormalize_x(args["x"]),
                self._denormalize_y(args["y"]),
                direction,
                mag,
            )
        elif name == "wait_5_seconds":
            return self._computer.wait_5_seconds()
        elif name == "go_back":
            return self._computer.go_back()
        elif name == "go_forward":
            return self._computer.go_forward()
        elif name == "search":
            return self._computer.search()
        elif name == "navigate":
            return self._computer.navigate(args["url"])
        elif name == "key_combination":
            return self._computer.key_combination(args["keys"].split("+"))
        elif name == "drag_and_drop":
            return self._computer.drag_and_drop(
                self._denormalize_x(args["x"]),
                self._denormalize_y(args["y"]),
                self._denormalize_x(args["destination_x"]),
                self._denormalize_y(args["destination_y"]),
            )
        else:
            # Attempt custom function dispatch
            for fn in self.config.custom_functions:
                if hasattr(fn, "__name__") and fn.__name__ == name:
                    return fn(**args)
            raise ValueError(f"Unsupported function call: {name}({args})")

    def _get_model_response(
        self, gen_config: GenerateContentConfig
    ) -> genai_types.GenerateContentResponse:
        for attempt in range(self.config.max_retries):
            try:
                return self._client.models.generate_content(
                    model=self.config.model,
                    contents=self._contents,
                    config=gen_config,
                )
            except Exception as exc:
                logger.warning("Generation attempt %d failed: %s", attempt + 1, exc)
                if attempt < self.config.max_retries - 1:
                    delay = self.config.base_delay_s * (2 ** attempt)
                    time.sleep(delay)
                else:
                    raise RuntimeError(
                        f"Model generation failed after {self.config.max_retries} attempts"
                    ) from exc
        raise RuntimeError("Unreachable")

    # ------------------------------------------------------------------
    # Safety Handling
    # ------------------------------------------------------------------

    def _handle_safety(
        self, safety: dict[str, Any]
    ) -> Literal["CONTINUE", "TERMINATE"]:
        if safety.get("decision") != "require_confirmation":
            logger.warning("Unknown safety decision: %s", safety.get("decision"))
            return "CONTINUE"

        explanation = safety.get("explanation", "No explanation provided.")
        event = BridgeEvent(
            event_type=BridgeEventType.SAFETY_PROMPT,
            payload={"explanation": explanation},
        )
        self._emit(event)

        if self.config.safety_mode == "auto_allow":
            logger.info("Auto-allowing safety-flagged action")
            self._emit(
                BridgeEvent(
                    event_type=BridgeEventType.SAFETY_RESOLVED,
                    payload={"decision": "CONTINUE"},
                )
            )
            return "CONTINUE"
        elif self.config.safety_mode == "auto_deny":
            logger.info("Auto-denying safety-flagged action")
            self._emit(
                BridgeEvent(
                    event_type=BridgeEventType.SAFETY_RESOLVED,
                    payload={"decision": "TERMINATE"},
                )
            )
            return "TERMINATE"
        else:
            termcolor.cprint(
                "\n[Safety Check Required]", color="yellow", attrs=["bold"]
            )
            print(f"Explanation: {explanation}")
            decision = ""
            while decision.lower() not in ("y", "yes", "n", "no"):
                decision = input("Proceed? [Yes]/[No]: ")
            result = "TERMINATE" if decision.lower() in ("n", "no") else "CONTINUE"
            self._emit(
                BridgeEvent(
                    event_type=BridgeEventType.SAFETY_RESOLVED,
                    payload={"decision": result},
                )
            )
            return result  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Single Turn Execution
    # ------------------------------------------------------------------

    def _run_one_turn(
        self, gen_config: GenerateContentConfig
    ) -> Literal["COMPLETE", "CONTINUE", "ERROR"]:
        self._turn_count += 1
        if self._turn_count > self.config.max_turns:
            logger.warning("Max turns (%d) reached. Stopping.", self.config.max_turns)
            return "COMPLETE"

        self._emit(
            BridgeEvent(
                event_type=BridgeEventType.TURN_START,
                payload={"turn": self._turn_count},
            )
        )

        try:
            response = self._get_model_response(gen_config)
        except Exception as exc:
            self._emit(
                BridgeEvent(
                    event_type=BridgeEventType.ERROR,
                    payload={"error": str(exc), "phase": "model_generation"},
                )
            )
            return "ERROR"

        if not response.candidates:
            if (
                response.prompt_feedback
                and response.prompt_feedback.block_reason
                == genai_types.BlockReason.SAFETY
            ):
                err = f"Response blocked due to safety: {response.prompt_feedback}"
                self._emit(
                    BridgeEvent(
                        event_type=BridgeEventType.ERROR,
                        payload={"error": err, "phase": "safety_block"},
                    )
                )
                raise ValueError(err)
            self._emit(
                BridgeEvent(
                    event_type=BridgeEventType.ERROR,
                    payload={"error": "Empty response (no candidates)", "phase": "response_parsing"},
                )
            )
            raise ValueError("Empty response from model")

        candidate = response.candidates[0]
        if candidate.content:
            self._contents.append(candidate.content)

        reasoning = self._extract_text(candidate)
        function_calls = self._extract_function_calls(candidate)

        # Malformed function call recovery
        if (
            not function_calls
            and not reasoning
            and candidate.finish_reason == genai_types.FinishReason.MALFORMED_FUNCTION_CALL
        ):
            self._emit(
                BridgeEvent(
                    event_type=BridgeEventType.TURN_END,
                    payload={"turn": self._turn_count, "status": "malformed_recovery"},
                )
            )
            return "CONTINUE"

        # Task completion
        if not function_calls:
            self._completed_reasoning = reasoning
            self._emit(
                BridgeEvent(
                    event_type=BridgeEventType.REASONING,
                    payload={"reasoning": reasoning or "(no reasoning)", "final": True},
                )
            )
            self._emit(
                BridgeEvent(
                    event_type=BridgeEventType.COMPLETE,
                    payload={
                        "reasoning": reasoning,
                        "turns": self._turn_count,
                    },
                )
            )
            return "COMPLETE"

        # Emit reasoning
        if reasoning:
            self._emit(
                BridgeEvent(
                    event_type=BridgeEventType.REASONING,
                    payload={"reasoning": reasoning, "final": False},
                )
            )

        # Process function calls
        for fc in function_calls:
            self._emit(
                BridgeEvent(
                    event_type=BridgeEventType.ACTION,
                    payload={
                        "action_name": fc.name,
                        "action_args": fc.args,
                    },
                )
            )

            # Safety check
            extra_fields: dict[str, str] = {}
            if fc.args and (safety := fc.args.get("safety_decision")):
                decision = self._handle_safety(safety)
                if decision == "TERMINATE":
                    self._emit(
                        BridgeEvent(
                            event_type=BridgeEventType.COMPLETE,
                            payload={"reasoning": "Terminated by safety check", "turns": self._turn_count},
                        )
                    )
                    return "COMPLETE"
                extra_fields["safety_acknowledgement"] = "true"

            # Execute action
            try:
                result = self._handle_action(fc)
            except Exception as exc:
                self._emit(
                    BridgeEvent(
                        event_type=BridgeEventType.ERROR,
                        payload={
                            "error": str(exc),
                            "phase": "action_execution",
                            "action": fc.name,
                        },
                    )
                )
                return "ERROR"

            if isinstance(result, EnvState):
                screenshot_b64 = base64.b64encode(result.screenshot).decode("utf-8")
                self._emit(
                    BridgeEvent(
                        event_type=BridgeEventType.SCREENSHOT,
                        payload={
                            "screenshot_b64": screenshot_b64,
                            "url": result.url,
                        },
                    )
                )
                self._emit(
                    BridgeEvent(
                        event_type=BridgeEventType.ACTION_RESULT,
                        payload={
                            "action_name": fc.name,
                            "url": result.url,
                            **extra_fields,
                        },
                    )
                )
            elif isinstance(result, dict):
                self._emit(
                    BridgeEvent(
                        event_type=BridgeEventType.ACTION_RESULT,
                        payload={"action_name": fc.name, "result": result},
                    )
                )

        self._emit(
            BridgeEvent(
                event_type=BridgeEventType.TURN_END,
                payload={"turn": self._turn_count, "status": "ok"},
            )
        )
        return "CONTINUE"

    # ------------------------------------------------------------------
    # Text / Function Call Extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(candidate: Candidate) -> Optional[str]:
        if not candidate.content or not candidate.content.parts:
            return None
        texts = [p.text for p in candidate.content.parts if p.text]
        return " ".join(texts) or None

    @staticmethod
    def _extract_function_calls(
        candidate: Candidate,
    ) -> list[genai_types.FunctionCall]:
        if not candidate.content or not candidate.content.parts:
            return []
        return [p.function_call for p in candidate.content.parts if p.function_call]

    # ------------------------------------------------------------------
    # Public API: Run Methods
    # ------------------------------------------------------------------

    def run_stream(
        self, query: str
    ) -> Generator[BridgeEvent, None, None]:
        """Execute a browser task synchronously, yielding events.

        Args:
            query: Natural language instruction for the browser agent.

        Yields:
            BridgeEvent: Structured events (reasoning, actions, screenshots, errors, completion).
        """
        if self._computer is None:
            raise RuntimeError("No computer backend attached. Call set_computer() first.")

        # Initialize conversation
        self._contents = [
            Content(
                role="user",
                parts=[Part(text=query)],
            )
        ]
        self._turn_count = 0
        self._completed_reasoning = None
        gen_config = self._build_config()

        # Optional initial state capture
        try:
            initial_state = self._computer.current_state()
            self._emit(
                BridgeEvent(
                    event_type=BridgeEventType.SCREENSHOT,
                    payload={
                        "screenshot_b64": base64.b64encode(initial_state.screenshot).decode(),
                        "url": initial_state.url,
                        "initial": True,
                    },
                )
            )
        except Exception:
            pass  # State may not be ready yet

        status: Literal["COMPLETE", "CONTINUE", "ERROR"] = "CONTINUE"
        while status == "CONTINUE":
            # Use a local queue to capture events from this turn
            turn_events: list[BridgeEvent] = []
            original_callbacks = self._callbacks[:]

            def capture(ev: BridgeEvent) -> None:
                turn_events.append(ev)

            self._callbacks.append(capture)
            try:
                status = self._run_one_turn(gen_config)
            finally:
                self._callbacks = original_callbacks

            # Yield all captured events
            for ev in turn_events:
                yield ev

        # Restore original callbacks and emit final events
        for cb in self._callbacks:
            try:
                cb(ev)  # type: ignore[name-defined]
            except Exception:
                pass

    async def run_stream_async(
        self, query: str
    ) -> AsyncGenerator[BridgeEvent, None]:
        """Async version of run_stream().

        Executes the browser agent loop in a background thread and
        yields events asynchronously.
        """
        loop = asyncio.get_event_loop()
        stream = self.run_stream(query)

        def _next() -> BridgeEvent:
            try:
                return next(stream)
            except StopIteration:
                raise StopAsyncIteration

        while True:
            try:
                event = await loop.run_in_executor(None, _next)
                yield event
            except StopAsyncIteration:
                break

    def run(self, query: str) -> str:
        """Execute a task synchronously and return final reasoning.

        Args:
            query: Natural language instruction.

        Returns:
            Final reasoning text from the model upon task completion.
        """
        for _ in self.run_stream(query):
            pass
        return self._completed_reasoning or ""

    async def run_async(self, query: str) -> str:
        """Async version of run()."""
        async for _ in self.run_stream_async(query):
            pass
        return self._completed_reasoning or ""

    # ------------------------------------------------------------------
    # History Management (Screenshot Pruning)
    # ------------------------------------------------------------------

    def prune_screenshot_history(self, max_turns: int = MAX_RECENT_TURN_WITH_SCREENSHOTS) -> None:
        """Remove inline screenshot data from older turns to manage token usage.

        Keeps only the most recent `max_turns` turns with full screenshot data.
        This is called automatically after each turn but can be invoked manually.
        """
        turn_count = 0
        for content in reversed(self._contents):
            if content.role == "user" and content.parts:
                has_screenshot = any(
                    p.function_response
                    and p.function_response.parts
                    and p.function_response.name in PREDEFINED_COMPUTER_USE_FUNCTIONS
                    for p in content.parts
                )
                if has_screenshot:
                    turn_count += 1
                    if turn_count > max_turns:
                        for part in content.parts:
                            if (
                                part.function_response
                                and part.function_response.parts
                                and part.function_response.name
                                in PREDEFINED_COMPUTER_USE_FUNCTIONS
                            ):
                                part.function_response.parts = None

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @property
    def turn_count(self) -> int:
        return self._turn_count

    @property
    def completed_reasoning(self) -> Optional[str]:
        return self._completed_reasoning

    def get_conversation_history(self) -> list[dict]:
        """Export conversation history as serializable dicts."""
        result = []
        for content in self._contents:
            entry: dict[str, Any] = {"role": content.role, "parts": []}
            for part in content.parts:
                p: dict[str, Any] = {}
                if part.text:
                    p["text"] = part.text
                if part.function_call:
                    p["function_call"] = {
                        "name": part.function_call.name,
                        "args": part.function_call.args,
                    }
                if part.function_response:
                    p["function_response"] = {
                        "name": part.function_response.name,
                        "response": part.function_response.response,
                    }
                entry["parts"].append(p)
            result.append(entry)
        return result


# ---------------------------------------------------------------------------
# Factory / Convenience Functions
# ---------------------------------------------------------------------------


def create_bridge_with_playwright(
    query: Optional[str] = None,
    config: Optional[GeminiComputerUseConfig] = None,
    **overrides: Any,
) -> Generator[GeminiComputerUseBridge, None, None]:
    """Context manager that creates a bridge with PlaywrightComputer attached.

    Args:
        query: Optional initial query (if None, bridge is returned for manual use).
        config: Bridge configuration.
        **overrides: Overrides for config attributes.

    Yields:
        Configured GeminiComputerUseBridge with Playwright backend.

    Example:
        with create_bridge_with_playwright() as bridge:
            for event in bridge.run_stream("Go to example.com"):
                print(event)
    """
    cfg = config or GeminiComputerUseConfig.from_env()
    for key, value in overrides.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)

    bridge = GeminiComputerUseBridge(cfg)
    computer = PlaywrightComputer(
        screen_size=cfg.screen_size,
        initial_url=cfg.initial_url,
        highlight_mouse=cfg.highlight_mouse,
    )
    with computer:
        bridge.set_computer(computer)
        yield bridge


@asynccontextmanager
async def create_bridge_with_playwright_async(
    config: Optional[GeminiComputerUseConfig] = None,
    **overrides: Any,
) -> AsyncGenerator[GeminiComputerUseBridge, None]:
    """Async context manager for Playwright-backed bridge."""
    cfg = config or GeminiComputerUseConfig.from_env()
    for key, value in overrides.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)

    bridge = GeminiComputerUseBridge(cfg)
    computer = PlaywrightComputer(
        screen_size=cfg.screen_size,
        initial_url=cfg.initial_url,
        highlight_mouse=cfg.highlight_mouse,
    )
    with computer:
        bridge.set_computer(computer)
        yield bridge


def quick_run(query: str, **kwargs: Any) -> str:
    """One-shot function to run a query and return the final reasoning.

    Args:
        query: Natural language browser task.
        **kwargs: Overrides for GeminiComputerUseConfig.

    Returns:
        Final reasoning text from the agent.
    """
    with create_bridge_with_playwright(**kwargs) as bridge:
        return bridge.run(query)


# ---------------------------------------------------------------------------
# Module-level __all__
# ---------------------------------------------------------------------------

__all__ = [
    # Config
    "GeminiComputerUseConfig",
    # Bridge
    "GeminiComputerUseBridge",
    # Events
    "BridgeEvent",
    "BridgeEventType",
    # Computers
    "Computer",
    "EnvState",
    "PlaywrightComputer",
    "BrowserbaseComputer",
    # Factories
    "create_bridge_with_playwright",
    "create_bridge_with_playwright_async",
    "quick_run",
    # Constants
    "PREDEFINED_COMPUTER_USE_FUNCTIONS",
    "DEFAULT_MODEL",
    "DEFAULT_SCREEN_SIZE",
]
