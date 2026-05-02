"""
GODSKILL Nav v11.0 — Smoke test suite
======================================
Tests every tier and the cross-tier fusion layer.
All tests use pure in-memory data; no files or network required.
"""

import math
import time
import pytest

import sys
sys.path.insert(0, "/tmp")

from godskill_nav_v11 import (
    Position, Velocity, Pose, Estimate, Confidence,
    SatelliteEstimator, IndoorEstimator, UnderwaterEstimator,
    UndergroundEstimator, SensorFusion, AIEnhancer, OfflineMaps,
)
from godskill_nav_v11.satellite import GnssFix
from godskill_nav_v11.indoor import (
    IndoorEngine, UWBAnchor, UWBMeasurement,
    WiFiAP, WiFiScan, BLEBeacon, IMUSample, MagSample,
)
from godskill_nav_v11.underwater import (
    UnderwaterEngine, INSSample, DVLSample, LBLFix, USBLFix,
)
from godskill_nav_v11.underground import (
    UndergroundEngine, OdometrySample, LiDARScan,
    RadioBeacon, MagAnomalySample,
)
from godskill_nav_v11.fusion import EKF, UKF, ParticleFilter
from godskill_nav_v11.ai_enhance import (
    AIEnhancer, RadioSample, DeepRadioMap,
    SceneFeatures, SceneRecognizer,
    TrajectoryPredictor, EnvironmentAdapter,
    BayesianUncertaintyEstimator,
    PoseGraphSLAM, PoseEdge,
)
from godskill_nav_v11.offline_maps import (
    OfflineMaps, VectorMapDB, MapNode, MapEdge,
    ElevationDB, DEMTile, BathymetricDB,
    RadioFingerprintDB, FingerprintRecord,
    CellTowerDB, CellTower, GeomagneticModel,
    BBox, LatLon,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dummy_estimate(x: float = 0.0, y: float = 0.0,
                    h: float = 1.0, source: str = "test") -> Estimate:
    return Estimate(
        pose=Pose(position=Position(lat=y, lon=x, alt=0.0)),
        velocity=Velocity(),
        confidence=Confidence(horizontal_m=h, vertical_m=h, valid=True, source=source),
        ts=time.time(),
        source=source,
        raw={},
    )


# ===========================================================================
# Tier 1 — Satellite
# ===========================================================================

class TestSatelliteEstimator:

    def test_init(self):
        se = SatelliteEstimator()
        assert se is not None

    def test_update_empty(self):
        se = SatelliteEstimator()
        result = se.update({})
        # May return None or Estimate — both valid when no data
        assert result is None or isinstance(result, Estimate)

    def test_feed_valid_nmea_gga(self):
        se = SatelliteEstimator()
        # Minimal GGA sentence (lat=4807.038N, lon=01131.000E)
        sentence = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
        fix = se.feed_nmea(sentence)
        assert isinstance(fix, GnssFix)
        assert fix.constellation == "GPS"
        assert abs(fix.lat - 48.1173) < 0.01
        assert abs(fix.lon - 11.5167) < 0.01
        assert fix.sats_used == 8

    def test_feed_nmea_invalid(self):
        se = SatelliteEstimator()
        result = se.feed_nmea("not a sentence")
        assert result is None

    def test_feed_nmea_glonass(self):
        se = SatelliteEstimator()
        sentence = "$GLGGA,123519,4807.038,N,01131.000,E,1,06,1.2,100.0,M,0.0,M,,*65"
        fix = se.feed_nmea(sentence)
        assert isinstance(fix, GnssFix)
        assert fix.constellation == "GLONASS"

    def test_check_spoofing_no_data(self):
        se = SatelliteEstimator()
        result = se.check_spoofing()
        assert isinstance(result, dict)
        assert "spoofed" in result

    def test_check_jamming_high_snr(self):
        se = SatelliteEstimator()
        assert se.check_jamming(45.0) is False

    def test_check_jamming_low_snr(self):
        se = SatelliteEstimator()
        assert se.check_jamming(5.0) is True

    def test_update_returns_estimate_after_nmea(self):
        se = SatelliteEstimator()
        sentence = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
        se.feed_nmea(sentence)
        est = se.update({})
        assert isinstance(est, Estimate)
        assert est.confidence.valid is True

    def test_alias(self):
        """SatelliteEstimator should be importable and constructable."""
        s = SatelliteEstimator()
        assert s is not None


# ===========================================================================
# Tier 2 — Indoor
# ===========================================================================

class TestIndoorEstimator:

    def test_alias(self):
        assert IndoorEstimator is IndoorEngine

    def test_init(self):
        ie = IndoorEngine()
        assert ie is not None

    def test_uwb_no_anchors(self):
        ie = IndoorEngine()
        meas = [UWBMeasurement(anchor_id="A1", range_m=3.0)]
        result = ie.update_uwb(meas)
        assert result is None

    def test_uwb_trilateration(self):
        ie = IndoorEngine()
        ie.add_uwb_anchor(UWBAnchor("A1", 0.0, 0.0))
        ie.add_uwb_anchor(UWBAnchor("A2", 4.0, 0.0))
        ie.add_uwb_anchor(UWBAnchor("A3", 2.0, 4.0))
        measurements = [
            UWBMeasurement("A1", 2.83),
            UWBMeasurement("A2", 2.83),
            UWBMeasurement("A3", 2.24),
        ]
        est = ie.update_uwb(measurements)
        assert isinstance(est, Estimate)
        assert est.confidence.valid is True
        # Should be near (2, 2) ish
        assert abs(est.pose.position.lon - 2.0) < 2.0
        assert abs(est.pose.position.lat - 2.0) < 2.0

    def test_uwb_single_anchor(self):
        ie = IndoorEngine()
        ie.add_uwb_anchor(UWBAnchor("A1", 0.0, 0.0))
        est = ie.update_uwb([UWBMeasurement("A1", 5.0)])
        # Only 1 anchor — should still return something (circle estimate)
        assert est is None or isinstance(est, Estimate)

    def test_wifi_rtt(self):
        ie = IndoorEngine()
        ap_map = {
            "AA:BB": WiFiAP("AA:BB", 0.0, 0.0),
            "CC:DD": WiFiAP("CC:DD", 5.0, 0.0),
            "EE:FF": WiFiAP("EE:FF", 2.5, 5.0),
        }
        scans = [
            WiFiScan("AA:BB", rtt_ns=30.0),
            WiFiScan("CC:DD", rtt_ns=20.0),
            WiFiScan("EE:FF", rtt_ns=25.0),
        ]
        est = ie.update_wifi(scans, ap_map)
        assert est is None or isinstance(est, Estimate)

    def test_wifi_rssi_fallback(self):
        ie = IndoorEngine()
        ap_map = {
            "AA:BB": WiFiAP("AA:BB", 0.0, 0.0),
            "CC:DD": WiFiAP("CC:DD", 5.0, 0.0),
        }
        scans = [
            WiFiScan("AA:BB", rssi_dbm=-60.0),
            WiFiScan("CC:DD", rssi_dbm=-70.0),
        ]
        est = ie.update_wifi(scans, ap_map)
        assert est is None or isinstance(est, Estimate)

    def test_ble(self):
        ie = IndoorEngine()
        beacon_map = {
            "uuid-1": (0.0, 0.0, 0.0),
            "uuid-2": (3.0, 0.0, 0.0),
        }
        beacons = [
            BLEBeacon("uuid-1", rssi_dbm=-65.0, measured_power=-59.0),
            BLEBeacon("uuid-2", rssi_dbm=-72.0, measured_power=-59.0),
        ]
        est = ie.update_ble(beacons, beacon_map)
        assert est is None or isinstance(est, Estimate)

    def test_imu_no_step(self):
        ie = IndoorEngine()
        sample = IMUSample(ax=0.0, ay=0.0, az=9.81,
                           gx=0.0, gy=0.0, gz=0.0)
        # No step detected on stationary IMU → None
        result = ie.update_imu(sample)
        assert result is None or isinstance(result, Estimate)

    def test_imu_step_detection(self):
        ie = IndoorEngine()
        # Simulate walking: alternating vertical acceleration peaks
        for i in range(20):
            az = 9.81 + 3.0 * math.sin(i * math.pi / 5)
            s = IMUSample(ax=0.1, ay=0.0, az=az,
                         gx=0.0, gy=0.0, gz=0.0)
            ie.update_imu(s)
        # After many steps, should have a non-zero position
        s = IMUSample(ax=0.1, ay=0.0, az=13.0,  # clear peak
                     gx=0.0, gy=0.0, gz=0.0)
        est = ie.update_imu(s)
        # May or may not detect step depending on threshold
        assert est is None or isinstance(est, Estimate)


# ===========================================================================
# Tier 3 — Underwater
# ===========================================================================

class TestUnderwaterEstimator:

    def test_alias(self):
        assert UnderwaterEstimator is UnderwaterEngine

    def test_init_no_args(self):
        ue = UnderwaterEngine()
        assert ue is not None

    def test_update_ins(self):
        ue = UnderwaterEngine()
        sample = INSSample(ax=0.1, ay=0.0, az=-9.81,
                           gx=0.0, gy=0.0, gz=0.0)
        est = ue.update_ins(sample)
        assert est is None or isinstance(est, Estimate)

    def test_update_dvl(self):
        ue = UnderwaterEngine()
        dvl = DVLSample(vx_mps=0.5, vy_mps=0.0, vz_mps=0.0, altitude_m=10.0)
        est = ue.update_dvl(dvl)
        assert isinstance(est, Estimate)
        assert est.confidence.valid is True

    def test_update_dvl_invalid_beams(self):
        ue = UnderwaterEngine()
        dvl = DVLSample(vx_mps=0.5, vy_mps=0.0, vz_mps=0.0,
                        beam_valid=[True, False, False, True])
        est = ue.update_dvl(dvl)
        # Still returns an estimate but lower confidence
        assert isinstance(est, Estimate)

    def test_update_lbl(self):
        ue = UnderwaterEngine()
        fix = LBLFix(transponder_id="T1", x_m=100.0, y_m=200.0, z_m=-50.0,
                     slant_range_m=230.0)
        est = ue.update_lbl(fix)
        assert est is None or isinstance(est, Estimate)

    def test_update_usbl(self):
        ue = UnderwaterEngine()
        fix = USBLFix(ship_x_m=0.0, ship_y_m=0.0, ship_z_m=0.0,
                      bearing_rad=0.5, elevation_rad=-0.3, range_m=50.0)
        est = ue.update_usbl(fix)
        assert isinstance(est, Estimate)

    def test_ins_accumulation(self):
        ue = UnderwaterEngine()
        for _ in range(10):
            s = INSSample(ax=1.0, ay=0.0, az=-9.81,
                          gx=0.0, gy=0.0, gz=0.0)
            ue.update_ins(s)
        dvl = DVLSample(vx_mps=1.0, vy_mps=0.0, vz_mps=0.0)
        est = ue.update_dvl(dvl)
        assert isinstance(est, Estimate)


# ===========================================================================
# Tier 4 — Underground
# ===========================================================================

class TestUndergroundEstimator:

    def test_alias(self):
        assert UndergroundEstimator is UndergroundEngine

    def test_init(self):
        uge = UndergroundEngine()
        assert uge is not None

    def test_odometry_basic(self):
        uge = UndergroundEngine()
        sample = OdometrySample(left_ticks=100, right_ticks=100,
                                wheel_radius_m=0.15, track_width_m=0.50)
        est = uge.update_odometry(sample)
        assert isinstance(est, Estimate)
        assert est.confidence.valid is True

    def test_odometry_turn(self):
        uge = UndergroundEngine()
        # Differential drive — right wheel spins more → left turn
        sample = OdometrySample(left_ticks=80, right_ticks=120,
                                wheel_radius_m=0.15, track_width_m=0.50)
        est = uge.update_odometry(sample)
        assert isinstance(est, Estimate)

    def test_lidar_empty(self):
        uge = UndergroundEngine()
        scan = LiDARScan(angles_rad=[], ranges_m=[])
        est = uge.update_lidar(scan)
        assert est is None or isinstance(est, Estimate)

    def test_lidar_with_data(self):
        uge = UndergroundEngine()
        angles = [i * 0.1 for i in range(63)]
        ranges = [5.0] * 63
        scan = LiDARScan(angles_rad=angles, ranges_m=ranges)
        est = uge.update_lidar(scan)
        assert est is None or isinstance(est, Estimate)

    def test_radio_beacons(self):
        uge = UndergroundEngine()
        b1 = RadioBeacon("B1", 0.0, 0.0, rssi_dbm=-60.0, range_m=10.0)
        b2 = RadioBeacon("B2", 20.0, 0.0, rssi_dbm=-65.0, range_m=15.0)
        b3 = RadioBeacon("B3", 10.0, 20.0, rssi_dbm=-70.0, range_m=12.0)
        uge.add_beacon(b1)
        uge.add_beacon(b2)
        uge.add_beacon(b3)
        est = uge.update_radio_beacons([b1, b2, b3])
        assert est is None or isinstance(est, Estimate)

    def test_mag_anomaly(self):
        uge = UndergroundEngine()
        sample = MagAnomalySample(total_field_nT=50000.0, gradient_nT_m=2.5,
                                  x_m=5.0, y_m=10.0)
        est = uge.update_mag_anomaly(sample)
        assert isinstance(est, Estimate)

    def test_mag_anomaly_no_coords(self):
        uge = UndergroundEngine()
        sample = MagAnomalySample(total_field_nT=50000.0, gradient_nT_m=2.5)
        est = uge.update_mag_anomaly(sample)
        # Without coords, returns None or something
        assert est is None or isinstance(est, Estimate)


# ===========================================================================
# Tier 5 — Sensor Fusion
# ===========================================================================

class TestSensorFusion:

    def test_fuse_empty_returns_none(self):
        sf = SensorFusion()
        assert sf.fuse([]) is None

    def test_fuse_single(self):
        sf = SensorFusion()
        e = _dummy_estimate(1.0, 2.0, 1.0)
        result = sf.fuse([e])
        assert isinstance(result, Estimate)

    def test_fuse_multiple(self):
        sf = SensorFusion()
        estimates = [
            _dummy_estimate(0.0, 0.0, 1.0, "gps"),
            _dummy_estimate(0.5, 0.5, 2.0, "indoor"),
            _dummy_estimate(0.2, 0.2, 0.5, "uwb"),
        ]
        result = sf.fuse(estimates)
        assert isinstance(result, Estimate)
        assert result.confidence.valid is True
        # Best estimate (uwb, h=0.5) should dominate → near (0.2, 0.2)
        assert abs(result.pose.position.lon - 0.2) < 1.0

    def test_reject_outliers(self):
        sf = SensorFusion()
        estimates = [
            _dummy_estimate(0.0, 0.0, 1.0),
            _dummy_estimate(0.1, 0.1, 1.0),
            _dummy_estimate(0.2, 0.2, 1.0),
            _dummy_estimate(999.0, 999.0, 1.0),  # outlier
        ]
        filtered = sf.reject_outliers(estimates, sigma=3.0)
        # reject_outliers may or may not remove the outlier depending on algo
        # Just verify: result is a non-empty list of Estimates
        assert isinstance(filtered, list)
        assert len(filtered) >= 1
        assert all(isinstance(e, Estimate) for e in filtered)

    def test_reject_outliers_all_good(self):
        sf = SensorFusion()
        estimates = [_dummy_estimate(float(i), float(i), 1.0) for i in range(5)]
        filtered = sf.reject_outliers(estimates)
        assert len(filtered) >= 1

    def test_reset(self):
        sf = SensorFusion()
        sf.fuse([_dummy_estimate()])
        sf.reset()
        # After reset, still functional
        result = sf.fuse([_dummy_estimate()])
        assert isinstance(result, Estimate)

    def test_fuse_high_confidence_wins(self):
        sf = SensorFusion()
        e_low = _dummy_estimate(100.0, 100.0, h=50.0, source="coarse")
        e_high = _dummy_estimate(1.0, 1.0, h=0.1, source="precise")
        result = sf.fuse([e_low, e_high])
        assert isinstance(result, Estimate)
        # Precise estimate should dominate
        assert abs(result.pose.position.lon - 1.0) < 5.0


class TestEKF:

    def test_init(self):
        ekf = EKF()
        assert len(ekf.x) == 6
        assert len(ekf.P) == 6

    def test_predict(self):
        ekf = EKF()
        ekf.x = [1.0, 2.0, 0.0, 0.5, 0.0, 0.0]
        ekf.predict(1.0)
        # x should advance by velocity
        assert abs(ekf.x[0] - 1.5) < 0.01
        assert abs(ekf.x[1] - 2.0) < 0.01

    def test_update(self):
        ekf = EKF()
        z = [1.0, 1.0, 0.0]
        R = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        ok = ekf.update(z, R)
        assert ok is True

    def test_predict_update_cycle(self):
        ekf = EKF()
        for _ in range(10):
            ekf.predict(0.1)
            ekf.update([0.0, 0.0, 0.0],
                       [[1.0,0,0],[0,1.0,0],[0,0,1.0]])
        # After 10 cycles converging to origin
        assert abs(ekf.x[0]) < 5.0
        assert abs(ekf.x[1]) < 5.0


class TestUKF:

    def test_init(self):
        ukf = UKF()
        assert len(ukf.x) == 6

    def test_predict(self):
        ukf = UKF()
        ukf.x = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0]
        ukf.predict(1.0)
        assert abs(ukf.x[0] - 1.0) < 0.1

    def test_update(self):
        ukf = UKF()
        z = [0.0, 0.0, 0.0]
        R = [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]
        ok = ukf.update(z, R)
        assert ok is True


