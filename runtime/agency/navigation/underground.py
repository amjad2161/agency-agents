"""GODSKILL Nav v11 — Tier 4: Underground / GNSS-Denied Navigation Engine.

Provides offline positioning when satellites are unavailable:
- Terrain-Referenced Navigation (TRN/TERCOM-style)
- LiDAR SLAM (ICP-3D + voxel grid mapping)
- Radar-based landmark positioning
- Celestial navigation (sun/moon/star, no external libs)
- Gravity / Magnetic anomaly matching
- Radio beacon triangulation (RSSI weighted centroid + Loran TDOA)
- Sensor fusion with priority ordering

Pure stdlib + numpy. All classes operate on offline map data.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple

import numpy as np

from .types import Confidence, Estimate, Position, Pose, Velocity


# ---------------------------------------------------------------------------
# Backward-compatible scaffold types (kept for existing callers / tests)
# ---------------------------------------------------------------------------

@dataclass
class OdometrySample:
    left_ticks: int
    right_ticks: int
    wheel_radius_m: float = 0.15
    track_width_m: float = 0.50
    heading_rad: Optional[float] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class LiDARScan:
    angles_rad: List[float]
    ranges_m: List[float]
    max_range_m: float = 30.0


@dataclass
class RadioBeacon:
    beacon_id: str
    x_m: float
    y_m: float
    z_m: float = 0.0
    rssi_dbm: float = -70.0
    range_m: Optional[float] = None
    frequency_hz: float = 2.4e9


@dataclass
class MagAnomalySample:
    total_field_nT: float
    gradient_nT_m: float
    x_m: Optional[float] = None
    y_m: Optional[float] = None


@dataclass(frozen=True)
class Pose3D:
    """Full 6-DoF pose. Translation in metres, rotation in radians."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


def _rssi_to_range(rssi: float, ref_dbm: float = -40.0, n: float = 2.5) -> float:
    return 10 ** ((ref_dbm - rssi) / (10 * n))


# ---------------------------------------------------------------------------
# 1. Terrain-Referenced Navigation (TERCOM / Sandia MAD correlator)
# ---------------------------------------------------------------------------

class TRNNavigator:
    """Map-matching against a Digital Elevation Model (DEM).

    Uses Mean Absolute Difference (MAD) terrain correlation in the spirit of
    Sandia / TERCOM systems used on cruise missiles.
    """

    def __init__(self) -> None:
        self._dem: Optional[np.ndarray] = None
        self._origin_lat: float = 0.0
        self._origin_lon: float = 0.0
        self._resolution_m: float = 1.0
        self._x: float = 0.0
        self._y: float = 0.0

    def load_dem(
        self,
        elevation_grid: np.ndarray,
        origin_lat: float,
        origin_lon: float,
        resolution_m: float,
    ) -> None:
        if elevation_grid.ndim != 2:
            raise ValueError("elevation_grid must be 2-D (rows=lat, cols=lon)")
        self._dem = np.asarray(elevation_grid, dtype=np.float64)
        self._origin_lat = float(origin_lat)
        self._origin_lon = float(origin_lon)
        self._resolution_m = float(resolution_m)

    @staticmethod
    def _sandia_correlator(measured: np.ndarray, reference: np.ndarray) -> np.ndarray:
        """Return a MAD correlation surface. Lower value = better match.

        `measured` is a 1-D track of N elevations. `reference` is a 2-D DEM.
        Output shape is (rows, cols - N + 1). Each cell is mean(|m - r|) along
        the slid window.
        """
        m = np.asarray(measured, dtype=np.float64).ravel()
        ref = np.asarray(reference, dtype=np.float64)
        n = m.size
        if n == 0 or ref.shape[1] < n:
            return np.full(ref.shape, np.inf)
        rows, cols = ref.shape
        out = np.full((rows, cols - n + 1), np.inf)
        for r in range(rows):
            row = ref[r]
            for c in range(cols - n + 1):
                window = row[c : c + n]
                out[r, c] = float(np.mean(np.abs(window - m)))
        return out

    def match(
        self,
        measured_elevations: np.ndarray,
        heading: float,
        speed: float,
        dt: float,
    ) -> Tuple[float, float]:
        """Find best (lat, lon) by sliding the measured track over the DEM."""
        if self._dem is None:
            raise RuntimeError("DEM not loaded")
        surface = self._sandia_correlator(measured_elevations, self._dem)
        idx = np.unravel_index(int(np.argmin(surface)), surface.shape)
        row, col = int(idx[0]), int(idx[1])
        # Convert grid index -> lat/lon. Approximate: 1 deg lat ~= 111_320 m.
        meters_per_deg_lat = 111_320.0
        meters_per_deg_lon = 111_320.0 * max(math.cos(math.radians(self._origin_lat)), 1e-6)
        lat = self._origin_lat + (row * self._resolution_m) / meters_per_deg_lat
        lon = self._origin_lon + (col * self._resolution_m) / meters_per_deg_lon
        # Cache as planar offset (m) for incremental update.
        self._x = col * self._resolution_m
        self._y = row * self._resolution_m
        return float(lat), float(lon)

    def update(
        self,
        measured_elevation: float,
        heading: float,
        speed: float,
        dt: float,
    ) -> Tuple[float, float]:
        """Single-sample incremental update.

        Advances dead-reckoned position by `speed * dt` along `heading`, then
        searches a small neighbourhood in the DEM for the best 1-cell match.
        """
        if self._dem is None:
            raise RuntimeError("DEM not loaded")
        self._x += speed * dt * math.cos(heading)
        self._y += speed * dt * math.sin(heading)
        rows, cols = self._dem.shape
        # Predicted DEM cell.
        cy = int(round(self._y / self._resolution_m))
        cx = int(round(self._x / self._resolution_m))
        cy = max(0, min(rows - 1, cy))
        cx = max(0, min(cols - 1, cx))
        # 3x3 search around the prediction.
        best = (cy, cx)
        best_diff = abs(self._dem[cy, cx] - measured_elevation)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < rows and 0 <= nx < cols:
                    diff = abs(self._dem[ny, nx] - measured_elevation)
                    if diff < best_diff:
                        best_diff = diff
                        best = (ny, nx)
        self._y = best[0] * self._resolution_m
        self._x = best[1] * self._resolution_m
        meters_per_deg_lat = 111_320.0
        meters_per_deg_lon = 111_320.0 * max(math.cos(math.radians(self._origin_lat)), 1e-6)
        lat = self._origin_lat + self._y / meters_per_deg_lat
        lon = self._origin_lon + self._x / meters_per_deg_lon
        return float(lat), float(lon)


# ---------------------------------------------------------------------------
# 2. LiDAR SLAM with point-to-point ICP and voxel grid mapping
# ---------------------------------------------------------------------------

