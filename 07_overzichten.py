"""Stap 07: overzichten en grafieken van de brug-MKI.

De laatste stap vat de resultaten samen in Excel-overzichten en twee
interactieve HTML-dashboards. Er wordt niets meer aan de MKI berekend; dit is
aggregatie en visualisatie.

Twee dashboards, met verschillende leesdoelen:

    mki_overzicht.html    de uitkomst: MKI per gemeente, per profiel, per
                          bronhouder, en de opsplitsing van de MKI per profiel
                          binnen elke gemeente (gestapeld en genormaliseerd).

    mki_verdelingen.html  de datakwaliteit: violinplots van lengte, oppervlakte
                          en breedte per profiel, en histogrammen van diezelfde
                          maten over alle bruggen.

Daarnaast een Excel met alle aggregatietabellen en de foutenanalyse.

    python 07_overzichten.py
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import common
from common import (
    get_excel_path,
    get_output_dir,
    get_gpkg_path,
    read_layer,
    setup_logging,
)


# --- Configuratie ---------------------------------------------------------

SCRIPT_NAME = "07_overzichten"
MKI_SCRIPT = "06_mki"
CLASSIFY_SCRIPT = "05_classify"

BRUG_LAYER = "bruggen_mki"
GEEN_BRUG_LAYER = "geen_brug"

MKI_JAAR_COL = "mki_per_jaar"
MKI_TOTAAL_COL = "mki_totaal_100jaar"

VERDELING_KOLOMMEN = {
    "bbox_lengte_m": "Lengte (m)",
    "area_m2": "Oppervlakte (m2)",
    "oppervlakte_breedte_m": "Breedte (m)",
}

# Vaste x-as-bereiken per maat, ruim genoeg voor de grote bruggen. Alleen echte
# artefacten (een deling door bijna-nul bij de breedte, een kapotte polygoon bij
# de oppervlakte) vallen buiten beeld, zodat een enkele uitschieter de as niet
# oprekt en de verdeling onleesbaar maakt.
HIST_BEREIK = {
    "bbox_lengte_m": (0, 3000),
    "area_m2": (0, 30000),
    "oppervlakte_breedte_m": (0, 200),
}

# Vaste kleur per profiel, zodat de profielen in alle grafieken dezelfde kleur
# houden en tussen dashboards herkenbaar blijven.
PROFIEL_KLEUREN = {
    "brug_1x2": "#3b6ea5",
    "brug_2x2": "#2a4d73",
    "brug_2x3": "#1b3450",
    "viaduct_1x2": "#c17f3a",
    "viaduct_2x2": "#9c5f22",
    "viaduct_2x3": "#6f4114",
    "fietsbrug_over_water": "#4a9d7f",
    "fietsbrug_over_weg": "#7bb8a1",
}

logger = common.logger


# --- Hulp -----------------------------------------------------------------

def eerste_bronhouder(value):
    """Geef de eerste (dominante) bronhouder uit een puntkomma-lijst."""
    if pd.isna(value) or not str(value).strip():
        return "onbekend"
    return str(value).split(";")[0].strip()


# --- Aggregaties ----------------------------------------------------------

def aggregeer(bridges):
    """Maak de aggregatietabellen die naar Excel en grafiek gaan."""
    geldig = bridges[~bridges["mki_ontbreekt"]].copy()
    geldig["bronhouder"] = geldig["bronhouder_values"].map(eerste_bronhouder)

    def sommeer(kolom):
        return (
            geldig.groupby(kolom)
            .agg(mki_per_jaar=(MKI_JAAR_COL, "sum"),
                 mki_totaal_100jaar=(MKI_TOTAAL_COL, "sum"),
                 aantal_bruggen=(MKI_JAAR_COL, "size"))
            .round(2).sort_values("mki_per_jaar", ascending=False).reset_index()
        )

    per_gemeente = sommeer("gekozen_gemeente_naam")
    per_profiel = sommeer("profiel")
    per_bronhouder = sommeer("bronhouder")

    gem_profiel = (
        geldig.groupby(["gekozen_gemeente_naam", "profiel"])[MKI_JAAR_COL]
        .sum().round(2).reset_index()
    )
    kruistabel = gem_profiel.pivot(
        index="gekozen_gemeente_naam", columns="profiel", values=MKI_JAAR_COL
    ).fillna(0).round(2)

    return geldig, per_gemeente, per_profiel, per_bronhouder, gem_profiel, kruistabel


def foutenanalyse(geen_brug):
    """Vat samen wat er is weggefilterd, in aantal en oppervlak."""
    per_reden = (
        geen_brug.groupby("classificatie_reden")
        .agg(aantal=("area_m2", "size"), oppervlak_m2=("area_m2", "sum"))
        .round(1).sort_values("oppervlak_m2", ascending=False).reset_index()
    )

    relaties = {}
    for kolom, label in [
        ("kruist_water", "kruist water"),
        ("kruist_weghartlijn", "kruist weghartlijn"),
        ("kruist_weglijn", "kruist weglijn"),
    ]:
        if kolom in geen_brug.columns:
            mask = geen_brug[kolom].astype(bool)
            relaties[label] = {
                "aantal": int(mask.sum()),
                "oppervlak_m2": round(geen_brug.loc[mask, "area_m2"].sum(), 1),
            }
    relaties_df = pd.DataFrame(relaties).T.reset_index().rename(columns={"index": "relatie"})

    return per_reden, relaties_df


# --- Grafieken ------------------------------------------------------------

def bar_figuur(df, x, y, titel, y_label, kleur="#3b6ea5"):
    """Enkelvoudig staafdiagram, gesorteerd op waarde."""
    fig = px.bar(df, x=x, y=y, title=titel)
    fig.update_layout(
        xaxis_title=None, yaxis_title=y_label,
        template="plotly_white", title_x=0.5,
        margin=dict(t=60, b=40, l=60, r=20),
    )
    fig.update_traces(marker_color=kleur)
    return fig


def gestapelde_figuur(gem_profiel, normaliseer, titel, y_label):
    """Gestapelde staaf per gemeente, opgedeeld naar profiel.

    Bij normaliseer=True wordt per gemeente naar 100% geschaald, zodat de
    samenstelling tussen gemeenten vergelijkbaar is los van hun totale omvang.
    """
    data = gem_profiel.copy()
    if normaliseer:
        totalen = data.groupby("gekozen_gemeente_naam")[MKI_JAAR_COL].transform("sum")
        data["waarde"] = (data[MKI_JAAR_COL] / totalen * 100).round(1)
    else:
        data["waarde"] = data[MKI_JAAR_COL]

    fig = px.bar(
        data, x="gekozen_gemeente_naam", y="waarde", color="profiel",
        title=titel, color_discrete_map=PROFIEL_KLEUREN,
        category_orders={"profiel": list(PROFIEL_KLEUREN)},
    )
    fig.update_layout(
        barmode="stack", xaxis_title=None, yaxis_title=y_label,
        template="plotly_white", title_x=0.5, legend_title_text="Profiel",
        margin=dict(t=60, b=40, l=60, r=20),
    )
    return fig


def violin_figuur(bridges, kolom, label):
    """Violinplot van een maat per profiel, met mediaan en spreiding.

    De violin toont de vorm van de verdeling per profiel. Waarden buiten het
    realistische bereik vallen weg, zodat een artefact de as niet oprekt.
    """
    lo, hi = HIST_BEREIK.get(kolom, (0, float("inf")))
    data = bridges[
        bridges[kolom].notna() & (bridges[kolom] >= lo) & (bridges[kolom] <= hi)
    ].copy()

    fig = go.Figure()
    for profiel in PROFIEL_KLEUREN:
        sub = data[data["profiel"] == profiel]
        if sub.empty:
            continue
        fig.add_trace(go.Violin(
            x=[profiel] * len(sub), y=sub[kolom],
            name=profiel, box_visible=True, meanline_visible=True,
            line_color=PROFIEL_KLEUREN[profiel], fillcolor=PROFIEL_KLEUREN[profiel],
            opacity=0.6, points=False,
        ))
    fig.update_layout(
        title=f"Verdeling {label} per profiel", title_x=0.5,
        yaxis_title=label, template="plotly_white", showlegend=False,
        margin=dict(t=60, b=80, l=60, r=20),
    )
    fig.update_xaxes(tickangle=-30)
    return fig


def histogram_figuur(bridges, kolom, label):
    """Histogram op een log-x-as, met bins die in log-ruimte liggen.

    De bins worden zelf logaritmisch verdeeld en als staven getekend; Plotly's
    eigen histogram maakt op een log-as lineaire bins die uitwaaieren. Waarden
    buiten het realistische bereik vallen weg, zodat een artefact de as niet
    oprekt.
    """
    import numpy as np

    lo, hi = HIST_BEREIK.get(kolom, (0, None))
    waarden = bridges[kolom].dropna()
    bovengrens = hi if hi is not None else waarden.max()
    binnen = waarden[(waarden > 0) & (waarden >= lo) & (waarden <= bovengrens)].to_numpy()

    weggelaten = len(waarden) - len(binnen)
    if weggelaten:
        logger.warning("%s: %d waarden buiten (0, %g] weggelaten uit de grafiek",
                       label, weggelaten, bovengrens)

    if len(binnen) < 5:
        return None

    # Bins logaritmisch verdeeld tussen de kleinste en grootste waarde.
    log_edges = np.linspace(np.log10(binnen.min()), np.log10(binnen.max()), 51)
    edges = 10 ** log_edges
    counts, _ = np.histogram(binnen, bins=edges)
    centers = np.sqrt(edges[:-1] * edges[1:])   # geometrisch midden per bin
    widths = edges[1:] - edges[:-1]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=centers, y=counts, width=widths,
        marker_color="#3b6ea5", opacity=0.85,
    ))
    fig.update_layout(
        title=f"Verdeling {label} over alle bruggen (log-as)", title_x=0.5,
        xaxis_title=label, yaxis_title="aantal bruggen", bargap=0,
        template="plotly_white", margin=dict(t=60, b=40, l=60, r=20),
    )
    fig.update_xaxes(type="log")
    return fig

# --- Uitvoer --------------------------------------------------------------

def bouw_html(figuren, titel, path):
    """Zet figuren onder elkaar in een zelfstandig HTML-bestand."""
    delen = []
    for i, fig in enumerate(figuren):
        if fig is None:
            continue
        include = "cdn" if i == 0 else False
        delen.append(fig.to_html(full_html=False, include_plotlyjs=include))

    html = (
        f"<!DOCTYPE html><html lang='nl'><head><meta charset='utf-8'>"
        f"<title>{titel}</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:1100px;"
        "margin:0 auto;padding:20px;background:#fafafa;}"
        "h1{color:#2a4d73;}</style></head><body>"
        f"<h1>{titel}</h1>"
        + "".join(f"<div style='margin-bottom:40px;'>{d}</div>" for d in delen)
        + "</body></html>"
    )
    path.write_text(html, encoding="utf-8")
    logger.info("Opgeslagen: %s", path.name)


def schrijf_excel(tabellen, path):
    """Schrijf alle overzichtstabellen naar een Excel met een tabblad per stuk."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for naam, tabel in tabellen.items():
            index = isinstance(tabel.index, pd.MultiIndex) or tabel.index.name is not None
            tabel.to_excel(writer, sheet_name=naam[:31], index=index)
    logger.info("Overzichten opgeslagen: %s", path.name)


