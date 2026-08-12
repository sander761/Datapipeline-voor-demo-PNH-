"""Interactieve Brug-MKI-viewer — Streamlit-app.

Een dunne, alleen-lezen laag boven de bruggen-MKI-pipeline. De zijbalk biedt
alleen de gemeentekeuze: die keuze filtert de (gecachte) bruggen-laag en stuurt
bij een volledige rerun zowel de kaart (Lambert) als de grafieken (Parker). De
schuiven staan bij de grafieken in een fragment: een globale MKI-schuif plus een
schuif per profiel dat in de gemeente voorkomt. Een schuiftik schaalt de
getoonde MKI-waarden op het weergavemoment (multiplicatieve master: effectieve
factor = globaal x profiel) en rerunt alleen de grafieken en de totaal-metric —
de kaart eronder blijft ongemoeid en de brondata verandert nooit.

De grafieken staan vol-breed onder elkaar (bronhouder -> profiel ->
samenstelling), elk volledig zichtbaar, met de kaart als laatste vol-breed
daaronder.

Deze module is een dunne dirigent: laden/filteren zit in `viewer.data`, de
schaling in `viewer.scaling`, de kaart in `viewer.map` en de grafieken in
`viewer.charts`. Alle Streamlit-rendering gebeurt hier; de viewer-modules
leveren kale objecten (een folium-kaart, plotly-figuren).

Starten (vanuit de projectmap):

    streamlit run app.py
"""

import streamlit as st
from streamlit_folium import st_folium

from viewer import map as map_view, charts, data, scaling
from viewer.style import PROFIEL_KLEUREN


# --- Viewer-styling -------------------------------------------------------
#
# Eén puur cosmetische CSS-injectie (v1.3 UI-polish): de algemene viewer-tekst
# net iets groter (~+10-15% t.o.v. de Streamlit 1.51-standaard) — de
# metric-label en -waarde, de bijschriften, de schuif-/selectlabels, de
# expander-kop en de subkoppen. Alleen lettergroottes: geen layout, geen gedrag.
# Kaart-tooltips (in de folium-iframe) en de grafiek-teksten (charts.py) vallen
# hier bewust buiten. De standaardgroottes uit het thema staan ter referentie in
# commentaar; de selectors mikken op stabiele Streamlit 1.51-testid's.
VIEWER_CSS = """
<style>
[data-testid="stMetricValue"] { font-size: 2.5rem; }          /* was 2.25rem */
[data-testid="stMetricLabel"] { font-size: 1rem; }            /* label, was 0.875rem */
[data-testid="stMarkdownContainer"] p { font-size: 1.1rem; }  /* algemene tekst, was 1rem */
[data-testid="stCaptionContainer"] p { font-size: 1rem; }     /* bijschriften, was ~0.875rem */
[data-testid="stWidgetLabel"] { font-size: 1rem; }            /* schuif-/selectlabels, was 0.875rem */
[data-testid="stExpander"] summary { font-size: 1.1rem; }     /* expander-kop */
[data-testid="stHeading"] h3 { font-size: 1.9rem; }           /* subkoppen, was 1.75rem */
</style>
"""


# --- Paginaopzet ----------------------------------------------------------

st.set_page_config(page_title="Brug-MKI viewer", page_icon="🌉", layout="wide")

# Injecteer de viewer-styling direct na de paginaopzet, vóór de eerste render.
st.markdown(VIEWER_CSS, unsafe_allow_html=True)

st.title("Brug-MKI viewer")
st.caption(
    "Milieukostenindicator (MKI) van bruggen per gemeente. "
    "Alleen-lezen weergave van de pipeline-output (stap 06/07)."
)


# --- Grafiekenpaneel (fragment) -------------------------------------------
#
# Op module-niveau gedefinieerd voor een stabiele fragment-id. De schuiven
# zitten HIER, niet in de zijbalk: een schuiftik rerunt alleen dit fragment (de
# grafieken en de totaal-metric herrekenen), terwijl de kaart eronder — buiten
# het fragment — ongemoeid blijft en niet opnieuw wordt verstuurd. Bij een
# fragment-rerun geeft Streamlit dezelfde subset mee als bij de laatste
# volledige run.

