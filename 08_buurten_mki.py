"""Stap 08: brug-MKI koppelen aan CBS-buurten.

Downloadt de CBS Wijk- en Buurtkaart 2025 binnen de bounding box om de
gemeenten uit config.yaml, schoont de buurten op, perkt de kolommen in tot de
bruikbare kerncijfers, en koppelt er de brug-MKI uit stap 06 aan. Het resultaat
is een buurtlaag met per buurt het aantal brugobjecten (per type en totaal) en
de bijbehorende MKI-kosten, inclusief MKI per inwoner.

Beslissingen, zodat ze terug te vinden zijn:

  Opschonen   Buurten zonder bruikbaar inwonertal vallen af: de CBS-codes
              -99997 en -99998 (onbekend/geheim), 0 inwoners, en lege waarden.
              Dat haalt bedrijventerreinen, water en niet-ingevulde buurten weg.

  Kolommen    Alleen de kerncijfers hieronder blijven behouden, plus het
              inwonertal zelf (nodig voor de MKI per inwoner) en de geometrie.

  Koppeling   Elke brug hoort bij de buurt waar zijn grootste deel in ligt
              (grootste overlap). Een grensbrug telt zo bij precies een buurt,
              wat dubbeltelling voorkomt; de buurttotalen tellen samen op tot
              het echte totaal.

  Tellingen   Per buurt komen er tellingen per type (viaduct, brug, fietsbrug)
              en een totaal, de totale en de gemiddelde MKI per brugobject, en
              de MKI per inwoner.

    python 08_buurten_mki.py
"""

import math
import time

import geopandas as gpd
import pandas as pd
import requests

import common
from common import (
    TARGET_CRS,
    get_download_settings,
    get_gpkg_path,
    keep_polygons,
    parse_numeric_value,
    read_layer,
    save_layer,
    setup_logging,
)


# --- Configuratie ---------------------------------------------------------

SCRIPT_NAME = "08_buurten_mki"
GEMEENTE_SOURCE_SCRIPT = "01_download"
MKI_SOURCE_SCRIPT = "06_mki"
MKI_LAYER = "bruggen_mki"

CBS_BASE_URL = "https://api.pdok.nl/cbs/wijken-en-buurten-2025/ogc/v1"

# De buurtcollectie. De CBS-service biedt gemeenten, wijken en buurten aan; hier
# gaat het om de buurten. De naam wordt tegen de collectielijst gecontroleerd,
# dus een afwijking wordt gemeld in plaats van stil te falen.
BUURT_COLLECTION = "buurten"

# Mogelijke namen voor de inwonerkolom, want CBS wisselt wel eens tussen
# schrijfwijzen. De eerste die in de data zit, wordt gebruikt.
INWONER_KOLOM_KANDIDATEN = ["aantal_inwoners", "aantalInwoners", "inwoners"]

# CBS-codes voor onbekend of geheim; deze tellen als geen bruikbare waarde.
CBS_ONBEKEND = {-99997, -99998}

# Kolommen die van de buurten behouden blijven, plus het inwonertal en de
# geometrie (die worden apart toegevoegd).
BUURT_KOLOMMEN = [
    "bevolkingsdichtheid_inwoners_per_km2",
    "buurtcode",
    "aantal_huishoudens",
    "buurtnaam",
    "gemeentecode",
    "gemeentenaam",
    "mannen",
    "vrouwen",
    "oppervlakte_land_in_ha",
    "oppervlakte_totaal_in_ha",
    "wijkcode",
    "percentage_personen_0_tot_15_jaar",
    "percentage_personen_15_tot_25_jaar",
    "percentage_personen_25_tot_45_jaar",
    "percentage_personen_45_tot_65_jaar",
    "percentage_personen_65_jaar_en_ouder",
]

# Profiel-prefix naar teltype: waarmee we per buurt viaducten, bruggen en
# fietsbruggen apart tellen. De volgorde is belangrijk: fietsbrug wordt voor
# brug getest, zodat een fietsbrugprofiel niet als gewone brug telt.
TYPE_PREFIXEN = {
    "viaduct": "aantal_viaducten",
    "fietsbrug": "aantal_fietsbruggen",
    "brug": "aantal_bruggen",
}

REQUEST_LIMIT = 1000
RD_CRS_URI = "http://www.opengis.net/def/crs/EPSG/0/28992"
HEADERS = {
    "User-Agent": "co2-monitor-bridges-analysis/0.2",
    "Accept": "application/geo+json, application/json",
}

