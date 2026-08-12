"""Gecachte dataladers voor de Brug-MKI-viewer.

Een dunne laag boven de pipeline: leest de GeoPackage-output van stap 06 en
levert de gemeentelijst uit config.yaml. Er wordt niets herberekend — de viewer
leest alleen (zie decisions.md, 2026-08-10). De MKI-schaal van de schuif wordt
pas bij het tonen toegepast, niet hier.

Deze module her-exporteert daarnaast de pipeline-kolomnamen uit de streamlit-
vrije module `viewer.schema` (zodat `data.MKI_JAAR_COLUMN` blijft werken) en
leest de optionele `viewer`-sectie uit config.yaml: welke gemeenten de viewer
overslaat (`get_excluded_municipalities`) en de kaart-vereenvoudigingstolerantie
(`get_map_simplify_tolerance`). Zo lezen de kaart- en app-code die instellingen
uit config in plaats van ze hard te coderen. Voor de kaart levert
`get_map_geometry` een gecachte, vereenvoudigde en naar EPSG:4326 gereprojecteerde
kaartlaag per gemeente, zodat de kaart bij een rerun niet steeds opnieuw hoeft te
worden opgebouwd.
"""

import streamlit as st

import common
from viewer import geo

# Pipeline-schema (laag- en kolomnamen uit stap 06) komt uit de streamlit-vrije
# module viewer.schema en wordt hier her-geëxporteerd, zodat bestaande code en
# tests `data.MKI_JAAR_COLUMN` e.d. kunnen blijven gebruiken, terwijl zuivere
# modules (kaart, grafieken) dezelfde namen zonder streamlit kunnen importeren.
from viewer.schema import (
    BRIDGE_LAYER,
    BRONHOUDER_VALUES_COLUMN,
    GEMEENTE_COLUMN,
    MKI_JAAR_COLUMN,
    MKI_ONTBREEKT_COLUMN,
    MKI_SCRIPT,
    MKI_TOTAAL_COLUMN,
    PROFIEL_COLUMN,
)


# --- Optionele viewer-instellingen uit config.yaml ------------------------
#
# De viewer-sectie stuurt alleen de viewer; de pipeline gebruikt hem niet.
# Ontbreekt de sectie of een sleutel, dan gelden veilige standaarden: niets
# uitsluiten en niet vereenvoudigen.

VIEWER_SECTION = "viewer"
UITGESLOTEN_GEMEENTEN_KEY = "uitgesloten_gemeenten"
SIMPLIFY_TOLERANTIE_KEY = "kaart_simplify_tolerantie_m"

# Publieke namen van deze module: de her-geëxporteerde schema-constanten plus de
# eigen helpers. Zo blijft `from viewer.data import MKI_JAAR_COLUMN` werken en
# weten linters dat de imports hierboven bewust worden doorgegeven.
__all__ = [
    "BRIDGE_LAYER",
    "BRONHOUDER_VALUES_COLUMN",
    "GEMEENTE_COLUMN",
    "MKI_JAAR_COLUMN",
    "MKI_ONTBREEKT_COLUMN",
    "MKI_SCRIPT",
    "MKI_TOTAAL_COLUMN",
    "PROFIEL_COLUMN",
    "get_municipalities",
    "get_excluded_municipalities",
    "get_map_simplify_tolerance",
    "load_bridges",
    "filter_by_municipality",
    "get_map_geometry",
]


def _viewer_config():
    """Geef de optionele viewer-sectie uit config.yaml, of een lege dict.

    Ontbreekt de sectie (of is hij geen mapping), dan geldt de veilige
    standaard: een lege dict, zodat de helpers hieronder niets uitsluiten en
    niet vereenvoudigen.
    """
    sectie = common.load_config().get(VIEWER_SECTION)
    return sectie if isinstance(sectie, dict) else {}


def get_excluded_municipalities():
    """Geef de gemeenten die de viewer NIET toont (uit config.yaml).

    Leest `viewer.uitgesloten_gemeenten`. De pipeline gebruikt deze lijst niet;
    hij is puur voor de viewer (bijvoorbeeld Amsterdam weglaten vanwege de
    kaartprestaties). Ontbreekt de sleutel, dan is de lijst leeg (niets
    uitsluiten). Namen worden getrimd, net als common.get_gemeenten().
    """
    namen = _viewer_config().get(UITGESLOTEN_GEMEENTEN_KEY) or []
    return [str(naam).strip() for naam in namen if str(naam).strip()]