class LiDARSLAM:
    """Incremental LiDAR SLAM. ICP scan-to-map alignment + voxel map."""

    def __init__(self, voxel_size: float = 0.1) -> None:
        self._voxel_size = float(voxel_size)
        self._map_voxels: Dict[Tuple[int, int, int], np.ndarray] = {}
        self._pose = Pose3D()
        self._last_points: Optional[np.ndarray] = None

    @staticmethod
    def _voxel_downsample(points: np.ndarray, voxel_size: float = 0.1) -> np.ndarray:
        """Average points falling in the same voxel."""
        pts = np.asarray(points, dtype=np.float64)
        if pts.size == 0:
            return pts.reshape(0, 3)
        if pts.ndim != 2 or pts.shape[1] != 3:
            raise ValueError("points must be (N,3)")
        keys = np.floor(pts / voxel_size).astype(np.int64)
        # Hash voxel keys.
        buckets: Dict[Tuple[int, int, int], List[np.ndarray]] = {}
        for p, k in zip(pts, keys):
            tk = (int(k[0]), int(k[1]), int(k[2]))
            buckets.setdefault(tk, []).append(p)
        return np.array([np.mean(v, axis=0) for v in buckets.values()])

    @staticmethod
    def _icp_3d(
        source: np.ndarray,
        target: np.ndarray,
        max_iter: int = 50,
        tolerance: float = 1e-4,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Point-to-point ICP with SVD alignment. Returns (R, t)."""
        src = np.asarray(source, dtype=np.float64)
        tgt = np.asarray(target, dtype=np.float64)
        if src.size == 0 or tgt.size == 0:
            return np.eye(3), np.zeros(3)
        R = np.eye(3)
        t = np.zeros(3)
        prev_err = float("inf")
        cur = src.copy()
        for _ in range(max_iter):
            # Brute-force nearest neighbour (fine for small N).
            diffs = cur[:, None, :] - tgt[None, :, :]
            dists = np.linalg.norm(diffs, axis=2)
            nn_idx = np.argmin(dists, axis=1)
            nn = tgt[nn_idx]
            # Centroids.
            mu_s = cur.mean(axis=0)
            mu_t = nn.mean(axis=0)
            S = (cur - mu_s).T @ (nn - mu_t)
            U, _, Vt = np.linalg.svd(S)
            R_step = Vt.T @ U.T
            if np.linalg.det(R_step) < 0:
                Vt[-1, :] *= -1
                R_step = Vt.T @ U.T
            t_step = mu_t - R_step @ mu_s
            cur = (R_step @ cur.T).T + t_step
            R = R_step @ R
            t = R_step @ t + t_step
            err = float(np.mean(np.linalg.norm(cur - nn, axis=1)))
            if abs(prev_err - err) < tolerance:
                break
            prev_err = err
        return R, t

    def _update_map(self, points_global: np.ndarray) -> None:
        if points_global.size == 0:
            return
        ds = self._voxel_downsample(points_global, self._voxel_size)
        for p in ds:
            k = (
                int(math.floor(p[0] / self._voxel_size)),
                int(math.floor(p[1] / self._voxel_size)),
                int(math.floor(p[2] / self._voxel_size)),
            )
            self._map_voxels[k] = p

    def get_map(self) -> np.ndarray:
        if not self._map_voxels:
            return np.zeros((0, 3))
        return np.array(list(self._map_voxels.values()))

    def process_scan(self, points: np.ndarray, timestamp: float) -> Pose3D:
        pts = np.asarray(points, dtype=np.float64)
        if pts.size == 0:
            return self._pose
        ds = self._voxel_downsample(pts, self._voxel_size)
        target = self.get_map()
        if target.shape[0] == 0:
            # First scan — set as map.
            self._update_map(ds)
            self._last_points = ds
            return self._pose
        R, t = self._icp_3d(ds, target)
        # Update pose.
        new_x = self._pose.x + float(t[0])
        new_y = self._pose.y + float(t[1])
        new_z = self._pose.z + float(t[2])
        # Yaw from R (small-angle approximation around Z).
        new_yaw = self._pose.yaw + math.atan2(R[1, 0], R[0, 0])
        self._pose = Pose3D(
            x=new_x, y=new_y, z=new_z,
            roll=self._pose.roll, pitch=self._pose.pitch, yaw=new_yaw,
        )
        # Transform the new scan into global frame and append to map.
        global_pts = (R @ ds.T).T + t
        self._update_map(global_pts)
        self._last_points = ds
        return self._pose


# ---------------------------------------------------------------------------
# 3. Radar positioning (CFAR-like landmark detection)
# ---------------------------------------------------------------------------

class RadarPositioner:
    """Radar-based positioning. Polar -> Cartesian, CFAR peaks, map match."""

    def __init__(self) -> None:
        self._point_cloud: Optional[np.ndarray] = None

    def process_return(
        self,
        ranges: np.ndarray,
        azimuths: np.ndarray,
        elevations: np.ndarray,
    ) -> np.ndarray:
        r = np.asarray(ranges, dtype=np.float64)
        a = np.asarray(azimuths, dtype=np.float64)
        e = np.asarray(elevations, dtype=np.float64)
        if not (r.shape == a.shape == e.shape):
            raise ValueError("ranges/azimuths/elevations must have equal shape")
        x = r * np.cos(e) * np.cos(a)
        y = r * np.cos(e) * np.sin(a)
        z = r * np.sin(e)
        cloud = np.stack([x, y, z], axis=-1)
        self._point_cloud = cloud
        return cloud

    @staticmethod
    def detect_landmarks(point_cloud: np.ndarray) -> List[dict]:
        """Cell-Averaging CFAR-like peak detection on radial intensity.

        Treat point density along radius as the "signal" and pick local maxima
        whose magnitude exceeds the rolling mean by a threshold factor.
        """
        pts = np.asarray(point_cloud, dtype=np.float64)
        if pts.size == 0:
            return []
        if pts.ndim != 2 or pts.shape[1] != 3:
            raise ValueError("point_cloud must be (N,3)")
        radii = np.linalg.norm(pts, axis=1)
        # Histogram along radius.
        max_r = float(radii.max()) if radii.size else 0.0
        if max_r <= 0.0:
            return []
        nbins = max(8, int(min(64, max_r)))
        hist, edges = np.histogram(radii, bins=nbins)
        bg = float(hist.mean()) + 1e-6
        threshold = 1.5 * bg
        landmarks: List[dict] = []
        for i in range(1, nbins - 1):
            if hist[i] >= threshold and hist[i] >= hist[i - 1] and hist[i] >= hist[i + 1]:
                lo, hi = edges[i], edges[i + 1]
                mask = (radii >= lo) & (radii < hi)
                if mask.any():
                    centroid = pts[mask].mean(axis=0)
                    landmarks.append(
                        {
                            "range_m": float(0.5 * (lo + hi)),
                            "count": int(hist[i]),
                            "centroid": centroid.tolist(),
                        }
                    )
        return landmarks

    @staticmethod
    def match_to_map(landmarks: List[dict], radar_map: List[dict]) -> Pose3D:
        """Greedy nearest-landmark association -> mean translation."""
        if not landmarks or not radar_map:
            return Pose3D()
        diffs: List[np.ndarray] = []
        for lm in landmarks:
            c = np.array(lm["centroid"], dtype=np.float64)
            best = None
            best_d = float("inf")
            for ref in radar_map:
                rc = np.array(ref["centroid"], dtype=np.float64)
                d = float(np.linalg.norm(c - rc))
                if d < best_d:
                    best_d = d
                    best = rc
            if best is not None:
                diffs.append(best - c)
        if not diffs:
            return Pose3D()
        t = np.mean(np.stack(diffs, axis=0), axis=0)
        return Pose3D(x=float(t[0]), y=float(t[1]), z=float(t[2]))


# ---------------------------------------------------------------------------
# 4. Celestial Navigation (Spencer's formula, no external astronomy libs)
# ---------------------------------------------------------------------------

def _julian_day(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    y, m, d = dt.year, dt.month, dt.day
    if m <= 2:
        y -= 1
        m += 12
    A = y // 100
    B = 2 - A + A // 4
    jd = (
        math.floor(365.25 * (y + 4716))
        + math.floor(30.6001 * (m + 1))
        + d + B - 1524.5
    )
    frac = (dt.hour + dt.minute / 60.0 + (dt.second + dt.microsecond / 1e6) / 3600.0) / 24.0
    return jd + frac


def _gmst_hours(jd: float) -> float:
    """Greenwich Mean Sidereal Time in hours (0..24)."""
    T = (jd - 2451545.0) / 36525.0
    gmst_deg = (
        280.46061837
        + 360.98564736629 * (jd - 2451545.0)
        + 0.000387933 * T * T
        - (T ** 3) / 38710000.0
    )
    gmst_deg = gmst_deg % 360.0
    return gmst_deg / 15.0


class CelestialNavigator:
    """Sun, moon and star positioning. Pure math; no astronomy libraries."""

    @staticmethod
    def sun_position(
        utc_datetime: datetime,
        observer_lat: float,
        observer_lon: float,
    ) -> Tuple[float, float]:
        """Return (altitude_deg, azimuth_deg) using Spencer's formula."""
        dt = utc_datetime if utc_datetime.tzinfo else utc_datetime.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        N = dt.timetuple().tm_yday
        hour = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
        gamma = (2.0 * math.pi / 365.0) * (N - 1 + (hour - 12) / 24.0)
        # Equation of time (minutes).
        eot = 229.18 * (
            0.000075
            + 0.001868 * math.cos(gamma)
            - 0.032077 * math.sin(gamma)
            - 0.014615 * math.cos(2 * gamma)
            - 0.040849 * math.sin(2 * gamma)
        )
        # Declination (radians).
        decl = (
            0.006918
            - 0.399912 * math.cos(gamma)
            + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma)
            + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma)
            + 0.00148 * math.sin(3 * gamma)
        )
        # True solar time in minutes.
        time_offset = eot + 4.0 * observer_lon  # observer longitude in deg E
        tst = hour * 60.0 + dt.minute * 0 + dt.second * 0 + time_offset
        # Hour angle in degrees.
        ha = (tst / 4.0) - 180.0
        ha_rad = math.radians(ha)
        lat_rad = math.radians(observer_lat)
        sin_alt = (
            math.sin(lat_rad) * math.sin(decl)
            + math.cos(lat_rad) * math.cos(decl) * math.cos(ha_rad)
        )
        sin_alt = max(-1.0, min(1.0, sin_alt))
        alt = math.asin(sin_alt)
        cos_az_num = math.sin(decl) - math.sin(alt) * math.sin(lat_rad)
        cos_az_den = math.cos(alt) * math.cos(lat_rad)
        if abs(cos_az_den) < 1e-9:
            az = 0.0
        else:
            cos_az = max(-1.0, min(1.0, cos_az_num / cos_az_den))
            az = math.acos(cos_az)
            if math.sin(ha_rad) > 0:
                az = 2 * math.pi - az
        return math.degrees(alt), math.degrees(az)

    @staticmethod
    def moon_position(
        utc_datetime: datetime,
        observer_lat: float,
        observer_lon: float,
    ) -> Tuple[float, float]:
        """Simplified low-precision lunar theory -> (alt_deg, az_deg)."""
        jd = _julian_day(utc_datetime)
        d = jd - 2451545.0
        # Mean elements (degrees).
        L = (218.316 + 13.176396 * d) % 360.0  # mean longitude
        M = (134.963 + 13.064993 * d) % 360.0  # mean anomaly
        F = (93.272 + 13.229350 * d) % 360.0   # argument of latitude
        # Ecliptic longitude / latitude (degrees).
        lam = L + 6.289 * math.sin(math.radians(M))
        beta = 5.128 * math.sin(math.radians(F))
        eps = 23.439 - 0.0000004 * d  # obliquity
        lam_r = math.radians(lam)
        beta_r = math.radians(beta)
        eps_r = math.radians(eps)
        # Equatorial coords (RA, Dec).
        sin_dec = math.sin(beta_r) * math.cos(eps_r) + math.cos(beta_r) * math.sin(eps_r) * math.sin(lam_r)
        sin_dec = max(-1.0, min(1.0, sin_dec))
        dec = math.asin(sin_dec)
        ra = math.atan2(
            math.sin(lam_r) * math.cos(eps_r) - math.tan(beta_r) * math.sin(eps_r),
            math.cos(lam_r),
        )
        ra_deg = math.degrees(ra) % 360.0
        # Convert to alt/az via star_position math.
        return CelestialNavigator.star_position(
            ra_deg=ra_deg,
            dec_deg=math.degrees(dec),
            utc_datetime=utc_datetime,
            observer_lat=observer_lat,
            observer_lon=observer_lon,
        )

    @staticmethod
    def star_position(
        ra_deg: float,
        dec_deg: float,
        utc_datetime: datetime,
        observer_lat: float,
        observer_lon: float,
    ) -> Tuple[float, float]:
        """RA/Dec -> alt/az using local sidereal time and hour angle."""
        jd = _julian_day(utc_datetime)
        gmst = _gmst_hours(jd)
        lst_hours = (gmst + observer_lon / 15.0) % 24.0
        ha_deg = (lst_hours * 15.0 - ra_deg) % 360.0
        if ha_deg > 180.0:
            ha_deg -= 360.0
        ha = math.radians(ha_deg)
        lat = math.radians(observer_lat)
        dec = math.radians(dec_deg)
        sin_alt = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(ha)
        sin_alt = max(-1.0, min(1.0, sin_alt))
        alt = math.asin(sin_alt)
        cos_az_den = math.cos(alt) * math.cos(lat)
        if abs(cos_az_den) < 1e-9:
            az = 0.0
        else:
            cos_az = (math.sin(dec) - math.sin(alt) * math.sin(lat)) / cos_az_den
            cos_az = max(-1.0, min(1.0, cos_az))
            az = math.acos(cos_az)
            if math.sin(ha) > 0:
                az = 2 * math.pi - az
        return math.degrees(alt), math.degrees(az)

    @staticmethod
    def fix_from_sights(sights: List[dict]) -> Tuple[float, float]:
        """Two-or-more body celestial fix via the St-Hilaire intercept method.

        Each sight: {"body":"sun"|"moon"|"star", "ra":..., "dec":...,
                      "utc": datetime, "observed_alt": deg,
                      "assumed_lat": deg, "assumed_lon": deg}
        Returns improved (lat, lon).
        """
        if len(sights) < 2:
            raise ValueError("Need at least two sights for a fix")
        # Linearised LOPs around the assumed position.
        # Each LOP: dx*cos(Z) + dy*sin(Z) = intercept (nm)
        # where dy is dlat (nm), dx is dlon*cos(lat0) (nm), Z is azimuth.
        A_rows: List[List[float]] = []
        b_rows: List[float] = []
        lat0 = sights[0]["assumed_lat"]
        lon0 = sights[0]["assumed_lon"]
        for s in sights:
            body = s.get("body", "star")
            if body == "sun":
                Hc, Zn = CelestialNavigator.sun_position(s["utc"], lat0, lon0)
            elif body == "moon":
                Hc, Zn = CelestialNavigator.moon_position(s["utc"], lat0, lon0)
            else:
                Hc, Zn = CelestialNavigator.star_position(
                    s["ra"], s["dec"], s["utc"], lat0, lon0
                )
            Ho = float(s["observed_alt"])
            intercept_min = (Ho - Hc) * 60.0  # arcmin -> nautical miles (1' lat = 1 nm)
            Z = math.radians(Zn)
            # Row for [d_lat_nm, d_lon_nm_eastward]
            A_rows.append([math.cos(Z), math.sin(Z)])
            b_rows.append(intercept_min)
        A = np.asarray(A_rows, dtype=np.float64)
        b = np.asarray(b_rows, dtype=np.float64)
        sol, *_ = np.linalg.lstsq(A, b, rcond=None)
        d_lat_nm, d_lon_nm = float(sol[0]), float(sol[1])
        new_lat = lat0 + d_lat_nm / 60.0
        new_lon = lon0 + d_lon_nm / (60.0 * max(math.cos(math.radians(lat0)), 1e-6))
        return new_lat, new_lon


