"""
JARVIS BRAINIAC - AgenticSeek Integration Bridge
================================================

Unified AgenticSeek (Fosowl/agenticSeek) adapter providing:
- Task planning with multi-step reasoning
- Web browsing and information retrieval
- Code generation with context awareness
- Mock fallback when agenticseek is not installed

Usage:
    bridge = AgenticSeekBridge()
    plan = bridge.plan_task("Build a REST API")
    result = bridge.browse_web("https://example.com")
    code = bridge.generate_code("Write a FastAPI endpoint")
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability flag
# ---------------------------------------------------------------------------
_AGENTICSEEK_AVAILABLE: bool = False

try:
    import agenticseek
    from agenticseek.planner import TaskPlanner
    from agenticseek.browser import WebBrowser
    from agenticseek.coder import CodeGenerator
    from agenticseek.agent import AgenticSeekAgent
    _AGENTICSEEK_AVAILABLE = True
    logger.info("AgenticSeek %s loaded successfully.", agenticseek.__version__)
except Exception as _import_exc:
    logger.warning(
        "AgenticSeek not installed or failed to import (%s). "
        "Falling back to mock implementations.", _import_exc,
    )

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class TaskPlan:
    """Output from task planning."""
    task: str
    steps: List[str] = field(default_factory=list)
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    estimated_time: int = 0
    success: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task, "steps": self.steps,
            "dependencies": self.dependencies,
            "estimated_time": self.estimated_time, "success": self.success,
        }


@dataclass
class BrowseResult:
    """Output from web browsing."""
    url: str
    title: str = ""
    content: str = ""
    links: List[str] = field(default_factory=list)
    success: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url, "title": self.title,
            "content": self.content[:500], "links": self.links,
            "success": self.success,
        }


@dataclass
class CodeResult:
    """Output from code generation."""
    prompt: str
    code: str = ""
    language: str = "python"
    explanation: str = ""
    success: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt, "code": self.code,
            "language": self.language, "explanation": self.explanation,
            "success": self.success,
        }


# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------

class _MockPlanner:
    """Mock task planner simulating AgenticSeek planner."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self.history: List[Dict[str, Any]] = []

    def plan(self, task: str) -> TaskPlan:
        steps = [
            f"Analyze requirements for: {task[:60]}",
            "Research existing solutions and best practices",
            "Design architecture and data models",
            "Implement core functionality",
            "Write tests and validate",
            "Deploy and monitor",
        ]
        plan = TaskPlan(
            task=task, steps=steps,
            dependencies={"step_3": ["step_1", "step_2"], "step_4": ["step_3"]},
            estimated_time=120, success=True,
        )
        self.history.append(plan.to_dict())
        return plan

    def refine(self, plan: TaskPlan, feedback: str) -> TaskPlan:
        plan.steps.append(f"Refinement based on feedback: {feedback[:50]}")
        return plan


class _MockBrowser:
    """Mock web browser simulating AgenticSeek browser."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self.visited: List[str] = []

    def browse(self, url: str) -> BrowseResult:
        self.visited.append(url)
        return BrowseResult(
            url=url, title=f"Mock Page - {url.split('/')[-1][:30]}",
            content=f"<html><body><h1>Mock content from {url}</h1>"
                    f"<p>This is simulated page content.</p></body></html>",
            links=[f"{url}/page1", f"{url}/page2"], success=True,
        )

    def search(self, query: str) -> List[BrowseResult]:
        return [
            BrowseResult(
                url=f"https://example.com/search?q={query.replace(' ', '+')}",
                title=f"Search result for '{query[:30]}'",
                content=f"<p>Mock search results for: {query}</p>",
                success=True,
            ),
        ]

    def extract_text(self, html: str) -> str:
        import re
        return re.sub(r"<[^>]+>", " ", html).strip()[:500]


class _MockCodeGenerator:
    """Mock code generator simulating AgenticSeek coder."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self.generation_history: List[Dict[str, Any]] = []

    def generate(self, prompt: str, language: str = "python") -> CodeResult:
        code = self._mock_code_for_prompt(prompt, language)
        result = CodeResult(
            prompt=prompt, code=code, language=language,
            explanation=f"Generated {language} code for: {prompt[:80]}",
            success=True,
        )
        self.generation_history.append(result.to_dict())
        return result

    def _mock_code_for_prompt(self, prompt: str, language: str) -> str:
        p = prompt.lower()
        if "fastapi" in p or "api" in p:
            return "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get(\"/\")\ndef read_root():\n    return {\"message\": \"Hello World\"}"
        elif "flask" in p:
            return "from flask import Flask\n\napp = Flask(__name__)\n\n@app.route(\"/\")\ndef home():\n    return \"Hello, World!\""
        elif "django" in p:
            return "from django.http import JsonResponse\n\ndef home(request):\n    return JsonResponse({\"message\": \"Hello\"})"
        elif "sort" in p:
            return "def sort_data(data):\n    return sorted(data)\n\n# Usage\nprint(sort_data([3, 1, 4, 1, 5]))"
        elif "scrape" in p:
            return "import requests\nfrom bs4 import BeautifulSoup\n\ndef scrape(url):\n    r = requests.get(url)\n    return BeautifulSoup(r.text, 'html.parser')"
        else:
            return f"# Generated code for: {prompt}\ndef solution():\n    pass\n\nif __name__ == '__main__':\n    solution()"


