"""
===============================================================================
JARVIS BRAINIAC — Visual Quality Assurance Engine
===============================================================================
Checks generated images, videos, and documents for quality issues, artifacts,
and compliance with specifications — then triggers corrections automatically.

Author      : JARVIS BRAINIAC — Visual QA Division
Module      : runtime.agency.visual_qa
Version     : 1.0.0
License     : Proprietary

Classes
-------
VisualQAEngine    : Full-featured visual quality-assurance engine.
MockVisualQA      : Deterministic simulator for CI / unit-testing.
get_visual_qa()   : Factory that returns the appropriate implementation.

Usage
-----
    from jarvis.runtime.agency.visual_qa import get_visual_qa

    qa = get_visual_qa(mode="production")
    result = qa.check_image_quality("/path/to/image.png")
    if result["score"] < 80:
        qa.request_correction("/path/to/image.png", result["issues"])
===============================================================================
"""

from __future__ import annotations

import os
import io
import re
import json
import math
import time
import hashlib
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

import numpy as np

# ── Optional heavy dependencies (graceful degradation) ───────────────────────
try:
    from PIL import Image, ImageStat, ImageFilter, ImageChops
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False

try:
    import cv2
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False

try:
    from skimage.metrics import structural_similarity as ssim
    _HAS_SKIMAGE = True
except Exception:
    _HAS_SKIMAGE = False

try:
    import fitz  # PyMuPDF
    _HAS_FITZ = True
except Exception:
    _HAS_FITZ = False

# ── Logging ──────────────────────────────────────────────────────────────────
logger = logging.getLogger("jarvis.visual_qa")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    ))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

# ── Module-level constants ──────────────────────────────────────────────────
DEFAULT_SCORE_THRESHOLD: int = 80
ISSUE_CATEGORIES: tuple[str, ...] = (
    "blur", "noise", "artifacts", "compression", "resolution",
    "aspect_ratio", "color_profile", "format", "frame_drops",
    "audio_sync", "duration", "codec", "bitrate", "text_extractability",
    "formatting", "template_mismatch",
)

RESOLUTION_TIERS: dict[str, tuple[int, int]] = {
    "SD": (720, 480),
    "HD": (1280, 720),
    "FHD": (1920, 1080),
    "2K": (2048, 1080),
    "QHD": (2560, 1440),
    "4K": (3840, 2160),
    "8K": (7680, 4320),
}

COMMON_ASPECT_RATIOS: dict[str, float] = {
    "1:1": 1.0,
    "4:3": 4 / 3,
    "3:2": 3 / 2,
    "16:9": 16 / 9,
    "21:9": 21 / 9,
    "9:16": 9 / 16,
    "3:4": 3 / 4,
    "2:3": 2 / 3,
}


# ═══════════════════════════════════════════════════════════════════════════════
# Helper data structures
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class QualityIssue:
    """A single quality issue found during inspection."""
    category: str
    severity: str  # critical | major | minor | info
    description: str
    metric: Optional[float] = None
    recommendation: str = ""

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "metric": self.metric,
            "recommendation": self.recommendation,
        }


