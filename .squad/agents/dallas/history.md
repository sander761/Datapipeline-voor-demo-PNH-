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
- (2026-08-12) Verified data facts from `output/06_mki/06_mki.gpkg`: layer is **`bruggen_mki`**, **4746 rows**; municipality-selection column is **`gekozen_gemeente_naam`**; MKI columns are **`mki_per_jaar`** and **`mki_totaal_100jaar`**; there is a **profiel** column; geometry is **MultiPolygon**. Use these exact names in the viewer.
- (2026-08-12) Streamlit scaffold + `VIEWER_PLAN.md` are **done and runnable** (verified via AppTest), pending owner confirmation of the plan + 5 open questions before the Ripley/Lambert/Parker/Brett build fan-out.
- (2026-08-12) Owner confirmed the plan; team built v1 and I reviewed it end-to-end (AppTest across all 4 municipalities + real-server HTTP 200). Verdict **🟡 approve-with-notes** — v1 shipped. 3 non-blocking follow-ups logged in `decisions.md`: streamlit-free `viewer/schema.py`; `use_container_width`→`width='stretch'`; Amsterdam map-payload perf (cache/simplify/representative-points).
- (2026-08-12, v1.1) Led v1.1: created streamlit-free `viewer/schema.py` + refactored `viewer/data.py` (config-driven Amsterdam exclusion, cached `get_map_geometry`) + a `viewer:` section in `config.yaml`; wrote the Phase-2 perf contract (`@st.fragment` + simplify 2.0 m + cache). Integration review **🟢 GREEN** — heaviest shown map ~249 KB vs Amsterdam's old ~6,5 MB (~26× lighter), all 3 owner requests delivered, guardrail held. The 3 v1.0 follow-ups are now resolved.
- (2026-08-12, v1.2) Led v1.2 per-profiel scaling: added `scaling.combineer_factoren` + `scaling.schaal_per_rij` (effective factor = `globaal × profiel`, clamp `[0,1]`, display-time only, source untouched) and wrote the Phase-2 contract. Integration review **🟢 GREEN** — multiplicative-master proven on real Amstelveen data (metric == Σ per-profiel bars in every scenario); sliders + metric inside the `@st.fragment`, `st_folium` outside; guardrail held; **76 tests green**.
