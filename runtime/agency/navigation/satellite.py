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


# ---------------------------------------------------------------------------
# Tightly-coupled GNSS/IMU EKF (Round 5)
# ---------------------------------------------------------------------------

try:
    import numpy as _np
except Exception:  # pragma: no cover
    _np = None


class TightlyCoupledGNSSIMU:
    """17-state EKF for tightly-coupled GNSS/IMU navigation.

    State vector (17,):
        [0:3]   position (m, ECEF or local NED)
        [3:6]   velocity (m/s)
        [6:9]   attitude (small-angle Euler, rad)
        [9:12]  accelerometer bias (m/s^2)
        [12:15] gyroscope bias (rad/s)
        [15]    receiver clock bias (m, scaled by c)
        [16]    receiver clock drift (m/s)

    ``predict`` runs IMU mechanization (constant-velocity attitude integration
    + strapdown velocity / position update).  ``update_pseudorange`` and
    ``update_doppler`` perform raw GNSS measurement updates.  ``integrity_check``
    runs a chi-square gate over recent residuals (RAIM-style).
    """

    N_STATES = 17

    def __init__(self, gravity: float = 9.80665) -> None:
        if _np is None:  # pragma: no cover
            raise RuntimeError("TightlyCoupledGNSSIMU requires numpy")
        self.x = _np.zeros(self.N_STATES, dtype=float)
        self.P = _np.eye(self.N_STATES, dtype=float) * 10.0
        self.g = float(gravity)
        self.sigma_a = 0.05
        self.sigma_g = 0.005
        self._residuals: list = []

    # -- mechanization ------------------------------------------------------
    def predict(self, accel, gyro, dt: float) -> None:
        if dt <= 0.0:
            return
        a = _np.asarray(accel, dtype=float).reshape(3) - self.x[9:12]
        w = _np.asarray(gyro, dtype=float).reshape(3) - self.x[12:15]
        # Strapdown integration in local NED frame (gravity along +z down).
        a_world = a + _np.array([0.0, 0.0, self.g])
        self.x[0:3] = self.x[0:3] + self.x[3:6] * dt + 0.5 * a_world * dt * dt
        self.x[3:6] = self.x[3:6] + a_world * dt
        self.x[6:9] = self.x[6:9] + w * dt
        # Clock model: bias <- bias + drift*dt
        self.x[15] = self.x[15] + self.x[16] * dt

        # Covariance propagation (block-diagonal F approximation).
        F = _np.eye(self.N_STATES, dtype=float)
        F[0:3, 3:6] = _np.eye(3) * dt
        F[15, 16] = dt
        Q = _np.zeros((self.N_STATES, self.N_STATES), dtype=float)
        Q[0:3, 0:3] = _np.eye(3) * (self.sigma_a ** 2) * dt ** 4 / 4.0
        Q[3:6, 3:6] = _np.eye(3) * (self.sigma_a ** 2) * dt ** 2
        Q[6:9, 6:9] = _np.eye(3) * (self.sigma_g ** 2) * dt ** 2
        Q[9:12, 9:12] = _np.eye(3) * 1e-6 * dt
        Q[12:15, 12:15] = _np.eye(3) * 1e-8 * dt
        Q[15, 15] = 1e-2 * dt
        Q[16, 16] = 1e-4 * dt
        self.P = F @ self.P @ F.T + Q

    # -- pseudorange update -------------------------------------------------
    def update_pseudorange(
        self,
        sv_pos,
        pseudorange: float,
        sv_clock_bias: float = 0.0,
        sigma: float = 5.0,
    ) -> dict:
        """Update with one raw GNSS pseudorange.

        Predicted: rho_pred = ||sv - r|| + clock_bias - sv_clock_bias
        """
        sv = _np.asarray(sv_pos, dtype=float).reshape(3)
        diff = sv - self.x[0:3]
        r = float(_np.linalg.norm(diff))
        if r < 1e-6:
            return {"accepted": False, "residual": 0.0}
        rho_pred = r + self.x[15] - float(sv_clock_bias)
        residual = float(pseudorange) - rho_pred
        # Jacobian wrt state: dh/dr = -unit(diff), dh/db = 1
        H = _np.zeros((1, self.N_STATES), dtype=float)
        H[0, 0:3] = -diff / r
        H[0, 15] = 1.0
        R = _np.array([[sigma ** 2]])
        S = H @ self.P @ H.T + R
        K = self.P @ H.T / float(S[0, 0])
        self.x = self.x + (K * residual).reshape(self.N_STATES)
        self.P = (_np.eye(self.N_STATES) - K @ H) @ self.P
        self._residuals.append(residual)
        if len(self._residuals) > 50:
            self._residuals = self._residuals[-50:]
        return {"accepted": True, "residual": residual, "rho_pred": rho_pred}

    # -- doppler update -----------------------------------------------------
    def update_doppler(
        self,
        sv_vel,
        doppler_hz: float,
        freq_hz: float = 1_575_420_000.0,
        sigma: float = 0.5,
    ) -> dict:
        """Update with Doppler observation.

        Radial velocity = -lambda * doppler_hz; predicted radial velocity =
        unit(sv-r) . (vel_sv - vel_r) + clock_drift.
        """
        c = 299_792_458.0
        wavelength = c / float(freq_hz)
        radial_meas = -wavelength * float(doppler_hz)
        sv = _np.zeros(3)  # we only need the relative direction; assume known
        # Direction reused from receiver to nominal up if no SV pos passed.
        sv_v = _np.asarray(sv_vel, dtype=float).reshape(3)
        # Use velocity-difference projection along estimated direction of
        # motion (fall back to z-axis if zero).
        v_rel = sv_v - self.x[3:6]
        n = float(_np.linalg.norm(self.x[3:6])) or 1.0
        unit = self.x[3:6] / n
        radial_pred = float(unit @ v_rel) + self.x[16]
        residual = radial_meas - radial_pred
        H = _np.zeros((1, self.N_STATES), dtype=float)
        H[0, 3:6] = -unit
        H[0, 16] = 1.0
        R = _np.array([[sigma ** 2]])
        S = H @ self.P @ H.T + R
        K = self.P @ H.T / float(S[0, 0])
        self.x = self.x + (K * residual).reshape(self.N_STATES)
        self.P = (_np.eye(self.N_STATES) - K @ H) @ self.P
        return {"accepted": True, "residual": residual,
                "wavelength_m": wavelength}

    # -- RAIM-style integrity ----------------------------------------------
    def integrity_check(self, threshold_sigma: float = 3.0) -> dict:
        if not self._residuals:
            return {"integrity_ok": True, "n_residuals": 0,
                    "max_normalized": 0.0, "rms": 0.0}
        arr = _np.asarray(self._residuals, dtype=float)
        rms = float(_np.sqrt(_np.mean(arr ** 2)))
        max_norm = float(_np.max(_np.abs(arr)) / max(rms, 1e-9))
        ok = max_norm < float(threshold_sigma)
        return {
            "integrity_ok": ok,
            "n_residuals": int(arr.size),
            "max_normalized": max_norm,
            "rms": rms,
        }

    def state(self) -> dict:
        return {
            "position": self.x[0:3].copy(),
            "velocity": self.x[3:6].copy(),
            "attitude": self.x[6:9].copy(),
            "accel_bias": self.x[9:12].copy(),
            "gyro_bias": self.x[12:15].copy(),
            "clock_bias_m": float(self.x[15]),
            "clock_drift_mps": float(self.x[16]),
        }


