# Tier 7 — Offline Data Bundles

**Role:** ship the world with the device. Zero internet ever required.

## Layers

| Layer | Source | Size budget | Format |
|---|---|---|---|
| Vector maps (256 LOD) | OpenStreetMap planet PBF + Mapbox vector tiles | 60–150 GB global | MBTiles |
| Satellite imagery | Sentinel-2, Landsat, ESA WorldCover | 100–500 GB | COG GeoTIFF |
| DEM (elevation) | SRTM 1″ + ASTER GDEM | 30 GB global | GeoTIFF |
| Bathymetric maps | GEBCO 2024 | 4 GB | NetCDF |
| Radio fingerprint DB | crowd-sourced + base-stations | 100 MB / city | SQLite + PMTiles |
| Cellular tower DB | OpenCellID + Mozilla MLS | 1.5 GB global | SQLite |
| BLE beacon DB | building owners + crowd | 50 MB / city | SQLite |
| Geomagnetic field | NOAA WMM 2025, EMAG2 v3 | 200 MB | NetCDF |
| Terrain features | derived (slope, aspect, curvature) | 20 GB global | GeoTIFF |

## Components

- `tile_server.py` — local MBTiles + PMTiles server for offline maps
- `dem_query.py` — bilinear elevation lookup at any (lat, lon)
- `bathy_query.py` — depth lookup from GEBCO
- `radio_fp_db.py` — k-NN radio fingerprint matcher
- `magnetic_model.py` — WMM 2025 declination/inclination at (lat, lon, alt, t)
- `ephemeris_cache.py` — JPL DE440 daily window prefetch

## Update strategy (per GODSKILL v11.0 R10)

- Weekly delta downloads when online
- Cryptographic signatures (Ed25519) on every bundle
- LRU eviction when device storage <10 % free
- Differential updates via `bsdiff` to minimize bandwidth

## References

- OpenStreetMap planet — planet.openstreetmap.org
- GEBCO 2024 — gebco.net
- NOAA WMM — ngdc.noaa.gov/geomag/WMM
- JPL DE440 — naif.jpl.nasa.gov
