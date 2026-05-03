#!/usr/bin/env python3
"""
Meta-Agent Bridge: Dynamic Integration Adapter for Top 10 AI Agent Repositories.

This module provides a unified interface to dynamically load, configure, and
interact with any of the top 10 AI agent / autonomous agent repositories found
on GitHub. It handles repository cloning, dependency management, configuration,
and runtime execution across heterogeneous agent frameworks.

Supported Agents:
    1. crewAI        - Multi-agent orchestration framework (Python)
    2. cherry-studio - AI productivity desktop app (TypeScript)
    3. AgentGPT      - Browser-based autonomous agents (TypeScript/Python) [ARCHIVED]
    4. khoj          - Personal AI second brain (Python/TypeScript)
    5. ruflo         - Claude multi-agent swarm platform (TypeScript)
    6. zeroclaw      - Rust-based personal AI assistant (Rust)
    7. awesome-ai-agents - Curated list (reference only)
    8. gpt-researcher - Deep research agent (Python)
    9. agenticSeek   - Fully local Manus alternative (Python)
    10. elizaOS      - Multi-agent AI development platform (TypeScript)

Usage:
    from meta_agent_bridge import MetaAgentBridge

    bridge = MetaAgentBridge()

    # Load an agent by name
    agent = bridge.load_agent("crewai")

    # Configure and run
    agent.configure({"model": "gpt-4", "verbose": True})
    result = agent.execute("Research the latest AI trends")

    # Or use the unified execution interface
    result = bridge.execute("crewai", "Create a marketing plan", config={...})

Author: JARVIS Runtime
Date: 2026-04-28
"""

from __future__ import annotations

import abc
import json
import logging
from runtime.agency.jarvis_logging import configure, get_logger
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    List,
    Optional,
    Protocol,
    Type,
    TypeVar,
    Union,
    runtime_checkable,
)

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------

logger = logging.getLogger("meta_agent_bridge")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter(
    "[%(asctime)s] %(levelname)s - %(name)s: %(message)s"
))
if not logger.handlers:
    logger.addHandler(_handler)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class AgentStatus(Enum):
    """Lifecycle states for an agent integration."""
    NOT_INSTALLED = "not_installed"
    INSTALLING = "installing"
    READY = "ready"
    CONFIGURED = "configured"
    RUNNING = "running"
    ERROR = "error"
    ARCHIVED = "archived"


@dataclass
class AgentMetadata:
    """Metadata descriptor for a supported external agent."""
    name: str
    repo_url: str
    github_stars: int
    primary_language: str
    license: str
    description: str
    status: AgentStatus = AgentStatus.NOT_INSTALLED
    install_path: Optional[Path] = None
    config_path: Optional[Path] = None
    version: str = "latest"
    is_archived: bool = False
    dependencies: List[str] = field(default_factory=list)
    env_vars: List[str] = field(default_factory=list)
    entry_points: Dict[str, str] = field(default_factory=dict)
    plugin_name: Optional[str] = None


@dataclass
class ExecutionResult:
    """Standardized result wrapper for agent executions."""
    success: bool
    agent_name: str
    output: Any
    logs: List[str] = field(default_factory=list)
    artifacts: Dict[str, Union[str, bytes]] = field(default_factory=dict)
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "agent_name": self.agent_name,
            "output": self.output if isinstance(self.output, (str, int, float, bool, type(None))) else str(self.output),
            "logs": self.logs,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


# ---------------------------------------------------------------------------
# Agent Registry
# ---------------------------------------------------------------------------

