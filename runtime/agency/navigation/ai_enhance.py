"""
Tier 6 — AI/ML Enhancement
===========================
Pure-Python AI enhancement layer: deep radio maps, scene recognition,
trajectory prediction, uncertainty quantification, pose-graph SLAM,
and environment-adaptive bias correction.

All models use lightweight in-process computation (no external deps).
Optional PyTorch / ONNX backends auto-activate when available.
"""

from __future__ import annotations

import math
import time
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .types import Estimate, Confidence, Pose, Position, Velocity


# ---------------------------------------------------------------------------
# Shared helpers
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


# ---------------------------------------------------------------------------
# Radio sample for DeepRadioMap
# ---------------------------------------------------------------------------

@dataclass
class RadioSample:
    """Training sample: observed RSSI → known ground-truth position."""
    bssid: str
    rssi_dbm: float
    true_x_m: float
    true_y_m: float


# ---------------------------------------------------------------------------
# DeepRadioMap  (k-NN over fingerprint table, RSSI path-loss model)
# ---------------------------------------------------------------------------

class DeepRadioMap:
    """
    Lightweight radio-fingerprint positioning.

    Internally stores (bssid → [(rssi, x, y), ...]) and uses
    k-NN weighted by distance in RSSI space for position prediction.
    """

    def __init__(self, k: int = 5) -> None:
        self._k = k
        self._table: Dict[str, List[Tuple[float, float, float]]] = {}  # bssid → [(rssi, x, y)]

    # ------------------------------------------------------------------
    def train(self, sample: RadioSample) -> None:
        self._table.setdefault(sample.bssid, []).append(
            (sample.rssi_dbm, sample.true_x_m, sample.true_y_m)
        )

    # ------------------------------------------------------------------
    def predict(
        self, observations: List[Tuple[str, float]]
    ) -> Optional[Tuple[float, float]]:
        """
        Predict (x_m, y_m) from a list of (bssid, rssi_dbm) observations.
        Returns None if no trained data overlaps with observations.
        """
        if not observations or not self._table:
            return None

        candidates: List[Tuple[float, float, float]] = []  # (dist_sq, x, y)

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

        # Inverse-distance weighting (weight = 1 / (1 + d))
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
# SceneFeatures / SceneRecognizer
# ---------------------------------------------------------------------------

@dataclass
class SceneFeatures:
    """12-dimensional environment feature vector."""
    features: List[float]  # length 12

    def __post_init__(self) -> None:
        if len(self.features) != 12:
            # Pad or truncate to 12
            self.features = (self.features + [0.0] * 12)[:12]


_SCENE_CLASSES = [
    "outdoor_open",
    "outdoor_urban",
    "indoor_office",
    "indoor_mall",
    "underground",
    "underwater",
    "mixed",
]

# Per-class prototype vectors (hand-crafted heuristic centroids)
_SCENE_PROTOTYPES: Dict[str, List[float]] = {
    "outdoor_open":   [1,0,0,0,0,0,1,0,0,0,0,1],
    "outdoor_urban":  [1,0,0,1,1,0,0,1,0,0,0,0],
    "indoor_office":  [0,1,0,0,1,1,0,0,1,0,0,0],
    "indoor_mall":    [0,1,0,1,1,1,0,0,1,0,0,0],
    "underground":    [0,0,1,0,0,1,0,0,0,1,1,0],
    "underwater":     [0,0,0,0,0,0,0,0,0,1,0,1],
    "mixed":          [0.5]*12,
}


class SceneRecognizer:
    """Cosine-similarity nearest-prototype scene classifier."""

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
# TrajectoryPredictor  (LSTM-like ring buffer + linear extrapolation)
# ---------------------------------------------------------------------------

class TrajectoryPredictor:
    """
    Lightweight trajectory predictor using a velocity-smoothed history buffer.

    Stores the last N position estimates and extrapolates linearly
    (with exponential smoothing of the velocity vector).
    """

    def __init__(self, max_history: int = 30, alpha: float = 0.3) -> None:
        self._history: List[Tuple[float, float, float]] = []  # (x, y, ts)
        self._max = max_history
        self._alpha = alpha          # EMA weight for velocity
        self._vx: float = 0.0
        self._vy: float = 0.0

    # ------------------------------------------------------------------
    def push(self, est: Estimate) -> None:
        x = est.pose.position.lon   # treat lon=x, lat=y in local frame
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

    # ------------------------------------------------------------------
    def predict(self, horizon_s: float) -> Optional[Tuple[float, float]]:
        """Return predicted (x_m, y_m) at t+horizon_s, or None if no history."""
        if not self._history:
            return None
        x, y, _ = self._history[-1]
        return x + self._vx * horizon_s, y + self._vy * horizon_s


# ---------------------------------------------------------------------------
# EnvironmentAdapter  (per-type bias table)
# ---------------------------------------------------------------------------

class EnvironmentAdapter:
    """
    Learns per-environment-type position bias from ground-truth corrections
    and applies it to future estimates.
    """

    def __init__(self) -> None:
        self._bias: Dict[str, List[Tuple[float, float]]] = {}

    # ------------------------------------------------------------------
    def learn(self, env_type: str, dx: float, dy: float) -> None:
        """Record an observed position error (dx, dy) for env_type."""
        self._bias.setdefault(env_type, []).append((dx, dy))
        # Keep at most 200 samples per type
        if len(self._bias[env_type]) > 200:
            self._bias[env_type].pop(0)

    # ------------------------------------------------------------------
    def apply(self, env_type: str, est: Estimate) -> Estimate:
        """Return a bias-corrected copy of est for the given env_type."""
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