logger = common.logger


# --- API-communicatie -----------------------------------------------------

def request_json(session, url, params=None, max_retries=5, timeout=120):
    for attempt in range(1, max_retries + 1):
        try:
            response = session.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            if attempt == max_retries:
                raise RuntimeError(f"Request mislukt na {max_retries} pogingen: {url}") from exc
            time.sleep(2 * attempt)


def list_collections(session, base_url):
    try:
        data = request_json(session, f"{base_url}/collections", params={"f": "json"})
        return [c["id"] for c in data.get("collections", [])]
    except RuntimeError:
        return []


def features_to_gdf(features, crs):
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
    gdf = gpd.GeoDataFrame.from_features(cleaned, crs=crs)
    return gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()


def paginate(session, url, params):
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


def create_tiles(bounds, tile_size_m, buffer_m):
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


def fetch_tiled(session, base_url, collection_name, tiles):
    url = f"{base_url}/collections/{collection_name}/items"
    parts = []
    for index, (minx, miny, maxx, maxy) in enumerate(tiles, start=1):
        params = {
            "f": "json", "limit": REQUEST_LIMIT,
            "bbox": f"{minx},{miny},{maxx},{maxy}",
            "bbox-crs": RD_CRS_URI, "crs": RD_CRS_URI,
        }
        try:
            features = paginate(session, url, params)
        except RuntimeError as exc:
            logger.warning("  tegel %d/%d mislukt: %s", index, len(tiles), exc)
            continue
        gdf = features_to_gdf(features, crs=f"EPSG:{TARGET_CRS}")
        if not gdf.empty:
            parts.append(gdf)

    parts = [p for p in parts if not p.empty]
    if not parts:
        return gpd.GeoDataFrame(columns=["geometry"], geometry="geometry", crs=f"EPSG:{TARGET_CRS}")
    combined = gpd.GeoDataFrame(
        pd.concat(parts, ignore_index=True), geometry="geometry", crs=f"EPSG:{TARGET_CRS}"
    )
    if "feature_id" in combined.columns:
        combined = combined.drop_duplicates(subset=["feature_id"]).copy()
    return combined.reset_index(drop=True)


# --- Opschonen en inperken ------------------------------------------------

def vind_inwonerkolom(gdf):
    """Zoek welke van de kandidaat-kolomnamen het inwonertal bevat."""
    for kandidaat in INWONER_KOLOM_KANDIDATEN:
        if kandidaat in gdf.columns:
            return kandidaat
    logger.warning("Geen inwonerkolom gevonden; opschonen op inwoners overgeslagen")
    return None


def schoon_buurten(gdf):
    """Verwijder buurten zonder bruikbaar inwonertal.

    De CBS-codes -99997 en -99998 (onbekend/geheim), nul inwoners en lege
    waarden vallen af. Zo blijven alleen bewoonde buurten met echte cijfers
    over.
    """
    inwoner_kol = vind_inwonerkolom(gdf)
    if inwoner_kol is None:
        return gdf

    waarden = gdf[inwoner_kol].map(parse_numeric_value)
    houd = waarden.notna() & (~waarden.isin(CBS_ONBEKEND)) & (waarden > 0)

    verwijderd = int((~houd).sum())
    logger.info("Buurten opgeschoond op inwonertal: %d -> %d (%d weg)",
                len(gdf), int(houd.sum()), verwijderd)
    return gdf[houd].copy()


def perk_kolommen_in(gdf):
    """Behoud alleen de gewenste kerncijfers, het inwonertal en de geometrie."""
    inwoner_kol = vind_inwonerkolom(gdf)
    houd = []
    for col in BUURT_KOLOMMEN:
        if col in gdf.columns:
            houd.append(col)
        else:
            logger.warning("  buurtkolom ontbreekt: %s", col)
    if inwoner_kol and inwoner_kol not in houd:
        houd.append(inwoner_kol)
    houd.append(gdf.geometry.name)
    return gdf[houd].copy()


# --- Bruggen aan buurten koppelen -----------------------------------------

