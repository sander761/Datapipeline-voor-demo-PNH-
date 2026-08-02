"""Gedeelde paden, instellingen en helpers voor de Bridge_MKI-pipeline v2.

Deze versie schrijft de output van elk script naar een eigen submap onder
output/, met per script een GeoPackage (alle lagen van dat script) en een map
excel/ met per laag een xlsx zonder geometrie. Zo blijft de output van de
stappen gescheiden en is per stap terug te zien wat eruit kwam.

Wat de gebruiker aanpast staat in config.yaml: het studiegebied, de
download-instellingen en de classificatie-drempels. Wat hier in de code staat
zijn aannames waar de pipeline op rust, zoals het coordinatensysteem en de
mapstructuur.
"""

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

try:
    import yaml
except ImportError as exc:
    raise ImportError("PyYAML ontbreekt. Installeer met: pip install pyyaml") from exc

try:
    import openpyxl  # noqa: F401  (alleen nodig als engine voor pandas)
except ImportError as exc:
    raise ImportError("openpyxl ontbreekt. Installeer met: pip install openpyxl") from exc


# --- Paden ----------------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "output"
CONFIG_FILE = PROJECT_DIR / "config.yaml"


def get_output_dir(script_name):
    """Geef de outputmap van een script en maak de submappen aan.

    Elk script schrijft naar output/<script_name>/, met daarin een GeoPackage
    en een map excel/. De naam is die van het script zonder .py, bijvoorbeeld
    '01_download'. Door de mappen hier aan te maken hoeft elk script alleen
    zijn eigen naam te kennen.
    """
    script_dir = OUTPUT_DIR / script_name
    (script_dir / "excel").mkdir(parents=True, exist_ok=True)
    return script_dir


def get_gpkg_path(script_name):
    """Geef het pad van de GeoPackage van een script.

    Een GeoPackage per script, met alle lagen van dat script erin. De naam
    volgt de scriptnaam, zodat je in de outputmap direct ziet welk bestand bij
    welke stap hoort.
    """
    return get_output_dir(script_name) / f"{script_name}.gpkg"


def get_excel_path(script_name, layer_name):
    """Geef het pad van de Excel voor een specifieke laag van een script."""
    return get_output_dir(script_name) / "excel" / f"{layer_name}.xlsx"


# --- Vaste instellingen ---------------------------------------------------

# EPSG:28992 is het Rijksdriehoeksstelsel (RD New). Alle ruimtelijke bewerkingen
# gebeuren hierin, zodat oppervlaktes in vierkante meters uitkomen en afstanden
# in meters.
TARGET_CRS = 28992

logger = logging.getLogger("bridge_mki_v2")


def setup_logging(level=logging.INFO):
    """Zet logging op en geef de gedeelde logger terug."""
    logging.basicConfig(level=level, format="%(message)s")
    return logger


# --- Configuratie inlezen -------------------------------------------------

_config_cache = None


def load_config(force_reload=False):
    """Lees config.yaml in en controleer de verwachte secties.

    De uitkomst wordt gecachet, zodat herhaalde aanroepen binnen een run geen
    extra schijftoegang kosten.
    """
    global _config_cache

    if _config_cache is not None and not force_reload:
        return _config_cache

    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Configuratiebestand niet gevonden: {CONFIG_FILE}\n"
            "Zonder dit bestand weet de pipeline niet welk gebied hij moet "
            "analyseren."
        )

    try:
        config = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(
            f"Kon {CONFIG_FILE.name} niet lezen. Controleer de opmaak: YAML "
            f"gebruikt inspringing met spaties, nooit tabs.\n\n{exc}"
        ) from exc

    if not isinstance(config, dict):
        raise ValueError(f"{CONFIG_FILE.name} bevat geen instellingen.")

    for key in ["gemeenten", "download"]:
        if key not in config:
            raise ValueError(f"Ontbrekende sectie in {CONFIG_FILE.name}: {key}")

    if not config["gemeenten"]:
        raise ValueError(f"Geen gemeenten opgegeven in {CONFIG_FILE.name}.")

    _config_cache = config
    return config


def get_gemeenten():
    """Geef de gemeentenamen die het studiegebied bepalen."""
    names = [str(name).strip() for name in load_config()["gemeenten"]]
    return [name for name in names if name]


