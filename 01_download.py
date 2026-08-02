"""Stap 01: BGT-, TOP10NL- en gemeentedata downloaden van PDOK.

Dit eerste script haalt alle data op binnen een bounding box om de gemeenten.
Het aanpassen van rijen en kolommen gebeurt pas in latere stappen, zodat de
ruwe data bewaard blijft en je altijd terug kunt.

Drie bronnen:

    Gemeenten   uit de bestuurlijke-gebieden-API van het Kadaster; hieruit
                worden de gemeenten uit config.yaml geselecteerd, en die
                bepalen de bounding box.

    BGT         overbruggingsdeel, waterdeel en wegdeel. De overbruggingsdelen
                zijn de basis voor de MKI-berekeningen en de waterdelen zijn nodig
                om te bepalen of overbruggingsdelen waterdelen kruisen. De wegdelen
                waren initieel gebruikt om te bepalen of overbruggingsdelen wegen kruisen, 
                maar de TOP10NL dataset heeft hier een beter alternatief voor. Dus wegdelen 
                data uit de BGT worden nog steeds gedownload maar verder niet gebruikt. 

    TOP10NL     wegdeel (vlak, lijn, hartlijn), spoorbaandeel, gebouw en
                plaats worden gedownload vanuit TOP10NL. Deze data is minder gedetailleerd dan de BGT, 
                maar heeft zeer goed gevulde attribuutdata, iets wat de BGT data vaak mist. De attribuutdata
                worden gebruikt in volgende stappen om de overbruggingsdelen verder te classificeren zodat
                de MKI berekeningen beter kunnen worden uitgevoerd. 

Een belangrijke opmerking voor dit script is dat de BGT data worden opgehaald in een enkele bbox-request; 
de TOP10NL data worden opgehaald in meerdere tegels, omdat een bbox om zes gemeenten daar te groot voor is.

"""
# Hier importeren we alle libaries 
import math
import time
import geopandas as gpd
import pandas as pd
import requests
import common

from difflib import get_close_matches

# Hier importeren we enkele veel gebruikte functies uit het common.py script

from common import (
    TARGET_CRS,
    get_download_settings,
    get_gemeenten,
    get_gpkg_path,
    save_layer,
    setup_logging,
)


# --- Configuratie ---------------------------------------------------------

SCRIPT_NAME = "01_download"
GEMEENTE_BASE_URL = "https://api.pdok.nl/kadaster/brk-bestuurlijke-gebieden/ogc/v1"
BGT_BASE_URL = "https://api.pdok.nl/lv/bgt/ogc/v1"
TOP10NL_BASE_URL = "https://api.pdok.nl/brt/top10nl/ogc/v1"

# Hoeveel features per request kunnen worden gedownload via de API's. 1000 is het maximum. 

REQUEST_LIMIT = 1000

# Een library met de BGT-lagen die we willen downloaden. Sleutel = laagnaam in de output, 
# waarde = collectienaam in de API.

BGT_COLLECTIONS = {
    "bgt_overbruggingsdeel": "overbruggingsdeel",
    "bgt_waterdeel": "waterdeel",
    }

# Een library met de TOP10NL-lagen die we willen downloaden. Sleutel = laagnaam in de output, 
# waarde = collectienaam in de API.

TOP10NL_COLLECTIONS = {
    "top10nl_wegdeel_vlak": "wegdeel_vlak",
    "top10nl_wegdeel_lijn": "wegdeel_lijn",
    "top10nl_wegdeel_hartlijn": "wegdeel_hartlijn",
    "top10nl_spoorbaandeel_lijn": "spoorbaandeel_lijn",
    "top10nl_gebouw_vlak": "gebouw_vlak",
    "top10nl_plaats_vlak": "plaats_vlak",
    "top10nl_plaats_multivlak": "plaats_multivlak",
}

