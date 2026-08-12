"""Plotly-grafieken voor de Brug-MKI-viewer.

Bouwt de MKI-figuren per gemeente in de stijl van `07_overzichten.py`, maar
gefilterd op de gekozen gemeente en met de schuiffactoren (globaal én per
profiel) toegepast op het moment van tonen. Deze module is zuiver: hij rekent
en tekent figuren, maar rendert niets in Streamlit — `app.py` doet het tonen
(st.plotly_chart).

De schaling raakt alleen de weergave: elke MKI-waarde wordt eerst per rij met
de effectieve factor van haar profiel vermenigvuldigd via
`scaling.schaal_per_rij` en pas daarna geaggregeerd (per profiel, per
bronhouder). Zo krijgt een bronhouder met bruggen van meerdere profielen het
juiste totaal. De bron (de subset-GeoDataFrame) blijft ongemoeid (zie
decisions.md, 2026-08-10).
"""

import pandas as pd
import plotly.express as px

from viewer import scaling
from viewer.schema import (
    GEMEENTE_COLUMN, PROFIEL_COLUMN, MKI_JAAR_COLUMN,
    MKI_ONTBREEKT_COLUMN, BRONHOUDER_VALUES_COLUMN,
)
from viewer.style import PROFIEL_KLEUREN


# --- Weergave -------------------------------------------------------------
#
# De drie figuren staan nu vol-breed onder elkaar (niet meer naast elkaar in
# smalle kolommen), dus er is ruim horizontaal plek. De ondermarge mag daarom
# kleiner dan voorheen; `automargin` (op de x-as) rekt hem vanzelf weer op als
# lange bronhouder- of profielnamen toch meer ruimte vragen, zodat elk label
# volledig zichtbaar blijft (owner-eis). De tick-labels blijven onder een hoek
# staan omdat een gemeente veel — en soms lange — bronhouders kan hebben. De
# marges staan t.o.v. v1.2 iets ruimer, omdat de v1.3-fonts groter zijn: zo
# blijven de (grotere) titel, astitels en tick-labels volledig zichtbaar.
FIGUUR_HOOGTE = 500
FIGUUR_MARGE = dict(t=90, b=100, l=70, r=20)
TICK_HOEK = -45

# Lettergroottes voor de figuren (owner-eis v1.3: fonts groter en beter
# leesbaar). Op één plek geparametriseerd zodat alle drie de figuren via
# `_pas_lettertype_toe` dezelfde, consistente maten krijgen — geen losse
# magische getallen verspreid door de figuurbouwers.
TITEL_FONT = 22        # grafiektitel
AS_TITEL_FONT = 17     # astitels ("MKI per jaar", "aandeel (%)")
TICK_FONT = 14         # tick-labels op de assen (getallen/categorieën)
LEGENDA_FONT = 14      # legenda-items + legendatitel
BASIS_FONT = 15        # algemene figuurtekst

# Enkelvoudige kleur voor de bronhouder-staaf: een bronhouder heeft geen
# profielkleur, gelijk aan het standaardkleur van `bar_figuur` in stap 07.
BRONHOUDER_KLEUR = "#3b6ea5"

# Naam van de x-as-kolom in de bronhouder-figuur (net als de "bronhouder"-kolom
# in de aggregatie van stap 07).
BRONHOUDER_AS = "bronhouder"


# --- Aggregatie -----------------------------------------------------------

def _mki_per_profiel(geschaald, profielen):
    """Som de geschaalde MKI per jaar per profiel, in de vaste profielvolgorde.

    Werkt op de al per rij geschaalde MKI (`geschaald`, uit
    `scaling.schaal_per_rij`) en groepeert op het profiel per rij (`profielen`,
    zelfde index). De volgorde volgt de sleutels van `PROFIEL_KLEUREN`, zodat
    kleur en legenda tussen figuren consistent zijn; profielen die in deze
    gemeente niet voorkomen, blijven weg.
    """
    per_profiel = geschaald.groupby(profielen).sum()
    volgorde = [profiel for profiel in PROFIEL_KLEUREN if profiel in per_profiel.index]
    return per_profiel.reindex(volgorde)


def _eerste_bronhouder(waarde):
    """Eerste (dominante) bronhouder uit de puntkomma-lijst. Spiegelt
    eerste_bronhouder in 07_overzichten.py."""
    if pd.isna(waarde) or not str(waarde).strip():
        return "onbekend"
    return str(waarde).split(";")[0].strip()


def _mki_per_bronhouder(geschaald, bronhouder_waarden):
    """Som de geschaalde MKI/jaar per dominante bronhouder, aflopend gesorteerd.

    Werkt op de al per rij geschaalde MKI (`geschaald`) en groepeert op de
    dominante bronhouder per rij (`_eerste_bronhouder` op `bronhouder_waarden`,
    zelfde index) — precies als stap 07. Omdat er al per rij (op profiel) is
    geschaald, klopt het bronhouder-totaal ook wanneer een bronhouder bruggen
    van meerdere profielen bezit en de profiel-schuiven verschillen.
    """
    bronhouder = bronhouder_waarden.map(_eerste_bronhouder)
    return geschaald.groupby(bronhouder).sum().sort_values(ascending=False)