# ---------------------------------------------------------------------------
# 5. Gravity / Magnetic anomaly navigation
# ---------------------------------------------------------------------------

class AnomalyNavigator:
    """Match measured gravity / magnetic anomaly to a stored map."""

    def __init__(self) -> None:
        self._g_map: Optional[np.ndarray] = None
        self._g_origin: Tuple[float, float] = (0.0, 0.0)
        self._g_res: float = 1.0
        self._m_map: Optional[np.ndarray] = None  # (rows, cols, 3) for vector
        self._m_origin: Tuple[float, float] = (0.0, 0.0)
        self._m_res: float = 1.0

    def load_gravity_map(
        self,
        anomaly_grid: np.ndarray,
        origin_lat: float,
        origin_lon: float,
        resolution_m: float,
    ) -> None:
        g = np.asarray(anomaly_grid, dtype=np.float64)
        if g.ndim != 2:
            raise ValueError("gravity map must be 2-D")
        self._g_map = g
        self._g_origin = (float(origin_lat), float(origin_lon))
        self._g_res = float(resolution_m)

    def load_magnetic_map(
        self,
        mag_grid: np.ndarray,
        origin_lat: float,
        origin_lon: float,
        resolution_m: float,
    ) -> None:
        m = np.asarray(mag_grid, dtype=np.float64)
        if m.ndim not in (2, 3):
            raise ValueError("magnetic map must be 2-D scalar or 3-D vector")
        self._m_map = m
        self._m_origin = (float(origin_lat), float(origin_lon))
        self._m_res = float(resolution_m)

    def gravity_match(self, measured_gravity_mgal: float) -> Tuple[float, float]:
        if self._g_map is None:
            raise RuntimeError("gravity map not loaded")
        diffs = np.abs(self._g_map - measured_gravity_mgal)
        idx = np.unravel_index(int(np.argmin(diffs)), self._g_map.shape)
        row, col = int(idx[0]), int(idx[1])
        lat0, lon0 = self._g_origin
        meters_per_deg_lat = 111_320.0
        meters_per_deg_lon = 111_320.0 * max(math.cos(math.radians(lat0)), 1e-6)
        lat = lat0 + (row * self._g_res) / meters_per_deg_lat
        lon = lon0 + (col * self._g_res) / meters_per_deg_lon
        return float(lat), float(lon)

    def magnetic_match(self, measured_field: np.ndarray) -> Tuple[float, float]:
        if self._m_map is None:
            raise RuntimeError("magnetic map not loaded")
        v = np.asarray(measured_field, dtype=np.float64).ravel()
        m = self._m_map
        if m.ndim == 2:
            # Scalar field — compare magnitude.
            scalar = float(np.linalg.norm(v))
            diffs = np.abs(m - scalar)
            idx = np.unravel_index(int(np.argmin(diffs)), m.shape)
        else:
            # Vector field — minimise per-cell L2 distance.
            d = m - v[None, None, : m.shape[2]]
            diffs = np.linalg.norm(d, axis=2)
            idx = np.unravel_index(int(np.argmin(diffs)), diffs.shape)
        row, col = int(idx[0]), int(idx[1])
        lat0, lon0 = self._m_origin
        meters_per_deg_lat = 111_320.0
        meters_per_deg_lon = 111_320.0 * max(math.cos(math.radians(lat0)), 1e-6)
        lat = lat0 + (row * self._m_res) / meters_per_deg_lat
        lon = lon0 + (col * self._m_res) / meters_per_deg_lon
        return float(lat), float(lon)


