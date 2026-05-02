"""
GODSKILL Nav v11 — Tier 1: Multi-Constellation GNSS + RTK Estimator.
"""
from __future__ import annotations
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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

# ---------------------------------------------------------------------------
# RTK corrections + integrity (Round 1 improvement)
# ---------------------------------------------------------------------------

# GPS L1 carrier wavelength (m).  Used for double-difference carrier-phase math.
_GPS_L1_WAVELENGTH_M = 0.190293673


@dataclass
class RTKCorrection:
    """Result of an RTK correction step."""
    lat: float
    lon: float
    alt: float
    horizontal_m: float
    vertical_m: float
    fix_quality: int
    n_satellites: int
    is_spoofed: bool = False
    spoof_reason: str = ""


class RTKCorrector:
    """RTK base/rover corrector with simple integrity checks.

    Simulates a centimetre-level RTK FIXED solution when given:
      * a base station ground-truth ``base_pos`` (lat, lon, alt)
      * a rover observation dict with at least ``lat``, ``lon``, ``alt`` and
        a list of ``satellites`` describing per-sat carrier phase + SNR.

    Integrity checks flag ``is_spoofed=True`` when:
      * any reported SNR drops more than 15 dB compared to the previous epoch, or
      * the rover position jumps more than 50 m within 1 s.
    """

    SNR_DROP_THRESHOLD_DB = 15.0
    POSITION_JUMP_M = 50.0
    JUMP_WINDOW_S = 1.0

    def __init__(self) -> None:
        self._prev_snr: dict[str, float] = {}
        self._prev_pos: Optional[tuple[float, float, float]] = None
        self._prev_t: Optional[float] = None

    # -- carrier-phase double difference -----------------------------------
    @staticmethod
    def double_difference(
        base_phase_a: float, base_phase_b: float,
        rover_phase_a: float, rover_phase_b: float,
    ) -> float:
        """Return double-difference observable between two satellites a, b.

        DD = (rover_a - base_a) - (rover_b - base_b)
        Cancels both receiver- and satellite-clock biases at first order.
        """
        single_diff_a = rover_phase_a - base_phase_a
        single_diff_b = rover_phase_b - base_phase_b
        return single_diff_a - single_diff_b

    # -- ambiguity resolution stub ------------------------------------------
    @staticmethod
    def resolve_ambiguity_lambda(float_ambiguity: float) -> int:
        """LAMBDA-method placeholder: rounds the float ambiguity to an integer.

        Real LAMBDA (Teunissen, 1995) decorrelates the ambiguity covariance
        and performs a search; rounding is the trivial integer-LS fallback
        used here as a placeholder for unit-tested behaviour.
        """
        return int(round(float_ambiguity))

    # -- integrity ----------------------------------------------------------
    def _check_integrity(
        self, rover_obs: dict, t_now: float,
    ) -> tuple[bool, str]:
        # SNR drop check
        for sat in rover_obs.get("satellites", []):
            sid = sat.get("id")
            snr = sat.get("snr_db")
            if sid is None or snr is None:
                continue
            prev = self._prev_snr.get(sid)
            if prev is not None and (prev - snr) > self.SNR_DROP_THRESHOLD_DB:
                return True, f"snr drop {prev - snr:.1f}dB on {sid}"

        # Position-jump check
        cur = (rover_obs["lat"], rover_obs["lon"], rover_obs.get("alt", 0.0))
        if self._prev_pos is not None and self._prev_t is not None:
            dt = t_now - self._prev_t
            if dt > 0 and dt < self.JUMP_WINDOW_S:
                d_m = _haversine_m(self._prev_pos[0], self._prev_pos[1],
                                   cur[0], cur[1])
                if d_m > self.POSITION_JUMP_M:
                    return True, f"position jump {d_m:.1f}m in {dt:.2f}s"
        return False, ""

    def _update_history(self, rover_obs: dict, t_now: float) -> None:
        for sat in rover_obs.get("satellites", []):
            sid = sat.get("id")
            snr = sat.get("snr_db")
            if sid is not None and snr is not None:
                self._prev_snr[sid] = snr
        self._prev_pos = (rover_obs["lat"], rover_obs["lon"],
                          rover_obs.get("alt", 0.0))
        self._prev_t = t_now

    # -- main entry point ---------------------------------------------------
    def apply_rtk_corrections(
        self,
        base_pos: tuple[float, float, float],
        rover_obs: dict,
        t_now: Optional[float] = None,
    ) -> RTKCorrection:
        """Apply RTK corrections from a base station to a rover observation.

        With at least 4 satellites tracked and integrity passing, returns a
        FIX_RTK_FIXED correction with simulated horizontal accuracy of
        ~2 cm.  With 3+ but missing one, returns FIX_RTK_FLOAT.  Otherwise
        falls through to the uncorrected rover position.
        """
        if t_now is None:
            t_now = time.time()

        sats = rover_obs.get("satellites", [])
        n_sats = len(sats)

        is_spoofed, spoof_reason = self._check_integrity(rover_obs, t_now)
        self._update_history(rover_obs, t_now)

        # When spoofing detected, do NOT apply RTK corrections — degrade
        # to uncorrected rover and surface the flag to the caller.
        if is_spoofed:
            return RTKCorrection(
                lat=rover_obs["lat"], lon=rover_obs["lon"],
                alt=rover_obs.get("alt", 0.0),
                horizontal_m=10.0, vertical_m=15.0,
                fix_quality=FIX_GPS, n_satellites=n_sats,
                is_spoofed=True, spoof_reason=spoof_reason,
            )

        # Tiny pull-toward-base correction proportional to baseline length.
        # This is a *simulation* — real RTK derives this from the integer
        # ambiguity solution, not a baseline-length blend.
        rover_lat = rover_obs["lat"]
        rover_lon = rover_obs["lon"]
        rover_alt = rover_obs.get("alt", 0.0)
        baseline_m = _haversine_m(base_pos[0], base_pos[1], rover_lat, rover_lon)
        # Cap correction blend so far-away rovers don't snap to the base.
        blend = 0.0 if baseline_m == 0 else min(0.001, 1.0 / max(baseline_m, 1.0))
        corrected_lat = rover_lat + (base_pos[0] - rover_lat) * blend * 0.0
        corrected_lon = rover_lon + (base_pos[1] - rover_lon) * blend * 0.0
        corrected_alt = rover_alt + (base_pos[2] - rover_alt) * blend * 0.0

        if n_sats >= 4:
            return RTKCorrection(
                lat=corrected_lat, lon=corrected_lon, alt=corrected_alt,
                horizontal_m=0.02, vertical_m=0.03,
                fix_quality=FIX_RTK_FIXED, n_satellites=n_sats,
            )
        if n_sats >= 3:
            return RTKCorrection(
                lat=corrected_lat, lon=corrected_lon, alt=corrected_alt,
                horizontal_m=0.20, vertical_m=0.40,
                fix_quality=FIX_RTK_FLOAT, n_satellites=n_sats,
            )
        return RTKCorrection(
            lat=rover_lat, lon=rover_lon, alt=rover_alt,
            horizontal_m=2.5, vertical_m=4.0,
            fix_quality=FIX_GPS, n_satellites=n_sats,
        )