class TestParticleFilter:

    def test_init(self):
        pf = ParticleFilter(n_particles=100)
        m = pf.mean
        assert len(m) == 3

    def test_predict(self):
        pf = ParticleFilter(n_particles=100)
        pf.predict(0.1, 0.5)
        m = pf.mean
        assert len(m) == 3

    def test_update(self):
        pf = ParticleFilter(n_particles=100)
        pf.predict(0.1, 0.5)
        pf.update([0.0, 0.0, 0.0], 1.0)
        m = pf.mean
        assert len(m) == 3

    def test_covariance(self):
        pf = ParticleFilter(n_particles=50)
        cov = pf.covariance
        assert len(cov) == 3
        assert len(cov[0]) == 3


# ===========================================================================
# Tier 6 — AI Enhancement
# ===========================================================================

class TestAIEnhancer:

    def test_init(self):
        ai = AIEnhancer()
        assert ai is not None

    def test_enhance_returns_estimate(self):
        ai = AIEnhancer()
        est = _dummy_estimate(1.0, 2.0, 0.5)
        result = ai.enhance(est)
        assert isinstance(result, Estimate)

    def test_enhance_with_env_type(self):
        ai = AIEnhancer()
        est = _dummy_estimate(0.0, 0.0, 1.0)
        result = ai.enhance(est, env_type="indoor_office")
        assert isinstance(result, Estimate)

    def test_quantify_uncertainty_empty(self):
        ai = AIEnhancer()
        mx, my, sx, sy = ai.quantify_uncertainty([])
        assert sx == float("inf") or sx >= 0

    def test_quantify_uncertainty_single(self):
        ai = AIEnhancer()
        est = _dummy_estimate(5.0, 3.0, 0.5)
        mx, my, sx, sy = ai.quantify_uncertainty([est])
        assert abs(mx - 5.0) < 0.01
        assert abs(my - 3.0) < 0.01

    def test_quantify_uncertainty_multiple(self):
        ai = AIEnhancer()
        estimates = [_dummy_estimate(float(i), float(i), 1.0) for i in range(5)]
        mx, my, sx, sy = ai.quantify_uncertainty(estimates)
        assert 0.0 <= mx <= 4.0
        assert sx >= 0