# ---------------------------------------------------------------------------
# 6. Radio Beacon Triangulation (RSSI weighted centroid + Loran TDOA)
# ---------------------------------------------------------------------------

class RadioTriangulator:
    """Multi-mode radio positioning."""

    SPEED_OF_LIGHT = 299_792_458.0  # m/s

    def __init__(self) -> None:
        self._beacons: Dict[str, dict] = {}

    def add_beacon(
        self,
        id: str,
        position_xyz: Tuple[float, float, float],
        frequency_hz: float,
        signal_strength_dbm: float,
    ) -> None:
        self._beacons[str(id)] = {
            "position": np.asarray(position_xyz, dtype=np.float64),
            "frequency": float(frequency_hz),
            "signal_dbm": float(signal_strength_dbm),
        }

    def triangulate(self, rssi_readings: Dict[str, float]) -> np.ndarray:
        """Linear-power-weighted centroid + TDOA refinement.

        rssi_readings maps beacon id -> RSSI (dBm).
        Returns 3-vector position estimate.
        """
        if not rssi_readings or not self._beacons:
            return np.zeros(3)
        positions: List[np.ndarray] = []
        weights: List[float] = []
        for bid, rssi in rssi_readings.items():
            ref = self._beacons.get(bid)
            if ref is None:
                continue
            positions.append(ref["position"])
            # Linear power from dBm; clamp to avoid extreme floats.
            w = 10.0 ** (max(-150.0, float(rssi)) / 10.0)
            weights.append(w)
        if not positions:
            return np.zeros(3)
        P = np.stack(positions, axis=0)
        w = np.asarray(weights, dtype=np.float64)
        centroid = (P * w[:, None]).sum(axis=0) / w.sum()

        # TDOA-style refinement: estimate range from RSSI, do least-squares
        # on linearised range equations relative to first beacon.
        if len(positions) >= 3:
            ranges = np.array(
                [_rssi_to_range(rssi_readings[bid]) for bid in rssi_readings if bid in self._beacons],
                dtype=np.float64,
            )
            p0 = P[0]
            r0 = ranges[0]
            A_rows: List[np.ndarray] = []
            b_rows: List[float] = []
            for i in range(1, len(P)):
                pi = P[i]
                ri = ranges[i]
                A_rows.append(2.0 * (pi - p0))
                b_rows.append(
                    float(r0 ** 2 - ri ** 2 + np.dot(pi, pi) - np.dot(p0, p0))
                )
            if A_rows:
                A = np.stack(A_rows, axis=0)
                b = np.asarray(b_rows, dtype=np.float64)
                try:
                    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
                    if np.all(np.isfinite(sol)):
                        # Blend with centroid for stability.
                        return 0.5 * (centroid + sol)
                except np.linalg.LinAlgError:
                    pass
        return centroid

    def loran_update(self, toa_readings: Dict[str, float]) -> np.ndarray:
        """Hyperbolic positioning from Time-Of-Arrival differences.

        toa_readings maps beacon id -> arrival time (seconds, common clock).
        Uses pairs against a reference (first) beacon.
        """
        if len(toa_readings) < 3 or not self._beacons:
            return np.zeros(3)
        ids = [b for b in toa_readings if b in self._beacons]
        if len(ids) < 3:
            return np.zeros(3)
        ref_id = ids[0]
        ref_pos = self._beacons[ref_id]["position"]
        ref_t = float(toa_readings[ref_id])
        c = self.SPEED_OF_LIGHT
        A_rows: List[np.ndarray] = []
        b_rows: List[float] = []
        for bid in ids[1:]:
            pi = self._beacons[bid]["position"]
            ti = float(toa_readings[bid])
            d = c * (ti - ref_t)  # range difference (m)
            # Hyperbolic linearisation: 2*(pi-p0)·x = |pi|^2 - |p0|^2 - d^2 - 2*d*r0
            # We solve for x assuming small range r0; use simple least-squares form
            # 2*(pi-p0)·x = |pi|^2 - |p0|^2 - d^2.
            A_rows.append(2.0 * (pi - ref_pos))
            b_rows.append(
                float(np.dot(pi, pi) - np.dot(ref_pos, ref_pos) - d ** 2)
            )
        A = np.stack(A_rows, axis=0)
        b = np.asarray(b_rows, dtype=np.float64)
        try:
            sol, *_ = np.linalg.lstsq(A, b, rcond=None)
            if np.all(np.isfinite(sol)):
                return sol.astype(np.float64)
        except np.linalg.LinAlgError:
            pass
        return np.zeros(3)


