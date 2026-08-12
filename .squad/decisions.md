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

### 2026-08-12: Viewer v1 scope confirmed by owner (ship)
**By:** Squad (Coordinator), confirming owner sign-off (joellehansenlove) on `VIEWER_PLAN.md`.
Owner confirmed the plan; v1 is built and shipped with verdict **🟡 approve-with-notes**. Confirmed v1 scope:
- Bridges are drawn as **real polygons** (not points/markers).
- Basemap is **OpenStreetMap**.
- **`mki_per_jaar`** is the lead MKI metric.
- The **neighborhood layer (script 08) is deferred to v2**.
- `PROFIEL_KLEUREN` is **copied into `viewer/style.py`** (single source for map + chart colours).
- The **0–100% slider scales the graphs and the MKI metric at display time, not the map** (map geometry is slider-independent in v1).
Ship v1; the review notes below are non-blocking follow-ups.

### 2026-08-12: Viewer charts + style modules (`viewer/charts.py`, `viewer/style.py`)
**By:** Parker (Data & Visualization Engineer).
- `viewer/style.py` holds `PROFIEL_KLEUREN` (8 profiles), copied verbatim from `07_overzichten.py`; Lambert's map imports the same dict (`from viewer.style import PROFIEL_KLEUREN`) so map and chart colours stay in sync.
- `viewer/charts.py` exposes `build_charts(subset_gdf, factor) -> list[plotly.graph_objects.Figure]` — a pure module that renders nothing (`app.py` calls `st.plotly_chart`).
Decisions affecting others: (1) lead MKI metric = `mki_per_jaar` (owner-approved 2026-08-12); column names come from `viewer.data` constants, never hardcoded. (2) Figure 1 = scaled MKI/year per profile (bar) — the slider factor is applied here via `scaling.scale_series` just before plotting; this is the figure where scaling is visible/testable. (3) Figure 2 = profile composition (100% stacked bar) — deliberately scale-independent so it stays readable at 0% (no divide-by-zero); **Brett tests scaling on figure 1, not figure 2.** (4) Empty/no-MKI subset → `build_charts` returns `[]` and `app.py` shows the "no bridges" message. (5) Profile order is always `list(PROFIEL_KLEUREN)` for legend/colour consistency with step 07.
Verified on real data (Amsterdam = 3364 bridges): sum-y at factor 1.0 = 1,578,993.40; at 0.5 = 789,496.70 (exact half); at 0.0 = 0.00; empty subset → `[]`.

### 2026-08-12: Viewer test suite conventions (`tests/`)
**By:** Brett (Tester / QA).
Pytest suite under `tests/` (Brett owns `tests/`; no other agent edits it). `conftest.py` provides a session-scoped `bridges` fixture that reads the GeoPackage once via `common.read_layer(get_gpkg_path("06_mki"), "bruggen_mki")` (no `st.cache_data`, no Streamlit run-context), plus fresh function-scoped `amsterdam`/`diemen`/`empty` subsets via `data.filter_by_municipality`; injects project root into `sys.path`. Test files: `test_scaling.py`, `test_data.py`, `test_charts.py`, `test_geo_map.py`, `test_app_smoke.py`.
Conventions affecting others: (1) `tests/` is Brett's — change behaviour in the source module and Brett updates the test. (2) Scaling is proven on figure 1, not figure 2 (scale-invariant, per Parker). (3) Tests load data directly via `common.read_layer`, not `data.load_bridges()`, to keep the Streamlit cache/run-context out of tests. (4) Tester does not modify source (reviewer-lockout) — bugs are reported to the Coordinator, not self-fixed.
Result: `python -m pytest tests -q` → **26 passed, 0 failed** (~15 s), no product bugs. Residual risk: `mki_ontbreekt=True` never occurs in current data (column all False), so that path is covered by code logic but not by live data.

