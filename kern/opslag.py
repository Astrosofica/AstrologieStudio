"""Kaartopslag: één bestand per kaart in een gewone map plus één indexbestand (besluit T21).

Geen databank, geen accounts. De map is met de hand te lezen en te kopiëren; een back-up is
de map kopiëren.

De index (`index.json`) is de kaartenlijst van de pagina: per kaart de bestandsnaam, de naam, het
moment, de plaats, de tijdzone en het huizenstelsel. Daar staat het huizenstelsel als **letter**
(`K`), want dat is wat `kern/kaart.py` verwacht als een bewaarde kaart opnieuw gerekend wordt; de
naam (`Koch`) staat in het kaartbestand zelf. Tot 14 oktober 2026 stond in de index de naam, en
gaf een bewaarde kaart opnieuw rekenen een 500.
"""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata

from .efemeride import HUISSTELSELS
from .invoer import InvoerFout
from . import paden

# De map heet sinds 20 oktober 2026 `~/astrologie-horoscopen` (Jan: "hernoem de map ook maar, we zijn
# nog steeds in development mode"). De oude naam `~/astrologie-kaarten` is met de verhuizing vervallen;
# de omgevingsvariabele heet mee `ASTRO_HOROSCOPENMAP`. Sinds de bundel (20 okt 2026) komt de map uit
# `kern/paden.py`, zodat de schrijfmap losstaat van de map waarin het programma zelf staat.
STANDAARD_MAP = paden.standaardmap()
INDEX = "index.json"


def _slug(naam):
    s = unicodedata.normalize("NFKD", naam).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s or "kaart"


def veilige_naam(bestand):
    """Alleen een kale bestandsnaam uit de eigen map: geen pad, geen `..`, geen index."""
    tekst = str(bestand if bestand is not None else "").strip()
    naam = os.path.basename(tekst)
    if not naam or naam != tekst or naam in (INDEX, ".", "..") or not naam.endswith(".json"):
        raise InvoerFout([f"'{bestand}' is geen horoscoopbestand uit de map met horoscopen."])
    return naam


def kaartmap(map_=None):
    m = os.path.expanduser(map_ or STANDAARD_MAP)
    os.makedirs(m, exist_ok=True)
    return m


def bestandsnaam(kaart):
    meta = kaart["meta"]
    return f"{meta['datum']}-{_slug(meta['naam'])}.json"


# --- het id van een kaart ----------------------------------------------------------------------
# Sinds 19 oktober 2026 heeft elke kaart een **id**: de tijd van aanmaken in milliseconden. Het is
# het anker van de kaart en niet de bestandsnaam, want die volgt uit datum en naam en verandert dus
# zodra de gebruiker de kaart hernoemt (of botst als twee kaarten dezelfde naam en datum hebben).
# Het id staat in de index en, bij het wegschrijven, ook in `meta` van het kaartbestand zelf: de
# index is de waarheid, het bestand is de leesbare kopie. Een kaart van vóór die datum krijgt er
# één bij het lezen van de index, uit de mtime van het bestand - eerlijk: "sinds dan staat hij er".

def _nu_ms():
    return int(time.time() * 1000)


def _als_int(waarde):
    try:
        return int(waarde)
    except (TypeError, ValueError):
        return None


def _id_rij(regel):
    return _als_int((regel or {}).get("id"))


def _vrij_id(index):
    cid = _nu_ms()
    gezet = {_id_rij(r) for r in index}
    while cid in gezet:
        cid += 1
    return cid


def _migreer(m, index):
    """Id's toekennen waar ze ontbreken en dubbele id's uit elkaar trekken. Geeft (index, gewijzigd).

    Twee kaarten met hetzelfde id komt van een gekopieerd bestand of een teruggezette back-up; de
    tweede schuift één milliseconde op, zodat "aanpassen" altijd één kaart raakt en niet twee.
    """
    gewijzigd = False
    gezien = set()
    for regel in index:
        cid = _id_rij(regel)
        if cid is None:
            bestand = regel.get("bestand")
            if bestand:
                try:
                    cid = int(os.path.getmtime(os.path.join(m, veilige_naam(bestand))) * 1000)
                except (OSError, InvoerFout):
                    cid = None
            if cid is None:
                cid = _nu_ms()
            gewijzigd = True
        while cid in gezien:
            cid += 1
            gewijzigd = True
        gezien.add(cid)
        if _id_rij(regel) != cid:
            regel["id"] = cid
            gewijzigd = True
    return index, gewijzigd


def _doelnaam(m, kaart, cid, oud):
    """De bestandsnaam voor deze kaart: leesbaar, en nooit stilletjes die van een ándere kaart."""
    basis = bestandsnaam(kaart)
    if oud and oud.get("bestand") == basis:
        return basis                     # dezelfde kaart, dezelfde naam: overschrijven
    if not os.path.exists(os.path.join(m, basis)):
        return basis
    # De naam is bezet: het id erachter. Twee keer "Jan" op dezelfde datum mag niet stil
    # overschrijven, en de bestandsnaam moet leesbaar blijven.
    return basis[:-5] + "-" + str(cid) + ".json"


