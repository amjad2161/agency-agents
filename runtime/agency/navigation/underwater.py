"""GODSKILL Nav v11 — Tier 3: Underwater Navigation.

Full implementation:
  - INSNavigator        : strapdown INS with DCM
  - DVLNavigator        : Doppler velocity-aided dead reckoning
  - LBLPositioner       : Long Baseline acoustic trilateration
  - USBLPositioner      : Ultra-Short Baseline bearing+range
  - SonarSLAM           : sonar landmark extraction + ICP localize
  - BathymetricMatcher  : depth-profile correlation against map
  - UnderwaterPositioner: priority fusion of all above
  - UnderwaterEngine    : legacy facade kept for backwards compatibility
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict

import numpy as np

from .types import Confidence, Estimate, Position, Pose, Velocity


# ---------------------------------------------------------------------------
# Common pose/landmark types
# ---------------------------------------------------------------------------


@dataclass
class Pose3D:
    """6-DoF pose in local navigation (NED) frame, plus timestamp."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0     # rad, about x
    pitch: float = 0.0    # rad, about y
    yaw: float = 0.0      # rad, about z (heading)
    timestamp: float = field(default_factory=time.time)

    def as_array(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z, self.roll, self.pitch, self.yaw],
                        dtype=float)


@dataclass
class Landmark:
    """Sonar-extracted point landmark in nav frame."""
    id: int
    x: float
    y: float
    z: float = 0.0
    strength: float = 1.0
    observations: int = 1


# ---------------------------------------------------------------------------
# Legacy sample dataclasses (kept; existing call-sites depend on these)
# ---------------------------------------------------------------------------


@dataclass
class INSSample:
    ax: float; ay: float; az: float
    gx: float; gy: float; gz: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class DVLSample:
    vx_mps: float
    vy_mps: float
    vz_mps: float
    beam_valid: List[bool] = field(default_factory=lambda: [True, True, True, True])
    altitude_m: Optional[float] = None


@dataclass
class LBLFix:
    transponder_id: str
    x_m: float
    y_m: float
    z_m: float = 0.0
    slant_range_m: float = 0.0
    travel_time_s: float = 0.0


@dataclass
class USBLFix:
    ship_x_m: float
    ship_y_m: float
    ship_z_m: float
    bearing_rad: float
    elevation_rad: float
    range_m: float


# ---------------------------------------------------------------------------
# Helpers — Direction Cosine Matrix from Euler (roll, pitch, yaw)
# ---------------------------------------------------------------------------


