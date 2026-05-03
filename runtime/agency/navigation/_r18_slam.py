"""R18 — MonteCarloLocalization. Imported into indoor_slam."""
from __future__ import annotations

import math
import numpy as np


class MonteCarloLocalization:
    """Particle-filter localisation in a known occupancy grid."""

    def __init__(self, map_grid, resolution: float = 0.1,
                 n_particles: int = 500, seed: int = 42):
        self.map = np.asarray(map_grid, dtype=bool).copy()
        self.resolution = float(resolution)
        self.n_particles = int(n_particles)
        self._rng = np.random.default_rng(int(seed))
        self._particles, self._weights = self._init_uniform()

    def _init_uniform(self):
        free = np.argwhere(self.map)
        if free.size == 0:
            # No free cells; fall back to origin
            particles = np.zeros((self.n_particles, 3))
            return particles, np.ones(self.n_particles) / self.n_particles
        idx = self._rng.integers(0, len(free), self.n_particles)
        cell = free[idx].astype(float)
        thetas = self._rng.uniform(-math.pi, math.pi,
                                   (self.n_particles, 1))
        particles = np.hstack([cell * self.resolution, thetas])
        weights = np.ones(self.n_particles) / self.n_particles
        return particles, weights

    def predict(self, dx: float, dy: float, dtheta: float,
                noise: float = 0.05):
        n = self.n_particles
        delta = np.tile([float(dx), float(dy), float(dtheta)], (n, 1))
        noise_vec = self._rng.normal(0.0, float(noise), (n, 3))
        self._particles = self._particles + delta + noise_vec
        # Wrap theta
        self._particles[:, 2] = np.arctan2(np.sin(self._particles[:, 2]),
                                           np.cos(self._particles[:, 2]))

    def weight(self, obs_ranges, obs_bearings, sigma: float = 0.3):
        """Likelihood from average observed range vs particle distance to
        nearest map edge — simplified ranged-likelihood model."""
        ranges = np.asarray(obs_ranges, dtype=float).reshape(-1)
        if ranges.size == 0:
            return
        mean_obs = float(np.mean(ranges))
        # Per-particle distance to nearest map boundary (cell index)
        rows, cols = self.map.shape
        # Convert particle position back to cell coordinates
        cells = (self._particles[:, :2] / self.resolution).astype(int)
        cells[:, 0] = np.clip(cells[:, 0], 0, rows - 1)
        cells[:, 1] = np.clip(cells[:, 1], 0, cols - 1)
        # Approximate nearest-edge distance = min(row, col, rows-1-row, cols-1-col)
        d_top = cells[:, 0]
        d_bot = (rows - 1) - cells[:, 0]
        d_left = cells[:, 1]
        d_right = (cols - 1) - cells[:, 1]
        nearest_cells = np.minimum(np.minimum(d_top, d_bot),
                                   np.minimum(d_left, d_right))
        nearest_m = nearest_cells.astype(float) * self.resolution
        diff = mean_obs - nearest_m
        log_w = -0.5 * (diff / max(float(sigma), 1e-6)) ** 2
        log_w -= log_w.max()
        w = np.exp(log_w)
        s = float(w.sum())
        self._weights = (w / s) if s > 0 else (np.ones_like(w) / w.size)

    def resample(self):
        positions = (self._rng.random()
                     + np.arange(self.n_particles)) / self.n_particles
        cumulative = np.cumsum(self._weights)
        idx = np.searchsorted(cumulative, positions)
        idx = np.clip(idx, 0, self.n_particles - 1)
        self._particles = self._particles[idx].copy()
        self._weights = np.ones(self.n_particles) / self.n_particles

    def estimate(self):
        x = float(np.sum(self._weights * self._particles[:, 0]))
        y = float(np.sum(self._weights * self._particles[:, 1]))
        sin_sum = float(np.sum(self._weights * np.sin(self._particles[:, 2])))
        cos_sum = float(np.sum(self._weights * np.cos(self._particles[:, 2])))
        theta = math.atan2(sin_sum, cos_sum)
        return np.array([x, y, theta])

    def spread(self) -> float:
        return float(np.std(self._particles[:, :2]))
