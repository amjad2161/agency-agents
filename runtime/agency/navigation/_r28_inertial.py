"""R28 — PedestrianDeadReckoning + UWBTwoWayRanging. Imported into indoor_inertial."""
from __future__ import annotations

import math
import numpy as np


class PedestrianDeadReckoning:
    """PDR: step detection, Weinberg step length, heading integration."""

    def __init__(self, step_length_m: float = 0.75):
        self.step_length_m = float(step_length_m)

    def detect_step(self, accel_norm_window) -> bool:
        a = np.asarray(accel_norm_window, dtype=float).reshape(-1)
        if a.size < 2:
            return False
        m = float(a.mean()); s = float(a.std())
        return float(a.max()) > m + 1.2 * s

    def weinberg_step_length(self, accel_window, k: float = 0.45) -> float:
        a = np.asarray(accel_window, dtype=float).reshape(-1)
        if a.size == 0:
            return 0.0
        diff = float(a.max()) - float(a.min())
        return float(k * (max(diff, 0.0) ** 0.25))

    def update_heading(self, heading_rad: float, turn_rate_rads: float,
                       dt_s: float) -> float:
        return float(heading_rad) + float(turn_rate_rads) * float(dt_s)

    def step_position(self, pos_xy, heading_rad: float,
                      step_len: float | None = None):
        L = float(self.step_length_m if step_len is None else step_len)
        p = np.asarray(pos_xy, dtype=float).reshape(2)
        return np.array([p[0] + L * math.cos(float(heading_rad)),
                         p[1] + L * math.sin(float(heading_rad))])

    def dead_reckon(self, accel_windows, gyro_z_windows, dt_s: float,
                    initial_pos, initial_heading: float):
        traj = [np.asarray(initial_pos, dtype=float).reshape(2).copy()]
        heading = float(initial_heading)
        for a_win, g_win in zip(accel_windows, gyro_z_windows):
            a_arr = np.asarray(a_win, dtype=float).reshape(-1)
            g_arr = np.asarray(g_win, dtype=float).reshape(-1)
            avg_turn = float(g_arr.mean()) if g_arr.size else 0.0
            heading = self.update_heading(heading, avg_turn, float(dt_s))
            if self.detect_step(a_arr):
                L = self.weinberg_step_length(a_arr)
                if L <= 0:
                    L = self.step_length_m
                traj.append(self.step_position(traj[-1], heading, L))
        return np.array(traj)


class UWBTwoWayRanging:
    """UWB two-way ranging + 3-D LS trilateration."""

    C = 299792458.0
    NOISE_FLOOR_M = 0.05

    def __init__(self):
        self.anchors = {}     # aid -> pos_xyz
        self._tof = {}        # aid -> tof_ns

    def add_anchor(self, aid, pos_xyz):
        self.anchors[aid] = np.asarray(pos_xyz, dtype=float).reshape(3)

    def twr_range(self, tof_ns: float) -> float:
        d = float(self.C) * float(tof_ns) * 1e-9
        return float(max(d, 0.0))

    def add_tof(self, aid, tof_ns: float):
        self._tof[aid] = float(tof_ns)

    def trilaterate_3d(self):
        ids = [a for a in self._tof if a in self.anchors]
        if len(ids) < 3:
            return np.zeros(3)
        anchors = np.stack([self.anchors[a] for a in ids])
        ranges = np.array([self.twr_range(self._tof[a]) for a in ids])
        p = anchors.mean(axis=0)
        for _ in range(5):
            d = np.linalg.norm(anchors - p, axis=1) + 1e-9
            H = (p - anchors) / d[:, None]
            residual = ranges - d
            try:
                dp, *_ = np.linalg.lstsq(H, residual, rcond=None)
            except np.linalg.LinAlgError:
                break
            p = p + dp
            if float(np.linalg.norm(dp)) < 1e-6:
                break
        return p

    def range_std(self, tof_std_ns: float) -> float:
        return float(self.C) * float(tof_std_ns) * 1e-9
