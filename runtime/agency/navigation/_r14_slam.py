"""R14 — FastSLAM2 + UltraWidebandPositioning. Imported into indoor_slam."""
from __future__ import annotations

import math
import numpy as np


class FastSLAM2:
    """Particle-based SLAM with per-particle EKF landmark trackers."""

    def __init__(self, n_particles: int = 50, motion_noise: float = 0.1,
                 obs_noise_range: float = 0.5, obs_noise_bearing: float = 0.05,
                 seed: int = 0):
        self.n_particles = int(n_particles)
        self.motion_noise = float(motion_noise)
        self.obs_noise_range = float(obs_noise_range)
        self.obs_noise_bearing = float(obs_noise_bearing)
        self._rng = np.random.default_rng(int(seed))
        self._particles = [{"pose": np.zeros(3), "landmarks": {}}
                           for _ in range(self.n_particles)]
        self._weights = np.ones(self.n_particles) / self.n_particles

    def predict(self, dx: float, dy: float, dtheta: float):
        for p in self._particles:
            noise = self._rng.normal(0.0, self.motion_noise, 3)
            p["pose"] = p["pose"] + np.array([float(dx), float(dy),
                                              float(dtheta)]) + noise

    def update(self, lm_id: int, obs_range: float, obs_bearing: float):
        R = np.diag([self.obs_noise_range ** 2, self.obs_noise_bearing ** 2])
        new_w = np.zeros(self.n_particles)
        for i, p in enumerate(self._particles):
            x, y, th = p["pose"]
            lm = p["landmarks"].get(int(lm_id))
            if lm is None:
                lx = x + obs_range * math.cos(th + obs_bearing)
                ly = y + obs_range * math.sin(th + obs_bearing)
                p["landmarks"][int(lm_id)] = (np.array([lx, ly]),
                                              np.eye(2) * 1.0)
                new_w[i] = self._weights[i]
                continue
            mu, Sigma = lm
            dx = mu[0] - x
            dy = mu[1] - y
            q = dx * dx + dy * dy
            r_pred = math.sqrt(max(q, 1e-9))
            b_pred = math.atan2(dy, dx) - th
            H = np.array([
                [dx / r_pred, dy / r_pred],
                [-dy / q, dx / q],
            ])
            S = H @ Sigma @ H.T + R
            try:
                K = Sigma @ H.T @ np.linalg.inv(S)
            except np.linalg.LinAlgError:
                K = np.zeros((2, 2))
            innov = np.array([float(obs_range) - r_pred,
                              float(obs_bearing) - b_pred])
            mu_new = mu + K @ innov
            Sigma_new = (np.eye(2) - K @ H) @ Sigma
            p["landmarks"][int(lm_id)] = (mu_new, Sigma_new)
            try:
                det_S = max(float(np.linalg.det(S)), 1e-12)
                like = math.exp(-0.5 * float(innov @ np.linalg.inv(S)
                                              @ innov)) / math.sqrt(
                    (2 * math.pi) ** 2 * det_S)
            except np.linalg.LinAlgError:
                like = 1e-9
            new_w[i] = self._weights[i] * like
        total = float(np.sum(new_w))
        if total > 0:
            self._weights = new_w / total
        else:
            self._weights = np.ones(self.n_particles) / self.n_particles

    def resample(self):
        positions = (self._rng.random() + np.arange(self.n_particles)) \
                    / self.n_particles
        cumulative = np.cumsum(self._weights)
        new_particles = []
        i = 0
        for p in positions:
            while i < self.n_particles - 1 and p > cumulative[i]:
                i += 1
            src = self._particles[i]
            new_particles.append({
                "pose": src["pose"].copy(),
                "landmarks": {k: (mu.copy(), Sigma.copy())
                              for k, (mu, Sigma) in src["landmarks"].items()},
            })
        self._particles = new_particles
        self._weights = np.ones(self.n_particles) / self.n_particles

    def best_pose(self):
        x = sum(self._weights[i] * self._particles[i]["pose"][0]
                for i in range(self.n_particles))
        y = sum(self._weights[i] * self._particles[i]["pose"][1]
                for i in range(self.n_particles))
        sin_sum = sum(self._weights[i]
                      * math.sin(self._particles[i]["pose"][2])
                      for i in range(self.n_particles))
        cos_sum = sum(self._weights[i]
                      * math.cos(self._particles[i]["pose"][2])
                      for i in range(self.n_particles))
        theta = math.atan2(sin_sum, cos_sum)
        return np.array([x, y, theta])

    def n_landmarks(self) -> int:
        ids = set()
        for p in self._particles:
            ids.update(p["landmarks"].keys())
        return len(ids)


class UltraWidebandPositioning:
    """UWB anchor ranging with weighted-LS and iterative Taylor refinement."""

    def __init__(self, anchors, noise_std: float = 0.05, seed: int = 0):
        self.anchors = np.asarray(anchors, dtype=float).copy()
        if self.anchors.ndim != 2 or self.anchors.shape[1] != 2:
            raise ValueError("anchors must have shape (n, 2)")
        self.noise_std = float(noise_std)
        self._rng = np.random.default_rng(int(seed))
        self._last_pos = np.zeros(2)

    def ranges_from_pos(self, true_pos, add_noise: bool = False):
        p = np.asarray(true_pos, dtype=float).reshape(2)
        ranges = np.linalg.norm(self.anchors - p, axis=1)
        if add_noise:
            ranges = ranges + self._rng.normal(0.0, self.noise_std,
                                               ranges.shape)
        return ranges

    def solve_wls(self, ranges):
        r = np.asarray(ranges, dtype=float).reshape(-1)
        if r.size < 3 or r.size != self.anchors.shape[0]:
            return self._last_pos.copy()
        a0 = self.anchors[0]
        r0 = r[0]
        A = 2.0 * (self.anchors[1:] - a0)
        b = (np.sum(self.anchors[1:] ** 2, axis=1) - np.sum(a0 * a0)) \
            - (r[1:] ** 2 - r0 ** 2)
        sigma2 = max(self.noise_std ** 2, 1e-12)
        w = np.full(b.size, 1.0 / sigma2)
        Aw = A * w[:, None]
        bw = b * w
        try:
            p, *_ = np.linalg.lstsq(Aw, bw, rcond=None)
        except np.linalg.LinAlgError:
            return self._last_pos.copy()
        self._last_pos = p
        return p

    def solve_iterative(self, ranges, n_iter: int = 5):
        r = np.asarray(ranges, dtype=float).reshape(-1)
        p = self.solve_wls(r).copy()
        for _ in range(int(n_iter)):
            diff = self.anchors - p
            dist = np.linalg.norm(diff, axis=1) + 1e-9
            H = -diff / dist[:, None]
            residual = r - dist
            try:
                dp, *_ = np.linalg.lstsq(H, residual, rcond=None)
            except np.linalg.LinAlgError:
                break
            p = p + dp
            if float(np.linalg.norm(dp)) < 1e-6:
                break
        self._last_pos = p
        return p

    def position_error(self, estimated, true_pos) -> float:
        return float(np.linalg.norm(np.asarray(estimated, dtype=float)
                                    - np.asarray(true_pos, dtype=float)))