# De BGT- en gemeente-API verwachten een bbox in graden (CRS84); TOP10NL wordt
# in coördinaten systeem EPSG:28992 (Rijksdriehoek nieuw) bevraagd. Deze API's 
# gebruiken dus twee verschillende coordinaten systemen. 

BBOX_CRS_DEGREES = 4326
RD_CRS_URI = "http://www.opengis.net/def/crs/EPSG/0/28992"

# Laat zien aan de PDOK servers wie de database bevraagd en welk dataformaat
# we accepteren om te ontvangen. 

HEADERS = {
    "User-Agent": "CO2-monitor-brug-MKI-analyse (sander.hoogendoorn@sogelink.com)",
    "Accept": "application/geo+json, application/json",
}

# Laad de logger uit het common.py script. Deze logger gebruiken we om informatie op te
# slaan over de verschillende stappen die worden doorlopen in de dit script. 

logger = common.logger


# --- API-communicatie -----------------------------------------------------


def request_json(session, url, params=None, max_retries=5, timeout=120):

    """Haal JSON op van een URL, met herhaalpogingen bij netwerkfouten.
    Bij een fout wordt het opnieuw geprobeerd met een oplopende wachttijd,
    zodat een tijdelijk overbelaste server de kans krijgt te herstellen. Pas
    na max_retries mislukte pogingen wordt een RuntimeError opgeworpen en 
    stopt het script met runnen. Standaard hebben we 5 retries"""

    for attempt in range(1, max_retries + 1):
        try:
            response = session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            if attempt == max_retries:
                raise RuntimeError(f"Request mislukt na {max_retries} pogingen: {url}") from exc
            wait_seconds = 2 * attempt
            logger.debug("Request mislukt, opnieuw over %ss: %s", wait_seconds, url)
            time.sleep(wait_seconds)

# HAAL MOGELIJK WEG OMDAT DEZE FUNCTIE OVERBODIG IS
def list_collections(session, base_url):
    """Vraag de beschikbare collectie-id's van een service op."""
    try:
        data = request_json(session, f"{base_url}/collections", params={"f": "json"})
        return [c["id"] for c in data.get("collections", [])]
    except RuntimeError:
        return []


def features_to_gdf(features, crs):
    """Zet GeoJSON-features om naar een GeoDataFrame. De GeoJSOn-features worden op 
    deze manier aangeleverd:

    {"id": "NL.12345", "properties": {"naam": "Erasmusbrug", "bouwjaar": 1996}, "geometry": {...}}
    {"id": "NL.12346", "properties": {"naam": "Ketelbrug", "bouwjaar": 1997}, "geometry": {...}}

    De object-id en de geometrie van een object zitten dus een niveau boven de attributendata
    van het object. In de GeoDataFrame worden zowel de feature_id als de geometrie samengevoegd
    met de attributendata. Bij nul objecten komt een leeg GeoDataFrame terug."""

    if not features:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=crs)

    cleaned = []
    for feature in features:
        properties = dict(feature.get("properties") or {})
        if feature.get("id") is not None:
            properties["feature_id"] = feature["id"]
        cleaned.append({
            "type": "Feature",  
            "properties": properties,
            "geometry": feature.get("geometry"),
        })

    # Hier worden de lijst met met features omgezet naar een dataframe. 
    # Daarbij geldt de regel dat als geometrie niet null is en de cell 
    # ook niet leeg is, we endigen met True en False. Alleen de ~ zet 
    # de False om naar True. We eindigen dus met een True-True masker.
    # Alles waar False in zit wordt weggefilterd. We houden dus alleen
    # gevulde cellen met een bestaande geometrie over. 

    gdf = gpd.GeoDataFrame.from_features(cleaned, crs=crs)
    return gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()



