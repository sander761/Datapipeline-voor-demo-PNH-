"""Stap 06: MKI-kentallen aan de geclassificeerde bruggen koppelen.

Elke brug uit stap 05 heeft een profiel (viaduct/brug/fietsbrug met
breedteklasse). Deze stap zoekt bij dat profiel het kental op en berekent de
MKI, geschaald op de lengte van de brug.

De kentallen staan in config.yaml als MKI per jaar (levensduur al verrekend).
Per profiel is er een vast deel (alleen viaducten, voor het landhoofd) plus een
deel per strekkende meter. De lengteklasse (onder/boven 60 m, en voor
fietsbruggen ook onder 20 m) wordt hier uit bbox_lengte_m afgeleid, want dat is
een opdeling van de kentallen-tabel, geen eigenschap van de brug zelf.

    MKI_per_jaar = vast_per_jaar + per_meter_per_jaar * lengte

Bruggen waarvan het profiel niet in de kentallen voorkomt, of die geen lengte
hebben, krijgen geen MKI maar worden gemarkeerd, zodat zichtbaar is hoe vaak
dat gebeurt.

    python 06_mki.py
"""

import pandas as pd

import common
from common import (
    get_gpkg_path,
    get_mki_kentallen,
    parse_numeric_value,
    read_layer,
    save_layer,
    setup_logging,
)


# --- Configuratie ---------------------------------------------------------

SCRIPT_NAME = "06_mki"
SOURCE_SCRIPT = "05_classify"
SOURCE_LAYER = "bruggen"

# Aantal jaren waarover de totale MKI wordt getoond, naast de jaarwaarde.
LEVENSDUUR_JAAR = 100

logger = common.logger


# --- Kental opzoeken ------------------------------------------------------

def lengteklasse_label(tot_m, vorige_grens):
    """Geef een leesbaar label voor een lengteklasse.

    tot_m is de bovengrens (strikt kleiner dan); None is de restklasse. De
    vorige_grens maakt het label preciezer ("20-60 m" in plaats van "onder
    60 m") wanneer er een ondergrens is.
    """
    if tot_m is None:
        return f"boven {vorige_grens:g} m" if vorige_grens else "alle lengtes"
    if vorige_grens:
        return f"{vorige_grens:g}-{tot_m:g} m"
    return f"onder {tot_m:g} m"


def lookup_kental(profiel, lengte, kentallen):
    """Zoek het kental voor een profiel en lengte.

    Geeft (vast, per_meter, lengteklasse_label) terug, of None als het profiel
    niet in de kentallen staat. Voor viaducten (een enkel kental zonder
    lengteklasse) wordt de lengteklasse "alle lengtes".
    """
    if profiel not in kentallen:
        return None

    kental = kentallen[profiel]

    # Viaducten: een enkel kental (dict met vast + per_meter), geen lengteklasse.
    if isinstance(kental, dict):
        return kental["vast_per_jaar"], kental["per_meter_per_jaar"], "alle lengtes"

    # Bruggen en fietsbruggen: een lijst klassen, oplopend op tot_m. De eerste
    # klasse waar de lengte onder valt (strikt) wint; de laatste (tot_m null) is
    # de restklasse.
    vorige_grens = None
    for klasse in kental:
        tot_m = klasse["tot_m"]
        if tot_m is None or lengte < tot_m:
            label = lengteklasse_label(tot_m, vorige_grens)
            return klasse["vast_per_jaar"], klasse["per_meter_per_jaar"], label
        vorige_grens = tot_m

    # Zou niet moeten voorkomen: geen restklasse gedefinieerd.
    return None


# --- MKI berekenen --------------------------------------------------------

def add_mki(bridges, kentallen):
    """Bereken per brug de MKI en de gebruikte lengteklasse.

    Bruggen zonder passend kental of zonder lengte krijgen geen MKI en worden
    gemarkeerd met mki_ontbreekt, zodat het aantal zichtbaar is.
    """
    bridges = bridges.copy()

    mki_jaar = []
    mki_totaal = []
    lengteklasse = []
    kental_rij = []
    ontbreekt = []

    for row in bridges.itertuples():
        profiel = getattr(row, "profiel", None)
        lengte = parse_numeric_value(getattr(row, "bbox_lengte_m", None))

        if profiel is None or lengte is None:
            mki_jaar.append(None)
            mki_totaal.append(None)
            lengteklasse.append(None)
            kental_rij.append(None)
            ontbreekt.append(True)
            continue

        gevonden = lookup_kental(profiel, lengte, kentallen)
        if gevonden is None:
            mki_jaar.append(None)
            mki_totaal.append(None)
            lengteklasse.append(None)
            kental_rij.append(None)
            ontbreekt.append(True)
            continue

        vast, per_meter, klasse_label = gevonden
        per_jaar = vast + per_meter * lengte

        mki_jaar.append(round(per_jaar, 2))
        mki_totaal.append(round(per_jaar * LEVENSDUUR_JAAR, 2))
        lengteklasse.append(klasse_label)
        kental_rij.append(f"{profiel} ({klasse_label})")
        ontbreekt.append(False)

    bridges["mki_lengteklasse"] = lengteklasse
    bridges["mki_per_jaar"] = mki_jaar
    bridges[f"mki_totaal_{LEVENSDUUR_JAAR}jaar"] = mki_totaal
    bridges["mki_kental_rij"] = kental_rij
    bridges["mki_ontbreekt"] = ontbreekt

    n_ontbreekt = int(bridges["mki_ontbreekt"].sum())
    logger.info(
        "MKI toegekend aan %d van %d bruggen (%d zonder kental)",
        len(bridges) - n_ontbreekt, len(bridges), n_ontbreekt,
    )
    if n_ontbreekt:
        # Laat zien welke profielen ontbreken, om te kunnen bijsturen.
        missende = bridges.loc[bridges["mki_ontbreekt"], "profiel"].value_counts()
        logger.warning("Profielen zonder kental:\n%s", missende.to_string())

    return bridges


def main():
    setup_logging()

    source_gpkg = get_gpkg_path(SOURCE_SCRIPT)
    if not source_gpkg.exists():
        raise FileNotFoundError(
            f"GeoPackage van stap 05 ontbreekt: {source_gpkg}\nDraai eerst stap 05."
        )

    output_gpkg = get_gpkg_path(SCRIPT_NAME)
    output_gpkg.unlink(missing_ok=True)

    kentallen = get_mki_kentallen()
    bridges = read_layer(source_gpkg, SOURCE_LAYER)
    bridges = add_mki(bridges, kentallen)

    save_layer(bridges, output_gpkg, "bruggen_mki", script_name=SCRIPT_NAME)

    # Totalen ter controle: som per jaar, en de verdeling over profielen.
    geldig = bridges[~bridges["mki_ontbreekt"]]
    logger.info(
        "\nTotale MKI: %.2f per jaar (%.2f over %d jaar)",
        geldig["mki_per_jaar"].sum(),
        geldig[f"mki_totaal_{LEVENSDUUR_JAAR}jaar"].sum(),
        LEVENSDUUR_JAAR,
    )
    logger.info(
        "\nMKI per jaar per profiel:\n%s",
        geldig.groupby("profiel")["mki_per_jaar"].sum().round(2).to_string(),
    )

    logger.info("\nStap 06 klaar.")
    logger.info("GeoPackage: %s", output_gpkg)


if __name__ == "__main__":
    main()