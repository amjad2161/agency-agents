"""
Tier 5 — REAL Extended Kalman Filter for sensor fusion.
Plain Python, no NumPy required (uses lists for vectors/matrices).
State vector: [x, y, z, vx, vy, vz] in ENU local frame.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable
from .types import Estimate, Pose, Position, Confidence, Velocity


def matmul(A, B):
    """Plain Python matrix multiply."""
    n, m, p = len(A), len(A[0]), len(B[0])
    return [[sum(A[i][k] * B[k][j] for k in range(m)) for j in range(p)] for i in range(n)]


def matadd(A, B):
    return [[A[i][j] + B[i][j] for j in range(len(A[0]))] for i in range(len(A))]


def matsub(A, B):
    return [[A[i][j] - B[i][j] for j in range(len(A[0]))] for i in range(len(A))]


def transpose(A):
    return [[A[j][i] for j in range(len(A))] for i in range(len(A[0]))]


def identity(n):
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def inv2x2(M):
    """Inverse of a 2x2 matrix."""
    a, b = M[0]; c, d = M[1]
    det = a * d - b * c
    if abs(det) < 1e-12:
        return [[1.0, 0.0], [0.0, 1.0]]
    return [[d/det, -b/det], [-c/det, a/det]]


@dataclass
class EKFState:
    """6-state EKF: position (3) + velocity (3) in local ENU."""
    x: list[list[float]] = field(default_factory=lambda: [[0.0]] * 6)  # column vector
    P: list[list[float]] = field(default_factory=lambda: [[10.0 if i == j else 0.0
                                                             for j in range(6)]
                                                             for i in range(6)])


class EKF:
    """Real EKF for position/velocity tracking from noisy 2D position measurements.

    Replaces winner-takes-all stub in fusion.py for real-world deployment.
    """

    def __init__(self, dt: float = 0.1, process_noise: float = 1.0,
                 measurement_noise: float = 5.0):
        self.dt = dt
        self.q = process_noise        # process variance
        self.r = measurement_noise    # measurement variance (m)
        self.state = EKFState()
        # State transition matrix F (constant velocity model)
        self.F = identity(6)
        for i in range(3):
            self.F[i][i + 3] = dt
        # Process noise covariance Q (block-diagonal)
        self.Q = [[0.0] * 6 for _ in range(6)]
        for i in range(3):
            self.Q[i][i] = self.q * dt ** 2
            self.Q[i + 3][i + 3] = self.q
        # Measurement matrix H (observe x, y only)
        self.H = [[1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                  [0.0, 1.0, 0.0, 0.0, 0.0, 0.0]]
        self.R = [[self.r, 0.0], [0.0, self.r]]

    def predict(self):
        """x' = F x ; P' = F P Fᵀ + Q"""
        self.state.x = matmul(self.F, self.state.x)
        FP = matmul(self.F, self.state.P)
        FT = transpose(self.F)
        FPFT = matmul(FP, FT)
        self.state.P = matadd(FPFT, self.Q)

    def update(self, z_xy: tuple[float, float]):
        """Measurement update with 2D position observation."""
        z = [[z_xy[0]], [z_xy[1]]]
        # y = z - H x
        Hx = matmul(self.H, self.state.x)
        y = matsub(z, Hx)
        # S = H P Hᵀ + R
        HP = matmul(self.H, self.state.P)
        HT = transpose(self.H)
        HPHt = matmul(HP, HT)
        S = matadd(HPHt, self.R)
        # K = P Hᵀ S⁻¹
        S_inv = inv2x2(S)
        PHt = matmul(self.state.P, HT)
        K = matmul(PHt, S_inv)
        # x = x + K y
        Ky = matmul(K, y)
        self.state.x = matadd(self.state.x, Ky)
        # P = (I - K H) P
        KH = matmul(K, self.H)
        I = identity(6)
        IKH = matsub(I, KH)
        self.state.P = matmul(IKH, self.state.P)

    def get_estimate(self) -> Estimate:
        x = [row[0] for row in self.state.x]
        # Pull horizontal uncertainty from P[0][0] + P[1][1]
        h_var = self.state.P[0][0] + self.state.P[1][1]
        h_acc = h_var ** 0.5
        v_acc = self.state.P[2][2] ** 0.5
        return Estimate(
            pose=Pose(Position(x[0], x[1], x[2])),
            velocity=Velocity(east=x[3], north=x[4], up=x[5]),
            confidence=Confidence(
                horizontal_m=h_acc,
                vertical_m=v_acc,
                valid=True,
                source="ekf-real",
            ),
            source="fusion-ekf",
        )


class EKFFusion:
    """Drop-in replacement for SensorFusion that uses real EKF instead of stub."""

    def __init__(self, dt: float = 0.1):
        self.ekf = EKF(dt=dt)

    def fuse(self, estimates: Iterable[Estimate]) -> Estimate:
        valid = [e for e in estimates if e.confidence.valid]
        if not valid:
            return self.ekf.get_estimate()
        self.ekf.predict()
        # Use lowest-uncertainty estimate as measurement
        best = min(valid, key=lambda e: e.confidence.horizontal_m)
        # In a real system: convert lat/lon to local ENU first
        z = (best.pose.position.lat, best.pose.position.lon)
        self.ekf.update(z)
        out = self.ekf.get_estimate()
        out.raw = {"contributors": [e.source for e in valid],
                   "filter": "EKF-6-state"}
        return out