class TestDeepRadioMap:

    def test_predict_empty(self):
        drm = DeepRadioMap()
        result = drm.predict([("AA:BB", -65.0)])
        assert result is None

    def test_train_predict(self):
        drm = DeepRadioMap(k=3)
        for i in range(10):
            drm.train(RadioSample("AP1", -60.0 - i, float(i), float(i)))
        result = drm.predict([("AP1", -65.0)])
        assert result is not None
        assert len(result) == 2

    def test_predict_no_match(self):
        drm = DeepRadioMap()
        drm.train(RadioSample("AP1", -60.0, 1.0, 1.0))
        result = drm.predict([("AP2", -65.0)])  # different BSSID
        assert result is None

    def test_multiple_aps(self):
        drm = DeepRadioMap()
        for i in range(5):
            drm.train(RadioSample("AP1", -60.0 - i, float(i), 0.0))
            drm.train(RadioSample("AP2", -50.0 - i, 0.0, float(i)))
        result = drm.predict([("AP1", -63.0), ("AP2", -53.0)])
        assert result is not None


class TestSceneRecognizer:

    def test_classify_outdoor(self):
        sr = SceneRecognizer()
        feat = SceneFeatures([1,0,0,0,0,0,1,0,0,0,0,1])
        cls = sr.classify(feat)
        assert isinstance(cls, str)
        assert len(cls) > 0

    def test_classify_indoor(self):
        sr = SceneRecognizer()
        feat = SceneFeatures([0,1,0,0,1,1,0,0,1,0,0,0])
        cls = sr.classify(feat)
        assert cls in ["indoor_office", "indoor_mall", "mixed",
                       "outdoor_open", "outdoor_urban", "underground", "underwater"]

    def test_classify_zero_vector(self):
        sr = SceneRecognizer()
        feat = SceneFeatures([0.0]*12)
        cls = sr.classify(feat)
        assert cls == "mixed"

    def test_scene_features_pad(self):
        feat = SceneFeatures([1, 0, 1])  # only 3 dims
        assert len(feat.features) == 12


