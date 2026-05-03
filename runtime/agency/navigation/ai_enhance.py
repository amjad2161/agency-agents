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


# ============================================================================
# R7 — Federated Navigation Learner (decentralised on-device training)
# ============================================================================

class FederatedNavigationLearner:
    """Federated learning for multi-agent navigation.

    Edge devices train a small MLP on local position-error data and share
    only weight gradients (not raw data). A central coordinator performs
    Federated Averaging (FedAvg). Privacy-preserving Gaussian noise is
    added to gradients before sharing.
    """

    def __init__(self,
                 input_dim: int = 4,
                 hidden_dim: int = 8,
                 output_dim: int = 2,
                 learning_rate: float = 0.01,
                 privacy_noise_std: float = 0.01,
                 seed: int = 42):
        self.input_dim = int(input_dim)
        self.hidden_dim = int(hidden_dim)
        self.output_dim = int(output_dim)
        self.lr = float(learning_rate)
        self.privacy_noise_std = float(privacy_noise_std)
        self._rng = np.random.default_rng(int(seed))

        # He initialisation
        self.W1 = self._rng.standard_normal((input_dim, hidden_dim)) \
                  * math.sqrt(2.0 / input_dim)
        self.b1 = np.zeros(hidden_dim)
        self.W2 = self._rng.standard_normal((hidden_dim, output_dim)) \
                  * math.sqrt(2.0 / hidden_dim)
        self.b2 = np.zeros(output_dim)

    # --- Forward / backward --------------------------------------------------

    def _forward(self, X):
        Z1 = X @ self.W1 + self.b1
        H = np.maximum(0.0, Z1)                  # ReLU
        Y = H @ self.W2 + self.b2
        return Z1, H, Y

    def predict(self, X):
        X = np.asarray(X, dtype=float).reshape(-1, self.input_dim)
        _, _, Y = self._forward(X)
        return Y

    # --- Local SGD training (returns weight delta) --------------------------

    def local_train(self, data, labels, epochs: int = 3, batch_size: int = 8):
        """Run local SGD on (data, labels). Return weight delta vs starting
        weights, with Gaussian privacy noise added.
        """
        X = np.asarray(data, dtype=float).reshape(-1, self.input_dim)
        Y_true = np.asarray(labels, dtype=float).reshape(-1, self.output_dim)
        n = X.shape[0]
        if n == 0:
            return self._zero_delta()

        W1_start = self.W1.copy()
        b1_start = self.b1.copy()
        W2_start = self.W2.copy()
        b2_start = self.b2.copy()

        for _ in range(int(epochs)):
            perm = self._rng.permutation(n)
            for s in range(0, n, batch_size):
                idx = perm[s:s + batch_size]
                Xb = X[idx]; Yb = Y_true[idx]
                Z1, H, Y_pred = self._forward(Xb)
                m = max(Xb.shape[0], 1)
                # MSE loss gradient
                dY = (Y_pred - Yb) * (2.0 / m)
                dW2 = H.T @ dY
                db2 = dY.sum(axis=0)
                dH = dY @ self.W2.T
                dZ1 = dH * (Z1 > 0).astype(float)
                dW1 = Xb.T @ dZ1
                db1 = dZ1.sum(axis=0)
                self.W1 -= self.lr * dW1
                self.b1 -= self.lr * db1
                self.W2 -= self.lr * dW2
                self.b2 -= self.lr * db2

        # Compute delta and apply differential-privacy noise
        delta = {
            "W1": self.W1 - W1_start,
            "b1": self.b1 - b1_start,
            "W2": self.W2 - W2_start,
            "b2": self.b2 - b2_start,
        }
        return self._add_privacy_noise(delta)

    def _zero_delta(self):
        return {
            "W1": np.zeros_like(self.W1),
            "b1": np.zeros_like(self.b1),
            "W2": np.zeros_like(self.W2),
            "b2": np.zeros_like(self.b2),
        }

    def _add_privacy_noise(self, delta):
        sigma = self.privacy_noise_std
        return {
            k: v + self._rng.normal(0.0, sigma, size=v.shape)
            for k, v in delta.items()
        }

    # --- Federated averaging -------------------------------------------------

    @staticmethod
    def federated_average(local_weights_list):
        """Average a list of weight dictionaries (FedAvg).

        Args:
            local_weights_list: list of dicts with keys W1, b1, W2, b2.

        Returns:
            Single dict with averaged weights.
        """
        if not local_weights_list:
            raise ValueError("local_weights_list is empty")
        keys = local_weights_list[0].keys()
        n = len(local_weights_list)
        out = {}
        for k in keys:
            stacked = np.stack([w[k] for w in local_weights_list], axis=0)
            out[k] = stacked.mean(axis=0)
        return out

    # --- Apply global update -------------------------------------------------

    def apply_global_update(self, global_weights):
        """Replace local weights with the federated global weights."""
        self.W1 = np.asarray(global_weights["W1"], dtype=float).copy()
        self.b1 = np.asarray(global_weights["b1"], dtype=float).copy()
        self.W2 = np.asarray(global_weights["W2"], dtype=float).copy()
        self.b2 = np.asarray(global_weights["b2"], dtype=float).copy()

    def get_weights(self):
        return {
            "W1": self.W1.copy(),
            "b1": self.b1.copy(),
            "W2": self.W2.copy(),
            "b2": self.b2.copy(),
        }


