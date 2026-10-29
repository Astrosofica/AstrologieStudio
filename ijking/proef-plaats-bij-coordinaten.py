"""Proef: past de plaatsnaam bij de coördinaten van elke bewaarde kaart?

Telt per kaart de exacte naamtreffers in de plaatsenlijst en de afstand (km) van de bewaarde
coördinaten tot de dichtstbijzijnde treffer. Bedoeld om te bepalen welke tolerantie de controle
kan hebben zonder de kaarten van Jan te breken.
"""
import glob
import json
import math
import os
import sys

sys.path.insert(0, os.path.expanduser("~/projects/astrologie-studio"))
from kern import plaatsen  # noqa: E402


def afstand_km(lat1, lon1, lat2, lon2):
    dlat = (lat2 - lat1) * 111.0
    dlon = (lon2 - lon1) * 111.0 * math.cos(math.radians(lat1))
    return math.hypot(dlat, dlon)


def kaartbestanden():
    map_ = os.path.expanduser("~/astrologie-horoscopen")
    for pad in sorted(glob.glob(os.path.join(map_, "*.json"))):
        naam = os.path.basename(pad)
        if naam in ("index.json", "settings.json"):
            continue
        yield pad


def main():
    rijen = []
    for pad in kaartbestanden():
        d = json.load(open(pad, encoding="utf-8"))
        m = d.get("meta", {})
        plaats, lat, lon = m.get("plaats"), m.get("lat"), m.get("lon")
        treffers = plaatsen.zoek(str(plaats), limiet=50) if plaats else []
        exact = [t for t in treffers if t["naam"].strip().lower() == str(plaats).strip().lower()]
        dichtst = min((afstand_km(lat, lon, t["lat"], t["lon"]) for t in exact), default=None)
        rijen.append({
            "bestand": os.path.basename(pad),
            "plaats": plaats, "lat": lat, "lon": lon,
            "treffers": len(treffers),
            "exact": [(t["naam"], t["land"], round(afstand_km(lat, lon, t["lat"], t["lon"]), 2))
                      for t in exact],
            "dichtst_km": None if dichtst is None else round(dichtst, 2),
        })
    print(json.dumps(rijen, ensure_ascii=False, indent=1))
    print()
    print("kaarten:", len(rijen),
          "| zonder exacte treffer:", sum(1 for r in rijen if not r["exact"]),
          "| verder dan 1 km:", [r["bestand"] for r in rijen if r["dichtst_km"] is not None and r["dichtst_km"] > 1.0])


if __name__ == "__main__":
    main()
