"""Tests voor ``viewer.scaling`` — de weergaveschaling (value * factor).

De schaling is bewust simpele rekenkunst; precies daar verstopt zich een
off-by-een-procent. Daarom hier de randen: 0/50/100%, afkappen buiten bereik en
het ongemoeid laten van ``None``/``NaN`` (zie VIEWER_PLAN.md §7, §8).

v1.2 voegt de per-profiel-schaling toe: ``combineer_factoren`` bouwt de
effectieve factor per profiel (de owner-bevestigde **multiplicatieve master**
``effectief = globaal * profiel``) en ``schaal_per_rij`` past die per rij toe
vóór elke aggregatie. Die twee zijn de kern van deze ronde; de master wordt
zowel op hand-gebouwde frames als op een echte gemeente (Amstelveen) bewezen.
"""

import math

import pandas as pd
import pytest

from viewer import scaling
from viewer.schema import (
    MKI_JAAR_COLUMN,
    MKI_ONTBREEKT_COLUMN,
    PROFIEL_COLUMN,
)
from viewer.style import PROFIEL_KLEUREN

# Canonieke profielvolgorde uit de gedeelde stijl (niet hardgecodeerd): het
# eerste profiel (``brug_1x2``) wordt in de master-bewijzen fijngeregeld, een
# ander profiel (``viaduct_1x2``) blijft dan op globaal x 1.0 als tegenvoorbeeld.
CANONIEKE_PROFIELEN = list(PROFIEL_KLEUREN)
DOEL_PROFIEL = CANONIEKE_PROFIELEN[0]
ANDER_PROFIEL = CANONIEKE_PROFIELEN[3]


# --- percentage_to_factor -------------------------------------------------

@pytest.mark.parametrize("percentage, verwacht", [
    (0, 0.0),
    (50, 0.5),
    (100, 1.0),
])
def test_percentage_to_factor_binnen_bereik(percentage, verwacht):
    assert scaling.percentage_to_factor(percentage) == verwacht


@pytest.mark.parametrize("percentage, verwacht", [
    (-10, 0.0),   # onder 0 wordt afgekapt naar 0.0
    (150, 1.0),   # boven 100 wordt afgekapt naar 1.0
])
def test_percentage_to_factor_kapt_af(percentage, verwacht):
    assert scaling.percentage_to_factor(percentage) == verwacht


# --- apply_factor ---------------------------------------------------------

def test_apply_factor_vermenigvuldigt():
    assert scaling.apply_factor(200.0, 0.5) == 100.0
    assert scaling.apply_factor(42.0, 0.0) == 0.0
    assert scaling.apply_factor(42.0, 1.0) == 42.0


def test_apply_factor_none_blijft_none():
    assert scaling.apply_factor(None, 0.5) is None


def test_apply_factor_nan_blijft_nan():
    resultaat = scaling.apply_factor(float("nan"), 0.5)
    assert math.isnan(resultaat)


# --- scale_series ---------------------------------------------------------

def test_scale_series_vermenigvuldigt_elementsgewijs():
    reeks = pd.Series([10.0, 20.0, 30.0])
    geschaald = scaling.scale_series(reeks, 0.5)
    pd.testing.assert_series_equal(geschaald, pd.Series([5.0, 10.0, 15.0]))


def test_scale_series_factor_nul_geeft_nullen():
    reeks = pd.Series([10.0, 20.0, 30.0])
    geschaald = scaling.scale_series(reeks, 0.0)
    assert (geschaald == 0.0).all()


# --- v1.2: combineer_factoren (multiplicatieve master) --------------------
#
# combineer_factoren bouwt de effectieve factor per profiel:
#     effectief(profiel) = globaal * profiel_factor(profiel)
# voor elk canoniek profiel (geef PROFIEL_KLEUREN.keys() mee). Een profiel zonder
# eigen schuif krijgt globaal x 1.0; alle invoer wordt begrensd tot [0.0, 1.0].

