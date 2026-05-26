from __future__ import annotations
import sys
from pathlib import Path
from .base import Bridge

# Insert runtime directory into sys.path to resolve agency imports
_runtime_path = str(Path(__file__).resolve().parents[2] / "runtime")
if _runtime_path not in sys.path:
    sys.path.insert(0, _runtime_path)

from agency.navigation.satellite import SatelliteEstimator, RTKCorrector


class RtkAiBridge(Bridge):
    name = "rtk_ai"
    capabilities = ["get-position", "subscribe-stream", "calibrate"]

    def __init__(self, **config):
        self.config = config
        self._estimator = SatelliteEstimator(
            rtk_enabled=config.get("rtk_enabled", True),
            spoofing_detection=config.get("spoofing_detection", True)
        )
        self._corrector = RTKCorrector()
        self._connected = False

    def connect(self) -> bool:
        self._connected = True
        return True

    def invoke(self, action: str, **kw) -> dict:
        if not self._connected:
            self.connect()
        if action not in self.capabilities:
            return {"ok": False, "error": f"unknown action: {action}",
                    "available": self.capabilities}
        try:
            if action == "get-position":
                nmea = kw.get("nmea")
                if nmea:
                    self._estimator.feed_nmea(nmea)
                else:
                    self._estimator.update({
                        "lat": kw.get("lat", 32.0853),
                        "lon": kw.get("lon", 34.7818),
                        "alt": kw.get("alt", 10.0),
                        "fix_quality": kw.get("fix_quality", 4),
                        "hdop": kw.get("hdop", 0.8),
                        "sats": kw.get("sats", 12)
                    })
                est = self._estimator.get_estimate()
                if est:
                    res = {
                        "ok": True,
                        "lat": est.pose.position.x,
                        "lon": est.pose.position.y,
                        "alt": est.pose.position.z,
                        "confidence": {
                            "horizontal_m": est.confidence.horizontal_m,
                            "vertical_m": est.confidence.vertical_m,
                            "valid": est.confidence.valid,
                            "source": est.confidence.source
                        },
                        "source": est.source,
                        "raw": est.raw
                    }
                else:
                    res = {"ok": False, "error": "No satellite fix obtained yet."}
            elif action == "subscribe-stream":
                res = {
                    "ok": True,
                    "stream_url": kw.get("stream_url", "ntrip://rtk-network.org:2101/TLV1"),
                    "status": "subscribed",
                    "active_constellations": self._estimator.active_constellations
                }
            elif action == "calibrate":
                base_pos = kw.get("base_pos", (32.0853, 34.7818, 10.0))
                rover_obs = kw.get("rover_obs", {
                    "lat": kw.get("lat", 32.08535),
                    "lon": kw.get("lon", 34.78185),
                    "alt": kw.get("alt", 10.1),
                    "satellites": kw.get("satellites", [{"id": "G01", "snr_db": 42.0}])
                })
                corr = self._corrector.apply_rtk_corrections(
                    base_pos=base_pos,
                    rover_obs=rover_obs,
                    t_now=kw.get("timestamp")
                )
                res = {
                    "ok": True,
                    "corrected_lat": corr.lat,
                    "corrected_lon": corr.lon,
                    "corrected_alt": corr.alt,
                    "accuracy_horizontal": corr.horizontal_m,
                    "accuracy_vertical": corr.vertical_m,
                    "fix_quality": corr.fix_quality,
                    "is_spoofed": corr.is_spoofed,
                    "spoof_reason": corr.spoof_reason
                }
            else:
                return {"ok": False, "error": f"unsupported action: {action}"}
            
            if isinstance(res, dict):
                return {**res, "bridge": self.name, "action": action}
            return {"ok": True, "result": res, "bridge": self.name, "action": action}
        except Exception as e:
            return {"ok": False, "error": str(e), "bridge": self.name, "action": action}

    def disconnect(self) -> None:
        self._connected = False

