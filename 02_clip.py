"""Stap 02: lagen begrenzen tot de gemeenten en kolommen inperken.

Deze stap doet drie dingen met de ruwe download uit stap 01:

    begrenzen   De meeste lagen worden geclipt op de gemeentegrenzen: alleen
                het deel binnen het studiegebied blijft over. De
                overbruggingsdelen worden daarentegen geselecteerd, niet
                afgesneden, zodat een brug op de rand zijn volledige omvang
                houdt (die omvang bepaalt straks het profiel).

    kolommen    Per laag blijft alleen de selectie kolommen over die in latere
                stappen nodig is, plus geometrie en feature_id. De ruwe,
                volledige data blijft in stap 01 bewaard.

    gemeenten   De overbruggingsdelen krijgen twee kolommen die aangeven in
                welke gemeente(n) ze liggen: binnen_gemeente_naam en
                binnen_gemeente_code, met de gemeente met de grootste overlap
                vooraan. Een brug die een grens overschrijdt krijgt beide
                gemeenten, puntkomma-gescheiden. De definitieve toewijzing op
                oppervlak gebeurt pas in stap 03, na het samenvoegen tot hele
                bruggen.

    python 02_clip.py
"""

import geopandas as gpd
import pandas as pd

import common
from common import (
    TARGET_CRS,
    get_gpkg_path,
    keep_polygons,
    read_layer,
    save_layer,
    setup_logging,
)


# --- Configuratie ---------------------------------------------------------

SCRIPT_NAME = "02_clip"
SOURCE_SCRIPT = "01_download"

# Per laag de kolommen die behouden blijven. feature_id en geometry worden
# altijd bewaard en staan hier niet bij. Een kolom die in de bron ontbreekt
# wordt overgeslagen met een waarschuwing, zodat een tikfout of een gewijzigd
# veld opvalt in plaats van stil te verdwijnen.
COLUMNS_TO_KEEP = {
    "bgt_overbruggingsdeel": [
        "bronhouder",
        "hoort_bij_typeoverbrugging",
        "lokaal_id",
        "overbrugging_is_beweegbaar",
        "relatieve_hoogteligging",
        "type_overbruggingsdeel",
    ],
    "bgt_waterdeel": [
        "bronhouder",
        "lokaal_id",
        "plus_type",
        "type",
    ],

     "top10nl_wegdeel_vlak": [
        "aantalrijstroken", "afritnummer", "awegnummer", "ewegnummer",
        "fysiekvoorkomen", "gescheidenrijbaan", "hoofdverkeersgebruik",
        "hoogteniveau", "knooppuntnaam", "lokaal_id", "naam", "nwegnummer",
        "tdncode", "tunnelnaam", "typeweg", "typeinfrastructuur",
        "verhardingsbreedteklasse", "verhardingstype",
    ],
    "top10nl_wegdeel_lijn": [
        "brugnaam", "fysiekvoorkomen", "hoofdverkeersgebruik", "hoogteniveau",
        "isbagnaam", "lokaal_id", "naam", "tunnelnaam", "typeweg",
        "verhardingsbreedteklasse", "verhardingstype",
    ],
    "top10nl_wegdeel_hartlijn": [
        "aantalrijstroken", "afritnummer", "ewegnummer", "awegnummer",
        "fysiekvoorkomen", "gescheidenrijbaan", "hoofdverkeersgebruik",
        "hoogteniveau", "brugnaam", "lokaal_id", "naam", "nwegnummer",
        "isbagnaam", "tunnelnaam", "typeweg", "verhardingsbreedteklasse",
        "verhardingstype",
    ],
    "top10nl_spoorbaandeel_lijn": [
        "aantalsporen", "fysiekvoorkomen", "hoogteniveau", "hoofdspoor",
        "typespoorbaan", "vervoerfunctie",
    ],
    "top10nl_gebouw_vlak": [
        "lokaal_id", "typegebouw",
    ],
    "top10nl_plaats_vlak": [
        "aantalinwoners", "bebouwdekom", "isbagwoonplaats", "lokaal_id",
        "naamnl", "typegebied",
    ],
    "top10nl_plaats_multivlak": [
        "aantalinwoners", "bebouwdekom", "isbagwoonplaats", "lokaal_id",
        "naamnl", "typegebied",
    ],
}

