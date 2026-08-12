"""Tests voor ``viewer.charts`` — de MKI-figuren per gemeente en de schaling.

v1.2 wijzigt ``build_charts``:

* de signatuur is nu ``build_charts(subset_gdf, effectieve_factoren)`` — een
  **dict** ``profiel -> effectieve factor`` (uitkomst van
  ``scaling.combineer_factoren``), niet meer een scalar;
* de MKI wordt éérst **per rij** geschaald (via ``scaling.schaal_per_rij``) en
  pas daarna geaggregeerd, zodat globaal én per-profiel doorwerken;
* de retour**volgorde** is ``[bronhouder, profiel, samenstelling]`` — daarom
  pinnen we figuren op hun **TITEL**, niet op index.

Kern van de dekking: de twee per-jaar-figuren (bronhouder, profiel) bewegen met
de globale schuif mee (halveren bij 0.5, nul bij 0.0); een per-profiel-schuif
raakt alléén het eigen profiel (en de bronhouders die dat profiel bezitten); de
samenstelling is invariant voor de globale schuif maar reageert wél op een
per-profiel-verschil, met een 0-guard tegen delen door nul. Een gemeente zonder
bruggen levert een lege lijst (VIEWER_PLAN.md §8). De aggregatie-helpers pinnen
we vast tegen de logica van stap 07 (eerste token van ``bronhouder_values``;
``mki_ontbreekt`` valt weg vóór de helper).
"""

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from viewer import charts, scaling
from viewer.schema import (
    BRONHOUDER_VALUES_COLUMN,
    MKI_JAAR_COLUMN,
    MKI_ONTBREEKT_COLUMN,
    PROFIEL_COLUMN,
)
from viewer.style import PROFIEL_KLEUREN

# Titels waarop we pinnen (de volgorde wijzigde in v1.2 → niet op index pinnen).
TITEL_BRONHOUDER = "MKI per jaar per bronhouder"
TITEL_PROFIEL = "MKI per jaar per profiel"
TITEL_SAMENSTELLING = "Profielsamenstelling (%)"

# Canonieke profielvolgorde (niet hardgecodeerd): het eerste en een ander
# profiel dienen als DOEL/tegenvoorbeeld in de hand-gebouwde aggregatie-tests.
CANONIEKE_PROFIELEN = list(PROFIEL_KLEUREN)
DOEL_PROFIEL = CANONIEKE_PROFIELEN[0]
ANDER_PROFIEL = CANONIEKE_PROFIELEN[3]


# --- Hulpjes --------------------------------------------------------------

def _effectief(globaal=1.0, profiel_factoren=None):
    """Bouw de effectieve-factoren-map zoals app.py dat doet (gedeelde regel)."""
    return scaling.combineer_factoren(
        globaal, profiel_factoren or {}, PROFIEL_KLEUREN.keys()
    )


def _figuur(figuren, titel_fragment):
    """Vind de figuur waarvan de titel het fragment bevat (pin op TITEL)."""
    for figuur in figuren:
        if titel_fragment in figuur.layout.title.text:
            return figuur
    raise AssertionError(f"Geen figuur met titel die '{titel_fragment}' bevat")


def _som_y(figuur):
    """Som alle y-waarden over alle traces: de totale (geschaalde) waarde."""
    return sum(
        float(np.nansum([y for y in spoor.y if y is not None]))
        for spoor in figuur.data
    )


def _bars(figuur):
    """Map van x-categorie -> som van y (voor de bronhouder- en profielstaven)."""
    totalen = {}
    for spoor in figuur.data:
        for x, y in zip(spoor.x, spoor.y):
            if y is None:
                continue
            totalen[x] = totalen.get(x, 0.0) + float(y)
    return totalen


def _trace_map(figuur):
    """Map van trace-naam (profiel) -> som van y (profiel- en samenstellingsfiguur)."""
    return {
        spoor.name: float(np.nansum([y for y in spoor.y if y is not None]))
        for spoor in figuur.data
    }


def _kies_doelprofiel(subset):
    """Eerste canonieke profiel dat in de subset voorkomt (fijn te regelen)."""
    aanwezig = set(subset[~subset[MKI_ONTBREEKT_COLUMN]][PROFIEL_COLUMN])
    for profiel in PROFIEL_KLEUREN:
        if profiel in aanwezig:
            return profiel
    return None


# --- Vorm: drie figuren, owner-volgorde op TITEL --------------------------

def test_build_charts_geeft_drie_figuren_in_owner_volgorde(amstelveen):
    figuren = charts.build_charts(amstelveen, _effectief())
    assert isinstance(figuren, list)
    assert len(figuren) == 3
    assert all(isinstance(figuur, go.Figure) for figuur in figuren)

    # Owner-tekenvolgorde: bronhouder -> profiel -> samenstelling.
    titels = [figuur.layout.title.text for figuur in figuren]
    assert TITEL_BRONHOUDER in titels[0]
    assert TITEL_PROFIEL in titels[1]
    assert TITEL_SAMENSTELLING in titels[2]


