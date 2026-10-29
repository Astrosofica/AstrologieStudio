#!/usr/bin/env python3
"""IJking van het venstergeheugen (27 oktober 2026 (avond)): de stand, de vlaggen en de rustmaat.

Aanleiding: Jans klacht dat "kleiner" na een start in volledig scherm op een half scherm landde, en
daarna dat de gemaximaliseerde stand niet werd toegepast.

De weg daarheen, met de metingen die het besluit dragen:

  * Linux, echte Chromium (Xvfb 2560x1440): `--start-fullscreen` zonder maat geeft na "kleiner"
    1265x1415 - Chromium's eigen terugvalmaat.
  * Windows 11, Edge 156, scherm 1920x1080, werkgebied 1920x1032, gemeten in een ingelogde sessie:
      - `--window-size=800,600`            -> normal 800x600, herstelmaat 800x600
      - `--start-maximized`                -> maximized, **herstelmaat 945x1012** (Chromium's eigen
                                              standaard: halve breedte, bijna volle hoogte)
      - `--window-size=800,600 --start-maximized` -> normal 800x600: de maat wint
      - `--start-fullscreen` (+ maat)      -> normal, randloos, 1920x1080 (vlag wint hier wél)
      - tweede `--app=`-start terwijl de browser al draait -> alle vlaggen genegeerd (945x1012)
      - `SetWindowPlacement(max, herstel 800x600@40,40)` op datzelfde venster -> gemaximaliseerd, en
        na herstellen precies 800x600@40,40. Ook met een al draaiende browser.
      - F11 insturen -> volledig scherm; nog een F11 -> terug op 800x600@40,40.

Daarom sinds 27 okt 2026: de vlaggen zetten alleen nog de **beginmaat** (en bij volledig scherm de
vlag), en de **stand** zet de schil zelf met de Windows-API uit `schil/venster.py`.

Wat deze proef vastlegt (zonder browser, dus overal te draaien):

  1. geen staat -> gewoon, de vaste maat 1440x900;
  2. een gewoon venster -> precies die maat, met dezelfde beginmaat als herstelmaat;
  3. volledig scherm -> alleen de rustmaat: de stand zet de schil zelf met F11, want
     `--start-fullscreen` zet de herstelmaat op de schermmaat (gemeten: na F11 kwam het venster op
     1920x1080 in plaats van op de rustmaat);
  4. gemaximaliseerd -> de rustmaat en **geen** `--start-maximized`: die vlag zet Chromium's eigen
     herstelmaat (945x1012), en samen met `--window-size` wint de maat. In geen van de drie standen
     staat er nog een `--start-`-vlag:
  5. de Windows-vorm van volledig scherm: de buitenmaat blijft op de venstermaat staan en alleen het
     beeldvlak vult het scherm (Jans melding van 27 okt 2026, met zijn eigen getallen);
  6. de Windows-vorm van gemaximaliseerd: de buitenmaat vult het werkblad;
  7. de plaats gaat mee als `--window-position`, zodat het venster niet verspringt;
  8. een melding vanuit volledig scherm overschrijft de rustmaat **niet**;
  9. een nieuwe rustmaat wordt wel bewaard;
 10. onzin wordt geweigerd (1x2, `True`, geen lijst) en een kapot bestand valt terug op de vaste maat;
 11. op een machine zonder Windows doet `venster.pas_toe` niets (lege regel, geen crash);
 12. het kenmerk dat de schil in het adres zet, staat ook echt in de titel van de pagina.

Draaien:  /usr/bin/python3 ijking/ijk-venster.py
Schrijft: ijking/uitkomsten-<datum>-venster.md
"""

import datetime
import json
import os
import re
import shutil
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from schil import server, venster  # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HIER)
VANDAAG = datetime.date.today().isoformat()
NAAM = "venster"
PROEFMAP = os.path.expanduser("~/.hermes/cache/scratch/ijk-venster")

SCHERM = [2560, 1440]
WERKBLAD = [2560, 1400]

regels = []
uit = []


def schrijf(t=""):
    regels.append(t)
    print(t)


