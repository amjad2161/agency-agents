"""
ACE-Step UI Bridge — JARVIS Runtime Integration Adapter
========================================================

Provides programmatic access to the ACE-Step UI backend (Express.js API on
:3001) and, optionally, direct access to the underlying ACE-Step Gradio
gateway (:8001).

Intended use-cases:
- Submit AI music generation jobs from agent workflows.
- Poll job status and retrieve resulting audio URLs / file paths.
- Query the local song library, playlists, and user profiles.
- Upload reference audio for cover / repaint / audio2audio tasks.
- Perform health checks and model discovery for orchestration.

External dependency: `requests` (install if not present).

Example::

    bridge = AceStepUIBridge(base_url="http://localhost:3001")
    job = bridge.generate(
        style="cinematic orchestral, dramatic choir, 120 BPM",
        lyrics="[Verse]\nDark skies awaken...",
        title="Epic Dawn",
        duration=120,
        instrumental=False,
    )
    result = bridge.poll_until_complete(job.job_id, timeout=300)
    print(result.audio_urls)

Author: JARVIS Runtime / Auto-generated
Date: 2026-06-28
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable

# ---------------------------------------------------------------------------
# Optional dependency handling
# ---------------------------------------------------------------------------
try:
    import requests
except ImportError as _imp_err:  # pragma: no cover
    raise ImportError(
        "The ACE-Step UI bridge requires the 'requests' package. "
        "Install it with: pip install requests"
    ) from _imp_err

# ---------------------------------------------------------------------------
# Constants & defaults
# ---------------------------------------------------------------------------

DEFAULT_UI_BASE_URL = "http://localhost:3001"
DEFAULT_GRADIO_URL = "http://localhost:8001"
DEFAULT_POLL_INTERVAL = 2.0  # seconds
DEFAULT_REQUEST_TIMEOUT = 30  # seconds
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB — matches UI backend limit


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class AudioFormat(Enum):
    MP3 = "mp3"
    FLAC = "flac"


class InferMethod(Enum):
    ODE = "ode"
    SDE = "sde"


class LMBackend(Enum):
    PT = "pt"       # ~1.6 GB VRAM
    VLLM = "vllm"   # ~9.2 GB VRAM


class TaskType(Enum):
    TEXT2MUSIC = "text2music"
    COVER = "cover"
    AUDIO2AUDIO = "audio2audio"
    REPAINT = "repaint"


class JobStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------

@dataclass
class GenerationParams:
    """Mirror of the UI's GenerationParams (simplified for agent use)."""

    # Mode
    custom_mode: bool = True

    # Simple mode fields (used when custom_mode=False)
    song_description: Optional[str] = None

    # Custom mode fields
    prompt: str = ""
    lyrics: str = ""
    style: str = ""
    title: str = ""
    instrumental: bool = False
    vocal_language: Optional[str] = None

    # Musical parameters
    duration: int = 60          # seconds (30–240)
    bpm: Optional[int] = None   # 60–200
    key_scale: Optional[str] = None
    time_signature: Optional[str] = None

    # Quality / generation settings
    inference_steps: int = 8
    guidance_scale: float = 10.0
    batch_size: int = 1         # Keep at 1 for 8 GB GPUs
    random_seed: bool = True
    seed: int = 0
    thinking: bool = False
    enhance: bool = False
    audio_format: AudioFormat = field(default_factory=lambda: AudioFormat.MP3)
    infer_method: InferMethod = field(default_factory=lambda: InferMethod.ODE)
    shift: float = 0.0

    # LM parameters
    lm_temperature: float = 1.0
    lm_cfg_scale: float = 5.0
    lm_top_k: int = 250
    lm_top_p: float = 0.99
    lm_negative_prompt: str = ""
    lm_backend: LMBackend = field(default_factory=lambda: LMBackend.PT)
    lm_model: Optional[str] = None

    # Expert / advanced
    reference_audio_url: Optional[str] = None
    source_audio_url: Optional[str] = None
    reference_audio_title: Optional[str] = None
    source_audio_title: Optional[str] = None
    audio_codes: Optional[str] = None
    repainting_start: Optional[float] = None
    repainting_end: Optional[float] = None
    instruction: Optional[str] = None
    audio_cover_strength: Optional[float] = None
    task_type: Optional[TaskType] = None
    use_adg: bool = False
    cfg_interval_start: Optional[float] = None
    cfg_interval_end: Optional[float] = None
    custom_timesteps: Optional[str] = None
    use_cot_metas: bool = False
    use_cot_caption: bool = False
    use_cot_language: bool = False
    autogen: bool = False
    dit_model: Optional[str] = None

    def to_api_payload(self) -> Dict[str, Any]:
        """Flatten to snake_case → camelCase mapping expected by the UI backend."""
        d: Dict[str, Any] = {}

        def _set(cc: str, val: Any) -> None:
            if val is None:
                return
            if isinstance(val, Enum):
                d[cc] = val.value
            elif isinstance(val, bool):
                d[cc] = val
            elif isinstance(val, (int, float, str)):
                d[cc] = val
            else:
                d[cc] = val

        _set("customMode", self.custom_mode)
        _set("songDescription", self.song_description)
        _set("prompt", self.prompt)
        _set("lyrics", self.lyrics)
        _set("style", self.style)
        _set("title", self.title)
        _set("instrumental", self.instrumental)
        _set("vocalLanguage", self.vocal_language)
        _set("duration", self.duration)
        _set("bpm", self.bpm)
        _set("keyScale", self.key_scale)
        _set("timeSignature", self.time_signature)
        _set("inferenceSteps", self.inference_steps)
        _set("guidanceScale", self.guidance_scale)
        _set("batchSize", self.batch_size)
        _set("randomSeed", self.random_seed)
        _set("seed", self.seed)
        _set("thinking", self.thinking)
        _set("enhance", self.enhance)
        _set("audioFormat", self.audio_format)
        _set("inferMethod", self.infer_method)
        _set("shift", self.shift)
        _set("lmTemperature", self.lm_temperature)
        _set("lmCfgScale", self.lm_cfg_scale)
        _set("lmTopK", self.lm_top_k)
        _set("lmTopP", self.lm_top_p)
        _set("lmNegativePrompt", self.lm_negative_prompt)
        _set("lmBackend", self.lm_backend)
        _set("lmModel", self.lm_model)
        _set("referenceAudioUrl", self.reference_audio_url)
        _set("sourceAudioUrl", self.source_audio_url)
        _set("referenceAudioTitle", self.reference_audio_title)
        _set("sourceAudioTitle", self.source_audio_title)
        _set("audioCodes", self.audio_codes)
        _set("repaintingStart", self.repainting_start)
        _set("repaintingEnd", self.repainting_end)
        _set("instruction", self.instruction)
        _set("audioCoverStrength", self.audio_cover_strength)
        _set("taskType", self.task_type)
        _set("useAdg", self.use_adg)
        _set("cfgIntervalStart", self.cfg_interval_start)
        _set("cfgIntervalEnd", self.cfg_interval_end)
        _set("customTimesteps", self.custom_timesteps)
        _set("useCotMetas", self.use_cot_metas)
        _set("useCotCaption", self.use_cot_caption)
        _set("useCotLanguage", self.use_cot_language)
        _set("autogen", self.autogen)
        _set("ditModel", self.dit_model)
        return d


