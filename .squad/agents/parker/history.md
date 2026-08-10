# Project Context

- **Owner:** joellehansenlove
- **Project:** Interactive viewer for bridge MKI (environmental cost) values per Dutch municipality, built on top of an existing Python geospatial data pipeline (scripts 01–08). The viewer shows a municipality map (zoom + filter on selection) and MKI graphs (from script 07), with a 0–100% (1% step) slider that dynamically rescales the graph values.
- **Stack:** Python; geopandas, pandas, plotly, PyYAML, openpyxl. Pipeline outputs are GeoPackage (`.gpkg`) + Excel per script under `output/<script>/`, in EPSG:28992 (RD New). `config.yaml` drives the municipalities (`gemeenten`), classification thresholds, and MKI kentallen.
- **Created:** 2026-08-10

## My Role

Data & Visualization Engineer. I read the pipeline's MKI outputs, build the plotly graphs (mirroring script 07), and implement the 0–100% scaling factor with dynamic updates.

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->
- MKI columns: `mki_per_jaar` and `mki_totaal_100jaar` on layer `bruggen_mki` (script 06). Rows with `mki_ontbreekt=True` have no MKI — exclude them.
- Script 07 aggregates per `gekozen_gemeente_naam`, `profiel`, and `bronhouder`, with fixed `PROFIEL_KLEUREN` — reuse for consistency.
- Framework: **Streamlit** (approved 2026-08-10). Cache the GeoPackage read with `@st.cache_data`; return updated plotly figures when the slider factor or selected municipality changes.
- Scaling: apply `value * factor` (factor 0.0–1.0, 0.01 steps) at display time; never mutate source data.
- Git: the owner (joellehansenlove) runs ALL git ops (add/commit/push/pull); agents edit files only and never run git write commands. (See `decisions.md`.)
