"""Tests voor ``viewer.geo`` en ``viewer.map`` — reprojectie, bounds en kaart.

De pipeline levert RD New (EPSG:28992); de webkaart heeft WGS84 (EPSG:4326)
nodig. ``viewer.geo`` doet die omzetting en leidt de bounds af; ``build_map``
bouwt de folium-kaart uit een reeds tekenklare 4326-laag (de uitvoer van
``data.get_map_geometry``) — het reprojecteert of vereenvoudigt zelf niet meer en
kent geen ``simplify_tolerance``-parameter (Lambert v1.1, Dallas §4a/§6). Hier
pinnen we vast dat reprojecteren de bron ongemoeid laat, dat een lege laag geen
bounds oplevert (``None``) en dat de kaart voor zowel een gevulde als een lege
laag een geldig ``folium.Map`` teruggeeft dat rendert — geen crash bij een
gemeente zonder bruggen (VIEWER_PLAN.md §8).
"""

import folium

from viewer import data
from viewer import geo
from viewer import map as map_view


def test_to_wgs84_reprojecteert_en_laat_bron_ongemoeid(amsterdam):
    herprojected = geo.to_wgs84(amsterdam)
    assert herprojected.crs.to_epsg() == 4326
    # De bron blijft in RD New (28992): reprojectie geeft een kopie terug.
    assert amsterdam.crs.to_epsg() == 28992


def test_bounds_wgs84_leeg_is_none(empty):
    assert geo.bounds_wgs84(empty) is None


def test_bounds_wgs84_gevuld_is_zuidwest_dan_noordoost(amsterdam):
    bounds = geo.bounds_wgs84(amsterdam)
    assert bounds is not None

    # Folium verwacht [[zuid, west], [noord, oost]]: zuid < noord en west < oost.
    (zuid, west), (noord, oost) = bounds
    assert zuid < noord
    assert west < oost


def test_build_map_tekenklare_laag_geeft_folium_map():
    # Nieuwe signature: build_map krijgt de reeds-4326 laag uit get_map_geometry
    # (geen simplify_tolerance-param meer). Amsterdam zit nog in de GeoPackage,
    # dus dit levert echte data om te tekenen.
    kaartlaag = data.get_map_geometry("Amsterdam", 2.0)
    kaart = map_view.build_map(kaartlaag)
    assert isinstance(kaart, folium.Map)

    # Niet-lege, échte kaart-HTML: de bruggenlaag met tooltip is toegevoegd
    # (groter dan een lege basiskaart), niet "toevallig groen" op ruwe invoer.
    html = kaart.get_root().render()
    leeg_html = map_view.build_map(kaartlaag.iloc[0:0]).get_root().render()
    assert "Profiel:" in html
    assert len(html) > len(leeg_html)


def test_build_map_lege_laag_geeft_folium_map():
    # Lege (maar tekenklare) laag mag niet crashen: een geldige, NL-gecentreerde
    # kaart die rendert (get_map_geometry(...).iloc[0:0], Dallas §6).
    leeg = data.get_map_geometry("Amsterdam", 2.0).iloc[0:0]
    kaart = map_view.build_map(leeg)
    assert isinstance(kaart, folium.Map)
    assert kaart.get_root().render()  # rendert zonder exception
