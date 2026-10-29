#!/usr/bin/env python3
"""IJking van de console (25 okt 2026): titel, kaders, geen ruis, en de wachtregel aan het eind.

Wat hier nagemeten wordt, is wat Jan op zijn scherm ziet en waar hij drie dingen over zei: het
afsluiten ging te snel (de laatste mededeling was weg voor je hem las), de access-log stond nog in de
terminal, en de venstertitel mocht van hem. Alle drie zijn hier een proef.

Waarom een pty: alleen in een **echt** consolevenster horen de titel en de teller te verschijnen.
Zonder console (pijp, logbestand, bouwscript) mag er niets wachten - anders hangt elke bouw. Dat is de
tweede helft van deze proef.

Draaien:  /usr/bin/python3 ijking/ijk-console.py     (Linux/macOS: `pty` bestaat niet op Windows)
"""

from __future__ import annotations

import os
import pty
import re
import select
import socket
import subprocess
import sys
import time
import urllib.request

HIER = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HIER)
SERVER = os.path.join(PROJECT, "schil", "server.py")

goed, fout = [], []


def meld(ok, wat, detail=""):
    (goed if ok else fout).append(wat)
    print("%-6s %s%s" % ("GOED" if ok else "FOUT", wat, ("  " + detail) if detail else ""))


def vrije_poort():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    poort = s.getsockname()[1]
    s.close()
    return poort


def post(poort, pad):
    verzoek = urllib.request.Request("http://127.0.0.1:%d%s" % (poort, pad), data=b"", method="POST",
                                     headers={"Origin": "http://127.0.0.1:%d" % poort})
    return urllib.request.urlopen(verzoek, timeout=5).status


def wacht_op_schil(poort, seconden=8.0):
    eind = time.monotonic() + seconden
    while time.monotonic() < eind:
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/api/leeft" % poort, timeout=1).read()
            return True
        except Exception:
            time.sleep(0.1)
    return False


def lees(fd, seconden, tot=None):
    """Lees wat er in die tijd uit de pty komt; stop eerder als `tot` erin zit."""
    uit = b""
    eind = time.monotonic() + seconden
    while time.monotonic() < eind:
        r, _, _ = select.select([fd], [], [], 0.2)
        if not r:
            continue
        try:
            brok = os.read(fd, 65536)
        except OSError:
            break
        if not brok:
            break
        uit += brok
        if tot and tot.encode() in uit:
            break
    return uit.decode("utf-8", "replace")


