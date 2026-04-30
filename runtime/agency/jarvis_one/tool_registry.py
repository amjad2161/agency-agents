"""Tool registry — inspired by MCP (Model Context Protocol).

Discoverable, typed, name-spaced tool registry. Each tool exposes a JSON
schema for its parameters and a callable for execution. Compatible with
the MCP ``tools/list`` + ``tools/call`` shape at the JSON surface.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Any]
    namespace: str = "default"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "description": self.description,
            "parameters": dict(self.parameters),
        }


class ToolRegistry:
    """Name-spaced tool index with MCP-shaped invocation."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    # ------------------------------------------------------------------
    def register(self, name: str, *, description: str = "",
                 parameters: dict[str, Any] | None = None,
                 namespace: str = "default") -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
            params = parameters or self._infer_params(fn)
            self._tools[f"{namespace}/{name}"] = ToolSpec(
                name=name, description=description or (fn.__doc__ or "").strip(),
                parameters=params, handler=fn, namespace=namespace,
            )
            return fn
        return _wrap

    def list_tools(self, *, namespace: str | None = None) -> list[dict[str, Any]]:
        items = [t.to_dict() for k, t in self._tools.items()
                 if namespace is None or t.namespace == namespace]
        items.sort(key=lambda t: (t["namespace"], t["name"]))
        return items

    def call(self, qualified_name: str, **kwargs: Any) -> Any:
        if "/" not in qualified_name:
            qualified_name = f"default/{qualified_name}"
        if qualified_name not in self._tools:
            raise KeyError(f"unknown tool: {qualified_name!r}")
        return self._tools[qualified_name].handler(**kwargs)

    # ------------------------------------------------------------------
    @staticmethod
    def _infer_params(fn: Callable[..., Any]) -> dict[str, Any]:
        try:
            hints = inspect.get_annotations(fn, eval_str=True)
        except Exception:
            hints = getattr(fn, "__annotations__", {}) or {}
        sig = inspect.signature(fn)
        type_map = {int: "integer", float: "number", bool: "boolean",
                    list: "array", tuple: "array", dict: "object", str: "string"}
        name_map = {"int": "integer", "float": "number", "bool": "boolean",
                    "list": "array", "tuple": "array", "dict": "object",
                    "str": "string"}
        props: dict[str, Any] = {}
        required: list[str] = []
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            ann = hints.get(name, param.annotation)
            if isinstance(ann, type):
                ptype = type_map.get(ann, "string")
            elif isinstance(ann, str):
                ptype = name_map.get(ann, "string")
            else:
                ptype = "string"
            props[name] = {"type": ptype}
            if param.default is inspect.Parameter.empty:
                required.append(name)
        return {"type": "object", "properties": props, "required": required}
