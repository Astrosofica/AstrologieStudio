#!/usr/bin/env python3
"""De schil van Astrologie Studio: een klein HTTP-proces op poort 8086.

Offline en lokaal (besluit T21): geen databank, geen accounts. De schil is dom - hij leest het
techniek-register, vraagt de kern om cijfers, geeft ze aan de tekenaar en levert de kaart als JSON
plus SVG aan de pagina.

Eén uitzondering sinds 19 oktober 2026: `POST /api/osm-zoek` vraagt OpenStreetMap naar een plaats
die de eigen lijst niet kent, en alleen als de gebruiker daar zelf om klikt (`schil/osm.py`, met de
regels van Nominatim erin: één verzoek per seconde, een User-Agent met het adres uit de
instellingen, en resultaten in `staat/osm-cache.json`).

Draaien:  /usr/bin/python3 schil/server.py [poort]
Bundel:   `--controle` doet een zelfcontrole (bestanden, efemeriden, een ijkkaart) en sluit af met
          0 of 1; zonder dat start de schil en opent in een bundel zelf de browser.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Waarmee de schil zich op zijn eigen poort bekendmaakt (`/api/leeft`). Zo weet een tweede start
# dat daar geen vreemd programma zit maar hijzelf, en zet hij geen tweede schil naast de eerste.
PROGRAMMA = "astrologie-studio"

# Staat op True in de versie zonder consolevenster (`bouw-windows.bat stil`). Dan is er geen
# scherm om naar te schrijven: geen access-log, en wat een gebruiker moet zien komt als
# Windows-melding in beeld.
STIL = False

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)

from kern import kaart as kern_kaart      # noqa: E402
from kern import elementen, heerschappen, instellingen as kern_instellingen, invoer as kern_invoer  # noqa: E402
from kern import opslag, paden, plaatsen, tijd   # noqa: E402
from kern.versie import VERSIE            # noqa: E402
from schil import osm                    # noqa: E402
from schil import venster                # noqa: E402
from teken import wiel                    # noqa: E402

# In ontwikkeling is dit de projectmap; in een bundel de uitgepakte map (zie `kern/paden.py`).
STATIC = paden.bron("schil", "static")
TECHNIEKEN = paden.bron("technieken")
POORT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8086
# Alleen op dit apparaat luisteren (20 okt 2026). De schil stond op 0.0.0.0, wat op de pc van een
# cursist betekent: de horoscopen van de hele les bereikbaar voor iedereen op hetzelfde netwerk, en
# een firewall-vraag bij de eerste start. Ontwikkelen op bot640 zet ASTRO_HOST=0.0.0.0 in het
# startcommando, want daar komt de browser van een andere machine.
HOST = os.environ.get("ASTRO_HOST", "127.0.0.1")


def _lees_json(pad):
    with open(pad, encoding="utf-8") as f:
        return json.load(f)


def _register():
    profiel = _lees_json(os.path.join(TECHNIEKEN, "jaar1.json"))
    uit = []
    for regel in profiel["technieken"]:
        pad = os.path.join(TECHNIEKEN, regel["id"] + ".json")
        if os.path.exists(pad):
            t = _lees_json(pad)
            t["aan"] = regel["aan"]
            uit.append(t)
    return {"profiel": profiel, "technieken": uit}


def _techniek_aan(techniek_id):
    """Staat deze techniek aan in het jaarprofiel? (de schakelaar uit besluit T2/T13)"""
    for regel in _lees_json(os.path.join(TECHNIEKEN, "jaar1.json"))["technieken"]:
        if regel["id"] == techniek_id:
            return bool(regel["aan"])
    return False


def _aanvullingen(kaart):
    """De aanvullingen van jaar 1 die in het jaarprofiel aanstaan, als kant-en-klare JSON."""
    uit = {}
    if _techniek_aan("element-kruis"):
        uit["element_kruis"] = elementen.verdeling(kaart)
    if _techniek_aan("heerschappen"):
        uit["heerschappen"] = {"schema": heerschappen.schema(),
                               "per_huis": heerschappen.per_huis(kaart),
                               "per_lichaam": heerschappen.per_lichaam(kaart)}
    return uit


def _invoer(vraag):
    """Eén veld uit het formulier -> de standaardvorm, of niets (26 okt 2026).

    De pagina vraagt dit als je een veld verlaat: dan komt `19.7.1963` terug als `19-07-1963` en
    `9u30` als `09:30:00`, en schrijft de pagina dat stil in het veld. Leeg of onleesbaar levert
    **geen** sleutel op - en dus ook geen markering: de keuring hoort bij Berekenen, niet bij het
    tabben door de velden. Wat hier terugkomt is altijd wat `lees()` ook zou lezen (zelfde lezer,
    geen tweede set regels in de pagina).
    """
    antwoord = {}
    for sleutel, keur in (("datum", kern_invoer.keur_datum), ("tijd", kern_invoer.keur_tijd)):
        if sleutel not in vraag:
            continue
        try:
            antwoord[sleutel] = keur(vraag.get(sleutel))
        except kern_invoer.InvoerFout:
            continue
    return antwoord


def _rekenen(vraag):
    """Vraag uit het formulier -> kaart, SVG en de aanvullingen.

    Lezen en keuren van de invoer gebeurt in `kern/invoer.py`; wat daar niet door komt is een
    InvoerFout met een boodschap in gewone taal (HTTP 400), geen 500 en geen Engelse fout.
    """
    g = kern_invoer.lees(vraag)
    k = kern_kaart.maak_kaart(
        naam=g["naam"],
        jaar=g["jaar"], maand=g["maand"], dag=g["dag"],
        uur=g["uur"], minuut=g["minuut"], seconde=g["seconde"],
        tijdzone_id=g["tijdzone_id"], lat=g["lat"], lon=g["lon"],
        plaats=g["plaats"],
        huizenstelsel=g["huizenstelsel"],
        tijdcorrectie=g["tijdcorrectie"],
        met_chiron=g["met_chiron"],
    )
    # de sectormaat van het wiel is een instelling in spec.json; de pagina mag hem per vraag
    # meekrijgen (nodig om de twee afdrukken naast elkaar te kunnen leggen, besluit T11b)
    spec = None
    if g["sectoren"]:
        spec = wiel.laad_spec()
        spec["orientatie"]["sectoren"] = g["sectoren"]
    svg, botsingen = wiel.teken(k, spec)
    return {"kaart": k, "svg": svg, "botsingen": botsingen,
            "sectoren": (spec or wiel.laad_spec())["orientatie"]["sectoren"],
            "invoer": {sleutel: g[sleutel] for sleutel in
                       ("naam", "plaats", "datum", "tijd", "tijdzone_id", "lat", "lon",
                        "huizenstelsel", "tijdcorrectie", "met_chiron")},
            # De invoer meldt wat er met de invoer aan de hand is (lege zone, plaats niet in de
            # lijst); de kaart meldt wat er met de berekening aan de hand is (Moshier-benadering).
            "waarschuwingen": g["waarschuwingen"] + list(k.get("waarschuwingen") or []),
            **_aanvullingen(k)}


def _nu_moment():
    """Het moment van de server: datum en tijd zoals hij ze zelf leest, plus UT.

    De pagina vult hiermee bij het openen het formulier (naam "Nu", dit moment, de locatie uit de
    instellingen) en rekent daarna gewoon. Zo blijft er één waarheid voor "nu" en hoeft de pagina
    niets over tijdzones te weten; de klok van een pc mag scheef staan zonder gevolg.
    """
    nu = datetime.datetime.now()
    return {"datum": nu.strftime("%Y-%m-%d"), "tijd": nu.strftime("%H:%M:%S"),
            "utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}


# --- Het venster en de schil sluiten samen (25 okt 2026) -----------------------------------------
# Het venster is van de browser, de schil is het programma - en tot nu toe stopte het ene niet als het
# andere stopte: het kruisje liet de schil draaien (gemeten: ±101 MB en een luisterende poort) en
# Bestand > Afsluiten liet het venster staan. Eén boekhouding repareert beide richtingen.
#
# Elke pagina meldt zich bij het laden met een eigen id (`POST /api/venster?id=…`) en meldt zich af
# met een beacon (`/api/afgesloten?id=…`) op `pagehide`. **Gemeten 25 okt 2026 in Chromium (Xvfb +
# openbox, venster gesloten via WM_DELETE zoals het kruisje): `beforeunload` én `pagehide` komen
# allebei aan, en de beacon arriveert nog terwijl de pagina al weg is.** De schil stopt pas als er
# géén venster meer over is - en pas na een korte wachttijd, want bij een verversing meldt de oude
# pagina zich af en de nieuwe zich meteen weer aan; zonder die wachttijd zou elke F5 het programma
# stoppen.
VENSTERS: dict = {}
VENSTERS_SLOT = threading.Lock()
WACHT_NA_SLUITEN = 3.0          # seconden: ruimte voor een verversing van de pagina
# Hoe lang het consolevenster blijft staan nadat het programma gestopt is: lang genoeg om de laatste
# mededeling te lezen, kort genoeg om niet te hoeven wachten. Geen toets, want een afsluiting hoort
# geen taak te zijn (Jans punt, 25 okt 2026).
NASTAREN = 5
# Alles van het verkeer op het scherm (`--log` of ASTRO_LOG=1). Zonder dat alleen wat misgaat: een
# geslaagd verzoek is geen mededeling aan de gebruiker (Jans punt, 25 okt 2026).
ALLES_OP_HET_SCHERM = "--log" in sys.argv[1:] or os.environ.get("ASTRO_LOG") == "1"


def _is_console():
    """Zit dit programma in een echt consolevenster (en niet in een pijp of een logbestand)?"""
    for stroom in (sys.stdin, sys.stdout):
        try:
            if stroom is None or not stroom.isatty():
                return False
        except Exception:
            return False
    return True


def _venstertitel(tekst):
    """De titel van het consolevenster (25 okt 2026): in de taakbalk zie je dan welke versie draait."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(tekst)
            return
        except Exception:
            pass                    # geen console (of geen Windows): dan gewoon niet
    try:
        if sys.stdout.isatty():
            sys.stdout.write("\033]0;%s\007" % tekst)
            sys.stdout.flush()
    except Exception:
        pass



