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
- (2026-08-12) v1 shipped 🟡 approve-with-notes. I created `tests/` (conftest + 5 files: scaling, data, charts, geo_map, app_smoke); `pytest` → 26 passed, 0 failed, no product bugs. Scaling proven on figure 1 (figure 2 is scale-invariant). Data loaded directly via `common.read_layer` to keep Streamlit cache/run-context out. Residual risk: `mki_ontbreekt=True` absent in current data.
- Project rule: "done" means a run with no blocking errors — verify, don't assume.
- (2026-08-12, v1.1) Updated `tests/` for schema/exclusion/`get_map_geometry`/the new `build_map(map_gdf)` signature/3 charts incl. bronhouder scaling + step-07 parity/app smoke (Amsterdam absent, Amstelveen present). Full suite: **52 passed** (was 25). No product bugs; config-absent cases via `monkeypatch` (config.yaml untouched).
- Git: the owner (joellehansenlove) runs ALL git ops (add/commit/push/pull); agents edit files only and never run git write commands. (See `decisions.md`.)
- (2026-08-12, v1.2) Updated `tests/`: new `amstelveen` fixture; `test_scaling.py` covers `combineer_factoren`/`schaal_per_rij` incl. multiplicative-master proofs (hand-frames + real Amstelveen) + no-mutation; `test_charts.py` rewritten for the dict signature with **title-pinning** (not index); app smoke asserts sliders + the dropping total-metric + ≥3 stacked charts. Full suite: **76 passed** (was 44/8 mid-flight). No product bugs.
- (2026-08-12, v1.3) Added `tests/test_styling.py` (+4 guards, figures pinned on title): v1.3 font sizes on all 3 figures (title 22 / layout 15 / legend 14 / tick 14 / axis-title 17); samenstelling bar `width==0.2`; bronhouder/profiel `width is None`; AppTest boots with exactly one `<style>` block. Full suite: **80 passed** (76 baseline + 4). No production code touched; no product bugs.
