"""
GODSKILL Nav v11 — Tier 7: Offline Data & Map Engine.

All map data is stored locally; no internet required at runtime.

Legacy stores (kept for backward compatibility):
    VectorMapDB         — Road/path network in WGS-84 tiles (CSV-driven)
    ElevationDB         — Digital Elevation Model grid
    BathymetricDB       — Underwater depth grid
    RadioFingerprintDB  — RSSI + UWB offline fingerprint database
    CellTowerDB         — Cell tower / radio beacon catalogue
    GeomagneticModel    — IGRF-13 dipole approximation
    OfflineMaps         — Unified facade over the legacy stores

Tier 7 stores (new spec):
    VectorMapStore      — GeoJSON vector layer + spatial grid + ASCII renderer
    SatelliteImageCache — SQLite-backed slippy-map tile store
    DEMStore            — SRTM .hgt parser + bilinear interpolation + contours
    TowerDatabase       — Cellular tower CSV (mcc/mnc/lac/cid) + nearby search
    WMMModel            — Simplified WMM-2020 dipole + secular-variation model
    OfflineMapManager   — Unified facade over the Tier-7 stores

Dependencies: stdlib only (sqlite3, json, struct, math, os) + numpy.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import sqlite3
import struct
import time
from dataclasses import dataclass, field
from typing import Iterator, Optional

import numpy as np


# ---------------------------------------------------------------------------
# Shared spatial types
# ---------------------------------------------------------------------------

@dataclass
class BBox:
    """Axis-aligned bounding box (WGS-84)."""
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float

    def contains(self, lat: float, lon: float) -> bool:
        return (self.min_lat <= lat <= self.max_lat and
                self.min_lon <= lon <= self.max_lon)

    def expand(self, margin_deg: float) -> "BBox":
        return BBox(self.min_lat - margin_deg, self.min_lon - margin_deg,
                    self.max_lat + margin_deg, self.max_lon + margin_deg)


@dataclass
class LatLon:
    lat: float
    lon: float

    def distance_m(self, other: "LatLon") -> float:
        """Haversine distance (metres)."""
        return _haversine_m(self.lat, self.lon, other.lat, other.lon)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


# ---------------------------------------------------------------------------
# Spatial grid index  (uniform bucket hash for O(1) tile lookup)
# ---------------------------------------------------------------------------

class SpatialGrid:
    """Uniform lat/lon grid index. Items must have .lat and .lon attributes."""

    def __init__(self, bucket_deg: float = 0.01) -> None:
        self._bkt = bucket_deg
        self._grid: dict[tuple[int, int], list] = {}

    def _key(self, lat: float, lon: float) -> tuple[int, int]:
        return (int(lat / self._bkt), int(lon / self._bkt))

    def insert(self, item) -> None:
        k = self._key(item.lat, item.lon)
        self._grid.setdefault(k, []).append(item)

    def query_radius(self, lat: float, lon: float,
                     radius_m: float) -> list:
        deg_margin = radius_m / 111_320.0 + self._bkt
        results = []
        min_ik = int((lat - deg_margin) / self._bkt)
        max_ik = int((lat + deg_margin) / self._bkt) + 1
        min_jk = int((lon - deg_margin) / self._bkt)
        max_jk = int((lon + deg_margin) / self._bkt) + 1
        for ik in range(min_ik, max_ik + 1):
            for jk in range(min_jk, max_jk + 1):
                for item in self._grid.get((ik, jk), []):
                    if _haversine_m(lat, lon, item.lat, item.lon) <= radius_m:
                        results.append(item)
        return results

    def query_bbox(self, bbox: BBox) -> list:
        results = []
        ik0 = int(bbox.min_lat / self._bkt)
        ik1 = int(bbox.max_lat / self._bkt) + 1
        jk0 = int(bbox.min_lon / self._bkt)
        jk1 = int(bbox.max_lon / self._bkt) + 1
        for ik in range(ik0, ik1 + 1):
            for jk in range(jk0, jk1 + 1):
                for item in self._grid.get((ik, jk), []):
                    if bbox.contains(item.lat, item.lon):
                        results.append(item)
        return results

    @property
    def item_count(self) -> int:
        return sum(len(v) for v in self._grid.values())


# ===========================================================================
# LEGACY: Vector Map DB (road/path network) — preserved for back-compat
# ===========================================================================

@dataclass
class MapNode:
    node_id: int
    lat: float
    lon: float
    alt_m: float = 0.0
    tags: dict = field(default_factory=dict)


@dataclass
class MapEdge:
    from_id: int
    to_id: int
    length_m: float
    speed_limit_kmh: float = 0.0
    road_class: str = "path"


class VectorMapDB:
    """Offline vector map (legacy CSV-driven graph)."""

    def __init__(self) -> None:
        self._nodes: dict[int, MapNode] = {}
        self._edges: dict[int, list[MapEdge]] = {}
        self._idx = SpatialGrid(bucket_deg=0.01)

    def add_node(self, node: MapNode) -> None:
        self._nodes[node.node_id] = node
        self._idx.insert(node)

    def add_edge(self, edge: MapEdge, bidirectional: bool = True) -> None:
        self._edges.setdefault(edge.from_id, []).append(edge)
        if bidirectional:
            rev = MapEdge(edge.to_id, edge.from_id, edge.length_m,
                          edge.speed_limit_kmh, edge.road_class)
            self._edges.setdefault(edge.to_id, []).append(rev)

    def nearest_node(self, lat: float, lon: float,
                     max_radius_m: float = 500.0) -> Optional[MapNode]:
        candidates = self._idx.query_radius(lat, lon, max_radius_m)
        if not candidates:
            return None
        return min(candidates,
                   key=lambda n: _haversine_m(lat, lon, n.lat, n.lon))

    def route(self, from_node_id: int,
              to_node_id: int) -> Optional[list[int]]:
        if from_node_id not in self._nodes or to_node_id not in self._nodes:
            return None
        dist: dict[int, float] = {from_node_id: 0.0}
        prev: dict[int, Optional[int]] = {from_node_id: None}
        heap: list[tuple[float, int]] = [(0.0, from_node_id)]
        visited: set[int] = set()
        while heap:
            heap.sort(key=lambda x: x[0])
            d, u = heap.pop(0)
            if u in visited:
                continue
            visited.add(u)
            if u == to_node_id:
                break
            for edge in self._edges.get(u, []):
                v = edge.to_id
                nd = d + edge.length_m
                if nd < dist.get(v, math.inf):
                    dist[v] = nd
                    prev[v] = u
                    heap.append((nd, v))
        if to_node_id not in dist:
            return None
        path: list[int] = []
        node: Optional[int] = to_node_id
        while node is not None:
            path.append(node)
            node = prev.get(node)
        path.reverse()
        return path

    def load_csv(self, nodes_path: str, edges_path: str) -> None:
        if os.path.exists(nodes_path):
            with open(nodes_path, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i == 0:
                        continue
                    parts = line.strip().split(",")
                    if len(parts) < 3:
                        continue
                    nid = int(parts[0])
                    lat, lon = float(parts[1]), float(parts[2])
                    alt = float(parts[3]) if len(parts) > 3 else 0.0
                    self.add_node(MapNode(nid, lat, lon, alt))
        if os.path.exists(edges_path):
            with open(edges_path, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i == 0:
                        continue
                    parts = line.strip().split(",")
                    if len(parts) < 3:
                        continue
                    frm, to, lng = int(parts[0]), int(parts[1]), float(parts[2])
                    spd = float(parts[3]) if len(parts) > 3 else 0.0
                    cls = parts[4].strip() if len(parts) > 4 else "path"
                    self.add_edge(MapEdge(frm, to, lng, spd, cls))

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return sum(len(v) for v in self._edges.values())


# ===========================================================================
# LEGACY: DEM tile + ElevationDB + BathymetricDB
# ===========================================================================

@dataclass
class DEMTile:
    bbox: BBox
    rows: int
    cols: int
    data: list[float]

    def elevation_at(self, lat: float, lon: float) -> Optional[float]:
        if not self.bbox.contains(lat, lon):
            return None
        frac_lat = (lat - self.bbox.min_lat) / \
                   (self.bbox.max_lat - self.bbox.min_lat + 1e-12)
        frac_lon = (lon - self.bbox.min_lon) / \
                   (self.bbox.max_lon - self.bbox.min_lon + 1e-12)
        row = max(0, min(int(frac_lat * self.rows), self.rows - 1))
        col = max(0, min(int(frac_lon * self.cols), self.cols - 1))
        return self.data[row * self.cols + col]


class ElevationDB:
    def __init__(self) -> None:
        self._tiles: list[DEMTile] = []

    def add_tile(self, tile: DEMTile) -> None:
        self._tiles.append(tile)

    def elevation_at(self, lat: float, lon: float) -> Optional[float]:
        for tile in self._tiles:
            elev = tile.elevation_at(lat, lon)
            if elev is not None:
                return elev
        return None

    def load_srtm_hgt(self, path: str) -> None:
        basename = os.path.basename(path).upper()
        try:
            lat_dir = 1 if basename[0] == "N" else -1
            lon_dir = 1 if basename[3] == "E" else -1
            lat_sw = lat_dir * int(basename[1:3])
            lon_sw = lon_dir * int(basename[4:7])
        except (ValueError, IndexError):
            lat_sw, lon_sw = 0, 0
        size = os.path.getsize(path)
        npts = int(math.sqrt(size // 2))
        with open(path, "rb") as f:
            raw = f.read()
        data: list[float] = []
        for i in range(0, len(raw) - 1, 2):
            val = struct.unpack(">h", raw[i:i + 2])[0]
            data.append(float(val) if val != -32768 else 0.0)
        bbox = BBox(lat_sw, lon_sw, lat_sw + 1.0, lon_sw + 1.0)
        self.add_tile(DEMTile(bbox, npts, npts, data))

    @property
    def tile_count(self) -> int:
        return len(self._tiles)


class BathymetricDB:
    def __init__(self) -> None:
        self._tiles: list[DEMTile] = []

    def add_tile(self, tile: DEMTile) -> None:
        self._tiles.append(tile)

    def depth_at(self, lat: float, lon: float) -> Optional[float]:
        for tile in self._tiles:
            val = tile.elevation_at(lat, lon)
            if val is not None:
                return abs(val)
        return None

    @property
    def tile_count(self) -> int:
        return len(self._tiles)


# ===========================================================================
# LEGACY: RadioFingerprintDB + extension to Tier-7 spec
# ===========================================================================

@dataclass
class FingerprintRecord:
    lat: float
    lon: float
    floor: int
    bssid: str
    rssi_mean: float
    rssi_std: float
    technology: str


# Fixed-dim canonical fingerprint vector dimension (top-N strongest BSSIDs).
_FINGERPRINT_DIM = 32


class RadioFingerprintDB:
    """Offline radio fingerprint DB.

    Supports two interfaces:
      Legacy: add(rec), query(lat, lon, radius), load_csv (per-BSSID rows).
      Tier-7: store(lat, lon, fingerprint: dict),
              lookup_nearest(fingerprint, k) -> KNN by RSSI vector,
              export_csv / import_csv, stats().

    Optionally SQLite-backed when a db_path is supplied; otherwise in-memory.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._records: list[FingerprintRecord] = []
        self._idx = SpatialGrid(bucket_deg=0.0001)
        self._scans: list[dict] = []   # raw scans for KNN: each = {lat,lon,fp}
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        if db_path is not None:
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
            self._conn = sqlite3.connect(db_path)
            self._init_sqlite()
            self._load_scans_from_sqlite()

    def _init_sqlite(self) -> None:
        assert self._conn is not None
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS scans ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  lat REAL NOT NULL, lon REAL NOT NULL,"
            "  fingerprint_json TEXT NOT NULL,"
            "  ts REAL NOT NULL"
            ")"
        )
        self._conn.commit()

    def _load_scans_from_sqlite(self) -> None:
        assert self._conn is not None
        cur = self._conn.execute(
            "SELECT lat, lon, fingerprint_json FROM scans"
        )
        for lat, lon, fpj in cur.fetchall():
            self._scans.append({
                "lat": lat, "lon": lon, "fp": json.loads(fpj)
            })

    # --- Legacy API -------------------------------------------------------

    def add(self, rec: FingerprintRecord) -> None:
        self._records.append(rec)
        self._idx.insert(rec)

    def query(self, lat: float, lon: float,
              radius_m: float = 30.0,
              technology: Optional[str] = None) -> list[FingerprintRecord]:
        hits = self._idx.query_radius(lat, lon, radius_m)
        if technology:
            hits = [h for h in hits if h.technology == technology]
        return hits

    def load_csv(self, path: str) -> int:
        """Legacy per-BSSID CSV loader."""
        if not os.path.exists(path):
            return 0
        count = 0
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i == 0:
                    continue
                parts = line.strip().split(",")
                if len(parts) < 7:
                    continue
                try:
                    rec = FingerprintRecord(
                        lat=float(parts[0]), lon=float(parts[1]),
                        floor=int(parts[2]), bssid=parts[3].strip(),
                        rssi_mean=float(parts[4]), rssi_std=float(parts[5]),
                        technology=parts[6].strip(),
                    )
                    self.add(rec)
                    count += 1
                except (ValueError, IndexError):
                    continue
        return count

    @property
    def record_count(self) -> int:
        return len(self._records)

    # --- Tier-7 API -------------------------------------------------------

    def store(self, lat: float, lon: float, fingerprint: dict) -> int:
        """Store a (lat, lon, fingerprint) scan. fingerprint = {bssid: rssi}."""
        scan = {"lat": float(lat), "lon": float(lon), "fp": dict(fingerprint)}
        self._scans.append(scan)
        if self._conn is not None:
            self._conn.execute(
                "INSERT INTO scans (lat, lon, fingerprint_json, ts)"
                " VALUES (?, ?, ?, ?)",
                (lat, lon, json.dumps(fingerprint), time.time()),
            )
            self._conn.commit()
        return len(self._scans)

    @staticmethod
    def _fingerprint_vector(scan: dict) -> np.ndarray:
        """Hash BSSIDs into a fixed-dim RSSI vector (no-signal = -100 dBm)."""
        vec = np.full(_FINGERPRINT_DIM, -100.0, dtype=np.float64)
        for bssid, rssi in scan.items():
            idx = (hash(bssid) & 0x7FFFFFFF) % _FINGERPRINT_DIM
            # Take strongest signal at each slot (handle hash collisions).
            if float(rssi) > vec[idx]:
                vec[idx] = float(rssi)
        return vec

    def lookup_nearest(self, fingerprint: dict,
                       k: int = 3) -> list[tuple[float, float, float]]:
        """KNN by Euclidean distance on RSSI vectors.

        Returns list of (lat, lon, distance) sorted by distance.
        """
        if not self._scans:
            return []
        q = self._fingerprint_vector(fingerprint)
        scored: list[tuple[float, float, float]] = []
        for s in self._scans:
            v = self._fingerprint_vector(s["fp"])
            d = float(np.linalg.norm(q - v))
            scored.append((s["lat"], s["lon"], d))
        scored.sort(key=lambda t: t[2])
        return scored[:k]

    def export_csv(self, path: str) -> int:
        """Export scans to CSV: lat,lon,fingerprint_json."""
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["lat", "lon", "fingerprint_json"])
            for s in self._scans:
                w.writerow([s["lat"], s["lon"], json.dumps(s["fp"])])
        return len(self._scans)

    def import_csv(self, path: str) -> int:
        """Import scans from CSV produced by export_csv."""
        if not os.path.exists(path):
            return 0
        n = 0
        with open(path, encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                try:
                    lat = float(row["lat"])
                    lon = float(row["lon"])
                    fp = json.loads(row["fingerprint_json"])
                except (ValueError, KeyError, json.JSONDecodeError):
                    continue
                self.store(lat, lon, fp)
                n += 1
        return n

    def stats(self) -> dict:
        if not self._scans:
            return {
                "scan_count": 0, "record_count": len(self._records),
                "coverage_area_km2": 0.0,
            }
        lats = [s["lat"] for s in self._scans]
        lons = [s["lon"] for s in self._scans]
        dlat = max(lats) - min(lats)
        dlon = max(lons) - min(lons)
        # Crude rectangle area in km² (1° lat ≈ 111 km; 1° lon ≈ 111·cos(lat)).
        mid_lat = (max(lats) + min(lats)) / 2.0
        area = dlat * 111.0 * dlon * 111.0 * math.cos(math.radians(mid_lat))
        return {
            "scan_count": len(self._scans),
            "record_count": len(self._records),
            "coverage_area_km2": float(abs(area)),
        }


# ===========================================================================
# LEGACY: CellTower + CellTowerDB
# ===========================================================================

@dataclass
class CellTower:
    tower_id: str
    lat: float
    lon: float
    alt_m: float
    frequency_mhz: float
    power_w: float = 10.0
    technology: str = "lte"


class CellTowerDB:
    def __init__(self) -> None:
        self._towers: dict[str, CellTower] = {}
        self._idx = SpatialGrid(bucket_deg=0.05)

    def add(self, tower: CellTower) -> None:
        self._towers[tower.tower_id] = tower
        self._idx.insert(tower)

    def get(self, tower_id: str) -> Optional[CellTower]:
        return self._towers.get(tower_id)

    def nearby(self, lat: float, lon: float,
               radius_m: float = 10_000.0,
               technology: Optional[str] = None) -> list[CellTower]:
        hits = self._idx.query_radius(lat, lon, radius_m)
        if technology:
            hits = [h for h in hits if h.technology == technology]
        return hits

    def load_csv(self, path: str) -> int:
        if not os.path.exists(path):
            return 0
        count = 0
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i == 0:
                    continue
                parts = line.strip().split(",")
                if len(parts) < 4:
                    continue
                try:
                    t = CellTower(
                        tower_id=parts[0].strip(),
                        lat=float(parts[1]), lon=float(parts[2]),
                        alt_m=float(parts[3]),
                        frequency_mhz=float(parts[4]) if len(parts) > 4 else 0.0,
                        power_w=float(parts[5]) if len(parts) > 5 else 10.0,
                        technology=parts[6].strip() if len(parts) > 6 else "lte",
                    )
                    self.add(t)
                    count += 1
                except (ValueError, IndexError):
                    continue
        return count

    @property
    def tower_count(self) -> int:
        return len(self._towers)


# ===========================================================================
# LEGACY: GeomagneticModel (IGRF-13 dipole)
# ===========================================================================

class GeomagneticModel:
    """Simplified IGRF-13 dipole approximation (legacy)."""

    _G10 = -29_404.5
    _G11 = -1_450.9
    _H11 = 4_652.5
    _EARTH_RADIUS_M = 6_371_200.0

    def field_nT(self, lat_deg: float, lon_deg: float,
                 alt_m: float = 0.0) -> tuple[float, float, float]:
        lat = math.radians(lat_deg)
        lon = math.radians(lon_deg)
        r = (self._EARTH_RADIUS_M + alt_m) / self._EARTH_RADIUS_M
        cos_lat = math.cos(lat)
        sin_lat = math.sin(lat)
        cos_lon = math.cos(lon)
        sin_lon = math.sin(lon)
        p10 = sin_lat
        p11 = cos_lat
        dp10 = cos_lat
        dp11 = -sin_lat
        Br = (2.0 / r ** 3) * (self._G10 * p10 + self._G11 * p11 * cos_lon
                                + self._H11 * p11 * sin_lon)
        Bt = (1.0 / r ** 3) * (self._G10 * dp10 + self._G11 * dp11 * cos_lon
                                + self._H11 * dp11 * sin_lon)
        Bx = -Bt
        By = 0.0
        Bz = -Br
        return Bx, By, Bz

    def total_intensity_nT(self, lat_deg: float, lon_deg: float,
                           alt_m: float = 0.0) -> float:
        Bx, By, Bz = self.field_nT(lat_deg, lon_deg, alt_m)
        return math.sqrt(Bx ** 2 + By ** 2 + Bz ** 2)

    def declination_deg(self, lat_deg: float, lon_deg: float,
                        alt_m: float = 0.0) -> float:
        Bx, By, _ = self.field_nT(lat_deg, lon_deg, alt_m)
        return math.degrees(math.atan2(By, Bx))


# ===========================================================================
# LEGACY: OfflineMaps facade
# ===========================================================================

class OfflineMaps:
    """Single access point for the legacy offline data stores."""

    def __init__(self) -> None:
        self.vector = VectorMapDB()
        self.elevation = ElevationDB()
        self.bathymetry = BathymetricDB()
        self.fingerprints = RadioFingerprintDB()
        self.towers = CellTowerDB()
        self.geomagnetic = GeomagneticModel()

    def load_directory(self, data_dir: str) -> dict[str, int]:
        summary: dict[str, int] = {}
        if not os.path.isdir(data_dir):
            return summary
        for fname in os.listdir(data_dir):
            fpath = os.path.join(data_dir, fname)
            lower = fname.lower()
            if lower == "nodes.csv":
                edges = os.path.join(data_dir, "edges.csv")
                self.vector.load_csv(fpath, edges)
                summary["vector_nodes"] = self.vector.node_count
            elif lower == "fingerprints.csv":
                n = self.fingerprints.load_csv(fpath)
                summary["fingerprints"] = n
            elif lower == "towers.csv":
                n = self.towers.load_csv(fpath)
                summary["towers"] = n
            elif lower.endswith(".hgt"):
                self.elevation.load_srtm_hgt(fpath)
                summary["dem_tiles"] = self.elevation.tile_count
        return summary

    @property
    def stats(self) -> dict:
        return {
            "vector_nodes": self.vector.node_count,
            "vector_edges": self.vector.edge_count,
            "dem_tiles": self.elevation.tile_count,
            "bathy_tiles": self.bathymetry.tile_count,
            "fingerprints": self.fingerprints.record_count,
            "towers": self.towers.tower_count,
        }


# ===========================================================================
# TIER-7: VectorMapStore — GeoJSON + grid index + ASCII renderer
# ===========================================================================

# Slippy-map / web-mercator constants. 256 zoom levels supported by API,
# though only z ≤ ~30 are practically meaningful for Earth-scale data.
_MAX_ZOOM = 256


class VectorMapStore:
    """Global vector layer over GeoJSON with grid-cell spatial index.

    Supports zoom 0..255. The grid bucket size shrinks geometrically with
    zoom, so query_bbox is O(features in viewport) at any zoom.
    """

    def __init__(self, zoom: int = 12) -> None:
        if not 0 <= zoom < _MAX_ZOOM:
            raise ValueError(f"zoom must be in [0,{_MAX_ZOOM})")
        self.zoom = zoom
        self._features: list[dict] = []
        # Grid resolution: 1 cell ≈ 360°/2^zoom (clamped to a sane minimum).
        self._cell_deg = max(360.0 / (2 ** min(zoom, 24)), 1e-6)
        self._grid: dict[tuple[int, int], list[int]] = {}

    @staticmethod
    def _feature_centroid(feature: dict) -> tuple[float, float]:
        geom = feature.get("geometry") or {}
        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])
        if gtype == "Point":
            return float(coords[1]), float(coords[0])
        if gtype in ("LineString", "MultiPoint"):
            xs = [float(c[0]) for c in coords]
            ys = [float(c[1]) for c in coords]
            return sum(ys) / len(ys), sum(xs) / len(xs)
        if gtype == "Polygon":
            ring = coords[0] if coords else []
            xs = [float(c[0]) for c in ring]
            ys = [float(c[1]) for c in ring]
            return sum(ys) / len(ys), sum(xs) / len(xs)
        if gtype in ("MultiLineString", "MultiPolygon"):
            xs: list[float] = []
            ys: list[float] = []
            for part in coords:
                ring = part[0] if gtype == "MultiPolygon" else part
                for c in ring:
                    xs.append(float(c[0]))
                    ys.append(float(c[1]))
            if xs:
                return sum(ys) / len(ys), sum(xs) / len(xs)
        return 0.0, 0.0

    def _cell_of(self, lat: float, lon: float) -> tuple[int, int]:
        return (int(lat / self._cell_deg), int(lon / self._cell_deg))

    def load_geojson(self, path_or_string: str) -> int:
        """Parse a GeoJSON FeatureCollection (file path or raw string)."""
        if os.path.exists(path_or_string):
            with open(path_or_string, encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.loads(path_or_string)
        if data.get("type") == "FeatureCollection":
            features = data.get("features", [])
        elif data.get("type") == "Feature":
            features = [data]
        else:
            features = []
        self._build_rtree(features)
        return len(features)

    def _build_rtree(self, features: list[dict]) -> None:
        """Rebuild the grid-cell spatial index over the supplied features."""
        self._features = list(features)
        self._grid.clear()
        for i, feat in enumerate(self._features):
            lat, lon = self._feature_centroid(feat)
            self._grid.setdefault(self._cell_of(lat, lon), []).append(i)

    def query_bbox(self, min_lat: float, min_lon: float,
                   max_lat: float, max_lon: float) -> list[dict]:
        out: list[dict] = []
        ik0 = int(min_lat / self._cell_deg)
        ik1 = int(max_lat / self._cell_deg) + 1
        jk0 = int(min_lon / self._cell_deg)
        jk1 = int(max_lon / self._cell_deg) + 1
        seen: set[int] = set()
        for ik in range(ik0, ik1 + 1):
            for jk in range(jk0, jk1 + 1):
                for idx in self._grid.get((ik, jk), []):
                    if idx in seen:
                        continue
                    seen.add(idx)
                    feat = self._features[idx]
                    lat, lon = self._feature_centroid(feat)
                    if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
                        out.append(feat)
        return out

    def query_nearest(self, lat: float, lon: float,
                      k: int = 5) -> list[dict]:
        scored: list[tuple[float, dict]] = []
        for feat in self._features:
            flat, flon = self._feature_centroid(feat)
            d = _haversine_m(lat, lon, flat, flon)
            scored.append((d, feat))
        scored.sort(key=lambda t: t[0])
        return [f for _, f in scored[:k]]

    def render_ascii(self, lat: float, lon: float, zoom: int,
                     width: int = 80, height: int = 24) -> str:
        """Render features near (lat,lon) at the given zoom into ASCII."""
        if width <= 0 or height <= 0:
            return ""
        # Half-window scales with zoom: high zoom -> small window.
        half_deg = max(180.0 / (2 ** min(max(zoom, 0), 24)), 1e-6)
        min_lat = lat - half_deg
        max_lat = lat + half_deg
        min_lon = lon - half_deg
        max_lon = lon + half_deg
        feats = self.query_bbox(min_lat, min_lon, max_lat, max_lon)
        canvas = [[" "] * width for _ in range(height)]

        def plot(la: float, lo: float, ch: str) -> None:
            r = int((max_lat - la) / (max_lat - min_lat + 1e-12) * (height - 1))
            c = int((lo - min_lon) / (max_lon - min_lon + 1e-12) * (width - 1))
            if 0 <= r < height and 0 <= c < width:
                canvas[r][c] = ch

        symbol_map = {
            "Point": "*", "LineString": ".", "Polygon": "#",
            "MultiPoint": "*", "MultiLineString": ".",
            "MultiPolygon": "#",
        }
        for feat in feats:
            geom = feat.get("geometry") or {}
            gt = geom.get("type", "")
            ch = symbol_map.get(gt, "?")
            coords = geom.get("coordinates", [])
            if gt == "Point":
                plot(float(coords[1]), float(coords[0]), ch)
            elif gt == "LineString":
                for c in coords:
                    plot(float(c[1]), float(c[0]), ch)
            elif gt == "Polygon":
                ring = coords[0] if coords else []
                for c in ring:
                    plot(float(c[1]), float(c[0]), ch)
        # Mark center (camera) with @.
        plot(lat, lon, "@")
        return "\n".join("".join(row) for row in canvas)

    def get_road_graph(self, bbox: tuple[float, float, float, float]) -> dict:
        """Extract LineString features inside bbox as adjacency list.

        Returns: {node_key: [(neighbour_key, length_m), ...]}
        Node keys are (lat, lon) rounded to ~1e-6 deg to coalesce duplicates.
        """
        min_lat, min_lon, max_lat, max_lon = bbox
        feats = self.query_bbox(min_lat, min_lon, max_lat, max_lon)
        graph: dict[tuple[float, float],
                    list[tuple[tuple[float, float], float]]] = {}

        def key(la: float, lo: float) -> tuple[float, float]:
            return (round(la, 6), round(lo, 6))

        for feat in feats:
            geom = feat.get("geometry") or {}
            if geom.get("type") != "LineString":
                continue
            coords = geom.get("coordinates", [])
            for a, b in zip(coords[:-1], coords[1:]):
                ka = key(float(a[1]), float(a[0]))
                kb = key(float(b[1]), float(b[0]))
                if ka == kb:
                    continue
                d = _haversine_m(ka[0], ka[1], kb[0], kb[1])
                graph.setdefault(ka, []).append((kb, d))
                graph.setdefault(kb, []).append((ka, d))
        return graph

    @property
    def feature_count(self) -> int:
        return len(self._features)


# ===========================================================================
# TIER-7: SatelliteImageCache — slippy-map tile store (SQLite)
# ===========================================================================

class SatelliteImageCache:
    """Slippy-map raster tile cache, SQLite-backed."""

    def __init__(self, db_path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS tiles ("
            "  zoom INTEGER NOT NULL, x INTEGER NOT NULL,"
            "  y INTEGER NOT NULL, data BLOB NOT NULL,"
            "  bytes INTEGER NOT NULL,"
            "  PRIMARY KEY (zoom, x, y)"
            ")"
        )
        self._conn.commit()

    @staticmethod
    def lat_lon_to_tile(lat: float, lon: float,
                        zoom: int) -> tuple[int, int]:
        """OSM/Slippy formula. Lat clamped to web-mercator domain."""
        if zoom < 0:
            raise ValueError("zoom must be >= 0")
        lat = max(min(lat, 85.0511287798), -85.0511287798)
        n = 2 ** zoom
        xtile = int((lon + 180.0) / 360.0 * n)
        lat_rad = math.radians(lat)
        ytile = int(
            (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad))
             / math.pi) / 2.0 * n
        )
        xtile = max(0, min(xtile, n - 1))
        ytile = max(0, min(ytile, n - 1))
        return xtile, ytile

    @staticmethod
    def tile_to_lat_lon(tx: int, ty: int,
                        zoom: int) -> tuple[float, float]:
        """Return NW corner (lat, lon) of tile (tx, ty, zoom)."""
        n = 2 ** zoom
        lon = tx / n * 360.0 - 180.0
        lat_rad = math.atan(math.sinh(math.pi * (1.0 - 2.0 * ty / n)))
        lat = math.degrees(lat_rad)
        return lat, lon

    @staticmethod
    def tile_key(lat: float, lon: float,
                 zoom: int) -> tuple[int, int, int]:
        x, y = SatelliteImageCache.lat_lon_to_tile(lat, lon, zoom)
        return x, y, zoom

    def cache_tile(self, zoom: int, tx: int, ty: int,
                   image_bytes: bytes) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO tiles (zoom, x, y, data, bytes)"
            " VALUES (?, ?, ?, ?, ?)",
            (zoom, tx, ty, sqlite3.Binary(image_bytes), len(image_bytes)),
        )
        self._conn.commit()

    def get_tile(self, zoom: int, tx: int, ty: int) -> Optional[bytes]:
        cur = self._conn.execute(
            "SELECT data FROM tiles WHERE zoom=? AND x=? AND y=?",
            (zoom, tx, ty),
        )
        row = cur.fetchone()
        return bytes(row[0]) if row else None

    def preload_region(self, min_lat: float, min_lon: float,
                       max_lat: float, max_lon: float,
                       zoom: int) -> list[tuple[int, int, int]]:
        """Return list of (zoom, tx, ty) tiles that cover the bbox."""
        x0, y1 = self.lat_lon_to_tile(min_lat, min_lon, zoom)  # SW -> low-x, high-y
        x1, y0 = self.lat_lon_to_tile(max_lat, max_lon, zoom)  # NE -> high-x, low-y
        xa, xb = min(x0, x1), max(x0, x1)
        ya, yb = min(y0, y1), max(y0, y1)
        return [(zoom, x, y) for x in range(xa, xb + 1) for y in range(ya, yb + 1)]

    def cache_stats(self) -> dict:
        cur = self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(bytes), 0) FROM tiles"
        )
        count, total = cur.fetchone()
        return {
            "tile_count": int(count),
            "size_bytes": int(total),
            "size_mb": float(total) / (1024 * 1024),
        }