@dataclass
class JobSubmission:
    job_id: str


@dataclass
class JobResult:
    """Parsed result when a job reaches 'succeeded' status."""

    audio_urls: List[str] = field(default_factory=list)
    duration: float = 0.0
    bpm: Optional[int] = None
    key_scale: Optional[str] = None
    time_signature: Optional[str] = None
    status: str = ""
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class JobState:
    """Snapshot of a generation job while in flight or after completion."""

    job_id: str
    status: JobStatus
    queue_position: Optional[int] = None
    stage: Optional[str] = None
    progress: Optional[float] = None
    error: Optional[str] = None
    result: Optional[JobResult] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def is_terminal(self) -> bool:
        return self.status in (JobStatus.SUCCEEDED, JobStatus.FAILED)


@dataclass
class Song:
    id: str
    title: str
    style: str
    duration: str
    audio_url: Optional[str] = None
    cover_url: Optional[str] = None
    lyrics: Optional[str] = None
    is_public: bool = False
    like_count: int = 0
    view_count: int = 0
    creator: Optional[str] = None
    created_at: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class Playlist:
    id: str
    name: str
    description: Optional[str] = None
    cover_url: Optional[str] = None
    song_count: int = 0
    is_public: bool = False
    creator: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class SystemHealth:
    ui_ok: bool
    gradio_ok: bool
    ui_message: str = ""
    gradio_message: str = ""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AceStepBridgeError(Exception):
    """Base exception for all bridge errors."""


