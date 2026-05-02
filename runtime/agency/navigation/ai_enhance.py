"""
Tier 6 — AI/ML Enhancement
===========================
AI/ML enhancement layer: deep radio maps, scene recognition,
trajectory prediction, uncertainty quantification, pose-graph SLAM,
neural SLAM, LSTM trajectory prediction, transfer learning,
and environment-adaptive bias correction.

Numpy-only neural networks. No torch / no tensorflow / no sklearn.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .types import Estimate, Confidence, Pose, Position, Velocity


# ---------------------------------------------------------------------------
# Shared helpers (legacy plain-Python helpers kept for back-compat)
# ---------------------------------------------------------------------------

def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(v: List[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _softmax(scores: List[float]) -> List[float]:
    mx = max(scores)
    exps = [math.exp(s - mx) for s in scores]
    total = sum(exps)
    return [e / total for e in exps]


def _mean_std(values: List[float]) -> Tuple[float, float]:
    if not values:
        return 0.0, 0.0
    n = len(values)
    mu = sum(values) / n
    if n == 1:
        return mu, 0.0
    var = sum((x - mu) ** 2 for x in values) / (n - 1)
    return mu, math.sqrt(var)


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# ---------------------------------------------------------------------------
# Pose3D (Tier 6) — 6-DoF pose used by NeuralSLAM
# ---------------------------------------------------------------------------

@dataclass
class Pose3D:
    """6-DoF pose in a local Cartesian frame."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0

    def as_array(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z, self.roll, self.pitch, self.yaw], dtype=np.float64)


# ---------------------------------------------------------------------------
# Radio sample for DeepRadioMap (legacy)
# ---------------------------------------------------------------------------

@dataclass
class RadioSample:
    """Training sample: observed RSSI → known ground-truth position."""
    bssid: str
    rssi_dbm: float
    true_x_m: float
    true_y_m: float


# ---------------------------------------------------------------------------
# DeepRadioMap (legacy k-NN fingerprint positioner — kept for back-compat)
# ---------------------------------------------------------------------------

class DeepRadioMap:
    """Lightweight k-NN radio-fingerprint positioning."""

    def __init__(self, k: int = 5) -> None:
        self._k = k
        self._table: Dict[str, List[Tuple[float, float, float]]] = {}

    def train(self, sample: RadioSample) -> None:
        self._table.setdefault(sample.bssid, []).append(
            (sample.rssi_dbm, sample.true_x_m, sample.true_y_m)
        )

    def predict(
        self, observations: List[Tuple[str, float]]
    ) -> Optional[Tuple[float, float]]:
        if not observations or not self._table:
            return None

        candidates: List[Tuple[float, float, float]] = []
        for bssid, rssi_obs in observations:
            if bssid not in self._table:
                continue
            for rssi_ref, x, y in self._table[bssid]:
                d = (rssi_obs - rssi_ref) ** 2
                candidates.append((d, x, y))

        if not candidates:
            return None

        candidates.sort(key=lambda c: c[0])
        k = min(self._k, len(candidates))
        top = candidates[:k]

        total_w = 0.0
        wx, wy = 0.0, 0.0
        for d, x, y in top:
            w = 1.0 / (1.0 + d)
            wx += w * x
            wy += w * y
            total_w += w

        if total_w < 1e-12:
            return None
        return wx / total_w, wy / total_w


# ---------------------------------------------------------------------------
# RadioMapNet — Tier 6 numpy-only 3-layer MLP
# ---------------------------------------------------------------------------