def bewaar(kaart, map_=None, vervang=None):
    """Kaart wegschrijven en de index bijwerken. Geeft (pad, nieuw, id).

    `vervang` is het id van de kaart die overschreven wordt (None of onbekend: een nieuwe kaart).
    Verandert de naam, dan verhuist het bestand mee en gaat het oude bestand weg - anders staan er
    twee kaarten van dezelfde horoscoop.
    """
    m = kaartmap(map_)
    indexpad = os.path.join(m, INDEX)
    index = _migreer(m, _lees_index(indexpad))[0]
    oud = None
    vervang_id = _als_int(vervang)
    if vervang_id is not None:
        for regel in index:
            if _id_rij(regel) == vervang_id:
                oud = regel
                break
    cid = _id_rij(oud) if oud else None
    if cid is None:
        cid = _vrij_id(index)
    kaart.setdefault("meta", {})["id"] = cid
    naam = _doelnaam(m, kaart, cid, oud)
    pad = os.path.join(m, naam)
    nieuw = oud is None
    with open(pad, "w", encoding="utf-8") as f:
        json.dump(kaart, f, ensure_ascii=False, indent=2)
    if oud and oud.get("bestand") and oud["bestand"] != naam:
        oudpad = os.path.join(m, veilige_naam(oud["bestand"]))
        if os.path.exists(oudpad):
            os.remove(oudpad)
    _index_bijwerken(m, naam, kaart, cid)
    return pad, nieuw, cid


def _index_bijwerken(m, naam, kaart, cid=None):
    pad = os.path.join(m, INDEX)
    index = _lees_index(pad)
    meta = kaart["meta"]
    regel = {
        "id": cid if cid is not None else _id_rij(meta),
        # Wanneer deze kaart voor het laatst **bewaard** is (26 okt 2026). Alleen in de index, niet in
        # de kaart: de index is een afgeleide en geen contract, en het `id` blijft het anker voor
        # Aanpassen (dat verandert dus niet als je een kaart opnieuw bewaart). Het paneel sorteert
        # hierop: "recente horoscopen" is "laatst bewaard", niet "laatst aangemaakt".
        "bewaard": _nu_ms(),
        "bestand": naam,
        "naam": meta["naam"],
        "datum": meta["datum"],
        "tijd": meta["tijd"],
        "plaats": meta.get("plaats", ""),
        "tijdzone_id": meta.get("tijdzone_id", ""),
        "huizenstelsel": meta.get("huizenstelsel", "K"),
        "huizenstelsel_naam": meta.get("huizenstelsel_naam", "Koch"),
        "met_chiron": bool(meta.get("met_chiron")),
    }
    index = [r for r in index
             if r.get("bestand") != regel["bestand"] and _id_rij(r) != regel["id"]]
    index.append(regel)
    index.sort(key=lambda r: (r.get("naam", ""), r.get("datum", "")))
    with open(pad, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    return pad


def _lees_index(pad):
    if not os.path.exists(pad):
        return []
    try:
        with open(pad, encoding="utf-8") as f:
            inhoud = json.load(f)
    except Exception:
        return []
    return inhoud if isinstance(inhoud, list) else []


def lees(bestand, map_=None):
    m = kaartmap(map_)
    naam = veilige_naam(bestand)
    pad = os.path.join(m, naam)
    if not os.path.exists(pad):
        raise InvoerFout([f"De horoscoop '{naam}' staat niet in de map met horoscopen ({m})."])
    with open(pad, encoding="utf-8") as f:
        return json.load(f)


def verwijder(bestand, map_=None):
    """Kaartbestand weggooien en de regel uit de index halen. Geeft de bestandsnaam terug."""
    m = kaartmap(map_)
    naam = veilige_naam(bestand)
    pad = os.path.join(m, naam)
    if not os.path.exists(pad):
        raise InvoerFout([f"De horoscoop '{naam}' staat niet in de map met horoscopen ({m})."])
    os.remove(pad)
    indexpad = os.path.join(m, INDEX)
    index = [r for r in _lees_index(indexpad) if r.get("bestand") != naam]
    with open(indexpad, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    return naam


def lijst(map_=None):
    """De kaartenlijst uit de index; regels zonder bestand vallen af.

    Hier zit ook de migratie: een regel zonder id (van vóór 19 oktober 2026) krijgt er één. Dat
    wordt meteen weggeschreven, zodat het id daarna vastligt en niet bij elke keer lezen uit de
    mtime opnieuw wordt afgeleid.
    """
    m = kaartmap(map_)
    pad = os.path.join(m, INDEX)
    index, gewijzigd = _migreer(m, _lees_index(pad))
    if gewijzigd:
        with open(pad, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    return [_recht(regel) for regel in index if regel.get("bestand")]


def _recht(regel):
    """Een oude indexregel (vóór 14 oktober 2026) rechtzetten.

    Daar stond de **naam** van het huizenstelsel ("Koch") in het veld waar nu de **letter**
    ("K") hoort. De kaart zelf is niet in orde te maken (die is wat hij is), maar de lijst en
    het openen horen altijd hetzelfde te lezen; daarom hier omzetten bij het lezen.
    """
    uit = dict(regel)
    waarde = str(uit.get("huizenstelsel") or "").strip()
    if len(waarde) > 1:
        for letter, naam in HUISSTELSELS.items():
            if naam.lower() == waarde.lower():
                uit["huizenstelsel"] = letter
                break
    uit.setdefault("huizenstelsel_naam",
                   HUISSTELSELS.get(str(uit.get("huizenstelsel") or ""), ""))
    uit.setdefault("met_chiron", False)
    uit.setdefault("plaats", "")
    uit.setdefault("tijdzone_id", "")
    uit["id"] = _id_rij(uit)          # het anker van de kaart; altijd int of None, nooit een string
    return uit
