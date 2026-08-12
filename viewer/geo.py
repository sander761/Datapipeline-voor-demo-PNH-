"""Reprojectie en bounds voor de Brug-MKI-viewer.

De pipeline levert geometrie in EPSG:28992 (RD New); een webkaart heeft
EPSG:4326 (WGS84) nodig. Deze module doet dat ene: 28992 -> 4326 omzetten en
daaruit de folium-bounds afleiden om op de gekozen gemeente in te zoomen.

Zuivere module: geen streamlit-import. De Streamlit-weergave zit in app.py.
"""

import common


def to_wgs84(gdf):
    """Geef een kopie van gdf, gereprojecteerd van EPSG:28992 naar EPSG:4326.

    Ontbreekt het CRS op de invoer, dan nemen we aan dat het RD New is (28992),
    zoals de rest van de pipeline (zie common.TARGET_CRS). Zo blijft de bron
    ongemoeid en krijgt de kaartlaag altijd WGS84 terug.
    """
    if gdf.crs is None:
        gdf = gdf.set_crs(common.TARGET_CRS)
    return gdf.to_crs(4326)


def bounds_wgs84(gdf):
    """Geef de folium-bounds [[zuid, west], [noord, oost]] in WGS84.

    Berekend op de gereprojecteerde geometrie, want folium wil lat/lon. De
    volgorde is [[miny, minx], [maxy, maxx]] — dat is wat fit_bounds verwacht.
    Bij een lege laag is er niets om op in te zoomen; dan is de uitkomst None.
    """
    if gdf.empty:
        return None

    minx, miny, maxx, maxy = to_wgs84(gdf).total_bounds
    return [[miny, minx], [maxy, maxx]]
