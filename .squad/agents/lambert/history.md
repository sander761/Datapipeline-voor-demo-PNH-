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
- Framework: **Streamlit** (approved 2026-08-10). Map via `streamlit-folium`; use `total_bounds` (reprojected 28992→4326) + `fit_bounds` to zoom to the selected municipality.
- Use `common.read_layer()` to load GeoPackage layers with consistent CRS handling.
- Git: the owner (joellehansenlove) runs ALL git ops (add/commit/push/pull); agents edit files only and never run git write commands. (See `decisions.md`.)
