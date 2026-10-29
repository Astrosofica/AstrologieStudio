#!/usr/bin/env python3
"""IJking van de plaatsenlijst (14 oktober 2026): klopt wat er in staat en wat eruit komt.

Zeven metingen:
  1. de lijst laadt: aantallen per bron, gebouwd op welke datum, elke plaats een zone, en de tijd
     die het inlezen kost;
  2. de eigen aanvullingen (het eigen bestand in de gebruikersmap) komen erover heen: een
     proefplaats wordt
     gevonden, staat bovenaan en houdt zijn eigen zone - en de zone valt terug op die van het land
     als hij niet is ingevuld;
  3. de plaatsen zijn **letterlijk** die van GeoNames: per plaats wordt de regel uit het
     bronbestand opgezocht en vergeleken;
  4. zoeken: de precieze naam eerst, dan wat ermee begint, dan wat het bevat; de Nederlandse namen
     van buitenlandse steden (Antwerpen, Luik, Keulen, Londen, Wenen, Parijs) en de grootste plaats
     eerst;
  5. alles binnen bereik: breedte -90..90, lengte -180..180, geen lege naam of zone;
  6. **de etiketten** (14 oktober 2026): hoeveel plaatsen een streek en een gemeente hebben, de
     voorbeelden zoals de keuzelijst ze toont, en hoeveel gelijknamige plaatsen in Nederland en
     Belgie er met (naam, land, streek, gemeente) nog niet te onderscheiden zijn;
  7. de tijd: het gewone zoeken (microseconden) tegen het zoeken dat de hele lijst moet doorlopen.

Draaien:  /usr/bin/python3 ijking/ijk-plaatsen.py
Schrijft: ijking/uitkomsten-<datum>-<naam>.md
"""

import datetime
import os
import shutil
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kern import plaatsen  # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HIER)
VANDAAG = datetime.date.today().isoformat()
NAAM = "plaatsen-en-etiketten"    # het verslag van deze ronde (14 okt: de streek en de gemeente)
BRONMAP = os.path.expanduser("~/.hermes/cache/scratch/plaatsen")
# Het eigen bestand staat sinds 20 oktober 2026 in de gebruikersmap en niet meer in de projectmap
# (zie kern/paden.py); deze ijk gebruikt hetzelfde pad als het programma, anders toetst hij een
# bestand dat niemand meer leest.
EIGEN = plaatsen.EIGEN

# Zoekproeven: wat er getypt wordt, en hoe de eerste treffer hoort te zijn.
ZOEKPROEVEN = [
    ("dieren", "Dieren", "NL"),
    ("dier", "Dieren", "NL"),
    ("achthuizen", "Achthuizen", "NL"),
    ("amsterdam", "Amsterdam", "NL"),
    ("antwerpen", "Antwerp", "BE"),
    ("luik", "Liège", "BE"),
    ("keulen", "Köln", "DE"),
    ("londen", "London", "GB"),
    ("wenen", "Vienna", "AT"),
    ("parijs", "Paris", "FR"),
    ("brussel", "Brussels", "BE"),
    ("thuizen", None, None),
]

# Vergelijking met het bronbestand: gezochte naam -> (plek in de bron, kolom met de gezochte naam).
BRONPROEVEN = ["Achthuizen", "Dieren", "Doesburg", "Amsterdam", "Brussel", "Gent", "Antwerpen"]


def lees_bron():
    """Alle bewoonde plaatsen uit de GeoNames-bestanden, als [(naam, lat, lon, land, zone)]."""
    uit = []
    for zipnaam, lid in (("NL.zip", "NL.txt"), ("BE.zip", "BE.txt"),
                         ("cities15000.zip", "cities15000.txt")):
        pad = os.path.join(BRONMAP, zipnaam)
        if not os.path.exists(pad):
            continue
        with zipfile.ZipFile(pad) as z, z.open(lid) as f:
            for regel in f.read().decode("utf-8").splitlines():
                r = regel.split("\t")
                if len(r) > 17 and (r[6] == "P" or r[7].startswith("PPL")):
                    uit.append((r[1], round(float(r[4]), 5), round(float(r[5]), 5), r[8], r[17]))
    return uit


