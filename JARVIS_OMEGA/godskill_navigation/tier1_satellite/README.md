# Tier 1 — Satellite Positioning

**Target accuracy:** ±0.5 m outdoor (open-sky), ±2 cm with RTK, ±5 m urban-canyon (multi-constellation rescue).

## Constellations

| System | Owner | Frequencies | Notes |
|---|---|---|---|
| GPS    | USA    | L1 (1575.42), L2 (1227.60), L5 (1176.45) MHz | baseline; full ICD documented |
| GLONASS| Russia | G1 (1602.0), G2 (1246.0) MHz | FDMA — channel-per-satellite |
| Galileo| EU     | E1 (1575.42), E5a (1176.45), E5b (1207.14), E6 (1278.75) MHz | best multi-frequency civil access |
| BeiDou | China  | B1I (1561.098), B1C (1575.42), B2a (1176.45), B2b (1207.14), B3I (1268.52) MHz | global since 2020 |
| QZSS   | Japan  | L1, L2, L5, L6 + LEX | Asia-Pacific augmentation |
| NavIC  | India  | L5 (1176.45), S-band (2492.028) MHz | regional, dual-frequency |

## Components to implement

- `multi_constellation_receiver.py` — fuse all 6 constellations; pick best 8–12 SVs by GDOP
- `rtk_engine.py` — Real-Time Kinematic with NTRIP correction stream; integer ambiguity resolution (LAMBDA)
- `spoofing_detector.py` — clock-anomaly + signal-power + cross-constellation consistency checks
- `jamming_mitigation.py` — FFT-based interference detection; null-steering antenna control
- `iono_tropo_correction.py` — Klobuchar + Saastamoinen models; offline tables
- `pvt_solver.py` — weighted least-squares + Kalman-smoothed PVT (position-velocity-time)

## Offline assets needed

- BRDC (broadcast) ephemeris tables — last 24h
- Almanac files for each constellation
- Klobuchar α/β coefficients (cached daily)
- NTRIP base-station list (for opportunistic RTK)

## References

- RTKLIB (BSD) — open-source RTK reference implementation
- GNSS-SDR — software-defined receiver
- IS-GPS-200, ICD-GLONASS, Galileo OS SIS ICD, BeiDou ICD-B1I/B2a, QZSS IS, NavIC SIS-ICD