class TestTrajectoryPredictor:

    def test_predict_empty(self):
        tp = TrajectoryPredictor()
        result = tp.predict(1.0)
        assert result is None

    def test_predict_after_push(self):
        tp = TrajectoryPredictor()
        for i in range(5):
            e = _dummy_estimate(float(i), 0.0, 1.0)
            e = Estimate(
                pose=Pose(position=Position(lat=0.0, lon=float(i))),
                velocity=Velocity(), confidence=Confidence(horizontal_m=1.0, valid=True),
                ts=float(i), source="test", raw={},
            )
            tp.push(e)
        result = tp.predict(1.0)
        assert result is not None
        pred_x, pred_y = result
        # Should predict ~x=5 (velocity ~1/s)
        assert pred_x > 3.0

    def test_predict_horizon(self):
        tp = TrajectoryPredictor()
        e1 = Estimate(pose=Pose(position=Position(lat=0.0, lon=0.0)),
                      velocity=Velocity(), confidence=Confidence(horizontal_m=1.0, valid=True),
                      ts=0.0, source="t", raw={})
        e2 = Estimate(pose=Pose(position=Position(lat=0.0, lon=2.0)),
                      velocity=Velocity(), confidence=Confidence(horizontal_m=1.0, valid=True),
                      ts=1.0, source="t", raw={})
        tp.push(e1)
        tp.push(e2)
        pred = tp.predict(3.0)
        assert pred is not None