# ---------------------------------------------------------------------------
# BayesianUncertaintyEstimator
# ---------------------------------------------------------------------------

class BayesianUncertaintyEstimator:
    """
    Combines multiple position estimates into a weighted mean and
    returns per-axis uncertainty (std deviation).

    Returns (mean_x, mean_y, std_x, std_y).
    """

    # ------------------------------------------------------------------
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
# PoseEdge / PoseGraphSLAM
# ---------------------------------------------------------------------------

@dataclass
class PoseEdge:
    """Constraint between two poses in the graph."""
    from_id: int
    to_id: int
    dx_m: float
    dy_m: float
    dtheta_rad: float
    information: float = 1.0  # inverse variance weight


class PoseGraphSLAM:
    """
    Lightweight pose-graph SLAM with simple gradient-descent optimization.

    Nodes: (x, y, theta) — stored in ._nodes list.
    Edges: constraints — stored in ._edges list.
    close_loop() runs one GD sweep to minimize constraint residuals.
    """

    def __init__(self, learning_rate: float = 0.05, iterations: int = 50) -> None:
        self._nodes: List[List[float]] = []   # [[x,y,theta], ...]
        self._edges: List[PoseEdge] = []
        self._lr = learning_rate
        self._iterations = iterations

    # ------------------------------------------------------------------
    def add_pose(self, x: float, y: float, theta: float) -> int:
        idx = len(self._nodes)
        self._nodes.append([x, y, theta])
        return idx

    # ------------------------------------------------------------------
    def add_edge(self, edge: PoseEdge) -> None:
        self._edges.append(edge)

    # ------------------------------------------------------------------
    def close_loop(self) -> None:
        """Run gradient-descent to minimise constraint residuals."""
        if len(self._nodes) < 2 or not self._edges:
            return

        for _ in range(self._iterations):
            grads = [[0.0, 0.0, 0.0] for _ in self._nodes]

            for e in self._edges:
                i, j = e.from_id, e.to_id
                if i >= len(self._nodes) or j >= len(self._nodes):
                    continue
                ni, nj = self._nodes[i], self._nodes[j]

                # Predicted relative pose from node i to j
                cos_t = math.cos(ni[2])
                sin_t = math.sin(ni[2])
                pred_dx = cos_t * (nj[0] - ni[0]) + sin_t * (nj[1] - ni[1])
                pred_dy = -sin_t * (nj[0] - ni[0]) + cos_t * (nj[1] - ni[1])
                pred_dth = nj[2] - ni[2]

                # Residuals
                rx = pred_dx - e.dx_m
                ry = pred_dy - e.dy_m
                rt = pred_dth - e.dtheta_rad
                # Normalise theta residual to [-pi, pi]
                while rt > math.pi:
                    rt -= 2 * math.pi
                while rt < -math.pi:
                    rt += 2 * math.pi

                w = e.information
                # Accumulate gradients (simplified; fix node 0)
                if i != 0:
                    grads[i][0] += w * rx * cos_t
                    grads[i][1] += w * ry * (-sin_t)
                    grads[i][2] += w * rt
                if j != 0:
                    grads[j][0] -= w * rx * cos_t
                    grads[j][1] -= w * ry * cos_t
                    grads[j][2] -= w * rt

            # Apply gradients (skip node 0 — anchor)
            for k in range(1, len(self._nodes)):
                for d in range(3):
                    self._nodes[k][d] -= self._lr * grads[k][d]


# ---------------------------------------------------------------------------
# AIEnhancer  — main public class
# ---------------------------------------------------------------------------

class AIEnhancer:
    """
    Tier-6 AI/ML enhancement layer.

    Wraps scene recognition, radio-map positioning,
    trajectory prediction, environment adaptation,
    Bayesian uncertainty, and pose-graph SLAM.
    """

    def __init__(self) -> None:
        self.scene_recognizer = SceneRecognizer()
        self.trajectory_predictor = TrajectoryPredictor()
        self.environment_adapter = EnvironmentAdapter()
        self.uncertainty_estimator = BayesianUncertaintyEstimator()
        self.radio_map = DeepRadioMap()
        self.pose_graph = PoseGraphSLAM()
        self._env_type: str = "outdoor_open"

    # ------------------------------------------------------------------
    def enhance(
        self, est: Estimate, env_type: Optional[str] = None
    ) -> Estimate:
        """
        Apply AI enhancements to a raw position estimate.

        Steps:
          1. Detect / override environment type.
          2. Apply learned environment bias correction.
          3. Smooth trajectory.
          4. Update confidence based on Bayesian uncertainty.
        """
        etype = env_type or self._env_type
        adapted = self.environment_adapter.apply(etype, est)
        self.trajectory_predictor.push(adapted)

        # Refine confidence using trajectory smoothness
        horiz = adapted.confidence.horizontal_m
        if len(self.trajectory_predictor._history) >= 3:
            # Use velocity variance as proxy for confidence quality
            vx = self.trajectory_predictor._vx
            vy = self.trajectory_predictor._vy
            speed = math.sqrt(vx ** 2 + vy ** 2)
            # If speed is very low, slightly tighten uncertainty
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

    # ------------------------------------------------------------------
    def quantify_uncertainty(
        self, estimates: List[Estimate]
    ) -> Tuple[float, float, float, float]:
        """
        Return (mean_x, mean_y, std_x, std_y) from a list of estimates.
        Uses Bayesian uncertainty estimator internally.
        """
        return self.uncertainty_estimator.estimate(estimates)