def test_combineer_factoren_dekt_alle_canonieke_profielen():
    # De map dekt exact de acht canonieke profielen, ook zonder eigen schuiven.
    effectieve = scaling.combineer_factoren(1.0, {}, PROFIEL_KLEUREN.keys())
    assert set(effectieve) == set(PROFIEL_KLEUREN)
    # Alles op 100% (globaal 1.0, geen profiel-schuiven) => overal factor 1.0.
    assert all(factor == 1.0 for factor in effectieve.values())


def test_combineer_factoren_ontbrekend_profiel_krijgt_globaal_maal_een():
    # Alleen DOEL_PROFIEL heeft een eigen schuif; de rest valt terug op globaal x 1.0.
    effectieve = scaling.combineer_factoren(
        0.8, {DOEL_PROFIEL: 0.5}, PROFIEL_KLEUREN.keys()
    )
    assert effectieve[DOEL_PROFIEL] == pytest.approx(0.8 * 0.5)
    for profiel in PROFIEL_KLEUREN:
        if profiel != DOEL_PROFIEL:
            assert effectieve[profiel] == pytest.approx(0.8)  # globaal x 1.0


def test_combineer_factoren_begrenst_globale_factor_boven_een():
    # Globaal boven 1.0 wordt afgekapt naar 1.0 (geen versterking > 100%).
    effectieve = scaling.combineer_factoren(5.0, {}, PROFIEL_KLEUREN.keys())
    assert all(factor == 1.0 for factor in effectieve.values())


def test_combineer_factoren_begrenst_negatieve_profielfactor_naar_nul():
    # Een negatieve profiel-factor is zinloos en wordt naar 0.0 afgekapt.
    effectieve = scaling.combineer_factoren(
        1.0, {DOEL_PROFIEL: -3.0}, PROFIEL_KLEUREN.keys()
    )
    assert effectieve[DOEL_PROFIEL] == 0.0


def test_combineer_factoren_ongeldige_profielfactor_valt_terug_op_een():
    # None/NaN => 1.0 (geen aanpassing): een kapotte schuif verstoort de weergave niet.
    effectieve = scaling.combineer_factoren(
        1.0, {DOEL_PROFIEL: None, ANDER_PROFIEL: float("nan")}, PROFIEL_KLEUREN.keys()
    )
    assert effectieve[DOEL_PROFIEL] == 1.0
    assert effectieve[ANDER_PROFIEL] == 1.0


def test_combineer_factoren_master_globaal_halveert_alles():
    # global=0.5 & alle profiel=1.0 => elke effectieve factor 0.5.
    effectieve = scaling.combineer_factoren(0.5, {}, PROFIEL_KLEUREN.keys())
    assert all(factor == pytest.approx(0.5) for factor in effectieve.values())


def test_combineer_factoren_master_alleen_een_profiel():
    # global=1.0 & brug_1x2=0.5 => alleen brug_1x2 = 0.5, de rest 1.0.
    effectieve = scaling.combineer_factoren(
        1.0, {DOEL_PROFIEL: 0.5}, PROFIEL_KLEUREN.keys()
    )
    assert effectieve[DOEL_PROFIEL] == pytest.approx(0.5)
    for profiel in PROFIEL_KLEUREN:
        if profiel != DOEL_PROFIEL:
            assert effectieve[profiel] == pytest.approx(1.0)


def test_combineer_factoren_master_globaal_en_profiel_vermenigvuldigen():
    # both => brug_1x2 = 0.5*0.5 = 0.25, viaduct_1x2 = 0.5*1.0 = 0.5.
    effectieve = scaling.combineer_factoren(
        0.5, {DOEL_PROFIEL: 0.5}, PROFIEL_KLEUREN.keys()
    )
    assert effectieve[DOEL_PROFIEL] == pytest.approx(0.25)
    assert effectieve[ANDER_PROFIEL] == pytest.approx(0.5)