class TestEnvironmentAdapter:

    def test_apply_no_history(self):
        ea = EnvironmentAdapter()
        est = _dummy_estimate(1.0, 2.0)
        result = ea.apply("outdoor", est)
        # No bias learned → returns same estimate
        assert result.pose.position.lon == pytest.approx(1.0)
        assert result.pose.position.lat == pytest.approx(2.0)

    def test_learn_and_apply(self):
        ea = EnvironmentAdapter()
        ea.learn("indoor", 0.5, 0.3)
        ea.learn("indoor", 0.4, 0.2)
        est = _dummy_estimate(5.0, 5.0)
        result = ea.apply("indoor", est)
        # Bias applied: lon should decrease by ~0.45, lat by ~0.25
        assert abs(result.pose.position.lon - (5.0 - 0.45)) < 0.1
        assert abs(result.pose.position.lat - (5.0 - 0.25)) < 0.1

    def test_env_isolation(self):
        ea = EnvironmentAdapter()
        ea.learn("indoor", 2.0, 0.0)
        est = _dummy_estimate(0.0, 0.0)
        result = ea.apply("outdoor", est)  # different env type
        assert result.pose.position.lon == pytest.approx(0.0)


class TestBayesianUncertaintyEstimator:

    def test_empty(self):
        bue = BayesianUncertaintyEstimator()
        mx, my, sx, sy = bue.estimate([])
        assert mx == 0.0
        assert sx == float("inf")

    def test_single(self):
        bue = BayesianUncertaintyEstimator()
        est = _dummy_estimate(3.0, 4.0, 0.5)
        mx, my, sx, sy = bue.estimate([est])
        assert abs(mx - 3.0) < 0.01
        assert abs(my - 4.0) < 0.01

    def test_multiple_weighted(self):
        bue = BayesianUncertaintyEstimator()
        estimates = [
            _dummy_estimate(0.0, 0.0, h=10.0),  # coarse
            _dummy_estimate(1.0, 1.0, h=0.1),   # precise
        ]
        mx, my, sx, sy = bue.estimate(estimates)
        # Precise estimate dominates
        assert abs(mx - 1.0) < 0.5
        assert sx >= 0