def zet(staat):
    """Schrijf een proefstaat weg (of verwijder het bestand bij None) en geef de vlaggen terug."""
    pad = server._vensterstaat_pad()
    if os.path.exists(pad):
        os.remove(pad)
    if staat is not None:
        with open(pad, "w", encoding="utf-8") as f:
            if isinstance(staat, str):
                f.write(staat)
            else:
                json.dump(staat, f)
    return server.venster_vlaggen()


def beoordeel(naam, goed, uitleg=""):
    schrijf(f"- {'goed' if goed else 'FOUT'}: {uitleg}")
    uit.append((naam, goed))


_OORSPRONKELIJK = {}


def _namaak_api(schaal, monitor_breed, negeer=False):
    """Een namaak-venster-API om de schaalberekening te beproeven (zonder browser, zonder Windows).

    `schaal` is hoeveel API-eenheden er in één CSS-pixel gaan; `monitor_breed` is wat de namaak als
    schermbreedte teruggeeft. Met `negeer=True` levert hij een kleinere maat dan gevraagd, zoals een
    vensterbeheerder die klemt - om te zien of de schil dat meldt in plaats van het goed te praten.

    Geeft `(api, vraag)` terug; `vraag` vult zich met wat de schil werkelijk vroeg.
    """
    import ctypes

    bewaard = {}
    vraag = {}

    class Api:
        def SetWindowPlacement(self, hwnd, ref):
            p = ctypes.cast(ref, ctypes.POINTER(venster._Plaatsing)).contents
            k = venster._Plaatsing()
            k.lengte = p.lengte
            k.vlaggen = p.vlaggen
            k.stand = p.stand
            k.herstel.links = p.herstel.links
            k.herstel.boven = p.herstel.boven
            k.herstel.rechts = p.herstel.rechts
            k.herstel.onder = p.herstel.onder
            if negeer:
                k.herstel.rechts = k.herstel.links + 1440
                k.herstel.onder = k.herstel.boven + 900
            vraag["breed"] = p.herstel.rechts - p.herstel.links
            vraag["hoog"] = p.herstel.onder - p.herstel.boven
            bewaard["p"] = k
            return 1

        def GetWindowPlacement(self, hwnd, ref):
            if "p" not in bewaard:
                return 0
            ctypes.cast(ref, ctypes.POINTER(venster._Plaatsing))[0] = bewaard["p"]
            return 1

    def namaak_monitor(api, hwnd):
        info = types.SimpleNamespace()
        info.monitor = venster._Rechthoek()
        info.monitor.links, info.monitor.boven = 0, 0
        info.monitor.rechts, info.monitor.onder = monitor_breed, int(monitor_breed * 0.5625)
        info.werkblad = venster._Rechthoek()
        info.werkblad.links, info.werkblad.boven = 0, 0
        info.werkblad.rechts = monitor_breed
        info.werkblad.onder = info.monitor.onder - 48
        return info

    for naam, waarde in (("_koppel", lambda: Api()), ("_monitor", namaak_monitor),
                         ("_vult_scherm", lambda api, hwnd: False),
                         ("_bewust", lambda: 0), ("beschikbaar", lambda: True)):
        _OORSPRONKELIJK.setdefault(naam, getattr(venster, naam))
        setattr(venster, naam, waarde)
    if "zoek" not in _OORSPRONKELIJK:
        _OORSPRONKELIJK["zoek"] = venster.zoek
    venster.zoek = lambda kenmerk, wacht=0: 1
    return Api(), vraag


def _herstel_namaak():
    for naam, waarde in _OORSPRONKELIJK.items():
        setattr(venster, naam, waarde)