# --- v1.2: schaal_per_rij -------------------------------------------------
#
# schaal_per_rij vermenigvuldigt elke waarde met de effectieve factor van HAAR
# profiel (per rij), muteert de invoer nooit en vult een profiel dat niet in de
# map staat met `standaard` (1.0).

def _canoniek_frame():
    """Klein frame met alleen canonieke profielen: DOEL, ANDER, DOEL."""
    waarden = pd.Series([100.0, 200.0, 300.0])
    profielen = pd.Series([DOEL_PROFIEL, ANDER_PROFIEL, DOEL_PROFIEL])
    return waarden, profielen


def test_schaal_per_rij_mapt_per_profiel():
    # Gemengde index om uitlijning te bewijzen; onbekend profiel => standaard 1.0.
    waarden = pd.Series([100.0, 200.0, 300.0, 400.0], index=[10, 11, 12, 13])
    profielen = pd.Series(
        [DOEL_PROFIEL, ANDER_PROFIEL, DOEL_PROFIEL, "onbekend_profiel"],
        index=[10, 11, 12, 13],
    )
    resultaat = scaling.schaal_per_rij(
        waarden, profielen, {DOEL_PROFIEL: 0.5, ANDER_PROFIEL: 0.25}
    )
    verwacht = pd.Series([50.0, 50.0, 150.0, 400.0], index=[10, 11, 12, 13])
    pd.testing.assert_series_equal(resultaat, verwacht)


def test_schaal_per_rij_muteert_de_invoer_niet():
    waarden, profielen = _canoniek_frame()
    waarden_kopie = waarden.copy()
    profielen_kopie = profielen.copy()

    resultaat = scaling.schaal_per_rij(waarden, profielen, {DOEL_PROFIEL: 0.5})

    # De invoer-Series blijven ongemoeid en het resultaat is een nieuw object.
    pd.testing.assert_series_equal(waarden, waarden_kopie)
    pd.testing.assert_series_equal(profielen, profielen_kopie)
    assert resultaat is not waarden


def test_schaal_per_rij_ontbrekend_profiel_krijgt_standaard():
    waarden = pd.Series([100.0, 200.0])
    profielen = pd.Series([DOEL_PROFIEL, "komt_niet_voor"])

    # Standaard 1.0: het onbekende profiel blijft ongemoeid.
    standaard_een = scaling.schaal_per_rij(waarden, profielen, {DOEL_PROFIEL: 0.5})
    assert standaard_een.iloc[0] == pytest.approx(50.0)
    assert standaard_een.iloc[1] == pytest.approx(200.0)

    # Een andere standaard wordt gerespecteerd (0.0 => nul).
    standaard_nul = scaling.schaal_per_rij(
        waarden, profielen, {DOEL_PROFIEL: 0.5}, standaard=0.0
    )
    assert standaard_nul.iloc[1] == 0.0


def test_schaal_per_rij_master_globaal_halveert_elke_rij():
    # global=0.5 & alle profiel=1.0 => elke rij x0.5.
    waarden, profielen = _canoniek_frame()
    effectieve = scaling.combineer_factoren(0.5, {}, PROFIEL_KLEUREN.keys())
    resultaat = scaling.schaal_per_rij(waarden, profielen, effectieve)
    pd.testing.assert_series_equal(resultaat, waarden * 0.5)


def test_schaal_per_rij_master_alleen_doelprofiel():
    # global=1.0 & brug_1x2=0.5 => alleen de DOEL-rijen halveren, ANDER ongemoeid.
    waarden, profielen = _canoniek_frame()
    effectieve = scaling.combineer_factoren(
        1.0, {DOEL_PROFIEL: 0.5}, PROFIEL_KLEUREN.keys()
    )
    resultaat = scaling.schaal_per_rij(waarden, profielen, effectieve)
    assert resultaat.iloc[0] == pytest.approx(50.0)   # DOEL 100*0.5
    assert resultaat.iloc[1] == pytest.approx(200.0)  # ANDER ongemoeid
    assert resultaat.iloc[2] == pytest.approx(150.0)  # DOEL 300*0.5


