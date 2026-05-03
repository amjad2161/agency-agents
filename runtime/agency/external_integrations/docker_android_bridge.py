#!/usr/bin/env python3
"""
docker_android_bridge.py

JARVIS Runtime Agency — External Integration Adapter for docker-android
=======================================================================

Provides a programmatic Python interface to build, run, and control Android
emulator containers based on the HQarroum/docker-android image set.

Capabilities
------------
- Build or pull docker-android images (standard / GPU / minimal).
- Start/stop containers with correct port mappings, KVM privileges, and
  volume mounts (ADB keys, AVD persistence, external SDK).
- Connect ADB from the host to the containerized emulator.
- Poll boot completion via ADB or by tailing container JSON state logs.
- Execute ADB commands (shell, install, push, logcat, etc.).
- GPU acceleration toggle, API level selection, image type selection.
- Automatic cleanup and lifecycle management.

Dependencies
------------
- Docker Engine installed on the host.
- ``adb`` (Android Debug Bridge) available on the host $PATH.
- ``/dev/kvm`` accessible (for performant emulation).
- Optional: ``docker`` PyPI package for SDK-backed operations.

Example
-------
    bridge = DockerAndroidBridge(
        api_level=33,
        image_type="google_apis",
        gpu_accelerated=False,
        memory=8192,
        cores=4,
    )
    bridge.start_container()
    bridge.wait_for_boot(timeout=300)
    bridge.adb_shell("pm list packages")
    bridge.stop_container()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DockerAndroidError(Exception):
    """Base exception for docker-android bridge errors."""


class ContainerNotRunningError(DockerAndroidError):
    """Raised when an operation requires a running container but none exists."""


class BootTimeoutError(DockerAndroidError):
    """Raised when the emulator fails to boot within the allotted time."""


class ADBConnectionError(DockerAndroidError):
    """Raised when the ADB host-client cannot connect to the container."""


class DockerCommandError(DockerAndroidError):
    """Raised when a Docker CLI command returns a non-zero exit code."""


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


@dataclass
class EmulatorState:
    """Structured representation of the emulator/container state."""

    container_id: Optional[str] = None
    container_name: Optional[str] = None
    image_tag: Optional[str] = None
    adb_host: str = "127.0.0.1"
    adb_port: int = 5555
    console_port: int = 5554
    booted: bool = False
    last_known_state: Literal["UNKNOWN", "ANDROID_BOOTING", "ANDROID_READY", "ANDROID_STOPPED"] = "UNKNOWN"
    api_level: int = 33
    image_type: str = "google_apis"
    gpu_accelerated: bool = False
    memory: int = 8192
    cores: int = 4
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BridgeConfig:
    """Immutable-ish configuration for the bridge."""

    # Image selection / build
    api_level: int = 33
    image_type: Literal["google_apis", "google_apis_playstore"] = "google_apis"
    architecture: Literal["x86_64", "x86"] = "x86_64"
    gpu_accelerated: bool = False
    use_prebuilt_image: bool = True
    prebuilt_tag_prefix: str = "halimqarroum/docker-android"
    custom_dockerfile_path: Optional[str] = None
    build_args: Dict[str, str] = field(default_factory=dict)

    # Container runtime
    memory: int = 8192
    cores: int = 4
    skip_auth: bool = True
    disable_animation: bool = False
    disable_hidden_policy: bool = False
    extra_emulator_flags: str = "-no-metrics -no-audio -partition-size=8192"
    privileged: bool = True
    device_kvm: bool = True
    publish_ports: bool = True
    console_port: int = 5554
    adb_port: int = 5555
    container_name: str = "jarvis-android-emulator"

    # Volumes
    avd_data_host_path: Optional[str] = None
    adb_keys_host_path: Optional[str] = None
    external_sdk_host_path: Optional[str] = None

    # ADB / Host
    adb_host: str = "127.0.0.1"
    adb_binary: str = "adb"
    adb_server_port: int = 5037

    # Polling / Timeouts
    boot_poll_interval: float = 5.0
    boot_timeout: float = 300.0
    adb_connect_retry: int = 10
    adb_connect_retry_interval: float = 3.0

    # Repo / build context (if building from source)
    repo_url: str = "https://github.com/HQarroum/docker-android"
    repo_clone_dir: Optional[str] = None

    def resolve_image_tag(self) -> str:
        """Return the Docker image tag to pull or build."""
        if self.custom_dockerfile_path:
            return f"jarvis-docker-android:{self.api_level}"
        if self.use_prebuilt_image:
            suffix = ""
            if self.image_type == "google_apis_playstore":
                suffix = "-playstore"
            if self.gpu_accelerated:
                suffix += "-cuda"
            return f"{self.prebuilt_tag_prefix}:api-{self.api_level}{suffix}"
        return f"jarvis-docker-android:api-{self.api_level}"

    def get_emulator_env(self) -> Dict[str, str]:
        """Runtime environment variables for the container."""
        env: Dict[str, str] = {
            "MEMORY": str(self.memory),
            "CORES": str(self.cores),
            "SKIP_AUTH": str(self.skip_auth).lower(),
            "DISABLE_ANIMATION": str(self.disable_animation).lower(),
            "DISABLE_HIDDEN_POLICY": str(self.disable_hidden_policy).lower(),
            "EXTRA_FLAGS": self.extra_emulator_flags,
        }
        if self.gpu_accelerated:
            env["GPU_ACCELERATED"] = "true"
        return env


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _which(cmd: str) -> Optional[str]:
    return shutil.which(cmd)


def _run_command(
    cmd: List[str],
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    capture: bool = True,
    timeout: Optional[float] = None,
) -> Tuple[int, str, str]:
    """Run a shell command and return (rc, stdout, stderr)."""
    logger.debug("Running command: %s", " ".join(cmd))
    kwargs: Dict[str, Any] = {
        "cwd": cwd,
        "env": {**os.environ, **(env or {})},
    }
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
        kwargs["text"] = True
    try:
        proc = subprocess.run(cmd, timeout=timeout, **kwargs)  # noqa: S603
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired as exc:
        raise DockerCommandError(f"Command timed out: {' '.join(cmd)}") from exc


def _docker(*args: str, capture: bool = True, timeout: Optional[float] = None) -> Tuple[int, str, str]:
    """Run a Docker CLI command."""
    docker_bin = _which("docker")
    if not docker_bin:
        raise DockerCommandError("Docker CLI ('docker') not found on PATH.")
    return _run_command([docker_bin, *args], capture=capture, timeout=timeout)


def _adb(*args: str, capture: bool = True, timeout: Optional[float] = None) -> Tuple[int, str, str]:
    """Run an ADB command."""
    adb_bin = _which("adb")
    if not adb_bin:
        raise ADBConnectionError("ADB binary ('adb') not found on PATH.")
    return _run_command([adb_bin, *args], capture=capture, timeout=timeout)


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------


class DockerAndroidBridge:
    """JARVIS integration bridge for docker-android."""

    def __init__(self, config: Optional[BridgeConfig] = None) -> None:
        self.cfg = config or BridgeConfig()
        self._container_id: Optional[str] = None
        self._state = EmulatorState(
            api_level=self.cfg.api_level,
            image_type=self.cfg.image_type,
            gpu_accelerated=self.cfg.gpu_accelerated,
            memory=self.cfg.memory,
            cores=self.cfg.cores,
            adb_host=self.cfg.adb_host,
            adb_port=self.cfg.adb_port,
            console_port=self.cfg.console_port,
        )
        self._log_tail_thread: Optional[threading.Thread] = None
        self._log_tail_stop = threading.Event()
        self._log_tail_buffer: List[str] = []
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> EmulatorState:
        with self._lock:
            return self._state

    @property
    def container_id(self) -> Optional[str]:
        with self._lock:
            return self._container_id

    # ------------------------------------------------------------------
    # Image Lifecycle
    # ------------------------------------------------------------------

    def pull_image(self, tag: Optional[str] = None) -> str:
        """Pull a pre-built image from Docker Hub (or another registry)."""
        image_tag = tag or self.cfg.resolve_image_tag()
        logger.info("Pulling docker-android image: %s", image_tag)
        rc, out, err = _docker("pull", image_tag, timeout=600)
        if rc != 0:
            raise DockerCommandError(f"Failed to pull image {image_tag}: {err}")
        with self._lock:
            self._state.image_tag = image_tag
        logger.info("Pulled %s successfully.", image_tag)
        return image_tag

    def build_image(
        self,
        context_path: Optional[str] = None,
        dockerfile: Optional[str] = None,
        tag: Optional[str] = None,
        extra_build_args: Optional[Dict[str, str]] = None,
    ) -> str:
        """Build a docker-android image from source."""
        ctx = context_path or self._clone_repo_if_needed()
        df = dockerfile or self.cfg.custom_dockerfile_path
        image_tag = tag or self.cfg.resolve_image_tag()

        cmd: List[str] = ["docker", "build", "-t", image_tag]
        if df:
            cmd.extend(["-f", df])

        # Standard build args
        build_args = {
            "API_LEVEL": str(self.cfg.api_level),
            "IMG_TYPE": self.cfg.image_type,
            "ARCHITECTURE": self.cfg.architecture,
            **self.cfg.build_args,
            **(extra_build_args or {}),
        }
        if self.cfg.gpu_accelerated:
            build_args.setdefault("GPU_ACCELERATED", "true")

        for k, v in build_args.items():
            cmd.extend(["--build-arg", f"{k}={v}"])

        cmd.append(ctx)

        logger.info("Building docker-android image: %s", image_tag)
        rc, out, err = _run_command(cmd, timeout=1800)
        if rc != 0:
            raise DockerCommandError(f"Failed to build image {image_tag}: {err}")

        with self._lock:
            self._state.image_tag = image_tag
        logger.info("Built %s successfully.", image_tag)
        return image_tag

    def _clone_repo_if_needed(self) -> str:
        """Clone the upstream docker-android repo if no local context exists."""
        clone_dir = self.cfg.repo_clone_dir
        if clone_dir and Path(clone_dir).exists():
            return clone_dir
        tmp = tempfile.mkdtemp(prefix="docker_android_")
        logger.info("Cloning docker-android repo into %s", tmp)
        rc, _, err = _run_command(
            ["git", "clone", "--depth", "1", self.cfg.repo_url, tmp],
            timeout=120,
        )
        if rc != 0:
            raise DockerCommandError(f"Git clone failed: {err}")
        self.cfg.repo_clone_dir = tmp
        return tmp

    # ------------------------------------------------------------------
    # Container Lifecycle
    # ------------------------------------------------------------------

    def start_container(self, image_tag: Optional[str] = None) -> str:
        """Start the Android emulator container."""
        if self.is_running():
            logger.warning("Container %s is already running.", self._container_id)
            return self._container_id  # type: ignore[return-value]

        tag = image_tag or self.cfg.resolve_image_tag()
        env = self.cfg.get_emulator_env()

        cmd: List[str] = [
            "docker", "run", "-d",
            "--name", self.cfg.container_name,
        ]

        if self.cfg.privileged:
            cmd.append("--privileged")
        if self.cfg.device_kvm:
            cmd.extend(["--device", "/dev/kvm"])
        if self.cfg.publish_ports:
            cmd.extend(["-p", f"{self.cfg.console_port}:{self.cfg.console_port}"])
            cmd.extend(["-p", f"{self.cfg.adb_port}:{self.cfg.adb_port}"])

        for k, v in env.items():
            cmd.extend(["-e", f"{k}={v}"])

        # Volume mounts
        if self.cfg.avd_data_host_path:
            cmd.extend(["-v", f"{self.cfg.avd_data_host_path}:/data"])
        if self.cfg.adb_keys_host_path:
            # Mount both key and pub if the directory is given, or individual files.
            keys_dir = Path(self.cfg.adb_keys_host_path)
            if keys_dir.is_dir():
                cmd.extend(["-v", f"{keys_dir / 'adbkey'}:/root/.android/adbkey:ro"])
                cmd.extend(["-v", f"{keys_dir / 'adbkey.pub'}:/root/.android/adbkey.pub:ro"])
            else:
                cmd.extend(["-v", f"{self.cfg.adb_keys_host_path}:/root/.android/adbkey:ro"])
        if self.cfg.external_sdk_host_path:
            cmd.extend(["-v", f"{self.cfg.external_sdk_host_path}:/opt/android"])

        cmd.append(tag)

        logger.info("Starting container from image %s", tag)
        rc, out, err = _run_command(cmd, timeout=60)
        if rc != 0:
            raise DockerCommandError(f"Failed to start container: {err}")

        container_id = out.strip().splitlines()[0]
        with self._lock:
            self._container_id = container_id
            self._state.container_id = container_id
            self._state.container_name = self.cfg.container_name
            self._state.image_tag = tag
            self._state.booted = False
            self._state.last_known_state = "ANDROID_BOOTING"

        logger.info("Container started: %s", container_id)
        self._start_log_tail()
        return container_id

    def stop_container(self, remove: bool = True) -> None:
        """Stop and optionally remove the container."""
        cid = self.container_id
        if not cid:
            logger.warning("No container to stop.")
            return

        logger.info("Stopping container %s", cid)
        _docker("stop", cid, timeout=30)
        if remove:
            _docker("rm", cid, timeout=30)
        with self._lock:
            self._container_id = None
            self._state.container_id = None
            self._state.booted = False
            self._state.last_known_state = "ANDROID_STOPPED"
        self._stop_log_tail()

    def is_running(self) -> bool:
        """Check whether the managed container is currently running."""
        cid = self.container_id
        if not cid:
            return False
        rc, out, _ = _docker("inspect", "-f", "{{.State.Running}}", cid, timeout=10)
        return rc == 0 and out.strip().lower() == "true"

    def container_logs(self, tail: int = 100) -> str:
        """Retrieve container logs."""
        cid = self.container_id
        if not cid:
            raise ContainerNotRunningError("No container ID known.")
        rc, out, err = _docker("logs", "--tail", str(tail), cid, timeout=30)
        if rc != 0:
            raise DockerCommandError(f"Failed to get logs: {err}")
        return out

    # ------------------------------------------------------------------
    # ADB Integration
    # ------------------------------------------------------------------

    def adb_connect(self) -> bool:
        """Connect the host ADB client to the containerized emulator."""
        addr = f"{self.cfg.adb_host}:{self.cfg.adb_port}"
        logger.info("Connecting ADB to %s", addr)

        # Start local ADB server if not already running
        _adb("start-server", timeout=10)

        for attempt in range(1, self.cfg.adb_connect_retry + 1):
            rc, out, err = _adb("connect", addr, timeout=10)
            combined = (out + err).lower()
            if rc == 0 and ("connected to" in combined or "already connected" in combined):
                logger.info("ADB connected to %s (attempt %d)", addr, attempt)
                with self._lock:
                    self._state.booted = True  # optimistic; wait_for_boot confirms
                return True
            logger.debug("ADB connect attempt %d failed: %s", attempt, combined)
            time.sleep(self.cfg.adb_connect_retry_interval)

        raise ADBConnectionError(f"Could not connect ADB to {addr} after {self.cfg.adb_connect_retry} attempts.")

    def adb_disconnect(self) -> None:
        """Disconnect the ADB session."""
        addr = f"{self.cfg.adb_host}:{self.cfg.adb_port}"
        _adb("disconnect", addr, timeout=10)
        logger.info("ADB disconnected from %s", addr)

    def adb_shell(self, command: str, timeout: float = 30) -> str:
        """Execute a shell command inside the emulator via ADB."""
        self._ensure_adb_connected()
        rc, out, err = _adb("-s", f"{self.cfg.adb_host}:{self.cfg.adb_port}", "shell", command, timeout=timeout)
        if rc != 0:
            raise DockerAndroidError(f"ADB shell command failed: {err}")
        return out

    def adb_install(self, apk_path: str, timeout: float = 60) -> str:
        """Install an APK on the emulator."""
        self._ensure_adb_connected()
        rc, out, err = _adb(
            "-s", f"{self.cfg.adb_host}:{self.cfg.adb_port}",
            "install", "-r", apk_path,
            timeout=timeout,
        )
        if rc != 0:
            raise DockerAndroidError(f"ADB install failed: {err}")
        return out

    def adb_push(self, local_path: str, remote_path: str, timeout: float = 60) -> str:
        """Push a file to the emulator."""
        self._ensure_adb_connected()
        rc, out, err = _adb(
            "-s", f"{self.cfg.adb_host}:{self.cfg.adb_port}",
            "push", local_path, remote_path,
            timeout=timeout,
        )
        if rc != 0:
            raise DockerAndroidError(f"ADB push failed: {err}")
        return out

    def adb_logcat(
        self,
        lines: Optional[int] = None,
        filter_regex: Optional[str] = None,
        timeout: float = 30,
    ) -> str:
        """Fetch logcat output."""
        self._ensure_adb_connected()
        args: List[str] = ["-s", f"{self.cfg.adb_host}:{self.cfg.adb_port}", "logcat", "-d"]
        if lines:
            args.extend(["-t", str(lines)])
        rc, out, err = _adb(*args, timeout=timeout)
        if rc != 0:
            raise DockerAndroidError(f"ADB logcat failed: {err}")
        if filter_regex:
            pattern = re.compile(filter_regex)
            out = "\n".join(line for line in out.splitlines() if pattern.search(line))
        return out

    def _ensure_adb_connected(self) -> None:
        addr = f"{self.cfg.adb_host}:{self.cfg.adb_port}"
        rc, out, err = _adb("devices", timeout=10)
        devices = out + err
        if addr not in devices:
            self.adb_connect()

    # ------------------------------------------------------------------
    # Boot Monitoring
    # ------------------------------------------------------------------

    def wait_for_boot(self, timeout: Optional[float] = None) -> None:
        """
        Block until the emulator reports ``sys.boot_completed == 1``.

        Uses two strategies in parallel:
        1. Tail container JSON logs for ``ANDROID_READY``.
        2. Poll ``adb shell getprop sys.boot_completed``.
        """
        if not self.is_running():
            raise ContainerNotRunningError("Container is not running.")

        deadline = time.time() + (timeout or self.cfg.boot_timeout)
        addr = f"{self.cfg.adb_host}:{self.cfg.adb_port}"

        self.adb_connect()

        while time.time() < deadline:
            # Strategy 1: JSON log tail buffer
            with self._lock:
                for line in self._log_tail_buffer:
                    try:
                        msg = json.loads(line)
                        if msg.get("type") == "state-update" and msg.get("value") == "ANDROID_READY":
                            self._state.booted = True
                            self._state.last_known_state = "ANDROID_READY"
                            logger.info("Boot detected via log stream.")
                            return
                    except json.JSONDecodeError:
                        continue
                self._log_tail_buffer.clear()

            # Strategy 2: ADB property poll
            try:
                rc, out, _ = _adb(
                    "-s", addr, "shell", "getprop", "sys.boot_completed",
                    timeout=10,
                )
                if rc == 0 and out.strip() == "1":
                    with self._lock:
                        self._state.booted = True
                        self._state.last_known_state = "ANDROID_READY"
                    logger.info("Boot detected via ADB sys.boot_completed.")
                    return
            except Exception as exc:
                logger.debug("ADB poll error: %s", exc)

            time.sleep(self.cfg.boot_poll_interval)

        raise BootTimeoutError(
            f"Emulator did not boot within {timeout or self.cfg.boot_timeout} seconds."
        )

    def _start_log_tail(self) -> None:
        """Background thread that tails container stdout for JSON state lines."""
        self._log_tail_stop.clear()
        self._log_tail_buffer.clear()
        cid = self.container_id
        if not cid:
            return

        def tail() -> None:
            try:
                proc = subprocess.Popen(  # noqa: S603
                    ["docker", "logs", "-f", cid],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                while not self._log_tail_stop.is_set() and proc.poll() is None:
                    line = proc.stdout.readline() if proc.stdout else ""
                    if not line:
                        time.sleep(0.5)
                        continue
                    with self._lock:
                        self._log_tail_buffer.append(line.strip())
                        # Keep buffer bounded
                        if len(self._log_tail_buffer) > 200:
                            self._log_tail_buffer = self._log_tail_buffer[-200:]
                        # Update state from JSON if present
                        try:
                            msg = json.loads(line.strip())
                            if msg.get("type") == "state-update":
                                self._state.last_known_state = msg.get("value", self._state.last_known_state)
                        except json.JSONDecodeError:
                            pass
                proc.terminate()
            except Exception as exc:
                logger.debug("Log tail thread ended: %s", exc)

        t = threading.Thread(target=tail, daemon=True)
        t.start()
        self._log_tail_thread = t

    def _stop_log_tail(self) -> None:
        self._log_tail_stop.set()
        if self._log_tail_thread:
            self._log_tail_thread.join(timeout=2)
            self._log_tail_thread = None

    # ------------------------------------------------------------------
    # Higher-Level Helpers
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Return a structured health report."""
        report: Dict[str, Any] = {
            "docker_available": _which("docker") is not None,
            "adb_available": _which("adb") is not None,
            "kvm_available": Path("/dev/kvm").exists(),
            "container_running": False,
            "booted": False,
            "state": self.state.__dict__,
        }
        if self.container_id:
            report["container_running"] = self.is_running()
            report["booted"] = self.state.booted
        return report

    def run_shell_pipeline(self, commands: List[str], timeout_per_cmd: float = 30) -> List[str]:
        """Execute a sequence of ADB shell commands."""
        results: List[str] = []
        for cmd in commands:
            results.append(self.adb_shell(cmd, timeout=timeout_per_cmd))
        return results

    def screenshot(self, local_path: str, timeout: float = 30) -> None:
        """
        Capture a screenshot via ADB and pull it to ``local_path``.
        Requires ``scrcpy`` or uses ``adb exec-out screencap``. Here we
        use the built-in ``screencap`` binary on the device.
        """
        self._ensure_adb_connected()
        tmp_remote = "/data/local/tmp/jarvis_screenshot.png"
        self.adb_shell(f"screencap -p {tmp_remote}", timeout=timeout)
        _adb(
            "-s", f"{self.cfg.adb_host}:{self.cfg.adb_port}",
            "pull", tmp_remote, local_path,
            timeout=timeout,
        )
        self.adb_shell(f"rm {tmp_remote}", timeout=10)
        logger.info("Screenshot saved to %s", local_path)

    def reboot_emulator(self, wait_after: float = 60) -> None:
        """Reboot the emulator via ADB and block until it comes back."""
        self._ensure_adb_connected()
        _adb("-s", f"{self.cfg.adb_host}:{self.cfg.adb_port}", "reboot", timeout=10)
        with self._lock:
            self._state.booted = False
            self._state.last_known_state = "ANDROID_BOOTING"
        time.sleep(wait_after)
        self.wait_for_boot()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self) -> None:
        """Stop container, disconnect ADB, and prune temporary clone dir."""
        try:
            self.adb_disconnect()
        except Exception as exc:
            logger.debug("ADB disconnect on cleanup failed (ignorable): %s", exc)
        self.stop_container(remove=True)
        if self.cfg.repo_clone_dir and Path(self.cfg.repo_clone_dir).exists():
            shutil.rmtree(self.cfg.repo_clone_dir, ignore_errors=True)
            self.cfg.repo_clone_dir = None

    # ------------------------------------------------------------------
    # Async Interface (Optional)
    # ------------------------------------------------------------------

    async def astart_container(self, image_tag: Optional[str] = None) -> str:
        """Async wrapper around start_container."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.start_container, image_tag)

    async def await_for_boot(self, timeout: Optional[float] = None) -> None:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.wait_for_boot, timeout)

    async def aadb_shell(self, command: str, timeout: float = 30) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.adb_shell, command, timeout)

    async def ahealth_check(self) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.health_check)

    async def acleanup(self) -> None:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.cleanup)


# ---------------------------------------------------------------------------
# Standalone CLI (for quick manual tests)
# ---------------------------------------------------------------------------


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Docker Android Bridge CLI")
    parser.add_argument("--api-level", type=int, default=33)
    parser.add_argument("--image-type", default="google_apis", choices=["google_apis", "google_apis_playstore"])
    parser.add_argument("--gpu", action="store_true", help="Use GPU-accelerated image")
    parser.add_argument("--memory", type=int, default=8192)
    parser.add_argument("--cores", type=int, default=4)
    parser.add_argument("--adb-port", type=int, default=5555)
    parser.add_argument("--console-port", type=int, default=5554)
    parser.add_argument("--container-name", default="jarvis-android-emulator")
    parser.add_argument("--avd-path", default=None, help="Host path to persist AVD data")
    parser.add_argument("--keys-path", default=None, help="Host path to ADB keys directory")
    parser.add_argument("--build", action="store_true", help="Build image instead of pulling")
    parser.add_argument("--dockerfile", default=None, help="Path to custom Dockerfile")
    parser.add_argument("--command", default=None, help="ADB shell command to run after boot")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    cfg = BridgeConfig(
        api_level=args.api_level,
        image_type=args.image_type,  # type: ignore[arg-type]
        gpu_accelerated=args.gpu,
        memory=args.memory,
        cores=args.cores,
        adb_port=args.adb_port,
        console_port=args.console_port,
        container_name=args.container_name,
        avd_data_host_path=args.avd_path,
        adb_keys_host_path=args.keys_path,
        custom_dockerfile_path=args.dockerfile,
        use_prebuilt_image=not args.build,
    )
    bridge = DockerAndroidBridge(cfg)

    try:
        if args.build:
            bridge.build_image()
        else:
            bridge.pull_image()
        bridge.start_container()
        logger.info("Waiting for emulator boot ...")
        bridge.wait_for_boot()
        if args.command:
            result = bridge.adb_shell(args.command)
            print(result)
        input("Press Enter to stop and cleanup ...")
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
    finally:
        bridge.cleanup()


if __name__ == "__main__":
    _cli()