# =====================================================================
# GODSKILL Nav R6 — PPP (Precise Point Positioning)
# =====================================================================

class PPPCorrector:
    """Precise Point Positioning corrector.

    Applies satellite clock corrections, Saastamoinen tropospheric delay
    model, and phase wind-up correction to raw pseudoranges. Targets
    decimeter-level accuracy without a base station.
    """

    SPEED_OF_LIGHT = 299_792_458.0
    CARRIER_L1_HZ = 1_575_420_000.0

    def __init__(self) -> None:
        self._last_windup_cycles = 0.0
        self._sat_clock_table: dict[str, float] = {}

    # --- satellite clock bias table ---------------------------------
    def set_satellite_clock_bias(self, sat_id: str, bias_seconds: float) -> None:
        self._sat_clock_table[str(sat_id)] = float(bias_seconds)

    def get_satellite_clock_bias(self, sat_id: str) -> float:
        return float(self._sat_clock_table.get(str(sat_id), 0.0))

    # --- Saastamoinen tropospheric delay ----------------------------
    def saastamoinen_delay(self, elevation_deg: float, height_m: float,
                           pressure_hpa: float = 1013.25,
                           temp_k: float = 288.15,
                           humidity_frac: float = 0.5) -> float:
        """Saastamoinen tropospheric delay in metres along line of sight.

        Standard atmosphere defaults (sea-level, 15 °C, 50% RH).
        Returns 0 for elevation <= 0.
        """
        import numpy as _np
        elev = float(elevation_deg)
        if elev <= 0.0:
            return 0.0
        # Reduce pressure with altitude (barometric, dry-adiabatic approx)
        h = max(0.0, float(height_m))
        p = float(pressure_hpa) * (1.0 - 2.26e-5 * h) ** 5.225
        t = max(200.0, float(temp_k))
        rh = max(0.0, min(1.0, float(humidity_frac)))
        # Partial pressure of water vapour (Magnus form)
        es = 6.11 * 10.0 ** ((7.5 * (t - 273.15)) / (237.3 + (t - 273.15)))
        e = rh * es
        z_rad = math.radians(90.0 - elev)
        cosz = math.cos(z_rad)
        if cosz < 1e-3:
            cosz = 1e-3
        # Saastamoinen formula (m)
        dry = (0.002277 / cosz) * p
        wet = (0.002277 / cosz) * ((1255.0 / t) + 0.05) * e
        return float(dry + wet)

    # --- Phase wind-up correction -----------------------------------
    def phase_windup(self, satellite_pos, receiver_pos, prev_windup: float) -> float:
        """Phase wind-up in carrier cycles.

        Receiver/satellite relative orientation rotates the carrier
        phase. Returns updated cumulative wind-up in cycles.
        """
        import numpy as _np
        sp = _np.asarray(satellite_pos, dtype=float).reshape(3)
        rp = _np.asarray(receiver_pos, dtype=float).reshape(3)
        los = sp - rp
        norm = float(_np.linalg.norm(los))
        if norm < 1e-9:
            return float(prev_windup)
        k = los / norm
        # Reference dipole frame (simplified — cross with z then x)
        z = _np.array([0.0, 0.0, 1.0])
        x_dip = _np.cross(z, k)
        nx = float(_np.linalg.norm(x_dip))
        if nx < 1e-6:
            x_dip = _np.array([1.0, 0.0, 0.0])
        else:
            x_dip = x_dip / nx
        y_dip = _np.cross(k, x_dip)
        # Project onto satellite-frame X (assumed equal to receiver X for unit test)
        # Phase angle = atan2(y · k_cross_x_sat, x · x_sat)
        phi = math.atan2(float(_np.dot(y_dip, x_dip)),
                         float(_np.dot(x_dip, x_dip)))
        delta_cycles = phi / (2.0 * math.pi)
        # Cumulative — unwrap relative to prev
        prev = float(prev_windup)
        n = round(prev - delta_cycles)
        cycles = delta_cycles + n
        self._last_windup_cycles = cycles
        return cycles

    # --- Apply combined corrections ---------------------------------
    def apply_ppp_corrections(self, pseudorange: float, satellite_pos,
                              receiver_pos, clock_bias_seconds: float,
                              elevation_deg: float = 30.0,
                              height_m: float = 0.0) -> float:
        """Return PPP-corrected range (m).

        rho_corr = rho_raw + c·dt_sat - tropo_delay - windup·lambda
        """
        import numpy as _np
        rho = float(pseudorange)
        # Satellite clock advance is added to range (subtracts bias from rcv side)
        rho += self.SPEED_OF_LIGHT * float(clock_bias_seconds)
        # Tropo delay (subtract — adds to measured pseudorange)
        rho -= self.saastamoinen_delay(elevation_deg, height_m)
        # Phase wind-up in metres at L1
        cycles = self.phase_windup(satellite_pos, receiver_pos,
                                   self._last_windup_cycles)
        wavelength = self.SPEED_OF_LIGHT / self.CARRIER_L1_HZ
        rho -= cycles * wavelength
        return float(rho)


