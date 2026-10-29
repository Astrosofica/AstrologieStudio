#!/usr/bin/env python3
"""IJking van de invoer (etappe 1, 14 oktober 2026): wat er in gaat komt er heel uit.

Drie metingen:
  1. de invoer die een mens intypt (16:51 zonder seconden, 19-07-1963, 51,675, 51°40' N,
     "Koch" als naam) wordt aanvaard en levert dezelfde kaart als de paginavorm;
  2. invoer die niet klopt geeft een regel in gewone taal - geen 500 en geen Engelse fout;
  3. de rekenkern zelf is niet veranderd: Jans bewaarde kaart komt punt voor punt op 0,000000°
     uit, gerekend uit **zijn eigen** meta (de reparatie mag aan de cijfers niets raken), plus
     wat een verschil met de proefgegevens van dit ijkpunt veroorzaakt (de coordinaten) en of die
     kaart met de efemeriden of met de Moshier-benadering gerekend is - gemeten, niet aangenomen.

Daarnaast de Chiron-stand van twee ijkpunten, om na te rekenen in een eigen programma.

Draaien:  /usr/bin/python3 ijking/ijk-invoer.py
Schrijft: ijking/uitkomsten-<datum>-invoer.md
"""

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kern import efemeride, formaat, invoer, kaart  # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))
VANDAAG = datetime.date.today().isoformat()
BEWAARD = os.path.expanduser("~/astrologie-horoscopen/controle-1963-07-19.json")

CONTROLE_KLOPT = dict(naam="Controle", datum="1963-07-19", tijd="16:51:26", plaats="Langstraat",
                 lat=51.675, lon=4.27917, tijdzone_id="Europe/Amsterdam", huizenstelsel="K")
# Dit is de controletaak **zoals die in het scherm staat**: op 14 oktober 2026 opnieuw bewaard vanuit
# de app, met de plaats uit de plaatsenlijst in plaats van de handmatig ingetypte coordinaten. Daarom
# wordt hier tegen dat bewaarde kaartbestand vergeleken en hoort dat verschil 0,000000 boogseconde te
# zijn. Ontbreekt het bestand (een verse kopie heeft geen horoscopen), dan slaat die proef zichzelf over.
#
# Let op: de ijkpunten die tegen een **buitenbron** vergelijken - de twee afdrukken, het testgeval in
# `wheel.php` en Janus - houden de coordinaten die bij die bron horen (51,6736 / 4,2811). Die staan in
# `ijk-kaarten.py` en verderop in dit bestand bij de Chiron-tabel; pas die niet aan.

# --- 1. invoer die aanvaard moet worden --------------------------------------------------------