def paginate(session, url, params):
    """Loop door alle resultatenpagina's van een OGC-request heen via 
    het aanroepen van de request-json functie en
    append al de data van de JSON in een lijst.De eerste request 
    krijgt de zoekparameters mee; de vervolgpagina's gebruiken de 
    kant-en-klare next-URL die de API teruggeeft.
    """

    # De features uit data worden opgehaald. In het geval er geen data aanwezig 
    # is, komt er een lege lijst terug. Ook worden de links voor de volgende
    # pagina opgehaald binnen next-url. Alleen href links worden geaccepteerd waarvan
    #  'rel' == 'next' en href /= 'None'. Als er geen next_url meer in de lijst staat
    # dan wordt deze generator ook None. Dit zorg ervoor dat deze 
    # conditie waar is: if not next_url = True. 
    # De while loop wordt nu vebroken en de data request stopt. In het geval er nog 
    # wel een next_url bestaat, word de functie geupdated met deze nieuwe url. Hierbij
    # wordt niet opnieuw een bounding box gedefineerd via params. 
    
    features = []
    while True:
        data = request_json(session, url, params=params)
        features.extend(data.get("features", []))
        next_url = next(
            (link["href"] for link in data.get("links", [])
             if link.get("rel") == "next" and link.get("href")),
            None,
        )
        if not next_url:
            break
        url, params = next_url, None
    return features


# --- BGT en gemeenten: enkele bbox-request --------------------------------

# Hier wordt een url gebouwd voor het ophalen van de BGT en gemeenten data. 
# Daarbij worden parameters gedefineerd die worden meegestuurd met de request.
# REQUEST_LIMIT is bovenaan het script gedefineerd. Bbox gaat in degrees:
# bijvoorbeeld (min_lon, min_lat, max_lon, max_lat). Na het maken van de juiste
# url en params worden de features verzameld via de paginate functie en vervolgens
# wordt de geopanda opgehaald via de features_to_gdf functie. Belangrijk om hier 
# te begrijpen dat geodata in internationaal coordinaten systeem 4326 staat of anders
# wordt gezet. De functie returned de data als geopanda binnen de box in
# coordinaten systeem 4326. 

def fetch_bbox(session, base_url, collection_name, bbox_degrees):

    """Download een collectie binnen een bbox in graden, als GeoDataFrame."""

    url = f"{base_url}/collections/{collection_name}/items"
    params = {"f": "json", "limit": REQUEST_LIMIT, "bbox": bbox_degrees}
    features = paginate(session, url, params)
    gdf = features_to_gdf(features, crs=f"EPSG:{BBOX_CRS_DEGREES}")
    return gdf.set_crs(BBOX_CRS_DEGREES) if gdf.crs is None else gdf


# --- TOP10NL: getegelde download ------------------------------------------

def create_tiles(bounds, tile_size_m, buffer_m):

    """Verdeel de bounding box in overlappende tegels in het Rijksdriehoek (RD) 
    New systeem. Via tuple unpacking worden een minx, miny, maxx, en maxy gedefineerd. 
    De hoeveelheid tiles worden bepaald door de totale lengte en breedte van de bbox
    te delen door de lengte en breedte afmetingen van de tile. De math.ceil zorgt er vervolgens 
    voor dat het getal dat hier uitkomt naar boven wordt afgerond. Er is per definitie altijd minimaal
    1 tegel aanwezig. De twee nested loops zorgen dat er voor elke tegel coördinaten worden bepaald.     
    De buffer zorgt dat er een kleine margin bij elke tegel wordt toegevoegd. Uiteindelijkt wordt 
    de lijst met tuples terug geven vanuit de functie. De dubbelingen in het ophalen van de data moeten
    er weer uit gefilterd worden."""

    minx, miny, maxx, maxy = bounds
    x_count = max(1, math.ceil((maxx - minx) / tile_size_m))
    y_count = max(1, math.ceil((maxy - miny) / tile_size_m))

    tiles = []
    for xi in range(x_count):
        for yi in range(y_count):
            tx0 = minx + xi * tile_size_m
            ty0 = miny + yi * tile_size_m
            tx1 = min(tx0 + tile_size_m, maxx)
            ty1 = min(ty0 + tile_size_m, maxy)
            tiles.append((
                max(minx, tx0 - buffer_m), max(miny, ty0 - buffer_m),
                min(maxx, tx1 + buffer_m), min(maxy, ty1 + buffer_m),
            ))
    return tiles


