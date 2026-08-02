"""Stap 05: brugobjecten classificeren met de beslisboom en typering.

Deze stap neemt de ruimtelijke metingen uit stap 04 en beslist per object twee
dingen: is het een brug die we meenemen, en zo ja, welk profiel krijgt het. De
zware ruimtelijke berekening zit in stap 04; hier staat alleen de logica, zodat
de regels aangepast kunnen worden zonder het dure meetwerk over te doen.

De beslisboom, in volgorde (de eerste die past, beslist):

    1. te klein, te smal of te kort            -> geen brug (ruis)
    2. gebouwoverlap >= 66%                    -> geen brug (complex/station)
    3. hoort_bij_typeoverbrugging gevuld       -> brug (sterkste BGT-signaal)
    4. brugnaam gevuld, of fysiekvoorkomen
       bevat "brug"                            -> brug
    5. fysiekvoorkomen bevat "overkluisd"      -> geen brug
    6. water eronder                           -> brug
       anders weg met hoogteverschil           -> brug (viaduct)
       anders spoor met "brug"                 -> brug
       anders                                  -> geen brug

Voor elke brug worden context (water/viaduct/overig) en verkeerstype
(auto/langzaam) bepaald, en die leiden samen met de breedte tot een profiel.

De breedteklasse komt bij voorkeur uit het aantal rijstroken op dekniveau, maar
alleen als stap 04 die telling plausibel vond: past het aantal stroken niet bij
de gemeten breedte, dan valt de schatting terug op de breedte zelf. Zo krijgt
een fietsbrug over een snelweg niet de rijstroken van de weg eronder.

    python 05_classify.py
"""

import geopandas as gpd
import pandas as pd

import common
from common import (
    get_classification_settings,
    get_gpkg_path,
    parse_numeric_value,
    read_layer,
    save_layer,
    setup_logging,
)


# --- Configuratie ---------------------------------------------------------

SCRIPT_NAME = "05_classify"
SOURCE_SCRIPT = "04_spatial_relations"
SOURCE_LAYER = "brugobjecten_relaties"

# Drempels van de beslisboom.
MIN_AREA_M2 = 4.0
MIN_LENGTE_M = 1.0
MIN_BREEDTE_M = 1.0
GEBOUW_OVERLAP_DREMPEL = 0.66
WEGVLAK_OVERLAP_DREMPEL = 0.25
VIADUCT_MIN_NIVEAUS = 2

# Kolommen met fysiekvoorkomen-waarden van meetellende lijnen. De check op
# "brug" en "overkluisd" gebeurt als substring over al deze kolommen samen,
# omdat de waarden samengesteld zijn (op vast deel van brug|op knooppuntverbinding).
FYSIEKVOORKOMEN_COLUMNS = [
    "weghartlijn_fysiekvoorkomen_values",
    "weglijn_fysiekvoorkomen_values",
]
BRUGNAAM_COLUMNS = [
    "weghartlijn_brugnaam_values",
    "weglijn_brugnaam_values",
]
HOOFDVERKEER_COLUMNS = [
    "weghartlijn_hoofdverkeersgebruik_values",
    "weglijn_hoofdverkeersgebruik_values",
]

# Hoofdverkeersgebruik-waarden die op gemotoriseerd verkeer wijzen. Staat een
# van deze op de meetellende wegen, dan is het een autobrug, ongeacht of er ook
# fiets- of voetgangersverkeer bij zit.
AUTO_VERKEER = {"gemengd verkeer", "snelverkeer", "busverkeer"}

# Overlappende bruggen met dezelfde naam boven deze drempel: de kleinste valt
# weg. Klein, want het gaat om objecten die duidelijk hetzelfde bouwwerk zijn
# maar in stap 03 net niet werden samengevoegd.
NAAM_DEDUP_OVERLAP_M2 = 1.0

logger = common.logger


# --- Naam-deduplicatie ----------------------------------------------------

def bridge_names(row):
    """Geef de set brugnamen van een object, uit hart- en weglijn samen."""
    names = set()
    for col in BRUGNAAM_COLUMNS:
        value = row.get(col)
        if not pd.isna(value) and str(value).strip():
            names.update(n.strip().lower() for n in str(value).split(";") if n.strip())
    return names


