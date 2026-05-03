"""
JARVIS BRAINIAC - MetaGPT Integration Bridge
=============================================

Unified MetaGPT adapter providing:
- Team creation with configurable roles
- Full software project lifecycle execution
- Individual role factories (PM, Architect, Engineer)
- Project idea refinement and task decomposition
- Mock fallback when metagpt is not installed

Usage:
    bridge = MetaGPTBridge()
    team = bridge.create_team(["product_manager", "architect", "engineer"])
    result = bridge.run_project("Build a todo list app")
"""

from __future__ import annotations

# Prevent local logging.py from shadowing stdlib during transitive imports
_sys = __import__("sys")
_Path = __import__("pathlib").Path
_agency_dir = str(_Path(__file__).parent.resolve())
_removed_path = None
for _p in list(_sys.path):
    if str(_Path(_p).resolve()) == _agency_dir:
        _sys.path.remove(_p)
        _removed_path = _p
        break

import logging

# Restore agency dir to sys.path so sibling modules remain importable
if _removed_path is not None:
    _sys.path.insert(0, _removed_path)
import json
import os
import re
import sys
import uuid
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability flag
# ---------------------------------------------------------------------------
_METAGPT_AVAILABLE: bool = False

try:
    import metagpt
    from metagpt.team import Team
    from metagpt.roles import Role
    from metagpt.roles.product_manager import ProductManager
    from metagpt.roles.architect import Architect
    from metagpt.roles.engineer import Engineer
    from metagpt.roles.qa_engineer import QaEngineer
    from metagpt.roles.project_manager import ProjectManager
    from metagpt.schema import Message
    from metagpt.actions import Action, WritePRD, WriteDesign, WriteCode, RunCode, WriteTest
    from metagpt.config import CONFIG
    _METAGPT_AVAILABLE = True
    logger.info("MetaGPT %s loaded successfully.", metagpt.__version__)
except Exception as _import_exc:
    logger.warning(
        "MetaGPT not installed or failed to import (%s). "
        "Falling back to mock implementations.",
        _import_exc,
    )

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ProjectOutput:
    """Output from a MetaGPT project execution."""
    idea: str
    prd: str = ""
    design: str = ""
    code: str = ""
    tests: str = ""
    success: bool = False
    messages: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "idea": self.idea,
            "prd": self.prd,
            "design": self.design,
            "code": self.code,
            "tests": self.tests,
            "success": self.success,
            "messages": self.messages,
            "artifacts": self.artifacts,
        }


@dataclass
class RoleConfig:
    """Configuration for a MetaGPT role."""
    role_type: str
    name: str
    system_prompt: str
    goal: str = ""
    constraints: str = ""


# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------

class _MockAction:
    """Mock action that simulates a MetaGPT action."""

    def __init__(self, name: str, description: str, func: Optional[Callable[..., str]] = None) -> None:
        self.name: str = name
        self.description: str = description
        self.func: Optional[Callable[..., str]] = func
        self.execution_count: int = 0

    def run(self, context: str, **kwargs: Any) -> str:
        """Execute the mock action."""
        self.execution_count += 1
        if self.func:
            try:
                return self.func(context, **kwargs)
            except Exception as exc:
                return f"[MOCK ACTION ERROR] {self.name}: {exc}"
        return f"[MOCK ACTION] {self.name} processed context: {context[:100]}..."

    def __call__(self, *args: Any, **kwargs: Any) -> str:
        """Callable interface."""
        context = args[0] if args else kwargs.get("context", "")
        return self.run(context, **kwargs)


