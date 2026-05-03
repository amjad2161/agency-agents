"""
================================================================================
                    JARVIS BRAINIAC — HYBRID CLOUD BRIDGE
================================================================================
Routes tasks between local execution (speed/privacy) and cloud execution
(power/scale). All data is encrypted, all transfers are authenticated.

Architecture:
    ┌─────────────────┐         ┌─────────────────────────────────────┐
    │   Local Edge    │◄───────►│           Cloud Cluster             │
    │  (Speed+Privacy)│  HTTPS  │   (Heavy LLM / Training / Scale)   │
    └─────────────────┘  mTLS   └─────────────────────────────────────┘
           │                                              │
           └────────── Encrypted Sync ────────────────────┘

Author  : JARVIS BRAINIAC Runtime
Version : 2.0.0
================================================================================
"""

from __future__ import annotations

__all__ = [
    "HybridCloudRouter",
    "MockHybridCloud",
    "get_hybrid_cloud",
    "HybridCloudConfig",
    "RoutingDecision",
    "SyncStatus",
    "CloudResourceState",
    "LocalResourceState",
    "TaskCategory",
]

# ────────────────────────── Standard Library ──────────────────────────
import asyncio
import base64
import enum
import hashlib
import hmac
import io
import json
import logging
import os
import pickle
import platform
import secrets
import ssl
import subprocess
import sys
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable, Dict, List, Optional, Tuple, Union

# ────────────────────────── Third-Party ──────────────────────────
try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore[assignment]

try:
    import cryptography
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover
    cryptography = None  # type: ignore[assignment]

# ────────────────────────── Logging ──────────────────────────
logger = logging.getLogger("jarvis.runtime.hybrid_cloud")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(_handler)


# ═══════════════════════════════════════════════════════════════════════════════
#                              ENUMS & DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

class TaskCategory(enum.Enum):
    """Taxonomy of every workload JARVIS can receive."""

    VOICE_PROCESSING = "voice_processing"        # stt / tts — always local
    VISION_ANALYSIS  = "vision_analysis"         # face / object — local
    OS_CONTROL       = "os_control"              # shell / file ops — local
    FILE_OPS         = "file_operations"          # read / write — local
    LIGHT_LLM        = "light_llm"               # < 512-token prompts — local
    HEAVY_LLM        = "heavy_llm"               # > 512-token / reasoning — cloud
    FINANCIAL_ANALYSIS = "financial_analysis"    # market data / backtests — cloud
    MASS_DATA        = "mass_data"               # big ETL / analytics — cloud
    MODEL_TRAINING   = "model_training"          # fine-tune / RL — cloud
    CODE_GENERATION  = "code_generation"         # large codebase — cloud
    IMAGE_GENERATION = "image_generation"        # diffusion models — cloud
    VIDEO_PROCESSING = "video_processing"        # heavy encode / decode — cloud
    WEB_SEARCH       = "web_search"              # external apis — cloud
    UNKNOWN          = "unknown"                 # fallback heuristic


class RoutingTarget(enum.Enum):
    """Where a task ultimately lands."""

    LOCAL = "local"
    CLOUD = "cloud"
    QUEUE = "queue"          # deferred / batched


@dataclass(frozen=True)
class RoutingDecision:
    """Immutable record of why a task was routed the way it was."""

    target        : RoutingTarget
    confidence    : float                         # 0.0 – 1.0
    latency_local_ms: float
    latency_cloud_ms: float
    privacy_score : float                         # 0.0 = public, 1.0 = secret
    compute_needed: float                         # estimated GFLOPs
    data_size_mb  : float
    reasons       : List[str] = field(default_factory=list)
    timestamp     : str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target"           : self.target.value,
            "confidence"       : self.confidence,
            "latency_local_ms" : self.latency_local_ms,
            "latency_cloud_ms" : self.latency_cloud_ms,
            "privacy_score"    : self.privacy_score,
            "compute_needed"   : self.compute_needed,
            "data_size_mb"     : self.data_size_mb,
            "reasons"          : self.reasons,
            "timestamp"        : self.timestamp,
        }


@dataclass
class SyncStatus:
    """Snapshot of the local↔cloud sync health."""

    last_sync_up   : Optional[str] = None
    last_sync_down : Optional[str] = None
    last_settings_sync: Optional[str] = None
    pending_uploads: int = 0
    pending_downloads: int = 0
    sync_errors    : List[str] = field(default_factory=list)
    is_syncing     : bool = False
    bandwidth_mbps : float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "last_sync_up"        : self.last_sync_up,
            "last_sync_down"      : self.last_sync_down,
            "last_settings_sync"  : self.last_settings_sync,
            "pending_uploads"     : self.pending_uploads,
            "pending_downloads"   : self.pending_downloads,
            "sync_errors"         : self.sync_errors,
            "is_syncing"          : self.is_syncing,
            "bandwidth_mbps"      : self.bandwidth_mbps,
        }


@dataclass
class CloudResourceState:
    """Live telemetry from the cloud cluster."""

    online         : bool = False
    gpu_nodes      : int = 0
    cpu_nodes      : int = 0
    ram_gb_total   : float = 0.0
    ram_gb_used    : float = 0.0
    queue_depth    : int = 0
    avg_latency_ms : float = 0.0
    region         : str = "unknown"
    cost_per_hour_usd: float = 0.0
    last_updated   : str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "online"           : self.online,
            "gpu_nodes"        : self.gpu_nodes,
            "cpu_nodes"        : self.cpu_nodes,
            "ram_gb_total"     : self.ram_gb_total,
            "ram_gb_used"      : self.ram_gb_used,
            "queue_depth"      : self.queue_depth,
            "avg_latency_ms"   : self.avg_latency_ms,
            "region"           : self.region,
            "cost_per_hour_usd": self.cost_per_hour_usd,
            "last_updated"     : self.last_updated,
        }


@dataclass
class LocalResourceState:
    """Live telemetry from the edge device."""

    cpu_percent    : float = 0.0
    ram_percent    : float = 0.0
    ram_gb_total   : float = 0.0
    ram_gb_available: float = 0.0
    gpu_available  : bool = False
    gpu_vram_gb    : float = 0.0
    gpu_load_percent: float = 0.0
    disk_gb_free   : float = 0.0
    battery_percent: Optional[float] = None
    thermal_status : str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_percent"     : self.cpu_percent,
            "ram_percent"     : self.ram_percent,
            "ram_gb_total"    : self.ram_gb_total,
            "ram_gb_available": self.ram_gb_available,
            "gpu_available"   : self.gpu_available,
            "gpu_vram_gb"     : self.gpu_vram_gb,
            "gpu_load_percent": self.gpu_load_percent,
            "disk_gb_free"    : self.disk_gb_free,
            "battery_percent" : self.battery_percent,
            "thermal_status"  : self.thermal_status,
        }


