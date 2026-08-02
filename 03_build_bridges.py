"""Stap 03: brugobjecten opbouwen uit losse overbruggingsdelen.

De BGT levert bruggen als losse vlakken: een dek, soms meerdere stukken per
rijrichting. Deze stap maakt daar hele brugobjecten van, in vier stappen:

    1. Filteren op brugdekken (dek of leeg; pijler, landhoofd, sloof en pyloon
       vallen af, want dat zijn dragende onderdelen die al in de MKI-kentallen
       zitten).

    2. Delen met hetzelfde lokaal_id samenvoegen tot een brugobject. De
       attributen komen van het grootste deel: een object dat uit tientallen
       vlakken bestaat krijgt zo een enkele, leesbare set waarden in plaats van
       lange puntkomma-lijsten. De geometrie is wel de vereniging van alles.

    3. Duplicaten verwijderen: als het kleinste van twee objecten voor 90% of
       meer binnen het andere valt, is het een dubbele aanlevering en verdwijnt
       het kleinste. Hoogte telt hier niet mee.

    4. Overlappende objecten samenvoegen, met drie zones:
         onder 50%      nooit samenvoegen
         50 tot 80%     alleen als de hoogteniveaus exact gelijk zijn
         boven 80%      altijd samenvoegen, ook bij verschillende hoogte
       De hoogtecheck in de middenzone voorkomt dat een dek op niveau 1 aan de
       weg op maaiveld eronder wordt geplakt.

Daarna wordt elke brug toegewezen aan de gemeente met de grootste overlap en
worden de afmetingen berekend.

De invoer komt uit stap 02: de overbruggingsdelen zijn daar geselecteerd (niet
afgesneden) en hebben binnen_gemeente_naam en binnen_gemeente_code meegekregen.

    python 03_build_bridges.py
"""

import math

import geopandas as gpd
import pandas as pd

import common
from common import (
    get_gpkg_path,
    keep_polygons,
    min_max_numeric,
    read_layer,
    save_layer,
    setup_logging,
)


# --- Configuratie ---------------------------------------------------------

SCRIPT_NAME = "03_build_bridges"
SOURCE_SCRIPT = "02_clip"

BRIDGE_LAYER = "bgt_overbruggingsdeel"


# Een minimale overlapoppervlakte om kleine geometrische ruis te negeren.
SPATIAL_OVERLAP_AREA_THRESHOLD_M2 = 1.0

# Duplicaat: het kleinste object valt voor deze fractie binnen het andere.
SPATIAL_DUPLICATE_OVERLAP_RATIO_THRESHOLD = 0.90

# Samenvoegen: onder deze fractie gebeurt er niets.
SPATIAL_MERGE_OVERLAP_RATIO_THRESHOLD = 0.50

# Boven deze fractie wordt het hoogteverschil genegeerd bij het samenvoegen:
# zo sterk overlappende objecten zijn vrijwel zeker hetzelfde bouwwerk, alleen
# anders gekarteerd. Tussen de merge-drempel en deze grens moeten de
# hoogteniveaus exact overeenkomen.
SPATIAL_MERGE_IGNORE_HEIGHT_RATIO = 0.80

# type_overbruggingsdeel-waarden die als dek tellen. Leeg hoort erbij, omdat
# een ontbrekend type in de praktijk vrijwel altijd een dek blijkt. Alle andere
# waarden (pijler, landhoofd, sloof, pyloon) vallen af.
BRIDGE_DECK_VALUES = {"", "none", "null", "nan", "dek"}

# Kolommen waarvan de waarde van het grootste deel wordt overgenomen. De
# _values-achtervoegsel blijft in de kolomnaam staan, zodat stap 04 en 05
# ongewijzigd blijven werken.
SUMMARY_COLUMNS = [
    "bronhouder",
    "lokaal_id",
    "type_overbruggingsdeel",
    "overbrugging_is_beweegbaar",
    "hoort_bij_typeoverbrugging",
]

