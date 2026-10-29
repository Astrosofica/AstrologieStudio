#!/usr/bin/env python3
"""IJkpunt voor het font: raakt geen enkele glyph de randen van zijn band?

Draaien:  /usr/bin/python3 ijking/ijk-font.py [kaartbestand]

Waarom. Een fontwissel verandert de *vorm* van de glyphs, en daarmee of een glyph binnen zijn band
past. Twee plekken zijn daar gevoelig voor:

1. **de cusplabels in de buitenste band** (cuspband_binnen 442 -> buitenrand 478, 36 eenheden). De
   stukjes staan rechtop langs de tangent van hun cusp, dus op 3 en 9 uur loopt hun *breedte* in de
   richting van de band; het glyphstukje (letters.cusp_teken) is het grootste van de drie en het
   stukje dat de rand raakt. Gemeten met PIL (anchor midden-midden, precies wat
   `text-anchor:middle` + `dominant-baseline:middle` doet).
2. **de zodiakring** (zodiakring_binnen 400 -> cuspband_binnen 442). Elke ringglyph staat op de
   15-graad van zijn teken, waar een tikje naar buiten wijst; de glyphcontour wordt hier met de
   juiste em-uitlijning geplaatst (penvoorsprong/2 naar links, (ascent+descent)/2 naar beneden - dat
   is wat de browser doet, en het is precies de fout die een eerdere meting een glyph ten onrechte
   tegen een tikje liet raken).

Uitkomst: per stukje de kleinste afstand tot de binnen- en buitenrand. Negatief betekent: over de
rand heen, en dan zegt dit script dat met zoveel woorden. Een glyph die de band raakt is geen
rekenfout maar een tekening die niet klopt, dus dit hoort bij elke fontwissel opnieuw te draaien.
"""
from __future__ import annotations

import copy
import math
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

HIER = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HIER)
sys.path.insert(0, PROJECT)

from kern import invoer, kaart as kern_kaart, opslag  # noqa: E402
from teken import wiel  # noqa: E402

STANDAARD_KAART = "controle-1963-07-19.json"
PIECES = 200
CX = CY = 500


# De kaart van de proef. Stond hier als bestandsnaam van een bewaarde horoscoop; sinds 29 okt 2026
# rekent de proef hem rechtstreeks uit de kern als dat bestand ontbreekt, zodat een verse kopie van de
# bron (zonder horoscopenmap) hetzelfde ijkpunt heeft en er geen persoonsnaam in een pad staat.
CONTROLE = dict(naam="Controle", jaar=1963, maand=7, dag=19, uur=16, minuut=51, seconde=26,
                tijdzone_id="Europe/Amsterdam", lat=51.675, lon=4.27917, plaats="Langstraat",
                huizenstelsel="K")


def _kaart(bestand):
    try:
        m = opslag.lees(bestand)["meta"]
    except (invoer.InvoerFout, OSError):
        return kern_kaart.maak_kaart(**CONTROLE)
    g = invoer.lees({"naam": m["naam"], "datum": m["datum"], "tijd": m["tijd"], "plaats": m["plaats"],
                     "lat": m["lat"], "lon": m["lon"], "tijdzone_id": m["tijdzone_id"],
                     "huizenstelsel": m["huizenstelsel"],
                     "tijdcorrectie": m.get("tijdcorrectie", "zone"),
                     "met_chiron": m.get("met_chiron", False)})
    return kern_kaart.maak_kaart(
        naam=g["naam"], jaar=g["jaar"], maand=g["maand"], dag=g["dag"], uur=g["uur"],
        minuut=g["minuut"], seconde=g["seconde"], tijdzone_id=g["tijdzone_id"], lat=g["lat"],
        lon=g["lon"], plaats=g["plaats"], huizenstelsel=g["huizenstelsel"],
        tijdcorrectie=g["tijdcorrectie"], met_chiron=g["met_chiron"])


def _inktdoos(tekst, fontpad, grootte):
    """De inktdoos van een stukje tekst, ten opzichte van het anker (midden-midden)."""
    letter = ImageFont.truetype(fontpad, PIECES)
    beeld = Image.new("L", (PIECES * 4, PIECES * 4), 0)
    ImageDraw.Draw(beeld).text((PIECES * 2, PIECES * 2), tekst, font=letter, fill=255, anchor="mm")
    doos = beeld.getbbox()
    if doos is None:
        return None
    schaal = PIECES / float(grootte)
    m = PIECES * 2
    return tuple((v - m) / schaal for v in doos)


def _ring_punten(font, cp, grootte):
    """De contour van een ringglyph in tekeningeenheden, met de em-uitlijning van de browser."""
    from fontTools.pens.recordingPen import RecordingPen

    upem = font["head"].unitsPerEm
    naam = font.getBestCmap()[cp]
    adv = font["hmtx"][naam][0]
    midden = (font["hhea"].ascent + font["hhea"].descent) / 2.0
    schaal = grootte / upem
    rec = RecordingPen()
    font.getGlyphSet()[naam].draw(rec)
    uit = []
    for op, punten in rec.value:
        if op in ("moveTo", "lineTo", "qCurveTo", "curveTo"):
            uit += [((-adv / 2.0 + x) * schaal, (midden - y) * schaal)
                    for (x, y) in punten if (x, y) is not None]
    return uit


