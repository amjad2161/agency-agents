"""
LocalSend Bridge — Python Integration Adapter for LocalSend
============================================================

A programmatic interface to discover, send, and receive files with
LocalSend-compatible devices on the local network.

Implements the LocalSend REST API (Protocol v2.1) with partial v3 support:
  - Discovery: UDP multicast + HTTP scan fallback
  - Upload API: prepare-upload -> upload -> cancel
  - Download API: prepare-download -> download
  - Optional built-in HTTP receiver to accept files from other LocalSend peers.

Author:     Agency Runtime (auto-generated)
Reference:  https://github.com/localsend/localsend
            https://github.com/localsend/protocol
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import mimetypes
import os
import random
import socket
import string
import struct
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("localsend_bridge")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PORT = 53317
MULTICAST_GROUP = "224.0.0.167"
MULTICAST_PORT = 53317
DISCOVERY_TIMEOUT = 2.0  # seconds
API_PREFIX_V2 = "/api/localsend/v2"
API_PREFIX_V3 = "/api/localsend/v3"
FALLBACK_PROTOCOL_VERSION = "1.0"
CURRENT_PROTOCOL_VERSION = "2.1"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DeviceType(Enum):
    mobile = "mobile"
    desktop = "desktop"
    web = "web"
    headless = "headless"
    server = "server"


class ProtocolType(Enum):
    http = "http"
    https = "https"


class FileType(Enum):
    image = "image"
    video = "video"
    pdf = "pdf"
    text = "text"
    apk = "apk"
    other = "other"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class FileMetadata:
    modified: Optional[str] = None  # ISO-8601
    accessed: Optional[str] = None  # ISO-8601

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        if self.modified:
            d["modified"] = self.modified
        if self.accessed:
            d["accessed"] = self.accessed
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FileMetadata:
        return cls(modified=data.get("modified"), accessed=data.get("accessed"))


@dataclass
class FileDto:
    id: str
    file_name: str
    size: int
    file_type: FileType = FileType.other
    hash: Optional[str] = None  # sha256
    preview: Optional[str] = None  # base64
    metadata: Optional[FileMetadata] = None

    def mime_type(self) -> str:
        return _file_type_to_mime(self.file_type, self.file_name)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "fileName": self.file_name,
            "size": self.size,
            "fileType": self.mime_type(),
        }
        if self.hash:
            d["hash"] = self.hash
        if self.preview:
            d["preview"] = self.preview
        if self.metadata:
            d["metadata"] = self.metadata.to_dict()
        return d

    @classmethod
    def from_path(cls, path: Path, file_id: Optional[str] = None) -> FileDto:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(p)
        ft = _mime_to_file_type(mimetypes.guess_type(p.name)[0] or "")
        sha = _sha256_file(p)
        return cls(
            id=file_id or str(uuid.uuid4()),
            file_name=p.name,
            size=p.stat().st_size,
            file_type=ft,
            hash=sha,
            metadata=FileMetadata(
                modified=datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
                accessed=datetime.fromtimestamp(p.stat().st_atime, tz=timezone.utc).isoformat(),
            ),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FileDto:
        raw_ft = data.get("fileType", "")
        if "/" in raw_ft:
            ft = _mime_to_file_type(raw_ft)
        else:
            ft = FileType(raw_ft) if raw_ft in [e.value for e in FileType] else FileType.other
        meta = data.get("metadata")
        return cls(
            id=data["id"],
            file_name=data["fileName"],
            size=data["size"],
            file_type=ft,
            hash=data.get("hash"),
            preview=data.get("preview"),
            metadata=FileMetadata.from_dict(meta) if meta else None,
        )


@dataclass
class DeviceInfo:
    alias: str
    version: str = CURRENT_PROTOCOL_VERSION
    device_model: Optional[str] = None
    device_type: DeviceType = DeviceType.desktop
    fingerprint: str = ""
    port: int = DEFAULT_PORT
    protocol: ProtocolType = ProtocolType.http
    download: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "alias": self.alias,
            "version": self.version,
            "deviceType": self.device_type.value,
            "fingerprint": self.fingerprint,
            "port": self.port,
            "protocol": self.protocol.value,
            "download": self.download,
        }
        if self.device_model:
            d["deviceModel"] = self.device_model
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> DeviceInfo:
        return cls(
            alias=data["alias"],
            version=data.get("version", FALLBACK_PROTOCOL_VERSION),
            device_model=data.get("deviceModel"),
            device_type=DeviceType(data.get("deviceType", "desktop")),
            fingerprint=data.get("fingerprint", ""),
            port=data.get("port", DEFAULT_PORT),
            protocol=ProtocolType(data.get("protocol", "http")),
            download=data.get("download", False),
        )


@dataclass
class Device:
    """Discovered or registered remote device."""

    ip: str
    port: int
    alias: str
    version: str = CURRENT_PROTOCOL_VERSION
    device_model: Optional[str] = None
    device_type: DeviceType = DeviceType.desktop
    fingerprint: str = ""
    https: bool = False
    download: bool = False
    discovery_method: str = "unknown"

    @property
    def base_url(self) -> str:
        proto = "https" if self.https else "http"
        return f"{proto}://{self.ip}:{self.port}"

    @classmethod
    def from_info_dict(cls, ip: str, port: int, data: Dict[str, Any], https: bool = False) -> Device:
        return cls(
            ip=ip,
            port=port,
            alias=data.get("alias", "Unknown"),
            version=data.get("version", FALLBACK_PROTOCOL_VERSION),
            device_model=data.get("deviceModel"),
            device_type=DeviceType(data.get("deviceType", "desktop")),
            fingerprint=data.get("fingerprint", ""),
            https=https,
            download=data.get("download", False),
        )


@dataclass
class PrepareUploadRequest:
    info: DeviceInfo
    files: Dict[str, FileDto]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "info": self.info.to_dict(),
            "files": {k: v.to_dict() for k, v in self.files.items()},
        }


@dataclass
class PrepareUploadResponse:
    session_id: str
    files: Dict[str, str]  # file_id -> token

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PrepareUploadResponse:
        return cls(session_id=data["sessionId"], files=data.get("files", {}))


@dataclass
class PrepareDownloadResponse:
    info: DeviceInfo
    session_id: str
    files: Dict[str, FileDto]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PrepareDownloadResponse:
        return cls(
            info=DeviceInfo.from_dict(data["info"]),
            session_id=data["sessionId"],
            files={k: FileDto.from_dict(v) for k, v in data.get("files", {}).items()},
        )


# ---------------------------------------------------------------------------
# Internal Utilities
# ---------------------------------------------------------------------------

def _file_type_to_mime(ft: FileType, file_name: str = "") -> str:
    if ft == FileType.image:
        return "image/jpeg"
    if ft == FileType.video:
        return "video/mp4"
    if ft == FileType.pdf:
        return "application/pdf"
    if ft == FileType.text:
        return "text/plain"
    if ft == FileType.apk:
        return "application/vnd.android.package-archive"
    guessed = mimetypes.guess_type(file_name)[0]
    return guessed or "application/octet-stream"


def _mime_to_file_type(mime: str) -> FileType:
    if mime.startswith("image/"):
        return FileType.image
    if mime.startswith("video/"):
        return FileType.video
    if mime == "application/pdf":
        return FileType.pdf
    if mime.startswith("text/"):
        return FileType.text
    if mime == "application/vnd.android.package-archive":
        return FileType.apk
    return FileType.other


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _random_fingerprint() -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=32))


def _make_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
    session.mount("http://", HTTPAdapter(max_retries=retries))
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


def _verify_or_skip(response: requests.Response, verify_cert: bool) -> None:
    """LocalSend uses self-signed certs. In HTTP mode we skip verification.
    In HTTPS mode we could verify the fingerprint, but for this adapter
    we rely on the caller to supply `verify=False` when needed."""
    pass


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

class LocalSendDiscovery:
    """Discovers LocalSend devices on the local network via multicast UDP
    and optional HTTP subnet scanning."""

    def __init__(self, own_port: int = DEFAULT_PORT, fingerprint: Optional[str] = None):
        self.own_port = own_port
        self.fingerprint = fingerprint or _random_fingerprint()
        self._devices: Dict[str, Device] = {}
        self._lock = threading.Lock()
        self._listen_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ---------------------------- Public API -------------------------------

    def scan_once(self, timeout: float = DISCOVERY_TIMEOUT) -> List[Device]:
        """Send a single multicast announcement and collect responses."""
        self._send_multicast_announcement()
        time.sleep(0.1)
        return self._collect_udp_responses(timeout)

    def start_listener(
        self,
        alias: str,
        device_type: DeviceType = DeviceType.server,
        device_model: Optional[str] = None,
        on_device_found: Optional[Callable[[Device], None]] = None,
    ) -> None:
        """Start a background thread that listens for multicast announcements
        and responds to them so other peers can discover us."""
        if self._listen_thread and self._listen_thread.is_alive():
            return
        self._stop_event.clear()
        self._listen_thread = threading.Thread(
            target=self._listener_loop,
            args=(alias, device_type, device_model, on_device_found),
            daemon=True,
        )
        self._listen_thread.start()

    def stop_listener(self) -> None:
        self._stop_event.set()
        if self._listen_thread:
            self._listen_thread.join(timeout=2.0)

    def get_devices(self) -> List[Device]:
        with self._lock:
            return list(self._devices.values())

    def http_scan_subnet(
        self,
        subnet: str = "192.168.1",
        start: int = 1,
        end: int = 254,
        port: int = DEFAULT_PORT,
        timeout: float = 1.5,
    ) -> List[Device]:
        """Fallback HTTP scan across a /24 subnet."""
        found: List[Device] = []
        for i in range(start, end + 1):
            ip = f"{subnet}.{i}"
            try:
                dev = self._probe_http_info(ip, port, timeout)
                if dev:
                    found.append(dev)
            except Exception as e:
                logger.debug("HTTP probe failed for %s: %s", ip, e)
        return found

    # ---------------------------- Internals -------------------------------

    def _send_multicast_announcement(self) -> None:
        payload = json.dumps(
            {
                "alias": "LocalSendBridge",
                "deviceModel": "Python",
                "deviceType": DeviceType.server.value,
                "fingerprint": self.fingerprint,
                "announcement": True,
                "port": self.own_port,
                "protocol": "http",
                "download": True,
            }
        )
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack("b", 2))
        sock.settimeout(2.0)
        try:
            sock.sendto(payload.encode("utf-8"), (MULTICAST_GROUP, MULTICAST_PORT))
        finally:
            sock.close()

    def _collect_udp_responses(self, timeout: float) -> List[Device]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", MULTICAST_PORT))
        mreq = struct.pack("4sL", socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(timeout)
        found: Dict[str, Device] = {}
        deadline = time.time() + timeout
        try:
            while time.time() < deadline:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                sock.settimeout(remaining)
                data, addr = sock.recvfrom(2048)
                try:
                    msg = json.loads(data.decode("utf-8"))
                    if msg.get("fingerprint") == self.fingerprint:
                        continue  # ignore self
                    ip = addr[0]
                    port = msg.get("port", DEFAULT_PORT)
                    https = msg.get("protocol", "http") == "https"
                    dev = Device.from_info_dict(ip, port, msg, https=https)
                    dev.discovery_method = "multicast"
                    found[dev.fingerprint] = dev
                except Exception as e:
                    logger.debug("Malformed multicast from %s: %s", addr, e)
        except socket.timeout:
            pass
        finally:
            sock.close()
        return list(found.values())

    def _listener_loop(
        self,
        alias: str,
        device_type: DeviceType,
        device_model: Optional[str],
        on_device_found: Optional[Callable[[Device], None]],
    ) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", MULTICAST_PORT))
        mreq = struct.pack("4sL", socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(1.0)
        while not self._stop_event.is_set():
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            try:
                msg = json.loads(data.decode("utf-8"))
                if msg.get("fingerprint") == self.fingerprint:
                    continue
                announcement = msg.get("announcement", False)
                ip = addr[0]
                port = msg.get("port", DEFAULT_PORT)
                https = msg.get("protocol", "http") == "https"
                # If someone announced, respond with HTTP register + UDP fallback
                if announcement:
                    self._respond_to_peer(ip, port, alias, device_type, device_model, https)
                dev = Device.from_info_dict(ip, port, msg, https=https)
                dev.discovery_method = "multicast"
                with self._lock:
                    self._devices[dev.fingerprint] = dev
                if on_device_found:
                    on_device_found(dev)
            except Exception as e:
                logger.debug("Listener error: %s", e)
        sock.close()

    def _respond_to_peer(
        self,
        ip: str,
        port: int,
        alias: str,
        device_type: DeviceType,
        device_model: Optional[str],
        https: bool,
    ) -> None:
        payload = {
            "alias": alias,
            "version": CURRENT_PROTOCOL_VERSION,
            "deviceModel": device_model,
            "deviceType": device_type.value,
            "fingerprint": self.fingerprint,
            "port": self.own_port,
            "protocol": "https" if https else "http",
            "download": True,
        }
        try:
            proto = "https" if https else "http"
            url = f"{proto}://{ip}:{port}{API_PREFIX_V2}/register"
            requests.post(
                url,
                json=payload,
                timeout=2.0,
                verify=False,  # self-signed certs
            )
        except Exception as e:
            logger.debug("HTTP register response failed to %s: %s", ip, e)

    def _probe_http_info(self, ip: str, port: int, timeout: float) -> Optional[Device]:
        for https in (False, True):
            proto = "https" if https else "http"
            url = f"{proto}://{ip}:{port}{API_PREFIX_V2}/info?fingerprint={self.fingerprint}"
            try:
                resp = requests.get(url, timeout=timeout, verify=False)
                if resp.status_code == 200:
                    data = resp.json()
                    return Device.from_info_dict(ip, port, data, https=https)
            except Exception:
                continue
        return None


# ---------------------------------------------------------------------------
# Client (Sender)
# ---------------------------------------------------------------------------

class LocalSendClient:
    """HTTP client that sends files to a LocalSend receiver or downloads
    files from a LocalSend sender (Download API)."""

    def __init__(self, verify_ssl: bool = False):
        self.session = _make_session()
        self.verify_ssl = verify_ssl
        if not verify_ssl:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # ---------------------------- Upload API -------------------------------

    def prepare_upload(
        self,
        target: Device,
        request: PrepareUploadRequest,
        pin: Optional[str] = None,
    ) -> PrepareUploadResponse:
        """Step 1 of Upload API: negotiate session and get file tokens."""
        params: Dict[str, str] = {}
        if pin:
            params["pin"] = pin
        url = f"{target.base_url}{API_PREFIX_V2}/prepare-upload"
        if params:
            url += "?" + urlencode(params)
        resp = self.session.post(
            url,
            json=request.to_dict(),
            timeout=30.0,
            verify=self.verify_ssl,
        )
        if resp.status_code == 204:
            # No file transfer needed (e.g., text-only). Return empty session.
            return PrepareUploadResponse(session_id="", files={})
        resp.raise_for_status()
        return PrepareUploadResponse.from_dict(resp.json())

    def upload_file(
        self,
        target: Device,
        session_id: str,
        file_id: str,
        token: str,
        file_path: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """Step 2 of Upload API: stream a single file to the receiver.
        Parallel calls are allowed for multiple files."""
        url = (
            f"{target.base_url}{API_PREFIX_V2}/upload"
            f"?sessionId={session_id}&fileId={file_id}&token={token}"
        )
        total = Path(file_path).stat().st_size
        sent = 0

        def _chunked_reader():
            nonlocal sent
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    sent += len(chunk)
                    if progress_callback:
                        progress_callback(sent, total)
                    yield chunk

        resp = self.session.post(
            url,
            data=_chunked_reader(),
            timeout=None,  # large files
            verify=self.verify_ssl,
            headers={"Content-Type": "application/octet-stream"},
        )
        resp.raise_for_status()

    def upload_bytes(
        self,
        target: Device,
        session_id: str,
        file_id: str,
        token: str,
        data: bytes,
    ) -> None:
        """Upload raw bytes instead of a file on disk."""
        url = (
            f"{target.base_url}{API_PREFIX_V2}/upload"
            f"?sessionId={session_id}&fileId={file_id}&token={token}"
        )
        resp = self.session.post(
            url,
            data=data,
            timeout=None,
            verify=self.verify_ssl,
            headers={"Content-Type": "application/octet-stream"},
        )
        resp.raise_for_status()

    def cancel_session(self, target: Device, session_id: str) -> None:
        """Cancel an ongoing upload session on the receiver."""
        url = f"{target.base_url}{API_PREFIX_V2}/cancel?sessionId={session_id}"
        self.session.post(url, timeout=10.0, verify=self.verify_ssl)

    def send_files(
        self,
        target: Device,
        files: List[Path],
        sender_info: DeviceInfo,
        pin: Optional[str] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> PrepareUploadResponse:
        """High-level helper: prepare + upload all files sequentially."""
        file_map = {str(uuid.uuid4()): FileDto.from_path(p) for p in files}
        req = PrepareUploadRequest(info=sender_info, files=file_map)
        prep = self.prepare_upload(target, req, pin=pin)
        for fid, fdto in file_map.items():
            token = prep.files.get(fid)
            if not token:
                logger.warning("File %s was not accepted by receiver", fdto.file_name)
                continue

            def _cb(sent: int, total: int) -> None:
                if progress_callback:
                    progress_callback(fdto.file_name, sent, total)

            self.upload_file(target, prep.session_id, fid, token, Path(fdto.file_name), _cb)
        return prep

    # --------------------------- Download API ------------------------------

    def prepare_download(
        self,
        sender: Device,
        session_id: Optional[str] = None,
        pin: Optional[str] = None,
    ) -> PrepareDownloadResponse:
        """Request metadata list from a sender that is hosting files."""
        params: Dict[str, str] = {}
        if session_id:
            params["sessionId"] = session_id
        if pin:
            params["pin"] = pin
        url = f"{sender.base_url}{API_PREFIX_V2}/prepare-download"
        if params:
            url += "?" + urlencode(params)
        resp = self.session.post(url, timeout=10.0, verify=self.verify_ssl)
        resp.raise_for_status()
        return PrepareDownloadResponse.from_dict(resp.json())

    def download_file(
        self,
        sender: Device,
        session_id: str,
        file_id: str,
        destination: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        """Download a single file from a sender to disk."""
        url = (
            f"{sender.base_url}{API_PREFIX_V2}/download"
            f"?sessionId={session_id}&fileId={file_id}"
        )
        resp = self.session.get(url, stream=True, timeout=None, verify=self.verify_ssl)
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        with open(destination, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)

    def download_bytes(
        self,
        sender: Device,
        session_id: str,
        file_id: str,
    ) -> bytes:
        """Download a single file into memory."""
        url = (
            f"{sender.base_url}{API_PREFIX_V2}/download"
            f"?sessionId={session_id}&fileId={file_id}"
        )
        resp = self.session.get(url, timeout=None, verify=self.verify_ssl)
        resp.raise_for_status()
        return resp.content

    # ---------------------------- v3 Nonce ---------------------------------

    def nonce_exchange(self, target: Device) -> str:
        """v3 protocol nonce exchange. Returns the remote nonce."""
        nonce = os.urandom(32)
        nonce_b64 = base64.b64encode(nonce).decode("ascii")
        url = f"{target.base_url}{API_PREFIX_V3}/nonce"
        resp = self.session.post(url, json={"nonce": nonce_b64}, timeout=10.0, verify=self.verify_ssl)
        resp.raise_for_status()
        return resp.json()["nonce"]


# ---------------------------------------------------------------------------
# Simple HTTP Receiver
# ---------------------------------------------------------------------------

class LocalSendReceiver:
    """A lightweight HTTP server that implements the LocalSend v2 receiver
    endpoints so other LocalSend peers can push files to this process.

    This is intentionally minimal: it handles registration, prepare-upload,
    upload, and cancel. It does NOT implement a GUI or interactive accept/reject
    flow; instead it accepts all incoming files into a configured directory.
    """

    def __init__(
        self,
        alias: str = "PythonBridge",
        port: int = DEFAULT_PORT,
        device_type: DeviceType = DeviceType.server,
        download_dir: Path = Path("./received"),
        pin: Optional[str] = None,
    ):
        self.alias = alias
        self.port = port
        self.device_type = device_type
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.pin = pin
        self.fingerprint = _random_fingerprint()
        self._sessions: Dict[str, Dict[str, str]] = {}  # session_id -> {file_id: token}
        self._session_files: Dict[str, Dict[str, FileDto]] = {}  # session_id -> {file_id: FileDto}
        self._server: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # ---------------------------- Lifecycle --------------------------------

    def start(self) -> None:
        """Start the HTTP receiver in a background thread."""
        if self._server and self._server.is_alive():
            return
        self._stop.clear()
        self._server = threading.Thread(target=self._run_server, daemon=True)
        self._server.start()
        logger.info("LocalSendReceiver started on port %d", self.port)

    def stop(self) -> None:
        self._stop.set()
        # Trigger a dummy request to unblock accept()
        try:
            requests.get(f"http://127.0.0.1:{self.port}/", timeout=1.0)
        except Exception:
            pass
        if self._server:
            self._server.join(timeout=2.0)

    def is_running(self) -> bool:
        return self._server is not None and self._server.is_alive()

    # ---------------------------- Internals --------------------------------

    def _run_server(self) -> None:
        from http.server import BaseHTTPRequestHandler, HTTPServer

        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:
                logger.debug(fmt, *args)

            def _json_response(self, status: int, data: Any) -> None:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode("utf-8"))

            def _read_json(self) -> Dict[str, Any]:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                return json.loads(body.decode("utf-8")) if body else {}

            def do_GET(self) -> None:
                if self.path.startswith(f"{API_PREFIX_V2}/info"):
                    self._json_response(200, {
                        "alias": receiver.alias,
                        "version": CURRENT_PROTOCOL_VERSION,
                        "deviceType": receiver.device_type.value,
                        "fingerprint": receiver.fingerprint,
                        "download": True,
                    })
                elif self.path.startswith(f"{API_PREFIX_V2}/download"):
                    self._handle_download()
                else:
                    self.send_error(404)

            def do_POST(self) -> None:
                if self.path.startswith(f"{API_PREFIX_V2}/register"):
                    self._json_response(200, {
                        "alias": receiver.alias,
                        "version": CURRENT_PROTOCOL_VERSION,
                        "deviceType": receiver.device_type.value,
                        "token": receiver.fingerprint,
                        "has_web_interface": False,
                    })
                elif self.path.startswith(f"{API_PREFIX_V2}/prepare-upload"):
                    self._handle_prepare_upload()
                elif self.path.startswith(f"{API_PREFIX_V2}/upload"):
                    self._handle_upload()
                elif self.path.startswith(f"{API_PREFIX_V2}/cancel"):
                    self._handle_cancel()
                elif self.path.startswith(f"{API_PREFIX_V2}/prepare-download"):
                    self._handle_prepare_download()
                else:
                    self.send_error(404)

            def _handle_prepare_upload(self) -> None:
                data = self._read_json()
                files = data.get("files", {})
                session_id = str(uuid.uuid4())
                tokens = {fid: str(uuid.uuid4()) for fid in files}
                receiver._sessions[session_id] = tokens
                receiver._session_files[session_id] = {
                    fid: FileDto.from_dict(finfo) for fid, finfo in files.items()
                }
                self._json_response(200, {"sessionId": session_id, "files": tokens})

            def _handle_upload(self) -> None:
                import urllib.parse
                parsed = urllib.parse.urlparse(self.path)
                qs = urllib.parse.parse_qs(parsed.query)
                session_id = qs.get("sessionId", [""])[0]
                file_id = qs.get("fileId", [""])[0]
                token = qs.get("token", [""])[0]

                if session_id not in receiver._sessions:
                    self.send_error(403, "Invalid session")
                    return
                if receiver._sessions[session_id].get(file_id) != token:
                    self.send_error(403, "Invalid token")
                    return

                fdto = receiver._session_files[session_id].get(file_id)
                fname = fdto.file_name if fdto else file_id
                dest = receiver.download_dir / fname
                length = int(self.headers.get("Content-Length", 0))
                received = 0
                with open(dest, "wb") as f:
                    while received < length:
                        chunk = self.rfile.read(min(65536, length - received))
                        if not chunk:
                            break
                        f.write(chunk)
                        received += len(chunk)
                logger.info("Received file: %s (%d bytes)", dest, received)
                self.send_response(200)
                self.end_headers()

            def _handle_cancel(self) -> None:
                import urllib.parse
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                session_id = qs.get("sessionId", [""])[0]
                receiver._sessions.pop(session_id, None)
                receiver._session_files.pop(session_id, None)
                self.send_response(200)
                self.end_headers()

            def _handle_prepare_download(self) -> None:
                # Minimal: we only expose files placed in download_dir manually
                # A full implementation would track active send sessions.
                self.send_error(501, "Not fully implemented")

            def _handle_download(self) -> None:
                import urllib.parse
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                session_id = qs.get("sessionId", [""])[0]
                file_id = qs.get("fileId", [""])[0]
                # In a full implementation, look up the file from an active send session.
                self.send_error(501, "Not fully implemented")

        httpd = HTTPServer(("0.0.0.0", self.port), Handler)
        httpd.timeout = 1.0
        while not receiver._stop.is_set():
            try:
                httpd.handle_request()
            except Exception as e:
                logger.debug("Server loop error: %s", e)
        httpd.server_close()


# ---------------------------------------------------------------------------
# Convenience / Scripting API
# ---------------------------------------------------------------------------

class LocalSendBridge:
    """High-level facade combining discovery, client, and receiver."""

    def __init__(
        self,
        alias: str = "PythonBridge",
        port: int = DEFAULT_PORT,
        device_type: DeviceType = DeviceType.server,
        download_dir: Path = Path("./received"),
        pin: Optional[str] = None,
    ):
        self.alias = alias
        self.port = port
        self.device_type = device_type
        self.download_dir = Path(download_dir)
        self.pin = pin
        self.discovery = LocalSendDiscovery(own_port=port)
        self.client = LocalSendClient(verify_ssl=False)
        self.receiver = LocalSendReceiver(
            alias=alias,
            port=port,
            device_type=device_type,
            download_dir=download_dir,
            pin=pin,
        )

    # -------------------------- Lifecycle ----------------------------------

    def start(self) -> None:
        """Start the HTTP receiver and the multicast listener."""
        self.receiver.start()
        self.discovery.start_listener(
            alias=self.alias,
            device_type=self.device_type,
            on_device_found=lambda d: logger.info("Found device: %s @ %s", d.alias, d.ip),
        )

    def stop(self) -> None:
        self.discovery.stop_listener()
        self.receiver.stop()

    # -------------------------- Discovery ----------------------------------

    def scan(self, timeout: float = DISCOVERY_TIMEOUT) -> List[Device]:
        return self.discovery.scan_once(timeout)

    # -------------------------- Send ---------------------------------------

    def send_to(
        self,
        target: Device,
        files: List[Path],
        progress: Optional[Callable[[str, int, int], None]] = None,
    ) -> PrepareUploadResponse:
        sender_info = DeviceInfo(
            alias=self.alias,
            version=CURRENT_PROTOCOL_VERSION,
            device_model="Python",
            device_type=self.device_type,
            fingerprint=self.discovery.fingerprint,
            port=self.port,
            protocol=ProtocolType.http,
            download=False,
        )
        return self.client.send_files(target, files, sender_info, pin=self.pin, progress_callback=progress)

    # -------------------------- Receive ------------------------------------

    def receive_dir(self) -> Path:
        return self.download_dir


# ---------------------------------------------------------------------------
# Standalone execution helper
# ---------------------------------------------------------------------------

def _demo() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    bridge = LocalSendBridge()
    bridge.start()
    try:
        print("Scanning for LocalSend devices...")
        devices = bridge.scan(timeout=3.0)
        for d in devices:
            print(f"  - {d.alias} @ {d.base_url} ({d.device_type.value})")
        if not devices:
            print("No devices found. Make sure LocalSend is running on another device.")
        print(f"\nReceiver running. Files will be saved to: {bridge.receive_dir()}")
        print("Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.stop()
        print("Stopped.")


if __name__ == "__main__":
    _demo()
