---
updated_at: 2026-08-12T14:28:38+02:00
focus_area: Bridge-MKI Streamlit viewer v1.3 UI-polish shipped (larger graph + viewer fonts, ~4× narrower composition bar) — awaiting owner visual confirm + commit
active_issues: []
---

# What We're Focused On

Interactive **Streamlit** viewer on top of the existing bridge-MKI pipeline:
municipality map (menu from `config.yaml`, zoom + filter on selection) + MKI graphs
(script 07) + a 0–100% (1% step) slider that rescales MKI at display time.

**v1.3 "UI-polish" is shipped** (styling-only: larger, readable graph + viewer
fonts and a ~4× narrower composition bar); now awaiting the owner's visual
confirmation of the sizes + commit.

## Status
- ✅ Team hired (Alien cast: Dallas, Ripley, Lambert, Parker, Brett + built-ins).
- ✅ Framework: **Streamlit** (approved 2026-08-10). See `decisions.md`.
- ✅ Viewer **v1 DONE** (🟡), **v1.1 DONE** (🟢), **v1.2 DONE** (🟢),
  then **v1.3 DONE** (🟢 — pure styling, verification folded into Brett).
- ✅ v1.3 delivered (UI-polish, styling-only — no logic/signature/order/colour/title change):
  - **Larger graph fonts (`viewer/charts.py`):** font constants (`TITEL_FONT=22`,
    `AS_TITEL_FONT=17`, `TICK_FONT=14`, `LEGENDA_FONT=14`, `BASIS_FONT=15`) + helper
    `_pas_lettertype_toe(fig)` on all 3 figures; margins slightly wider; height
    unchanged (500); stays streamlit-free.
  - **~4× narrower composition bar:** `update_traces(width=0.2)` on the samenstelling
    figure; bronhouder/profiel bars keep default width.
  - **Larger viewer-chrome fonts (`app.py`):** one `VIEWER_CSS` `<style>` constant +
    one `st.markdown(..., unsafe_allow_html=True)` after `st.set_page_config`; targeted
    Streamlit 1.51 selectors (metric value/label, markdown, caption, widget label,
    expander summary, h3). Map tooltip + graph fonts out of scope.
  - `pytest` → **80 passed** (was 76; +4 in `tests/test_styling.py`); no product bugs.
- Earlier: v1.2 = per-profiel multiplicative sliders + stacked layout/map-last + live
  scaled total metric (`viewer/scaling.py` `combineer_factoren`/`schaal_per_rij`).

## Next step
- Owner (joellehansenlove) to **visually confirm** the v1.3 font/bar sizes, then review
  & commit the v1.3 changes (`viewer/charts.py`, `app.py`, `tests/test_styling.py`).
- **No open blocking follow-ups from this round.**

Reminder: the owner runs ALL git ops; agents edit files only.