def get_download_settings():
    """Geef de download-instellingen (tegelgrootte en -buffer)."""
    return load_config()["download"]


def get_classification_settings():
    """Geef de classificatie-instellingen voor stap 05.

    Bevat de breedtegrenzen die de terugval gebruikt wanneer het aantal
    rijstroken ontbreekt. Ontbreekt de sectie in config.yaml, dan worden
    standaardgrenzen teruggegeven, zodat stap 05 blijft werken.
    """
    config = load_config()
    default = {"breedte_grenzen": {"1x2": 12.0, "2x2": 28.0}}

    settings = config.get("classificatie", default)

    if "breedte_grenzen" not in settings:
        logger.warning(
            "Geen breedte_grenzen in config.yaml; standaardwaarden gebruikt."
        )
        settings["breedte_grenzen"] = default["breedte_grenzen"]

    return settings


# --- Waarden omzetten -----------------------------------------------------

def parse_numeric_value(value):
    """Zet een waarde om naar float, of geef None als dat niet kan.

    Attributen komen soms als tekst binnen, en met een komma als decimaalteken.
    Een waarde die niet te parsen is levert None op in plaats van een fout,
    zodat een enkele rommelige rij de verwerking niet stopt.
    """
    if pd.isna(value):
        return None
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        return None


def summarize_unique_values(series):
    """Vat een kolom samen als puntkomma-lijst van unieke, niet-lege waarden.

    Wordt gebruikt bij het samenvoegen: als meerdere delen samengaan tot een
    brug, blijft zichtbaar welke waarden die delen hadden. dict.fromkeys houdt
    de volgorde van eerste voorkomen aan, zodat de uitvoer reproduceerbaar is.
    """
    values = dict.fromkeys(
        str(v).strip() for v in series if not pd.isna(v) and str(v).strip()
    )
    return "; ".join(values) if values else None


def min_max_numeric(series):
    """Geef (min, max) van de numeriek parsebare waarden in een reeks.

    Waarden die niet te parsen zijn worden overgeslagen. Bij een reeks zonder
    bruikbare waarden is de uitkomst (None, None).
    """
    values = [v for v in map(parse_numeric_value, series) if v is not None]
    return (min(values), max(values)) if values else (None, None)


# --- Geometrie ------------------------------------------------------------

def keep_valid_geometries(gdf):
    """Verwijder rijen zonder geometrie of met een lege geometrie."""
    return gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()


def keep_polygons(gdf):
    """Houd alleen niet-lege (Multi)Polygonen over.

    Een intersection kan lijnen of punten opleveren wanneer twee vlakken elkaar
    precies op een rand raken. Die hebben geen oppervlakte en zijn voor deze
    analyse betekenisloos, dus ze gaan eruit.
    """
    return gdf[
        gdf.geometry.notna()
        & ~gdf.geometry.is_empty
        & gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    ].copy()


def geometry_union(gdf):
    """Voeg alle geometrieen van een laag samen tot een enkele geometrie.

    Bij een lege laag is de uitkomst None; de aanroepende code moet daarop
    controleren voor die de uitkomst gebruikt.
    """
    return None if gdf.empty else gdf.geometry.union_all()


# --- Opslaan --------------------------------------------------------------

def clean_gdf_for_storage(gdf):
    """Zet kolommen met complexe waarden om naar tekst, zodat ze opslaanbaar zijn.

    GeoPackage en Excel kunnen alleen eenvoudige types opslaan. Een dict of
    lijst in een kolom, wat voorkomt bij geneste JSON uit een API, wordt hier
    omgezet naar tekst. De geometriekolom blijft ongemoeid.
    """
    gdf = gdf.copy()
    for col in gdf.columns:
        if col == gdf.geometry.name:
            continue
        if gdf[col].map(lambda v: isinstance(v, (dict, list, tuple, set))).any():
            gdf[col] = gdf[col].map(
                lambda v: "; ".join(map(str, v)) if isinstance(v, (list, tuple, set))
                else (str(v) if isinstance(v, dict) else v)
            )
    return gdf