def _euler_to_dcm(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Body→NED rotation matrix using ZYX (yaw,pitch,roll) convention."""
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return np.array([
        [cy * cp,  cy * sp * sr - sy * cr,  cy * sp * cr + sy * sr],
        [sy * cp,  sy * sp * sr + cy * cr,  sy * sp * cr - cy * sr],
        [-sp,      cp * sr,                 cp * cr               ],
    ], dtype=float)


def _dcm_to_euler(dcm: np.ndarray) -> Tuple[float, float, float]:
    pitch = math.asin(max(-1.0, min(1.0, -dcm[2, 0])))
    if abs(math.cos(pitch)) > 1e-9:
        roll = math.atan2(dcm[2, 1], dcm[2, 2])
        yaw = math.atan2(dcm[1, 0], dcm[0, 0])
    else:
        roll = 0.0
        yaw = math.atan2(-dcm[0, 1], dcm[1, 1])
    return roll, pitch, yaw


def _wrap_pi(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


# Schuler period (~84.4 min for Earth) — used to damp INS vertical-channel-like
# horizontal oscillations in the simplified model.
_SCHULER_OMEGA = 2.0 * math.pi / (84.4 * 60.0)
_GRAVITY = 9.80665


# ---------------------------------------------------------------------------
# INS — Strapdown with DCM
# ---------------------------------------------------------------------------


class INSNavigator:
    """Strapdown INS using DCM body→nav with Schuler-damped horizontal
    velocity. Not a full Kalman INS; deterministic integrator suitable for
    short-window dead reckoning between aiding fixes."""

    def __init__(self, initial_pose: Optional[Pose3D] = None,
                 schuler_damping: bool = True) -> None:
        self.schuler = bool(schuler_damping)
        self.reset(initial_pose or Pose3D())

    # --------------------------------------------------------------- API ---
    def reset(self, initial_pose: Pose3D) -> None:
        self.pose = Pose3D(
            x=initial_pose.x, y=initial_pose.y, z=initial_pose.z,
            roll=initial_pose.roll, pitch=initial_pose.pitch,
            yaw=initial_pose.yaw, timestamp=initial_pose.timestamp,
        )
        self.velocity = np.zeros(3, dtype=float)            # nav frame
        self.dcm = _euler_to_dcm(self.pose.roll, self.pose.pitch, self.pose.yaw)
        self._distance = 0.0

    def update(self, accel: np.ndarray, gyro: np.ndarray, dt: float) -> Pose3D:
        """One strapdown step. accel/gyro are 3-vectors in body frame.
        Returns updated pose."""
        if dt <= 0.0:
            return self.pose
        accel = np.asarray(accel, dtype=float).reshape(3)
        gyro = np.asarray(gyro, dtype=float).reshape(3)

        self._update_dcm(gyro, dt)
        v_nav_dot = self._compute_velocity(accel, self.dcm)

        # Schuler damping on horizontal velocity error (small-amplitude model).
        if self.schuler:
            v_nav_dot[0] -= (_SCHULER_OMEGA ** 2) * (self.pose.x) * dt
            v_nav_dot[1] -= (_SCHULER_OMEGA ** 2) * (self.pose.y) * dt

        self.velocity = self.velocity + v_nav_dot * dt

        dx = self.velocity[0] * dt
        dy = self.velocity[1] * dt
        dz = self.velocity[2] * dt
        self.pose.x += dx
        self.pose.y += dy
        self.pose.z += dz
        self._distance += math.sqrt(dx * dx + dy * dy + dz * dz)

        roll, pitch, yaw = _dcm_to_euler(self.dcm)
        self.pose.roll, self.pose.pitch, self.pose.yaw = roll, pitch, yaw
        self.pose.timestamp += dt
        return self.pose

    # ----------------------------------------------------------- internals -
    def _update_dcm(self, gyro: np.ndarray, dt: float) -> None:
        """Small-angle DCM update: C_{k+1} = C_k * (I + Omega*dt)."""
        wx, wy, wz = float(gyro[0]), float(gyro[1]), float(gyro[2])
        # Skew-symmetric matrix of body-frame angular rate.
        omega_skew = np.array([
            [0.0, -wz,  wy],
            [wz,   0.0, -wx],
            [-wy,  wx,  0.0],
        ], dtype=float)
        # Second-order term improves stability for non-tiny dt.
        I = np.eye(3)
        delta = I + omega_skew * dt + 0.5 * (omega_skew @ omega_skew) * (dt * dt)
        self.dcm = self.dcm @ delta
        # Re-orthonormalize to fight numerical drift.
        u, _, vt = np.linalg.svd(self.dcm)
        self.dcm = u @ vt

    def _compute_velocity(self, accel_body: np.ndarray,
                          dcm: np.ndarray) -> np.ndarray:
        """Transform body-frame specific force to nav-frame acceleration with
        gravity removed."""
        a_nav = dcm @ accel_body
        # NED: gravity is +z; subtract it from measured specific force.
        a_nav[2] -= _GRAVITY
        return a_nav

    @property
    def distance_travelled(self) -> float:
        return self._distance


# ---------------------------------------------------------------------------
# DVL — Doppler Velocity Logger
# ---------------------------------------------------------------------------


class DVLNavigator:
    """DVL-aided dead reckoning. Velocity in body frame is rotated to nav
    frame using the supplied attitude, then integrated."""

    BOTTOM_TRACK_MIN_ALTITUDE = 0.5    # m
    VELOCITY_ERROR_FRAC = 0.001        # 0.1 % of distance travelled

    def __init__(self, initial_pose: Optional[Pose3D] = None) -> None:
        self.pose = initial_pose or Pose3D()
        self.distance = 0.0
        self.last_velocity_nav = np.zeros(3, dtype=float)

    def update(self, velocity_body: np.ndarray, depth: float,
               dt: float) -> Pose3D:
        v_body = np.asarray(velocity_body, dtype=float).reshape(3)
        v_nav = self._correct_for_attitude(
            v_body, self.pose.roll, self.pose.pitch, self.pose.yaw,
        )
        self.last_velocity_nav = v_nav
        if dt > 0.0:
            self.pose.x += v_nav[0] * dt
            self.pose.y += v_nav[1] * dt
            # depth is measured by pressure sensor → trust it directly
            self.pose.z = depth
            self.distance += float(np.linalg.norm(v_nav[:2])) * dt
            self.pose.timestamp += dt
        return self.pose

    @staticmethod
    def _correct_for_attitude(velocity_body: np.ndarray, roll: float,
                              pitch: float, heading: float) -> np.ndarray:
        dcm = _euler_to_dcm(roll, pitch, heading)
        return dcm @ np.asarray(velocity_body, dtype=float).reshape(3)

    def bottom_track_available(self, altitude: float) -> bool:
        return altitude > self.BOTTOM_TRACK_MIN_ALTITUDE

    def position_uncertainty(self) -> float:
        """1-σ horizontal uncertainty (velocity random walk model)."""
        return self.VELOCITY_ERROR_FRAC * self.distance


# ---------------------------------------------------------------------------
# Acoustic positioning — LBL (Long Baseline)
# ---------------------------------------------------------------------------


@dataclass
class _Transponder:
    id: str
    position: np.ndarray              # (3,)
    reply_delay_s: float = 0.0


class LBLPositioner:
    """Spherical least-squares trilateration from N>=3 transponders."""

    def __init__(self) -> None:
        self.transponders: Dict[str, _Transponder] = {}
        self.last_position: Optional[np.ndarray] = None

    def add_transponder(self, id: str, position_xyz, reply_delay_s: float = 0.0) -> None:
        pos = np.asarray(position_xyz, dtype=float).reshape(3)
        self.transponders[id] = _Transponder(id=id, position=pos,
                                             reply_delay_s=float(reply_delay_s))

    def update(self, ranges: Dict[str, float]) -> np.ndarray:
        """Compute receiver position from a dict of {transponder_id: slant_range}."""
        valid: List[Tuple[_Transponder, float]] = []
        for tid, r in ranges.items():
            t = self.transponders.get(tid)
            if t is None or not math.isfinite(float(r)) or r <= 0.0:
                continue
            # Reply delay biases observed range upward by c*tau/2 — but here
            # the delay is supplied in seconds and we don't know sound speed
            # exactly; subtract a 1500 m/s nominal correction.
            r_corr = float(r) - 1500.0 * t.reply_delay_s
            valid.append((t, r_corr))
        if len(valid) < 3:
            raise ValueError("LBL trilateration needs at least 3 transponders")
        return self._spherical_trilateration(valid)

    @staticmethod
    def _spherical_trilateration(
            measurements: List[Tuple[_Transponder, float]]) -> np.ndarray:
        """Linearize ||p - p_i||^2 = r_i^2 against the first beacon."""
        p0 = measurements[0][0].position
        r0 = measurements[0][1]
        A_rows: List[np.ndarray] = []
        b_rows: List[float] = []
        for t, r in measurements[1:]:
            pi = t.position
            A_rows.append(2.0 * (pi - p0))
            b_rows.append((r0 ** 2 - r ** 2)
                          + (pi @ pi) - (p0 @ p0))
        A = np.vstack(A_rows)
        b = np.array(b_rows, dtype=float)
        # Least-squares solution.
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
        # If we only have 3D->3 equations, sol has shape (3,); when ill-posed
        # in z (e.g., transponders co-planar in z), keep z=p0.z.
        if sol.shape[0] == 2:
            sol = np.array([sol[0], sol[1], p0[2]], dtype=float)
        return sol


# ---------------------------------------------------------------------------
# Acoustic positioning — USBL (Ultra-Short Baseline)
# ---------------------------------------------------------------------------


class USBLPositioner:
    """Compute target position from ship pose + bearing/elevation/slant range.

    Convention:
      azimuth   — angle CW from North in the horizontal plane (rad)
      elevation — angle below horizontal (rad), positive = below ship
      surface_position — (x, y, z) of ship in nav frame
    """

    def __init__(self) -> None:
        self.last_position: Optional[np.ndarray] = None

    def update(self, angle_azimuth: float, angle_elevation: float,
               slant_range: float, surface_position) -> np.ndarray:
        ship = np.asarray(surface_position, dtype=float).reshape(3)
        r = float(slant_range)
        az = float(angle_azimuth)
        el = float(angle_elevation)
        horiz = r * math.cos(el)
        dx = horiz * math.sin(az)        # East component
        dy = horiz * math.cos(az)        # North component
        dz = r * math.sin(el)            # positive = below
        target = ship + np.array([dx, dy, dz], dtype=float)
        self.last_position = target
        return target


# ---------------------------------------------------------------------------
# Sonar SLAM — landmark extraction + 2D ICP localize
# ---------------------------------------------------------------------------


class SonarSLAM:
    """Lightweight 2D sonar SLAM.

    process_scan : extract Landmarks from a (ranges, angles) scan.
    update_map   : merge landmarks into the map (nearest-neighbour fusion).
    localize     : 2D point-to-point ICP between a new scan and the map.
    """

    def __init__(self, peak_threshold: float = 0.5,
                 association_radius: float = 1.0) -> None:
        self.peak_threshold = peak_threshold
        self.association_radius = association_radius
        self.landmarks: List[Landmark] = []
        self._next_id = 0

    # --------------------------------------------------------- scan parse --
    def process_scan(self, ranges: np.ndarray, angles: np.ndarray,
                     pose: Pose3D) -> List[Landmark]:
        peaks = self._detect_landmarks(np.asarray(ranges, dtype=float),
                                       np.asarray(angles, dtype=float))
        cy, sy = math.cos(pose.yaw), math.sin(pose.yaw)
        out: List[Landmark] = []
        for r, theta in peaks:
            # body frame: x forward, y right
            bx = r * math.cos(theta)
            by = r * math.sin(theta)
            wx = pose.x + cy * bx - sy * by
            wy = pose.y + sy * bx + cy * by
            out.append(Landmark(id=-1, x=wx, y=wy, z=pose.z, strength=r))
        return out

    def _detect_landmarks(self, ranges: np.ndarray,
                          angles: np.ndarray) -> List[Tuple[float, float]]:
        """Find local minima ('returns closer than neighbours') in the
        range scan — these are likely point reflectors."""
        n = len(ranges)
        if n < 3 or len(angles) != n:
            return []
        peaks: List[Tuple[float, float]] = []
        finite = np.isfinite(ranges)
        for i in range(1, n - 1):
            if not (finite[i - 1] and finite[i] and finite[i + 1]):
                continue
            r = ranges[i]
            if r <= 0.0:
                continue
            # local minimum in range = closer object spike
            if r < ranges[i - 1] - self.peak_threshold and \
               r < ranges[i + 1] - self.peak_threshold:
                peaks.append((float(r), float(angles[i])))
        return peaks

    # ------------------------------------------------------------ mapping -
    def update_map(self, landmarks: List[Landmark], pose: Pose3D) -> None:
        for lm in landmarks:
            existing = self._nearest(lm.x, lm.y)
            if existing is not None and \
               math.hypot(existing.x - lm.x, existing.y - lm.y) < self.association_radius:
                # Running mean update.
                n = existing.observations + 1
                existing.x = (existing.x * existing.observations + lm.x) / n
                existing.y = (existing.y * existing.observations + lm.y) / n
                existing.z = (existing.z * existing.observations + lm.z) / n
                existing.observations = n
            else:
                lm.id = self._next_id
                self._next_id += 1
                lm.observations = 1
                self.landmarks.append(lm)

    def _nearest(self, x: float, y: float) -> Optional[Landmark]:
        if not self.landmarks:
            return None
        best, best_d = None, float("inf")
        for lm in self.landmarks:
            d = math.hypot(lm.x - x, lm.y - y)
            if d < best_d:
                best, best_d = lm, d
        return best

    # ----------------------------------------------------------- localize -
    def localize(self, scan_ranges: np.ndarray,
                 scan_angles: np.ndarray) -> Pose3D:
        """ICP-lite scan-to-map alignment. Assumes initial pose ≈ origin and
        small heading offset; suitable for incremental localization."""
        if not self.landmarks:
            return Pose3D()
        # Convert scan into body-frame Cartesian points.
        ranges = np.asarray(scan_ranges, dtype=float)
        angles = np.asarray(scan_angles, dtype=float)
        finite = np.isfinite(ranges) & (ranges > 0.0)
        ranges = ranges[finite]
        angles = angles[finite]
        if ranges.size == 0:
            return Pose3D()
        sx = ranges * np.cos(angles)
        sy = ranges * np.sin(angles)
        source = np.column_stack([sx, sy])
        target = np.array([[lm.x, lm.y] for lm in self.landmarks], dtype=float)
        R, t = self._icp(source, target)
        yaw = math.atan2(R[1, 0], R[0, 0])
        return Pose3D(x=float(t[0]), y=float(t[1]), yaw=yaw)

    # ---------------------------------------------------------------- NDT --
    def scan_matching_ndt(
        self,
        scan_a: np.ndarray,
        scan_b: np.ndarray,
        cell_size: float = 1.0,
        max_iter: int = 20,
    ) -> Dict[str, object]:
        """Normal Distribution Transform scan matching.

        Fits 2-D Gaussians to cells of ``scan_a`` then runs Newton steps to
        find the rigid (R, t) that maximises the likelihood of points in
        ``scan_b`` under those Gaussians.  Faster than ICP for sparse sonar
        scans because it avoids the O(N*M) nearest-neighbour search.

        Returns dict with ``R`` (2x2), ``t`` (2,), ``score``, ``iterations``.
        """
        a = np.asarray(scan_a, dtype=float)
        b = np.asarray(scan_b, dtype=float)
        if (a.ndim != 2 or a.shape[1] != 2 or b.ndim != 2 or b.shape[1] != 2
                or a.shape[0] == 0 or b.shape[0] == 0):
            return {"R": np.eye(2), "t": np.zeros(2),
                    "score": 0.0, "iterations": 0}
        cells = self._build_ndt_cells(a, cell_size)
        # Pose parameter: (tx, ty, theta).  Initialise at zero.
        p = np.zeros(3, dtype=float)
        score = 0.0
        iters = 0
        for iters in range(1, max_iter + 1):
            R = self._rot2d(p[2])
            t = p[:2]
            transformed = (R @ b.T).T + t
            score, grad, H = self._ndt_score_and_hessian(
                transformed, b, cells, p[2],
            )
            # Levenberg-style damping for stability.
            H_d = H + np.eye(3) * 1e-3
            try:
                dp = np.linalg.solve(H_d, -grad)
            except np.linalg.LinAlgError:
                break
            p = p + dp
            if np.linalg.norm(dp) < 1e-6:
                break
        R = self._rot2d(p[2])
        return {
            "R": R,
            "t": p[:2],
            "score": float(score),
            "iterations": iters,
        }

    @staticmethod
    def _rot2d(theta: float) -> np.ndarray:
        c, s = math.cos(theta), math.sin(theta)
        return np.array([[c, -s], [s, c]], dtype=float)

    @staticmethod
    def _build_ndt_cells(points: np.ndarray, cell_size: float) -> Dict:
        """Bin ``points`` into cells of size ``cell_size`` and fit a Gaussian
        per cell.  Cells with fewer than 3 points are skipped.  Returns
        dict mapping (ix, iy) → (mean (2,), inv_cov (2x2))."""
        cs = max(float(cell_size), 1e-6)
        groups: Dict[Tuple[int, int], List[np.ndarray]] = {}
        for pt in points:
            key = (int(math.floor(pt[0] / cs)), int(math.floor(pt[1] / cs)))
            groups.setdefault(key, []).append(pt)
        cells: Dict[Tuple[int, int], Tuple[np.ndarray, np.ndarray]] = {}
        for key, pts in groups.items():
            if len(pts) < 3:
                continue
            arr = np.array(pts, dtype=float)
            mu = arr.mean(axis=0)
            cov = np.cov(arr.T) + np.eye(2) * 1e-3
            try:
                inv = np.linalg.inv(cov)
            except np.linalg.LinAlgError:
                continue
            cells[key] = (mu, inv)
        return cells

    @staticmethod
    def _ndt_score_and_hessian(
        transformed: np.ndarray,
        original: np.ndarray,
        cells: Dict,
        theta: float,
    ) -> Tuple[float, np.ndarray, np.ndarray]:
        """Compute NDT score, gradient (3,) and Hessian (3x3) wrt (tx,ty,θ)."""
        if not cells:
            return 0.0, np.zeros(3), np.eye(3)
        score = 0.0
        grad = np.zeros(3, dtype=float)
        H = np.zeros((3, 3), dtype=float)
        s, c = math.sin(theta), math.cos(theta)
        for i, q in enumerate(transformed):
            # Find nearest cell mean (cheap: round to cell index of q).
            best_key = None
            best_d = float("inf")
            for key in cells:
                mu, _ = cells[key]
                d = (q[0] - mu[0]) ** 2 + (q[1] - mu[1]) ** 2
                if d < best_d:
                    best_d = d
                    best_key = key
            if best_key is None:
                continue
            mu, inv = cells[best_key]
            r = q - mu
            e = math.exp(-0.5 * float(r @ inv @ r))
            score += e
            # Jacobian of q wrt (tx, ty, theta)
            x0, y0 = original[i]
            J = np.array([
                [1.0, 0.0, -s * x0 - c * y0],
                [0.0, 1.0,  c * x0 - s * y0],
            ], dtype=float)
            g_local = -e * (inv @ r) @ J
            grad += g_local
            H += e * (J.T @ inv @ J)
        return score, grad, H

    # ----------------------------------------------------- loop closure ----
    def bathymetric_loop_closure(
        self,
        map_store: "BathymetricMatcher",
        depth_profile: np.ndarray,
        heading: float = 0.0,
        threshold: float = 0.85,
    ) -> Dict[str, object]:
        """Compare ``depth_profile`` against ``map_store``'s grid and trigger
        loop closure when normalised cross-correlation exceeds ``threshold``.
        """
        if map_store.depth_grid is None:
            return {"closed": False, "score": 0.0, "lat": 0.0, "lon": 0.0,
                    "reason": "no_map"}
        prof = np.asarray(depth_profile, dtype=float).ravel()
        if prof.size < 2:
            return {"closed": False, "score": 0.0, "lat": 0.0, "lon": 0.0,
                    "reason": "profile_too_small"}
        H, W = map_store.depth_grid.shape
        L = prof.size
        best_score = -float("inf")
        best_ix, best_iy = 0, 0
        cos_h = math.cos(heading)
        sin_h = math.sin(heading)
        for iy in range(H):
            for ix in range(W):
                xs = ix + np.arange(L) * sin_h
                ys = iy + np.arange(L) * cos_h
                xi = np.clip(np.round(xs).astype(int), 0, W - 1)
                yi = np.clip(np.round(ys).astype(int), 0, H - 1)
                ref = map_store.depth_grid[yi, xi]
                m0 = prof - prof.mean()
                r0 = ref - ref.mean()
                denom = float(np.linalg.norm(m0) * np.linalg.norm(r0))
                if denom < 1e-12:
                    continue
                ncc = float(np.dot(m0, r0) / denom)
                if ncc > best_score:
                    best_score = ncc
                    best_ix, best_iy = ix, iy
        meters_per_deg_lat = 111_320.0
        meters_per_deg_lon = 111_320.0 * max(
            0.01, math.cos(math.radians(map_store.origin_lat)),
        )
        lat = map_store.origin_lat + (best_iy * map_store.resolution_m) / meters_per_deg_lat
        lon = map_store.origin_lon + (best_ix * map_store.resolution_m) / meters_per_deg_lon
        closed = best_score >= float(threshold)
        return {
            "closed": closed,
            "score": float(best_score),
            "lat": float(lat),
            "lon": float(lon),
            "threshold": float(threshold),
        }

    # -------------------------------------------------- uncertainty prop ---
    def uncertainty_propagation(
        self,
        scan_jacobian: Optional[np.ndarray] = None,
        prior_cov: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Propagate prior pose covariance through scan-matching Jacobian.

        Returns a 3x3 covariance.  Defaults: identity Jacobian and unit
        prior — useful for runtime monitoring rather than estimation.
        """
        J = (np.asarray(scan_jacobian, dtype=float) if scan_jacobian is not None
             else np.eye(3))
        P = (np.asarray(prior_cov, dtype=float) if prior_cov is not None
             else np.eye(3) * 0.1)
        if J.shape != (3, 3) or P.shape != (3, 3):
            return np.eye(3) * 0.1
        # Standard linearised propagation: P' = J P J^T + small additive noise
        out = J @ P @ J.T + np.eye(3) * 1e-4
        return out

    @staticmethod
    def _icp(source: np.ndarray, target: np.ndarray,
             max_iter: int = 20) -> Tuple[np.ndarray, np.ndarray]:
        """Plain 2D point-to-point ICP. Returns (R, t) such that R @ s + t ≈ target."""
        src = source.astype(float).copy()
        tgt = target.astype(float)
        if src.size == 0 or tgt.size == 0:
            return np.eye(2), np.zeros(2)
        R_total = np.eye(2)
        t_total = np.zeros(2)
        for _ in range(int(max_iter)):
            # Nearest-neighbour association (brute force; fine for small N).
            diffs = src[:, None, :] - tgt[None, :, :]
            d2 = np.sum(diffs * diffs, axis=2)
            idx = np.argmin(d2, axis=1)
            matched = tgt[idx]
            # Compute rigid transform via SVD.
            mu_s = src.mean(axis=0)
            mu_t = matched.mean(axis=0)
            S = (src - mu_s).T @ (matched - mu_t)
            U, _, Vt = np.linalg.svd(S)
            R = Vt.T @ U.T
            if np.linalg.det(R) < 0.0:
                Vt[-1, :] *= -1
                R = Vt.T @ U.T
            t = mu_t - R @ mu_s
            src = (R @ src.T).T + t
            R_total = R @ R_total
            t_total = R @ t_total + t
            if np.linalg.norm(t) < 1e-6 and np.allclose(R, np.eye(2), atol=1e-6):
                break
        return R_total, t_total


# ---------------------------------------------------------------------------
# Bathymetric map matching
# ---------------------------------------------------------------------------


class BathymetricMatcher:
    """Match measured depth profile against a stored depth grid."""

    def __init__(self) -> None:
        self.depth_grid: Optional[np.ndarray] = None
        self.origin_lat: float = 0.0
        self.origin_lon: float = 0.0
        self.resolution_m: float = 1.0

    def load_map(self, depth_grid: np.ndarray, origin_lat: float,
                 origin_lon: float, resolution_m: float) -> None:
        self.depth_grid = np.asarray(depth_grid, dtype=float)
        self.origin_lat = float(origin_lat)
        self.origin_lon = float(origin_lon)
        self.resolution_m = float(resolution_m)

    def match(self, depth_profile: np.ndarray, heading: float,
              speed: float) -> Tuple[float, float]:
        """Slide the depth profile across rows of the grid (along heading)
        and return the (lat, lon) of the best correlation peak."""
        if self.depth_grid is None:
            raise RuntimeError("BathymetricMatcher: no map loaded")
        prof = np.asarray(depth_profile, dtype=float)
        if prof.ndim != 1 or prof.size < 2:
            raise ValueError("depth_profile must be a 1-D array with >=2 samples")
        H, W = self.depth_grid.shape
        best_score = -float("inf")
        best_ix = 0
        best_iy = 0
        # Sample step (in cells) along travel direction.
        # We assume one profile sample per grid cell along heading.
        cos_h = math.cos(heading)
        sin_h = math.sin(heading)
        L = prof.size
        for iy in range(H):
            for ix in range(W):
                # Reconstruct the reference profile starting at (ix, iy).
                xs = ix + np.arange(L) * sin_h
                ys = iy + np.arange(L) * cos_h
                xi = np.clip(np.round(xs).astype(int), 0, W - 1)
                yi = np.clip(np.round(ys).astype(int), 0, H - 1)
                ref = self.depth_grid[yi, xi]
                score = self._terrain_correlation(prof, ref)
                if score > best_score:
                    best_score = score
                    best_ix, best_iy = ix, iy
        # Convert (ix, iy) cell to lat/lon offset.
        meters_per_deg_lat = 111_320.0
        meters_per_deg_lon = 111_320.0 * max(0.01, math.cos(math.radians(self.origin_lat)))
        dx_m = best_ix * self.resolution_m
        dy_m = best_iy * self.resolution_m
        lat = self.origin_lat + dy_m / meters_per_deg_lat
        lon = self.origin_lon + dx_m / meters_per_deg_lon
        return lat, lon

    @staticmethod
    def _terrain_correlation(measured: np.ndarray,
                             reference: np.ndarray) -> float:
        """Normalized cross-correlation; safe against constant slices."""
        m = np.asarray(measured, dtype=float)
        r = np.asarray(reference, dtype=float)
        if m.size != r.size or m.size == 0:
            return -float("inf")
        m0 = m - m.mean()
        r0 = r - r.mean()
        denom = (np.linalg.norm(m0) * np.linalg.norm(r0))
        if denom < 1e-12:
            return 0.0
        return float(np.dot(m0, r0) / denom)


# ---------------------------------------------------------------------------
# Sensor fusion — priority blending of acoustic / DVL-INS / INS-only
# ---------------------------------------------------------------------------


class UnderwaterPositioner:
    """High-level fusion. Priority:
        1. acoustic (LBL/USBL fix) — bounded error, ~0.5 m
        2. DVL+INS                 — ~0.1 % of distance travelled
        3. INS only                — high drift
    """

    def __init__(self) -> None:
        self.ins = INSNavigator()
        self.dvl = DVLNavigator()
        self.last_pose: Pose3D = Pose3D()
        self.last_source: str = "init"

    def fuse(self, dvl: Optional[Pose3D], ins: Optional[Pose3D],
             acoustic: Optional[np.ndarray], depth: Optional[float]) -> Pose3D:
        # 1. Acoustic snaps the horizontal position.
        if acoustic is not None:
            a = np.asarray(acoustic, dtype=float).reshape(3)
            base = dvl or ins or self.last_pose
            self.last_pose = Pose3D(
                x=float(a[0]), y=float(a[1]),
                z=depth if depth is not None else float(a[2]),
                roll=base.roll, pitch=base.pitch, yaw=base.yaw,
                timestamp=time.time(),
            )
            self.last_source = "acoustic"
            return self.last_pose
        # 2. DVL-aided dead reckoning.
        if dvl is not None:
            self.last_pose = Pose3D(
                x=dvl.x, y=dvl.y,
                z=depth if depth is not None else dvl.z,
                roll=(ins.roll if ins else dvl.roll),
                pitch=(ins.pitch if ins else dvl.pitch),
                yaw=(ins.yaw if ins else dvl.yaw),
                timestamp=time.time(),
            )
            self.last_source = "dvl-ins" if ins else "dvl"
            return self.last_pose
        # 3. INS-only.
        if ins is not None:
            self.last_pose = Pose3D(
                x=ins.x, y=ins.y,
                z=depth if depth is not None else ins.z,
                roll=ins.roll, pitch=ins.pitch, yaw=ins.yaw,
                timestamp=time.time(),
            )
            self.last_source = "ins"
            return self.last_pose
        return self.last_pose


# ---------------------------------------------------------------------------
# Backwards-compatible legacy facade: UnderwaterEngine
# ---------------------------------------------------------------------------


class UnderwaterEngine:
    """Legacy facade — wraps the new components but preserves the older API
    used by call-sites elsewhere in the codebase."""

    def __init__(self) -> None:
        self._x = 0.0; self._y = 0.0; self._z = 0.0
        self._vx = 0.0; self._vy = 0.0; self._vz = 0.0
        self._heading = 0.0; self._pitch = 0.0; self._roll = 0.0
        self._dist_travelled = 0.0
        self._h_acc = float("inf")
        self._last_ts: Optional[float] = None
        self._lbl_fixes: Dict[str, LBLFix] = {}

    def update_ins(self, sample: INSSample) -> Optional[Estimate]:
        ts = sample.timestamp
        if self._last_ts is None:
            self._last_ts = ts
            return None
        dt = max(ts - self._last_ts, 1e-6)
        self._last_ts = ts
        self._heading += sample.gz * dt
        self._pitch += sample.gy * dt
        self._roll += sample.gx * dt
        ax_world = sample.ax - _GRAVITY * math.sin(self._pitch)
        ay_world = sample.ay - _GRAVITY * math.sin(self._roll)
        self._vx += ax_world * dt
        self._vy += ay_world * dt
        self._x += self._vx * dt
        self._y += self._vy * dt
        self._z += self._vz * dt
        self._h_acc = min((self._h_acc if math.isfinite(self._h_acc) else 0.0)
                          + 0.003 * dt, 50.0)
        return self._make_estimate("underwater-ins", self._h_acc)

    def update_dvl(self, sample: DVLSample) -> Optional[Estimate]:
        valid_beams = sum(1 for v in sample.beam_valid if v)
        if valid_beams < 1:
            return None
        vx = sample.vx_mps * math.cos(self._heading) - sample.vy_mps * math.sin(self._heading)
        vy = sample.vx_mps * math.sin(self._heading) + sample.vy_mps * math.cos(self._heading)
        self._vx, self._vy, self._vz = vx, vy, sample.vz_mps
        dt = 0.1
        self._x += self._vx * dt
        self._y += self._vy * dt
        speed = math.hypot(vx, vy)
        self._dist_travelled += speed * dt
        self._h_acc = max(0.003 * self._dist_travelled, 0.1)
        return self._make_estimate("underwater-dvl", self._h_acc)

    def update_lbl(self, fix: LBLFix) -> Optional[Estimate]:
        self._lbl_fixes[fix.transponder_id] = fix
        if len(self._lbl_fixes) < 3:
            return None
        positioner = LBLPositioner()
        ranges = {}
        for tid, f in self._lbl_fixes.items():
            positioner.add_transponder(tid, [f.x_m, f.y_m, f.z_m])
            ranges[tid] = f.slant_range_m
        try:
            pos = positioner.update(ranges)
        except (ValueError, np.linalg.LinAlgError):
            return None
        self._x, self._y = float(pos[0]), float(pos[1])
        self._h_acc = 0.5
        self._dist_travelled = 0.0
        return self._make_estimate("underwater-lbl", self._h_acc)

    def update_usbl(self, fix: USBLFix) -> Optional[Estimate]:
        usbl = USBLPositioner()
        target = usbl.update(
            angle_azimuth=fix.bearing_rad,
            angle_elevation=fix.elevation_rad,
            slant_range=fix.range_m,
            surface_position=[fix.ship_x_m, fix.ship_y_m, fix.ship_z_m],
        )
        self._x, self._y, self._z = float(target[0]), float(target[1]), float(target[2])
        self._h_acc = max(fix.range_m * 0.01, 0.1)
        return self._make_estimate("underwater-usbl", self._h_acc)

    def _make_estimate(self, src: str, h_acc: float) -> Estimate:
        return Estimate(
            pose=Pose(Position(self._x, self._y, self._z)),
            velocity=Velocity(east=self._vx, north=self._vy, up=self._vz),
            confidence=Confidence(horizontal_m=h_acc, vertical_m=h_acc * 1.5,
                                  valid=True, source=src),
            source="underwater",
            raw={"dist_travelled_m": self._dist_travelled},
        )

    def reset(self) -> None:
        self.__init__()


UnderwaterEstimator = UnderwaterEngine

__all__ = [
    "Pose3D", "Landmark",
    "INSSample", "DVLSample", "LBLFix", "USBLFix",
    "INSNavigator", "DVLNavigator",
    "LBLPositioner", "USBLPositioner",
    "SonarSLAM", "BathymetricMatcher",
    "UnderwaterPositioner",
    "UnderwaterEngine", "UnderwaterEstimator",
]


# ---------------------------------------------------------------------------
# Acoustic modem navigation (Round 5)
# ---------------------------------------------------------------------------


class AcousticModemNav:
    """Acoustic modem-based navigation: TWTT ranging + TDOA fix + Doppler.

    All times in seconds, positions in metres (any consistent frame).  The
    speed of sound default is 1500 m/s — typical seawater value at 4°C and
    35 PSU; pass a measured speed for higher accuracy.
    """

    def __init__(self, sound_speed: float = 1500.0) -> None:
        self.sound_speed = float(sound_speed)
        self._range_history: List[float] = []

    # -- two-way ranging ----------------------------------------------------
    @staticmethod
    def two_way_ranging(
        tx_time: float,
        rx_time: float,
        sound_speed: float = 1500.0,
    ) -> float:
        """Return slant range = ((rx - tx) / 2) * c."""
        dt = float(rx_time) - float(tx_time)
        if dt < 0.0:
            return 0.0
        return 0.5 * dt * float(sound_speed)

    # -- TDOA fix -----------------------------------------------------------
    @staticmethod
    def tdoa_fix(
        hydrophone_positions: np.ndarray,
        arrival_times: np.ndarray,
        sound_speed: float = 1500.0,
        max_iter: int = 50,
    ) -> dict:
        """Hyperbolic TDOA fix using Newton-Raphson over (x, y, z, t0).

        Requires at least 3 hydrophones (4 unknowns may need 4+ for unique
        fix; we expose the 3-hydrophone underdetermined case anyway and
        damp the solver).  Returns dict with ``position`` and ``iterations``.
        """
        H = np.asarray(hydrophone_positions, dtype=float)
        T = np.asarray(arrival_times, dtype=float).reshape(-1)
        if H.ndim != 2 or H.shape[1] != 3 or H.shape[0] < 3:
            return {"position": np.zeros(3), "iterations": 0,
                    "converged": False}
        if H.shape[0] != T.size:
            return {"position": np.zeros(3), "iterations": 0,
                    "converged": False}
        c = float(sound_speed)
        # Initial guess: centroid of hydrophones.
        x = H.mean(axis=0).astype(float)
        t0 = float(T.min()) - float(np.linalg.norm(H[0] - x)) / c
        params = np.array([x[0], x[1], x[2], t0], dtype=float)
        n = H.shape[0]
        converged = False
        for itr in range(1, max_iter + 1):
            # Residual: c*(T_i - t0) - ||H_i - p||
            p = params[:3]
            t0_cur = params[3]
            r = np.zeros(n, dtype=float)
            J = np.zeros((n, 4), dtype=float)
            for i in range(n):
                diff = H[i] - p
                d = float(np.linalg.norm(diff))
                if d < 1e-9:
                    d = 1e-9
                r[i] = c * (T[i] - t0_cur) - d
                J[i, 0:3] = diff / d
                J[i, 3] = -c
            JtJ = J.T @ J + np.eye(4) * 1e-6
            try:
                dp = np.linalg.solve(JtJ, -J.T @ r)
            except np.linalg.LinAlgError:
                break
            params = params + dp
            if float(np.linalg.norm(dp)) < 1e-6:
                converged = True
                return {
                    "position": params[:3].copy(),
                    "t0": float(params[3]),
                    "iterations": itr,
                    "converged": True,
                }
        return {
            "position": params[:3].copy(),
            "t0": float(params[3]),
            "iterations": max_iter,
            "converged": converged,
        }

    # -- Doppler ------------------------------------------------------------
    @staticmethod
    def doppler_velocity(
        carrier_freq_hz: float,
        observed_freq_hz: float,
        sound_speed: float = 1500.0,
    ) -> float:
        """Radial velocity (m/s) from observed Doppler shift.

        f_obs = f_carrier * (c - v_radial) / c
        => v_radial = c * (1 - f_obs / f_carrier)
        Positive = receiver moving away (frequency drops).
        """
        if carrier_freq_hz <= 0.0:
            return 0.0
        return float(sound_speed) * (1.0 - float(observed_freq_hz)
                                     / float(carrier_freq_hz))

    # -- multipath rejection -----------------------------------------------
    @staticmethod
    def multipath_filter(
        ranges: np.ndarray,
        window: int = 5,
        sigma_threshold: float = 2.0,
    ) -> np.ndarray:
        """Median filter + outlier rejection (>sigma_threshold * std)."""
        arr = np.asarray(ranges, dtype=float).reshape(-1)
        if arr.size == 0:
            return arr
        w = max(int(window), 1)
        out = arr.copy()
        for i in range(arr.size):
            lo = max(0, i - w // 2)
            hi = min(arr.size, i + w // 2 + 1)
            window_vals = arr[lo:hi]
            med = float(np.median(window_vals))
            std = float(np.std(window_vals)) + 1e-9
            if abs(arr[i] - med) > sigma_threshold * std:
                out[i] = med
        return out


# ============================================================================
# R8 — Pressure-Depth Navigation (UNESCO 1983 + Mackenzie sound speed)
# ============================================================================

class PressureDepthNav:
    """Pressure-derived depth, Mackenzie sound speed, vertical velocity."""

    def __init__(self):
        import numpy as _np
        self._np = _np

    def depth_from_pressure(self, pressure_dbar: float,
                            latitude_deg: float) -> float:
        """UNESCO 1983 depth from pressure (decibars) with latitude correction.

        d = (9.72659e2·p − 2.512e-1·p² + 2.279e-4·p³ − 1.82e-7·p⁴)
            ÷ (9.780318·(1 + 5.2788e-3·sin²φ) + 2.36e-5·p)
        where p = pressure_dbar / 10  (decibars→bar via /10 per spec).
        """
        p = float(pressure_dbar) / 10.0
        sin2 = math.sin(math.radians(float(latitude_deg))) ** 2
        num = (9.72659e2 * p
               - 2.512e-1 * p * p
               + 2.279e-4 * p ** 3
               - 1.82e-7 * p ** 4)
        denom = 9.780318 * (1.0 + 5.2788e-3 * sin2) + 2.36e-5 * p
        return float(num / denom)

    def sound_speed_mackenzie(self, temp_c: float, salinity_ppt: float,
                              depth_m: float) -> float:
        """Mackenzie 1981 sound-speed equation in m/s."""
        T = float(temp_c)
        S = float(salinity_ppt)
        D = float(depth_m)
        c = (1448.96
             + 4.591 * T
             - 5.304e-2 * T * T
             + 2.374e-4 * T ** 3
             + 1.340 * (S - 35.0)
             + 1.630e-2 * D
             + 1.675e-7 * D * D
             - 1.025e-2 * T * (S - 35.0)
             - 7.139e-13 * T * D ** 3)
        return float(c)

    def vertical_velocity(self, depth_series, dt: float):
        """Estimate vertical velocity via centred finite differences."""
        np = self._np
        arr = np.asarray(depth_series, dtype=float).reshape(-1)
        if arr.size == 0:
            return arr
        return np.gradient(arr, float(dt))


# ============================================================================
# R10 — Underwater DVL (Doppler Velocity Log) Navigator
# ============================================================================

class UnderwaterDVLNavigator:
    """4-beam Janus-configuration DVL dead-reckoning.

    Beams 1–4 oriented at azimuths 0°, 90°, 180°, 270° from heading and
    inclined ``beam_angle_deg`` from vertical (default 30°).
    """

    def __init__(self, beam_angle_deg: float = 30.0):
        import numpy as _np
        self._np = _np
        self.beam_angle_deg = float(beam_angle_deg)

    def compute_velocity_from_beams(self, beam_velocities,
                                    beam_angles_deg=None):
        """Recover body-frame (vx, vy, vz) from Janus beam radial velocities.

        Janus geometry inversion:
            vx = (b1 - b3) / (2·sin θ)
            vy = (b2 - b4) / (2·sin θ)
            vz = (b1 + b2 + b3 + b4) / (4·cos θ)
        """
        np = self._np
        b = np.asarray(beam_velocities, dtype=float).reshape(-1)
        if b.size < 4:
            return np.zeros(3)
        theta = math.radians(float(beam_angles_deg)
                             if beam_angles_deg is not None
                             else self.beam_angle_deg)
        sin_t = max(math.sin(theta), 1e-9)
        cos_t = max(math.cos(theta), 1e-9)
        vx = (b[0] - b[2]) / (2.0 * sin_t)
        vy = (b[1] - b[3]) / (2.0 * sin_t)
        vz = (b[0] + b[1] + b[2] + b[3]) / (4.0 * cos_t)
        return np.array([vx, vy, vz])

    def integrate_position(self, vx: float, vy: float, vz: float,
                           heading_rad: float, dt: float):
        """Rotate body velocity into world frame and integrate by dt."""
        c = math.cos(float(heading_rad))
        s = math.sin(float(heading_rad))
        dx = (c * vx - s * vy) * float(dt)
        dy = (s * vx + c * vy) * float(dt)
        dz = float(vz) * float(dt)
        return (dx, dy, dz)

    def detect_bottom_lock(self, beam_velocities,
                           threshold: float = 20.0) -> bool:
        """Bottom-lock when every beam radial velocity stays below threshold."""
        np = self._np
        b = np.asarray(beam_velocities, dtype=float).reshape(-1)
        if b.size == 0:
            return False
        return bool(np.all(np.abs(b) < float(threshold)))


# ============================================================================
# R11 — Tidal Current Compensator (sinusoid fit + drift estimation)
# ============================================================================

class TidalCurrentCompensator:
    """Harmonic tidal-current model fit and compensation."""

    def __init__(self):
        import numpy as _np
        self._np = _np

    def fit_tidal_model(self, time_series, velocity_series):
        """Fit v(t) = A·sin(2π·t/T + φ) via grid search over T then linear LS.

        Returns (A, T, phi) — A in m/s, T in seconds, phi in radians.
        """
        np = self._np
        t = np.asarray(time_series, dtype=float).reshape(-1)
        v = np.asarray(velocity_series, dtype=float).reshape(-1)
        if t.size < 4:
            return (0.0, 1.0, 0.0)
        span = max(float(t.max() - t.min()), 1e-9)
        # Period candidates: a logarithmic sweep around the typical tidal range
        candidates = np.linspace(span / 8.0, span * 2.0, 32)
        candidates = candidates[candidates > 1e-3]
        best = None
        for T in candidates:
            omega = 2.0 * math.pi / float(T)
            X = np.column_stack([np.sin(omega * t), np.cos(omega * t)])
            try:
                coeff, *_ = np.linalg.lstsq(X, v, rcond=None)
            except np.linalg.LinAlgError:
                continue
            v_hat = X @ coeff
            sse = float(np.sum((v - v_hat) ** 2))
            if best is None or sse < best[0]:
                best = (sse, float(T), coeff)
        if best is None:
            return (0.0, 1.0, 0.0)
        _, T_best, coeff = best
        a_sin, b_cos = float(coeff[0]), float(coeff[1])
        A = math.sqrt(a_sin * a_sin + b_cos * b_cos)
        phi = math.atan2(b_cos, a_sin)
        return (A, T_best, phi)

    def predict_current(self, t: float, A: float, T: float, phi: float):
        """Return tidal current as (vx, vy) (vx component used; vy = 0)."""
        omega = 2.0 * math.pi / max(float(T), 1e-9)
        v = float(A) * math.sin(omega * float(t) + float(phi))
        return (v, 0.0)

    def compensate(self, measured_vel, t: float, A: float, T: float,
                   phi: float):
        """Subtract predicted tidal current from a measured velocity vector."""
        np = self._np
        v_meas = np.asarray(measured_vel, dtype=float).reshape(-1)
        cx, cy = self.predict_current(t, A, T, phi)
        out = v_meas.copy()
        out[0] -= cx
        if v_meas.size > 1:
            out[1] -= cy
        return out

    def estimate_drift(self, positions, times):
        """Return mean (Δx, Δy) drift between consecutive samples."""
        np = self._np
        P = np.asarray(positions, dtype=float).reshape(-1, 2)
        t = np.asarray(times, dtype=float).reshape(-1)
        if P.shape[0] < 2:
            return np.zeros(2)
        dP = np.diff(P, axis=0)
        return np.mean(dP, axis=0)