class AceStepAPIError(AceStepBridgeError):
    """Raised when the UI backend returns a non-2xx or structured error."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class AceStepTimeoutError(AceStepBridgeError):
    """Raised when a polling loop exceeds its deadline."""


class AceStepUploadError(AceStepBridgeError):
    """Raised when audio file upload fails validation or transport."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _raise_for_json(resp: requests.Response) -> Dict[str, Any]:
    """Parse JSON and surface UI-backend error messages."""
    try:
        data = resp.json()
    except Exception as exc:
        raise AceStepAPIError(
            f"Non-JSON response ({resp.status_code}): {resp.text[:500]}",
            status_code=resp.status_code,
            response_body=resp.text,
        ) from exc

    if not resp.ok:
        err_msg = data.get("error") or data.get("message") or json.dumps(data)
        raise AceStepAPIError(
            f"API error {resp.status_code}: {err_msg}",
            status_code=resp.status_code,
            response_body=json.dumps(data),
        )
    return data


def _audio_ext_from_mime(mime: str) -> str:
    mapping = {
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/flac": ".flac",
        "audio/x-flac": ".flac",
        "audio/ogg": ".ogg",
        "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/aac": ".aac",
        "audio/webm": ".webm",
        "video/mp4": ".mp4",
    }
    return mapping.get(mime, ".audio")


# ---------------------------------------------------------------------------
# Bridge class
# ---------------------------------------------------------------------------

