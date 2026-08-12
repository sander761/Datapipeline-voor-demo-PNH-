# Project Context

- **Owner:** joellehansenlove
- **Project:** Interactive viewer for bridge MKI (environmental cost) values per Dutch municipality, built on top of an existing Python geospatial data pipeline (scripts 01–08). The viewer shows a municipality map (zoom + filter on selection) and MKI graphs (from script 07), with a 0–100% (1% step) slider that dynamically rescales the graph values.
- **Stack:** Python; geopandas, pandas, plotly, PyYAML, openpyxl. Pipeline outputs are GeoPackage (`.gpkg`) + Excel per script under `output/<script>/`, in EPSG:28992 (RD New). `config.yaml` drives the municipalities (`gemeenten`), classification thresholds, and MKI kentallen.
- **Created:** 2026-08-10

## My Role

Geospatial Engineer. I own geometry loading, reprojection (28992 → web CRS), map rendering, zoom-to-municipality, and spatial filtering to the selected municipality.

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->
- All pipeline geometry is EPSG:28992 (RD New); reproject to EPSG:4326/3857 for web maps. `common.TARGET_CRS = 28992`.
- Bridges carry a `gekozen_gemeente_naam` attribute — use it for municipality filtering rather than re-running a spatial join.
- (2026-08-12) v1 shipped 🟡 approve-with-notes. I created `viewer/geo.py` (`to_wgs84`, `bounds_wgs84`) and `viewer/map.py` (`build_map -> folium.Map`: real polygons, OSM basemap, `fit_bounds`) — Streamlit-free, verified on real data. Perf note (v1.1/v2): Amsterdam ~3364 polygons ≈ 7.0 MB map-HTML/rerun; `simplify_tolerance=1.0` cut it ~77% (~1.6 MB).
- Framework: **Streamlit** (approved 2026-08-10). Map via `streamlit-folium`; use `total_bounds` (reprojected 28992→4326) + `fit_bounds` to zoom to the selected municipality.
- Use `common.read_layer()` to load GeoPackage layers with consistent CRS handling.
- (2026-08-12, v1.1) `viewer/map.py` → `build_map(map_gdf)` now consumes Dallas's cached, draw-ready EPSG:4326 layer; removed internal reproject/simplify + the old `simplify_tolerance` param (that logic now lives cached in `data.get_map_geometry`). Amstelveen map HTML 768 KB → 339 KB (−55,8%); module stays streamlit-free (schema import).
- Git: the owner (joellehansenlove) runs ALL git ops (add/commit/push/pull); agents edit files only and never run git write commands. (See `decisions.md`.)