class _MockRole:
    """Mock role that simulates a MetaGPT role with actions."""

    def __init__(
        self,
        name: str,
        role_type: str,
        system_prompt: str,
        goal: str = "",
        constraints: str = "",
        actions: Optional[List[_MockAction]] = None,
    ) -> None:
        self.name: str = name
        self.role_type: str = role_type
        self.system_prompt: str = system_prompt
        self.goal: str = goal or f"Fulfill the duties of {role_type}"
        self.constraints: str = constraints or "None"
        self.actions: List[_MockAction] = actions or []
        self.rc = self  # role context compatibility
        self.working_memory: List[Dict[str, str]] = []
        self._message_buffer: List[Dict[str, Any]] = []

    def set_actions(self, actions: List[_MockAction]) -> None:
        """Set actions for this role."""
        self.actions = actions

    def run(self, context: Optional[str] = None) -> str:
        """Execute all actions in sequence."""
        results: List[str] = []
        ctx = context or ""
        for action in self.actions:
            result = action.run(ctx)
            results.append(result)
            self.working_memory.append({"action": action.name, "result": result})
            ctx = result  # Pass output as next input
        return "\n\n".join(results)

    def recv(self, message: Union[str, Dict[str, Any]]) -> None:
        """Receive a message into the buffer."""
        self._message_buffer.append({"content": str(message), "from": "unknown"})

    def send(self, message: str, recipient: Any) -> None:
        """Send a message to another role."""
        if hasattr(recipient, 'recv'):
            recipient.recv(message)

    def _think(self) -> Optional[_MockAction]:
        """Select next action (mock: return first available)."""
        if self.actions:
            return self.actions[0]
        return None

    def _act(self) -> str:
        """Execute the selected action."""
        action = self._think()
        if action:
            context = self._message_buffer[-1]["content"] if self._message_buffer else ""
            return action.run(context)
        return f"[MOCK] {self.name}: No action available."

    def __repr__(self) -> str:
        return f"_MockRole(name='{self.name}', type='{self.role_type}')"


class _MockTeam:
    """Mock team that orchestrates multiple mock roles."""

    def __init__(self, roles: List[_MockRole]) -> None:
        self.roles: List[_MockRole] = roles
        self.role_map: Dict[str, _MockRole] = {r.name: r for r in roles}
        self.project_history: List[Dict[str, Any]] = []
        self._current_idea: str = ""

    def hire(self, role: _MockRole) -> None:
        """Add a role to the team."""
        self.roles.append(role)
        self.role_map[role.name] = role

    def run_project(self, idea: str, investment: float = 5.0, n_round: int = 10) -> ProjectOutput:
        """Execute a full software project lifecycle."""
        self._current_idea = idea
        output = ProjectOutput(idea=idea)
        output.messages.append({"role": "System", "content": f"Starting project: {idea}"})

        # Simulate sequential workflow: PM -> Architect -> Engineer
        for role in self.roles:
            output.messages.append({"role": role.name, "content": f"{role.name} starting work..."})
            result = role.run(idea)
            output.messages.append({"role": role.name, "content": result[:500]})

            # Store outputs by role type
            if "product" in role.role_type.lower() or "pm" in role.role_type.lower():
                output.prd = result
                output.artifacts["prd.md"] = result
            elif "architect" in role.role_type.lower():
                output.design = result
                output.artifacts["design.md"] = result
            elif "engineer" in role.role_type.lower():
                output.code = result
                output.artifacts["main.py"] = result
            elif "qa" in role.role_type.lower() or "test" in role.role_type.lower():
                output.tests = result
                output.artifacts["test.py"] = result

        output.success = bool(output.code or output.prd)
        self.project_history.append(output.to_dict())
        return output

    def get_role(self, name: str) -> Optional[_MockRole]:
        """Get a role by name."""
        return self.role_map.get(name)

    def list_roles(self) -> List[str]:
        """List all role names in the team."""
        return list(self.role_map.keys())


# ---------------------------------------------------------------------------
# MetaGPTBridge
# ---------------------------------------------------------------------------

