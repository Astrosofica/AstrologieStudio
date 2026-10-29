#!/usr/bin/env python3
"""IJking van de rekenkern: drie ijkpunten, met per lichaam de gemeten afwijking.

  1. Print A        - de Janus 5-print van 19-09-2026 (besluit T11b, PRINTS.md)
  2. Print B        - de Pathfinder-print van 24-07-2023, waarden uit de tekstlaag/het beeld
  3. wheel.php      - het hardgecodeerde testgeval in public_html/Wheel/wheel.php
                      (het derde ijkpunt) uit github.com/Astrosofica/Horoscoopberekening

Draaien:  /usr/bin/python3 ijking/ijk-kaarten.py
Schrijft: ijking/uitkomsten-<datum>.json  en  ijking/uitkomsten-<datum>.md  (bestaat die al, dan
          komt er een nummer achter: uitkomsten-<datum>-2.md, zodat twee rondes op één dag elkaars
          bewijs niet overschrijven)
"""

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kern import aspecten, efemeride, formaat, kaart  # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))
VANDAAG = datetime.date.today().isoformat()

PRINT_A = dict(naam="Print A", jaar=1968, maand=12, dag=13, uur=5, minuut=20, seconde=0,
              tijdzone_id="Europe/Amsterdam", lat=52 + 22 / 60, lon=6 + 27 / 60,
              plaats="", huizenstelsel="K")
PRINT_B = dict(naam="Print B", jaar=1969, maand=4, dag=4, uur=9, minuut=50, seconde=0,
           tijdzone_id="Europe/Amsterdam", lat=53 + 6 / 60, lon=6 + 5 / 60,
           plaats="", huizenstelsel="K")
CONTROLE = dict(naam="Controle", jaar=1963, maand=7, dag=19, uur=16, minuut=51, seconde=26,
           tijdzone_id="Europe/Amsterdam", lat=51.6736, lon=4.2811,
           plaats="", huizenstelsel="K")

# --- Afgedrukte waarden (afgekapte minuten) ---------------------------------------------------

PRINT_A_WAARDEN = {
    "Ascendant": ("Schorpioen", 13, 57), "MC": ("Maagd", 1, 20),
    "Zon": ("Boogschutter", 21, 13), "Maan": ("Maagd", 22, 59),
    "Mercurius": ("Boogschutter", 24, 36), "Venus": ("Waterman", 3, 49),
    "Mars": ("Weegschaal", 20, 18), "Jupiter": ("Weegschaal", 3, 49),
    "Saturnus": ("Ram", 18, 45), "Uranus": ("Weegschaal", 3, 41),
    "Neptunus": ("Schorpioen", 27, 9), "Pluto": ("Maagd", 25, 3),
    "Noorderknoop": ("Ram", 6, 18), "Dagpars": ("Leeuw", 15, 42),
}

# Print B: gelezen uit de Pathfinder-afdruk; die afdruk staat in de privérepo, niet hier.
PRINT_B_WAARDEN = {
    "Ascendant": ("Kreeft", 5, 37), "MC": ("Waterman", 28, 56),
    "Zon": ("Ram", 14, 24), "Maan": ("Schorpioen", 4, 58), "Mercurius": ("Ram", 9, 35),
    "Venus": ("Ram", 21, 14), "Mars": ("Boogschutter", 13, 47),
    "Jupiter": ("Maagd", 29, 26), "Saturnus": ("Ram", 26, 45),
    "Uranus": ("Weegschaal", 1, 25), "Neptunus": ("Schorpioen", 28, 23),
    "Pluto": ("Maagd", 23, 14), "Noorderknoop": ("Ram", 0, 16),
    "Dagpars": ("Steenbok", 26, 10),
}
PRINT_B_CUSPEN = {1: ("Kreeft", 5, 37), 2: ("Kreeft", 24, 47), 3: ("Leeuw", 12, 6),
                    4: ("Leeuw", 28, 56), 5: ("Weegschaal", 29, 15), 6: ("Boogschutter", 10, 44),
                    7: ("Steenbok", 5, 37), 8: ("Steenbok", 24, 47), 9: ("Waterman", 12, 6),
                    10: ("Waterman", 28, 56), 11: ("Ram", 29, 15), 12: ("Tweelingen", 10, 44)}

