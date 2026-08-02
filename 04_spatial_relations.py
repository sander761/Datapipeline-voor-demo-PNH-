"""Stap 04: ruimtelijke relaties van brugobjecten meten.

Deze stap neemt geen enkele beslissing over wat een brug is; het meet alleen de
signalen die stap 05 nodig heeft om dat te beslissen. De scheiding is bewust:
het ruimtelijke rekenwerk is zwaar en verandert zelden, terwijl de beslisregels
in stap 05 juist vaak worden bijgesteld.

Per brugobject worden de volgende relaties bepaald, elk als kolom:

    wegvlakken   overlapfractie met TOP10NL-wegvlakken, en hoeveel losse
                 wegvlakken de brug kruisen
    weglijnen    of weglijn en weghartlijn substantieel over de brug lopen, en
                 hun attributen. Een lijn telt alleen mee als een voldoende deel
                 van zijn lengte binnen het brugvlak valt; zo vallen segmenten
                 af die de brug alleen in een hoekje raken.
    rijstroken   het aantal rijstroken op het hoogste hoogteniveau, want dat is
                 het brugdek zelf. Rijbanen op dat niveau worden opgeteld, wegen
                 op lagere niveaus (die de brug overspant) tellen niet mee. De
                 telling wordt getoetst aan de gemeten breedte: past hij niet,
                 dan wordt hij als onbruikbaar gemarkeerd.
    hoogte       op hoeveel verschillende niveaus de kruisende wegen liggen
                 (viaduct-signaal)
    gebouwen     overlapfractie met TOP10NL-gebouwvlakken (voor het uitsluiten
                 van stationsdekken en overkluizingen)
    water        of een BGT-waterdeel door de brug snijdt
    spoor        of een spoorbaandeel de brug kruist, met fysiekvoorkomen en
                 typespoorbaan

De invoer komt uit stap 02 (de geclipte context-lagen) en stap 03 (de
brugobjecten).

    python 04_spatial_relations.py
"""

import geopandas as gpd
import pandas as pd

import common
from common import (
    get_gpkg_path,
    keep_polygons,
    read_layer,
    save_layer,
    setup_logging,
    summarize_unique_values,
)


# --- Configuratie ---------------------------------------------------------

SCRIPT_NAME = "04_spatial_relations"
BRIDGE_SCRIPT = "03_build_bridges"
CONTEXT_SCRIPT = "02_clip"

BRIDGE_LAYER = "brugobjecten"

# Context-lagen uit stap 02. De sleutel is de rol in dit script, de waarde de
# laagnaam in de GeoPackage van stap 02.
LAYERS = {
    "wegvlak": "top10nl_wegdeel_vlak",
    "weglijn": "top10nl_wegdeel_lijn",
    "weghartlijn": "top10nl_wegdeel_hartlijn",
    "spoor": "top10nl_spoorbaandeel_lijn",
    "gebouw": "top10nl_gebouw_vlak",
    "water": "bgt_waterdeel",
}

# Attributen die per laag van de meetellende lijnen worden overgenomen.
WEGHARTLIJN_ATTRS = [
    "fysiekvoorkomen", "brugnaam", "hoofdverkeersgebruik",
    "aantalrijstroken", "typeweg", "verhardingstype",
]
WEGLIJN_ATTRS = ["fysiekvoorkomen", "brugnaam", "hoofdverkeersgebruik", "typeweg"]
SPOOR_ATTRS = ["fysiekvoorkomen", "typespoorbaan"]

# Een lijn telt alleen mee als dit deel van zijn lengte binnen de brug valt.
# Zo vallen segmenten af die de brug alleen in een hoekje raken maar er niet
# overheen lopen; hun attributen horen niet bij de brug.
LIJN_OVERLAP_MIN_FRACTIE = 0.85

# Plausibiliteitscheck op de strokentelling. Een rijstrook is ongeveer drie
# meter breed, dus een brug moet minstens rijstroken x 3 meter breed zijn. De
# verhouding gemeten / verwacht ligt normaal boven de 1, want er komen bermen,
# leuningen en fietspaden naast de rijbaan. Ligt hij onder deze grens, dan past
# de telling fysiek niet bij de brug en is hij vervuild.
METER_PER_RIJSTROOK = 3.0
RIJSTROOK_BREEDTE_RATIO_MIN = 1.2

# Een overlap kleiner dan dit telt als ruis bij het bepalen of water door een
# brug snijdt.
INTERSECTION_AREA_THRESHOLD_M2 = 1.0