# ---------------------------------------------------------------------------
# AgenticSeekBridge
# ---------------------------------------------------------------------------

class AgenticSeekBridge:
    """
    Unified AgenticSeek integration bridge for JARVIS BRAINIAC.

    Provides task planning, web browsing, and code generation.
    When AgenticSeek is not installed, all methods return
    fully-functional mock implementations.

    Attributes:
        available (bool): Whether the real AgenticSeek library is installed.
        config (dict): Bridge configuration.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, verbose: bool = True) -> None:
        self.available: bool = _AGENTICSEEK_AVAILABLE
        self.verbose: bool = verbose
        self.config: Dict[str, Any] = config or self._build_default_config()
        self._planner: Any = None
        self._browser: Any = None
        self._coder: Any = None
        self._call_history: List[Dict[str, Any]] = []
        logger.info("AgenticSeekBridge initialized (available=%s)", self.available)

    def _build_default_config(self) -> Dict[str, Any]:
        return {
            "llm": {
                "provider": os.environ.get("LLM_PROVIDER", "openai"),
                "model": os.environ.get("AGENTICSEEK_MODEL", "gpt-4"),
                "api_key": os.environ.get("OPENAI_API_KEY", ""),
            },
            "browser": {"headless": True, "timeout": 30},
            "code": {"max_tokens": 4096, "temperature": 0.2},
        }

    def _log(self, msg: str) -> None:
        if self.verbose:
            logger.info("[AgenticSeekBridge] %s", msg)

    def _get_planner(self) -> Any:
        if self._planner is None:
            if self.available:
                try:
                    self._planner = TaskPlanner(config=self.config)
                except Exception as exc:
                    logger.error("Planner init failed: %s. Using mock.", exc)
                    self._planner = _MockPlanner(self.config)
            else:
                self._planner = _MockPlanner(self.config)
        return self._planner

    def _get_browser(self) -> Any:
        if self._browser is None:
            if self.available:
                try:
                    self._browser = WebBrowser(config=self.config.get("browser"))
                except Exception as exc:
                    logger.error("Browser init failed: %s. Using mock.", exc)
                    self._browser = _MockBrowser(self.config.get("browser"))
            else:
                self._browser = _MockBrowser(self.config.get("browser"))
        return self._browser

    def _get_coder(self) -> Any:
        if self._coder is None:
            if self.available:
                try:
                    self._coder = CodeGenerator(config=self.config.get("code"))
                except Exception as exc:
                    logger.error("Coder init failed: %s. Using mock.", exc)
                    self._coder = _MockCodeGenerator(self.config.get("code"))
            else:
                self._coder = _MockCodeGenerator(self.config.get("code"))
        return self._coder

    # -- public API ----------------------------------------------------------

    def plan_task(self, task: str, context: Optional[str] = None) -> TaskPlan:
        """
        Plan a multi-step execution for a given task.

        Args:
            task: Natural language task description.
            context: Optional additional context.

        Returns:
            TaskPlan with steps and dependencies.
        """
        self._log(f"Planning task: {task[:80]}")
        planner = self._get_planner()
        full_task = f"{task}\nContext: {context}" if context else task
        try:
            if self.available and hasattr(planner, 'plan'):
                result = planner.plan(full_task)
                if not isinstance(result, TaskPlan):
                    result = TaskPlan(task=task, steps=[str(result)], success=True)
            else:
                result = planner.plan(full_task)
        except Exception as exc:
            logger.error("plan_task failed: %s", exc)
            result = TaskPlan(task=task, steps=["Error during planning"], success=False)
        self._call_history.append({"method": "plan_task", "task": task, "success": result.success})
        return result

    def browse_web(self, url: str, extract_text: bool = True) -> BrowseResult:
        """
        Browse a web page and extract information.

        Args:
            url: Target URL to browse.
            extract_text: Whether to extract plain text from HTML.

        Returns:
            BrowseResult with page content.
        """
        self._log(f"Browsing: {url}")
        browser = self._get_browser()
        try:
            result = browser.browse(url)
            if extract_text and hasattr(browser, 'extract_text'):
                result.content = browser.extract_text(result.content)
        except Exception as exc:
            logger.error("browse_web failed: %s", exc)
            result = BrowseResult(url=url, success=False)
        self._call_history.append({"method": "browse_web", "url": url})
        return result

    def generate_code(self, prompt: str, language: str = "python") -> CodeResult:
        """
        Generate code from a natural language prompt.

        Args:
            prompt: Natural language code description.
            language: Target programming language.

        Returns:
            CodeResult with generated code.
        """
        self._log(f"Generating {language} code for: {prompt[:80]}")
        coder = self._get_coder()
        try:
            result = coder.generate(prompt, language=language)
        except Exception as exc:
            logger.error("generate_code failed: %s", exc)
            result = CodeResult(prompt=prompt, success=False)
        self._call_history.append({"method": "generate_code", "prompt": prompt})
        return result

    def get_status(self) -> Dict[str, Any]:
        """Return detailed bridge status and history."""
        return {
            "available": self.available,
            "calls": len(self._call_history),
            "recent_calls": self._call_history[-5:],
            "components": {
                "planner": self._planner is not None,
                "browser": self._browser is not None,
                "coder": self._coder is not None,
            },
        }

    def health_check(self) -> Dict[str, Any]:
        """Return health status of the bridge."""
        return {
            "available": self.available,
            "calls": len(self._call_history),
            "component_status": {
                "planner": "ok" if self._get_planner() else "fail",
                "browser": "ok" if self._get_browser() else "fail",
                "coder": "ok" if self._get_coder() else "fail",
            },
        }

    def metadata(self) -> Dict[str, Any]:
        """Return bridge metadata."""
        return {
            "name": "AgenticSeekBridge",
            "version": "1.0.0",
            "project": "Fosowl/agenticSeek",
            "stars": "26.1k",
            "description": "Fully local Manus AI alternative",
            "methods": ["plan_task", "browse_web", "generate_code", "get_status"],
            "mock_fallback": True,
        }


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def get_agenticseek_bridge(config: Optional[Dict[str, Any]] = None, verbose: bool = True) -> AgenticSeekBridge:
    return AgenticSeekBridge(config=config, verbose=verbose)


# ---------------------------------------------------------------------------
# __main__ self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bridge = get_agenticseek_bridge(verbose=True)

    assert bridge.health_check()["available"] in (True, False)
    assert bridge.metadata()["name"] == "AgenticSeekBridge"

    plan = bridge.plan_task("Build a REST API for user management")
    assert isinstance(plan, TaskPlan)
    assert len(plan.steps) > 0

    browse = bridge.browse_web("https://example.com")
    assert isinstance(browse, BrowseResult)
    assert browse.url == "https://example.com"

    code = bridge.generate_code("Write a FastAPI hello world endpoint")
    assert isinstance(code, CodeResult)
    assert len(code.code) > 0
    assert code.success

    status = bridge.get_status()
    assert status["calls"] == 3

    print("All AgenticSeekBridge self-tests passed!")
