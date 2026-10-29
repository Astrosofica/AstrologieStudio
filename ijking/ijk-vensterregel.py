#!/usr/bin/env python3
"""IJking van de vensterregel (28 okt 2026): een gelukte stand hoort achter `--log`, een mislukking
hoort altijd op het scherm.

Waarom dit een eigen proef is: de regel komt uit `_pas_venster_toe()`, en die draait pas als er echt
een browservenster opent. In een pijp of in een ijk-run zonder browser komt hij dus nooit langs, en
dan zegt een test die alleen naar de uitvoer kijkt niets. Daarom hier de vier gevallen direct: met en
zonder `ALLES_OP_HET_SCHERM`, bij een gelukte en bij een mislukte stand — plus de stille bundel.

Draaien:  /usr/bin/python3 ijking/ijk-vensterregel.py
"""

from __future__ import annotations

import contextlib
import io
import os
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HIER)
sys.path.insert(0, os.path.join(PROJECT, "schil"))
sys.path.insert(0, PROJECT)

goed, fout = [], []


def meld(ok, wat, detail=""):
    (goed if ok else fout).append(wat)
    print("%-6s %s%s" % ("GOED" if ok else "FOUT", wat, ("  " + detail) if detail else ""))


def proef():
    import server as S

    echte_pas_toe = S.venster.pas_toe
    echte_stil = S.STIL
    echte_alles = S.ALLES_OP_HET_SCHERM

    def uitvoer(regel, gelukt, alles_op_scherm, stil=False):
        S.venster.pas_toe = lambda *a, **k: (regel, gelukt)
        S.ALLES_OP_HET_SCHERM = alles_op_scherm
        S.STIL = stil
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            S._pas_venster_toe((1440, 900), (1440, 900), None, "proef")
        return buffer.getvalue()

    try:
        gelukt_regel = "gemaximaliseerd (herstelmaat 1440 x 900)"
        fout_regel = "het venster is niet gevonden"

        # 1. Gelukt zonder --log: niets. Dit is de klacht van Jan (28 okt 2026).
        tekst = uitvoer(gelukt_regel, True, False)
        meld(tekst == "", "een gelukte stand zwijgt zonder --log", repr(tekst))

        # 2. Gelukt met --log: de regel, in de vorm die hij kent.
        tekst = uitvoer(gelukt_regel, True, True)
        meld("venster      " + gelukt_regel in tekst and tekst.count("venster") == 1,
             "een gelukte stand verschijnt met --log", repr(tekst))

        # 3. Mislukt zonder --log: blijft staan. Anders is er geen regel meer die een verkeerd venster
        #    verklaart, en dat was juist de bedoeling van de uitzondering.
        tekst = uitvoer(fout_regel, False, False)
        meld("venster      " + fout_regel in tekst,
             "een mislukking blijft zonder --log staan", repr(tekst))

        # 4. Mislukt met --log: ook, en één keer.
        tekst = uitvoer(fout_regel, False, True)
        meld(tekst.count("  venster      ") == 1 and fout_regel in tekst,
             "een mislukking verschijnt ook met --log, één keer", repr(tekst))

        # 5. De stille bundel zwijgt altijd, ook over een mislukking: daar is geen console om het te
        #    lezen en de regel zou alleen in een logbestand van de bouw belanden.
        tekst = uitvoer(fout_regel, False, False, stil=True)
        meld(tekst == "", "de stille bundel zwijgt ook bij een mislukking", repr(tekst))
    finally:
        S.venster.pas_toe = echte_pas_toe
        S.STIL = echte_stil
        S.ALLES_OP_HET_SCHERM = echte_alles


def main():
    print("IJking vensterregel - %d proeven\n" % 5)
    proef()
    print("\n%d goed, %d fout" % (len(goed), len(fout)))
    return 0 if not fout else 1


if __name__ == "__main__":
    sys.exit(main())