@st.fragment
def grafieken_paneel(subset):
    """Toon de schuiven, de live totaal-metric en de grafieken; alleen dit
    fragment rerunt bij een schuiftik.

    De globale schuif werkt op alle profielen; daaronder staat (in een expander)
    een schuif per profiel dat in deze gemeente voorkomt. De effectieve factor
    per profiel = globaal x profiel (multiplicatieve master; de regel leeft in
    `scaling`). Die factoren schalen zowel de totaal-MKI-metric als de figuren,
    per rij en op het weergavemoment, zodat metric en grafieken exact dezelfde
    waarden tonen. De figuren staan vol-breed onder elkaar in de owner-volgorde
    die `build_charts` teruggeeft (bronhouder -> profiel -> samenstelling), elk
    volledig zichtbaar. Zonder bruggen (lege figurenlijst) verschijnt een nette
    melding.
    """
    # Globale schuif: werkt op elk profiel (gedraagt zich als de v1.1-scalar
    # wanneer alleen deze schuif beweegt).
    schaal_pct = st.slider("MKI-schaal (%)", 0, 100, 100, 1)
    globale_factor = scaling.percentage_to_factor(schaal_pct)
    st.caption(
        f"Globale weergavefactor: MKI \u00d7 {globale_factor:.2f} "
        "\u2014 plus per-profiel bijstellingen hieronder."
    )

    # Per-profiel-schuiven: alleen voor profielen die in deze gemeente voorkomen
    # (canonieke volgorde uit PROFIEL_KLEUREN, dus geen dode schuiven voor
    # afwezige profielen). Ze staan in een uitgeklapte expander, zodat het paneel
    # netjes maar zichtbaar blijft. Een stabiele key houdt de stand per profiel
    # vast tussen de rerruns.
    profielen_in_subset = set(subset[data.PROFIEL_COLUMN])
    aanwezige_profielen = [
        profiel for profiel in PROFIEL_KLEUREN if profiel in profielen_in_subset
    ]
    profiel_factoren = {}
    with st.expander("Schaal per profiel (%)", expanded=True):
        for profiel in aanwezige_profielen:
            profiel_pct = st.slider(profiel, 0, 100, 100, 1, key=f"schaal_{profiel}")
            profiel_factoren[profiel] = scaling.percentage_to_factor(profiel_pct)

    # Effectieve factor per profiel via de gedeelde scaling-regel (globaal x
    # profiel). combineer_factoren vult de niet-getoonde profielen met globaal x
    # 1.0, zodat de map gegarandeerd alle canonieke profielen dekt.
    effectieve = scaling.combineer_factoren(
        globale_factor, profiel_factoren, PROFIEL_KLEUREN.keys()
    )

    # Live metric-rij: aantal bruggen naast de geschaalde totale MKI per jaar.
    # Het totaal gebruikt exact dezelfde regel als de grafieken (schaal per rij,
    # rijen zonder MKI vallen weg via mki_ontbreekt), zodat metric en figuren
    # consistent blijven. Maat = mki_per_jaar (als de per-jaar-grafieken); wil de
    # owner later het 100-jaars-totaal, dan is dit de enige plek om te wisselen.
    geldig = subset[~subset[data.MKI_ONTBREEKT_COLUMN]]
    totaal = scaling.schaal_per_rij(
        geldig[data.MKI_JAAR_COLUMN], geldig[data.PROFIEL_COLUMN], effectieve
    ).sum()

    kol_bruggen, kol_mki = st.columns(2)
    kol_bruggen.metric("Aantal bruggen", f"{len(subset):,}".replace(",", "."))
    kol_mki.metric(
        "Totale MKI per jaar (geschaald)",
        f"{totaal:,.0f}".replace(",", "."),
    )

    # Grafieken vol-breed onder elkaar, in de owner-volgorde die build_charts al
    # teruggeeft (bronhouder -> profiel -> samenstelling), dus niet omsorteren.
    figuren = charts.build_charts(subset, effectieve)
    if figuren:
        for figuur in figuren:
            st.plotly_chart(figuur, width="stretch")
    else:
        st.info("Geen bruggen voor deze gemeente.")


# --- Zijbalk: alleen de gemeentekeuze (stuurt de volledige rerun) ---------

with st.sidebar:
    st.header("Instellingen")

    gemeenten = data.get_municipalities()
    gekozen_gemeente = st.selectbox("Gemeente", gemeenten, index=0)


# --- Data laden en filteren op de gekozen gemeente ------------------------
#
# Volledige-rerun scope: bij een gemeentewissel rerunt het hele script, zodat
# zowel de grafieken als de kaart meebewegen. Het laden en de kaartlaag zijn
# gecachet. Een fout (bijvoorbeeld ontbrekende stap 06-output) blokkeert de UI
# niet, maar wordt als waarschuwing getoond.

laadfout = None
gefilterd = None
kaartlaag = None
try:
    bruggen = data.load_bridges()
    gefilterd = data.filter_by_municipality(bruggen, gekozen_gemeente)
    tol = data.get_map_simplify_tolerance()
    kaartlaag = data.get_map_geometry(gekozen_gemeente, tol)
except Exception as exc:  # defensief: nette melding i.p.v. een crash
    laadfout = exc


# --- Samenvatting, grafieken en kaart -------------------------------------
#
# Bij een laadfout tonen we een nette waarschuwing i.p.v. te crashen. Anders:
# eerst het gemeente-label (factor-onafhankelijk), dan het grafiekenpaneel met
# de schuiven, de live totaal-metric en de gestapelde grafieken, en ten slotte
# de kaart vol-breed eronder.

if laadfout is not None:
    st.warning(
        "Kon de bruggen-MKI-output (stap 06) niet laden. Draai eerst de "
        f"pipeline. Details: {laadfout}"
    )
else:
    # Factor-onafhankelijk label: de gemeentenaam verandert alleen bij een
    # gemeentewissel, niet bij het schuiven, dus buiten het fragment.
    st.subheader(f"Gemeente: {gekozen_gemeente}")

    # Grafiekenpaneel: de schuiven, de live totaal-metric (naast Aantal bruggen)
    # en de gestapelde grafieken. Alleen dit paneel rerunt bij een schuiftik.
    grafieken_paneel(gefilterd)

    st.divider()

    # Kaart vol-breed onder de grafieken en BUITEN het fragment: een schuiftik
    # raakt deze st_folium-aanroep niet, dus de (gecachte, lichte) kaart-payload
    # wordt niet opnieuw verstuurd. De sleutel wisselt alleen bij een
    # gemeentewissel (stabiele identiteit); returned_objects=[] voorkomt een
    # rerun bij pan/zoom.
    st.subheader("Kaart")
    kaart = map_view.build_map(kaartlaag)
    st_folium(
        kaart,
        use_container_width=True,
        height=600,
        key=f"kaart_{gekozen_gemeente}",
        returned_objects=[],
    )