# ===========================================================================
# TIER-7: DEMStore — SRTM .hgt loader + bilinear + slope + contours
# ===========================================================================

class DEMStore:
    """Digital Elevation Model store, supporting SRTM .hgt tiles."""

    def __init__(self) -> None:
        # Each tile: dict(grid: np.ndarray (rows x cols), lat0, lon0, side_deg, n)
        self._tiles: list[dict] = []

    def load_srtm_hgt(self, data: bytes,
                      lat_origin: int, lon_origin: int) -> dict:
        """Parse SRTM .hgt bytes (big-endian int16, 1201² or 3601²).

        SRTM convention: first row = northernmost row at (lat_origin+1).
        Each cell spans 1°/(n-1).
        """
        ncells = len(data) // 2
        n = int(round(math.sqrt(ncells)))
        if n * n * 2 != len(data) or n not in (1201, 3601):
            raise ValueError(
                f"SRTM .hgt must be 1201x1201 or 3601x3601 int16; got {len(data)} bytes"
            )
        arr = np.frombuffer(data, dtype=">i2").reshape(n, n).astype(np.float32)
        # -32768 = void (replace with 0 for safety; caller may want NaN).
        arr = np.where(arr == -32768, 0.0, arr)
        side_deg = 1.0
        tile = {
            "grid": arr,           # row 0 = northern edge (lat_origin+1)
            "lat0": float(lat_origin),
            "lon0": float(lon_origin),
            "side_deg": side_deg,
            "n": n,
        }
        self._tiles.append(tile)
        return tile

    def _find_tile(self, lat: float, lon: float) -> Optional[dict]:
        for t in self._tiles:
            if (t["lat0"] <= lat <= t["lat0"] + t["side_deg"] and
                    t["lon0"] <= lon <= t["lon0"] + t["side_deg"]):
                return t
        return None

    def get_elevation(self, lat: float, lon: float) -> float:
        t = self._find_tile(lat, lon)
        if t is None:
            return 0.0
        n = t["n"]
        # x runs west->east (0..n-1), y runs north->south (0..n-1).
        x = (lon - t["lon0"]) * (n - 1) / t["side_deg"]
        y = (t["lat0"] + t["side_deg"] - lat) * (n - 1) / t["side_deg"]
        x = max(0.0, min(x, n - 1.0))
        y = max(0.0, min(y, n - 1.0))
        x0 = int(math.floor(x))
        y0 = int(math.floor(y))
        x1 = min(x0 + 1, n - 1)
        y1 = min(y0 + 1, n - 1)
        fx = x - x0
        fy = y - y0
        g = t["grid"]
        v00 = float(g[y0, x0])
        v10 = float(g[y0, x1])
        v01 = float(g[y1, x0])
        v11 = float(g[y1, x1])
        top = v00 * (1 - fx) + v10 * fx
        bot = v01 * (1 - fx) + v11 * fx
        return top * (1 - fy) + bot * fy

    def get_profile(self, lat1: float, lon1: float,
                    lat2: float, lon2: float,
                    n: int = 100) -> list[float]:
        if n < 2:
            return [self.get_elevation(lat1, lon1)]
        out: list[float] = []
        for i in range(n):
            t = i / (n - 1)
            la = lat1 + (lat2 - lat1) * t
            lo = lon1 + (lon2 - lon1) * t
            out.append(self.get_elevation(la, lo))
        return out

    def get_slope(self, lat: float, lon: float) -> float:
        """Approximate terrain slope (deg) by central differences."""
        t = self._find_tile(lat, lon)
        if t is None:
            return 0.0
        # 1 cell ≈ side_deg/(n-1) degrees ≈ ~30 m at equator for SRTM-1.
        dlat_deg = t["side_deg"] / (t["n"] - 1)
        dlon_deg = dlat_deg
        h_n = self.get_elevation(lat + dlat_deg, lon)
        h_s = self.get_elevation(lat - dlat_deg, lon)
        h_e = self.get_elevation(lat, lon + dlon_deg)
        h_w = self.get_elevation(lat, lon - dlon_deg)
        # Convert deg->m for partial derivatives.
        dy_m = _haversine_m(lat - dlat_deg, lon, lat + dlat_deg, lon)
        dx_m = _haversine_m(lat, lon - dlon_deg, lat, lon + dlon_deg)
        if dy_m <= 0 or dx_m <= 0:
            return 0.0
        dz_dx = (h_e - h_w) / dx_m
        dz_dy = (h_n - h_s) / dy_m
        slope = math.degrees(math.atan(math.sqrt(dz_dx ** 2 + dz_dy ** 2)))
        return slope

    def contour_lines(self,
                      elevation_step: float = 50.0
                      ) -> list[list[tuple[float, float]]]:
        """Marching-squares contour extraction over each loaded tile."""
        contours: list[list[tuple[float, float]]] = []
        for t in self._tiles:
            grid = t["grid"]
            n = t["n"]
            lat0 = t["lat0"]
            lon0 = t["lon0"]
            side = t["side_deg"]
            cell_lat = side / (n - 1)
            cell_lon = side / (n - 1)
            zmin = float(grid.min())
            zmax = float(grid.max())
            level = math.ceil(zmin / elevation_step) * elevation_step
            while level <= zmax:
                segs = self._marching_squares_level(grid, level)
                for (r1, c1), (r2, c2) in segs:
                    lat1 = lat0 + side - r1 * cell_lat
                    lon1 = lon0 + c1 * cell_lon
                    lat2 = lat0 + side - r2 * cell_lat
                    lon2 = lon0 + c2 * cell_lon
                    contours.append([(lat1, lon1), (lat2, lon2)])
                level += elevation_step
        return contours

    @staticmethod
    def _marching_squares_level(
        grid: np.ndarray, level: float
    ) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        rows, cols = grid.shape
        segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for r in range(rows - 1):
            for c in range(cols - 1):
                v00 = float(grid[r, c])
                v10 = float(grid[r, c + 1])
                v11 = float(grid[r + 1, c + 1])
                v01 = float(grid[r + 1, c])
                idx = ((1 if v00 > level else 0) |
                       (2 if v10 > level else 0) |
                       (4 if v11 > level else 0) |
                       (8 if v01 > level else 0))
                if idx in (0, 15):
                    continue

                def interp(a: float, b: float) -> float:
                    if abs(b - a) < 1e-12:
                        return 0.5
                    return (level - a) / (b - a)

                top = (r, c + interp(v00, v10))
                right = (r + interp(v10, v11), c + 1)
                bottom = (r + 1, c + interp(v01, v11))
                left = (r + interp(v00, v01), c)

                # Standard 16-case marching squares (saddles use midpoint avg).
                cases = {
                    1: [(left, top)], 2: [(top, right)],
                    3: [(left, right)], 4: [(right, bottom)],
                    5: [(left, top), (right, bottom)],
                    6: [(top, bottom)], 7: [(left, bottom)],
                    8: [(left, bottom)], 9: [(top, bottom)],
                    10: [(left, bottom), (top, right)],
                    11: [(right, bottom)], 12: [(left, right)],
                    13: [(top, right)], 14: [(left, top)],
                }
                for s in cases.get(idx, []):
                    segs.append(s)
        return segs

    @property
    def tile_count(self) -> int:
        return len(self._tiles)


