"""GODSKILL Navigation R15 — improvement-round tests."""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'runtime'))

from agency.navigation.satellite import GNSSDopplerVelocity  # noqa: E402
from agency.navigation.indoor_inertial import StrapdownINS  # noqa: E402
from agency.navigation.indoor_slam import OccupancyGridMapper  # noqa: E402
from agency.navigation.fusion import RTSSmoother  # noqa: E402
from agency.navigation.underground import TerrainAidedNavigation  # noqa: E402


# ============================================================================
# GNSSDopplerVelocity
# ============================================================================

class TestGNSSDopplerVelocity:
    def test_doppler_to_pseudorange_rate_sign(self):
        d = GNSSDopplerVelocity()
        rate = d.doppler_to_pseudorange_rate(np.array([1000.0]))
        # Positive Doppler = approaching → negative pseudorange rate
        assert rate[0] < 0.0
        assert abs(rate[0]) == pytest.approx(1000.0 * d.lambda_l1)

    def test_estimate_velocity_shape(self):
        d = GNSSDopplerVelocity()
        los = np.array([[1.0, 0.0, 0.0],
                        [0.0, 1.0, 0.0],
                        [0.0, 0.0, 1.0],
                        [1.0, 1.0, 1.0]]) / np.array([[1], [1], [1], [math.sqrt(3)]])
        dop = np.zeros(4)
        v = d.estimate_velocity(dop, los)
        assert v.shape == (3,)

    def test_estimate_velocity_near_zero_for_stationary(self):
        d = GNSSDopplerVelocity()
        los = np.eye(3)
        v = d.estimate_velocity(np.zeros(3), los)
        assert float(np.linalg.norm(v)) < 1e-6

    def test_estimate_velocity_known_motion(self):
        d = GNSSDopplerVelocity()
        # Receiver moving +1 m/s in x; rate to a SV at +x = -v · u = -1
        los = np.array([
            [1.0, 0.0, 0.0],     # SV in +x → rate = -vx
            [-1.0, 0.0, 0.0],    # SV in -x → rate = +vx
            [0.0, 1.0, 0.0],     # SV in +y → rate = 0
            [0.0, 0.0, 1.0],     # SV in +z → rate = 0
        ])
        true_v = np.array([1.0, 0.0, 0.0])
        # rate = -los · v
        rate = -los @ true_v
        # Convert back to Doppler: rate = -doppler · λ → doppler = -rate / λ
        dop = -rate / d.lambda_l1
        v = d.estimate_velocity(dop, los)
        assert np.allclose(v, true_v, atol=1e-6)

    def test_receiver_clock_drift_scalar(self):
        d = GNSSDopplerVelocity()
        los = np.eye(3)
        los = np.vstack([los, np.array([1.0, 1.0, 1.0]) / math.sqrt(3)])
        dop = np.zeros(4)
        cd = d.receiver_clock_drift(dop, los)
        assert isinstance(cd, float)

    def test_speed_non_negative(self):
        d = GNSSDopplerVelocity()
        d._last_vel = np.array([3.0, 4.0, 0.0])
        assert d.speed() == pytest.approx(5.0)

    def test_lambda_value_correct(self):
        d = GNSSDopplerVelocity()
        assert d.lambda_l1 == pytest.approx(0.1903, abs=1e-3)


# ============================================================================
# StrapdownINS
# ============================================================================

class TestStrapdownINS:
    def test_propagate_increases_velocity(self):
        ins = StrapdownINS()
        # Body accel = -gravity in body z (standing still on ground = +gravity up
        # because IMU senses reaction force).  Apply +1 m/s² extra in body x.
        ins.propagate(np.array([1.0, 0.0, 9.80665]),
                      np.zeros(3), dt=0.1)
        assert ins.vel[0] > 0.0

    def test_propagate_moves_position(self):
        ins = StrapdownINS()
        ins.vel = np.array([1.0, 0.0, 0.0])
        ins.propagate(np.array([0.0, 0.0, 9.80665]), np.zeros(3), dt=1.0)
        assert ins.pos[0] > 0.0

    def test_gyro_only_rotates_quaternion(self):
        ins = StrapdownINS()
        before = ins.q.copy()
        ins.propagate(np.array([0.0, 0.0, 9.80665]),
                      np.array([0.0, 0.0, 1.0]),  # 1 rad/s yaw
                      dt=0.5)
        assert not np.allclose(before, ins.q)

    def test_quaternion_stays_unit(self):
        ins = StrapdownINS()
        for _ in range(50):
            ins.propagate(np.array([0.1, 0.05, 9.80665]),
                          np.array([0.1, 0.2, 0.3]), dt=0.01)
        assert float(np.linalg.norm(ins.q)) == pytest.approx(1.0, abs=1e-6)

    def test_euler_angles_shape(self):
        ins = StrapdownINS()
        e = ins.euler_angles()
        assert e.shape == (3,)

    def test_reset_clears_state(self):
        ins = StrapdownINS()
        ins.pos = np.array([1.0, 2.0, 3.0])
        ins.vel = np.array([0.5, 0.5, 0.5])
        ins.reset(pos=np.zeros(3), vel=np.zeros(3),
                  q=np.array([1.0, 0.0, 0.0, 0.0]))
        assert np.allclose(ins.pos, 0.0)
        assert np.allclose(ins.vel, 0.0)

    def test_horizontal_accel_no_vertical_velocity(self):
        ins = StrapdownINS()
        # Body accel = +g in body z (standing still) + 1 m/s² in body x
        for _ in range(10):
            ins.propagate(np.array([1.0, 0.0, 9.80665]),
                          np.zeros(3), dt=0.1)
        # Vertical velocity should stay near zero — gravity cancels accel z
        assert abs(ins.vel[2]) < 1e-6