class RadioMapNet:
    """
    Tiny 3-layer MLP (input → hidden ReLU → linear output) implemented
    in numpy with He weight init, MSE loss, mini-batch SGD.

    Predicts position (x, y) from a fixed-length RSSI fingerprint vector.
    """

    def __init__(
        self,
        input_dim: int = 8,
        hidden_dim: int = 32,
        output_dim: int = 2,
        seed: int = 42,
    ) -> None:
        self.input_dim = int(input_dim)
        self.hidden_dim = int(hidden_dim)
        self.output_dim = int(output_dim)
        rng = np.random.default_rng(seed)
        # He initialization for ReLU layers: std = sqrt(2 / fan_in)
        self.W1 = rng.normal(0.0, math.sqrt(2.0 / self.input_dim),
                             size=(self.input_dim, self.hidden_dim))
        self.b1 = np.zeros(self.hidden_dim, dtype=np.float64)
        self.W2 = rng.normal(0.0, math.sqrt(2.0 / self.hidden_dim),
                             size=(self.hidden_dim, self.output_dim))
        self.b2 = np.zeros(self.output_dim, dtype=np.float64)

    @staticmethod
    def _relu(x: np.ndarray) -> np.ndarray:
        return np.maximum(x, 0.0)

    @staticmethod
    def _relu_grad(x: np.ndarray) -> np.ndarray:
        return (x > 0.0).astype(np.float64)

    @staticmethod
    def _mse_loss(y_pred: np.ndarray, y_true: np.ndarray) -> float:
        return float(np.mean((y_pred - y_true) ** 2))

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Forward pass. x: (N, input_dim) → (N, output_dim). 1-D x supported."""
        single = (x.ndim == 1)
        if single:
            x = x.reshape(1, -1)
        z1 = x @ self.W1 + self.b1
        a1 = self._relu(z1)
        y_hat = a1 @ self.W2 + self.b2
        # Cache for backprop
        self._cache = (x, z1, a1, y_hat)
        return y_hat[0] if single else y_hat

    def _backward(
        self, y_true: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        x, z1, a1, y_hat = self._cache
        n = x.shape[0]
        dL_dy = (2.0 / n) * (y_hat - y_true)            # (N, output_dim)
        dW2 = a1.T @ dL_dy                              # (hidden, output)
        db2 = np.sum(dL_dy, axis=0)                     # (output,)
        dL_da1 = dL_dy @ self.W2.T                      # (N, hidden)
        dL_dz1 = dL_da1 * self._relu_grad(z1)           # (N, hidden)
        dW1 = x.T @ dL_dz1                              # (input, hidden)
        db1 = np.sum(dL_dz1, axis=0)                    # (hidden,)
        return dW1, db1, dW2, db2

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 100,
        lr: float = 0.01,
        batch_size: int = 16,
        seed: int = 0,
    ) -> List[float]:
        """Mini-batch SGD with MSE. Returns per-epoch loss history."""
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        if y.ndim == 1:
            y = y.reshape(1, -1)
        n = X.shape[0]
        rng = np.random.default_rng(seed)
        history: List[float] = []
        for _ in range(int(epochs)):
            idx = rng.permutation(n)
            X_sh, y_sh = X[idx], y[idx]
            for start in range(0, n, batch_size):
                end = min(start + batch_size, n)
                xb = X_sh[start:end]
                yb = y_sh[start:end]
                self.forward(xb)
                dW1, db1, dW2, db2 = self._backward(yb)
                self.W1 -= lr * dW1
                self.b1 -= lr * db1
                self.W2 -= lr * dW2
                self.b2 -= lr * db2
            # Epoch loss on full set
            preds = self.forward(X)
            history.append(self._mse_loss(preds, y))
        return history

    def predict(self, rssi_scan: np.ndarray) -> Tuple[float, float]:
        """Predict (x, y) from a single RSSI fingerprint vector."""
        rssi_scan = np.asarray(rssi_scan, dtype=np.float64).reshape(-1)
        if rssi_scan.shape[0] != self.input_dim:
            raise ValueError(
                f"rssi_scan must have length {self.input_dim}, got {rssi_scan.shape[0]}"
            )
        out = self.forward(rssi_scan)
        return float(out[0]), float(out[1])


# ---------------------------------------------------------------------------
# SceneFeatures / SceneRecognizer  (legacy 12-dim cosine classifier)
# ---------------------------------------------------------------------------

@dataclass
class SceneFeatures:
    """12-dimensional environment feature vector."""
    features: List[float]

    def __post_init__(self) -> None:
        if len(self.features) != 12:
            self.features = (self.features + [0.0] * 12)[:12]


_SCENE_PROTOTYPES: Dict[str, List[float]] = {
    "outdoor_open":   [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
    "outdoor_urban":  [1, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 0],
    "indoor_office":  [0, 1, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0],
    "indoor_mall":    [0, 1, 0, 1, 1, 1, 0, 0, 1, 0, 0, 0],
    "underground":    [0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 1, 0],
    "underwater":     [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1],
    "mixed":          [0.5] * 12,
}


class SceneRecognizer:
    """Cosine-similarity nearest-prototype scene classifier (legacy)."""

    def classify(self, feat: SceneFeatures) -> str:
        v = feat.features
        n_v = _norm(v)
        if n_v < 1e-9:
            return "mixed"
        best_cls, best_sim = "mixed", -2.0
        for cls, proto in _SCENE_PROTOTYPES.items():
            n_p = _norm(proto)
            if n_p < 1e-9:
                continue
            sim = _dot(v, proto) / (n_v * n_p)
            if sim > best_sim:
                best_sim = sim
                best_cls = cls
        return best_cls


# ---------------------------------------------------------------------------
# SceneClassifier — Tier 6 dict-based environment classifier
# ---------------------------------------------------------------------------

class SceneClassifier:
    """
    Decision-tree classifier for environment scene type.

    Returns one of: indoor, outdoor, underground, underwater, urban, rural.
    Operates on a feature dict with optional keys:

        wifi_count       int     number of detected wifi APs
        cell_count       int     number of cell towers visible
        gnss_count       int     number of GNSS satellites in view
        altitude_m       float   altitude above sea level (m)
        depth_m          float   depth below water surface (m), 0 if dry
        pressure_hpa     float   ambient pressure (hPa)
        light_lux        float   ambient illuminance (lux)
        magnetic_uT      float   magnetic field strength (microtesla)
    """

    LABELS = ("indoor", "outdoor", "underground", "underwater", "urban", "rural")

    def __init__(self) -> None:
        self._last_confidence: float = 0.0
        self._last_label: str = "outdoor"

    def classify(self, features: dict) -> str:
        wifi = float(features.get("wifi_count", 0))
        cell = float(features.get("cell_count", 0))
        gnss = float(features.get("gnss_count", 0))
        alt = float(features.get("altitude_m", 0.0))
        depth = float(features.get("depth_m", 0.0))
        pressure = float(features.get("pressure_hpa", 1013.25))
        light = float(features.get("light_lux", 1000.0))
        mag = float(features.get("magnetic_uT", 50.0))

        scores: Dict[str, float] = {k: 0.0 for k in self.LABELS}

        # Underwater — pressure spike and/or explicit depth
        if depth > 0.5 or pressure > 1100.0:
            scores["underwater"] += 4.0 + min(depth / 5.0, 5.0)
        # Underground — negative altitude or low light + low gnss + high mag noise
        if alt < -3.0:
            scores["underground"] += 3.0 + min(-alt / 10.0, 4.0)
        if gnss <= 1 and light < 50.0 and pressure < 1013.0:
            scores["underground"] += 2.0
        # Indoor — many wifi APs, low gnss, normal-ish light
        if gnss <= 3 and wifi >= 3:
            scores["indoor"] += 3.0 + min(wifi / 5.0, 3.0)
        if gnss == 0 and wifi >= 1 and depth < 0.5 and alt > -3.0:
            scores["indoor"] += 1.5
        # Outdoor — many GNSS sats and natural light
        if gnss >= 4:
            scores["outdoor"] += 3.0 + min(gnss / 4.0, 3.0)
        if light > 1000.0 and depth < 0.5:
            scores["outdoor"] += 1.5
        # Urban — many cells + many wifi outdoors
        if cell >= 3 and wifi >= 5:
            scores["urban"] += 3.0 + min((cell + wifi) / 10.0, 3.0)
        # Rural — few cells, few wifi, lots of GNSS
        if gnss >= 4 and wifi <= 1 and cell <= 1:
            scores["rural"] += 3.0
        # Magnetic anomaly hints subterranean
        if mag > 80.0 and gnss <= 1:
            scores["underground"] += 1.0

        # Pick the winner
        label = max(scores, key=lambda k: scores[k])
        # If everything is zero, default to outdoor (open sky assumed)
        total = sum(scores.values())
        if total <= 0.0:
            label = "outdoor"
            confidence = 0.2
        else:
            top = scores[label]
            # Softmax-style confidence: normalized winner
            sx = np.array(list(scores.values()), dtype=np.float64)
            sx = sx - sx.max()
            ex = np.exp(sx)
            probs = ex / ex.sum()
            confidence = float(probs[list(scores.keys()).index(label)])
            # Boost confidence if winner is dominant
            margin = (top - sorted(scores.values())[-2]) / max(top, 1e-9)
            confidence = max(confidence, min(0.99, 0.5 + 0.5 * margin))

        self._last_label = label
        self._last_confidence = float(np.clip(confidence, 0.0, 1.0))
        return label

    def confidence(self) -> float:
        """Return confidence (0-1) of the most recent classify() call."""
        return self._last_confidence


# ---------------------------------------------------------------------------
# Legacy TrajectoryPredictor (history + EMA velocity extrapolation)
# ---------------------------------------------------------------------------

class TrajectoryPredictor:
    """Lightweight EMA-velocity trajectory predictor (legacy)."""

    def __init__(self, max_history: int = 30, alpha: float = 0.3) -> None:
        self._history: List[Tuple[float, float, float]] = []
        self._max = max_history
        self._alpha = alpha
        self._vx: float = 0.0
        self._vy: float = 0.0

    def push(self, est: Estimate) -> None:
        x = est.pose.position.lon
        y = est.pose.position.lat
        ts = est.ts
        if self._history:
            prev_x, prev_y, prev_ts = self._history[-1]
            dt = ts - prev_ts
            if dt > 0:
                raw_vx = (x - prev_x) / dt
                raw_vy = (y - prev_y) / dt
                self._vx = self._alpha * raw_vx + (1 - self._alpha) * self._vx
                self._vy = self._alpha * raw_vy + (1 - self._alpha) * self._vy
        self._history.append((x, y, ts))
        if len(self._history) > self._max:
            self._history.pop(0)

    def predict(self, horizon_s: float) -> Optional[Tuple[float, float]]:
        if not self._history:
            return None
        x, y, _ = self._history[-1]
        return x + self._vx * horizon_s, y + self._vy * horizon_s


# ---------------------------------------------------------------------------
# LSTMPredictor — Tier 6 numpy LSTM cell, multi-step rollout
# ---------------------------------------------------------------------------

class LSTMPredictor:
    """
    Numpy LSTM cell with single-step forward and multi-step trajectory rollout.

    State: hidden h (hidden_dim,), cell c (hidden_dim,).
    Output projection maps h → (output_dim,) for predicted (dx, dy) per step.
    """

    def __init__(
        self,
        input_dim: int = 4,
        hidden_dim: int = 32,
        output_dim: int = 2,
        seed: int = 7,
    ) -> None:
        self.input_dim = int(input_dim)
        self.hidden_dim = int(hidden_dim)
        self.output_dim = int(output_dim)
        rng = np.random.default_rng(seed)
        scale = math.sqrt(1.0 / (self.input_dim + self.hidden_dim))

        # Concatenated [x, h] → 4 * hidden_dim gates (forget, input, candidate, output)
        d_in = self.input_dim + self.hidden_dim
        self.W_f = rng.normal(0.0, scale, size=(d_in, self.hidden_dim))
        self.b_f = np.zeros(self.hidden_dim)
        self.W_i = rng.normal(0.0, scale, size=(d_in, self.hidden_dim))
        self.b_i = np.zeros(self.hidden_dim)
        self.W_g = rng.normal(0.0, scale, size=(d_in, self.hidden_dim))
        self.b_g = np.zeros(self.hidden_dim)
        self.W_o = rng.normal(0.0, scale, size=(d_in, self.hidden_dim))
        self.b_o = np.zeros(self.hidden_dim)

        # Output head h → output_dim
        self.W_y = rng.normal(0.0, math.sqrt(1.0 / self.hidden_dim),
                              size=(self.hidden_dim, self.output_dim))
        self.b_y = np.zeros(self.output_dim)

        self.h = np.zeros(self.hidden_dim)
        self.c = np.zeros(self.hidden_dim)

    @staticmethod
    def _sigmoid(x: np.ndarray) -> np.ndarray:
        # Stable sigmoid
        return np.where(x >= 0, 1.0 / (1.0 + np.exp(-x)), np.exp(x) / (1.0 + np.exp(x)))

    def reset_state(self) -> None:
        """Clear hidden state (h) and cell state (c)."""
        self.h = np.zeros(self.hidden_dim)
        self.c = np.zeros(self.hidden_dim)

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Single LSTM step. x: (input_dim,). Returns predicted output (output_dim,)."""
        x = np.asarray(x, dtype=np.float64).reshape(-1)
        if x.shape[0] != self.input_dim:
            raise ValueError(
                f"x must have length {self.input_dim}, got {x.shape[0]}"
            )
        z = np.concatenate([x, self.h])
        f = self._sigmoid(z @ self.W_f + self.b_f)
        i = self._sigmoid(z @ self.W_i + self.b_i)
        g = np.tanh(z @ self.W_g + self.b_g)
        o = self._sigmoid(z @ self.W_o + self.b_o)
        self.c = f * self.c + i * g
        self.h = o * np.tanh(self.c)
        y = self.h @ self.W_y + self.b_y
        return y

    def predict_trajectory(
        self,
        history: np.ndarray,
        steps: int = 5,
    ) -> np.ndarray:
        """
        Predict next `steps` positions from history of (x, y, vx, vy) rows.

        Output shape: (steps, 2). Output is auto-regressively unrolled —
        the network produces a position delta per step which we accumulate
        on top of the last observed position with the last observed velocity.
        """
        history = np.asarray(history, dtype=np.float64)
        if history.ndim != 2 or history.shape[1] != self.input_dim:
            raise ValueError(
                f"history must be 2-D with {self.input_dim} cols, got shape {history.shape}"
            )
        if history.shape[0] == 0:
            return np.zeros((steps, self.output_dim), dtype=np.float64)
        self.reset_state()
        # Run the encoder over the whole history
        last_out = np.zeros(self.output_dim)
        for row in history:
            last_out = self.forward(row)

        # Auto-regressive rollout
        last = history[-1].copy()
        positions = np.zeros((steps, self.output_dim), dtype=np.float64)
        x_pos, y_pos = float(last[0]), float(last[1])
        vx, vy = float(last[2]), float(last[3])
        for t in range(int(steps)):
            delta = self.forward(np.array([x_pos, y_pos, vx, vy], dtype=np.float64))
            # Treat output as predicted (vx, vy) for next step (delta if output_dim==2)
            if self.output_dim >= 2:
                vx = vx * 0.5 + 0.5 * float(delta[0])
                vy = vy * 0.5 + 0.5 * float(delta[1])
            x_pos = x_pos + vx
            y_pos = y_pos + vy
            positions[t, 0] = x_pos
            positions[t, 1] = y_pos
        # Silence "last_out unused" — keep for callers that subclass and want it
        _ = last_out
        return positions