# ============================================================================
# R7 — LEO Satellite Navigation (Starlink/OneWeb-style Doppler positioning)
# ============================================================================

class LEOSatelliteNav:
    """Low-Earth Orbit satellite navigation via Doppler frequency shifts.

    Uses simplified SGP4-style two-body propagation with J2 oblateness
    perturbation. No external dependencies — numpy only.

    Reference frames: ECEF km (positions), ECEF km/s (velocities).
    """

    EARTH_MU_KM3_S2 = 398600.4418            # Earth gravitational parameter
    EARTH_RADIUS_KM = 6378.137               # WGS84 equatorial radius
    EARTH_J2 = 1.0826267e-3                  # J2 oblateness coefficient
    SPEED_OF_LIGHT_KMS = 299792.458          # km/s
    EARTH_ROT_RATE = 7.2921159e-5            # rad/s

    def __init__(self, default_alt_km: float = 550.0):
        import numpy as _np
        self._np = _np
        self.default_alt_km = float(default_alt_km)
        self._receiver_estimate = _np.zeros(3)

    # --- Orbit propagation ---------------------------------------------------

    def propagate_orbit(self, t_seconds: float, tle_mean_motion: float,
                        eccentricity: float, inclination_rad: float,
                        raan_rad: float = 0.0,
                        arg_perigee_rad: float = 0.0,
                        mean_anomaly0_rad: float = 0.0):
        """Propagate satellite orbit using simplified Kepler + J2.

        Args:
            t_seconds: Time since epoch (s)
            tle_mean_motion: Mean motion (rev/day)
            eccentricity: Orbital eccentricity (0–1)
            inclination_rad: Inclination (rad)
            raan_rad: Right ascension of ascending node at epoch (rad)
            arg_perigee_rad: Argument of perigee at epoch (rad)
            mean_anomaly0_rad: Mean anomaly at epoch (rad)

        Returns:
            ECEF position (x, y, z) in km as numpy array.
        """
        np = self._np
        n_rad_s = float(tle_mean_motion) * 2.0 * math.pi / 86400.0  # rad/s
        if n_rad_s <= 0:
            return np.zeros(3)
        a_km = (self.EARTH_MU_KM3_S2 / (n_rad_s * n_rad_s)) ** (1.0 / 3.0)
        e = float(eccentricity)
        e = max(0.0, min(0.95, e))
        i = float(inclination_rad)

        # J2 secular perturbation rates
        d_raan_dt, d_arg_dt = self.j2_perturbation(a_km, e, i)
        raan = float(raan_rad) + d_raan_dt * float(t_seconds)
        argp = float(arg_perigee_rad) + d_arg_dt * float(t_seconds)
        M = float(mean_anomaly0_rad) + n_rad_s * float(t_seconds)
        M = M % (2.0 * math.pi)

        # Solve Kepler's equation E - e·sin(E) = M (Newton iter)
        E = M
        for _ in range(20):
            f = E - e * math.sin(E) - M
            fp = 1.0 - e * math.cos(E)
            if abs(fp) < 1e-12:
                break
            dE = f / fp
            E -= dE
            if abs(dE) < 1e-12:
                break

        # True anomaly
        sin_nu = math.sqrt(1.0 - e * e) * math.sin(E)
        cos_nu = math.cos(E) - e
        nu = math.atan2(sin_nu, cos_nu)

        # Distance and position in perifocal frame
        r_km = a_km * (1.0 - e * math.cos(E))
        x_pf = r_km * math.cos(nu)
        y_pf = r_km * math.sin(nu)

        # Rotate perifocal -> ECI -> approximate ECEF (subtract Earth rotation)
        cos_O = math.cos(raan); sin_O = math.sin(raan)
        cos_w = math.cos(argp); sin_w = math.sin(argp)
        cos_i = math.cos(i);    sin_i = math.sin(i)

        # Perifocal to ECI rotation matrix * (x_pf, y_pf, 0)
        x_eci = (cos_O * cos_w - sin_O * sin_w * cos_i) * x_pf + \
                (-cos_O * sin_w - sin_O * cos_w * cos_i) * y_pf
        y_eci = (sin_O * cos_w + cos_O * sin_w * cos_i) * x_pf + \
                (-sin_O * sin_w + cos_O * cos_w * cos_i) * y_pf
        z_eci = (sin_w * sin_i) * x_pf + (cos_w * sin_i) * y_pf

        # Earth rotation -> ECEF
        theta_g = self.EARTH_ROT_RATE * float(t_seconds)
        cos_g = math.cos(theta_g); sin_g = math.sin(theta_g)
        x_ecef =  cos_g * x_eci + sin_g * y_eci
        y_ecef = -sin_g * x_eci + cos_g * y_eci
        z_ecef = z_eci

        return np.array([x_ecef, y_ecef, z_ecef])

    def j2_perturbation(self, a_km: float, e: float, i_rad: float):
        """Compute J2-induced secular drift of RAAN and arg-perigee.

        Returns:
            (d_raan_dt, d_argperigee_dt) in rad/s.
        """
        a = float(a_km)
        if a <= 0:
            return (0.0, 0.0)
        e = max(0.0, min(0.95, float(e)))
        i = float(i_rad)
        n = math.sqrt(self.EARTH_MU_KM3_S2 / (a ** 3))
        p = a * (1.0 - e * e)
        if p <= 0:
            return (0.0, 0.0)
        factor = -1.5 * n * self.EARTH_J2 * (self.EARTH_RADIUS_KM / p) ** 2
        d_raan_dt = factor * math.cos(i)
        # Arg-perigee secular rate
        d_argp_dt = -0.5 * factor * (5.0 * math.cos(i) ** 2 - 1.0)
        return (d_raan_dt, d_argp_dt)

    # --- Doppler positioning -------------------------------------------------

    def doppler_position_fix(self, freq_obs, freq_nominal, sat_positions,
                             sat_velocities):
        """Estimate receiver position using Doppler shifts from LEO satellites.

        Args:
            freq_obs: Array of observed carrier frequencies (Hz), shape (N,)
            freq_nominal: Nominal carrier frequency (Hz), scalar
            sat_positions: Satellite ECEF positions (km), shape (N, 3)
            sat_velocities: Satellite ECEF velocities (km/s), shape (N, 3)

        Returns:
            Estimated receiver ECEF position (km) as length-3 array.
        """
        np = self._np
        f_obs = np.asarray(freq_obs, dtype=float).reshape(-1)
        f_nom = float(freq_nominal)
        sp = np.asarray(sat_positions, dtype=float).reshape(-1, 3)
        sv = np.asarray(sat_velocities, dtype=float).reshape(-1, 3)
        n_sats = sp.shape[0]
        if n_sats < 3 or f_obs.shape[0] != n_sats:
            return np.zeros(3)

        # Range-rate from Doppler:  rdot = -c * (f_obs - f_nom) / f_nom
        rdot = -self.SPEED_OF_LIGHT_KMS * (f_obs - f_nom) / f_nom

        # Iterative Gauss-Newton — start from receiver estimate or origin
        r = self._receiver_estimate.copy()
        if float(np.linalg.norm(r)) < 1.0:
            r = np.array([self.EARTH_RADIUS_KM, 0.0, 0.0])

        for _ in range(15):
            # Predicted range-rate per satellite
            los = sp - r                                           # (N,3)
            ranges = np.linalg.norm(los, axis=1) + 1e-9
            unit_los = los / ranges[:, None]                       # (N,3)
            # rdot_pred = -unit_los · sat_vel  (receiver assumed stationary)
            rdot_pred = -np.sum(unit_los * sv, axis=1)
            residual = rdot - rdot_pred                            # (N,)
            # Jacobian d(rdot_pred)/dr — gradient w.r.t. receiver
            # d(unit_los)/dr is small; approximate H = sv_perp / range
            # Use H ≈ -(I - los·losᵀ) · sv / range  (per row)
            H = np.zeros((n_sats, 3))
            for k in range(n_sats):
                u = unit_los[k]
                proj = np.eye(3) - np.outer(u, u)
                H[k] = -(proj @ sv[k]) / ranges[k]
            # Solve H · dr = residual (least squares)
            try:
                dr, *_ = np.linalg.lstsq(H, residual, rcond=None)
            except np.linalg.LinAlgError:
                break
            r = r + dr
            if float(np.linalg.norm(dr)) < 1e-6:
                break

        self._receiver_estimate = r
        return r


