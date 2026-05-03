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
    "VisualSLAM", "VIOEstimator", "VisualPlaceRecognition",
]


# ---------------------------------------------------------------------------
# Visual Place Recognition (Round 5)
# ---------------------------------------------------------------------------


class VisualPlaceRecognition:
    """Bag-of-words place recognition over BRIEF descriptors.

    Builds a BoW vocabulary (random-init word centroids in 64-byte BRIEF
    descriptor space; k-means refinement is left as a stub).  Each image
    is encoded into an L1-normalised histogram over word IDs and matched
    against a database via cosine similarity.
    """

    def __init__(self, vocab_size: int = 256, descriptor_dim: int = 128,
                 seed: int = 0) -> None:
        self.vocab_size = int(vocab_size)
        self.descriptor_dim = int(descriptor_dim)
        rng = np.random.default_rng(seed)
        # Vocabulary: vocab_size BRIEF-style binary words (64 bytes = 512 bits).
        # We treat each row as a 64-byte uint8 word for Hamming comparison.
        self._vocab = rng.integers(0, 256, size=(self.vocab_size, 64),
                                   dtype=np.uint8)
        self._db: dict[object, np.ndarray] = {}
        self._slam = VisualSLAM()

    # -- vocabulary refinement (stub) ---------------------------------------
    def refine_vocabulary(self, descriptors_pool: np.ndarray,
                          n_iter: int = 1) -> None:
        """k-means refinement stub: assigns words to nearest centroids and
        updates centroids by majority bit per byte across cluster members.
        """
        if descriptors_pool.size == 0:
            return
        for _ in range(int(n_iter)):
            up_pool = np.unpackbits(descriptors_pool, axis=1).astype(np.int32)
            up_voc = np.unpackbits(self._vocab, axis=1).astype(np.int32)
            # Hamming distance pool x vocab.
            d = np.array([
                np.sum(np.abs(up_voc - row), axis=1) for row in up_pool
            ])
            assign = np.argmin(d, axis=1)
            for k in range(self.vocab_size):
                members = up_pool[assign == k]
                if members.shape[0] > 0:
                    new_bits = (members.mean(axis=0) > 0.5).astype(np.uint8)
                    self._vocab[k] = np.packbits(new_bits)

    # -- descriptor extraction ---------------------------------------------
    def _bow_from_descriptors(self, desc: np.ndarray) -> np.ndarray:
        if desc.size == 0:
            return np.zeros(self.vocab_size, dtype=float)
        up_desc = np.unpackbits(desc, axis=1).astype(np.int32)
        up_voc = np.unpackbits(self._vocab, axis=1).astype(np.int32)
        hist = np.zeros(self.vocab_size, dtype=float)
        for row in up_desc:
            d = np.sum(np.abs(up_voc - row), axis=1)
            hist[int(np.argmin(d))] += 1.0
        s = hist.sum()
        if s > 0:
            hist = hist / s
        return hist

    def extract_descriptor(self, image_gray: np.ndarray) -> np.ndarray:
        """Detect FAST + BRIEF then return BoW histogram (L1-norm)."""
        _, desc = self._slam.extract_orb_features(image_gray)
        return self._bow_from_descriptors(desc)

    # -- database -----------------------------------------------------------
    def add_to_database(self, place_id, image_gray: np.ndarray) -> None:
        bow = self.extract_descriptor(image_gray)
        self._db[place_id] = bow

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        if na < 1e-12 or nb < 1e-12:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def query(self, image_gray: np.ndarray, top_k: int = 5) -> list:
        """Return top-k matches as [(place_id, score)] sorted by score."""
        if not self._db:
            return []
        q = self.extract_descriptor(image_gray)
        scored = [(pid, self._cosine(q, bow)) for pid, bow in self._db.items()]
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored[:int(top_k)]

    def loop_closure_candidates(self, current_image: np.ndarray,
                                threshold: float = 0.7) -> list:
        """Return [(place_id, score)] above ``threshold``."""
        return [(pid, s) for pid, s in self.query(current_image, top_k=len(self._db))
                if s >= float(threshold)]

    @property
    def db_size(self) -> int:
        return len(self._db)