# ============================================================================
# R8 — Graph Neural Odometry (message-passing GNN over pose graph)
# ============================================================================

class GraphNeuralOdometry:
    """Lightweight GNN for pose-graph odometry refinement.

    Each node holds a state feature vector. Each message-passing step
    aggregates neighbour features (mean) and applies tanh(W · concat).
    """

    def __init__(self):
        self.nodes = {}              # id -> state_vec
        self.edges = []              # list of (i, j, rel_motion)
        self.node_features = {}      # id -> feature_vec
        self._W = None
        self._next_id = 0

    def add_node(self, state_vec) -> int:
        """Add a node with its state vector. Returns the assigned ID."""
        s = np.asarray(state_vec, dtype=float).reshape(-1)
        node_id = int(self._next_id)
        self._next_id += 1
        self.nodes[node_id] = s.copy()
        self.node_features[node_id] = s.copy()
        return node_id

    def add_edge(self, i: int, j: int, relative_motion):
        """Add a directed edge i → j with associated relative motion."""
        self.edges.append((int(i), int(j),
                           np.asarray(relative_motion, dtype=float).copy()))

    def _neighbours(self, node_id: int):
        """Return list of node IDs that share an edge with ``node_id``."""
        out = []
        for i, j, _ in self.edges:
            if i == node_id and j in self.node_features:
                out.append(j)
            elif j == node_id and i in self.node_features:
                out.append(i)
        return out

    def message_passing_step(self):
        """One round of GNN message passing (mean-aggregator + tanh)."""
        if not self.node_features:
            return
        # Determine feature dimension and lazy-init W
        dim = len(next(iter(self.node_features.values())))
        if self._W is None or self._W.shape != (dim, 2 * dim):
            # Concat-input weight matrix init: [I | I] / 2 keeps signal stable
            self._W = np.hstack([np.eye(dim), np.eye(dim)]) / 2.0

        new_features = {}
        for nid, own in self.node_features.items():
            neigh_ids = self._neighbours(nid)
            if neigh_ids:
                agg = np.mean(np.stack(
                    [self.node_features[n] for n in neigh_ids]), axis=0)
            else:
                agg = np.zeros_like(own)
            x = np.concatenate([own, agg])
            new_features[nid] = np.tanh(self._W @ x)
        self.node_features = new_features

    def predict_odometry(self, node_id: int):
        """Return current feature vector for ``node_id``."""
        return self.node_features[int(node_id)].copy()


# ============================================================================
# R9 — Temporal Convolutional Network Odometry (numpy-only)
# ============================================================================

class TemporalConvOdometry:
    """1-D dilated causal-convolution network for IMU sequence → pose delta.

    3 conv layers with dilations 1, 2, 4 (receptive field 8 timesteps),
    followed by mean pooling and a linear head.
    """

    def __init__(self, seq_len: int = 16, in_features: int = 6,
                 out_features: int = 3, hidden: int = 8, seed: int = 0):
        self.seq_len = int(seq_len)
        self.in_features = int(in_features)
        self.out_features = int(out_features)
        self.hidden = int(hidden)
        rng = np.random.default_rng(int(seed))
        # Conv layer = (kernel=2) weight matrices: shape (in, out)
        scale_in = math.sqrt(2.0 / (2 * in_features))
        scale_h = math.sqrt(2.0 / (2 * hidden))
        # Kernel size 2: each layer holds [W_curr, W_prev] for both taps
        self.W1_a = rng.standard_normal((in_features, hidden)) * scale_in
        self.W1_b = rng.standard_normal((in_features, hidden)) * scale_in
        self.W2_a = rng.standard_normal((hidden, hidden)) * scale_h
        self.W2_b = rng.standard_normal((hidden, hidden)) * scale_h
        self.W3_a = rng.standard_normal((hidden, hidden)) * scale_h
        self.W3_b = rng.standard_normal((hidden, hidden)) * scale_h
        # Linear head
        self.W_out = rng.standard_normal((hidden, out_features)) * scale_h
        self.b_out = np.zeros(out_features)

    # --- Causal dilated convolution ----------------------------------------

    def causal_conv1d(self, x, W_curr, W_prev, dilation: int):
        """Causal 1-D conv with kernel size 2 and given dilation.

        Args:
            x:        (T, C_in) sequence
            W_curr:   (C_in, C_out) weight on x[t]
            W_prev:   (C_in, C_out) weight on x[t - dilation]
            dilation: integer dilation factor

        Returns:
            (T, C_out) output (causal: future timesteps not used).
        """
        T = x.shape[0]
        C_out = W_curr.shape[1]
        out = np.zeros((T, C_out))
        for t in range(T):
            curr = x[t] @ W_curr
            if t - dilation >= 0:
                prev = x[t - dilation] @ W_prev
            else:
                prev = np.zeros(C_out)        # causal zero-pad
            out[t] = np.tanh(curr + prev)
        return out

    # --- Forward / loss / SGD ----------------------------------------------

    def _forward_with_cache(self, X):
        h1 = self.causal_conv1d(X, self.W1_a, self.W1_b, dilation=1)
        h2 = self.causal_conv1d(h1, self.W2_a, self.W2_b, dilation=2)
        h3 = self.causal_conv1d(h2, self.W3_a, self.W3_b, dilation=4)
        pooled = h3.mean(axis=0)
        y = pooled @ self.W_out + self.b_out
        return y, pooled

    def forward(self, imu_sequence):
        X = np.asarray(imu_sequence, dtype=float).reshape(-1, self.in_features)
        y, _ = self._forward_with_cache(X)
        return y

    def train_step(self, imu_seq, true_delta, lr: float = 1e-3) -> float:
        """One SGD step (numerical gradient on output head only).

        Returns scalar MSE loss.
        """
        X = np.asarray(imu_seq, dtype=float).reshape(-1, self.in_features)
        y_true = np.asarray(true_delta, dtype=float).reshape(self.out_features)
        y_pred, pooled = self._forward_with_cache(X)
        err = y_pred - y_true
        loss = float(np.mean(err ** 2))
        # Output-head gradient (closed form)
        d_out = (2.0 / self.out_features) * err
        dW_out = np.outer(pooled, d_out)
        db_out = d_out
        self.W_out -= lr * dW_out
        self.b_out -= lr * db_out
        return loss


