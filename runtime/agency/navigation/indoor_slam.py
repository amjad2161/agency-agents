"""GODSKILL Nav v11 — Visual SLAM + Visual-Inertial Odometry.

Pure-Python implementations using only numpy:
- ORB-style FAST corner detection + binary descriptor
- Hamming distance feature matching with Lowe ratio test
- Essential matrix recovery via 8-point algorithm + SVD
- IMU pre-integration with mid-point Runge-Kutta
- Loose visual-inertial coupling with periodic visual correction
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# ------------------------------------------------------------------
# Data classes
# ------------------------------------------------------------------

@dataclass(frozen=True)
class KeyPoint:
    """Detected feature point in image coordinates."""
    x: float
    y: float
    response: float = 0.0
    angle: float = 0.0
    octave: int = 0


@dataclass(frozen=True)
class DMatch:
    """Match between two descriptors."""
    query_idx: int
    train_idx: int
    distance: float


@dataclass(frozen=True)
class Pose2D:
    x: float = 0.0
    y: float = 0.0
    theta: float = 0.0


@dataclass(frozen=True)
class Pose3D:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    qw: float = 1.0
    qx: float = 0.0
    qy: float = 0.0
    qz: float = 0.0


# ------------------------------------------------------------------
# ORB-style feature extraction
# ------------------------------------------------------------------

# 16-pixel circular FAST mask offsets (Bresenham circle of radius 3)
_FAST_OFFSETS: tuple[tuple[int, int], ...] = (
    (0, -3), (1, -3), (2, -2), (3, -1),
    (3, 0), (3, 1), (2, 2), (1, 3),
    (0, 3), (-1, 3), (-2, 2), (-3, 1),
    (-3, 0), (-3, -1), (-2, -2), (-1, -3),
)

# 64-pair BRIEF-style sampling pattern (deterministic for test stability)
_BRIEF_PAIRS: tuple[tuple[int, int, int, int], ...] = tuple(
    (
        ((i * 31 + 7) % 31) - 15,
        ((i * 53 + 11) % 31) - 15,
        ((i * 71 + 17) % 31) - 15,
        ((i * 97 + 23) % 31) - 15,
    )
    for i in range(64)
)


def _fast_score(image: np.ndarray, x: int, y: int, threshold: int) -> float:
    """FAST-9 score for a candidate pixel."""
    center = int(image[y, x])
    diffs = []
    for dx, dy in _FAST_OFFSETS:
        diffs.append(int(image[y + dy, x + dx]) - center)
    arr = np.asarray(diffs, dtype=np.int32)
    bright = int(np.sum(arr > threshold))
    dark = int(np.sum(arr < -threshold))
    if bright >= 9 or dark >= 9:
        return float(np.sum(np.abs(arr)))
    return 0.0


def _orientation(image: np.ndarray, x: int, y: int, radius: int = 3) -> float:
    """Intensity centroid orientation (rotation invariance)."""
    h, w = image.shape
    if x - radius < 0 or x + radius >= w or y - radius < 0 or y + radius >= h:
        return 0.0
    patch = image[y - radius:y + radius + 1, x - radius:x + radius + 1].astype(np.float32)
    ys, xs = np.mgrid[-radius:radius + 1, -radius:radius + 1]
    m10 = float(np.sum(xs * patch))
    m01 = float(np.sum(ys * patch))
    return math.atan2(m01, m10)


def _brief_descriptor(image: np.ndarray, x: int, y: int, angle: float) -> np.ndarray:
    """Rotated BRIEF descriptor — 64 bytes (512 bits)."""
    h, w = image.shape
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    bits = np.zeros(512, dtype=np.uint8)
    for i, (ax, ay, bx, by) in enumerate(_BRIEF_PAIRS):
        for k, (px, py) in enumerate(((ax, ay), (bx, by))):
            rx = int(round(cos_a * px - sin_a * py))
            ry = int(round(sin_a * px + cos_a * py))
            xx = max(0, min(w - 1, x + rx))
            yy = max(0, min(h - 1, y + ry))
            if k == 0:
                v1 = int(image[yy, xx])
            else:
                v2 = int(image[yy, xx])
        for j in range(8):
            shifted_a = ((ax * (j + 1)) % 5) - 2
            shifted_b = ((bx * (j + 1)) % 5) - 2
            xa = max(0, min(w - 1, x + rx + shifted_a))
            ya = max(0, min(h - 1, y + ry + shifted_b))
            bit_idx = i * 8 + j
            bits[bit_idx] = 1 if int(image[ya, xa]) > v1 else 0
    return np.packbits(bits)


class VisualSLAM:
    """Monocular Visual SLAM with ORB features and pose recovery."""

    def __init__(
        self,
        max_features: int = 500,
        fast_threshold: int = 20,
        ratio_test: float = 0.75,
    ):
        self.max_features = int(max_features)
        self.fast_threshold = int(fast_threshold)
        self.ratio_test = float(ratio_test)
        self._prev_kp: list[KeyPoint] = []
        self._prev_desc: Optional[np.ndarray] = None
        self._pose = Pose2D()
        self._cum_R = np.eye(3)
        self._cum_t = np.zeros(3)

    # -------- feature extraction --------

    def extract_orb_features(
        self, image_gray: np.ndarray
    ) -> tuple[list[KeyPoint], np.ndarray]:
        """Detect FAST corners and compute rotated BRIEF descriptors."""
        if image_gray.ndim != 2:
            raise ValueError("image_gray must be 2D")
        img = image_gray.astype(np.uint8, copy=False)
        h, w = img.shape
        candidates: list[KeyPoint] = []
        # Border of 3 px to keep FAST mask in bounds
        for y in range(3, h - 3, 2):
            for x in range(3, w - 3, 2):
                score = _fast_score(img, x, y, self.fast_threshold)
                if score > 0.0:
                    angle = _orientation(img, x, y)
                    candidates.append(KeyPoint(float(x), float(y), score, angle))
        candidates.sort(key=lambda k: k.response, reverse=True)
        kp = candidates[: self.max_features]
        if not kp:
            return [], np.zeros((0, 64), dtype=np.uint8)
        desc = np.stack([
            _brief_descriptor(img, int(k.x), int(k.y), k.angle) for k in kp
        ])
        return kp, desc

    # -------- matching --------

    def match_features(
        self,
        kp1: list[KeyPoint],
        desc1: np.ndarray,
        kp2: list[KeyPoint],
        desc2: np.ndarray,
    ) -> list[DMatch]:
        """Brute-force Hamming match with Lowe's ratio test."""
        if desc1.size == 0 or desc2.size == 0:
            return []
        # XOR each row of desc1 against all of desc2 then popcount
        matches: list[DMatch] = []
        unpacked2 = np.unpackbits(desc2, axis=1).astype(np.int32)
        for i in range(desc1.shape[0]):
            row = np.unpackbits(desc1[i:i + 1], axis=1).astype(np.int32)
            d = np.sum(np.abs(unpacked2 - row), axis=1)
            order = np.argsort(d)
            best, second = int(order[0]), int(order[1]) if len(order) > 1 else int(order[0])
            if len(order) == 1 or d[best] < self.ratio_test * d[second]:
                matches.append(DMatch(i, best, float(d[best])))
        return matches

    # -------- pose --------

    def estimate_pose(
        self,
        kp1: list[KeyPoint],
        kp2: list[KeyPoint],
        matches: list[DMatch],
        K: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Recover relative rotation R and translation t from 8+ matches.

        Uses the normalised 8-point algorithm to estimate the essential
        matrix, then SVD-based decomposition.
        """
        if len(matches) < 8:
            return np.eye(3), np.zeros(3)
        K = np.asarray(K, dtype=np.float64)
        K_inv = np.linalg.inv(K)
        pts1 = np.array([[kp1[m.query_idx].x, kp1[m.query_idx].y, 1.0] for m in matches])
        pts2 = np.array([[kp2[m.train_idx].x, kp2[m.train_idx].y, 1.0] for m in matches])
        n1 = (K_inv @ pts1.T).T
        n2 = (K_inv @ pts2.T).T
        # Build constraint matrix A · e = 0
        A = np.zeros((len(matches), 9))
        for i in range(len(matches)):
            x1, y1 = n1[i, 0], n1[i, 1]
            x2, y2 = n2[i, 0], n2[i, 1]
            A[i] = [x2 * x1, x2 * y1, x2, y2 * x1, y2 * y1, y2, x1, y1, 1.0]
        _, _, vt = np.linalg.svd(A)
        E = vt[-1].reshape(3, 3)
        # Enforce rank-2 + equal singular values for valid essential matrix
        u, s, vt2 = np.linalg.svd(E)
        if np.linalg.det(u) < 0:
            u = -u
        if np.linalg.det(vt2) < 0:
            vt2 = -vt2
        E = u @ np.diag([1.0, 1.0, 0.0]) @ vt2
        # Decompose E = [t]_x R
        u, _, vt2 = np.linalg.svd(E)
        W = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]], dtype=np.float64)
        R1 = u @ W @ vt2
        R2 = u @ W.T @ vt2
        t = u[:, 2]
        # Choose R with positive determinant (proper rotation)
        R = R1 if np.linalg.det(R1) > 0 else R2
        return R, t

    # -------- main step --------

    def update(self, image_gray: np.ndarray, timestamp: float) -> Pose2D:
        """Process a new frame and return current 2-D pose."""
        kp, desc = self.extract_orb_features(image_gray)
        if self._prev_desc is not None and len(kp) >= 8:
            matches = self.match_features(self._prev_kp, self._prev_desc, kp, desc)
            if len(matches) >= 8:
                K = np.array([[500.0, 0.0, image_gray.shape[1] / 2.0],
                              [0.0, 500.0, image_gray.shape[0] / 2.0],
                              [0.0, 0.0, 1.0]])
                R, t = self.estimate_pose(self._prev_kp, kp, matches, K)
                self._cum_R = R @ self._cum_R
                self._cum_t = self._cum_t + self._cum_R @ t
                yaw = math.atan2(self._cum_R[1, 0], self._cum_R[0, 0])
                self._pose = Pose2D(float(self._cum_t[0]), float(self._cum_t[1]), float(yaw))
        self._prev_kp = kp
        self._prev_desc = desc
        return self._pose

    @property
    def pose(self) -> Pose2D:
        return self._pose

    def reset(self) -> None:
        self._prev_kp = []
        self._prev_desc = None
        self._pose = Pose2D()
        self._cum_R = np.eye(3)
        self._cum_t = np.zeros(3)


# ------------------------------------------------------------------
# Visual-Inertial Odometry
# ------------------------------------------------------------------

def _quat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    ])


def _quat_to_rot(q: np.ndarray) -> np.ndarray:
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def _rot_to_quat(R: np.ndarray) -> np.ndarray:
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    q = np.array([w, x, y, z])
    return q / np.linalg.norm(q)


class VIOEstimator:
    """Loose-coupling Visual-Inertial Odometry."""

    GRAVITY = np.array([0.0, 0.0, 9.81])

    def __init__(self, visual_correction_interval: int = 5):
        self._slam = VisualSLAM()
        self._pos = np.zeros(3)
        self._vel = np.zeros(3)
        self._quat = np.array([1.0, 0.0, 0.0, 0.0])
        self._frame_count = 0
        self._correction_interval = max(1, int(visual_correction_interval))
        self._bias_accel = np.zeros(3)
        self._bias_gyro = np.zeros(3)

    def _preintegrate_imu(
        self,
        accel: np.ndarray,
        gyro: np.ndarray,
        dt: float,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Mid-point Runge-Kutta IMU pre-integration."""
        if dt <= 0.0:
            return self._pos.copy(), self._vel.copy(), self._quat.copy()
        accel = np.asarray(accel, dtype=np.float64) - self._bias_accel
        gyro = np.asarray(gyro, dtype=np.float64) - self._bias_gyro
        # Mid-point orientation
        omega_norm = float(np.linalg.norm(gyro))
        if omega_norm > 1e-8:
            half_angle = 0.5 * omega_norm * dt
            axis = gyro / omega_norm
            dq = np.array([
                math.cos(half_angle),
                axis[0] * math.sin(half_angle),
                axis[1] * math.sin(half_angle),
                axis[2] * math.sin(half_angle),
            ])
        else:
            dq = np.array([1.0, 0.0, 0.0, 0.0])
        q_mid = _quat_mul(self._quat, np.array([
            (1.0 + dq[0]) / 2.0, dq[1] / 2.0, dq[2] / 2.0, dq[3] / 2.0,
        ]))
        q_mid = q_mid / np.linalg.norm(q_mid)
        R_mid = _quat_to_rot(q_mid)
        accel_world = R_mid @ accel - self.GRAVITY
        new_pos = self._pos + self._vel * dt + 0.5 * accel_world * dt * dt
        new_vel = self._vel + accel_world * dt
        new_quat = _quat_mul(self._quat, dq)
        new_quat = new_quat / np.linalg.norm(new_quat)
        return new_pos, new_vel, new_quat

    def update(
        self,
        image_gray: np.ndarray,
        accel: np.ndarray,
        gyro: np.ndarray,
        dt: float,
    ) -> Pose3D:
        """Fuse a frame + IMU sample into a 3-D pose."""
        new_pos, new_vel, new_quat = self._preintegrate_imu(accel, gyro, dt)
        self._pos, self._vel, self._quat = new_pos, new_vel, new_quat
        self._frame_count += 1
        # Periodic visual correction (loose coupling)
        if image_gray is not None:
            visual_pose = self._slam.update(image_gray, 0.0)
            if self._frame_count % self._correction_interval == 0:
                # Replace XY with visual estimate, average heading
                self._pos[0] = 0.5 * self._pos[0] + 0.5 * visual_pose.x
                self._pos[1] = 0.5 * self._pos[1] + 0.5 * visual_pose.y
        return Pose3D(
            float(self._pos[0]), float(self._pos[1]), float(self._pos[2]),
            float(self._quat[0]), float(self._quat[1]),
            float(self._quat[2]), float(self._quat[3]),
        )

    @property
    def position(self) -> np.ndarray:
        return self._pos.copy()

    def reset(self) -> None:
        self._pos = np.zeros(3)
        self._vel = np.zeros(3)
        self._quat = np.array([1.0, 0.0, 0.0, 0.0])
        self._frame_count = 0
        self._slam.reset()


__all__ = [
    "KeyPoint", "DMatch", "Pose2D", "Pose3D",
    "VisualSLAM", "VIOEstimator",
]