# ============================================================================
# R8 — WiFi RTT (802.11mc Fine Time Measurement) Positioning
# ============================================================================

class WiFiRTTPositioning:
    """802.11mc Round-Trip-Time positioning with weighted least squares.

    Each access point provides a 2-D anchor position and a measured RTT;
    the receiver position is solved by linearising around the anchor centroid.
    """

    SPEED_OF_LIGHT = 299792458.0

    def __init__(self):
        import numpy as _np
        self._np = _np
        self.aps = []  # list of (position_2d, distance_m)

    def add_ap(self, ap_id, position_2d, rtt_ns: float):
        """Add an AP with its 2-D position and measured RTT in nanoseconds.

        Distance = c · RTT(ns) · 1e-9 / 2  (round-trip).
        """
        np = self._np
        d_m = self.SPEED_OF_LIGHT * float(rtt_ns) * 1e-9 / 2.0
        self.aps.append((str(ap_id),
                         np.asarray(position_2d, dtype=float).reshape(2),
                         float(d_m)))

    def ranging_error_model(self, d_m: float) -> float:
        """802.11mc empirical ranging-error standard deviation (m)."""
        return 0.3 + 0.02 * float(d_m)

    def compute_position(self):
        """Solve receiver (x, y) via weighted linear least squares.

        Returns (x, y, accuracy_m) or ``None`` if fewer than 3 APs.
        """
        np = self._np
        if len(self.aps) < 3:
            return None

        anchors = np.array([a[1] for a in self.aps])
        ranges = np.array([a[2] for a in self.aps])
        sigmas = np.array([self.ranging_error_model(r) for r in ranges])

        # Linearise by subtracting eq 0 from the rest:
        # |p - a_i|² - |p - a_0|² = r_i² - r_0²
        # ⇒ 2·(a_0 - a_i)ᵀ·p = (a_0·a_0 - a_i·a_i) - (r_0² - r_i²)
        a0 = anchors[0]
        r0 = ranges[0]
        A = 2.0 * (a0 - anchors[1:])
        b = (np.sum(a0 * a0) - np.sum(anchors[1:] ** 2, axis=1)) \
            - (r0 ** 2 - ranges[1:] ** 2)
        s2 = sigmas[1:] ** 2 + sigmas[0] ** 2
        w = 1.0 / np.maximum(s2, 1e-12)
        Aw = A * w[:, None]
        bw = b * w
        try:
            p_est, *_ = np.linalg.lstsq(Aw, bw, rcond=None)
        except np.linalg.LinAlgError:
            return None
        try:
            cov = np.linalg.inv(A.T @ (A * w[:, None]))
            accuracy = float(math.sqrt(max(np.trace(cov), 0.0)))
        except np.linalg.LinAlgError:
            accuracy = float(np.mean(sigmas))
        return (float(p_est[0]), float(p_est[1]), accuracy)


# ============================================================================
# R9 — BLE Proximity Mapper (RSSI path-loss trilateration)
# ============================================================================