# ---------------------------------------------------------------------------
# NeuralSLAMEstimator — Tier 6 lightweight neural SLAM
# ---------------------------------------------------------------------------

class NeuralSLAMEstimator:
    """
    Lightweight neural SLAM:

      * encode_observation(sensor_dict) → 64-d float feature vector
      * update_pose_graph(obs_vec, prev_pose) → incremental Pose3D
      * detect_loop_closure(obs_vec) → (found, keyframe_idx) by cosine sim
      * apply_loop_correction(keyframe_idx, current_pose) → corrected Pose3D
        (g2o-style correction simplified to linear interpolation along the loop)
    """

    FEATURE_DIM = 64

    def __init__(
        self,
        loop_threshold: float = 0.92,
        history_max: int = 256,
        seed: int = 11,
    ) -> None:
        self.loop_threshold = float(loop_threshold)
        self.history_max = int(history_max)
        self._keyframes: List[np.ndarray] = []
        self._poses: List[Pose3D] = []
        rng = np.random.default_rng(seed)
        # Random projection matrix used to fold raw scalar inputs into 64-d
        self._proj_keys: List[str] = [
            "ax", "ay", "az", "gx", "gy", "gz",
            "wifi_count", "cell_count", "gnss_count",
            "altitude_m", "pressure_hpa", "light_lux",
            "magnetic_uT", "temperature_c", "depth_m", "speed_mps",
        ]
        self._proj = rng.normal(
            0.0, 1.0 / math.sqrt(len(self._proj_keys)),
            size=(len(self._proj_keys), self.FEATURE_DIM),
        )

    def encode_observation(self, sensor_dict: dict) -> np.ndarray:
        """Encode a heterogeneous sensor dict to a 64-d feature vector."""
        raw = np.array(
            [float(sensor_dict.get(k, 0.0)) for k in self._proj_keys],
            dtype=np.float64,
        )
        # Stable sin/cos encoding to bound magnitudes; cos(0)=1 so feat is
        # non-zero even when every input scalar is zero.
        sin_half = np.sin(raw)
        cos_half = np.cos(raw)
        feat_a = raw @ self._proj
        feat_b = sin_half @ self._proj
        feat_c = cos_half @ self._proj
        feat = feat_a + feat_b + feat_c
        n = float(np.linalg.norm(feat))
        if n > 1e-9:
            feat = feat / n
        return feat

    def update_pose_graph(
        self,
        obs_vec: np.ndarray,
        prev_pose: Optional[Pose3D] = None,
    ) -> Pose3D:
        """Incrementally update pose graph and return new Pose3D."""
        obs_vec = np.asarray(obs_vec, dtype=np.float64).reshape(-1)
        if prev_pose is None:
            prev_pose = self._poses[-1] if self._poses else Pose3D()
        if self._keyframes:
            last_obs = self._keyframes[-1]
            sim = _cosine_sim(obs_vec, last_obs)
            # Lower similarity ⇒ we moved more
            step = max(0.0, 1.0 - sim)
        else:
            step = 0.0
        # Heading-aligned forward step in xy plane
        cos_y = math.cos(prev_pose.yaw)
        sin_y = math.sin(prev_pose.yaw)
        new_pose = Pose3D(
            x=prev_pose.x + step * cos_y,
            y=prev_pose.y + step * sin_y,
            z=prev_pose.z,
            roll=prev_pose.roll,
            pitch=prev_pose.pitch,
            yaw=prev_pose.yaw,
        )
        self._keyframes.append(obs_vec.copy())
        self._poses.append(new_pose)
        if len(self._keyframes) > self.history_max:
            self._keyframes.pop(0)
            self._poses.pop(0)
        return new_pose

    def detect_loop_closure(self, obs_vec: np.ndarray) -> Tuple[bool, int]:
        """Return (found, idx) — best matching keyframe by cosine similarity."""
        obs_vec = np.asarray(obs_vec, dtype=np.float64).reshape(-1)
        if len(self._keyframes) < 5:
            return False, -1
        # Skip the most-recent few frames to avoid trivial self-match
        candidates = self._keyframes[: max(0, len(self._keyframes) - 3)]
        if not candidates:
            return False, -1
        best_idx = -1
        best_sim = -2.0
        for i, kf in enumerate(candidates):
            sim = _cosine_sim(obs_vec, kf)
            if sim > best_sim:
                best_sim = sim
                best_idx = i
        return (best_sim >= self.loop_threshold), best_idx

    def apply_loop_correction(
        self, keyframe_idx: int, current_pose: Pose3D
    ) -> Pose3D:
        """Simplified g2o-style correction: linear blend toward matched keyframe pose."""
        if not (0 <= keyframe_idx < len(self._poses)):
            return current_pose
        target = self._poses[keyframe_idx]
        # Interpolate halfway — the loop has just been closed, both endpoints
        # carry equal weight in the absence of an information matrix.
        corrected = Pose3D(
            x=0.5 * (current_pose.x + target.x),
            y=0.5 * (current_pose.y + target.y),
            z=0.5 * (current_pose.z + target.z),
            roll=0.5 * (current_pose.roll + target.roll),
            pitch=0.5 * (current_pose.pitch + target.pitch),
            yaw=0.5 * (current_pose.yaw + target.yaw),
        )
        # Apply correction back to the most recent stored pose
        if self._poses:
            self._poses[-1] = corrected
        return corrected