def deduplicate_by_name(bridges):
    """Verwijder overlappende bruggen die dezelfde naam dragen.

    Soms blijft een viaduct als twee losse objecten staan omdat ze in stap 03
    net onder de samenvoegdrempel bleven. Dragen ze dezelfde benoemde brugnaam
    en overlappen ze meer dan de drempel, dan zijn het zeker hetzelfde bouwwerk:
    de grootste blijft staan, de kleinere valt weg.

    De regel grijpt alleen in bij een gevulde naam. Naamloze objecten worden
    nooit op deze grond samengevoegd.
    """
    bridges = bridges.reset_index(drop=True)

    named = bridges[bridges.apply(lambda r: len(bridge_names(r)) > 0, axis=1)].copy()
    if named.empty:
        logger.info("Naam-deduplicatie: geen benoemde bruggen")
        return bridges

    name_sets = {idx: bridge_names(row) for idx, row in named.iterrows()}
    areas = {idx: parse_numeric_value(named.loc[idx, "area_m2"]) or 0.0 for idx in named.index}

    spatial_index = named.sindex
    te_verwijderen = set()

    for idx, geom in named.geometry.items():
        if idx in te_verwijderen or geom is None or geom.is_empty:
            continue
        for other in spatial_index.query(geom, predicate="intersects"):
            other_idx = named.index[other]
            if other_idx <= idx or other_idx in te_verwijderen:
                continue

            if not (name_sets[idx] & name_sets[other_idx]):
                continue

            overlap = geom.intersection(named.geometry.loc[other_idx]).area
            if overlap <= NAAM_DEDUP_OVERLAP_M2:
                continue

            kleinste = idx if areas[idx] < areas[other_idx] else other_idx
            te_verwijderen.add(kleinste)

    remaining = bridges.drop(index=sorted(te_verwijderen)).reset_index(drop=True)

    logger.info(
        "Naam-deduplicatie: %d overlappende gelijknamige bruggen verwijderd (%d -> %d)",
        len(te_verwijderen), len(bridges), len(remaining),
    )
    return remaining


# --- Hulpfuncties voor de regels ------------------------------------------

def any_filled(row, columns):
    """Bepaal of minstens een van de kolommen een niet-lege waarde heeft."""
    for col in columns:
        value = row.get(col)
        if not pd.isna(value) and str(value).strip():
            return True
    return False


def combined_text(row, columns):
    """Voeg de waarden van meerdere kolommen samen tot een kleine-letter string.

    Gebruikt voor de substring-checks op "brug" en "overkluisd": door alle
    fysiekvoorkomen-kolommen samen te voegen hoeft de check maar een keer te
    gebeuren, en vangt hij ook samengestelde waarden.
    """
    parts = []
    for col in columns:
        value = row.get(col)
        if not pd.isna(value) and str(value).strip():
            parts.append(str(value).lower())
    return " ".join(parts)


# --- De beslisboom --------------------------------------------------------