def _afstand_lijn(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def main():
    from fontTools.ttLib import TTFont

    bestand = sys.argv[1] if len(sys.argv) > 1 else STANDAARD_KAART
    spec = wiel.laad_spec()
    R, G = spec["stralen"], spec["letters"]
    fontpad = os.path.join(PROJECT, spec["glyph_font"]["bestand"])
    font = TTFont(fontpad)
    svg, botsingen = wiel.teken(_kaart(bestand), spec)
    R_ = spec["stralen"]
    over = []

    # 1. de cusplabels in de buitenste band
    binnen, buiten = R["cuspband_binnen"], R["buitenrand"]
    print(f"cusplabels in de band {binnen}-{buiten} (glyph op {G['cusp_teken']} pt, cijfers op "
          f"{G['cusp_label']} pt)")
    krap = []
    for m in re.finditer(r'<text class="cusp-label(?: ([a-z]+))?" x="([\d.]+)" y="([\d.]+)" '
                         r'font-size="(\d+)"[^>]*>([^<]*)</text>', svg):
        x, y, grootte, tekst = float(m.group(2)), float(m.group(3)), int(m.group(4)), m.group(5)
        doos = _inktdoos(tekst, fontpad, grootte)
        if doos is None:
            continue
        stralen = [math.hypot(x + dx - CX, y + dy - CY)
                   for dx in (doos[0], doos[2]) for dy in (doos[1], doos[3])]
        vrij_in, vrij_uit = min(stralen) - binnen, buiten - max(stralen)
        krap.append((min(vrij_in, vrij_uit), tekst, grootte, vrij_in, vrij_uit))
        if min(vrij_in, vrij_uit) < 0:
            over.append(f"cusplabel {tekst!r} ({grootte} pt): {min(vrij_in, vrij_uit):+.2f} over de rand")
    for vrij, tekst, grootte, vrij_in, vrij_uit in sorted(krap)[:4]:
        print(f"    {tekst!r:8} {grootte:2} pt: naar binnen {vrij_in:6.2f}  naar buiten {vrij_uit:6.2f}")

    # 2. de ringglyphs in de zodiakring
    binnen_ring, buiten_ring = R_["zodiakring_binnen"], R_["cuspband_binnen"]
    tik = R_["zodiak_tik"]
    print(f"\nringglyphs tussen {binnen_ring} en {buiten_ring} (glyph op {G['zodiak_teken']} pt, "
          f"tikken {tik['graad']}/{tik['kort']}/{tik['lang']})")
    deel = svg.split('<g id="laag-zodiak">')[1].split("</g>")[0]
    krap = []
    for m in re.finditer(r'<text class="glyf" x="([\d.]+)" y="([\d.]+)" font-size="(\d+)"[^>]*>([^<])</text>',
                         deel):
        x, y, grootte, ch = float(m.group(1)), float(m.group(2)), int(m.group(3)), m.group(4)
        punten = [(x + px, y + py) for px, py in _ring_punten(font, ord(ch), grootte)]
        if not punten:
            continue
        hoek_glyph = math.atan2(y - CY, x - CX)
        d_rand = min(abs(math.hypot(px - CX, py - CY) - binnen_ring) for px, py in punten)
        d_uit = min(buiten_ring - math.hypot(px - CX, py - CY) for px, py in punten)
        d_tik, welke = 9e9, None
        for gr in range(0, 30):
            lengte = tik["graad"] if gr % 5 else (tik["lang"] if gr % 10 == 0 else tik["kort"])
            hoek = hoek_glyph + math.radians(gr - 15.0)
            a = (CX + binnen_ring * math.cos(hoek), CY + binnen_ring * math.sin(hoek))
            b = (CX + (binnen_ring + lengte) * math.cos(hoek),
                 CY + (binnen_ring + lengte) * math.sin(hoek))
            for p in punten:
                d = _afstand_lijn(p, a, b)
                if d < d_tik:
                    d_tik, welke = d, gr
        vrij = min(d_rand, d_uit, d_tik)
        krap.append((vrij, ch, d_rand, d_uit, d_tik, welke))
        if vrij < 0:
            over.append(f"ringglyph {ch}: {vrij:+.2f} over de rand (tik op {welke} graden)")
    for vrij, ch, d_rand, d_uit, d_tik, welke in sorted(krap)[:4]:
        print(f"    {ch} : ringlijn {d_rand:6.2f}  cuspband {d_uit:6.2f}  tik op {welke:2}° {d_tik:6.2f}")

    print(f"\nbotstingen in het wiel: {botsingen['aantal']}")
    if over:
        print("\nNIET IN ORDE — deze stukjes komen over de rand:")
        for regel in over:
            print("  " + regel)
        raise SystemExit(1)
    print("alles vrij: geen enkel stukje komt over de rand van zijn band.")


if __name__ == "__main__":
    main()
