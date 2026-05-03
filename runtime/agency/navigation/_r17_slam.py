"""R17 — ICPScanMatcher. Imported into indoor_slam."""
from __future__ import annotations

import numpy as np


class ICPScanMatcher:
    """Iterative Closest Point 2-D rigid scan matching."""

    def __init__(self, max_iter: int = 50, tol: float = 1e-4,
                 max_dist: float = 1.0):
        self.max_iter = int(max_iter)
        self.tol = float(tol)
        self.max_dist = float(max_dist)

    def _transform(self, pts, T):
        P = np.asarray(pts, dtype=float).reshape(-1, 2)
        homo = np.hstack([P, np.ones((P.shape[0], 1))])
        out = (T @ homo.T).T
        return out[:, :2]

    def _nearest(self, src, dst):
        src = np.asarray(src, dtype=float).reshape(-1, 2)
        dst = np.asarray(dst, dtype=float).reshape(-1, 2)
        if src.shape[0] == 0 or dst.shape[0] == 0:
            return src, dst
        d2 = ((src[:, None, :] - dst[None, :, :]) ** 2).sum(axis=2)
        idx = np.argmin(d2, axis=1)
        nearest = dst[idx]
        # Filter by max_dist
        mask = np.sqrt(d2[np.arange(src.shape[0]), idx]) < self.max_dist
        if mask.sum() == 0:
            return src, nearest
        return src[mask], nearest[mask]

    def _svd_align(self, src, dst):
        src = np.asarray(src, dtype=float).reshape(-1, 2)
        dst = np.asarray(dst, dtype=float).reshape(-1, 2)
        sm = src.mean(axis=0)
        dm = dst.mean(axis=0)
        sc = src - sm
        dc = dst - dm
        H = sc.T @ dc
        U, _, Vt = np.linalg.svd(H)
        R = Vt.T @ U.T
        if np.linalg.det(R) < 0:
            Vt[-1, :] *= -1.0
            R = Vt.T @ U.T
        t = dm - R @ sm
        T = np.eye(3)
        T[:2, :2] = R
        T[:2, 2] = t
        return T

    def align(self, source, target):
        src = np.asarray(source, dtype=float).reshape(-1, 2).copy()
        tgt = np.asarray(target, dtype=float).reshape(-1, 2)
        T_total = np.eye(3)
        prev_rmse = float("inf")
        last_rmse = float("inf")
        for _ in range(self.max_iter):
            matched_src, matched_dst = self._nearest(src, tgt)
            if matched_src.shape[0] < 2:
                break
            T_step = self._svd_align(matched_src, matched_dst)
            src = self._transform(src, T_step)
            T_total = T_step @ T_total
            diff = src - self._nearest(src, tgt)[1] \
                if matched_src.shape[0] > 0 else np.zeros((0, 2))
            last_rmse = float(np.sqrt(np.mean(np.sum(diff ** 2, axis=1)))) \
                if diff.size > 0 else 0.0
            if abs(prev_rmse - last_rmse) < self.tol:
                break
            prev_rmse = last_rmse
        return T_total, last_rmse

    def rmse(self, source, target, T):
        transformed = self._transform(source, T)
        _, matched_dst = self._nearest(transformed, target)
        if matched_dst.shape[0] == 0:
            return float("inf")
        diff = transformed[:matched_dst.shape[0]] - matched_dst
        return float(np.sqrt(np.mean(np.sum(diff ** 2, axis=1))))
