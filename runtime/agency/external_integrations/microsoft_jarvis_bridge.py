#!/usr/bin/env python3
"""
Microsoft JARVIS (HuggingGPT) Integration Adapter
=================================================

Bridge module for integrating Microsoft JARVIS capabilities into the JARVIS runtime.
Provides interfaces for task planning, model selection, task execution, and response
generation using the HuggingGPT four-stage pipeline architecture.

Repository: https://github.com/microsoft/JARVIS
Paper: https://arxiv.org/abs/2303.17580

This adapter implements:
  - Task planning via LLM-based dependency graph generation
  - HuggingFace model discovery and selection
  - Multi-modal task execution (local + remote inference)
  - Response synthesis from execution traces
  - TaskBench DAG-based evaluation primitives
  - EasyTool unified tool instruction formatting

Author: JARVIS Runtime Agency
Version: 1.0.0
"""

from __future__ import annotations

import abc
import asyncio
import base64
import io
import json
import logging
import os
import re
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Coroutine,
    Dict,
    Generic,
    List,
    Literal,
    Optional,
    Protocol,
    Tuple,
    TypeVar,
    Union,
)

import aiohttp
import yaml

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ---------------------------------------------------------------------------
# Enums & Constants
# ---------------------------------------------------------------------------


class InferenceMode(str, Enum):
    """Inference endpoint strategy."""

    LOCAL = "local"
    HUGGINGFACE = "huggingface"
    HYBRID = "hybrid"


class DeploymentScale(str, Enum):
    """Local model deployment scale."""

    MINIMAL = "minimal"
    STANDARD = "standard"
    FULL = "full"


class TaskType(str, Enum):
    """Supported HuggingFace task types in JARVIS."""

    # NLP
    TOKEN_CLASSIFICATION = "token-classification"
    TEXT2TEXT_GENERATION = "text2text-generation"
    SUMMARIZATION = "summarization"
    TRANSLATION = "translation"
    QUESTION_ANSWERING = "question-answering"
    CONVERSATIONAL = "conversational"
    TEXT_GENERATION = "text-generation"
    SENTENCE_SIMILARITY = "sentence-similarity"
    TABULAR_CLASSIFICATION = "tabular-classification"

    # Computer Vision
    OBJECT_DETECTION = "object-detection"
    IMAGE_CLASSIFICATION = "image-classification"
    IMAGE_TO_IMAGE = "image-to-image"
    IMAGE_TO_TEXT = "image-to-text"
    TEXT_TO_IMAGE = "text-to-image"
    TEXT_TO_VIDEO = "text-to-video"
    VISUAL_QUESTION_ANSWERING = "visual-question-answering"
    DOCUMENT_QUESTION_ANSWERING = "document-question-answering"
    IMAGE_SEGMENTATION = "image-segmentation"
    DEPTH_ESTIMATION = "depth-estimation"

    # Audio
    TEXT_TO_SPEECH = "text-to-speech"
    AUTOMATIC_SPEECH_RECOGNITION = "automatic-speech-recognition"
    AUDIO_TO_AUDIO = "audio-to-audio"
    AUDIO_CLASSIFICATION = "audio-classification"

    # ControlNet
    CANNY_CONTROL = "canny-control"
    HED_CONTROL = "hed-control"
    MLSD_CONTROL = "mlsd-control"
    NORMAL_CONTROL = "normal-control"
    OPENPOSE_CONTROL = "openpose-control"
    CANNY_TEXT_TO_IMAGE = "canny-text-to-image"
    DEPTH_TEXT_TO_IMAGE = "depth-text-to-image"
    HED_TEXT_TO_IMAGE = "hed-text-to-image"
    MLSD_TEXT_TO_IMAGE = "mlsd-text-to-image"
    NORMAL_TEXT_TO_IMAGE = "normal-text-to-image"
    OPENPOSE_TEXT_TO_IMAGE = "openpose-text-to-image"
    SEG_TEXT_TO_IMAGE = "seg-text-to-image"


# All task types as a set for fast membership checks
ALL_TASK_TYPES: set[str] = {t.value for t in TaskType}


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class TaskPlan:
    """A single parsed task from Stage 1 (Task Planning)."""

    task: str
    id: int
    dep: List[int]
    args: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {"task": self.task, "id": self.id, "dep": self.dep, "args": self.args}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskPlan:
        return cls(
            task=data["task"],
            id=data["id"],
            dep=data.get("dep", []),
            args=data.get("args", {}),
        )


@dataclass
class ModelSelection:
    """Model choice from Stage 2 (Model Selection)."""

    task_id: int
    model_id: str
    reason: str
    endpoint: Optional[str] = None  # URL if remote, None if local

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "model_id": self.model_id,
            "reason": self.reason,
            "endpoint": self.endpoint,
        }


@dataclass
class ExecutionResult:
    """Result from Stage 3 (Task Execution)."""

    task_id: int
    model_id: str
    status: Literal["success", "error", "skipped"]
    output: Any = None
    output_type: Literal["text", "image", "audio", "video", "binary"] = "text"
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "model_id": self.model_id,
            "status": self.status,
            "output": self._serialize_output(),
            "output_type": self.output_type,
            "error_message": self.error_message,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata,
        }

    def _serialize_output(self) -> Any:
        if self.output_type in ("image", "audio", "video", "binary") and isinstance(
            self.output, bytes
        ):
            return base64.b64encode(self.output).decode("utf-8")
        return self.output


