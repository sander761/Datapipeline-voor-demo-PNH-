# Project Context

- **Owner:** joellehansenlove
- **Project:** Interactive viewer for bridge MKI (environmental cost) values per Dutch municipality, built on top of an existing Python geospatial data pipeline (scripts 01–08). The viewer shows a municipality map (zoom + filter on selection) and MKI graphs (from script 07), with a 0–100% (1% step) slider that dynamically rescales the graph values.
- **Stack:** Python; geopandas, pandas, plotly, PyYAML, openpyxl. Pipeline outputs are GeoPackage (`.gpkg`) + Excel per script under `output/<script>/`, in EPSG:28992 (RD New). `config.yaml` drives the municipalities (`gemeenten`), classification thresholds, and MKI kentallen.
- **Created:** 2026-08-10

## My Role

Tester / QA. I test the filtering, zoom, and scaling logic, hunt edge cases (empty municipality, missing MKI, slider bounds), and confirm work is done with a real run.

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->
- Key edge cases: municipality with no bridges, rows with `mki_ontbreekt=True`, slider at 0% and 100%, missing pipeline outputs.
- Scaling invariant: scaled total == source total * factor (within rounding).
- Project rule: "done" means a run with no blocking errors — verify, don't assume.
- Git: the owner (joellehansenlove) runs ALL git ops (add/commit/push/pull); agents edit files only and never run git write commands. (See `decisions.md`.)