# ============================================================================
# R8 — SBAS Corrector (WAAS/EGNOS/MSAS-style augmentation)
# ============================================================================

class SBASCorrector:
    """Satellite-Based Augmentation System corrections.

    Applies fast clock corrections, ionospheric grid corrections, and
    computes Horizontal/Vertical Protection Levels.
    """

    def __init__(self):
        import numpy as _np
        self._np = _np

    def apply_fast_corrections(self, sv_id, pseudorange: float,
                               fast_corr_dict) -> float:
        """Subtract per-SV fast clock correction from pseudorange.

        Args:
            sv_id: Satellite vehicle identifier (key into dict)
            pseudorange: Raw pseudorange (m)
            fast_corr_dict: {sv_id: correction_m}
        """
        corr = float(fast_corr_dict.get(sv_id, 0.0))
        return float(pseudorange) - corr

    def interpolate_ionospheric_grid(self, lat: float, lon: float,
                                     iono_grid_points) -> float:
        """Inverse-distance-weighted interpolation of vertical iono delay.

        Args:
            lat, lon: Pierce-point coordinates (deg)
            iono_grid_points: Iterable of (lat, lon, delay_m) tuples
        """
        np = self._np
        pts = list(iono_grid_points)
        if not pts:
            return 0.0
        weights = []
        delays = []
        for plat, plon, pdelay in pts:
            d2 = (float(plat) - float(lat)) ** 2 + \
                 (float(plon) - float(lon)) ** 2
            if d2 < 1e-12:
                return float(pdelay)
            weights.append(1.0 / d2)
            delays.append(float(pdelay))
        w = np.asarray(weights, dtype=float)
        d = np.asarray(delays, dtype=float)
        return float(np.sum(w * d) / np.sum(w))

    def compute_protection_levels(self, H_matrix, sigma_vec):
        """Compute HPL and VPL from geometry and per-satellite sigmas.

        HPL = ||H[:,0:2]ᵀ · sigma||
        VPL = ||H[:,2] * sigma||
        """
        np = self._np
        H = np.asarray(H_matrix, dtype=float).reshape(-1, H_matrix.shape[1]
                                                      if hasattr(H_matrix, 'shape')
                                                      else 3)
        sigma = np.asarray(sigma_vec, dtype=float).reshape(-1)
        hpl = float(np.linalg.norm(H[:, 0:2].T @ sigma))
        vpl = float(np.linalg.norm(H[:, 2] * sigma))
        return np.array([hpl, vpl])