# Harde bovengrens op het aantal rijstroken. De breedste snelweg in Nederland
# heeft veertien stroken per rijbaan; twee rijbanen naast elkaar op een dek
# geeft achtentwintig. Alles daarboven is een telfout, en dan valt de
# classificatie terug op de gemeten breedte.
RIJSTROKEN_MAX = 30

logger = common.logger


# --- Overlapfracties (vlak-op-vlak) ---------------------------------------

def add_area_overlap_fraction(bridges, other, prefix):
    """Bereken per brug welke fractie van zijn oppervlak overlapt met een laag.

    Wordt gebruikt voor wegvlakken en gebouwen. De overlay knipt de bruggen op
    de andere laag; per brug wordt het overlappende oppervlak gesommeerd en
    gedeeld door het brugoppervlak.

    Een brug zonder overlap krijgt fractie 0 en telling 0, niet NaN, zodat de
    beslisboom in stap 05 er zonder controle mee kan rekenen.
    """
    fractie_col = f"{prefix}_overlap_fractie"
    count_col = f"aantal_{prefix}"

    other = keep_polygons(other)
    if other.empty:
        bridges[fractie_col] = 0.0
        bridges[count_col] = 0
        logger.warning("Laag voor %s is leeg; overlap op 0 gezet", prefix)
        return bridges

    overlay = gpd.overlay(
        bridges[["bridge_group_id", "area_m2", "geometry"]],
        other[["geometry"]],
        how="intersection",
        keep_geom_type=True,
    )
    overlay["overlap_area"] = overlay.geometry.area

    per_bridge = overlay.groupby("bridge_group_id").agg(
        overlap_area=("overlap_area", "sum"),
        aantal=("overlap_area", "count"),
    )

    bridges = bridges.merge(per_bridge, on="bridge_group_id", how="left")
    bridges["overlap_area"] = bridges["overlap_area"].fillna(0.0)
    bridges["aantal"] = bridges["aantal"].fillna(0).astype(int)

    bridges[fractie_col] = (bridges["overlap_area"] / bridges["area_m2"]).round(3)
    bridges[count_col] = bridges["aantal"]
    bridges = bridges.drop(columns=["overlap_area", "aantal"])

    logger.info(
        "%s: %d bruggen met overlap",
        prefix, int((bridges[fractie_col] > 0).sum()),
    )
    return bridges


# --- Kruisende lijnen (attributen overnemen) ------------------------------

def add_crossing_line_attributes(bridges, lines, prefix, attr_columns):
    """Bepaal per brug welke lijnen er substantieel overheen lopen.

    Een lijn telt alleen mee als minstens LIJN_OVERLAP_MIN_FRACTIE van zijn
    lengte binnen het brugvlak valt. Zo vallen segmenten af die de brug alleen
    in een hoekje raken: die lopen er niet overheen, en hun attributen horen
    dus niet bij de brug.
    """
    kruist_col = f"kruist_{prefix}"

    lines = lines[lines.geometry.notna() & ~lines.geometry.is_empty].copy()
    present = [c for c in attr_columns if c in lines.columns]
    missing = [c for c in attr_columns if c not in lines.columns]
    if missing:
        logger.warning("Kolommen ontbreken in %s: %s", prefix, ", ".join(missing))

    def geen_lijnen():
        bridges[kruist_col] = False
        for col in attr_columns:
            bridges[f"{prefix}_{col}_values"] = None
        return bridges

    if lines.empty:
        logger.warning("Laag voor %s is leeg", prefix)
        return geen_lijnen()

    # De lijnlengte per segment bewaren, om straks de fractie te bepalen.
    lines = lines[present + ["geometry"]].copy()
    lines["_lijn_id"] = range(len(lines))
    lines["_lijn_lengte"] = lines.geometry.length

    # De lijnen knippen op de brugvlakken: wat overblijft is het deel binnen de
    # brug, en daarvan meten we de lengte.
    geknipt = gpd.overlay(
        lines,
        bridges[["bridge_group_id", "geometry"]],
        how="intersection",
        keep_geom_type=True,
    )

    if geknipt.empty:
        logger.warning("Geen lijnen binnen de bruggen voor %s", prefix)
        return geen_lijnen()

    geknipt["_binnen_lengte"] = geknipt.geometry.length

    # Een lijn kan door meerdere losse stukken van dezelfde brug lopen; die
    # stukken bij elkaar optellen voor de fractie.
    per_paar = (
        geknipt.groupby(["bridge_group_id", "_lijn_id"])
        .agg(binnen=("_binnen_lengte", "sum"), totaal=("_lijn_lengte", "first"))
        .reset_index()
    )
    per_paar["_fractie"] = per_paar["binnen"] / per_paar["totaal"]

    voldoende = per_paar[per_paar["_fractie"] >= LIJN_OVERLAP_MIN_FRACTIE]

    afgevallen = len(per_paar) - len(voldoende)
    if afgevallen:
        logger.info(
            "%s: %d lijn-brugcombinaties vallen af (< %.0f%% van de lijn op de brug)",
            prefix, afgevallen, LIJN_OVERLAP_MIN_FRACTIE * 100,
        )

    if voldoende.empty:
        return geen_lijnen()

    # De attributen terughalen bij de overgebleven combinaties.
    meetellend = voldoende.merge(
        lines[present + ["_lijn_id"]], on="_lijn_id", how="left"
    )

    kruisende_ids = set(meetellend["bridge_group_id"])
    bridges[kruist_col] = bridges["bridge_group_id"].isin(kruisende_ids)

    for col in present:
        samenvatting = (
            meetellend.groupby("bridge_group_id")[col]
            .agg(summarize_unique_values)
            .rename(f"{prefix}_{col}_values")
        )
        bridges = bridges.merge(samenvatting, on="bridge_group_id", how="left")

    for col in missing:
        bridges[f"{prefix}_{col}_values"] = None

    logger.info("%s: %d bruggen met een meetellende lijn", prefix, len(kruisende_ids))
    return bridges


