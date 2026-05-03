"""
================================================================================
                        JARVIS BRAINIAC -- LiveKit Bridge
================================================================================

Production-grade integration adapter between **JARVIS BRAINIAC** and
**LiveKit Agents / LiveKit Realtime API**.

Provides a unified, async-first interface for:
    - Connecting to LiveKit rooms via WebSocket
    - Creating and managing voice agents
    - Publishing / subscribing to audio tracks
    - Sending / receiving data messages (transcripts, commands)
    - Full lifecycle management (join, publish, subscribe, leave, cleanup)

If the `livekit` / `livekit-agents` ecosystem is not installed in the current
environment every method degrades gracefully to a **mock implementation** that
logs calls and returns sensible sentinel values so downstream code never
explodes.

Design principles
-----------------
1. **Single-responsibility** -- one class handles everything LiveKit.
2. **Fail-soft** -- missing dependencies → mock, never ImportError.
3. **Type-safe** -- full type hints + generics.
4. **Observable** -- structured logging + optional tracing callbacks.
5. **Lifecycle-aware** -- context-manager support, explicit cleanup.

================================================================================
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
import wave
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    Union,
    runtime_checkable,
)

# ---------------------------------------------------------------------------
# Structured logger
# ---------------------------------------------------------------------------
_LOGGER = logging.getLogger("jarvis.runtime.agency.livekit_bridge")

# ---------------------------------------------------------------------------
# Optional dependency discovery -- LiveKit
# ---------------------------------------------------------------------------
try:
    import livekit  # type: ignore[import-untyped]
    import livekit.agents  # type: ignore[import-untyped]

    _LIVEKIT_AVAILABLE = True
    _LIVEKIT_VERSION = getattr(livekit, "__version__", "unknown")
    _LOGGER.info("livekit-sdk %s loaded", _LIVEKIT_VERSION)
except ImportError:
    _LIVEKIT_AVAILABLE = False
    _LIVEKIT_VERSION = None
    _LOGGER.warning(
        "livekit / livekit-agents not installed -- falling back to mock bridge"
    )


# =============================================================================
#  Domain models & enums
# =============================================================================


class ConnectionState(Enum):
    """Finite states of the bridge's room connection."""

    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    DISCONNECTING = auto()


class TrackKind(Enum):
    """Audio track classification inside a LiveKit room."""

    MICROPHONE = auto()
    SCREEN_SHARE_AUDIO = auto()
    PUBLISHED_AGENT = auto()
    UNKNOWN = auto()


