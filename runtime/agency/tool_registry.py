"""MCP-style tool registry.

Functions registered via `@tool` get their parameters introspected from
type hints and exposed via `openai_schema()` for function-calling. The
registry is process-singleton; helpers below provide module-level access.
"""

from __future__ import annotations

import inspect
import threading
import typing
from dataclasses import dataclass, field
from typing import Any, Callable, get_args, get_origin

from .logging import get_logger

log = get_logger()


_PY_TO_JSON: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
    type(None): "null",
}


def _json_type_for(py_type: Any) -> str:
    if py_type is inspect.Parameter.empty:
        return "string"
    origin = get_origin(py_type)
    if origin in (list, tuple, set, frozenset):
        return "array"
    if origin is dict:
        return "object"
    if origin is typing.Union or (hasattr(typing, "UnionType") and isinstance(py_type, typing.UnionType)):  # type: ignore[attr-defined]
        # Optional[X] / X | None — pick first non-None
        args = [a for a in get_args(py_type) if a is not type(None)]
        if args:
            return _json_type_for(args[0])
        return "string"
    return _PY_TO_JSON.get(py_type, "string")


@dataclass
class ToolParameter:
    """One parameter on a tool."""

    name: str
    type: str
    description: str = ""
    required: bool = True
    default: Any = None

    def to_schema(self) -> dict[str, Any]:
        s: dict[str, Any] = {"type": self.type}
        if self.description:
            s["description"] = self.description
        if self.default is not None and not self.required:
            s["default"] = self.default
        return s


@dataclass
class Tool:
    """A registered tool."""

    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    fn: Callable | None = None
    schema: dict[str, Any] = field(default_factory=dict)

    def to_openai_schema(self) -> dict[str, Any]:
        properties = {p.name: p.to_schema() for p in self.parameters}
        required = [p.name for p in self.parameters if p.required]
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


class ToolRegistry:
    """Process-wide registry of callable tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._lock = threading.RLock()

    def tool(
        self,
        name: str | None = None,
        description: str | None = None,
    ) -> Callable:
        """Decorator that registers a function as a tool."""

        def decorator(fn: Callable) -> Callable:
            self.register(fn, name=name, description=description)
            return fn

        return decorator

    def register(
        self,
        fn: Callable,
        name: str | None = None,
        description: str | None = None,
        parameters: list[ToolParameter] | None = None,
    ) -> Tool:
        tool_name = name or fn.__name__
        tool_desc = description or (inspect.getdoc(fn) or "").strip().split("\n")[0] or tool_name
        if parameters is None:
            parameters = self._introspect(fn)
        tool = Tool(
            name=tool_name,
            description=tool_desc,
            parameters=parameters,
            fn=fn,
        )
        tool.schema = tool.to_openai_schema()
        with self._lock:
            self._tools[tool_name] = tool
        return tool

    @staticmethod
    def _introspect(fn: Callable) -> list[ToolParameter]:
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            return []
        try:
            hints = typing.get_type_hints(fn)
        except Exception:
            hints = {}
        out: list[ToolParameter] = []
        for pname, p in sig.parameters.items():
            if pname in {"self", "cls"} or p.kind in {
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            }:
                continue
            ann = hints.get(pname, p.annotation)
            jt = _json_type_for(ann)
            required = p.default is inspect.Parameter.empty
            default = None if required else p.default
            out.append(
                ToolParameter(
                    name=pname,
                    type=jt,
                    required=required,
                    default=default,
                )
            )
        return out

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def openai_schema(self) -> list[dict[str, Any]]:
        return [t.to_openai_schema() for t in self._tools.values()]

    def execute(self, name: str, **kwargs) -> Any:
        tool = self.get(name)
        if tool is None or tool.fn is None:
            raise KeyError(f"unknown tool: {name}")
        return tool.fn(**kwargs)

    def unregister(self, name: str) -> bool:
        with self._lock:
            return self._tools.pop(name, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._tools.clear()


_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def tool(name: str | None = None, description: str | None = None) -> Callable:
    """Module-level decorator using the singleton registry."""
    return get_registry().tool(name=name, description=description)


__all__ = [
    "ToolParameter",
    "Tool",
    "ToolRegistry",
    "get_registry",
    "tool",
]