# --- Rijstroken op dekniveau ----------------------------------------------

def add_rijstroken_op_dekniveau(bridges, weghartlijn):
    """Bepaal het aantal rijstroken op het brugdek, en toets of dat plausibel is.

    Een brug kan meerdere hartlijnen kruisen: rijbanen naast elkaar op het dek,
    en de wegen die de brug overspant. Het hoogste hoogteniveau is het dek zelf;
    lagere niveaus zijn wat eronder doorloopt. Alleen het dek bepaalt de
    breedte, dus de rijstroken van het hoogste niveau tellen. Rijbanen op dat
    niveau liggen naast elkaar en worden opgeteld.

    Zo krijgt een fietsbrug over een snelweg de smalle fietspad-breedte in plaats
    van de tien rijstroken van de weg eronder.

    De telling wordt daarna getoetst aan de gemeten breedte: een rijstrook is
    ongeveer drie meter, dus de brug moet breed genoeg zijn voor het aantal
    stroken. De ratio gemeten / verwacht komt als kolom mee, plus een boolean
    die aangeeft of de telling bruikbaar is voor de classificatie.
    """
    def geen_telling():
        bridges["rijstroken_dekniveau"] = None
        bridges["rijstroken_per_niveau_values"] = None
        bridges["rijstrook_breedte_ratio"] = None
        bridges["rijstroken_bruikbaar"] = False
        return bridges

    nodig = ["hoogteniveau", "aantalrijstroken"]
    ontbreekt = [c for c in nodig if c not in weghartlijn.columns]
    if ontbreekt:
        logger.warning("Kolommen ontbreken voor rijstrooktelling: %s", ", ".join(ontbreekt))
        return geen_telling()

    lijnen = weghartlijn[
        weghartlijn.geometry.notna() & ~weghartlijn.geometry.is_empty
    ][nodig + ["geometry"]].copy()
    lijnen["_lijn_id"] = range(len(lijnen))
    lijnen["_lijn_lengte"] = lijnen.geometry.length

    geknipt = gpd.overlay(
        lijnen,
        bridges[["bridge_group_id", "geometry"]],
        how="intersection",
        keep_geom_type=True,
    )

    if geknipt.empty:
        logger.warning("Geen hartlijnen binnen de bruggen")
        return geen_telling()

    geknipt["_binnen_lengte"] = geknipt.geometry.length

    per_paar = (
        geknipt.groupby(["bridge_group_id", "_lijn_id"])
        .agg(
            binnen=("_binnen_lengte", "sum"),
            totaal=("_lijn_lengte", "first"),
            niveau=("hoogteniveau", "first"),
            stroken=("aantalrijstroken", "first"),
        )
        .reset_index()
    )
    per_paar["_fractie"] = per_paar["binnen"] / per_paar["totaal"]
    per_paar = per_paar[per_paar["_fractie"] >= LIJN_OVERLAP_MIN_FRACTIE]

    per_paar["_niveau"] = pd.to_numeric(per_paar["niveau"], errors="coerce")
    per_paar["_stroken"] = pd.to_numeric(per_paar["stroken"], errors="coerce")
    per_paar = per_paar.dropna(subset=["_niveau", "_stroken"])

    if per_paar.empty:
        logger.warning("Geen bruikbare hoogteniveau/rijstrook-waarden gevonden")
        return geen_telling()

    # Rijstroken optellen per niveau.
    per_niveau = (
        per_paar.groupby(["bridge_group_id", "_niveau"])["_stroken"].sum().reset_index()
    )

    # Het hoogste niveau is het brugdek; dat bepaalt de breedte.
    dekniveau = (
        per_niveau.loc[per_niveau.groupby("bridge_group_id")["_niveau"].idxmax()]
        .set_index("bridge_group_id")["_stroken"]
        .rename("rijstroken_dekniveau")
    )

    leesbaar = (
        per_niveau.assign(
            _tekst=lambda d: "niveau " + d["_niveau"].astype(int).astype(str)
                             + ": " + d["_stroken"].astype(int).astype(str)
        )
        .groupby("bridge_group_id")["_tekst"]
        .agg("; ".join)
        .rename("rijstroken_per_niveau_values")
    )

    bridges = bridges.merge(dekniveau, on="bridge_group_id", how="left")
    bridges = bridges.merge(leesbaar, on="bridge_group_id", how="left")

      # Plausibiliteitscheck: past het aantal stroken bij de gemeten breedte, en
    # blijft het onder de fysieke bovengrens?
    breedte = pd.to_numeric(bridges["oppervlakte_breedte_m"], errors="coerce")
    stroken = pd.to_numeric(bridges["rijstroken_dekniveau"], errors="coerce")

    verwachte_breedte = stroken * METER_PER_RIJSTROOK
    bridges["rijstrook_breedte_ratio"] = (
        (breedte / verwachte_breedte).where(verwachte_breedte > 0).round(2)
    )

    # Bruikbaar als de ratio ruim genoeg is en het aantal stroken fysiek kan.
    bridges["rijstroken_bruikbaar"] = (
        bridges["rijstrook_breedte_ratio"].notna()
        & (bridges["rijstrook_breedte_ratio"] >= RIJSTROOK_BREEDTE_RATIO_MIN)
        & (stroken <= RIJSTROKEN_MAX)
    )

    heeft_telling = bridges["rijstroken_dekniveau"].notna()
    verworpen_ratio = int(
        (heeft_telling & (bridges["rijstrook_breedte_ratio"] < RIJSTROOK_BREEDTE_RATIO_MIN)).sum()
    )
    verworpen_max = int((heeft_telling & (stroken > RIJSTROKEN_MAX)).sum())

    logger.info(
        "Rijstroken op dekniveau: %d bruggen met telling, %d verworpen op ratio "
        "(< %.2f), %d verworpen op bovengrens (> %d stroken)",
        int(heeft_telling.sum()), verworpen_ratio,
        RIJSTROOK_BREEDTE_RATIO_MIN, verworpen_max, RIJSTROKEN_MAX,
    )
    return bridges