AANVAARD = [
    ("tijd zonder seconden",        dict(CONTROLE_KLOPT, tijd="16:51"),
     {"tijd": "16:51:00", "seconde": 0}),
    ("datum dag-eerst",             dict(CONTROLE_KLOPT, datum="19-07-1963"),
     {"datum": "1963-07-19"}),
    ("datum met schuine strepen",   dict(CONTROLE_KLOPT, datum="19/07/1963"),
     {"datum": "1963-07-19"}),
    ("datum met punten, korte maand", dict(CONTROLE_KLOPT, datum="19.7.1963"),
     {"datum": "1963-07-19"}),
    ("datum aaneengesloten, dag eerst", dict(CONTROLE_KLOPT, datum="19071963"),
     {"datum": "1963-07-19"}),
    ("datum aaneengesloten, jaar eerst", dict(CONTROLE_KLOPT, datum="19630719"),
     {"datum": "1963-07-19"}),
    ("tijd met punt",               dict(CONTROLE_KLOPT, tijd="16.51.26"),
     {"tijd": "16:51:26"}),
    ("tijd met u",                  dict(CONTROLE_KLOPT, tijd="16u51"),
     {"tijd": "16:51:00"}),
    ("tijd aaneengesloten",         dict(CONTROLE_KLOPT, tijd="1651"),
     {"tijd": "16:51:00"}),
    ("coordinaten met komma",       dict(CONTROLE_KLOPT, lat="51,675", lon="4,27917"),
     {"lat": 51.675, "lon": 4.27917}),
    ("coordinaten in graden en minuten", dict(CONTROLE_KLOPT, lat="51°40' N", lon="4°17' O"),
     {"lat": 51.6667, "lon": 4.2833, "tolerantie": 0.001}),
    ("noorderbreedte met letter",   dict(CONTROLE_KLOPT, lat="51.675 N", lon="4.27917 O"),
     {"lat": 51.675, "lon": 4.27917}),
    ("zuid en west met letter",     dict(CONTROLE_KLOPT, plaats="", lat="33.9 Z", lon="151.2 W"),
     {"lat": -33.9, "lon": -151.2}),
    ("huizenstelsel als naam",      dict(CONTROLE_KLOPT, huizenstelsel="Koch"),
     {"huizenstelsel": "K"}),
    ("huizenstelsel kleine letter", dict(CONTROLE_KLOPT, huizenstelsel="placidus"),
     {"huizenstelsel": "P"}),
    # Sinds 19 okt 2026 wordt een lege zone opgezocht bij de coördinaten, dus er komt een waarschuwing
    # bij die zegt waar hij vandaan komt; hier telt alleen dat de zone klopt.
    ("tijdzone leeg wordt opgezocht", dict(CONTROLE_KLOPT, tijdzone_id=""),
     {"tijdzone_id": "Europe/Amsterdam"}),
    # Sinds 19 okt 2026 rekent het programma buiten 1800-2399 door met de Moshier-benadering.
    ("datum voor 1800",            dict(CONTROLE_KLOPT, datum="04-04-1650"), {"jaar": 1650}),
    ("tijd in UT",                  dict(CONTROLE_KLOPT, tijdcorrectie="UT"),
     {"tijdcorrectie": "utc"}),
    ("Chiron met ja",               dict(CONTROLE_KLOPT, met_chiron="ja"),
     {"met_chiron": True}),
    ("sectoren leeg laat spec.json beslissen", dict(CONTROLE_KLOPT, sectoren=""),
     {"sectoren": None}),
]

# --- 2. invoer die een boodschap in gewone taal moet geven --------------------------------------

AFGEKEURD = [
    ("leeg gelaten tijd",        dict(CONTROLE_KLOPT, tijd=""),            "Vul een tijd in"),
    ("tijd in woorden",          dict(CONTROLE_KLOPT, tijd="kwart voor vijf"), "snap ik niet"),
    ("uur 24",                   dict(CONTROLE_KLOPT, tijd="24:10"),       "bestaat niet"),
    ("datum zonder jaar",        dict(CONTROLE_KLOPT, datum="19-07"),      "snap ik niet"),
    ("datum met afgekort jaar",  dict(CONTROLE_KLOPT, datum="19-07-63"),   "jaar voluit"),
    ("maand 13",                 dict(CONTROLE_KLOPT, datum="1963-13-45"), "maand 13 bestaat niet"),
    ("30 februari",              dict(CONTROLE_KLOPT, datum="1963-02-30"), "dag 30 bestaat niet in maand 2"),
    ("jaar buiten bereik",       dict(CONTROLE_KLOPT, datum="3000-04-04"), "buiten het bereik"),
    ("breedte 95",               dict(CONTROLE_KLOPT, lat="95"),           "buiten het mogelijke bereik"),
    ("breedte in letters",       dict(CONTROLE_KLOPT, lat="tussen Dieren en Doesburg"), "is geen getal"),
    ("minuten boven 60",         dict(CONTROLE_KLOPT, lat="51°70' N"),     "onder 60 blijven"),
    ("huizenstelsel onbekend",   dict(CONTROLE_KLOPT, huizenstelsel="Kochhuis"), "ken ik niet"),
    ("tijdcorrectie onbekend",   dict(CONTROLE_KLOPT, tijdcorrectie="middeleeuwse tijd"), "ken ik niet"),
    ("sectormaat onbekend",      dict(CONTROLE_KLOPT, sectoren="driehoekig"), "ken ik niet"),
    ("drie fouten tegelijk",     dict(CONTROLE_KLOPT, datum="1963-02-30", tijd="", lat="95"),
     "3 regels"),
]


