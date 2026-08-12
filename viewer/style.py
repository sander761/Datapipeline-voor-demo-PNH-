"""Gedeelde stijl voor de Brug-MKI-viewer.

Eén plek voor de vaste profielkleuren, zodat de grafieken (Parker) en de kaart
(Lambert) dezelfde kleur per profiel gebruiken. De kleuren zijn verbatim
overgenomen uit `07_overzichten.py`, zodat de viewer herkenbaar blijft naast de
bestaande dashboards. Wordt de kleurenset daar aangepast, pas hem dan hier ook
aan (of verplaats hem later naar config.yaml — zie VIEWER_PLAN.md, open vraag 5).
"""

# Vaste kleur per profiel, verbatim overgenomen uit 07_overzichten.py, zodat de
# profielen in alle grafieken en op de kaart dezelfde kleur houden en tussen de
# viewer en de bestaande dashboards herkenbaar blijven.
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
