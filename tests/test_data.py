"""Tests voor ``viewer.data`` — gemeentelijst, exclusie, filteren en kaartlaag.

Het filter is de spil van de viewer: één keuze in de zijbalk stuurt zowel de
kaart als de grafieken (VIEWER_PLAN.md §4). Deze tests pinnen vast dat de
viewer-gemeentelijst de uitgesloten gemeenten (Amsterdam) weglaat, dat het filter
exact de rijen van de gekozen gemeente teruggeeft, dat een onbekende gemeente een
lege laag oplevert (geen crash — §8) en dat de gecachte bronlaag ongemoeid blijft.
Daarnaast dekken ze de config-helpers (``get_excluded_municipalities``,
``get_map_simplify_tolerance``) en de gecachte, tekenklare kaartlaag
``get_map_geometry`` (EPSG:4326, alleen ``[profiel, geometry]``, optioneel
vereenvoudigd).
"""

import geopandas as gpd
import pytest

import common
from viewer import data


# --- Gemeentelijst en exclusie (config-gedreven) --------------------------

def test_get_municipalities_sluit_uitgesloten_gemeenten_uit():
    # De viewer-lijst is config.yaml (via common) MINUS viewer.uitgesloten_gemeenten;
    # hoofdletter- en spatie-ongevoelig, niet hardgecodeerd.
    alle = common.get_gemeenten()
    uitgesloten = {g.strip().lower() for g in data.get_excluded_municipalities()}
    verwacht = [g for g in alle if g.strip().lower() not in uitgesloten]

    assert data.get_municipalities() == verwacht
    # Amsterdam staat in viewer.uitgesloten_gemeenten en mag niet in het menu.
    assert "Amsterdam" not in data.get_municipalities()


def test_get_excluded_municipalities_bevat_amsterdam():
    uitgesloten = data.get_excluded_municipalities()
    assert isinstance(uitgesloten, list)
    # Amsterdam is uitgesloten vanwege de kaartprestaties (~71% van de bruggen).
    assert any(naam.strip().lower() == "amsterdam" for naam in uitgesloten)


def test_get_excluded_municipalities_zonder_viewer_sectie_is_leeg(monkeypatch):
    # Zonder viewer-sectie sluit de viewer niets uit (veilige standaard). We
    # monkeypatchen common.load_config; config.yaml zelf blijft ongemoeid.
    monkeypatch.setattr(common, "load_config", lambda *a, **k: {"gemeenten": ["Diemen"]})
    assert data.get_excluded_municipalities() == []


# --- Vereenvoudigingstolerantie (config-gedreven) -------------------------

def test_get_map_simplify_tolerance_uit_config():
    # config.yaml → viewer.kaart_simplify_tolerantie_m == 2.0
    assert data.get_map_simplify_tolerance() == 2.0


@pytest.mark.parametrize("nep_config", [
    {"gemeenten": ["Diemen"]},                          # viewer-sectie ontbreekt
    {"viewer": {}},                                     # sleutel ontbreekt in viewer
    {"viewer": {"kaart_simplify_tolerantie_m": 0}},     # 0 => geen vereenvoudiging
    {"viewer": {"kaart_simplify_tolerantie_m": -5}},    # negatief => veilige 0.0
    {"viewer": {"kaart_simplify_tolerantie_m": "x"}},   # ongeldig => 0.0
])
def test_get_map_simplify_tolerance_afwezig_of_ongeldig_is_nul(monkeypatch, nep_config):
    # Ontbrekend/ongeldig/≤0 => 0.0 (niets vervormen). Monkeypatch i.p.v.
    # config.yaml aanraken, zodat de echte config ongemoeid blijft.
    monkeypatch.setattr(common, "load_config", lambda *a, **k: nep_config)
    assert data.get_map_simplify_tolerance() == 0.0


# --- Filteren per gemeente (spil van de viewer) ---------------------------

def test_filter_amsterdam_geeft_alleen_amsterdam(bridges):
    # Amsterdam zit nog in de GeoPackage — alleen uit het viewer-menu geweerd,
    # dus filteren levert nog steeds data (Dallas §6).
    subset = data.filter_by_municipality(bridges, "Amsterdam")
    assert not subset.empty
    assert (subset[data.GEMEENTE_COLUMN] == "Amsterdam").all()


def test_filter_diemen_geeft_alleen_diemen(bridges):
    subset = data.filter_by_municipality(bridges, "Diemen")
    assert not subset.empty
    assert (subset[data.GEMEENTE_COLUMN] == "Diemen").all()


def test_filter_onbekende_gemeente_is_leeg(bridges):
    subset = data.filter_by_municipality(bridges, "Onbekende Gemeente")
    assert isinstance(subset, gpd.GeoDataFrame)
    assert subset.empty


def test_filter_geeft_kopie_bron_blijft_ongemoeid(bridges):
    aantal_voor = len(bridges)
    subset = data.filter_by_municipality(bridges, "Diemen")

    # Muteren van de subset mag de gecachte bronlaag niet raken.
    subset.loc[subset.index[0], data.GEMEENTE_COLUMN] = "GEWIJZIGD"

    assert len(bridges) == aantal_voor
    assert "GEWIJZIGD" not in bridges[data.GEMEENTE_COLUMN].values


# --- Tekenklare, gecachte kaartlaag (get_map_geometry) --------------------
#
# get_map_geometry is @st.cache_data-gedecoreerd; buiten een Streamlit-runtime
# draait hij in "bare mode" (alleen waarschuwingen, geen fouten) en levert de
# reeds tekenklare kaartlaag die de kaart (Lambert) rechtstreeks consumeert.

def test_get_map_geometry_is_wgs84_met_alleen_teken_kolommen():
    laag = data.get_map_geometry("Amstelveen", 2.0)
    assert isinstance(laag, gpd.GeoDataFrame)
    # Webkaart-CRS en alleen de kolommen die getekend worden: [profiel, geometry].
    assert laag.crs.to_epsg() == 4326
    assert set(laag.columns) == {data.PROFIEL_COLUMN, laag.geometry.name}


def test_get_map_geometry_simplify_verkleint_payload():
    licht = data.get_map_geometry("Amstelveen", 2.0)
    zwaar = data.get_map_geometry("Amstelveen", 0.0)
    # Vereenvoudigen (tol=2.0) levert een lichtere GeoJSON-payload dan tol=0.0 —
    # precies de winst die de kaart snel houdt (Dallas §2, Lambert §3).
    assert len(licht.to_json()) < len(zwaar.to_json())


def test_get_map_geometry_lege_gemeente_geen_crash():
    # Onbekende gemeente => lege maar geldige laag (4326, juiste kolommen), geen
    # crash: de kaart kan dan een nette NL-weergave tonen (VIEWER_PLAN.md §8).
    leeg = data.get_map_geometry("Onbekende Gemeente", 2.0)
    assert isinstance(leeg, gpd.GeoDataFrame)
    assert leeg.empty
    assert leeg.crs.to_epsg() == 4326
    assert set(leeg.columns) == {data.PROFIEL_COLUMN, leeg.geometry.name}