# ============================================================================
# R10 — Online Bayesian Position Filter (Gaussian-mixture belief)
# ============================================================================

class OnlineBayesianPosFilter:
    """Online Gaussian-mixture position filter (K=5 components).

    Maintains a fixed-cardinality mixture; predict convolves each component
    with motion noise, update reweights by measurement likelihood, and
    resample merges low-weight components into their nearest neighbour.
    """

    def __init__(self, n_components: int = 5, dim: int = 2,
                 init_spread: float = 5.0, seed: int = 0):
        self.n = int(n_components)
        self.dim = int(dim)
        rng = np.random.default_rng(int(seed))
        self.means = rng.normal(0.0, float(init_spread), (self.n, self.dim))
        self.covs = np.tile(np.eye(self.dim) * 1.0, (self.n, 1, 1))
        self.weights = np.full(self.n, 1.0 / self.n)

    def predict(self, motion_delta, motion_sigma: float):
        delta = np.asarray(motion_delta, dtype=float).reshape(self.dim)
        Q = (float(motion_sigma) ** 2) * np.eye(self.dim)
        self.means = self.means + delta
        self.covs = self.covs + Q

    def update(self, measurement, meas_sigma: float):
        z = np.asarray(measurement, dtype=float).reshape(self.dim)
        R = (float(meas_sigma) ** 2) * np.eye(self.dim)
        new_w = np.zeros_like(self.weights)
        for k in range(self.n):
            S = self.covs[k] + R
            try:
                S_inv = np.linalg.inv(S)
            except np.linalg.LinAlgError:
                S_inv = np.linalg.pinv(S)
            d = z - self.means[k]
            quad = float(d @ S_inv @ d)
            det_S = max(float(np.linalg.det(S)), 1e-12)
            like = math.exp(-0.5 * quad) / math.sqrt((2 * math.pi) ** self.dim
                                                      * det_S)
            new_w[k] = self.weights[k] * like
            # Kalman update of component
            K = self.covs[k] @ S_inv
            self.means[k] = self.means[k] + K @ d
            self.covs[k] = (np.eye(self.dim) - K) @ self.covs[k]
        total = float(np.sum(new_w))
        if total > 0.0:
            self.weights = new_w / total
        else:
            self.weights = np.full(self.n, 1.0 / self.n)

    def get_position_estimate(self):
        """Weighted mean and total covariance (mixture moment matching)."""
        mean = np.sum(self.weights[:, None] * self.means, axis=0)
        cov = np.zeros((self.dim, self.dim))
        for k in range(self.n):
            d = (self.means[k] - mean).reshape(-1, 1)
            cov = cov + self.weights[k] * (self.covs[k] + d @ d.T)
        return (mean, cov)

    def resample_components(self):
        """Merge any component with weight < 0.05 into its nearest neighbour."""
        low = np.where(self.weights < 0.05)[0]
        if low.size == 0:
            return
        for k in low:
            # Nearest non-low component
            others = [j for j in range(self.n) if j != k]
            if not others:
                continue
            dists = [float(np.linalg.norm(self.means[j] - self.means[k]))
                     for j in others]
            j = others[int(np.argmin(dists))]
            w_sum = self.weights[j] + self.weights[k]
            if w_sum <= 0:
                continue
            new_mean = (self.weights[j] * self.means[j]
                        + self.weights[k] * self.means[k]) / w_sum
            d_j = (self.means[j] - new_mean).reshape(-1, 1)
            d_k = (self.means[k] - new_mean).reshape(-1, 1)
            new_cov = (self.weights[j] * (self.covs[j] + d_j @ d_j.T)
                       + self.weights[k] * (self.covs[k] + d_k @ d_k.T)) / w_sum
            self.means[j] = new_mean
            self.covs[j] = new_cov
            self.weights[j] = w_sum
            # Re-init the merged component as a small-weight perturbation
            self.weights[k] = 1e-6
            self.means[k] = new_mean + np.ones(self.dim) * 1e-3
            self.covs[k] = np.eye(self.dim)
        # Renormalise
        total = float(np.sum(self.weights))
        if total > 0:
            self.weights = self.weights / total


