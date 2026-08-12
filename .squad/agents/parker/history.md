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
- (2026-08-12) v1 shipped 🟡 approve-with-notes. I created `viewer/style.py` (`PROFIEL_KLEUREN`, verbatim from step 07) and `viewer/charts.py` (`build_charts -> list[Figure]`: fig1 scaled MKI/yr bar, fig2 100% composition — deliberately scale-invariant). Scaling exact on Amsterdam (1,578,993.40 → half → 0). Follow-up: column constants may move to a streamlit-free `viewer/schema.py`.
- Framework: **Streamlit** (approved 2026-08-10). Cache the GeoPackage read with `@st.cache_data`; return updated plotly figures when the slider factor or selected municipality changes.
- Scaling: apply `value * factor` (factor 0.0–1.0, 0.01 steps) at display time; never mutate source data.
- (2026-08-12, v1.1) `viewer/charts.py` now truly streamlit-free (imports `viewer.schema`, not `viewer.data`). Added the "MKI per jaar per bronhouder" graph (mirrors step 07: `_eerste_bronhouder` + `_mki_per_bronhouder`, scaled). `build_charts` now returns 3 figures ([0] profiel scaled / [1] bronhouder scaled / [2] samenstelling unscaled); index [0] held for Brett's scaling test. Byte-identical to step 07 (top G0362 = 77278.83).
- Git: the owner (joellehansenlove) runs ALL git ops (add/commit/push/pull); agents edit files only and never run git write commands. (See `decisions.md`.)
- (2026-08-12, v1.2) `build_charts(subset_gdf, factor)` → `build_charts(subset_gdf, effectieve_factoren)` (dict): scale PER ROW via `scaling.schaal_per_rij` **then** aggregate, so bronhouder totals reflect each bridge's own profiel factor; return order changed to `[bronhouder, profiel, samenstelling]`; samenstelling now responds to per-profiel but is global-invariant (0-guard kept); module stays streamlit-free. Verified on Amstelveen (`brug_1x2`=0.5 → only that bar halves).
- (2026-08-12, v1.3) UI-polish (styling-only) in `viewer/charts.py`: font constants (`TITEL_FONT=22`, `AS_TITEL_FONT=17`, `TICK_FONT=14`, `LEGENDA_FONT=14`, `BASIS_FONT=15`) + helper `_pas_lettertype_toe(fig)` on all 3 figures; narrowed the samenstelling bar via `update_traces(width=0.2)` (~4× narrower, bronhouder/profiel keep default width); bumped `FIGUUR_MARGE`, height unchanged (500). No logic/signature/order/colour/title change; stays streamlit-free.
