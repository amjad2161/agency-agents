"""Smoke test — all tiers import + return scaffold Estimate."""
from godskill_nav_v11 import (
    SatelliteEstimator, IndoorEstimator, UnderwaterEstimator,
    UndergroundEstimator, SensorFusion, AIEnhancer,
)


def test_imports():
    assert SatelliteEstimator and IndoorEstimator and UnderwaterEstimator
    assert UndergroundEstimator and SensorFusion and AIEnhancer


def test_satellite_stub():
    e = SatelliteEstimator().update({})
    assert e.source == "satellite"


def test_indoor_stub():
    e = IndoorEstimator().update({})
    assert e.source == "indoor"


def test_fusion_empty():
    f = SensorFusion()
    e = f.fuse([])
    assert "fusion" in e.source


def test_fusion_picks_best():
    from godskill_nav_v11 import Estimate, Pose, Position, Confidence
    a = Estimate(
        pose=Pose(Position(1, 2, 3)),
        confidence=Confidence(horizontal_m=5.0, vertical_m=10.0, valid=True, source="a"),
        source="a",
    )
    b = Estimate(
        pose=Pose(Position(4, 5, 6)),
        confidence=Confidence(horizontal_m=1.0, vertical_m=2.0, valid=True, source="b"),
        source="b",
    )
    fused = SensorFusion().fuse([a, b])
    assert fused.pose.position.lat == 4  # b had lower uncertainty


def test_ai_predict_empty():
    assert AIEnhancer().predict_next([]) is None


def test_ai_predict_returns_last():
    from godskill_nav_v11 import Estimate, Pose, Position, Confidence
    e = Estimate(pose=Pose(Position(0, 0, 0)), source="x")
    assert AIEnhancer().predict_next([e]) is e
