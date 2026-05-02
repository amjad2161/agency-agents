"""
GODSKILL Nav v11 — Tier 1: Multi-Constellation GNSS + RTK Estimator.
"""
from __future__ import annotations
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from .types import Confidence, Estimate, Position, Pose, Velocity

CONSTELLATIONS = {"GP":"GPS","GL":"GLONASS","GA":"Galileo","GB":"BeiDou","GQ":"QZSS","GI":"NavIC","GN":"Multi"}
FIX_INVALID=0; FIX_GPS=1; FIX_DGPS=2; FIX_PPS=3; FIX_RTK_FIXED=4; FIX_RTK_FLOAT=5; FIX_DEAD_RECK=6

@dataclass
class GnssFix:
    constellation: str
    fix_quality: int
    sats_used: int
    hdop: float
    lat: float
    lon: float
    alt: float
    raw_sentence: str

@dataclass
class RTKStatus:
    active: bool = False
    age_s: float = float("inf")
    ref_station_id: str = ""

def _nmea_checksum(sentence: str) -> bool:
    if "*" not in sentence:
        return True
    body, cs = sentence.rsplit("*", 1)
    body = body.lstrip("$")
    expected = 0
    for c in body:
        expected ^= ord(c)
    return expected == int(cs[:2], 16)

def parse_gga(sentence: str) -> Optional[GnssFix]:
    sentence = sentence.strip()
    if not _nmea_checksum(sentence):
        return None
    parts = sentence.split(",")
    if len(parts) < 10 or not parts[0].endswith("GGA"):
        return None
    try:
        prefix = parts[0][1:3]
        constellation = CONSTELLATIONS.get(prefix, "Unknown")
        fix_q = int(parts[6]) if parts[6] else FIX_INVALID
        if fix_q == FIX_INVALID:
            return None
        sats = int(parts[7]) if parts[7] else 0
        hdop = float(parts[8]) if parts[8] else 99.0
        lat_raw = parts[2]
        if not lat_raw:
            return None
        lat = int(lat_raw[:2]) + float(lat_raw[2:]) / 60.0
        if parts[3] == "S":
            lat = -lat
        lon_raw = parts[4]
        if not lon_raw:
            return None
        lon = int(lon_raw[:3]) + float(lon_raw[3:]) / 60.0
        if parts[5] == "W":
            lon = -lon
        alt = float(parts[9]) if parts[9] else 0.0
        return GnssFix(constellation, fix_q, sats, hdop, lat, lon, alt, sentence)
    except (ValueError, IndexError):
        return None

def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6_371_000.0
    f1, f2 = math.radians(lat1), math.radians(lat2)
    df = math.radians(lat2-lat1); dl = math.radians(lon2-lon1)
    a = math.sin(df/2)**2 + math.cos(f1)*math.cos(f2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

class SatelliteEstimator:
    def __init__(self, rtk_enabled: bool = True, spoofing_detection: bool = True) -> None:
        self.rtk_enabled = rtk_enabled
        self.spoofing_detection = spoofing_detection
        self._fixes: dict[str, GnssFix] = {}
        self._last: Optional[Estimate] = None

    def feed_nmea(self, sentence: str) -> Optional[GnssFix]:
        fix = parse_gga(sentence)
        if fix:
            self._fixes[fix.constellation] = fix
        return fix

    def feed_fix(self, fix: GnssFix) -> None:
        self._fixes[fix.constellation] = fix

    def update(self, raw: dict) -> Estimate:
        if "nmea" in raw:
            self.feed_nmea(raw["nmea"])
        elif "lat" in raw and "lon" in raw:
            fix = GnssFix(
                constellation=raw.get("constellation","GPS"),
                fix_quality=raw.get("fix_quality", FIX_GPS),
                sats_used=raw.get("sats", 0),
                hdop=raw.get("hdop", 1.0),
                lat=raw["lat"], lon=raw["lon"],
                alt=raw.get("alt", 0.0),
                raw_sentence="",
            )
            self._fixes[fix.constellation] = fix
        est = self._fuse()
        self._last = est
        return est

    def _fuse(self) -> Estimate:
        valid = [f for f in self._fixes.values() if f.fix_quality != FIX_INVALID]
        if not valid:
            return Estimate(
                pose=Pose(Position(0.0,0.0,0.0)),
                confidence=Confidence(valid=False, source="satellite-no-fix"),
                source="satellite",
            )
        total_w = 0.0; lat_s = lon_s = alt_s = 0.0
        for f in valid:
            w = 1.0 / max(f.hdop, 0.1)
            lat_s += f.lat*w; lon_s += f.lon*w; alt_s += f.alt*w; total_w += w
        avg_lat = lat_s/total_w; avg_lon = lon_s/total_w; avg_alt = alt_s/total_w
        best_hdop = min(f.hdop for f in valid)
        bq = max(f.fix_quality for f in valid)
        if bq == FIX_RTK_FIXED: h_acc, v_acc = 0.02, 0.03
        elif bq == FIX_RTK_FLOAT: h_acc, v_acc = 0.20, 0.40
        elif bq == FIX_DGPS: h_acc, v_acc = 1.0, 1.5
        else: h_acc, v_acc = best_hdop*5.0, best_hdop*8.0
        if len(valid) >= 3: h_acc *= 0.7
        return Estimate(
            pose=Pose(Position(avg_lat, avg_lon, avg_alt)),
            confidence=Confidence(horizontal_m=h_acc, vertical_m=v_acc, valid=True,
                                  source=f"satellite-{len(valid)}const"),
            source="satellite",
            raw={"constellations":[f.constellation for f in valid],
                 "fix_quality":bq,"rtk_fixed":bq==FIX_RTK_FIXED},
        )

    def check_spoofing(self) -> dict:
        fixes = list(self._fixes.values())
        if len(fixes) < 2:
            return {"spoofed":False,"reason":"insufficient-constellations","max_dist_m":0.0}
        positions = [(f.lat,f.lon) for f in fixes]
        max_d = 0.0
        for i,p1 in enumerate(positions):
            for p2 in positions[i+1:]:
                d = _haversine_m(p1[0],p1[1],p2[0],p2[1])
                if d > max_d: max_d = d
        THRESH = 50.0
        spoofed = max_d > THRESH
        return {"spoofed":spoofed,"reason":f"spread {max_d:.1f}m","max_dist_m":max_d}

    def detect_spoofing(self, raw: dict = None) -> bool:
        return self.check_spoofing()["spoofed"]

    def check_jamming(self, snr_db: float) -> bool:
        return snr_db < 25.0

    def get_estimate(self) -> Optional[Estimate]:
        est = self._fuse()
        if est.confidence.valid:
            self._last = est
            return est
        return self._last

    @property
    def active_constellations(self) -> list:
        return list(self._fixes.keys())

    def reset(self) -> None:
        self._fixes.clear(); self._last = None

__all__ = ["SatelliteEstimator","GnssFix","RTKStatus","parse_gga",
           "CONSTELLATIONS","FIX_GPS","FIX_DGPS","FIX_RTK_FIXED","FIX_RTK_FLOAT"]