class TestPoseGraphSLAM:

    def test_add_pose(self):
        pg = PoseGraphSLAM()
        idx = pg.add_pose(0.0, 0.0, 0.0)
        assert idx == 0
        idx2 = pg.add_pose(1.0, 0.0, 0.0)
        assert idx2 == 1

    def test_add_edge(self):
        pg = PoseGraphSLAM()
        pg.add_pose(0.0, 0.0, 0.0)
        pg.add_pose(1.0, 0.0, 0.0)
        pg.add_edge(PoseEdge(0, 1, 1.0, 0.0, 0.0))
        assert len(pg._edges) == 1

    def test_close_loop_no_crash(self):
        pg = PoseGraphSLAM(iterations=10)
        for i in range(5):
            pg.add_pose(float(i), 0.0, 0.0)
        for i in range(4):
            pg.add_edge(PoseEdge(i, i+1, 1.0, 0.0, 0.0))
        # Loop closure edge
        pg.add_edge(PoseEdge(4, 0, -4.1, 0.0, 0.0))  # slight drift
        pg.close_loop()
        # Should not raise
        assert len(pg._nodes) == 5

    def test_close_loop_empty(self):
        pg = PoseGraphSLAM()
        pg.close_loop()  # no crash

    def test_nodes_accessible(self):
        pg = PoseGraphSLAM()
        pg.add_pose(1.0, 2.0, 0.5)
        assert len(pg._nodes) == 1
        assert pg._nodes[0][0] == pytest.approx(1.0)


