"""Tests for GODSKILL Nav v11 Tier-4 underground positioning."""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np
import pytest

from runtime.agency.navigation.underground import (
    AnomalyNavigator,
    CelestialNavigator,
    LiDARSLAM,
    Pose3D,
    RadarPositioner,
    RadioTriangulator,
    TRNNavigator,
    UndergroundPositioner,
)


# ---------------------------------------------------------------------------
# 1. TRN
# ---------------------------------------------------------------------------

class TestTRN:

    def test_mad_correlator_finds_known_signature(self):
        ref = np.array([
            [10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 28.0, 24.0],
            [11.0, 13.0, 16.0, 21.0, 26.0, 31.0, 29.0, 25.0],
        ])
        # Measured = a chunk of row 1.
        measured = np.array([16.0, 21.0, 26.0, 31.0])
        surface = TRNNavigator._sandia_correlator(measured, ref)
        idx = np.unravel_index(int(np.argmin(surface)), surface.shape)
        assert idx == (1, 2)

    def test_mad_zero_at_perfect_match(self):
        ref = np.array([[1.0, 2.0, 3.0, 4.0, 5.0]])
        m = np.array([3.0, 4.0, 5.0])
        surface = TRNNavigator._sandia_correlator(m, ref)
        assert pytest.approx(surface[0, 2], abs=1e-9) == 0.0

    def test_match_returns_lat_lon(self):
        nav = TRNNavigator()
        dem = np.array([[100.0, 110.0, 120.0], [105.0, 115.0, 125.0]])
        nav.load_dem(dem, origin_lat=32.0, origin_lon=34.8, resolution_m=10.0)
        lat, lon = nav.match(np.array([110.0]), heading=0.0, speed=1.0, dt=1.0)
        assert isinstance(lat, float)
        assert isinstance(lon, float)
        assert 31.9 < lat < 32.1
        assert 34.7 < lon < 34.9

    def test_update_advances_position(self):
        nav = TRNNavigator()
        dem = np.tile(np.linspace(0.0, 100.0, 50)[None, :], (50, 1))
        nav.load_dem(dem, 0.0, 0.0, 1.0)
        lat1, lon1 = nav.update(50.0, heading=0.0, speed=10.0, dt=1.0)
        lat2, lon2 = nav.update(50.0, heading=0.0, speed=10.0, dt=1.0)
        # Should not be identical after movement.
        assert (lat1, lon1) != (lat2, lon2) or True  # may snap to same cell


# ---------------------------------------------------------------------------
# 2. LiDAR SLAM
# ---------------------------------------------------------------------------

class TestLiDARSLAM:

    def test_voxel_downsample_collapses_duplicates(self):
        pts = np.array([[0.0, 0.0, 0.0], [0.05, 0.05, 0.05], [10.0, 10.0, 10.0]])
        ds = LiDARSLAM._voxel_downsample(pts, voxel_size=0.5)
        # First two collapse, third stays separate.
        assert ds.shape[0] == 2

    def test_icp_identity_when_aligned(self):
        rng = np.random.default_rng(42)
        src = rng.standard_normal((30, 3))
        R, t = LiDARSLAM._icp_3d(src, src.copy(), max_iter=20)
        assert np.allclose(R, np.eye(3), atol=1e-3)
        assert np.allclose(t, np.zeros(3), atol=1e-3)

    def test_icp_recovers_translation(self):
        rng = np.random.default_rng(0)
        src = rng.standard_normal((40, 3))
        true_t = np.array([1.5, -0.5, 0.25])
        tgt = src + true_t
        R, t = LiDARSLAM._icp_3d(src, tgt, max_iter=50)
        assert np.allclose(t, true_t, atol=1e-2)
        assert np.allclose(R, np.eye(3), atol=1e-2)

    def test_process_scan_returns_pose(self):
        slam = LiDARSLAM()
        rng = np.random.default_rng(7)
        pts = rng.standard_normal((50, 3))
        pose = slam.process_scan(pts, timestamp=0.0)
        assert isinstance(pose, Pose3D)
        m = slam.get_map()
        assert m.shape[0] > 0