# ============================================================================
# R11 — Adaptive Map Matcher (HMM Viterbi over road segments)
# ============================================================================

class AdaptiveMapMatcher:
    """HMM-based map matching: emission = N(d_to_seg, σ); transition by adjacency."""

    EMISSION_SIGMA = 5.0     # m
    P_ADJACENT = 0.8
    P_NON_ADJ = 0.01

    def __init__(self):
        self.segments = {}    # seg_id -> (start_pt, end_pt)

    def add_segment(self, seg_id, start_pt, end_pt):
        self.segments[seg_id] = (
            np.asarray(start_pt, dtype=float).reshape(2),
            np.asarray(end_pt, dtype=float).reshape(2),
        )

    @staticmethod
    def point_to_segment_dist(point, seg_start, seg_end) -> float:
        """Perpendicular distance from a point to a 2-D line segment."""
        p = np.asarray(point, dtype=float).reshape(2)
        a = np.asarray(seg_start, dtype=float).reshape(2)
        b = np.asarray(seg_end, dtype=float).reshape(2)
        ab = b - a
        denom = float(ab @ ab)
        if denom < 1e-12:
            return float(np.linalg.norm(p - a))
        t = float(np.clip((p - a) @ ab / denom, 0.0, 1.0))
        proj = a + t * ab
        return float(np.linalg.norm(p - proj))

    def _emission_logprob(self, point, seg_id) -> float:
        a, b = self.segments[seg_id]
        d = self.point_to_segment_dist(point, a, b)
        return -0.5 * (d / self.EMISSION_SIGMA) ** 2

    def _is_adjacent(self, s1, s2) -> bool:
        a1, b1 = self.segments[s1]
        a2, b2 = self.segments[s2]
        for p in (a1, b1):
            for q in (a2, b2):
                if float(np.linalg.norm(p - q)) < 1e-3:
                    return True
        return False

    def _trans_logprob(self, s_from, s_to) -> float:
        if s_from == s_to or self._is_adjacent(s_from, s_to):
            return math.log(self.P_ADJACENT)
        return math.log(self.P_NON_ADJ)

    def viterbi(self, observations):
        """Most-likely sequence of segment IDs for a list of 2-D observations."""
        if not self.segments or not observations:
            return []
        seg_ids = list(self.segments.keys())
        n_states = len(seg_ids)
        T = len(observations)
        dp = np.full((T, n_states), -np.inf)
        back = np.zeros((T, n_states), dtype=int)
        # Init
        for j, s in enumerate(seg_ids):
            dp[0, j] = self._emission_logprob(observations[0], s)
        # Recursion
        for t in range(1, T):
            for j, s_to in enumerate(seg_ids):
                e = self._emission_logprob(observations[t], s_to)
                best_prev = -np.inf
                best_idx = 0
                for i, s_from in enumerate(seg_ids):
                    cand = dp[t - 1, i] + self._trans_logprob(s_from, s_to)
                    if cand > best_prev:
                        best_prev = cand
                        best_idx = i
                dp[t, j] = best_prev + e
                back[t, j] = best_idx
        # Backtrace
        last = int(np.argmax(dp[-1]))
        path = [seg_ids[last]]
        for t in range(T - 1, 0, -1):
            last = int(back[t, last])
            path.append(seg_ids[last])
        path.reverse()
        return path


# ============================================================================
# R12 — Continual Learning Navigator (Elastic Weight Consolidation)
# ============================================================================