def main():
    if os.path.exists(PROEFMAP):
        shutil.rmtree(PROEFMAP)
    os.makedirs(PROEFMAP)
    bewaard = os.environ.get("ASTRO_HOROSCOPENMAP")
    os.environ["ASTRO_HOROSCOPENMAP"] = PROEFMAP

    schrijf(f"# IJking van het venstergeheugen - {VANDAAG}")
    schrijf()
    schrijf(f"Proefmap: `{PROEFMAP}` (de horoscopen en de vensterstaat van Jan blijven ongemoeid).")
    schrijf(f"Scherm in de proef: {SCHERM[0]}x{SCHERM[1]}, werkblad {WERKBLAD[0]}x{WERKBLAD[1]}.")
    schrijf()

    # 1. geen staat
    vlaggen = zet(None)
    stand, rust, _ = server.venster_stand()
    schrijf("## 1. Nog niets gemeld")
    schrijf()
    schrijf(f"- stand `{stand}`, vlaggen `{' '.join(vlaggen)}`")
    beoordeel("geen_staat", stand == venster.STAND_GEWOON and vlaggen == ["--window-size=1440,900"],
              "de vaste maat van de app, geen stand")
    schrijf()

    # 2. een gewoon venster
    vlaggen = zet({"buiten": [1800, 1000], "scherm": SCHERM, "beschikbaar": WERKBLAD,
                   "rust": [1800, 1000]})
    stand, rust, _ = server.venster_stand()
    schrijf("## 2. Gewoon venster, 1800x1000")
    schrijf()
    schrijf(f"- stand `{stand}`, vlaggen `{' '.join(vlaggen)}`")
    beoordeel("gewoon_venster", stand == venster.STAND_GEWOON
              and vlaggen == ["--window-size=1800,1000"] and rust == (1800, 1000),
              "precies de maat waarin hij sloot, en die maat is ook de herstelmaat")
    schrijf()

    # 3. volledig scherm: rustmaat plus de vlag
    vlaggen = zet({"buiten": SCHERM, "scherm": SCHERM, "beschikbaar": WERKBLAD,
                   "rust": [1800, 1000]})
    stand, rust, _ = server.venster_stand()
    schrijf("## 3. Volledig scherm")
    schrijf()
    schrijf(f"- stand `{stand}`, vlaggen `{' '.join(vlaggen)}`")
    beoordeel("volledig_scherm", stand == venster.STAND_VOLLEDIG
              and vlaggen == ["--window-size=1800,1000"],
              "alleen de rustmaat: de stand zet de schil zelf, want `--start-fullscreen` zet de "
              "herstelmaat op de schermmaat")
    schrijf()

    # 4. gemaximaliseerd: geen --start-maximized, en in geen enkele stand een --start-vlag
    maxi = zet({"buiten": [2560, 1400], "scherm": SCHERM, "beschikbaar": WERKBLAD,
                "rust": [1800, 1000]})
    stand, rust, _ = server.venster_stand()
    schrijf("## 4. Gemaximaliseerd")
    schrijf()
    schrijf(f"- stand `{stand}`, vlaggen `{' '.join(maxi)}`")
    geen_startvlag = True
    for proef in ({"buiten": [1800, 1000], "scherm": SCHERM, "beschikbaar": WERKBLAD},
                  {"buiten": [2560, 1400], "scherm": SCHERM, "beschikbaar": WERKBLAD},
                  {"buiten": SCHERM, "scherm": SCHERM, "beschikbaar": WERKBLAD}):
        if any(v.startswith("--start-") for v in zet(proef)):
            geen_startvlag = False
    beoordeel("gemaximaliseerd", stand == venster.STAND_GEMAXIMALISEERD
              and maxi == ["--window-size=1800,1000"] and geen_startvlag,
              "de rustmaat, en in geen van de drie standen nog een `--start-`-vlag")
    schrijf()

    # 5. de Windows-vorm van volledig scherm: buiten blijft 1444x900, het beeldvlak vult het scherm
    vlaggen = zet({"buiten": [1444, 900], "binnen": [2134, 1200], "scherm": [2134, 1200],
                   "beschikbaar": [2134, 1160], "rust": [1444, 900]})
    stand, _, _ = server.venster_stand()
    schrijf("## 5. Volledig scherm zoals Windows-Edge het meldt")
    schrijf()
    schrijf(f"- stand `{stand}`, vlaggen `{' '.join(vlaggen)}`")
    beoordeel("windows_volledig", stand == venster.STAND_VOLLEDIG
              and vlaggen == ["--window-size=1444,900"],
              "het beeldvlak vult het scherm, dus volledig scherm - ook al zegt de buitenmaat "
              "1444x900")
    schrijf()

    # 6. de Windows-vorm van gemaximaliseerd: de buitenmaat vult het werkblad
    vlaggen = zet({"buiten": [2134, 1160], "binnen": [2134, 1104], "scherm": [2134, 1200],
                   "beschikbaar": [2134, 1160], "rust": [1444, 900]})
    stand, _, _ = server.venster_stand()
    schrijf("## 6. Gemaximaliseerd zoals Windows het meldt")
    schrijf()
    schrijf(f"- stand `{stand}`, vlaggen `{' '.join(vlaggen)}`")
    beoordeel("windows_gemaximaliseerd", stand == venster.STAND_GEMAXIMALISEERD
              and vlaggen == ["--window-size=1444,900"],
              "het werkblad gevuld is gemaximaliseerd, geen volledig scherm")
    schrijf()

    # 7. de plaats gaat mee
    vlaggen = zet({"buiten": [1800, 1000], "scherm": SCHERM, "beschikbaar": WERKBLAD,
                   "rust": [1800, 1000], "links": [40, 60]})
    _, _, positie = server.venster_stand()
    schrijf("## 7. De plaats van het venster")
    schrijf()
    schrijf(f"- vlaggen `{' '.join(vlaggen)}`")
    beoordeel("positie", positie == (40, 60)
              and vlaggen == ["--window-size=1800,1000", "--window-position=40,60"],
              "de gemelde plaats gaat mee als `--window-position`")
    schrijf()

    # 8 en 9. de rustmaat bewaren
    server.bewaar_vensterstaat({"buiten": [1800, 1000], "scherm": SCHERM, "beschikbaar": WERKBLAD,
                                "rust": [1800, 1000]})
    server.bewaar_vensterstaat({"buiten": SCHERM, "scherm": SCHERM, "beschikbaar": WERKBLAD})
    staat = server.lees_vensterstaat() or {}
    schrijf("## 8. Een melding vanuit volledig scherm")
    schrijf()
    schrijf(f"- bewaard: `{json.dumps(staat)}`")
    beoordeel("rust_blijft", staat.get("rust") == [1800, 1000] and staat.get("buiten") == SCHERM,
              "de buitenmaat is bijgewerkt, de rustmaat niet overschreven")
    schrijf()

    server.bewaar_vensterstaat({"buiten": SCHERM, "scherm": SCHERM, "beschikbaar": WERKBLAD,
                                "rust": [2000, 1200]})
    staat = server.lees_vensterstaat() or {}
    schrijf("## 9. Een nieuwe rustmaat")
    schrijf()
    schrijf(f"- bewaard: `{json.dumps(staat)}`")
    beoordeel("nieuwe_rust", staat.get("rust") == [2000, 1200],
              "een nieuwe maat wordt overgenomen")
    schrijf()

    # 10. onzin
    schrijf("## 10. Onzin wordt geweigerd")
    schrijf()
    goed = True
    for onzin, waarom in (({"buiten": [1, 2]}, "1x2 is geen venster"),
                          ({"buiten": [True, 800]}, "True is geen maat"),
                          (["geen", "dict"], "geen object"),
                          ({"buiten": "1920x1080"}, "geen lijst")):
        try:
            server.bewaar_vensterstaat(onzin)
            schrijf(f"- FOUT: `{onzin}` werd opgeslagen, terwijl {waarom}")
            goed = False
        except ValueError as e:
            schrijf(f"- goed: `{onzin}` geweigerd ({waarom}): {e}")
    vlaggen = zet("geen json")
    stand, _, _ = server.venster_stand()
    schrijf(f"- een kapot bestand geeft stand `{stand}` en `{' '.join(vlaggen)}`")
    goed = goed and vlaggen == ["--window-size=1440,900"] and stand == venster.STAND_GEWOON
    beoordeel("onzin_geweigerd", goed,
              "een kapot bestand is geen crash maar de vaste maat")
    schrijf()

    # 11. zonder Windows doet de venstermodule niets
    schrijf("## 11. De venstermodule op een machine zonder Windows")
    schrijf()
    if os.name == "nt":
        schrijf("- overgeslagen: deze proef draait op Windows, daar doet de module wél iets")
        uit.append(("geen_windows", True))
    else:
        regel, gelukt = venster.pas_toe(venster.STAND_GEMAXIMALISEERD, (1440, 900),
                                       kenmerk="bestaat-niet", wacht=0.5)
        schrijf(f"- `pas_toe(...)` geeft `{regel!r}` (gelukt: {gelukt}), "
                f"`beschikbaar()` is {venster.beschikbaar()}")
        beoordeel("geen_windows", regel == "" and gelukt is False
                  and venster.beschikbaar() is False,
                  "geen Windows, dus geen aanroep en geen wachttijd")
    schrijf()

    # 12. het kenmerk staat in de titel van de pagina
    schrijf("## 12. Het kenmerk in de venstertitel")
    schrijf()
    with open(os.path.join(PROJECT, "schil", "static", "index.html"), encoding="utf-8") as f:
        pagina = f.read()
    heeft_lezen = bool(re.search(r'URLSearchParams\(location\.search\)\.get\("vt"\)', pagina))
    heeft_zetten = bool(re.search(r'document\.title\s*\+=', pagina))
    schrijf(f"- leest `?{venster.TOKEN_SLEUTEL}=` uit het adres: {heeft_lezen}")
    schrijf(f"- zet het in `document.title`: {heeft_zetten}")
    schrijf(f"- het kenmerk van deze start: `{venster.token()}`")
    beoordeel("kenmerk_in_titel", heeft_lezen and heeft_zetten
              and venster.token() == "as%d" % os.getpid(),
              "de schil kan het venster terugvinden op de titel")
    schrijf()

    schrijf("## 13. De tekst in het startblok")
    schrijf()
    zet({"buiten": [2134, 1160], "binnen": [2134, 1104], "scherm": [2134, 1200],
         "beschikbaar": [2134, 1160], "rust": [1444, 900]})
    tekst = server.venster_tekst()
    schrijf(f"- `{tekst}`")
    beoordeel("startblok_tekst", tekst == "gemaximaliseerd (herstelmaat 1444 x 900)",
              "de console zegt de stand én de maat waar \"kleiner\" op landt")
    schrijf()

    # 14. de schaal: de venster-API in beeldpunten, de pagina in CSS-pixels
    schrijf("## 14. De schaal tussen de pagina en de venster-API")
    schrijf()
    schrijf("De monitor die de API ziet is 2560 breed, de pagina meldt een scherm van 2134: dat is")
    schrijf("weergave 120 %, en dan moet een gevraagde 1444 neerkomen op 1733 in de API. Dit is de")
    schrijf("fout die Jan zag (`1440 x 900` werd `1200 x 751`): de maat ging er in de verkeerde")
    schrijf("eenheid in. De namaak hieronder is een venster-API die precies doet wat Windows doet.")
    schrijf()
    for schaal, monitor, scherm_breed, uitleg in (
            (1.2, 2560, 2134, "120 % weergave: 1444 wordt ±1732"),
            (1.0, 1920, 1920, "100 %: de maat gaat er ongewijzigd in"),
            (1.5, 3200, 2134, "150 %: 1444 wordt ±2165")):
        # De schaal komt uit monitor / scherm, dus 2560 / 2134 = 1,1996 en geen 1,20 precies.
        verwacht = round(1444 * monitor / scherm_breed)
        namaak, gevraagd = _namaak_api(schaal, monitor)
        regel, gelukt = venster.pas_toe(venster.STAND_GEWOON, (1444, 900), (0, 0), "proef",
                                        scherm=(scherm_breed, 1200), wacht=0.1)
        schrijf(f"- {uitleg}: gevraagd aan de API {gevraagd['breed']} x {gevraagd['hoog']} "
                f"(breedte moet {verwacht}), regel `{regel}`")
        goed = gevraagd["breed"] == verwacht and regel.startswith("1444 x 900") and gelukt
        uit.append((f"schaal_{schaal}", goed))
        schrijf(f"- {'goed' if goed else 'FOUT'}")
        _herstel_namaak()
    schrijf()

    # 15. een maat die niet wordt overgenomen wordt gemeld, niet goedgepraat
    namaak, gevraagd = _namaak_api(1.2, 2560, negeer=True)
    regel, gelukt = venster.pas_toe(venster.STAND_GEWOON, (1444, 900), (0, 0), "proef",
                                    scherm=(2134, 1200), wacht=0.1)
    schrijf("## 15. Een maat die Windows niet overneemt")
    schrijf()
    schrijf(f"- regel `{regel}`")
    _herstel_namaak()
    beoordeel("maat_gemeld", "niet overgenomen" in regel and "1200" in regel and not gelukt,
              "de console zegt gevraagd én gemeten, in plaats van \"geslaagd\"")
    schrijf()

    # 16. de beginmaat gaat in de eenheid van de browser
    schrijf("## 16. De beginmaat van de browser")
    schrijf()
    schrijf("Chromium leest `--window-size` in beeldpunten: bij Jan gaf 1440 een venster van 1200")
    schrijf("CSS-pixels, en die eerste meting werd als rustmaat bewaard (de krimp). Daarom krijgt de")
    schrijf("beginmaat dezelfde schaal mee als de venster-API.")
    schrijf()
    vlaggen = zet({"buiten": [1440, 900], "scherm": SCHERM, "beschikbaar": WERKBLAD,
                   "rust": [1440, 900], "links": [40, 40]})
    schrijf(f"- op deze machine (geen Windows): schaal {venster.beginschaal((SCHERM[0], SCHERM[1]))}, "
            f"vlaggen `{' '.join(vlaggen)}`")
    beoordeel("beginmaat_eenheid", venster.beginschaal((SCHERM[0], SCHERM[1])) == 1.0
              and vlaggen == ["--window-size=1440,900", "--window-position=40,40"],
              "zonder Windows verandert er niets; op Windows gaat de schaal erin")
    schrijf()

    # 17. de schil bewaart de rustmaat die ze zelf heeft gezet
    schrijf("## 17. De rustmaat die de schil zelf zet")
    schrijf()
    zet({"buiten": [1200, 750], "scherm": SCHERM, "beschikbaar": WERKBLAD, "rust": [1200, 750]})
    server.bewaar_rust((1440, 900))
    staat = server.lees_vensterstaat() or {}
    schrijf(f"- na `bewaar_rust((1440, 900))`: `{json.dumps(staat)}`")
    beoordeel("rust_door_de_schil", staat.get("rust") == [1440, 900]
              and staat.get("buiten") == [1200, 750],
              "de rustmaat is bijgezet zonder de gemelde maten te verzinnen")
    schrijf()

    # 18. Het werkblad is kleiner dan de bewaarde maat (28 okt 2026, proef op een klein scherm)
    schrijf("## 18. Een werkblad dat kleiner is dan de bewaarde maat")
    schrijf()
    schrijf("Melding van 28 okt 2026, uit een proef op een klein scherm: bij 150 % weergave kreeg")
    schrijf("ze geen groene statusbalk onderin - die viel achter de taakbalk. Maximaliseren verhielp")
    schrijf("het, want dan houdt de browser zichzelf binnen het werkblad. Gewoon openen deed dat niet:")
    schrijf("de schil gaf de bewaarde maat ongeklemd door.")
    schrijf()
    klein_scherm, klein_werkblad = [1920, 1080], [1280, 688]
    schrijf(f"- `klem_maat((1440, 900), (1280, 688))` = `{venster.klem_maat((1440, 900), klein_werkblad)}`")
    schrijf(f"- `klem_maat((1440, 900), None)` = `{venster.klem_maat((1440, 900), None)}` "
            "(geen werkblad gemeld: ongewijzigd)")
    schrijf(f"- `klem_maat((1000, 600), (1280, 688))` = `{venster.klem_maat((1000, 600), klein_werkblad)}` "
            "(past hij, dan blijft hij)")
    # De stand van een gemaximaliseerd venster op dat scherm: de buitenmaat vult het werkblad, en de
    # herstelmaat (waar "kleiner" op landt) is de maat van het grote scherm.
    zet({"buiten": [1280, 688], "binnen": [1280, 664], "scherm": klein_scherm,
         "beschikbaar": klein_werkblad, "rust": [1440, 900], "links": [0, 0]})
    stand, rust, _ = server.venster_stand()
    schrijf(f"- stand `{stand}`, rust `{rust}`")
    beoordeel("klem_werkblad", venster.klem_maat((1440, 900), klein_werkblad) == (1280, 688)
              and venster.klem_maat((1000, 600), klein_werkblad) == (1000, 600)
              and stand == venster.STAND_GEMAXIMALISEERD and rust == (1280, 688),
              "de bewaarde maat wordt tot het werkblad teruggebracht, een maat die past blijft staan")
    schrijf()

    # 19. De schil klemt ook als er nog geen staat is: het werkblad wordt dan aan Windows gevraagd
    schrijf("## 19. De klem bij het plaatsen, ook op de eerste start")
    schrijf()
    schrijf("Op de eerste start is er geen `venster.json` met een werkblad erin. De schil vraagt de")
    schrijf("werkmaat dan aan Windows zelf, via de monitor van het venster. Zo werkt de klem ook")
    schrijf("wanneer er nog niets bewaard is - en zonder dat het als mislukking wordt gemeld.")
    schrijf()
    _, vraag = _namaak_api(1.0, 1280)
    regel, gelukt = venster.pas_toe(venster.STAND_GEWOON, (1440, 900))
    schrijf(f"- gevraagd 1440x900, werkblad 1280x672: de schil zette {vraag.get('breed')}x{vraag.get('hoog')}")
    schrijf(f"- regel `{regel}`, gelukt `{gelukt}`")
    _herstel_namaak()
    beoordeel("klem_bij_plaatsen", vraag.get("breed") == 1280 and vraag.get("hoog") == 672
              and gelukt and "geklemd op het werkblad" in regel,
              "de maat past op het werkblad, en de console zegt dat hij geklemd is")
    schrijf()

    # 20. De mutex waaraan de installer ziet dat het programma draait (28 okt 2026)
    schrijf("## 20. De mutex voor de installer")
    schrijf()
    schrijf("Bij Jan mislukte het installeren van een nieuwe versie terwijl het programma draaide: Inno")
    schrijf("probeerde het venster te sluiten, dat lukte niet, en daarna was het programma ook niet meer")
    schrijf("netjes af te sluiten. Nu maakt de app een mutex en weigert de installer (AppMutex).")
    schrijf("Hier met een namaak-Windows-API, want op deze machine bestaat CreateMutexW niet.")
    schrijf()
    gevraagd = {}

    def namaak_maak(attr, initial, naam):
        gevraagd["naam"] = naam
        gevraagd["initial"] = initial
        return 4242

    # SimpleNamespace en geen eigen klasse: `maak_mutex()` zet `restype` op de functie, en dat kan
    # alleen op een gewoon functieobject (niet op een gebonden methode).
    api = types.SimpleNamespace(CreateMutexW=namaak_maak)
    bewaard_kernel32, bewaard_mutex, bewaard_naam = server._kernel32, server._MUTEX, server.MUTEX_NAAM
    server._kernel32 = lambda: api
    server._MUTEX = None
    handvat = server.maak_mutex()
    tweede = server.maak_mutex()
    server._kernel32 = lambda: None          # geen Windows
    server._MUTEX = None
    zonder = server.maak_mutex()
    server._kernel32, server._MUTEX = bewaard_kernel32, bewaard_mutex
    schrijf(f"- gevraagd: `{gevraagd}`; handvat `{handvat}`; tweede aanroep `{tweede}`")
    schrijf(f"- zonder Windows: `{zonder}` (geen crash, geen mutex nodig)")
    beoordeel("mutex", gevraagd.get("naam") == bewaard_naam and handvat == 4242 and tweede == 4242
              and zonder is None,
              "de app maakt één mutex met de vaste naam, en doet op een ander systeem niets")
    schrijf()

    # opruimen
    pad = server._vensterstaat_pad()
    if os.path.exists(pad):
        os.remove(pad)
    if bewaard is None:
        os.environ.pop("ASTRO_HOROSCOPENMAP", None)
    else:
        os.environ["ASTRO_HOROSCOPENMAP"] = bewaard
    shutil.rmtree(PROEFMAP, ignore_errors=True)

    schrijf("## Uitkomst")
    schrijf()
    geslaagd = [naam for naam, ok in uit if ok]
    mislukt = [naam for naam, ok in uit if not ok]
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