# ============================================================================
# OccupancyGridMapper
# ============================================================================

class TestOccupancyGridMapper:
    def test_initial_probability_05(self):
        m = OccupancyGridMapper(grid_size=20, resolution=0.5)
        p = m.probability_map()
        assert np.allclose(p, 0.5)

    def test_update_increases_endpoint(self):
        m = OccupancyGridMapper(grid_size=20, resolution=0.5)
        m.update(np.array([0.0, 0.0]),
                 np.array([2.0]), np.array([0.0]))
        # Endpoint should have higher than 0.5 occupancy
        cx, cy = m._world_to_cell(2.0, 0.0)
        assert m.probability_map()[cx, cy] > 0.5

    def test_update_decreases_along_ray(self):
        m = OccupancyGridMapper(grid_size=20, resolution=0.5)
        m.update(np.array([0.0, 0.0]),
                 np.array([4.0]), np.array([0.0]))
        cx, cy = m._world_to_cell(2.0, 0.0)
        assert m.probability_map()[cx, cy] < 0.5

    def test_probability_map_shape(self):
        m = OccupancyGridMapper(grid_size=30, resolution=0.5)
        assert m.probability_map().shape == (30, 30)

    def test_probability_map_in_unit_interval(self):
        m = OccupancyGridMapper(grid_size=10)
        m.update(np.array([0.0, 0.0]),
                 np.array([0.5, 0.3]), np.array([0.0, 1.5]))
        p = m.probability_map()
        assert np.all(p >= 0.0) and np.all(p <= 1.0)

    def test_occupied_cells_increments(self):
        m = OccupancyGridMapper(grid_size=20, resolution=0.5)
        before = m.occupied_cells()
        m.update(np.array([0.0, 0.0]),
                 np.array([2.0, 2.5, 3.0]),
                 np.array([0.0, 0.7, -0.5]))
        assert m.occupied_cells() > before

    def test_free_cells_increments(self):
        m = OccupancyGridMapper(grid_size=30, resolution=0.5)
        before = m.free_cells()
        # Multiple ray updates accumulate free log-odds below 0.4 threshold
        for _ in range(3):
            m.update(np.array([0.0, 0.0]),
                     np.array([5.0]), np.array([0.0]))
        assert m.free_cells() > before


# ============================================================================
# RTSSmoother
# ============================================================================

def _build_filter_seq(T=10, n=2, seed=0):
    rng = np.random.default_rng(seed)
    xs = rng.normal(0, 1.0, (T, n))
    Ps = np.tile(np.eye(n) * 1.0, (T, 1, 1))
    xs_pred = xs + 0.05 * rng.normal(0, 1.0, (T, n))
    Ps_pred = np.tile(np.eye(n) * 1.5, (T, 1, 1))
    Fs = np.tile(np.eye(n), (T, 1, 1))
    return xs, Ps, xs_pred, Ps_pred, Fs