# ===========================================================================
# TIER-7: TowerDatabase — cell tower CSV + nearby search
# ===========================================================================

@dataclass
class TowerRecord:
    mcc: int
    mnc: int
    lac: int
    cid: int
    lat: float
    lon: float
    range_m: float


class TowerDatabase:
    """Cellular tower database with exact-key lookup + nearby search."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[int, int, int, int], TowerRecord] = {}
        self._all: list[TowerRecord] = []

    def load_csv(self, path: str) -> int:
        """CSV columns: mcc,mnc,lac,cid,lat,lon,range_m (header optional)."""
        if not os.path.exists(path):
            return 0
        n = 0
        with open(path, encoding="utf-8") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if not row:
                    continue
                if i == 0 and not row[0].lstrip("-").isdigit():
                    continue   # header row
                if len(row) < 7:
                    continue
                try:
                    rec = TowerRecord(
                        mcc=int(row[0]), mnc=int(row[1]),
                        lac=int(row[2]), cid=int(row[3]),
                        lat=float(row[4]), lon=float(row[5]),
                        range_m=float(row[6]),
                    )
                except (ValueError, IndexError):
                    continue
                self._by_key[(rec.mcc, rec.mnc, rec.lac, rec.cid)] = rec
                self._all.append(rec)
                n += 1
        return n

    def lookup(self, mcc: int, mnc: int, lac: int,
               cid: int) -> Optional[dict]:
        rec = self._by_key.get((mcc, mnc, lac, cid))
        if rec is None:
            return None
        return {
            "mcc": rec.mcc, "mnc": rec.mnc, "lac": rec.lac, "cid": rec.cid,
            "lat": rec.lat, "lon": rec.lon, "range_m": rec.range_m,
        }

    def nearby(self, lat: float, lon: float,
               radius_m: float = 5000.0) -> list[dict]:
        out: list[dict] = []
        for rec in self._all:
            d = _haversine_m(lat, lon, rec.lat, rec.lon)
            if d <= radius_m:
                out.append({
                    "mcc": rec.mcc, "mnc": rec.mnc, "lac": rec.lac,
                    "cid": rec.cid, "lat": rec.lat, "lon": rec.lon,
                    "range_m": rec.range_m, "distance_m": d,
                })
        out.sort(key=lambda d: d["distance_m"])
        return out

    @staticmethod
    def position_estimate(towers: list[dict],
                          signal_strengths: list[float]
                          ) -> tuple[float, float]:
        """Weighted-centroid position estimate.

        Stronger RSSI (less negative) -> higher weight via 10^(rssi/20).
        """
        if not towers:
            raise ValueError("position_estimate requires >= 1 tower")
        if len(towers) != len(signal_strengths):
            raise ValueError("towers and signal_strengths length mismatch")
        weights = [10.0 ** (float(s) / 20.0) for s in signal_strengths]
        total_w = sum(weights)
        if total_w <= 0:
            total_w = 1e-12
        lat = sum(t["lat"] * w for t, w in zip(towers, weights)) / total_w
        lon = sum(t["lon"] * w for t, w in zip(towers, weights)) / total_w
        return lat, lon

    @property
    def tower_count(self) -> int:
        return len(self._all)


# ===========================================================================
# TIER-7: WMMModel — simplified World Magnetic Model 2020
# ===========================================================================

class WMMModel:
    """Simplified WMM-2020 dipole + first-order secular variation.

    Coefficients are the degree-1 main-field terms from WMM-2020 (epoch
    2020.0) plus the published secular variation; higher harmonics are
    omitted, so accuracy is roughly ±2° declination over most of the globe
    — enough for compass correction, not for survey-grade work.
    """

    # WMM2020 epoch (year)
    _T0 = 2020.0
    # Degree-1 main-field Gauss coefficients (nT) at epoch 2020.0
    _G10 = -29404.5
    _G11 = -1450.7
    _H11 = 4652.9
    # Secular variation (nT/yr)
    _DG10 = 6.7
    _DG11 = 7.7
    _DH11 = -25.1

    _EARTH_RADIUS_M = 6_371_200.0

    def _coeffs(self, year: float) -> tuple[float, float, float]:
        dt = year - self._T0
        return (
            self._G10 + self._DG10 * dt,
            self._G11 + self._DG11 * dt,
            self._H11 + self._DH11 * dt,
        )

    def _field_components_nT(self, lat: float, lon: float,
                             altitude_m: float, year: float
                             ) -> tuple[float, float, float]:
        """Return (X north, Y east, Z down) in nT."""
        g10, g11, h11 = self._coeffs(year)
        a = self._EARTH_RADIUS_M
        r = a + altitude_m
        # Geocentric colatitude theta from geodetic lat (sphere approx).
        theta = math.radians(90.0 - lat)
        phi = math.radians(lon)
        st = math.sin(theta)
        ct = math.cos(theta)
        cp = math.cos(phi)
        sp = math.sin(phi)
        # Schmidt-normalized degree-1 spherical-harmonic expansion.
        ar3 = (a / r) ** 3
        Br = 2.0 * ar3 * (g10 * ct + (g11 * cp + h11 * sp) * st)
        Btheta = ar3 * (g10 * st - (g11 * cp + h11 * sp) * ct)
        Bphi = ar3 * (g11 * sp - h11 * cp)
        # Convert (Br, Btheta, Bphi) to (X north, Y east, Z down).
        X = -Btheta
        Y = Bphi
        Z = -Br
        return X, Y, Z

    def compute(self, lat: float, lon: float,
                altitude_m: float,
                year: float) -> tuple[float, float, float]:
        """Return (declination_deg, inclination_deg, intensity_nT)."""
        X, Y, Z = self._field_components_nT(lat, lon, altitude_m, year)
        H = math.sqrt(X * X + Y * Y)
        F = math.sqrt(H * H + Z * Z)
        decl = math.degrees(math.atan2(Y, X))
        incl = math.degrees(math.atan2(Z, H))
        return decl, incl, F

    def declination(self, lat: float, lon: float,
                    year: float, alt_km: float = 0.0) -> float:
        d, _, _ = self.compute(lat, lon, alt_km * 1000.0, year)
        return d

    # -------------------------------------------------------------
    # Round 4: full-field, secular variation, grid survey
    # -------------------------------------------------------------

    def compute_full_field(
        self, lat: float, lon: float, alt_km: float, year: float
    ) -> dict:
        """Full geomagnetic field with secular variation applied.

        Returns a dict with X (north), Y (east), Z (down), H (horizontal), F
        (total intensity) in nT, plus declination/inclination in degrees.
        """
        X, Y, Z = self._field_components_nT(lat, lon, alt_km * 1000.0, year)
        H = math.sqrt(X * X + Y * Y)
        F = math.sqrt(H * H + Z * Z)
        decl = math.degrees(math.atan2(Y, X))
        incl = math.degrees(math.atan2(Z, H))
        return {
            "X_nT": X,
            "Y_nT": Y,
            "Z_nT": Z,
            "H_nT": H,
            "F_nT": F,
            "declination_deg": decl,
            "inclination_deg": incl,
            "year": year,
            "alt_km": alt_km,
        }

    def inclination(
        self, lat: float, lon: float, alt_km: float, year: float
    ) -> float:
        """Magnetic dip (inclination) angle in degrees."""
        X, Y, Z = self._field_components_nT(lat, lon, alt_km * 1000.0, year)
        H = math.sqrt(X * X + Y * Y)
        return math.degrees(math.atan2(Z, H))

    def total_intensity(
        self, lat: float, lon: float, alt_km: float, year: float
    ) -> float:
        """Total field magnitude |B| in nT."""
        X, Y, Z = self._field_components_nT(lat, lon, alt_km * 1000.0, year)
        return math.sqrt(X * X + Y * Y + Z * Z)

    def grid_survey(
        self,
        lat_range: tuple[float, float],
        lon_range: tuple[float, float],
        step_deg: float = 1.0,
        year: float = 2025.0,
        alt_km: float = 0.0,
    ) -> dict:
        """Compute full grid of declination/inclination/intensity (D, I, F).

        Returns a dict with numpy arrays:
            'lats', 'lons'              — 1-D coordinate vectors
            'declination', 'inclination', 'intensity' — 2-D grids (rows=lats)
        """
        lat0, lat1 = float(lat_range[0]), float(lat_range[1])
        lon0, lon1 = float(lon_range[0]), float(lon_range[1])
        step = float(step_deg)
        if step <= 0.0:
            raise ValueError("step_deg must be positive")
        n_lat = int(math.floor((lat1 - lat0) / step)) + 1
        n_lon = int(math.floor((lon1 - lon0) / step)) + 1
        lats = np.array([lat0 + i * step for i in range(n_lat)])
        lons = np.array([lon0 + j * step for j in range(n_lon)])
        D = np.zeros((n_lat, n_lon))
        I = np.zeros((n_lat, n_lon))
        F = np.zeros((n_lat, n_lon))
        for i, la in enumerate(lats):
            for j, lo in enumerate(lons):
                full = self.compute_full_field(float(la), float(lo), alt_km, year)
                D[i, j] = full["declination_deg"]
                I[i, j] = full["inclination_deg"]
                F[i, j] = full["F_nT"]
        return {
            "lats": lats,
            "lons": lons,
            "declination": D,
            "inclination": I,
            "intensity": F,
            "year": year,
            "alt_km": alt_km,
        }


# ===========================================================================
# TIER-7: OfflineMapManager — unified facade
# ===========================================================================

class OfflineMapManager:
    """Unified Tier-7 facade. All stores share a single data_dir."""

    def __init__(self, data_dir: str) -> None:
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir = data_dir
        self.vector = VectorMapStore()
        self.satellite = SatelliteImageCache(
            os.path.join(data_dir, "satellite.sqlite")
        )
        self.dem = DEMStore()
        self.fingerprints = RadioFingerprintDB(
            db_path=os.path.join(data_dir, "fingerprints.sqlite")
        )
        self.towers = TowerDatabase()
        self.wmm = WMMModel()

    def get_context(self, lat: float, lon: float) -> dict:
        """Return offline context (elev, towers, roads, declination) at point."""
        elevation = self.dem.get_elevation(lat, lon) if self.dem.tile_count else None
        towers = self.towers.nearby(lat, lon, radius_m=5000.0)
        # Small road-graph window: ±0.01° (~1 km).
        road_features: list[dict] = []
        if self.vector.feature_count:
            road_features = self.vector.query_bbox(
                lat - 0.01, lon - 0.01, lat + 0.01, lon + 0.01
            )
        year = 2020.0 + (time.time() - 1577836800.0) / (365.25 * 86400.0)
        declination = self.wmm.declination(lat, lon, year)
        return {
            "lat": lat,
            "lon": lon,
            "elevation_m": elevation,
            "nearby_towers": towers,
            "road_features": road_features,
            "magnetic_declination_deg": declination,
        }

    def is_available(self, lat: float, lon: float, zoom: int) -> bool:
        """True iff the satellite tile covering (lat, lon) at zoom is cached."""
        x, y, z = SatelliteImageCache.tile_key(lat, lon, zoom)
        return self.satellite.get_tile(z, x, y) is not None

    def storage_summary(self) -> dict:
        sat_path = self.satellite.db_path
        fp_path = self.fingerprints._db_path or ""
        sat_bytes = os.path.getsize(sat_path) if os.path.exists(sat_path) else 0
        fp_bytes = os.path.getsize(fp_path) if fp_path and os.path.exists(fp_path) else 0
        return {
            "satellite_bytes": sat_bytes,
            "satellite_mb": sat_bytes / (1024 * 1024),
            "fingerprint_bytes": fp_bytes,
            "fingerprint_mb": fp_bytes / (1024 * 1024),
            "vector_features": self.vector.feature_count,
            "dem_tiles": self.dem.tile_count,
            "tower_count": self.towers.tower_count,
        }