class AgentRegistry:
    """Central registry of all supported agent integrations."""

    _AGENTS: Dict[str, AgentMetadata] = {
        "crewai": AgentMetadata(
            name="crewai",
            repo_url="https://github.com/crewAIInc/crewAI",
            github_stars=50200,
            primary_language="python",
            license="MIT",
            description="Framework for orchestrating role-playing, autonomous AI agents",
            dependencies=["crewai", "crewai-tools", "uv"],
            env_vars=["OPENAI_API_KEY", "SERPER_API_KEY"],
            entry_points={
                "cli": "crewai",
                "python": "crewai",
                "create": "crewai create crew",
            },
            plugin_name="crewai-skills",
        ),
        "cherry-studio": AgentMetadata(
            name="cherry-studio",
            repo_url="https://github.com/CherryHQ/cherry-studio",
            github_stars=44700,
            primary_language="typescript",
            license="AGPL-3.0",
            description="AI productivity studio with smart chat, autonomous agents, and 300+ assistants",
            dependencies=["node", "pnpm"],
            env_vars=[],
            entry_points={
                "desktop": "cherry-studio",
                "web": "pnpm dev",
            },
        ),
        "agentgpt": AgentMetadata(
            name="agentgpt",
            repo_url="https://github.com/reworkd/AgentGPT",
            github_stars=36000,
            primary_language="typescript",
            license="GPL-3.0",
            description="Assemble, configure, and deploy autonomous AI Agents in your browser",
            is_archived=True,
            dependencies=["node", "docker"],
            env_vars=["OPENAI_API_KEY", "SERPER_API_KEY", "REPLICATE_API_TOKEN"],
            entry_points={
                "web": "npm run dev",
                "setup": "./setup.sh",
            },
        ),
        "khoj": AgentMetadata(
            name="khoj",
            repo_url="https://github.com/khoj-ai/khoj",
            github_stars=34300,
            primary_language="python",
            license="AGPL-3.0",
            description="Your AI second brain. Self-hostable. Get answers from the web or your docs",
            dependencies=["khoj", "docker"],
            env_vars=["OPENAI_API_KEY", "KHOJ_ADMIN_EMAIL", "KHOJ_ADMIN_PASSWORD"],
            entry_points={
                "self-hosted": "docker compose up",
                "python": "khoj",
                "web": "https://app.khoj.dev",
            },
        ),
        "ruflo": AgentMetadata(
            name="ruflo",
            repo_url="https://github.com/ruvnet/ruflo",
            github_stars=33900,
            primary_language="typescript",
            license="MIT",
            description="Agent orchestration platform for Claude with multi-agent swarms",
            dependencies=["node", "npm"],
            env_vars=["ANTHROPIC_API_KEY"],
            entry_points={
                "cli": "npx ruflo@latest",
                "claude-plugin": "/plugin install ruflo-core@ruflo",
                "mcp": "claude mcp add ruflo",
            },
            plugin_name="ruflo-core",
        ),
        "zeroclaw": AgentMetadata(
            name="zeroclaw",
            repo_url="https://github.com/zeroclaw-labs/zeroclaw",
            github_stars=30800,
            primary_language="rust",
            license="Apache-2.0 / MIT",
            description="Fast, small, fully autonomous AI personal assistant infrastructure",
            dependencies=["rust", "cargo"],
            env_vars=["OPENAI_API_KEY", "ANTHROPIC_API_KEY"],
            entry_points={
                "cli": "zeroclaw",
                "onboard": "zeroclaw onboard",
                "agent": "zeroclaw agent",
                "service": "zeroclaw service",
            },
        ),
        "awesome-ai-agents": AgentMetadata(
            name="awesome-ai-agents",
            repo_url="https://github.com/e2b-dev/awesome-ai-agents",
            github_stars=27500,
            primary_language="markdown",
            license="CC BY-NC-SA 4.0",
            description="Curated list of AI autonomous agents (reference only, not executable)",
            dependencies=[],
            env_vars=[],
            entry_points={
                "web": "https://e2b.dev/ai-agents",
            },
        ),
        "gpt-researcher": AgentMetadata(
            name="gpt-researcher",
            repo_url="https://github.com/assafelovic/gpt-researcher",
            github_stars=26800,
            primary_language="python",
            license="Apache-2.0",
            description="Autonomous agent that conducts deep research on any data using any LLM",
            dependencies=["gpt-researcher", "tavily-python"],
            env_vars=["OPENAI_API_KEY", "TAVILY_API_KEY"],
            entry_points={
                "cli": "python -m gpt_researcher",
                "web": "docker run -it --rm gptresearcher/gpt-researcher",
                "python": "gpt_researcher",
            },
            plugin_name="assafelovic/gpt-researcher",
        ),
        "agenticseek": AgentMetadata(
            name="agenticseek",
            repo_url="https://github.com/Fosowl/agenticSeek",
            github_stars=26100,
            primary_language="python",
            license="GPL-3.0",
            description="Fully Local Manus AI. No APIs. Autonomous agent that browses and codes locally",
            dependencies=["python3.11", "docker"],
            env_vars=[],
            entry_points={
                "cli": "python api.py",
                "web": "docker compose up",
            },
        ),
        "elizaos": AgentMetadata(
            name="elizaos",
            repo_url="https://github.com/elizaOS/eliza",
            github_stars=18300,
            primary_language="typescript",
            license="MIT",
            description="Autonomous agents for everyone. Multi-agent AI development platform",
            dependencies=["node", "bun"],
            env_vars=["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY"],
            entry_points={
                "cli": "bunx @elizaos/cli",
                "create": "elizaos create",
                "dev": "bun run dev",
                "desktop": "bun run dev:desktop",
            },
        ),
    }

    @classmethod
    def list_agents(cls) -> List[str]:
        """Return sorted list of all supported agent names."""
        return sorted(cls._AGENTS.keys())

    @classmethod
    def get_metadata(cls, name: str) -> AgentMetadata:
        """Retrieve metadata for a specific agent."""
        key = name.lower().replace("_", "-").replace(" ", "-")
        # Handle aliases
        aliases = {
            "crew-ai": "crewai",
            "cherry": "cherry-studio",
            "agent-gpt": "agentgpt",
            "gpt_researcher": "gpt-researcher",
            "gptresearcher": "gpt-researcher",
            "agentic-seek": "agenticseek",
            "eliza": "elizaos",
            "eliza-os": "elizaos",
        }
        key = aliases.get(key, key)
        if key not in cls._AGENTS:
            raise ValueError(
                f"Unknown agent '{name}'. Supported: {cls.list_agents()}"
            )
        return cls._AGENTS[key]

    @classmethod
    def search_by_language(cls, language: str) -> List[AgentMetadata]:
        """Find all agents matching a programming language."""
        lang = language.lower()
        return [a for a in cls._AGENTS.values() if a.primary_language == lang]

    @classmethod
    def search_by_license(cls, license_name: str) -> List[AgentMetadata]:
        """Find all agents matching a license type."""
        return [a for a in cls._AGENTS.values() if license_name.lower() in a.license.lower()]

    @classmethod
    def get_all_metadata(cls) -> Dict[str, AgentMetadata]:
        """Return full registry copy."""
        return dict(cls._AGENTS)