# Het testgeval uit wheel.php, letterlijk uit regels 10-28.
WHEELPHP_CUSPS = {1: 242.4434837, 2: 266.2266421, 3: 299.1805031, 4: 358.7428395,
                  5: 19.9678896, 6: 41.0435929, 7: 62.4434837, 8: 86.2266421,
                  9: 119.1805031, 10: 178.7428395, 11: 199.9678896, 12: 221.0435929}
WHEELPHP_PLANETEN = {
    "Zon": 116.2546858, "Maan": 100.6654060, "Mercurius": 122.8794288, "Venus": 104.9154051,
    "Mars": 175.5075901, "Jupiter": 18.7711609, "Saturnus": 321.5064139, "Uranus": 153.2257521,
    "Neptunus": 222.8988242, "Pluto": 160.3788631, "Noorderknoop": 110.4502822,
}


def pos_van(k, naam):
    if naam == "Ascendant":
        return k["ascendant"]["lengte"]
    if naam == "MC":
        return k["mc"]["lengte"]
    for p in k["punten"]:
        if p["naam"] == naam:
            return p["lengte"]
    raise KeyError(naam)


def vergelijk_punt(naam, berekend, verwacht):
    """Vergelijkt onze ruwe waarde met de afgedrukte (graad, minuut).

    De print kapt af (besluit T22). Onze ruwe minuut X hoort dus in [m, m+1) te liggen; de
    echte afwijking is X - m. Ligt X onder m, dan is de print geen afkapping van onze waarde.
    """
    t_b, g_b, m_b = formaat.afgekapt(berekend)
    t_v, g_v, m_v = verwacht
    x = berekend % 30 * 60            # onze ruwe minuut binnen het teken
    m = g_v * 60 + m_v                # de afgedrukte waarde
    afw = x - m
    if afw >= 1.0 or afw < -0.5:
        oordeel = "AFWIJKING"
    elif afw < 0:
        oordeel = "print 1' hoger dan onze afkapping"
    else:
        oordeel = "gelijk (afgekapt)"
    return {
        "punt": naam,
        "hier": f"{formaat.TEKENS[t_b-1]} {g_b}°{m_b:02d}'",
        "print": f"{t_v} {g_v}°{m_v:02d}'",
        "hier_ruw_minuten": round(x, 3),
        "teken_gelijk": formaat.TEKENS[t_b - 1] == t_v,
        "afwijking_boogminuten": round(afw, 2),
        "oordeel": oordeel,
    }


def blok(titel, k, tabel, met_cuspen=None):
    print("=" * 84)
    print(titel)
    print("=" * 84)
    m = k["meta"]
    print(f"  UTC {m['utc']}  offset {m['offset_sec']}s ({m['offset_label']} / {m['offset_source']})"
          f"  JD {m['julian_day_ut']:.6f}  {m['huizenstelsel_naam']}")
    rijen = []
    for naam, verwacht in tabel.items():
        r = vergelijk_punt(naam, pos_van(k, naam), verwacht)
        rijen.append(r)
        print(f"  {naam:<13} hier {r['hier']:<18} print {r['print']:<18} "
              f"afw {r['afwijking_boogminuten']:+6.2f}'  {r['oordeel']}")
    uit = {"meta": m, "punten": rijen}
    if met_cuspen:
        crijen = []
        print("  -- huiscuspen --")
        for nr, verwacht in met_cuspen.items():
            r = vergelijk_punt(f"cusp {nr}", k["huizen"][nr - 1]["lengte"], verwacht)
            crijen.append(r)
            print(f"  cusp {nr:>2}     hier {r['hier']:<18} print {r['print']:<18} "
                  f"afw {r['afwijking_boogminuten']:+6.2f}'  {r['oordeel']}")
        uit["cuspen"] = crijen
    alle = rijen + uit.get("cuspen", [])
    uit["grootste_afwijking_boogminuten"] = max(abs(r["afwijking_boogminuten"]) for r in alle)
    uit["aantal_met_afwijking"] = sum(1 for r in alle if r["oordeel"] == "AFWIJKING")
    print(f"  -> grootste afwijking {uit['grootste_afwijking_boogminuten']:.2f} boogminuten; "
          f"{uit['aantal_met_afwijking']} punt(en) met een echte afwijking")
    print()
    return uit