# De kolommen die de output overhoudt, in deze volgorde.
OUTPUT_COLUMNS = [
    "bridge_group_id",
    "gekozen_gemeente_naam",
    "gekozen_gemeente_code",
    "deelt_gemeentegrens",
    "component_count",
    "is_samengevoegd",
    "bridge_hoogte_values",
    "bronhouder_values",
    "lokaal_id_values",
    "type_overbruggingsdeel_values",
    "overbrugging_is_beweegbaar_values",
    "hoort_bij_typeoverbrugging_values",
    "area_m2",
    "bbox_lengte_m",
    "oppervlakte_breedte_m",
    "bbox_breedte_m",
    "geometry",
]

logger = common.logger


# --- Hulpfuncties ---------------------------------------------------------

def find_height_column(gdf):
    """Zoek de kolom met de relatieve hoogteligging."""
    for col in gdf.columns:
        if "hoogteligging" in col.lower() or "hoogteniveau" in col.lower():
            return col
    logger.warning("Geen hoogteliggingkolom gevonden")
    return None


# --- Stap 1: filteren -----------------------------------------------------

def is_bridge_deck(value):
    """Bepaal of een type_overbruggingsdeel een brugdek aanduidt."""
    if pd.isna(value):
        return True
    return str(value).strip().lower() in BRIDGE_DECK_VALUES


def filter_bridge_parts(parts):
    """Houd alleen brugdekken over en geef elk deel een groeps-id.

    Het bridge_group_id is het lokaal_id waarmee de bronhouder bij elkaar
    horende delen aanduidt. Ontbreekt dat, dan krijgt het deel een eigen unieke
    waarde en blijft het op zichzelf staan; de ruimtelijke stappen vangen zulke
    losse delen alsnog samen als ze overlappen.
    """
    if "type_overbruggingsdeel" not in parts.columns:
        raise KeyError("Kolom 'type_overbruggingsdeel' ontbreekt.")

    parts = keep_polygons(parts)
    before = len(parts)
    parts = parts[parts["type_overbruggingsdeel"].map(is_bridge_deck)].reset_index(drop=True)
    logger.info("Gefilterd op dek: %d -> %d delen", before, len(parts))

    lokaal_id = (
        parts["lokaal_id"] if "lokaal_id" in parts.columns
        else pd.Series(index=parts.index, dtype=object)
    )
    parts["bridge_group_id"] = [
        str(v).strip() if not pd.isna(v) and str(v).strip()
        else f"zonder_lokaal_id_{i:06d}"
        for i, v in enumerate(lokaal_id)
    ]

    logger.info("Unieke bridge_group_id: %d", parts["bridge_group_id"].nunique())
    return parts


# --- Stap 2: samenvoegen per lokaal_id ------------------------------------

def dissolve_by_lokaal_id(parts, height_col):
    """Voeg delen met hetzelfde lokaal_id samen tot een brugobject.

    De geometrie is de vereniging van alle delen, maar de attributen komen van
    het grootste deel. Een object dat uit tientallen vlakken bestaat krijgt zo
    een enkele set waarden in plaats van een lange puntkomma-lijst; dat houdt de
    attribuutdata leesbaar en de latere classificatie eenvoudig.

    De hoogteniveaus worden wel als verzameling bewaard (bridge_hoogte_set),
    omdat de merge-stap moet weten welke niveaus er in het object zitten.
    """
    records = []

    for group_id, group in parts.groupby("bridge_group_id"):
        # Het grootste deel bepaalt de attributen.
        grootste = group.loc[group.geometry.area.idxmax()]

        height_min, height_max = (
            min_max_numeric(group[height_col]) if height_col else (None, None)
        )
        height_set = (
            frozenset(
                pd.to_numeric(group[height_col], errors="coerce").dropna().astype(int)
            )
            if height_col else frozenset()
        )

        record = {
            "bridge_group_id": group_id,
            "merge_object_count": 1,
            "component_count": len(group),
            "bridge_hoogte_values": (
                str(grootste[height_col]) if height_col and not pd.isna(grootste[height_col])
                else None
            ),
            "bridge_hoogte_set": height_set,
            "bridge_hoogte_min": height_min,
            "bridge_hoogte_max": height_max,
            "geometry": group.geometry.union_all(),
        }

        # Attributen van het grootste deel.
        for col in SUMMARY_COLUMNS:
            if col in group.columns:
                waarde = grootste[col]
                record[f"{col}_values"] = (
                    str(waarde).strip() if not pd.isna(waarde) and str(waarde).strip()
                    else None
                )
            else:
                record[f"{col}_values"] = None

        records.append(record)

    bridges = keep_polygons(
        gpd.GeoDataFrame(records, geometry="geometry", crs=parts.crs)
    ).reset_index(drop=True)

    logger.info("Samengevoegd per lokaal_id: %d brugobjecten", len(bridges))
    return bridges