# ---------------------------------------------------------------------------
# Abstract Agent Adapter
# ---------------------------------------------------------------------------

class AgentAdapter(abc.ABC):
    """Abstract base class for agent-specific adapters."""

    def __init__(self, metadata: AgentMetadata, workspace: Path):
        self.metadata = metadata
        self.workspace = workspace
        self.config: Dict[str, Any] = {}
        self._process: Optional[subprocess.Popen] = None
        self._status = AgentStatus.NOT_INSTALLED

    @property
    def status(self) -> AgentStatus:
        return self._status

    @abc.abstractmethod
    def install(self, force: bool = False) -> None:
        """Install the agent and its dependencies into the workspace."""

    @abc.abstractmethod
    def configure(self, config: Dict[str, Any]) -> None:
        """Apply configuration settings."""

    @abc.abstractmethod
    def execute(self, task: str, **kwargs: Any) -> ExecutionResult:
        """Execute a task and return standardized results."""

    @abc.abstractmethod
    def health_check(self) -> bool:
        """Verify the agent is properly installed and functional."""

    def teardown(self) -> None:
        """Clean up running processes."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def _run_command(
        self,
        cmd: Union[str, List[str]],
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = 300,
    ) -> subprocess.CompletedProcess:
        """Run a shell command with proper error handling."""
        if isinstance(cmd, str):
            cmd = ["bash", "-c", cmd]
        working_dir = cwd or self.workspace
        merged_env = {**os.environ, **(env or {})}

        logger.debug("Executing: %s in %s", " ".join(cmd), working_dir)
        return subprocess.run(
            cmd,
            cwd=working_dir,
            env=merged_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )


# ---------------------------------------------------------------------------
# Concrete Adapters
# ---------------------------------------------------------------------------

class PythonAgentAdapter(AgentAdapter):
    """Adapter for Python-based agents (crewAI, khoj, gpt-researcher, agenticSeek)."""

    def __init__(self, metadata: AgentMetadata, workspace: Path):
        super().__init__(metadata, workspace)
        self.venv_path = workspace / ".venv"
        self.python_bin = self.venv_path / "bin" / "python"
        if sys.platform == "win32":
            self.python_bin = self.venv_path / "Scripts" / "python.exe"

    def install(self, force: bool = False) -> None:
        if self._status == AgentStatus.READY and not force:
            return
        self._status = AgentStatus.INSTALLING

        try:
            # Create virtual environment
            if not self.python_bin.exists() or force:
                logger.info("Creating virtual environment for %s", self.metadata.name)
                venv.create(self.venv_path, with_pip=True)

            # Install dependencies
            for dep in self.metadata.dependencies:
                if dep in ("docker", "uv"):
                    continue  # System dependencies
                logger.info("Installing %s for %s", dep, self.metadata.name)
                self._run_command([str(self.python_bin), "-m", "pip", "install", "-U", dep])

            self._status = AgentStatus.READY
            logger.info("%s installed successfully", self.metadata.name)
        except Exception as e:
            self._status = AgentStatus.ERROR
            logger.error("Installation failed for %s: %s", self.metadata.name, e)
            raise

    def configure(self, config: Dict[str, Any]) -> None:
        self.config.update(config)
        # Write .env file if needed
        env_path = self.workspace / ".env"
        env_lines = []
        for key in self.metadata.env_vars:
            if key in self.config:
                env_lines.append(f"{key}={self.config[key]}")
        if env_lines:
            env_path.write_text("\n".join(env_lines) + "\n")
        self._status = AgentStatus.CONFIGURED

    def execute(self, task: str, **kwargs: Any) -> ExecutionResult:
        import time
        start = time.time()
        logs: List[str] = []

        try:
            # Build execution command based on agent
            if self.metadata.name == "crewai":
                cmd = self._build_crewai_command(task, **kwargs)
            elif self.metadata.name == "gpt-researcher":
                cmd = self._build_gpt_researcher_command(task, **kwargs)
            elif self.metadata.name == "khoj":
                cmd = self._build_khoj_command(task, **kwargs)
            elif self.metadata.name == "agenticseek":
                cmd = self._build_agenticseek_command(task, **kwargs)
            else:
                cmd = [str(self.python_bin), "-c", f"print('Task: {task}')"]

            self._status = AgentStatus.RUNNING
            result = self._run_command(cmd, timeout=kwargs.get("timeout", 600))
            duration = (time.time() - start) * 1000

            logs = [result.stdout, result.stderr] if result.stderr else [result.stdout]
            success = result.returncode == 0

            return ExecutionResult(
                success=success,
                agent_name=self.metadata.name,
                output=result.stdout if success else result.stderr,
                logs=logs,
                duration_ms=duration,
                metadata={"returncode": result.returncode},
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.error("Execution error in %s: %s", self.metadata.name, e)
            return ExecutionResult(
                success=False,
                agent_name=self.metadata.name,
                output=str(e),
                logs=[str(e)],
                duration_ms=duration,
                metadata={"error_type": type(e).__name__},
            )
        finally:
            self._status = AgentStatus.CONFIGURED

    def _build_crewai_command(self, task: str, **kwargs: Any) -> List[str]:
        topic = kwargs.get("topic", task)
        return [
            str(self.python_bin), "-c",
            f"from crewai import Agent, Crew, Process, Task; "
            f"agent = Agent(role='Researcher', goal='{task}', verbose=True); "
            f"task = Task(description='{task}', agent=agent); "
            f"crew = Crew(agents=[agent], tasks=[task], process=Process.sequential); "
            f"print(crew.kickoff(inputs={{'topic': '{topic}'}}))"
        ]

    def _build_gpt_researcher_command(self, task: str, **kwargs: Any) -> List[str]:
        report_type = kwargs.get("report_type", "research_report")
        return [
            str(self.python_bin), "-m", "gpt_researcher",
            "--query", task,
            "--report_type", report_type,
        ]

    def _build_khoj_command(self, task: str, **kwargs: Any) -> List[str]:
        return [str(self.python_bin), "-m", "khoj", "--query", task]

    def _build_agenticseek_command(self, task: str, **kwargs: Any) -> List[str]:
        return [str(self.python_bin), "api.py", "--task", task]

    def health_check(self) -> bool:
        try:
            result = self._run_command([str(self.python_bin), "--version"])
            return result.returncode == 0
        except Exception:
            return False


class NodeAgentAdapter(AgentAdapter):
    """Adapter for Node.js/TypeScript-based agents (cherry-studio, ruflo, elizaOS)."""

    def __init__(self, metadata: AgentMetadata, workspace: Path):
        super().__init__(metadata, workspace)
        self.node_bin = shutil.which("node") or "node"
        self.npm_bin = shutil.which("npm") or "npm"
        self.bun_bin = shutil.which("bun")

    def install(self, force: bool = False) -> None:
        if self._status == AgentStatus.READY and not force:
            return
        self._status = AgentStatus.INSTALLING

        try:
            # Clone repository
            repo_dir = self.workspace / self.metadata.name
            if not repo_dir.exists() or force:
                if repo_dir.exists():
                    shutil.rmtree(repo_dir)
                logger.info("Cloning %s from %s", self.metadata.name, self.metadata.repo_url)
                self._run_command(["git", "clone", "--depth", "1", self.metadata.repo_url, str(repo_dir)])

            # Install dependencies
            pkg_manager = "bun" if self.bun_bin and self.metadata.name in ("elizaos",) else "npm"
            install_cmd = [pkg_manager, "install"]
            logger.info("Running %s install for %s", pkg_manager, self.metadata.name)
            self._run_command(install_cmd, cwd=repo_dir)

            self.metadata.install_path = repo_dir
            self._status = AgentStatus.READY
            logger.info("%s installed successfully", self.metadata.name)
        except Exception as e:
            self._status = AgentStatus.ERROR
            logger.error("Installation failed for %s: %s", self.metadata.name, e)
            raise

    def configure(self, config: Dict[str, Any]) -> None:
        self.config.update(config)
        # Write .env file
        if self.metadata.install_path:
            env_path = self.metadata.install_path / ".env"
            env_lines = []
            for key in self.metadata.env_vars:
                if key in self.config:
                    env_lines.append(f"{key}={self.config[key]}")
            if env_lines:
                env_path.write_text("\n".join(env_lines) + "\n")
        self._status = AgentStatus.CONFIGURED

    def execute(self, task: str, **kwargs: Any) -> ExecutionResult:
        import time
        start = time.time()

        try:
            repo_dir = self.metadata.install_path or self.workspace / self.metadata.name
            if self.metadata.name == "elizaos":
                cmd = [self.bun_bin or "bun", "run", "start", "--", "--task", task]
            elif self.metadata.name == "cherry-studio":
                cmd = [self.npm_bin, "run", "dev"]
            elif self.metadata.name == "ruflo":
                cmd = ["npx", "ruflo@latest", "run", task]
            else:
                cmd = [self.npm_bin, "run", "dev"]

            self._status = AgentStatus.RUNNING
            env = {k: str(v) for k, v in self.config.items() if isinstance(v, (str, int, float))}
            result = self._run_command(cmd, cwd=repo_dir, env=env, timeout=kwargs.get("timeout", 600))
            duration = (time.time() - start) * 1000

            return ExecutionResult(
                success=result.returncode == 0,
                agent_name=self.metadata.name,
                output=result.stdout if result.returncode == 0 else result.stderr,
                logs=[result.stdout, result.stderr] if result.stderr else [result.stdout],
                duration_ms=duration,
                metadata={"returncode": result.returncode},
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return ExecutionResult(
                success=False,
                agent_name=self.metadata.name,
                output=str(e),
                logs=[str(e)],
                duration_ms=duration,
            )
        finally:
            self._status = AgentStatus.CONFIGURED

    def health_check(self) -> bool:
        try:
            result = self._run_command([self.node_bin, "--version"])
            return result.returncode == 0
        except Exception:
            return False


class RustAgentAdapter(AgentAdapter):
    """Adapter for Rust-based agents (zeroclaw)."""

    def __init__(self, metadata: AgentMetadata, workspace: Path):
        super().__init__(metadata, workspace)
        self.cargo_bin = shutil.which("cargo") or "cargo"

    def install(self, force: bool = False) -> None:
        if self._status == AgentStatus.READY and not force:
            return
        self._status = AgentStatus.INSTALLING

        try:
            # Use prebuilt binary if available
            install_script = self.workspace / "install.sh"
            if install_script.exists() and not force:
                logger.info("Running install script for %s", self.metadata.name)
                self._run_command(["bash", str(install_script), "--prebuilt"])
            else:
                # Install via cargo
                logger.info("Installing %s via cargo", self.metadata.name)
                self._run_command([self.cargo_bin, "install", "zeroclaw"])

            self._status = AgentStatus.READY
            logger.info("%s installed successfully", self.metadata.name)
        except Exception as e:
            self._status = AgentStatus.ERROR
            logger.error("Installation failed for %s: %s", self.metadata.name, e)
            raise

    def configure(self, config: Dict[str, Any]) -> None:
        self.config.update(config)
        config_dir = Path.home() / ".zeroclaw"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "config.toml"

        toml_lines = ["[providers.models.default]"]
        if "OPENAI_API_KEY" in self.config:
            toml_lines.append(f'api_key = "{self.config["OPENAI_API_KEY"]}"')
        if "model" in self.config:
            toml_lines.append(f'model = "{self.config["model"]}"')

        config_file.write_text("\n".join(toml_lines) + "\n")
        self._status = AgentStatus.CONFIGURED

    def execute(self, task: str, **kwargs: Any) -> ExecutionResult:
        import time
        start = time.time()

        try:
            cmd = ["zeroclaw", "agent", "--prompt", task]
            self._status = AgentStatus.RUNNING
            result = self._run_command(cmd, timeout=kwargs.get("timeout", 600))
            duration = (time.time() - start) * 1000

            return ExecutionResult(
                success=result.returncode == 0,
                agent_name=self.metadata.name,
                output=result.stdout if result.returncode == 0 else result.stderr,
                logs=[result.stdout, result.stderr] if result.stderr else [result.stdout],
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return ExecutionResult(
                success=False,
                agent_name=self.metadata.name,
                output=str(e),
                logs=[str(e)],
                duration_ms=duration,
            )
        finally:
            self._status = AgentStatus.CONFIGURED

    def health_check(self) -> bool:
        try:
            result = self._run_command(["zeroclaw", "--version"])
            return result.returncode == 0
        except Exception:
            return False


class ArchiveAgentAdapter(AgentAdapter):
    """Adapter for archived projects (AgentGPT) - limited functionality."""

    def install(self, force: bool = False) -> None:
        logger.warning("%s is archived and read-only. Cloning for reference only.", self.metadata.name)
        repo_dir = self.workspace / self.metadata.name
        if not repo_dir.exists() or force:
            if repo_dir.exists():
                shutil.rmtree(repo_dir)
            self._run_command(["git", "clone", "--depth", "1", self.metadata.repo_url, str(repo_dir)])
        self.metadata.install_path = repo_dir
        self._status = AgentStatus.ARCHIVED

    def configure(self, config: Dict[str, Any]) -> None:
        self.config.update(config)

    def execute(self, task: str, **kwargs: Any) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            agent_name=self.metadata.name,
            output=f"{self.metadata.name} is archived and cannot execute tasks.",
            logs=["Project is archived"],
            metadata={"archived": True},
        )

    def health_check(self) -> bool:
        return self.metadata.install_path and self.metadata.install_path.exists()


class ReferenceAgentAdapter(AgentAdapter):
    """Adapter for reference-only repos (awesome-ai-agents)."""

    def install(self, force: bool = False) -> None:
        repo_dir = self.workspace / self.metadata.name
        if not repo_dir.exists() or force:
            if repo_dir.exists():
                shutil.rmtree(repo_dir)
            self._run_command(["git", "clone", "--depth", "1", self.metadata.repo_url, str(repo_dir)])
        self.metadata.install_path = repo_dir
        self._status = AgentStatus.READY

    def configure(self, config: Dict[str, Any]) -> None:
        self.config.update(config)

    def execute(self, task: str, **kwargs: Any) -> ExecutionResult:
        # Return the list of agents from the awesome list
        repo_dir = self.metadata.install_path
        if repo_dir:
            readme = repo_dir / "README.md"
            if readme.exists():
                content = readme.read_text()[:5000]
                return ExecutionResult(
                    success=True,
                    agent_name=self.metadata.name,
                    output=f"Reference repository loaded. First 5000 chars of README:\n{content}",
                    logs=["Reference content loaded"],
                )
        return ExecutionResult(
            success=True,
            agent_name=self.metadata.name,
            output="Reference repository for AI agents. Visit https://e2b.dev/ai-agents for the web UI.",
        )

    def health_check(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Adapter Factory
# ---------------------------------------------------------------------------

class AdapterFactory:
    """Factory for creating appropriate agent adapters."""

    _ADAPTER_MAP: Dict[str, Type[AgentAdapter]] = {
        "crewai": PythonAgentAdapter,
        "khoj": PythonAgentAdapter,
        "gpt-researcher": PythonAgentAdapter,
        "agenticseek": PythonAgentAdapter,
        "cherry-studio": NodeAgentAdapter,
        "ruflo": NodeAgentAdapter,
        "elizaos": NodeAgentAdapter,
        "zeroclaw": RustAgentAdapter,
        "agentgpt": ArchiveAgentAdapter,
        "awesome-ai-agents": ReferenceAgentAdapter,
    }

    @classmethod
    def create_adapter(cls, metadata: AgentMetadata, workspace: Path) -> AgentAdapter:
        """Create the appropriate adapter for the given agent metadata."""
        adapter_cls = cls._ADAPTER_MAP.get(metadata.name, AgentAdapter)
        return adapter_cls(metadata, workspace)


# ---------------------------------------------------------------------------
# Meta Agent Bridge (Main API)
# ---------------------------------------------------------------------------

class MetaAgentBridge:
    """Unified interface for loading and executing any supported external agent.

    This is the primary entry point for the meta-integration system. It handles
    agent discovery, installation, configuration, and execution across all
    supported agent frameworks.

    Example:
        >>> bridge = MetaAgentBridge(workspace="/tmp/agents")
        >>> result = bridge.execute("crewai", "Create a marketing plan",
        ...                         config={"OPENAI_API_KEY": "sk-xxx"})
        >>> print(result.output)
    """

    def __init__(self, workspace: Optional[Union[str, Path]] = None):
        """Initialize the bridge with a workspace directory.

        Args:
            workspace: Directory for agent installations. Defaults to tempfile.
        """
        if workspace is None:
            workspace = tempfile.mkdtemp(prefix="meta_agent_bridge_")
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._adapters: Dict[str, AgentAdapter] = {}
        self._registry = AgentRegistry()

    # -- Discovery ----------------------------------------------------------

    def list_agents(self) -> List[str]:
        """Return list of all supported agent names."""
        return self._registry.list_agents()

    def get_metadata(self, name: str) -> AgentMetadata:
        """Get metadata for a specific agent."""
        return self._registry.get_metadata(name)

    def get_all_metadata(self) -> Dict[str, AgentMetadata]:
        """Get metadata for all agents."""
        return self._registry.get_all_metadata()

    def find_agents(
        self,
        language: Optional[str] = None,
        license_name: Optional[str] = None,
        min_stars: Optional[int] = None,
    ) -> List[AgentMetadata]:
        """Find agents matching criteria."""
        results = list(self._registry.get_all_metadata().values())
        if language:
            results = [a for a in results if a.primary_language == language.lower()]
        if license_name:
            results = [a for a in results if license_name.lower() in a.license.lower()]
        if min_stars:
            results = [a for a in results if a.github_stars >= min_stars]
        return results

    # -- Lifecycle Management -----------------------------------------------

    def load_agent(self, name: str, auto_install: bool = True) -> AgentAdapter:
        """Load an agent by name, returning its adapter.

        Args:
            name: Agent name (e.g., 'crewai', 'elizaos')
            auto_install: Whether to automatically install if not present

        Returns:
            Configured AgentAdapter instance
        """
        key = name.lower()
        if key in self._adapters:
            return self._adapters[key]

        metadata = self._registry.get_metadata(name)
        adapter = AdapterFactory.create_adapter(metadata, self.workspace)

        if auto_install and adapter.status == AgentStatus.NOT_INSTALLED:
            adapter.install()

        self._adapters[key] = adapter
        return adapter

    def configure_agent(self, name: str, config: Dict[str, Any]) -> None:
        """Configure an agent with settings."""
        adapter = self.load_agent(name)
        adapter.configure(config)

    def health_check(self, name: str) -> bool:
        """Check if an agent is healthy and ready."""
        try:
            adapter = self.load_agent(name, auto_install=False)
            return adapter.health_check()
        except Exception as e:
            logger.error("Health check failed for %s: %s", name, e)
            return False

    # -- Execution ----------------------------------------------------------

    def execute(
        self,
        agent_name: str,
        task: str,
        config: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        """Execute a task using a specific agent.

        Args:
            agent_name: Name of the agent to use
            task: Task description or command
            config: Optional configuration to apply before execution
            **kwargs: Additional arguments passed to the agent adapter

        Returns:
            ExecutionResult with standardized output
        """
        adapter = self.load_agent(agent_name)
        if config:
            adapter.configure(config)
        return adapter.execute(task, **kwargs)

    def execute_multi(
        self,
        agent_tasks: Dict[str, str],
        shared_config: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, ExecutionResult]:
        """Execute tasks across multiple agents in sequence.

        Args:
            agent_tasks: Dict mapping agent names to task descriptions
            shared_config: Configuration applied to all agents
            **kwargs: Additional arguments

        Returns:
            Dict mapping agent names to ExecutionResults
        """
        results: Dict[str, ExecutionResult] = {}
        for agent_name, task in agent_tasks.items():
            try:
                result = self.execute(agent_name, task, config=shared_config, **kwargs)
                results[agent_name] = result
            except Exception as e:
                results[agent_name] = ExecutionResult(
                    success=False,
                    agent_name=agent_name,
                    output=str(e),
                    logs=[str(e)],
                )
        return results

    def chain_execute(
        self,
        chain: List[Dict[str, Any]],
        shared_config: Optional[Dict[str, Any]] = None,
    ) -> List[ExecutionResult]:
        """Execute a chain of agent tasks, passing output between steps.

        Args:
            chain: List of dicts with keys: 'agent', 'task', 'config' (optional)
            shared_config: Base configuration for all steps

        Returns:
            List of ExecutionResults in execution order
        """
        results: List[ExecutionResult] = []
        context = ""
        for step in chain:
            agent_name = step["agent"]
            task = step["task"]
            if context:
                task = f"{task}\n\nPrevious context:\n{context}"

            step_config = {**(shared_config or {}), **step.get("config", {})}
            result = self.execute(agent_name, task, config=step_config)
            results.append(result)

            if result.success:
                context = str(result.output)[:2000]  # Limit context size
            else:
                context = f"Error: {result.output}"
        return results

    # -- Cleanup ------------------------------------------------------------

    def unload_agent(self, name: str) -> None:
        """Unload an agent and clean up resources."""
        key = name.lower()
        if key in self._adapters:
            self._adapters[key].teardown()
            del self._adapters[key]

    def unload_all(self) -> None:
        """Unload all agents and clean up."""
        for adapter in list(self._adapters.values()):
            adapter.teardown()
        self._adapters.clear()

    def cleanup_workspace(self) -> None:
        """Remove the workspace directory and all installed agents."""
        self.unload_all()
        if self.workspace.exists():
            shutil.rmtree(self.workspace)
            logger.info("Cleaned up workspace: %s", self.workspace)

    # -- Plugin / Skill Integration -----------------------------------------

    def get_claude_skill_command(self, agent_name: str) -> Optional[str]:
        """Get the Claude Code skill installation command for an agent.

        Args:
            agent_name: Name of the agent

        Returns:
            CLI command string or None if not available
        """
        metadata = self._registry.get_metadata(agent_name)
        if metadata.plugin_name:
            return f"/plugin install {metadata.plugin_name}"
        return None

    def get_mcp_server_command(self, agent_name: str) -> Optional[str]:
        """Get the MCP server add command for an agent.

        Args:
            agent_name: Name of the agent

        Returns:
            MCP server add command or None
        """
        metadata = self._registry.get_metadata(agent_name)
        entry = metadata.entry_points.get("mcp")
        if entry:
            return entry
        # Generate default MCP command for supported agents
        if metadata.name == "ruflo":
            return "claude mcp add ruflo -- npx -y @claude-flow/cli@latest"
        return None

    def install_as_claude_skill(self, agent_name: str) -> ExecutionResult:
        """Install an agent as a Claude Code skill.

        Args:
            agent_name: Name of the agent to install

        Returns:
            ExecutionResult indicating success/failure
        """
        import time
        start = time.time()

        cmd = self.get_claude_skill_command(agent_name)
        if not cmd:
            return ExecutionResult(
                success=False,
                agent_name=agent_name,
                output=f"No Claude skill available for {agent_name}",
                metadata={"available_skills": [a.plugin_name for a in self._registry.get_all_metadata().values() if a.plugin_name]},
            )

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            duration = (time.time() - start) * 1000
            return ExecutionResult(
                success=result.returncode == 0,
                agent_name=agent_name,
                output=result.stdout or result.stderr,
                logs=[result.stdout, result.stderr] if result.stderr else [result.stdout],
                duration_ms=duration,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                agent_name=agent_name,
                output=str(e),
                logs=[str(e)],
            )

    # -- Reporting ----------------------------------------------------------

    def generate_report(self) -> Dict[str, Any]:
        """Generate a comprehensive status report of all agents."""
        report: Dict[str, Any] = {
            "workspace": str(self.workspace),
            "total_agents_supported": len(self.list_agents()),
            "agents_loaded": list(self._adapters.keys()),
            "agent_statuses": {},
            "metadata": {},
        }

        for name in self.list_agents():
            metadata = self._registry.get_metadata(name)
            adapter = self._adapters.get(name)
            report["agent_statuses"][name] = {
                "status": adapter.status.value if adapter else "not_loaded",
                "stars": metadata.github_stars,
                "language": metadata.primary_language,
                "license": metadata.license,
                "archived": metadata.is_archived,
                "has_claude_skill": metadata.plugin_name is not None,
            }
            report["metadata"][name] = {
                "repo_url": metadata.repo_url,
                "description": metadata.description,
                "dependencies": metadata.dependencies,
                "env_vars": metadata.env_vars,
                "entry_points": metadata.entry_points,
            }

        return report

    def print_report(self) -> None:
        """Print a human-readable status report."""
        report = self.generate_report()
        print("\n" + "=" * 60)
        print("  META AGENT BRIDGE - STATUS REPORT")
        print("=" * 60)
        print(f"Workspace: {report['workspace']}")
        print(f"Supported Agents: {report['total_agents_supported']}")
        print(f"Loaded Agents: {len(report['agents_loaded'])}")
        print("-" * 60)
        for name, status in report["agent_statuses"].items():
            skill_icon = "🔌" if status["has_claude_skill"] else "  "
            archived_icon = "📦" if status["archived"] else "  "
            print(f"\n{skill_icon}{archived_icon} {name}")
            print(f"   Status: {status['status']}")
            print(f"   Stars:  {status['stars']:,}")
            print(f"   Lang:   {status['language']}")
            print(f"   License: {status['license']}")
        print("\n" + "=" * 60)


# ---------------------------------------------------------------------------
# CLI Interface
# ---------------------------------------------------------------------------

def main():
    """Command-line interface for the Meta Agent Bridge."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Meta-Agent Bridge: Universal adapter for AI agent frameworks"
    )
    parser.add_argument("--workspace", "-w", help="Workspace directory for installations")
    parser.add_argument("--list", "-l", action="store_true", help="List all supported agents")
    parser.add_argument("--info", "-i", help="Show info for a specific agent")
    parser.add_argument("--execute", "-e", nargs=2, metavar=("AGENT", "TASK"), help="Execute a task")
    parser.add_argument("--config", "-c", help="JSON configuration string")
    parser.add_argument("--install-skill", help="Install agent as Claude skill")
    parser.add_argument("--report", action="store_true", help="Generate status report")
    parser.add_argument("--health", help="Health check an agent")

    args = parser.parse_args()

    bridge = MetaAgentBridge(workspace=args.workspace)

    if args.list:
        print("\nSupported Agents:")
        print("-" * 40)
        for name in bridge.list_agents():
            meta = bridge.get_metadata(name)
            archived = " [ARCHIVED]" if meta.is_archived else ""
            print(f"  {name:20s} - {meta.github_stars:,} stars{archived}")
        print()

    elif args.info:
        meta = bridge.get_metadata(args.info)
        print(f"\n{'='*50}")
        print(f"Agent: {meta.name}")
        print(f"Stars: {meta.github_stars:,}")
        print(f"Language: {meta.primary_language}")
        print(f"License: {meta.license}")
        print(f"Repository: {meta.repo_url}")
        print(f"Description: {meta.description}")
        print(f"Dependencies: {', '.join(meta.dependencies)}")
        print(f"Env Vars: {', '.join(meta.env_vars)}")
        print(f"Entry Points: {meta.entry_points}")
        if meta.plugin_name:
            print(f"Claude Skill: {meta.plugin_name}")
        print(f"{'='*50}\n")

    elif args.execute:
        agent_name, task = args.execute
        config = {}
        if args.config:
            config = json.loads(args.config)
        result = bridge.execute(agent_name, task, config=config)
        print(result.to_json())

    elif args.install_skill:
        result = bridge.install_as_claude_skill(args.install_skill)
        print(result.to_json())

    elif args.report:
        bridge.print_report()

    elif args.health:
        healthy = bridge.health_check(args.health)
        print(f"Health check for '{args.health}': {'✅ PASS' if healthy else '❌ FAIL'}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