# De maat van het laatst geprinte kader: het aftellen onder het sluitblok schrijft één regel opnieuw
# in plaats van het hele kader te herdrukken (28 okt 2026, Jans ontwerp).
_LAATSTE_KADER = {}


def _kader(titel, regels, breedte=None, telt=False):
    """Een kader om een paar regels: ASCII, meteen geflusht.

    Waarom ASCII en geen kadertekens als `╔═╗`: het consolevenster van Windows kan in een andere
    codepage staan (de .bat-bestanden zijn er al op aangepast) en dezelfde tekst kan in `fouten.log`
    belanden. Waarom flushen geen luxe is: zodra de uitvoer naar een bestand of pijp gaat, buffert
    Python blokgewijs en zie je van een afgebroken proces niets terug (gemeten 25 okt 2026).

    `breedte` is de kleinste **binnenmaat**: het start- en het sluitblok horen even breed te zijn,
    ook als het sluitblok kortere regels heeft (Jans tekening, 28 okt 2026: allebei 64 tekens breed).
    `telt` zegt dat de laatste regel de aftelregel is; `_tel_af()` gebruikt de maat hieronder om die
    regel later te overschrijven.
    """
    alles = ([titel] if titel else []) + list(regels)
    binnen = max(max(len(r) for r in alles) + 2, breedte or 0)
    streep = "+" + "=" * binnen + "+"
    uit = ["", streep]
    if titel:
        uit.append("| " + titel.ljust(binnen - 1) + "|")
        uit.append(streep)
    for regel in regels:
        uit.append("| " + regel.ljust(binnen - 1) + "|")
    uit.append(streep)
    print("\n".join(uit), flush=True)
    _LAATSTE_KADER.update({"binnen": binnen, "streep": streep, "telt": bool(telt)})


def _ansi_kan():
    """Kan deze console de cursor verplaatsen (ANSI)?

    Nodig voor het aftellen, want dat schrijft dezelfde regel elke seconde opnieuw. Het consolevenster
    van Windows doet dat pas als het proces `ENABLE_VIRTUAL_TERMINAL_PROCESSING` aanzet, en dat zet
    Python niet zelf. Lukt het niet, dan blijft de regel staan en wordt er alleen gewacht — liegen
    doet het programma dan niet.
    """
    if not _is_console():
        return False
    if os.name != "nt":
        return True                 # Linux en macOS: ANSI is de standaard
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        greep = kernel.GetStdHandle(-11)                 # STD_OUTPUT_HANDLE
        stand = ctypes.c_uint32()
        if not kernel.GetConsoleMode(greep, ctypes.byref(stand)):
            return False
        if stand.value & 0x0004:                         # stond al aan
            return True
        return bool(kernel.SetConsoleMode(greep, stand.value | 0x0004))
    except Exception:
        return False


def _teller_regel(seconde):
    """De onderste regel van het sluitblok (Jans tekst: "1 seconde", "0 seconden")."""
    return "Dit venster sluit vanzelf over %d seconde%s." % (seconde, "" if seconde == 1 else "n")


def _kan_aftellen(binnen):
    """Komt het aftellen ook echt in beeld?

    Drie voorwaarden: een echt consolevenster, een cursor die vooruit kan (ANSI), en een venster dat
    breder is dan het kader — anders wikkelt een regel en zet de sprong van twee regels de tekst op
    de verkeerde plek.
    """
    if not _ansi_kan():
        return False
    try:
        return shutil.get_terminal_size().columns > binnen + 2
    except Exception:
        return False


def _tel_af(seconden):
    """Tel af in de onderste regel van het laatste kader: "over 4 ... 0 seconden".

    Twee regels omhoog (de aftelregel en de streep eronder), de nieuwe tekst, en de streep weer
    neerzetten — het kader blijft staan en alleen die regel verandert (Jans ontwerp, 28 okt 2026).
    Zonder console of zonder ANSI wordt er niets geschreven en alleen gewacht.
    """
    kader = dict(_LAATSTE_KADER)
    if not kader.get("telt") or not _kan_aftellen(kader["binnen"]):
        time.sleep(seconden)
        return
    for seconde in range(int(seconden) - 1, -1, -1):
        try:
            time.sleep(1.0)
        except (KeyboardInterrupt, OSError):
            return
        sys.stdout.write("\033[2A\r| " + _teller_regel(seconde).ljust(kader["binnen"] - 1)
                         + "|\n" + kader["streep"] + "\n")
        sys.stdout.flush()


def _venster_meld(tid):
    """Een venster doet mee. Geeft het aantal open vensters terug."""
    with VENSTERS_SLOT:
        if tid:
            VENSTERS[tid] = time.monotonic()
        return len(VENSTERS)


def _venster_weg(tid, server):
    """Een venster is weg. Was het de laatste, dan gaat de aftelling lopen."""
    with VENSTERS_SLOT:
        VENSTERS.pop(tid, None)
        open_ = len(VENSTERS)
    if open_ == 0:
        threading.Thread(target=_stop_na_aftellen, args=(server, WACHT_NA_SLUITEN, True),
                         daemon=True).start()
    return open_


# --- stoppen: één boekhouding (27 okt 2026) ----------------------------------------------------
# Twee routes kunnen het programma laten stoppen: Bestand > Afsluiten (`/api/afsluiten`) en het
# laatste venster dat zich afmeldt (het kruisje). Ze liepen allebei het héle ritueel af, en dan stond
# het twee keer op het scherm, met twee tellers die over elkaar heen schreven. Gemeten bij één klik op
# Afsluiten in een echte console: "AFSLUITEN" 2x en "GESTOPT" 2x, en pas ná de tweede GESTOPT sloot
# het venster. Daarom is er nu één slot: de eerste aanvraag telt en print, elke volgende zwijgt.
STOP_SLOT = threading.Lock()
STOP_BEZIG = False              # er loopt al een aftelling
STOP_KLAAR = False              # het ritueel is klaar: nooit meer opnieuw beginnen
STOP_NU = threading.Event()     # de gebruiker vroeg intussen om af te sluiten: meteen stoppen


