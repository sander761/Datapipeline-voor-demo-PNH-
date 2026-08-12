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
- (2026-08-12) v1 shipped 🟡 approve-with-notes. I finalized `app.py`: sidebar municipality selection + 0–100% slider wired to `st_folium(map_view.build_map(...))` and `st.plotly_chart(charts.build_charts(...))`, with empty/error handling; AppTest smoke passed. My follow-up: migrate `use_container_width=True` → `width='stretch'` in `app.py` (Streamlit 1.51 deprecation).
- Framework: **Streamlit** (approved by owner 2026-08-10). Reuse script 07 figures; cache the GeoPackage read with `@st.cache_data`; municipality menu from `common.get_gemeenten()`; maps via `streamlit-folium` `fit_bounds` for zoom-to-municipality.
- (2026-08-12, v1.1) Reworked `app.py`: graphs on top side-by-side, map full-width below; MKI slider moved into a module-level `@st.fragment` so a slider tick reruns only the charts (map not re-sent); wired `data.get_map_geometry(...)`; migrated `st.plotly_chart(..., width='stretch')`, kept `st_folium(use_container_width=True)` (own param of streamlit_folium).
- Git: the owner (joellehansenlove) runs ALL git ops (add/commit/push/pull); agents edit files only and never run git write commands. (See `decisions.md`.)
- (2026-08-12, v1.2) `app.py`: graphs stacked full-width (bronhouder → profiel → samenstelling), map **last** and outside the `@st.fragment`; added the global slider + one per-profiel slider per present profiel (from `PROFIEL_KLEUREN`) in an expander (effective map via `scaling.combineer_factoren`); restored a live "Totale MKI per jaar (geschaald)" metric next to "Aantal bruggen" via `schaal_per_rij(...).sum()` (uses `mki_per_jaar`). AppTest green.
- (2026-08-12, v1.3) UI-polish (styling-only) in `app.py`: one `VIEWER_CSS` `<style>` constant + one `st.markdown(..., unsafe_allow_html=True)` after `st.set_page_config`; Streamlit-1.51 `data-testid` selectors (metric value 2.5rem / label 1rem, markdown p 1.1rem, caption 1rem, widget label 1rem, expander summary 1.1rem, h3 1.9rem). No functional change; map folium tooltip + graph fonts (Parker) left out of scope; no global html/body font.
