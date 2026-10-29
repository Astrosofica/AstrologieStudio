#!/usr/bin/env python3
"""IJking van de opslag (etappe 2, 14 oktober 2026): bewaren, openen en verwijderen.

Alles gebeurt in een **proefmap** (`~/astrologie-horoscopen-proef`), zodat de horoscopen van Jan in
`~/astrologie-horoscopen` niet geraakt worden. Zeven metingen:

  1. bewaren -> teruglezen levert precies dezelfde kaart (alle punten, huizen en aspecten);
  2. de index bewaart het huizenstelsel als **letter** (K) en houdt `met_chiron` bij;
  3. nog eens bewaren is bijwerken, geen tweede regel;
  4. Chiron aan: kaart, bestand en index houden dat vast;
  5. de rondgang kaart -> meta -> lezer -> kaart geeft 0,000000 boogseconde (openen = opnieuw
     rekenen, en dat is precies wat de pagina doet);
  6. verwijderen haalt het bestand én de regel weg;
  7. een onbekende kaart of een bestandsnaam met een pad wordt geweigerd (geen 500, geen
     bestand buiten de map).

Draaien:  /usr/bin/python3 ijking/ijk-opslag.py
Schrijft: ijking/uitkomsten-<datum>-opslag.md
"""

import datetime
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kern import invoer, kaart, opslag  # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))
VANDAAG = datetime.date.today().isoformat()
PROEFMAP = os.path.expanduser("~/astrologie-horoscopen-proef")

CONTROLE = dict(naam="Controle", datum="1963-07-19", tijd="16:51:26", plaats="Controleplaats",
           lat=51.6736, lon=4.2811, tijdzone_id="Europe/Amsterdam", huizenstelsel="K")


def maak(vraag):
    g = invoer.lees(vraag)
    return kaart.maak_kaart(naam=g["naam"], jaar=g["jaar"], maand=g["maand"], dag=g["dag"],
                            uur=g["uur"], minuut=g["minuut"], seconde=g["seconde"],
                            tijdzone_id=g["tijdzone_id"], lat=g["lat"], lon=g["lon"],
                            plaats=g["plaats"], huizenstelsel=g["huizenstelsel"],
                            tijdcorrectie=g["tijdcorrectie"], met_chiron=g["met_chiron"])


def verschillen(a, b):
    """Grootste verschil in boogseconde tussen twee kaarten, plus aantal vergeleken velden."""
    grootste, aantal = 0.0, 0
    for p, q in zip(a["punten"], b["punten"]):
        grootste = max(grootste, abs(p["lengte"] - q["lengte"])); aantal += 1
    for p, q in zip(a["huizen"], b["huizen"]):
        grootste = max(grootste, abs(p["lengte"] - q["lengte"])); aantal += 1
    for p, q in zip(a["aspecten"], b["aspecten"]):
        grootste = max(grootste, abs(p["orb"] - q["orb"])); aantal += 1
    return grootste * 3600, aantal