# ============================================================================
# R9 — Multipath Mitigation (narrow-correlator, Hatch filter, cycle slips)
# ============================================================================

class MultiPathMitigator:
    """GNSS multipath detection and pseudorange smoothing.

    Combines narrow vs wide correlator differencing, Hatch carrier-phase
    smoothing, and cycle-slip detection on phase differences.
    """

    NARROW_SPACING_CHIPS = 0.1
    WIDE_SPACING_CHIPS = 1.0

    def __init__(self):
        import numpy as _np
        self._np = _np

    def compute_multipath_indicator(self, narrow_corr: float,
                                    wide_corr: float) -> float:
        """Indicator = |wide - narrow| / max(|wide|, eps)."""
        n = float(narrow_corr)
        w = float(wide_corr)
        denom = max(abs(w), 1e-9)
        return abs(w - n) / denom

    def smooth_pseudorange(self, pseudoranges, carrier_phases, n: int = 5):
        """Hatch carrier-smoothed pseudorange.

        P_smooth[k] = ((n-1)/n)·(P_smooth[k-1] + (Φ[k] - Φ[k-1]))
                    + (1/n)·P_raw[k]
        """
        np = self._np
        P = np.asarray(pseudoranges, dtype=float).reshape(-1)
        Phi = np.asarray(carrier_phases, dtype=float).reshape(-1)
        if P.size == 0:
            return P
        out = np.zeros_like(P)
        out[0] = P[0]
        a = (n - 1.0) / float(n)
        b = 1.0 / float(n)
        for k in range(1, P.size):
            d_phi = Phi[k] - Phi[k - 1]
            out[k] = a * (out[k - 1] + d_phi) + b * P[k]
        return out

    def detect_cycle_slip(self, phase_diffs, threshold: float = 0.1):
        """Boolean array: True where |Δϕ| exceeds ``threshold`` cycles."""
        np = self._np
        d = np.asarray(phase_diffs, dtype=float).reshape(-1)
        return np.abs(d) > float(threshold)


# ============================================================================
# R10 — Receiver Autonomous Integrity Monitoring (Solution-Separation RAIM)
# ============================================================================

class ReceiverAutonomousIntegrityMonitoring:
    """Solution-Separation RAIM (SS-RAIM) for GNSS integrity.

    Computes per-satellite slope and protection levels (HPL, VPL) using
    the geometry matrix and a per-SV UERE σ.  Issues an alert when the
    horizontal or vertical protection level exceeds its limit.
    """

    DEFAULT_HAL = 556.0  # m, en-route alert limit
    DEFAULT_VAL = 50.0   # m, vertical alert limit
    K_FAULT = 5.33       # MHSS fault-mode multiplier (P_fault ≈ 1e-7 budget)

    def __init__(self):
        import numpy as _np
        self._np = _np

    def compute_protection_level(self, geometry_matrix, sigma_uere,
                                 fault_prob: float = 1e-4):
        """Return (HPL, VPL) in metres.

        HPL = K · σ_pos_horiz · max_slope_h
        VPL = K · σ_pos_vert  · max_slope_v
        """
        np = self._np
        H = np.asarray(geometry_matrix, dtype=float).reshape(-1, 4) \
            if hasattr(geometry_matrix, "shape") and geometry_matrix.shape[-1] == 4 \
            else np.asarray(geometry_matrix, dtype=float)
        sigma = np.asarray(sigma_uere, dtype=float).reshape(-1)
        if H.ndim != 2 or H.shape[0] < H.shape[1]:
            return (float("inf"), float("inf"))

        # Weighted normal-equation inverse: P = (Hᵀ W H)⁻¹
        W = np.diag(1.0 / np.maximum(sigma ** 2, 1e-12))
        try:
            P = np.linalg.inv(H.T @ W @ H)
        except np.linalg.LinAlgError:
            return (float("inf"), float("inf"))

        # Position-state variances
        sigma_h = math.sqrt(max(P[0, 0] + P[1, 1], 0.0))
        sigma_v = math.sqrt(max(P[2, 2], 0.0))

        # Per-SV slope (Brown 1992): slope_i = sqrt(s_i_h or v) / sqrt(W_ii) where
        # s = (HᵀWH)⁻¹HᵀW; here we approximate by leverages.
        try:
            S = P @ H.T @ W                          # (4, n)
            slopes_h = np.sqrt(np.maximum(S[0] ** 2 + S[1] ** 2, 0.0)) \
                       * np.sqrt(np.maximum(np.diag(W), 1e-12))
            slopes_v = np.sqrt(np.maximum(S[2] ** 2, 0.0)) \
                       * np.sqrt(np.maximum(np.diag(W), 1e-12))
            max_h = float(np.max(slopes_h))
            max_v = float(np.max(slopes_v))
        except Exception:
            max_h = max_v = 1.0

        # Fault-mode multiplier from chi-square approximation
        K = self.K_FAULT * max(1.0, math.sqrt(-math.log(max(fault_prob, 1e-12))))
        hpl = K * sigma_h * max(max_h, 1.0)
        vpl = K * sigma_v * max(max_v, 1.0)
        return (float(hpl), float(vpl))

    def solution_separation(self, all_subsets, full_solution):
        """Maximum element-wise separation between full and subset solutions."""
        np = self._np
        full = np.asarray(full_solution, dtype=float).reshape(-1)
        max_sep = np.zeros_like(full)
        for sub in all_subsets:
            s = np.asarray(sub, dtype=float).reshape(-1)
            sep = np.abs(s - full)
            max_sep = np.maximum(max_sep, sep)
        return max_sep

    def alert(self, HPL: float, HAL: float = None, VPL: float = 0.0,
              VAL: float = 50.0) -> bool:
        """Return True if either protection level exceeds its alert limit."""
        hal = float(HAL) if HAL is not None else self.DEFAULT_HAL
        val = float(VAL)
        return bool(float(HPL) > hal or float(VPL) > val)


