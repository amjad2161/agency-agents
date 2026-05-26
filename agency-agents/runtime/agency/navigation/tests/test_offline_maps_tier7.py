"""Tier-7 offline map engine tests.

Covers:
- Slippy-tile math round-trip + preload region
- DEM SRTM .hgt parser, bilinear interpolation, profile, slope, contours
- Tower CSV load, exact lookup, Haversine nearby, weighted-centroid estimate
- Radio fingerprint store, KNN, export/import CSV, SQLite persistence
- WMM declination range + secular variation
- VectorMapStore GeoJSON parse, bbox query, nearest, ASCII render, road graph
- OfflineMapManager get_context, is_available, storage_summary
"""
from __future__ import annotations

import json
import math
import os
import struct
import tempfile

import numpy as np
import pytest

from runtime.agency.navigation.offline_maps import (
    DEMStore,
    OfflineMapManager,
    RadioFingerprintDB,
    SatelliteImageCache,
    TowerDatabase,
    VectorMapStore,
    WMMModel,
    _haversine_m,
)


# ---------------------------------------------------------------------------
# 1. Slippy-tile math
# ---------------------------------------------------------------------------

def test_lat_lon_to_tile_round_trip_z10() -> None:
    cache = SatelliteImageCache(os.path.join(tempfile.mkdtemp(), "s.db"))
    lat, lon = 32.0853, 34.7818  # Tel Aviv
    z = 10
    x, y = cache.lat_lon_to_tile(lat, lon, z)
    nw_lat, nw_lon = cache.tile_to_lat_lon(x, y, z)
    se_lat, se_lon = cache.tile_to_lat_lon(x + 1, y + 1, z)
    assert se_lat <= lat <= nw_lat
    assert nw_lon <= lon <= se_lon


def test_tile_key_matches_lat_lon_to_tile() -> None:
    cache = SatelliteImageCache(os.path.join(tempfile.mkdtemp(), "s.db"))
    x, y, z = cache.tile_key(40.7128, -74.0060, 12)
    x2, y2 = cache.lat_lon_to_tile(40.7128, -74.0060, 12)
    assert (x, y) == (x2, y2) and z == 12


def test_preload_region_returns_grid_of_tiles() -> None:
    cache = SatelliteImageCache(os.path.join(tempfile.mkdtemp(), "s.db"))
    tiles = cache.preload_region(31.0, 34.0, 32.0, 35.0, zoom=8)
    assert len(tiles) >= 1
    zooms = {t[0] for t in tiles}
    assert zooms == {8}


def test_cache_tile_round_trip_and_stats() -> None:
    db = os.path.join(tempfile.mkdtemp(), "tiles.db")
    cache = SatelliteImageCache(db)
    payload = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    cache.cache_tile(10, 600, 380, payload)
    got = cache.get_tile(10, 600, 380)
    assert got == payload
    stats = cache.cache_stats()
    assert stats["tile_count"] == 1
    assert stats["size_bytes"] == len(payload)
    assert stats["size_mb"] > 0


# ---------------------------------------------------------------------------
# 2. DEMStore
# ---------------------------------------------------------------------------

def _synthetic_hgt_bytes(n: int = 1201, slope: float = 1.0) -> bytes:
    """Build a 1201×1201 SRTM tile where elev = row + slope*col (in metres)."""
    arr = np.zeros((n, n), dtype=">i2")
    for r in range(n):
        for c in range(n):
            arr[r, c] = int(r + slope * c)
    return arr.tobytes()


def test_srtm_hgt_header_parse_and_grid_dims() -> None:
    raw = _synthetic_hgt_bytes(1201)
    dem = DEMStore()
    tile = dem.load_srtm_hgt(raw, lat_origin=31, lon_origin=34)
    assert tile["n"] == 1201
    assert tile["lat0"] == 31.0
    assert tile["lon0"] == 34.0
    assert dem.tile_count == 1


def test_srtm_hgt_rejects_bad_size() -> None:
    dem = DEMStore()
    with pytest.raises(ValueError):
        dem.load_srtm_hgt(b"\x00" * 1000, 31, 34)


def test_dem_bilinear_interpolation_centre_of_cell() -> None:
    raw = _synthetic_hgt_bytes(1201, slope=1.0)
    dem = DEMStore()
    dem.load_srtm_hgt(raw, lat_origin=31, lon_origin=34)
    # SW corner = lat 31, lon 34 -> bottom-left = row 1200, col 0 -> elev 1200
    elev_sw = dem.get_elevation(31.0, 34.0)
    assert math.isclose(elev_sw, 1200.0, abs_tol=1.0)
    # NE corner = lat 32, lon 35 -> top-right = row 0, col 1200 -> elev 1200
    elev_ne = dem.get_elevation(32.0, 35.0)
    assert math.isclose(elev_ne, 1200.0, abs_tol=1.0)
    # NW corner = row 0 col 0 -> elev 0
    elev_nw = dem.get_elevation(32.0, 34.0)
    assert math.isclose(elev_nw, 0.0, abs_tol=1.0)