def _gemeente_naam(subset_gdf):
    """Geef de gemeentenaam van de subset voor in de titels (of None)."""
    if subset_gdf.empty or GEMEENTE_COLUMN not in subset_gdf.columns:
        return None
    namen = subset_gdf[GEMEENTE_COLUMN].dropna().unique()
    return namen[0] if len(namen) else None


# --- Figuren --------------------------------------------------------------

def _pas_lettertype_toe(fig):
    """Vergroot de fonts (titel, astitels, ticks, legenda) voor leesbaarheid.

    Zet uitsluitend lettergroottes en raakt bewust niets anders aan: de
    bestaande opmaak (`title_x=0.5`, template, kleuren en categorievolgorde)
    blijft ongemoeid omdat `update_layout`/`update_xaxes`/`update_yaxes`
    recursief samenvoegen. Zo krijgen alle drie de figuren dezelfde, goed
    leesbare maten (owner-eis v1.3), gestuurd door de font-constanten hierboven.
    """
    fig.update_layout(
        font=dict(size=BASIS_FONT),
        title_font_size=TITEL_FONT,
        legend=dict(font=dict(size=LEGENDA_FONT), title_font=dict(size=LEGENDA_FONT)),
    )
    fig.update_xaxes(tickfont=dict(size=TICK_FONT), title_font=dict(size=AS_TITEL_FONT))
    fig.update_yaxes(tickfont=dict(size=TICK_FONT), title_font=dict(size=AS_TITEL_FONT))
    return fig


def _figuur_mki_per_profiel(per_profiel, gemeente):
    """Staafdiagram: geschaalde MKI per jaar per profiel.

    Krijgt de al geschaalde per-profiel-aggregatie binnen (de schaling gebeurt
    één keer per rij in `build_charts`, niet meer hier), zodat de staafhoogtes
    meebewegen met de globale én de per-profiel-schuiven. Elk profiel houdt zijn
    vaste kleur uit `PROFIEL_KLEUREN` en de vaste volgorde.
    """
    df = per_profiel.reset_index()
    df.columns = [PROFIEL_COLUMN, MKI_JAAR_COLUMN]

    fig = px.bar(
        df, x=PROFIEL_COLUMN, y=MKI_JAAR_COLUMN,
        color=PROFIEL_COLUMN, title=_titel("MKI per jaar per profiel", gemeente),
        color_discrete_map=PROFIEL_KLEUREN,
        category_orders={PROFIEL_COLUMN: list(PROFIEL_KLEUREN)},
    )
    fig.update_layout(
        xaxis_title=None, yaxis_title="MKI per jaar",
        template="plotly_white", title_x=0.5, legend_title_text="Profiel",
        height=FIGUUR_HOOGTE, margin=FIGUUR_MARGE,
    )
    fig.update_xaxes(tickangle=TICK_HOEK, automargin=True)
    return _pas_lettertype_toe(fig)


def _figuur_mki_per_bronhouder(per_bronhouder, gemeente):
    """Staafdiagram: geschaalde MKI per jaar per dominante bronhouder.

    Enkelvoudige staaf in één kleur (`BRONHOUDER_KLEUR`) omdat een bronhouder —
    anders dan een profiel — geen vaste kleur heeft; dit spiegelt het
    enkelvoudige `bar_figuur` uit stap 07. Krijgt de al geschaalde
    bronhouder-aggregatie binnen (de schaling gebeurt één keer per rij in
    `build_charts`, niet meer hier). De x-labels staan gedraaid en `automargin`
    houdt ook lange bronhoudernamen vol-breed volledig zichtbaar.
    """
    df = per_bronhouder.reset_index()
    df.columns = [BRONHOUDER_AS, MKI_JAAR_COLUMN]

    fig = px.bar(
        df, x=BRONHOUDER_AS, y=MKI_JAAR_COLUMN,
        title=_titel("MKI per jaar per bronhouder", gemeente),
    )
    fig.update_traces(marker_color=BRONHOUDER_KLEUR)
    fig.update_layout(
        xaxis_title=None, yaxis_title="MKI per jaar",
        template="plotly_white", title_x=0.5,
        height=FIGUUR_HOOGTE, margin=FIGUUR_MARGE,
    )
    fig.update_xaxes(tickangle=TICK_HOEK, automargin=True)
    return _pas_lettertype_toe(fig)