# --- Stap 3 en 4: ruimtelijk opschonen ------------------------------------

def overlap_with_smallest(geom_a, geom_b):
    """Geef overlapoppervlak en overlap als fractie van de kleinste.

    Delen door het kleinste oppervlak zorgt dat een klein object dat volledig
    binnen een groot valt een ratio van 1.0 krijgt.
    """
    if geom_a is None or geom_b is None or geom_a.is_empty or geom_b.is_empty:
        return 0.0, 0.0
    area_a, area_b = geom_a.area, geom_b.area
    if area_a <= 0 or area_b <= 0:
        return 0.0, 0.0
    inter = geom_a.intersection(geom_b).area
    if inter <= 0:
        return 0.0, 0.0
    return inter, inter / min(area_a, area_b)


def heights_match(row_a, row_b):
    """Bepaal of twee objecten qua hoogte mogen worden samengevoegd.

    De hoogteniveaus moeten exact overeenkomen. Zo voegt een dek op niveau 1
    niet samen met een weg op maaiveld. Ontbrekende hoogte-informatie blokkeert
    niet: bij twijfel mag er worden samengevoegd, zodat een brug niet in stukken
    valt door een leeg veld.
    """
    a = row_a["bridge_hoogte_set"]
    b = row_b["bridge_hoogte_set"]

    if a is None or b is None or not a or not b:
        return True

    return a == b


def find_overlapping_pairs(bridges, ratio_threshold, respect_height=False):
    """Geef alle objectparen die elkaar meer dan de drempel overlappen.

    De overlap wordt gemeten als fractie van het kleinste object. Bij
    respect_height=True geldt de hoogtecheck alleen in de middenzone: boven
    SPATIAL_MERGE_IGNORE_HEIGHT_RATIO wordt hoogte genegeerd, omdat zulke sterk
    overlappende objecten vrijwel zeker hetzelfde bouwwerk zijn.
    """
    spatial_index = bridges.sindex

    for index, geom in bridges.geometry.items():
        if geom is None or geom.is_empty:
            continue
        for candidate in spatial_index.query(geom, predicate="intersects"):
            if candidate <= index:
                continue

            area, ratio = overlap_with_smallest(geom, bridges.geometry.iloc[candidate])

            if area <= SPATIAL_OVERLAP_AREA_THRESHOLD_M2 or ratio < ratio_threshold:
                continue

            if (
                respect_height
                and ratio < SPATIAL_MERGE_IGNORE_HEIGHT_RATIO
                and not heights_match(bridges.iloc[index], bridges.iloc[candidate])
            ):
                continue

            yield index, candidate, area, ratio


def remove_spatial_duplicates(bridges):
    """Verwijder objecten die vrijwel volledig binnen een ander vallen.

    Valt het kleinste van twee objecten voor 90% of meer binnen het andere, dan
    is het een dubbele aanlevering en verdwijnt het kleinste. Hoogte telt hier
    niet mee: zowel een dubbele aanlevering als een stapeling wil je
    terugbrengen tot een object, om dubbeltelling in de MKI te voorkomen.
    """
    bridges = bridges.reset_index(drop=True)

    pairs = []
    for i, j, area, ratio in find_overlapping_pairs(
        bridges, SPATIAL_DUPLICATE_OVERLAP_RATIO_THRESHOLD, respect_height=False
    ):
        area_i = bridges.geometry.iloc[i].area
        area_j = bridges.geometry.iloc[j].area
        if abs(area_i - area_j) < 1e-6:
            keep, remove = min(i, j), max(i, j)
        elif area_i > area_j:
            keep, remove = i, j
        else:
            keep, remove = j, i
        pairs.append({"keep": keep, "remove": remove, "ratio": ratio})

    pairs.sort(key=lambda p: p["ratio"], reverse=True)

    removed_indices = set()
    for pair in pairs:
        if pair["remove"] in removed_indices or pair["keep"] in removed_indices:
            continue
        removed_indices.add(pair["remove"])

    removed = bridges.loc[sorted(removed_indices)].copy()
    remaining = bridges.drop(index=sorted(removed_indices)).reset_index(drop=True)

    logger.info(
        "Duplicaten verwijderd: %d (%d -> %d)",
        len(removed), len(bridges), len(remaining),
    )
    return remaining, removed.reset_index(drop=True)


