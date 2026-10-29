"""Aspecten: de acht uit zijn eigen programma, met orbs, en de twee eigen regels.

Overgebracht uit `src/Calculation/AspectCalculator.php` (AspectCalculator::ASPECT_DEFINITIONS).
Besluit T18. De regels die het verschil maken:

1. **Buiten teken vervalt boven 2 graden orb** - een aspect waarvan de lichamen in
   verschillende tekens staan telt alleen mee bij een orb <= 2. Geldt alleen voor de
   "zodiacale" hoeken 0/60/90/120/150/180; 45 en 135 kennen de regel niet (net als in PHP).
2. **Dominant** - een hard aspect (0, 45, 90, 135, 180) naar Ascendant of MC onder 2 graden.

S/A (scheidend/aanvallend) is hier nagemeten in plaats van overgenomen: per paar wordt
gekeken of de orb met de tijd kleiner wordt (aanvallend) of groter (scheidend).
"""

from __future__ import annotations

import math

from . import formaat

ASPECTEN = [
    {"hoek": 0,   "orb": 6.0, "naam": "Conjunctie",        "hard": True},
    {"hoek": 180, "orb": 6.0, "naam": "Oppositie",         "hard": True},
    {"hoek": 90,  "orb": 6.0, "naam": "Vierkant",          "hard": True},
    {"hoek": 120, "orb": 5.0, "naam": "Driehoek",          "hard": False},
    {"hoek": 60,  "orb": 4.0, "naam": "Sextiel",           "hard": False},
    {"hoek": 150, "orb": 2.5, "naam": "Inconjunct",        "hard": False},
    {"hoek": 45,  "orb": 2.0, "naam": "Halfvierkant",      "hard": True},
    {"hoek": 135, "orb": 2.0, "naam": "Anderhalfvierkant", "hard": True},
]
ZODIACAAL = [0, 60, 90, 120, 150, 180]
DT = 0.01   # dagen, voor het bepalen van aanvallend/scheidend

# De kleurgroepen van Jan voor de tekening (13 oktober 2026, avondronde): de harde aspecten rood,
# de harmonische groen, de inconjunct (150) als eigen groep - die is niet hard maar ook niet
# harmonisch. De harde groep is precies de `hard`-vlag uit het bronprogramma (die de
# dominantregel gebruikt), dus er is één waarheid over wat hard is. Alleen op het scherm:
# de afdruk laat de aspectlijnen helemaal weg (besluit T14).
HARMONISCH = (60, 120)

# Punten die **geen** aspectlijnen krijgen (Jan, 29 okt 2026). De regel erachter: aspecten horen tussen
# planeten onderling en tussen planeten en de hoeken; de knoop en de pars zijn geen van beide. Dat is
# vakinhoud en geen opmaak, dus de lijst staat hier en niet in de pagina - de weergave leest hem uit de
# kaart (`weg_punt`) en de tekenaar gebruikt hem ook. Reden zoals Jan hem gaf: ruimte én pedagogie
# ("deels voor ruimte en deels vanuit pedagogisch oogpunt").
#
# De aspecten zelf blijven **berekend**: `kaart["aspecten"]` houdt alle paren en de matrix blijft
# 14 x 14. Wie later toch aspecten naar de knoop wil (er zijn scholen die dat doen), haalt hier één naam
# weg en wiel, lijst en trap volgen alle drie - er is geen tweede plek om te zoeken (besluit T42).
WEG_PUNT = ("Noorderknoop", "Dagpars")


def soort_van(definitie):
    """"hard", "harmonisch" of "overig" - de groep waar de kleur aan hangt."""
    if definitie["hard"]:
        return "hard"
    return "harmonisch" if definitie["hoek"] in HARMONISCH else "overig"



def afstand(lon1, lon2):
    """Kortste boog 0..180, gelijk aan AspectCalculator::calculateDistance()."""
    d = abs(lon1 - lon2)
    return 360.0 - d if d > 180.0 else d


def vind_aspect(afst, hoek, orb_range):
    """None of de orb (afstand tot de exacte hoek); zelfde strikte ongelijkheden als PHP."""
    if afst > hoek - orb_range and afst < hoek + orb_range:
        return abs(afst - hoek)
    return None