def test_dem_profile_monotonic_on_linear_grid() -> None:
    raw = _synthetic_hgt_bytes(1201, slope=1.0)
    dem = DEMStore()
    dem.load_srtm_hgt(raw, lat_origin=31, lon_origin=34)
    # Walk west->east at constant lat: row stays fixed, col increases -> elev increases.
    profile = dem.get_profile(31.5, 34.0, 31.5, 35.0, n=20)
    assert profile == sorted(profile)


def test_dem_slope_nonnegative() -> None:
    raw = _synthetic_hgt_bytes(1201, slope=1.0)
    dem = DEMStore()
    dem.load_srtm_hgt(raw, lat_origin=31, lon_origin=34)
    s = dem.get_slope(31.5, 34.5)
    assert 0.0 <= s <= 90.0


def test_dem_contour_lines_runs() -> None:
    # Tiny 11x11 grid for speed via direct list_of_tiles append.
    n = 11
    arr = np.fromfunction(lambda r, c: r + c, (n, n), dtype=np.float32)
    dem = DEMStore()
    dem._tiles.append({
        "grid": arr, "lat0": 0.0, "lon0": 0.0,
        "side_deg": 1.0, "n": n,
    })
    contours = dem.contour_lines(elevation_step=2.0)
    assert len(contours) > 0
    for seg in contours:
        assert len(seg) == 2


# ---------------------------------------------------------------------------
# 3. TowerDatabase
# ---------------------------------------------------------------------------

def _write_tower_csv(path: str) -> None:
    rows = [
        ("mcc", "mnc", "lac", "cid", "lat", "lon", "range_m"),
        (425, 1, 100, 1001, 32.0, 34.8, 2000),
        (425, 1, 100, 1002, 32.01, 34.81, 1500),
        (425, 1, 100, 1003, 40.0, -74.0, 3000),
    ]
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(",".join(str(x) for x in r) + "\n")


def test_tower_load_and_exact_lookup() -> None:
    p = os.path.join(tempfile.mkdtemp(), "towers.csv")
    _write_tower_csv(p)
    db = TowerDatabase()
    n = db.load_csv(p)
    assert n == 3
    assert db.tower_count == 3
    rec = db.lookup(425, 1, 100, 1001)
    assert rec is not None and rec["lat"] == 32.0


def test_tower_nearby_uses_haversine() -> None:
    p = os.path.join(tempfile.mkdtemp(), "towers.csv")
    _write_tower_csv(p)
    db = TowerDatabase()
    db.load_csv(p)
    # Query around Tel Aviv -> US tower must be excluded.
    near = db.nearby(32.0, 34.8, radius_m=5000.0)
    cids = [r["cid"] for r in near]
    assert 1001 in cids and 1002 in cids and 1003 not in cids


def test_tower_position_estimate_weighted_centroid() -> None:
    towers = [
        {"lat": 32.0, "lon": 34.8},
        {"lat": 32.1, "lon": 34.9},
    ]
    # Stronger signal at first tower -> estimate should pull toward it.
    lat, lon = TowerDatabase.position_estimate(towers, [-50.0, -90.0])
    assert lat < 32.05 and lon < 34.85


# ---------------------------------------------------------------------------
# 4. RadioFingerprintDB (Tier-7 API)
# ---------------------------------------------------------------------------

def test_fingerprint_store_and_knn() -> None:
    db = RadioFingerprintDB()
    db.store(32.0, 34.8, {"AA:BB": -50, "CC:DD": -70})
    db.store(32.001, 34.801, {"AA:BB": -52, "CC:DD": -72})
    db.store(40.0, -74.0, {"EE:FF": -55})
    res = db.lookup_nearest({"AA:BB": -49, "CC:DD": -71}, k=2)
    assert len(res) == 2
    # Closest matches should be Tel-Aviv-area scans.
    assert all(31.9 < lat < 32.1 for lat, _, _ in res)


def test_fingerprint_export_import_round_trip() -> None:
    p = os.path.join(tempfile.mkdtemp(), "fp.csv")
    src = RadioFingerprintDB()
    src.store(1.0, 2.0, {"X": -40})
    src.store(3.0, 4.0, {"Y": -60})
    src.export_csv(p)
    dst = RadioFingerprintDB()
    n = dst.import_csv(p)
    assert n == 2
    assert dst.stats()["scan_count"] == 2


def test_fingerprint_sqlite_persistence() -> None:
    db_path = os.path.join(tempfile.mkdtemp(), "fp.sqlite")
    a = RadioFingerprintDB(db_path=db_path)
    a.store(10.0, 20.0, {"M": -30})
    a.store(11.0, 21.0, {"M": -32})
    # New instance pointed at same SQLite must see same data.
    b = RadioFingerprintDB(db_path=db_path)
    assert b.stats()["scan_count"] == 2


