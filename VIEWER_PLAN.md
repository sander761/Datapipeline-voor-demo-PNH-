# Bouwplan — Interactieve Brug-MKI-viewer (Streamlit)

> Status: **skelet draait**, wacht op akkoord van de owner voor de volledige bouw.
> Opgesteld door **Dallas** (Lead/Architect) — 2026-08-12.
> Framework: **Streamlit** (goedgekeurd 2026-08-10). Niet heropenen.

---

## 1. Doel & scope

Een **eenvoudige**, alleen-lezen webviewer die per gemeente laat zien waar de bruggen
liggen (kaart) en hoe hun MKI (milieukostenindicator) is opgebouwd (grafieken uit
stap 07). Eén schuif (0–100%, stappen van 1%) schaalt de getoonde MKI op het moment
van tonen. De viewer is een **dunne laag** boven de bestaande pipeline: hij leest de
GeoPackage-output van stap 06 en herberekent niets (zie `decisions.md`, 2026-08-10).

We beginnen **bewust klein**: eerst een werkende, leesbare kern; complexiteit komt later.

### Deferred — expliciet NIET in v1
- Meerdere gemeenten tegelijk of "alle gemeenten" naast elkaar.
- Kaart-kleuring/heatmap op MKI-waarde, legenda's, pop-ups met veel attributen.
- De buurtlaag (`08_buurten_mki.gpkg`) op de kaart (MKI per inwoner/m²) — kan in v2.
- De datakwaliteit-grafieken uit `mki_verdelingen.html` (violin/histogram).
- Foutenanalyse (`geen_brug`), bronhouder-uitsplitsing, Excel-download-knoppen.
- Meertaligheid, thema's, authenticatie, multi-user/performance-tuning.
- De schuif laten inwerken op de kaart-styling (in v1 raakt de schuif alleen de grafieken; zie §7).

---

## 2. File-/modulestructuur

Huidige structuur na het skelet (dit turn opgeleverd):

```
requirements.txt          # app- + pipeline-deps (streamlit, streamlit-folium, folium, ...)
app.py                    # entrypoint: paginaopzet, zijbalk (gemeente + schuif), layout, samenvatting
viewer/
  __init__.py             # pakketdocstring
  data.py                 # gecachte laders + pipeline-kolomnamen (contract)
  scaling.py              # value * factor (weergaveschaling)
common.py                 # (bestaand) pipeline-helpers — hergebruikt, niet aangepast
config.yaml               # (bestaand) gemeenten, drempels, MKI-kentallen — bron van waarheid
```

Wat de bouw **toevoegt** (nieuwe modules, klein gehouden):

```
viewer/
  geo.py                  # reprojectie 28992 -> 4326 + bounds per gemeente (Lambert)
  map.py                  # folium-kaart bouwen, zoom-to-gemeente, bruggen tekenen (Lambert)
  charts.py               # plotly-figuren uit stap 07, gefilterd + geschaald (Parker)
tests/
  test_scaling.py         # zuivere-functietests schaling (Brett)
  test_data.py            # laden/filteren op gemeente, edge cases (Brett)
```

Principe: alleen een module toevoegen als hij deze turn ook echt gebruikt wordt —
geen lege placeholders. `app.py` blijft de dunne dirigent; de logica zit in `viewer/`.

---

## 3. Data flow

```
config.yaml ──get_gemeenten()──► zijbalk-keuze (gemeente)
                                        │
06_mki.gpkg (laag: bruggen_mki) ──read_layer()──► GeoDataFrame (EPSG:28992)  [@st.cache_data]
                                        │
                         filter op gekozen_gemeente_naam == keuze
                                        ├────────────► kaart:  reproject 28992→4326, teken, fit_bounds
                                        └────────────► grafieken: aggregatie stap 07, × factor
```

**Geverifieerd tegen de echte data (2026-08-12):**

| Wat | Waarde |
|---|---|
| GeoPackage | `output/06_mki/06_mki.gpkg` |
| Laagnaam | **`bruggen_mki`** (enige laag) |
| Aantal rijen | 4.746 |
| CRS | **EPSG:28992** (RD New) |
| Geometrietype | **MultiPolygon** (bruggen zijn vlakken, geen punten) |
| Gemeentekolom | **`gekozen_gemeente_naam`** |
| Gemeentewaarden | Amsterdam (3364), Amstelveen (786), Ouder-Amstel (365), Diemen (231) — matcht `get_gemeenten()` |
| Profielkolom | **`profiel`** (8 waarden = sleutels van `PROFIEL_KLEUREN`) |
| MKI-kolommen | **`mki_per_jaar`**, **`mki_totaal_100jaar`** (beide float) |
| Markering | `mki_ontbreekt` (alle False in deze dataset) |
| Bronhouder | `bronhouder_values` (puntkomma-lijst; eerste = dominant) |

