"""Weergaveschaling voor de Brug-MKI-viewer.

De schuiven worden op het moment van tonen toegepast op de MKI-waarden; de
bronwaarden uit de pipeline blijven ongemoeid (zie decisions.md, 2026-08-10).
Deze module is de enige plek waar de schalingsregel woont, zodat de grafieken
(charts.py) en de totaal-metric (app.py) exact dezelfde regel delen.

Evolutie van de regel:

* **v1.1** gebruikte één scalaire factor voor alle bruggen tegelijk:

      getoonde_waarde = waarde * factor        (factor 0.0-1.0, stappen van 0.01)

  `percentage_to_factor`, `apply_factor` en `scale_series` blijven hiervoor
  bestaan (scalaire gevallen en achterwaartse compatibiliteit).

* **v1.2** veralgemeniseert dit naar een **effectieve factor per profiel**. Het
  door de owner bevestigde model is een *multiplicatieve master*:

      effectieve_factor(profiel) = globale_factor * profiel_factor(profiel)

  De globale schuif werkt op alles; elke profiel-schuif fijnregelt zijn eigen
  type; alles op 100% (factor 1.0) betekent geen verandering. `combineer_factoren`
  bouwt de effectieve factor per canoniek profiel en `schaal_per_rij` past die
  per rij toe op het weergavemoment. De bron wordt nooit gemuteerd of herrekend.

Deze module is bewust **zuiver** (alleen pandas): geen streamlit, geen geopandas.
Zij rekent op Series, zodat zowel de grafieken als de app haar kunnen hergebruiken.
"""

import pandas as pd


def percentage_to_factor(percentage):
    """Zet een schuifstand (0-100) om naar een factor (0.0-1.0).

    Waarden buiten het bereik worden afgekapt, zodat de factor altijd geldig is.
    """
    begrensd = max(0, min(100, int(percentage)))
    return begrensd / 100


def apply_factor(value, factor):
    """Schaal een enkele waarde: value * factor. None/NaN blijft ongewijzigd."""
    if value is None or pd.isna(value):
        return value
    return value * factor


def scale_series(series, factor):
    """Schaal een pandas Series met de factor (voor grafiek- of kaartwaarden)."""
    return series * factor


# --- v1.2: per-profiel effectieve factoren --------------------------------
#
# De multiplicatieve master combineert de globale schuif met een schuif per
# profiel tot één effectieve factor per profiel; die factor wordt daarna per rij
# op de MKI toegepast. Zo leeft de regel op één plek en delen de grafieken en de
# totaal-metric hem letterlijk.


def _begrens_factor(factor, standaard=1.0):
    """Begrens een schaalfactor tot het geldige bereik [0.0, 1.0].

    Een factor is een weergaveschaling (0-100% -> 0.0-1.0). Negatief of boven 1
    is zinloos en wordt afgekapt. Een ontbrekende of niet-numerieke waarde
    (None/NaN/tekst) valt terug op `standaard` (standaard 1.0 = geen
    aanpassing), zodat een ontbrekende schuif de weergave niet verandert.
    """
    if factor is None:
        return standaard
    try:
        waarde = float(factor)
    except (TypeError, ValueError):
        return standaard
    if pd.isna(waarde):
        return standaard
    return max(0.0, min(1.0, waarde))


def combineer_factoren(globale_factor, profiel_factoren, alle_profielen):
    """Bouw de effectieve factor per profiel (globale master x profiel-schuif).

    De multiplicatieve master (owner-bevestigd, v1.2):

        effectieve_factor(profiel) = globale_factor * profiel_factor(profiel)

    Parameters
    ----------
    globale_factor : float
        De factor van de globale MKI-schuif (0.0-1.0). Werkt op elk profiel.
    profiel_factoren : dict
        Factor per profiel voor de profielen die een eigen schuif hebben
        (profiel -> factor 0.0-1.0). Een profiel dat hier ontbreekt krijgt 1.0
        (alleen de globale schuif werkt er dan op).
    alle_profielen : iterable
        Alle canonieke profielen (geef `PROFIEL_KLEUREN.keys()` mee vanuit de
        aanroeper). De uitkomst dekt hierdoor *elk* canoniek profiel, ook al
        heeft het geen eigen schuif of komt het in deze gemeente niet voor.

    Returns
    -------
    dict
        profiel -> effectieve factor (globaal x eigen), voor elk profiel in
        `alle_profielen`. Alle invoerfactoren worden begrensd tot [0.0, 1.0],
        dus de effectieve factor ligt ook in [0.0, 1.0]. Alles op 100% -> 1.0
        (geen verandering); alleen de globale schuif -> globaal x 1.0 (gedraagt
        zich exact als de v1.1-scalar).
    """
    globaal = _begrens_factor(globale_factor)
    losse = profiel_factoren or {}
    return {
        profiel: globaal * _begrens_factor(losse.get(profiel, 1.0))
        for profiel in alle_profielen
    }


def schaal_per_rij(waarden, profielen, effectieve_factoren, standaard=1.0):
    """Schaal elke waarde met de effectieve factor van haar profiel.

    De per-rij-variant van de schaling: elke MKI-waarde wordt vermenigvuldigd
    met de effectieve factor die bij het profiel van diezelfde rij hoort. Dit is
    de gedeelde weergavewaarde die zowel `charts.py` (figuren) als `app.py` (de
    totaal-metric) gebruiken, zodat de multiplicatieve regel op één plek leeft.

    Parameters
    ----------
    waarden : pandas.Series
        De te schalen MKI-waarden (bijv. `subset[MKI_JAAR_COLUMN]`).
    profielen : pandas.Series
        Het profiel per rij, met dezelfde index als `waarden` (bijv.
        `subset[PROFIEL_COLUMN]`).
    effectieve_factoren : dict
        profiel -> effectieve factor, doorgaans de uitkomst van
        `combineer_factoren`.
    standaard : float, optioneel
        Factor voor een profiel dat niet in `effectieve_factoren` staat
        (standaard 1.0 = geen verandering).

    Returns
    -------
    pandas.Series
        Een NIEUWE Series `waarden * factor_per_rij`, uitgelijnd op de index van
        de invoer. De invoer-Series blijven ongemoeid (nooit muteren).
    """
    factoren = profielen.map(effectieve_factoren).fillna(standaard)
    return waarden * factoren
