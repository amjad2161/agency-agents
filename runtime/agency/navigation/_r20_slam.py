"""R20 — NeuralSLAM. Imported into indoor_slam."""
from __future__ import annotations

import numpy as np


class NeuralSLAM:
    """EKF-SLAM with MLP-learned observation likelihood."""

    def __init__(self, state_dim: int = 3, obs_dim: int = 4,
                 hidden: int = 16, lr: float = 1e-3, seed: int = 42):
        self.n = int(state_dim)
        self.m = int(obs_dim)
        self.hidden = int(hidden)
        rng = np.random.default_rng(int(seed))
        self.W1 = rng.normal(0, 0.1, (self.hidden, self.n))
        self.b1 = np.zeros(self.hidden)
        self.W2 = rng.normal(0, 0.1, (self.m, self.hidden))
        self.b2 = np.zeros(self.m)
        self.lr = float(lr)
        self.x = np.zeros(self.n)
        self.P = np.eye(self.n)

    def _forward(self, x):
        x = np.asarray(x, dtype=float).reshape(self.n)
        h = np.tanh(self.W1 @ x + self.b1)
        return self.W2 @ h + self.b2, h

    def _jacobian(self, x):
        x = np.asarray(x, dtype=float).reshape(self.n)
        eps = 1e-5
        J = np.zeros((self.m, self.n))
        for j in range(self.n):
            xp = x.copy(); xm = x.copy()
            xp[j] += eps; xm[j] -= eps
            yp, _ = self._forward(xp)
            ym, _ = self._forward(xm)
            J[:, j] = (yp - ym) / (2 * eps)
        return J

    def predict(self, F, Q):
        F = np.asarray(F, dtype=float).reshape(self.n, self.n)
        Q = np.asarray(Q, dtype=float).reshape(self.n, self.n)
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

    def update(self, z, R):
        z = np.asarray(z, dtype=float).reshape(self.m)
        R = np.asarray(R, dtype=float).reshape(self.m, self.m)
        z_hat, _ = self._forward(self.x)
        H = self._jacobian(self.x)
        S = H @ self.P @ H.T + R
        try:
            K = self.P @ H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return
        self.x = self.x + K @ (z - z_hat)
        self.P = (np.eye(self.n) - K @ H) @ self.P

    def train_step(self, x_true, z_true) -> float:
        x_true = np.asarray(x_true, dtype=float).reshape(self.n)
        z_true = np.asarray(z_true, dtype=float).reshape(self.m)
        z_pred, h = self._forward(x_true)
        err = z_pred - z_true
        loss = float(np.mean(err ** 2))
        dL_dz = 2.0 * err / self.m
        self.W2 = self.W2 - self.lr * np.outer(dL_dz, h)
        self.b2 = self.b2 - self.lr * dL_dz
        dL_dh = (self.W2.T @ dL_dz) * (1.0 - h ** 2)
        self.W1 = self.W1 - self.lr * np.outer(dL_dh, x_true)
        self.b1 = self.b1 - self.lr * dL_dh
        return loss