class AceStepUIBridge:
    """
    Integration adapter for ACE-Step UI.

    Parameters
    ----------
    base_url:
        URL of the ACE-Step UI Express backend (default ``http://localhost:3001``).
    gradio_url:
        URL of the raw ACE-Step Gradio server (default ``http://localhost:8001``).
    jwt_token:
        Optional Bearer token for authenticated routes. If omitted, only public
        routes and the ``/api/auth/*`` family can be used.
    timeout:
        Default HTTP request timeout in seconds.
    poll_interval:
        Seconds between ``/api/generate/status`` polls.
    retries:
        Number of transport-level retries for idempotent GET requests.
    session:
        Optional ``requests.Session`` to reuse connections / customize adapters.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_UI_BASE_URL,
        gradio_url: str = DEFAULT_GRADIO_URL,
        jwt_token: Optional[str] = None,
        timeout: float = DEFAULT_REQUEST_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        retries: int = 3,
        session: Optional[requests.Session] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.gradio_url = gradio_url.rstrip("/")
        self.jwt_token = jwt_token
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.retries = retries
        self._session = session or requests.Session()

    # ------------------------------------------------------------------
    # Internal request builders
    # ------------------------------------------------------------------

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        h: Dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.jwt_token:
            h["Authorization"] = f"Bearer {self.jwt_token}"
        if extra:
            h.update(extra)
        return h

    def _request(
        self,
        method: str,
        endpoint: str,
        use_gradio: bool = False,
        **kwargs: Any,
    ) -> requests.Response:
        """Execute an HTTP request with simple retry logic for GETs."""
        base = self.gradio_url if use_gradio else self.base_url
        url = f"{base}{endpoint}"
        attempt = 0
        while True:
            try:
                resp = self._session.request(
                    method=method,
                    url=url,
                    timeout=self.timeout,
                    **kwargs,
                )
                return resp
            except requests.RequestException as exc:
                attempt += 1
                if attempt >= self.retries or method.upper() != "GET":
                    raise AceStepAPIError(
                        f"{method} {url} failed after {attempt} attempt(s): {exc}"
                    ) from exc
                time.sleep(1.0)

    def _get_json(self, endpoint: str, use_gradio: bool = False) -> Dict[str, Any]:
        resp = self._request("GET", endpoint, use_gradio=use_gradio, headers=self._headers())
        return _raise_for_json(resp)

    def _post_json(
        self,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
        use_gradio: bool = False,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        resp = self._request(
            "POST",
            endpoint,
            use_gradio=use_gradio,
            headers=self._headers(extra=extra_headers),
            json=payload,
        )
        return _raise_for_json(resp)

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def register(self, username: str, password: str) -> str:
        """Create a local user and return the JWT token."""
        data = self._post_json("/api/auth/register", {"username": username, "password": password})
        token = data.get("token")
        if not token:
            raise AceStepAPIError("Registration response missing token")
        self.jwt_token = token
        return token

    def login(self, username: str, password: str) -> str:
        """Authenticate and store the JWT token for subsequent calls."""
        data = self._post_json("/api/auth/login", {"username": username, "password": password})
        token = data.get("token")
        if not token:
            raise AceStepAPIError("Login response missing token")
        self.jwt_token = token
        return token

    def me(self) -> Dict[str, Any]:
        """Fetch current user profile."""
        return self._get_json("/api/auth/me")

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(self, params: Optional[GenerationParams] = None, **kwargs: Any) -> JobSubmission:
        """
        Submit a generation job to the UI backend queue.

        Accepts either a :class:`GenerationParams` object or keyword arguments
        that will be folded into ``GenerationParams()``.

        Returns the ``job_id`` immediately; the job is processed asynchronously.
        """
        if params is None:
            params = GenerationParams(**kwargs)
        if not isinstance(params, GenerationParams):
            raise TypeError("params must be a GenerationParams instance")

        payload = params.to_api_payload()
        data = self._post_json("/api/generate", payload)
        job_id = data.get("jobId") or data.get("job_id")
        if not job_id:
            raise AceStepAPIError("Generation response missing jobId")
        return JobSubmission(job_id=str(job_id))

    def quick_generate(
        self,
        style: str,
        lyrics: str = "",
        title: str = "",
        duration: int = 60,
        instrumental: bool = False,
        **kwargs: Any,
    ) -> JobSubmission:
        """
        Convenience wrapper for the most common generation path.

        Automatically sets ``custom_mode=True`` and populates ``style``,
        ``lyrics``, ``title``, ``duration``, ``instrumental``.
        Any extra kwargs are forwarded to :class:`GenerationParams`.
        """
        params = GenerationParams(
            custom_mode=True,
            style=style,
            lyrics=lyrics,
            title=title or (style.split()[0] if style else "Untitled"),
            duration=duration,
            instrumental=instrumental,
            **kwargs,
        )
        return self.generate(params)

    def get_job_status(self, job_id: str) -> JobState:
        """Poll the current state of a generation job."""
        data = self._get_json(f"/api/generate/status/{urllib.parse.quote(job_id, safe='')}")
        status_str = (data.get("status") or "queued").lower()
        status = JobStatus(status_str) if status_str in {s.value for s in JobStatus} else JobStatus.QUEUED

        result = None
        if status == JobStatus.SUCCEEDED:
            raw_result = data.get("result", {})
            result = JobResult(
                audio_urls=raw_result.get("audioUrls", []),
                duration=raw_result.get("duration", 0.0),
                bpm=raw_result.get("bpm"),
                key_scale=raw_result.get("keyScale"),
                time_signature=raw_result.get("timeSignature"),
                status=raw_result.get("status", "succeeded"),
                raw=raw_result,
            )

        return JobState(
            job_id=job_id,
            status=status,
            queue_position=data.get("queuePosition"),
            stage=data.get("stage"),
            progress=data.get("progress"),
            error=data.get("error"),
            result=result,
            raw=data,
        )

    def poll_until_complete(
        self,
        job_id: str,
        timeout: float = 300.0,
        interval: Optional[float] = None,
        on_tick: Optional[Callable[[JobState], None]] = None,
    ) -> JobState:
        """
        Block until the job reaches a terminal state or *timeout* expires.

        Parameters
        ----------
        job_id:
            The queued job identifier.
        timeout:
            Maximum seconds to wait before raising :class:`AceStepTimeoutError`.
        interval:
            Override the default poll interval.
        on_tick:
            Optional callback invoked on every poll with the current :class:`JobState`.

        Returns
        -------
        The final :class:`JobState`. If ``status == FAILED``, ``error`` will be set.
        """
        interval = interval or self.poll_interval
        deadline = time.time() + timeout

        while time.time() < deadline:
            state = self.get_job_status(job_id)
            if on_tick:
                on_tick(state)
            if state.is_terminal:
                return state
            time.sleep(interval)

        raise AceStepTimeoutError(
            f"Job {job_id} did not complete within {timeout} seconds"
        )

    # ------------------------------------------------------------------
    # Audio upload (reference / source tracks)
    # ------------------------------------------------------------------

    def upload_audio(
        self,
        file_path: Union[str, Path],
        mime_type: Optional[str] = None,
    ) -> str:
        """
        Upload a local audio file to the UI backend storage.

        Returns the public URL that can be used as ``reference_audio_url``
        or ``source_audio_url`` in generation params.

        Raises :class:`AceStepUploadError` if the file is too large or unreadable.
        """
        path = Path(file_path)
        if not path.exists():
            raise AceStepUploadError(f"File not found: {path}")

        size = path.stat().st_size
        if size > MAX_UPLOAD_BYTES:
            raise AceStepUploadError(
                f"File {path.name} is {size} bytes; max allowed is {MAX_UPLOAD_BYTES}"
            )

        mime = mime_type or "audio/mpeg"
        # Derive extension from mime if not already present in filename
        ext = _audio_ext_from_mime(mime)
        if not path.suffix:
            # The backend doesn't strictly require a real suffix, but matching
            # the original filename helps debugging.
            pass

        headers = self._headers()
        # Remove Content-Type set by _headers so multipart can set its own boundary
        headers.pop("Content-Type", None)

        try:
            with open(path, "rb") as fh:
                files = {"audio": (path.name, fh, mime)}
                resp = self._request(
                    "POST",
                    "/api/generate/upload-audio",
                    headers=headers,
                    files=files,
                )
            data = _raise_for_json(resp)
        except AceStepAPIError:
            raise
        except Exception as exc:
            raise AceStepUploadError(f"Upload failed: {exc}") from exc

        url = data.get("url")
        if not url:
            raise AceStepUploadError("Upload response missing 'url' field")
        return url

    def upload_audio_bytes(
        self,
        data: bytes,
        filename: str = "upload.audio",
        mime_type: str = "audio/mpeg",
    ) -> str:
        """
        Upload raw audio bytes without requiring a filesystem path.
        """
        if len(data) > MAX_UPLOAD_BYTES:
            raise AceStepUploadError(
                f"Payload is {len(data)} bytes; max allowed is {MAX_UPLOAD_BYTES}"
            )

        headers = self._headers()
        headers.pop("Content-Type", None)

        try:
            files = {"audio": (filename, data, mime_type)}
            resp = self._request(
                "POST",
                "/api/generate/upload-audio",
                headers=headers,
                files=files,
            )
            result = _raise_for_json(resp)
        except AceStepAPIError:
            raise
        except Exception as exc:
            raise AceStepUploadError(f"Upload failed: {exc}") from exc

        url = result.get("url")
        if not url:
            raise AceStepUploadError("Upload response missing 'url' field")
        return url

    # ------------------------------------------------------------------
    # Library / songs
    # ------------------------------------------------------------------

    def list_songs(
        self,
        search: Optional[str] = None,
        tag: Optional[str] = None,
        creator: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> List[Song]:
        """Query the song library with filters and pagination."""
        params: Dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }
        if search:
            params["search"] = search
        if tag:
            params["tag"] = tag
        if creator:
            params["creator"] = creator

        resp = self._request(
            "GET",
            "/api/songs",
            headers=self._headers(),
            params=params,
        )
        data = _raise_for_json(resp)
        items = data.get("songs", data.get("items", data.get("data", [])))
        return [_song_from_raw(r) for r in items]

    def get_song(self, song_id: str) -> Song:
        """Fetch full metadata for a single song."""
        data = self._get_json(f"/api/songs/{urllib.parse.quote(song_id, safe='')}")
        return _song_from_raw(data.get("song", data))

    def stream_audio(self, song_id: str) -> requests.Response:
        """
        Return the raw HTTP response for a song's audio stream.

        The caller is responsible for reading / saving the response content.
        """
        return self._request(
            "GET",
            f"/api/songs/{urllib.parse.quote(song_id, safe='')}/stream",
            headers=self._headers(),
            stream=True,
        )

    def download_audio(
        self,
        song_id: str,
        destination: Union[str, Path],
        chunk_size: int = 8192,
    ) -> Path:
        """Stream a song's audio to a local file path."""
        dest = Path(destination)
        resp = self.stream_audio(song_id)
        if not resp.ok:
            raise AceStepAPIError(
                f"Stream failed with status {resp.status_code}",
                status_code=resp.status_code,
            )
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    fh.write(chunk)
        return dest

    def like_song(self, song_id: str, unlike: bool = False) -> Dict[str, Any]:
        """Toggle like status for a song."""
        method = "DELETE" if unlike else "POST"
        endpoint = f"/api/songs/{urllib.parse.quote(song_id, safe='')}/like"
        resp = self._request(method, endpoint, headers=self._headers())
        return _raise_for_json(resp)

    # ------------------------------------------------------------------
    # Playlists
    # ------------------------------------------------------------------

    def list_playlists(self, user_id: Optional[str] = None) -> List[Playlist]:
        """List playlists, optionally filtered by owner."""
        params: Dict[str, str] = {}
        if user_id:
            params["userId"] = user_id
        resp = self._request("GET", "/api/playlists", headers=self._headers(), params=params)
        data = _raise_for_json(resp)
        items = data.get("playlists", data.get("items", data.get("data", [])))
        return [_playlist_from_raw(r) for r in items]

    def get_playlist(self, playlist_id: str) -> Playlist:
        data = self._get_json(f"/api/playlists/{urllib.parse.quote(playlist_id, safe='')}")
        return _playlist_from_raw(data.get("playlist", data))

    def create_playlist(
        self,
        name: str,
        description: Optional[str] = None,
        song_ids: Optional[List[str]] = None,
        is_public: bool = False,
    ) -> Playlist:
        payload: Dict[str, Any] = {"name": name, "isPublic": is_public}
        if description:
            payload["description"] = description
        if song_ids:
            payload["songIds"] = song_ids
        data = self._post_json("/api/playlists", payload)
        return _playlist_from_raw(data.get("playlist", data))

    def update_playlist(
        self,
        playlist_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        song_ids: Optional[List[str]] = None,
        is_public: Optional[bool] = None,
    ) -> Playlist:
        payload: Dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if song_ids is not None:
            payload["songIds"] = song_ids
        if is_public is not None:
            payload["isPublic"] = is_public

        endpoint = f"/api/playlists/{urllib.parse.quote(playlist_id, safe='')}"
        resp = self._request("PUT", endpoint, headers=self._headers(), json=payload)
        data = _raise_for_json(resp)
        return _playlist_from_raw(data.get("playlist", data))

    def delete_playlist(self, playlist_id: str) -> Dict[str, Any]:
        endpoint = f"/api/playlists/{urllib.parse.quote(playlist_id, safe='')}"
        resp = self._request("DELETE", endpoint, headers=self._headers())
        return _raise_for_json(resp)

    # ------------------------------------------------------------------
    # Reference tracks
    # ------------------------------------------------------------------

    def list_reference_tracks(self) -> List[Dict[str, Any]]:
        """Return raw reference-track metadata from the UI backend."""
        data = self._get_json("/api/referenceTrack")
        return data.get("tracks", data.get("items", data.get("data", [])))

    # ------------------------------------------------------------------
    # LoRA & Training
    # ------------------------------------------------------------------

    def list_loras(self) -> List[Dict[str, Any]]:
        data = self._get_json("/api/lora")
        return data.get("loras", data.get("items", data.get("data", [])))

    def get_training_status(self) -> Dict[str, Any]:
        return self._get_json("/api/training/status")

    # ------------------------------------------------------------------
    # Health & discovery
    # ------------------------------------------------------------------

    def health(self) -> Dict[str, Any]:
        """Hit the UI backend ``/health`` endpoint."""
        return self._get_json("/health")

    def gradio_health(self) -> bool:
        """
        Probe the raw ACE-Step Gradio instance.

        Tries ``/gradio_api/info`` (Gradio 5+), ``/info`` (Gradio 4.x), then ``/``.
        """
        for endpoint in ("/gradio_api/info", "/info", "/"):
            try:
                resp = self._request(
                    "GET",
                    endpoint,
                    use_gradio=True,
                    headers={"Accept": "application/json"},
                )
                if resp.ok or resp.status_code < 500:
                    return True
            except AceStepAPIError:
                continue
        return False

    def system_health(self) -> SystemHealth:
        """Combined health snapshot of UI backend + Gradio engine."""
        ui_ok = False
        ui_msg = ""
        try:
            h = self.health()
            ui_ok = h.get("status") == "ok"
            ui_msg = str(h)
        except Exception as exc:
            ui_msg = str(exc)

        gradio_ok = self.gradio_health()
        return SystemHealth(
            ui_ok=ui_ok,
            gradio_ok=gradio_ok,
            ui_message=ui_msg,
            gradio_message="reachable" if gradio_ok else "unreachable",
        )

    def discover_endpoints(self) -> Dict[str, Any]:
        """
        Ask the UI backend to enumerate available generation endpoints.

        Useful for runtime capability negotiation (e.g. checking whether
        ``/generation_wrapper`` exists vs. older endpoints).
        """
        return self._get_json("/api/generate/discover")

    # ------------------------------------------------------------------
    # Convenience: full end-to-end generation
    # ------------------------------------------------------------------

    def generate_and_wait(
        self,
        params: Optional[GenerationParams] = None,
        timeout: float = 300.0,
        on_progress: Optional[Callable[[JobState], None]] = None,
        **kwargs: Any,
    ) -> JobResult:
        """
        One-shot helper: submit a job and block until it completes.

        Returns the :class:`JobResult` on success, or raises on failure / timeout.
        """
        sub = self.generate(params, **kwargs)
        final = self.poll_until_complete(
            sub.job_id,
            timeout=timeout,
            on_tick=on_progress,
        )
        if final.status == JobStatus.FAILED:
            raise AceStepBridgeError(
                f"Generation failed: {final.error or 'Unknown error'}"
            )
        if final.result is None:
            raise AceStepBridgeError("Generation succeeded but result payload was empty")
        return final.result