def wijs_bruggen_toe_aan_buurten(bruggen, buurten):
    """Wijs elke brug toe aan de buurt met de grootste overlap.

    Per brug wordt de buurt met de grootste overlappende oppervlakte gekozen,
    zodat een grensbrug bij precies een buurt hoort en niet dubbel telt.
    """
    buurten = buurten.reset_index(drop=True).copy()
    buurten["_buurt_id"] = buurten.index

    overlay = gpd.overlay(
        bruggen[["bridge_group_id", "profiel", "mki_per_jaar", "mki_totaal_100jaar", "geometry"]],
        buurten[["_buurt_id", "geometry"]],
        how="intersection", keep_geom_type=True,
    )
    if overlay.empty:
        logger.warning("Geen enkele brug overlapt met een buurt")
        return bruggen.assign(_buurt_id=pd.NA)

    overlay["_overlap_area"] = overlay.geometry.area
    grootste = overlay.loc[
        overlay.groupby("bridge_group_id")["_overlap_area"].idxmax(),
        ["bridge_group_id", "_buurt_id"],
    ]

    toegewezen = bruggen.merge(grootste, on="bridge_group_id", how="left")
    n_zonder = int(toegewezen["_buurt_id"].isna().sum())
    if n_zonder:
        logger.info("%d bruggen vallen buiten alle buurten (overgeslagen bij telling)", n_zonder)
    return toegewezen


def teltype_van_profiel(profiel):
    """Bepaal het teltype (viaduct/brug/fietsbrug) uit een profielnaam."""
    if not isinstance(profiel, str):
        return None
    for prefix, kolom in TYPE_PREFIXEN.items():
        if profiel.startswith(prefix):
            return kolom
    return None


def aggregeer_naar_buurten(bruggen_toegewezen, buurten, inwoner_kol=None):
    """Tel per buurt de brugobjecten en som de MKI.

    Per buurt komen er tellingen per type en een totaal, de totale MKI, de
    gemiddelde MKI per brugobject, de MKI per inwoner, en de MKI per m².
    Buurten zonder bruggen krijgen nullen, niet leeg, zodat de kolommen overal 
    ingevuld zijn.
    """
    buurten = buurten.reset_index(drop=True).copy()
    buurten["_buurt_id"] = buurten.index

    geldig = bruggen_toegewezen[bruggen_toegewezen["_buurt_id"].notna()].copy()
    geldig["_teltype"] = geldig["profiel"].map(teltype_van_profiel)

    # Tellingen per type, als brede tabel per buurt.
    per_type = (
        geldig.dropna(subset=["_teltype"])
        .groupby(["_buurt_id", "_teltype"]).size()
        .unstack(fill_value=0)
    )
    for kolom in TYPE_PREFIXEN.values():
        if kolom not in per_type.columns:
            per_type[kolom] = 0

    # Totaal aantal en MKI-sommen per buurt.
    totalen = geldig.groupby("_buurt_id").agg(
        aantal_overbruggingen=("bridge_group_id", "size"),
        mki_per_jaar_totaal=("mki_per_jaar", "sum"),
        mki_totaal_100jaar=("mki_totaal_100jaar", "sum"),
    )

    samen = per_type.join(totalen, how="outer")
    samen["mki_per_jaar_gemiddeld"] = (
        samen["mki_per_jaar_totaal"] / samen["aantal_overbruggingen"]
    )

    resultaat = buurten.merge(samen, on="_buurt_id", how="left")

    # Buurten zonder bruggen: tellingen op 0, MKI op 0, gemiddelde op 0.
    telkolommen = list(TYPE_PREFIXEN.values()) + [
        "aantal_overbruggingen", "mki_per_jaar_totaal", "mki_totaal_100jaar",
        "mki_per_jaar_gemiddeld",
    ]
    for kolom in telkolommen:
        if kolom in resultaat.columns:
            resultaat[kolom] = resultaat[kolom].fillna(0)

    # MKI per inwoner: de totale jaar-MKI van de buurt gedeeld door het
    # inwonertal. Een buurt zonder inwoners of zonder bruggen krijgt 0. Let op
    # bij het interpreteren: een dunbevolkte buurt met een grote brug scoort
    # hoog, want de kosten worden over weinig mensen verdeeld.
    if inwoner_kol and inwoner_kol in resultaat.columns:
        inwoners = resultaat[inwoner_kol].map(parse_numeric_value)
        resultaat["mki_per_jaar_per_inwoner"] = (
            resultaat["mki_per_jaar_totaal"] / inwoners
        ).where(inwoners > 0, 0).round(4)
    else:
        logger.warning("Geen inwonerkolom; mki_per_jaar_per_inwoner overgeslagen")

    # MKI per vierkante meter: de totale jaar-MKI gedeeld door de landoppervlakte
    # in m². De CBS-kolom geeft hectares, dus vermenigvuldigen met 10.000 voor m².
    # Een buurt zonder landoppervlakte of zonder bruggen krijgt 0.
    if "oppervlakte_land_in_ha" in resultaat.columns:
        oppervlakte_ha = resultaat["oppervlakte_land_in_ha"].map(parse_numeric_value)
        oppervlakte_m2 = oppervlakte_ha * 10000  # hectare naar m²
        resultaat["mki_per_jaar_per_m2"] = (
            resultaat["mki_per_jaar_totaal"] / oppervlakte_m2
        ).where(oppervlakte_m2 > 0, 0).round(6)
    else:
        logger.warning("Geen oppervlakte_land_in_ha kolom; mki_per_jaar_per_m2 overgeslagen")

    # Afronden en opruimen.
    for kolom in ["mki_per_jaar_totaal", "mki_totaal_100jaar", "mki_per_jaar_gemiddeld"]:
        resultaat[kolom] = resultaat[kolom].round(2)
    for kolom in list(TYPE_PREFIXEN.values()) + ["aantal_overbruggingen"]:
        resultaat[kolom] = resultaat[kolom].astype(int)

    return resultaat.drop(columns=["_buurt_id"])


