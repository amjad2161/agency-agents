"""R19 — LiDARSLAM. Imported into indoor_slam."""
from __future__ import annotations

import math
import numpy as np


class LiDARSLAM:
    """2-D LiDAR SLAM with hill-climb scan matching + log-odds map."""

    L_OCC = 0.85
    L_FREE = -0.4

    def __init__(self, map_size: int = 200, resolution: float = 0.05,
                 max_range: float = 10.0):
        self.map_size = int(map_size)
        self.resolution = float(resolution)
        self.max_range = float(max_range)
        self.log_odds = np.zeros((self.map_size, self.map_size))
        self.pose = np.zeros(3)
        self._scan_count = 0

    def _to_cell(self, x, y):
        cx = int(float(x) / self.resolution) + self.map_size // 2
        cy = int(float(y) / self.resolution) + self.map_size // 2
        cx = int(np.clip(cx, 0, self.map_size - 1))
        cy = int(np.clip(cy, 0, self.map_size - 1))
        return cx, cy

    def scan_to_points(self, ranges, angles):
        r = np.asarray(ranges, dtype=float).reshape(-1)
        a = np.asarray(angles, dtype=float).reshape(-1)
        n = min(r.size, a.size)
        return np.stack([r[:n] * np.cos(a[:n]),
                         r[:n] * np.sin(a[:n])], axis=1)

    def _world_points(self, body_points, pose):
        x, y, th = pose
        c = math.cos(th); s = math.sin(th)
        out = np.empty_like(body_points)
        out[:, 0] = c * body_points[:, 0] - s * body_points[:, 1] + x
        out[:, 1] = s * body_points[:, 0] + c * body_points[:, 1] + y
        return out

    def _bresenham(self, x0, y0, x1, y1):
        cells = []
        dx = abs(x1 - x0); dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        x, y = x0, y0
        while True:
            cells.append((x, y))
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy; x += sx
            if e2 < dx:
                err += dx; y += sy
        return cells

    def update_map(self, scan_points_world):
        x0c, y0c = self._to_cell(self.pose[0], self.pose[1])
        for ex, ey in scan_points_world:
            x1c, y1c = self._to_cell(ex, ey)
            cells = self._bresenham(x0c, y0c, x1c, y1c)
            for cx, cy in cells[:-1]:
                self.log_odds[cx, cy] += self.L_FREE
            ex_c, ey_c = cells[-1]
            self.log_odds[ex_c, ey_c] += self.L_OCC

    def _score(self, scan_points_world):
        score = 0.0
        for ex, ey in scan_points_world:
            cx, cy = self._to_cell(ex, ey)
            score += float(self.log_odds[cx, cy])
        return score

    def scan_match(self, scan_points, n_iter: int = 20,
                   step: float = 0.05):
        pose = self.pose.copy()
        best_pts = self._world_points(scan_points, pose)
        best_score = self._score(best_pts)
        deltas = [
            (step, 0.0, 0.0), (-step, 0.0, 0.0),
            (0.0, step, 0.0), (0.0, -step, 0.0),
            (0.0, 0.0, step), (0.0, 0.0, -step),
        ]
        for _ in range(int(n_iter)):
            improved = False
            for dx, dy, dth in deltas:
                cand = pose + np.array([dx, dy, dth])
                cand_pts = self._world_points(scan_points, cand)
                s = self._score(cand_pts)
                if s > best_score:
                    pose = cand
                    best_pts = cand_pts
                    best_score = s
                    improved = True
            if not improved:
                break
        self.pose = pose
        return pose

    def process_scan(self, ranges, angles, odometry_delta=None):
        if odometry_delta is not None:
            self.pose = self.pose + np.asarray(odometry_delta,
                                               dtype=float).reshape(3)
        body_pts = self.scan_to_points(ranges, angles)
        self.scan_match(body_pts)
        world_pts = self._world_points(body_pts, self.pose)
        self.update_map(world_pts)
        self._scan_count += 1

    @property
    def scan_count(self) -> int:
        return self._scan_count

    def probability_map(self):
        return 1.0 / (1.0 + np.exp(-self.log_odds))