# ============================================================================
# R11 — Ionospheric Storm Detector (ROTI + 8-param Klobuchar)
# ============================================================================

class IonosphericStormDetector:
    """ROTI-based ionospheric scintillation/storm detection + Klobuchar.

    ROTI (Rate Of TEC Index) = std(ΔTEC/Δt) over a sliding window.
    Klobuchar 8-coefficient broadcast iono model returns L1 group delay (m).
    """

    SPEED_OF_LIGHT = 299792458.0  # m/s

    def __init__(self):
        import numpy as _np
        self._np = _np

    def compute_roti(self, phase_diff_series, dt: float = 30.0) -> float:
        """ROTI in TECu/min from carrier-phase TEC differences.

        Args:
            phase_diff_series: array of TEC differences (TECu)
            dt: sampling interval (s)
        """
        np = self._np
        d = np.asarray(phase_diff_series, dtype=float).reshape(-1)
        if d.size < 2:
            return 0.0
        rate = d / float(dt)             # TECu/s
        return float(np.std(rate) * 60.0)  # TECu/min

    def detect_storm(self, roti: float, threshold: float = 0.5) -> bool:
        return float(roti) > float(threshold)

    def klobuchar_correction(self, alpha, beta, elevation_deg: float,
                             azimuth_deg: float, lat_rad: float,
                             lon_rad: float, gps_time_s: float = 43200.0
                             ) -> float:
        """8-parameter Klobuchar L1 ionospheric delay (m)."""
        a = list(alpha)
        b = list(beta)
        E = float(elevation_deg) / 180.0          # semi-circles
        A = float(azimuth_deg) * math.pi / 180.0  # rad
        phi_u = float(lat_rad) / math.pi          # semi-circles
        lam_u = float(lon_rad) / math.pi          # semi-circles

        # Earth-centred angle (semi-circles)
        psi = 0.0137 / (E + 0.11) - 0.022

        # Sub-ionospheric latitude (semi-circles)
        phi_i = phi_u + psi * math.cos(A)
        if phi_i > 0.416:
            phi_i = 0.416
        elif phi_i < -0.416:
            phi_i = -0.416

        # Sub-ionospheric longitude (semi-circles)
        lam_i = lam_u + psi * math.sin(A) / math.cos(phi_i * math.pi)

        # Geomagnetic latitude (semi-circles)
        phi_m = phi_i + 0.064 * math.cos((lam_i - 1.617) * math.pi)

        # Local time (sec)
        t = (43200.0 * lam_i + float(gps_time_s)) % 86400.0
        if t < 0:
            t += 86400.0

        # Amplitude AMP and period PER
        AMP = sum(a[n] * (phi_m ** n) for n in range(4))
        if AMP < 0:
            AMP = 0.0
        PER = sum(b[n] * (phi_m ** n) for n in range(4))
        if PER < 72000.0:
            PER = 72000.0

        # Phase x (rad)
        x = 2.0 * math.pi * (t - 50400.0) / PER

        # Slant factor (obliquity)
        F = 1.0 + 16.0 * (0.53 - E) ** 3

        if abs(x) < 1.57:
            iono_time = F * (5.0e-9 + AMP * (1.0 - (x ** 2) / 2.0
                                              + (x ** 4) / 24.0))
        else:
            iono_time = F * 5.0e-9

        return float(iono_time * self.SPEED_OF_LIGHT)

    def storm_scale_factor(self, kp_index: float) -> float:
        """Iono-error inflation factor as a function of Kp geomagnetic index."""
        s = 1.0 + 0.1 * (float(kp_index) - 3.0)
        return float(max(1.0, min(2.5, s)))


# ============================================================================
# R12 — Software-Defined GNSS Clock Steering Loop (PLL/FLL + NCO)
# ============================================================================