def test_schaal_per_rij_master_globaal_en_profiel():
    # both => DOEL-rijen x0.25 (0.5*0.5), ANDER-rij x0.5 (0.5*1.0).
    waarden, profielen = _canoniek_frame()
    effectieve = scaling.combineer_factoren(
        0.5, {DOEL_PROFIEL: 0.5}, PROFIEL_KLEUREN.keys()
    )
    resultaat = scaling.schaal_per_rij(waarden, profielen, effectieve)
    assert resultaat.iloc[0] == pytest.approx(25.0)   # 100*0.25
    assert resultaat.iloc[1] == pytest.approx(100.0)  # 200*0.5
    assert resultaat.iloc[2] == pytest.approx(75.0)   # 300*0.25


# --- v1.2: multiplicatieve master op echte data (Amstelveen) --------------
#
# Sanity-check op een echte gemeente: bewijst dat de master op de volledige
# subset klopt, niet alleen op speelgoedframes (Dallas §1: rauwe som 136.144,24).

def _rauwe_mki_som(subset):
    """Rauwe som van mki_per_jaar over de rijen met MKI (mki_ontbreekt weg)."""
    geldig = subset[~subset[MKI_ONTBREEKT_COLUMN]]
    return geldig[MKI_JAAR_COLUMN].sum()


def _geschaalde_totaal(subset, effectieve):
    """Geschaald totaal per jaar met exact de regel van charts.py en app.py."""
    geldig = subset[~subset[MKI_ONTBREEKT_COLUMN]]
    return scaling.schaal_per_rij(
        geldig[MKI_JAAR_COLUMN], geldig[PROFIEL_COLUMN], effectieve
    ).sum()


def test_master_amstelveen_alles_100_gelijk_aan_rauw(amstelveen):
    # Alles op 100% (factor 1.0) => geen verandering: exact de rauwe MKI-som.
    rauw = _rauwe_mki_som(amstelveen)
    assert rauw > 0  # zinnige testdata
    effectieve = scaling.combineer_factoren(1.0, {}, PROFIEL_KLEUREN.keys())
    assert _geschaalde_totaal(amstelveen, effectieve) == pytest.approx(rauw)


def test_master_amstelveen_globaal_50_halveert(amstelveen):
    # De globale schuif alleen op 50% halveert het totaal exact.
    rauw = _rauwe_mki_som(amstelveen)
    effectieve = scaling.combineer_factoren(0.5, {}, PROFIEL_KLEUREN.keys())
    assert _geschaalde_totaal(amstelveen, effectieve) == pytest.approx(rauw / 2)


def test_master_amstelveen_profiel_schuif_alleen_eigen_type(amstelveen):
    # brug_1x2=0.5 (globaal 100%): het totaal daalt met precies 0,5 x de rauwe
    # brug_1x2-som; de andere profielen blijven ongemoeid (multiplicatieve master).
    geldig = amstelveen[~amstelveen[MKI_ONTBREEKT_COLUMN]]
    rauw = geldig[MKI_JAAR_COLUMN].sum()
    rauw_doel = geldig[geldig[PROFIEL_COLUMN] == DOEL_PROFIEL][MKI_JAAR_COLUMN].sum()
    assert rauw_doel > 0  # DOEL_PROFIEL komt in Amstelveen voor

    effectieve = scaling.combineer_factoren(
        1.0, {DOEL_PROFIEL: 0.5}, PROFIEL_KLEUREN.keys()
    )
    assert _geschaalde_totaal(amstelveen, effectieve) == pytest.approx(
        rauw - 0.5 * rauw_doel
    )