class BLEProximityMapper:
    """BLE beacon proximity positioning via log-distance path-loss model.

    PL(d) = PL0 + 10·n·log10(d), with n=2.0 (free space), PL0=-59 dBm @ 1 m.
    """

    PATH_LOSS_EXPONENT = 2.0
    REFERENCE_RSSI_DBM = -59.0   # PL0 at d = 1 m

    def __init__(self):
        import numpy as _np
        self._np = _np
        self.beacons = []  # (id, position_2d, distance_m)

    def rssi_to_distance(self, rssi_dbm: float) -> float:
        """Invert path-loss model to recover distance (m)."""
        rssi = float(rssi_dbm)
        exp = (self.REFERENCE_RSSI_DBM - rssi) / (10.0 * self.PATH_LOSS_EXPONENT)
        return float(10.0 ** exp)

    def add_beacon(self, beacon_id, known_pos, rssi_dbm: float):
        np = self._np
        d = self.rssi_to_distance(rssi_dbm)
        self.beacons.append((str(beacon_id),
                             np.asarray(known_pos, dtype=float).reshape(2),
                             float(d)))

    def trilaterate_position(self):
        """Return (x, y) from ≥3 beacons via eq-0-subtraction LS, else None."""
        np = self._np
        if len(self.beacons) < 3:
            return None
        anchors = np.array([b[1] for b in self.beacons])
        ranges = np.array([b[2] for b in self.beacons])
        a0 = anchors[0]
        r0 = ranges[0]
        A = 2.0 * (a0 - anchors[1:])
        b = (np.sum(a0 * a0) - np.sum(anchors[1:] ** 2, axis=1)) \
            - (r0 ** 2 - ranges[1:] ** 2)
        try:
            p, *_ = np.linalg.lstsq(A, b, rcond=None)
        except np.linalg.LinAlgError:
            return None
        return (float(p[0]), float(p[1]))


# ============================================================================
# R12 — Radio SLAM (joint AP mapping + receiver localisation)
# ============================================================================

class RadioSLAM:
    """Simultaneous localisation and AP mapping from RSSI observations.

    Each observation: (cur_pos, RSSI in dBm) at a known receiver pose.
    AP positions are estimated as RSSI-weighted centroids of observation
    poses; receiver position can then be refined by least-squares
    trilateration against estimated APs.
    """

    REFERENCE_RSSI_DBM = -59.0
    PATH_LOSS_EXPONENT = 2.0

    def __init__(self):
        import numpy as _np
        self._np = _np
        self.observations = {}    # ap_id -> list[(pos_2d, rssi_dbm)]

    @staticmethod
    def _rssi_to_distance(rssi_dbm: float) -> float:
        exp = (RadioSLAM.REFERENCE_RSSI_DBM - float(rssi_dbm)) \
              / (10.0 * RadioSLAM.PATH_LOSS_EXPONENT)
        return float(10.0 ** exp)

    def observe(self, ap_id, rssi_dbm: float, cur_pos):
        np = self._np
        pos = np.asarray(cur_pos, dtype=float).reshape(2)
        self.observations.setdefault(str(ap_id), []) \
            .append((pos.copy(), float(rssi_dbm)))

    def estimate_ap_position(self, ap_id):
        """Return AP position as RSSI-weighted centroid of observation points."""
        np = self._np
        obs = self.observations.get(str(ap_id), [])
        if not obs:
            return np.zeros(2)
        # Convert RSSI to a positive linear weight (higher RSSI → higher weight)
        weights = np.array([10.0 ** (r / 10.0) for _, r in obs])
        positions = np.stack([p for p, _ in obs])
        w_sum = float(np.sum(weights))
        if w_sum <= 0:
            return positions.mean(axis=0)
        return (weights[:, None] * positions).sum(axis=0) / w_sum

    def map_uncertainty(self, ap_id):
        """Sample covariance of observation positions for a given AP."""
        np = self._np
        obs = self.observations.get(str(ap_id), [])
        if len(obs) < 2:
            return np.eye(2) * 1.0
        positions = np.stack([p for p, _ in obs])
        return np.cov(positions, rowvar=False)

    def update_position_from_map(self, cur_pos, observations):
        """Refine ``cur_pos`` from a list of (ap_id, rssi_dbm) observations.

        Uses the AP positions already stored to do an LS trilateration.
        """
        np = self._np
        anchors = []
        ranges = []
        for ap_id, rssi in observations:
            apid = str(ap_id)
            if apid not in self.observations:
                continue
            ap_pos = self.estimate_ap_position(apid)
            anchors.append(ap_pos)
            ranges.append(self._rssi_to_distance(rssi))
        if len(anchors) < 3:
            return np.asarray(cur_pos, dtype=float).reshape(2)
        anchors = np.stack(anchors)
        ranges = np.array(ranges)
        a0 = anchors[0]
        r0 = ranges[0]
        A = 2.0 * (a0 - anchors[1:])
        b = (np.sum(a0 * a0) - np.sum(anchors[1:] ** 2, axis=1)) \
            - (r0 ** 2 - ranges[1:] ** 2)
        try:
            p, *_ = np.linalg.lstsq(A, b, rcond=None)
        except np.linalg.LinAlgError:
            return np.asarray(cur_pos, dtype=float).reshape(2)
        return p