# ---------------------------------------------------------------------------
# 7. Underground Positioner — sensor fusion with priority ordering
# ---------------------------------------------------------------------------

# Priority: lower number = higher priority.
_SOURCE_PRIORITY: Dict[str, int] = {
    "lidar": 1,
    "trn": 2,
    "celestial": 3,
    "magnetic": 4,
    "gravity": 4,
    "radio": 5,
    "dead_reckoning": 6,
}

# Heuristic baseline accuracies (1-σ horizontal metres).
_SOURCE_SIGMA: Dict[str, float] = {
    "lidar": 0.5,
    "trn": 5.0,
    "celestial": 200.0,
    "magnetic": 50.0,
    "gravity": 50.0,
    "radio": 10.0,
    "dead_reckoning": 30.0,
}


class UndergroundPositioner:
    """Top-level fuser combining all Tier-4 sources by priority."""

    def __init__(self) -> None:
        self.trn = TRNNavigator()
        self.lidar = LiDARSLAM()
        self.radar = RadarPositioner()
        self.celestial = CelestialNavigator()
        self.anomaly = AnomalyNavigator()
        self.radio = RadioTriangulator()

    @staticmethod
    def _priority(source: str) -> int:
        return _SOURCE_PRIORITY.get(source, 99)

    @staticmethod
    def _sigma(source: str) -> float:
        return _SOURCE_SIGMA.get(source, 100.0)

    def fuse(self, readings: Dict[str, dict]) -> Optional[Estimate]:
        """Fuse heterogeneous Tier-4 readings.

        readings: source -> {"x": float, "y": float, "z": float (opt),
                              "sigma": float (opt)}
        Priority: lidar > trn > celestial > magnetic > radio > dead_reckoning.
        """
        if not readings:
            return None
        # Sort by priority.
        ordered = sorted(readings.items(), key=lambda kv: self._priority(kv[0]))
        # Inverse-variance weighted mean of all available, but the top-priority
        # source dominates by getting an additional weight boost.
        xs: List[float] = []
        ys: List[float] = []
        zs: List[float] = []
        ws: List[float] = []
        for src, r in ordered:
            sigma = float(r.get("sigma", self._sigma(src)))
            sigma = max(sigma, 1e-3)
            w = 1.0 / (sigma ** 2)
            if src == ordered[0][0]:
                w *= 4.0  # priority boost
            xs.append(float(r.get("x", 0.0)))
            ys.append(float(r.get("y", 0.0)))
            zs.append(float(r.get("z", 0.0)))
            ws.append(w)
        W = sum(ws)
        if W <= 0:
            return None
        x = sum(a * b for a, b in zip(xs, ws)) / W
        y = sum(a * b for a, b in zip(ys, ws)) / W
        z = sum(a * b for a, b in zip(zs, ws)) / W
        h_acc = math.sqrt(1.0 / W)
        primary = ordered[0][0]
        return Estimate(
            pose=Pose(position=Position(lat=y, lon=x, alt=z)),
            velocity=Velocity(),
            confidence=Confidence(
                horizontal_m=h_acc, vertical_m=max(h_acc, 2.0),
                valid=True, source=f"underground-{primary}",
            ),
            source="underground",
            raw={"primary": primary, "fused": [s for s, _ in ordered]},
        )


# ---------------------------------------------------------------------------
# Backward-compatible high-level engine (kept for existing smoke tests)
# ---------------------------------------------------------------------------