class ContinualLearningNavigator:
    """EWC-regularised continual learner for nav models.

    Stores a small dict of weights and per-weight Fisher importance.
    Calling :py:meth:`consolidate` snapshots the current weights and
    Fisher diagonal so the next task is penalised against drifting
    away from them.
    """

    def __init__(self, weight_shape=(8, 4), seed: int = 0):
        rng = np.random.default_rng(int(seed))
        self.weights = {"W": rng.standard_normal(weight_shape) * 0.1}
        self.old_weights = {k: v.copy() for k, v in self.weights.items()}
        self.fisher = {k: np.zeros_like(v) for k, v in self.weights.items()}
        self.lambda_ewc = 100.0

    def compute_fisher_diagonal(self, data_loader):
        """Empirical Fisher diagonal: average of per-sample squared gradients.

        ``data_loader`` is an iterable of (X, Y) pairs.  We model the
        forward pass as a single-layer linear projection and use the
        prediction-error gradient as a proxy.
        """
        fisher = {k: np.zeros_like(v) for k, v in self.weights.items()}
        n = 0
        for X, Y in data_loader:
            X = np.asarray(X, dtype=float).reshape(-1, self.weights["W"].shape[0])
            Y = np.asarray(Y, dtype=float).reshape(-1, self.weights["W"].shape[1])
            pred = X @ self.weights["W"]
            err = pred - Y
            grad = X.T @ err / max(X.shape[0], 1)
            fisher["W"] += grad ** 2
            n += 1
        if n > 0:
            for k in fisher:
                fisher[k] /= n
        return fisher

    @staticmethod
    def ewc_loss(current_weights, old_weights, fisher,
                 lambda_ewc: float = 100.0) -> float:
        """EWC penalty: λ/2 · Σ F_i · (θ_i − θ*_i)² over all weights."""
        total = 0.0
        for k in current_weights:
            diff = current_weights[k] - old_weights[k]
            total += float(np.sum(fisher[k] * diff ** 2))
        return float(0.5 * lambda_ewc * total)

    def train_with_ewc(self, data, labels, old_weights=None, fisher=None,
                       lr: float = 0.01, epochs: int = 1):
        """One-pass SGD with EWC regulariser; returns the updated weights."""
        if old_weights is None:
            old_weights = self.old_weights
        if fisher is None:
            fisher = self.fisher
        X = np.asarray(data, dtype=float).reshape(-1, self.weights["W"].shape[0])
        Y = np.asarray(labels, dtype=float).reshape(-1, self.weights["W"].shape[1])
        for _ in range(int(epochs)):
            pred = X @ self.weights["W"]
            err = pred - Y
            grad_loss = X.T @ err / max(X.shape[0], 1)
            grad_ewc = self.lambda_ewc * fisher["W"] \
                       * (self.weights["W"] - old_weights["W"])
            self.weights["W"] -= lr * (grad_loss + grad_ewc)
        return {k: v.copy() for k, v in self.weights.items()}

    def consolidate(self, data_loader):
        """Snapshot current weights and refresh Fisher importance."""
        self.fisher = self.compute_fisher_diagonal(data_loader)
        self.old_weights = {k: v.copy() for k, v in self.weights.items()}


# ============================================================================
# R13 — Reinforcement-Learning Path Planner (ε-greedy Q-learning grid agent)
# ============================================================================

class ReinforcementPathPlanner:
    """Tabular Q-learning planner on a grid_size × grid_size grid.

    Actions (8): N, S, E, W, NE, NW, SE, SW.
    """

    ACTIONS = (
        ( 0,  1),    # 0 N
        ( 0, -1),    # 1 S
        ( 1,  0),    # 2 E
        (-1,  0),    # 3 W
        ( 1,  1),    # 4 NE
        (-1,  1),    # 5 NW
        ( 1, -1),    # 6 SE
        (-1, -1),    # 7 SW
    )

    def __init__(self, grid_size: int = 10, seed: int = 0):
        self.grid_size = int(grid_size)
        self._rng = np.random.default_rng(int(seed))
        self.Q = np.zeros((self.grid_size * self.grid_size, 8))

    # --- Helpers -----------------------------------------------------------

    def _state_index(self, state):
        x, y = int(state[0]), int(state[1])
        return x * self.grid_size + y

    def _step(self, state, action_idx: int):
        dx, dy = self.ACTIONS[int(action_idx)]
        nx = max(0, min(self.grid_size - 1, int(state[0]) + dx))
        ny = max(0, min(self.grid_size - 1, int(state[1]) + dy))
        return (nx, ny)

    # --- Policy ------------------------------------------------------------

    def choose_action(self, state, epsilon: float = 0.1) -> int:
        if float(self._rng.random()) < float(epsilon):
            return int(self._rng.integers(0, 8))
        idx = self._state_index(state)
        return int(np.argmax(self.Q[idx]))

    def update_q(self, state, action: int, reward: float, next_state,
                 alpha: float = 0.1, gamma: float = 0.9):
        s = self._state_index(state)
        sp = self._state_index(next_state)
        target = float(reward) + float(gamma) * float(np.max(self.Q[sp]))
        self.Q[s, int(action)] += float(alpha) * (target - self.Q[s, int(action)])

    def plan_path(self, start, goal, max_steps: int = 50):
        """Train briefly online, then roll out a greedy path start→goal."""
        gx, gy = int(goal[0]), int(goal[1])
        # Quick on-policy learning
        for _ in range(200):
            state = (int(self._rng.integers(0, self.grid_size)),
                     int(self._rng.integers(0, self.grid_size)))
            for _ in range(int(max_steps)):
                a = self.choose_action(state, epsilon=0.3)
                ns = self._step(state, a)
                d = math.hypot(ns[0] - gx, ns[1] - gy)
                reward = 10.0 if (ns[0], ns[1]) == (gx, gy) else -d * 0.1
                self.update_q(state, a, reward, ns)
                state = ns
                if (state[0], state[1]) == (gx, gy):
                    break
        # Greedy rollout
        state = (int(start[0]), int(start[1]))
        path = [state]
        for _ in range(int(max_steps)):
            if state == (gx, gy):
                break
            a = self.choose_action(state, epsilon=0.0)
            state = self._step(state, a)
            path.append(state)
        return path