# --- Hoogteniveaus uit de weglijnen ---------------------------------------

def add_road_height_levels(bridges, weglijn, weghartlijn):
    """Bepaal per brug op hoeveel verschillende hoogteniveaus wegen liggen.

    Liggen er onder een brug wegen op twee of meer niveaus, dan kruisen twee
    wegen elkaar en is het een viaduct. Beide lijnlagen worden samengenomen,
    omdat een niveau in de ene laag kan zitten en niet in de andere.
    """
    frames = []
    for laag in [weglijn, weghartlijn]:
        if "hoogteniveau" in laag.columns:
            sub = laag[laag.geometry.notna() & ~laag.geometry.is_empty]
            frames.append(sub[["hoogteniveau", "geometry"]])

    if not frames:
        logger.warning("Geen hoogteniveau-kolom in de weglijnen")
        bridges["weg_hoogteniveaus_values"] = None
        bridges["aantal_hoogteniveaus"] = 0
        return bridges

    lijnen = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True), geometry="geometry", crs=bridges.crs
    )

    joined = gpd.sjoin(
        bridges[["bridge_group_id", "geometry"]],
        lijnen,
        how="inner",
        predicate="intersects",
    )

    niveaus = (
        joined.groupby("bridge_group_id")["hoogteniveau"]
        .agg(
            weg_hoogteniveaus_values=summarize_unique_values,
            aantal_hoogteniveaus="nunique",
        )
    )

    bridges = bridges.merge(niveaus, on="bridge_group_id", how="left")
    bridges["aantal_hoogteniveaus"] = bridges["aantal_hoogteniveaus"].fillna(0).astype(int)

    logger.info(
        "Hoogteniveaus: %d bruggen met meerdere niveaus (viaduct-signaal)",
        int((bridges["aantal_hoogteniveaus"] >= 2).sum()),
    )
    return bridges


