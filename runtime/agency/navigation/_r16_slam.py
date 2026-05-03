"""R16 — GraphSLAM. Imported into indoor_slam."""
from __future__ import annotations

import math
import numpy as np


def _wrap_angle(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


class GraphSLAM:
    """Gauss-Newton 2-D pose-graph SLAM with loop closures."""

    def __init__(self, state_dim: int = 3):
        self.state_dim = int(state_dim)
        self._poses = [np.zeros(self.state_dim)]
        self._edges = []  # (i, j, z_ij, Omega_ij)

    def add_odometry(self, delta, info):
        d = np.asarray(delta, dtype=float).reshape(self.state_dim)
        Om = np.asarray(info, dtype=float).reshape(self.state_dim,
                                                   self.state_dim)
        new_pose = self._poses[-1] + d
        if self.state_dim >= 3:
            new_pose[2] = _wrap_angle(new_pose[2])
        self._poses.append(new_pose)
        i = len(self._poses) - 2
        j = len(self._poses) - 1
        self._edges.append((i, j, d.copy(), Om.copy()))

    def add_loop_closure(self, i: int, j: int, z_ij, info):
        z = np.asarray(z_ij, dtype=float).reshape(self.state_dim)
        Om = np.asarray(info, dtype=float).reshape(self.state_dim,
                                                   self.state_dim)
        self._edges.append((int(i), int(j), z.copy(), Om.copy()))

    def _error(self, pi, pj, z_ij):
        e = z_ij - (pj - pi)
        if e.size >= 3:
            e[2] = _wrap_angle(e[2])
        return e

    def _total_error(self) -> float:
        total = 0.0
        for i, j, z, Om in self._edges:
            e = self._error(self._poses[i], self._poses[j], z)
            total += float(e @ Om @ e)
        return total

    def optimize(self, n_iter: int = 10, lr: float = 1.0) -> float:
        n = len(self._poses)
        d = self.state_dim
        for _ in range(int(n_iter)):
            H = np.zeros((n * d, n * d))
            b = np.zeros(n * d)
            for i, j, z, Om in self._edges:
                e = self._error(self._poses[i], self._poses[j], z)
                # Jacobians:  ∂e/∂pi = +I,  ∂e/∂pj = −I
                A = np.eye(d)
                B = -np.eye(d)
                ii = i * d; jj = j * d
                H[ii:ii + d, ii:ii + d] += A.T @ Om @ A
                H[jj:jj + d, jj:jj + d] += B.T @ Om @ B
                H[ii:ii + d, jj:jj + d] += A.T @ Om @ B
                H[jj:jj + d, ii:ii + d] += B.T @ Om @ A
                b[ii:ii + d] += A.T @ Om @ e
                b[jj:jj + d] += B.T @ Om @ e
            # Anchor pose 0 by overwriting its block with identity
            H[0:d, :] = 0.0
            H[:, 0:d] = 0.0
            H[0:d, 0:d] = np.eye(d)
            b[0:d] = 0.0
            try:
                dx = np.linalg.solve(H, -b)
            except np.linalg.LinAlgError:
                break
            for k in range(n):
                self._poses[k] = self._poses[k] + float(lr) * dx[k * d:(k + 1) * d]
                if d >= 3:
                    self._poses[k][2] = _wrap_angle(self._poses[k][2])
        return self._total_error()

    def poses(self):
        return np.array(self._poses)

    def n_poses(self) -> int:
        return len(self._poses)