def buiten_teken(lon1, lon2, hoek):
    """De buiten-teken-toets uit het PHP-programma, letterlijk."""
    s1 = int(lon1 / 30)
    s2 = int(lon2 / 30)
    verw1 = int((((lon1 + hoek) % 360)) / 30)
    verw2 = int((((lon2 + hoek) % 360)) / 30)
    return verw1 != s2 and verw2 != s1


def bereken(punten, alleen_met_hoeken=True):
    """`punten`: [{naam, lengte, snelheid, is_hoek}] -> lijst aspecten (dicts)."""
    uit = []
    n = len(punten)
    for i in range(n):
        for j in range(i + 1, n):
            p1, p2 = punten[i], punten[j]
            if p1["naam"] in ("Ascendant", "MC") and p2["naam"] in ("Ascendant", "MC"):
                continue    # Asc-MC slaat het programma over
            afst = afstand(p1["lengte"], p2["lengte"])
            for def_ in ASPECTEN:
                orb = vind_aspect(afst, def_["hoek"], def_["orb"])
                if orb is None:
                    continue
                oos = False
                if def_["hoek"] in ZODIACAAL:
                    oos = buiten_teken(p1["lengte"], p2["lengte"], def_["hoek"])
                    if oos and orb > 2.0:
                        continue
                dominant = False
                if p2["naam"] in ("Ascendant", "MC") and def_["hard"] and orb < 2.0:
                    dominant = True
                aanvallend = _aanvallend(p1, p2, def_["hoek"], afst)
                uit.append({
                    "p1": p1["naam"],
                    "p2": p2["naam"],
                    "hoek": def_["hoek"],
                    "naam": def_["naam"],
                    "orb": orb,
                    "orb_afgekapt": formaat.orb_kort(orb),
                    "scheidend": not aanvallend,
                    "letter": "A" if aanvallend else "S",
                    "dominant": dominant,
                    "buiten_teken": oos,
                    "glyf": formaat.glyf_aspect(def_["hoek"]),
                    "soort": soort_van(def_),
                })
    return uit


def _aanvallend(p1, p2, hoek, afst_nu):
    """Waar als de orb kleiner wordt: het aspect nadert dus (applying, letter A).

    Let op de naam: "aanvallend" komt uit het bronprogramma en betekent hier **ingaand**
    (applying / approaching) — niet hard, niet agressief. Het tegendeel is **uitgaand**
    (separating / parting, letter S). Jan, 19 okt 2026: "Ingaand = Applying (of approaching) en
    Uitgaand = Separating (of parting)." De sleutel in de kaart-JSON blijft `scheidend`
    (true = uitgaand): dat is het contract, ook al is de term misleidend.
    """
    l1 = p1["lengte"] + p1.get("snelheid", 0.0) * DT
    l2 = p2["lengte"] + p2.get("snelheid", 0.0) * DT
    return abs(afstand(l1, l2) - hoek) < abs(afst_nu - hoek)


def dominante(aspecten):
    return [a for a in aspecten if a["dominant"]]


def matrix(punten, aspecten):
    """Driehoekige matrix: rijen/kolommen in de volgorde van `punten`.

    Elke cel: lijst met (glyf, orb, letter) - in de praktijk nul of één, want de orbreeksen
    van de acht aspecten overlappen elkaar niet.
    """
    index = {p["naam"]: k for k, p in enumerate(punten)}
    cellen = {}
    for a in aspecten:
        i, j = index[a["p1"]], index[a["p2"]]
        if i > j:
            i, j = j, i
        cellen.setdefault((i, j), []).append(a)
    return cellen


def als_tekst(aspecten):
    regels = []
    for a in sorted(aspecten, key=lambda x: (x["hoek"], x["p1"])):
        regels.append(
            f"{a['p1']:<12} {a['naam']:<19} {a['p2']:<12} orb {a['orb']:5.2f}° "
            f"({a['orb_afgekapt']:>7}) {a['letter']}"
            + ("  DOMINANT" if a["dominant"] else "")
            + ("  [buiten teken]" if a["buiten_teken"] else "")
        )
    return regels


def _unused():   # houdt math geïmporteerd voor toekomstige helpers
    return math.pi