def classify_is_bridge(row):
    """Beslis of een object een brug is, en geef de reden terug."""
    area = parse_numeric_value(row.get("area_m2")) or 0.0
    lengte = parse_numeric_value(row.get("bbox_lengte_m")) or 0.0
    breedte = parse_numeric_value(row.get("oppervlakte_breedte_m")) or 0.0
    gebouw_overlap = parse_numeric_value(row.get("gebouw_overlap_fractie")) or 0.0

    # 1. Te klein, te smal of te kort. Een flinterdun of heel kort object kan
    #    geen brug zijn, ook niet als het toevallig 4 m2 haalt.
    if area < MIN_AREA_M2:
        return False, f"te klein (< {MIN_AREA_M2:g} m2)"
    if breedte < MIN_BREEDTE_M:
        return False, f"te smal (< {MIN_BREEDTE_M:g} m breed)"
    if lengte < MIN_LENGTE_M:
        return False, f"te kort (< {MIN_LENGTE_M:g} m lang)"

    # 2. Complex object / station.
    if gebouw_overlap >= GEBOUW_OVERLAP_DREMPEL:
        return False, f"gebouwoverlap >= {GEBOUW_OVERLAP_DREMPEL:.0%}"

    # 3. Sterkste BGT-signaal: hoort bij een benoemd overbruggingsobject.
    if any_filled(row, ["hoort_bij_typeoverbrugging_values"]):
        return True, "hoort_bij_typeoverbrugging gevuld"

    # 4. TOP10NL-insluiting: brugnaam of fysiekvoorkomen "brug".
    fysiek = combined_text(row, FYSIEKVOORKOMEN_COLUMNS)
    if any_filled(row, BRUGNAAM_COLUMNS):
        return True, "brugnaam gevuld"
    if "brug" in fysiek:
        return True, "fysiekvoorkomen bevat 'brug'"

    # 5. Uitsluiting overkluisd (alleen nu 3 en 4 niet vuurden).
    if "overkluisd" in fysiek:
        return False, "fysiekvoorkomen bevat 'overkluisd'"

    # 6. Water alleen is genoeg: een bruggetje over water is een brug, ook als
    #    er geen weg in TOP10NL overheen loopt (kleine bruggen ontbreken daar
    #    vaak). Ligt er geen water, dan is een weg met hoogteverschil nodig
    #    (viaduct), of een spoorbrug.
    if bool(row.get("kruist_water")):
        return True, "over water"

    wegvlak_overlap = parse_numeric_value(row.get("wegvlak_overlap_fractie")) or 0.0
    weg_aanwezig = (
        wegvlak_overlap >= WEGVLAK_OVERLAP_DREMPEL
        or bool(row.get("kruist_weghartlijn"))
        or bool(row.get("kruist_weglijn"))
    )
    niveaus = int(parse_numeric_value(row.get("aantal_hoogteniveaus")) or 0)

    if weg_aanwezig and niveaus >= VIADUCT_MIN_NIVEAUS:
        return True, "weg met hoogteverschil (viaduct)"

    spoor_fysiek = combined_text(row, ["spoor_fysiekvoorkomen_values"])
    if "brug" in spoor_fysiek:
        return True, "spoorbrug (fysiekvoorkomen bevat 'brug')"

    return False, "geen water/hoogteverschil/spoor"


# --- Context en verkeerstype ----------------------------------------------

def determine_context(row):
    """Bepaal de context: over water, viaduct, of overig.

    Water wint van hoogteverschil: een object dat zowel water als kruisende
    wegen op verschillende niveaus heeft, geldt als brug over water.
    """
    if bool(row.get("kruist_water")):
        return "brug_over_water"
    niveaus = int(parse_numeric_value(row.get("aantal_hoogteniveaus")) or 0)
    if niveaus >= VIADUCT_MIN_NIVEAUS:
        return "viaduct"
    return "brug_overig"


def determine_traffic_class(row):
    """Bepaal of het een auto- of langzaam-verkeersbrug is.

    Gemotoriseerd verkeer wint: staat gemengd verkeer, snelverkeer of
    busverkeer op een van de meetellende wegen, dan is het een autobrug, ook als
    er daarnaast fiets- of voetgangersverkeer is. Alleen fiets- en
    voetgangersverkeer maakt een langzaam-verkeersbrug.
    """
    text = combined_text(row, HOOFDVERKEER_COLUMNS)
    if not text:
        return None
    if any(v in text for v in AUTO_VERKEER):
        return "auto"
    if "fietsers" in text or "voetgangers" in text:
        return "langzaam"
    return "auto"


# --- Breedteklasse voor autobruggen ---------------------------------------

def determine_width_class(row, settings):
    """Bepaal de rijstrookklasse (1x2, 2x2, 2x3) van een autobrug.

    Bij voorkeur uit het aantal rijstroken op dekniveau, maar alleen als stap 04
    die telling plausibel vond: past het aantal stroken niet bij de gemeten
    breedte (ratio onder de drempel), dan is de telling vervuild door een weg
    die er niet bij hoort, en valt de schatting terug op de breedte uit
    oppervlakte gedeeld door lengte.
    """
    bruikbaar = bool(row.get("rijstroken_bruikbaar"))
    rijstroken = parse_numeric_value(row.get("rijstroken_dekniveau")) if bruikbaar else None

    if rijstroken is not None:
        if rijstroken <= 2:
            return "1x2"
        if rijstroken <= 4:
            return "2x2"
        return "2x3"

    # Terugval op de gemeten breedte.
    breedte = parse_numeric_value(row.get("oppervlakte_breedte_m"))
    grenzen = settings["breedte_grenzen"]
    if breedte is None:
        return "1x2"
    if breedte <= grenzen["1x2"]:
        return "1x2"
    if breedte <= grenzen["2x2"]:
        return "2x2"
    return "2x3"


# --- Profiel samenstellen -------------------------------------------------