@dataclass
class HuggingGPTResult:
    """Complete result from the HuggingGPT pipeline."""

    request_id: str
    task_plans: List[TaskPlan]
    model_selections: List[ModelSelection]
    execution_results: List[ExecutionResult]
    response: str
    total_execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "task_plans": [t.to_dict() for t in self.task_plans],
            "model_selections": [m.to_dict() for m in self.model_selections],
            "execution_results": [e.to_dict() for e in self.execution_results],
            "response": self.response,
            "total_execution_time_ms": self.total_execution_time_ms,
            "metadata": self.metadata,
        }


@dataclass
class ToolInstruction:
    """Unified tool instruction (EasyTool format)."""

    tool_name: str
    description: str
    parameters: List[Dict[str, Any]]
    required_params: List[str]
    examples: List[Dict[str, Any]] = field(default_factory=list)
    api_endpoint: Optional[str] = None
    method: Optional[str] = None

    def to_markdown(self) -> str:
        """Render as concise Markdown instruction."""
        lines = [
            f"## {self.tool_name}",
            f"{self.description}",
            "",
            "### Parameters",
        ]
        for param in self.parameters:
            req_flag = " (required)" if param["name"] in self.required_params else ""
            lines.append(f"- `{param['name']}`{req_flag}: {param.get('type', 'any')} - {param.get('description', '')}")
        if self.examples:
            lines.extend(["", "### Examples"])
            for ex in self.examples:
                lines.append(f"```json\n{json.dumps(ex, indent=2, ensure_ascii=False)}\n```")
        return "\n".join(lines)


@dataclass
class TaskGraphNode:
    """Node in a TaskBench dependency graph."""

    node_id: str
    tool_name: str
    parameters: Dict[str, Any]
    expected_output_type: str = "text"


@dataclass
class TaskGraphEdge:
    """Edge in a TaskBench dependency graph (resource dependency)."""

    source: str
    target: str
    resource_type: Literal["text", "image", "audio", "video"]
    mapping: Dict[str, str]  # target_param -> source_output_field


@dataclass
class TaskGraph:
    """TaskBench DAG representation."""

    graph_id: str
    nodes: List[TaskGraphNode]
    edges: List[TaskGraphEdge]
    domain: str = "general"

    def topological_order(self) -> List[str]:
        """Return node IDs in topological execution order."""
        in_degree: Dict[str, int] = {n.node_id: 0 for n in self.nodes}
        adj: Dict[str, List[str]] = {n.node_id: [] for n in self.nodes}
        for edge in self.edges:
            adj[edge.source].append(edge.target)
            in_degree[edge.target] += 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        order: List[str] = []
        while queue:
            nid = queue.pop(0)
            order.append(nid)
            for neighbor in adj[nid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        if len(order) != len(self.nodes):
            raise ValueError("Task graph contains cycles")
        return order

    def to_networkx_dict(self) -> Dict[str, Any]:
        """Export to NetworkX-compatible adjacency dict."""
        return {
            "graph_id": self.graph_id,
            "nodes": [
                {"id": n.node_id, "tool": n.tool_name, "params": n.parameters}
                for n in self.nodes
            ],
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "resource_type": e.resource_type,
                    "mapping": e.mapping,
                }
                for e in self.edges
            ],
            "domain": self.domain,
        }


# ---------------------------------------------------------------------------
# Abstract Interfaces (Ports)
# ---------------------------------------------------------------------------


