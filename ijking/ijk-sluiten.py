#!/usr/bin/env python3
"""IJking van het samen sluiten van venster en schil (25 okt 2026).

Twee richtingen, één boekhouding: het kruisje laat de schil stoppen, en Bestand > Afsluiten laat het
venster stoppen. Wat de pagina daarvoor doet is klein - zich melden bij het laden
(`POST /api/venster?id=…`), zich afmelden bij `pagehide` met een beacon (`POST /api/afgesloten?id=…`),
en na het afsluiten `window.close()` aanroepen. Wat hier nagemeten wordt is de **schil-kant**: telt
hij de vensters goed, stopt hij pas bij de laatste, en legt een verversing hem niet om?

Wat dit script **niet** kan: bewijzen dat `window.close()` in Edge op Windows een app-venster sluit en
dat de beacon daar aankomt. Dat is op Linux in Chromium gemeten (Xvfb + openbox, venster gesloten via
WM_DELETE): `beforeunload` én `pagehide` komen aan, de beacon arriveert en het proces stopt zelf. Edge
is dezelfde code; de echte proef is de knop en het kruisje bij Jan.

Draaien:  /usr/bin/python3 ijking/ijk-sluiten.py
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

HIER = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HIER)
SERVER = os.path.join(PROJECT, "schil", "server.py")

goed, fout = [], []


def meld(ok, wat, detail=""):
    (goed if ok else fout).append((wat, detail))
    print("%-6s %s%s" % ("GOED" if ok else "FOUT", wat, ("  " + detail) if detail else ""))


def vrije_poort():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    poort = s.getsockname()[1]
    s.close()
    return poort


def post(poort, pad, body=b""):
    verzoek = urllib.request.Request("http://127.0.0.1:%d%s" % (poort, pad), data=body,
                                     method="POST",
                                     headers={"Origin": "http://127.0.0.1:%d" % poort})
    with urllib.request.urlopen(verzoek, timeout=5) as antwoord:
        return antwoord.status, antwoord.read()


def leeft(poort):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/leeft" % poort, timeout=2):
            return True
    except Exception:
        return False


def start(poort):
    proc = subprocess.Popen([sys.executable, SERVER, str(poort)],
                            env=dict(os.environ, ASTRO_HOST="127.0.0.1"),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for _ in range(80):
        if leeft(poort):
            return proc
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    return proc


def wacht_tot_weg(proc, hooguit=6.0):
    """Wacht tot het serverproces zelf gestopt is; geeft de gemeten tijd terug (of None)."""
    begin = time.monotonic()
    while time.monotonic() - begin < hooguit:
        if proc.poll() is not None:
            return time.monotonic() - begin
        time.sleep(0.05)
    return None


def slotblok(uit):
    """Het slotblok van een afsluiting, zonder het startblok en de poort eromheen.

    Waarom dit bestaat: sinds 28 okt 2026 moeten het kruisje en Bestand > Afsluiten **letterlijk
    dezelfde tekst** op het scherm zetten. Vergelijken op één woord zou een verschil in de regels
    eronder niet zien. Sinds de tweede ronde van die dag heet het blok "Astrologie Studio is
    afgesloten" (kleine letter), dus er wordt niet meer op een hoofdletter gezocht.
    """
    regels = uit.replace("\r", "").splitlines()
    for i, r in enumerate(regels):
        if "afgesloten" in r.lower():
            begin = i - 1 if i > 0 else i
            return "\n".join(x.rstrip() for x in regels[begin:]).strip()
    return ""


def main():
    # 1. melden telt: twee vensters, en de schil blijft draaien als er één weg is.
    poort = vrije_poort()
    proc = start(poort)
    if proc.poll() is not None or not leeft(poort):
        meld(False, "de schil start", "poort %d" % poort)
        return 1
    meld(True, "de schil start", "poort %d" % poort)

    _, a = post(poort, "/api/venster?id=venster-A")
    _, b = post(poort, "/api/venster?id=venster-B")
    meld(b'"open": 2' in b, "twee vensters geteld", b.decode().strip())

    post(poort, "/api/afgesloten?id=venster-A", b"")
    time.sleep(4.2)                  # langer dan de wachttijd van 3 s
    meld(leeft(poort), "één venster weg: de schil blijft draaien")

    # 2. het laatste venster weg: de schil stopt zelf, na de wachttijd.
    post(poort, "/api/afgesloten?id=venster-B", b"")
    duur = wacht_tot_weg(proc)
    meld(duur is not None, "laatste venster weg: de schil stopt",
         ("na %.1f s" % duur) if duur is not None else "niet gestopt")
    meld(duur is not None and 2.5 <= duur <= 4.5, "stopt binnen de wachttijd (2,5-4,5 s)",
         ("%.1f s" % duur) if duur is not None else "")
    if proc.poll() is None:
        proc.kill()
    uit, _ = proc.communicate(timeout=10)
    meld("Astrologie Studio" in uit and "cursusjaar 1" in uit,
         "startblok staat in een kader op het scherm")
    # Sinds 28 okt 2026 telt er niets hardop af in een **pijp**: het aftellen hoort bij een echt
    # consolevenster, en daar is er geen. De aftelregel komt er dus ook niet in te staan (een belofte
    # die niet gebeurt is erger dan geen belofte). Beide routes printen hetzelfde slotblok.
    meld("AFSLUITEN" not in uit and "Dit venster sluit vanzelf" not in uit,
         "kruisje: geen aankondiging, en zonder console ook geen aftelregel",
         "gevonden: " + (uit.count("AFSLUITEN") * "AFSLUITEN "))
    meld("afgesloten" in uit.lower() and "Locatie:" in uit and "astrologie-horoscopen" in uit,
         "slotblok noemt waar de horoscopen staan")

    # 3. een verversing legt de schil niet om: afmelden en meteen weer aanmelden.
    poort = vrije_poort()
    proc = start(poort)
    post(poort, "/api/venster?id=venster-C")
    post(poort, "/api/afgesloten?id=venster-C", b"")     # pagehide van de oude pagina
    time.sleep(0.4)
    post(poort, "/api/venster?id=venster-C2")            # de nieuwe pagina meldt zich
    time.sleep(4.2)
    meld(leeft(poort), "een verversing (F5) stopt de schil niet")
    post(poort, "/api/afgesloten?id=venster-C2", b"")
    meld(wacht_tot_weg(proc) is not None, "daarna stopt hij wel netjes")
    if proc.poll() is None:
        proc.kill()
    uit3, _ = proc.communicate(timeout=10)
    # De verversing mag helemaal niets zeggen; het enige blok in deze uitvoer is van de échte stop
    # daarna. Vóór 28 okt 2026 stond hier "TOCH NIET GESTOPT" midden in het scherm.
    meld(uit3.lower().count("afgesloten") == 1 and "TOCH NIET GESTOPT" not in uit3,
         "een verversing houdt hem stil tegen (alleen het blok van de echte stop)",
         "afgesloten %dx" % uit3.lower().count("afgesloten"))

    # 4. een oproep van een andere site mag dit niet kunnen.
    poort = vrije_poort()
    proc = start(poort)
    post(poort, "/api/venster?id=venster-D")
    try:
        verzoek = urllib.request.Request("http://127.0.0.1:%d/api/afgesloten?id=venster-D" % poort,
                                         data=b"", method="POST",
                                         headers={"Origin": "https://kwaad.example"})
        code = urllib.request.urlopen(verzoek, timeout=5).status
    except urllib.error.HTTPError as e:
        code = e.code
    meld(code == 403, "een andere site kan het venster niet afmelden", "status %s" % code)
    meld(leeft(poort), "en de schil draait nog")
    proc.kill()

    # 5. Bestand > Afsluiten, met de beacon die er altijd op volgt. Twee routes, één boekhouding:
    #    één keer "GESTOPT" en geen aankondiging met een teller. Vóór 27 okt 2026 stond het hele
    #    ritueel hier twee keer (AFSLUITEN 2x, GESTOPT 2x) en sloot het venster pas na de tweede.
    poort = vrije_poort()
    proc = start(poort)
    post(poort, "/api/venster?id=venster-E")
    post(poort, "/api/afsluiten", b"{}")
    post(poort, "/api/afgesloten?id=venster-E", b"")     # pagehide van het venster dat zich sluit
    duur = wacht_tot_weg(proc)
    meld(duur is not None, "Afsluiten: de schil stopt",
         ("na %.1f s" % duur) if duur is not None else "niet gestopt")
    if proc.poll() is None:
        proc.kill()
    uit5, _ = proc.communicate(timeout=10)
    meld(uit5.lower().count("afgesloten") == 1, "Afsluiten: het slotblok staat er één keer",
         "geteld: %d" % uit5.lower().count("afgesloten"))
    meld("AFSLUITEN" not in uit5, "Afsluiten: geen aankondiging in kapitalen",
         "geteld: %d" % uit5.count("AFSLUITEN"))
    meld(slotblok(uit) != "" and slotblok(uit) == slotblok(uit5),
         "kruisje en Afsluiten printen hetzelfde slotblok",
         ("verschil: %r tegen %r" % (slotblok(uit), slotblok(uit5)))
         if slotblok(uit) != slotblok(uit5) else "")

    print("\n%d van %d goed" % (len(goed), len(goed) + len(fout)))
    return 0 if not fout else 1


if __name__ == "__main__":
    sys.exit(main())
