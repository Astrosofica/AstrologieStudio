"""De tekenaar: van kaart-JSON naar SVG.

Eén wiel, één ontwerp (besluit T11). Alle maten en kleuren komen uit `spec.json`; deze code
bevat er geen enkele. De opbouw is laag per laag (besluit B6): achtergrond, band, cusplijnen,
huisnummers, lichaamsticks, lichaamslabels, aspecten (apart, uitschakelbaar).

Oriëntatie en opbouw volgen de twee afdrukken (T11b/PRINTS):

- de Ascendant links (het horizontale assenkruis); de cusplijnen op de echte graden
  (`sectoren: eigen-graden`, zoals de Pathfinder-print) of op twaalf even brede sectoren
  (`sectoren: vast-30`, zoals de Janus-print). Alles - cuspen, lichamen, aspectlijnen -
  gaat door dezelfde hoekfunctie, zodat de tekening altijd in zichzelf klopt;
- de cusplabels liggen in de band, elk op zijn eigen cusp, de stukjes rechtop naast elkaar
  langs de rand;
- de lichaamslabels staan radiaal: glyph, graad, teken, minuut van de rand naar binnen, de
  stukjes rechtop (zoals in beide prints);
- in de afdruk staan **geen** aspectlijnen (besluit T14) - die laag krijgt de klasse
  `laag-aspecten` en de print-CSS zet hem uit.
"""

from __future__ import annotations

import base64
import json
import math
import os

from kern import elementen as _elementen
from kern import formaat as _fmt
from kern import paden

HIER = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HIER)

# De vier huizen waarvan de cusplijn een as is: 1 en 7 de Asc-Desc-as, 4 en 10 de MC-IC-as.
# Die blijven donker, de acht andere huislijnen zijn lichter (besluit van Jan, 13 oktober 2026).
AS_HUIZEN = (1, 4, 7, 10)


def laad_spec(pad=None):
    with open(pad or os.path.join(HIER, "spec.json"), encoding="utf-8") as f:
        return json.load(f)


def maak_mapper(kaart, spec):
    """Lengtegraad -> beeldhoek: één functie voor cuspen, lichamen en aspecten (T11b).

    `eigen-graden`  de echte graden, lineair vanaf de Ascendant (Pathfinder-print);
    `vast-30`       twaalf even brede sectoren met de echte cusp als label (Janus-print),
                    waarbij de positie binnen een sector meeloopt met de echte graden.
    """
    asc_hoek = float(spec["orientatie"]["ascendant_hoek"])
    soort = spec["orientatie"].get("sectoren", "eigen-graden")

    if soort == "vast-30":
        cuspen = [h["lengte"] for h in kaart["huizen"]]

        def hoek(lengte):
            for i in range(12):
                a, b = cuspen[i], cuspen[(i + 1) % 12]
                span = (b - a) % 360.0
                verschil = (lengte - a) % 360.0
                if verschil <= span + 1e-9:
                    deel = (verschil / span) if span > 1e-12 else 0.0
                    return (asc_hoek + 30.0 * (i + deel)) % 360.0
            return asc_hoek % 360.0

        return hoek

    asc = kaart["ascendant"]["lengte"]
    return lambda lengte: (asc_hoek + (lengte - asc)) % 360.0


def _xy(cx, cy, r, hoek):
    a = math.radians(hoek)
    return cx + r * math.cos(a), cy - r * math.sin(a)


def _raaklijn(hoek):
    """Richting langs de rand waarin een label leesbaar loopt: de richting met een positieve
    x-component, en waar die nul is (links en rechts) naar beneden - zoals in de print."""
    x, y = math.sin(math.radians(hoek)), math.cos(math.radians(hoek))
    if x < 0 or (abs(x) < 1e-12 and y < 0):
        x, y = -x, -y
    return x, y