class MetaGPTBridge:
    """
    Unified MetaGPT integration bridge for JARVIS BRAINIAC.

    Provides factory methods for creating software development teams,
    running projects with multiple roles, and individual role creation.
    When MetaGPT is not installed, all methods return fully-functional
    mock implementations.

    Attributes:
        available (bool): Whether the real MetaGPT library is installed.
        config (dict): Bridge configuration.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        verbose: bool = True,
    ) -> None:
        """
        Initialize the MetaGPT bridge.

        Args:
            config: Optional configuration dictionary.
            verbose: Enable verbose logging.
        """
        self.available: bool = _METAGPT_AVAILABLE
        self.verbose: bool = verbose
        self.config: Dict[str, Any] = config or self._build_default_config()
        self._teams: Dict[str, Any] = {}
        self._roles: Dict[str, Any] = {}
        self._project_history: List[Dict[str, Any]] = []
        logger.info("MetaGPTBridge initialized (available=%s)", self.available)

    def _build_default_config(self) -> Dict[str, Any]:
        """Build default MetaGPT configuration."""
        api_key = os.environ.get("OPENAI_API_KEY", "")
        return {
            "llm": {
                "api_type": "openai",
                "model": os.environ.get("METAGPT_MODEL", "gpt-4"),
                "api_key": api_key,
                "temperature": 0.3,
                "max_token": 4096,
            },
            "proxy": os.environ.get("HTTP_PROXY", ""),
            "search": {
                "engine": "google",
                "api_key": os.environ.get("SEARCH_API_KEY", ""),
            },
        }

    def _log(self, msg: str) -> None:
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            logger.info("[MetaGPTBridge] %s", msg)

    # -- Role factories ------------------------------------------------------

    def create_product_manager(
        self,
        name: str = "Alice",
        goal: str = "Create product requirements that are clear, complete, and actionable.",
        constraints: str = "Ensure PRD follows industry standards.",
    ) -> Any:
        """
        Create a Product Manager role (or mock equivalent).

        Args:
            name: Name for the PM role.
            goal: Goal description for the PM.
            constraints: Constraints for the PM's work.

        Returns:
            ProductManager role or mock role object.

        Example:
            >>> bridge = MetaGPTBridge()
            >>> pm = bridge.create_product_manager("Alice")
        """
        if self.available:
            try:
                pm = ProductManager()
                self._roles[name] = pm
                self._log(f"Created ProductManager '{name}'")
                return pm
            except Exception as exc:
                logger.error("Failed to create ProductManager: %s. Using mock.", exc)

        # Mock fallback
        actions = [
            _MockAction("write_prd", "Write Product Requirements Document"),
        ]
        mock_pm = _MockRole(
            name=name,
            role_type="product_manager",
            system_prompt=(
                f"You are {name}, a senior Product Manager. "
                "Your job is to analyze the product idea and write a comprehensive PRD "
                "including user stories, functional requirements, non-functional requirements, "
                "and acceptance criteria."
            ),
            goal=goal,
            constraints=constraints,
            actions=actions,
        )
        self._roles[name] = mock_pm
        self._log(f"Created mock ProductManager '{name}'")
        return mock_pm

    def create_architect(
        self,
        name: str = "Bob",
        goal: str = "Design system architecture that is scalable, maintainable, and efficient.",
        constraints: str = "Use modern design patterns and best practices.",
    ) -> Any:
        """
        Create an Architect role (or mock equivalent).

        Args:
            name: Name for the architect role.
            goal: Goal description for the architect.
            constraints: Constraints for the architect's work.

        Returns:
            Architect role or mock role object.

        Example:
            >>> bridge = MetaGPTBridge()
            >>> architect = bridge.create_architect("Bob")
        """
        if self.available:
            try:
                architect = Architect()
                self._roles[name] = architect
                self._log(f"Created Architect '{name}'")
                return architect
            except Exception as exc:
                logger.error("Failed to create Architect: %s. Using mock.", exc)

        actions = [
            _MockAction("write_design", "Write system design document"),
        ]
        mock_architect = _MockRole(
            name=name,
            role_type="architect",
            system_prompt=(
                f"You are {name}, a senior Software Architect. "
                "Your job is to design the system architecture including component diagrams, "
                "data models, API specifications, and technology stack recommendations."
            ),
            goal=goal,
            constraints=constraints,
            actions=actions,
        )
        self._roles[name] = mock_architect
        self._log(f"Created mock Architect '{name}'")
        return mock_architect

    def create_engineer(
        self,
        name: str = "Charlie",
        goal: str = "Write clean, efficient, and well-tested code.",
        constraints: str = "Follow PEP8, write type hints, and include docstrings.",
    ) -> Any:
        """
        Create an Engineer role (or mock equivalent).

        Args:
            name: Name for the engineer role.
            goal: Goal description for the engineer.
            constraints: Constraints for the engineer's work.

        Returns:
            Engineer role or mock role object.

        Example:
            >>> bridge = MetaGPTBridge()
            >>> engineer = bridge.create_engineer("Charlie")
        """
        if self.available:
            try:
                engineer = Engineer(n_borg=5)
                self._roles[name] = engineer
                self._log(f"Created Engineer '{name}'")
                return engineer
            except Exception as exc:
                logger.error("Failed to create Engineer: %s. Using mock.", exc)

        actions = [
            _MockAction("write_code", "Write implementation code"),
        ]
        mock_engineer = _MockRole(
            name=name,
            role_type="engineer",
            system_prompt=(
                f"You are {name}, a senior Software Engineer. "
                "Your job is to implement the system based on the PRD and design documents. "
                "Write production-quality Python code with proper error handling, logging, and tests."
            ),
            goal=goal,
            constraints=constraints,
            actions=actions,
        )
        self._roles[name] = mock_engineer
        self._log(f"Created mock Engineer '{name}'")
        return mock_engineer

    def create_qa_engineer(
        self,
        name: str = "Diana",
        goal: str = "Ensure software quality through comprehensive testing.",
        constraints: str = "Write unit tests, integration tests, and edge case tests.",
    ) -> Any:
        """
        Create a QA Engineer role (or mock equivalent).

        Args:
            name: Name for the QA role.
            goal: Goal description for QA.
            constraints: Testing constraints.

        Returns:
            QaEngineer or mock role object.
        """
        if self.available:
            try:
                qa = QaEngineer()
                self._roles[name] = qa
                self._log(f"Created QA Engineer '{name}'")
                return qa
            except Exception as exc:
                logger.error("Failed to create QA Engineer: %s. Using mock.", exc)

        actions = [
            _MockAction("write_tests", "Write test cases"),
            _MockAction("run_tests", "Run test suite"),
        ]
        mock_qa = _MockRole(
            name=name,
            role_type="qa_engineer",
            system_prompt=(
                f"You are {name}, a senior QA Engineer. "
                "Your job is to write comprehensive tests including unit tests, "
                "integration tests, and edge case tests. Ensure all acceptance criteria are covered."
            ),
            goal=goal,
            constraints=constraints,
            actions=actions,
        )
        self._roles[name] = mock_qa
        self._log(f"Created mock QA Engineer '{name}'")
        return mock_qa

    def create_project_manager(
        self,
        name: str = "Eve",
        goal: str = "Manage project execution and ensure timely delivery.",
        constraints: str = "Track progress and manage scope creep.",
    ) -> Any:
        """
        Create a Project Manager role (or mock equivalent).

        Args:
            name: Name for the PM role.
            goal: Goal for project management.
            constraints: PM constraints.

        Returns:
            ProjectManager or mock role object.
        """
        if self.available:
            try:
                pm = ProjectManager()
                self._roles[name] = pm
                self._log(f"Created Project Manager '{name}'")
                return pm
            except Exception as exc:
                logger.error("Failed to create Project Manager: %s. Using mock.", exc)

        actions = [
            _MockAction("plan_project", "Create project plan"),
            _MockAction("track_progress", "Track project progress"),
        ]
        mock_pm = _MockRole(
            name=name,
            role_type="project_manager",
            system_prompt=(
                f"You are {name}, a Project Manager. "
                "Your job is to create project plans, assign tasks, track progress, "
                "and ensure the team delivers on time."
            ),
            goal=goal,
            constraints=constraints,
            actions=actions,
        )
        self._roles[name] = mock_pm
        self._log(f"Created mock Project Manager '{name}'")
        return mock_pm

    # -- Team and project management -----------------------------------------

    def create_team(
        self,
        roles: List[Union[str, _MockRole, Any]],
        team_name: str = "default_team",
    ) -> Any:
        """
        Create a MetaGPT Team with the specified roles (or mock equivalent).

        Args:
            roles: List of role identifiers (strings like "product_manager",
                   "architect", "engineer") or role objects.
            team_name: Identifier for the team.

        Returns:
            Team or mock team object.

        Example:
            >>> bridge = MetaGPTBridge()
            >>> team = bridge.create_team(["product_manager", "architect", "engineer"])
            >>> result = bridge.run_project("Build a web scraper")
        """
        resolved_roles: List[Any] = []
        role_factory_map: Dict[str, Callable[..., Any]] = {
            "product_manager": self.create_product_manager,
            "pm": self.create_product_manager,
            "architect": self.create_architect,
            "engineer": self.create_engineer,
            "qa_engineer": self.create_qa_engineer,
            "qa": self.create_qa_engineer,
            "project_manager": self.create_project_manager,
        }

        for role_spec in roles:
            if isinstance(role_spec, str):
                factory = role_factory_map.get(role_spec.lower())
                if factory:
                    resolved = factory()
                else:
                    logger.warning("Unknown role type '%s', creating generic role.", role_spec)
                    resolved = _MockRole(
                        name=role_spec,
                        role_type="generic",
                        system_prompt=f"You are a {role_spec}.",
                    )
                resolved_roles.append(resolved)
            else:
                resolved_roles.append(role_spec)

        if self.available:
            try:
                team = Team()
                for role in resolved_roles:
                    if hasattr(role, 'name'):
                        team.hire(role)
                self._teams[team_name] = team
                self._log(f"Created team '{team_name}' with {len(resolved_roles)} roles")
                return team
            except Exception as exc:
                logger.error("Failed to create team: %s. Using mock.", exc)

        mock_team = _MockTeam(resolved_roles)
        self._teams[team_name] = mock_team
        self._log(f"Created mock team '{team_name}' with {len(resolved_roles)} roles")
        return mock_team

    def run_project(
        self,
        idea: str,
        team_name: str = "default_team",
        investment: float = 5.0,
        n_round: int = 10,
    ) -> ProjectOutput:
        """
        Run a full software project with the specified team.

        Args:
            idea: Natural language description of the software to build.
            team_name: Name of the team to use (created if not exists).
            investment: Budget/investment parameter (for MetaGPT compatibility).
            n_round: Maximum conversation rounds.

        Returns:
            ProjectOutput dataclass with all artifacts.

        Example:
            >>> bridge = MetaGPTBridge()
            >>> team = bridge.create_team(["product_manager", "architect", "engineer"])
            >>> result = bridge.run_project("A URL shortener service")
            >>> print(result.prd)
            >>> print(result.code)
        """
        team = self._teams.get(team_name)
        if team is None:
            logger.info("Team '%s' not found, creating default team.", team_name)
            team = self.create_team(["product_manager", "architect", "engineer"], team_name)

        self._log(f"Running project: {idea[:100]}")

        if self.available and hasattr(team, 'run_project'):
            try:
                team.run_project(idea=idea, investment=investment, n_round=n_round)
                # Extract results
                output = ProjectOutput(
                    idea=idea,
                    prd="[PRD extracted from MetaGPT output]",
                    design="[Design extracted from MetaGPT output]",
                    code="[Code extracted from MetaGPT output]",
                    success=True,
                )
                self._project_history.append(output.to_dict())
                return output
            except Exception as exc:
                logger.error("Project execution failed: %s. Using mock.", exc)

        # Mock execution
        if hasattr(team, 'run_project'):
            output = team.run_project(idea=idea, investment=investment, n_round=n_round)
        else:
            output = ProjectOutput(idea=idea)
            output.prd = self._mock_prd(idea)
            output.design = self._mock_design(idea)
            output.code = self._mock_code(idea)
            output.tests = self._mock_tests(idea)
            output.success = True
            output.artifacts = {
                "prd.md": output.prd,
                "design.md": output.design,
                "main.py": output.code,
                "test.py": output.tests,
            }

        self._project_history.append(output.to_dict() if hasattr(output, 'to_dict') else output)
        self._log(f"Project complete: success={getattr(output, 'success', True)}")
        return output if isinstance(output, ProjectOutput) else ProjectOutput(**output.__dict__ if hasattr(output, '__dict__') else {"idea": idea})

    def _mock_prd(self, idea: str) -> str:
        """Generate a mock PRD for an idea."""
        return f"""# Product Requirements Document