# Lagen die geclipt worden op de gemeentegrens. De overbruggingsdelen staan
# hier bewust niet bij: die worden geselecteerd, zie SELECT_LAYER.
CLIP_LAYERS = [
    "bgt_waterdeel",
    "top10nl_wegdeel_vlak",
    "top10nl_wegdeel_lijn",
    "top10nl_wegdeel_hartlijn",
    "top10nl_spoorbaandeel_lijn",
    "top10nl_gebouw_vlak",
    "top10nl_plaats_vlak",
    "top10nl_plaats_multivlak",
]

# De laag die geselecteerd wordt in plaats van geclipt, zodat randbruggen hun
# volledige omvang houden. Deze krijgt ook de gemeentekolommen.
SELECT_LAYER = "bgt_overbruggingsdeel"

logger = common.logger


# --- Kolommen inperken ----------------------------------------------------

def select_columns(gdf, layer_name):
    """Behoud alleen de gewenste kolommen, plus feature_id en geometry.

    Een gevraagde kolom die niet in de laag zit wordt overgeslagen met een
    waarschuwing. Zo valt op als een veldnaam is veranderd of verkeerd
    gespeld, in plaats van dat de kolom stil ontbreekt in de output.
    """
    wanted = COLUMNS_TO_KEEP.get(layer_name, [])
    keep = []

    for col in ["feature_id"] + wanted:
        if col in gdf.columns:
            keep.append(col)
        elif col != "feature_id":
            logger.warning("  kolom ontbreekt in %s: %s", layer_name, col)

    keep.append(gdf.geometry.name)
    return gdf[keep].copy()


# --- Begrenzen ------------------------------------------------------------

def clip_layer(gdf, gemeenten, layer_name):
    """Snijd een laag af op de gemeentegrenzen.

    De overlay houdt alleen de delen binnen een gemeente over. Na de overlay
    blijven alleen polygonen over voor de vlaklagen; voor lijnlagen (zoals de
    hartlijnen en spoorbanen) wordt keep_geom_type gebruikt zodat het
    lijntype behouden blijft.
    """
    # Voor lijnlagen levert keep_polygons niets op; daarom clippen we met
    # gpd.clip, dat het geometrietype respecteert, in plaats van een overlay
    # die op vlakken is gericht.
    is_polygon = gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).any()

    if is_polygon:
        clipped = keep_polygons(
            gpd.overlay(gdf, gemeenten, how="intersection", keep_geom_type=True)
        )
    else:
        clipped = gpd.clip(gdf, gemeenten)
        clipped = clipped[clipped.geometry.notna() & ~clipped.geometry.is_empty].copy()

    logger.info("Geclipt: %s (%d -> %d)", layer_name, len(gdf), len(clipped))
    return clipped


def select_bridges_with_municipality(gdf, gemeenten, layer_name):
    """Selecteer overbruggingsdelen en voeg de gemeente(n) toe waarin ze liggen.

    De brugdelen worden niet afgesneden: een deel dat het studiegebied raakt
    gaat er in zijn geheel in. Vervolgens wordt per deel bepaald welke
    gemeenten het overlapt en hoe groot die overlap is. De gemeenten komen in
    twee kolommen, met de grootste overlap vooraan; een deel op een
    gemeentegrens krijgt beide, puntkomma-gescheiden.

    De definitieve toewijzing (een brug hoort bij een gemeente) gebeurt pas in
    stap 03, na het samenvoegen tot hele bruggen. Hier blijft de volledige
    informatie bewaard.
    """
    # Overlap per deel per gemeente, om op te kunnen sorteren op grootte.
    overlap = gpd.overlay(
        gdf[["feature_id", "geometry"]],
        gemeenten[["binnen_gemeente_naam", "binnen_gemeente_code", "geometry"]],
        how="intersection",
        keep_geom_type=True,
    )
    overlap["overlap_area"] = overlap.geometry.area

    # Per feature_id de gemeenten op aflopende overlap, samengevoegd tot een
    # puntkomma-lijst. De namen en codes blijven in dezelfde volgorde.
    overlap = overlap.sort_values("overlap_area", ascending=False)

    def join_unique(values):
        # dict.fromkeys houdt de volgorde en verwijdert dubbelingen.
        return "; ".join(dict.fromkeys(str(v) for v in values))

    gemeente_per_deel = (
        overlap.groupby("feature_id")
        .agg(
            binnen_gemeente_naam=("binnen_gemeente_naam", join_unique),
            binnen_gemeente_code=("binnen_gemeente_code", join_unique),
            aantal_gemeenten=("binnen_gemeente_naam", "nunique"),
        )
        .reset_index()
    )

    # Alleen de delen die minstens een gemeente raken; delen volledig buiten
    # het studiegebied vallen af.
    selected = gdf[gdf["feature_id"].isin(gemeente_per_deel["feature_id"])].copy()
    selected = selected.merge(
        gemeente_per_deel, on="feature_id", how="left"
    )

    dubbel = int((gemeente_per_deel["aantal_gemeenten"] > 1).sum())
    logger.info("Geselecteerd: %s (%d -> %d)", layer_name, len(gdf), len(selected))
    logger.info(
        "  brugdelen in meerdere gemeenten: %d van %d (%.1f%%)",
        dubbel, len(selected), 100 * dubbel / len(selected) if len(selected) else 0,
    )

    # De hulpkolom aantal_gemeenten hoeft niet mee de output in.
    return selected.drop(columns=["aantal_gemeenten"])