def _ringvlak(cx, cy, r_in, r_uit, hoek_van, graad_van, graad_tot, stap=2.0):
    """Een ringstuk (sector) tussen twee stralen, als één gevulde vorm.

    De twee randen worden elke `stap` graden opgezocht via de hoekfunctie in plaats van als één
    cirkelboog getekend: in de stand `vast-30` kan die functie binnen een teken knikken, en dan
    zou een boog naast de tekengrens vallen.
    """
    buiten, binnen = [], []
    g = float(graad_van)
    while g <= graad_tot + 1e-9:
        buiten.append(_xy(cx, cy, r_uit, hoek_van(g)))
        binnen.append(_xy(cx, cy, r_in, hoek_van(g)))
        g += stap
    punten = buiten + list(reversed(binnen))
    return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in punten) + " Z"


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _glyph_font_als_data_uri(pad):
    with open(pad, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _maten(spec):
    """Gemeten glyphbreedtes (B4) uit data/glyph-maten.json.

    Sinds 15 okt 2026 staat in datzelfde bestand ook de penvoorsprong per teken ("tekens"):
    de cijfers, het graadteken en de minuutstreep worden daarmee *gemeten* in plaats van
    geschat met `tekenbreedte_gewoon`/`_smal` (die twee blijven als vangnet voor tekst die
    niet in het font zit). Ze komen onder de sleutel `_tekens` in dezelfde map, zodat één
    lezing volstaat en er niets doorgegeven hoeft te worden.
    """
    pad = paden.bron("data", "glyph-maten.json")
    if os.path.exists(pad):
        with open(pad, encoding="utf-8") as f:
            gegevens = json.load(f)
        uit = dict(gegevens["glyphs"])
        uit["_tekens"] = gegevens.get("tekens", {})
        return uit
    return {}


def _maat_sleutel(naam):
    return "Pars Fortuna" if naam == "Dagpars" else naam


def _breedte(tekst, grootte, spec, sleutel=None, maten=None):
    """Breedte van een stukje label: gemeten als het kan, anders geschat (B4)."""
    if sleutel and maten and sleutel in maten:
        return maten[sleutel]["breedte"] * grootte
    tekens = (maten or {}).get("_tekens") or {}
    if tekst and tekens and all(c in tekens for c in tekst):
        return sum(tekens[c] for c in tekst) * grootte
    MA = spec["maten"]
    smal = sum(1 for c in tekst if c in " 1'°.,ilI")
    return ((len(tekst) - smal) * MA["tekenbreedte_gewoon"]
            + smal * MA["tekenbreedte_smal"]) * grootte


def _cusp_tokens(p, spec):
    """De drie stukjes van een cusplabel: graad, tekenglyph, minuut."""
    G = spec["letters"]
    return [{"tekst": f'{p["graad"]:02d}°', "klasse": "", "grootte": G["cusp_label"], "sleutel": None},
            {"tekst": _esc(p["glyf"]), "klasse": "glyf", "grootte": G["cusp_teken"], "sleutel": p["teken"]},
            {"tekst": f'{p["minuut"]:02d}\'', "klasse": "", "grootte": G["cusp_label"], "sleutel": None}]


def _lichaam_tokens(p, spec):
    """De stukjes van een lichaamslabel, van de rand naar binnen (zoals in de print):
    glyph, graad, teken, minuut - en Retrograde als staart."""
    G = spec["letters"]
    tokens = [
        {"tekst": _esc(_fmt.glyf_planeet(p["naam"])), "klasse": "glyf",
         "grootte": G["lichaam_glyf"], "sleutel": _maat_sleutel(p["naam"])},
        {"tekst": f'{p["positie"]["graad"]:02d}°', "klasse": "",
         "grootte": G["lichaam_graad"], "sleutel": None},
        {"tekst": _esc(p["positie"]["glyf"]), "klasse": "glyf",
         "grootte": G["lichaam_teken"], "sleutel": p["positie"]["teken"]},
        {"tekst": f'{p["positie"]["minuut"]:02d}\'', "klasse": "",
         "grootte": G["lichaam_minuut"], "sleutel": None},
    ]
    if p.get("retrograde"):
        tokens.append({"tekst": chr(_fmt.RETRO_GLYPH), "klasse": "glyf retro",
                       "grootte": G["retro"], "sleutel": None})
    return tokens


def _keten_plaats(x0, y0, tx, ty, tokens, marge, maten, spec):
    """Leg de stukjes naast elkaar langs de richting (tx, ty), samen gecentreerd op (x0, y0)."""
    breedtes = [_breedte(t["tekst"], t["grootte"], spec, t["sleutel"], maten) for t in tokens]
    totaal = sum(breedtes) + marge * (len(tokens) - 1)
    afstand = -totaal / 2.0
    uit = []
    for t, w in zip(tokens, breedtes):
        afstand += w / 2.0
        uit.append((x0 + tx * afstand, y0 + ty * afstand, t, w))
        afstand += w / 2.0 + marge
    return uit


def teken(kaart, spec=None, met_aspecten=True, titel=None):
    spec = spec or laad_spec()
    C, M = spec["canvas"], spec["midden"]
    R, L, K = spec["stralen"], spec["lijnen"], spec["kleuren"]
    G, T, MA = spec["letters"], spec["tekst"], spec["maten"]
    cx, cy = M["x"], M["y"]
    maten = _maten(spec)
    hoek_van = maak_mapper(kaart, spec)

    fontpad = paden.bron(spec["glyph_font"]["bestand"])
    font_uri = ""
    if os.path.exists(fontpad):
        font_uri = ("data:font/ttf;base64," + _glyph_font_als_data_uri(fontpad))

    uit = []
    A = uit.append
    A(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {C["breedte"]} {C["hoogte"]}" '
      f'width="{C["breedte"]}" height="{C["hoogte"]}" class="wiel">')
    A("<defs><style>")
    A(f'.wiel{{background:{C["achtergrond"]};font-family:{T["familie"]};font-weight:{T["dikte"]};}}')
    A(f'.wiel text{{fill:{K["tekst"]};}}')
    if font_uri:
        A(f'@font-face{{font-family:{spec["glyph_font"]["familie"]};src:url({font_uri});}}')
    A(f'.glyf{{font-family:{spec["glyph_font"]["familie"]};}}')
    A(f'.lijn{{stroke:{K["lijn"]};fill:none;}}')
    # de kleur per aspectgroep (alleen op het scherm bruikbaar; de afdruk zet deze laag uit).
    # Twee klasseselectoren (.lijn.asp-hard) zodat deze regel het altijd wint van .lijn.
    for soort, kleur in (K.get("aspect") or {}).items():
        if not str(soort).startswith("_"):
            A(f'.lijn.asp-{soort}{{stroke:{kleur};}}')
    # de huislijnen: de vier assen donker, de acht andere lichter (besluit van Jan, 13 okt 2026)
    for sleutel, klasse in (("cusp_as", "cusp-as"), ("cusp", "cusp-overig")):
        if K.get(sleutel):
            A(f'.lijn.{klasse}{{stroke:{K[sleutel]};}}')
    # de graadverdeling in de zodiakring: de 5- en 10-graden-tikken, de fijne verdeling per graad
    # en de tekengrenzen elk hun eigen kleur (Jan, 13 okt 2026: de tikken donkerder)
    for sleutel, klasse in (("zodiak_tik", "zodiak-tik"), ("zodiak_graad", "zodiak-graad"),
                            ("zodiak_grens", "zodiak-grens")):
        if K.get(sleutel):
            A(f'.lijn.{klasse}{{stroke:{K[sleutel]};}}')
    # de buitenrand heeft zijn eigen kleur (Jan, 17 okt 2026: dun en grijs); ontbreekt de sleutel,
    # dan blijft de gewone lijnkleur staan en is dit de oude stand
    if K.get("buitenrand"):
        A(f'.lijn.buitenrand{{stroke:{K["buitenrand"]};}}')
    A(f'.cusp-label{{fill:{K["cusp_label"]};}}')
    A(f'.retro{{fill:{K["retrograde"]};}}')
    A(".laag-aspecten{opacity:1}")
    A("</style></defs>")

    # 1. buitenrand en binnencirkels
    A(f'<circle class="lijn buitenrand" cx="{cx}" cy="{cy}" r="{R["buitenrand"]}" stroke-width="{L["buitenrand"]}"/>')
    A(f'<circle class="lijn" cx="{cx}" cy="{cy}" r="{R["cuspband_binnen"]}" stroke-width="{L["cusp"]}"/>')
    A(f'<circle class="lijn" cx="{cx}" cy="{cy}" r="{R["zodiakring_binnen"]}" stroke-width="{L["cusp"]}"/>')
    A(f'<circle class="lijn" cx="{cx}" cy="{cy}" r="{R["binnencirkel"]}" stroke-width="{L["binnencirkel"]}"/>')

    # 1b. de tint van de tekens: elk teken in de zodiakring in de kleur van zijn element
    # (besluit van Jan, 13 oktober 2026). Alleen op het scherm: de afdruk en de A4-weergave
    # zetten deze laag uit (print-CSS in schil/static/index.html).
    elementkleur = K.get("element") or {}
    if elementkleur:
        A('<g id="laag-zodiak-tint">')
        for i, teken in enumerate(_fmt.TEKENS):
            kleur = elementkleur.get(_elementen.ELEMENT[teken])
            if not kleur:
                continue
            pad = _ringvlak(cx, cy, R["zodiakring_binnen"], R["cuspband_binnen"],
                            hoek_van, i * 30.0, i * 30.0 + 30.0)
            A(f'<path d="{pad}" fill="{kleur}" stroke="none"/>')
        A("</g>")

    # 2. cusplijnen op hun eigen graad, huisnummers in het midden van de sector
    cusp_hoeken = [hoek_van(h["lengte"]) for h in kaart["huizen"]]
    A('<g id="laag-cuspen">')
    for i, h in enumerate(kaart["huizen"]):
        hoek = cusp_hoeken[i]
        x1, y1 = _xy(cx, cy, R["binnencirkel"], hoek)
        x2, y2 = _xy(cx, cy, R["cuspband_binnen"], hoek)
        # de vier assen (1 en 7 = Asc-Desc, 4 en 10 = MC-IC) blijven zwart, de acht andere
        # huislijnen zijn lichter (besluit van Jan, 13 oktober 2026)
        klasse = "lijn cusp-as" if h["nr"] in AS_HUIZEN else "lijn cusp-overig"
        A(f'<line class="{klasse}" x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
          f'stroke-width="{L["cusp"]}"/>')
    for i, h in enumerate(kaart["huizen"]):
        a, b = cusp_hoeken[i], cusp_hoeken[(i + 1) % 12]
        midden = (a + ((b - a) % 360.0) / 2.0) % 360.0
        x, y = _xy(cx, cy, R["huisnummer_cirkel"], midden)
        A(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{G["huisnummer"]}" text-anchor="middle" '
          f'dominant-baseline="middle">{h["nr"]}</text>')
    A("</g>")

    # 3. cusplabels in de band, elk op zijn eigen cusp, de stukjes langs de rand
    A('<g id="laag-cusplabels">')
    r_band = (R["buitenrand"] + R["cuspband_binnen"]) / 2.0
    for i, h in enumerate(kaart["huizen"]):
        hoek = cusp_hoeken[i]
        tokens = _cusp_tokens(h["positie"], spec)
        x0, y0 = _xy(cx, cy, r_band, hoek)
        tx, ty = _raaklijn(hoek)
        for x, y, t, _w in _keten_plaats(x0, y0, tx, ty, tokens, MA["token_marge"], maten, spec):
            klasse = ("cusp-label " + t["klasse"]).strip()
            A(f'<text class="{klasse}" x="{x:.1f}" y="{y:.1f}" font-size="{t["grootte"]}" '
              f'text-anchor="middle" dominant-baseline="middle">{t["tekst"]}</text>')
    A("</g>")

    # 4. de zodiakring: de twaalf tekens op hun echte graden, in de ring waar eerst de
    # huisnummers stonden, met een grove graadverdeling (tikjes per 5 en 10 graden) en een
    # lijn op elke tekengrens. Besluit van Jan (13 okt 2026): de echte graden, dus de grens
    # van het teken van de Ascendant valt niet op de Asc-as maar waar hij echt hoort.
    A('<g id="laag-zodiak">')
    r_teken, binnen = R["zodiak_teken"], R["zodiakring_binnen"]
    tik_kort, tik_lang = R["zodiak_tik"]["kort"], R["zodiak_tik"]["lang"]
    tik_graad = R["zodiak_tik"].get("graad") or 0
    for i in range(12):
        begin = i * 30.0
        x1, y1 = _xy(cx, cy, binnen, hoek_van(begin))
        x2, y2 = _xy(cx, cy, R["cuspband_binnen"], hoek_van(begin))
        A(f'<line class="lijn zodiak-grens" x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
          f'stroke-width="{L["zodiak_grens"]}"/>')
        # de fijne verdeling per graad (360 tikjes per rondgang, proef van Jan 13 okt 2026): de
        # veelvouden van 5 slaan we over, die krijgen hieronder hun eigen langere tikje
        if tik_graad:
            for graad in range(1, 30):
                if graad % 5 == 0:
                    continue
                xt1, yt1 = _xy(cx, cy, binnen, hoek_van(begin + graad))
                xt2, yt2 = _xy(cx, cy, binnen + tik_graad, hoek_van(begin + graad))
                A(f'<line class="lijn zodiak-graad" x1="{xt1:.2f}" y1="{yt1:.2f}" x2="{xt2:.2f}" '
                  f'y2="{yt2:.2f}" stroke-width="{L["zodiak_tik"]}"/>')
        # de graadverdeling hangt aan de binnenrand van de band (besluit van Jan, 13 okt 2026)
        for graad in range(5, 30, 5):
            lengte = tik_lang if graad % 10 == 0 else tik_kort
            xt1, yt1 = _xy(cx, cy, binnen, hoek_van(begin + graad))
            xt2, yt2 = _xy(cx, cy, binnen + lengte, hoek_van(begin + graad))
            A(f'<line class="lijn zodiak-tik" x1="{xt1:.2f}" y1="{yt1:.2f}" x2="{xt2:.2f}" '
              f'y2="{yt2:.2f}" stroke-width="{L["zodiak_tik"]}"/>')
        x, y = _xy(cx, cy, r_teken, hoek_van(begin + 15.0))
        A(f'<text class="glyf" x="{x:.1f}" y="{y:.1f}" font-size="{G["zodiak_teken"]}" '
          f'text-anchor="middle" dominant-baseline="middle">'
          f'{_esc(_fmt.glyf_teken(begin + 15.0))}</text>')
    A("</g>")

    # 5. de lichamen: tick op de echte graad, label radiaal naar binnen, clusters uit elkaar
    blokken, verschoven = plaats_lichamen(kaart, spec, hoek_van, maten)
    A('<g id="laag-lichamen">')
    for p, hoek, shift in blokken:
        hoek_tick = hoek_van(p["lengte"])
        x1, y1 = _xy(cx, cy, R["lichaam_tick_buiten"], hoek_tick)
        x2, y2 = _xy(cx, cy, R["lichaam_tick_binnen"], hoek_tick)
        A(f'<line class="lijn" x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
          f'stroke-width="{L["lichaam_tick"]}"/>')
        if abs(shift) > MA["keten_drempel"]:
            xa0, ya0 = _xy(cx, cy, R["lichaam_tick_binnen"], hoek_tick)
            xa1, ya1 = _xy(cx, cy, R["lichaam_keten"][0], hoek)
            A(f'<line class="lijn" x1="{xa0:.2f}" y1="{ya0:.2f}" x2="{xa1:.2f}" y2="{ya1:.2f}" '
              f'stroke-width="{L["leiderlijn"]}"/>')
        for i, t in enumerate(_lichaam_tokens(p, spec)):
            x, y = _xy(cx, cy, R["lichaam_keten"][i], hoek)
            klasse = t["klasse"]
            A(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{t["grootte"]}" text-anchor="middle" '
              f'dominant-baseline="middle"' + (f' class="{klasse}"' if klasse else "") +
              f'>{t["tekst"]}</text>')
    A("</g>")

    # 6. de aspecten - aparte laag, alleen op het scherm (besluit T14)
    if met_aspecten:
        A('<g id="laag-aspecten" class="laag-aspecten">')
        per_naam = {p["naam"]: p for p in kaart["punten"]}
        # De Noorderknoop en de Dagpars horen niet in het lijnenspel (T42, 29 okt 2026): aspecten gaan
        # tussen planeten onderling en tussen planeten en de hoeken. Welke punten dat zijn staat in de
        # kaart, zodat de kern de enige plek is waar die regel woont - de lijst en de trap op de A4
        # lezen dezelfde lijst en liepen er dus niet meer langs.
        weg = set(kaart.get("weg_punt") or ())
        for a in kaart["aspecten"]:
            if a["p1"] not in per_naam or a["p2"] not in per_naam:
                continue
            if a["p1"] in weg or a["p2"] in weg:
                continue
            h1 = hoek_van(per_naam[a["p1"]]["lengte"])
            h2 = hoek_van(per_naam[a["p2"]]["lengte"])
            x1, y1 = _xy(cx, cy, R["aspecten"], h1)
            x2, y2 = _xy(cx, cy, R["aspecten"], h2)
            streepl = "45 12" if a["scheidend"] else ""
            A(f'<line class="lijn asp-{a.get("soort", "overig")}" x1="{x1:.2f}" y1="{y1:.2f}" '
              f'x2="{x2:.2f}" y2="{y2:.2f}" '
              f'stroke-width="{L["aspect"]}" stroke-dasharray="{streepl}"/>')
        A("</g>")

    # De naam in de kerncirkel is er op 20 okt 2026 uit (Jan: "Naam mag weg uit de tekening"). Hij
    # stond als enige directe <text>-kind in de SVG; op de A4 was hij al verborgen met CSS, nu is hij
    # er in de tekening zelf niet meer. De parameter `titel` blijft bestaan voor wie de tekening ooit
    # opnieuw wil labelen, maar wordt hier niet meer gebruikt.
    A("</svg>")

    botsingen = tel_botsingen(blokken, kaart, spec, maten)
    return "\n".join(uit), botsingen


def plaats_lichamen(kaart, spec, hoek_van, maten=None):
    """Zet elk lichaam op zijn eigen graad en schuift de labels uit elkaar tot ze niet raken.

    Dit is het hart van B4/B5: eerst meten (glyphbreedtes), dan pas verschuiven, met een
    leiderlijn van het label naar de echte positie. De mate van verschuiving wordt gemeten,
    niet gekozen.
    """
    maten = maten if maten is not None else _maten(spec)
    MA = spec["maten"]

    lichamen = [p for p in kaart["punten"] if p["naam"] not in ("Ascendant", "MC")]
    lichamen.sort(key=lambda p: (p["lengte"] - kaart["ascendant"]["lengte"]) % 360)
    if not lichamen:
        return [], 0
    namen = [p["naam"] for p in lichamen]
    basis = [hoek_van(p["lengte"]) for p in lichamen]
    breedtes = [[_breedte(t["tekst"], t["grootte"], spec, t["sleutel"], maten)
                 for t in _lichaam_tokens(p, spec)] for p in lichamen]

    nodig = [_nodig_afstand(breedtes[i], breedtes[i + 1], spec) for i in range(len(breedtes) - 1)]
    nodig.append(0.0)          # de naad tussen het laatste en het eerste label blijft vrij
    # Eerst rekenen, dan meten: de afstandsregel hierboven werkt langs de rand, maar de
    # botsingstelling kijkt naar de assen van het beeld. Wat daar nog raakt, krijgt een
    # ruimere eis en de keten wordt opnieuw gelegd - dat kan de volgorde niet breken, want
    # alleen de kleinste afstand tussen twee buren groeit.
    hoeken = _spreid(basis, nodig)
    for _ in range(60):
        raak = _botsende_paren(lichamen, hoeken, spec, maten)
        if not raak:
            break
        for a, b in raak:
            i, j = namen.index(a), namen.index(b)
            nodig[min(i, j)] += 0.6
        hoeken = _spreid(basis, nodig)
    uit = [(p, h, (h - b + 180) % 360 - 180) for p, h, b in zip(lichamen, hoeken, basis)]
    verschoven = sum(1 for _, _, s in uit if abs(s) > MA["keten_drempel"])
    return uit, verschoven


def _nodig_afstand(breedte_a, breedte_b, spec):
    """Kleinste hoekafstand tussen twee labelketens, gemeten uit de breedtes per ring (B4)."""
    keten, marge = spec["stralen"]["lichaam_keten"], spec["maten"]["token_marge"]
    nodig = 0.0
    for k in range(min(len(breedte_a), len(breedte_b))):
        nodig = max(nodig, math.degrees(
            (breedte_a[k] / 2 + breedte_b[k] / 2 + marge) / keten[k]))
    return nodig


def _spreid(basis, nodig):
    """Zet de labels uit elkaar **met behoud van volgorde**.

    De volgorde langs de rand ligt vast (de dierenriemorde vanaf de Ascendant); geen enkel
    label mag langs zijn buurman schuiven. Daarom wordt de keten eerst op een lijn gelegd,
    daarna worden de afstanden opgelost met een ronde vooruit (alles wat te dicht op zijn
    voorganger staat naar rechts) en een ronde terug (alles wat onnodig ver staat weer naar
    links). Tenslotte wordt elke groep die elkaar raakt rond zijn eigen zwaartepunt
    teruggezet, zodat een label dat niets in de weg staat gewoon op zijn echte graad blijft.

    Dit is de fout van 13 oktober 2026 niet meer mogelijk: de oude code duwde een botsend paar
    uit elkaar op alfabetische volgorde van de namen, en dan schuift een label wel eens de
    verkeerde kant op - bij Jans eigen kaart kwam Mercurius zo 19 graden links van Venus,
    Noorderknoop en Zon te staan. Hier groeit alleen de kleinste afstand tussen twee buren,
    dus de volgorde kan niet meer wisselen.
    """
    n = len(basis)
    if n <= 1:
        return list(basis)
    ruw = [basis[0]]
    for i in range(1, n):
        ruw.append(ruw[i - 1] + (basis[i] - basis[i - 1]) % 360.0)
    x = list(ruw)
    for i in range(1, n):
        x[i] = max(x[i], x[i - 1] + nodig[i - 1])
    for i in range(n - 2, -1, -1):
        x[i] = min(x[i], x[i + 1] - nodig[i])

    # groepen die elkaar raken (opeenvolgend en op de kleinste afstand) rond hun eigen
    # zwaartepunt terugzetten; losse labels blijven exact op hun echte graad staan
    contact = [i for i in range(n - 1) if (x[i + 1] - x[i]) - nodig[i] < 0.05]
    groepen, huidig = [], []
    for i in range(n):
        huidig.append(i)
        if i not in contact:
            groepen.append(huidig)
            huidig = []
    if huidig:
        groepen.append(huidig)
    for groep in groepen:
        if len(groep) < 2:
            continue
        a, b = groep[0], groep[-1]
        correctie = sum(x[i] - ruw[i] for i in groep) / len(groep)
        if a > 0:
            correctie = min(correctie, (x[a] - x[a - 1]) - nodig[a - 1])
        if b < n - 1:
            correctie = min(correctie, (x[b + 1] - nodig[b]) - x[b])
        for i in groep:
            x[i] -= correctie

    return [xi % 360.0 for xi in x]


def _lichaam_dozen(p, hoek, spec, maten):
    """De dozen van de labelstukjes in beeldcoordinaten, voor de botsingstelling."""
    M, R, MA = spec["midden"], spec["stralen"], spec["maten"]
    cx, cy = M["x"], M["y"]
    dozen = []
    for i, t in enumerate(_lichaam_tokens(p, spec)):
        x, y = _xy(cx, cy, R["lichaam_keten"][i], hoek)
        w = _breedte(t["tekst"], t["grootte"], spec, t["sleutel"], maten)
        h = t["grootte"] * MA["hoogte_factor"]
        dozen.append((x - w / 2, y - h, x + w / 2, y + h))
    return dozen


def _overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _botsende_paren(lichamen, hoeken, spec, maten):
    """Welke labelketens raken elkaar? Dit is de meting die de plaatsing bijstelt (B4/B5)."""
    alle = []
    for p, h in zip(lichamen, hoeken):
        for b in _lichaam_dozen(p, h, spec, maten):
            alle.append((p["naam"], b))
    raak = set()
    for i in range(len(alle)):
        for j in range(i + 1, len(alle)):
            if alle[i][0] != alle[j][0] and _overlap(alle[i][1], alle[j][1]):
                raak.add(tuple(sorted((alle[i][0], alle[j][0]))))
    return raak


def tel_botsingen(blokken, kaart, spec, maten=None):
    """Meet, niet gokken: hoeveel labelstukjes raken elkaar (B4/B5, acceptatiecriterium)."""
    maten = maten if maten is not None else _maten(spec)
    alle = []
    for p, hoek, _ in blokken:
        for b in _lichaam_dozen(p, hoek, spec, maten):
            alle.append((p["naam"], b))
    raak = set()
    for i in range(len(alle)):
        for j in range(i + 1, len(alle)):
            if alle[i][0] != alle[j][0] and _overlap(alle[i][1], alle[j][1]):
                raak.add(tuple(sorted((alle[i][0], alle[j][0]))))
    return {"paren": sorted(raak), "aantal": len(raak)}


def naar_bestand(kaart, pad, **kwargs):
    svg, botsingen = teken(kaart, **kwargs)
    with open(pad, "w", encoding="utf-8") as f:
        f.write(svg)
    return svg, botsingen