class LLMProvider(abc.ABC):
    """Abstract LLM provider for controller stage prompts."""

    @abc.abstractmethod
    async def complete(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stop_sequences: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        """Send a completion request to the LLM."""

    @abc.abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> str:
        """Send a chat completion request."""


class ModelRegistry(abc.ABC):
    """Abstract registry for discovering available models."""

    @abc.abstractmethod
    async def list_models(self, task_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """List available models, optionally filtered by task type."""

    @abc.abstractmethod
    async def get_model_info(self, model_id: str) -> Dict[str, Any]:
        """Get metadata for a specific model."""

    @abc.abstractmethod
    async def is_local(self, model_id: str) -> bool:
        """Check if a model is available on local endpoints."""


class InferenceEndpoint(abc.ABC):
    """Abstract inference endpoint for executing a single model."""

    @abc.abstractmethod
    async def run(
        self,
        model_id: str,
        task_type: str,
        inputs: Dict[str, Any],
        **kwargs: Any,
    ) -> ExecutionResult:
        """Execute inference on the given model with inputs."""


class ToolRegistry(abc.ABC):
    """Abstract registry for tool/API documentation."""

    @abc.abstractmethod
    async def list_tools(self) -> List[str]:
        """List available tool names."""

    @abc.abstractmethod
    async def get_tool_doc(self, tool_name: str) -> Dict[str, Any]:
        """Get raw tool documentation."""

    @abc.abstractmethod
    async def get_unified_instruction(self, tool_name: str) -> ToolInstruction:
        """Get EasyTool-formatted unified instruction."""


# ---------------------------------------------------------------------------
# Concrete Implementations
# ---------------------------------------------------------------------------


class OpenAILLMProvider(LLMProvider):
    """OpenAI-compatible LLM provider (supports OpenAI, Azure, local endpoints)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4",
        use_completion: bool = False,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url or "https://api.openai.com/v1"
        self.model = model
        self.use_completion = use_completion
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self._session

    async def complete(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        stop_sequences: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> str:
        session = await self._get_session()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stop_sequences:
            payload["stop"] = stop_sequences
        payload.update(kwargs)

        url = f"{self.base_url}/completions"
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"LLM completion failed ({resp.status}): {text}")
            data = await resp.json()
            return data["choices"][0]["text"]

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> str:
        session = await self._get_session()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        payload.update(kwargs)

        url = f"{self.base_url}/chat/completions"
        async with session.post(url, headers=headers, json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"LLM chat failed ({resp.status}): {text}")
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


class HuggingFaceRegistry(ModelRegistry):
    """Model registry backed by the HuggingFace Hub."""

    def __init__(
        self,
        token: Optional[str] = None,
        cache_dir: Optional[str] = None,
        local_endpoint_url: Optional[str] = None,
    ) -> None:
        self.token = token or os.environ.get("HUGGINGFACE_TOKEN", "")
        self.cache_dir = cache_dir
        self.local_endpoint_url = local_endpoint_url
        self._local_models: set[str] = set()
        self._model_cache: Dict[str, Dict[str, Any]] = {}

    def register_local_model(self, model_id: str) -> None:
        """Register a model as available on local endpoints."""
        self._local_models.add(model_id)

    async def list_models(self, task_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch models from HuggingFace Hub, optionally filtered by pipeline tag."""
        try:
            from huggingface_hub import HfApi, list_models as hf_list_models
        except ImportError:
            logger.warning("huggingface_hub not installed; returning empty model list")
            return []

        api = HfApi(token=self.token)
        filters: Dict[str, Any] = {}
        if task_type:
            filters["pipeline_tag"] = task_type
        models = list(api.list_models(**filters, limit=100, sort="downloads"))
        results = []
        for m in models:
            info = {
                "id": m.modelId,
                "author": m.author,
                "downloads": m.downloads,
                "tags": m.tags,
                "pipeline_tag": m.pipeline_tag,
                "is_local": m.modelId in self._local_models,
            }
            results.append(info)
            self._model_cache[m.modelId] = info
        return results

    async def get_model_info(self, model_id: str) -> Dict[str, Any]:
        if model_id in self._model_cache:
            return self._model_cache[model_id]
        try:
            from huggingface_hub import model_info as hf_model_info
        except ImportError:
            return {"id": model_id, "error": "huggingface_hub not installed"}
        info = hf_model_info(model_id, token=self.token)
        result = {
            "id": info.modelId,
            "author": info.author,
            "downloads": info.downloads,
            "tags": info.tags,
            "pipeline_tag": info.pipeline_tag,
            "card_data": dict(info.cardData) if info.cardData else {},
            "is_local": model_id in self._local_models,
        }
        self._model_cache[model_id] = result
        return result

    async def is_local(self, model_id: str) -> bool:
        return model_id in self._local_models


class HuggingFaceInferenceEndpoint(InferenceEndpoint):
    """Inference via HuggingFace Inference API (remote)."""

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: str = "https://api-inference.huggingface.co/models",
        timeout: float = 120.0,
    ) -> None:
        self.token = token or os.environ.get("HUGGINGFACE_TOKEN", "")
        self.base_url = base_url
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self._session

    async def run(
        self,
        model_id: str,
        task_type: str,
        inputs: Dict[str, Any],
        **kwargs: Any,
    ) -> ExecutionResult:
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {self.token}"}
        url = f"{self.base_url}/{model_id}"

        # Normalize inputs to HF API format
        payload = self._normalize_inputs(inputs, task_type)

        start = time.perf_counter()
        try:
            async with session.post(url, headers=headers, json=payload) as resp:
                elapsed = (time.perf_counter() - start) * 1000
                if resp.status != 200:
                    text = await resp.text()
                    return ExecutionResult(
                        task_id=kwargs.get("task_id", -1),
                        model_id=model_id,
                        status="error",
                        error_message=f"HTTP {resp.status}: {text}",
                        execution_time_ms=elapsed,
                    )
                data = await resp.json()
                output, output_type = self._denormalize_outputs(data, task_type)
                return ExecutionResult(
                    task_id=kwargs.get("task_id", -1),
                    model_id=model_id,
                    status="success",
                    output=output,
                    output_type=output_type,
                    execution_time_ms=elapsed,
                )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return ExecutionResult(
                task_id=kwargs.get("task_id", -1),
                model_id=model_id,
                status="error",
                error_message=str(exc),
                execution_time_ms=elapsed,
            )

    def _normalize_inputs(self, inputs: Dict[str, Any], task_type: str) -> Any:
        """Convert standard inputs to HuggingFace API format."""
        if task_type in ("text-to-image", "text-to-video"):
            return {"inputs": inputs.get("text", "")}
        if "image" in inputs and isinstance(inputs["image"], str):
            # Assume URL or base64
            return {"inputs": inputs["image"]}
        return inputs

    def _denormalize_outputs(
        self, data: Any, task_type: str
    ) -> Tuple[Any, Literal["text", "image", "audio", "video", "binary"]]:
        """Convert HF API output to standard format."""
        if task_type in ("text-to-image", "image-to-image"):
            # Binary image data
            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], bytes):
                return data[0], "image"
            if isinstance(data, bytes):
                return data, "image"
        if task_type in ("text-to-speech", "audio-to-audio"):
            if isinstance(data, bytes):
                return data, "audio"
        return data, "text"

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