# --- Gemeenten voorbereiden -----------------------------------------------

def prepare_municipalities(gemeenten):
    """Breng de gemeentelaag terug tot naam, code en geometrie.

    De kolommen worden hernoemd naar binnen_gemeente_naam en
    binnen_gemeente_code, zodat in de overbruggingslaag meteen duidelijk is
    dat het om de gemeente gaat waarbinnen het deel ligt, niet om een
    bronhouder of andere administratieve verwijzing.
    """
    if "naam" not in gemeenten.columns or "identificatie" not in gemeenten.columns:
        raise KeyError(
            "Verwacht 'naam' en 'identificatie' in gemeentegebied_selected. "
            f"Aanwezig: {list(gemeenten.columns)}"
        )

    gemeenten = gemeenten.rename(columns={
        "naam": "binnen_gemeente_naam",
        "identificatie": "binnen_gemeente_code",
    })
    return gemeenten[["binnen_gemeente_naam", "binnen_gemeente_code", "geometry"]].copy()


# --- Hoofdprogramma -------------------------------------------------------

def main():
    setup_logging()

    source_gpkg = get_gpkg_path(SOURCE_SCRIPT)
    if not source_gpkg.exists():
        raise FileNotFoundError(
            f"Download-GeoPackage niet gevonden: {source_gpkg}\n"
            "Draai eerst 01_download.py."
        )

    output_gpkg = get_gpkg_path(SCRIPT_NAME)
    output_gpkg.unlink(missing_ok=True)

    gemeenten = prepare_municipalities(
        read_layer(source_gpkg, "gemeentegebied_selected", make_valid=True)
    )
    save_layer(gemeenten, output_gpkg, "gemeentegebied_selected", script_name=SCRIPT_NAME)

    # De overbruggingsdelen: selecteren, gemeenten toevoegen, kolommen inperken.
    logger.info("\n=== Overbruggingsdelen (selecteren) ===")
    bridges = read_layer(source_gpkg, SELECT_LAYER, make_valid=True)
    bridges = select_bridges_with_municipality(bridges, gemeenten, SELECT_LAYER)
    bridges = select_columns_keeping_gemeente(bridges, SELECT_LAYER)
    save_layer(bridges, output_gpkg, SELECT_LAYER, script_name=SCRIPT_NAME)

    # De overige lagen: clippen en kolommen inperken.
    logger.info("\n=== Overige lagen (clippen) ===")
    for layer_name in CLIP_LAYERS:
        gdf = read_layer(source_gpkg, layer_name, make_valid=True)
        gdf = clip_layer(gdf, gemeenten, layer_name)
        if gdf.empty:
            logger.warning("Leeg na clippen, overgeslagen: %s", layer_name)
            continue
        gdf = select_columns(gdf, layer_name)
        save_layer(gdf, output_gpkg, layer_name, script_name=SCRIPT_NAME)

    logger.info("\nStap 02 klaar.")
    logger.info("GeoPackage: %s", output_gpkg)


def select_columns_keeping_gemeente(gdf, layer_name):
    """Als select_columns, maar met de twee gemeentekolommen erbij.

    De overbruggingsdelen hebben naast hun eigen kolommen ook de zojuist
    toegevoegde binnen_gemeente_naam en binnen_gemeente_code, die behouden
    moeten blijven.
    """
    wanted = COLUMNS_TO_KEEP.get(layer_name, [])
    keep = []

    for col in ["feature_id"] + wanted + ["binnen_gemeente_naam", "binnen_gemeente_code"]:
        if col in gdf.columns:
            keep.append(col)
        elif col not in ("feature_id",):
            logger.warning("  kolom ontbreekt in %s: %s", layer_name, col)

    keep.append(gdf.geometry.name)
    return gdf[keep].copy()


if __name__ == "__main__":
    main()