def fetch_tiled(session, collection_name, tiles):

    """Download een TOP10NL-collectie over alle tegels. Deze functie begint met 
    het aanpassen van een url die indicatief is voor het downloaden van de tiles.
    Deze Url bestaat uit een basis deel dat bovenin het script word gedefineerd. 
    Vervolgens wordt hier een collectie_name aan toegevoegd, zoals: wegdeel. Er
    wordt een lege lijst genaamd 'parts' aangemaakt. Daar komen straks alle data
    in te staan. Params worden gedefineerd zodat die meegegeven kunnen worden aan
    de paginate functie. 

    
    Vervolgens probeert de try functie om de features te downloaden via de paginate functie. 
    Alle data komt terecht in een feature lijst. Als het ophalen van de data fout gaat, 
    krijg je een automatische error. De functie hierna wordt de data in een GeoPanda gezet. 
    Als de Geopanda niet leeg is (wel rijen), worden de geopandas toegevoegd aan parts. Dus 
    uiteindelijk krijg je een lijst met geopandas. De logger geeft ondertussen statusupdates over 
    het downloaden van de data. Vervolgens wordt in de combined line ervoor gezorgd dat alle
    geopanda tiles onder elkaar worden gezet via de concat-methode. 

    Eventuele verdubbelingen in de data die door de overlap waren geintroduceerd worden 
    verwijderd via de drop_duplicates methode op de feature_id kolom.  

    """
    url = f"{TOP10NL_BASE_URL}/collections/{collection_name}/items" 

    parts = []
    for index, (minx, miny, maxx, maxy) in enumerate(tiles, start=1):
        params = {
            "f": "json",
            "limit": REQUEST_LIMIT,
            "bbox": f"{minx},{miny},{maxx},{maxy}",
            "bbox-crs": RD_CRS_URI,
            "crs": RD_CRS_URI,
        }
        try:
            features = paginate(session, url, params)
        except RuntimeError as exc:
            logger.warning("  tegel %d/%d mislukt: %s", index, len(tiles), exc)
            continue

        gdf = features_to_gdf(features, crs=f"EPSG:{TARGET_CRS}")
        if not gdf.empty:
            parts.append(gdf)
        logger.debug("  tegel %d/%d: %d features", index, len(tiles), len(gdf))

    if not parts:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=f"EPSG:{TARGET_CRS}")

    combined = gpd.GeoDataFrame(
        pd.concat(parts, ignore_index=True), geometry="geometry", crs=f"EPSG:{TARGET_CRS}"
    )

    # Objecten op tegelranden komen in meerdere tegels voor; op feature_id
    # ontdubbelen laat elk object een keer over.
    if "feature_id" in combined.columns:
        before = len(combined)
        combined = combined.drop_duplicates(subset=["feature_id"]).copy()
        logger.debug("  ontdubbeld: %d -> %d", before, len(combined))

    return combined.reset_index(drop=True)


# --- Gemeenteselectie -----------------------------------------------------