def save_layer(gdf, gpkg_path, layer_name, write_excel=True, script_name=None):
    """Sla een laag op in de GeoPackage en optioneel als Excel.

    De GeoPackage is de werkelijke output; de Excel is een leesbare kopie van
    de attribuutdata zonder geometrie, om in te kunnen bladeren. Voor de Excel
    is script_name nodig, omdat die in de excel-submap van dat script komt.

    Een lege laag wordt overgeslagen met een waarschuwing.
    """
    if gdf.empty:
        logger.warning("Lege laag overgeslagen: %s", layer_name)
        return

    gdf = clean_gdf_for_storage(gdf)

    if gdf.crs is None:
        gdf = gdf.set_crs(TARGET_CRS)
    gdf = gdf.to_crs(TARGET_CRS)

    gdf.to_file(gpkg_path, layer=layer_name, driver="GPKG")
    logger.info("Opgeslagen in GeoPackage: %s (%d rijen)", layer_name, len(gdf))

    if write_excel:
        if script_name is None:
            raise ValueError("script_name is nodig om de Excel weg te schrijven.")
        save_layer_excel(gdf, script_name, layer_name)


def save_layer_excel(gdf, script_name, layer_name):
    """Schrijf de attribuutdata van een laag naar een Excel zonder geometrie.

    Twee tabbladen. 'attributen' is de volledige tabel om doorheen te scrollen.
    'overzicht' vat per kolom samen hoeveel waarden ingevuld en uniek zijn en
    welke voorkomen; dat is het tabblad om te zien wat bruikbaar is.

    Excel kan maximaal ruim een miljoen rijen per tabblad aan. Zit een laag
    daarboven, dan geeft openpyxl een foutmelding; dat is bij dit studiegebied
    onwaarschijnlijk, maar goed om te weten.
    """
    attributen = pd.DataFrame(gdf.drop(columns=[gdf.geometry.name]))

    overzicht_rows = []
    for col in attributen.columns:
        waarden = attributen[col]
        uniek = waarden.nunique(dropna=True)

        if uniek <= 50:
            top = waarden.value_counts(dropna=True).head(50)
            voorbeelden = "; ".join(f"{v} ({n})" for v, n in top.items())
        else:
            voorbeelden = "; ".join(str(v) for v in waarden.dropna().unique()[:5]) + " ..."

        overzicht_rows.append({
            "kolom": col,
            "ingevuld": int(waarden.notna().sum()),
            "leeg": int(waarden.isna().sum()),
            "aantal_uniek": int(uniek),
            "waarden_of_voorbeelden": voorbeelden,
        })

    overzicht = pd.DataFrame(overzicht_rows)
    path = get_excel_path(script_name, layer_name)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        overzicht.to_excel(writer, sheet_name="overzicht", index=False)
        attributen.to_excel(writer, sheet_name="attributen", index=False)

    logger.info("Opgeslagen in Excel: %s", path.name)


def read_layer(gpkg_path, layer_name, make_valid=False):
    """Lees een laag uit een GeoPackage, omgezet naar RD New.

    Zet make_valid=True voor lagen die daarna in een overlay of sjoin gaan;
    dat repareert zelfsnijdende polygonen, die anders een TopologyException
    veroorzaken. De reparatie kost tijd op grote lagen, dus staat standaard uit.
    """
    gdf = gpd.read_file(gpkg_path, layer=layer_name)

    if gdf.crs is None:
        gdf = gdf.set_crs(TARGET_CRS)
    gdf = gdf.to_crs(TARGET_CRS)
    gdf = keep_valid_geometries(gdf)

    if make_valid:
        gdf["geometry"] = gdf.geometry.make_valid()
        gdf = keep_valid_geometries(gdf)

    logger.info("Gelezen: %s (%d rijen)", layer_name, len(gdf))
    return gdf

def get_mki_kentallen():
    """Geef de MKI-kentallen per profiel uit config.yaml.

    Ontbreekt de sectie, dan volgt een duidelijke fout: zonder kentallen kan
    stap 06 geen MKI toekennen.
    """
    config = load_config()
    if "mki_kentallen" not in config:
        raise ValueError(
            "Sectie 'mki_kentallen' ontbreekt in config.yaml; stap 06 kan geen "
            "MKI berekenen."
        )
    return config["mki_kentallen"]