# --- Hoofdprogramma -------------------------------------------------------

def main():
    setup_logging()

    mki_gpkg = get_gpkg_path(MKI_SCRIPT)
    classify_gpkg = get_gpkg_path(CLASSIFY_SCRIPT)
    for path, stap in [(mki_gpkg, "06"), (classify_gpkg, "05")]:
        if not path.exists():
            raise FileNotFoundError(f"GeoPackage van stap {stap} ontbreekt: {path}")

    output_dir = get_output_dir(SCRIPT_NAME)

    bridges = read_layer(mki_gpkg, BRUG_LAYER)
    geen_brug = read_layer(classify_gpkg, GEEN_BRUG_LAYER)

    geldig, per_gemeente, per_profiel, per_bronhouder, gem_profiel, kruistabel = aggregeer(bridges)
    per_reden, relaties = foutenanalyse(geen_brug)

    # --- Excel ---
    schrijf_excel(
        {
            "per_gemeente": per_gemeente,
            "per_profiel": per_profiel,
            "per_bronhouder": per_bronhouder,
            "kruistabel_gem_x_profiel": kruistabel,
            "weggefilterd_per_reden": per_reden,
            "uitgesloten_relaties": relaties,
        },
        get_excel_path(SCRIPT_NAME, "mki_overzichten"),
    )

    # --- Dashboard 1: de uitkomst ---
    overzicht_figuren = [
        bar_figuur(per_gemeente, "gekozen_gemeente_naam", MKI_JAAR_COL,
                   "MKI per jaar per gemeente", "MKI per jaar"),
        bar_figuur(per_profiel, "profiel", MKI_JAAR_COL,
                   "MKI per jaar per profiel", "MKI per jaar"),
        bar_figuur(per_bronhouder, "bronhouder", MKI_JAAR_COL,
                   "MKI per jaar per bronhouder", "MKI per jaar"),
        gestapelde_figuur(gem_profiel, False,
                          "MKI per jaar per gemeente, opgedeeld naar profiel", "MKI per jaar"),
        gestapelde_figuur(gem_profiel, True,
                          "Profielsamenstelling per gemeente (%)", "aandeel (%)"),
        bar_figuur(per_reden, "classificatie_reden", "oppervlak_m2",
                   "Weggefilterd oppervlak per reden", "Oppervlak (m2)", kleur="#c1440e"),
    ]
    bouw_html(overzicht_figuren, "Brug-MKI overzicht", output_dir / "mki_overzicht.html")

    # --- Dashboard 2: de datakwaliteit ---
    verdeling_figuren = []
    for kolom, label in VERDELING_KOLOMMEN.items():
        if kolom in geldig.columns:
            verdeling_figuren.append(violin_figuur(geldig, kolom, label))
    for kolom, label in VERDELING_KOLOMMEN.items():
        if kolom in geldig.columns:
            verdeling_figuren.append(histogram_figuur(geldig, kolom, label))
    bouw_html(verdeling_figuren, "Brug-MKI verdelingen en kwaliteit",
              output_dir / "mki_verdelingen.html")

    # --- Samenvatting ---
    logger.info("\nTotale MKI: %.2f per jaar", geldig[MKI_JAAR_COL].sum())
    logger.info("Weggefilterd: %d objecten, %.0f m2",
                len(geen_brug), geen_brug["area_m2"].sum())
    logger.info("\nStap 07 klaar.")
    logger.info("Excel:       %s", get_excel_path(SCRIPT_NAME, "mki_overzichten"))
    logger.info("Overzicht:   %s", output_dir / "mki_overzicht.html")
    logger.info("Verdelingen: %s", output_dir / "mki_verdelingen.html")


if __name__ == "__main__":
    main()