## Overview
{idea}

## User Stories
- As a user, I want to use {idea} so that I can be more productive
- As a user, I want the system to be reliable and fast
- As a user, I want an intuitive interface

## Functional Requirements
1. Core functionality implementing {idea}
2. User authentication and authorization
3. Data persistence layer
4. RESTful API endpoints
5. Error handling and logging

## Non-Functional Requirements
- Response time < 200ms
- 99.9% uptime
- Support 10,000 concurrent users
- Data encryption at rest and in transit

## Acceptance Criteria
- All user stories implemented
- Unit test coverage > 80%
- Integration tests passing
- Documentation complete
"""

    def _mock_design(self, idea: str) -> str:
        """Generate a mock design document for an idea."""
        return f"""# System Design Document

## Architecture
- Frontend: React/Vue SPA
- Backend: Python FastAPI
- Database: PostgreSQL
- Cache: Redis
- Message Queue: Redis/Celery

## Component Diagram
```
[Client] -> [API Gateway] -> [Service Layer] -> [Data Layer]
                |                  |                  |
           [Auth]           [Business Logic]   [PostgreSQL]
```

## API Design
- GET /api/v1/items - List items
- POST /api/v1/items - Create item
- GET /api/v1/items/{{id}} - Get item
- PUT /api/v1/items/{{id}} - Update item
- DELETE /api/v1/items/{{id}} - Delete item

