"""Folium-kaart voor de Brug-MKI-viewer.

Bouwt de kaart voor één gemeente: de bruggen als vlakken (MultiPolygon),
gekleurd per profiel, met inzoomen op de gemeente-extent. De owner koos
bewust voor echte polygonen (geen punten) en een OpenStreetMap-achtergrond
(zie decisions.md, 2026-08-12).

De kaartlaag komt tekenklaar binnen uit data.get_map_geometry (EPSG:4326,
alleen [PROFIEL_COLUMN, geometry], eventueel al vereenvoudigd en gecachet).
Deze module reprojecteert of vereenvoudigt dus niet meer zelf; die logica zit
gecachet in data.get_map_geometry.

Zuivere module: geen streamlit-import. app.py rendert de kaart met st_folium;
deze module levert alleen het folium.Map-object. De schuif raakt de kaart in
v1 niet — de kaart is ongeschaald (VIEWER_PLAN.md §7).
"""

import folium

from viewer import geo

# Profielkolom uit stap 06 (de waarden zijn exact de sleutels van
# PROFIEL_KLEUREN). Uit de streamlit-vrije module viewer.schema, zodat deze
# module streamlit-vrij blijft — app.py doet de Streamlit-weergave.
from viewer.schema import PROFIEL_COLUMN
from viewer.style import PROFIEL_KLEUREN


# Terugval-kleur voor een profiel dat niet in PROFIEL_KLEUREN staat.
DEFAULT_KLEUR = "#999999"

# Achtergrondkaart: standaard folium-tegels zijn OpenStreetMap (geen sleutel).
OSM_TILES = "OpenStreetMap"

# Startpositie voor een lege kaart: ruwweg het midden van Nederland.
NEDERLAND_CENTRUM = [52.2, 5.3]
NEDERLAND_ZOOM = 8


def _style_function(feature):
    """Geef de folium-stijl voor één brug, gekleurd op zijn profiel.

    Leest het profiel uit de feature-properties en zoekt de bijbehorende kleur
    in PROFIEL_KLEUREN. Een onbekend of ontbrekend profiel krijgt de grijze
    terugval-kleur, zodat de brug altijd zichtbaar blijft.
    """
    profiel = feature["properties"].get(PROFIEL_COLUMN)
    kleur = PROFIEL_KLEUREN.get(profiel, DEFAULT_KLEUR)
    return {
        "fillColor": kleur,
        "color": kleur,
        "weight": 1,
        "fillOpacity": 0.7,
    }


def build_map(map_gdf):
    """Bouw de folium-kaart uit een reeds tekenklare kaartlaag.

    map_gdf is de uitvoer van data.get_map_geometry: al in EPSG:4326 (WGS84),
    alleen de kolommen [PROFIEL_COLUMN, geometry], en eventueel al vereenvoudigd
    en gecachet. Deze functie reprojecteert of vereenvoudigt dus niet meer zelf;
    ze tekent de bruggen als gekleurde polygonen en zoomt in op hun extent.

    Een lege laag levert een geldige, lege kaart op gecentreerd op Nederland,
    zodat de app altijd iets kan tonen (geen crash bij een gemeente zonder
    bruggen).
    """
    if map_gdf.empty:
        return folium.Map(
            location=NEDERLAND_CENTRUM, zoom_start=NEDERLAND_ZOOM, tiles=OSM_TILES
        )

    kaart = folium.Map(
        location=NEDERLAND_CENTRUM, zoom_start=NEDERLAND_ZOOM, tiles=OSM_TILES
    )

    folium.GeoJson(
        map_gdf,
        name="Bruggen",
        style_function=_style_function,
        tooltip=folium.GeoJsonTooltip(fields=[PROFIEL_COLUMN], aliases=["Profiel:"]),
    ).add_to(kaart)

    # Inzoomen op de extent van de laag. bounds_wgs84 verwerkt een reeds-4326
    # laag correct (to_crs 4326->4326 is een no-op); None => niets om op te zoomen.
    bounds = geo.bounds_wgs84(map_gdf)
    if bounds is not None:
        kaart.fit_bounds(bounds)

    return kaart