@dataclass
class CheckResult:
    """Structured result for any quality check."""
    passed: bool
    score: float
    issues: list[QualityIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": round(self.score, 2),
            "issues": [i.to_dict() for i in self.issues],
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# VisualQAEngine
# ═══════════════════════════════════════════════════════════════════════════════

class VisualQAEngine:
    """
    Production-quality visual QA engine for JARVIS BRAINIAC.

    Performs pixel-level, temporal, and structural analysis on images,
    videos, and documents.  Collects historical metrics so the system can
    learn which pipelines most often produce defects.
    """

    # ── construction ─────────────────────────────────────────────────────────

    def __init__(
        self,
        score_threshold: int = DEFAULT_SCORE_THRESHOLD,
        history_db_path: Optional[str] = None,
        enable_ffmpeg: bool = True,
    ) -> None:
        self.score_threshold = score_threshold
        self.history_db_path = history_db_path or os.path.join(
            tempfile.gettempdir(), "jarvis_vqa_history.json"
        )
        self.enable_ffmpeg = enable_ffmpeg

        # In-memory history (flushed to disk periodically)
        self._history: list[dict] = self._load_history()
        self._failure_log: list[dict] = []

        # Capability flags
        self.capabilities = {
            "pil": _HAS_PIL,
            "cv2": _HAS_CV2,
            "skimage": _HAS_SKIMAGE,
            "fitz": _HAS_FITZ,
            "ffmpeg": self._ffmpeg_available(),
        }

        logger.info(
            "VisualQAEngine initialised — threshold=%d, caps=%s",
            self.score_threshold,
            self.capabilities,
        )

    # ── internal helpers ─────────────────────────────────────────────────────

    def _ffmpeg_available(self) -> bool:
        if not self.enable_ffmpeg:
            return False
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                timeout=5,
            )
            return True
        except Exception:
            return False

    def _load_history(self) -> list[dict]:
        if os.path.exists(self.history_db_path):
            try:
                with open(self.history_db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                logger.warning("Failed to load QA history: %s", exc)
        return []

    def _save_history(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.history_db_path), exist_ok=True)
            with open(self.history_db_path, "w", encoding="utf-8") as f:
                json.dump(self._history, f, indent=2, default=str)
        except Exception as exc:
            logger.warning("Failed to persist QA history: %s", exc)

    def _record(self, check_type: str, file_path: str, result: dict) -> None:
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "check_type": check_type,
            "file": os.path.basename(file_path),
            "file_hash": self._file_hash(file_path),
            "score": result.get("score"),
            "passed": result.get("score", 0) >= self.score_threshold,
            "issue_count": len(result.get("issues", [])),
            "issue_categories": [
                i.get("category") for i in result.get("issues", [])
            ],
        }
        self._history.append(entry)
        if not entry["passed"]:
            self._failure_log.append(entry)
        # Flush every 10 entries
        if len(self._history) % 10 == 0:
            self._save_history()

    @staticmethod
    def _file_hash(path: str) -> str:
        try:
            with open(path, "rb") as f:
                return hashlib.sha256(f.read(8192)).hexdigest()[:16]
        except Exception:
            return "unknown"

    @staticmethod
    def _aspect_ratio(w: int, h: int) -> float:
        return round(w / h, 4) if h else 0.0

    @staticmethod
    def _closest_aspect_ratio(ratio: float) -> str:
        best_label = "unknown"
        best_diff = float("inf")
        for label, ref in COMMON_ASPECT_RATIOS.items():
            diff = abs(ratio - ref)
            if diff < best_diff:
                best_diff = diff
                best_label = label
        return best_label if best_diff < 0.05 else "custom"

    # ═════════════════════════════════════════════════════════════════════════
    # IMAGE QUALITY CHECKS
    # ═════════════════════════════════════════════════════════════════════════

    def check_image_quality(self, image_path: str) -> dict:
        """
        Comprehensive image quality analysis.

        Detects blur, noise, compression artifacts, and general degradation.
        Returns a dict with score (0-100), issues list, and recommendations.
        """
        if not os.path.exists(image_path):
            return self._error_result(f"File not found: {image_path}")

        issues: list[QualityIssue] = []
        score = 100.0
        metadata: dict[str, Any] = {"path": image_path}

        # ── Load image ─────────────────────────────────────────────────────
        img_array, pil_img = self._load_image(image_path)
        if img_array is None:
            return self._error_result(f"Unable to load image: {image_path}")

        h, w = img_array.shape[:2]
        metadata["width"] = w
        metadata["height"] = h
        metadata["channels"] = img_array.shape[2] if img_array.ndim == 3 else 1

        # ── Blur detection (Laplacian variance) ────────────────────────────
        blur_score = self._detect_blur(img_array)
        metadata["blur_variance"] = round(blur_score, 2)
        if blur_score < 100:
            severity = "critical" if blur_score < 50 else "major"
            issues.append(QualityIssue(
                category="blur",
                severity=severity,
                description=f"Image appears blurry (Laplacian variance={blur_score:.1f}).",
                metric=blur_score,
                recommendation="Re-generate with sharper focus or reduce motion blur.",
            ))
            score -= 25 if severity == "critical" else 15

        # ── Noise detection ────────────────────────────────────────────────
        noise_score = self._detect_noise(img_array)
        metadata["noise_estimate"] = round(noise_score, 2)
        if noise_score > 10:
            severity = "major" if noise_score > 20 else "minor"
            issues.append(QualityIssue(
                category="noise",
                severity=severity,
                description=f"Excessive noise detected (estimate={noise_score:.1f}).",
                metric=noise_score,
                recommendation="Apply denoising or regenerate with better lighting.",
            ))
            score -= 15 if severity == "major" else 8

        # ── Compression / artifact detection ───────────────────────────────
        artifact_score = self._detect_artifacts_internal(img_array)
        metadata["artifact_score"] = round(artifact_score, 2)
        if artifact_score > 15:
            severity = "major" if artifact_score > 30 else "minor"
            issues.append(QualityIssue(
                category="compression",
                severity=severity,
                description=f"Compression artifacts detected (score={artifact_score:.1f}).",
                metric=artifact_score,
                recommendation="Increase export quality or use lossless format.",
            ))
            score -= 12 if severity == "major" else 6

        # ── Blocking artifacts ─────────────────────────────────────────────
        blocking_score = self._detect_blocking(img_array)
        metadata["blocking_score"] = round(blocking_score, 2)
        if blocking_score > 8:
            issues.append(QualityIssue(
                category="artifacts",
                severity="major" if blocking_score > 15 else "minor",
                description=f"Blocking artifacts visible (score={blocking_score:.1f}).",
                metric=blocking_score,
                recommendation="Reduce compression ratio or use better encoder.",
            ))
            score -= 10 if blocking_score > 15 else 5

        # ── General artifacts ──────────────────────────────────────────────
        general_artifacts = self._detect_general_artifacts(img_array)
        if general_artifacts:
            issues.extend(general_artifacts)
            score -= sum(
                15 if a.severity == "critical" else
                10 if a.severity == "major" else 5
                for a in general_artifacts
            )

        # ── Color banding ──────────────────────────────────────────────────
        banding_score = self._detect_color_banding(img_array)
        metadata["banding_score"] = round(banding_score, 2)
        if banding_score > 12:
            issues.append(QualityIssue(
                category="artifacts",
                severity="minor",
                description=f"Color banding detected (score={banding_score:.1f}).",
                metric=banding_score,
                recommendation="Use higher bit-depth (10-bit+) or dithering.",
            ))
            score -= 5

        # ── Score clamp ────────────────────────────────────────────────────
        score = max(0.0, min(100.0, score))
        passed = score >= self.score_threshold

        result = {
            "score": round(score, 2),
            "passed": passed,
            "issues": [i.to_dict() for i in issues],
            "recommendations": [i.recommendation for i in issues if i.recommendation],
            "metadata": metadata,
        }
        self._record("image_quality", image_path, result)
        return result

    # ── Image compliance ─────────────────────────────────────────────────────

    def check_image_compliance(self, image_path: str, requirements: dict) -> dict:
        """
        Check image against a requirements dict.

        Requirements keys: min_width, min_height, aspect_ratio, format,
        color_profile, max_file_size_mb.
        """
        if not os.path.exists(image_path):
            return self._error_result(f"File not found: {image_path}")

        issues: list[QualityIssue] = []
        score = 100.0
        metadata: dict[str, Any] = {"path": image_path, "requirements": requirements}

        img_array, pil_img = self._load_image(image_path)
        if img_array is None:
            return self._error_result(f"Unable to load image: {image_path}")

        h, w = img_array.shape[:2]
        file_size_mb = os.path.getsize(image_path) / (1024 * 1024)
        ext = os.path.splitext(image_path)[1].lower().replace(".", "")

        metadata.update({"width": w, "height": h, "file_size_mb": file_size_mb, "format": ext})

        # Resolution check
        if "min_width" in requirements and w < requirements["min_width"]:
            issues.append(QualityIssue(
                category="resolution",
                severity="critical",
                description=f"Width {w}px < required {requirements['min_width']}px.",
                recommendation=f"Upscale to at least {requirements['min_width']}px width.",
            ))
            score -= 25

        if "min_height" in requirements and h < requirements["min_height"]:
            issues.append(QualityIssue(
                category="resolution",
                severity="critical",
                description=f"Height {h}px < required {requirements['min_height']}px.",
                recommendation=f"Upscale to at least {requirements['min_height']}px height.",
            ))
            score -= 25

        # Aspect ratio check
        actual_ar = self._aspect_ratio(w, h)
        if "aspect_ratio" in requirements:
            req_ar = requirements["aspect_ratio"]
            if isinstance(req_ar, str) and req_ar in COMMON_ASPECT_RATIOS:
                req_ar = COMMON_ASPECT_RATIOS[req_ar]
            ar_diff = abs(actual_ar - float(req_ar))
            if ar_diff > 0.02:
                issues.append(QualityIssue(
                    category="aspect_ratio",
                    severity="major",
                    description=f"Aspect ratio {actual_ar:.3f} != required {req_ar}.",
                    metric=ar_diff,
                    recommendation=f"Crop or resize to match aspect ratio {req_ar}.",
                ))
                score -= 15

        # Format check
        if "format" in requirements and ext != requirements["format"].lower():
            issues.append(QualityIssue(
                category="format",
                severity="major",
                description=f"Format '{ext}' != required '{requirements['format']}'.",
                recommendation=f"Convert to {requirements['format']}.",
            ))
            score -= 15

        # Color profile check
        if "color_profile" in requirements and pil_img is not None:
            actual_profile = self._get_color_profile(pil_img)
            if actual_profile.lower() != requirements["color_profile"].lower():
                issues.append(QualityIssue(
                    category="color_profile",
                    severity="minor",
                    description=f"Color profile '{actual_profile}' != required '{requirements['color_profile']}'.",
                    recommendation=f"Convert color profile to {requirements['color_profile']}.",
                ))
                score -= 8

        # File size check
        if "max_file_size_mb" in requirements and file_size_mb > requirements["max_file_size_mb"]:
            issues.append(QualityIssue(
                category="compression",
                severity="minor",
                description=f"File size {file_size_mb:.1f}MB > max {requirements['max_file_size_mb']}MB.",
                metric=file_size_mb,
                recommendation="Compress or use more efficient encoding.",
            ))
            score -= 5

        score = max(0.0, min(100.0, score))
        result = {
            "score": round(score, 2),
            "passed": score >= self.score_threshold,
            "issues": [i.to_dict() for i in issues],
            "recommendations": [i.recommendation for i in issues if i.recommendation],
            "metadata": metadata,
        }
        self._record("image_compliance", image_path, result)
        return result

    # ── Artifact detection (public API) ──────────────────────────────────────

    def detect_artifacts(self, image: Union[str, np.ndarray]) -> list:
        """
        Find visual artifacts in an image.

        Parameters
        ----------
        image : str or np.ndarray
            File path or loaded image array.

        Returns
        -------
        list of dict
            Each dict describes one artifact region / type.
        """
        if isinstance(image, str):
            img_array, _ = self._load_image(image)
        else:
            img_array = image

        if img_array is None:
            return [{"error": "Could not load image"}]

        artifacts = self._detect_general_artifacts(img_array)
        return [a.to_dict() for a in artifacts]

    # ── Color accuracy ───────────────────────────────────────────────────────

    def check_color_accuracy(
        self,
        image: Union[str, np.ndarray],
        reference: Union[str, np.ndarray],
    ) -> float:
        """
        Compute color fidelity between image and reference.

        Returns a score 0-100 where 100 is perfect color match.
        """
        if isinstance(image, str):
            img, _ = self._load_image(image)
        else:
            img = image
        if isinstance(reference, str):
            ref, _ = self._load_image(reference)
        else:
            ref = reference

        if img is None or ref is None:
            return 0.0

        # Resize to same dimensions
        if img.shape[:2] != ref.shape[:2]:
            target_h, target_w = min(img.shape[0], ref.shape[0]), min(img.shape[1], ref.shape[1])
            if _HAS_CV2:
                img = cv2.resize(img, (target_w, target_h))
                ref = cv2.resize(ref, (target_w, target_h))
            else:
                return 50.0  # Cannot compare without resize capability

        # Convert to LAB for perceptual comparison
        if _HAS_CV2 and img.ndim == 3 and ref.ndim == 3:
            img_lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB).astype(np.float32)
            ref_lab = cv2.cvtColor(ref, cv2.COLOR_RGB2LAB).astype(np.float32)
            delta_e = np.mean(np.sqrt(np.sum((img_lab - ref_lab) ** 2, axis=2)))
            # Delta E < 2 is imperceptible; > 10 is very noticeable
            score = max(0.0, 100.0 - (delta_e * 5))
        else:
            # Fallback: simple mean squared error
            mse = np.mean((img.astype(np.float32) - ref.astype(np.float32)) ** 2)
            score = max(0.0, 100.0 - (mse / 255.0) * 10)

        return round(score, 2)

    # ═════════════════════════════════════════════════════════════════════════
    # VIDEO QUALITY CHECKS
    # ═════════════════════════════════════════════════════════════════════════

    def check_video_quality(self, video_path: str) -> dict:
        """
        Analyse video quality: resolution consistency, frame drops, audio sync.
        Uses ffprobe when available; falls back to OpenCV.
        """
        if not os.path.exists(video_path):
            return self._error_result(f"File not found: {video_path}")

        issues: list[QualityIssue] = []
        score = 100.0
        metadata: dict[str, Any] = {"path": video_path}

        # ── Probe with ffprobe ─────────────────────────────────────────────
        probe = self._probe_video(video_path)
        metadata["probe"] = probe

        if not probe:
            issues.append(QualityIssue(
                category="format",
                severity="critical",
                description="Could not probe video file.",
                recommendation="Check file integrity or codec support.",
            ))
            score = 0.0
            result = {"score": 0.0, "passed": False, "issues": [i.to_dict() for i in issues],
                      "recommendations": [i.recommendation for i in issues], "metadata": metadata}
            self._record("video_quality", video_path, result)
            return result

        # ── Resolution consistency ─────────────────────────────────────────
        width = probe.get("width", 0)
        height = probe.get("height", 0)
        metadata["width"] = width
        metadata["height"] = height

        if width == 0 or height == 0:
            issues.append(QualityIssue(
                category="resolution",
                severity="critical",
                description="Could not determine video resolution.",
                recommendation="Re-encode with standard resolution settings.",
            ))
            score -= 25

        # Check for resolution changes mid-stream
        if probe.get("has_resolution_change"):
            issues.append(QualityIssue(
                category="resolution",
                severity="major",
                description="Resolution changes detected during playback.",
                recommendation="Use constant resolution encoding.",
            ))
            score -= 15

        # ── Frame rate / frame drops ───────────────────────────────────────
        fps = probe.get("fps", 0)
        metadata["fps"] = fps
        frame_count = probe.get("frame_count", 0)
        metadata["frame_count"] = frame_count

        if fps > 0:
            duration = probe.get("duration", 0)
            expected_frames = int(fps * duration)
            if expected_frames > 0 and frame_count > 0:
                drop_ratio = abs(expected_frames - frame_count) / expected_frames
                metadata["frame_drop_ratio"] = round(drop_ratio, 4)
                if drop_ratio > 0.05:
                    severity = "critical" if drop_ratio > 0.2 else "major"
                    issues.append(QualityIssue(
                        category="frame_drops",
                        severity=severity,
                        description=f"Possible frame drops: {drop_ratio*100:.1f}% deviation.",
                        metric=drop_ratio,
                        recommendation="Re-encode with consistent frame rate or check source.",
                    ))
                    score -= 20 if severity == "critical" else 12

        # ── Audio sync ─────────────────────────────────────────────────────
        audio_delay = probe.get("audio_delay_ms", 0)
        metadata["audio_delay_ms"] = audio_delay
        if abs(audio_delay) > 40:
            severity = "critical" if abs(audio_delay) > 200 else "major"
            issues.append(QualityIssue(
                category="audio_sync",
                severity=severity,
                description=f"Audio sync offset: {audio_delay} ms.",
                metric=audio_delay,
                recommendation="Re-mux with corrected audio offset.",
            ))
            score -= 20 if severity == "critical" else 10

        # ── Bitrate adequacy ───────────────────────────────────────────────
        bitrate = probe.get("bitrate_kbps", 0)
        metadata["bitrate_kbps"] = bitrate
        min_bitrate = self._min_recommended_bitrate(width, height, fps)
        if bitrate > 0 and bitrate < min_bitrate * 0.5:
            issues.append(QualityIssue(
                category="bitrate",
                severity="major",
                description=f"Bitrate {bitrate}kbps very low for {width}x{height}@{fps}fps.",
                metric=bitrate,
                recommendation=f"Increase bitrate to at least {min_bitrate}kbps.",
            ))
            score -= 12

        # ── Codec check ────────────────────────────────────────────────────
        codec = probe.get("codec", "").lower()
        metadata["codec"] = codec
        if codec and codec not in ("h264", "h265", "hevc", "av1", "vp9"):
            issues.append(QualityIssue(
                category="codec",
                severity="minor",
                description=f"Non-ideal codec: {codec}.",
                recommendation="Re-encode with H.264, HEVC, or AV1.",
            ))
            score -= 5

        score = max(0.0, min(100.0, score))
        result = {
            "score": round(score, 2),
            "passed": score >= self.score_threshold,
            "issues": [i.to_dict() for i in issues],
            "recommendations": [i.recommendation for i in issues if i.recommendation],
            "metadata": metadata,
        }
        self._record("video_quality", video_path, result)
        return result

    # ── Video compliance ─────────────────────────────────────────────────────

    def check_video_compliance(self, video_path: str, requirements: dict) -> dict:
        """
        Check video against requirements dict.

        Requirements: min_duration, max_duration, format, codec,
        min_bitrate_kbps, min_resolution.
        """
        if not os.path.exists(video_path):
            return self._error_result(f"File not found: {video_path}")

        issues: list[QualityIssue] = []
        score = 100.0
        probe = self._probe_video(video_path)
        metadata: dict[str, Any] = {"path": video_path, "requirements": requirements, "probe": probe}

        if not probe:
            return self._error_result("Could not probe video for compliance check.")

        duration = probe.get("duration", 0)
        bitrate = probe.get("bitrate_kbps", 0)
        width = probe.get("width", 0)
        height = probe.get("height", 0)
        codec = probe.get("codec", "")
        ext = os.path.splitext(video_path)[1].lower().replace(".", "")

        # Duration checks
        if "min_duration" in requirements and duration < requirements["min_duration"]:
            issues.append(QualityIssue(
                category="duration",
                severity="critical",
                description=f"Duration {duration:.1f}s < min {requirements['min_duration']}s.",
                metric=duration,
                recommendation="Extend content or adjust generation parameters.",
            ))
            score -= 25

        if "max_duration" in requirements and duration > requirements["max_duration"]:
            issues.append(QualityIssue(
                category="duration",
                severity="minor",
                description=f"Duration {duration:.1f}s > max {requirements['max_duration']}s.",
                metric=duration,
                recommendation="Trim or adjust generation parameters.",
            ))
            score -= 8

        # Format check
        if "format" in requirements and ext != requirements["format"].lower():
            issues.append(QualityIssue(
                category="format",
                severity="major",
                description=f"Format '{ext}' != required '{requirements['format']}'.",
                recommendation=f"Convert to {requirements['format']}.",
            ))
            score -= 15

        # Codec check
        if "codec" in requirements:
            req_codec = requirements["codec"].lower()
            if codec.lower() != req_codec:
                issues.append(QualityIssue(
                    category="codec",
                    severity="major",
                    description=f"Codec '{codec}' != required '{req_codec}'.",
                    recommendation=f"Re-encode with {req_codec}.",
                ))
                score -= 15

        # Bitrate check
        if "min_bitrate_kbps" in requirements and bitrate < requirements["min_bitrate_kbps"]:
            issues.append(QualityIssue(
                category="bitrate",
                severity="major",
                description=f"Bitrate {bitrate}kbps < required {requirements['min_bitrate_kbps']}kbps.",
                metric=bitrate,
                recommendation=f"Increase bitrate to at least {requirements['min_bitrate_kbps']}kbps.",
            ))
            score -= 15

        # Resolution check
        if "min_resolution" in requirements:
            req_res = requirements["min_resolution"]
            if isinstance(req_res, str) and req_res in RESOLUTION_TIERS:
                req_w, req_h = RESOLUTION_TIERS[req_res]
            else:
                req_w, req_h = req_res
            if width < req_w or height < req_h:
                issues.append(QualityIssue(
                    category="resolution",
                    severity="critical",
                    description=f"Resolution {width}x{height} < required {req_w}x{req_h}.",
                    recommendation=f"Upscale or regenerate at {req_w}x{req_h}.",
                ))
                score -= 20

        score = max(0.0, min(100.0, score))
        result = {
            "score": round(score, 2),
            "passed": score >= self.score_threshold,
            "issues": [i.to_dict() for i in issues],
            "recommendations": [i.recommendation for i in issues if i.recommendation],
            "metadata": metadata,
        }
        self._record("video_compliance", video_path, result)
        return result

    # ═════════════════════════════════════════════════════════════════════════
    # DOCUMENT QUALITY CHECKS
    # ═════════════════════════════════════════════════════════════════════════

    def check_pdf_quality(self, pdf_path: str) -> dict:
        """
        Analyse PDF quality: text extractability, embedded image quality,
        formatting consistency.
        """
        if not os.path.exists(pdf_path):
            return self._error_result(f"File not found: {pdf_path}")

        issues: list[QualityIssue] = []
        score = 100.0
        metadata: dict[str, Any] = {"path": pdf_path}

        # ── Text extractability ────────────────────────────────────────────
        text_extracted, text_quality = self._extract_pdf_text(pdf_path)
        metadata["text_extractable"] = text_extracted
        metadata["text_quality_score"] = text_quality

        if not text_extracted:
            issues.append(QualityIssue(
                category="text_extractability",
                severity="major",
                description="No extractable text found (possibly scanned image PDF).",
                recommendation="Use OCR or generate text-based PDF.",
            ))
            score -= 20
        elif text_quality < 50:
            issues.append(QualityIssue(
                category="text_extractability",
                severity="minor",
                description=f"Text extraction quality low ({text_quality}/100).",
                metric=text_quality,
                recommendation="Check font embedding and encoding.",
            ))
            score -= 8

        # ── Embedded image quality ─────────────────────────────────────────
        img_issues = self._check_pdf_images(pdf_path)
        issues.extend(img_issues)
        for issue in img_issues:
            score -= 15 if issue.severity == "major" else 8

        # ── Page count and structure ───────────────────────────────────────
        page_count = self._get_pdf_page_count(pdf_path)
        metadata["page_count"] = page_count
        if page_count == 0:
            issues.append(QualityIssue(
                category="formatting",
                severity="critical",
                description="Could not read PDF pages.",
                recommendation="Check PDF structure and re-generate.",
            ))
            score -= 30

        # ── File size sanity ───────────────────────────────────────────────
        file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        metadata["file_size_mb"] = round(file_size_mb, 2)
        if file_size_mb > 100:
            issues.append(QualityIssue(
                category="compression",
                severity="minor",
                description=f"Very large PDF: {file_size_mb:.1f}MB.",
                metric=file_size_mb,
                recommendation="Compress images within PDF.",
            ))
            score -= 5

        score = max(0.0, min(100.0, score))
        result = {
            "score": round(score, 2),
            "passed": score >= self.score_threshold,
            "issues": [i.to_dict() for i in issues],
            "recommendations": [i.recommendation for i in issues if i.recommendation],
            "metadata": metadata,
        }
        self._record("pdf_quality", pdf_path, result)
        return result

    # ── Document compliance ──────────────────────────────────────────────────

    def check_document_compliance(self, doc_path: str, template: dict) -> dict:
        """
        Check document against a template specification.

        Template: required_pages, required_sections, fonts, margins,
        header_footer, page_size.
        """
        if not os.path.exists(doc_path):
            return self._error_result(f"File not found: {doc_path}")

        issues: list[QualityIssue] = []
        score = 100.0
        metadata: dict[str, Any] = {"path": doc_path, "template": template}

        ext = os.path.splitext(doc_path)[1].lower()

        if ext == ".pdf":
            page_count = self._get_pdf_page_count(doc_path)
            text_content, _ = self._extract_pdf_text(doc_path)
        else:
            page_count = 0
            text_content = ""
            issues.append(QualityIssue(
                category="format",
                severity="info",
                description=f"Compliance checking for '{ext}' is limited.",
                recommendation="Use PDF for full compliance checking.",
            ))

        metadata["page_count"] = page_count

        # Required pages
        if "required_pages" in template and page_count < template["required_pages"]:
            issues.append(QualityIssue(
                category="template_mismatch",
                severity="major",
                description=f"Pages {page_count} < required {template['required_pages']}.",
                recommendation="Add missing content pages.",
            ))
            score -= 15

        # Required sections
        if "required_sections" in template:
            missing = []
            for section in template["required_sections"]:
                if section.lower() not in text_content.lower():
                    missing.append(section)
            if missing:
                issues.append(QualityIssue(
                    category="template_mismatch",
                    severity="major",
                    description=f"Missing sections: {missing}.",
                    recommendation="Add required document sections.",
                ))
                score -= 12

        # Font check (basic)
        if "fonts" in template and ext == ".pdf" and _HAS_FITZ:
            doc_fonts = self._extract_pdf_fonts(doc_path)
            metadata["detected_fonts"] = doc_fonts
            for font in template["fonts"]:
                if font.lower() not in [f.lower() for f in doc_fonts]:
                    issues.append(QualityIssue(
                        category="template_mismatch",
                        severity="minor",
                        description=f"Required font '{font}' not detected.",
                        recommendation=f"Ensure '{font}' is embedded in the PDF.",
                    ))
                    score -= 5

        # Page size check
        if "page_size" in template and ext == ".pdf" and _HAS_FITZ:
            actual_size = self._get_pdf_page_size(doc_path)
            metadata["page_size"] = actual_size
            req_size = template["page_size"]
            if actual_size and actual_size.upper() != req_size.upper():
                issues.append(QualityIssue(
                    category="template_mismatch",
                    severity="minor",
                    description=f"Page size '{actual_size}' != required '{req_size}'.",
                    recommendation=f"Set page size to {req_size}.",
                ))
                score -= 5

        score = max(0.0, min(100.0, score))
        result = {
            "score": round(score, 2),
            "passed": score >= self.score_threshold,
            "issues": [i.to_dict() for i in issues],
            "recommendations": [i.recommendation for i in issues if i.recommendation],
            "metadata": metadata,
        }
        self._record("document_compliance", doc_path, result)
        return result

    # ═════════════════════════════════════════════════════════════════════════
    # CORRECTION PIPELINE
    # ═════════════════════════════════════════════════════════════════════════

    def generate_fix_prompt(self, issues: list) -> str:
        """
        Generate a correction prompt from a list of quality issues.

        The prompt is designed to be sent back to the generation pipeline
        to instruct it on how to fix the detected problems.
        """
        if not issues:
            return "No issues detected. Output is approved."

        lines = [
            "=== JARVIS VISUAL QA — CORRECTION REQUIRED ===",
            f"Total issues detected: {len(issues)}",
            "",
            "Issues to fix:",
        ]

        for idx, issue in enumerate(issues, 1):
            lines.append(f"  {idx}. [{issue.get('severity', 'unknown').upper()}] "
                         f"{issue.get('category', 'unknown')}: {issue.get('description', '')}")
            if issue.get("recommendation"):
                lines.append(f"     Action: {issue['recommendation']}")
            if issue.get("metric") is not None:
                lines.append(f"     Metric: {issue['metric']}")
            lines.append("")

        # Prioritize critical issues first
        critical = [i for i in issues if i.get("severity") == "critical"]
        major = [i for i in issues if i.get("severity") == "major"]

        lines.extend([
            "Priority order:",
            f"  1. Fix {len(critical)} critical issue(s).",
            f"  2. Fix {len(major)} major issue(s).",
            "  3. Address minor issues if time permits.",
            "",
            "Generate a corrected version addressing all issues above.",
            "=== END CORRECTION PROMPT ===",
        ])

        return "\n".join(lines)

    def request_correction(self, original: str, issues: list) -> dict:
        """
        Trigger a correction request for a failing asset.

        Returns a dict with the correction prompt, estimated effort,
        and a tracking ID for the correction job.
        """
        correction_id = hashlib.sha256(
            f"{original}:{time.time()}".encode()
        ).hexdigest()[:16]

        prompt = self.generate_fix_prompt(issues)

        # Estimate effort based on issue severity
        effort_map = {"critical": 5, "major": 3, "minor": 1, "info": 0}
        estimated_effort = sum(
            effort_map.get(i.get("severity", "minor"), 1) for i in issues
        )

        # Determine correction strategy
        strategies = []
        categories = {i.get("category", "") for i in issues}
        if "blur" in categories or "noise" in categories:
            strategies.append("re_generate")
        if "resolution" in categories or "aspect_ratio" in categories:
            strategies.append("resize")
        if "compression" in categories or "artifacts" in categories:
            strategies.append("re_encode")
        if "format" in categories:
            strategies.append("convert_format")
        if "text_extractability" in categories:
            strategies.append("ocr_or_recreate")
        if "template_mismatch" in categories:
            strategies.append("restructure")
        if not strategies:
            strategies.append("re_generate")

        correction_request = {
            "correction_id": correction_id,
            "original_file": original,
            "status": "pending",
            "prompt": prompt,
            "estimated_effort": estimated_effort,
            "strategies": strategies,
            "issue_count": len(issues),
            "critical_issues": sum(1 for i in issues if i.get("severity") == "critical"),
            "created_at": datetime.utcnow().isoformat() + "Z",
        }

        logger.info(
            "Correction requested: id=%s, file=%s, issues=%d, strategies=%s",
            correction_id, os.path.basename(original), len(issues), strategies,
        )
        return correction_request

    def compare_versions(self, original: str, corrected: str) -> dict:
        """
        Compare original and corrected versions.

        Returns a detailed before/after comparison with improvement metrics.
        """
        # Determine file type and run appropriate checks
        ext = os.path.splitext(original)[1].lower()

        if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"):
            original_result = self.check_image_quality(original)
            corrected_result = self.check_image_quality(corrected)
            check_type = "image"
        elif ext in (".mp4", ".avi", ".mov", ".mkv", ".webm"):
            original_result = self.check_video_quality(original)
            corrected_result = self.check_video_quality(corrected)
            check_type = "video"
        elif ext == ".pdf":
            original_result = self.check_pdf_quality(original)
            corrected_result = self.check_pdf_quality(corrected)
            check_type = "pdf"
        else:
            return {"error": f"Unsupported file type: {ext}"}

        orig_score = original_result.get("score", 0)
        corr_score = corrected_result.get("score", 0)
        improvement = corr_score - orig_score

        # Check for regression (new issues introduced)
        orig_categories = {i["category"] for i in original_result.get("issues", [])}
        corr_categories = {i["category"] for i in corrected_result.get("issues", [])}
        new_issues = corr_categories - orig_categories

        comparison = {
            "check_type": check_type,
            "original": {
                "path": original,
                "score": orig_score,
                "issue_count": len(original_result.get("issues", [])),
            },
            "corrected": {
                "path": corrected,
                "score": corr_score,
                "issue_count": len(corrected_result.get("issues", [])),
            },
            "improvement": round(improvement, 2),
            "improved": improvement > 0,
            "passed": corr_score >= self.score_threshold,
            "regressions": list(new_issues),
            "has_regression": len(new_issues) > 0,
            "remaining_issues": [i.to_dict() if isinstance(i, QualityIssue) else i
                                 for i in corrected_result.get("issues", [])],
            "verified_at": datetime.utcnow().isoformat() + "Z",
        }

        logger.info(
            "Version comparison: original=%.1f -> corrected=%.1f (Δ%+.1f)",
            orig_score, corr_score, improvement,
        )
        return comparison

    def approve_correction(self, corrected: Union[str, dict]) -> bool:
        """
        Final approval check for a corrected asset.

        If `corrected` is a file path, runs full QA.  If it's a dict
        (result from compare_versions), evaluates directly.
        """
        if isinstance(corrected, str):
            ext = os.path.splitext(corrected)[1].lower()
            if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
                result = self.check_image_quality(corrected)
            elif ext in (".mp4", ".avi", ".mov", ".mkv", ".webm"):
                result = self.check_video_quality(corrected)
            elif ext == ".pdf":
                result = self.check_pdf_quality(corrected)
            else:
                logger.warning("Cannot approve unknown type: %s", ext)
                return False
            score = result.get("score", 0)
        else:
            score = corrected.get("corrected", {}).get("score", 0)

        approved = score >= self.score_threshold
        logger.info(
            "Correction approval: score=%.1f, threshold=%d, approved=%s",
            score, self.score_threshold, approved,
        )
        return approved

    # ═════════════════════════════════════════════════════════════════════════
    # BATCH PROCESSING
    # ═════════════════════════════════════════════════════════════════════════

    def batch_check(self, files: list[Union[str, dict]]) -> list[dict]:
        """
        Check multiple files in sequence.

        Each item can be a path string or a dict with 'path' and optional
        'requirements' / 'template' keys.
        """
        results = []
        logger.info("Starting batch check of %d file(s)", len(files))

        for item in files:
            if isinstance(item, str):
                path = item
                reqs = {}
                check_type = "auto"
            else:
                path = item.get("path", "")
                reqs = item.get("requirements", item.get("template", {}))
                check_type = item.get("type", "auto")

            if not path or not os.path.exists(path):
                results.append({
                    "path": path,
                    "error": "File not found",
                    "score": 0,
                    "passed": False,
                })
                continue

            ext = os.path.splitext(path)[1].lower()

            # Auto-detect type
            if check_type == "auto":
                if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"):
                    check_type = "image"
                elif ext in (".mp4", ".avi", ".mov", ".mkv", ".webm"):
                    check_type = "video"
                elif ext == ".pdf":
                    check_type = "pdf"
                else:
                    check_type = "unknown"

            try:
                if check_type == "image":
                    if reqs:
                        result = self.check_image_compliance(path, reqs)
                    else:
                        result = self.check_image_quality(path)
                elif check_type == "video":
                    if reqs:
                        result = self.check_video_compliance(path, reqs)
                    else:
                        result = self.check_video_quality(path)
                elif check_type == "pdf":
                    if reqs:
                        result = self.check_document_compliance(path, reqs)
                    else:
                        result = self.check_pdf_quality(path)
                else:
                    result = {"error": f"Unknown file type: {ext}", "score": 0, "passed": False}

                result["path"] = path
                results.append(result)
            except Exception as exc:
                logger.error("Batch check failed for %s: %s", path, exc)
                results.append({
                    "path": path,
                    "error": str(exc),
                    "score": 0,
                    "passed": False,
                })

        passed_count = sum(1 for r in results if r.get("passed"))
        logger.info(
            "Batch check complete: %d/%d passed",
            passed_count, len(files),
        )
        return results

    def batch_correct(self, results: list[dict]) -> list[dict]:
        """
        Generate correction requests for all failing results.

        Takes the output of `batch_check` and returns a list of
        correction request dicts for items that did not pass.
        """
        corrections = []
        logger.info("Processing corrections for %d result(s)", len(results))

        for result in results:
            if result.get("passed"):
                continue

            path = result.get("path", "")
            issues = result.get("issues", [])

            if not path or not issues:
                continue

            correction = self.request_correction(path, issues)
            correction["original_result"] = result
            corrections.append(correction)

        logger.info("Generated %d correction request(s)", len(corrections))
        return corrections

    # ═════════════════════════════════════════════════════════════════════════
    # METRICS
    # ═════════════════════════════════════════════════════════════════════════

    def get_quality_trends(self, window: Optional[int] = None) -> dict:
        """
        Get quality score trends over time.

        Parameters
        ----------
        window : int, optional
            Number of most-recent entries to consider.

        Returns
        -------
        dict
            trend data with averages, pass rates, and time series.
        """
        data = self._history
        if window:
            data = data[-window:]

        if not data:
            return {"message": "No quality data available yet.", "data_points": 0}

        scores = [e["score"] for e in data if e.get("score") is not None]
        passed = [e for e in data if e.get("passed")]

        # Time-binned averages (by day)
        daily: dict[str, list[float]] = defaultdict(list)
        for entry in data:
            if entry.get("score") is not None:
                day = entry["timestamp"][:10] if entry.get("timestamp") else "unknown"
                daily[day].append(entry["score"])

        daily_averages = {
            day: round(sum(vals) / len(vals), 2) if vals else 0
            for day, vals in sorted(daily.items())
        }

        # Trend direction
        if len(daily_averages) >= 2:
            vals = list(daily_averages.values())
            trend = "improving" if vals[-1] > vals[0] else "declining" if vals[-1] < vals[0] else "stable"
        else:
            trend = "insufficient_data"

        return {
            "data_points": len(data),
            "average_score": round(sum(scores) / len(scores), 2) if scores else 0,
            "median_score": round(sorted(scores)[len(scores) // 2], 2) if scores else 0,
            "min_score": round(min(scores), 2) if scores else 0,
            "max_score": round(max(scores), 2) if scores else 0,
            "pass_rate": round(len(passed) / len(data) * 100, 2) if data else 0,
            "trend": trend,
            "daily_averages": daily_averages,
            "check_type_breakdown": self._breakdown_by_check_type(data),
        }

    def get_failure_patterns(self) -> dict:
        """
        Analyse common failure patterns from the failure log.

        Returns categories ranked by frequency, correlated issue types,
        and recommendations for pipeline improvement.
        """
        failures = self._failure_log
        if not failures:
            return {"message": "No failures recorded yet.", "failure_count": 0}

        # Category frequency
        category_counts: dict[str, int] = defaultdict(int)
        file_failure_counts: dict[str, int] = defaultdict(int)
        check_type_failures: dict[str, int] = defaultdict(int)

        for entry in failures:
            for cat in entry.get("issue_categories", []):
                if cat:
                    category_counts[cat] += 1
            file_failure_counts[entry.get("file", "unknown")] += 1
            check_type_failures[entry.get("check_type", "unknown")] += 1

        top_categories = sorted(
            category_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]

        # Files with most failures
        problem_files = sorted(
            file_failure_counts.items(), key=lambda x: x[1], reverse=True
        )[:5]

        # Check type distribution
        check_type_distribution = dict(sorted(
            check_type_failures.items(), key=lambda x: x[1], reverse=True
        ))

        # Generate pipeline improvement recommendations
        recommendations = []
        for category, count in top_categories[:5]:
            rec = self._category_recommendation(category)
            recommendations.append({
                "category": category,
                "failure_count": count,
                "recommendation": rec,
            })

        return {
            "failure_count": len(failures),
            "top_issue_categories": [
                {"category": cat, "count": count} for cat, count in top_categories
            ],
            "problem_files": [
                {"file": f, "failures": c} for f, c in problem_files
            ],
            "check_type_distribution": check_type_distribution,
            "pipeline_recommendations": recommendations,
        }

    # ── Metrics helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _breakdown_by_check_type(data: list[dict]) -> dict:
        breakdown: dict[str, dict] = {}
        for entry in data:
            ct = entry.get("check_type", "unknown")
            if ct not in breakdown:
                breakdown[ct] = {"count": 0, "scores": [], "passed": 0}
            breakdown[ct]["count"] += 1
            if entry.get("score") is not None:
                breakdown[ct]["scores"].append(entry["score"])
            if entry.get("passed"):
                breakdown[ct]["passed"] += 1

        for ct, stats in breakdown.items():
            scores = stats.pop("scores")
            stats["average_score"] = round(sum(scores) / len(scores), 2) if scores else 0
            stats["pass_rate"] = round(stats["passed"] / stats["count"] * 100, 2) if stats["count"] else 0

        return breakdown

    @staticmethod
    def _category_recommendation(category: str) -> str:
        recs = {
            "blur": "Add sharpening post-processing or increase generation quality settings.",
            "noise": "Apply denoising filter or improve source lighting conditions.",
            "artifacts": "Reduce compression ratio or switch to a better encoder.",
            "compression": "Increase quality setting or use lossless format for intermediates.",
            "resolution": "Verify output resolution settings in generation pipeline.",
            "aspect_ratio": "Add aspect ratio enforcement to generation parameters.",
            "color_profile": "Standardize on sRGB and embed color profile.",
            "format": "Set explicit output format in generation config.",
            "frame_drops": "Use constant frame-rate encoding; avoid variable frame-rate sources.",
            "audio_sync": "Re-mux with corrected audio offset or use -async ffmpeg option.",
            "duration": "Add duration validation before final output.",
            "codec": "Standardize codec settings (H.264/HEVC recommended).",
            "bitrate": "Set minimum bitrate thresholds per resolution tier.",
            "text_extractability": "Ensure fonts are embedded; avoid rasterizing text.",
            "formatting": "Add template validation step to document pipeline.",
            "template_mismatch": "Enforce template compliance checks pre-approval.",
        }
        return recs.get(category, f"Review and address '{category}' issues in pipeline.")

    # ═════════════════════════════════════════════════════════════════════════
    # IMAGE ANALYSIS INTERNALS
    # ═════════════════════════════════════════════════════════════════════════

    def _load_image(self, path: str) -> tuple[Optional[np.ndarray], Optional[Any]]:
        """Load image as numpy array (RGB) and optional PIL Image."""
        pil_img = None
        img_array = None

        if _HAS_PIL:
            try:
                pil_img = Image.open(path).convert("RGB")
                img_array = np.array(pil_img)
            except Exception as exc:
                logger.debug("PIL load failed for %s: %s", path, exc)

        if img_array is None and _HAS_CV2:
            try:
                img_array = cv2.imread(path)
                if img_array is not None:
                    img_array = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
            except Exception as exc:
                logger.debug("CV2 load failed for %s: %s", path, exc)

        return img_array, pil_img

    def _detect_blur(self, img: np.ndarray) -> float:
        """Estimate blur using Laplacian variance (higher = sharper)."""
        if _HAS_CV2:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img
            return float(cv2.Laplacian(gray, cv2.CV_64F).var())
        # Fallback: simple gradient-based estimate
        if img.ndim == 3:
            img = np.mean(img, axis=2)
        gy, gx = np.gradient(img.astype(np.float32))
        return float(np.mean(gx ** 2 + gy ** 2))

    def _detect_noise(self, img: np.ndarray) -> float:
        """Estimate noise level using median absolute deviation."""
        if _HAS_CV2:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img
            blur = cv2.medianBlur(gray, 5)
            diff = np.abs(gray.astype(np.float32) - blur.astype(np.float32))
            return float(np.median(diff) * 2)
        # Simple fallback
        if img.ndim == 3:
            img = np.mean(img, axis=2)
        return float(np.std(img.astype(np.float32)))

    def _detect_artifacts_internal(self, img: np.ndarray) -> float:
        """
        Detect compression artifacts by comparing block boundaries.
        Returns a score where higher = more artifacts.
        """
        if img.ndim == 3:
            gray = np.mean(img, axis=2).astype(np.uint8)
        else:
            gray = img.astype(np.uint8)

        # Detect JPEG blocking artifacts (8x8 block boundaries)
        block_size = 8
        h, w = gray.shape
        block_h, block_w = h // block_size, w // block_size
        if block_h < 2 or block_w < 2:
            return 0.0

        # Measure discontinuity at block boundaries vs interior
        h_diff = np.abs(np.diff(gray.astype(np.int16), axis=0)).astype(np.float32)
        w_diff = np.abs(np.diff(gray.astype(np.int16), axis=1)).astype(np.float32)

        # Boundary positions — convert slices to index arrays for np.delete
        h_del_idx = np.arange(block_size - 1, h_diff.shape[0], block_size)
        h_boundaries = h_diff[h_del_idx, :] if len(h_del_idx) else h_diff[:0, :]
        h_interior = np.delete(h_diff, h_del_idx, axis=0) if len(h_del_idx) else h_diff

        w_del_idx = np.arange(block_size - 1, w_diff.shape[1], block_size)
        w_boundaries = w_diff[:, w_del_idx] if len(w_del_idx) else w_diff[:, :0]
        w_interior = np.delete(w_diff, w_del_idx, axis=1) if len(w_del_idx) else w_diff

        if h_interior.size == 0 or w_interior.size == 0:
            return 0.0

        h_ratio = np.mean(h_boundaries) / (np.mean(h_interior) + 1e-6)
        w_ratio = np.mean(w_boundaries) / (np.mean(w_interior) + 1e-6)

        return float(max(h_ratio, w_ratio) * 10)

    def _detect_blocking(self, img: np.ndarray) -> float:
        """Detect macro-blocking artifacts common in low-bitrate video frames."""
        if _HAS_CV2:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img
            # Sobel edge detection
            sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
            sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
            edge_mag = np.sqrt(sobelx ** 2 + sobely ** 2)
            # Blocking creates unnatural straight edges
            h_straight = np.mean(np.abs(np.diff(edge_mag, axis=0)))
            v_straight = np.mean(np.abs(np.diff(edge_mag, axis=1)))
            return float((h_straight + v_straight) / 2)
        return 0.0

    def _detect_general_artifacts(self, img: np.ndarray) -> list[QualityIssue]:
        """Detect various visual artifacts: ringing, halos, posterization."""
        issues = []

        # Ringing detection (overshoot near edges)
        if _HAS_CV2:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.ndim == 3 else img
            blur = cv2.GaussianBlur(gray, (0, 0), 2)
            diff = np.abs(gray.astype(np.float32) - blur.astype(np.float32))
            ringing_score = float(np.percentile(diff, 99))
            if ringing_score > 40:
                issues.append(QualityIssue(
                    category="artifacts",
                    severity="minor",
                    description=f"Ringing artifacts detected near edges (score={ringing_score:.1f}).",
                    metric=ringing_score,
                    recommendation="Reduce sharpening strength or use anti-ringing filter.",
                ))

        # Posterization detection (quantization bands)
        if img.ndim == 3:
            for i, channel in enumerate(["R", "G", "B"]):
                ch = img[:, :, i]
                unique_colors = len(np.unique(ch))
                total_pixels = ch.size
                ratio = unique_colors / min(total_pixels, 256)
                if ratio < 0.3 and unique_colors < 64:
                    issues.append(QualityIssue(
                        category="artifacts",
                        severity="minor",
                        description=f"Posterization in {channel} channel ({unique_colors} levels).",
                        metric=unique_colors,
                        recommendation="Use higher bit-depth source or add dithering.",
                    ))

        return issues

    def _detect_color_banding(self, img: np.ndarray) -> float:
        """Detect color banding in smooth gradient regions."""
        if img.ndim != 3:
            return 0.0
        gray = np.mean(img, axis=2).astype(np.float32)
        # Detect flat regions with sharp transitions (bands)
        second_deriv = np.abs(np.diff(gray, n=2, axis=0)) + np.abs(np.diff(gray, n=2, axis=1)[:, :gray.shape[0]-2])
        # High second derivative in otherwise smooth regions indicates banding
        banding_score = float(np.percentile(second_deriv, 95))
        return banding_score

    def _get_color_profile(self, pil_img: Any) -> str:
        """Extract embedded color profile name from PIL Image."""
        try:
            icc = pil_img.info.get("icc_profile")
            if icc:
                # Simple detection from ICC header
                if b"sRGB" in icc[:128]:
                    return "sRGB"
                if b"Adobe" in icc[:128]:
                    return "Adobe RGB"
                if b"ProPhoto" in icc[:128]:
                    return "ProPhoto RGB"
                return "ICC Embedded"
            return "sRGB (assumed)"
        except Exception:
            return "unknown"

    # ═════════════════════════════════════════════════════════════════════════
    # VIDEO ANALYSIS INTERNALS
    # ═════════════════════════════════════════════════════════════════════════

    def _probe_video(self, path: str) -> dict:
        """Probe video file using ffprobe or OpenCV fallback."""
        probe: dict[str, Any] = {}

        # Try ffprobe first
        if self.capabilities["ffmpeg"]:
            try:
                result = subprocess.run(
                    [
                        "ffprobe", "-v", "quiet", "-print_format", "json",
                        "-show_format", "-show_streams", path,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                    return self._parse_ffprobe(data)
            except Exception as exc:
                logger.debug("ffprobe failed: %s", exc)

        # Fallback to OpenCV
        if _HAS_CV2:
            try:
                cap = cv2.VideoCapture(path)
                if cap.isOpened():
                    probe["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    probe["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    probe["fps"] = cap.get(cv2.CAP_PROP_FPS)
                    probe["frame_count"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                    probe["duration"] = (
                        probe["frame_count"] / probe["fps"]
                        if probe["fps"] > 0 else 0
                    )
                    cap.release()
            except Exception as exc:
                logger.debug("OpenCV probe failed: %s", exc)

        return probe

    @staticmethod
    def _parse_ffprobe(data: dict) -> dict:
        """Parse ffprobe JSON output into a normalized dict."""
        probe: dict[str, Any] = {}
        video_stream = None
        audio_stream = None

        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video" and video_stream is None:
                video_stream = stream
            elif stream.get("codec_type") == "audio" and audio_stream is None:
                audio_stream = stream

        if video_stream:
            probe["width"] = video_stream.get("width", 0)
            probe["height"] = video_stream.get("height", 0)
            probe["codec"] = video_stream.get("codec_name", "")

            # Parse frame rate
            r_frame_rate = video_stream.get("r_frame_rate", "0/1")
            try:
                num, den = map(int, r_frame_rate.split("/"))
                probe["fps"] = num / den if den else 0
            except Exception:
                probe["fps"] = 0

            probe["frame_count"] = video_stream.get("nb_frames", 0)
            probe["bitrate_kbps"] = (
                int(video_stream.get("bit_rate", 0)) // 1000
                if video_stream.get("bit_rate")
                else 0
            )
            probe["pix_fmt"] = video_stream.get("pix_fmt", "")

        if audio_stream:
            probe["audio_codec"] = audio_stream.get("codec_name", "")
            probe["audio_delay_ms"] = int(
                audio_stream.get("start_time", "0") or "0"
            ) * 1000

        fmt = data.get("format", {})
        probe["duration"] = float(fmt.get("duration", 0) or 0)
        probe["format_name"] = fmt.get("format_name", "")
        if not probe.get("bitrate_kbps"):
            probe["bitrate_kbps"] = int(fmt.get("bit_rate", 0) or 0) // 1000

        return probe

    @staticmethod
    def _min_recommended_bitrate(width: int, height: int, fps: float) -> int:
        """Calculate minimum recommended bitrate in kbps for given resolution."""
        pixels = width * height
        if pixels <= 720 * 480:
            base = 2500
        elif pixels <= 1280 * 720:
            base = 5000
        elif pixels <= 1920 * 1080:
            base = 8000
        elif pixels <= 3840 * 2160:
            base = 25000
        else:
            base = 50000

        # Adjust for frame rate
        fps_factor = min(fps / 30, 2.0) if fps > 0 else 1.0
        return int(base * fps_factor)

    # ═════════════════════════════════════════════════════════════════════════
    # DOCUMENT ANALYSIS INTERNALS
    # ═════════════════════════════════════════════════════════════════════════

    def _extract_pdf_text(self, pdf_path: str) -> tuple[bool, float]:
        """Extract text from PDF and return (success, quality_score)."""
        if not _HAS_FITZ:
            return False, 0.0

        try:
            doc = fitz.open(pdf_path)
            total_text = ""
            total_chars = 0
            garbage_chars = 0

            for page in doc:
                text = page.get_text()
                total_text += text
                total_chars += len(text)
                # Count suspicious characters (poor encoding)
                garbage_chars += len(re.findall(r'[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f]', text))

            doc.close()

            has_text = total_chars > 0
            if not has_text:
                return False, 0.0

            # Quality: ratio of garbage to total chars
            quality = max(0, 100 - (garbage_chars / max(total_chars, 1) * 100))
            return True, round(quality, 2)
        except Exception as exc:
            logger.debug("PDF text extraction failed: %s", exc)
            return False, 0.0

    def _check_pdf_images(self, pdf_path: str) -> list[QualityIssue]:
        """Check quality of images embedded in a PDF."""
        issues = []
        if not _HAS_FITZ:
            return issues

        try:
            doc = fitz.open(pdf_path)
            low_res_images = 0
            total_images = 0

            for page_num, page in enumerate(doc):
                images = page.get_images(full=True)
                for img_index, img in enumerate(images):
                    total_images += 1
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    if base_image:
                        width = base_image.get("width", 0)
                        height = base_image.get("height", 0)
                        if width < 300 or height < 300:
                            low_res_images += 1

            doc.close()

            if total_images > 0 and low_res_images / total_images > 0.5:
                issues.append(QualityIssue(
                    category="formatting",
                    severity="major",
                    description=f"{low_res_images}/{total_images} embedded images are low resolution (<300px).",
                    recommendation="Use higher resolution source images in PDF.",
                ))

            if total_images == 0:
                issues.append(QualityIssue(
                    category="formatting",
                    severity="info",
                    description="No embedded images found in PDF.",
                    recommendation="N/A",
                ))

        except Exception as exc:
            logger.debug("PDF image check failed: %s", exc)

        return issues

    def _get_pdf_page_count(self, pdf_path: str) -> int:
        """Get the number of pages in a PDF."""
        if _HAS_FITZ:
            try:
                doc = fitz.open(pdf_path)
                count = len(doc)
                doc.close()
                return count
            except Exception:
                pass
        return 0

    def _extract_pdf_fonts(self, pdf_path: str) -> list[str]:
        """Extract list of fonts used in a PDF."""
        fonts = []
        if not _HAS_FITZ:
            return fonts
        try:
            doc = fitz.open(pdf_path)
            font_set: set[str] = set()
            for page in doc:
                for font in page.get_fonts():
                    font_set.add(font[3])  # font name is at index 3
            doc.close()
            fonts = sorted(font_set)
        except Exception:
            pass
        return fonts

    def _get_pdf_page_size(self, pdf_path: str) -> str:
        """Detect common page size from first page dimensions."""
        if not _HAS_FITZ:
            return ""
        try:
            doc = fitz.open(pdf_path)
            page = doc[0]
            rect = page.rect
            w, h = rect.width, rect.height
            doc.close()

            # Common sizes in points (1 inch = 72 points)
            sizes = {
                "A4": (595, 842),
                "Letter": (612, 792),
                "Legal": (612, 1008),
                "A3": (842, 1191),
                "A5": (420, 595),
            }
            for name, (sw, sh) in sizes.items():
                if abs(w - sw) < 10 and abs(h - sh) < 10:
                    return name
            return f"{int(w)}x{int(h)}pt"
        except Exception:
            return ""

    # ── Shared error helper ──────────────────────────────────────────────────

    @staticmethod
    def _error_result(message: str) -> dict:
        return {
            "score": 0.0,
            "passed": False,
            "issues": [{
                "category": "error",
                "severity": "critical",
                "description": message,
                "recommendation": "Check file path and permissions.",
            }],
            "recommendations": ["Check file path and permissions."],
            "metadata": {"error": message},
        }


# ═══════════════════════════════════════════════════════════════════════════════
# MockVisualQA — Deterministic simulator for testing
# ═══════════════════════════════════════════════════════════════════════════════

class MockVisualQA(VisualQAEngine):
    """
    Deterministic mock implementation of VisualQAEngine.

    Simulates quality checks with reproducible, predictable results
    based on filename hashing.  Useful for CI pipelines and unit tests
    where you don't want to pull in heavy dependencies.
    """

    def __init__(self, score_threshold: int = DEFAULT_SCORE_THRESHOLD) -> None:
        # Skip parent __init__ heavy setup
        self.score_threshold = score_threshold
        self._history: list[dict] = []
        self._failure_log: list[dict] = []
        self.capabilities = {
            "pil": True,
            "cv2": True,
            "skimage": True,
            "fitz": True,
            "ffmpeg": True,
        }

    def _seed_from_path(self, path: str) -> np.random.Generator:
        """Create a deterministic RNG from file path."""
        seed = int(hashlib.md5(path.encode()).hexdigest(), 16) % (2 ** 32)
        return np.random.default_rng(seed)

    def check_image_quality(self, image_path: str) -> dict:
        rng = self._seed_from_path(image_path)
        score = float(rng.integers(60, 100))
        issues = []

        if score < self.score_threshold:
            categories = ["blur", "noise", "artifacts", "compression"]
            rng.shuffle(categories)
            num_issues = rng.integers(1, 3)
            for cat in categories[:num_issues]:
                severity = "critical" if score < 50 else "major"
                issues.append({
                    "category": cat,
                    "severity": severity,
                    "description": f"Simulated {cat} issue.",
                    "metric": float(rng.integers(10, 50)),
                    "recommendation": f"Fix the simulated {cat} issue.",
                })

        result = {
            "score": round(score, 2),
            "passed": score >= self.score_threshold,
            "issues": issues,
            "recommendations": [i["recommendation"] for i in issues],
            "metadata": {"mock": True, "path": image_path},
        }
        self._record("image_quality", image_path, result)
        return result

    def check_image_compliance(self, image_path: str, requirements: dict) -> dict:
        rng = self._seed_from_path(image_path)
        score = float(rng.integers(70, 100))
        result = {
            "score": round(score, 2),
            "passed": score >= self.score_threshold,
            "issues": [],
            "recommendations": [],
            "metadata": {"mock": True, "requirements": requirements},
        }
        self._record("image_compliance", image_path, result)
        return result

    def detect_artifacts(self, image: Union[str, np.ndarray]) -> list:
        path = image if isinstance(image, str) else "array_input"
        rng = self._seed_from_path(path)
        count = rng.integers(0, 3)
        return [{"artifact": f"mock_artifact_{i}", "severity": "minor"} for i in range(count)]

    def check_color_accuracy(self, image: Union[str, np.ndarray], reference: Union[str, np.ndarray]) -> float:
        img_path = image if isinstance(image, str) else "array_a"
        rng = self._seed_from_path(img_path)
        return round(float(rng.integers(70, 100)), 2)

    def check_video_quality(self, video_path: str) -> dict:
        rng = self._seed_from_path(video_path)
        score = float(rng.integers(65, 100))
        issues = []
        if score < self.score_threshold:
            issues.append({
                "category": "frame_drops",
                "severity": "major",
                "description": "Simulated frame drop issue.",
                "recommendation": "Re-encode with constant frame rate.",
            })
        result = {
            "score": round(score, 2),
            "passed": score >= self.score_threshold,
            "issues": issues,
            "recommendations": [i["recommendation"] for i in issues],
            "metadata": {"mock": True, "path": video_path},
        }
        self._record("video_quality", video_path, result)
        return result

    def check_video_compliance(self, video_path: str, requirements: dict) -> dict:
        rng = self._seed_from_path(video_path)
        score = float(rng.integers(75, 100))
        result = {
            "score": round(score, 2),
            "passed": score >= self.score_threshold,
            "issues": [],
            "recommendations": [],
            "metadata": {"mock": True, "requirements": requirements},
        }
        self._record("video_compliance", video_path, result)
        return result

    def check_pdf_quality(self, pdf_path: str) -> dict:
        rng = self._seed_from_path(pdf_path)
        score = float(rng.integers(70, 100))
        result = {
            "score": round(score, 2),
            "passed": score >= self.score_threshold,
            "issues": [],
            "recommendations": [],
            "metadata": {"mock": True, "path": pdf_path},
        }
        self._record("pdf_quality", pdf_path, result)
        return result

    def check_document_compliance(self, doc_path: str, template: dict) -> dict:
        rng = self._seed_from_path(doc_path)
        score = float(rng.integers(70, 100))
        result = {
            "score": round(score, 2),
            "passed": score >= self.score_threshold,
            "issues": [],
            "recommendations": [],
            "metadata": {"mock": True, "template": template},
        }
        self._record("document_compliance", doc_path, result)
        return result

    def compare_versions(self, original: str, corrected: str) -> dict:
        rng = self._seed_from_path(original + corrected)
        orig_score = float(rng.integers(50, 75))
        corr_score = float(rng.integers(80, 98))
        return {
            "check_type": "mock",
            "original": {"path": original, "score": orig_score, "issue_count": 2},
            "corrected": {"path": corrected, "score": corr_score, "issue_count": 0},
            "improvement": round(corr_score - orig_score, 2),
            "improved": True,
            "passed": corr_score >= self.score_threshold,
            "regressions": [],
            "has_regression": False,
            "remaining_issues": [],
            "verified_at": datetime.utcnow().isoformat() + "Z",
        }

    # Inherited methods that work fine:
    # generate_fix_prompt, request_correction, approve_correction,
    # batch_check, batch_correct, get_quality_trends, get_failure_patterns


# ═══════════════════════════════════════════════════════════════════════════════
# Factory
# ═══════════════════════════════════════════════════════════════════════════════

def get_visual_qa(mode: str = "auto", **kwargs: Any) -> VisualQAEngine:
    """
    Factory function to create the appropriate VisualQA implementation.

    Parameters
    ----------
    mode : str
        - "production" → full VisualQAEngine with all dependencies
        - "mock"     → MockVisualQA for deterministic testing
        - "auto"     → choose based on available dependencies
    **kwargs
        Passed to the engine constructor.

    Returns
    -------
    VisualQAEngine or MockVisualQA
    """
    mode = mode.lower()
    if mode == "mock":
        logger.info("Using MockVisualQA (deterministic testing mode)")
        return MockVisualQA(**kwargs)

    if mode == "production":
        logger.info("Using VisualQAEngine (production mode)")
        return VisualQAEngine(**kwargs)

    # Auto mode: check if we have enough real dependencies
    deps_available = _HAS_PIL or _HAS_CV2
    if deps_available:
        logger.info("Auto-selected VisualQAEngine (deps available)")
        return VisualQAEngine(**kwargs)
    else:
        logger.info("Auto-selected MockVisualQA (no image deps found)")
        return MockVisualQA(**kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience module-level interface (optional shorthand)
# ═══════════════════════════════════════════════════════════════════════════════

# Default singleton instance (lazily created)
_default_qa: Optional[VisualQAEngine] = None


def _get_default() -> VisualQAEngine:
    global _default_qa
    if _default_qa is None:
        _default_qa = get_visual_qa("auto")
    return _default_qa


# Shortcuts for quick checks
def quick_check_image(path: str) -> dict:
    return _get_default().check_image_quality(path)


def quick_check_video(path: str) -> dict:
    return _get_default().check_video_quality(path)


def quick_check_pdf(path: str) -> dict:
    return _get_default().check_pdf_quality(path)


# ═══════════════════════════════════════════════════════════════════════════════
# __main__ sanity check
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Run a quick sanity test with the mock engine
    print("=" * 60)
    print("JARVIS BRAINIAC — Visual QA Engine Self-Test")
    print("=" * 60)

    qa = get_visual_qa("mock", score_threshold=80)
    print(f"\nEngine: {type(qa).__name__}")
    print(f"Capabilities: {qa.capabilities}")

    # Test image quality
    result = qa.check_image_quality("/test/output/image_01.png")
    print(f"\nImage Quality Check:")
    print(f"  Score: {result['score']}")
    print(f"  Passed: {result['passed']}")
    print(f"  Issues: {len(result['issues'])}")

    # Test compliance
    compliance = qa.check_image_compliance(
        "/test/output/image_01.png",
        {"min_width": 1920, "min_height": 1080, "format": "png", "aspect_ratio": "16:9"},
    )
    print(f"\nImage Compliance Check:")
    print(f"  Score: {compliance['score']}")
    print(f"  Passed: {compliance['passed']}")

    # Test video quality
    vresult = qa.check_video_quality("/test/output/video_01.mp4")
    print(f"\nVideo Quality Check:")
    print(f"  Score: {vresult['score']}")
    print(f"  Passed: {vresult['passed']}")

    # Test PDF quality
    presult = qa.check_pdf_quality("/test/output/document_01.pdf")
    print(f"\nPDF Quality Check:")
    print(f"  Score: {presult['score']}")
    print(f"  Passed: {presult['passed']}")

    # Test correction pipeline
    if result["issues"]:
        prompt = qa.generate_fix_prompt(result["issues"])
        print(f"\nCorrection Prompt:\n{prompt[:200]}...")

        correction = qa.request_correction("/test/output/image_01.png", result["issues"])
        print(f"\nCorrection Request:")
        print(f"  ID: {correction['correction_id']}")
        print(f"  Strategies: {correction['strategies']}")

    # Test batch processing
    batch = qa.batch_check([
        "/test/output/img_01.png",
        "/test/output/img_02.png",
        "/test/output/vid_01.mp4",
    ])
    print(f"\nBatch Check: {len(batch)} files processed")
    passed = sum(1 for b in batch if b["passed"])
    print(f"  Passed: {passed}/{len(batch)}")

    # Test metrics
    trends = qa.get_quality_trends()
    print(f"\nQuality Trends:")
    print(f"  Data points: {trends.get('data_points')}")
    print(f"  Average score: {trends.get('average_score')}")

    patterns = qa.get_failure_patterns()
    print(f"\nFailure Patterns:")
    print(f"  Failure count: {patterns.get('failure_count')}")

    print("\n" + "=" * 60)
    print("Self-test complete. Visual QA Engine is operational.")
    print("=" * 60)