def select_gemeenten(gemeenten_all, requested_names):
    """Zoek de opgegeven gemeentenamen op in de gedownloade gemeentegebieden.

    Het matchen gebeurt hoofdletterongevoelig en zonder omringende spaties.
    Bij een naam die niet voorkomt stopt het script met een foutmelding en
    suggesties, want doorgaan met een lege selectie zou verderop een
    onbegrijpelijke fout opleveren.
    """
    if "naam" not in gemeenten_all.columns:
        raise KeyError(
            "Kolom 'naam' ontbreekt in de gemeentegebieden. "
            f"Aanwezig: {list(gemeenten_all.columns)}"
        )

    gemeenten_all = gemeenten_all.copy()
    gemeenten_all["naam_norm"] = gemeenten_all["naam"].astype(str).str.strip().str.casefold()

    requested = {name.strip().casefold(): name for name in requested_names}
    selected = gemeenten_all[gemeenten_all["naam_norm"].isin(requested)].copy()

    missing = [orig for norm, orig in requested.items() if norm not in set(selected["naam_norm"])]
    if missing:
        suggestions = get_close_matches(
            missing[0].strip().casefold(), gemeenten_all["naam_norm"].tolist(), n=3, cutoff=0.6
        )
        message = f"Onbekende gemeenten in config.yaml: {missing}."
        if suggestions:
            message += f" Bedoelde je: {suggestions}?"
        raise ValueError(message)

    return selected.drop(columns=["naam_norm"])


# --- Hoofdprogramma -------------------------------------------------------

def main():
    setup_logging()

    gpkg_path = get_gpkg_path(SCRIPT_NAME)
    gpkg_path.unlink(missing_ok=True)

    settings = get_download_settings()
    requested_names = get_gemeenten()
    logger.info("Studiegebied: %s\n", ", ".join(requested_names))

    with requests.Session() as session:
        session.headers.update(HEADERS)

        # --- Gemeenten ---
        gemeenten_all = fetch_bbox(session, GEMEENTE_BASE_URL, "gemeentegebied", None)
        gemeenten_selected = select_gemeenten(gemeenten_all, requested_names)
        logger.info(
            "Geselecteerd: %s",
            ", ".join(f"{r.naam} ({r.code})" for r in gemeenten_selected.itertuples()),
        )

        save_layer(gemeenten_selected, gpkg_path, "gemeentegebied_selected",
                   script_name=SCRIPT_NAME)

        # De bbox in graden voor de BGT, en in RD New voor de TOP10NL-tegels.
        bounds_degrees = gemeenten_selected.to_crs(BBOX_CRS_DEGREES).total_bounds
        bbox_degrees = ",".join(map(str, bounds_degrees))
        bounds_rd = gemeenten_selected.to_crs(TARGET_CRS).total_bounds

        # --- BGT ---
        logger.info("\n=== BGT ===")
        for layer_name, collection_name in BGT_COLLECTIONS.items():
            gdf = fetch_bbox(session, BGT_BASE_URL, collection_name, bbox_degrees)
            if gdf.empty:
                raise RuntimeError(
                    f"BGT-collectie '{collection_name}' leverde niets op. "
                    f"Controleer {BGT_BASE_URL}/collections"
                )
            logger.info("%s: %d features", layer_name, len(gdf))
            save_layer(gdf, gpkg_path, layer_name, script_name=SCRIPT_NAME)

        # --- TOP10NL ---
        logger.info("\n=== TOP10NL ===")
        tiles = create_tiles(bounds_rd, settings["tegel_grootte_m"], settings["tegel_buffer_m"])
        logger.info("Studiegebied in %d tegels van %d m\n", len(tiles), settings["tegel_grootte_m"])

        available = list_collections(session, TOP10NL_BASE_URL)
        for layer_name, collection_name in TOP10NL_COLLECTIONS.items():
            if available and collection_name not in available:
                logger.warning("TOP10NL-collectie '%s' niet gevonden; overgeslagen.", collection_name)
                continue

            logger.info("%s ophalen...", layer_name)
            gdf = fetch_tiled(session, collection_name, tiles)
            if gdf.empty:
                logger.warning("%s: leeg, overgeslagen", layer_name)
                continue
            logger.info("%s: %d features", layer_name, len(gdf))
            save_layer(gdf, gpkg_path, layer_name, script_name=SCRIPT_NAME)

    logger.info("\nStap 01 klaar.")
    logger.info("GeoPackage: %s", gpkg_path)


if __name__ == "__main__":
    main()