class LocalInferenceEndpoint(InferenceEndpoint):
    """Inference via local model server (models_server.py)."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8005,
        timeout: float = 300.0,
    ) -> None:
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self._session

    async def run(
        self,
        model_id: str,
        task_type: str,
        inputs: Dict[str, Any],
        **kwargs: Any,
    ) -> ExecutionResult:
        session = await self._get_session()
        url = f"{self.base_url}/inference"
        payload = {
            "model": model_id,
            "task": task_type,
            "input": inputs,
        }
        start = time.perf_counter()
        try:
            async with session.post(url, json=payload) as resp:
                elapsed = (time.perf_counter() - start) * 1000
                if resp.status != 200:
                    text = await resp.text()
                    return ExecutionResult(
                        task_id=kwargs.get("task_id", -1),
                        model_id=model_id,
                        status="error",
                        error_message=f"HTTP {resp.status}: {text}",
                        execution_time_ms=elapsed,
                    )
                data = await resp.json()
                return ExecutionResult(
                    task_id=kwargs.get("task_id", -1),
                    model_id=model_id,
                    status="success",
                    output=data.get("output"),
                    output_type=data.get("output_type", "text"),
                    execution_time_ms=elapsed,
                )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return ExecutionResult(
                task_id=kwargs.get("task_id", -1),
                model_id=model_id,
                status="error",
                error_message=str(exc),
                execution_time_ms=elapsed,
            )

    async def health(self) -> bool:
        """Check if local model server is alive."""
        session = await self._get_session()
        try:
            async with session.get(f"{self.base_url}/health", timeout=aiohttp.ClientTimeout(total=5)):
                return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


# ---------------------------------------------------------------------------
# EasyTool Formatter
# ---------------------------------------------------------------------------


class EasyToolFormatter:
    """Converts raw tool documentation to unified EasyTool instructions."""

    @staticmethod
    def format(raw_doc: Dict[str, Any]) -> ToolInstruction:
        """Convert raw tool doc to unified instruction."""
        name = raw_doc.get("name", raw_doc.get("tool_name", "unknown"))
        desc = raw_doc.get("description", raw_doc.get("summary", ""))

        # Normalize parameters
        params: List[Dict[str, Any]] = []
        required: List[str] = []
        raw_params = raw_doc.get("parameters", raw_doc.get("params", []))
        if isinstance(raw_params, dict) and "properties" in raw_params:
            # OpenAPI-style schema
            for pname, pschema in raw_params["properties"].items():
                params.append(
                    {
                        "name": pname,
                        "type": pschema.get("type", "any"),
                        "description": pschema.get("description", ""),
                    }
                )
            required = list(raw_params.get("required", []))
        elif isinstance(raw_params, list):
            for p in raw_params:
                params.append(
                    {
                        "name": p.get("name", p.get("parameter", "")),
                        "type": p.get("type", "any"),
                        "description": p.get("description", p.get("summary", "")),
                    }
                )
                if p.get("required", False):
                    required.append(p.get("name", p.get("parameter", "")))

        # Normalize examples
        examples: List[Dict[str, Any]] = []
        raw_examples = raw_doc.get("examples", raw_doc.get("demo", []))
        if isinstance(raw_examples, list):
            examples = raw_examples
        elif isinstance(raw_examples, dict):
            examples = [raw_examples]

        return ToolInstruction(
            tool_name=name,
            description=desc,
            parameters=params,
            required_params=required,
            examples=examples,
            api_endpoint=raw_doc.get("endpoint", raw_doc.get("api", None)),
            method=raw_doc.get("method", "POST"),
        )

    @staticmethod
    def condense(instruction: ToolInstruction, max_length: int = 500) -> ToolInstruction:
        """Condense an instruction to fit within a token budget."""
        md = instruction.to_markdown()
        if len(md) <= max_length:
            return instruction
        # Truncate description if needed
        excess = len(md) - max_length
        new_desc = instruction.description[: max(50, len(instruction.description) - excess - 100)]
        new_desc = new_desc.rsplit(".", 1)[0] + "." if "." in new_desc else new_desc
        return ToolInstruction(
            tool_name=instruction.tool_name,
            description=new_desc,
            parameters=instruction.parameters,
            required_params=instruction.required_params,
            examples=instruction.examples[:1],  # Keep only one example
            api_endpoint=instruction.api_endpoint,
            method=instruction.method,
        )


# ---------------------------------------------------------------------------
# TaskBench DAG Engine
# ---------------------------------------------------------------------------


class TaskBenchEngine:
    """Engine for generating and evaluating task automation DAGs."""

    def __init__(self, llm_provider: LLMProvider) -> None:
        self.llm = llm_provider

    async def generate_task_graph(
        self,
        user_request: str,
        available_tools: List[ToolInstruction],
        domain: str = "general",
        max_nodes: int = 10,
    ) -> TaskGraph:
        """Generate a task dependency graph from a user request."""
        tools_md = "\n\n".join([t.to_markdown() for t in available_tools[:20]])
        prompt = textwrap.dedent(
            f"""\
            Given the following user request and available tools, generate a task dependency graph.
            
            User Request: {user_request}
            
            Available Tools:
            {tools_md}
            
            Generate a JSON object with the following structure:
            {{
              "nodes": [
                {{"id": "node_1", "tool": "tool_name", "params": {{"param1": "value1"}}}}
              ],
              "edges": [
                {{"source": "node_1", "target": "node_2", "resource_type": "text", "mapping": {{"input": "output"}}}}
              ]
            }}
            
            Rules:
            - Use at most {max_nodes} nodes
            - Only use tools from the available list
            - The graph must be a DAG (no cycles)
            - All node IDs must be unique
            - resource_type must be one of: text, image, audio, video
            
            Output only valid JSON.
            """
        )
        response = await self.llm.complete(prompt, temperature=0.3, max_tokens=2048)
        # Extract JSON from response
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if not json_match:
            raise ValueError(f"LLM did not return valid JSON. Response: {response}")
        data = json.loads(json_match.group())

        nodes = [TaskGraphNode(
            node_id=n["id"],
            tool_name=n["tool"],
            parameters=n.get("params", {}),
        ) for n in data.get("nodes", [])]

        edges = [TaskGraphEdge(
            source=e["source"],
            target=e["target"],
            resource_type=e.get("resource_type", "text"),
            mapping=e.get("mapping", {}),
        ) for e in data.get("edges", [])]

        return TaskGraph(
            graph_id=str(uuid.uuid4()),
            nodes=nodes,
            edges=edges,
            domain=domain,
        )

    async def evaluate_graph(
        self,
        predicted_graph: TaskGraph,
        ground_truth_graph: TaskGraph,
    ) -> Dict[str, float]:
        """Evaluate predicted graph against ground truth."""
        # Node accuracy
        pred_nodes = {n.node_id: n.tool_name for n in predicted_graph.nodes}
        gt_nodes = {n.node_id: n.tool_name for n in ground_truth_graph.nodes}
        correct_nodes = sum(1 for nid, tool in pred_nodes.items() if gt_nodes.get(nid) == tool)
        node_accuracy = correct_nodes / max(len(gt_nodes), 1)

        # Edge accuracy
        pred_edges = {(e.source, e.target) for e in predicted_graph.edges}
        gt_edges = {(e.source, e.target) for e in ground_truth_graph.edges}
        correct_edges = len(pred_edges & gt_edges)
        edge_accuracy = correct_edges / max(len(gt_edges), 1)

        # Graph structure accuracy (topological order match)
        try:
            pred_order = predicted_graph.topological_order()
            gt_order = ground_truth_graph.topological_order()
            # Compare order using Kendall tau-like metric
            matches = sum(1 for a, b in zip(pred_order, gt_order) if a == b)
            order_accuracy = matches / max(len(gt_order), 1)
        except ValueError:
            order_accuracy = 0.0

        return {
            "node_accuracy": node_accuracy,
            "edge_accuracy": edge_accuracy,
            "order_accuracy": order_accuracy,
            "overall": (node_accuracy + edge_accuracy + order_accuracy) / 3.0,
        }


# ---------------------------------------------------------------------------
# Core HuggingGPT Pipeline
# ---------------------------------------------------------------------------


class HuggingGPTPipeline:
    """
    Four-stage HuggingGPT pipeline implementation.

    Stage 1: Task Planning     - Parse user request into task DAG
    Stage 2: Model Selection   - Select best model per task
    Stage 3: Task Execution    - Execute models in dependency order
    Stage 4: Response Generation - Synthesize final response
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        model_registry: ModelRegistry,
        local_endpoint: Optional[LocalInferenceEndpoint] = None,
        hf_endpoint: Optional[HuggingFaceInferenceEndpoint] = None,
        inference_mode: InferenceMode = InferenceMode.HYBRID,
        deployment_scale: DeploymentScale = DeploymentScale.STANDARD,
        num_candidate_models: int = 5,
        max_description_length: int = 100,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.llm = llm_provider
        self.registry = model_registry
        self.local = local_endpoint
        self.hf = hf_endpoint
        self.inference_mode = inference_mode
        self.deployment_scale = deployment_scale
        self.num_candidates = num_candidate_models
        self.max_desc_len = max_description_length
        self.config = config or {}
        self.easytool = EasyToolFormatter()

        # Load stage prompts from config or use defaults
        self.prompts = self._load_prompts()

    def _load_prompts(self) -> Dict[str, str]:
        defaults = {
            "parse_task": textwrap.dedent(
                """\
                #1 Task Planning Stage: The AI assistant can parse user input to several tasks:
                [{"task": task, "id": task_id, "dep": dependency_task_id, "args": {"text": text or <GENERATED>-dep_id, "image": image_url or <GENERATED>-dep_id, "audio": audio_url or <GENERATED>-dep_id}}].
                The special tag "<GENERATED>-dep_id" refer to the one generated resource in the dependency task and "dep_id" must be in "dep" list.
                The "args" field must be in ["text", "image", "audio"].
                The task MUST be selected from: {task_types}.
                Think step by step and parse out as few tasks as possible.
                If the user input can't be parsed, reply empty JSON [].
                """
            ),
            "choose_model": textwrap.dedent(
                """\
                #2 Model Selection Stage: Given the user request and parsed tasks, select a suitable model from the list. Focus on the description and prefer models with local inference endpoints.
                Output strict JSON: {"id": "model_id", "reason": "explanation"}
                """
            ),
            "response_results": textwrap.dedent(
                """\
                #4 Response Generation Stage: With the task execution logs, describe the process and inference results. Filter out irrelevant information. Tell complete paths or URLs of files.
                """
            ),
        }
        # Override from config if present
        if self.config and "tprompt" in self.config:
            for key in defaults:
                if key in self.config["tprompt"]:
                    defaults[key] = self.config["tprompt"][key]
        return defaults

    # ------------------------------------------------------------------
    # Stage 1: Task Planning
    # ------------------------------------------------------------------

    async def plan_tasks(self, user_request: str, context: str = "") -> List[TaskPlan]:
        """Parse user request into a list of tasks with dependencies."""
        task_types_str = ", ".join(sorted(ALL_TASK_TYPES))
        prompt = self.prompts["parse_task"].format(task_types=task_types_str)
        user_prompt = f"{prompt}\n\nThe chat log [{context}] may contain resources. Now I input {{ {user_request} }}."

        messages = [
            {"role": "system", "content": "You are an AI task planning assistant."},
            {"role": "user", "content": user_prompt},
        ]

        raw = await self.llm.chat(messages, temperature=0.3, max_tokens=1024)

        # Extract JSON array
        plans: List[TaskPlan] = []
        try:
            # Find JSON array in response
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                for item in data:
                    if isinstance(item, dict) and "task" in item:
                        plans.append(TaskPlan.from_dict(item))
        except json.JSONDecodeError as exc:
            logger.warning(f"Failed to parse task plan JSON: {exc}. Raw: {raw}")

        logger.info(f"Stage 1 produced {len(plans)} tasks")
        return plans

    # ------------------------------------------------------------------
    # Stage 2: Model Selection
    # ------------------------------------------------------------------

    async def select_models(
        self, user_request: str, task_plans: List[TaskPlan]
    ) -> List[ModelSelection]:
        """Select the best model for each task plan."""
        selections: List[ModelSelection] = []

        for plan in task_plans:
            # Fetch candidate models for this task type
            candidates = await self.registry.list_models(task_type=plan.task)
            # Prefer local models in hybrid mode
            if self.inference_mode in (InferenceMode.HYBRID, InferenceMode.LOCAL):
                candidates.sort(key=lambda m: (not m.get("is_local", False), -m.get("downloads", 0)))
            candidates = candidates[: self.num_candidates]

            if not candidates:
                logger.warning(f"No models found for task type: {plan.task}")
                selections.append(
                    ModelSelection(
                        task_id=plan.id,
                        model_id="unknown",
                        reason="No candidates available",
                    )
                )
                continue

            # Build model descriptions prompt
            metas = []
            for c in candidates:
                desc = c.get("id", "")
                card = c.get("card_data", {})
                if isinstance(card, dict):
                    summary = card.get("model_summary", card.get("tags", ""))
                    if summary:
                        desc += f" - {str(summary)[:self.max_desc_len]}"
                metas.append(desc)

            meta_text = "\n".join([f"{i+1}. {m}" for i, m in enumerate(metas)])
            prompt = (
                f"{self.prompts['choose_model']}\n\n"
                f"Task: {plan.task}\n"
                f"User request: {user_request}\n\n"
                f"Available models:\n{meta_text}"
            )

            messages = [
                {"role": "system", "content": "You are a model selection assistant."},
                {"role": "user", "content": prompt},
            ]

            raw = await self.llm.chat(messages, temperature=0.2, max_tokens=256)

            # Parse JSON response
            model_id = candidates[0]["id"]  # Default to top candidate
            reason = "Fallback to top candidate"
            try:
                match = re.search(r"\{.*\}", raw, re.DOTALL)
                if match:
                    choice = json.loads(match.group())
                    chosen_id = choice.get("id", "")
                    # Verify chosen ID is in candidates
                    if any(c["id"] == chosen_id for c in candidates):
                        model_id = chosen_id
                    reason = choice.get("reason", reason)
            except json.JSONDecodeError:
                logger.warning(f"Model selection JSON parse failed. Raw: {raw}")

            is_local = await self.registry.is_local(model_id)
            endpoint = None if is_local else f"https://huggingface.co/{model_id}"
            selections.append(
                ModelSelection(
                    task_id=plan.id,
                    model_id=model_id,
                    reason=reason,
                    endpoint=endpoint,
                )
            )

        logger.info(f"Stage 2 selected {len(selections)} models")
        return selections

    # ------------------------------------------------------------------
    # Stage 3: Task Execution
    # ------------------------------------------------------------------

    async def execute_tasks(
        self,
        task_plans: List[TaskPlan],
        model_selections: List[ModelSelection],
    ) -> List[ExecutionResult]:
        """Execute tasks in dependency order."""
        results: Dict[int, ExecutionResult] = {}
        sel_map = {s.task_id: s for s in model_selections}

        # Build dependency graph
        in_degree: Dict[int, int] = {p.id: 0 for p in task_plans}
        dependents: Dict[int, List[int]] = {p.id: [] for p in task_plans}
        for plan in task_plans:
            for dep_id in plan.dep:
                if dep_id in dependents:
                    dependents[dep_id].append(plan.id)
                    in_degree[plan.id] += 1

        # Execute in waves (topological order via BFS)
        ready = [tid for tid, deg in in_degree.items() if deg == 0]
        while ready:
            current_batch = ready[:]
            ready = []

            # Execute current batch in parallel
            batch_tasks = [self._execute_single_task(task_plans, sel_map, results, tid) for tid in current_batch]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            for tid, res in zip(current_batch, batch_results):
                if isinstance(res, Exception):
                    results[tid] = ExecutionResult(
                        task_id=tid,
                        model_id=sel_map.get(tid, ModelSelection(task_id=tid, model_id="unknown", reason="")).model_id,
                        status="error",
                        error_message=str(res),
                    )
                else:
                    results[tid] = res

                # Update dependents
                for dependent in dependents.get(tid, []):
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        ready.append(dependent)

        logger.info(f"Stage 3 executed {len(results)} tasks")
        return list(results.values())

    async def _execute_single_task(
        self,
        task_plans: List[TaskPlan],
        sel_map: Dict[int, ModelSelection],
        prior_results: Dict[int, ExecutionResult],
        task_id: int,
    ) -> ExecutionResult:
        """Execute a single task, resolving dependency references."""
        plan = next((p for p in task_plans if p.id == task_id), None)
        if not plan:
            raise ValueError(f"Task plan {task_id} not found")

        sel = sel_map.get(task_id)
        if not sel:
            raise ValueError(f"Model selection for task {task_id} not found")

        # Resolve dependency references in args
        resolved_args = self._resolve_args(plan.args, prior_results)

        # Choose inference endpoint
        endpoint = self._choose_endpoint(sel)
        if endpoint is None:
            return ExecutionResult(
                task_id=task_id,
                model_id=sel.model_id,
                status="skipped",
                error_message="No inference endpoint available",
            )

        return await endpoint.run(
            model_id=sel.model_id,
            task_type=plan.task,
            inputs=resolved_args,
            task_id=task_id,
        )

    def _resolve_args(
        self, args: Dict[str, str], prior_results: Dict[int, ExecutionResult]
    ) -> Dict[str, Any]:
        """Replace <GENERATED>-dep_id references with actual outputs."""
        resolved: Dict[str, Any] = {}
        for key, value in args.items():
            if isinstance(value, str) and value.startswith("<GENERATED>-"):
                dep_id_str = value.replace("<GENERATED>-", "")
                try:
                    dep_id = int(dep_id_str)
                    if dep_id in prior_results:
                        resolved[key] = prior_results[dep_id].output
                    else:
                        resolved[key] = value  # Leave as-is if not found
                except ValueError:
                    resolved[key] = value
            else:
                resolved[key] = value
        return resolved

    def _choose_endpoint(self, sel: ModelSelection) -> Optional[InferenceEndpoint]:
        """Select appropriate inference endpoint based on mode and availability."""
        if self.inference_mode == InferenceMode.LOCAL:
            return self.local
        if self.inference_mode == InferenceMode.HUGGINGFACE:
            return self.hf
        # Hybrid mode
        if sel.endpoint is None and self.local is not None:
            return self.local
        return self.hf if self.hf is not None else self.local

    # ------------------------------------------------------------------
    # Stage 4: Response Generation
    # ------------------------------------------------------------------

    async def generate_response(
        self,
        user_request: str,
        task_plans: List[TaskPlan],
        execution_results: List[ExecutionResult],
    ) -> str:
        """Synthesize final response from execution results."""
        # Build execution log
        log_lines = [f"User request: {user_request}", "", "Execution log:"]
        for plan, result in zip(task_plans, execution_results):
            log_lines.append(f"\nTask {plan.id} ({plan.task}) -> Model: {result.model_id}")
            log_lines.append(f"  Status: {result.status}")
            if result.status == "success":
                output_str = str(result.output)
                if len(output_str) > 500:
                    output_str = output_str[:500] + "..."
                log_lines.append(f"  Output: {output_str}")
            elif result.error_message:
                log_lines.append(f"  Error: {result.error_message}")

        log_text = "\n".join(log_lines)
        prompt = f"{self.prompts['response_results']}\n\n{log_text}"

        messages = [
            {"role": "system", "content": "You are a helpful AI assistant."},
            {"role": "user", "content": prompt},
        ]

        response = await self.llm.chat(messages, temperature=0.7, max_tokens=1024)
        logger.info("Stage 4 generated response")
        return response

    # ------------------------------------------------------------------
    # Full Pipeline
    # ------------------------------------------------------------------

    async def run(self, user_request: str, context: str = "") -> HuggingGPTResult:
        """Execute the full four-stage pipeline."""
        request_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        # Stage 1
        task_plans = await self.plan_tasks(user_request, context)

        # Stage 2
        model_selections = await self.select_models(user_request, task_plans)

        # Stage 3
        execution_results = await self.execute_tasks(task_plans, model_selections)

        # Stage 4
        response = await self.generate_response(user_request, task_plans, execution_results)

        total_time = (time.perf_counter() - start_time) * 1000

        return HuggingGPTResult(
            request_id=request_id,
            task_plans=task_plans,
            model_selections=model_selections,
            execution_results=execution_results,
            response=response,
            total_execution_time_ms=total_time,
        )

    async def close(self) -> None:
        """Release resources."""
        if self.local:
            await self.local.close()
        if self.hf:
            await self.hf.close()
        if hasattr(self.llm, "close"):
            await self.llm.close()