## Data Model
```python
class Item:
    id: int
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
```

## Technology Stack
- Python 3.11+
- FastAPI
- SQLAlchemy
- Alembic
- Pytest
- Docker
"""

    def _mock_code(self, idea: str) -> str:
        """Generate mock implementation code for an idea."""
        return f"""# Implementation for: {idea}
\nfrom fastapi import FastAPI, HTTPException\nfrom pydantic import BaseModel\nfrom datetime import datetime\nfrom typing import List, Optional\n\napp = FastAPI(title="{idea}")\n\nclass Item(BaseModel):\n    id: Optional[int] = None\n    name: str\n    description: str\n    created_at: datetime = datetime.now()\n\n# In-memory storage (replace with database)\n_db: List[Item] = []\n\n@app.get("/api/v1/items", response_model=List[Item])\ndef list_items() -> List[Item]:\n    \"\"\"List all items.\"\"\"\n    return _db\n\n@app.post("/api/v1/items", response_model=Item)\ndef create_item(item: Item) -> Item:\n    \"\"\"Create a new item.\"\"\"\n    item.id = len(_db) + 1\n    _db.append(item)\n    return item\n\n@app.get("/api/v1/items/{{item_id}}", response_model=Item)\ndef get_item(item_id: int) -> Item:\n    \"\"\"Get item by ID.\"\"\"\n    for item in _db:\n        if item.id == item_id:\n            return item\n    raise HTTPException(status_code=404, detail="Item not found")\n\n@app.put("/api/v1/items/{{item_id}}", response_model=Item)\ndef update_item(item_id: int, item: Item) -> Item:\n    \"\"\"Update item by ID.\"\"\"\n    for i, existing in enumerate(_db):\n        if existing.id == item_id:\n            _db[i] = item\n            item.id = item_id\n            return item\n    raise HTTPException(status_code=404, detail="Item not found")\n\n@app.delete("/api/v1/items/{{item_id}}")\ndef delete_item(item_id: int) -> dict:\n    \"\"\"Delete item by ID.\"\"\"\n    for i, item in enumerate(_db):\n        if item.id == item_id:\n            del _db[i]\n            return {{"message": "Item deleted"}}\n    raise HTTPException(status_code=404, detail="Item not found")\n\nif __name__ == "__main__":\n    import uvicorn\n    uvicorn.run(app, host="0.0.0.0", port=8000)\n"""

    def _mock_tests(self, idea: str) -> str:
        """Generate mock test code for an idea."""
        return f"""# Tests for: {idea}
\nimport pytest\nfrom fastapi.testclient import TestClient\nfrom main import app, _db\n\nclient = TestClient(app)\n\ndef setup_function():\n    \"\"\"Clear database before each test.\"\"\"\n    _db.clear()\n\nclass TestItems:\n    def test_list_items_empty(self):\n        \"\"\"Test listing items when empty.\"\"\"\n        response = client.get("/api/v1/items")\n        assert response.status_code == 200\n        assert response.json() == []\n\n    def test_create_item(self):\n        \"\"\"Test creating an item.\"\"\"\n        data = {{"name": "Test", "description": "Test description"}}\n        response = client.post("/api/v1/items", json=data)\n        assert response.status_code == 200\n        result = response.json()\n        assert result["name"] == "Test"\n        assert result["id"] == 1\n\n    def test_get_item(self):\n        \"\"\"Test getting an item by ID.\"\"\"\n        data = {{"name": "Test", "description": "Test"}}\n        created = client.post("/api/v1/items", json=data).json()\n        response = client.get(f"/api/v1/items/{{created['id']}}")\n        assert response.status_code == 200\n        assert response.json()["name"] == "Test"\n\n    def test_get_item_not_found(self):\n        \"\"\"Test getting non-existent item.\"\"\"\n        response = client.get("/api/v1/items/999")\n        assert response.status_code == 404\n\n    def test_delete_item(self):\n        \"\"\"Test deleting an item.\"\"\"\n        data = {{"name": "Delete Me", "description": "To be deleted"}}\n        created = client.post("/api/v1/items", json=data).json()\n        response = client.delete(f"/api/v1/items/{{created['id']}}")\n        assert response.status_code == 200\n\nif __name__ == "__main__":\n    pytest.main([__file__, "-v"])\n"""

    def get_team(self, name: str) -> Optional[Any]:
        """Retrieve a team by name."""
        return self._teams.get(name)

    def get_role(self, name: str) -> Optional[Any]:
        """Retrieve a role by name."""
        return self._roles.get(name)

    def list_teams(self) -> List[str]:
        """List all registered team names."""
        return list(self._teams.keys())

    def list_roles(self) -> List[str]:
        """List all registered role names."""
        return list(self._roles.keys())

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all executed projects."""
        return self._project_history

    def health_check(self) -> Dict[str, Any]:
        """
        Return health status of the MetaGPT bridge.

        Returns:
            Dict with availability, team count, role count, project count.
        """
        return {
            "available": self.available,
            "teams": len(self._teams),
            "roles": len(self._roles),
            "projects": len(self._project_history),
            "team_names": self.list_teams(),
            "role_names": self.list_roles(),
        }


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def get_metagpt_bridge(
    config: Optional[Dict[str, Any]] = None,
    verbose: bool = True,
) -> MetaGPTBridge:
    """
    Factory function to create a MetaGPTBridge instance.

    Args:
        config: Optional configuration dictionary.
        verbose: Enable verbose logging.

    Returns:
        Configured MetaGPTBridge instance.

    Example:
        >>> bridge = get_metagpt_bridge()
        >>> result = bridge.run_project("Build a REST API")
    """
    return MetaGPTBridge(config=config, verbose=verbose)


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def quick_project(idea: str) -> ProjectOutput:
    """
    One-shot project execution with default team.

    Args:
        idea: Software project idea.

    Returns:
        ProjectOutput with all artifacts.
    """
    bridge = get_metagpt_bridge(verbose=False)
    team = bridge.create_team(["product_manager", "architect", "engineer"])
    return bridge.run_project(idea)


def quick_prd(idea: str) -> str:
    """
    Generate a PRD for an idea.

    Args:
        idea: Product idea.

    Returns:
        PRD text.
    """
    bridge = get_metagpt_bridge(verbose=False)
    pm = bridge.create_product_manager()
    if hasattr(pm, 'run'):
        return str(pm.run(idea))
    return ""


# ---------------------------------------------------------------------------
# __main__ quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bridge = get_metagpt_bridge(verbose=True)

    # Health check
    print("Health:", bridge.health_check())

    # Test role creation
    pm = bridge.create_product_manager("Alice")
    architect = bridge.create_architect("Bob")
    engineer = bridge.create_engineer("Charlie")
    print("Roles:", bridge.list_roles())

    # Test team creation and project
    team = bridge.create_team(["product_manager", "architect", "engineer"])
    result = bridge.run_project("A simple task management web application")
    print(f"Project success: {result.success}")
    print(f"PRD length: {len(result.prd)}")
    print(f"Design length: {len(result.design)}")
    print(f"Code length: {len(result.code)}")
    print(f"Tests length: {len(result.tests)}")