def _stop_na_aftellen(server, seconden, kan_terug):
    """Tel af en stop de schil - één keer, hoe vaak er ook om gevraagd wordt.

    `kan_terug` hoort bij het kruisje: komt er binnen de wachttijd weer een venster (een verversing),
    dan gaat het programma door en zegt dat ook. Bij Bestand > Afsluiten heeft de gebruiker het
    gevraagd en telt hij gewoon af.

    Komt Afsluiten binnen terwijl het kruisje al aftelt, dan is dat een opdracht en geen tweede
    aftelling: `STOP_NU` laat de lopende teller meteen ophouden.
    """
    global STOP_BEZIG, STOP_KLAAR
    with STOP_SLOT:
        if STOP_KLAAR:
            return
        if STOP_BEZIG:
            if not kan_terug:
                STOP_NU.set()
            return
        STOP_BEZIG = True
    gestopt = False
    try:
        gestopt = _stop_ritueel(server, seconden, kan_terug)
    finally:
        with STOP_SLOT:
            STOP_BEZIG = False
            if gestopt:
                STOP_KLAAR = True


def _stop_ritueel(server, seconden, kan_terug):
    """Het eigenlijke stoppen. Geeft terug of de schil ook echt gestopt is.

    Sinds 28 okt 2026 (T36) printen **beide routes hetzelfde blok**: één afsluiting hoort één tekst te
    zijn, en de drie seconden zijn een **technische marge** (een verversing meldt de oude pagina af en
    de nieuwe meteen aan; zonder die marge zou elke F5 het programma stoppen). Die marge is stil.

    Sinds dezelfde dag, tweede ronde (Jans ontwerp): het sluitblok zegt **waar de horoscopen staan** —
    dat is na afloop het enige wat een gebruiker wil terugvinden, en het scheelt een herhaling in het
    startblok — en het zegt dat het venster vanzelf sluit. Die laatste regel wordt door `_tel_af()`
    elke seconde bijgewerkt zodra dit blok geprint is.
    """
    if STIL:
        einde = time.monotonic() + seconden
        while time.monotonic() < einde and not STOP_NU.wait(0.1):
            pass
        with VENSTERS_SLOT:
            if VENSTERS and kan_terug:
                return False
        server.shutdown()
        return True
    rest = float(seconden)
    while rest > 0 and not STOP_NU.is_set():
        time.sleep(min(1.0, rest))
        rest -= 1.0
        if kan_terug:
            with VENSTERS_SLOT:
                terug = bool(VENSTERS)
            if terug:
                return False
    regels = ["Je horoscopen zijn opgeslagen op je computer.",
              "",
              "Locatie:",
              paden.standaardmap()]
    telt = _kan_aftellen(64)
    if telt:
        regels += ["", _teller_regel(int(NASTAREN))]
    _kader("Astrologie Studio is afgesloten", regels, breedte=64, telt=telt)
    server.shutdown()
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = "AstrologieStudio/%s" % VERSIE

    def log_message(self, fmt, *args):
        # Geen access-log in de stille versie: daar is geen console om het in te tonen, en de
        # cursist hoort geen log te zien. Fouten gaan via `_storing` naar fouten.log.
        if STIL:
            return
        # Alleen wat misgaat komt op het scherm (25 okt 2026). Een geslaagd verzoek is geen
        # mededeling aan de gebruiker, en met een stuk of zeven regels per paginalading verdween
        # elk kader tussen de ruis. `--log` (of ASTRO_LOG=1) zet alles weer aan.
        if not ALLES_OP_HET_SCHERM:
            try:
                if int(args[1]) < 400:
                    return
            except (IndexError, ValueError):
                pass
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _stuur(self, code, body, soort="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", soort)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _storing(self, e, vraag=None, wat="het verzoek"):
        """Een onverwachte fout: gewone taal op het scherm, de details naar `fouten.log`.

        In de bundel is er geen terminal om op terug te kijken - het venster sluit en de fout is
        weg. Zonder dit bestand is een melding als "[Errno 22] Invalid argument" niet na te lopen:
        er staat niet bij welke regel het misging. De traceback gaat daarom naar de map met de
        horoscopen, met de vraag erbij, zodat de melding van een gebruiker te reproduceren is.
        """
        spoor = traceback.format_exc()
        traceback.print_exc()
        try:
            with open(paden.staat("fouten.log"), "a", encoding="utf-8") as f:
                f.write("\n=== %s  %s\n" % (datetime.datetime.now().isoformat(timespec="seconds"),
                                            self.path))
                if vraag is not None:
                    f.write("vraag: %s\n" % json.dumps(vraag, ensure_ascii=False,
                                                        default=str)[:2000])
                f.write(spoor)
        except Exception:
            pass            # een mislukt logbestand mag de melding niet verbergen
        return self._stuur(500, {
            "fout": "Er ging iets mis bij %s: %s. De technische details staan in fouten.log, "
                    "in de submap staat van je horoscopenmap." % (wat, e),
            "spoor": spoor[-800:]})

    def _van_eigen_pagina(self):
        """Alleen de eigen pagina mag de schil iets laten doen - of laten stoppen.

        Een willekeurige website kan een POST sturen zonder het antwoord te lezen, dus dit is niet
        alleen netheid: zonder deze regel kan elke pagina die openstaat het programma afsluiten.
        """
        herkomst = (self.headers.get("Origin") or "").rstrip("/")
        poort = int(getattr(self.server, "server_port", 0))
        return not herkomst or herkomst in ("http://127.0.0.1:%d" % poort,
                                            "http://localhost:%d" % poort)

    def do_GET(self):
        pad = self.path.split("?")[0]
        try:
            if pad in ("/", "/index.html"):
                with open(os.path.join(STATIC, "index.html"), encoding="utf-8") as f:
                    return self._stuur(200, f.read(), "text/html; charset=utf-8")
            if pad == "/api/technieken":
                return self._stuur(200, _register())
            if pad == "/api/leeft":
                # Waarmee het programma zich op zijn eigen poort bekendmaakt: een tweede start
                # (dubbelklik, en in de stille versie zie je daar niets van) kan zo zien dat er al
                # een schil draait en hoeft er geen tweede naast te zetten.
                return self._stuur(200, {"programma": PROGRAMMA, "versie": VERSIE,
                                         "pid": os.getpid(),
                                         "horoscopen": paden.standaardmap(),
                                         "vensters": len(VENSTERS)})
            if pad == "/api/nu":
                # Alleen de tijd van de server (27 okt 2026). De klokstand van de pagina vraagt
                # elke 20 seconden hoe laat het is en rekent de horoscoop van nu opnieuw. Dit staat
                # hier en niet bij /api/instellingen: dat antwoord vult ook het venster
                # Instellingen, en een tik van de klok hoort daarin niets te veranderen.
                return self._stuur(200, {"nu": _nu_moment()})
            if pad == "/api/kaarten":
                return self._stuur(200, opslag.lijst())
            if pad == "/api/instellingen":
                # De huidige locatie; `instellingen` is None als er nog niets is ingesteld (dan
                # vraagt de pagina erom). `nu` is het moment van de **server** - één waarheid, en
                # het blijft kloppen als de klok van een pc scheef staat. De pagina vult daarmee bij
                # het openen het formulier: naam "Nu", dat moment en de locatie, en rekent gewoon.
                # Zo is de kaart van nu geen eigen scherm of eigen endpoint maar de gewone weg.
                bestand = kern_instellingen.bestandspad()
                try:
                    inhoud = kern_instellingen.lees()
                except kern_invoer.InvoerFout as e:
                    return self._stuur(400, {"fout": " ".join(e.meldingen),
                                             "fouten": e.meldingen, "velden": e.velden,
                                             "bestand": bestand})
                return self._stuur(200, {"instellingen": inhoud, "bestand": bestand,
                                         "nu": _nu_moment()})
            if pad == "/api/plaatsen":
                vraag = urllib.parse.parse_qs(self.path.partition("?")[2])
                zoek = (vraag.get("zoek") or [""])[0]
                try:
                    limiet = int((vraag.get("limiet") or [plaatsen.LIMIET])[0])
                except ValueError:
                    limiet = plaatsen.LIMIET
                # `zones` gaat mee voor de keuzelijst van het tijdzoneveld (19 okt 2026): de
                # cursist hoeft geen IANA-naam te kennen, hij kiest er een of het script vult hem.
                return self._stuur(200, {"zoek": zoek, "plaatsen": plaatsen.zoek(zoek, limiet),
                                         "bron": plaatsen.bron(), "zones": plaatsen.zones()})
            if pad == "/favicon.ico":
                # Het pictogram van het venster (25 okt 2026). De pagina verwijst ernaar met een
                # `<link rel="icon">`, maar een browser (of een andere bezoeker van deze poort) kan om
                # /favicon.ico vragen; zonder deze route staat daar een 404 van in de console, en dat
                # was precies de eerste regel die Jan na het startblok zag.
                bestand = os.path.join(STATIC, "favicon.ico")
                if os.path.exists(bestand):
                    with open(bestand, "rb") as f:
                        return self._stuur(200, f.read(), "image/x-icon")
                return self._stuur(204, b"", "image/x-icon")
            if pad.startswith("/static/"):
                bestand = os.path.normpath(os.path.join(STATIC, pad[len("/static/"):]))
                if not bestand.startswith(STATIC) or not os.path.exists(bestand):
                    return self._stuur(404, {"fout": "niet gevonden"})
                soort = {"css": "text/css", "js": "text/javascript",
                         "html": "text/html", "svg": "image/svg+xml",
                         "ico": "image/x-icon"}.get(
                    bestand.rsplit(".", 1)[-1], "application/octet-stream")
                with open(bestand, "rb") as f:
                    # Alleen tekst krijgt een tekenset mee; bij een pictogram of lettertype hoort die
                    # er niet (25 okt 2026).
                    tekenstel = ("; charset=utf-8"
                                 if soort.startswith("text/") or soort.endswith("svg+xml") else "")
                    return self._stuur(200, f.read(), soort + tekenstel)
            return self._stuur(404, {"fout": "onbekende route", "route": pad})
        except kern_invoer.InvoerFout as e:
            # een bestand dat niet te lezen is hoort een regel in gewone taal te geven, geen 500
            return self._stuur(400, {"fout": " ".join(e.meldingen), "fouten": e.meldingen,
                                     "velden": e.velden})
        except Exception as e:
            return self._storing(e, wat="het openen van deze pagina")

    def do_DELETE(self):
        """Een eigen plaats uit `data/eigen-plaatsen.tsv` halen (19 okt 2026).

        Sleutel is naam + coordinaten: die combinatie is uniek in het bestand en overleeft het met de
        hand bewerken ervan, wat een regelnummer niet doet.
        """
        lengte = int(self.headers.get("Content-Length") or 0)
        try:
            vraag = json.loads(self.rfile.read(lengte) or b"{}")
        except Exception as e:
            return self._stuur(400, {"fout": "geen geldige JSON: %s" % e})
        try:
            if self.path == "/api/eigenplaats":
                weg = plaatsen.verwijder_eigen(vraag.get("naam"), vraag.get("lat"), vraag.get("lon"))
                if weg is None:
                    return self._stuur(404, {"fout": "Die plaats staat niet (meer) in "
                                                     + os.path.basename(plaatsen.EIGEN) + "."})
                return self._stuur(200, {"verwijderd": weg.split("\t")[0],
                                         "bestand": os.path.basename(plaatsen.EIGEN)})
            return self._stuur(404, {"fout": "onbekende route"})
        except kern_invoer.InvoerFout as e:
            return self._stuur(400, {"fout": " ".join(e.meldingen), "fouten": e.meldingen,
                                     "velden": e.velden})
        except Exception as e:
            return self._storing(e, vraag, wat="het weghalen van deze plaats")

    def do_POST(self):
        # De twee meldingen van het venster (25 okt 2026) komen vóór het JSON-lezen: `sendBeacon`
        # stuurt een lege tekst mee, geen JSON. Het lichaam wordt wel weggelezen, anders blijft het
        # in de verbinding staan en verstoort het het volgende verzoek op die verbinding.
        pad = self.path.split("?")[0]
        lengte = int(self.headers.get("Content-Length") or 0)
        if pad in ("/api/venster", "/api/afgesloten"):
            if lengte:
                self.rfile.read(lengte)
            if not self._van_eigen_pagina():
                return self._stuur(403, {"fout": "Deze oproep komt niet van de eigen pagina."})
            vraag = urllib.parse.parse_qs(self.path.partition("?")[2])
            tid = (vraag.get("id") or [""])[0][:64]
            if pad == "/api/venster":
                return self._stuur(200, {"ok": True, "open": _venster_meld(tid)})
            return self._stuur(200, {"ok": True, "open": _venster_weg(tid, self.server)})
        try:
            vraag = json.loads(self.rfile.read(lengte) or b"{}")
        except Exception as e:
            return self._stuur(400, {"fout": "geen geldige JSON: %s" % e})
        try:
            if self.path == "/api/afsluiten":
                # Afsluiten (20 okt 2026): eerst antwoorden, dan pas stoppen - anders krijgt de
                # pagina een dode verbinding in plaats van een nette melding.
                # Alleen vanaf de eigen pagina: zie `_van_eigen_pagina`.
                if not self._van_eigen_pagina():
                    return self._stuur(403, {"fout": "Deze oproep komt niet van de eigen pagina."})
                # Wachten in de console terwijl het venster zichzelf sluit: dezelfde marge als bij
                # het kruisje (één getal, één gedrag), zodat beide routes hetzelfde blok printen
                # (besluit Jan, 28 okt 2026).
                threading.Thread(target=_stop_na_aftellen,
                                 args=(self.server, WACHT_NA_SLUITEN, False), daemon=True).start()
                return self._stuur(200, {"ok": True,
                                         "melding": "Astrologie Studio is afgesloten."})
            if self.path == "/api/vensterstaat":
                # De maten van het venster (27 okt 2026): de pagina meldt ze zodat de volgende start
                # hetzelfde venster opent (volledig scherm, gemaximaliseerd, of die maat).
                if not self._van_eigen_pagina():
                    return self._stuur(403, {"fout": "Deze oproep komt niet van de eigen pagina."})
                try:
                    bewaar_vensterstaat(vraag)
                except ValueError as e:
                    return self._stuur(400, {"fout": str(e)})
                return self._stuur(200, {"ok": True})
            if self.path == "/api/rekenen":
                return self._stuur(200, _rekenen(vraag))
            if self.path == "/api/invoer":
                # Wat de kern van één veld maakt, zodat het formulier de standaardvorm kan tonen
                # zonder de lezer na te bouwen (26 okt 2026). Nooit een 400: zwijgen is het antwoord
                # op een waarde die nog niet af is.
                return self._stuur(200, _invoer(vraag))
            if self.path == "/api/bewaren":
                # `id` in de vraag is de kaart die overschreven wordt (het anker, niet de
                # bestandsnaam: die verandert als de gebruiker de kaart hernoemt). Zonder id, of
                # met een onbekend id, is het een nieuwe kaart.
                pad, nieuw, cid = opslag.bewaar(vraag["kaart"], vraag.get("map"), vervang=vraag.get("id"))
                return self._stuur(200, {"bewaard": pad, "bestand": os.path.basename(pad),
                                         "nieuw": nieuw, "id": cid})
            if self.path == "/api/instellingen":
                # de huidige locatie opslaan; het bestand staat vast (ASTRO_INSTELLINGEN of naast
                # de kaarten) - er is geen veld om ergens anders te schrijven. `nu` gaat mee zodat
                # de pagina de kaart van nu meteen opnieuw kan rekenen met de nieuwe locatie.
                antwoord = kern_instellingen.bewaar(vraag)
                antwoord["nu"] = _nu_moment()
                return self._stuur(200, antwoord)
            if self.path == "/api/osm-zoek":
                # OpenStreetMap als aanvulling op de eigen lijst (19 okt 2026), sinds 20 okt 2026 via
                # de eigen proxy op studio.astrosofica.nl: de gebruiker heeft geen e-mailadres meer
                # nodig, want de proxy vraagt met de gegevens van de beheerder. Alleen op een
                # expliciete klik van de gebruiker.
                tekst = str(vraag.get("q") or "").strip()
                return self._stuur(200, {"q": tekst, "plaatsen": osm.zoek(tekst),
                                         "bron": "OpenStreetMap, © OpenStreetMap contributors (ODbL)"})
            if self.path == "/api/eigenplaats":
                # Een plaats toevoegen aan data/eigen-plaatsen.tsv (de schrijfkant).
                plaats, bestond = plaatsen.voeg_eigen_toe(
                    naam=vraag.get("naam"), lat=vraag.get("lat"), lon=vraag.get("lon"),
                    land=vraag.get("land"), zone=vraag.get("zone"),
                    streek=vraag.get("streek"), gemeente=vraag.get("gemeente"),
                    bron=vraag.get("bron"))
                return self._stuur(200, {"plaats": plaats, "bestond": bestond,
                                         "bestand": os.path.basename(plaatsen.EIGEN)})
            if self.path == "/api/lees":
                return self._stuur(200, opslag.lees(vraag["bestand"], vraag.get("map")))
            if self.path == "/api/verwijder":
                naam = opslag.verwijder(vraag["bestand"], vraag.get("map"))
                return self._stuur(200, {"verwijderd": naam})
            return self._stuur(404, {"fout": "onbekende route"})
        except kern_invoer.InvoerFout as e:
            # invoer die niet klopt is geen storing: 400 met de regels in gewone taal
            return self._stuur(400, {"fout": " ".join(e.meldingen), "fouten": e.meldingen,
                                     "velden": e.velden})
        except Exception as e:
            return self._storing(e, vraag, wat="het verwerken van deze vraag")