def test_fingerprint_vector_dim_and_norm() -> None:
    v = RadioFingerprintDB._fingerprint_vector({"X": -40, "Y": -60})
    assert v.shape == (32,)
    assert v.max() <= 0.0   # RSSI in dBm (always ≤ 0)
    assert v.min() == -100.0   # untouched slots default


# ---------------------------------------------------------------------------
# 5. WMM model
# ---------------------------------------------------------------------------

def test_wmm_declination_range_global() -> None:
    wmm = WMMModel()
    for lat in (-60.0, -30.0, 0.0, 30.0, 60.0):
        for lon in (-150.0, -60.0, 0.0, 60.0, 150.0):
            d = wmm.declination(lat, lon, 2024.0)
            assert -180.0 <= d <= 180.0


def test_wmm_intensity_in_plausible_range() -> None:
    wmm = WMMModel()
    _, _, F = wmm.compute(0.0, 0.0, 0.0, 2024.0)
    # Equatorial total field ~25k–35k nT.
    assert 15_000.0 < F < 60_000.0


def test_wmm_secular_variation_changes_decl() -> None:
    wmm = WMMModel()
    d2020 = wmm.declination(45.0, 10.0, 2020.0)
    d2030 = wmm.declination(45.0, 10.0, 2030.0)
    assert d2020 != d2030


# ---------------------------------------------------------------------------
# 6. VectorMapStore + GeoJSON
# ---------------------------------------------------------------------------

_GEOJSON = json.dumps({
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [34.78, 32.08]},
            "properties": {"name": "TLV"},
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-74.0, 40.7]},
            "properties": {"name": "NYC"},
        },
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [34.78, 32.08], [34.79, 32.09], [34.80, 32.10],
                ],
            },
            "properties": {"highway": "primary"},
        },
    ],
})


def test_vectormap_geojson_load_and_bbox_query() -> None:
    store = VectorMapStore(zoom=10)
    n = store.load_geojson(_GEOJSON)
    assert n == 3
    hits = store.query_bbox(31.5, 34.0, 32.5, 35.0)
    names = {f["properties"].get("name") for f in hits if "name" in f["properties"]}
    assert "TLV" in names
    assert "NYC" not in names


def test_vectormap_query_nearest_haversine() -> None:
    store = VectorMapStore(zoom=10)
    store.load_geojson(_GEOJSON)
    near = store.query_nearest(32.0, 34.8, k=1)
    assert near[0]["properties"].get("name") == "TLV"


def test_vectormap_render_ascii_dimensions_and_marker() -> None:
    store = VectorMapStore(zoom=10)
    store.load_geojson(_GEOJSON)
    out = store.render_ascii(32.08, 34.78, zoom=10, width=40, height=10)
    rows = out.split("\n")
    assert len(rows) == 10
    assert all(len(r) == 40 for r in rows)
    assert "@" in out


def test_vectormap_road_graph_has_edges() -> None:
    store = VectorMapStore(zoom=10)
    store.load_geojson(_GEOJSON)
    g = store.get_road_graph((31.5, 34.0, 32.5, 35.0))
    assert len(g) >= 2
    total_edges = sum(len(v) for v in g.values())
    assert total_edges >= 4   # 2 segments, both directions


# ---------------------------------------------------------------------------
# 7. OfflineMapManager — integration
# ---------------------------------------------------------------------------

def test_manager_get_context_and_storage_summary(tmp_path) -> None:
    mgr = OfflineMapManager(str(tmp_path))
    # Seed tower + cache one tile so summary has data.
    tower_csv = tmp_path / "t.csv"
    _write_tower_csv(str(tower_csv))
    mgr.towers.load_csv(str(tower_csv))
    x, y, z = SatelliteImageCache.tile_key(32.0, 34.8, 10)
    mgr.satellite.cache_tile(z, x, y, b"PNGDATA")
    assert mgr.is_available(32.0, 34.8, 10)
    ctx = mgr.get_context(32.0, 34.8)
    assert "magnetic_declination_deg" in ctx
    assert any(t["cid"] == 1001 for t in ctx["nearby_towers"])
    summary = mgr.storage_summary()
    assert summary["tower_count"] == 3
    assert summary["satellite_bytes"] > 0


def test_manager_is_available_false_when_uncached(tmp_path) -> None:
    mgr = OfflineMapManager(str(tmp_path))
    assert mgr.is_available(0.0, 0.0, 5) is False


# ---------------------------------------------------------------------------
# 8. Helpers
# ---------------------------------------------------------------------------

def test_haversine_known_distance() -> None:
    # NYC -> LA roughly 3935 km.
    d = _haversine_m(40.7128, -74.0060, 34.0522, -118.2437)
    assert 3_900_000 < d < 4_000_000
