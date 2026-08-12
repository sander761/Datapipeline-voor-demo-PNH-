"""Pipeline-schema voor de Brug-MKI-viewer — laag- en kolomnamen uit stap 06.

Dit zijn de namen uit het pipeline-schema (de output van stap 06/07), niet uit
config.yaml. Gemeenten, drempels en MKI-kentallen komen wél uit config (via
common) en worden nergens hardgecodeerd.

Bewust een **streamlit-vrije** module: hij bevat alleen kale constanten, geen
import van streamlit. Zo kunnen de zuivere modules (kaart, grafieken) deze namen
importeren zonder streamlit mee te trekken. `viewer.data` her-exporteert deze
constanten, zodat bestaande code (`data.MKI_JAAR_COLUMN`) blijft werken.
"""

# GeoPackage en laag van stap 06: één laag met alle bruggen + hun MKI.
MKI_SCRIPT = "06_mki"
BRIDGE_LAYER = "bruggen_mki"

# Gemeente waaraan een brug is toegekend (stuurt de filter in de viewer).
GEMEENTE_COLUMN = "gekozen_gemeente_naam"

# Profiel (brugtype); de waarden zijn exact de sleutels van PROFIEL_KLEUREN.
PROFIEL_COLUMN = "profiel"

# MKI-maten: per jaar (leidend in de viewer) en het totaal over 100 jaar.
MKI_JAAR_COLUMN = "mki_per_jaar"
MKI_TOTAAL_COLUMN = "mki_totaal_100jaar"

# Markering: True als er geen MKI kon worden toegekend (die rijen tellen niet mee).
MKI_ONTBREEKT_COLUMN = "mki_ontbreekt"

# Ruwe bronhouders als puntkomma-lijst; de dominante bronhouder is de eerste
# waarde (zie `eerste_bronhouder` in 07_overzichten.py).
BRONHOUDER_VALUES_COLUMN = "bronhouder_values"