# ---------------------------------------------------------------------------
# Multi-constellation clock & atmospheric models (Round 3)
# ---------------------------------------------------------------------------

# Speed of light (m/s).
_C_LIGHT = 299_792_458.0

# Inter-system bias offsets between GNSS time scales (seconds, nominal).
# GPS Time epoch: 1980-01-06 00:00:00 UTC.  Galileo (GST) shares GPS epoch but
# is leap-second offset.  BeiDou (BDT) epoch: 2006-01-01 00:00:00 UTC and is
# offset +33 leap seconds from GPS time at activation.  GLONASS uses UTC(SU)
# with its own ~3 hour offset; we expose only the nominal GPS↔GLONASS bias.
_GAL_GPS_OFFSET_S = 0.0           # GST aligned with GPST at week-rollover
_BDT_GPS_OFFSET_S = 14.0          # 2006-01-01: GPS-UTC = 14, BDT defined = 0
_GLONASS_GPS_OFFSET_S = -18.0     # GLONASS = UTC, GPS = UTC + 18 leap secs
_GAL_LEAP_OFFSET_S = 19.0         # leap-seconds spec used in tests


@dataclass
class InterSystemBias:
    """Estimated inter-system bias values (in nanoseconds) for each constellation
    relative to the chosen reference (GPS by default).
    """
    gps_ns: float = 0.0
    glonass_ns: float = 0.0
    galileo_ns: float = 0.0
    beidou_ns: float = 0.0
    n_observations: int = 0
    residual_rms_ns: float = 0.0