# ---------------------------------------------------------------------------
# Configuration Loader
# ---------------------------------------------------------------------------


def load_config(path: Union[str, Path]) -> Dict[str, Any]:
    """Load a HuggingGPT YAML configuration file."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


def pipeline_from_config(config: Dict[str, Any]) -> HuggingGPTPipeline:
    """Factory: Build a HuggingGPTPipeline from a config dict."""
    # LLM provider
    openai_cfg = config.get("openai", {})
    llm = OpenAILLMProvider(
        api_key=openai_cfg.get("api_key") or os.environ.get("OPENAI_API_KEY"),
        model=config.get("model", "gpt-4"),
        use_completion=config.get("use_completion", False),
    )

    # Model registry
    hf_cfg = config.get("huggingface", {})
    registry = HuggingFaceRegistry(
        token=hf_cfg.get("token") or os.environ.get("HUGGINGFACE_TOKEN"),
    )

    # Inference endpoints
    local_cfg = config.get("local_inference_endpoint", {})
    local_endpoint = None
    if config.get("inference_mode") in ("local", "hybrid"):
        local_endpoint = LocalInferenceEndpoint(
            host=local_cfg.get("host", "localhost"),
            port=local_cfg.get("port", 8005),
        )

    hf_endpoint = None
    if config.get("inference_mode") in ("huggingface", "hybrid"):
        hf_endpoint = HuggingFaceInferenceEndpoint(
            token=hf_cfg.get("token") or os.environ.get("HUGGINGFACE_TOKEN"),
        )

    return HuggingGPTPipeline(
        llm_provider=llm,
        model_registry=registry,
        local_endpoint=local_endpoint,
        hf_endpoint=hf_endpoint,
        inference_mode=InferenceMode(config.get("inference_mode", "hybrid")),
        deployment_scale=DeploymentScale(config.get("local_deployment", "standard")),
        num_candidate_models=config.get("num_candidate_models", 5),
        max_description_length=config.get("max_description_length", 100),
        config=config,
    )


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------


def render_task_graph_mermaid(graph: TaskGraph) -> str:
    """Render a TaskGraph as a Mermaid diagram string."""
    lines = ["graph TD"]
    for node in graph.nodes:
        lines.append(f"    {node.node_id}[{node.tool_name}]")
    for edge in graph.edges:
        lines.append(f"    {edge.source} -->|{edge.resource_type}| {edge.target}")
    return "\n".join(lines)


def build_dependency_matrix(task_plans: List[TaskPlan]) -> List[List[int]]:
    """Build an adjacency matrix from task plans."""
    n = len(task_plans)
    matrix = [[0] * n for _ in range(n)]
    id_to_idx = {p.id: i for i, p in enumerate(task_plans)}
    for plan in task_plans:
        for dep in plan.dep:
            if dep in id_to_idx:
                matrix[id_to_idx[dep]][id_to_idx[plan.id]] = 1
    return matrix


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    # Enums
    "InferenceMode",
    "DeploymentScale",
    "TaskType",
    # Data models
    "TaskPlan",
    "ModelSelection",
    "ExecutionResult",
    "HuggingGPTResult",
    "ToolInstruction",
    "TaskGraphNode",
    "TaskGraphEdge",
    "TaskGraph",
    # Abstract interfaces
    "LLMProvider",
    "ModelRegistry",
    "InferenceEndpoint",
    "ToolRegistry",
    # Concrete implementations
    "OpenAILLMProvider",
    "HuggingFaceRegistry",
    "HuggingFaceInferenceEndpoint",
    "LocalInferenceEndpoint",
    # Utilities
    "EasyToolFormatter",
    "TaskBenchEngine",
    "HuggingGPTPipeline",
    # Factory
    "load_config",
    "pipeline_from_config",
    # Helpers
    "render_task_graph_mermaid",
    "build_dependency_matrix",
]


# ---------------------------------------------------------------------------
# CLI entry point (for testing)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Microsoft JARVIS Integration Bridge")
    parser.add_argument("--config", type=str, default=None, help="Path to config YAML")
    parser.add_argument("--request", type=str, required=True, help="User request")
    parser.add_argument("--mode", choices=["plan", "execute", "full"], default="full")
    parser.add_argument("--output", type=str, default=None, help="Output JSON file")
    args = parser.parse_args()

    async def main():
        if args.config:
            cfg = load_config(args.config)
            pipeline = pipeline_from_config(cfg)
        else:
            # Minimal setup from env
            llm = OpenAILLMProvider()
            registry = HuggingFaceRegistry()
            pipeline = HuggingGPTPipeline(
                llm_provider=llm,
                model_registry=registry,
                hf_endpoint=HuggingFaceInferenceEndpoint(),
            )

        if args.mode == "plan":
            plans = await pipeline.plan_tasks(args.request)
            result = {"task_plans": [p.to_dict() for p in plans]}
        elif args.mode == "execute":
            plans = await pipeline.plan_tasks(args.request)
            selections = await pipeline.select_models(args.request, plans)
            executions = await pipeline.execute_tasks(plans, selections)
            result = {
                "task_plans": [p.to_dict() for p in plans],
                "model_selections": [s.to_dict() for s in selections],
                "execution_results": [e.to_dict() for e in executions],
            }
        else:
            result = await pipeline.run(args.request)
            result = result.to_dict()

        await pipeline.close()

        json_out = json.dumps(result, indent=2, ensure_ascii=False)
        if args.output:
            with open(args.output, "w") as f:
                f.write(json_out)
            print(f"Result written to {args.output}")
        else:
            print(json_out)

    asyncio.run(main())