### 2026-08-12: Viewer v1 review verdict + follow-ups (🟡 approve-with-notes)
**By:** Dallas (Lead / Architect) — final integration review.
End-to-end verification on real modules (no stubs), no blocking errors → **v1 may ship**. Evidence: Streamlit AppTest on `app.py` green across all 4 municipalities (Amsterdam 3364 → 1,578,993 MKI/yr at 100%; Diemen 231, Ouder-Amstel 365, Amstelveen 786; total 4746); slider 100/50/0% on Amsterdam = 1,578,993 → 789,497 (exact half) → 0; folium.Map + chart elements present; `build_charts([]) == []` and `build_map(empty)` gives a valid NL-centred map. Real-server smoke: `streamlit run` headless boots without traceback, HTTP 200 on root + `/_stcore/health`; process then stopped. Static: `py_compile` OK, imports resolve, signatures match contracts.
Non-blocking follow-ups: (1) `viewer/charts.py` transitively imports streamlit (via `viewer.data`) — consider a streamlit-free `viewer/schema.py` holding the pipeline column constants (`BRIDGE_LAYER`, `GEMEENTE_COLUMN`, `PROFIEL_COLUMN`, `MKI_JAAR_COLUMN`, `MKI_TOTAAL_COLUMN`, `MKI_ONTBREEKT_COLUMN`), re-exported by `data.py`, imported by `charts.py`/`map.py`. (2) `use_container_width=True` is deprecated in Streamlit 1.51 → migrate to `width='stretch'` (small isolated edit in `app.py`). (3) Perf: Amsterdam ~3364 polygons ≈ 7.0 MB map-HTML per rerun; cache the map per municipality (`@st.cache_data` / `st.fragment`) and/or simplify geometry (`simplify_tolerance=1.0` gave ~1.6 MB, −77%) or draw representative points (v1.1/v2).

### 2026-08-12T11:24:19+02:00: Viewer v1.1 — performance, layout & bronhouder-grafiek (consolidated)
**By:** Dallas, Lambert, Parker, Ripley, Brett — v1.1 "verbeter de viewer"-batch (owner: joellehansenlove).

Consolideert de zes v1.1-inboxbeslissingen (Dallas foundation + integratiereview, Lambert map-perf, Parker charts-bronhouder, Ripley app-layout, Brett tests). Lost de drie niet-blokkerende v1.0-follow-ups op.