# ============================================================================
# R14 — Attention-Based Multi-Modal Sensor Fusion (multi-head SDPA)
# ============================================================================

class AttentionBasedSensorFusion:
    """Scaled-dot-product multi-head attention over heterogeneous sensors.

    Each modality vector is projected/padded to ``d_model``, then split into
    ``n_heads`` chunks of size ``d_head = d_model // n_heads``.  Per-head
    Q/K/V projections produce a context vector that is concatenated, mean-
    pooled across modalities, and projected by ``W_O``.
    """

    def __init__(self, d_model: int = 16, n_heads: int = 4,
                 n_modalities: int = 3, seed: int = 42):
        if d_model % n_heads != 0:
            raise ValueError("d_model must be divisible by n_heads")
        self.d_model = int(d_model)
        self.n_heads = int(n_heads)
        self.d_head = self.d_model // self.n_heads
        self.n_modalities = int(n_modalities)
        rng = np.random.default_rng(int(seed))
        self.W_Q = rng.normal(0, 0.1, (self.n_heads, self.d_head, self.d_head))
        self.W_K = rng.normal(0, 0.1, (self.n_heads, self.d_head, self.d_head))
        self.W_V = rng.normal(0, 0.1, (self.n_heads, self.d_head, self.d_head))
        self.W_O = rng.normal(0, 0.1, (self.d_model, self.d_model))
        self._last_attn = None

    def _project(self, x):
        v = np.asarray(x, dtype=float).reshape(-1)
        out = np.zeros(self.d_model)
        n = min(v.size, self.d_model)
        out[:n] = v[:n]
        return out

    @staticmethod
    def _softmax(x):
        x = x - np.max(x, axis=-1, keepdims=True)
        e = np.exp(x)
        return e / np.sum(e, axis=-1, keepdims=True)

    def attend(self, modality_vectors):
        """Return fused (d_model,) vector from a list of modality vectors."""
        X = np.stack([self._project(v) for v in modality_vectors])  # (M, d_model)
        # Split along last axis into n_heads chunks of d_head
        X_heads = X.reshape(X.shape[0], self.n_heads, self.d_head)
        head_outputs = []
        attn_per_head = []
        for h in range(self.n_heads):
            Xh = X_heads[:, h, :]                          # (M, d_head)
            Q = Xh @ self.W_Q[h]
            K = Xh @ self.W_K[h]
            V = Xh @ self.W_V[h]
            scores = Q @ K.T / math.sqrt(self.d_head)      # (M, M)
            attn = self._softmax(scores)
            head_outputs.append(attn @ V)                  # (M, d_head)
            attn_per_head.append(attn)
        concat = np.concatenate(head_outputs, axis=-1)     # (M, d_model)
        pooled = concat.mean(axis=0)                       # (d_model,)
        out = pooled @ self.W_O
        self._last_attn = attn_per_head
        return out

    def update_weights(self, grad, lr: float = 1e-3):
        g = np.asarray(grad, dtype=float).reshape(self.W_O.shape)
        self.W_O = self.W_O - float(lr) * g


# ============================================================================
# R20 — Scene Recognizer (HOG-style histogram + cosine NN database) — R20 variant
# ============================================================================

class SceneRecognizerR20:
    """Gradient-histogram place recognition for topological localisation (R20)."""

    def __init__(self, n_bins: int = 8, cell_size: int = 4):
        self.n_bins = int(n_bins)
        self.cell_size = int(cell_size)
        self._database = []

    def extract_features(self, image):
        img = np.asarray(image, dtype=float)
        if img.ndim != 2:
            raise ValueError("image must be 2-D grayscale")
        # Sobel gradients via central differences
        Gx = np.zeros_like(img)
        Gy = np.zeros_like(img)
        Gx[:, 1:-1] = img[:, 2:] - img[:, :-2]
        Gy[1:-1, :] = img[2:, :] - img[:-2, :]
        mag = np.sqrt(Gx * Gx + Gy * Gy)
        ori = np.arctan2(Gy, Gx) % math.pi    # [0, π)
        bins = np.linspace(0.0, math.pi, self.n_bins + 1)
        hist = np.zeros(self.n_bins)
        for k in range(self.n_bins):
            mask = (ori >= bins[k]) & (ori < bins[k + 1])
            hist[k] = float(mag[mask].sum())
        n = float(np.linalg.norm(hist))
        if n > 0:
            hist = hist / n
        return hist

    def add_scene(self, image, label: str):
        self._database.append((self.extract_features(image), str(label)))

    def recognize(self, image, top_k: int = 1):
        if not self._database:
            return [("unknown", 0.0)]
        q = self.extract_features(image)
        scored = []
        for feat, lbl in self._database:
            denom = (float(np.linalg.norm(q)) * float(np.linalg.norm(feat))) \
                    + 1e-12
            cos = float(np.dot(q, feat) / denom)
            scored.append((lbl, cos))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:int(top_k)]

    def database_size(self) -> int:
        return len(self._database)

    def clear(self):
        self._database.clear()