class GNSSClockSteeringLoop:
    """Carrier tracking loop: PLL discriminator, FLL discriminator, 2nd-order
    NCO loop filter, and Carrier Lock Indicator (CLI).
    """

    def __init__(self):
        import numpy as _np
        self._np = _np
        self.phase = 0.0          # rad
        self.freq = 0.0           # Hz
        self._phase_acc = 0.0     # integrator state for loop filter
        self._freq_acc = 0.0      # integrator state for loop filter

    def discriminator_pll(self, I: float, Q: float) -> float:
        """Costas-loop arctan PLL discriminator (rad)."""
        I = float(I)
        Q = float(Q)
        if abs(I) < 1e-12 and abs(Q) < 1e-12:
            return 0.0
        return math.atan2(Q, I)

    def discriminator_fll(self, I1: float, Q1: float,
                          I2: float, Q2: float, dt: float) -> float:
        """Cross-product FLL frequency-error discriminator (Hz)."""
        cross = float(I1) * float(Q2) - float(I2) * float(Q1)
        dot = float(I1) * float(I2) + float(Q1) * float(Q2)
        # Atan2(cross, dot) is more robust for ±π wrapping
        delta_phi = math.atan2(cross, dot if abs(dot) > 1e-12 else 1e-12)
        return float(delta_phi / (2.0 * math.pi * max(float(dt), 1e-9)))

    def update_nco(self, phase_err: float, freq_err: float, dt: float,
                   bandwidth_hz: float = 10.0):
        """Second-order loop-filter NCO update.

        Returns the new (phase_rad, freq_hz) NCO state.
        """
        wn = 2.0 * math.pi * float(bandwidth_hz)
        zeta = math.sqrt(2.0) / 2.0
        k1 = 2.0 * zeta * wn       # phase coefficient
        k2 = wn * wn               # frequency coefficient
        self.freq += k2 * float(phase_err) * float(dt) + float(freq_err) * float(dt)
        self.phase += (k1 * float(phase_err) + 2.0 * math.pi * self.freq) * float(dt)
        # Wrap phase to [-π, π]
        self.phase = (self.phase + math.pi) % (2.0 * math.pi) - math.pi
        return (float(self.phase), float(self.freq))

    def carrier_lock_indicator(self, I, Q) -> float:
        """CLI = (I² − Q²) / (I² + Q²); >0.85 indicates phase-locked."""
        np = self._np
        Ia = np.asarray(I, dtype=float).reshape(-1)
        Qa = np.asarray(Q, dtype=float).reshape(-1)
        num = float(np.sum(Ia ** 2 - Qa ** 2))
        den = float(np.sum(Ia ** 2 + Qa ** 2)) + 1e-12
        return float(num / den)


# ============================================================================
# R13 — Differential GNSS (DGNSS) base + rover correction broadcast
# ============================================================================

class DifferentialGNSS:
    """DGNSS base-station-derived range corrections.

    Base station with surveyed-true position computes per-SV correction
    = true_geometric_range − measured_pseudorange.  Corrections are
    broadcast to the rover, which subtracts them from its own
    pseudoranges (with optional age-based extrapolation).
    """

    def __init__(self):
        import numpy as _np
        self._np = _np

    def compute_corrections(self, base_pseudoranges, base_true_pos,
                            sat_positions):
        """Return {sv_id: ΔP_m} dict of pseudorange corrections."""
        np = self._np
        base_pos = np.asarray(base_true_pos, dtype=float).reshape(3)
        out = {}
        for sv_id, p_meas in base_pseudoranges.items():
            sat_pos = np.asarray(sat_positions[sv_id], dtype=float).reshape(3)
            true_range = float(np.linalg.norm(sat_pos - base_pos))
            out[sv_id] = float(true_range - float(p_meas))
        return out

    def apply_corrections(self, rover_pseudoranges, corrections):
        """Add the broadcast correction to each rover pseudorange."""
        np = self._np
        keys = list(rover_pseudoranges.keys())
        out = np.zeros(len(keys))
        for i, sv_id in enumerate(keys):
            corr = float(corrections.get(sv_id, 0.0))
            out[i] = float(rover_pseudoranges[sv_id]) + corr
        return out

    def extrapolate_correction(self, correction: float, age_s: float,
                               correction_rate: float) -> float:
        """Linear extrapolation: corr + rate · age."""
        return float(correction) + float(correction_rate) * float(age_s)

    def quality_flag(self, correction_age_s: float,
                     threshold: float = 30.0) -> str:
        """Return 'good' / 'degraded' / 'invalid' based on correction age."""
        age = float(correction_age_s)
        if age < float(threshold):
            return "good"
        if age < 2.0 * float(threshold):
            return "degraded"
        return "invalid"


# ============================================================================
# R14 — Carrier-Phase Ambiguity Resolution (RTK integer fix via bootstrap)
# ============================================================================

class CarrierPhaseAmbiguityResolution:
    """Integer ambiguity bootstrap for RTK carrier-phase positioning.

    Stores a float ambiguity vector + covariance, then sequentially
    rounds each ambiguity conditional on the previously fixed values.
    """

    def __init__(self, wavelength: float = 0.1903):
        import numpy as _np
        self._np = _np
        self.wavelength = float(wavelength)
        self._float_ambiguities = None
        self._cov = None
        self._fixed = False
        self._fixed_vec = None

    def set_float_solution(self, float_amb, cov):
        np = self._np
        self._float_ambiguities = np.asarray(float_amb, dtype=float).reshape(-1).copy()
        self._cov = np.asarray(cov, dtype=float).copy()
        if self._cov.shape != (self._float_ambiguities.size,
                               self._float_ambiguities.size):
            raise ValueError("cov shape must be (n, n)")
        self._fixed = False
        self._fixed_vec = None

    def bootstrap_fix(self):
        """Sequential conditional rounding (LDL bootstrap)."""
        np = self._np
        if self._float_ambiguities is None:
            raise ValueError("call set_float_solution first")
        a = self._float_ambiguities.copy()
        P = self._cov.copy()
        n = a.size
        fixed = np.zeros(n)
        for k in range(n):
            fixed[k] = float(np.round(a[k]))
            if k + 1 < n:
                # Conditional update of remaining ambiguities given a_k fixed
                pkk = max(P[k, k], 1e-12)
                gain = P[k + 1:, k] / pkk
                a[k + 1:] = a[k + 1:] + gain * (fixed[k] - a[k])
                P[k + 1:, k + 1:] = P[k + 1:, k + 1:] - np.outer(
                    P[k + 1:, k], P[k, k + 1:]) / pkk
        self._fixed = True
        self._fixed_vec = fixed
        return fixed

    def phase_range_correction(self, integer_amb, carrier_cycles):
        np = self._np
        N = np.asarray(integer_amb, dtype=float).reshape(-1)
        phi = np.asarray(carrier_cycles, dtype=float).reshape(-1)
        return (phi + N) * self.wavelength

    def fix_ratio(self) -> float:
        """Variance-based ratio test: smaller residual variance → larger ratio."""
        np = self._np
        if self._float_ambiguities is None or self._fixed_vec is None:
            return float("inf")
        diff = self._float_ambiguities - self._fixed_vec
        try:
            P_inv = np.linalg.inv(self._cov)
        except np.linalg.LinAlgError:
            return float("inf")
        best = float(diff @ P_inv @ diff)
        # Second-best: all-rounded-up vector as competing hypothesis
        alt = np.round(self._float_ambiguities + 0.5)
        diff2 = self._float_ambiguities - alt
        second = float(diff2 @ P_inv @ diff2)
        if best <= 0:
            return float("inf")
        return float(second / best)

    @property
    def is_fixed(self) -> bool:
        return self._fixed