class UndergroundEngine:
    """Tunnel/mine/subway navigation without GNSS."""

    TICKS_PER_REV: float = 1024.0

    def __init__(self) -> None:
        self._x = 0.0
        self._y = 0.0
        self._heading = 0.0
        self._h_acc = float("inf")
        self._prev_ticks_l = 0
        self._prev_ticks_r = 0
        self._beacons: Dict[str, RadioBeacon] = {}
        self._mag_grid: List[MagAnomalySample] = []
        self._reference_scan: Optional[LiDARScan] = None
        self.positioner = UndergroundPositioner()

    def add_beacon(self, beacon: RadioBeacon) -> None:
        self._beacons[beacon.beacon_id] = beacon
        self.positioner.radio.add_beacon(
            id=beacon.beacon_id,
            position_xyz=(beacon.x_m, beacon.y_m, beacon.z_m),
            frequency_hz=beacon.frequency_hz,
            signal_strength_dbm=beacon.rssi_dbm,
        )

    def update_odometry(self, sample: OdometrySample) -> Estimate:
        dl_ticks = sample.left_ticks - self._prev_ticks_l
        dr_ticks = sample.right_ticks - self._prev_ticks_r
        self._prev_ticks_l = sample.left_ticks
        self._prev_ticks_r = sample.right_ticks
        circ = 2 * math.pi * sample.wheel_radius_m
        dl = dl_ticks / self.TICKS_PER_REV * circ
        dr = dr_ticks / self.TICKS_PER_REV * circ
        dist = (dl + dr) / 2.0
        d_theta = (dr - dl) / sample.track_width_m
        if sample.heading_rad is not None:
            self._heading = sample.heading_rad
        else:
            self._heading += d_theta
        self._x += dist * math.cos(self._heading)
        self._y += dist * math.sin(self._heading)
        self._h_acc = min(self._h_acc + abs(dist) * 0.02, 30.0)
        return self._make_estimate("underground-odometry", self._h_acc)

    def update_lidar(self, scan: LiDARScan) -> Estimate:
        valid = [
            (a, r) for a, r in zip(scan.angles_rad, scan.ranges_m)
            if r < scan.max_range_m
        ]
        if not valid:
            return self._make_estimate("underground-lidar-no-valid", self._h_acc)
        if self._reference_scan is None:
            self._reference_scan = scan
            return self._make_estimate("underground-lidar-ref", self._h_acc)
        ref_valid = [
            (a, r)
            for a, r in zip(self._reference_scan.angles_rad, self._reference_scan.ranges_m)
            if r < self._reference_scan.max_range_m
        ]
        if not ref_valid:
            self._reference_scan = scan
            return self._make_estimate("underground-lidar-reset", self._h_acc)
        cx_new = sum(r * math.cos(a) for a, r in valid) / len(valid)
        cy_new = sum(r * math.sin(a) for a, r in valid) / len(valid)
        cx_ref = sum(r * math.cos(a) for a, r in ref_valid) / len(ref_valid)
        cy_ref = sum(r * math.sin(a) for a, r in ref_valid) / len(ref_valid)
        dx = cx_new - cx_ref
        dy = cy_new - cy_ref
        self._x -= dx * math.cos(self._heading) - dy * math.sin(self._heading)
        self._y -= dx * math.sin(self._heading) + dy * math.cos(self._heading)
        self._h_acc = 2.0
        self._reference_scan = scan
        return self._make_estimate("underground-lidar-icp", self._h_acc)

    def update_radio_beacons(self, observations: List[RadioBeacon]) -> Optional[Estimate]:
        known = [
            (o, self._beacons[o.beacon_id]) for o in observations
            if o.beacon_id in self._beacons
        ]
        if len(known) < 3:
            return None
        pts: List[Tuple[float, float, float]] = []
        ranges: List[float] = []
        for obs, ref in known:
            pts.append((ref.x_m, ref.y_m, ref.z_m))
            r = obs.range_m if obs.range_m is not None else _rssi_to_range(obs.rssi_dbm)
            ranges.append(r)
        from .indoor import _trilaterate
        result = _trilaterate(pts, ranges)
        if result:
            self._x, self._y = result
            self._h_acc = 3.0
            return self._make_estimate("underground-radio", self._h_acc)
        return None

    def update_mag_anomaly(self, sample: MagAnomalySample) -> Optional[Estimate]:
        self._mag_grid.append(sample)
        if sample.x_m is not None and sample.y_m is not None:
            self._x = sample.x_m
            self._y = sample.y_m
            self._h_acc = 5.0
            return self._make_estimate("underground-mag-anomaly", self._h_acc)
        return None

    def _make_estimate(self, src: str, h_acc: float) -> Estimate:
        return Estimate(
            pose=Pose(Position(self._x, self._y, 0.0)),
            confidence=Confidence(
                horizontal_m=h_acc, vertical_m=2.0, valid=True, source=src,
            ),
            source="underground",
            raw={"heading_deg": math.degrees(self._heading)},
        )

    def reset(self) -> None:
        self.__init__()


UndergroundEstimator = UndergroundEngine

__all__ = [
    "UndergroundEngine",
    "UndergroundEstimator",
    "UndergroundPositioner",
    "OdometrySample",
    "LiDARScan",
    "RadioBeacon",
    "MagAnomalySample",
    "Pose3D",
    "TRNNavigator",
    "LiDARSLAM",
    "RadarPositioner",
    "CelestialNavigator",
    "AnomalyNavigator",
    "RadioTriangulator",
]


# ---------------------------------------------------------------------------
# Magnetometer SLAM (Round 5)
# ---------------------------------------------------------------------------

import numpy as _np_mag