**Reprojectie:** de pipeline levert 28992; de webkaart heeft 4326 (WGS84) nodig.
`common.read_layer` houdt 28992 aan (bewust — de kaartlaag reprojecteert pas vlak
voor het tekenen, zodat andere berekeningen in meters blijven).

---

## 4. Gedrag bij gemeentewisseling (owner-eis)

Eén keuze in de zijbalk stuurt **zowel de kaart als de grafieken** — dat is het hele
punt van de viewer:

- **Selecteer "Amsterdam"** ⇒ de kaart **zoomt/filtert** naar Amsterdam (alleen
  Amsterdamse bruggen zichtbaar, `fit_bounds` op de Amsterdamse extent) **én** de
  grafieken tonen **alleen Amsterdams** bruggen.
- Streamlit's rerun-model maakt dit vanzelf consistent: `gekozen_gemeente` (uit de
  `st.selectbox`) is één bron van waarheid die per rerun opnieuw wordt gelezen. Bij
  elke wijziging draait het script opnieuw, filtert `filter_by_municipality()` de
  gecachte laag, en krijgen kaart én grafiek **dezelfde** gefilterde subset door.
- De gecachte volledige laag wordt niet opnieuw ingelezen (alleen gefilterd), dus de
  wissel voelt direct. In het skelet is dit al bewezen: wisselen naar Amstelveen gaf
  786 bruggen; de metric-waarden veranderden mee.

---

## 5. Kaart (Lambert)

- Techniek: **folium** via **`streamlit-folium`** (`st_folium`), met `fit_bounds`
  voor zoom-to-gemeente.
- Stappen: (1) filter op gemeente → (2) reprojecteer subset 28992→4326 in
  `viewer/geo.py` → (3) teken in `viewer/map.py`.
- **Let op — geometrie is MultiPolygon, geen punten.** Voor de *simpele* v1 twee
  opties, keuze aan Lambert:
  - **Representatiepunten** (`geometry.representative_point()`) als lichte markers —
    snelst, minst rommelig bij 3.364 objecten; of
  - de **polygonen** zelf via `folium.GeoJson` (zwaarder; overweeg alleen de subset
    per gemeente, niet alle 4.746 tegelijk).
- `fit_bounds` op de **bounds van de gefilterde subset** (of de gemeentegrens uit
  `01_download` → `gemeentegebied_selected`, optioneel in v1).
- Kleur per profiel via `PROFIEL_KLEUREN` (uit stap 07 overnemen) waar praktisch.
- Performance: alleen de gemeentesubset tekenen; de volledige laag blijft gecachet.

---

## 6. Grafieken (Parker)

- Techniek: **plotly**, dezelfde figuren als `07_overzichten.py`, maar **gefilterd op
  de gekozen gemeente**. Hergebruik `PROFIEL_KLEUREN` en de opzet van `bar_figuur`/
  `gestapelde_figuur` uit stap 07.
- **Let op — `07_overzichten.py` is niet importeerbaar:** een modulenaam die met een
  cijfer begint kan niet met `import 07_overzichten`. Kopieer daarom `PROFIEL_KLEUREN`
  (8 kleuren) naar een kleine gedeelde plek in `viewer/` (bv. `viewer/charts.py` of
  `viewer/style.py`). Netter voor de parametrisatie-regel is een `profiel_kleuren`-
  sectie in `config.yaml` die zowel de viewer als (later) stap 07 lezen — maar dat
  raakt de pipeline en is een owner-beslissing (zie open vraag 5).
- Kernfiguren voor v1 (uit `mki_overzicht.html`), nu voor één gemeente:
  1. **MKI per jaar per profiel** (staaf) — de kern.
  2. **MKI per jaar per profiel, gestapeld / genormaliseerd** (samenstelling).
  3. Optioneel: MKI per bronhouder (staaf) — alleen als het simpel blijft.
- Aggregatie: filter `mki_ontbreekt == False`, `groupby("profiel")[mki_per_jaar].sum()`.
  (In deze dataset is `mki_ontbreekt` overal False, maar de filter hoort er principieel.)
- **Schaling:** vermenigvuldig de geaggregeerde MKI-waarden met `factor`
  (`scaling.scale_series`) **vlak voor het plotten**. Nooit de bron muteren.

---