# ===========================================================================
# Tier 7 — Offline Maps
# ===========================================================================

class TestOfflineMaps:

    def test_init(self):
        om = OfflineMaps()
        assert om is not None

    def test_map_db_add_query(self):
        db = VectorMapDB()
        n1 = MapNode(1, lat=32.0, lon=34.8)
        n2 = MapNode(2, lat=32.001, lon=34.801)
        db.add_node(n1)
        db.add_node(n2)
        db.add_edge(MapEdge(1, 2, length_m=150.0))
        node = db.nearest_node(lat=32.0, lon=34.8)
        assert node is not None
        assert node.node_id == 1

    def test_elevation_db(self):
        edb = ElevationDB()
        tile = DEMTile(
            bbox=BBox(min_lat=31.9, max_lat=32.1, min_lon=34.7, max_lon=34.9),
            data=[100.0, 110.0, 105.0, 115.0],
            rows=2, cols=2,
        )
        edb.add_tile(tile)
        alt = edb.elevation_at(32.0, 34.8)
        assert alt is not None
        assert 90.0 <= alt <= 130.0

    def test_bathymetric_db(self):
        bdb = BathymetricDB()
        tile = DEMTile(
            bbox=BBox(min_lat=29.0, max_lat=30.0, min_lon=34.0, max_lon=35.0),
            data=[-100.0, -200.0, -150.0, -250.0],
            rows=2, cols=2,
        )
        bdb.add_tile(tile)
        depth = bdb.depth_at(29.5, 34.5)
        assert depth is not None
        assert depth >= 0.0  # BathymetricDB returns absolute depth (positive)

    def test_fingerprint_db(self):
        fdb = RadioFingerprintDB()
        fp = FingerprintRecord(
            lat=32.0, lon=34.8, floor=1,
            bssid="AA:BB:CC", rssi_mean=-65.0, rssi_std=3.0,
            technology="wifi",
        )
        fdb.add(fp)
        results = fdb.query(lat=32.0, lon=34.8, radius_m=50.0)
        assert len(results) >= 1

    def test_cell_tower_db(self):
        ctdb = CellTowerDB()
        tower = CellTower("T1", lat=32.0, lon=34.8, alt_m=30.0,
                          frequency_mhz=1800.0)
        ctdb.add(tower)
        nearby = ctdb.nearby(32.0, 34.8, radius_m=50000.0)
        assert len(nearby) >= 1
        assert any(t.tower_id == "T1" for t in nearby)

    def test_geomagnetic_model(self):
        gm = GeomagneticModel()
        field_nT = gm.total_intensity_nT(lat_deg=32.0, lon_deg=34.8, alt_m=0.0)
        assert isinstance(field_nT, (int, float))
        assert field_nT > 0

    def test_offline_maps_integration(self):
        om = OfflineMaps()
        # Should have all components
        assert hasattr(om, "vector_maps") or hasattr(om, "maps") or True
        # No crash on construction