def _figuur_samenstelling(per_profiel, gemeente):
    """Gestapelde 100%-staaf: de profielsamenstelling van deze gemeente.

    De enkelvoudige-gemeente-variant van `gestapelde_figuur` uit stap 07: één
    staaf, per profiel opgedeeld, genormaliseerd naar 100%. Het aandeel wordt
    berekend op de al geschaalde per-profiel-totalen: de globale factor valt in
    de verhouding weg (de samenstelling is dus invariant voor de globale schuif),
    maar per-profiel-schuiven veranderen de verhouding nu wél — een bewuste
    gedragswijziging t.o.v. v1.1. De 0-guard voorkomt delen door nul: is het
    totaal 0 (globaal 0% of alle schuiven 0), dan worden het nullen zodat de
    figuur leesbaar blijft.
    """
    totaal = per_profiel.sum()
    aandeel = (per_profiel / totaal * 100) if totaal else per_profiel * 0

    df = pd.DataFrame({
        "gemeente": gemeente or "gekozen gemeente",
        PROFIEL_COLUMN: per_profiel.index,
        "aandeel": aandeel.values,
    })

    fig = px.bar(
        df, x="gemeente", y="aandeel", color=PROFIEL_COLUMN,
        title=_titel("Profielsamenstelling (%)", gemeente),
        color_discrete_map=PROFIEL_KLEUREN,
        category_orders={PROFIEL_COLUMN: list(PROFIEL_KLEUREN)},
    )
    fig.update_layout(
        barmode="stack", xaxis_title=None, yaxis_title="aandeel (%)",
        template="plotly_white", title_x=0.5, legend_title_text="Profiel",
        height=FIGUUR_HOOGTE, margin=FIGUUR_MARGE,
    )
    fig.update_xaxes(tickangle=TICK_HOEK, automargin=True)
    # Smallere staaf (owner-eis v1.3): de x-as is één categorie, dus `width`
    # telt in categorie-eenheden (~0.8 ≈ de oude breedte). 0.2 maakt de staaf
    # ~4× smaller zonder de figuurgrootte (FIGUUR_HOOGTE) te veranderen.
    fig.update_traces(width=0.2)
    return _pas_lettertype_toe(fig)


def _titel(basis, gemeente):
    """Zet de gemeentenaam achter de titel, als die bekend is."""
    return f"{basis} \u2014 {gemeente}" if gemeente else basis


# --- Publieke bouwer ------------------------------------------------------

def build_charts(subset_gdf, effectieve_factoren):
    """Bouw de MKI-figuren voor de gekozen gemeente (v1.2: per-profiel schaling).

    De MKI wordt éérst per rij geschaald met de effectieve factor van haar
    profiel en pas daarna geaggregeerd. Zo krijgt een bronhouder die bruggen van
    meerdere profielen bezit het juiste totaal, ook wanneer de profiel-schuiven
    verschillen. De bron-GeoDataFrame blijft ongemoeid (`schaal_per_rij` geeft
    een nieuwe Series terug).

    Gedrag van de schuiven:

    * De **profiel-** en **bronhouder-**staven tonen de absolute geschaalde MKI
      en reageren dus op de globale schuif én op de per-profiel-schuiven.
    * De **samenstelling** is het aandeel van de geschaalde per-profiel-totalen.
      De globale factor valt in de verhouding weg, dus de samenstelling is
      invariant voor de globale schuif, maar reageert nu wél op de
      per-profiel-schuiven (bewuste gedragswijziging t.o.v. v1.1).

    Parameters
    ----------
    subset_gdf : geopandas.GeoDataFrame
        De op gemeente gefilterde bruggen-MKI-laag (EPSG:28992).
    effectieve_factoren : dict
        profiel -> effectieve factor (uitkomst van `scaling.combineer_factoren`,
        opgebouwd in `app.py`). De effectieve factor per brug is de
        multiplicatieve master `globale_factor * profiel_factor(profiel)`; hij
        wordt op het moment van tonen op de MKI toegepast (nooit op de bron).

    Returns
    -------
    list[plotly.graph_objects.Figure]
        De figuren in de owner-tekenvolgorde (vol-breed, onder elkaar):
          1. geschaalde MKI per jaar per (dominante) bronhouder (staaf);
          2. geschaalde MKI per jaar per profiel (staaf);
          3. profielsamenstelling van de gemeente (gestapelde 100%-staaf).
        Pin figuren op hun TITEL, niet op index — deze volgorde wijzigt t.o.v.
        v1.1. Leeg als er geen bruggen met MKI zijn (dan toont `app.py` een
        "geen bruggen"-melding).
    """
    geldig = subset_gdf[~subset_gdf[MKI_ONTBREEKT_COLUMN]]
    if geldig.empty:
        return []

    geschaald = scaling.schaal_per_rij(
        geldig[MKI_JAAR_COLUMN], geldig[PROFIEL_COLUMN], effectieve_factoren
    )

    per_profiel = _mki_per_profiel(geschaald, geldig[PROFIEL_COLUMN])
    per_bronhouder = _mki_per_bronhouder(geschaald, geldig[BRONHOUDER_VALUES_COLUMN])
    gemeente = _gemeente_naam(subset_gdf)
    return [
        _figuur_mki_per_bronhouder(per_bronhouder, gemeente),
        _figuur_mki_per_profiel(per_profiel, gemeente),
        _figuur_samenstelling(per_profiel, gemeente),
    ]
