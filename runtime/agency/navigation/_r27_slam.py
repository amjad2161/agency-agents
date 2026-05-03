"""R27 — PoseGraphSLAM. Imported into indoor_slam."""
from __future__ import annotations

import math
import numpy as np


def _wrap(a: float) -> float:
    return math.atan2(math.sin(a), math.cos(a))


class PoseGraphSLAM:
    """Gauss-Newton 2-D pose-graph SLAM with anchor-fixed node 0."""

    def __init__(self):
        self.nodes = {}    # nid -> np.ndarray [x, y, theta]
        self.edges = []    # list of (i, j, delta_pose, info_3x3)
        self._H_full = None

    def add_node(self, nid, pose):
        self.nodes[nid] = np.asarray(pose, dtype=float).reshape(3).copy()

    def add_edge(self, i, j, delta_pose, information=None):
        if information is None:
            information = np.eye(3)
        self.edges.append((
            i, j,
            np.asarray(delta_pose, dtype=float).reshape(3).copy(),
            np.asarray(information, dtype=float).reshape(3, 3).copy(),
        ))

    def linearise_edge(self, i, j, delta_pose):
        pi = self.nodes[i]; pj = self.nodes[j]
        dp = np.asarray(delta_pose, dtype=float).reshape(3)
        e = np.zeros(3)
        e[0] = pj[0] - pi[0] - dp[0]
        e[1] = pj[1] - pi[1] - dp[1]
        e[2] = _wrap(pj[2] - pi[2] - dp[2])
        return e

    def optimise(self, n_iter: int = 5):
        ids = sorted(self.nodes.keys())
        if not ids:
            return
        idx_map = {nid: k for k, nid in enumerate(ids)}
        n = len(ids)
        d = 3
        anchor_nid = ids[0]
        for _ in range(int(n_iter)):
            H = np.zeros((n * d, n * d))
            b = np.zeros(n * d)
            for i, j, dp, Om in self.edges:
                if i not in self.nodes or j not in self.nodes:
                    continue
                e = self.linearise_edge(i, j, dp)
                A = -np.eye(d); B = np.eye(d)   # ∂e/∂pi=−I, ∂e/∂pj=+I
                ii = idx_map[i] * d; jj = idx_map[j] * d
                H[ii:ii + d, ii:ii + d] += A.T @ Om @ A
                H[jj:jj + d, jj:jj + d] += B.T @ Om @ B
                H[ii:ii + d, jj:jj + d] += A.T @ Om @ B
                H[jj:jj + d, ii:ii + d] += B.T @ Om @ A
                b[ii:ii + d] += A.T @ Om @ e
                b[jj:jj + d] += B.T @ Om @ e
            # Anchor first node
            anchor_idx = idx_map[anchor_nid] * d
            H[anchor_idx:anchor_idx + d, :] = 0.0
            H[:, anchor_idx:anchor_idx + d] = 0.0
            H[anchor_idx:anchor_idx + d,
              anchor_idx:anchor_idx + d] = np.eye(d)
            b[anchor_idx:anchor_idx + d] = 0.0
            try:
                dx = np.linalg.solve(H, -b)
            except np.linalg.LinAlgError:
                break
            for nid in ids:
                k = idx_map[nid] * d
                self.nodes[nid] = self.nodes[nid] + dx[k:k + d]
                self.nodes[nid][2] = _wrap(self.nodes[nid][2])
            self._H_full = H

    def marginal_covariance(self, nid):
        if self._H_full is None:
            self.optimise(n_iter=1)
        ids = sorted(self.nodes.keys())
        idx_map = {n: k for k, n in enumerate(ids)}
        d = 3
        try:
            P = np.linalg.inv(self._H_full)
        except np.linalg.LinAlgError:
            P = np.linalg.pinv(self._H_full)
        k = idx_map[nid] * d
        return P[k:k + d, k:k + d]