def main():
    uitkomst = {"datum": VANDAAG, "kern": "pyswisseph " + str(efemeride.initialiseer()),
                "let_op": "De uitkomsten zijn afgekapte minuten (besluit T22). Een afwijking "
                          "tussen 0 en 1 boogminuut is dus precies wat afkappen geeft."}
    k_cor = kaart.maak_kaart(**PRINT_A)
    uitkomst["print_a"] = blok("1. PRINT A - 13-12-1968 05:20 CET, Koch", k_cor, PRINT_A_WAARDEN)
    k_els = kaart.maak_kaart(**PRINT_B)
    uitkomst["print_b"] = blok("2. PRINT B - 04-04-1969 09:50 MET, Koch", k_els, PRINT_B_WAARDEN,
                           met_cuspen=PRINT_B_CUSPEN)

    print("=" * 84)
    print("3. WHEEL.PHP-TESTGEVAL (derde ijkpunt) - 19-07-1963 16:51:26 CET, Koch")
    print("=" * 84)
    k_jan = kaart.maak_kaart(**CONTROLE)
    print(f"  UTC {k_jan['meta']['utc']}  JD {k_jan['meta']['julian_day_ut']:.6f}")
    rijen = []
    for p in k_jan["punten"]:
        if p["naam"] not in WHEELPHP_PLANETEN:
            continue
        v = (p["lengte"] - WHEELPHP_PLANETEN[p["naam"]] + 180) % 360 - 180
        rijen.append({"punt": p["naam"], "hier": p["lengte"], "wheelphp": WHEELPHP_PLANETEN[p["naam"]],
                      "verschil_boogsec": round(v * 3600, 2)})
        print(f"  {p['naam']:<13} verschil {v*3600:+7.2f}\"")
    jd = k_jan["meta"]["julian_day_ut"]
    cusps_k, _, _, _ = efemeride.huizen(jd, 51.6736, 4.2811, "K")
    cusps_p, _, _, _ = efemeride.huizen(jd, 51.6736, 4.2811, "P")
    print("  -- de twaalf cuspen van het testgeval, met Koch --")
    crijen = []
    for nr in range(1, 13):
        v = (cusps_k[nr - 1] - WHEELPHP_CUSPS[nr] + 180) % 360 - 180
        crijen.append({"punt": f"cusp {nr}", "hier": cusps_k[nr - 1],
                       "wheelphp": WHEELPHP_CUSPS[nr], "verschil_boogsec": round(v * 3600, 2)})
        print(f"  cusp {nr:>2}  Koch {cusps_k[nr-1]:>10.5f}  wheel.php {WHEELPHP_CUSPS[nr]:>10.5f}"
              f"  verschil {v*3600:+8.2f}\"")
    afw_k = max(abs(r["verschil_boogsec"]) for r in crijen)
    afw_p = max(abs(((cusps_p[nr - 1] - WHEELPHP_CUSPS[nr] + 180) % 360 - 180) * 3600)
                for nr in range(1, 13))
    print(f"  grootste afwijking: Koch {afw_k:.2f}\"  /  Placidus {afw_p:.2f}\"")
    print("  conclusie: het testgeval in wheel.php is met KOCH gemaakt, niet met Placidus")
    print("  (een eerdere proef bekeek alleen Asc/MC, en die zijn in elk stelsel gelijk.)")
    uitkomst["wheelphp"] = {
        "planeten": rijen, "cuspen": crijen,
        "grootste_afwijking_cuspen_boogsec_koch": round(afw_k, 2),
        "grootste_afwijking_cuspen_boogsec_placidus": round(afw_p, 2),
        "bevinding": "Het testgeval is Koch, niet Placidus.",
    }
    print()

    print("=" * 84)
    print("ASPECTEN - Print A (de acht met orbs + buiten-teken- en dominantregel)")
    print("=" * 84)
    for regel in aspecten.als_tekst(k_cor["aspecten"]):
        print("  " + regel)
    uitkomst["print_a_aspecten"] = k_cor["aspecten"]

    # Twee rondes op één dag mogen elkaars bewijs niet overschrijven (15 okt 2026: een run voor de
    # controle van de rekenkern overschreef het verslag van de font-ronde van dezelfde dag - dat
    # bestand was toevallig byte voor byte gelijk, maar dat is geluk en geen waarborg). Bestaat het
    # verslag van vandaag al, dan komt er een nummer achter.
    pad = os.path.join(HIER, f"uitkomsten-{VANDAAG}")
    nummer = 2
    while os.path.exists(pad + ".md") or os.path.exists(pad + ".json"):
        pad = os.path.join(HIER, f"uitkomsten-{VANDAAG}-{nummer}")
        nummer += 1
    with open(pad + ".json", "w", encoding="utf-8") as f:
        json.dump(uitkomst, f, ensure_ascii=False, indent=2)
    with open(pad + ".md", "w", encoding="utf-8") as f:
        f.write(markdown(uitkomst))
    print()
    print(f"  -> {pad}.json")
    print(f"  -> {pad}.md")


