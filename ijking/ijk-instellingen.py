#!/usr/bin/env python3
"""IJking van de instellingen (etappe A, 15 oktober 2026): de huidige locatie.

Alles gebeurt in een **proefbestand** in de scratchmap, zodat de kaarten en instellingen van Jan
in `~/astrologie-horoscopen` niet geraakt worden. Zeven metingen:

  1. het pad: één functie, met `ASTRO_INSTELLINGEN` erover heen en een expliciet pad voor een proef;
  2. nog geen bestand: `lees()` geeft `None` en geen fout (dan vraagt de pagina om de locatie);
  3. bewaren -> teruglezen: alle vastgelegde waarden exact gelijk, en `bijgewerkt` erbij;
  4. `nieuw` is waar bij de eerste keer bewaren en onwaar bij de tweede;
  5. een kapot bestand, geen JSON-object en een ontbrekend veld geven een regel in gewone taal;
  6. wat er geweigerd wordt bij het opslaan (lege naam, breedte 95, geen getal);
  7. een onbekende tijdzone is een **waarschuwing** en geen fout, en wordt bewaard zoals hij is.

Draaien:  /usr/bin/python3 ijking/ijk-instellingen.py
Schrijft: ijking/uitkomsten-<datum>-instellingen.md
"""

import datetime
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kern import instellingen, invoer, opslag  # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))
VANDAAG = datetime.date.today().isoformat()
NAAM = "instellingen"
PROEFMAP = os.path.expanduser("~/.hermes/cache/scratch/ijk-instellingen")
PROEF = os.path.join(PROEFMAP, "settings.json")

# De coördinaten zijn de **echte** van Dieren uit de plaatsenlijst (52,0512 / 6,103). Ze stonden hier
# tot 17 oktober 2026 op 52,05083 / 6,30972 - 14 km ernaast - en dat werd sinds de plaatscontrole in
# `kern/invoer.py` terecht geweigerd; de proefgegevens van een ijkpunt horen bij de bron te passen.
LOCATIE = dict(naam="Dieren", etiket="Dieren, Gelderland, NL",
               lat=52.0512, lon=6.103, tijdzone_id="Europe/Amsterdam")

regels = []
uit = []


def schrijf(t=""):
    regels.append(t)
    print(t)


def meldingen(fn, *a, **kw):
    """(uitkomst, meldingen) - roept fn aan en vangt de Nederlandse regels van een InvoerFout."""
    try:
        return fn(*a, **kw), []
    except invoer.InvoerFout as e:
        return None, e.meldingen


def vingerafdruk(pad):
    """(bestaat, sha256) van een bestand - om te bewijzen dat een run het niet heeft aangeraakt."""
    if not os.path.exists(pad):
        return (False, None)
    with open(pad, "rb") as f:
        return (True, hashlib.sha256(f.read()).hexdigest())