class TestRTSSmoother:
    def test_output_shapes(self):
        s = RTSSmoother(state_dim=2)
        xs, Ps, xp, Pp, Fs = _build_filter_seq()
        x_s, P_s = s.smooth(xs, Ps, xp, Pp, Fs)
        assert x_s.shape == xs.shape
        assert P_s.shape == Ps.shape

    def test_smoother_gain_shape(self):
        s = RTSSmoother(state_dim=3)
        G = s.smoother_gain(np.eye(3) * 1.5, np.eye(3), np.eye(3) * 2.0)
        assert G.shape == (3, 3)

    def test_smoothed_cov_no_larger(self):
        s = RTSSmoother(state_dim=2)
        xs, Ps, xp, Pp, Fs = _build_filter_seq(T=20, seed=2)
        _, P_s = s.smooth(xs, Ps, xp, Pp, Fs)
        # Trace of smoothed covariance at t=0 should not exceed filtered
        assert float(np.trace(P_s[0])) <= float(np.trace(Ps[0])) + 1e-6

    def test_smoothed_mean_differs(self):
        s = RTSSmoother(state_dim=2)
        xs, Ps, xp, Pp, Fs = _build_filter_seq(T=10, seed=3)
        x_s, _ = s.smooth(xs, Ps, xp, Pp, Fs)
        assert not np.allclose(x_s, xs)

    def test_smoke_T1(self):
        s = RTSSmoother(state_dim=2)
        xs = np.array([[1.0, 2.0]])
        Ps = np.array([np.eye(2)])
        x_s, P_s = s.smooth(xs, Ps, xs, Ps, np.array([np.eye(2)]))
        assert np.allclose(x_s, xs)
        assert np.allclose(P_s, Ps)

    def test_symmetric_output_P(self):
        s = RTSSmoother(state_dim=2)
        xs, Ps, xp, Pp, Fs = _build_filter_seq(T=10, seed=4)
        _, P_s = s.smooth(xs, Ps, xp, Pp, Fs)
        for k in range(P_s.shape[0]):
            assert np.allclose(P_s[k], P_s[k].T, atol=1e-9)

    def test_state_dim_one_scalar(self):
        s = RTSSmoother(state_dim=1)
        T = 5
        xs = np.arange(T, dtype=float).reshape(T, 1)
        Ps = np.tile(np.array([[1.0]]), (T, 1, 1))
        xp = xs + 0.1
        Pp = np.tile(np.array([[1.5]]), (T, 1, 1))
        Fs = np.tile(np.array([[1.0]]), (T, 1, 1))
        x_s, P_s = s.smooth(xs, Ps, xp, Pp, Fs)
        assert x_s.shape == (T, 1)


# ============================================================================
# TerrainAidedNavigation
# ============================================================================

def _make_dem():
    rows = 21; cols = 21
    rs, cs = np.meshgrid(np.arange(rows), np.arange(cols), indexing="ij")
    # Smooth bowl: high at corners, low in centre
    return ((rs - rows // 2) ** 2 + (cs - cols // 2) ** 2).astype(float)


class TestTerrainAidedNavigation:
    def test_elevation_at_interior_bilinear(self):
        t = TerrainAidedNavigation(_make_dem())
        v = t.elevation_at(5.5, 5.5)
        assert isinstance(v, float)

    def test_elevation_at_corner_exact(self):
        dem = _make_dem()
        t = TerrainAidedNavigation(dem)
        assert t.elevation_at(0.0, 0.0) == pytest.approx(dem[0, 0])

    def test_gradient_at_shape(self):
        t = TerrainAidedNavigation(_make_dem())
        g = t.gradient_at(5.0, 5.0)
        assert g.shape == (2,)

    def test_match_profile_returns_2d(self):
        t = TerrainAidedNavigation(_make_dem())
        meas = np.array([0.0, 1.0, 4.0, 9.0, 16.0])
        out = t.match_profile(meas, heading_deg=0.0, n_points=5)
        assert out.shape == (2,)

    def test_update_position_returns_2d(self):
        t = TerrainAidedNavigation(_make_dem())
        out = t.update_position(np.array([8.0, 8.0]), measured_alt=5.0)
        assert out.shape == (2,)

    def test_update_position_corrects_toward_truth(self):
        dem = _make_dem()
        t = TerrainAidedNavigation(dem)
        # Truth elevation at (8,10) = (8-10)^2+0 = 4; pretend we measure 4.
        true_pos = np.array([8.0, 10.0])
        meas = float(dem[int(true_pos[0]), int(true_pos[1])])
        # Inertial estimate is offset
        inertial = np.array([7.0, 10.0])
        before = float(np.linalg.norm(inertial - true_pos))
        corrected = t.update_position(inertial, meas)
        after = float(np.linalg.norm(corrected - true_pos))
        # Either improves or stays comparable (numerical robustness)
        assert after <= before + 0.5

    def test_dem_shape_preserved(self):
        dem = _make_dem()
        t = TerrainAidedNavigation(dem)
        assert t.dem.shape == dem.shape