def test_build_charts_lege_gemeente_geeft_lege_lijst(empty):
    assert charts.build_charts(empty, _effectief()) == []


# --- Globale schuif: de twee per-jaar-figuren schalen lineair -------------

@pytest.mark.parametrize("titel", [TITEL_BRONHOUDER, TITEL_PROFIEL])
def test_perjaar_figuur_schaalt_lineair_met_globale_schuif(amstelveen, titel):
    vol = _som_y(_figuur(charts.build_charts(amstelveen, _effectief(1.0)), titel))
    assert vol > 0  # zinnige testdata: Amstelveen heeft MKI

    half = _som_y(_figuur(charts.build_charts(amstelveen, _effectief(0.5)), titel))
    nul = _som_y(_figuur(charts.build_charts(amstelveen, _effectief(0.0)), titel))
    assert half == pytest.approx(vol / 2, abs=1e-6)  # globaal 0.5 halveert
    assert nul == 0.0                                # globaal 0.0 => alles nul


# --- Per-profiel-onafhankelijkheid ----------------------------------------

def test_per_profiel_schuif_verlaagt_alleen_eigen_profielbalk(amstelveen):
    doel = _kies_doelprofiel(amstelveen)
    assert doel is not None

    vol = _trace_map(_figuur(charts.build_charts(amstelveen, _effectief(1.0)), TITEL_PROFIEL))
    half = _trace_map(
        _figuur(charts.build_charts(amstelveen, _effectief(1.0, {doel: 0.5})), TITEL_PROFIEL)
    )

    # Alleen de DOEL-balk halveert; alle andere profielbalken zijn ongemoeid.
    assert half[doel] == pytest.approx(vol[doel] / 2, abs=1e-6)
    for profiel, waarde in vol.items():
        if profiel != doel:
            assert half[profiel] == pytest.approx(waarde, abs=1e-6)


def test_per_profiel_schuif_verlaagt_profieltotaal_met_halve_doelsom(amstelveen):
    doel = _kies_doelprofiel(amstelveen)
    geldig = amstelveen[~amstelveen[MKI_ONTBREEKT_COLUMN]]
    rauw = geldig[MKI_JAAR_COLUMN].sum()
    rauw_doel = geldig[geldig[PROFIEL_COLUMN] == doel][MKI_JAAR_COLUMN].sum()
    assert rauw_doel > 0

    profiel_fig = _figuur(
        charts.build_charts(amstelveen, _effectief(1.0, {doel: 0.5})), TITEL_PROFIEL
    )
    # Het profieltotaal daalt met precies 0,5 x de rauwe DOEL-som.
    assert _som_y(profiel_fig) == pytest.approx(rauw - 0.5 * rauw_doel, abs=1e-6)


def test_per_profiel_schuif_verlaagt_alleen_bronhouders_met_doelprofiel(amstelveen):
    doel = _kies_doelprofiel(amstelveen)
    geldig = amstelveen[~amstelveen[MKI_ONTBREEKT_COLUMN]]
    bron = geldig[BRONHOUDER_VALUES_COLUMN].map(charts._eerste_bronhouder)
    met_doel = set(bron[geldig[PROFIEL_COLUMN] == doel])
    zonder_doel = set(bron) - met_doel
    assert met_doel  # er is minstens één bronhouder met het DOEL-profiel

    vol = _bars(_figuur(charts.build_charts(amstelveen, _effectief(1.0)), TITEL_BRONHOUDER))
    half = _bars(
        _figuur(charts.build_charts(amstelveen, _effectief(1.0, {doel: 0.5})), TITEL_BRONHOUDER)
    )

    # Bronhouders die het DOEL-profiel bezitten dalen; de overige blijven gelijk.
    for bronhouder in met_doel:
        assert half[bronhouder] < vol[bronhouder]
    for bronhouder in zonder_doel:
        assert half[bronhouder] == pytest.approx(vol[bronhouder], abs=1e-6)


# --- Samenstelling: globaal-invariant, per-profiel-gevoelig, 0-guard ------

def test_samenstelling_is_invariant_voor_globale_schuif(amstelveen):
    vol = _figuur(charts.build_charts(amstelveen, _effectief(1.0)), TITEL_SAMENSTELLING)
    half = _figuur(charts.build_charts(amstelveen, _effectief(0.5)), TITEL_SAMENSTELLING)

    # De som van de aandelen blijft 100 bij 1.0 én 0.5 (globaal valt weg in de ratio).
    assert _som_y(vol) == pytest.approx(100.0, abs=1e-6)
    assert _som_y(half) == pytest.approx(100.0, abs=1e-6)

    # Elk profiel-aandeel is identiek tussen globaal 1.0 en 0.5.
    vol_map, half_map = _trace_map(vol), _trace_map(half)
    for profiel, aandeel in vol_map.items():
        assert half_map[profiel] == pytest.approx(aandeel, abs=1e-6)