# ---------------------------------------------------------------------------
# UncertaintyEstimator — Tier 6 ensemble + HDOP + ellipse + reliability
# ---------------------------------------------------------------------------

class UncertaintyEstimator:
    """Multi-source uncertainty quantification."""

    def compute_position_uncertainty(
        self, position_estimates: List[np.ndarray]
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Return (mean, covariance) from an ensemble of position estimates."""
        if not position_estimates:
            cov = np.full((2, 2), float("inf"), dtype=np.float64)
            np.fill_diagonal(cov, float("inf"))
            return np.zeros(2), cov
        pts = np.array([np.asarray(p, dtype=np.float64).reshape(-1) for p in position_estimates])
        mean = pts.mean(axis=0)
        if pts.shape[0] == 1:
            cov = np.zeros((pts.shape[1], pts.shape[1]))
        else:
            cov = np.cov(pts.T, ddof=1)
            if cov.ndim == 0:
                cov = np.array([[float(cov)]])
        return mean, cov

    def hdop(self, satellite_positions: List[np.ndarray]) -> float:
        """
        Horizontal Dilution Of Precision from satellite line-of-sight unit vectors.

        Each entry is a 3-vector (x, y, z) — the unit vector from receiver to
        satellite, or any vector that we'll normalize internally.
        Returns +inf if the geometry matrix is singular.
        """
        if len(satellite_positions) < 4:
            return float("inf")
        rows = []
        for sat in satellite_positions:
            v = np.asarray(sat, dtype=np.float64).reshape(-1)
            if v.shape[0] < 3:
                continue
            n = float(np.linalg.norm(v[:3]))
            if n < 1e-9:
                continue
            u = v[:3] / n
            # Standard GNSS geometry row: [-ux, -uy, -uz, 1]
            rows.append([-u[0], -u[1], -u[2], 1.0])
        if len(rows) < 4:
            return float("inf")
        G = np.array(rows, dtype=np.float64)
        try:
            Q = np.linalg.inv(G.T @ G)
        except np.linalg.LinAlgError:
            return float("inf")
        h_sq = Q[0, 0] + Q[1, 1]
        if h_sq < 0:
            return float("inf")
        return float(math.sqrt(h_sq))

    def confidence_ellipse(
        self,
        cov_2x2: np.ndarray,
        confidence: float = 0.95,
    ) -> Tuple[float, float, float]:
        """
        2-D confidence ellipse from a 2x2 covariance matrix.

        Returns (semi_major, semi_minor, angle_rad).
        Uses chi-square 2-DoF: scale = -2 * ln(1 - confidence).
        """
        cov = np.asarray(cov_2x2, dtype=np.float64)
        if cov.shape != (2, 2):
            raise ValueError(f"cov_2x2 must be 2x2, got shape {cov.shape}")
        confidence = float(np.clip(confidence, 1e-6, 1.0 - 1e-9))
        scale = -2.0 * math.log(1.0 - confidence)
        # Symmetric cov → use eigh; ensure symmetry numerically
        sym = 0.5 * (cov + cov.T)
        eigvals, eigvecs = np.linalg.eigh(sym)
        # eigh returns ascending; reverse so [0] is largest
        order = np.argsort(eigvals)[::-1]
        eigvals = eigvals[order]
        eigvecs = eigvecs[:, order]
        eigvals = np.clip(eigvals, 0.0, None)
        semi_major = float(math.sqrt(scale * eigvals[0]))
        semi_minor = float(math.sqrt(scale * eigvals[1]))
        angle = float(math.atan2(eigvecs[1, 0], eigvecs[0, 0]))
        return semi_major, semi_minor, angle

    def reliability_score(self, sources: List[dict]) -> float:
        """
        Weighted reliability across heterogeneous sources.

        Each source dict may carry:
            quality   float  0..1   intrinsic source quality
            snr_db    float          fallback when quality missing
            valid     bool           hard gate, treated as 0 if False
            weight    float  >=0    weight (default 1.0)
        Returns 0..1.
        """
        if not sources:
            return 0.0
        total_w = 0.0
        score = 0.0
        for s in sources:
            valid = bool(s.get("valid", True))
            if not valid:
                # Invalid source still consumes weight at quality 0
                q = 0.0
            elif "quality" in s:
                q = float(np.clip(s["quality"], 0.0, 1.0))
            elif "snr_db" in s:
                # Map SNR to 0..1 with soft cap at 30 dB
                q = float(np.clip(s["snr_db"] / 30.0, 0.0, 1.0))
            else:
                q = 0.5
            w = float(s.get("weight", 1.0))
            if w < 0:
                w = 0.0
            total_w += w
            score += w * q
        if total_w < 1e-12:
            return 0.0
        return float(np.clip(score / total_w, 0.0, 1.0))


# ---------------------------------------------------------------------------
# Legacy BayesianUncertaintyEstimator — kept for back-compat
# ---------------------------------------------------------------------------

class BayesianUncertaintyEstimator:
    """Weighted mean + per-axis std-dev across estimates (legacy)."""

    def estimate(
        self, estimates: List[Estimate]
    ) -> Tuple[float, float, float, float]:
        if not estimates:
            return 0.0, 0.0, float("inf"), float("inf")
        xs = [e.pose.position.lon for e in estimates]
        ys = [e.pose.position.lat for e in estimates]
        weights = [
            1.0 / max(e.confidence.horizontal_m, 0.01)
            for e in estimates
        ]
        total_w = sum(weights)
        mx = sum(w * x for w, x in zip(weights, xs)) / total_w
        my = sum(w * y for w, y in zip(weights, ys)) / total_w
        if len(estimates) == 1:
            sx = estimates[0].confidence.horizontal_m
            sy = estimates[0].confidence.horizontal_m
        else:
            sx = math.sqrt(sum(w * (x - mx) ** 2 for w, x in zip(weights, xs)) / total_w)
            sy = math.sqrt(sum(w * (y - my) ** 2 for w, y in zip(weights, ys)) / total_w)
        return mx, my, sx, sy


# ---------------------------------------------------------------------------
# PoseEdge / PoseGraphSLAM (legacy)
# ---------------------------------------------------------------------------

@dataclass
class PoseEdge:
    """Constraint between two poses in the graph."""
    from_id: int
    to_id: int
    dx_m: float
    dy_m: float
    dtheta_rad: float
    information: float = 1.0


class PoseGraphSLAM:
    """Lightweight pose-graph SLAM with simple gradient-descent optimization (legacy)."""

    def __init__(self, learning_rate: float = 0.05, iterations: int = 50) -> None:
        self._nodes: List[List[float]] = []
        self._edges: List[PoseEdge] = []
        self._lr = learning_rate
        self._iterations = iterations

    def add_pose(self, x: float, y: float, theta: float) -> int:
        idx = len(self._nodes)
        self._nodes.append([x, y, theta])
        return idx

    def add_edge(self, edge: PoseEdge) -> None:
        self._edges.append(edge)

    def close_loop(self) -> None:
        if len(self._nodes) < 2 or not self._edges:
            return
        for _ in range(self._iterations):
            grads = [[0.0, 0.0, 0.0] for _ in self._nodes]
            for e in self._edges:
                i, j = e.from_id, e.to_id
                if i >= len(self._nodes) or j >= len(self._nodes):
                    continue
                ni, nj = self._nodes[i], self._nodes[j]
                cos_t = math.cos(ni[2])
                sin_t = math.sin(ni[2])
                pred_dx = cos_t * (nj[0] - ni[0]) + sin_t * (nj[1] - ni[1])
                pred_dy = -sin_t * (nj[0] - ni[0]) + cos_t * (nj[1] - ni[1])
                pred_dth = nj[2] - ni[2]
                rx = pred_dx - e.dx_m
                ry = pred_dy - e.dy_m
                rt = pred_dth - e.dtheta_rad
                while rt > math.pi:
                    rt -= 2 * math.pi
                while rt < -math.pi:
                    rt += 2 * math.pi
                w = e.information
                if i != 0:
                    grads[i][0] += w * rx * cos_t
                    grads[i][1] += w * ry * (-sin_t)
                    grads[i][2] += w * rt
                if j != 0:
                    grads[j][0] -= w * rx * cos_t
                    grads[j][1] -= w * ry * cos_t
                    grads[j][2] -= w * rt
            for k in range(1, len(self._nodes)):
                for d in range(3):
                    self._nodes[k][d] -= self._lr * grads[k][d]


# ---------------------------------------------------------------------------
# EnvironmentAdapter — legacy bias correction + Tier 6 transfer learning
# ---------------------------------------------------------------------------

class EnvironmentAdapter:
    """
    Two-faced adapter:

      Legacy API
      ----------
      learn(env_type, dx, dy)   record per-env position errors
      apply(env_type, est)      bias-correct an Estimate

      Tier 6 API
      ----------
      store_reference(env_id, feature_vector)   register environment fingerprint
      adapt(current_features) -> env_id          cosine-match to closest env
      fine_tune(net, samples, epochs=10)         few-shot fine-tune a RadioMapNet
    """

    def __init__(self) -> None:
        self._bias: Dict[str, List[Tuple[float, float]]] = {}
        self._refs: Dict[str, np.ndarray] = {}

    # ----- Legacy API -----

    def learn(self, env_type: str, dx: float, dy: float) -> None:
        self._bias.setdefault(env_type, []).append((dx, dy))
        if len(self._bias[env_type]) > 200:
            self._bias[env_type].pop(0)

    def apply(self, env_type: str, est: Estimate) -> Estimate:
        samples = self._bias.get(env_type, [])
        if not samples:
            return est
        mean_dx = sum(s[0] for s in samples) / len(samples)
        mean_dy = sum(s[1] for s in samples) / len(samples)
        old_pos = est.pose.position
        new_pos = Position(
            lat=old_pos.lat - mean_dy,
            lon=old_pos.lon - mean_dx,
            alt=old_pos.alt,
        )
        new_pose = Pose(
            position=new_pos,
            qw=est.pose.qw, qx=est.pose.qx,
            qy=est.pose.qy, qz=est.pose.qz,
        )
        return Estimate(
            pose=new_pose,
            velocity=est.velocity,
            confidence=est.confidence,
            ts=est.ts,
            source=est.source + "+adapt",
            raw=est.raw,
        )

    # ----- Tier 6 API -----

    def store_reference(self, env_id: str, feature_vector: np.ndarray) -> None:
        """Save a normalized fingerprint for later cosine matching."""
        v = np.asarray(feature_vector, dtype=np.float64).reshape(-1).copy()
        n = float(np.linalg.norm(v))
        if n > 1e-12:
            v = v / n
        self._refs[str(env_id)] = v

    def adapt(self, current_features: np.ndarray) -> str:
        """Return the stored env_id with the highest cosine similarity."""
        if not self._refs:
            return ""
        v = np.asarray(current_features, dtype=np.float64).reshape(-1)
        n = float(np.linalg.norm(v))
        if n > 1e-12:
            v = v / n
        best_id = ""
        best_sim = -2.0
        for env_id, ref in self._refs.items():
            sim = float(np.dot(v, ref))
            if sim > best_sim:
                best_sim = sim
                best_id = env_id
        return best_id

    def fine_tune(
        self,
        net: "RadioMapNet",
        new_samples: List[Tuple[np.ndarray, np.ndarray]],
        epochs: int = 10,
        lr: float = 0.005,
    ) -> List[float]:
        """
        Few-shot fine-tune a RadioMapNet on a small set of (features, target) pairs.
        Lower default learning rate to avoid catastrophic forgetting.
        """
        if not new_samples:
            return []
        X = np.array([np.asarray(s[0], dtype=np.float64).reshape(-1) for s in new_samples])
        y = np.array([np.asarray(s[1], dtype=np.float64).reshape(-1) for s in new_samples])
        return net.train(X, y, epochs=epochs, lr=lr, batch_size=max(1, min(8, X.shape[0])))


# ---------------------------------------------------------------------------
# AIEnhancer — legacy public class (kept for back-compat)
# ---------------------------------------------------------------------------

class AIEnhancer:
    """Tier-6 AI/ML enhancement layer (legacy Estimate-shaped API)."""

    def __init__(self) -> None:
        self.scene_recognizer = SceneRecognizer()
        self.trajectory_predictor = TrajectoryPredictor()
        self.environment_adapter = EnvironmentAdapter()
        self.uncertainty_estimator = BayesianUncertaintyEstimator()
        self.radio_map = DeepRadioMap()
        self.pose_graph = PoseGraphSLAM()
        self._env_type: str = "outdoor_open"

    def enhance(self, est: Estimate, env_type: Optional[str] = None) -> Estimate:
        etype = env_type or self._env_type
        adapted = self.environment_adapter.apply(etype, est)
        self.trajectory_predictor.push(adapted)
        horiz = adapted.confidence.horizontal_m
        if len(self.trajectory_predictor._history) >= 3:
            vx = self.trajectory_predictor._vx
            vy = self.trajectory_predictor._vy
            speed = math.sqrt(vx ** 2 + vy ** 2)
            if speed < 0.5:
                horiz = horiz * 0.95
        new_conf = Confidence(
            horizontal_m=horiz,
            vertical_m=adapted.confidence.vertical_m,
            valid=adapted.confidence.valid,
            source=adapted.confidence.source,
        )
        return Estimate(
            pose=adapted.pose,
            velocity=adapted.velocity,
            confidence=new_conf,
            ts=adapted.ts,
            source=adapted.source,
            raw=adapted.raw,
        )

    def quantify_uncertainty(
        self, estimates: List[Estimate]
    ) -> Tuple[float, float, float, float]:
        return self.uncertainty_estimator.estimate(estimates)


# ---------------------------------------------------------------------------
# AIEnhancement — new Tier 6 dict-based public class
# ---------------------------------------------------------------------------

class AIEnhancement:
    """
    Tier 6 AI/ML enhancement layer, dict-based API.

    enhance(sensor_dict, position_estimate) -> dict
        Runs scene classification, neural SLAM update, ensemble uncertainty,
        and reliability scoring. Returns an enriched dict containing the
        original position plus AI-derived signals.
    """

    def __init__(self) -> None:
        self.scene_classifier = SceneClassifier()
        self.uncertainty = UncertaintyEstimator()
        self.lstm = LSTMPredictor()
        self.slam = NeuralSLAMEstimator()
        self.adapter = EnvironmentAdapter()
        self.radio_net = RadioMapNet()
        self._last_pose: Pose3D = Pose3D()
        self._ensemble: List[np.ndarray] = []

    def enhance(self, sensor_dict: dict, position_estimate: dict) -> dict:
        """Apply Tier 6 enhancement to a single observation."""
        sensor_dict = sensor_dict or {}
        position_estimate = dict(position_estimate or {})

        # Scene
        scene = self.scene_classifier.classify(sensor_dict)
        scene_conf = self.scene_classifier.confidence()

        # Neural SLAM update
        obs_vec = self.slam.encode_observation(sensor_dict)
        new_pose = self.slam.update_pose_graph(obs_vec, self._last_pose)
        loop_found, loop_idx = self.slam.detect_loop_closure(obs_vec)
        if loop_found:
            new_pose = self.slam.apply_loop_correction(loop_idx, new_pose)
        self._last_pose = new_pose

        # Ensemble uncertainty: keep last N raw position estimates as ensemble
        x = float(position_estimate.get("x", position_estimate.get("lon", 0.0)))
        y = float(position_estimate.get("y", position_estimate.get("lat", 0.0)))
        self._ensemble.append(np.array([x, y]))
        if len(self._ensemble) > 16:
            self._ensemble.pop(0)
        mean, cov = self.uncertainty.compute_position_uncertainty(self._ensemble)
        if cov.shape == (2, 2):
            sm, sn, ang = self.uncertainty.confidence_ellipse(cov, confidence=0.95)
        else:
            sm, sn, ang = 0.0, 0.0, 0.0

        # Reliability score from sources advertised in sensor_dict
        sources = sensor_dict.get("sources", []) or []
        reliability = self.uncertainty.reliability_score(sources)

        return {
            **position_estimate,
            "scene": scene,
            "scene_confidence": scene_conf,
            "slam_pose": {
                "x": new_pose.x, "y": new_pose.y, "z": new_pose.z,
                "yaw": new_pose.yaw,
            },
            "loop_closed": bool(loop_found),
            "loop_keyframe": int(loop_idx),
            "ensemble_mean_xy": (float(mean[0]), float(mean[1])) if mean.shape[0] >= 2 else (0.0, 0.0),
            "uncertainty_ellipse_m": {
                "semi_major": sm,
                "semi_minor": sn,
                "angle_rad": ang,
            },
            "reliability": reliability,
        }


# ---------------------------------------------------------------------------
# Transformer-based trajectory predictor (Round 3)
# ---------------------------------------------------------------------------


class TransformerPredictor:
    """Pure-numpy transformer for autoregressive trajectory prediction.

    Implements:
      * scaled dot-product multi-head self-attention
      * sinusoidal positional encoding
      * 2-layer attention stack (encoder-only)
      * autoregressive decode for ``predict(steps_ahead)``
      * online weight update via gradient descent on prediction error

    State dimension is 2 (x, y).  Model dimension defaults to 16 with 4
    heads — small enough to keep tests fast yet large enough for
    self-attention to be meaningful.
    """

    def __init__(
        self,
        d_model: int = 16,
        n_heads: int = 4,
        n_layers: int = 2,
        max_len: int = 64,
        lr: float = 1e-3,
        seed: int = 0,
    ) -> None:
        if d_model % n_heads != 0:
            raise ValueError("d_model must be divisible by n_heads")
        self.d_model = int(d_model)
        self.n_heads = int(n_heads)
        self.d_head = self.d_model // self.n_heads
        self.n_layers = int(n_layers)
        self.max_len = int(max_len)
        self.lr = float(lr)

        rng = np.random.default_rng(seed)
        scale = 1.0 / math.sqrt(self.d_model)
        # Input embedding: 2 → d_model
        self.W_in = rng.standard_normal((2, self.d_model)) * scale
        # Per-layer projection matrices (Wq, Wk, Wv, Wo).
        self.layers = []
        for _ in range(self.n_layers):
            self.layers.append({
                "Wq": rng.standard_normal((self.d_model, self.d_model)) * scale,
                "Wk": rng.standard_normal((self.d_model, self.d_model)) * scale,
                "Wv": rng.standard_normal((self.d_model, self.d_model)) * scale,
                "Wo": rng.standard_normal((self.d_model, self.d_model)) * scale,
            })
        # Output head: d_model → 2
        self.W_out = rng.standard_normal((self.d_model, 2)) * scale
        self._cached_history: Optional[np.ndarray] = None

    # -- positional encoding ------------------------------------------------
    def _positional_encoding(self, length: int) -> np.ndarray:
        pos = np.arange(length)[:, None].astype(float)
        i = np.arange(self.d_model)[None, :].astype(float)
        denom = np.power(10000.0, (2 * (i // 2)) / self.d_model)
        pe = np.zeros((length, self.d_model), dtype=float)
        pe[:, 0::2] = np.sin(pos / denom[:, 0::2])
        pe[:, 1::2] = np.cos(pos / denom[:, 1::2])
        return pe

    # -- attention ----------------------------------------------------------
    def _attention(
        self,
        Q: np.ndarray,
        K: np.ndarray,
        V: np.ndarray,
        mask: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Scaled dot-product attention.  Q, K, V shape: (T, d_head) per head.

        For unbatched multi-head we accept (n_heads, T, d_head) shaped inputs.
        """
        scale = 1.0 / math.sqrt(self.d_head)
        scores = np.einsum("htd,hsd->hts", Q, K) * scale
        if mask is not None:
            scores = np.where(mask, scores, -1e9)
        # Stable softmax along last axis.
        scores = scores - scores.max(axis=-1, keepdims=True)
        weights = np.exp(scores)
        weights = weights / (weights.sum(axis=-1, keepdims=True) + 1e-12)
        out = np.einsum("hts,hsd->htd", weights, V)
        return out

    def _layer_forward(
        self,
        X: np.ndarray,
        layer: dict,
        causal: bool = False,
    ) -> np.ndarray:
        """One transformer-style attention layer with residual connection."""
        T = X.shape[0]
        Q = X @ layer["Wq"]
        K = X @ layer["Wk"]
        V = X @ layer["Wv"]
        Qh = Q.reshape(T, self.n_heads, self.d_head).transpose(1, 0, 2)
        Kh = K.reshape(T, self.n_heads, self.d_head).transpose(1, 0, 2)
        Vh = V.reshape(T, self.n_heads, self.d_head).transpose(1, 0, 2)
        mask = None
        if causal:
            mask = np.tril(np.ones((T, T), dtype=bool))[None, :, :]
        attn = self._attention(Qh, Kh, Vh, mask=mask)
        attn = attn.transpose(1, 0, 2).reshape(T, self.d_model)
        attn = attn @ layer["Wo"]
        return X + attn  # residual

    # -- public API ---------------------------------------------------------
    def encode(self, trajectory_history: np.ndarray) -> np.ndarray:
        """Encode a (T, 2) trajectory into a (T, d_model) representation."""
        traj = np.asarray(trajectory_history, dtype=float)
        if traj.ndim != 2 or traj.shape[1] != 2:
            raise ValueError("trajectory_history must be shape (T, 2)")
        T = min(traj.shape[0], self.max_len)
        traj = traj[-T:]
        X = traj @ self.W_in
        X = X + self._positional_encoding(T)
        for layer in self.layers:
            X = self._layer_forward(X, layer, causal=True)
        self._cached_history = traj.copy()
        return X

    def predict(self, steps_ahead: int = 10) -> dict:
        """Autoregressive decode.  Returns predicted positions and per-step
        uncertainty ellipses (semi-major, semi-minor, angle) growing with
        the prediction horizon (a simple ``sigma * sqrt(t)`` model).
        """
        if self._cached_history is None:
            raise RuntimeError("call encode(...) before predict(...)")
        traj = self._cached_history.copy()
        positions = []
        ellipses = []
        # Velocity inference from last two history samples.
        if traj.shape[0] >= 2:
            base_vel = traj[-1] - traj[-2]
        else:
            base_vel = np.zeros(2)
        for t in range(1, int(steps_ahead) + 1):
            X = self.encode(traj)
            last_h = X[-1]
            delta = last_h @ self.W_out
            # Combine learned delta (small) with velocity prior (dominant).
            next_pos = traj[-1] + base_vel + 0.01 * delta
            positions.append(next_pos.tolist())
            traj = np.vstack([traj, next_pos[None, :]])
            sigma_t = 0.5 * math.sqrt(t)
            ellipses.append({
                "semi_major_m": sigma_t * 1.5,
                "semi_minor_m": sigma_t,
                "angle_rad": 0.0,
            })
        return {
            "positions": positions,
            "uncertainty_ellipses": ellipses,
            "horizon": int(steps_ahead),
        }

    def update(self, actual_pos) -> float:
        """Online update: simple gradient step on MSE between predicted next
        position and observed ``actual_pos``.  Returns the MSE.
        """
        if self._cached_history is None:
            raise RuntimeError("call encode(...) before update(...)")
        actual = np.asarray(actual_pos, dtype=float).reshape(2)
        # One-step prediction (no autoregression to keep gradient simple).
        X = self.encode(self._cached_history)
        last_h = X[-1]
        delta = last_h @ self.W_out
        pred_pos = self._cached_history[-1] + delta
        error = pred_pos - actual
        mse = float((error ** 2).mean())
        # Gradient w.r.t. W_out only — last-layer update is enough to
        # demonstrate online learning without full backprop.
        grad_W_out = np.outer(last_h, error) * 2.0 / 2.0
        self.W_out -= self.lr * grad_W_out
        return mse


__all_r3 = [
    "TransformerPredictor",
]


# ---------------------------------------------------------------------------
# Neural Radiance Map for radio RSS (Round 4)
# ---------------------------------------------------------------------------


class NeuralRadianceMap:
    """NeRF-style MLP for radio-RSS field reconstruction.

    Input:  3-D position → Fourier-feature encoding (36-D)
    Hidden: one ReLU layer (default 32 units)
    Output: scalar predicted RSS (dBm)

    Trained via SGD on (position, rss) pairs.  ``query_map`` evaluates a
    batch of positions for coverage visualisation.  Pure numpy.
    """

    K_FREQS = 6  # 6 frequency bands → 36-D encoding

    def __init__(
        self,
        hidden: int = 32,
        seed: int = 0,
        weight_scale: float = 0.1,
    ) -> None:
        self.hidden = int(hidden)
        rng = np.random.default_rng(seed)
        d_in = self.K_FREQS * 2 * 3
        self.W1 = rng.standard_normal((d_in, self.hidden)) * weight_scale
        self.b1 = np.zeros(self.hidden, dtype=float)
        self.W2 = rng.standard_normal((self.hidden, 1)) * weight_scale
        self.b2 = np.zeros(1, dtype=float)

    @classmethod
    def encode_position(cls, pos_3d: np.ndarray) -> np.ndarray:
        """Fourier-feature encoding: [sin(2^k π x), cos(2^k π x)] for each
        coord, k=0..K-1, concatenated → (K*2*3,) vector.
        """
        p = np.asarray(pos_3d, dtype=float).reshape(3)
        feats = []
        for k in range(cls.K_FREQS):
            scale = (2.0 ** k) * math.pi
            feats.append(np.sin(scale * p))
            feats.append(np.cos(scale * p))
        return np.concatenate(feats)

    def _encode_batch(self, positions: np.ndarray) -> np.ndarray:
        positions = np.asarray(positions, dtype=float).reshape(-1, 3)
        return np.stack([self.encode_position(p) for p in positions])

    def forward(self, pos_3d: np.ndarray) -> float:
        """Predict RSS at one position."""
        x = self.encode_position(pos_3d)
        h = np.maximum(0.0, x @ self.W1 + self.b1)
        y = h @ self.W2 + self.b2
        return float(y[0])

    def train_step(
        self,
        positions: np.ndarray,
        rss_values: np.ndarray,
        lr: float = 0.01,
    ) -> float:
        """One SGD mini-batch update.  Returns mean squared error."""
        pos = np.asarray(positions, dtype=float).reshape(-1, 3)
        y_true = np.asarray(rss_values, dtype=float).reshape(-1)
        if pos.shape[0] != y_true.shape[0]:
            raise ValueError("positions and rss_values must have same length")
        X = self._encode_batch(pos)            # (N, d_in)
        Z = X @ self.W1 + self.b1              # (N, hidden)
        H = np.maximum(0.0, Z)
        Y = H @ self.W2 + self.b2              # (N, 1)
        err = (Y[:, 0] - y_true)               # (N,)
        mse = float((err ** 2).mean())
        # Backprop (MSE/N).
        N = pos.shape[0]
        dY = (2.0 / N) * err.reshape(-1, 1)    # (N, 1)
        dW2 = H.T @ dY                         # (hidden, 1)
        db2 = dY.sum(axis=0)                   # (1,)
        dH = dY @ self.W2.T                    # (N, hidden)
        dZ = dH * (Z > 0).astype(float)        # ReLU grad
        dW1 = X.T @ dZ                         # (d_in, hidden)
        db1 = dZ.sum(axis=0)                   # (hidden,)
        self.W1 -= lr * dW1
        self.b1 -= lr * db1
        self.W2 -= lr * dW2
        self.b2 -= lr * db2
        return mse

    def query_map(self, grid_positions: np.ndarray) -> np.ndarray:
        """Vectorised batch query — returns (N,) predicted RSS."""
        pos = np.asarray(grid_positions, dtype=float).reshape(-1, 3)
        X = self._encode_batch(pos)
        H = np.maximum(0.0, X @ self.W1 + self.b1)
        Y = H @ self.W2 + self.b2
        return Y[:, 0]


# =====================================================================
# GODSKILL Nav R6 — Bayesian Neural Odometry (MC-Dropout)
# =====================================================================

class BayesianNeuralOdometry:
    """Neural inertial odometry with MC-Dropout uncertainty.

    Maps a sequence of 6-DOF IMU samples (accel + gyro, 6 channels)
    to a 3-D position delta. MC-Dropout sampling at inference yields
    epistemic uncertainty (mean + std-dev per axis).
    """

    def __init__(self, seq_len: int = 50, hidden: int = 32,
                 dropout: float = 0.2, seed: int = 7) -> None:
        if seq_len < 1:
            raise ValueError("seq_len must be >= 1")
        if not 0.0 <= dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        self.seq_len = int(seq_len)
        self.hidden = int(hidden)
        self.dropout = float(dropout)
        rng = np.random.default_rng(int(seed))
        d_in = 6 * self.seq_len
        scale1 = math.sqrt(2.0 / d_in)
        scale2 = math.sqrt(2.0 / self.hidden)
        self.W1 = rng.normal(0.0, scale1, size=(d_in, hidden))
        self.b1 = np.zeros(hidden)
        self.W2 = rng.normal(0.0, scale2, size=(hidden, 3))
        self.b2 = np.zeros(3)
        self._rng = rng

    def _flatten(self, imu_seq: np.ndarray) -> np.ndarray:
        seq = np.asarray(imu_seq, dtype=float)
        if seq.ndim != 2 or seq.shape[1] != 6:
            raise ValueError("imu_sequence must be (T, 6)")
        T = seq.shape[0]
        if T < self.seq_len:
            pad = np.zeros((self.seq_len - T, 6))
            seq = np.vstack([pad, seq])
        elif T > self.seq_len:
            seq = seq[-self.seq_len:, :]
        return seq.reshape(-1)

    def _forward(self, x_flat: np.ndarray, training: bool) -> np.ndarray:
        h = np.maximum(0.0, x_flat @ self.W1 + self.b1)
        if training and self.dropout > 0.0:
            keep = 1.0 - self.dropout
            mask = (self._rng.random(self.hidden) < keep).astype(float) / keep
            h = h * mask
        elif (not training) and self.dropout > 0.0:
            # MC-Dropout — keep dropout active during inference for uncertainty
            keep = 1.0 - self.dropout
            mask = (self._rng.random(self.hidden) < keep).astype(float) / keep
            h = h * mask
        return h @ self.W2 + self.b2

    def predict_with_uncertainty(self, imu_sequence: np.ndarray,
                                 n_samples: int = 20) -> tuple:
        """Run n_samples stochastic forward passes.

        Returns (mean_delta (3,), std_delta (3,)).
        """
        n = max(2, int(n_samples))
        x = self._flatten(imu_sequence)
        outs = np.zeros((n, 3))
        for i in range(n):
            outs[i] = self._forward(x, training=False)
        mean = outs.mean(axis=0)
        # ddof=1 unbiased — guarantees >0 with non-zero dropout for any non-trivial input
        std = outs.std(axis=0, ddof=1) if n > 1 else np.zeros(3)
        return mean, std

    def predict(self, imu_sequence: np.ndarray) -> np.ndarray:
        """Single deterministic pass (dropout disabled — eval mode)."""
        x = self._flatten(imu_sequence)
        h = np.maximum(0.0, x @ self.W1 + self.b1)
        return h @ self.W2 + self.b2

    def train_step(self, imu_seq: np.ndarray, true_delta: np.ndarray,
                   lr: float = 1e-3) -> float:
        """One SGD step (MSE loss) with dropout active. Returns scalar loss."""
        x = self._flatten(imu_seq)
        y = np.asarray(true_delta, dtype=float).reshape(3)
        # Forward (training)
        z1 = x @ self.W1 + self.b1
        h = np.maximum(0.0, z1)
        keep = 1.0 - self.dropout
        if self.dropout > 0.0:
            mask = (self._rng.random(self.hidden) < keep).astype(float) / keep
        else:
            mask = np.ones(self.hidden)
        h_drop = h * mask
        y_pred = h_drop @ self.W2 + self.b2
        err = y_pred - y
        loss = float(np.mean(err ** 2))
        # Backward
        dY = (2.0 / 3.0) * err  # d MSE / d y_pred (3,)
        dW2 = np.outer(h_drop, dY)
        db2 = dY
        dh_drop = self.W2 @ dY
        dh = dh_drop * mask
        dz1 = dh * (z1 > 0).astype(float)
        dW1 = np.outer(x, dz1)
        db1 = dz1
        # Update
        self.W1 -= lr * dW1
        self.b1 -= lr * db1
        self.W2 -= lr * dW2
        self.b2 -= lr * db2
        return loss