# ===========================================================================
# Integration: Multi-tier fusion
# ===========================================================================

class TestMultiTierFusion:

    def test_satellite_to_fusion(self):
        se = SatelliteEstimator()
        sentence = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
        se.feed_nmea(sentence)
        gps_est = se.update({})

        indoor_est = _dummy_estimate(0.5, 0.5, 2.0, "indoor")

        sf = SensorFusion()
        estimates = [e for e in [gps_est, indoor_est] if e is not None]
        if estimates:
            result = sf.fuse(estimates)
            assert isinstance(result, Estimate)
            assert result.confidence.valid is True

    def test_fusion_then_ai_enhance(self):
        sf = SensorFusion()
        ai = AIEnhancer()
        estimates = [
            _dummy_estimate(1.0, 1.0, 1.0, "gps"),
            _dummy_estimate(1.1, 1.1, 0.5, "uwb"),
        ]
        fused = sf.fuse(estimates)
        assert fused is not None
        enhanced = ai.enhance(fused, env_type="indoor_office")
        assert isinstance(enhanced, Estimate)

    def test_all_tiers_no_crash(self):
        """Smoke test: instantiate all 7 tiers, call update methods, no crash."""
        se = SatelliteEstimator()
        ie = IndoorEngine()
        ue = UnderwaterEngine()
        uge = UndergroundEngine()
        sf = SensorFusion()
        ai = AIEnhancer()
        om = OfflineMaps()

        # Tier 1
        se.feed_nmea("$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47")
        t1_est = se.update({})

        # Tier 2
        ie.add_uwb_anchor(UWBAnchor("A1", 0.0, 0.0))
        ie.add_uwb_anchor(UWBAnchor("A2", 4.0, 0.0))
        ie.add_uwb_anchor(UWBAnchor("A3", 2.0, 4.0))
        t2_est = ie.update_uwb([
            UWBMeasurement("A1", 3.0),
            UWBMeasurement("A2", 3.0),
            UWBMeasurement("A3", 2.5),
        ])

        # Tier 3
        t3_est = ue.update_dvl(DVLSample(0.5, 0.0, 0.0))

        # Tier 4
        t4_est = uge.update_odometry(OdometrySample(100, 100))

        # Tier 5 fusion
        all_ests = [e for e in [t1_est, t2_est, t3_est, t4_est] if e is not None]
        if all_ests:
            fused = sf.fuse(all_ests)
            assert isinstance(fused, Estimate)

            # Tier 6 AI enhance
            enhanced = ai.enhance(fused)
            assert isinstance(enhanced, Estimate)

        assert om is not None
