# Project Context

- **Owner:** joellehansenlove
- **Project:** Interactive viewer for bridge MKI (environmental cost) values per Dutch municipality, built on top of an existing Python geospatial data pipeline (scripts 01–08). The viewer shows a municipality map (zoom + filter on selection) and MKI graphs (from script 07), with a 0–100% (1% step) slider that dynamically rescales the graph values.
- **Stack:** Python; geopandas, pandas, plotly, PyYAML, openpyxl. Pipeline outputs are GeoPackage (`.gpkg`) + Excel per script under `output/<script>/`, in EPSG:28992 (RD New). `config.yaml` drives the municipalities (`gemeenten`), classification thresholds, and MKI kentallen.
- **Created:** 2026-08-10

## My Role

Viewer Developer. I own the dashboard shell, layout, the municipality menu (from `config.yaml`), toggles, and the slider control — and the wiring that makes selection + slider drive the map and graphs live.

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->
- Municipality menu must come from `common.get_gemeenten()` / `config.yaml`, never a hardcoded list.
- Selection state feeds two consumers: Lambert's map (zoom + filter) and Parker's graphs (filter + scale).
- Framework: **Streamlit** (approved by owner 2026-08-10). Reuse script 07 figures; cache the GeoPackage read with `@st.cache_data`; municipality menu from `common.get_gemeenten()`; maps via `streamlit-folium` `fit_bounds` for zoom-to-municipality.
- Git: the owner (joellehansenlove) runs ALL git ops (add/commit/push/pull); agents edit files only and never run git write commands. (See `decisions.md`.)
