# Project Context

- **Owner:** joellehansenlove
- **Project:** Interactive viewer for bridge MKI (environmental cost) values per Dutch municipality, built on top of an existing Python geospatial data pipeline (scripts 01–08). The viewer shows a municipality map (zoom + filter on selection) and MKI graphs (from script 07), with a 0–100% (1% step) slider that dynamically rescales the graph values.
- **Stack:** Python; geopandas, pandas, plotly, PyYAML, openpyxl. Pipeline outputs are GeoPackage (`.gpkg`) + Excel per script under `output/<script>/`, in EPSG:28992 (RD New). `config.yaml` drives the municipalities (`gemeenten`), classification thresholds, and MKI kentallen.
- **Created:** 2026-08-10

## My Role

Lead / Architect. I own the viewer's architecture, the framework recommendation (for user approval), scope, and final review. Key sources: `config.yaml`, `06_mki.py`, `07_overzichten.py`, `common.py`.

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->
- Pipeline uses EPSG:28992 (RD New); web maps need reprojection to EPSG:4326/3857. (Lambert owns this.)
- MKI is precomputed in script 06 (`mki_per_jaar`, `mki_totaal_100jaar`); the viewer should read, not recompute.
- Framework decision: **Streamlit**, approved by the owner 2026-08-10 (my recommendation). See `decisions.md`.
- Project rules (`context.md`): always test work; keep code simple, clean, modular, parametrized; ask when unsure — don't assume; the owner runs ALL git ops (add/commit/push/pull) — agents edit files only.