def get_municipalities():
    """Geef de gemeentenamen voor de viewer: config.yaml minus de uitgesloten.

    De basislijst komt uit config.yaml via common.get_gemeenten() (niet
    hardgecodeerd). Gemeenten uit `viewer.uitgesloten_gemeenten` vallen weg; de
    vergelijking is hoofdletter- en spatie-ongevoelig, in dezelfde stijl als de
    gemeentenamen elders. Zonder viewer-sectie wordt er niets uitgesloten.
    """
    uitgesloten = {naam.strip().lower() for naam in get_excluded_municipalities()}
    return [
        naam for naam in common.get_gemeenten()
        if naam.strip().lower() not in uitgesloten
    ]


def get_map_simplify_tolerance():
    """Geef de vereenvoudigingstolerantie (meters, RD New) voor de kaart.

    Leest `viewer.kaart_simplify_tolerantie_m`. Groter = minder detail, lichtere
    kaart. Ontbreekt de sleutel of is de waarde 0/ongeldig/negatief, dan is de
    uitkomst 0.0 (geen vereenvoudiging) — de veilige standaard die niets
    vervormt.
    """
    waarde = _viewer_config().get(SIMPLIFY_TOLERANTIE_KEY, 0.0)
    try:
        tolerantie = float(waarde)
    except (TypeError, ValueError):
        return 0.0
    return tolerantie if tolerantie > 0 else 0.0


@st.cache_data(show_spinner="Bruggen laden...")
def load_bridges():
    """Lees de bruggen-MKI-laag uit stap 06 (gecachet).

    De geometrie blijft in EPSG:28992 (RD New); reprojectie naar 4326 gebeurt
    pas in de kaartlaag. Door te cachen wordt de GeoPackage maar één keer per
    sessie van schijf gelezen.
    """
    gpkg_path = common.get_gpkg_path(MKI_SCRIPT)
    return common.read_layer(gpkg_path, BRIDGE_LAYER)


def filter_by_municipality(bridges, municipality):
    """Filter de bruggen op de gekozen gemeente.

    Geeft een kopie terug, zodat de gecachte laag zelf ongemoeid blijft.
    """
    return bridges[bridges[GEMEENTE_COLUMN] == municipality].copy()


@st.cache_data(show_spinner="Kaart voorbereiden...")
def get_map_geometry(municipality, tolerance):
    """Gecachte, tekenklare kaartlaag voor één gemeente (EPSG:4326, licht).

    Gekeyed op (municipality, tolerance): laadt de gecachte bruggen, filtert op
    de gemeente, vereenvoudigt optioneel de polygonen in EPSG:28992 (meters, RD
    New) en reprojecteert daarna naar EPSG:4326. Alleen de kolommen die de kaart
    tekent blijven over: [PROFIEL_COLUMN, geometry]. Zo gebeurt simplify +
    reproject per (gemeente, tolerantie) maar één keer; bij een rerun komt de
    kaartlaag uit de cache in plaats van opnieuw te worden opgebouwd.

    Vereenvoudigen gebeurt VÓÓR reprojecteren, zodat de tolerantie in meters
    klopt, en behoudt de topologie (geopandas-standaard) zodat de bruggen echte
    polygonen blijven. tolerance <= 0 => niet vereenvoudigen (niets vervormen).
    Een lege subset => lege (maar geldige) laag, zodat de kaart een nette
    NL-weergave kan tonen zonder te crashen.
    """
    subset = filter_by_municipality(load_bridges(), municipality)

    tekenbaar = subset
    if tolerance and tolerance > 0 and not subset.empty:
        tekenbaar = subset.copy()
        tekenbaar["geometry"] = tekenbaar.geometry.simplify(tolerance)

    wgs84 = geo.to_wgs84(tekenbaar)
    return wgs84[[PROFIEL_COLUMN, wgs84.geometry.name]]
