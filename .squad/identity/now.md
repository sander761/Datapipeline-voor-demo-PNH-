---
updated_at: 2026-08-10T12:06:13+02:00
focus_area: Bridge-MKI interactive viewer (Streamlit) — pre-build
active_issues: []
---

# What We're Focused On

Building an interactive **Streamlit** viewer on top of the existing bridge-MKI pipeline:
municipality map (menu from `config.yaml`, zoom + filter on selection) + MKI graphs
(script 07) + a 0–100% (1% step) slider that rescales MKI at display time.

## Status
- ✅ Team hired (Alien cast: Dallas, Ripley, Lambert, Parker, Brett + built-ins).
- ✅ Framework decided: **Streamlit** (approved 2026-08-10). See `decisions.md`.
- ⏸️ Build **not started** — owner will first generate the pipeline data inputs
  (run scripts to produce `output/06_mki/*.gpkg` and script 07 outputs) that the
  viewer reads.

## Next step (next session)
Once data inputs exist: Dallas scaffolds the Streamlit app skeleton + `requirements.txt`
(adds `streamlit`, `streamlit-folium`), then fan out — Ripley (shell + menu + slider),
Lambert (map + zoom + filter), Parker (graphs + scaling), Brett (tests).

Reminder: the owner runs ALL git ops; agents edit files only.