# ---------------------------------------------------------------------------
# Internal model helpers
# ---------------------------------------------------------------------------

def _song_from_raw(raw: Dict[str, Any]) -> Song:
    return Song(
        id=raw.get("id", ""),
        title=raw.get("title", ""),
        style=raw.get("style", ""),
        duration=raw.get("duration", "0:00"),
        audio_url=raw.get("audioUrl") or raw.get("audio_url"),
        cover_url=raw.get("coverUrl") or raw.get("cover_url"),
        lyrics=raw.get("lyrics"),
        is_public=raw.get("isPublic") or raw.get("is_public") or False,
        like_count=raw.get("likeCount") or raw.get("like_count") or 0,
        view_count=raw.get("viewCount") or raw.get("view_count") or 0,
        creator=raw.get("creator"),
        created_at=raw.get("createdAt") or raw.get("created_at"),
        tags=raw.get("tags", []),
        raw=raw,
    )


def _playlist_from_raw(raw: Dict[str, Any]) -> Playlist:
    return Playlist(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        description=raw.get("description"),
        cover_url=raw.get("coverUrl") or raw.get("cover_url"),
        song_count=raw.get("songCount") or raw.get("song_count") or 0,
        is_public=raw.get("isPublic") or raw.get("is_public") or False,
        creator=raw.get("creator"),
        raw=raw,
    )
