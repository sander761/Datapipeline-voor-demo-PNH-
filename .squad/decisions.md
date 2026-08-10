# Squad Decisions

## Active Decisions

### 2026-08-10: Project working rules (from `context.md`)
**By:** joellehansenlove (owner) — captured at team setup.
These apply to all agents on this project:
1. **Always test your work.** Work is "done" only when there are no blocking errors in the code.
2. **Git is fully owned by the owner.** Agents must NOT run any git write commands — no `git add`, `git commit`, `git push`, or `git pull`. Agents make file edits only; joellehansenlove performs all adding, committing, pushing, and pulling.
3. **Ask, don't assume.** When unsure or something is unclear, ask joellehansenlove for feedback rather than guessing.
4. **Efficient and simple.** Keep code efficient and as simple as the requirement allows.
5. **Clean and human-readable.** Meaningful names, comments where necessary, follow language style best practices.
6. **Modular and reusable.** Structure code so pieces can be reused.
7. **Parametrize, don't hardcode.** Drive behavior from `config.yaml` (municipalities, thresholds, MKI kentallen) — avoid hardcoded values.
8. **Context can evolve.** These rules may change when the owner says so; feedback on workflow is welcome.

### 2026-08-10: Viewer reads the pipeline, does not recompute
**By:** Squad (Coordinator) — architectural guardrail for the viewer.
The viewer is a thin layer over the existing pipeline. It reads script 06/07 outputs (GeoPackage `bruggen_mki`, aggregations) and **applies the 0–100% slider factor at display time** (`value * factor`, factor 0.0–1.0 in 0.01 steps). It must never mutate source data or recompute MKI. Pipeline geometry is EPSG:28992 (RD New) and must be reprojected for web maps.

### 2026-08-10: Viewer framework — Streamlit (approved)
**By:** joellehansenlove (owner), on Dallas's recommendation.
The interactive viewer will be built with **Streamlit**. Rationale: plotly- and geopandas-native, so we reuse script 07's figures and `PROFIEL_KLEUREN` with minimal glue; least boilerplate (fits the simple/clean/modular rules); fastest path to a runnable, shareable single-user demo. The app's compute is light (one cached GeoPackage read + attribute filter on `gekozen_gemeente_naam` + linear MKI scaling), so the rerun model feels instant. Implementation notes: cache the GeoPackage read with `@st.cache_data`; municipality menu from `common.get_gemeenten()`; maps via `streamlit-folium` (`fit_bounds`) for zoom-to-municipality; slider `st.slider(0,100,100,1)` applying `value * factor` at display time. Revisit Dash only if this grows into a heavier, multi-user production dashboard.

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