# --- de zelfcontrole van de gebouwde app ------------------------------------------------------
# `--controle` is wat de bouw na het verpakken aanroept. Het controlepunt dat er echt toe doet is
# niet of een bestand in het archief zit, maar of het programma er ook bij kan: daarom rekent deze
# controle een kaart en kijkt of de standen uit Swiss Ephemeris komen en niet uit de Moshier-
# benadering. Dat is precies de stille terugval die een bundel kan veroorzaken.

NODIG_VOOR_DE_BUNDEL = (
    "efemeriden/sepl_18.se1", "efemeriden/semo_18.se1", "efemeriden/seas_18.se1",
    "data/plaatsen.json", "data/glyph-maten.json", "data/osm-dienst.json",
    "data/eigen-plaatsen.tsv",
    "schil/static/index.html", "schil/static/astro-sans.ttf",
    "schil/static/selawk.ttf", "schil/static/selawksb.ttf",
    "schil/static/favicon.ico",
    "teken/spec.json",
    "technieken/jaar1.json", "technieken/wiel.json", "technieken/radix.json",
    "technieken/aspecten.json", "technieken/heerschappen.json",
    "technieken/element-kruis.json", "technieken/afdruk.json", "technieken/opslag.json",
    "LICENSE", "README.md",
    "data/fonts/LICENTIE-AstroSans.txt", "data/fonts/LICENTIE-Selawik.txt",
    "data/fonts/bron/Source_Sans_3-OFL.txt", "data/fonts/bron/StarfisherUni-OFL.txt",
)