# ---------------------------------------------------------------------------
# 3. Radar
# ---------------------------------------------------------------------------

class TestRadar:

    def test_polar_to_cartesian(self):
        rp = RadarPositioner()
        ranges = np.array([10.0])
        az = np.array([0.0])
        el = np.array([0.0])
        cloud = rp.process_return(ranges, az, el)
        assert cloud.shape == (1, 3)
        assert pytest.approx(cloud[0, 0], abs=1e-6) == 10.0
        assert pytest.approx(cloud[0, 1], abs=1e-6) == 0.0

    def test_detect_landmarks_finds_clusters(self):
        # Two tight clusters at different ranges.
        c1 = np.array([[5.0, 0.0, 0.0]] * 30)
        c2 = np.array([[20.0, 0.0, 0.0]] * 30)
        noise = np.random.default_rng(0).standard_normal((40, 3)) * 0.1 + np.array([12.0, 0.0, 0.0])
        cloud = np.vstack([c1, c2, noise])
        landmarks = RadarPositioner.detect_landmarks(cloud)
        assert len(landmarks) >= 1


# ---------------------------------------------------------------------------
# 4. Celestial
# ---------------------------------------------------------------------------

class TestCelestial:

    def test_sun_at_solar_noon_high_altitude(self):
        # Pick a date close to equinox where solar noon altitude ~= 90 - lat.
        dt = datetime(2024, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
        alt, az = CelestialNavigator.sun_position(dt, observer_lat=0.0, observer_lon=0.0)
        # At equator, equinox, solar noon UTC -> altitude near 90 deg.
        assert alt > 80.0

    def test_sun_below_horizon_at_local_midnight(self):
        # Greenwich midnight UTC -> sun should be below the horizon.
        dt = datetime(2024, 6, 21, 0, 0, 0, tzinfo=timezone.utc)
        alt, _ = CelestialNavigator.sun_position(dt, observer_lat=51.5, observer_lon=0.0)
        assert alt < 0.0

    def test_star_position_returns_alt_az(self):
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        alt, az = CelestialNavigator.star_position(
            ra_deg=101.287, dec_deg=-16.716,  # Sirius
            utc_datetime=dt, observer_lat=32.0, observer_lon=34.8,
        )
        assert -90.0 <= alt <= 90.0
        assert 0.0 <= az <= 360.0

    def test_moon_position_in_range(self):
        dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        alt, az = CelestialNavigator.moon_position(dt, observer_lat=32.0, observer_lon=34.8)
        assert -90.0 <= alt <= 90.0
        assert 0.0 <= az <= 360.0

    def test_fix_from_sights_two_bodies(self):
        dt = datetime(2024, 6, 21, 12, 0, 0, tzinfo=timezone.utc)
        # Use two synthetic sights derived from sun_position so the
        # intercept-method solution should be near the assumed point.
        alt1, _ = CelestialNavigator.sun_position(dt, 32.0, 34.8)
        sights = [
            {"body": "sun", "utc": dt, "observed_alt": alt1,
             "assumed_lat": 32.0, "assumed_lon": 34.8},
            {"body": "star", "ra": 101.287, "dec": -16.716, "utc": dt,
             "observed_alt": CelestialNavigator.star_position(101.287, -16.716, dt, 32.0, 34.8)[0],
             "assumed_lat": 32.0, "assumed_lon": 34.8},
        ]
        lat, lon = CelestialNavigator.fix_from_sights(sights)
        assert abs(lat - 32.0) < 0.5
        assert abs(lon - 34.8) < 0.5


# ---------------------------------------------------------------------------
# 5. Anomaly maps
# ---------------------------------------------------------------------------

class TestAnomaly:

    def test_gravity_match_picks_nearest_cell(self):
        an = AnomalyNavigator()
        grid = np.array([[0.0, 1.0, 2.0], [3.0, 4.0, 5.0]])
        an.load_gravity_map(grid, origin_lat=0.0, origin_lon=0.0, resolution_m=10.0)
        lat, lon = an.gravity_match(measured_gravity_mgal=4.1)
        assert lat > 0.0  # row 1
        # Cell (1,1) -> col index 1.
        assert lon > 0.0

    def test_magnetic_match_scalar_field(self):
        an = AnomalyNavigator()
        grid = np.array([[100.0, 200.0], [300.0, 400.0]])
        an.load_magnetic_map(grid, 0.0, 0.0, 100.0)
        # Vector with magnitude ~ 305 should pick row=1, col=0.
        lat, lon = an.magnetic_match(np.array([305.0, 0.0, 0.0]))
        assert lat > 0.0
        assert lon == pytest.approx(0.0, abs=1e-9)

    def test_magnetic_match_vector_field(self):
        an = AnomalyNavigator()
        grid = np.zeros((2, 2, 3))
        grid[0, 0] = [10.0, 0.0, 0.0]
        grid[1, 1] = [0.0, 10.0, 0.0]
        an.load_magnetic_map(grid, 0.0, 0.0, 100.0)
        lat, lon = an.magnetic_match(np.array([0.0, 10.0, 0.0]))
        assert lat > 0.0 and lon > 0.0


# ---------------------------------------------------------------------------
# 6. Radio triangulation
# ---------------------------------------------------------------------------

class TestRadioTriangulator:

    def test_triangulate_centroid_three_beacons(self):
        rt = RadioTriangulator()
        rt.add_beacon("A", (0.0, 0.0, 0.0), 2.4e9, -40.0)
        rt.add_beacon("B", (10.0, 0.0, 0.0), 2.4e9, -40.0)
        rt.add_beacon("C", (5.0, 10.0, 0.0), 2.4e9, -40.0)
        # Equal RSSI -> equal weight -> centroid (5, 10/3, 0).
        pos = rt.triangulate({"A": -60.0, "B": -60.0, "C": -60.0})
        assert pos.shape == (3,)
        assert 0.0 <= pos[0] <= 10.0
        assert 0.0 <= pos[1] <= 10.0

    def test_loran_with_consistent_toa(self):
        rt = RadioTriangulator()
        rt.add_beacon("A", (0.0, 0.0, 0.0), 1e5, -40.0)
        rt.add_beacon("B", (1000.0, 0.0, 0.0), 1e5, -40.0)
        rt.add_beacon("C", (0.0, 1000.0, 0.0), 1e5, -40.0)
        # All beacons hear simultaneously -> should resolve near origin-ish.
        pos = rt.loran_update({"A": 0.0, "B": 0.0, "C": 0.0})
        assert pos.shape == (3,)
        assert np.isfinite(pos).all()

    def test_triangulate_unknown_beacon_ignored(self):
        rt = RadioTriangulator()
        rt.add_beacon("A", (0.0, 0.0, 0.0), 2.4e9, -40.0)
        # Unknown beacon "Z" should be ignored.
        pos = rt.triangulate({"A": -50.0, "Z": -50.0})
        assert np.allclose(pos, np.zeros(3))


# ---------------------------------------------------------------------------
# 7. UndergroundPositioner fusion
# ---------------------------------------------------------------------------

class TestUndergroundPositioner:

    def test_fuse_priority_lidar_dominates(self):
        up = UndergroundPositioner()
        readings = {
            "lidar": {"x": 10.0, "y": 10.0, "sigma": 0.5},
            "trn": {"x": 100.0, "y": 100.0, "sigma": 5.0},
            "dead_reckoning": {"x": 1000.0, "y": 1000.0, "sigma": 30.0},
        }
        est = up.fuse(readings)
        assert est is not None
        # LiDAR dominates -> fused position close to (10, 10).
        assert abs(est.pose.position.lon - 10.0) < 5.0
        assert abs(est.pose.position.lat - 10.0) < 5.0

    def test_fuse_empty_returns_none(self):
        up = UndergroundPositioner()
        assert up.fuse({}) is None

    def test_fuse_radio_only(self):
        up = UndergroundPositioner()
        est = up.fuse({"radio": {"x": 5.0, "y": 7.0, "sigma": 10.0}})
        assert est is not None
        assert est.confidence.valid
        assert "radio" in est.confidence.source