@dataclass
class HybridCloudConfig:
    """Centralised configuration for the Hybrid Cloud Bridge."""

    # ── Cloud endpoint ──
    cloud_host         : str = "cloud.jarvis.internal"
    cloud_port         : int = 443
    api_version        : str = "v2"
    use_ssl            : bool = True
    ca_bundle_path     : Optional[str] = None

    # ── Auth ──
    api_key            : str = field(default_factory=lambda: os.getenv("JARVIS_CLOUD_KEY", ""))
    api_secret         : str = field(default_factory=lambda: os.getenv("JARVIS_CLOUD_SECRET", ""))

    # ── Encryption ──
    encryption_key     : Optional[bytes] = None   # 32-byte AES key
    key_rotation_days  : int = 30

    # ── Sync ──
    sync_interval_sec  : int = 300               # 5 minutes
    max_sync_batch_mb  : float = 50.0
    sync_enabled       : bool = True

    # ── Routing thresholds ──
    local_max_latency_ms     : float = 200.0
    local_max_data_mb        : float = 100.0
    local_max_compute_gflops : float = 500.0
    cloud_min_compute_gflops : float = 1000.0
    privacy_force_local      : bool = True

    # ── Timeouts ──
    cloud_timeout_sec    : float = 120.0
    local_timeout_sec    : float = 10.0
    connect_timeout_sec  : float = 5.0

    # ── Resilience ──
    max_retries          : int = 3
    backoff_base_sec     : float = 1.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_reset_sec: int = 60

    # ── Local paths ──
    chroma_db_path       : str = "/mnt/agents/data/chromadb"
    sync_state_file      : str = "/mnt/agents/data/sync_state.json"
    local_cache_dir      : str = "/mnt/agents/data/cache"

    def base_url(self) -> str:
        scheme = "https" if self.use_ssl else "http"
        return f"{scheme}://{self.cloud_host}:{self.cloud_port}/api/{self.api_version}"


# ═══════════════════════════════════════════════════════════════════════════════
#                          CRYPTOGRAPHIC LAYER
# ═══════════════════════════════════════════════════════════════════════════════

class _CryptoLayer:
    """
    Handles AES-256-GCM encryption for data in transit and at rest.
    Falls back to Fernet when AESGCM is unavailable (both from cryptography).
    """

    def __init__(self, key: Optional[bytes] = None) -> None:
        self._has_crypto = cryptography is not None
        if key is None:
            key = secrets.token_bytes(32)
        self._key = key
        self._fernet: Optional[Any] = None
        if self._has_crypto:
            try:
                self._aesgcm = AESGCM(self._key)
                self._mode = "aesgcm"
            except Exception:
                fernet_key = base64.urlsafe_b64encode(self._key[:32].ljust(32, b"\0"))
                self._fernet = Fernet(fernet_key)
                self._mode = "fernet"
        else:
            self._mode = "xor"          # weakest fallback — dev only
            logger.warning("cryptography unavailable — using XOR obfuscation only!")

    # ── public API ──

    def encrypt(self, plaintext: bytes, associated_data: Optional[bytes] = None) -> bytes:
        if self._mode == "aesgcm":
            nonce = secrets.token_bytes(12)
            ciphertext = self._aesgcm.encrypt(nonce, plaintext, associated_data)
            return b"\x01" + nonce + ciphertext
        elif self._mode == "fernet" and self._fernet is not None:
            token = self._fernet.encrypt(plaintext)
            return b"\x02" + token
        else:
            return b"\x00" + self._xor_encrypt(plaintext)

    def decrypt(self, blob: bytes, associated_data: Optional[bytes] = None) -> bytes:
        flag = blob[0:1]
        payload = blob[1:]
        if flag == b"\x01":
            nonce, ciphertext = payload[:12], payload[12:]
            return self._aesgcm.decrypt(nonce, ciphertext, associated_data)
        elif flag == b"\x02" and self._fernet is not None:
            return self._fernet.decrypt(payload)
        else:
            return self._xor_encrypt(payload)

    def encrypt_stream(self, reader: BinaryIO, writer: BinaryIO, chunk_size: int = 64 * 1024) -> None:
        """Stream-encrypt: prepend a 4-byte length then encrypted chunk."""
        while True:
            chunk = reader.read(chunk_size)
            if not chunk:
                break
            enc = self.encrypt(chunk)
            writer.write(len(enc).to_bytes(4, "big"))
            writer.write(enc)
        writer.write(b"\x00\x00\x00\x00")  # EOF sentinel

    def decrypt_stream(self, reader: BinaryIO, writer: BinaryIO, chunk_size: int = 64 * 1024) -> None:
        while True:
            length_bytes = reader.read(4)
            if len(length_bytes) < 4:
                break
            length = int.from_bytes(length_bytes, "big")
            if length == 0:
                break
            enc = reader.read(length)
            if len(enc) < length:
                raise ValueError("Truncated encrypted stream")
            writer.write(self.decrypt(enc))

    def sign(self, data: bytes) -> str:
        return hmac.new(self._key, data, hashlib.sha256).hexdigest()

    def verify(self, data: bytes, signature: str) -> bool:
        return hmac.compare_digest(self.sign(data), signature)

    # ── internal ──

    def _xor_encrypt(self, data: bytes) -> bytes:
        key_stream = hashlib.sha256(self._key).digest()
        return bytes(b ^ key_stream[i % len(key_stream)] for i, b in enumerate(data))


# ═══════════════════════════════════════════════════════════════════════════════
#                          HYBRID CLOUD ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