def _controle():
    """Zelfcontrole: (1) de bestanden, (2) of ze leesbaar zijn, (3) of de efemeriden echt gebruikt
    worden, (4) of er geschreven kan worden waar het programma schrijft. Exit 0 of 1."""
    fouten = []

    def meld(goed, regel, detail=""):
        print(("ok    " if goed else "FOUT  ") + regel + ((" - " + detail) if detail else ""))
        if not goed:
            fouten.append(regel)

    print("Astrologie Studio - zelfcontrole")
    print("vorm:       %s" % ("bundel" if paden.GEBUNDELD else "bronmap"))
    print("leesmap:    %s" % paden.bron(""))
    print("schrijfmap: %s" % paden.standaardmap())
    print("")

    ontbreekt = [n for n in NODIG_VOOR_DE_BUNDEL
                 if not (os.path.isfile(paden.bron(n)) and os.path.getsize(paden.bron(n)) > 0)]
    meld(not ontbreekt, "%d bestanden aanwezig" % len(NODIG_VOOR_DE_BUNDEL),
         ("ontbreekt of is leeg: " + ", ".join(ontbreekt)) if ontbreekt else "")

    # De efemeriden: een kaart rekenen en kijken welke efemeride er gebruikt is. Bewust een datum
    # vóór 1 januari 1970: daar ging het op Windows mis (negatieve tijdstempel -> Errno 22), en met
    # een ijkpunt uit 1985 kwam dat er niet uit.
    try:
        k = kern_kaart.maak_kaart("Controle", 1963, 7, 19, 16, 51, 26, "Europe/Amsterdam",
                                  51.675, 4.27917, plaats="Controleplaats")
        soort = k["meta"]["efemeride"]
        meld(soort == "Swiss Ephemeris", "efemeriden in gebruik", soort)
    except Exception as e:
        k, soort = None, str(e)
        meld(False, "efemeriden in gebruik", soort)

    # De standen zelf: tegen het ijkpunt dat bij deze bronversie hoort (tolerantie 0,001 graad).
    try:
        with open(paden.bron("bouw", "controle-verwacht.json"), encoding="utf-8") as f:
            verwacht = json.load(f)
        punten = {p["naam"]: p["lengte"] for p in k["punten"]} if k else {}
        gemeten = {"Zon": punten.get("Zon"), "Maan": punten.get("Maan"),
                   "Ascendant": (k["ascendant"]["lengte"] if k else None),
                   "MC": (k["mc"]["lengte"] if k else None)}
        tolerantie = float(verwacht.get("tolerantie", 0.001))
        mis = [n for n, w in verwacht["standen"].items()
               if gemeten.get(n) is None or abs(gemeten[n] - w) > tolerantie]
        meld(not mis, "standen gelijk aan het ijkpunt (%s, %g graden)" % (
            verwacht["kaart"]["datum"] + " " + verwacht["kaart"]["tijd"] + " "
            + verwacht["kaart"]["plaats"], tolerantie),
            ("wijkt af: " + ", ".join(
                "%s %s tegen %s" % (n, gemeten.get(n), verwacht["standen"][n]) for n in mis))
            if mis else "")
    except Exception as e:
        meld(False, "standen gelijk aan het ijkpunt", str(e))

    # Het wiel: tekent het, en zit het meegeleverde font er als data-URI in?
    try:
        svg, botsingen = wiel.teken(k)
        meld(len(svg) > 1000 and "data:font/ttf;base64" in svg, "wiel getekend met het eigen font",
             "%d tekens, %d botsingen" % (len(svg), len(botsingen)))
    except Exception as e:
        meld(False, "wiel getekend met het eigen font", str(e))

    # De plaatsenlijst.
    try:
        treffers = plaatsen.zoek("Dieren")
        meld(bool(treffers), "plaatsenlijst leesbaar",
             (treffers[0].get("naam", "?") if treffers else "geen treffer voor Dieren"))
    except Exception as e:
        meld(False, "plaatsenlijst leesbaar", str(e))

    # De OSM-dienst (de proxy) moet in de bundel zitten; of hij bereikbaar is, is een netwerkvraag
    # en hoort niet in deze controle.
    try:
        with open(osm.DIENST_BESTAND, encoding="utf-8") as f:
            dienst = json.load(f)["dienst"]
        meld(bool(dienst), "dienst voor OpenStreetMap ingesteld", dienst)
    except Exception as e:
        meld(False, "dienst voor OpenStreetMap ingesteld", str(e))

    # Schrijven: de horoscopen, de instellingen en de cache moeten in de schrijfmap kunnen.
    try:
        proef = paden.gebruikersmap("controle-schrijfproef.tmp")
        with open(proef, "w", encoding="utf-8") as f:
            f.write("controle")
        os.remove(proef)
        meld(True, "schrijfmap beschrijfbaar", paden.standaardmap())
    except Exception as e:
        meld(False, "schrijfmap beschrijfbaar", str(e))

    # En de staat-map apart (28 okt 2026): daar komen de vensterstand, de OSM-cache en fouten.log.
    # Zonder deze controle zou een onbeschrijfbare submap pas opvallen als een fout niet in het log
    # staat - en dan is de melding aan de gebruiker ("de details staan in fouten.log") een leugen.
    try:
        proef = paden.staat("controle-schrijfproef.tmp")
        with open(proef, "w", encoding="utf-8") as f:
            f.write("controle")
        os.remove(proef)
        meld(True, "staat-map beschrijfbaar", paden.staat())
    except Exception as e:
        meld(False, "staat-map beschrijfbaar", str(e))

    print("")
    if fouten:
        print("NIET IN ORDE: %d van de controles faalt." % len(fouten))
        raise SystemExit(1)
    print("In orde: alle controles geslaagd.")
    raise SystemExit(0)


