"""De instellingen van het programma: de huidige locatie (besluit van Jan, 15 oktober 2026).

Eén bestand naast de kaarten (`~/astrologie-kaarten/settings.json`), zodat één map kopiëren de
hele back-up is. Het pad is **één functie met een omgevingsvariabele erover**
(`ASTRO_INSTELLINGEN`), net als het efemeridenpad: het einddoel is een app voor Windows en daar
hoort dit bestand in de gebruikersmap (`%APPDATA%`).

Vastgelegd wordt alles wat aan de huidige locatie vastligt: de plaatsnaam, het etiket dat de
keuzelijst toont, de breedte, de lengte en de tijdzone (Jans antwoord van 15 oktober 2026: "alles
wat je aan vaste waarden hebt over de huidige locatie, dus: ja").

**Geen stille terugval.** Een ontbrekend bestand is `None` - dan vraagt de pagina om de locatie in
te stellen. Een bestand dat niet te lezen is of velden mist is een fout met een boodschap in gewone
taal (een `InvoerFout`, en de schil antwoordt met 400): nooit een gok en nooit een half ingevulde
locatie, net als bij de efemeriden en de tijdzone.
"""

from __future__ import annotations

import datetime
import json
import os

from . import invoer as kern_invoer
from . import opslag

VERSIE = "instellingen-0.1"
BESTAND = "settings.json"
SLEUTELS = ("naam", "etiket", "lat", "lon", "tijdzone_id")


def bestandspad(pad=None):
    """Het instellingenbestand: naast de kaarten, tenzij de omgeving of de vraag iets anders zegt."""
    if pad:
        return os.path.expanduser(str(pad))
    uit_omgeving = os.environ.get("ASTRO_INSTELLINGEN")
    if uit_omgeving:
        return os.path.expanduser(uit_omgeving)
    return os.path.join(opslag.kaartmap(), BESTAND)


def lees(pad=None):
    """De instellingen als dict, of `None` als ze nog niet ingesteld zijn.

    Een bestand dat niet bestaat is geen fout (dan is er nog niets ingesteld); een bestand dat niet
    te lezen is of velden mist wel.
    """
    p = bestandspad(pad)
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            inhoud = json.load(f)
    except Exception as e:
        raise kern_invoer.InvoerFout(
            [f"Het instellingenbestand '{p}' is niet te lezen ({e}). "
             f"Haal het weg of stel de locatie opnieuw in."])
    if not isinstance(inhoud, dict):
        raise kern_invoer.InvoerFout(
            [f"Het instellingenbestand '{p}' bevat geen instellingen."])
    ontbreekt = [sleutel for sleutel in SLEUTELS if sleutel not in inhoud]
    if ontbreekt:
        raise kern_invoer.InvoerFout(
            [f"Het instellingenbestand '{p}' mist: {', '.join(ontbreekt)}. "
             f"Stel de locatie opnieuw in."])
    return inhoud


def bewaar(waarden, pad=None):
    """De locatie lezen en keuren (dezelfde lezer als het formulier) en wegschrijven.

    Geeft `{bestand, instellingen, nieuw, waarschuwingen}`: `nieuw` is waar als er nog geen
    instellingenbestand stond. Een onbekende tijdzone is een waarschuwing en geen fout - de lezer
    valt dan stil terug op LMT en dat hoort de pagina te melden.
    """
    # Eerst kijken dát het een object met velden is: zonder deze regel gaf een lijst of een tekst een
    # AttributeError (een 500 in de schil) in plaats van een regel in gewone taal. Gevonden door
    # `ijking/ijk-instellingen.py`, geval "geen lijst met velden" (20 okt 2026).
    if not isinstance(waarden, dict):
        raise kern_invoer.InvoerFout(
            ["De instellingen horen als één object met velden te worden aangeboden "
             "(plaats, etiket, breedte, lengte en tijdzone)."])
    # Het e-mailveld is er sinds 20 oktober 2026 niet meer: OpenStreetMap gaat via de eigen proxy,
    # die met de gegevens van de beheerder vraagt. Een oude `settings.json` met een `email`-sleutel
    # blijft leesbaar — die sleutel wordt alleen niet meer bewaard.
    schoon = kern_invoer.lees_plaats(waarden)
    p = bestandspad(pad)
    map_ = os.path.dirname(p)
    if map_:
        os.makedirs(map_, exist_ok=True)
    nieuw = not os.path.exists(p)
    inhoud = {"versie": VERSIE,
              "bijgewerkt": datetime.datetime.now().replace(microsecond=0).isoformat(),
              **{sleutel: schoon[sleutel] for sleutel in SLEUTELS}}
    with open(p, "w", encoding="utf-8") as f:
        json.dump(inhoud, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return {"bestand": p, "instellingen": inhoud, "nieuw": nieuw,
            "waarschuwingen": schoon["waarschuwingen"]}