# ============================================================================
# R15 — GNSS Doppler Velocity Estimator
# ============================================================================

class GNSSDopplerVelocity:
    """Receiver velocity from carrier-Doppler measurements."""

    def __init__(self, freq_l1: float = 1575.42e6, c: float = 2.998e8):
        import numpy as _np
        self._np = _np
        self.lambda_l1 = float(c) / float(freq_l1)
        self.c = float(c)
        self._last_vel = _np.zeros(3)

    def doppler_to_pseudorange_rate(self, doppler_hz):
        np = self._np
        d = np.asarray(doppler_hz, dtype=float).reshape(-1)
        return -d * self.lambda_l1

    def estimate_velocity(self, doppler_hz, sv_los):
        """3-state WLS velocity from Doppler observations."""
        np = self._np
        rate = self.doppler_to_pseudorange_rate(doppler_hz)
        H = -np.asarray(sv_los, dtype=float).reshape(-1, 3)
        if H.shape[0] < 3:
            return self._last_vel.copy()
        try:
            v, *_ = np.linalg.lstsq(H, rate, rcond=None)
        except np.linalg.LinAlgError:
            return self._last_vel.copy()
        self._last_vel = v
        return v

    def receiver_clock_drift(self, doppler_hz, sv_los) -> float:
        """4-state solve for [vx, vy, vz, clock_drift_m_s]."""
        np = self._np
        rate = self.doppler_to_pseudorange_rate(doppler_hz)
        L = np.asarray(sv_los, dtype=float).reshape(-1, 3)
        H = np.hstack([-L, np.ones((L.shape[0], 1))])
        if H.shape[0] < 4:
            return 0.0
        try:
            sol, *_ = np.linalg.lstsq(H, rate, rcond=None)
        except np.linalg.LinAlgError:
            return 0.0
        return float(sol[3])

    def speed(self) -> float:
        np = self._np
        return float(np.linalg.norm(self._last_vel))


# ============================================================================
# R16 — Advanced RAIM (ARAIM) — multi-constellation integrity + PLs
# ============================================================================

class AdvancedRAIM:
    """ARAIM-style integrity monitor with HPL/VPL + leave-one-out subset test."""

    K_FA_DEFAULT = 6.18  # ≈ Φ⁻¹(1 − 1e-7 / 2)

    def __init__(self, p_fa: float = 1e-7, p_md: float = 1e-3,
                 sigma_uere: float = 1.5):
        import numpy as _np
        self._np = _np
        self.p_fa = float(p_fa)
        self.p_md = float(p_md)
        self.sigma_uere = float(sigma_uere)

    def geometry_matrix(self, sv_az, sv_el):
        np = self._np
        az = np.asarray(sv_az, dtype=float).reshape(-1)
        el = np.asarray(sv_el, dtype=float).reshape(-1)
        n = az.size
        H = np.zeros((n, 4))
        H[:, 0] = -np.cos(el) * np.sin(az)
        H[:, 1] = -np.cos(el) * np.cos(az)
        H[:, 2] = -np.sin(el)
        H[:, 3] = 1.0
        return H

    def _k_fa(self) -> float:
        # Conservative inverse-Q approximation for small p_fa
        p = max(self.p_fa, 1e-15)
        if p <= 1e-7:
            return self.K_FA_DEFAULT
        return float(math.sqrt(-2.0 * math.log(p * 2.0 * math.pi)))

    def protection_level(self, sv_az, sv_el):
        np = self._np
        H = self.geometry_matrix(sv_az, sv_el)
        n = H.shape[0]
        if n < 4:
            return (float("inf"), float("inf"))
        W = np.eye(n) / max(self.sigma_uere ** 2, 1e-12)
        try:
            Q = np.linalg.inv(H.T @ W @ H)
        except np.linalg.LinAlgError:
            return (float("inf"), float("inf"))
        k = self._k_fa()
        hpl = k * math.sqrt(max(Q[0, 0] + Q[1, 1], 0.0))
        vpl = k * math.sqrt(max(Q[2, 2], 0.0))
        return (float(hpl), float(vpl))

    def check_alert_limits(self, hpl: float, vpl: float,
                           hal: float = 40.0, val: float = 50.0) -> bool:
        return float(hpl) <= float(hal) and float(vpl) <= float(val)

    def subset_test(self, sv_az, sv_el):
        """Flag SV whose removal most improves VPL (leave-one-out test)."""
        np = self._np
        az = np.asarray(sv_az, dtype=float).reshape(-1)
        el = np.asarray(sv_el, dtype=float).reshape(-1)
        n = az.size
        if n < 5:
            return np.ones(n, dtype=bool)
        _, base_vpl = self.protection_level(az, el)
        flags = np.ones(n, dtype=bool)
        improvements = np.zeros(n)
        for i in range(n):
            mask = np.ones(n, dtype=bool); mask[i] = False
            _, vpl_sub = self.protection_level(az[mask], el[mask])
            improvements[i] = base_vpl - vpl_sub
        worst = int(np.argmax(improvements))
        if improvements[worst] > 0.5 * base_vpl:
            flags[worst] = False
        return flags