def _maak_server():
    """De schil op de eerste vrije poort vanaf POORT (10 pogingen)."""
    laatste = None
    for poort in range(POORT, POORT + 10):
        try:
            return ThreadingHTTPServer((HOST, poort), Handler), poort
        except OSError as e:
            laatste = e
    raise SystemExit("Geen vrije poort tussen %d en %d (%s)." % (POORT, POORT + 9, laatste))


def _draait_al(poort):
    """Antwoordt op deze poort ons eigen programma? Dan is een tweede start niet nodig."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/leeft" % poort, timeout=0.7) as a:
            return json.load(a).get("programma") == PROGRAMMA
    except Exception:
        return False


def _controle_met_verslag():
    """`--controle`, met het verslag ook op schijf.

    In de versie zonder consolevenster is er niets om naar te kijken, en dan zou een mislukte
    controle onzichtbaar langskomen. `bouw-windows.bat` leest daarom `controle-uitkomst.txt` in
    plaats van het scherm.
    """
    verslag, echt = [], sys.stdout

    class _Tee:
        def write(self, s):
            verslag.append(s)
            if echt is not None:
                echt.write(s)

        def flush(self):
            if echt is not None:
                echt.flush()

    sys.stdout = _Tee()
    try:
        code = _controle()
    finally:
        sys.stdout = echt
        try:
            with open("controle-uitkomst.txt", "w", encoding="utf-8") as f:
                f.write("".join(verslag))
        except OSError:
            pass
    return code


def _meld(tekst, fout=False):
    """Iets zeggen dat de gebruiker moet zien. Zonder consolevenster gaat dat via Windows.

    `fout` kiest het pictogram: een rood kruis voor iets dat misging, een i voor iets dat gewoon zo
    is (bijvoorbeeld: het programma draait al).
    """
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, tekst, "Astrologie Studio", 0x10 if fout else 0x40)
    except Exception:
        if sys.stderr is not None:
            sys.stderr.write(tekst + "\n")


# Eén programma tegelijk (28 okt 2026). Jan installeerde een nieuwe versie terwijl het programma nog
# openstond: Inno Setup probeerde het venster te sluiten, dat lukte niet (dit is een console met een
# server erachter, geen venster dat op een sluitbericht reageert), en daarna was het programma ook niet
# meer netjes af te sluiten - hij moest de terminal doden.
#
# Daarom andersom: de app maakt bij het starten een Windows-mutex met een vaste naam, en de installer
# (AppMutex + CloseApplications=no in bouw/astrologie-studio.iss) weigert dan verder te gaan met de
# vraag het programma eerst via Bestand > Afsluiten te sluiten. De naam staat in twee bestanden en moet
# gelijk zijn; `ijking/ijk-installer.py` vergelijkt ze met elkaar.
#
# Een grens die je moet kennen: een mutex ziet dát er een proces is, niet of het nog leeft. Hangt het
# programma echt vast, dan houdt de mutex de installatie tegen en is Annuleren + Taakbeheer de uitweg.
MUTEX_NAAM = "AstrologieStudio"
_MUTEX = None


def _kernel32():
    """De Windows-API, of None elders (daar is geen mutex nodig en valt er niets stuk te gaan)."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        return ctypes.windll.kernel32
    except (AttributeError, OSError):
        return None


def maak_mutex(naam=MUTEX_NAAM):
    """De mutex aanmaken waaraan de installer ziet dat dit programma draait.

    Het handvat blijft in `_MUTEX` staan: zolang het proces leeft bestaat de mutex, en bij het
    afsluiten ruimt Windows hem zelf op - er is dus geen opruimcode en geen bestand.

    Een mislukking is voor het programma zelf geen ramp (het start gewoon), maar wel een melding: dan
    kan de installer een draaiend programma niet herkennen, en dan gebeurt precies wat er op 28 okt
    2026 misging. Daarom print een mislukking altijd en een gelukte aanmaak nooit: dat laatste is
    ontwikkelaarsinformatie (dezelfde regel als bij de vensterregel).
    """
    global _MUTEX
    if _MUTEX is not None:
        return _MUTEX
    api = _kernel32()
    if api is None:
        return None
    try:
        import ctypes
        api.CreateMutexW.restype = ctypes.c_void_p
        api.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        _MUTEX = api.CreateMutexW(None, 0, naam)
    except (AttributeError, OSError) as e:
        print("  mutex        niet aangemaakt (%s: %s) - een draaiend programma is voor de installer "
              "niet te herkennen" % (type(e).__name__, e), flush=True)
        return None
    return _MUTEX


def main():
    global STIL
    if "--controle" in sys.argv[1:]:
        return _controle_met_verslag()
    if sys.stdout is None or sys.stderr is None:
        # Zonder consolevenster (PyInstaller `console=False`) is er geen uitvoer: alles wat het
        # programma print gaat dan naar fouten.log in de staat-map, in plaats van
        # ergens te verdwijnen of op een None-object te knallen.
        STIL = True
        try:
            log = open(paden.staat("fouten.log"), "a", encoding="utf-8", buffering=1)
            sys.stdout = sys.stderr = log
        except OSError:
            class _Niets:
                def write(self, s):
                    pass

                def flush(self):
                    pass
            sys.stdout = sys.stderr = _Niets()
    # Vóór de server en het venster: zolang dit programma draait, hoort de installer te weigeren.
    maak_mutex()
    try:
        _start()
    except SystemExit:
        raise
    except Exception as e:
        traceback.print_exc()
        _meld("Astrologie Studio kon niet starten:\n\n%s" % e, fout=True)
        return 1
    return 0


# Het venster van de bundel (21 okt 2026). `webbrowser.open` geeft een gewoon tabblad, en dat kost
# op een laptop met 768 px ongeveer 110 px aan tabbladen, adresbalk en bookmarkbalk - dan valt de
# onderkant van het formulier onder de statusbalk. Chromium-browsers hebben een app-modus
# (`--app=`) zonder die drie balken; Edge staat op elke Windows-pc en wordt daarom als eerste
# geprobeerd. Firefox kent geen app-modus, dus daar blijft het een gewoon tabblad.
APP_VENSTER = (1440, 900)


def _browser_kandidaten():
    """De browsers waarin `--app=` werkt, in de orde waarin we ze proberen.

    `ASTRO_BROWSER` wijst er één aan (handig bij een ongewone installatie, en om dit op de server
    te kunnen proeven).
    """
    if os.environ.get("ASTRO_BROWSER"):
        return [os.environ["ASTRO_BROWSER"]]
    paden_ = []
    if os.name == "nt":
        for map_ in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                     os.environ.get("LOCALAPPDATA")):
            if not map_:
                continue
            paden_ += [os.path.join(map_, r"Microsoft\Edge\Application\msedge.exe"),
                       os.path.join(map_, r"Google\Chrome\Application\chrome.exe"),
                       os.path.join(map_, r"BraveSoftware\Brave-Browser\Application\brave.exe"),
                       os.path.join(map_, r"Chromium\Application\chrome.exe")]
    else:
        for naam in ("microsoft-edge", "google-chrome", "google-chrome-stable",
                     "chromium", "brave-browser"):
            paden_.append(shutil.which(naam))
    return [p for p in paden_ if p and os.path.isfile(p)]


# Het venster onthouden (27 okt 2026). Jan werkt op een groot scherm in volledig scherm met
# weergave 150%; bij elke start kwam het venster terug op 1440x900, dus moest hij dat elke keer
# opnieuw instellen. De pagina meldt de **maten** van het venster (buitenmaat, schermmaat,
# beschikbare schermmaat) en de schil kiest daar bij de volgende start de vlag uit. De drempels staan
# hier en niet in de pagina: één plek, en de getallen zijn feiten van zijn machine.
#
# Bewust een eigen bestand (`venster.json`) en niet een sleutel in `settings.json`: dat bestand heeft
# een contract met een versienummer en een keuring per veld, en een venstermaat hoort daar niet in.
VENSTERSTAAT = "venster.json"


def _vensterstaat_pad() -> str:
    return paden.staat(VENSTERSTAAT)


