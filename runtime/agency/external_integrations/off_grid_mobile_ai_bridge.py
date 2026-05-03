"""
Off Grid Mobile AI Bridge for JARVIS
====================================

Integration adapter that wraps the capabilities of the Off Grid mobile AI suite
(https://github.com/alichherawalla/off-grid-mobile-ai) for use within the JARVIS
runtime environment.

Off Grid is a privacy-first, fully-offline mobile AI application built in React
Native. It is not a consumable library, so this bridge provides:

1. A declarative Python interface matching Off Grid's service layer patterns.
2. A remote-provider client that connects to an OpenAI-compatible endpoint
   exposed by a running Off Grid instance (or any compatible local server).
3. Fallback implementations using the same underlying engines (llama.cpp,
   whisper.cpp, ONNX Runtime) that JARVIS can invoke directly when Off Grid
   is not present.
4. Reference data structures and tool schemas extracted from Off Grid's
   source code for compatibility.

Usage:
    from off_grid_mobile_ai_bridge import OffGridBridge

    bridge = OffGridBridge(
        base_url="http://192.168.1.50:8080/v1",  # Off Grid remote server
        api_key=None,  # Local networks typically need no key
    )

    async for token in bridge.stream_chat("Explain quantum computing"):
        print(token, end="")

Environment Variables:
    OFFGRID_BASE_URL   - OpenAI-compatible base URL (default: None)
    OFFGRID_API_KEY    - API key for remote provider (default: None)
    OFFGRID_MOCK_MODE  - "true" to use mock/fallback implementations
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Coroutine,
    Dict,
    List,
    Literal,
    Optional,
    Protocol,
    Tuple,
    Union,
)

# ---------------------------------------------------------------------------
# Optional dependencies – fail gracefully when not installed
# ---------------------------------------------------------------------------
try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants & configuration (mirrored from Off Grid source)
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful AI assistant running locally on the user's device. "
    "Be concise and helpful."
)

WHISPER_MODELS: List[Dict[str, Any]] = [
    {"id": "tiny.en", "name": "Whisper Tiny (English)", "size_mb": 75},
    {"id": "tiny", "name": "Whisper Tiny (Multilingual)", "size_mb": 75},
    {"id": "base.en", "name": "Whisper Base (English)", "size_mb": 142},
    {"id": "base", "name": "Whisper Base (Multilingual)", "size_mb": 142},
    {"id": "small.en", "name": "Whisper Small (English)", "size_mb": 466},
]

# Tool definitions extracted from src/services/tools/registry.ts
AVAILABLE_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate math expressions",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "Math expression"}
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Get current date and time",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {"type": "string", "description": "IANA timezone, e.g. America/New_York"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_device_info",
            "description": "Get device hardware info",
            "parameters": {
                "type": "object",
                "properties": {
                    "info_type": {
                        "type": "string",
                        "description": "Info type",
                        "enum": ["battery", "storage", "memory", "all"],
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Search uploaded project documents",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_url",
            "description": "Fetch and read a web page",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "URL to fetch"}},
                "required": ["url"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Data models (mirroring Off Grid TypeScript types)
# ---------------------------------------------------------------------------

class ImageGenerationMode(str, Enum):
    AUTO = "auto"
    ONNX = "onnx"
    CORE_ML = "coreml"


class InferenceBackend(str, Enum):
    CPU = "cpu"
    METAL = "metal"
    OPENCL = "opencl"
    VULKAN = "vulkan"


@dataclass
class DeviceInfo:
    """Hardware capability profile (mirrors src/services/hardware types)."""

    platform: Literal["android", "ios", "macos"]
    cpu_cores: int
    total_ram_mb: int
    available_ram_mb: int
    gpu_name: Optional[str] = None
    gpu_backend: Optional[InferenceBackend] = None
    is_flagship: bool = False


@dataclass
class ModelRecommendation:
    """Suggested model config based on device profile."""

    recommended_model: str
    max_context: int
    gpu_layers: int
    quant: str = "Q4_K_M"


@dataclass
class DownloadedModel:
    """Metadata for a downloaded GGUF text model."""

    id: str
    name: str
    file_name: str
    file_path: str
    file_size: int
    mm_proj_path: Optional[str] = None
    is_vision_model: bool = False


@dataclass
class GenerationOptions:
    """Inference-time generation parameters (mirrors AppStore settings)."""

    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    context_length: int = 4096
    n_threads: int = 4
    n_batch: int = 512
    enable_gpu: bool = True
    gpu_layers: int = 99
    flash_attn: bool = True
    thinking_enabled: bool = True
    enabled_tools: List[str] = field(default_factory=lambda: [t["function"]["name"] for t in AVAILABLE_TOOLS])


@dataclass
class StreamToken:
    """Single token emitted during streaming (mirrors src/services/llm)."""

    content: Optional[str] = None
    reasoning_content: Optional[str] = None


@dataclass
class RagDocument:
    """A document indexed in the RAG knowledge base."""

    id: int
    project_id: str
    name: str
    path: str
    size: int
    enabled: bool = True


@dataclass
class RagSearchResult:
    """A retrieved chunk from the knowledge base."""

    chunk_text: str
    document_name: str
    similarity: float


@dataclass
class TranscriptionResult:
    """Whisper transcription output."""

    text: str
    is_capturing: bool
    process_time_ms: float
    recording_time_ms: float


@dataclass
class GeneratedImage:
    """Metadata for a generated image."""

    id: str
    prompt: str
    file_path: str
    width: int
    height: int
    steps: int
    guidance_scale: float
    created_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Tool execution handlers (mirroring src/services/tools/handlers)
# ---------------------------------------------------------------------------

def _tool_calculator(expression: str) -> str:
    """Safely evaluate a math expression."""
    try:
        allowed_names = {"__builtins__": {}}
        allowed_names.update({name: getattr(math, name) for name in dir(math) if not name.startswith("_")})
        allowed_names.update({"abs": abs, "round": round, "max": max, "min": min, "sum": sum})
        result = eval(expression, allowed_names)  # noqa: S307
        return str(result)
    except Exception as exc:
        return f"[Error] {exc}"


def _tool_get_current_datetime(timezone: Optional[str] = None) -> str:
    import datetime

    if timezone:
        try:
            import zoneinfo

            tz = zoneinfo.ZoneInfo(timezone)
            return datetime.datetime.now(tz).isoformat()
        except Exception:
            return datetime.datetime.now().isoformat()
    return datetime.datetime.now().isoformat()


def _tool_get_device_info(info_type: Optional[str] = None) -> str:
    import platform as py_platform
    import psutil

    info: Dict[str, Any] = {
        "platform": py_platform.platform(),
        "python_version": py_platform.python_version(),
        "cpu_count": psutil.cpu_count(),
        "memory_total_mb": psutil.virtual_memory().total // (1024 * 1024),
        "memory_available_mb": psutil.virtual_memory().available // (1024 * 1024),
    }
    if info_type and info_type != "all":
        return json.dumps({info_type: info.get(info_type, "unknown")}, indent=2)
    return json.dumps(info, indent=2)


async def _tool_web_search(query: str) -> str:
    """Placeholder for web search – requires network. JARVIS should inject its own search."""
    return f"[web_search placeholder] Query: {query}. Install JARVIS search integration for real results."


async def _tool_read_url(url: str) -> str:
    """Placeholder for URL fetching – requires network."""
    if aiohttp is None:
        return f"[read_url placeholder] URL: {url}. Install aiohttp for real fetching."
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as resp:
                text = await resp.text()
                return text[:4000]  # truncate for context window safety
    except Exception as exc:
        return f"[Error fetching URL] {exc}"


async def _tool_search_knowledge_base(query: str, bridge: "OffGridBridge") -> str:
    """Search the local RAG knowledge base."""
    results = await bridge.search_knowledge_base(query)
    if not results:
        return "No relevant documents found in the knowledge base."
    lines = [f"- [{r.similarity:.2f}] {r.document_name}: {r.chunk_text[:200]}" for r in results[:5]]
    return "\n".join(lines)


# Map tool names to their async handlers
TOOL_HANDLERS: Dict[str, Callable[..., Coroutine[Any, Any, str]]] = {
    "web_search": _tool_web_search,
    "calculator": lambda **kwargs: asyncio.coroutine(lambda: _tool_calculator(kwargs.get("expression", "")))(),
    "get_current_datetime": lambda **kwargs: asyncio.coroutine(
        lambda: _tool_get_current_datetime(kwargs.get("timezone"))
    )(),
    "get_device_info": lambda **kwargs: asyncio.coroutine(lambda: _tool_get_device_info(kwargs.get("info_type")))(),
    "read_url": _tool_read_url,
    # search_knowledge_base is injected at runtime because it needs `self`
}


# ---------------------------------------------------------------------------
# LLM Provider Protocol (mirrors src/services/providers/types.ts)
# ---------------------------------------------------------------------------

class LLMProvider(Protocol):
    """Abstract interface for local or remote LLM inference."""

    @property
    def name(self) -> str: ...

    @property
    def provider_type(self) -> str: ...

    @property
    def capabilities(self) -> Dict[str, bool]: ...

    async def stream_completion(
        self,
        messages: List[Dict[str, str]],
        options: GenerationOptions,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[StreamToken]: ...

    async def list_models(self) -> List[str]: ...


# ---------------------------------------------------------------------------
# OpenAI-compatible remote provider (mirrors OpenAICompatibleProvider)
# ---------------------------------------------------------------------------

class OpenAICompatibleProvider:
    """Client for an OpenAI-compatible HTTP endpoint (Ollama, LM Studio, etc.)."""

    def __init__(self, base_url: str, api_key: Optional[str] = None, model: Optional[str] = None):
        if aiohttp is None:
            raise RuntimeError("aiohttp is required for OpenAI-compatible remote providers")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.session: Optional[aiohttp.ClientSession] = None

    @property
    def name(self) -> str:
        return f"openai-compatible@{self.base_url}"

    @property
    def provider_type(self) -> str:
        return "remote"

    @property
    def capabilities(self) -> Dict[str, bool]:
        return {"streaming": True, "tool_calling": True, "vision": True, "thinking": True}

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self._headers())
        return self.session

    async def list_models(self) -> List[str]:
        session = await self._get_session()
        async with session.get(f"{self.base_url}/models") as resp:
            payload = await resp.json()
            return [m.get("id", m.get("name", "unknown")) for m in payload.get("data", [])]

    async def stream_completion(
        self,
        messages: List[Dict[str, str]],
        options: GenerationOptions,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[StreamToken]:
        session = await self._get_session()
        payload: Dict[str, Any] = {
            "model": self.model or "local",
            "messages": messages,
            "stream": True,
            "temperature": options.temperature,
            "max_tokens": options.max_tokens,
            "top_p": options.top_p,
            "repeat_penalty": options.repeat_penalty,
        }
        if tools:
            payload["tools"] = tools

        async with session.post(f"{self.base_url}/chat/completions", json=payload) as resp:
            async for line in resp.content:
                line = line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    yield StreamToken(
                        content=delta.get("content"),
                        reasoning_content=delta.get("reasoning_content"),
                    )
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()


# ---------------------------------------------------------------------------
# Local LLM provider via llama.cpp Python (fallback when llama-cpp-python installed)
# ---------------------------------------------------------------------------

class LocalLlamaProvider:
    """Direct llama.cpp integration using llama-cpp-python when available."""

    def __init__(self, model_path: str, n_gpu_layers: int = 0, n_ctx: int = 4096, n_threads: int = 4):
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeError(
                "llama-cpp-python is required for LocalLlamaProvider. "
                "Install with: pip install llama-cpp-python"
            ) from exc
        self.model_path = model_path
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self._llm: Any = None
        self._load_model()

    def _load_model(self) -> None:
        from llama_cpp import Llama

        logger.info("Loading local GGUF model: %s", self.model_path)
        self._llm = Llama(
            model_path=self.model_path,
            n_gpu_layers=self.n_gpu_layers,
            n_ctx=self.n_ctx,
            n_threads=self.n_threads,
            verbose=False,
        )

    @property
    def name(self) -> str:
        return f"local-llama:{self.model_path}"

    @property
    def provider_type(self) -> str:
        return "local"

    @property
    def capabilities(self) -> Dict[str, bool]:
        return {"streaming": True, "tool_calling": False, "vision": False, "thinking": False}

    async def list_models(self) -> List[str]:
        return [self.model_path]

    async def stream_completion(
        self,
        messages: List[Dict[str, str]],
        options: GenerationOptions,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[StreamToken]:
        loop = asyncio.get_event_loop()

        def _generate():
            return self._llm.create_chat_completion(
                messages=messages,  # type: ignore[arg-type]
                temperature=options.temperature,
                max_tokens=options.max_tokens,
                top_p=options.top_p,
                repeat_penalty=options.repeat_penalty,
                stream=True,
            )

        stream = await loop.run_in_executor(None, _generate)
        for chunk in stream:
            delta = chunk["choices"][0].get("delta", {})
            yield StreamToken(content=delta.get("content"))

    async def close(self) -> None:
        del self._llm


# ---------------------------------------------------------------------------
# Mock provider for testing / when no backend is available
# ---------------------------------------------------------------------------

class MockProvider:
    """Deterministic mock provider for testing and dry-run scenarios."""

    def __init__(self, responses: Optional[List[str]] = None):
        self._responses = responses or ["This is a mock response from Off Grid bridge."]
        self._idx = 0

    @property
    def name(self) -> str:
        return "mock"

    @property
    def provider_type(self) -> str:
        return "mock"

    @property
    def capabilities(self) -> Dict[str, bool]:
        return {"streaming": True, "tool_calling": True, "vision": False, "thinking": False}

    async def list_models(self) -> List[str]:
        return ["mock-model"]

    async def stream_completion(
        self,
        messages: List[Dict[str, str]],
        options: GenerationOptions,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[StreamToken]:
        text = self._responses[self._idx % len(self._responses)]
        self._idx += 1
        words = text.split()
        for word in words:
            await asyncio.sleep(0.03)
            yield StreamToken(content=word + " ")

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# RAG engine (mirrors Off Grid's sqlite + embedding pipeline)
# ---------------------------------------------------------------------------

class RagEngine:
    """Lightweight RAG implementation compatible with Off Grid's schema.

    Uses sentence-transformers for embeddings when available; falls back to
    a simple TF-IDF baseline for pure-Python environments.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._embedding_model: Any = None
        self._embedding_dim: int = 384
        self._init_db()

    def _init_db(self) -> None:
        import sqlite3

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                path TEXT,
                size INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                chunk_index INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS embeddings (
                chunk_rowid INTEGER PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
                doc_id INTEGER NOT NULL,
                embedding BLOB NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
            CREATE INDEX IF NOT EXISTS idx_docs_project ON documents(project_id);
            """
        )
        self.conn.commit()

    def _load_embedding_model(self) -> None:
        if self._embedding_model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer

            self._embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            self._embedding_dim = self._embedding_model.get_sentence_embedding_dimension()
            logger.info("Loaded embedding model: all-MiniLM-L6-v2 (%sd)", self._embedding_dim)
        except ImportError:
            logger.warning("sentence-transformers not installed; using TF-IDF fallback")
            self._embedding_model = "tfidf"

    def _embed(self, texts: List[str]) -> List[List[float]]:
        self._load_embedding_model()
        if self._embedding_model == "tfidf":
            return self._tfidf_embed(texts)
        embeddings = self._embedding_model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    def _tfidf_embed(self, texts: List[str]) -> List[List[float]]:
        """Simple TF-IDF fallback when sentence-transformers is unavailable."""
        from collections import Counter
        import math

        tokenized = [t.lower().split() for t in texts]
        df: Dict[str, int] = Counter()
        for tokens in tokenized:
            df.update(set(tokens))
        vocab = list(df.keys())
        idf = {w: math.log(len(texts) / (df[w] + 1)) + 1 for w in vocab}
        vectors: List[List[float]] = []
        for tokens in tokenized:
            tf = Counter(tokens)
            vec = [tf.get(w, 0) * idf[w] for w in vocab]
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

    def index_document(self, project_id: str, file_path: str, file_name: str, text: str) -> int:
        """Index a document into the RAG store. Mirrors RagService.indexDocument."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO documents (project_id, name, path, size) VALUES (?, ?, ?, ?)",
            (project_id, file_name, file_path, len(text.encode("utf-8"))),
        )
        doc_id = cursor.lastrowid

        chunks = self._chunk_text(text)
        chunk_rowids = []
        for idx, chunk in enumerate(chunks):
            cursor.execute(
                "INSERT INTO chunks (doc_id, content, chunk_index) VALUES (?, ?, ?)",
                (doc_id, chunk, idx),
            )
            chunk_rowids.append(cursor.lastrowid)

        embeddings = self._embed(chunks)
        for rowid, emb in zip(chunk_rowids, embeddings):
            emb_blob = json.dumps(emb).encode("utf-8")
            cursor.execute(
                "INSERT INTO embeddings (chunk_rowid, doc_id, embedding) VALUES (?, ?, ?)",
                (rowid, doc_id, emb_blob),
            )

        self.conn.commit()
        logger.info("RAG indexed %s: %d chunks", file_name, len(chunks))
        return doc_id

    def _chunk_text(self, text: str, chunk_size: int = 512, overlap: int = 64) -> List[str]:
        """Simple sliding-window chunking (mirrors chunkDocument)."""
        words = text.split()
        chunks: List[str] = []
        start = 0
        while start < len(words):
            end = start + chunk_size
            chunk = " ".join(words[start:end])
            chunks.append(chunk)
            start += chunk_size - overlap
        return chunks

    def search(self, project_id: str, query: str, top_k: int = 5) -> List[RagSearchResult]:
        """Search knowledge base by cosine similarity."""
        query_emb = self._embed([query])[0]
        cursor = self.conn.execute(
            """
            SELECT c.id, c.content, d.name, e.embedding
            FROM embeddings e
            JOIN chunks c ON e.chunk_rowid = c.id
            JOIN documents d ON e.doc_id = d.id
            WHERE d.project_id = ? AND d.enabled = 1
            """,
            (project_id,),
        )
        results: List[Tuple[float, RagSearchResult]] = []
        for row in cursor.fetchall():
            emb = json.loads(row[3].decode("utf-8"))
            sim = self._cosine_similarity(query_emb, emb)
            results.append(
                (
                    sim,
                    RagSearchResult(
                        chunk_text=row[1], document_name=row[2], similarity=sim
                    ),
                )
            )
        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:top_k]]

    def get_documents(self, project_id: str) -> List[RagDocument]:
        cursor = self.conn.execute(
            "SELECT id, project_id, name, path, size, enabled FROM documents WHERE project_id = ?",
            (project_id,),
        )
        rows = cursor.fetchall()
        return [RagDocument(id=r[0], project_id=r[1], name=r[2], path=r[3], size=r[4], enabled=bool(r[5])) for r in rows]

    def delete_document(self, doc_id: int) -> None:
        self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