def main():
    if os.path.exists(PROEFMAP):
        shutil.rmtree(PROEFMAP)
    kaartenpad = os.path.join(opslag.STANDAARD_MAP, "settings.json")
    voor = vingerafdruk(kaartenpad)

    schrijf(f"# IJking van de instellingen - {VANDAAG}")
    schrijf()
    schrijf(f"Proefbestand: `{PROEF}` (de kaarten en instellingen van Jan in "
            f"`{opslag.STANDAARD_MAP}` blijven ongemoeid).")
    schrijf()

    # 1. het pad
    bewaard_env = os.environ.get("ASTRO_INSTELLINGEN")
    os.environ.pop("ASTRO_INSTELLINGEN", None)
    zonder = instellingen.bestandspad()
    os.environ["ASTRO_INSTELLINGEN"] = PROEF
    met_env = instellingen.bestandspad()
    met_argument = instellingen.bestandspad(PROEF)
    if bewaard_env is None:
        os.environ.pop("ASTRO_INSTELLINGEN", None)
    else:
        os.environ["ASTRO_INSTELLINGEN"] = bewaard_env
    schrijf("## 1. Het pad (één functie, met een omgevingsvariabele erover)")
    schrijf()
    schrijf(f"- zonder omgevingsvariabele: `{zonder}`")
    schrijf(f"- met `ASTRO_INSTELLINGEN`: `{met_env}`")
    schrijf(f"- met een expliciet pad: `{met_argument}`")
    goed1 = (zonder == os.path.join(opslag.kaartmap(), "settings.json")
             and met_env == PROEF and met_argument == PROEF)
    schrijf(f"- {'goed' if goed1 else 'FOUT'}: het bestand staat naast de kaarten, tenzij de "
            f"omgeving of de vraag iets anders zegt")
    uit.append(("pad", goed1))
    schrijf()

    # 2. nog geen bestand
    leeg, fout = meldingen(instellingen.lees, PROEF)
    schrijf("## 2. Nog niets ingesteld")
    schrijf()
    schrijf(f"- `lees()` op een onbekend bestand: {leeg!r}, fout: {fout or 'geen'} "
            f"({'goed' if leeg is None and not fout else 'FOUT'} - de pagina hoort hier om de "
            f"locatie te vragen)")
    uit.append(("geen_bestand", leeg is None and not fout))
    schrijf()

    # 3. bewaren en teruglezen
    os.makedirs(PROEFMAP, exist_ok=True)
    eerste = instellingen.bewaar(LOCATIE, PROEF)
    terug = instellingen.lees(PROEF)
    verschillen = []
    for sleutel in instellingen.SLEUTELS:
        if terug.get(sleutel) != LOCATIE[sleutel]:
            verschillen.append(f"{sleutel}: {LOCATIE[sleutel]!r} -> {terug.get(sleutel)!r}")
    schrijf("## 3. Bewaren en teruglezen")
    schrijf()
    schrijf(f"- bestand: `{eerste['bestand']}`, versie `{terug['versie']}`, "
            f"bijgewerkt `{terug['bijgewerkt']}`")
    schrijf(f"- {len(instellingen.SLEUTELS)} waarden vergeleken "
            f"({', '.join(instellingen.SLEUTELS)}): "
            f"{'alle gelijk' if not verschillen else 'WIJKT AF: ' + '; '.join(verschillen)}")
    schrijf(f"- breedte en lengte exact: {terug['lat'] == LOCATIE['lat'] and terug['lon'] == LOCATIE['lon']}")
    uit.append(("bewaren_gelijk", not verschillen))
    schrijf()
    schrijf("```json")
    schrijf(json.dumps(terug, ensure_ascii=False, indent=2))
    schrijf("```")
    schrijf()

    # 4. nieuw
    tweede = instellingen.bewaar(LOCATIE, PROEF)
    schrijf("## 4. Nieuw of bijgewerkt")
    schrijf()
    schrijf(f"- eerste keer: nieuw = {eerste['nieuw']} (moet True zijn); "
            f"tweede keer: nieuw = {tweede['nieuw']} (moet False zijn)")
    uit.append(("nieuw", eerste["nieuw"] is True and tweede["nieuw"] is False))
    schrijf()

    # 5. kapotte bestanden
    schrijf("## 5. Wat er met een kapot bestand gebeurt (geen 500, geen gok)")
    schrijf()
    schrijf("| wat er in het bestand staat | antwoord |")
    schrijf("|---|---|")
    gevallen = [("onzin", "dit is geen json"),
                ("een lijst in plaats van een object", "[1, 2, 3]"),
                ("een ontbrekend veld", json.dumps({k: v for k, v in LOCATIE.items()
                                                    if k != "tijdzone_id"})),
                ("een leeg object", "{}")]
    goed5 = 0
    for wat, inhoud in gevallen:
        with open(PROEF, "w", encoding="utf-8") as f:
            f.write(inhoud)
        _, fout = meldingen(instellingen.lees, PROEF)
        if fout:
            goed5 += 1
        schrijf(f"| {wat} | {' '.join(fout) if fout else 'geen fout gemeld - FOUT'} |")
    uit.append(("kapot_bestand", goed5 == len(gevallen)))
    schrijf()

    # 6. wat er geweigerd wordt bij het opslaan
    os.remove(PROEF)
    schrijf("## 6. Wat er bij het opslaan geweigerd wordt")
    schrijf()
    schrijf("| wat er ingevuld wordt | antwoord |")
    schrijf("|---|---|")
    onmogelijk = [("zonder plaatsnaam", dict(LOCATIE, naam="   ")),
                  ("breedte 95", dict(LOCATIE, lat=95)),
                  ("breedte 'abc'", dict(LOCATIE, lat="abc")),
                  ("lengte leeg", dict(LOCATIE, lon="")),
                  ("plaats die niet bij de coördinaten past", dict(LOCATIE, naam="Heerlen")),
                  ("geen lijst met velden", ["Dieren", 52.05])]
    goed6 = 0
    for wat, waarden in onmogelijk:
        _, fout = meldingen(instellingen.bewaar, waarden, PROEF)
        if fout:
            goed6 += 1
        schrijf(f"| {wat} | {' '.join(fout) if fout else 'geen fout gemeld - FOUT'} |")
    bestaat = os.path.exists(PROEF)
    schrijf()
    schrijf(f"- er is bij die {len(onmogelijk)} gevallen geen bestand geschreven: "
            f"{'ja' if not bestaat else 'NEE - FOUT'}")
    uit.append(("geweigerd", goed6 == len(onmogelijk) and not bestaat))
    schrijf()

    # 7. een onbekende zone
    onbekend = instellingen.bewaar(dict(LOCATIE, naam="Amsterdam-zone", tijdzone_id="Amsterdam"), PROEF)
    terug7 = instellingen.lees(PROEF)
    schrijf("## 7. Een onbekende tijdzone")
    schrijf()
    schrijf(f"- bewaard als `{terug7['tijdzone_id']}` (moet de ingevoerde naam blijven, geen stille "
            f"vervanging) en de waarschuwing mee: "
            f"{onbekend['waarschuwingen'] or 'geen waarschuwing - FOUT'}")
    uit.append(("onbekende_zone", terug7["tijdzone_id"] == "Amsterdam"
                and bool(onbekend["waarschuwingen"])))
    schrijf()

    # de kaartenmap is niet aangeraakt
    #
    # Tot 17 oktober 2026 stond hier `not os.path.exists(...)`: dat ging ervan uit dat Jan nog geen
    # settings.json had. Sinds hij zijn locatie op 15 oktober bewaarde, was deze meting altijd
    # MISLUKT zonder dat er iets mis was. Nu wordt het bestand vóór en ná vergeleken; dat meet wat
    # de meting bedoelt (deze run schrijft alleen in het proefbestand).
    na = vingerafdruk(kaartenpad)
    schrijf("## De kaartenmap van Jan")
    schrijf()
    schrijf(f"- `{kaartenpad}`: bestaat voor en na de run: {voor[0]} / {na[0]}, "
            f"inhoud {'gelijk' if voor == na else 'VERANDERD - FOUT'} "
            f"(sha256 {str(voor[1])[:12]})")
    uit.append(("kaartenmap_onberoerd", voor == na))

    # opruimen
    shutil.rmtree(PROEFMAP, ignore_errors=True)

    schrijf()
    schrijf("## Uitkomst")
    schrijf()
    geslaagd = [naam for naam, goed in uit if goed]
    mislukt = [naam for naam, goed in uit if not goed]
    schrijf(f"- {len(geslaagd)} van {len(uit)} metingen geslaagd"
            + (f"; MISLUKT: {', '.join(mislukt)}" if mislukt else ""))

    pad_md = os.path.join(HIER, f"uitkomsten-{VANDAAG}-{NAAM}.md")
    with open(pad_md, "w", encoding="utf-8") as f:
        f.write("\n".join(regels) + "\n")
    print()
    print(f"geschreven: {pad_md}")
    return 0 if not mislukt else 1


if __name__ == "__main__":
    raise SystemExit(main())