def lees_vensterstaat():
    """De laatst gemelde venstermaten, of None als er nog niets gemeld is."""
    try:
        with open(_vensterstaat_pad(), encoding="utf-8") as f:
            staat = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(staat, dict):
        return None
    return staat


# Hoe dicht twee maten bij elkaar moeten liggen om "hetzelfde" te zijn. Voor de buitenmaat is dat
# exact (een venster dat het scherm vult is even groot), voor het beeldvlak een paar pixels: de rand
# en een schuifbalk kunnen schelen. Een gemaximaliseerd venster zit tientallen pixels onder de
# schermhoogte, dus die marge maakt de twee standen niet aan elkaar gelijk.
MARGE_BUITEN = 2
MARGE_BINNEN = 8


def _bijna(a, b, marge=MARGE_BUITEN) -> bool:
    return (a is not None and b is not None
            and abs(a[0] - b[0]) <= marge and abs(a[1] - b[1]) <= marge)


def _maat(waarde):
    """Een bruikbare maat als (breedte, hoogte), of None. Geen `True`/`False`: dat zijn ints."""
    if (isinstance(waarde, list) and len(waarde) == 2
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) and 200 <= x <= 20000
                    for x in waarde)):
        return (int(waarde[0]), int(waarde[1]))
    return None


def bewaar_vensterstaat(staat) -> None:
    """Schrijf de maten weg; onzin wordt geweigerd in plaats van opgeslagen."""
    if not isinstance(staat, dict):
        raise ValueError("geen vensterstaat")
    buiten = _maat(staat.get("buiten"))
    if buiten is None:
        raise ValueError("geen bruikbare venstermaat")
    schoon = {"buiten": list(buiten)}
    for sleutel in ("binnen", "scherm", "beschikbaar"):
        maat = _maat(staat.get(sleutel))
        if maat is not None:
            schoon[sleutel] = list(maat)
    # Waar het venster staat. Niet gebruikt om iets te beslissen (de schil zet geen positie), maar het
    # maakt het bestand leesbaar als een stand niet klopt: volledig scherm begint linksboven.
    links = staat.get("links")
    if isinstance(links, list) and len(links) == 2 and all(isinstance(x, (int, float)) for x in links):
        schoon["links"] = [int(links[0]), int(links[1])]
    # De maat waar "kleiner" naar terugvalt. De pagina meldt hem alleen als het venster niet
    # schermvullend is; anders blijft de vorige bewaarde maat staan, want een melding vanuit volledig
    # scherm zou hem anders met de schermmaat overschrijven.
    rust = _maat(staat.get("rust"))
    if rust is None:
        rust = _maat((lees_vensterstaat() or {}).get("rust"))
    if rust is not None:
        schoon["rust"] = list(rust)
    with open(_vensterstaat_pad(), "w", encoding="utf-8") as f:
        json.dump(schoon, f)


def venster_stand():
    """De stand waarin het venster moet openen, met de maat waar "kleiner" naar terugvalt.

    Geeft `(stand, rust, positie)`: `stand` is "volledig", "gemaximaliseerd" of "gewoon", `rust` een
    (breedte, hoogte) en `positie` een (links, boven) of None. Zonder staat: de vaste maat.

    Volledig scherm als de buitenmaat de **hele** schermmaat vult, gemaximaliseerd als hij de
    beschikbare maat vult (scherm min taakbalk), anders gewoon die maat. Twee signalen voor "vult het
    scherm": de buitenmaat (Linux, gewone browservensters) of het beeldvlak (Windows app-modus, waar
    de buitenmaat blijft staan - gemeten bij Jan: buiten 1444x900 bij een scherm van 2134x1200, met
    een beeldvlak van 2134x1200).
    """
    staat = lees_vensterstaat() or {}
    buiten = _maat(staat.get("buiten"))
    if buiten is None:
        return venster.STAND_GEWOON, APP_VENSTER, None
    rust = _maat(staat.get("rust")) or buiten
    positie = None
    links = staat.get("links")
    if isinstance(links, list) and len(links) == 2:
        try:
            positie = (int(links[0]), int(links[1]))
        except (TypeError, ValueError):
            positie = None
    binnen = _maat(staat.get("binnen"))
    scherm = _maat(staat.get("scherm"))
    beschikbaar = _maat(staat.get("beschikbaar"))
    # Wat er teruggaat wordt naar het werkblad geklemd (28 okt 2026). Op een scherm met 150 % weergave
    # is het werkblad kleiner dan de bewaarde maat, en dan viel de onderkant van het venster - met de
    # groene statusbalk - achter de taakbalk. De toetsen hieronder gebruiken de **gemelde** maten: een
    # geklemde buitenmaat zou "vult het scherm" kunnen breken, en dan opent een schermvullend venster
    # als gewoon venster.
    rust = venster.klem_maat(rust, beschikbaar)
    buiten_geklemd = venster.klem_maat(buiten, beschikbaar)
    if _bijna(buiten, scherm) or _bijna(binnen, scherm, MARGE_BINNEN):
        return venster.STAND_VOLLEDIG, rust, positie
    if (beschikbaar and (buiten[1] >= beschikbaar[1] - MARGE_BUITEN
                         or (binnen is not None and binnen[1] >= beschikbaar[1] - MARGE_BINNEN))):
        return venster.STAND_GEMAXIMALISEERD, rust, positie
    return venster.STAND_GEWOON, buiten_geklemd, positie


def venster_vlaggen():
    """De vlaggen waarmee het venster opent: alleen de **beginmaat**.

    Sinds 27 okt 2026 zet de schil de stand zelf, met de Windows-API (`schil/venster.py`). Deze
    vlaggen zorgen alleen dat het venster meteen op de goede maat en plaats verschijnt, in plaats van
    eerst op Chromium's standaardmaat (gemeten: 945x1012 op een scherm van 1920x1080) en dan te
    verspringen. Waarom de stand niet meer via de vlaggen gaat, is alle drie gemeten op Windows 11
    met Edge 156:

      * `--start-maximized` maximaliseert wel, maar zet als **herstelmaat** Chromium's eigen standaard
        (945x1012) - dat is het halve scherm bij "kleiner";
      * `--window-size` wint van `--start-maximized`, dus die twee samen openen gewoon op die maat;
      * een browser die al draait negeert alle venstervlaggen van een tweede `--app=`-start.

    `--start-fullscreen` staat er sinds de nameting van 27 okt 2026 ook niet meer bij. Die vlag werkt
    wel bij een verse start, maar zet de herstelmaat op de **schermmaat**: na F11 kwam het venster dan
    op 1920x1080 in plaats van op de rustmaat. Zet de schil eerst de maat en daarna F11, dan landt
    "uit volledig scherm" wél op de rustmaat (gemeten: 900x700). Het venster is dan een tel eerder in
    beeld op de rustmaat - dat is de prijs, en die is kleiner dan een verkeerde herstelmaat.
    """
    _, rust, positie = venster_stand()
    # De beginmaat in de eenheid die de browser leest. Chromium leest `--window-size` in beeldpunten
    # (gemeten bij Jan: 1440 gevraagd gaf een venster van 1200 CSS-pixels), en dan opent het venster te
    # klein, meet de pagina die maat en bewaart hem als rustmaat - de krimp van 27 okt 2026.
    schaal = venster.beginschaal(venster_schermmaat())
    vlaggen = ["--window-size=%d,%d" % (round(rust[0] * schaal), round(rust[1] * schaal))]
    if positie:
        vlaggen.append("--window-position=%d,%d" % (round(positie[0] * schaal),
                                                     round(positie[1] * schaal)))
    return vlaggen


def venster_tekst():
    """De openingsstand in gewone taal, voor het startblok (27 okt 2026).

    Afgeleid uit de stand, zodat er maar één plek is die hem bepaalt. Nuttig bij het uitzoeken van een
    verkeerde stand: Jan leest dit in zijn console en hoeft geen bestand te openen.
    """
    stand, rust, _ = venster_stand()
    if stand == venster.STAND_VOLLEDIG:
        return "volledig scherm (herstelmaat %d x %d)" % rust
    if stand == venster.STAND_GEMAXIMALISEERD:
        return "gemaximaliseerd (herstelmaat %d x %d)" % rust
    return "%d x %d" % rust


