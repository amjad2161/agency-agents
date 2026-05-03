"""R28 — WiFiRTTPositioner + BLEBeaconPositioner. Imported into indoor_slam."""
from __future__ import annotations

import math
import numpy as np


class WiFiRTTPositioner:
    """802.11mc Round-Trip Time ranging + 2-D LS trilateration."""

    SPEED_OF_LIGHT = 299792458.0

    def __init__(self):
        self.aps = {}        # ap_id -> position_xy
        self._meas = {}      # ap_id -> rtt_ns

    def add_ap(self, ap_id, pos_xy):
        self.aps[ap_id] = np.asarray(pos_xy, dtype=float).reshape(2)

    def rtt_to_range(self, rtt_ns: float) -> float:
        return float(self.SPEED_OF_LIGHT) * float(rtt_ns) * 1e-9 / 2.0

    def add_measurement(self, ap_id, rtt_ns: float):
        self._meas[ap_id] = float(rtt_ns)

    def locate(self):
        ids = [a for a in self._meas if a in self.aps]
        if len(ids) < 3:
            return np.zeros(2)
        anchors = np.stack([self.aps[a] for a in ids])
        ranges = np.array([self.rtt_to_range(self._meas[a]) for a in ids])
        p = anchors.mean(axis=0)
        for _ in range(5):
            d = np.linalg.norm(anchors - p, axis=1) + 1e-9
            H = (p - anchors) / d[:, None]
            residual = ranges - d
            try:
                dp, *_ = np.linalg.lstsq(H, residual, rcond=None)
            except np.linalg.LinAlgError:
                break
            p = p + dp
            if float(np.linalg.norm(dp)) < 1e-6:
                break
        return p

    def range_residuals(self, pos_xy):
        ids = [a for a in self._meas if a in self.aps]
        if not ids:
            return np.zeros(0)
        p = np.asarray(pos_xy, dtype=float).reshape(2)
        anchors = np.stack([self.aps[a] for a in ids])
        ranges = np.array([self.rtt_to_range(self._meas[a]) for a in ids])
        d = np.linalg.norm(anchors - p, axis=1)
        return ranges - d

    def clear_measurements(self):
        self._meas.clear()


class BLEBeaconPositioner:
    """BLE iBeacon proximity classifier + WLS trilateration."""

    RSSI_1M = -59.0

    def __init__(self):
        self.beacons = {}      # bid -> (pos_xy, tx_power_dbm)
        self._rssi = {}

    def add_beacon(self, bid, pos_xy, tx_power_dbm: float = -59.0):
        self.beacons[bid] = (
            np.asarray(pos_xy, dtype=float).reshape(2),
            float(tx_power_dbm),
        )

    def rssi_to_range(self, rssi_dbm: float, tx_power_dbm: float,
                      path_loss_exp: float = 2.0) -> float:
        exp_val = (float(tx_power_dbm) - float(rssi_dbm)) \
                  / (10.0 * float(path_loss_exp))
        return float(10.0 ** exp_val)

    def proximity_zone(self, rssi_dbm: float) -> str:
        d = self.rssi_to_range(rssi_dbm, self.RSSI_1M)
        if d < 0.5:
            return "immediate"
        if d < 3.0:
            return "near"
        return "far"

    def add_rssi(self, bid, rssi_dbm: float):
        self._rssi[bid] = float(rssi_dbm)

    def locate(self):
        ids = [b for b in self._rssi if b in self.beacons]
        if len(ids) < 3:
            return np.zeros(2)
        anchors = np.stack([self.beacons[b][0] for b in ids])
        ranges = np.array([self.rssi_to_range(self._rssi[b],
                                              self.beacons[b][1])
                           for b in ids])
        weights = 1.0 / (ranges ** 2 + 1e-9)
        p = anchors.mean(axis=0)
        for _ in range(5):
            d = np.linalg.norm(anchors - p, axis=1) + 1e-9
            H = (p - anchors) / d[:, None]
            residual = ranges - d
            Hw = H * weights[:, None]
            rw = residual * weights
            try:
                dp, *_ = np.linalg.lstsq(Hw, rw, rcond=None)
            except np.linalg.LinAlgError:
                break
            p = p + dp
            if float(np.linalg.norm(dp)) < 1e-6:
                break
        return p