class MagnetometerSLAM:
    """Magnetic-anomaly fingerprint SLAM.

    Records (pos_2d, mag_vector) samples, builds a 2-D anomaly map by
    inverse-distance weighting (IDW) interpolation, and localises new
    readings via nearest-neighbour + small gradient-descent refinement.
    """

    def __init__(self) -> None:
        self._samples: list = []
        self._grid = None
        self._grid_origin = None
        self._grid_res = 1.0

    # -- recording ----------------------------------------------------------
    def record_measurement(self, pos_2d, mag_vector) -> None:
        p = _np_mag.asarray(pos_2d, dtype=float).reshape(2)
        m = _np_mag.asarray(mag_vector, dtype=float).reshape(-1)
        self._samples.append({"pos": p, "mag": m, "magnitude": float(_np_mag.linalg.norm(m))})

    # -- IDW interpolation --------------------------------------------------
    def build_anomaly_map(
        self,
        grid_resolution: float = 1.0,
        power: float = 2.0,
    ) -> _np_mag.ndarray:
        """Interpolate scalar magnitude onto a uniform grid via IDW."""
        if not self._samples:
            return _np_mag.zeros((0, 0))
        positions = _np_mag.array([s["pos"] for s in self._samples])
        values = _np_mag.array([s["magnitude"] for s in self._samples])
        x_min, y_min = positions.min(axis=0)
        x_max, y_max = positions.max(axis=0)
        # Pad to avoid degenerate single-cell grids.
        x_min -= grid_resolution; y_min -= grid_resolution
        x_max += grid_resolution; y_max += grid_resolution
        nx = max(2, int((x_max - x_min) / grid_resolution) + 1)
        ny = max(2, int((y_max - y_min) / grid_resolution) + 1)
        grid = _np_mag.zeros((ny, nx), dtype=float)
        for j in range(ny):
            for i in range(nx):
                x = x_min + i * grid_resolution
                y = y_min + j * grid_resolution
                d2 = (positions[:, 0] - x) ** 2 + (positions[:, 1] - y) ** 2
                if _np_mag.any(d2 < 1e-12):
                    grid[j, i] = float(values[_np_mag.argmin(d2)])
                    continue
                w = 1.0 / (_np_mag.sqrt(d2) ** power)
                grid[j, i] = float(_np_mag.sum(w * values) / _np_mag.sum(w))
        self._grid = grid
        self._grid_origin = _np_mag.array([x_min, y_min])
        self._grid_res = float(grid_resolution)
        return grid

    # -- localisation -------------------------------------------------------
    def localize(
        self,
        mag_vector,
        search_radius: float = 20.0,
    ) -> dict:
        """Find sample with closest magnitude within ``search_radius`` of the
        previous best, then refine via 4-neighbour gradient descent on the
        gridded map.
        """
        if not self._samples:
            return {"position": _np_mag.zeros(2), "score": 0.0,
                    "matched": False}
        target = float(_np_mag.linalg.norm(_np_mag.asarray(mag_vector,
                                                            dtype=float)))
        diffs = _np_mag.array([abs(s["magnitude"] - target)
                               for s in self._samples])
        best = int(_np_mag.argmin(diffs))
        pos = self._samples[best]["pos"].copy()
        # Optional gradient-descent refinement on the IDW grid.
        if self._grid is not None:
            for _ in range(20):
                ix = int((pos[0] - self._grid_origin[0]) / self._grid_res)
                iy = int((pos[1] - self._grid_origin[1]) / self._grid_res)
                if (ix < 1 or iy < 1
                        or ix >= self._grid.shape[1] - 1
                        or iy >= self._grid.shape[0] - 1):
                    break
                cur = self._grid[iy, ix]
                gx = (self._grid[iy, ix + 1] - self._grid[iy, ix - 1]) / (
                    2 * self._grid_res
                )
                gy = (self._grid[iy + 1, ix] - self._grid[iy - 1, ix]) / (
                    2 * self._grid_res
                )
                err = cur - target
                step = 0.1 * err * _np_mag.array([gx, gy])
                if float(_np_mag.linalg.norm(step)) < 1e-6:
                    break
                if float(_np_mag.linalg.norm(pos - self._samples[best]["pos"])) > search_radius:
                    break
                pos = pos - step
        score = 1.0 / (1.0 + float(diffs[best]))
        return {"position": pos, "score": score, "matched": True,
                "matched_sample": best}

    # -- online update ------------------------------------------------------
    def update_map(
        self,
        pos_2d,
        mag_vector,
        learning_rate: float = 0.1,
    ) -> None:
        """Add a new sample with running-mean blending if very close to an
        existing sample (within 1 m); otherwise just append.
        """
        p = _np_mag.asarray(pos_2d, dtype=float).reshape(2)
        m = _np_mag.asarray(mag_vector, dtype=float).reshape(-1)
        magnitude = float(_np_mag.linalg.norm(m))
        for s in self._samples:
            if float(_np_mag.linalg.norm(s["pos"] - p)) < 1.0:
                s["magnitude"] = (1 - learning_rate) * s["magnitude"] + learning_rate * magnitude
                s["mag"] = (1 - learning_rate) * s["mag"] + learning_rate * m
                return
        self.record_measurement(pos_2d, mag_vector)

    @property
    def n_samples(self) -> int:
        return len(self._samples)


# Add MagnetometerSLAM to __all__ if present.
try:
    __all__.append("MagnetometerSLAM")  # type: ignore[name-defined]
except Exception:
    pass


# ============================================================================
# R7 — Gravity-Gradiometry Navigation (submarine INS-style backup)
# ============================================================================

class GravityGradiometry:
    """Gravity gradient tensor navigation.

    Uses Somigliana's normal-gravity formula for the WGS-84 ellipsoid and
    finite-difference approximation of the gravity-gradient tensor (Eötvös
    units, 1 E = 1e-9 s⁻²).  Map matching finds the closest pre-surveyed
    tensor in a local map for position fixing.
    """

    # WGS-84 + Somigliana constants
    GAMMA_E = 9.7803253359          # equatorial normal gravity (m/s²)
    GAMMA_P = 9.8321849378          # polar normal gravity (m/s²)
    K_SOM   = 0.00193185265241      # Somigliana constant
    E2      = 6.69437999014e-3      # WGS-84 eccentricity²
    A_WGS   = 6378137.0             # equatorial radius (m)
    F_WGS   = 1.0 / 298.257223563   # flattening
    M_WGS   = 0.00344978650684      # m = ω²a²b/GM
    GM      = 3.986004418e14        # standard gravitational parameter (m³/s²)

    def __init__(self, fd_step_m: float = 100.0):
        import numpy as _np
        self._np = _np
        self.fd_step_m = float(fd_step_m)

    # --- Normal gravity (Somigliana) ----------------------------------------

    def normal_gravity(self, lat_rad: float, alt_m: float = 0.0) -> float:
        """Normal gravity on (or above) the WGS-84 ellipsoid.

        Returns the magnitude of g in m/s².
        """
        sin_phi = math.sin(float(lat_rad))
        sin2 = sin_phi * sin_phi
        denom = math.sqrt(max(1.0 - self.E2 * sin2, 1e-12))
        gamma0 = self.GAMMA_E * (1.0 + self.K_SOM * sin2) / denom

        # Free-air vertical gradient correction (Heiskanen-Moritz)
        h = float(alt_m)
        if abs(h) > 0:
            gamma_h = gamma0 * (
                1.0
                - 2.0 / self.A_WGS * (1.0 + self.F_WGS + self.M_WGS
                                       - 2.0 * self.F_WGS * sin2) * h
                + (3.0 / (self.A_WGS ** 2)) * h * h
            )
            return float(gamma_h)
        return float(gamma0)

    # --- Gravity gradient tensor --------------------------------------------

    def _g_vector_local(self, lat_rad: float, lon_rad: float, alt_m: float):
        """Return local gravity vector in local-level (E, N, Up) frame.

        Approximate: horizontal components small but non-zero from
        latitude-dependent gradient.
        """
        np = self._np
        g_mag = self.normal_gravity(lat_rad, alt_m)
        # Down component dominates; small horizontal component from latitudinal
        # gradient gives non-zero off-diagonal entries.
        d_lat = 1e-5
        g_north_grad = (self.normal_gravity(lat_rad + d_lat, alt_m)
                        - self.normal_gravity(lat_rad - d_lat, alt_m)) \
                       / (2.0 * d_lat * self.A_WGS)
        # ENU-frame gravity vector (mostly -Up):
        return np.array([0.0, g_north_grad, -g_mag])

    def compute_gravity_gradient_tensor(self, lat_rad: float,
                                        lon_rad: float,
                                        alt_m: float):
        """Finite-difference gravity gradient tensor in Eötvös units.

        Returns a 3×3 numpy array.  Trace is theoretically zero in vacuum
        (Laplace's equation).
        """
        np = self._np
        h = self.fd_step_m
        # Convert metres to lat/lon radians (approximate)
        d_lat = h / self.A_WGS
        d_lon = h / (self.A_WGS * max(math.cos(lat_rad), 1e-9))

        g_xp = self._g_vector_local(lat_rad, lon_rad + d_lon, alt_m)
        g_xn = self._g_vector_local(lat_rad, lon_rad - d_lon, alt_m)
        g_yp = self._g_vector_local(lat_rad + d_lat, lon_rad, alt_m)
        g_yn = self._g_vector_local(lat_rad - d_lat, lon_rad, alt_m)
        g_zp = self._g_vector_local(lat_rad, lon_rad, alt_m + h)
        g_zn = self._g_vector_local(lat_rad, lon_rad, alt_m - h)

        T = np.zeros((3, 3))
        T[:, 0] = (g_xp - g_xn) / (2.0 * h)
        T[:, 1] = (g_yp - g_yn) / (2.0 * h)
        T[:, 2] = (g_zp - g_zn) / (2.0 * h)
        # Symmetrise (Hessian is symmetric in gravity field)
        T = 0.5 * (T + T.T)
        # Enforce zero trace (Laplace) by removing mean diagonal
        trace_mean = np.trace(T) / 3.0
        T = T - trace_mean * np.eye(3)
        # Convert s⁻² to Eötvös (1 E = 1e-9 s⁻²)
        return T * 1.0e9

    # --- Map matching --------------------------------------------------------

    def match_gradient(self, observed_tensor, map_tensors, map_positions):
        """Return position from map closest to observed gradient tensor.

        Args:
            observed_tensor: (3,3) array
            map_tensors:     iterable of (3,3) arrays
            map_positions:   iterable of (lat, lon, alt) tuples

        Returns:
            best-matching position (tuple).
        """
        np = self._np
        obs = np.asarray(observed_tensor, dtype=float).reshape(3, 3)
        best_idx = 0
        best_score = float("inf")
        for i, T in enumerate(map_tensors):
            T_arr = np.asarray(T, dtype=float).reshape(3, 3)
            score = float(np.linalg.norm(T_arr - obs, ord="fro"))
            if score < best_score:
                best_score = score
                best_idx = i
        return tuple(map_positions[best_idx])