def met_console():
    poort = vrije_poort()
    meester, slaaf = pty.openpty()
    proc = subprocess.Popen([sys.executable, SERVER, str(poort)],
                            env=dict(os.environ, ASTRO_HOST="127.0.0.1"),
                            stdin=slaaf, stdout=slaaf, stderr=slaaf, close_fds=True)
    os.close(slaaf)
    begin = lees(meester, 6.0, tot="\x07")
    meld(re.search(r"\]0;Astrologie Studio [\d.]+ - cursusjaar 1", begin) is not None,
         "de venstertitel noemt het programma en de versie")
    meld("Astrologie Studio" in begin and "cursusjaar 1" in begin,
         "het startblok staat in een kader")
    # Sinds 28 okt 2026 staan onder het kader alleen nog `adres` en `programma`; de venstermaat was
    # een meetwaarde voor onszelf en de horoscoopmap staat nu in het sluitblok (Jans besluit).
    los = [r.rstrip() for r in begin.replace("\r", "").splitlines() if r.startswith("  ")]
    meld(len(los) == 2 and los[0].startswith("  adres") and los[1].startswith("  programma"),
         "onder het kader staan alleen adres en programma", "regels: %r" % los)
    meld("venster      " not in begin, "de venstermaat staat niet meer op het scherm")
    meld(wacht_op_schil(poort), "de schil draait")
    meld("GET /api/leeft" not in lees(meester, 1.0),
         "een geslaagd verzoek komt niet op het scherm")
    # Het pictogram: zonder route vroeg de browser om /favicon.ico en stond daar een 404 van in de
    # console - de eerste regel die Jan na het startblok zag (25 okt 2026).
    with urllib.request.urlopen("http://127.0.0.1:%d/favicon.ico" % poort, timeout=5) as a:
        meld(a.status == 200 and a.headers.get("Content-Type", "").startswith("image/"),
             "het vensterpictogram wordt geleverd", a.headers.get("Content-Type", ""))
    with urllib.request.urlopen("http://127.0.0.1:%d/" % poort, timeout=5) as a:
        pagina = a.read().decode()
    meld('rel="icon" href="/static/favicon.ico"' in pagina,
         "en de pagina verwijst ernaar, dus de browser vraagt /favicon.ico niet eens")
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/bestaatniet" % poort, timeout=3)
    except Exception:
        pass
    meld("404" in lees(meester, 1.5), "wat misgaat komt er wel (404)")
    post(poort, "/api/venster?id=A")
    begin = time.monotonic()
    post(poort, "/api/afgesloten?id=A")
    staart = lees(meester, 18.0, tot="over 0 seconden")
    meld("Astrologie Studio is afgesloten" in staart, "het slotkader staat er")
    meld("Je horoscopen zijn opgeslagen op je computer." in staart and "Locatie:" in staart,
         "het slotkader zegt waar de horoscopen staan")
    # Sinds de tweede ronde van 28 okt 2026 telt de **onderste regel van het kader** hardop af: 5, 4,
    # 3, 2, 1, 0 seconde(n), en bij nul sluit het venster. Vóór die ronde stond hier de omgekeerde eis
    # ("geen teller"), want toen telde de staart na het ritueel een tweede keer.
    tellers = re.findall(r"over (\d+) seconde", staart)
    meld(tellers == ["5", "4", "3", "2", "1", "0"],
         "de aftelregel telt van 5 naar 0", "gezien: %s" % ", ".join(tellers))
    meld("\x1b[2A" in staart, "en hij wordt bijgewerkt in plaats van bijgedrukt (cursor twee regels omhoog)")
    meld("AFSLUITEN" not in staart, "zonder aankondiging in kapitalen",
         "geteld: %d" % staart.count("AFSLUITEN"))
    meld("Druk op Enter" not in staart, "en er wordt niets van de gebruiker gevraagd")
    meld(proc.poll() is None, "het programma staat nog even stil bij de laatste mededeling")
    eind = time.monotonic() + 15
    while time.monotonic() < eind and proc.poll() is None:
        time.sleep(0.1)
    duur = time.monotonic() - begin
    lees(meester, 0.5)
    meld(proc.poll() is not None, "daarna sluit het venster vanzelf, zonder toets",
         "na %.1f s" % duur)
    meld(6.5 <= duur <= 10.0, "en wel na de marge plus de vijf tellen (6,5-10 s)", "%.1f s" % duur)
    if proc.poll() is None:
        proc.kill()
    os.close(meester)


def zonder_console():
    poort = vrije_poort()
    proc = subprocess.Popen([sys.executable, SERVER, str(poort)],
                            env=dict(os.environ, ASTRO_HOST="127.0.0.1"),
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    if not wacht_op_schil(poort):
        meld(False, "de schil start ook zonder console")
        proc.kill()
        return
    post(poort, "/api/venster?id=B")
    post(poort, "/api/afgesloten?id=B")
    eind = time.monotonic() + 10
    while time.monotonic() < eind and proc.poll() is None:
        time.sleep(0.1)
    meld(proc.poll() is not None, "zonder console stopt hij vanzelf (geen teller)")
    uit = ""
    if proc.poll() is not None:
        uit, _ = proc.communicate(timeout=10)
    else:
        proc.kill()
    meld("Dit venster sluit vanzelf" not in uit,
         "en er staat geen aftelregel in de uitvoer (zonder console telt hij niet)")
    meld("Astrologie Studio" in uit and "Astrologie Studio is afgesloten" in uit,
         "de kaders komen ook door een pijp heen (flush)")


def main():
    if os.name == "nt":
        print("Deze proef vraagt een pty en draait daarom niet op Windows.")
        return 0
    print("=== met een echt consolevenster (pty) ===")
    met_console()
    print("=== zonder console (pijp) ===")
    zonder_console()
    print("\n%d van %d goed" % (len(goed), len(goed) + len(fout)))
    return 0 if not fout else 1


if __name__ == "__main__":
    sys.exit(main())
