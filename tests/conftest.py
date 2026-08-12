"""Gedeelde pytest-fixtures voor de Brug-MKI-viewer-tests.

De bruggen-MKI-laag (±5,5 MB) wordt één keer per testsessie van schijf gelezen
via ``common.read_layer`` — zonder Streamlit-runtime, zodat de tests los van de
draaiende app werken. De per-gemeente-subsets zijn function-scoped: het filter
geeft een kopie terug, dus elke test krijgt een verse subset en kan die veilig
muteren zonder andere tests te raken.
"""

import sys
from pathlib import Path

# Zorg dat de projectroot importeerbaar is (common, viewer), ongeacht van waaruit
# pytest wordt gestart. Deze regels staan bewust vóór de projectimports.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402  (na de sys.path-injectie hierboven)

import common  # noqa: E402
from viewer import data  # noqa: E402


@pytest.fixture(scope="session")
def bridges():
    """Lees de volledige bruggen-MKI-laag één keer per sessie (EPSG:28992).

    Rechtstreeks via ``common.read_layer`` — dus zonder ``st.cache_data`` en
    zonder Streamlit-run-context, precies zoals de spawn-opdracht voorschrijft.
    """
    return common.read_layer(common.get_gpkg_path(data.MKI_SCRIPT), data.BRIDGE_LAYER)


@pytest.fixture
def amsterdam(bridges):
    """Verse Amsterdam-subset — de grootste gemeente in de dataset."""
    return data.filter_by_municipality(bridges, "Amsterdam")


@pytest.fixture
def diemen(bridges):
    """Verse Diemen-subset — een kleine gemeente, als tegenvoorbeeld."""
    return data.filter_by_municipality(bridges, "Diemen")


@pytest.fixture
def amstelveen(bridges):
    """Verse Amstelveen-subset — echte referentiegemeente voor de schaalbewijzen.

    Amstelveen zit in het viewer-menu (niet uitgesloten) en heeft bruggen in alle
    acht profielen zonder ontbrekende MKI, dus is het de ijkgemeente voor de
    multiplicatieve-master-bewijzen op echte data (Dallas §1: rauwe
    ``mki_per_jaar``-som ≈ 136.144,24).
    """
    return data.filter_by_municipality(bridges, "Amstelveen")


@pytest.fixture
def empty(bridges):
    """Lege subset: een gemeentenaam die niet in de data voorkomt.

    Bewijst de edge case 'gemeente zonder bruggen' (VIEWER_PLAN.md §8) zonder
    afhankelijk te zijn van de inhoud van de dataset.
    """
    return data.filter_by_municipality(bridges, "Onbekende Gemeente")