def main():
    regels, uit = [], []

    def schrijf(t=""):
        regels.append(t)
        print(t)

    schrijf(f"# IJking van de plaatsenlijst - {VANDAAG}")
    schrijf()
    schrijf("Bron: GeoNames (CC BY 4.0), gebouwd met `data/maak-plaatsen.py`. De eigen aanvullingen")
    schrijf("in `%s` komen er in `kern/plaatsen.py` overheen." % EIGEN)
    schrijf()

    # 1. de lijst
    t0 = time.perf_counter()
    lijst, namen, sleutels = plaatsen.laad()
    t1 = time.perf_counter()
    info = plaatsen.bron()
    zonder_zone = [p for p in lijst if not p[4]]
    schrijf("## 1. De lijst")
    schrijf()
    schrijf(f"- gebouwd: {info.get('gebouwd')}; bron: {info.get('bron')}")
    schrijf(f"- licentie: {info.get('licentie')}")
    schrijf(f"- {len(lijst)} plaatsen in {len(namen)} namen; per bron: "
            + ", ".join(f"{k} {v}" for k, v in (info.get("aantallen") or {}).items()))
    schrijf(f"- plaatsen zonder zone: {len(zonder_zone)}")
    schrijf(f"- inlezen uit het bestand: {(t1 - t0) * 1000:.0f} ms "
            f"({os.path.getsize(plaatsen.BESTAND) / 1e6:.1f} MB)")
    uit.append({"plaatsen": len(lijst), "namen": len(namen), "zonder_zone": len(zonder_zone)})

    # 2. eigen aanvullingen
    schrijf()
    schrijf("## 2. Eigen aanvullingen (`%s`)" % EIGEN)
    schrijf()
    bewaard = None
    if os.path.exists(EIGEN):
        bewaard = EIGEN + ".ijk-bewaard"
        shutil.copy(EIGEN, bewaard)
    try:
        with open(EIGEN, "w", encoding="utf-8") as f:
            f.write("# proefregels van de ijking\n"
                    "Proefdorp\t52.1234\t6.4321\tNL\t\n"
                    "Proefgehucht\t51.5\t4.9\tBE\tEurope/Brussels\n")
        treffer = plaatsen.vind("Proefdorp")
        treffer2 = plaatsen.vind("Proefgehucht")
        goed = bool(treffer and treffer["eigen"] and treffer["lat"] == 52.1234
                    and treffer["zone"] == "Europe/Amsterdam"
                    and treffer2 and treffer2["zone"] == "Europe/Brussels")
        schrijf(f"- Proefdorp zonder zone -> `{treffer['zone'] if treffer else '-'}` "
                f"(valt terug op het land NL)")
        schrijf(f"- Proefgehucht met eigen zone -> `{treffer2['zone'] if treffer2 else '-'}`")
        schrijf(f"- eigen aanvulling komt bovenaan en houdt zijn coordinaten: "
                f"{'ja' if goed else 'NEE'}")
        uit.append({"eigen_plaatsen": goed})
    finally:
        if bewaard:
            shutil.move(bewaard, EIGEN)
        elif os.path.exists(EIGEN):
            os.remove(EIGEN)

    # 3. letterlijk gelijk aan de bron
    schrijf()
    schrijf("## 3. De plaatsen tegen het bronbestand")
    schrijf()
    bron = lees_bron()
    if not bron:
        schrijf(f"- de bronbestanden staan niet in {BRONMAP}; deze meting is overgeslagen.")
        uit.append({"letterlijk_gelijk": None})
    else:
        schrijf("| gezocht | hier | in GeoNames | gelijk? |")
        schrijf("|---|---|---|---|")
        alles_gelijk = True
        for gezocht in BRONPROEVEN:
            t = plaatsen.vind(gezocht)
            if not t:
                schrijf(f"| {gezocht} | niet gevonden | | nee |")
                alles_gelijk = False
                continue
            in_bron = [b for b in bron if b[0] == t["naam"] and b[1] == t["lat"] and b[2] == t["lon"]]
            gelijk = bool(in_bron) and in_bron[0][3] == t["land"] and in_bron[0][4] == t["zone"]
            alles_gelijk = alles_gelijk and gelijk
            schrijf(f"| {gezocht} | {t['naam']} {t['lat']}, {t['lon']} | "
                    + (f"{in_bron[0][0]} {in_bron[0][1]}, {in_bron[0][2]}" if in_bron else
                       "deze naam staat er niet met deze coordinaten")
                    + f" | {'ja' if gelijk else 'nee'} |")
        schrijf()
        schrijf(f"- alle {len(BRONPROEVEN)} plaatsen letterlijk gelijk aan GeoNames: "
                f"{'ja' if alles_gelijk else 'NEE'}")
        uit.append({"letterlijk_gelijk": alles_gelijk})

    # 4. zoeken
    schrijf()
    schrijf("## 4. Zoeken")
    schrijf()
    schrijf("| getypt | eerste treffer | land | aantal | goed? |")
    schrijf("|---|---|---|---|---|")
    zoek_goed = 0
    for tekst, naam, land in ZOEKPROEVEN:
        treffers = plaatsen.zoek(tekst)
        eerste = treffers[0] if treffers else None
        goed = (eerste is not None) if naam is None else \
            (eerste is not None and eerste["naam"] == naam and eerste["land"] == land)
        zoek_goed += 1 if goed else 0
        schrijf(f"| `{tekst}` | {eerste['naam'] if eerste else '-'} | "
                f"{eerste['land'] if eerste else '-'} | {len(treffers)} | {'ja' if goed else 'nee'} |")
    schrijf()
    schrijf(f"- {zoek_goed} van {len(ZOEKPROEVEN)} zoekproeven met de verwachte eerste treffer "
            f"(de Nederlandse namen van buitenlandse steden komen uit de naamsvarianten van GeoNames)")
    uit.append({"zoek_goed": zoek_goed, "zoek_van": len(ZOEKPROEVEN)})

    # 5. binnen bereik
    schrijf()
    schrijf("## 5. Alles binnen bereik")
    schrijf()
    fout = [p for p in lijst
            if not p[0] or not (-90 <= p[1] <= 90) or not (-180 <= p[2] <= 180) or not p[4]]
    schrijf(f"- {len(lijst)} plaatsen gecontroleerd op naam, bereik en zone: {len(fout)} "
            f"onvolkomenheid(en)" + ("" if not fout else ": " + ", ".join(p[0] for p in fout[:5])))
    uit.append({"binnen_bereik": not fout})

    # 6. de etiketten: streek en gemeente (14 oktober 2026)
    schrijf()
    schrijf("## 6. De etiketten: streek en gemeente")
    schrijf()
    schrijf("Gelijknamige plaatsen zijn anders alleen aan hun coordinaten te onderscheiden. Elke plaats")
    schrijf("krijgt daarom een streek en een gemeente mee, per land uit het veld waar de bron ze heeft")
    schrijf("(Nederland: provincie en gemeente; Belgie: provincie uit adm2 en gemeente uit adm4; elders")
    schrijf("de adm1-naam). Het label laat de gemeente alleen zien als die anders heet dan de plaats.")
    schrijf()
    per_land = {}
    for p in lijst:
        d = per_land.setdefault(p[3], {"plaatsen": 0, "streek": 0, "gemeente": 0})
        d["plaatsen"] += 1
        d["streek"] += 1 if plaatsen._streek(p, 6) else 0
        d["gemeente"] += 1 if plaatsen._streek(p, 7) else 0
    schrijf("| land | plaatsen | met streek | met gemeente |")
    schrijf("|---|---|---|---|")
    for land in sorted(per_land, key=lambda l: -per_land[l]["plaatsen"])[:6]:
        d = per_land[land]
        schrijf(f"| {land} | {d['plaatsen']} | {d['streek']} | {d['gemeente']} |")
    schrijf()
    zonder_streek = [p for p in lijst if not plaatsen._streek(p, 6)]
    zonder_gemeente = [p for p in lijst if p[3] in ("NL", "BE") and not plaatsen._streek(p, 7)]
    schrijf(f"- plaatsen zonder streek: {len(zonder_streek)} van {len(lijst)} "
            f"(waarvan {sum(1 for p in zonder_streek if p[3] in ('NL', 'BE'))} in NL en BE: "
            f"{', '.join(p[0] for p in zonder_streek if p[3] in ('NL', 'BE'))[:120]})")
    schrijf(f"- plaatsen in NL en BE zonder gemeente: {len(zonder_gemeente)} "
            f"(de bron heeft daar geen gemeentecode; ze houden hun provincie)")
    schrijf()
    schrijf("De voorbeelden, zoals de keuzelijst ze toont:")
    schrijf()
    schrijf("| gezocht | het label | inwoners |")
    schrijf("|---|---|---|")
    for naam in ("Hengelo", "Bergen", "Rozendaal", "Doesburg", "Dieren"):
        for t in plaatsen.zoek(naam)[:4]:
            if t["naam"].lower() == naam.lower():
                schrijf(f"| {naam} | {t['etiket']} | {t['inwoners'] or '-'} |")
    schrijf()

    # de dubbele namen: hoeveel groepen zijn er nog niet te onderscheiden?
    per_naam = {}
    for p in lijst:
        if p[3] in ("NL", "BE"):
            per_naam.setdefault(p[0], []).append(p)
    dubbel = {n: v for n, v in per_naam.items() if len(v) > 1}
    groepen = {}
    for n, v in dubbel.items():
        for p in v:
            groepen.setdefault((n, p[3], plaatsen._streek(p, 6), plaatsen._streek(p, 7)),
                               []).append(p)
    rest = {k: v for k, v in groepen.items() if len(v) > 1}
    met_inwoners = {k: v for k, v in rest.items() if any(x[5] for x in v)}
    schrijf(f"- gelijknamige plaatsen in NL en BE: {len(dubbel)} namen, "
            f"{sum(len(v) for v in dubbel.values())} plaatsen")
    schrijf(f"- daarvan nog niet te onderscheiden met (naam, land, streek, gemeente): "
            f"{len(rest)} groepen ({sum(len(v) for v in rest.values())} plaatsen); "
            f"daarvan {len(met_inwoners)} groepen waar een plaats met inwoners in zit")
    for k, v in sorted(met_inwoners.items(), key=lambda kv: -max(x[5] for x in kv[1]))[:5]:
        schrijf(f"    - {k[0]}, {k[2]}, {k[3]}, {k[1]}: "
                + ", ".join(f"{x[5] or 0} inwoners ({x[1]}, {x[2]})" for x in v))
    schrijf()
    etiket_goed = all(plaatsen.etiket(p).strip() for p in lijst)
    schrijf(f"- elk van de {len(lijst)} labels is niet leeg: {'ja' if etiket_goed else 'nee'}")
    uit.append({"etiketten_leeg": not etiket_goed, "dubbel_nog": len(rest)})

    # 7. de tijd
    schrijf()
    schrijf("## 7. De tijd")
    schrijf()
    for tekst, lbl in (("dieren", "gewone zoekopdracht (naam begint ermee)"),
                       ("thuizen", "zoekopdracht die de hele lijst moet doorlopen")):
        t0 = time.perf_counter()
        for _ in range(20):
            plaatsen.zoek(tekst)
        t1 = time.perf_counter()
        schrijf(f"- {lbl}: {(t1 - t0) * 1000 / 20:.2f} ms per keer")
    schrijf("- (de pagina wacht 150 ms na de laatste toets, dus dit valt ruim binnen het typen)")

    schrijf()
    # Punt 3 kan overgeslagen zijn (de GeoNames-bronbestanden staan niet in de scratch-map): dan is
    # `letterlijk_gelijk` None. Dat is geen mislukking maar een meting die niet gedraaid heeft — een
    # `and None` maakte hier eerder ten onrechte "NIET GESLAAGD" van (gezien 20 okt 2026, bij een
    # ronde die niets met de plaatsenlijst te maken had).
    bron_gedaan = uit[2].get("letterlijk_gelijk") is not None
    alles = (uit[0]["zonder_zone"] == 0 and uit[1].get("eigen_plaatsen")
             and uit[2].get("letterlijk_gelijk") in (True, None)
             and uit[3]["zoek_goed"] == uit[3]["zoek_van"] and uit[4]["binnen_bereik"]
             and not uit[5]["etiketten_leeg"])
    schrijf("## Uitkomst")
    schrijf()
    schrijf(f"- de lijst, de eigen aanvullingen, de namen, de etiketten en de controles: "
            f"**{'geslaagd' if alles else 'NIET GESLAAGD'}**"
            + ("" if bron_gedaan else " (punt 3 overgeslagen: de bronbestanden staan er niet)"))
    schrijf(f"- nog niet te onderscheiden gelijknamige plaatsen in NL en BE: {uit[5]['dubbel_nog']} "
            f"groepen (zie punt 6; de rest zijn gehuchten zonder inwonertal)")

    pad_md = os.path.join(HIER, f"uitkomsten-{VANDAAG}-{NAAM}.md")
    with open(pad_md, "w", encoding="utf-8") as f:
        f.write("\n".join(regels) + "\n")
    print()
    print(f"geschreven: {pad_md}")
    return 0 if alles else 1


if __name__ == "__main__":
    raise SystemExit(main())