# --- Water dat door de brug snijdt ----------------------------------------

def add_water_crossing(bridges, water):
    """Bepaal per brug of er een BGT-waterdeel doorheen snijdt.

    Het gaat om de context (over water), niet om een precieze overlapfractie.
    Er wordt geeist dat de overlap groter is dan de ruisdrempel, zodat een brug
    die net een slootrand raakt niet meetelt.
    """
    water = keep_polygons(water)
    if water.empty:
        bridges["kruist_water"] = False
        logger.warning("Waterlaag is leeg")
        return bridges

    overlay = gpd.overlay(
        bridges[["bridge_group_id", "geometry"]],
        water[["geometry"]],
        how="intersection",
        keep_geom_type=True,
    )
    overlay["overlap_area"] = overlay.geometry.area
    per_bridge = overlay.groupby("bridge_group_id")["overlap_area"].sum()

    voldoende = set(per_bridge[per_bridge > INTERSECTION_AREA_THRESHOLD_M2].index)
    bridges["kruist_water"] = bridges["bridge_group_id"].isin(voldoende)

    logger.info("Water: %d bruggen met water eronder", len(voldoende))
    return bridges


# --- Hoofdprogramma -------------------------------------------------------

def main():
    setup_logging()

    bridge_gpkg = get_gpkg_path(BRIDGE_SCRIPT)
    context_gpkg = get_gpkg_path(CONTEXT_SCRIPT)

    for path, stap in [(bridge_gpkg, "03"), (context_gpkg, "02")]:
        if not path.exists():
            raise FileNotFoundError(f"GeoPackage van stap {stap} ontbreekt: {path}")

    output_gpkg = get_gpkg_path(SCRIPT_NAME)
    output_gpkg.unlink(missing_ok=True)

    bridges = read_layer(bridge_gpkg, BRIDGE_LAYER)

    logger.info("\nContext-lagen inlezen...")
    wegvlak = read_layer(context_gpkg, LAYERS["wegvlak"], make_valid=True)
    weglijn = read_layer(context_gpkg, LAYERS["weglijn"])
    weghartlijn = read_layer(context_gpkg, LAYERS["weghartlijn"])
    spoor = read_layer(context_gpkg, LAYERS["spoor"])
    gebouw = read_layer(context_gpkg, LAYERS["gebouw"], make_valid=True)
    water = read_layer(context_gpkg, LAYERS["water"], make_valid=True)

    # --- Vlak-op-vlak overlapfracties ---
    logger.info("\nOverlapfracties berekenen...")
    bridges = add_area_overlap_fraction(bridges, wegvlak, "wegvlak")
    bridges = add_area_overlap_fraction(bridges, gebouw, "gebouw")

    # --- Meetellende weglijnen met hun attributen ---
    logger.info("\nWeglijnen op de bruggen...")
    bridges = add_crossing_line_attributes(
        bridges, weghartlijn, "weghartlijn", WEGHARTLIJN_ATTRS
    )
    bridges = add_crossing_line_attributes(
        bridges, weglijn, "weglijn", WEGLIJN_ATTRS
    )

    # --- Rijstroken op dekniveau ---
    logger.info("\nRijstroken op dekniveau...")
    bridges = add_rijstroken_op_dekniveau(bridges, weghartlijn)

    # --- Hoogteniveaus ---
    logger.info("\nHoogteniveaus...")
    bridges = add_road_height_levels(bridges, weglijn, weghartlijn)

    # --- Water ---
    logger.info("\nWater...")
    bridges = add_water_crossing(bridges, water)

    # --- Spoor ---
    logger.info("\nSpoor...")
    bridges = add_crossing_line_attributes(bridges, spoor, "spoor", SPOOR_ATTRS)

    save_layer(bridges, output_gpkg, "brugobjecten_relaties", script_name=SCRIPT_NAME)

    logger.info("\nStap 04 klaar.")
    logger.info("GeoPackage: %s", output_gpkg)


if __name__ == "__main__":
    main()