@dataclass(frozen=True)
class AudioFrame:
    """Normalised audio frame delivered by LiveKit or the mock layer."""

    data: bytes
    sample_rate: int = 48000
    num_channels: int = 1
    samples_per_channel: int = 480
    timestamp_us: int = field(default_factory=lambda: int(time.time_ns() // 1000))

    def duration_ms(self) -> float:
        """Return the wall-clock duration represented by this frame."""
        if self.sample_rate == 0:
            return 0.0
        return (self.samples_per_channel / self.sample_rate) * 1000.0


@dataclass(frozen=True)
class TranscriptSegment:
    """A single transcript chunk from STT (local or remote participant)."""

    text: str
    participant_identity: str
    is_final: bool = False
    language: str = "en"
    received_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class RoomMessage:
    """Arbitrary data-message received on the LiveKit data channel."""

    topic: str
    payload: Union[str, bytes]
    participant_identity: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class BridgeMetrics:
    """Runtime counters surfaced for observability."""

    bytes_tx: int = 0
    bytes_rx: int = 0
    frames_tx: int = 0
    frames_rx: int = 0
    messages_tx: int = 0
    messages_rx: int = 0
    reconnections: int = 0
    errors: int = 0
    start_time: Optional[float] = None

    @property
    def uptime_seconds(self) -> float:
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time


# =============================================================================
#  Callback protocols
# =============================================================================


@runtime_checkable
class AudioReceivedCallback(Protocol):
    """Callable invoked when a remote audio frame arrives."""

    async def __call__(self, frame: AudioFrame, participant_identity: str) -> None:
        ...


@runtime_checkable
class TranscriptCallback(Protocol):
    """Callable invoked when a transcript segment is ready."""

    async def __call__(self, segment: TranscriptSegment) -> None:
        ...


@runtime_checkable
class MessageCallback(Protocol):
    """Callable invoked when a data message is received."""

    async def __call__(self, msg: RoomMessage) -> None:
        ...


# =============================================================================
#  Internal helpers
# =============================================================================

def _default_room_options() -> Dict[str, Any]:
    """Return sensible defaults for RoomOptions."""
    return {
        "auto_subscribe": True,
        " dynacast": True,
    }


def _generate_identity(name: str) -> str:
    """Create a deterministic participant identity."""
    return f"{name}_{uuid.uuid4().hex[:8]}"


# =============================================================================
#  LiveKitBridge
# =============================================================================


class LiveKitBridge:
    """Unified async bridge to a LiveKit room.

    Parameters
    ----------
    identity :
        Participant identity used when joining rooms.  Auto-generated if omitted.
    loop :
        Event loop to bind internal tasks to.  Uses *asyncio.get_event_loop()*
        if omitted.

    Usage
    -----
    .. code-block:: python

        bridge = LiveKitBridge(identity="jarvis-agent")
        await bridge.connect("wss://my.livekit.cloud", "<jwt-token>")
        await bridge.join_room("brainiac-main")

        agent = await bridge.create_voice_agent("EchoAgent")
        await bridge.publish_audio(agent.track)

        @bridge.on_audio_received
        async def handle_audio(frame, pid):
            await process(frame)

        # … later …
        await bridge.leave_room()
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def __init__(
        self,
        identity: Optional[str] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self._identity: str = identity or _generate_identity("jarvis")
        self._loop = loop or asyncio.get_event_loop()

        # LiveKit SDK handles (None until connect())
        self._room: Optional[Any] = None
        self._ws_url: Optional[str] = None
        self._token: Optional[str] = None

        # Internal state
        self._state: ConnectionState = ConnectionState.DISCONNECTED
        self._joined_room_name: Optional[str] = None
        self._published_tracks: List[Any] = []
        self._agents: Dict[str, Any] = {}
        self._metrics = BridgeMetrics()

        # Registered callbacks
        self._audio_callbacks: List[AudioReceivedCallback] = []
        self._transcript_callbacks: List[TranscriptCallback] = []
        self._message_callbacks: List[MessageCallback] = []

        # Background tasks
        self._tasks: Set[asyncio.Task[Any]] = set()

        # Mock recording buffer (used when livekit is absent)
        self._mock_audio_buffer: List[AudioFrame] = []
        self._mock_message_buffer: List[RoomMessage] = []

        _LOGGER.info(
            "LiveKitBridge created -- identity=%s livekit_available=%s",
            self._identity,
            _LIVEKIT_AVAILABLE,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def identity(self) -> str:
        """Return the participant identity."""
        return self._identity

    @property
    def state(self) -> ConnectionState:
        """Current connection state."""
        return self._state

    @property
    def room_name(self) -> Optional[str]:
        """Name of the currently joined room, or *None*."""
        return self._joined_room_name

    @property
    def metrics(self) -> BridgeMetrics:
        """Snapshot of runtime metrics."""
        return self._metrics

    @property
    def is_connected(self) -> bool:
        """``True`` when the bridge believes it is inside a LiveKit room."""
        return self._state == ConnectionState.CONNECTED and self._room is not None

    @property
    def is_mock(self) -> bool:
        """``True`` when operating in mock-fallback mode."""
        return not _LIVEKIT_AVAILABLE

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------
    async def __aenter__(self) -> "LiveKitBridge":
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.leave_room()

    # ------------------------------------------------------------------
    # connect
    # ------------------------------------------------------------------
    async def connect(self, ws_url: str, token: str) -> None:
        """Establish WebSocket signalling connection to a LiveKit server.

        Does **not** join a room -- call :meth:`join_room` afterwards.

        Parameters
        ----------
        ws_url :
            WebSocket endpoint, e.g. ``wss://my.livekit.cloud``.
        token :
            JWT access token generated by your auth server.
        """
        self._ws_url = ws_url
        self._token = token
        self._state = ConnectionState.CONNECTING
        self._metrics.start_time = time.time()

        if _LIVEKIT_AVAILABLE:
            try:
                self._room = livekit.Room(loop=self._loop)
                # Wire room events
                self._room.on(
                    "track_subscribed",
                    self._on_track_subscribed,
                )
                self._room.on(
                    "track_unsubscribed",
                    self._on_track_unsubscribed,
                )
                self._room.on(
                    "data_received",
                    self._on_data_received,
                )
                self._room.on(
                    "disconnected",
                    self._on_room_disconnected,
                )
                self._room.on(
                    "reconnecting",
                    self._on_room_reconnecting,
                )
                self._room.on(
                    "reconnected",
                    self._on_room_reconnected,
                )
                _LOGGER.info("LiveKit SDK room object initialised")
            except Exception as exc:
                self._state = ConnectionState.DISCONNECTED
                self._metrics.errors += 1
                _LOGGER.error("LiveKit room creation failed: %s", exc)
                raise
        else:
            # Mock path -- create a lightweight stand-in object
            self._room = _MockRoom(self._identity)
            _LOGGER.info("Mock room created (livekit not installed)")

        self._state = ConnectionState.CONNECTED
        _LOGGER.info("connect() completed -- ws_url=%s", ws_url)

    # ------------------------------------------------------------------
    # create_voice_agent
    # ------------------------------------------------------------------
    async def create_voice_agent(self, name: str) -> Dict[str, Any]:
        """Instantiate a voice-capable agent that can publish audio.

        Parameters
        ----------
        name :
            Human-readable name for the agent (used as part of the track
            publication name).

        Returns
        -------
        dict
            Agent descriptor containing at least ``name``, ``identity``,
            ``track`` and ``created_at``.
        """
        agent_identity = _generate_identity(name)
        created_at = time.time()

        if _LIVEKIT_AVAILABLE:
            try:
                # Build a VoicePipelineAgent or a raw LocalAudioTrack depending on
                # what the host application has installed.
                voice_agent = await self._try_create_real_agent(name)
            except Exception as exc:
                _LOGGER.warning(
                    "Real agent creation failed (%s) -- falling back to stub", exc
                )
                voice_agent = None
        else:
            voice_agent = None

        descriptor: Dict[str, Any] = {
            "name": name,
            "identity": agent_identity,
            "bridge_identity": self._identity,
            "track": voice_agent,
            "created_at": created_at,
            "kind": "voice",
        }
        self._agents[agent_identity] = descriptor
        _LOGGER.info("create_voice_agent: %s (%s)", name, agent_identity)
        return descriptor

    async def _try_create_real_agent(self, name: str) -> Any:
        """Attempt to use livekit-agents high-level API."""
        # If VoicePipelineAgent is available, construct one.  Otherwise
        # return a raw LocalAudioTrack that the caller can pump frames into.
        try:
            from livekit.agents import VoicePipelineAgent  # type: ignore[import-untyped]

            agent = VoicePipelineAgent(
                vad=livekit.agents.silero.VAD.load(),
                stt=livekit.agents.deepgram.STT(),
                llm=livekit.agents.openai.LLM(),
                tts=livekit.agents.elevenlabs.TTS(),
                room=self._room,
            )
            _LOGGER.debug("VoicePipelineAgent created for %s", name)
            return agent
        except Exception:
            # Fallback: local audio track only
            source = livekit.AudioSource(sample_rate=48000, num_channels=1)
            track = livekit.LocalAudioTrack.create_audio_track(
                name=f"audio-{name}", source=source
            )
            _LOGGER.debug("LocalAudioTrack created for %s", name)
            return track

    # ------------------------------------------------------------------
    # join_room
    # ------------------------------------------------------------------
    async def join_room(self, room_name: str) -> None:
        """Join a named LiveKit room.

        Must be called **after** :meth:`connect`.

        Parameters
        ----------
        room_name :
            Room identifier -- created on-the-fly if it does not exist.
        """
        if self._state != ConnectionState.CONNECTED or self._room is None:
            raise RuntimeError("connect() must be called before join_room()")

        self._joined_room_name = room_name

        if _LIVEKIT_AVAILABLE:
            try:
                await self._room.connect(
                    self._ws_url,
                    self._token,
                    options=_default_room_options(),
                )
                _LOGGER.info(
                    "Joined LiveKit room '%s' as %s", room_name, self._identity
                )
            except Exception as exc:
                self._metrics.errors += 1
                _LOGGER.error("Failed to join room %s: %s", room_name, exc)
                raise
        else:
            # Mock path -- simulate a brief handshake delay
            await asyncio.sleep(0.05)
            self._room.join(room_name)  # type: ignore[union-attr]
            _LOGGER.info("[MOCK] Joined room '%s' as %s", room_name, self._identity)

    # ------------------------------------------------------------------
    # publish_audio
    # ------------------------------------------------------------------
    async def publish_audio(self, audio_track: Any) -> None:
        """Publish a local audio track to the current room.

        Parameters
        ----------
        audio_track :
            A *livekit.LocalAudioTrack*, *livekit.agents* voice agent, or
            a mock-compatible wrapper.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to a room")

        self._published_tracks.append(audio_track)

        if _LIVEKIT_AVAILABLE:
            try:
                if isinstance(audio_track, livekit.LocalAudioTrack):
                    publication = await self._room.local_participant.publish_track(
                        audio_track
                    )
                    _LOGGER.debug("Audio track published: %s", publication.sid)
                elif hasattr(audio_track, "start"):
                    # VoicePipelineAgent-style object
                    await audio_track.start(self._room)
                    _LOGGER.debug("Voice agent started in room")
                else:
                    _LOGGER.warning("Unknown audio_track type -- %s", type(audio_track))
            except Exception as exc:
                self._metrics.errors += 1
                _LOGGER.error("publish_audio failed: %s", exc)
                raise
        else:
            _LOGGER.info("[MOCK] Audio track published (no-op)")

        self._metrics.frames_tx += 1

    # ------------------------------------------------------------------
    # subscribe_to_audio
    # ------------------------------------------------------------------
    async def subscribe_to_audio(self, participant: Union[str, Any]) -> None:
        """Subscribe to the audio track of a remote participant.

        Parameters
        ----------
        participant :
            Either the participant's ``identity`` string or a livekit
            ``RemoteParticipant`` object.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to a room")

        identity = (
            participant
            if isinstance(participant, str)
            else getattr(participant, "identity", "unknown")
        )

        if _LIVEKIT_AVAILABLE:
            try:
                # Auto-subscribe is on by default, so explicit subscription
                # is usually unnecessary; this method exists for fine-grained
                # control.
                remote_participant = self._room.remote_participants.get(identity)
                if remote_participant is None:
                    _LOGGER.warning("Participant %s not found in room", identity)
                    return
                for pub in remote_participant.track_publications.values():
                    if pub.kind == livekit.TrackKind.KIND_AUDIO:
                        await pub.set_subscribed(True)
                        _LOGGER.debug("Subscribed to audio from %s", identity)
            except Exception as exc:
                self._metrics.errors += 1
                _LOGGER.error("subscribe_to_audio failed: %s", exc)
        else:
            # Mock path -- schedule a synthetic audio frame after a short delay
            task = self._loop.create_task(
                self._mock_deliver_audio(identity),
            )
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            _LOGGER.info("[MOCK] Scheduled synthetic audio for %s", identity)

    # ------------------------------------------------------------------
    # send_message
    # ------------------------------------------------------------------
    async def send_message(
        self,
        message: Union[str, bytes, dict],
        topic: str = "jarvis-data",
        destination_identities: Optional[List[str]] = None,
    ) -> None:
        """Send a data message to participants in the room.

        Parameters
        ----------
        message :
            Payload -- strings and dicts are UTF-8 encoded; bytes are sent
            verbatim.
        topic :
            LiveKit data-channel topic used for routing.
        destination_identities :
            Optional list of participant identities to target.  When *None*
            the message is broadcast.
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to a room")

        if isinstance(message, dict):
            import json

            payload = json.dumps(message).encode("utf-8")
        elif isinstance(message, str):
            payload = message.encode("utf-8")
        else:
            payload = message

        self._metrics.messages_tx += 1
        self._metrics.bytes_tx += len(payload)

        if _LIVEKIT_AVAILABLE:
            try:
                await self._room.local_participant.publish_data(
                    payload,
                    topic=topic,
                    destination_identities=destination_identities or [],
                )
                _LOGGER.debug("Data message sent on topic '%s'", topic)
            except Exception as exc:
                self._metrics.errors += 1
                _LOGGER.error("send_message failed: %s", exc)
                raise
        else:
            self._mock_message_buffer.append(
                RoomMessage(
                    topic=topic,
                    payload=payload.decode("utf-8", errors="replace"),
                    participant_identity=self._identity,
                )
            )
            _LOGGER.info("[MOCK] Message buffered (topic=%s)", topic)

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------
    def on_audio_received(self, callback: AudioReceivedCallback) -> AudioReceivedCallback:
        """Register a coroutine callback invoked on every remote audio frame.

        The callback signature must be::

            async def callback(frame: AudioFrame, participant_identity: str) -> None: ...

        Multiple callbacks may be registered; they run concurrently.
        """
        if not isinstance(callback, AudioReceivedCallback):
            raise TypeError("callback must match AudioReceivedCallback protocol")
        self._audio_callbacks.append(callback)
        _LOGGER.debug("on_audio_received callback registered (%d total)", len(self._audio_callbacks))
        return callback

    def on_transcript(self, callback: TranscriptCallback) -> TranscriptCallback:
        """Register a coroutine callback invoked on transcript segments.

        Signature::

            async def callback(segment: TranscriptSegment) -> None: ...
        """
        if not isinstance(callback, TranscriptCallback):
            raise TypeError("callback must match TranscriptCallback protocol")
        self._transcript_callbacks.append(callback)
        _LOGGER.debug("on_transcript callback registered (%d total)", len(self._transcript_callbacks))
        return callback

    def on_message(self, callback: MessageCallback) -> MessageCallback:
        """Register a coroutine callback invoked on data messages.

        Signature::

            async def callback(msg: RoomMessage) -> None: ...
        """
        self._message_callbacks.append(callback)
        _LOGGER.debug("on_message callback registered (%d total)", len(self._message_callbacks))
        return callback

    # ------------------------------------------------------------------
    # leave_room
    # ------------------------------------------------------------------
    async def leave_room(self) -> None:
        """Gracefully disconnect from the room and release all resources.

        Safe to call multiple times (idempotent).
        """
        if self._state in (ConnectionState.DISCONNECTED, ConnectionState.DISCONNECTING):
            return

        self._state = ConnectionState.DISCONNECTING
        _LOGGER.info("leave_room() initiated")

        # Cancel background tasks
        for task in list(self._tasks):
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        # Stop agents
        for descriptor in list(self._agents.values()):
            track = descriptor.get("track")
            if track and hasattr(track, "stop"):
                try:
                    await track.stop()
                except Exception as exc:
                    _LOGGER.warning("Error stopping agent %s: %s", descriptor["name"], exc)

        # Disconnect SDK room
        if _LIVEKIT_AVAILABLE and self._room is not None:
            try:
                await self._room.disconnect()
            except Exception as exc:
                _LOGGER.warning("Room disconnect raised: %s", exc)
        else:
            if self._room is not None:
                self._room.disconnect()  # type: ignore[union-attr]

        self._room = None
        self._joined_room_name = None
        self._published_tracks.clear()
        self._agents.clear()
        self._audio_callbacks.clear()
        self._transcript_callbacks.clear()
        self._mock_audio_buffer.clear()
        self._mock_message_buffer.clear()
        self._state = ConnectionState.DISCONNECTED

        _LOGGER.info("leave_room() complete -- uptime=%.1fs", self._metrics.uptime_seconds)

    # ------------------------------------------------------------------
    # Internal event handlers (real LiveKit path)
    # ------------------------------------------------------------------
    def _on_track_subscribed(
        self, track: Any, publication: Any, participant: Any
    ) -> None:
        """Called when a remote track is subscribed."""
        identity = getattr(participant, "identity", "unknown")
        _LOGGER.debug("track_subscribed: %s from %s", publication.sid, identity)

        if track.kind == livekit.TrackKind.KIND_AUDIO:
            asyncio.create_task(
                self._audio_frame_reader(track, identity),
            )

    def _on_track_unsubscribed(
        self, track: Any, publication: Any, participant: Any
    ) -> None:
        identity = getattr(participant, "identity", "unknown")
        _LOGGER.debug("track_unsubscribed: %s from %s", publication.sid, identity)

    async def _audio_frame_reader(self, track: Any, identity: str) -> None:
        """Consume frames from a remote audio track forever."""
        try:
            async for frame_event in track.audio_stream():
                lk_frame = frame_event.frame
                frame = AudioFrame(
                    data=lk_frame.data.tobytes(),
                    sample_rate=lk_frame.sample_rate,
                    num_channels=lk_frame.num_channels,
                    samples_per_channel=lk_frame.samples_per_channel,
                )
                self._metrics.frames_rx += 1
                self._metrics.bytes_rx += len(frame.data)
                await self._dispatch_audio(frame, identity)
        except Exception as exc:
            self._metrics.errors += 1
            _LOGGER.error("Audio frame reader for %s ended: %s", identity, exc)

    def _on_data_received(self, data: Any) -> None:
        """Called when a data message hits the room."""
        msg = RoomMessage(
            topic=data.topic or "default",
            payload=data.data,
            participant_identity=getattr(data, "participant_identity", None),
        )
        self._metrics.messages_rx += 1
        self._metrics.bytes_rx += len(msg.payload) if isinstance(msg.payload, (str, bytes)) else 0
        asyncio.create_task(self._dispatch_message(msg))

    def _on_room_disconnected(self, reason: str) -> None:
        _LOGGER.warning("Room disconnected: %s", reason)
        self._state = ConnectionState.DISCONNECTED
        asyncio.create_task(self._attempt_reconnect())

    def _on_room_reconnecting(self) -> None:
        _LOGGER.info("Room reconnecting …")
        self._state = ConnectionState.RECONNECTING

    def _on_room_reconnected(self) -> None:
        _LOGGER.info("Room reconnected")
        self._state = ConnectionState.CONNECTED
        self._metrics.reconnections += 1

    # ------------------------------------------------------------------
    # Dispatch helpers
    # ------------------------------------------------------------------
    async def _dispatch_audio(self, frame: AudioFrame, identity: str) -> None:
        if not self._audio_callbacks:
            return
        await asyncio.gather(
            *[cb(frame, identity) for cb in self._audio_callbacks],
            return_exceptions=True,
        )

    async def _dispatch_transcript(self, segment: TranscriptSegment) -> None:
        if not self._transcript_callbacks:
            return
        await asyncio.gather(
            *[cb(segment) for cb in self._transcript_callbacks],
            return_exceptions=True,
        )

    async def _dispatch_message(self, msg: RoomMessage) -> None:
        for cb in self._message_callbacks:
            try:
                await cb(msg)
            except Exception as exc:
                _LOGGER.warning("Message callback error: %s", exc)

    # ------------------------------------------------------------------
    # Mock helpers
    # ------------------------------------------------------------------
    async def _mock_deliver_audio(self, identity: str) -> None:
        """Periodically synthesise audio frames in mock mode."""
        try:
            while self.is_connected:
                await asyncio.sleep(0.02)  # 20 ms tick
                # 480 samples @ 48 kHz, 16-bit mono ≈ 960 bytes of silence
                frame = AudioFrame(
                    data=b"\x00" * 960,
                    sample_rate=48000,
                    num_channels=1,
                    samples_per_channel=480,
                )
                self._mock_audio_buffer.append(frame)
                self._metrics.frames_rx += 1
                await self._dispatch_audio(frame, identity)
        except asyncio.CancelledError:
            pass

    async def _attempt_reconnect(self) -> None:
        """Simple exponential-backoff reconnection loop."""
        if self._ws_url is None or self._token is None:
            return
        delay = 1.0
        for attempt in range(1, 6):
            await asyncio.sleep(delay)
            try:
                self._state = ConnectionState.RECONNECTING
                await self.connect(self._ws_url, self._token)
                if self._joined_room_name:
                    await self.join_room(self._joined_room_name)
                _LOGGER.info("Reconnection succeeded on attempt %d", attempt)
                return
            except Exception as exc:
                _LOGGER.debug("Reconnect attempt %d failed: %s", attempt, exc)
                delay = min(delay * 2, 30.0)
        _LOGGER.error("All reconnection attempts exhausted")

    # ------------------------------------------------------------------
    # Convenience utilities
    # ------------------------------------------------------------------
    async def publish_wave_file(self, file_path: Union[str, Path]) -> None:
        """Read a WAV file and publish its audio contents as a single track.

        Parameters
        ----------
        file_path :
            Path to a valid RIFF/WAVE file.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(path)

        with wave.open(str(path), "rb") as wf:
            nchannels = wf.getnchannels()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            raw = wf.readframes(nframes)

        frame = AudioFrame(
            data=raw,
            sample_rate=framerate,
            num_channels=nchannels,
            samples_per_channel=nframes,
        )
        self._metrics.bytes_tx += len(raw)

        if _LIVEKIT_AVAILABLE:
            source = livekit.AudioSource(sample_rate=framerate, num_channels=nchannels)
            track = livekit.LocalAudioTrack.create_audio_track(
                name=f"wav-{path.stem}", source=source
            )
            await self.publish_audio(track)
        else:
            _LOGGER.info("[MOCK] WAV file '%s' published (%d bytes)", path.name, len(raw))

    async def inject_transcript(self, text: str, participant_identity: str = "local") -> None:
        """Manually fire a transcript segment through the callback pipeline.

        Useful for testing or for piping STT results from an external engine.
        """
        segment = TranscriptSegment(
            text=text,
            participant_identity=participant_identity,
            is_final=True,
        )
        await self._dispatch_transcript(segment)

    def get_mock_messages(self) -> List[RoomMessage]:
        """Return buffered mock messages (mock mode only)."""
        return list(self._mock_message_buffer)

    def get_mock_audio_buffer(self) -> List[AudioFrame]:
        """Return buffered mock audio frames (mock mode only)."""
        return list(self._mock_audio_buffer)

    def __repr__(self) -> str:
        return (
            f"LiveKitBridge(identity={self._identity!r}, "
            f"state={self._state.name}, "
            f"mock={self.is_mock}, "
            f"room={self._joined_room_name!r})"
        )


# =============================================================================
#  Internal mock room (used when livekit is absent)
# =============================================================================


class _MockRoom:
    """Minimal stand-in for ``livekit.Room`` when the SDK is unavailable."""

    def __init__(self, identity: str) -> None:
        self.identity = identity
        self._room_name: Optional[str] = None
        self._handlers: Dict[str, List[Callable[..., Any]]] = {
            "track_subscribed": [],
            "track_unsubscribed": [],
            "data_received": [],
            "disconnected": [],
            "reconnecting": [],
            "reconnected": [],
        }
        self.local_participant = _MockLocalParticipant(identity)

    def on(self, event: str, handler: Callable[..., Any]) -> None:
        self._handlers.setdefault(event, []).append(handler)

    def join(self, room_name: str) -> None:
        self._room_name = room_name

    def disconnect(self) -> None:
        self._room_name = None
        for handler in self._handlers.get("disconnected", []):
            try:
                handler("manual_disconnect")
            except Exception:
                pass

    @property
    def remote_participants(self) -> Dict[str, Any]:
        return {}

    @property
    def name(self) -> Optional[str]:
        return self._room_name


class _MockLocalParticipant:
    """Stand-in for ``room.local_participant``."""

    def __init__(self, identity: str) -> None:
        self.identity = identity

    async def publish_track(self, track: Any) -> Any:
        return _MockPublication()

    async def publish_data(
        self,
        data: bytes,
        *,
        topic: str = "default",
        destination_identities: Optional[List[str]] = None,
    ) -> None:
        _LOGGER.debug("[MOCK] publish_data topic=%s len=%d", topic, len(data))


class _MockPublication:
    sid: str = "mock-sid"


# =============================================================================
#  Factory function
# =============================================================================


def get_livekit_bridge(
    identity: Optional[str] = None,
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> LiveKitBridge:
    """Factory -- construct and return a :class:`LiveKitBridge`.

    Parameters
    ----------
    identity :
        Participant identity.  Auto-generated when omitted.
    loop :
        Event loop override (rarely needed).

    Returns
    -------
    LiveKitBridge
        Fully initialised bridge (connection not yet established).
    """
    return LiveKitBridge(identity=identity, loop=loop)


# =============================================================================
#  Quick self-test (run as ``python -m jarvis.runtime.agency.livekit_bridge``)
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(name)s] %(levelname)s -- %(message)s",
    )

    async def _self_test() -> None:
        bridge = get_livekit_bridge(identity="jarvis-test")
        print(bridge)
        assert bridge.is_mock == (not _LIVEKIT_AVAILABLE)

        await bridge.connect("wss://mock.livekit.example", "mock-jwt-token")
        assert bridge.state == ConnectionState.CONNECTED

        agent = await bridge.create_voice_agent("TestAgent")
        assert agent["name"] == "TestAgent"
        assert agent["kind"] == "voice"

        await bridge.join_room("test-room")
        assert bridge.room_name == "test-room"

        @bridge.on_audio_received
        async def _audio_cb(frame: AudioFrame, pid: str) -> None:
            _LOGGER.info("AUDIO  %s from %s", frame.duration_ms(), pid)

        @bridge.on_transcript
        async def _transcript_cb(seg: TranscriptSegment) -> None:
            _LOGGER.info("TRANSCRIPT %s: %s", seg.participant_identity, seg.text)

        # Simulate injection
        await bridge.inject_transcript("Hello from self-test", "test-speaker")
        await bridge.send_message({"command": "ping"}, topic="commands")

        # Let mock audio loop tick a couple of times
        await asyncio.sleep(0.15)

        await bridge.leave_room()
        assert bridge.state == ConnectionState.DISCONNECTED
        print(f"Metrics: {bridge.metrics}")
        print("Self-test passed ✅")

    asyncio.run(_self_test())
