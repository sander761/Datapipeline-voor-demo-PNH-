"""run_all: draai de hele Bridge_MKI-pipeline achter elkaar.

Voert de zeven stappen in volgorde uit, elk in hetzelfde Python-proces via een
import en aanroep van hun main(). Faalt een stap, dan stopt de pipeline daar met
een duidelijke melding, zodat je niet met halve output verder werkt.

    python run_all.py            draait alles
    python run_all.py --vanaf 04 draait vanaf stap 04 (handig na een aanpassing
                                 in de classificatie, als 01-03 al gedraaid zijn)
    python run_all.py --tot 05   draait tot en met stap 05

De stappen delen geen state in het geheugen: elk leest de GeoPackage van de
vorige stap van schijf. Daardoor kun je met --vanaf veilig midden in de pipeline
beginnen, mits de eerdere stappen eerder zijn gedraaid en hun output er nog is.
"""

import argparse
import importlib
import time

import common

logger = common.setup_logging()

# De stappen in volgorde: (nummer, modulenaam). Het nummer is waarmee je op de
# opdrachtregel selecteert; de modulenaam is het bestand zonder .py.
STAPPEN = [
    # ("01", "01_download"),
    ("02", "02_clip"),
    ("03", "03_build_bridges"),
    ("04", "04_spatial_relations"),
    ("05", "05_classify"),
    ("06", "06_mki"),
    ("07", "07_overzichten"),
]


def draai_stap(nummer, module_naam):
    """Importeer een stap-module en draai zijn main(); meet de duur.

    De configuratiecache in common wordt per stap vers gehouden is niet nodig,
    maar de modules importeren common zelf, dus we hoeven hier alleen main() aan
    te roepen. Een uitzondering laat de pipeline stoppen in run_all.
    """
    logger.info("\n" + "=" * 70)
    logger.info("STAP %s  (%s)", nummer, module_naam)
    logger.info("=" * 70)

    start = time.perf_counter()
    module = importlib.import_module(module_naam)
    module.main()
    duur = time.perf_counter() - start

    logger.info("Stap %s klaar in %.1f s", nummer, duur)


def main():
    parser = argparse.ArgumentParser(description="Draai de Bridge_MKI-pipeline.")
    parser.add_argument("--vanaf", default="01", help="Begin bij dit stapnummer (bijv. 04).")
    parser.add_argument("--tot", default="07", help="Stop na dit stapnummer (bijv. 05).")
    args = parser.parse_args()

    nummers = [nr for nr, _ in STAPPEN]
    if args.vanaf not in nummers or args.tot not in nummers:
        parser.error(f"Kies --vanaf en --tot uit: {', '.join(nummers)}")
    if nummers.index(args.vanaf) > nummers.index(args.tot):
        parser.error("--vanaf ligt na --tot")

    te_draaien = [
        (nr, mod) for nr, mod in STAPPEN
        if nummers.index(args.vanaf) <= nummers.index(nr) <= nummers.index(args.tot)
    ]

    logger.info("Pipeline: stap %s tot en met %s (%d stappen)",
                args.vanaf, args.tot, len(te_draaien))

    totaal_start = time.perf_counter()
    for nummer, module_naam in te_draaien:
        try:
            draai_stap(nummer, module_naam)
        except Exception as exc:
            logger.error("\nStap %s (%s) is mislukt: %s", nummer, module_naam, exc)
            logger.error("Pipeline gestopt. Los de fout op en draai opnieuw, "
                         "eventueel met --vanaf %s.", nummer)
            raise SystemExit(1) from exc

    totaal = time.perf_counter() - totaal_start
    logger.info("\n" + "=" * 70)
    logger.info("Hele pipeline klaar in %.1f s (%.1f min)", totaal, totaal / 60)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()