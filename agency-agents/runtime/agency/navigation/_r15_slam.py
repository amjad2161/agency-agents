"""R15 — OccupancyGridMapper. Imported into indoor_slam."""
from __future__ import annotations

import math
import numpy as np


class OccupancyGridMapper:
    """2-D log-odds occupancy grid built from range/bearing scans."""

    def __init__(self, grid_size: int = 100, resolution: float = 0.1,
                 l_occ: float = 0.85, l_free: float = -0.4):
        self.grid_size = int(grid_size)
        self.resolution = float(resolution)
        self.l_occ = float(l_occ)
        self.l_free = float(l_free)
        self.log_odds = np.zeros((self.grid_size, self.grid_size))

    def _world_to_cell(self, x, y):
        cx = int(float(x) / self.resolution) + self.grid_size // 2
        cy = int(float(y) / self.resolution) + self.grid_size // 2
        cx = int(np.clip(cx, 0, self.grid_size - 1))
        cy = int(np.clip(cy, 0, self.grid_size - 1))
        return cx, cy

    def _bresenham(self, x0, y0, x1, y1):
        """Integer Bresenham line between two cell coordinates."""
        cells = []
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
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
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
        return cells

    def update(self, pose_xy, ranges, bearings):
        pose = np.asarray(pose_xy, dtype=float).reshape(2)
        r = np.asarray(ranges, dtype=float).reshape(-1)
        b = np.asarray(bearings, dtype=float).reshape(-1)
        n = min(r.size, b.size)
        x0c, y0c = self._world_to_cell(pose[0], pose[1])
        for i in range(n):
            ex = pose[0] + r[i] * math.cos(b[i])
            ey = pose[1] + r[i] * math.sin(b[i])
            x1c, y1c = self._world_to_cell(ex, ey)
            cells = self._bresenham(x0c, y0c, x1c, y1c)
            # All but endpoint are free
            for (cx, cy) in cells[:-1]:
                self.log_odds[cx, cy] += self.l_free
            # Endpoint occupied
            ex_c, ey_c = cells[-1]
            self.log_odds[ex_c, ey_c] += self.l_occ

    def probability_map(self):
        return 1.0 / (1.0 + np.exp(-self.log_odds))

    def occupancy_at(self, x: float, y: float) -> float:
        cx, cy = self._world_to_cell(x, y)
        return float(self.probability_map()[cx, cy])

    def free_cells(self) -> int:
        return int(np.sum(self.probability_map() < 0.4))

    def occupied_cells(self) -> int:
        return int(np.sum(self.probability_map() > 0.6))
