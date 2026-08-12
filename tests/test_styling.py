"""Tests voor de v1.3 UI-polish (pure styling) — charts-fonts, staafbreedte, app-CSS.

v1.3 is puur cosmetisch: `viewer/charts.py` kreeg grotere, op één plek
geparametriseerde lettergroottes (via `_pas_lettertype_toe`) en een smallere
samenstellingsstaaf (`width=0.2`); `app.py` injecteert één `<style>`-blok
(`VIEWER_CSS`) direct na `st.set_page_config`. Deze lichte guards pinnen die
opmaak vast zonder de logica (signaturen, figuurvolgorde, kleuren, aggregatie)
te raken — die blijft door `test_charts.py` en `test_app_smoke.py` gedekt. De
verwachte maten spiegelen bewust de font-constanten uit `viewer/charts.py`.
"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from viewer import charts, scaling
from viewer.style import PROFIEL_KLEUREN

# Verwachte lettergroottes — moeten de constanten in viewer/charts.py spiegelen.
VERWACHT_TITEL_FONT = 22
VERWACHT_AS_TITEL_FONT = 17
VERWACHT_TICK_FONT = 14
VERWACHT_LEGENDA_FONT = 14
VERWACHT_BASIS_FONT = 15

# Titels (pin op TITEL, niet op index) en de smalle samenstellingsstaaf.
TITEL_BRONHOUDER = "MKI per jaar per bronhouder"
TITEL_PROFIEL = "MKI per jaar per profiel"
TITEL_SAMENSTELLING = "Profielsamenstelling (%)"
VERWACHT_STAAFBREEDTE = 0.2

# app.py staat in de projectroot, één niveau boven tests/.
APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")
TOTAAL_METRIC_LABEL = "Totale MKI per jaar (geschaald)"


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


# --- charts: grotere lettergroottes op alle drie de figuren ---------------

def test_alle_figuren_hebben_v13_lettergroottes(amstelveen):
    # Alle drie de figuren krijgen via _pas_lettertype_toe dezelfde maten.
    figuren = charts.build_charts(amstelveen, _effectief())
    assert len(figuren) == 3

    for figuur in figuren:
        opmaak = figuur.layout
        assert opmaak.title.font.size == VERWACHT_TITEL_FONT
        assert opmaak.font.size == VERWACHT_BASIS_FONT
        assert opmaak.legend.font.size == VERWACHT_LEGENDA_FONT
        assert opmaak.xaxis.tickfont.size == VERWACHT_TICK_FONT
        assert opmaak.yaxis.tickfont.size == VERWACHT_TICK_FONT
        assert opmaak.xaxis.title.font.size == VERWACHT_AS_TITEL_FONT
        assert opmaak.yaxis.title.font.size == VERWACHT_AS_TITEL_FONT


# --- charts: smalle samenstellingsstaaf, rest standaard -------------------

def test_samenstelling_staven_zijn_versmald(amstelveen):
    figuren = charts.build_charts(amstelveen, _effectief())
    samenstelling = _figuur(figuren, TITEL_SAMENSTELLING)
    # Elke (profiel-)staaf-trace is versmald naar 0.2 (owner-eis v1.3).
    assert samenstelling.data  # er zijn staven om te controleren
    assert all(spoor.width == VERWACHT_STAAFBREEDTE for spoor in samenstelling.data)


def test_bronhouder_en_profiel_staven_hebben_standaardbreedte(amstelveen):
    figuren = charts.build_charts(amstelveen, _effectief())
    # De per-jaar-figuren houden de standaard staafbreedte (width niet gezet).
    for titel in (TITEL_BRONHOUDER, TITEL_PROFIEL):
        figuur = _figuur(figuren, titel)
        assert all(spoor.width is None for spoor in figuur.data)


# --- app: boot met CSS-injectie (precies één <style>-blok) ----------------

def test_app_boot_met_styling_en_precies_een_style_blok():
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.run()

    # Boot ongewijzigd t.o.v. v1.2: geen exception, schuiven, de totaal-metric
    # en minstens drie gestapelde grafieken blijven aanwezig.
    assert not at.exception
    assert len(at.slider) >= 1
    assert TOTAAL_METRIC_LABEL in [metric.label for metric in at.metric]
    assert len(at.get("plotly_chart")) >= 3

    # Precies één <style>-blok surfacet (de enkele VIEWER_CSS-injectie), niet meer.
    aantal_style = sum(md.value.count("<style>") for md in at.markdown)
    assert aantal_style == 1