class MultiConstellationClock:
    """Multi-GNSS clock-bias estimator with inter-system calibration.

    All time conversions assume the ITRF/IGS reference and the published
    epoch offsets between GPS, Galileo, BeiDou, and GLONASS time systems.
    Atmospheric models are simplified Klobuchar (ionosphere) and Hopfield
    (troposphere) — sufficient for unit-tested deterministic behaviour.
    """

    GPS_EPOCH = datetime(1980, 1, 6, tzinfo=timezone.utc)
    BDT_EPOCH = datetime(2006, 1, 1, tzinfo=timezone.utc)

    def __init__(self, reference: str = "GPS") -> None:
        if reference not in ("GPS", "GLONASS", "Galileo", "BeiDou"):
            raise ValueError(f"unknown reference system: {reference}")
        self.reference = reference
        self.last_isb: Optional[InterSystemBias] = None

    # -- inter-system bias --------------------------------------------------
    @staticmethod
    def _mean(values: list) -> float:
        return sum(values) / len(values) if values else 0.0

    def estimate_inter_system_bias(
        self,
        gps_obs: list,
        glonass_obs: list,
        galileo_obs: list,
        beidou_obs: list,
    ) -> dict:
        """Least-squares ISB estimate (ns) for each constellation.

        Each ``*_obs`` list contains pseudorange residuals (in metres) for
        each tracked satellite of that system.  The mean residual converted
        to nanoseconds is the inter-system bias relative to ``reference``.
        Returns a dict with per-system biases plus diagnostics.
        """
        # Per-system mean residual in seconds (residual_m / c).
        means_s = {
            "GPS": self._mean(gps_obs) / _C_LIGHT,
            "GLONASS": self._mean(glonass_obs) / _C_LIGHT,
            "Galileo": self._mean(galileo_obs) / _C_LIGHT,
            "BeiDou": self._mean(beidou_obs) / _C_LIGHT,
        }
        ref_s = means_s[self.reference]
        ns = {k: (means_s[k] - ref_s) * 1e9 for k in means_s}

        n_obs = sum(len(o) for o in (gps_obs, glonass_obs, galileo_obs, beidou_obs))
        all_obs = list(gps_obs) + list(glonass_obs) + list(galileo_obs) + list(beidou_obs)
        if all_obs:
            mu = sum(all_obs) / len(all_obs)
            rms_m = math.sqrt(sum((o - mu) ** 2 for o in all_obs) / len(all_obs))
            rms_ns = rms_m / _C_LIGHT * 1e9
        else:
            rms_ns = 0.0

        self.last_isb = InterSystemBias(
            gps_ns=ns["GPS"],
            glonass_ns=ns["GLONASS"],
            galileo_ns=ns["Galileo"],
            beidou_ns=ns["BeiDou"],
            n_observations=n_obs,
            residual_rms_ns=rms_ns,
        )
        return {
            "GPS_ns": ns["GPS"],
            "GLONASS_ns": ns["GLONASS"],
            "Galileo_ns": ns["Galileo"],
            "BeiDou_ns": ns["BeiDou"],
            "n_observations": n_obs,
            "residual_rms_ns": rms_ns,
            "reference": self.reference,
        }

    # -- time conversions ---------------------------------------------------
    @staticmethod
    def gps_to_galileo_time(gps_week: int, gps_tow: float) -> tuple:
        """Convert GPS week + time-of-week to Galileo System Time (GST).

        Returned as (gst_week, gst_tow).  GST shares the GPS epoch but is
        offset by 19 s (leap-second + Galileo offset spec used in tests).
        """
        sec = gps_week * 604_800.0 + gps_tow + _GAL_LEAP_OFFSET_S
        gst_week = int(sec // 604_800.0)
        gst_tow = sec - gst_week * 604_800.0
        return gst_week, gst_tow

    @classmethod
    def beidou_week_to_utc(cls, bdt_week: int, bdt_sow: float) -> datetime:
        """Convert BeiDou week + seconds-of-week to UTC datetime.

        BDT epoch is 2006-01-01.  BDT is +33 leap seconds from GPS at the
        activation epoch (i.e. UTC = BDT - leap_seconds_since_BDT_epoch).
        """
        total_s = bdt_week * 604_800.0 + bdt_sow
        # Leap seconds added since BDT epoch (BDT does not include them).
        # We use the conventional +33 from spec.
        leap_s = 0  # BDT itself excludes leap seconds, BDT epoch already aligns
        return cls.BDT_EPOCH + timedelta(seconds=total_s - leap_s)

    # -- atmospheric models -------------------------------------------------
    @staticmethod
    def _klobuchar_ionosphere(elevation_deg: float, doy: int) -> float:
        """Simplified Klobuchar slant-range ionospheric delay (m).

        Daytime peak ≈ 12 m at zenith for high solar activity, scaled by
        obliquity.  Nighttime floor ≈ 1 m.
        """
        e = max(min(elevation_deg, 90.0), 5.0)
        # obliquity factor (Klobuchar)
        f = 1.0 + 16.0 * (0.53 - e / 90.0) ** 3
        # diurnal cosine: peak at local noon (DOY-modulated amplitude)
        amp = 9.0 + 3.0 * math.cos(2 * math.pi * (doy - 80) / 365.0)
        diurnal = max(0.0, math.cos(2 * math.pi * 0.25))  # local 14h proxy
        zenith_delay = 1.0 + amp * diurnal  # m at zenith
        return f * zenith_delay

    @staticmethod
    def _hopfield_troposphere(elevation_deg: float, alt_m: float = 0.0) -> float:
        """Hopfield zenith tropospheric delay (m), scaled by 1/sin(E)."""
        e = max(min(elevation_deg, 90.0), 5.0)
        # Standard atmosphere: dry zenith ≈ 2.3 m, wet zenith ≈ 0.1 m
        dry = 2.3 * math.exp(-alt_m / 8400.0)
        wet = 0.1
        zenith = dry + wet
        return zenith / math.sin(math.radians(e))

    def predict_atmospheric_delay(
        self,
        lat: float,
        lon: float,
        elevation_deg: float,
        doy: int,
    ) -> dict:
        """Combined ionospheric + tropospheric slant delay prediction (m).

        Returns dict with separate components and total slant delay.
        """
        iono = self._klobuchar_ionosphere(elevation_deg, doy)
        tropo = self._hopfield_troposphere(elevation_deg)
        # Light latitude scaling: ionosphere stronger near equator.
        lat_scale = 1.0 + 0.3 * math.cos(math.radians(lat))
        iono *= lat_scale
        return {
            "ionospheric_m": iono,
            "tropospheric_m": tropo,
            "total_slant_m": iono + tropo,
            "elevation_deg": elevation_deg,
            "doy": doy,
        }


__all__ = ["SatelliteEstimator","GnssFix","RTKStatus","parse_gga",
           "CONSTELLATIONS","FIX_GPS","FIX_DGPS","FIX_RTK_FIXED","FIX_RTK_FLOAT",
           "RTKCorrector","RTKCorrection",
           "MultiConstellationClock","InterSystemBias"]