## 7. Gedrag van de schuif

- `st.slider("MKI-schaal (%)", 0, 100, 100, 1)` → `factor = pct/100`
  (via `scaling.percentage_to_factor`).
- Toepassing op **weergavemoment**: `getoond = waarde * factor`
  (`scaling.apply_factor` voor losse waarden, `scale_series` voor Series).
- **Reikwijdte in v1:** de schuif schaalt **de grafiekwaarden** (en de MKI-metric).
  De **kaart-styling** blijft in v1 ongeschaald (bruggen zijn even zichtbaar,
  ongeacht de schuif) — dat houdt v1 simpel. Kaart-kleur-op-MKI (en dus schuif ×
  kaart) staat op de Deferred-lijst voor v2.
- Bron blijft altijd ongemoeid; de schuif is puur cosmetisch (decisions.md).

---

## 8. Edge cases

| Geval | Gedrag |
|---|---|
| Gemeente zonder bruggen | Lege subset → kaart toont alleen de extent/gemeentegrens, grafiek toont een nette "geen bruggen" melding (geen crash). |
| Gemeente zonder geldige MKI | Na `mki_ontbreekt`-filter leeg → zelfde nette melding. |
| Schuif op 0% | Alle getoonde MKI = 0 (bewezen in het skelet); grafieken tonen nulwaarden, geen fout. |
| Ontbrekende kolom / laag | `data.py` faalt met een duidelijke melding; `app.py` vangt het en toont een waarschuwing i.p.v. te crashen (al ingebouwd). |
| Ontbrekende stap 06-output | Waarschuwing "draai eerst de pipeline" (al ingebouwd). |
| Grote laag (4.746 objecten) | `@st.cache_data` op de GeoPackage-read; per gemeente alleen de subset tekenen/aggregeren. |
| Reprojectiefouten (ongeldige geometrie) | `common.read_layer` filtert al lege/ongeldige geometrieën; kaartlaag reprojecteert alleen de subset. |

---

## 9. Taakverdeling & volgorde

| # | Wie | Taak | Hangt af van |
|---|---|---|---|
| 1 | **Ripley** | App-schil: layout afmaken, zijbalk/menu, schuif-bedrading & selectie-state, secties voor kaart/grafiek. Skelet is er al — Ripley maakt het productieklaar. | skelet (klaar) |
| 2 | **Lambert** | `viewer/geo.py` (reproject 28992→4326, bounds) + `viewer/map.py` (folium, bruggen tekenen, `fit_bounds`, filter op gemeente). | 1 |
| 3 | **Parker** | `viewer/charts.py`: stap 07-figuren per gemeente + schaling toepassen; `PROFIEL_KLEUREN` hergebruiken. | 1 |
| 4 | **Brett** | `tests/`: schaling (0/50/100/afkap), filteren op gemeente, edge cases (lege gemeente, 0%). | 2, 3 |

Volgorde: **1 → (2 ‖ 3) → 4.** Lambert en Parker kunnen **parallel** nadat Ripley
de schil en de gedeelde selectie-/schuif-state heeft vastgezet. Brett sluit af zodra
kaart en grafieken staan. Dallas doet de eindreview + integratie.

**Setup-stap voor de owner (vóór de bouw):** `pip install -r requirements.txt` in de
omgeving die de app draait. De pipeline-omgeving (anaconda base) heeft alles **behalve
`streamlit-folium` en `folium`** — die zijn nodig voor Lambert's kaart.

---

## 10. Open vragen voor de owner

1. **Kaartweergave van bruggen:** representatiepunten (licht, aanbevolen voor de
   simpele v1) of de echte polygonen? Voorstel: **punten** in v1, polygonen in v2.
2. **Basiskaart:** OpenStreetMap-tegels als achtergrond akkoord? (Standaard folium,
   gratis, geen sleutel nodig.)
3. **Welke MKI-maat leidt de grafieken:** `mki_per_jaar` (voorstel) of
   `mki_totaal_100jaar`? De schuif werkt op beide identiek.
4. **Buurtlaag (stap 08):** in v1 buiten scope laten (aanbevolen) of toch een simpele
   MKI-per-buurt-weergave meenemen?
5. **Profielkleuren (`PROFIEL_KLEUREN`):** kopie in `viewer/` houden (simpel) of naar
   `config.yaml` verplaatsen zodat viewer én stap 07 dezelfde bron delen (netter, maar
   raakt de pipeline)? Voorstel: **kopie in v1**, config in v2.

_Geen antwoord nodig om te starten met taak 1; deze vragen sturen taak 2–3._
