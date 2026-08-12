"""Smoke-tests voor ``app.py`` via ``streamlit.testing``.

Bewijst de bedrading end-to-end zonder browser: de app draait zonder exception,
een tweede gemeentekeuze rerun't zonder fout (kaart én grafieken volgen de keuze
— VIEWER_PLAN.md §4) en de globale schuif op 0% rerun't zonder fout (alle
getoonde MKI wordt 0 — §8). Daarnaast pinnen we de v1.2-UI vast: de keuzelijst
sluit Amsterdam uit (viewer.uitgesloten_gemeenten) maar houdt Amstelveen; er is
een globale MKI-schuif **plus** per-profiel-schuiven (>1 schuif totaal); naast
"Aantal bruggen" staat de live metric "Totale MKI per jaar (geschaald)" die
daalt (≈ halveert) als de globale schuif naar 50% gaat; en er renderen minstens
drie vol-breed gestapelde plotly-grafieken (bronhouder, profiel, samenstelling).
Alle echte viewer-modules bestaan; er wordt niets gestubd.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

# app.py staat in de projectroot, één niveau boven tests/.
APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")

# Ruime timeout: de eerste run leest de GeoPackage (±5,5 MB) van schijf.
TIMEOUT_S = 60

# Vaste labels uit app.py (v1.2): de globale schuif en de live totaal-metric.
GLOBALE_SCHUIF_LABEL = "MKI-schaal (%)"
TOTAAL_METRIC_LABEL = "Totale MKI per jaar (geschaald)"
BRUGGEN_METRIC_LABEL = "Aantal bruggen"


def _verse_app():
    """Start een verse AppTest voor app.py met een ruime timeout."""
    return AppTest.from_file(APP_PATH, default_timeout=TIMEOUT_S)


def _schuif(at, label):
    """Geef de schuif met dit label (pin op label, niet op index)."""
    for schuif in at.slider:
        if schuif.label == label:
            return schuif
    raise AssertionError(f"Geen schuif met label '{label}'")


def _metric_waarde(at, label):
    """Geef de tekstwaarde van de metric met dit label, of None."""
    for metric in at.metric:
        if metric.label == label:
            return metric.value
    return None


def _parse_nl_getal(tekst):
    """Parse een NL-genoteerde metric-waarde ('138.119') naar een int."""
    return int(tekst.replace(".", ""))


def test_app_draait_zonder_exception():
    at = _verse_app()
    at.run()
    assert not at.exception


def test_gemeentewissel_rerun_zonder_exception():
    at = _verse_app()
    at.run()
    assert not at.exception

    # Wissel naar de tweede gemeente in de keuzelijst en rerun.
    tweede_gemeente = at.selectbox[0].options[1]
    at.selectbox[0].set_value(tweede_gemeente).run()

    assert not at.exception
    assert at.selectbox[0].value == tweede_gemeente


def test_schuif_op_nul_rerun_zonder_exception():
    at = _verse_app()
    at.run()
    assert not at.exception

    # Globale schuif naar 0%: alle getoonde MKI wordt 0, zonder fout.
    globale = _schuif(at, GLOBALE_SCHUIF_LABEL)
    globale.set_value(0).run()

    assert not at.exception
    assert _schuif(at, GLOBALE_SCHUIF_LABEL).value == 0


def test_selector_sluit_amsterdam_uit_en_bevat_amstelveen():
    at = _verse_app()
    at.run()
    assert not at.exception

    # De gemeentekeuze komt uit data.get_municipalities(): Amsterdam is geweerd
    # (viewer.uitgesloten_gemeenten), een gewone gemeente als Amstelveen blijft.
    opties = at.selectbox[0].options
    assert "Amsterdam" not in opties
    assert "Amstelveen" in opties


def test_globale_en_per_profiel_schuiven_aanwezig():
    at = _verse_app()
    at.run()
    assert not at.exception

    # De globale schuif MOET er zijn; daarnaast staan er per-profiel-schuiven in
    # de expander (de default-gemeente heeft bruggen in meerdere profielen), dus
    # meer dan één schuif in totaal. AppTest surfacet ook de expander-schuiven.
    labels = [schuif.label for schuif in at.slider]
    assert GLOBALE_SCHUIF_LABEL in labels
    assert len(at.slider) > 1


def test_totaal_mki_metric_staat_naast_aantal_bruggen():
    at = _verse_app()
    at.run()
    assert not at.exception

    # De live totaal-metric hoort naast de brugtelling (owner-verzoek 1, v1.2).
    labels = [metric.label for metric in at.metric]
    assert TOTAAL_METRIC_LABEL in labels
    assert BRUGGEN_METRIC_LABEL in labels


def test_totaal_mki_metric_daalt_bij_globaal_50():
    at = _verse_app()
    at.run()
    assert not at.exception

    # De metric is leesbaar (NL-notatie); noteer de waarde bij 100%.
    voor = _metric_waarde(at, TOTAAL_METRIC_LABEL)
    assert voor is not None

    # Globale schuif naar 50% en opnieuw draaien: het geschaalde totaal daalt en
    # halveert ongeveer (multiplicatieve master, alle per-profiel-schuiven op 100%).
    _schuif(at, GLOBALE_SCHUIF_LABEL).set_value(50).run()
    assert not at.exception
    na = _metric_waarde(at, TOTAAL_METRIC_LABEL)
    assert na is not None

    assert _parse_nl_getal(na) < _parse_nl_getal(voor)
    assert _parse_nl_getal(na) == pytest.approx(_parse_nl_getal(voor) / 2, rel=0.01)


def test_minstens_drie_gestapelde_grafieken_aanwezig():
    at = _verse_app()
    at.run()
    assert not at.exception

    # Parkers drie figuren (bronhouder, profiel, samenstelling) staan vol-breed
    # gestapeld; AppTest exposeert plotly-grafieken via get("plotly_chart").
    assert len(at.get("plotly_chart")) >= 3