def test_samenstelling_reageert_op_per_profiel_schuif(amstelveen):
    doel = _kies_doelprofiel(amstelveen)
    vol = _trace_map(
        _figuur(charts.build_charts(amstelveen, _effectief(1.0)), TITEL_SAMENSTELLING)
    )
    verschoven = _trace_map(
        _figuur(charts.build_charts(amstelveen, _effectief(1.0, {doel: 0.5})), TITEL_SAMENSTELLING)
    )

    # Het DOEL-aandeel daalt (relatief kleiner), maar de som blijft 100%.
    assert verschoven[doel] < vol[doel]
    assert sum(verschoven.values()) == pytest.approx(100.0, abs=1e-6)


def test_samenstelling_0_guard_bij_globaal_0(amstelveen):
    samenstelling = _figuur(
        charts.build_charts(amstelveen, _effectief(0.0)), TITEL_SAMENSTELLING
    )
    # Geen deling door nul: alle aandelen 0, geen NaN-balken.
    aandelen = [y for spoor in samenstelling.data for y in spoor.y if y is not None]
    assert all(not math.isnan(y) for y in aandelen)
    assert _som_y(samenstelling) == 0.0


# --- Aggregatie-helpers: parity met stap 07 (nieuwe 2-arg-signatuur) ------
#
# build_charts filtert mki_ontbreekt en geeft de al per rij geschaalde MKI plus
# de groepeersleutel-Series door aan de helpers (hier factor 1.0 => geschaald ==
# rauw), zodat we de stap-07-logica los kunnen pinnen.

@pytest.mark.parametrize("waarde, verwacht", [
    ("G0362", "G0362"),
    ("G0362; G0363", "G0362"),          # eerste (dominante) token
    ("  G0362 ; G0363 ", "G0362"),      # getrimd
    ("", "onbekend"),
    ("   ", "onbekend"),
    (None, "onbekend"),
    (float("nan"), "onbekend"),
])
def test_eerste_bronhouder(waarde, verwacht):
    # Spiegelt eerste_bronhouder in 07_overzichten.py.
    assert charts._eerste_bronhouder(waarde) == verwacht


def test_mki_per_profiel_sorteert_in_canonieke_volgorde():
    # Geschaalde MKI per rij + het profiel per rij; de helper somt per profiel in
    # de canonieke PROFIEL_KLEUREN-volgorde (DOEL vóór ANDER).
    geschaald = pd.Series([10.0, 5.0, 20.0])
    profielen = pd.Series([ANDER_PROFIEL, DOEL_PROFIEL, DOEL_PROFIEL])

    reeks = charts._mki_per_profiel(geschaald, profielen)
    assert list(reeks.index) == [DOEL_PROFIEL, ANDER_PROFIEL]  # canonieke volgorde
    assert reeks[DOEL_PROFIEL] == pytest.approx(25.0)          # 5 + 20
    assert reeks[ANDER_PROFIEL] == pytest.approx(10.0)


def test_mki_per_bronhouder_spiegelt_stap07():
    # Kleine hand-gebouwde tabel: groep op de dominante bronhouder, aflopend
    # gesorteerd — exact de logica van stap 07. mki_ontbreekt is al weggefilterd
    # (zoals build_charts doet) voordat de helper de twee kolommen krijgt.
    df = pd.DataFrame({
        BRONHOUDER_VALUES_COLUMN: ["A; B", "A", "B; C", "X; Y", None],
        MKI_JAAR_COLUMN: [10.0, 5.0, 20.0, 999.0, 1.0],
        MKI_ONTBREEKT_COLUMN: [False, False, False, True, False],
    })
    geldig = df[~df[MKI_ONTBREEKT_COLUMN]]
    reeks = charts._mki_per_bronhouder(
        geldig[MKI_JAAR_COLUMN], geldig[BRONHOUDER_VALUES_COLUMN]
    )

    # De mki_ontbreekt-rij (X;Y, 999) is al weg; groepen op eerste token.
    assert list(reeks.index) == ["B", "A", "onbekend"]  # aflopend op som
    assert reeks["B"] == pytest.approx(20.0)
    assert reeks["A"] == pytest.approx(15.0)            # 10 + 5
    assert reeks["onbekend"] == pytest.approx(1.0)      # lege bronhouder


def test_mki_per_bronhouder_zonder_geldige_rijen_is_leeg():
    # Alleen mki_ontbreekt-rijen => na filteren lege invoer => lege Series.
    df = pd.DataFrame({
        BRONHOUDER_VALUES_COLUMN: ["A", "B"],
        MKI_JAAR_COLUMN: [10.0, 20.0],
        MKI_ONTBREEKT_COLUMN: [True, True],
    })
    geldig = df[~df[MKI_ONTBREEKT_COLUMN]]
    reeks = charts._mki_per_bronhouder(
        geldig[MKI_JAAR_COLUMN], geldig[BRONHOUDER_VALUES_COLUMN]
    )
    assert reeks.empty