# ============================================================================
# R21 — Transfer Learning Navigator (domain-shift affine adaptation)
# ============================================================================

class TransferLearningNavigator:
    """Affine source→target feature-space adaptation for domain shift."""

    def __init__(self, feature_dim: int = 6):
        self.feature_dim = int(feature_dim)
        self.A = np.eye(self.feature_dim)
        self.b = np.zeros(self.feature_dim)
        self.source_mean = np.zeros(self.feature_dim)
        self.source_std = np.ones(self.feature_dim)
        self.target_mean = np.zeros(self.feature_dim)
        self.target_std = np.ones(self.feature_dim)

    def fit_source(self, source_features):
        s = np.asarray(source_features, dtype=float).reshape(
            -1, self.feature_dim)
        self.source_mean = np.mean(s, axis=0)
        self.source_std = np.std(s, axis=0) + 1e-9

    def fit_target(self, target_features):
        t = np.asarray(target_features, dtype=float).reshape(
            -1, self.feature_dim)
        self.target_mean = np.mean(t, axis=0)
        self.target_std = np.std(t, axis=0) + 1e-9

    def compute_transform(self):
        scale = self.target_std / self.source_std
        self.A = np.diag(scale)
        self.b = self.target_mean - self.A @ self.source_mean

    def adapt(self, source_feature):
        f = np.asarray(source_feature, dtype=float).reshape(self.feature_dim)
        return self.A @ f + self.b

    def domain_gap(self) -> float:
        ratio = self.target_std / (self.source_std + 1e-9)
        mean_diff = self.target_mean - self.source_mean
        kl = 0.5 * float(np.sum(ratio ** 2
                                + (mean_diff / self.target_std) ** 2
                                - 1.0
                                - 2.0 * np.log(ratio + 1e-9)))
        return kl


# ============================================================================
# R22 — Visual Odometry Frontend (LK optical flow + 2-D rotation SVD)
# ============================================================================

class VisualOdometryFrontend:
    """Lucas-Kanade optical flow + SVD-based 2-D rotation estimator."""

    def __init__(self, win_size: int = 7, max_iter: int = 20,
                 eps: float = 1e-3):
        self.win = int(win_size)
        self.max_iter = int(max_iter)
        self.eps = float(eps)
        self.prev_frame = None
        self.pose = np.eye(4)

    def _sobel(self, img):
        img = np.asarray(img, dtype=float)
        Ix = np.zeros_like(img)
        Iy = np.zeros_like(img)
        Ix[:, 1:-1] = (img[:, 2:] - img[:, :-2]) / 2.0
        Iy[1:-1, :] = (img[2:, :] - img[:-2, :]) / 2.0
        return Ix, Iy

    def track_features(self, prev_img, curr_img, prev_pts):
        Ix, Iy = self._sobel(prev_img.astype(float))
        tracked = []
        valid = []
        h, w = prev_img.shape[:2]
        hw = self.win // 2
        for pt in prev_pts:
            x = float(pt[0]); y = float(pt[1])
            dx = 0.0; dy = 0.0
            ok = True
            for _ in range(self.max_iter):
                xi = int(round(x + dx)); yi = int(round(y + dy))
                if not (1 <= xi < w - 1 and 1 <= yi < h - 1):
                    ok = False; break
                x0 = max(0, xi - hw); x1 = min(w, xi + hw + 1)
                y0 = max(0, yi - hw); y1 = min(h, yi + hw + 1)
                Ixx = float(np.sum(Ix[y0:y1, x0:x1] ** 2))
                Iyy = float(np.sum(Iy[y0:y1, x0:x1] ** 2))
                Ixy = float(np.sum(Ix[y0:y1, x0:x1] * Iy[y0:y1, x0:x1]))
                xi0 = int(round(x)); yi0 = int(round(y))
                xp0 = max(0, xi0 - hw); xp1 = min(w, xi0 + hw + 1)
                yp0 = max(0, yi0 - hw); yp1 = min(h, yi0 + hw + 1)
                It = (curr_img[yp0:yp1, xp0:xp1].astype(float)
                      - prev_img[yp0:yp1, xp0:xp1].astype(float))
                bx = -float(np.sum(Ix[yp0:yp1, xp0:xp1] * It))
                by = -float(np.sum(Iy[yp0:yp1, xp0:xp1] * It))
                det = Ixx * Iyy - Ixy ** 2
                if abs(det) < 1e-12:
                    ok = False; break
                vx = (Iyy * bx - Ixy * by) / det
                vy = (Ixx * by - Ixy * bx) / det
                dx += vx; dy += vy
                if vx * vx + vy * vy < self.eps ** 2:
                    break
            tracked.append((x + dx, y + dy))
            valid.append(ok)
        return np.asarray(tracked, dtype=float), np.asarray(valid, dtype=bool)

    def estimate_rotation(self, prev_pts, curr_pts, valid):
        prev_pts = np.asarray(prev_pts, dtype=float)
        curr_pts = np.asarray(curr_pts, dtype=float)
        valid = np.asarray(valid, dtype=bool)
        p = prev_pts[valid]; c = curr_pts[valid]
        if len(p) < 2:
            return 0.0
        dp = p - p.mean(axis=0)
        dc = c - c.mean(axis=0)
        H = dp.T @ dc
        U, _, Vt = np.linalg.svd(H)
        R2 = Vt.T @ U.T
        return float(math.atan2(R2[1, 0], R2[0, 0]))

    def update_pose(self, translation_2d, rotation_rad: float):
        c = math.cos(float(rotation_rad)); s = math.sin(float(rotation_rad))
        dT = np.eye(4)
        dT[0, 0], dT[0, 1] = c, -s
        dT[1, 0], dT[1, 1] = s, c
        dT[0, 3] = float(translation_2d[0])
        dT[1, 3] = float(translation_2d[1])
        self.pose = self.pose @ dT
        return self.pose.copy()


