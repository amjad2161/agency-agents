"""
Tier 1 — REAL multi-constellation NMEA parser + GPS estimator.
Supports GPS, GLONASS, Galileo, BeiDou, QZSS, NavIC.
Replaces stub in satellite.py for real-world deployment.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from .types import Estimate, Pose, Position, Confidence, Velocity


CONSTELLATIONS = {
    "GP": "GPS", "GL": "GLONASS", "GA": "Galileo",
    "GB": "BeiDou", "GQ": "QZSS", "GI": "NavIC",
}


@dataclass
class GnssFix:
    constellation: str
    fix_quality: int          # 0=invalid, 1=GPS, 2=DGPS, 4=RTK fixed, 5=RTK float
    sats_used: int
    hdop: float               # horizontal dilution of precision
    lat: float
    lon: float
    alt: float
    raw_sentence: str


def parse_gga(sentence: str) -> GnssFix | None:
    """Parse $XXGGA sentence (Global Positioning System Fix Data).

    Format: $GPGGA,UTC,lat,N/S,lon,E/W,fix,sats,hdop,alt,M,geoid,M,age,refid*cs
    """
    parts = sentence.strip().split(",")
    if len(parts) < 15 or not parts[0].endswith("GGA"):
        return None
    try:
        prefix = parts[0][1:3]  # GP, GL, etc
        constellation = CONSTELLATIONS.get(prefix, "Unknown")
        fix_q = int(parts[6]) if parts[6] else 0
        if fix_q == 0:
            return None
        sats = int(parts[7]) if parts[7] else 0
        hdop = float(parts[8]) if parts[8] else 99.0
        # Lat: ddmm.mmmm
        lat_raw = parts[2]
        lat = (int(lat_raw[:2]) + float(lat_raw[2:]) / 60.0) if lat_raw else 0.0
        if parts[3] == "S": lat = -lat
        # Lon: dddmm.mmmm
        lon_raw = parts[4]
        lon = (int(lon_raw[:3]) + float(lon_raw[3:]) / 60.0) if lon_raw else 0.0
        if parts[5] == "W": lon = -lon
        alt = float(parts[9]) if parts[9] else 0.0
        return GnssFix(constellation, fix_q, sats, hdop, lat, lon, alt, sentence)
    except (ValueError, IndexError):
        return None


class MultiConstellationFusion:
    """Fuses fixes from all 6 constellations using HDOP-weighted average."""

    def __init__(self):
        self.fixes_by_const: dict[str, GnssFix] = {}

    def ingest(self, sentence: str) -> GnssFix | None:
        fix = parse_gga(sentence)
        if fix:
            self.fixes_by_const[fix.constellation] = fix
        return fix

    def fuse(self) -> Estimate:
        valid = list(self.fixes_by_const.values())
        if not valid:
            return Estimate(
                pose=Pose(Position(0.0, 0.0, 0.0)),
                confidence=Confidence(valid=False, source="multi-gnss-empty"),
                source="multi-gnss",
            )

        # HDOP-weighted average (lower HDOP = higher weight)
        total_w = 0.0
        lat_sum = lon_sum = alt_sum = 0.0
        for f in valid:
            w = 1.0 / max(f.hdop, 0.5)
            lat_sum += f.lat * w
            lon_sum += f.lon * w
            alt_sum += f.alt * w
            total_w += w
        avg_lat = lat_sum / total_w
        avg_lon = lon_sum / total_w
        avg_alt = alt_sum / total_w

        # Best HDOP for confidence reporting
        best_hdop = min(f.hdop for f in valid)
        # Rough horizontal accuracy: HDOP * 5m (typical GPS UERE)
        h_acc = best_hdop * 5.0
        # If RTK fixed quality (4), use cm-level
        if any(f.fix_quality == 4 for f in valid):
            h_acc = 0.02  # 2 cm
        elif any(f.fix_quality == 5 for f in valid):
            h_acc = 0.20  # 20 cm

        return Estimate(
            pose=Pose(Position(avg_lat, avg_lon, avg_alt)),
            confidence=Confidence(
                horizontal_m=h_acc,
                vertical_m=h_acc * 1.5,
                valid=True,
                source=f"multi-gnss-{len(valid)}-const",
            ),
            source="multi-gnss",
            raw={"constellations": list(self.fixes_by_const.keys()),
                 "best_hdop": best_hdop,
                 "rtk": any(f.fix_quality in (4, 5) for f in valid)},
            ts=datetime.now(timezone.utc),
        )

    def detect_spoofing(self) -> dict:
        """Cross-constellation consistency check.

        Returns dict with `spoofed: bool` and `reason: str`.
        Spoofing indicator: position difference > 50m between constellations.
        """
        if len(self.fixes_by_const) < 2:
            return {"spoofed": False, "reason": "insufficient-constellations"}
        positions = [(f.lat, f.lon) for f in self.fixes_by_const.values()]
        # Compute max pairwise distance (meters via haversine approx)
        import math
        def dist(a, b):
            lat1, lon1 = math.radians(a[0]), math.radians(a[1])
            lat2, lon2 = math.radians(b[0]), math.radians(b[1])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
            return 6371000 * 2 * math.atan2(math.sqrt(h), math.sqrt(1-h))
        max_d = max(dist(p1, p2) for i, p1 in enumerate(positions)
                                  for p2 in positions[i+1:])
        spoofed = max_d > 50.0
        return {"spoofed": spoofed, "reason": f"max_inter-const_dist={max_d:.1f}m",
                "threshold_m": 50.0}