# ---------------------------------------------------------------------------
# Main bridge class
# ---------------------------------------------------------------------------

class OffGridBridge:
    """Unified bridge exposing Off Grid Mobile AI capabilities to JARVIS.

    The bridge attempts the following resolution order for LLM inference:
    1. OpenAI-compatible remote provider (Off Grid remote server, Ollama, etc.)
    2. Local llama.cpp provider (when llama-cpp-python is installed and model_path given)
    3. Mock provider (deterministic responses for testing)
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        local_model_path: Optional[str] = None,
        mock_mode: bool = False,
        rag_db_path: str = ":memory:",
    ):
        self.mock_mode = mock_mode or os.getenv("OFFGRID_MOCK_MODE", "false").lower() == "true"
        self.base_url = base_url or os.getenv("OFFGRID_BASE_URL")
        self.api_key = api_key or os.getenv("OFFGRID_API_KEY")
        self.model = model
        self.local_model_path = local_model_path
        self.rag_db_path = rag_db_path

        self._provider: Optional[LLMProvider] = None
        self._rag: Optional[RagEngine] = None
        self._active_model: Optional[DownloadedModel] = None
        self._generation_options = GenerationOptions()

    # ------------------------------------------------------------------
    # Provider lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Resolve and initialize the best available LLM provider."""
        if self.mock_mode:
            logger.info("OffGridBridge: using MockProvider")
            self._provider = MockProvider()
            return

        if self.base_url:
            try:
                self._provider = OpenAICompatibleProvider(
                    base_url=self.base_url, api_key=self.api_key, model=self.model
                )
                models = await self._provider.list_models()
                logger.info("OffGridBridge: connected to remote provider at %s (models: %d)", self.base_url, len(models))
                return
            except Exception as exc:
                logger.warning("OffGridBridge: remote provider failed (%s), trying fallback", exc)

        if self.local_model_path and os.path.exists(self.local_model_path):
            try:
                self._provider = LocalLlamaProvider(
                    model_path=self.local_model_path,
                    n_gpu_layers=self._generation_options.gpu_layers,
                    n_ctx=self._generation_options.context_length,
                    n_threads=self._generation_options.n_threads,
                )
                logger.info("OffGridBridge: loaded local model %s", self.local_model_path)
                return
            except Exception as exc:
                logger.warning("OffGridBridge: local model failed (%s), falling back to mock", exc)

        logger.info("OffGridBridge: no backend available; using MockProvider")
        self._provider = MockProvider()

    async def close(self) -> None:
        if self._provider is not None:
            await self._provider.close()
        if self._rag is not None:
            self._rag.close()

    @property
    def provider(self) -> LLMProvider:
        if self._provider is None:
            raise RuntimeError("Bridge not initialized. Call initialize() first.")
        return self._provider

    @property
    def rag(self) -> RagEngine:
        if self._rag is None:
            self._rag = RagEngine(db_path=self.rag_db_path)
        return self._rag

    # ------------------------------------------------------------------
    # Generation settings
    # ------------------------------------------------------------------

    def update_generation_options(self, **kwargs: Any) -> None:
        """Update inference parameters (temperature, max_tokens, etc.)."""
        for key, value in kwargs.items():
            if hasattr(self._generation_options, key):
                setattr(self._generation_options, key, value)
            else:
                raise ValueError(f"Unknown generation option: {key}")

    def get_generation_options(self) -> GenerationOptions:
        return self._generation_options

    # ------------------------------------------------------------------
    # Chat & streaming
    # ------------------------------------------------------------------

    async def stream_chat(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[StreamToken]:
        """Stream a chat response given a user message.

        Args:
            user_message: The latest user message.
            conversation_history: Previous messages in OpenAI format (role/content).
            system_prompt: Override the default system prompt.
        """
        messages: List[Dict[str, str]] = list(conversation_history or [])
        if system_prompt or self._generation_options.system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt or self._generation_options.system_prompt})
        messages.append({"role": "user", "content": user_message})

        tools = None
        if self._generation_options.enabled_tools:
            tools = [t for t in AVAILABLE_TOOLS if t["function"]["name"] in self._generation_options.enabled_tools]

        async for token in self.provider.stream_completion(
            messages=messages,
            options=self._generation_options,
            tools=tools if tools else None,
        ):
            yield token

    async def chat(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Non-streaming chat that aggregates tokens into a single string."""
        parts: List[str] = []
        async for token in self.stream_chat(user_message, conversation_history, system_prompt):
            if token.content:
                parts.append(token.content)
        return "".join(parts)

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Execute a built-in tool by name with JSON-encoded arguments.

        Args:
            tool_name: One of the tool names from AVAILABLE_TOOLS.
            arguments: Dictionary of parameter values.
        """
        if tool_name == "search_knowledge_base":
            return await _tool_search_knowledge_base(arguments.get("query", ""), self)
        handler = TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return f"[Error] Unknown tool: {tool_name}"
        try:
            if asyncio.iscoroutinefunction(handler):
                return await handler(**arguments)
            else:
                return handler(**arguments)
        except Exception as exc:
            return f"[Error executing {tool_name}] {exc}"

    def get_available_tools_schema(self) -> List[Dict[str, Any]]:
        """Return OpenAI-compatible function schemas for enabled tools."""
        enabled = set(self._generation_options.enabled_tools)
        return [t for t in AVAILABLE_TOOLS if t["function"]["name"] in enabled]

    # ------------------------------------------------------------------
    # RAG / Knowledge base
    # ------------------------------------------------------------------

    async def index_document(
        self, project_id: str, file_path: str, file_name: str, text: str
    ) -> int:
        """Index a document into the RAG knowledge base for a project."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.rag.index_document, project_id, file_path, file_name, text)

    async def search_knowledge_base(
        self, query: str, project_id: str = "default", top_k: int = 5
    ) -> List[RagSearchResult]:
        """Search the knowledge base for relevant chunks."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.rag.search, project_id, query, top_k)

    async def list_knowledge_base_documents(self, project_id: str = "default") -> List[RagDocument]:
        """List indexed documents for a project."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.rag.get_documents, project_id)

    async def delete_knowledge_base_document(self, doc_id: int) -> None:
        """Remove a document and its embeddings from the knowledge base."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.rag.delete_document, doc_id)

    # ------------------------------------------------------------------
    # Image generation (abstracted – requires platform-specific backends)
    # ------------------------------------------------------------------

    async def generate_image(
        self,
        prompt: str,
        width: int = 512,
        height: int = 512,
        steps: int = 20,
        guidance_scale: float = 7.5,
    ) -> GeneratedImage:
        """Generate an image from a text prompt.

        This is a placeholder interface. Real implementation requires either:
        - onnxruntime + diffusers pipeline (CPU/OpenCL)
        - Core ML Diffusion (macOS/iOS)
        - Off Grid's local-dream integration (Android)

        In mock mode, returns metadata without generating pixels.
        """
        if self.mock_mode:
            image_id = str(uuid.uuid4())
            mock_path = f"/tmp/offgrid_mock_{image_id}.png"
            return GeneratedImage(
                id=image_id,
                prompt=prompt,
                file_path=mock_path,
                width=width,
                height=height,
                steps=steps,
                guidance_scale=guidance_scale,
            )
        raise NotImplementedError(
            "Image generation requires a platform-specific backend (onnxruntime, diffusers, or CoreML). "
            "Set mock_mode=True for testing."
        )

    # ------------------------------------------------------------------
    # Voice / transcription
    # ------------------------------------------------------------------

    async def transcribe_audio(self, audio_path: str, model_id: str = "base") -> TranscriptionResult:
        """Transcribe an audio file using Whisper.

        Requires whisper.cpp Python bindings or whisper.rn server endpoint.
        In mock mode, returns placeholder text.
        """
        if self.mock_mode:
            return TranscriptionResult(
                text="[Mock transcription] This is a placeholder transcription result.",
                is_capturing=False,
                process_time_ms=0.0,
                recording_time_ms=0.0,
            )
        raise NotImplementedError(
            "Audio transcription requires whisper.cpp bindings or a running Off Grid server. "
            "Set mock_mode=True for testing."
        )

    # ------------------------------------------------------------------
    # Model management helpers
    # ------------------------------------------------------------------

    def get_model_recommendation(self, device_info: Optional[DeviceInfo] = None) -> ModelRecommendation:
        """Recommend a model configuration based on available hardware."""
        if device_info is None:
            import psutil

            device_info = DeviceInfo(
                platform="unknown",
                cpu_cores=os.cpu_count() or 4,
                total_ram_mb=psutil.virtual_memory().total // (1024 * 1024),
                available_ram_mb=psutil.virtual_memory().available // (1024 * 1024),
            )

        ram = device_info.available_ram_mb
        if ram > 12000:
            return ModelRecommendation(recommended_model="Qwen3-8B-Q4_K_M", max_context=8192, gpu_layers=99)
        elif ram > 6000:
            return ModelRecommendation(recommended_model="Phi-4-Q4_K_M", max_context=4096, gpu_layers=30)
        elif ram > 3500:
            return ModelRecommendation(recommended_model="Gemma-3-4B-Q4_K_M", max_context=4096, gpu_layers=20)
        else:
            return ModelRecommendation(recommended_model="Qwen3-1.8B-Q4_K_M", max_context=2048, gpu_layers=0)

    # ------------------------------------------------------------------
    # Provider introspection
    # ------------------------------------------------------------------

    @property
    def active_provider_info(self) -> Dict[str, Any]:
        """Return metadata about the currently active provider."""
        return {
            "name": self.provider.name,
            "type": self.provider.provider_type,
            "capabilities": self.provider.capabilities,
            "generation_options": asdict(self._generation_options),
        }


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def create_bridge(**kwargs: Any) -> OffGridBridge:
    """Create and initialize an OffGridBridge in one call.

    Examples:
        >>> bridge = await create_bridge(base_url="http://localhost:11434/v1", model="llama3.2")
        >>> bridge = await create_bridge(local_model_path="/models/phi-4-q4.gguf")
        >>> bridge = await create_bridge(mock_mode=True)
    """
    bridge = OffGridBridge(**kwargs)
    asyncio.get_event_loop().run_until_complete(bridge.initialize())
    return bridge


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    # Main bridge
    "OffGridBridge",
    "create_bridge",
    # Providers
    "LLMProvider",
    "OpenAICompatibleProvider",
    "LocalLlamaProvider",
    "MockProvider",
    # RAG
    "RagEngine",
    "RagDocument",
    "RagSearchResult",
    # Data models
    "DeviceInfo",
    "ModelRecommendation",
    "DownloadedModel",
    "GenerationOptions",
    "StreamToken",
    "TranscriptionResult",
    "GeneratedImage",
    # Enums
    "ImageGenerationMode",
    "InferenceBackend",
    # Constants
    "AVAILABLE_TOOLS",
    "WHISPER_MODELS",
    "DEFAULT_SYSTEM_PROMPT",
]