# ============================================================================
# R13 — Inertial Terrain Following (radar/laser altimeter + INS fusion)
# ============================================================================

class InertialTerrainFollowing:
    """Terrain-aided navigation using radar altimetry + barometric INS."""

    def __init__(self, tau: float = 2.0):
        import numpy as _np
        self._np = _np
        self.tau = float(tau)
        self.terrain_clearance = 0.0

    def update_terrain_alt(self, radar_alt: float, baro_alt: float,
                           dt: float) -> float:
        """Complementary blend of high-rate radar with low-rate baro."""
        radar = float(radar_alt)
        baro = float(baro_alt)
        dt = float(dt)
        alpha = self.tau / (self.tau + dt)
        self.terrain_clearance = alpha * radar + (1.0 - alpha) * baro
        return float(self.terrain_clearance)

    def terrain_contour_match(self, profile_observed, profile_map) -> float:
        """1-D normalised cross-correlation argmax shift (samples)."""
        np = self._np
        a = np.asarray(profile_observed, dtype=float).reshape(-1)
        b = np.asarray(profile_map, dtype=float).reshape(-1)
        if a.size == 0 or b.size == 0:
            return 0.0
        a = a - float(a.mean())
        b = b - float(b.mean())
        corr = np.correlate(b, a, mode="full")
        offset = int(np.argmax(corr)) - (a.size - 1)
        return float(offset)

    def update_position_from_terrain(self, current_pos, offset: float,
                                     heading: float):
        """Apply a contour-match offset along the heading direction."""
        np = self._np
        p = np.asarray(current_pos, dtype=float).reshape(2)
        d = float(offset)
        h = float(heading)
        return np.array([p[0] + d * math.cos(h),
                         p[1] + d * math.sin(h)])

    def slope_estimate(self, terrain_profile, dx: float):
        """Local slope (degrees) along the profile."""
        np = self._np
        a = np.asarray(terrain_profile, dtype=float).reshape(-1)
        if a.size < 2:
            return np.zeros_like(a)
        grad = np.gradient(a, float(dx))
        return np.degrees(np.arctan(grad))


# ============================================================================
# R15 — Terrain-Aided Navigation (DEM map matching)
# ============================================================================

class TerrainAidedNavigation:
    """DEM-based terrain-aided navigation with bilinear elevation lookup."""

    def __init__(self, dem, resolution: float = 10.0):
        import numpy as _np
        self._np = _np
        self.dem = _np.asarray(dem, dtype=float).copy()
        if self.dem.ndim != 2:
            raise ValueError("dem must be 2-D")
        self.resolution = float(resolution)
        self._pos = _np.array([self.dem.shape[0] // 2,
                               self.dem.shape[1] // 2], dtype=float)

    def elevation_at(self, row: float, col: float) -> float:
        np = self._np
        rows, cols = self.dem.shape
        r = max(0.0, min(rows - 1.0, float(row)))
        c = max(0.0, min(cols - 1.0, float(col)))
        r0 = int(math.floor(r)); r1 = min(r0 + 1, rows - 1)
        c0 = int(math.floor(c)); c1 = min(c0 + 1, cols - 1)
        dr = r - r0; dc = c - c0
        e00 = self.dem[r0, c0]; e01 = self.dem[r0, c1]
        e10 = self.dem[r1, c0]; e11 = self.dem[r1, c1]
        return float((1 - dr) * ((1 - dc) * e00 + dc * e01)
                     + dr * ((1 - dc) * e10 + dc * e11))

    def gradient_at(self, row: float, col: float):
        np = self._np
        e0 = self.elevation_at(row - 1.0, col)
        e1 = self.elevation_at(row + 1.0, col)
        e2 = self.elevation_at(row, col - 1.0)
        e3 = self.elevation_at(row, col + 1.0)
        return np.array([(e1 - e0) / 2.0, (e3 - e2) / 2.0])

    def match_profile(self, measured_elevations, heading_deg: float,
                      n_points: int = 5):
        """Search a small window around current pos for best correlation."""
        np = self._np
        meas = np.asarray(measured_elevations, dtype=float).reshape(-1)
        n = max(1, int(n_points))
        h = math.radians(float(heading_deg))
        dr_step = math.cos(h)
        dc_step = math.sin(h)
        rows, cols = self.dem.shape
        best_score = -np.inf
        best_pos = self._pos.copy()
        # Search a 5×5 cell window
        for dr_off in range(-2, 3):
            for dc_off in range(-2, 3):
                profile = []
                for k in range(n):
                    r = self._pos[0] + dr_off + k * dr_step
                    c = self._pos[1] + dc_off + k * dc_step
                    profile.append(self.elevation_at(r, c))
                p = np.array(profile)
                m = meas[:n] if meas.size >= n else np.pad(
                    meas, (0, n - meas.size), constant_values=meas[-1])
                pa = p - p.mean()
                ma = m - m.mean()
                score = float(np.sum(pa * ma))
                if score > best_score:
                    best_score = score
                    best_pos = np.array([self._pos[0] + dr_off,
                                         self._pos[1] + dc_off],
                                        dtype=float)
        return best_pos

    def update_position(self, inertial_pos, measured_alt: float):
        """Blend inertial position with elevation-error correction."""
        np = self._np
        ip = np.asarray(inertial_pos, dtype=float).reshape(2)
        dem_alt = self.elevation_at(ip[0], ip[1])
        err = float(measured_alt) - dem_alt
        grad = self.gradient_at(ip[0], ip[1])
        denom = float(grad @ grad) + 1e-9
        # Step toward truth along gradient direction (Newton-style)
        step = (err / denom) * grad
        corrected = ip + 0.1 * step
        self._pos = corrected
        return corrected

    @property
    def position(self):
        return self._pos.copy()