**Wat:**
- **Amsterdam uitgesloten op viewer-niveau (config-gedreven, omkeerbaar, pipeline ongemoeid).** Nieuwe `viewer:`-sectie in `config.yaml` (`uitgesloten_gemeenten: [Amsterdam]`, `kaart_simplify_tolerantie_m: 2.0`). `data.get_municipalities()` = `common.get_gemeenten()` **minus** `uitgesloten_gemeenten` (hoofdletter-/spatie-ongevoelig; ontbrekende sectie/sleutel → niets uitsluiten, veilige standaard). De pipeline-`gemeenten`-lijst en scripts 01–08 blijven ongemoeid; Amsterdam zit nog gewoon in de GeoPackage (`filter_by_municipality` geeft er nog data voor). Reversibel: haal Amsterdam uit de config en hij staat weer in het menu.
- **Performance-aanpak.** (1) **Schema-split:** streamlit-vrije `viewer/schema.py` met alle pipeline-kolomconstanten (incl. nieuw `BRONHOUDER_VALUES_COLUMN = "bronhouder_values"`), her-geëxporteerd door `data.py` en direct geïmporteerd door `charts.py`/`map.py` — die twee modules zijn nu écht streamlit-vrij (v1.0-follow-up 1). (2) **Simplify-tolerantie 2.0 m** (toegepast in 28992 vóór reproject). (3) **Gecachte, tekenklare geometrie per gemeente:** `data.get_map_geometry(gemeente, tol)` (`@st.cache_data`, EPSG:4326, alleen `[profiel, geometry]`, eventueel al vereenvoudigd); `build_map(map_gdf)` consumeert die laag en reprojecteert/vereenvoudigt niet meer zelf (oude `simplify_tolerance`-param vervallen). (4) **Schuif-in-fragment:** de MKI-schuif verhuisde naar een module-niveau `@st.fragment` bovenaan; de kaart (`st_folium`) staat erbuiten/eronder met `key=f"kaart_{gemeente}"` + `returned_objects=[]`, zodat een schuiftik alleen de grafieken herrekent en de kaart-payload **niet** opnieuw verstuurd wordt (een gemeentewissel stuurt wél de volledige rerun → kaart + grafieken, VIEWER_PLAN §4 behouden). Resultaat: zwaarste getoonde kaart ~249 KB (Amstelveen) t.o.v. Amsterdams oude ~6,5 MB — factor **~26** lichter; per-kaart HTML −55,8…−73,9%.
- **Nieuwe grafiek "MKI per jaar per bronhouder".** `charts.py` kreeg `_eerste_bronhouder` + `_mki_per_bronhouder` (spiegelt stap 07: eerste/dominante bronhouder uit de puntkomma-lijst, `~mki_ontbreekt`, `groupby.sum().sort_values(desc)`). `build_charts(subset, factor)` (signature ongewijzigd) geeft nu **3** figuren: `[0]` MKI/jaar per profiel (geschaald), `[1]` MKI/jaar per bronhouder (geschaald, één kleur `#3b6ea5`), `[2]` profielsamenstelling (bewust ongeschaald). Index `[0]` bewust vastgehouden (Brett's schalingtest pint deze). Byte-identiek aan stap 07 (top `G0362` = 77278.83 op Amstelveen).
- **Layout omgedraaid.** Grafieken bovenaan, naast elkaar en volledig zichtbaar (`st.columns(len(figuren))`, ruime marges + gedraaide labels); kaart vol-breed eronder. Zijbalk houdt alleen de gemeentekeuze.
- **Deprecation-migratie.** `st.plotly_chart(..., use_container_width=True)` → `width='stretch'` (Streamlit 1.51). `st_folium(..., use_container_width=True)` **bewust ongewijzigd** — dat is een eigen parameter van streamlit_folium (`width` is daar een pixel-int), geen core-deprecatie.
- **Tests.** `tests/` bijgewerkt voor schema/exclusie/`get_map_geometry`/nieuwe `build_map`-signature/3 grafieken incl. bronhouder-schaling/app-smoke. Volledige suite: **52 passed** (was 25). Geen productiebugs.

**Waarom:**
- Amsterdam (3364 polygonen, ~6,5 MB) domineerde de kaart-payload en maakte de viewer traag; uitsluiten op config-niveau (i.p.v. in code) houdt het omkeerbaar en laat de pipeline intact.
- De kolomconstanten naar een streamlit-vrije `schema.py` splitsen verwijdert de transitieve streamlit-import uit `charts.py`/`map.py` en houdt die modules puur/testbaar.
- Simplify + gecachte 4326-laag verkleinen de payload structureel; de schuif-in-fragment lost de kern-responsiviteit op (een schuiftik hoeft de kaart niet opnieuw te versturen), terwijl één gemeentekeuze beide consumenten blijft sturen.
- De bronhouder-grafiek geeft de owner het per-bronhouder-beeld uit stap 07 nu ook interactief.
- De deprecation-migratie haalt de enige core-waarschuwing weg zonder de kaart te breken.

**Review:** Dallas integratiereview **🟢 GROEN** — alle drie owner-verzoeken echt ingelost en op echte data bevestigd; guardrail gehouden (viewer alleen-lezen, schuif schaalt puur bij weergave, bron-MKI nooit gemuteerd/herrekend, `gemeenten` + scripts 01–08 ongemoeid). Geen productiedefecten. Klaar om te mergen/committen door de owner.

### 2026-08-12T13:05:54+02:00: Viewer v1.2 — per-profiel schuiven (multiplicatieve master), gestapelde layout & live totaal-metric (consolidated)
**By:** Dallas, Parker, Ripley, Brett — v1.2 "per-profiel sliders + layout + totaal-metric"-batch (owner: joellehansenlove).

Consolideert de vijf v1.2-inboxbeslissingen (Dallas foundation + integratiereview, Parker charts, Ripley app, Brett tests).

**Wat:**
- **Per-profiel schaling = multiplicatieve master.** Naast de bestaande globale MKI-schuif krijgt de viewer één schuif per profiel (uit `PROFIEL_KLEUREN`, alleen de profielen die in de gekozen gemeente voorkomen). De effectieve factor per profiel = **`globale_factor × profiel_factor(profiel)`**. Alles op 100% → geen verandering; de globale schuif alléén gedraagt zich exact als v1.1; elke profiel-schuif fijnregelt zijn eigen type; meerdere schuiven tegelijk actief; grafieken **én** de totaal-metric herschalen live. Clamp `[0,1]` (geen boost >100%); ontbrekend/None/NaN → 1.0.
- **De rekenregel leeft op één plek (`viewer/scaling.py`), puur bij weergave.** Nieuw: `combineer_factoren(globale_factor, profiel_factoren, alle_profielen) -> dict` (effectieve factor per canoniek profiel; ontbrekend → globaal × 1.0; met clamping) en `schaal_per_rij(waarden, profielen, effectieve_factoren, standaard=1.0) -> Series` (per-rij weergavewaarde; geeft een **nieuwe** Series, muteert de invoer nooit). `percentage_to_factor`/`apply_factor`/`scale_series` blijven behouden. Module blijft zuiver (alleen pandas). Bron-MKI wordt nooit gemuteerd of herrekend (guardrail 2026-08-10 gehouden).
- **Charts: schaal PER RIJ, dán aggregeren.** `build_charts(subset_gdf, factor)` → **`build_charts(subset_gdf, effectieve_factoren)`** (dict i.p.v. scalar). `charts.py` schaalt elke rij via `scaling.schaal_per_rij` **vóór** het groeperen, zodat bronhouder-totalen elk de eigen profiel-factor van die brug weerspiegelen (een bronhouder kan meerdere profielen bezitten). Retourvolgorde gewijzigd naar de owner-tekenvolgorde **`[bronhouder, profiel, samenstelling]`** (was `[profiel, bronhouder, samenstelling]`); 0-guard op de samenstelling behouden; module blijft streamlit-vrij. Gedragsnotitie: de **Profielsamenstelling (%)** reageert nu **wél** op per-profiel-schuiven, maar blijft invariant voor de globale schuif (de globale factor valt in de verhouding weg) — bewust, owner-zichtbaar, in de docstring benoemd.
- **App: gestapelde layout, kaart als laatste, sliders + live totaal-metric.** Grafieken staan nu **vol-breed onder elkaar** (verticale lus, volgorde bronhouder → profiel → samenstelling); de kaart komt **als laatste**, vol-breed, **buiten** het `@st.fragment` (`st_folium` met gemeente-sleutel + `returned_objects=[]` → een schuiftik verstuurt de kaart niet opnieuw). Toegevoegd: de globale schuif + één per-profiel-schuif per aanwezig profiel in een `st.expander("Schaal per profiel (%)")` (stabiele `key=f"schaal_{profiel}"`; profiel zonder bruggen in de gemeente → geen schuif). De effectieve map wordt via `scaling.combineer_factoren(globale_factor, profiel_factoren, PROFIEL_KLEUREN.keys())` gebouwd. **Live "Totale MKI per jaar (geschaald)"-metric hersteld** naast "Aantal bruggen" (beide binnen het fragment), berekend met dezelfde regel als de grafieken: `schaal_per_rij(geldig[MKI_JAAR_COLUMN], geldig[PROFIEL_COLUMN], effectieve).sum()` op `~mki_ontbreekt`-rijen. Maat = **`mki_per_jaar`** (consistent met de per-jaar-grafieken; één-regel-wissel naar `mki_totaal_100jaar` mogelijk als de owner dat later wil). NL-notatie (`.0f`, komma→punt).
- **Tests.** `tests/` bijgewerkt: nieuwe `amstelveen`-fixture; `test_scaling.py` dekt `combineer_factoren`/`schaal_per_rij` incl. multiplicatieve-master-bewijzen (hand-frames + echte Amstelveen-data) en no-mutation; `test_charts.py` herschreven voor de dict-signatuur met **titel-pinning** (niet op index) + per-profiel-onafhankelijkheid + samenstelling-gedrag + 0-guard; `test_app_smoke.py` assert de sliders (globaal + per-profiel), de dalende totaal-metric en de ≥3 gestapelde grafieken. Volledige suite: **76 passed** (was 44/8 mid-flight). Geen productiebugs.

**Waarom:**
- De owner wil per bridge-type kunnen fijnregelen zonder het globale beeld te verliezen; de multiplicatieve master geeft precies dat (globaal × profiel), houdt 100% neutraal en laat de globale schuif zich exact als voorheen gedragen.
- De rekenregel in `scaling.py` centraliseren (één bron van waarheid, per rij vóór aggregatie) zorgt dat de metric én alle grafieken tot op de cent overeenkomen en dat bronhouder-totalen de juiste per-profiel-factor per brug krijgen.
- Vol-breed gestapelde grafieken met de kaart als laatste lossen de "te krap naast elkaar"-klacht op; de kaart buiten het fragment houdt de v1.1-performancewinst (een schuiftik verstuurt de kaart niet opnieuw).
- De live geschaalde totaal-metric geeft de owner het directe "wat kost deze gemeente per jaar bij deze schaal"-getal terug, naast de brugtelling.

**Review:** Dallas integratiereview **🟢 GROEN** — de drie owner-verzoeken volledig en correct geïmplementeerd en schoon geïntegreerd over `scaling.py`/`charts.py`/`app.py`. Multiplicatieve-master bewezen op echte Amstelveen-data (rauw 136.144,24; globaal 0.5 → 68.072,12; `brug_1x2`=0.5 bij globaal 1.0 → 106.988,46 met alleen dat profiel gehalveerd; globaal 0.5 én `brug_1x2`=0.5 → `brug_1x2` ×0.25); de metric is in élk scenario numeriek gelijk aan de som van de per-profiel-balken; sliders + metric binnen het fragment, `st_folium` erbuiten (kaart niet opnieuw verstuurd); guardrail gehouden (viewer alleen-lezen, bron-MKI nooit gemuteerd/herrekend; `gemeenten` + scripts 01–08 ongemoeid). Geen productiedefecten; **76 tests groen**. Klaar om te mergen/committen door de owner.

### 2026-08-12T14:28:38+02:00: Viewer v1.3 — UI-polish (grotere fonts + smallere samenstelling-staaf) (consolidated)
**By:** Parker, Ripley, Brett — v1.3 "UI-polish"-batch (owner: joellehansenlove).

Consolideert de drie v1.3-inboxbeslissingen (Parker charts-fonts, Ripley app-chrome-fonts, Brett styling-guards). **Pure styling** — geen logica-, signatuur-, volgorde-, kleur- of titelwijziging.

**Wat:**
- **Grafiek-fonts groter + consistent (`viewer/charts.py`).** Nieuwe font-constanten `TITEL_FONT=22`, `AS_TITEL_FONT=17`, `TICK_FONT=14`, `LEGENDA_FONT=14`, `BASIS_FONT=15` + helper `_pas_lettertype_toe(fig)` toegepast op alle 3 de figuren (zet uitsluitend lettergroottes via `update_layout`/`update_xaxes`/`update_yaxes`; door plotly's recursieve merge blijven `title_x=0.5`, template, kleuren, legendatitel, `tickangle`/`automargin` en categorievolgorde ongemoeid).
- **Samenstelling-staaf ~4× smaller.** `fig.update_traces(width=0.2)` in `_figuur_samenstelling` (x-as = één categorie; ~0.8 → 0.2). `barmode="stack"`, kleuren en de 0-guard ongewijzigd. Bronhouder-/profiel-figuren houden standaardbreedte (`width is None`).
- **Marge iets ruimer** om afknippen door grotere fonts te voorkomen: `FIGUUR_MARGE` van `t70/b90/l60/r20` → `t90/b100/l70/r20`. `FIGUUR_HOOGTE` **ongewijzigd** (500) → grafiekgrootte gelijk. `charts.py` blijft streamlit-vrij.
- **Viewer-chrome-fonts iets groter (`app.py`).** Eén named constant `VIEWER_CSS` (`<style>`-blok) + precies één injectie `st.markdown(VIEWER_CSS, unsafe_allow_html=True)` direct ná `st.set_page_config`. Selectors geverifieerd tegen Streamlit 1.51: `stMetricValue` 2.5rem, `stMetricLabel` 1rem, `stMarkdownContainer p` 1.1rem, `stCaptionContainer p` 1rem, `stWidgetLabel` 1rem, `stExpander summary` 1.1rem, `stHeading h3` 1.9rem. Niets functioneels gewijzigd; **kaart-tooltips** (folium-iframe) en de **grafiek-fonts** (Parker) bewust buiten scope; geen globale `html/body`-font.
- **Tests (`tests/`).** Nieuw `tests/test_styling.py` (+4 guards, figuren op TITEL gepind): v1.3-lettergroottes op alle 3 figuren; samenstelling-staven `width==0.2`; bronhouder/profiel `width is None`; AppTest boot met precies **één** `<style>`-blok. Volledige suite: **80 passed / 0 failed** (76 baseline + 4 nieuw). Geen productie-defect.

**Waarom:**
- De owner vond de fonts te klein/onleesbaar en de enkele samenstellings-staaf te breed nu de grafieken vol-breed staan (v1.2). Grotere, geparametriseerde fonts + een smallere staaf maken de vol-brede layout leesbaar en gebalanceerd, zónder de grafiekgrootte of enige logica te wijzigen.
- Fonts als constanten + één helper (charts) en één `VIEWER_CSS`-constante + één injectie (app) houden de opmaak centraal, omkeerbaar en makkelijk bij te stellen; gerichte `data-testid`-selectors voorkomen neveneffecten.

**Review:** Geen aparte Dallas-integratiereview deze ronde (pure styling); de verificatie is in Brett gevouwen → **🟢 GROEN**, 80 tests groen, geen regressie/productie-defect. De owner bevestigt de maten visueel; daarna mergen/committen (owner doet alle git).

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