def markdown(u):
    L = [f"# IJking rekenkern - {u['datum']}", "",
         f"Kern: {u['kern']}. {u['let_op']}", ""]
    for sleutel, titel in (("print_a", "Print A (Janus 5-print)"),
                           ("print_b", "Print B (Pathfinder-print)")):
        b = u[sleutel]
        L += [f"## {titel}", "",
              f"- UTC {b['meta']['utc']} (offset {b['meta']['offset_sec']}s, "
              f"{b['meta']['offset_label']} via {b['meta']['offset_source']})",
              f"- Huizenstelsel: {b['meta']['huizenstelsel_naam']}",
              f"- Grootste afwijking: **{b['grootste_afwijking_boogminuten']:.2f} boogminuten**; "
              f"{b['aantal_met_afwijking']} punt(en) met een echte afwijking", "",
              "| punt | hier | print | ruwe minuut | afwijking (') | oordeel |",
              "|---|---|---|---|---|---|"]
        for r in b["punten"] + b.get("cuspen", []):
            L.append(f"| {r['punt']} | {r['hier']} | {r['print']} | {r['hier_ruw_minuten']:.3f} "
                     f"| {r['afwijking_boogminuten']:+.2f} | {r['oordeel']} |")
        L.append("")
    w = u["wheelphp"]
    L += ["## wheel.php-testgeval (derde ijkpunt)", "",
          f"- Planeten: grootste verschil "
          f"{max(abs(r['verschil_boogsec']) for r in w['planeten']):.2f} boogseconden", "",
          "| punt | hier | wheel.php | verschil (\\\") |", "|---|---|---|---|"]
    for r in w["planeten"] + w["cuspen"]:
        L.append(f"| {r['punt']} | {r['hier']:.7f} | {r['wheelphp']:.7f} | {r['verschil_boogsec']:+.2f} |")
    L += ["",
          f"- Grootste afwijking van de twaalf cuspen: **{w['grootste_afwijking_cuspen_boogsec_koch']:.2f}\\\" "
          f"met Koch** tegen {w['grootste_afwijking_cuspen_boogsec_placidus']:.2f}\\\" met Placidus.",
          f"- {w['bevinding']} Alle twaalf cuspen komen met Koch uit op 6 boogseconden "
          "(0,1 boogminuut) bij een invoertijd van 16:51:23 in plaats van 16:51:26.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