def build_profile(context, traffic_class, width_class):
    """Stel de profielnaam samen uit context, verkeersklasse en breedte.

    Langzaam-verkeersbruggen worden fietsbruggen, met de context erin.
    Autobruggen krijgen viaduct of brug plus de breedteklasse. Een brug zonder
    duidelijke context (overig) wordt als brug behandeld, want dat is het meest
    voorkomende type.
    """
    if traffic_class == "langzaam":
        if context == "brug_over_water":
            return "fietsbrug_over_water"
        return "fietsbrug_over_weg"

    if context == "viaduct":
        return f"viaduct_{width_class}"
    return f"brug_{width_class}"


# --- Hoofdverwerking ------------------------------------------------------

def classify(bridges, settings):
    """Pas de beslisboom en typering toe op alle objecten."""
    bridges = bridges.copy()

    resultaten = bridges.apply(classify_is_bridge, axis=1)
    bridges["is_brug"] = [r[0] for r in resultaten]
    bridges["classificatie_reden"] = [r[1] for r in resultaten]

    logger.info(
        "Bruggen: %d van %d (%d uitgesloten)",
        int(bridges["is_brug"].sum()), len(bridges),
        int((~bridges["is_brug"]).sum()),
    )
    logger.info(
        "\nRedenen:\n%s",
        bridges["classificatie_reden"].value_counts().to_string(),
    )

    is_brug = bridges["is_brug"]

    bridges["context"] = None
    bridges["verkeersklasse"] = None
    bridges["breedteklasse"] = None
    bridges["profiel"] = None
    bridges["kruist_spoor_relevant"] = False

    bridges.loc[is_brug, "context"] = bridges[is_brug].apply(determine_context, axis=1)

    # Ontbrekende verkeersklasse (geen weg gekruist) telt als auto, want dan
    # bepaalt de breedte het type.
    verkeer = bridges[is_brug].apply(determine_traffic_class, axis=1).fillna("auto")
    bridges.loc[is_brug, "verkeersklasse"] = verkeer

    auto_mask = is_brug & (bridges["verkeersklasse"] == "auto")
    bridges.loc[auto_mask, "breedteklasse"] = bridges[auto_mask].apply(
        lambda r: determine_width_class(r, settings), axis=1
    )

    bridges.loc[is_brug, "profiel"] = bridges[is_brug].apply(
        lambda r: build_profile(r["context"], r["verkeersklasse"], r["breedteklasse"]),
        axis=1,
    )

    spoor_brug = (
        bridges["spoor_fysiekvoorkomen_values"].fillna("").str.lower().str.contains("brug")
    )
    bridges["kruist_spoor_relevant"] = is_brug & spoor_brug

    # Hoe vaak de rijstrooktelling is verworpen, ter controle op de
    # breedteclassificatie.
    if "rijstroken_bruikbaar" in bridges.columns:
        auto_bruggen = bridges[auto_mask]
        op_breedte = int((~auto_bruggen["rijstroken_bruikbaar"].astype(bool)).sum())
        logger.info(
            "\nBreedteklasse: %d autobruggen op rijstroken, %d op gemeten breedte",
            len(auto_bruggen) - op_breedte, op_breedte,
        )

    return bridges


def main():
    setup_logging()

    source_gpkg = get_gpkg_path(SOURCE_SCRIPT)
    if not source_gpkg.exists():
        raise FileNotFoundError(
            f"GeoPackage van stap 04 ontbreekt: {source_gpkg}\nDraai eerst stap 04."
        )

    output_gpkg = get_gpkg_path(SCRIPT_NAME)
    output_gpkg.unlink(missing_ok=True)

    settings = get_classification_settings()
    bridges = read_layer(source_gpkg, SOURCE_LAYER)
    bridges = deduplicate_by_name(bridges)
    bridges = classify(bridges, settings)

    brug = bridges[bridges["is_brug"]].copy()
    geen_brug = bridges[~bridges["is_brug"]].copy()

    save_layer(brug, output_gpkg, "bruggen", script_name=SCRIPT_NAME)
    save_layer(geen_brug, output_gpkg, "geen_brug", script_name=SCRIPT_NAME)

    logger.info("\nProfielverdeling:\n%s", brug["profiel"].value_counts().to_string())
    logger.info("\nStap 05 klaar.")
    logger.info("GeoPackage: %s", output_gpkg)


if __name__ == "__main__":
    main()