def main():
    if os.path.exists(PROEFMAP):
        shutil.rmtree(PROEFMAP)
    regels, uit = [], []

    def schrijf(t=""):
        regels.append(t)
        print(t)

    schrijf(f"# IJking van de opslag - {VANDAAG}")
    schrijf()
    schrijf(f"Proefmap: `{PROEFMAP}` (de horoscopen van Jan in `~/astrologie-horoscopen` blijven ongemoeid).")
    schrijf()

    # 1. bewaren en teruglezen
    k = maak(CONTROLE)
    pad, nieuw, _id = opslag.bewaar(k, PROEFMAP)
    terug = opslag.lees(os.path.basename(pad), PROEFMAP)
    seconden, velden = verschillen(k, terug)
    schrijf("## 1. Bewaren en teruglezen")
    schrijf()
    schrijf(f"- bestand: `{os.path.basename(pad)}`, nieuw = {nieuw}")
    schrijf(f"- {velden} velden vergeleken (punten, huizen, aspecten): grootste afwijking "
            f"**{seconden:.6f} boogseconde** ({'gelijk' if seconden < 0.001 else 'WIJKT AF'})")
    uit.append({"bewaren_gelijk": seconden < 0.001, "velden": velden})

    # 2. de index
    index = opslag.lijst(PROEFMAP)
    regel = index[0]
    schrijf()
    schrijf("## 2. De index")
    schrijf()
    schrijf(f"- huizenstelsel in de index: `{regel['huizenstelsel']}` "
            f"(moet de letter zijn, want dat is wat de kern verwacht) en de naam "
            f"`{regel['huizenstelsel_naam']}` staat ernaast voor het scherm")
    schrijf(f"- velden: {', '.join(regel.keys())}")
    goed = regel["huizenstelsel"] == "K" and "met_chiron" in regel
    schrijf(f"- letter en `met_chiron` aanwezig: {'ja' if goed else 'nee'}")
    uit.append({"index_letter": goed})
    schrijf()
    schrijf("```json")
    for r in index:
        schrijf(json.dumps(r, ensure_ascii=False))
    schrijf("```")

    # 3. nog eens bewaren: sinds 8ec0106 is elke Bewaren een **nieuwe** horoscoop met een eigen id;
    #    alleen Aanpassen overschrijft de openstaande kaart, via `vervang=<id>`. Deze meting stond nog
    #    op de oude regel ("tweede keer bewaren = bijwerken") en was daardoor stil stuk.
    pad2, nieuw2, id2 = opslag.bewaar(k, PROEFMAP)
    index2 = opslag.lijst(PROEFMAP)
    pad2b, nieuw2b, _id2b = opslag.bewaar(k, PROEFMAP, vervang=id2)
    index2b = opslag.lijst(PROEFMAP)
    schrijf()
    schrijf("## 3. Nog eens bewaren, en overschrijven met `vervang`")
    schrijf()
    schrijf(f"- tweede keer Bewaren zonder `vervang`: nieuw = {nieuw2} (moet True zijn), "
            f"regels in de index: {len(index2)} (moet 2 zijn), tweede bestand: "
            f"`{os.path.basename(pad2)}`")
    schrijf(f"- daarna Bewaren met `vervang={id2}` (wat Aanpassen doet): nieuw = {nieuw2b} "
            f"(moet False zijn), zelfde bestand: {pad2b == pad2}, regels: {len(index2b)} "
            f"(moet 2 blijven)")
    uit.append({"bijwerken": (nieuw2 is True and len(index2) == 2 and nieuw2b is False
                             and pad2b == pad2 and len(index2b) == 2)})

    # 4. Chiron
    kc = maak(dict(CONTROLE, naam="Proef met Chiron", met_chiron=True))
    padc, _nieuw, _idc = opslag.bewaar(kc, PROEFMAP)
    terugc = opslag.lees(os.path.basename(padc), PROEFMAP)
    namen = [p["naam"] for p in terugc["punten"]]
    regelc = [r for r in opslag.lijst(PROEFMAP) if r["bestand"] == os.path.basename(padc)][0]
    schrijf()
    schrijf("## 4. Chiron")
    schrijf()
    schrijf(f"- `meta.met_chiron` in het bestand: {terugc['meta']['met_chiron']}, "
            f"in de index: {regelc['met_chiron']}, Chiron in de punten: {'Chiron' in namen} "
            f"({len(namen)} punten)")
    uit.append({"chiron_vastgehouden": terugc["meta"]["met_chiron"] and "Chiron" in namen})

    # 5. openen = opnieuw rekenen vanaf de meta
    from_meta = maak(dict(terug["meta"], naam=terug["meta"]["naam"], met_chiron=terug["meta"]["met_chiron"]))
    seconden2, velden2 = verschillen(terug, from_meta)
    schrijf()
    schrijf("## 5. Openen is opnieuw rekenen")
    schrijf()
    schrijf(f"- de meta van de bewaarde kaart door de lezer en de kern gehaald: {velden2} velden, "
            f"grootste afwijking **{seconden2:.6f} boogseconde** "
            f"({'gelijk' if seconden2 < 0.001 else 'WIJKT AF'})")
    schrijf("- (dit is wat de pagina doet bij openen: het formulier vullen uit de meta en opnieuw")
    schrijf("  rekenen, zodat een oude kaart niet met verouderde standen op het scherm komt)")
    uit.append({"openen_gelijk": seconden2 < 0.001})

    # 6. verwijderen
    weg = opslag.verwijder(os.path.basename(pad2), PROEFMAP)
    bestaat = os.path.exists(os.path.join(PROEFMAP, os.path.basename(pad2)))
    index3 = opslag.lijst(PROEFMAP)
    schrijf()
    schrijf("## 6. Verwijderen")
    schrijf()
    schrijf(f"- `{weg}` verwijderd; bestand nog aanwezig: {bestaat} (moet False zijn); "
            f"regels in de index: {len(index3)} (was 3, moet 2 zijn: de eerste kaart en de "
            f"Chiron-proef)")
    uit.append({"verwijderen": (not bestaat and len(index3) == 2)})

    # 7. wat geweigerd wordt
    schrijf()
    schrijf("## 7. Wat geweigerd wordt (geen 500, geen bestand buiten de map)")
    schrijf()
    schrijf("| wat er gevraagd wordt | antwoord |")
    schrijf("|---|---|")
    gevallen = [("lees", "../astrologie-horoscopen/index.json"),
                ("lees", "/etc/passwd"),
                ("lees", "index.json"),
                ("lees", "geen-kaart.json"),
                ("verwijder", "geen-kaart.json"),
                ("verwijder", "sub/kaart.json")]
    goed7 = 0
    for wat, bestand in gevallen:
        try:
            if wat == "lees":
                opslag.lees(bestand, PROEFMAP)
            else:
                opslag.verwijder(bestand, PROEFMAP)
            schrijf(f"| {wat} `{bestand}` | geen fout gemeld - FOUT |")
        except invoer.InvoerFout as e:
            goed7 += 1
            schrijf(f"| {wat} `{bestand}` | {' '.join(e.meldingen)} |")
    uit.append({"geweigerd": goed7, "van": len(gevallen)})
    schrijf()

    # opruimen
    shutil.rmtree(PROEFMAP, ignore_errors=True)

    schrijf("## Uitkomst")
    schrijf()
    alles = (uit[0]["bewaren_gelijk"] and uit[1]["index_letter"] and uit[2]["bijwerken"]
             and uit[3]["chiron_vastgehouden"] and uit[4]["openen_gelijk"] and uit[5]["verwijderen"]
             and goed7 == len(gevallen))
    schrijf(f"- alle zeven metingen: **{'geslaagd' if alles else 'NIET GESLAAGD'}** "
            f"({goed7} van {len(gevallen)} gevallen geweigerd)")

    pad_md = os.path.join(HIER, f"uitkomsten-{VANDAAG}-opslag.md")
    with open(pad_md, "w", encoding="utf-8") as f:
        f.write("\n".join(regels) + "\n")
    print()
    print(f"geschreven: {pad_md}")
    return 0 if alles else 1


if __name__ == "__main__":
    raise SystemExit(main())