# ============================================================================
# R23 — Online Place Database (incremental similarity-gated DB)
# ============================================================================

class OnlinePlaceDatabase:
    """Growing place-recognition database with similarity gating."""

    def __init__(self, feature_dim: int, similarity_threshold: float = 0.85):
        self.feat_dim = int(feature_dim)
        self.threshold = float(similarity_threshold)
        self.features = np.zeros((0, self.feat_dim))
        self.labels = []

    @staticmethod
    def _normalize(f):
        v = np.asarray(f, dtype=float).reshape(-1)
        n = float(np.linalg.norm(v))
        return v / (n + 1e-12)

    def add_place(self, feature, label=None) -> bool:
        f = self._normalize(feature)
        if self.features.shape[0] > 0:
            sims = self.features @ f
            if float(np.max(sims)) >= self.threshold:
                return False
        self.features = (np.vstack([self.features, f[np.newaxis, :]])
                         if self.features.shape[0] > 0
                         else f[np.newaxis, :])
        self.labels.append(label)
        return True

    def query(self, feature, top_k: int = 1):
        if self.features.shape[0] == 0:
            return []
        f = self._normalize(feature)
        sims = self.features @ f
        idx = np.argsort(sims)[::-1][:int(top_k)]
        return [(float(sims[i]), self.labels[i]) for i in idx]

    def size(self) -> int:
        return int(self.features.shape[0])

    def update_feature(self, idx: int, new_feature):
        self.features[int(idx)] = self._normalize(new_feature)

    def prune(self, min_similarity: float = 0.0):
        if self.features.shape[0] < 2:
            return
        keep = [True] * self.features.shape[0]
        for i in range(self.features.shape[0]):
            if not keep[i]:
                continue
            for j in range(i + 1, self.features.shape[0]):
                if keep[j] and float(self.features[i] @ self.features[j]) \
                        > self.threshold:
                    keep[j] = False
        mask = np.asarray(keep, dtype=bool)
        self.features = self.features[mask]
        self.labels = [l for l, k in zip(self.labels, keep) if k]


# ============================================================================
# R24 — Map-Based Lane Estimator (HD map lane assignment + snap)
# ============================================================================

class MapBasedLaneEstimator:
    """HD map lane assignment with lateral-offset estimation + snap-to-centre."""

    def __init__(self, lane_width_m: float = 3.5):
        self.lane_width = float(lane_width_m)
        self.lanes = []
        self.current_lane = None
        self.lateral_offset = 0.0

    def add_lane(self, lane_id, center_xy, heading_rad: float):
        self.lanes.append({
            "id": lane_id,
            "center": np.asarray(center_xy, dtype=float).reshape(2),
            "heading": float(heading_rad),
        })

    def _lateral_distance(self, lane, pos_xy) -> float:
        pos = np.asarray(pos_xy, dtype=float).reshape(2)
        diff = pos - lane["center"]
        perp = np.array([-math.sin(lane["heading"]),
                         math.cos(lane["heading"])])
        return float(np.dot(diff, perp))

    def assign_lane(self, pos_xy):
        pos = np.asarray(pos_xy, dtype=float).reshape(2)
        best = None
        best_d = float("inf")
        for lane in self.lanes:
            d = float(np.linalg.norm(pos - lane["center"]))
            if d < best_d:
                best_d = d
                best = lane
        self.current_lane = best
        if best is not None:
            self.lateral_offset = self._lateral_distance(best, pos_xy)
        return best, best_d

    def in_lane_bounds(self, pos_xy) -> bool:
        if self.current_lane is None:
            self.assign_lane(pos_xy)
        if self.current_lane is None:
            return False
        lat = self._lateral_distance(self.current_lane, pos_xy)
        return abs(lat) <= self.lane_width / 2.0

    def lane_constrained_position(self, raw_xy):
        pos = np.asarray(raw_xy, dtype=float).reshape(2)
        lane, _ = self.assign_lane(pos)
        if lane is None:
            return pos
        lat = self._lateral_distance(lane, pos)
        if abs(lat) <= self.lane_width / 2.0:
            perp = np.array([-math.sin(lane["heading"]),
                             math.cos(lane["heading"])])
            return pos - lat * perp
        return pos