# --- Hoofdprogramma -------------------------------------------------------

def main():
    setup_logging()

    gemeente_gpkg = get_gpkg_path(GEMEENTE_SOURCE_SCRIPT)
    mki_gpkg = get_gpkg_path(MKI_SOURCE_SCRIPT)
    for path, stap in [(gemeente_gpkg, "01"), (mki_gpkg, "06")]:
        if not path.exists():
            raise FileNotFoundError(f"GeoPackage van stap {stap} ontbreekt: {path}")

    output_gpkg = get_gpkg_path(SCRIPT_NAME)
    output_gpkg.unlink(missing_ok=True)

    settings = get_download_settings()
    gemeenten = read_layer(gemeente_gpkg, "gemeentegebied_selected", make_valid=True)
    bruggen = read_layer(mki_gpkg, MKI_LAYER)

    tiles = create_tiles(gemeenten.total_bounds, settings["tegel_grootte_m"], settings["tegel_buffer_m"])
    logger.info("Studiegebied in %d tegels\n", len(tiles))

    with requests.Session() as session:
        session.headers.update(HEADERS)

        available = list_collections(session, CBS_BASE_URL)
        logger.info("Beschikbare CBS-collecties:\n  %s\n", ", ".join(available) or "(geen)")

        if BUURT_COLLECTION not in available:
            raise RuntimeError(
                f"Buurtcollectie '{BUURT_COLLECTION}' niet gevonden. "
                f"Beschikbaar: {available}"
            )

        logger.info("%s ophalen...", BUURT_COLLECTION)
        buurten = fetch_tiled(session, CBS_BASE_URL, BUURT_COLLECTION, tiles)
        logger.info("%s: %d features\n", BUURT_COLLECTION, len(buurten))

    if buurten.empty:
        raise RuntimeError("Geen buurten opgehaald.")

    # Opschonen, clippen op de gemeenten, kolommen inperken.
    buurten = schoon_buurten(buurten)
    buurten = keep_polygons(gpd.overlay(
        keep_polygons(buurten), gemeenten[["geometry"]], how="intersection", keep_geom_type=True
    ))
    logger.info("Buurten na clippen op de gemeenten: %d", len(buurten))
    buurten = perk_kolommen_in(buurten)

    # Bruggen toewijzen en aggregeren.
    toegewezen = wijs_bruggen_toe_aan_buurten(bruggen, buurten)
    inwoner_kol = vind_inwonerkolom(buurten)
    buurten_mki = aggregeer_naar_buurten(toegewezen, buurten, inwoner_kol)

    save_layer(buurten_mki, output_gpkg, "buurten_mki", script_name=SCRIPT_NAME)

    # Korte samenvatting.
    met_bruggen = int((buurten_mki["aantal_overbruggingen"] > 0).sum())
    logger.info("\nBuurten: %d, waarvan %d met minstens een brug", len(buurten_mki), met_bruggen)
    logger.info("Totale MKI over alle buurten: %.2f per jaar",
                buurten_mki["mki_per_jaar_totaal"].sum())
    logger.info("\nStap 08 klaar.")
    logger.info("GeoPackage: %s", output_gpkg)


if __name__ == "__main__":
    main()