def main():
    uit = []
    regels = []

    def schrijf(t):
        regels.append(t)
        print(t)

    schrijf(f"# IJking van de invoer - {VANDAAG}")
    schrijf("")
    schrijf("Gemaakt met `ijking/ijk-invoer.py`. Elke regel is met het echte antwoord van de")
    schrijf("lezer in `kern/invoer.py` nagemeten, niet geschat.")
    schrijf("")

    # 1. aanvaard
    schrijf("## 1. Invoer die aanvaard wordt")
    schrijf("")
    schrijf("| wat er ingetypt wordt | uitkomst | goed? |")
    schrijf("|---|---|---|")
    goed = fout = 0
    for omschrijving, vraag, verwacht in AANVAARD:
        try:
            g = invoer.lees(vraag)
        except invoer.InvoerFout as e:
            fout += 1
            schrijf(f"| {omschrijving} | AFGEKEURD: {' '.join(e.meldingen)} | nee |")
            continue
        mis = []
        for sleutel, waarde in verwacht.items():
            if sleutel == "tolerantie":
                continue
            echt = g.get(sleutel)
            if isinstance(waarde, float) and isinstance(echt, float):
                if abs(echt - waarde) > verwacht.get("tolerantie", 1e-9):
                    mis.append(f"{sleutel}: {echt} in plaats van {waarde}")
            elif echt != waarde:
                mis.append(f"{sleutel}: {echt!r} in plaats van {waarde!r}")
        if mis:
            fout += 1
            schrijf(f"| {omschrijving} | {'; '.join(mis)} | nee |")
        else:
            goed += 1
            kern = ", ".join(f"{s}={g[s]!r}" for s in
                             ("datum", "tijd", "lat", "lon", "huizenstelsel", "tijdcorrectie",
                              "met_chiron", "sectoren") if s in verwacht)
            schrijf(f"| {omschrijving} | {kern or 'aanvaard'} | ja |")
    uit.append({"aanvaard_goed": goed, "aanvaard_fout": fout})
    schrijf("")

    # 2. afgekeurd
    schrijf("## 2. Invoer die een boodschap in gewone taal krijgt")
    schrijf("")
    schrijf("| wat er ingetypt wordt | boodschap | geen 500? |")
    schrijf("|---|---|---|")
    goed2 = fout2 = 0
    for omschrijving, vraag, deelstring in AFGEKEURD:
        try:
            invoer.lees(vraag)
            fout2 += 1
            schrijf(f"| {omschrijving} | geen fout gemeld | nee |")
        except invoer.InvoerFout as e:
            melding = " ".join(e.meldingen)
            if deelstring == "3 regels" and len(e.meldingen) >= 3:
                goed2 += 1
                schrijf(f"| {omschrijving} | alle {len(e.meldingen)} in een keer: {melding} | ja |")
            elif deelstring in melding:
                goed2 += 1
                schrijf(f"| {omschrijving} | {melding} | ja |")
            else:
                fout2 += 1
                schrijf(f"| {omschrijving} | {melding} (verwachtte '{deelstring}') | nee |")
    uit.append({"afgekeurd_goed": goed2, "afgekeurd_fout": fout2})
    schrijf("")

    # 2b. de plaatsnaam bij de coördinaten (17 oktober 2026)
    #
    # Aanleiding: in het formulier typte ik "Heerlen" en drukte op Rekenen; de kaart kwam met de
    # coördinaten van Dieren (52,0512 / 6,103) en droeg de naam Heerlen. Zonder deze controle is er
    # geen eerlijke kaart en geen melding die het verraadt.
    schrijf("## 2b. Hoort de plaatsnaam bij de coördinaten?")
    schrijf("")
    schrijf("| geval | uitkomst | goed? |")
    schrijf("|---|---|---|")
    PLAATS_GEVALLEN = [
        ("plaats uit de lijst met haar eigen coördinaten", dict(CONTROLE_KLOPT), "aanvaard"),
        ("naam getypt, coördinaten 130 km ernaast (Heerlen bij Dieren)",
         dict(CONTROLE_KLOPT, plaats="Heerlen"), "horen niet bij"),
        ("coördinaten 3 km ernaast", dict(CONTROLE_KLOPT, lat=51.70, lon=4.28), "aanvaard"),
        ("coördinaten 20 km ernaast", dict(CONTROLE_KLOPT, lat=51.85, lon=4.28), "horen niet bij"),
        ("plaats buiten de lijst (eigen plek)", dict(CONTROLE_KLOPT, plaats="Mijn tuin"),
         "let-op: staat niet in de plaatsenlijst"),
        ("plaats leeg, coördinaten ingevuld", dict(CONTROLE_KLOPT, plaats=""), "aanvaard"),
    ]
    goed3 = fout3 = 0
    # `verwacht` is "aanvaard", "let-op: <deel van de waarschuwing>" (aanvaard, met een let-op-regel)
    # of een deel van de foutmelding die hoort te komen.
    for omschrijving, vraag, verwacht in PLAATS_GEVALLEN:
        try:
            g3 = invoer.lees(vraag)
        except invoer.InvoerFout as e:
            melding = " ".join(e.meldingen)
            if verwacht == "aanvaard" or verwacht.startswith("let-op:"):
                fout3 += 1
                schrijf(f"| {omschrijving} | AFGEKEURD: {melding} | nee |")
            elif verwacht in melding:
                goed3 += 1
                schrijf(f"| {omschrijving} | {melding} | ja |")
            else:
                fout3 += 1
                schrijf(f"| {omschrijving} | {melding} (verwachtte '{verwacht}') | nee |")
            continue
        let_op = " ".join(g3.get("waarschuwingen") or [])
        if verwacht == "aanvaard":
            goed3 += 1
            schrijf(f"| {omschrijving} | aanvaard ({let_op or 'geen waarschuwing'}) | ja |")
        elif verwacht.startswith("let-op:"):
            deel = verwacht[len("let-op:"):].strip()
            if deel in let_op:
                goed3 += 1
                schrijf(f"| {omschrijving} | aanvaard met let-op: {let_op} | ja |")
            else:
                fout3 += 1
                schrijf(f"| {omschrijving} | aanvaard zonder de verwachte let-op "
                        f"('{let_op}' in plaats van '{deel}') | nee |")
        else:
            fout3 += 1
            schrijf(f"| {omschrijving} | aanvaard, maar er hoort een klacht te komen | nee |")
    uit.append({"plaats_goed": goed3, "plaats_fout": fout3})
    schrijf("")

    # 3. de rekenkern ongewijzigd
    schrijf("## 3. De rekenkern is niet veranderd")
    schrijf("")
    g = invoer.lees(dict(CONTROLE_KLOPT, sectoren="eigen-graden"))
    k = kaart.maak_kaart(naam=g["naam"], jaar=g["jaar"], maand=g["maand"], dag=g["dag"],
                         uur=g["uur"], minuut=g["minuut"], seconde=g["seconde"],
                         tijdzone_id=g["tijdzone_id"], lat=g["lat"], lon=g["lon"],
                         plaats=g["plaats"], huizenstelsel=g["huizenstelsel"],
                         tijdcorrectie=g["tijdcorrectie"], met_chiron=g["met_chiron"])
    rechtstreeks = kaart.maak_kaart(
        naam="Controle", jaar=1963, maand=7, dag=19, uur=16, minuut=51, seconde=26,
        tijdzone_id="Europe/Amsterdam", lat=51.675, lon=4.27917, plaats="Langstraat",
        huizenstelsel="K")
    verschil = 0.0
    for p_oud, p_nieuw in zip(rechtstreeks["punten"], k["punten"]):
        verschil = max(verschil, abs(p_oud["lengte"] - p_nieuw["lengte"]))
    for h_oud, h_nieuw in zip(rechtstreeks["huizen"], k["huizen"]):
        verschil = max(verschil, abs(h_oud["lengte"] - h_nieuw["lengte"]))
    schrijf(f"- dezelfde kaart via de lezer en rechtstreeks via de kern: **grootste afwijking "
            f"{verschil * 3600:.6f} boogseconde** "
            f"({'gelijk' if verschil * 3600 < 0.001 else 'WIJKT AF'}) - de lezer rekent niet mee.")
    uit.append({"lezer_tegen_kern_boogseconde": verschil * 3600})

    # 3b. de bewaarde kaart: is die reproduceerbaar, en zo niet, waarom?
    if os.path.exists(BEWAARD):
        with open(BEWAARD, encoding="utf-8") as f:
            oud = json.load(f)
        meta = oud.get("meta", {})

        def afwijking(a, b):
            paren = [(abs(x["lengte"] - y["lengte"]) * 3600, x["naam"]) for x, y in zip(a, b)]
            return max(paren) if paren else (0.0, "-")

        # (a) de kaart opnieuw rekenen uit **zijn eigen** meta: dit hoort 0,000000 te zijn
        datum = [int(v) for v in str(meta.get("datum", "")).split("-")]
        tijd = [int(v) for v in str(meta.get("tijd", "0:0:0")).split(":")]
        tijd = (tijd + [0, 0])[:3]
        eigen = kaart.maak_kaart(meta.get("naam", "bewaard"), *(datum + tijd),
                                 tijdzone_id=meta.get("tijdzone_id", "Europe/Amsterdam"),
                                 lat=meta.get("lat"), lon=meta.get("lon"),
                                 huizenstelsel=meta.get("huizenstelsel", "K"),
                                 met_chiron=bool(meta.get("met_chiron")))
        d_eigen, naam_eigen = afwijking(oud["punten"], eigen["punten"])
        schrijf(f"- de bewaarde kaart `{os.path.basename(BEWAARD)}` opnieuw uit **zijn eigen** meta")
        schrijf(f"  gerekend ({meta.get('datum')} {meta.get('tijd')}, {meta.get('plaats')}, "
                f"{meta.get('lat')} / {meta.get('lon')}): grootste afwijking "
                f"**{d_eigen:.6f} boogseconde** ({naam_eigen})")
        uit.append({"bewaard_eigen_meta_boogseconde": d_eigen})

        # (b) dezelfde kaart tegen de proefgegevens van dit ijkpunt: een verschil hoort dan van de
        #     invoer te komen (de coordinaten), niet van de efemeriden
        d_proef, naam_proef = afwijking(oud["punten"], k["punten"])
        zelfde_invoer = (float(meta.get("lat", 0)) == CONTROLE_KLOPT["lat"]
                         and float(meta.get("lon", 0)) == CONTROLE_KLOPT["lon"])
        schrijf(f"- dezelfde kaart tegen de proefgegevens van dit ijkpunt ({CONTROLE_KLOPT['lat']} / "
                f"{CONTROLE_KLOPT['lon']}): grootste afwijking **{d_proef:.6f} boogseconde** "
                f"({naam_proef})")
        if not zelfde_invoer:
            schrijf(f"  dat verschil komt van de invoer en niet van de efemeriden: de kaart staat")
            schrijf(f"  op {meta.get('plaats')} met {meta.get('lat')} / {meta.get('lon')} in")
            schrijf("  plaats van de proefgegevens hierboven, en de Ascendant (en de dagpars, die")
            schrijf("  van de Ascendant afhangt) reageert op de coordinaten.")
        uit.append({"bewaard_tegen_proef_boogseconde": d_proef})

        # (c) is deze kaart met de **Moshier-benadering** gerekend? Dat was op 14 oktober 2026 zo
        #     voor de kaart van 13 oktober (toen 2,881941 boogseconde, Noorderknoop). De kaart is
        #     daarna opnieuw bewaard, dus meet het opnieuw in plaats van het aan te nemen.
        import swisseph as swe
        jd = meta.get("julian_day_ut")
        if jd:
            mosh = {naam: swe.calc_ut(jd, pid, swe.FLG_MOSEPH)[0][0] for pid, naam in efemeride.LICHAMEN}
            mosh_af = max((abs(efemeride.lengte_van(naam, oud["punten"]) - mosh[naam]) * 3600, naam)
                          for naam in mosh)
            eigen_af = max((abs(efemeride.lengte_van(naam, oud["punten"])
                                - efemeride.lengte_van(naam, eigen["punten"])) * 3600, naam)
                           for naam in mosh)
            schrijf(f"- dezelfde kaart tegen de **Moshier-benadering**: grootste afwijking "
                    f"**{mosh_af[0]:.6f} boogseconde** ({mosh_af[1]}), tegen "
                    f"{eigen_af[0]:.6f} boogseconde voor de efemeriden van nu.")
            if mosh_af[0] < 0.001 <= eigen_af[0]:
                schrijf("  deze kaart is dus met de benadering gerekend en niet met de efemeriden.")
            elif eigen_af[0] < 0.001 <= mosh_af[0]:
                schrijf("  deze kaart is dus met de **efemeriden** gerekend (opnieuw bewaard).")
            else:
                schrijf("  geen van beide komt exact uit: de invoer van de kaart is veranderd.")
            uit.append({"moshier_boogseconde": mosh_af[0], "efemeriden_boogseconde": eigen_af[0]})

        # 3c. de controle werkt
        import subprocess
        proef = ("import sys; sys.path.insert(0, %r)\n"
                 "from kern import kaart\n"
                 "kaart.maak_kaart(naam='proef', jaar=1963, maand=7, dag=19, uur=16, minuut=51,\n"
                 " seconde=26, tijdzone_id='Europe/Amsterdam', lat=51.675, lon=4.27917,\n"
                 " plaats='Langstraat', huizenstelsel='K')\n" % os.path.dirname(HIER))
        omgeving = dict(os.environ, ASTRO_EPHE_PATH="/geen/efemeriden")
        r = subprocess.run([sys.executable, "-c", proef], capture_output=True, text=True,
                           env=omgeving)
        laatste = [regel for regel in r.stderr.strip().splitlines() if regel.strip()]
        geweigerd = r.returncode != 0 and "ontbreken" in r.stderr
        schrijf(f"- proef met een verkeerde efemeridenmap: "
                f"{'geweigerd zoals bedoeld' if geweigerd else 'NIET GEWEIGERD'} "
                f"(afsluitcode {r.returncode}).")
        if laatste:
            schrijf(f"  melding: {laatste[-1].strip()}")
        uit.append({"controle_weigert_zonder_bestanden": geweigerd})
    else:
        schrijf(f"- geen bewaarde kaart gevonden op {BEWAARD}; alleen de nieuwe berekening gedaan.")
    schrijf("")

    # 4. Chiron
    schrijf("## 4. Chiron (om na te rekenen)")
    schrijf("")
    schrijf("`kern/efemeride.py` gebruikte het catalogusnummer 2060 waar swisseph zijn eigen")
    schrijf("constante 15 wil; de optie gaf daardoor een 500. Nu via `swe.CHIRON`, met de standen uit")
    schrijf("`seas_18.se1` (de hoofasteroiden) - dat bestand staat in de efemeridenmap.")
    schrijf("")
    schrijf("| moment (UT) | lengte | teken | breedte | snelheid | retrograde | huis |")
    schrijf("|---|---|---|---|---|---|---|")
    chiron = []
    for lbl, args in (("Jans kaart: 1963-07-19 15:51:26 UT",
                       dict(jaar=1963, maand=7, dag=19, uur=15, minuut=51, seconde=26,
                            tijdzone_id="Europe/Amsterdam", tijdcorrectie="utc",
                            lat=51.6736, lon=4.2811, huizenstelsel="K")),
                      ("2026-01-01 00:00:00 UT",
                       dict(jaar=2026, maand=1, dag=1, uur=0, minuut=0, seconde=0,
                            tijdzone_id="Europe/Amsterdam", tijdcorrectie="utc",
                            lat=51.6736, lon=4.2811, huizenstelsel="K"))):
        kk = kaart.maak_kaart(naam="ijkpunt", plaats="Achthuizen", met_chiron=True, **args)
        c = [p for p in kk["punten"] if p["naam"] == "Chiron"][0]
        pos = c["positie"]
        schrijf(f"| {lbl} | {c['lengte']:.6f}° | {pos['teken']} {pos['graad']}°{pos['minuut']:02d}' "
                f"| {c['snelheid']:+.6f}°/dag | {'ja' if c['retrograde'] else 'nee'} | huis {c['huis']} |")
        chiron.append({"moment_ut": lbl, "lengte": c["lengte"], "snelheid": c["snelheid"],
                       "retrograde": c["retrograde"], "huis": c["huis"],
                       "label": pos["label"]})
    uit.append({"chiron": chiron})
    schrijf("")

    pad_md = os.path.join(HIER, f"uitkomsten-{VANDAAG}-invoer.md")
    with open(pad_md, "w", encoding="utf-8") as f:
        f.write("\n".join(regels) + "\n")
    pad_json = os.path.join(HIER, f"uitkomsten-{VANDAAG}-invoer.json")
    with open(pad_json, "w", encoding="utf-8") as f:
        json.dump(uit, f, ensure_ascii=False, indent=2)

    print()
    print(f"aanvaard goed/fout: {goed}/{fout} - afgekeurd goed/fout: {goed2}/{fout2} - "
          f"plaats bij coordinaten goed/fout: {goed3}/{fout3}")
    print(f"geschreven: {pad_md}")
    return 0 if (fout == 0 and fout2 == 0 and fout3 == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