# ============================================================================
# R13 — Semantic Landmark Mapper (topological indoor navigation)
# ============================================================================

class SemanticLandmarkMapper:
    """Map of semantic landmarks (doors, elevators, stairs, rooms…)."""

    CONNECT_RADIUS = 15.0  # m — topological adjacency cutoff

    def __init__(self):
        import numpy as _np
        self._np = _np
        self.landmarks = {}    # id -> {category, position_2d, descriptor}

    def add_landmark(self, lm_id, category: str, position_2d, descriptor):
        np = self._np
        self.landmarks[str(lm_id)] = {
            "category": str(category),
            "position": np.asarray(position_2d, dtype=float).reshape(2),
            "descriptor": np.asarray(descriptor, dtype=float).reshape(-1),
        }

    def find_nearest(self, query_pos, category: str | None = None,
                     max_dist: float = 20.0):
        np = self._np
        q = np.asarray(query_pos, dtype=float).reshape(2)
        best_id = None
        best_d = float("inf")
        for lm_id, lm in self.landmarks.items():
            if category is not None and lm["category"] != category:
                continue
            d = float(np.linalg.norm(lm["position"] - q))
            if d < best_d and d <= float(max_dist):
                best_d = d
                best_id = lm_id
        if best_id is None:
            return (None, float("inf"))
        return (best_id, best_d)

    def recognize_landmark(self, sensor_data, vocab):
        """Cosine-similarity BoW match against the landmark descriptors.

        ``vocab`` maps category -> reference descriptor.  Returns the
        best (category, confidence ∈ [0, 1]).
        """
        np = self._np
        s = np.asarray(sensor_data, dtype=float).reshape(-1)
        best_cat = None
        best_score = -1.0
        for cat, ref in vocab.items():
            r = np.asarray(ref, dtype=float).reshape(-1)
            denom = (float(np.linalg.norm(s)) * float(np.linalg.norm(r)))
            if denom <= 0:
                continue
            cos = float(np.dot(s, r) / denom)
            score = (cos + 1.0) / 2.0           # map to [0, 1]
            if score > best_score:
                best_score = score
                best_cat = cat
        if best_cat is None:
            return ("unknown", 0.0)
        return (best_cat, float(best_score))

    def compute_topological_graph(self):
        """Adjacency dict: {id: [neighbour_ids…]} within CONNECT_RADIUS."""
        np = self._np
        ids = list(self.landmarks.keys())
        adj = {i: [] for i in ids}
        for i in ids:
            pi = self.landmarks[i]["position"]
            for j in ids:
                if i == j:
                    continue
                pj = self.landmarks[j]["position"]
                if float(np.linalg.norm(pi - pj)) <= self.CONNECT_RADIUS:
                    adj[i].append(j)
        return adj


# ============================================================================
# R14 — re-export FastSLAM2 + UltraWidebandPositioning from helper module
# ============================================================================
from ._r14_slam import FastSLAM2, UltraWidebandPositioning  # noqa: E402,F401


# ============================================================================
# R15 — re-export OccupancyGridMapper from helper module
# ============================================================================
from ._r15_slam import OccupancyGridMapper  # noqa: E402,F401


# ============================================================================
# R16 — re-export GraphSLAM from helper module
# ============================================================================
from ._r16_slam import GraphSLAM  # noqa: E402,F401


# ============================================================================
# R17 — re-export ICPScanMatcher
# ============================================================================
from ._r17_slam import ICPScanMatcher  # noqa: E402,F401