def bewaar_rust(maat) -> None:
    """De rustmaat vastleggen die de schil zojuist heeft gezet.

    De pagina kan dat niet altijd: is het venster eenmaal schermvullend, dan meet ze de schermmaat en
    niet de maat waar "kleiner" naartoe gaat (bij Jan meldt Edge in app-modus gewoon het werkblad).
    Zonder deze regel blijft de meting van vlak na het opstarten staan - en dat is de maat waarop de
    browser opende, niet de maat van het programma. Dat is precies de krimp die hij zag.
    """
    staat = lees_vensterstaat()
    if not staat:
        return
    staat["rust"] = [int(maat[0]), int(maat[1])]
    try:
        bewaar_vensterstaat(staat)
    except ValueError:
        pass


def venster_schermmaat():
    """De schermmaat die de pagina meldt, in CSS-pixels (of None).

    Nodig om de schaal te bepalen: de venster-API rekent bij weergave boven 100 % in beeldpunten, en
    het verschil tussen de monitor die de API ziet en deze maat is precies die schaal (zie
    `schil/venster.py`).
    """
    return _maat((lees_vensterstaat() or {}).get("scherm"))


def _pas_venster_toe(stand, rust, positie, kenmerk):
    """De stand toepassen zodra het venster er is (draait op de achtergrond).

    Nooit laten stuklopen op iets wat de Windows-API teruggeeft: het programma moet ook starten als
    het venster niet gevonden wordt of de aanroep faalt. Dan staat er één regel in de console en
    verder verandert er niets.
    """
    gelukt = False
    try:
        regel, gelukt = venster.pas_toe(stand, rust, positie, kenmerk,
                                        scherm=venster_schermmaat())
    except Exception as e:                                          # noqa: BLE001
        regel = "de stand is niet toegepast (%s: %s)" % (type(e).__name__, e)
    if gelukt:
        # De schil heeft de maat net gezet en nagemeten: dat is de rustmaat, wat de pagina ook meldt.
        bewaar_rust(rust)
    if regel and not STIL and (not gelukt or ALLES_OP_HET_SCHERM):
        # Alleen een **mislukking** is een mededeling aan de gebruiker (punt 3 vóór 0.5.0, 28 okt 2026):
        # die verklaart een venster dat niet doet wat hij verwacht. Een gelukte stand is
        # ontwikkelaarsinformatie en hoort achter `--log`/ASTRO_LOG, net als de access-log. Zonder die
        # vlag blijft het scherm dus leeg zolang het venster doet wat het moet doen.
        print("  venster      %s" % regel, flush=True)


def _open_venster(adres):
    """Het venster openen: eerst een browser met app-modus, anders een gewoon tabblad.

    Geeft terug of er iets geopend is; de tweede start gebruikt dat om te weten of er nog iets te
    melden valt.
    """
    stand, rust, positie = venster_stand()
    # Een kenmerk in het adres, dat de pagina in de venstertitel zet. Daarmee vindt de schil het
    # juiste venster terug, ook als er twee openstaan of de browser al draaide.
    kenmerk = venster.token()
    adres = "%s?%s=%s" % (adres, venster.TOKEN_SLEUTEL, kenmerk)
    for exe in _browser_kandidaten():
        try:
            subprocess.Popen([exe, "--app=%s" % adres] + venster_vlaggen(), close_fds=True)
        except OSError:
            continue
        threading.Thread(target=_pas_venster_toe,
                         args=(stand, rust, positie, kenmerk), daemon=True).start()
        return True
    return webbrowser.open(adres)


def _start():
    # Een tweede start naast een draaiende schil: geen tweede server. Het venster wordt wel weer
    # geopend (21 okt 2026 — gewijzigd besluit). De oude regel was: alleen zeggen dat het programma
    # al draait, want een browser haalt een bestaand tabblad niet naar voren en een tweede tabblad
    # zet een leeg formulier naast het zijne. Sinds het venster in app-modus opent is er geen
    # tabblad meer om naar terug te gaan: wie het venster dichtklikt, heeft zonder deze regel geen
    # weg terug, en in de stille bundel is er ook geen console meer om iets uit te leggen. Twee
    # vensters op één schil is ongevaarlijk: er blijft één server, en die is de enige die schrijft.
    # Is de vaste poort door iets anders bezet, dan zoekt `_maak_server` gewoon een vrije, zoals
    # voorheen.
    expliciet = len(sys.argv) > 1 and sys.argv[1].isdigit()
    if not expliciet and _draait_al(POORT):
        bestaand = "http://%s:%d/" % (HOST, POORT)
        if paden.GEBUNDELD and "--geen-browser" not in sys.argv[1:] and _open_venster(bestaand):
            return
        melding = ("Astrologie Studio draait al.\n\nHet venster kon niet geopend worden; ga naar\n"
                   + bestaand)
        if STIL:
            _meld(melding)
        else:
            _kader("Let op - het programma draait al",
                   ["Het venster kon niet geopend worden.",
                    "Ga met je browser naar " + bestaand])
        return
    server, poort = _maak_server()
    adres = "http://%s:%d/" % (HOST, poort)
    if STIL:
        # Geen console (en dus geen kader): één regel naar fouten.log, meer heeft niemand nodig.
        print("Astrologie Studio %s gestart op %s (horoscopen: %s)"
              % (VERSIE, adres, paden.standaardmap()))
    else:
        _kader("Astrologie Studio - cursusjaar 1 - versie %s" % VERSIE,
               ["Dit venster hoort bij Astrologie Studio. Je hoeft hier niets",
                "te doen. Laat het openstaan zolang je met het programma werkt.",
                "",
                "Sluiten kan met het kruisje van dit venster of via",
                "Bestand > Afsluiten in het programma. Beide manieren werken."],
               breedte=64)
        # Ontwikkelaarsinformatie staat buiten het kader en in kleine letters: bruikbaar voor wie
        # meekijkt, onopvallend voor wie het programma alleen gebruikt. Waar de horoscopen staan is
        # hier sinds 28 okt 2026 weg (Jans punt: dat is na afloop nuttiger, en zo staat het er één keer).
        print("  adres        %s" % adres, flush=True)
        print("  programma    %s" % paden.bron(""), flush=True)
        # De venstermaat is een meetwaarde voor onszelf en staat niet meer op het scherm (zelfde
        # besluit): de schil onthoudt hem in `venster.json`, daar is hij te controleren.
        _venstertitel("Astrologie Studio %s - cursusjaar 1" % VERSIE)
    # In een bundel opent de schil zelf de browser; in ontwikkeling niet, want daar kijk je vanaf
    # een andere machine. `--geen-browser` houdt dat tegen.
    if paden.GEBUNDELD and "--geen-browser" not in sys.argv[1:]:
        threading.Timer(0.8, _open_venster, args=(adres,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        # Ctrl+C is in een consolevenster een gewone manier om te stoppen; dan hoort er ook een
        # afsluitblok te staan in plaats van een kale prompt.
        if not STIL:
            _kader("Astrologie Studio is afgesloten",
                   ["Je hebt het programma met Ctrl+C gestopt.",
                    "",
                    "Locatie:",
                    paden.standaardmap()], breedte=64)
    finally:
        server.server_close()
    # Het venster sluit zichzelf, maar niet zo snel dat de laatste mededeling weg is voor je hem leest
    # (25 okt 2026). Geen toets: een afsluiting hoort geen taak te zijn, en een wachtend programma kan
    # blijven hangen als er niets op de invoer komt. Alleen in een echt consolevenster, dus niet in een
    # pijp, een logbestand of de stille bundel.
    #
    # Sinds 28 okt 2026 **telt deze staart hardop af**, in de onderste regel van het blok dat net
    # geprint is: "Dit venster sluit vanzelf over 4 ... 0 seconden", en bij nul gaat het venster dicht.
    # Dat is Jans ontwerp: de wachttijd is er toch, en zo is te zien dat het programma bezig is met
    # stoppen in plaats van te hangen. Na een Ctrl+C telt er niets (dat blok heeft geen aftelregel) en
    # wordt er alleen gewacht.
    if not STIL and _is_console():
        try:
            _tel_af(NASTAREN)
        except (KeyboardInterrupt, OSError):
            pass
    if STIL:
        print("Afgesloten.")


if __name__ == "__main__":
    main()