def cluster_overlapping(bridges):
    """Geef per object een clusternummer; overlappende objecten delen er een.

    Union-find, zodat ketens meegaan: overlapt A met B en B met C, dan komen ze
    alle drie in een cluster. Met de merge-drempel op 50% moet die overlap fors
    zijn, wat de ketens kort houdt.
    """
    parent = list(range(len(bridges)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, j, _, _ in find_overlapping_pairs(
        bridges, SPATIAL_MERGE_OVERLAP_RATIO_THRESHOLD, respect_height=True
    ):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    return [find(i) for i in range(len(bridges))]


def merge_overlapping(bridges):
    """Voeg objecten samen waarvan overlap en hoogte het toelaten.

    De attributen komen van het grootste object in het cluster, in lijn met hoe
    het samenvoegen per lokaal_id werkt.
    """
    bridges = bridges.reset_index(drop=True)
    bridges["cluster_id"] = cluster_overlapping(bridges)

    sum_cols = ["merge_object_count", "component_count"]
    fixed = sum_cols + [
        "geometry", "cluster_id", "bridge_group_id",
        "bridge_hoogte_min", "bridge_hoogte_max", "bridge_hoogte_set",
    ]
    attribuut_cols = [c for c in bridges.columns if c not in fixed]

    records = []
    for cluster_id, group in bridges.groupby("cluster_id"):
        # Het grootste object bepaalt de attributen.
        grootste = group.loc[group.geometry.area.idxmax()]

        record = {
            "bridge_group_id": (
                group["bridge_group_id"].iloc[0] if len(group) == 1
                else f"samengevoegd_{cluster_id:06d}"
            ),
            "geometry": group.geometry.union_all(),
            "bridge_hoogte_min": min_max_numeric(group["bridge_hoogte_min"])[0],
            "bridge_hoogte_max": min_max_numeric(group["bridge_hoogte_max"])[1],
            "bridge_hoogte_set": frozenset().union(
                *[s for s in group["bridge_hoogte_set"] if s]
            ),
        }
        record.update({c: int(group[c].sum()) for c in sum_cols})
        record.update({c: grootste[c] for c in attribuut_cols})

        records.append(record)

    merged = keep_polygons(
        gpd.GeoDataFrame(records, geometry="geometry", crs=bridges.crs)
    ).reset_index(drop=True)

    merged["is_samengevoegd"] = merged["merge_object_count"] > 1

    logger.info(
        "Samengevoegd: %d -> %d (%d uit meerdere delen)",
        len(bridges), len(merged), int(merged["is_samengevoegd"].sum()),
    )
    return merged


# --- Gemeente toewijzen ---------------------------------------------------

def assign_municipality(bridges, gemeenten):
    """Wijs elke brug toe aan de gemeente met de grootste overlap.

    Stap 02 legde per deel al vast welke gemeenten het raakte; na het
    samenvoegen wordt hier de definitieve keuze gemaakt op grootste oppervlak.
    De boolean deelt_gemeentegrens geeft aan of de brug meer dan een gemeente
    raakte, zodat grensgevallen herkenbaar blijven.
    """
    overlap = gpd.overlay(
        bridges[["bridge_group_id", "geometry"]],
        gemeenten,
        how="intersection",
        keep_geom_type=True,
    )
    if overlap.empty:
        logger.warning("Geen enkele brug overlapt met een gemeente")
        bridges["gekozen_gemeente_naam"] = None
        bridges["gekozen_gemeente_code"] = None
        bridges["deelt_gemeentegrens"] = False
        return bridges

    overlap["overlap_area_m2"] = overlap.geometry.area

    grens = (
        overlap.groupby("bridge_group_id")["binnen_gemeente_naam"]
        .nunique()
        .rename("aantal_gemeenten")
    )

    largest = overlap.loc[
        overlap.groupby("bridge_group_id")["overlap_area_m2"].idxmax(),
        ["bridge_group_id", "binnen_gemeente_naam", "binnen_gemeente_code"],
    ].rename(columns={
        "binnen_gemeente_naam": "gekozen_gemeente_naam",
        "binnen_gemeente_code": "gekozen_gemeente_code",
    })

    largest = largest.merge(grens, on="bridge_group_id", how="left")
    largest["deelt_gemeentegrens"] = largest["aantal_gemeenten"] > 1
    largest = largest.drop(columns=["aantal_gemeenten"])

    logger.info(
        "Gemeente toegewezen; %d bruggen delen een gemeentegrens",
        int(largest["deelt_gemeentegrens"].sum()),
    )
    return bridges.merge(largest, on="bridge_group_id", how="left")


# --- Afmetingen -----------------------------------------------------------

def rectangle_dimensions(geom):
    """Schat lengte en breedte via de kleinste omhullende rechthoek."""
    empty = pd.Series({"bbox_lengte_m": None, "bbox_breedte_m": None})
    if geom is None or geom.is_empty:
        return empty
    rect = geom.minimum_rotated_rectangle
    if rect.geom_type != "Polygon":
        return empty
    coords = list(rect.exterior.coords)
    if len(coords) < 5:
        return empty
    sides = [math.dist(coords[i], coords[i + 1]) for i in range(4)]
    return pd.Series({
        "bbox_lengte_m": round(max(sides), 2),
        "bbox_breedte_m": round(min(sides), 2),
    })


def add_dimensions(bridges):
    """Voeg oppervlakte, bbox-afmetingen en de oppervlakte-breedte toe.

    De breedte voor classificatie is oppervlakte gedeeld door lengte, niet de
    korte zijde van de omhullende rechthoek. Die eerste middelt over de hele
    brug en is daarmee robuuster.
    """
    bridges = bridges.copy()
    bridges["area_m2"] = bridges.geometry.area.round(2)
    bridges = pd.concat([bridges, bridges.geometry.apply(rectangle_dimensions)], axis=1)

    lengte = pd.to_numeric(bridges["bbox_lengte_m"], errors="coerce")
    bridges["oppervlakte_breedte_m"] = (
        (bridges["area_m2"] / lengte).where(lengte > 0).round(2)
    )

    return gpd.GeoDataFrame(bridges, geometry="geometry", crs=bridges.crs)


# --- Output ---------------------------------------------------------------

def select_output_columns(bridges):
    """Houd alleen de kolommen uit OUTPUT_COLUMNS over, in die volgorde."""
    existing = [c for c in OUTPUT_COLUMNS if c in bridges.columns]
    missing = [c for c in OUTPUT_COLUMNS if c not in bridges.columns]
    if missing:
        logger.warning("Verwachte kolom ontbreekt in de output: %s", ", ".join(missing))
    return gpd.GeoDataFrame(bridges[existing], geometry="geometry", crs=bridges.crs)


def main():
    setup_logging()

    source_gpkg = get_gpkg_path(SOURCE_SCRIPT)
    if not source_gpkg.exists():
        raise FileNotFoundError(
            f"Clip-GeoPackage niet gevonden: {source_gpkg}\nDraai eerst 02_clip.py."
        )

    output_gpkg = get_gpkg_path(SCRIPT_NAME)
    output_gpkg.unlink(missing_ok=True)

    gemeenten = read_layer(source_gpkg, "gemeentegebied_selected")
    parts = read_layer(source_gpkg, BRIDGE_LAYER, make_valid=True)

    height_col = find_height_column(parts)

    parts = filter_bridge_parts(parts)
    bridges = dissolve_by_lokaal_id(parts, height_col)
    bridges, removed = remove_spatial_duplicates(bridges)
    bridges = merge_overlapping(bridges)
    bridges = assign_municipality(bridges, gemeenten)
    bridges = add_dimensions(bridges)
    bridges = select_output_columns(bridges)

    save_layer(bridges, output_gpkg, "brugobjecten", script_name=SCRIPT_NAME)
    save_layer(removed, output_gpkg, "verwijderde_duplicaten",
               script_name=SCRIPT_NAME, write_excel=False)

    logger.info("\nStap 03 klaar.")
    logger.info("GeoPackage: %s", output_gpkg)


if __name__ == "__main__":
    main()