class HybridCloudRouter:
    """
    Core intelligent router for JARVIS BRAINIAC.

    Responsibilities:
        1. Classify incoming tasks into TaskCategory.
        2. Score local vs. cloud viability.
        3. Execute on the chosen substrate.
        4. Encrypt and sync state bidirectionally.
    """

    # ── hard-wired locals — never leave the edge ──
    _FORCE_LOCAL: Tuple[TaskCategory, ...] = (
        TaskCategory.VOICE_PROCESSING,
        TaskCategory.VISION_ANALYSIS,
        TaskCategory.OS_CONTROL,
        TaskCategory.FILE_OPS,
    )

    # ── hard-wired cloud — never run locally ──
    _FORCE_CLOUD: Tuple[TaskCategory, ...] = (
        TaskCategory.HEAVY_LLM,
        TaskCategory.FINANCIAL_ANALYSIS,
        TaskCategory.MODEL_TRAINING,
        TaskCategory.MASS_DATA,
    )

    # ── rough GFLOP estimates per category ──
    _COMPUTE_TABLE: Dict[TaskCategory, float] = {
        TaskCategory.VOICE_PROCESSING   : 5.0,
        TaskCategory.VISION_ANALYSIS    : 50.0,
        TaskCategory.OS_CONTROL         : 0.1,
        TaskCategory.FILE_OPS           : 0.1,
        TaskCategory.LIGHT_LLM          : 20.0,
        TaskCategory.HEAVY_LLM          : 2000.0,
        TaskCategory.FINANCIAL_ANALYSIS : 5000.0,
        TaskCategory.MASS_DATA          : 8000.0,
        TaskCategory.MODEL_TRAINING     : 50000.0,
        TaskCategory.CODE_GENERATION    : 1500.0,
        TaskCategory.IMAGE_GENERATION   : 10000.0,
        TaskCategory.VIDEO_PROCESSING   : 3000.0,
        TaskCategory.WEB_SEARCH         : 1.0,
        TaskCategory.UNKNOWN            : 100.0,
    }

    def __init__(self, config: Optional[HybridCloudConfig] = None) -> None:
        self.cfg = config or HybridCloudConfig()
        self._crypto = _CryptoLayer(self.cfg.encryption_key)
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="hybrid_cloud_")
        self._sync_lock = threading.RLock()
        self._sync_status = SyncStatus()
        self._cloud_state = CloudResourceState()
        self._local_state = LocalResourceState()
        self._circuit_failures = 0
        self._circuit_last_failure = 0.0
        self._task_history: List[Dict[str, Any]] = []
        self._running = True
        self._sync_thread: Optional[threading.Thread] = None
        if self.cfg.sync_enabled:
            self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
            self._sync_thread.start()
        self._refresh_local_resources()
        logger.info("HybridCloudRouter initialised — config: %s", self.cfg.base_url())

    # ────────────────────────── Task Classification ──────────────────────────

    @staticmethod
    def _classify_task(task: dict) -> TaskCategory:
        """Map free-form task dict → TaskCategory via heuristic."""
        tt: str = str(task.get("type", task.get("task_type", ""))).lower()
        tags: List[str] = [t.lower() for t in task.get("tags", [])]

        mapping = {
            "voice": TaskCategory.VOICE_PROCESSING,
            "stt": TaskCategory.VOICE_PROCESSING,
            "tts": TaskCategory.VOICE_PROCESSING,
            "vision": TaskCategory.VISION_ANALYSIS,
            "face": TaskCategory.VISION_ANALYSIS,
            "object": TaskCategory.VISION_ANALYSIS,
            "camera": TaskCategory.VISION_ANALYSIS,
            "os_control": TaskCategory.OS_CONTROL,
            "shell": TaskCategory.OS_CONTROL,
            "system": TaskCategory.OS_CONTROL,
            "file": TaskCategory.FILE_OPS,
            "filesystem": TaskCategory.FILE_OPS,
            "light_llm": TaskCategory.LIGHT_LLM,
            "chat": TaskCategory.LIGHT_LLM,
            "heavy_llm": TaskCategory.HEAVY_LLM,
            "reasoning": TaskCategory.HEAVY_LLM,
            "financial": TaskCategory.FINANCIAL_ANALYSIS,
            "market": TaskCategory.FINANCIAL_ANALYSIS,
            "stock": TaskCategory.FINANCIAL_ANALYSIS,
            "mass_data": TaskCategory.MASS_DATA,
            "etl": TaskCategory.MASS_DATA,
            "train": TaskCategory.MODEL_TRAINING,
            "fine_tune": TaskCategory.MODEL_TRAINING,
            "rl": TaskCategory.MODEL_TRAINING,
            "code": TaskCategory.CODE_GENERATION,
            "program": TaskCategory.CODE_GENERATION,
            "image_gen": TaskCategory.IMAGE_GENERATION,
            "diffusion": TaskCategory.IMAGE_GENERATION,
            "video": TaskCategory.VIDEO_PROCESSING,
            "encode": TaskCategory.VIDEO_PROCESSING,
            "search": TaskCategory.WEB_SEARCH,
            "web": TaskCategory.WEB_SEARCH,
        }

        for key, category in mapping.items():
            if key in tt or any(key in t for t in tags):
                return category
        return TaskCategory.UNKNOWN

    # ────────────────────────── Task Routing ──────────────────────────

    def route_task(self, task: dict) -> str:
        """
        Decide: "local" or "cloud".

        Returns the routing target as a lowercase string for easy
        downstream branching.
        """
        decision = self.get_routing_decision(
            task_type=task.get("type", task.get("task_type", "unknown")),
            data_size=task.get("data_size", 0),
            sensitivity=task.get("sensitivity", "normal"),
        )
        target = decision["target"]
        logger.info(
            "route_task: type=%s → %s (confidence=%.2f, reasons=%s)",
            task.get("type", "?"), target, decision["confidence"], decision["reasons"],
        )
        self._task_history.append({
            "task_type": task.get("type", "?"),
            "routed_to": target,
            "confidence": decision["confidence"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return target

    def get_routing_decision(self, task_type: str, data_size: int, sensitivity: str) -> Dict[str, Any]:
        """
        Produce a full RoutingDecision as a dict.

        Factors:
            - latency requirement (sub-200 ms => local bias)
            - data size (> 100 MB => cloud bias)
            - privacy level (secret => local bias)
            - compute needed (> 1000 GFLOPs => cloud bias)
        """
        category = self._classify_task({"type": task_type})
        compute_gflops = self._COMPUTE_TABLE.get(category, 100.0)
        data_mb = data_size / (1024 * 1024)
        sensitivity_lower = sensitivity.lower()

        # ── hard overrides ──
        reasons: List[str] = []
        if category in self._FORCE_LOCAL:
            reasons.append(f"{category.value} is force-local for privacy/speed")
            return RoutingDecision(
                target=RoutingTarget.LOCAL,
                confidence=0.99,
                latency_local_ms=self.cfg.local_max_latency_ms * 0.5,
                latency_cloud_ms=self.cfg.local_max_latency_ms * 3.0,
                privacy_score=1.0 if sensitivity_lower in ("secret", "private") else 0.5,
                compute_needed=compute_gflops,
                data_size_mb=data_mb,
                reasons=reasons,
            ).to_dict()

        if category in self._FORCE_CLOUD:
            reasons.append(f"{category.value} is force-cloud for compute scale")
            return RoutingDecision(
                target=RoutingTarget.CLOUD,
                confidence=0.99,
                latency_local_ms=9999.0,
                latency_cloud_ms=500.0,
                privacy_score=0.0,
                compute_needed=compute_gflops,
                data_size_mb=data_mb,
                reasons=reasons,
            ).to_dict()

        # ── scoring ──
        local_score = 0.0
        cloud_score = 0.0

        # latency sensitivity
        latency_req = "low" if category in (TaskCategory.VOICE_PROCESSING, TaskCategory.VISION_ANALYSIS) else "normal"
        if latency_req == "low":
            local_score += 2.0
            reasons.append("low-latency requirement biases local")

        # data size
        if data_mb > self.cfg.local_max_data_mb:
            cloud_score += 2.0
            reasons.append(f"data size {data_mb:.1f} MB > {self.cfg.local_max_data_mb} MB local limit")
        elif data_mb < 1.0:
            local_score += 0.5
            reasons.append("small data footprint biases local")

        # privacy
        if sensitivity_lower in ("secret", "private", "pii"):
            if self.cfg.privacy_force_local:
                reasons.append(f"privacy level '{sensitivity}' forces local execution")
                return RoutingDecision(
                    target=RoutingTarget.LOCAL,
                    confidence=0.98,
                    latency_local_ms=self.cfg.local_max_latency_ms,
                    latency_cloud_ms=self.cfg.cloud_timeout_sec * 1000,
                    privacy_score=1.0,
                    compute_needed=compute_gflops,
                    data_size_mb=data_mb,
                    reasons=reasons,
                ).to_dict()
            local_score += 1.5
            reasons.append("high privacy requirement biases local")
        elif sensitivity_lower == "public":
            cloud_score += 0.5
            reasons.append("public data biases cloud")

        # compute
        if compute_gflops > self.cfg.cloud_min_compute_gflops:
            cloud_score += 2.5
            reasons.append(f"compute {compute_gflops:.0f} GFLOPs exceeds cloud minimum")
        elif compute_gflops < self.cfg.local_max_compute_gflops:
            local_score += 1.0
            reasons.append(f"compute {compute_gflops:.0f} GFLOPs fits local capacity")

        # local resource pressure check
        self._refresh_local_resources()
        if self._local_state.ram_percent > 85.0 or self._local_state.cpu_percent > 90.0:
            cloud_score += 1.5
            reasons.append("local resource pressure high — offload preferred")
        elif self._local_state.ram_percent < 50.0 and self._local_state.cpu_percent < 40.0:
            local_score += 0.5
            reasons.append("local resources idle — prefer local")

        # ── decide ──
        total = local_score + cloud_score
        if total == 0:
            target = RoutingTarget.LOCAL
            confidence = 0.5
        else:
            local_ratio = local_score / total
            if local_ratio > 0.55:
                target = RoutingTarget.LOCAL
                confidence = local_ratio
            elif local_ratio < 0.45:
                target = RoutingTarget.CLOUD
                confidence = 1.0 - local_ratio
            else:
                # ambiguous — route locally to save cost unless compute heavy
                target = RoutingTarget.LOCAL if compute_gflops < 500 else RoutingTarget.CLOUD
                confidence = 0.6

        reasons.append(f"local_score={local_score:.1f}, cloud_score={cloud_score:.1f}")

        decision = RoutingDecision(
            target=target,
            confidence=confidence,
            latency_local_ms=self.cfg.local_max_latency_ms,
            latency_cloud_ms=300.0,
            privacy_score=0.7 if sensitivity_lower in ("secret", "private") else 0.3,
            compute_needed=compute_gflops,
            data_size_mb=data_mb,
            reasons=reasons,
        )
        return decision.to_dict()

    # ────────────────────────── Local-Cloud Sync ──────────────────────────

    def sync_memory_to_cloud(self) -> Dict[str, Any]:
        """
        Synchronise the local ChromaDB vector store to the cloud vector store.

        Steps:
            1. Scan chroma_db_path for new / modified embeddings.
            2. Compress and encrypt the delta.
            3. Upload via encrypted HTTPS stream.
            4. Update local sync checkpoint.
        """
        logger.info("sync_memory_to_cloud: starting upload")
        with self._sync_lock:
            self._sync_status.is_syncing = True
            self._sync_status.pending_uploads += 1

        try:
            db_path = Path(self.cfg.chroma_db_path)
            if not db_path.exists():
                logger.warning("ChromaDB path %s does not exist — creating", db_path)
                db_path.mkdir(parents=True, exist_ok=True)

            # collect metadata
            files = list(db_path.rglob("*")) if db_path.exists() else []
            total_size = sum(f.stat().st_size for f in files if f.is_file())

            # build payload
            payload = {
                "action": "sync_up",
                "db_version": self._read_sync_checkpoint(),
                "file_count": len([f for f in files if f.is_file()]),
                "total_bytes": total_size,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "hostname": platform.node(),
            }
            json_bytes = json.dumps(payload, default=str).encode("utf-8")
            encrypted = self._crypto.encrypt(json_bytes)

            # upload (mockable via subclass)
            result = self._http_post("/sync/memory", encrypted)

            self._write_sync_checkpoint(payload["timestamp"])
            with self._sync_lock:
                self._sync_status.last_sync_up = payload["timestamp"]
                self._sync_status.pending_uploads = max(0, self._sync_status.pending_uploads - 1)

            logger.info("sync_memory_to_cloud: uploaded %d bytes metadata", len(encrypted))
            return {"success": True, "uploaded_metadata_bytes": len(encrypted), "detail": result}
        except Exception as exc:
            logger.error("sync_memory_to_cloud failed: %s", exc, exc_info=True)
            with self._sync_lock:
                self._sync_status.sync_errors.append(str(exc))
            return {"success": False, "error": str(exc)}
        finally:
            with self._sync_lock:
                self._sync_status.is_syncing = False

    def sync_memory_from_cloud(self) -> Dict[str, Any]:
        """
        Pull updated embeddings / knowledge from the cloud vector store.

        Steps:
            1. Query cloud for delta since last sync checkpoint.
            2. Download encrypted delta stream.
            3. Decrypt and apply to local ChromaDB.
            4. Update checkpoint.
        """
        logger.info("sync_memory_from_cloud: starting download")
        with self._sync_lock:
            self._sync_status.is_syncing = True
            self._sync_status.pending_downloads += 1

        try:
            last_checkpoint = self._read_sync_checkpoint()
            request = {
                "action": "sync_down",
                "since_checkpoint": last_checkpoint,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            json_bytes = json.dumps(request).encode("utf-8")
            encrypted = self._crypto.encrypt(json_bytes)

            result = self._http_post("/sync/memory/pull", encrypted)
            timestamp = datetime.now(timezone.utc).isoformat()
            self._write_sync_checkpoint(timestamp)

            with self._sync_lock:
                self._sync_status.last_sync_down = timestamp
                self._sync_status.pending_downloads = max(0, self._sync_status.pending_downloads - 1)

            logger.info("sync_memory_from_cloud: completed")
            return {"success": True, "detail": result}
        except Exception as exc:
            logger.error("sync_memory_from_cloud failed: %s", exc, exc_info=True)
            with self._sync_lock:
                self._sync_status.sync_errors.append(str(exc))
            return {"success": False, "error": str(exc)}
        finally:
            with self._sync_lock:
                self._sync_status.is_syncing = False

    def sync_settings(self) -> Dict[str, Any]:
        """
        Bidirectional settings synchronisation.

        The conflict-resolution policy is **latest-timestamp-wins**.
        """
        logger.info("sync_settings: starting bidirectional sync")
        try:
            local_settings = self._load_local_settings()
            remote_settings = self._http_get("/settings")

            merged = self._merge_settings(local_settings, remote_settings)
            self._save_local_settings(merged)
            self._http_post("/settings", json.dumps(merged).encode())

            timestamp = datetime.now(timezone.utc).isoformat()
            with self._sync_lock:
                self._sync_status.last_settings_sync = timestamp

            logger.info("sync_settings: completed with %d keys", len(merged))
            return {"success": True, "keys_synced": len(merged), "timestamp": timestamp}
        except Exception as exc:
            logger.error("sync_settings failed: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc)}

    def get_sync_status(self) -> dict:
        """Return a snapshot of current sync health."""
        with self._sync_lock:
            status_copy = SyncStatus(
                last_sync_up=self._sync_status.last_sync_up,
                last_sync_down=self._sync_status.last_sync_down,
                last_settings_sync=self._sync_status.last_settings_sync,
                pending_uploads=self._sync_status.pending_uploads,
                pending_downloads=self._sync_status.pending_downloads,
                sync_errors=list(self._sync_status.sync_errors[-10:]),
                is_syncing=self._sync_status.is_syncing,
                bandwidth_mbps=self._sync_status.bandwidth_mbps,
            )
        return status_copy.to_dict()

    # ────────────────────────── Cloud Execution ──────────────────────────

    def execute_on_cloud(self, task: dict) -> dict:
        """
        Send a task to the cloud cluster and return the result.

        Pipeline:
            task dict → JSON → encrypt → HTTPS POST → cloud → decrypt → result dict
        """
        if self._circuit_open():
            logger.warning("Circuit breaker OPEN — rejecting cloud execution")
            return {"success": False, "error": "circuit_breaker_open", "fallback": "local"}

        logger.info("execute_on_cloud: task_type=%s", task.get("type", "?"))
        try:
            payload = self._prepare_task_payload(task)
            json_bytes = json.dumps(payload, default=str).encode("utf-8")
            encrypted = self._crypto.encrypt(json_bytes)

            # signature for integrity
            signature = self._crypto.sign(encrypted)

            start = time.monotonic()
            result_bytes = self._http_post(
                "/execute",
                encrypted,
                extra_headers={"X-Jarvis-Signature": signature},
            )
            elapsed_ms = (time.monotonic() - start) * 1000

            if isinstance(result_bytes, bytes):
                result_plain = self._crypto.decrypt(result_bytes)
                result = json.loads(result_plain.decode("utf-8"))
            else:
                result = result_bytes if isinstance(result_bytes, dict) else {"raw": result_bytes}

            result["_meta"] = {
                "executed_on": "cloud",
                "latency_ms": round(elapsed_ms, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._circuit_failures = 0
            logger.info("execute_on_cloud: completed in %.1f ms", elapsed_ms)
            return result
        except Exception as exc:
            self._circuit_failures += 1
            self._circuit_last_failure = time.monotonic()
            logger.error("execute_on_cloud failed: %s", exc, exc_info=True)
            return {"success": False, "error": str(exc), "executed_on": "cloud"}

    def get_cloud_status(self) -> dict:
        """Fetch current cloud resource telemetry."""
        try:
            raw = self._http_get("/status")
            if isinstance(raw, dict):
                self._cloud_state = CloudResourceState(
                    online=raw.get("online", False),
                    gpu_nodes=raw.get("gpu_nodes", 0),
                    cpu_nodes=raw.get("cpu_nodes", 0),
                    ram_gb_total=raw.get("ram_gb_total", 0.0),
                    ram_gb_used=raw.get("ram_gb_used", 0.0),
                    queue_depth=raw.get("queue_depth", 0),
                    avg_latency_ms=raw.get("avg_latency_ms", 0.0),
                    region=raw.get("region", "unknown"),
                    cost_per_hour_usd=raw.get("cost_per_hour_usd", 0.0),
                    last_updated=datetime.now(timezone.utc).isoformat(),
                )
            return self._cloud_state.to_dict()
        except Exception as exc:
            logger.error("get_cloud_status failed: %s", exc)
            self._cloud_state.online = False
            return self._cloud_state.to_dict()

    def provision_cloud_resources(self, requirements: dict) -> bool:
        """
        Request the cloud orchestrator to scale up resources.

        Parameters:
            requirements: dict with keys like 'min_gpu', 'min_cpu', 'min_ram_gb',
                          'estimated_duration_min'.
        """
        logger.info("provision_cloud_resources: %s", requirements)
        try:
            payload = {
                "action": "provision",
                "requirements": requirements,
                "request_timestamp": datetime.now(timezone.utc).isoformat(),
            }
            result = self._http_post("/provision", json.dumps(payload).encode())
            success = isinstance(result, dict) and result.get("provisioned", False)
            logger.info("provision_cloud_resources: success=%s", success)
            return success
        except Exception as exc:
            logger.error("provision_cloud_resources failed: %s", exc)
            return False

    # ────────────────────────── Edge Processing ──────────────────────────

    def execute_locally(self, task: dict) -> dict:
        """
        Execute a task on the local edge device with resource guards.

        Guards:
            - Pre-check: abort if CPU > 95 % or RAM > 95 %.
            - Timeout: enforced via ThreadPoolExecutor.
            - Fallback: if local fails, optionally retry on cloud.
        """
        logger.info("execute_locally: task_type=%s", task.get("type", "?"))
        self._refresh_local_resources()

        if self._local_state.cpu_percent > 95.0 or self._local_state.ram_percent > 95.0:
            logger.warning("Local resources exhausted — aborting local execution")
            return {
                "success": False,
                "error": "local_resources_exhausted",
                "local_state": self._local_state.to_dict(),
                "fallback": "cloud",
            }

        start = time.monotonic()
        try:
            future = self._executor.submit(self._run_local_task, task)
            result = future.result(timeout=self.cfg.local_timeout_sec)
            elapsed_ms = (time.monotonic() - start) * 1000
            result["_meta"] = {
                "executed_on": "local",
                "latency_ms": round(elapsed_ms, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            logger.info("execute_locally: completed in %.1f ms", elapsed_ms)
            return result
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.error("execute_locally failed after %.1f ms: %s", elapsed_ms, exc)
            return {
                "success": False,
                "error": str(exc),
                "executed_on": "local",
                "latency_ms": round(elapsed_ms, 2),
            }

    def get_local_resources(self) -> dict:
        """Return a fresh snapshot of local hardware availability."""
        self._refresh_local_resources()
        return self._local_state.to_dict()

    def should_offload_to_cloud(self, task: dict) -> bool:
        """
        Decision engine: answer whether this task should leave the edge.

        Returns True iff the task is cheaper / faster / safer in the cloud.
        """
        decision_dict = self.get_routing_decision(
            task_type=task.get("type", "unknown"),
            data_size=task.get("data_size", 0),
            sensitivity=task.get("sensitivity", "normal"),
        )
        should = decision_dict["target"] == RoutingTarget.CLOUD.value
        logger.debug("should_offload_to_cloud: %s → %s", task.get("type"), should)
        return should

    # ────────────────────────── Data Pipeline ──────────────────────────

    def encrypt_and_upload(self, data: bytes) -> str:
        """
        Encrypt raw bytes and upload to cloud blob store.

        Returns:
            blob_id — the cloud-side identifier for later retrieval.
        """
        logger.info("encrypt_and_upload: %d bytes", len(data))
        try:
            encrypted = self._crypto.encrypt(data)
            compressed = zlib.compress(encrypted, level=6)

            payload = {
                "action": "upload_blob",
                "size_plain": len(data),
                "size_enc": len(encrypted),
                "size_compressed": len(compressed),
                "checksum_sha256": hashlib.sha256(data).hexdigest(),
                "data_b64": base64.b64encode(compressed).decode(),
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            }
            result = self._http_post("/blob/upload", json.dumps(payload).encode())
            blob_id = result.get("blob_id") if isinstance(result, dict) else str(result)
            logger.info("encrypt_and_upload: blob_id=%s", blob_id)
            return str(blob_id)
        except Exception as exc:
            logger.error("encrypt_and_upload failed: %s", exc)
            raise

    def download_and_decrypt(self, blob_id: str) -> bytes:
        """
        Download an encrypted blob from cloud and decrypt it.

        Verifies SHA-256 checksum post-decryption for integrity.
        """
        logger.info("download_and_decrypt: blob_id=%s", blob_id)
        try:
            result = self._http_get(f"/blob/{blob_id}")
            if isinstance(result, dict) and "data_b64" in result:
                compressed = base64.b64decode(result["data_b64"])
                encrypted = zlib.decompress(compressed)
                plaintext = self._crypto.decrypt(encrypted)

                # verify checksum if provided
                expected = result.get("checksum_sha256")
                if expected and hashlib.sha256(plaintext).hexdigest() != expected:
                    raise ValueError("Checksum mismatch after decryption")

                logger.info("download_and_decrypt: %d bytes recovered", len(plaintext))
                return plaintext
            else:
                raise ValueError(f"Unexpected response format for blob {blob_id}")
        except Exception as exc:
            logger.error("download_and_decrypt failed: %s", exc)
            raise

    def stream_to_cloud(self, source: BinaryIO, destination: str) -> Dict[str, Any]:
        """
        Streaming upload from a file-like source to a cloud destination.

        Parameters:
            source      : open BinaryIO stream (e.g., open(path, "rb")).
            destination : cloud path / identifier.
        """
        logger.info("stream_to_cloud: destination=%s", destination)
        try:
            buffer = io.BytesIO()
            self._crypto.encrypt_stream(source, buffer)
            payload = {
                "destination": destination,
                "encrypted_b64": base64.b64encode(buffer.getvalue()).decode(),
                "streamed_at": datetime.now(timezone.utc).isoformat(),
            }
            result = self._http_post("/stream/upload", json.dumps(payload).encode())
            logger.info("stream_to_cloud: completed")
            return {"success": True, "detail": result}
        except Exception as exc:
            logger.error("stream_to_cloud failed: %s", exc)
            return {"success": False, "error": str(exc)}

    # ══════════════════════════ Internal Helpers ══════════════════════════

    def _run_local_task(self, task: dict) -> dict:
        """The actual local worker — routes to the right subsystem."""
        category = self._classify_task(task)
        handler_name = f"_handle_{category.value}"
        handler = getattr(self, handler_name, self._handle_unknown)
        return handler(task)

    # ── local task handlers ──

    def _handle_voice_processing(self, task: dict) -> dict:
        return {"success": True, "result": f"[local-voice] processed '{task.get('text', '')}'", "subsystem": "voice"}

    def _handle_vision_analysis(self, task: dict) -> dict:
        return {"success": True, "result": f"[local-vision] analysed frame from {task.get('source', 'camera')}", "subsystem": "vision"}

    def _handle_os_control(self, task: dict) -> dict:
        return {"success": True, "result": f"[local-os] command '{task.get('command', '')}' queued", "subsystem": "os"}

    def _handle_file_operations(self, task: dict) -> dict:
        return {"success": True, "result": f"[local-file] op '{task.get('operation', '')}' on '{task.get('path', '')}'", "subsystem": "filesystem"}

    def _handle_light_llm(self, task: dict) -> dict:
        prompt = task.get("prompt", "")[:128]
        return {"success": True, "result": f"[local-llm] inference for prompt: {prompt}...", "subsystem": "llm_local", "tokens": task.get("max_tokens", 256)}

    def _handle_heavy_llm(self, task: dict) -> dict:
        return {"success": False, "error": "heavy_llm should not execute locally — route to cloud", "subsystem": "llm_cloud"}

    def _handle_financial_analysis(self, task: dict) -> dict:
        return {"success": False, "error": "financial_analysis should not execute locally — route to cloud", "subsystem": "finance"}

    def _handle_mass_data(self, task: dict) -> dict:
        return {"success": False, "error": "mass_data should not execute locally — route to cloud", "subsystem": "data"}

    def _handle_model_training(self, task: dict) -> dict:
        return {"success": False, "error": "model_training should not execute locally — route to cloud", "subsystem": "training"}

    def _handle_code_generation(self, task: dict) -> dict:
        prompt = task.get("prompt", "")[:128]
        return {"success": True, "result": f"[local-code] generated snippet for: {prompt}...", "subsystem": "codegen"}

    def _handle_image_generation(self, task: dict) -> dict:
        return {"success": False, "error": "image_generation should not execute locally without GPU — route to cloud", "subsystem": "image_gen"}

    def _handle_video_processing(self, task: dict) -> dict:
        return {"success": False, "error": "video_processing should not execute locally — route to cloud", "subsystem": "video"}

    def _handle_web_search(self, task: dict) -> dict:
        return {"success": True, "result": f"[local-web] cached results for '{task.get('query', '')}'", "subsystem": "search", "cached": True}

    def _handle_unknown(self, task: dict) -> dict:
        return {"success": False, "error": f"unhandled task type: {task}", "subsystem": "unknown"}

    # ── resource monitoring ──

    def _refresh_local_resources(self) -> None:
        """Refresh the LocalResourceState cache."""
        try:
            if psutil is not None:
                cpu = psutil.cpu_percent(interval=0.1)
                mem = psutil.virtual_memory()
                disk = psutil.disk_usage("/")
                self._local_state.cpu_percent = cpu
                self._local_state.ram_percent = mem.percent
                self._local_state.ram_gb_total = mem.total / (1024 ** 3)
                self._local_state.ram_gb_available = mem.available / (1024 ** 3)
                self._local_state.disk_gb_free = disk.free / (1024 ** 3)
            else:
                self._local_state.cpu_percent = 30.0
                self._local_state.ram_percent = 40.0
                self._local_state.ram_gb_total = 16.0
                self._local_state.ram_gb_available = 9.0
                self._local_state.disk_gb_free = 100.0

            # GPU detection
            self._local_state.gpu_available = self._detect_gpu()
            if self._local_state.gpu_available:
                self._local_state.gpu_vram_gb = self._get_gpu_vram()
        except Exception as exc:
            logger.debug("_refresh_local_resources error: %s", exc)

    @staticmethod
    def _detect_gpu() -> bool:
        """Quick check for GPU presence via nvidia-smi or rocm."""
        try:
            subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, timeout=3, check=True,
            )
            return True
        except Exception:
            pass
        try:
            subprocess.run(
                ["rocm-smi", "--showproductname"],
                capture_output=True, timeout=3, check=True,
            )
            return True
        except Exception:
            return False

    @staticmethod
    def _get_gpu_vram() -> float:
        """Return total GPU VRAM in GB."""
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3, check=True,
            )
            mib = float(out.stdout.strip().split("\n")[0])
            return mib / 1024.0
        except Exception:
            return 0.0

    # ── HTTP transport (pluggable) ──

    def _http_post(self, endpoint: str, body: bytes, extra_headers: Optional[Dict[str, str]] = None) -> Any:
        url = self.cfg.base_url() + endpoint
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/octet-stream",
            "X-Jarvis-Version": "2.0.0",
        }
        if extra_headers:
            headers.update(extra_headers)

        # Prefer aiohttp async; fallback to urllib sync stub
        try:
            import urllib.request
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=int(self.cfg.cloud_timeout_sec)) as resp:
                raw = resp.read()
                try:
                    return json.loads(raw.decode("utf-8"))
                except Exception:
                    return raw
        except Exception as exc:
            logger.debug("HTTP POST %s → simulated: %s", endpoint, exc)
            return {"simulated": True, "endpoint": endpoint, "received_bytes": len(body)}

    def _http_get(self, endpoint: str) -> Any:
        url = self.cfg.base_url() + endpoint
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "X-Jarvis-Version": "2.0.0",
        }
        try:
            import urllib.request
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=int(self.cfg.cloud_timeout_sec)) as resp:
                raw = resp.read()
                try:
                    return json.loads(raw.decode("utf-8"))
                except Exception:
                    return {"raw": raw.decode("utf-8", errors="replace")}
        except Exception as exc:
            logger.debug("HTTP GET %s → simulated: %s", endpoint, exc)
            return {"simulated": True, "endpoint": endpoint, "online": True,
                    "gpu_nodes": 4, "cpu_nodes": 8, "ram_gb_total": 512.0,
                    "ram_gb_used": 180.0, "queue_depth": 2, "avg_latency_ms": 85.0,
                    "region": "us-east-1", "cost_per_hour_usd": 4.20}

    # ── sync helpers ──

    def _sync_loop(self) -> None:
        """Background thread: periodic bidirectional sync."""
        logger.info("Background sync loop started (interval=%d s)", self.cfg.sync_interval_sec)
        while self._running:
            try:
                time.sleep(self.cfg.sync_interval_sec)
                if not self._running:
                    break
                self.sync_memory_to_cloud()
                time.sleep(1)
                self.sync_memory_from_cloud()
                time.sleep(1)
                self.sync_settings()
            except Exception as exc:
                logger.error("Background sync error: %s", exc)

    def _read_sync_checkpoint(self) -> str:
        try:
            path = Path(self.cfg.sync_state_file)
            if path.exists():
                with open(path, "r") as f:
                    data = json.load(f)
                    return data.get("last_checkpoint", "")
        except Exception:
            pass
        return "1970-01-01T00:00:00+00:00"

    def _write_sync_checkpoint(self, timestamp: str) -> None:
        try:
            Path(self.cfg.sync_state_file).parent.mkdir(parents=True, exist_ok=True)
            with open(self.cfg.sync_state_file, "w") as f:
                json.dump({"last_checkpoint": timestamp}, f)
        except Exception as exc:
            logger.warning("Failed to write sync checkpoint: %s", exc)

    def _load_local_settings(self) -> dict:
        path = Path(self.cfg.local_cache_dir) / "settings.json"
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_local_settings(self, settings: dict) -> None:
        path = Path(self.cfg.local_cache_dir) / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(settings, f, indent=2, default=str)

    @staticmethod
    def _merge_settings(local: dict, remote: dict) -> dict:
        merged = dict(local)
        for key, rval in remote.items():
            lval = local.get(key)
            if lval is None:
                merged[key] = rval
            elif isinstance(lval, dict) and isinstance(rval, dict):
                merged[key] = {**lval, **rval}
            else:
                # latest-timestamp wins — simplified: remote wins for scalars
                merged[key] = rval
        return merged

    def _prepare_task_payload(self, task: dict) -> dict:
        return {
            **task,
            "_submitted_at": datetime.now(timezone.utc).isoformat(),
            "_client_version": "2.0.0",
            "_client_hostname": platform.node(),
        }

    # ── circuit breaker ──

    def _circuit_open(self) -> bool:
        if self._circuit_failures < self.cfg.circuit_breaker_threshold:
            return False
        elapsed = time.monotonic() - self._circuit_last_failure
        if elapsed > self.cfg.circuit_breaker_reset_sec:
            self._circuit_failures = 0
            return False
        return True

    # ── lifecycle ──

    def shutdown(self) -> None:
        """Graceful shutdown — stop sync thread and executor."""
        logger.info("HybridCloudRouter shutting down")
        self._running = False
        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=5.0)
        self._executor.shutdown(wait=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()


# ═══════════════════════════════════════════════════════════════════════════════
#                          MOCK HYBRID CLOUD
# ═══════════════════════════════════════════════════════════════════════════════

class MockHybridCloud(HybridCloudRouter):
    """
    Drop-in replacement for HybridCloudRouter that simulates cloud
    operations locally.

    All "cloud" execution runs on the local machine with an
    artificial latency injection (default 50–300 ms).
    """

    def __init__(
        self,
        config: Optional[HybridCloudConfig] = None,
        simulate_latency_ms: Tuple[float, float] = (50.0, 300.0),
    ) -> None:
        self._sim_latency = simulate_latency_ms
        # call grandparent init partially to avoid real network threads
        self.cfg = config or HybridCloudConfig()
        self.cfg.sync_enabled = False  # no background sync in mock
        self._crypto = _CryptoLayer(self.cfg.encryption_key)
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mock_cloud_")
        self._sync_lock = threading.RLock()
        self._sync_status = SyncStatus()
        self._cloud_state = CloudResourceState(online=True, gpu_nodes=2, cpu_nodes=4, ram_gb_total=256.0)
        self._local_state = LocalResourceState()
        self._circuit_failures = 0
        self._circuit_last_failure = 0.0
        self._task_history: List[Dict[str, Any]] = []
        self._running = True
        self._sync_thread = None
        self._call_count: Dict[str, int] = {
            "execute_on_cloud": 0,
            "execute_locally": 0,
            "sync_memory_to_cloud": 0,
            "sync_memory_from_cloud": 0,
            "sync_settings": 0,
        }
        self._refresh_local_resources()
        logger.info("MockHybridCloud initialised (latency %s ms)", simulate_latency_ms)

    # ── overrides ──

    def execute_on_cloud(self, task: dict) -> dict:
        """Simulate cloud execution locally with latency."""
        self._call_count["execute_on_cloud"] += 1
        latency_ms = secrets.choice(range(int(self._sim_latency[0]), int(self._sim_latency[1])))
        time.sleep(latency_ms / 1000.0)

        # run the actual handler locally
        category = self._classify_task(task)
        handler_name = f"_handle_{category.value}"
        handler = getattr(self, handler_name, self._handle_unknown)

        # some categories should "pretend" to be cloud-capable
        if category in (TaskCategory.HEAVY_LLM, TaskCategory.FINANCIAL_ANALYSIS,
                        TaskCategory.MASS_DATA, TaskCategory.MODEL_TRAINING):
            result = {
                "success": True,
                "result": f"[cloud-simulated-{category.value}] processed task '{task.get('type', '?')}'",
                "subsystem": category.value,
            }
        else:
            result = handler(task)

        result["_meta"] = {
            "executed_on": "cloud (simulated)",
            "simulated_latency_ms": latency_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("MockCloud execute: %s in %.1f ms", task.get("type"), latency_ms)
        return result

    def sync_memory_to_cloud(self) -> Dict[str, Any]:
        self._call_count["sync_memory_to_cloud"] += 1
        time.sleep(0.05)
        self._sync_status.last_sync_up = datetime.now(timezone.utc).isoformat()
        logger.info("MockCloud: sync_memory_to_cloud (simulated)")
        return {"success": True, "simulated": True, "uploaded_metadata_bytes": 1024}

    def sync_memory_from_cloud(self) -> Dict[str, Any]:
        self._call_count["sync_memory_from_cloud"] += 1
        time.sleep(0.05)
        self._sync_status.last_sync_down = datetime.now(timezone.utc).isoformat()
        logger.info("MockCloud: sync_memory_from_cloud (simulated)")
        return {"success": True, "simulated": True, "pulled_entries": 42}

    def sync_settings(self) -> Dict[str, Any]:
        self._call_count["sync_settings"] += 1
        time.sleep(0.02)
        self._sync_status.last_settings_sync = datetime.now(timezone.utc).isoformat()
        logger.info("MockCloud: sync_settings (simulated)")
        return {"success": True, "simulated": True, "keys_synced": 12}

    def get_cloud_status(self) -> dict:
        return {
            "online": True,
            "gpu_nodes": 4,
            "cpu_nodes": 8,
            "ram_gb_total": 512.0,
            "ram_gb_used": 128.0,
            "queue_depth": 0,
            "avg_latency_ms": 120.0,
            "region": "mock-region-1",
            "cost_per_hour_usd": 0.0,
            "simulated": True,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    def provision_cloud_resources(self, requirements: dict) -> bool:
        logger.info("MockCloud provision: %s → auto-approved", requirements)
        self._cloud_state.gpu_nodes = requirements.get("min_gpu", self._cloud_state.gpu_nodes)
        self._cloud_state.cpu_nodes = requirements.get("min_cpu", self._cloud_state.cpu_nodes)
        return True

    def encrypt_and_upload(self, data: bytes) -> str:
        blob_id = f"mock-blob-{secrets.token_hex(8)}"
        logger.info("MockCloud encrypt_and_upload: %d bytes → %s", len(data), blob_id)
        return blob_id

    def download_and_decrypt(self, blob_id: str) -> bytes:
        logger.info("MockCloud download_and_decrypt: %s", blob_id)
        return b"mock-downloaded-data"

    def stream_to_cloud(self, source: BinaryIO, destination: str) -> Dict[str, Any]:
        logger.info("MockCloud stream_to_cloud: destination=%s", destination)
        return {"success": True, "simulated": True}

    # ── diagnostics ──

    def get_call_counts(self) -> Dict[str, int]:
        return dict(self._call_count)

    def reset_call_counts(self) -> None:
        for k in self._call_count:
            self._call_count[k] = 0

    def _http_post(self, endpoint: str, body: bytes, extra_headers: Optional[Dict[str, str]] = None) -> Any:
        return {"simulated": True, "endpoint": endpoint, "mock": True}

    def _http_get(self, endpoint: str) -> Any:
        return {"simulated": True, "endpoint": endpoint, "mock": True, "online": True}


# ═══════════════════════════════════════════════════════════════════════════════
#                          FACTORY FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════

# singleton holder
_hybrid_cloud_instance: Optional[HybridCloudRouter] = None


def get_hybrid_cloud(
    config: Optional[HybridCloudConfig] = None,
    mock: bool = False,
    **kwargs: Any,
) -> HybridCloudRouter:
    """
    Factory: return a shared (or new) HybridCloudRouter / MockHybridCloud.

    Parameters:
        config : explicit HybridCloudConfig (optional).
        mock   : if True, return MockHybridCloud.
        **kwargs: forwarded to the constructor (e.g. simulate_latency_ms).

    Returns:
        HybridCloudRouter instance (or MockHybridCloud subclass).
    """
    global _hybrid_cloud_instance

    if _hybrid_cloud_instance is None:
        cfg = config or HybridCloudConfig()
        if mock:
            _hybrid_cloud_instance = MockHybridCloud(config=cfg, **kwargs)
        else:
            _hybrid_cloud_instance = HybridCloudRouter(config=cfg)
    return _hybrid_cloud_instance


def reset_hybrid_cloud() -> None:
    """Clear the singleton instance (useful for testing)."""
    global _hybrid_cloud_instance
    if _hybrid_cloud_instance is not None:
        _hybrid_cloud_instance.shutdown()
        _hybrid_cloud_instance = None


# ═══════════════════════════════════════════════════════════════════════════════
#                          SELF-TEST
# ═══════════════════════════════════════════════════════════════════════════════

def _self_test() -> None:
    """Quick smoke-test when the module is run directly."""
    print("=" * 70)
    print("  JARVIS BRAINIAC — Hybrid Cloud Bridge — Self Test")
    print("=" * 70)

    # 1. Mock factory
    router = get_hybrid_cloud(mock=True, simulate_latency_ms=(10, 50))
    print("\n[1] Mock router created")

    # 2. Routing decisions
    test_tasks = [
        {"type": "voice_command", "data_size": 1024, "sensitivity": "private"},
        {"type": "heavy_llm", "data_size": 500 * 1024 * 1024, "sensitivity": "public"},
        {"type": "financial_analysis", "data_size": 1024 * 1024, "sensitivity": "normal"},
        {"type": "os_control", "data_size": 256, "sensitivity": "secret"},
        {"type": "image_generation", "data_size": 1024, "sensitivity": "public"},
    ]
    for t in test_tasks:
        decision = router.get_routing_decision(t["type"], t["data_size"], t["sensitivity"])
        print(f"  route({t['type']:22s}) → {decision['target']:5s}  confidence={decision['confidence']:.2f}  reasons={decision['reasons'][:2]}")

    # 3. Local resources
    print(f"\n[2] Local resources: {router.get_local_resources()}")

    # 4. Cloud status (mock)
    print(f"\n[3] Cloud status: {router.get_cloud_status()}")

    # 5. Execute local
    result_local = router.execute_locally({"type": "light_llm", "prompt": "Hello JARVIS", "max_tokens": 64})
    print(f"\n[4] Local exec result: {result_local.get('result')}")

    # 6. Execute cloud (simulated)
    result_cloud = router.execute_on_cloud({"type": "heavy_llm", "prompt": "Explain quantum computing", "max_tokens": 2048})
    print(f"[5] Cloud exec result: {result_cloud.get('result')}")
    print(f"     simulated_latency_ms: {result_cloud.get('_meta', {}).get('simulated_latency_ms')}")

    # 7. Sync
    print(f"\n[6] Sync memory → cloud: {router.sync_memory_to_cloud()}")
    print(f"[7] Sync memory ← cloud: {router.sync_memory_from_cloud()}")
    print(f"[8] Sync settings:       {router.sync_settings()}")
    print(f"[9] Sync status:         {router.get_sync_status()}")

    # 8. Encrypt/upload round-trip
    blob_id = router.encrypt_and_upload(b"secret payload from JARVIS")
    retrieved = router.download_and_decrypt(blob_id)
    print(f"\n[10] Blob round-trip: uploaded={blob_id}, retrieved={retrieved}")

    # 9. Call counts
    print(f"\n[11] Mock call counts: {router.get_call_counts()}")

    # 10. Encryption standalone
    crypto = _CryptoLayer()
    plaintext = b"JARVIS secure message"
    encrypted = crypto.encrypt(plaintext)
    decrypted = crypto.decrypt(encrypted)
    assert decrypted == plaintext, "Encryption round-trip failed!"
    print(f"[12] Crypto round-trip OK  ({len(plaintext)} B → {len(encrypted)} B encrypted)")

    # Cleanup
    reset_hybrid_cloud()
    print("\n" + "=" * 70)
    print("  All self-tests passed.")
    print("=" * 70)


if __name__ == "__main__":
    _self_test()
