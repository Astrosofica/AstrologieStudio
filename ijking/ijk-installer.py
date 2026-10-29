#!/usr/bin/env python3
"""Controle vóór het compileren: klopt het Inno Setup-script met wat er in de projectmap staat?

Inno Setup draait alleen op Windows, dus op de server kan de installer niet gebouwd worden. Wat hier
wél kan, is alles nakijken waar ISCC op zou stuklopen: bestaat elk bestand dat het script noemt, is
`versie.iss` geschreven en klopt het nummer met `kern/versie.py`, en staan de twee dingen die niet
mogen ontbreken erin (de bronzip voor de AGPL, en de vraag over de gegevensmap bij het verwijderen).

Wat dit script **niet** kan: de Pascal-code in [Code] compileren. Dat gebeurt op de Windows-pc; klaagt
ISCC daarover, dan is dat de eerste echte proef. Eén klasse van die fouten wordt hier wél gevangen:
commentaar met een accolade-paar erin, want Pascal kent geen geneste commentaren en zo'n notitie sluit
zichzelf (27 okt 2026).

Draaien:  /usr/bin/python3 ijking/ijk-installer.py
"""

from __future__ import annotations

import os
import re
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HIER)
sys.path.insert(0, PROJECT)

from kern.versie import VERSIE        # noqa: E402
from kern import paden                # noqa: E402

BOUW = os.path.join(PROJECT, "bouw")
ISS = os.path.join(BOUW, "astrologie-studio.iss")

goed, fout = [], []


def meld(ok, wat, detail=""):
    (goed if ok else fout).append(wat)
    print(("ok    " if ok else "FOUT  ") + wat + ((" - " + detail) if detail else ""))


def rtf_tekst(ruw: bytes) -> str:
    """De leesbare tekst uit een RTF-bestand — genoeg om te controleren wát er staat.

    **Een ontleder, geen rij regexen.** RTF schrijft één backslash als `\\\\`, en een regex die eerst
    alle stuurwoorden wegstreept leest `\\astrologie` als het stuurwoord `\\astrologie` en gooit de
    mapnaam weg. Dat gebeurde hier op 28 okt 2026 bijna: de controle meldde een fout in de aangeleverde
    tekst (`horoscopen` in plaats van `astrologie-horoscopen`) die niet bestond — de tekst was goed, de
    lezer was stuk. `\\\\`, `\\{`, `\\}`, `\\'xx` en `\\uNNNN` worden daarom vóór de stuurwoorden
    afgehandeld, en de groepskoppen `{ … }` vallen weg zonder de tekst erin aan te raken.
    """
    tekst = ruw.decode("cp1252", "replace")
    for naam in ("fonttbl", "colortbl", "stylesheet", "info", "*"):
        while True:
            i = tekst.find("{\\" + naam)
            if i < 0:
                break
            diepte, j = 0, i
            while j < len(tekst):
                if tekst[j] == "{":
                    diepte += 1
                elif tekst[j] == "}":
                    diepte -= 1
                    if diepte == 0:
                        break
                j += 1
            tekst = tekst[:i] + tekst[j + 1:]

    uit, i, n = [], 0, len(tekst)
    while i < n:
        teken = tekst[i]
        if teken == "\\":
            volgende = tekst[i + 1] if i + 1 < n else ""
            if volgende in ("\\", "{", "}"):
                uit.append(volgende)
                i += 2
                continue
            if volgende == "'":
                uit.append(bytes([int(tekst[i + 2:i + 4], 16)]).decode("cp1252", "replace"))
                i += 4
                continue
            m = re.match(r"([a-zA-Z]+)(-?\d+)? ?", tekst[i + 1:])
            if not m:
                i += 2
                continue
            woord, getal = m.group(1), m.group(2)
            i += 1 + m.end()
            if woord in ("par", "line"):
                uit.append("\n")
            elif woord == "tab":
                uit.append("\t")
            elif woord == "u" and getal:
                uit.append(chr(int(getal) % 65536))
                if i < n:                     # \\uc1: het valt-teken erna overslaan
                    i += 1
            continue
        if teken in "{}":
            i += 1
            continue
        uit.append(teken)
        i += 1
    return "".join(uit)


def keur_commentaren(code_deel):
    """Commentaar in [Code] mag geen accolade-paar bevatten.

    Pascal kent geen geneste commentaren: `{ uitleg met {x} erin }` eindigt bij de éérste `}` die
    na dat binnenste haakje komt - de rest van de regel wordt dan als code gelezen en de compiler
    struikelt. Dat overkwam ons op 27 okt 2026 met een notitie die juist over die constante ging:
    de uitleg over `userprofile` brak zichzelf. Commentaarregels met `//` zijn wel veilig, en
    accolades tussen aanhalingstekens zijn gewone tekst (zoals `{%USERPROFILE}` in ExpandConstant).
    """
    problemen = []
    binnen, haak_erin, start = False, False, 0
    for nr, regel in enumerate(code_deel.splitlines(), 1):
        i = 0
        while i < len(regel):
            teken = regel[i]
            if binnen:
                if teken == "{":
                    haak_erin = True
                elif teken == "}":
                    if haak_erin:
                        problemen.append((start, regel.strip()))
                    binnen, haak_erin = False, False
                i += 1
                continue
            if teken == "'":                     # letterlijke tekst: geen commentaar
                sluit = regel.find("'", i + 1)
                i = len(regel) if sluit < 0 else sluit + 1
                continue
            if regel.startswith("//", i):        # commentaar tot het eind van de regel
                break
            if teken == "{":
                binnen, haak_erin, start = True, False, nr
            i += 1
    if binnen:
        problemen.append((start, "(commentaar niet gesloten)"))
    return problemen


def main():
    if not os.path.isfile(ISS):
        print("FOUT: bouw/astrologie-studio.iss ontbreekt.")
        return 1
    tekst = open(ISS, encoding="utf-8").read()

    # 1. versie.iss: geschreven door maak-versie-iss.py, en het nummer moet hetzelfde zijn.
    versie_pad = os.path.join(BOUW, "versie.iss")
    if not os.path.isfile(versie_pad):
        meld(False, "bouw/versie.iss bestaat", "draai eerst: python bouw/maak-versie-iss.py")
        print("\nNiet in orde.")
        return 1
    v = open(versie_pad, encoding="utf-8").read()
    m = re.search(r'#define\s+AppVersie\s+"([^"]+)"', v)
    meld(bool(m) and m.group(1) == VERSIE, "versienummer gelijk aan kern/versie.py",
         "%s (script) vs %s (versie.py)" % (m.group(1) if m else "?", VERSIE))
    mz = re.search(r'#define\s+BronZip\s+"([^"]+)"', v)
    bronzip = os.path.join(PROJECT, "uitgave", mz.group(1)) if mz else ""
    meld(bool(mz) and os.path.isfile(bronzip), "de bronzip bestaat",
         mz.group(1) if mz else "(geen BronZip in versie.iss)")

    # 2. alle bestanden die het script noemt, met de defines ingevuld. AppExe wordt uit het script
    #    zelf gelezen in plaats van hier overgetypt: anders keurt de proef een naam die er niet
    #    meer staat (27 okt 2026 ging de installer van de stille naar de consoleversie).
    mexe = re.search(r'#define\s+AppExe\s+"([^"]+)"', tekst)
    meld(bool(mexe), "AppExe staat in het script", mexe.group(1) if mexe else "(niet gevonden)")
    #    Het besluit van 27 okt 2026: de cursist krijgt de versie MET consolevenster, zodat hij
    #    ziet dat er een lokale server draait. Deze proef houdt dat vast.
    meld(bool(mexe) and "console" in mexe.group(1),
         "de installer bundelt de consoleversie (besluit: niets verbergen)",
         mexe.group(1) if mexe else "")
    defines = {"AppNaam": "Astrologie Studio", "AppExe": mexe.group(1) if mexe else "?",
               "AppVersie": VERSIE, "BronZip": mz.group(1) if mz else ""}
    bronnen = re.findall(r'^\s*Source:\s*"([^"]+)"', tekst, flags=re.M)
    ontbreekt = []
    for pad in bronnen:
        for naam, waarde in defines.items():
            pad = pad.replace("{#%s}" % naam, waarde)
        vol = os.path.normpath(os.path.join(BOUW, pad.replace("\\", "/")))
        if "*" in vol:
            map_, patroon = os.path.dirname(vol), os.path.basename(vol)
            if not (os.path.isdir(map_) and any(f.endswith(patroon.lstrip("*"))
                                                for f in os.listdir(map_))):
                ontbreekt.append(pad)
        elif not os.path.isfile(vol):
            # Op Linux zet PyInstaller geen .exe achter de naam; het script noemt de Windows-naam.
            # Wie dit op de server draait, mag daar niet op stuklopen.
            if not (vol.endswith(".exe") and os.path.isfile(vol[:-4])):
                ontbreekt.append(pad)
    meld(not ontbreekt, "%d bestanden uit [Files] aanwezig" % len(bronnen),
         ", ".join(ontbreekt) if ontbreekt else "")

    # 3. de losse bestanden buiten [Files]: het pictogram en de tekst vóór de installatie.
    for directive, pad in (("SetupIconFile", "astrologie-studio.ico"),
                           ("InfoBeforeFile", "installatie-tekst.rtf")):
        meld(directive in tekst and os.path.isfile(os.path.join(BOUW, pad)),
             "%s wijst naar een bestaand bestand" % directive, pad)

    # 3b. Die tekst is sinds 28 okt 2026 **RTF** (koppen en vet, Inno toont hem in een rich-edit-venster).
    #     Dan moet het bestand ook echt RTF zijn: een .txt met een andere naam zet stuurcodes op het
    #     scherm. En er mag niets in staan wat dat venster niet kan — tabellen en afbeeldingen. De
    #     belangrijkste controle is de laatste: de map die erin staat moet de map zijn die het programma
    #     ook echt maakt. Let op: die controle ging op 28 okt 2026 zelf de fout in - de eerste versie van
    #     `rtf_tekst()` at de backslash voor `astrologie` op en meldde een fout die niet bestond. Zie de
    #     vangnet-controle hieronder.
    rtf_pad = os.path.join(BOUW, "installatie-tekst.rtf")
    if os.path.isfile(rtf_pad):
        with open(rtf_pad, "rb") as f:
            ruw = f.read()
        meld(ruw.startswith(b"{\\rtf1"), "de installatietekst is echte RTF")
        meld(b"\\ansicpg1252" in ruw, "de RTF is ANSI (cp1252), geen UTF-16")
        meld(b"\\trowd" not in ruw and b"\\pict" not in ruw,
             "geen tabellen of afbeeldingen in de RTF")
        # En geen eigen tekstkleur (28 okt 2026): Jan zag de installatietekst in donkere modus als
        # zwart op zwart, onleesbaar. Inno Setup houdt sinds 6.6.1 expliciet gezette kleuren vast en
        # vervangt alleen de standaardkleur door die van het thema; een `\colortbl` met een donkere
        # kleur maakt de tekst dus onleesbaar in het donker. Zonder kleurenblad tekent het
        # rich-edit-venster de kleur van het thema.
        meld(b"colortbl" not in ruw and b"\\cf1" not in ruw,
             "de RTF zet geen eigen tekstkleur (anders onleesbaar in het donkere thema)")
        # De lezer zelf mag geen pad opeten: `\\astrologie` is een backslash plus letters, geen
        # stuurwoord. Deze regel is de vangnet-controle voor de fout van 28 okt 2026.
        meld(rtf_tekst(rb"{\rtf1 \\astrologie-horoscopen\par}").strip() == "\\astrologie-horoscopen",
             "de RTF-lezer laat een pad met een backslash intact")
        plat = rtf_tekst(ruw)
        mapnaam = os.path.basename(paden.standaardmap())
        meld(mapnaam in plat, "de installatietekst noemt de echte gegevensmap", mapnaam)

    # 4. per gebruiker installeren (besluit 20 okt 2026) en de AppId die nooit mag wijzigen.
    meld("PrivilegesRequired=lowest" in tekst, "installatie per gebruiker (geen UAC)")
    appid = re.search(r"^AppId=(\{\{[0-9A-Fa-f-]{36}\})", tekst, flags=re.M)
    meld(bool(appid), "AppId is een vaste GUID", appid.group(1) if appid else "")

    # 5. de twee dingen die er inhoudelijk in moeten zitten.
    code = tekst.split("[Code]", 1)[-1]
    meld("MB_DEFBUTTON2" in code and "astrologie-horoscopen" in code,
         "de verwijderaar vraagt naar de gegevensmap, met 'nee' als antwoord")

    # 5b. Een update laat geen oude bronzip staan (28 okt 2026). Inno Setup schrijft bij een update bij
    #     in het bestaande verwijderlogboek in plaats van het oude pakket eerst weg te halen, dus wat
    #     uit het pakket verdwijnt blijft op de schijf staan. De bronzip heeft per versie een nieuwe
    #     naam; zonder [InstallDelete] groeit de installatiemap met 6 MB per update.
    meld("[InstallDelete]" in tekst and "{app}\\bron\\*.zip" in tekst,
         "een update ruimt de bronzip van de vorige versie op")
    meld("uitgave\\{#BronZip}" in tekst or "uitgave\\{#BronZip}" in tekst.replace("/", "\\"),
         "de bronzip gaat mee de installatiemap in (AGPL)")

    # 6. geen omgevingsvariabele als Inno-constante (21 okt 2026). De verwijderaar viel bij Jan om
    #    met "Interne fout: unknown constant userprofile": de constante `userprofile` bestaat niet,
    #    het is `{%USERPROFILE}` - met een procentteken leest Inno de omgevingsvariabele. De negen
    #    andere controles keken naar bestanden, naar het nummer en naar de opbouw, nooit naar de
    #    constanten zelf, dus dit kwam er doorheen. Juist de namen die er bijna zo uitzien zijn de
    #    valkuil; `username`, `tmp`, `localappdata` en `app` bestaan wél en staan daarom niet in
    #    deze lijst.
    #
    #    Alleen wat Inno uitvoert telt: de regels buiten [Code] zonder hun `;`-commentaar, en in
    #    [Code] alleen de tekst tussen aanhalingstekens (daar staat de constante die aan
    #    ExpandConstant gegeven wordt). Een uitleg in een commentaarblok mag de naam dus gewoon
    #    noemen - anders zou de uitleg over deze fout de controle zelf laten afgaan.
    voor_code, _, code_deel = tekst.partition("[Code]")
    te_keuren = "\n".join(r for r in voor_code.splitlines() if not r.lstrip().startswith(";"))
    te_keuren += "\n" + "\n".join(re.findall(r"'([^']*)'", code_deel))
    variabelen = ("userprofile", "userhome", "homepath", "homedrive", "appdata",
                  "programfiles", "programdata", "windir", "systemroot", "public")
    gevonden = sorted({n for n in variabelen
                       if re.search(r"\{%s\}" % re.escape(n), te_keuren, flags=re.I)})
    meld(not gevonden, "geen omgevingsvariabele als Inno-constante",
         ("{%s} moet {%%%s} zijn" % (gevonden[0], gevonden[0].upper())) if gevonden else "")
    meld("{%USERPROFILE}" in te_keuren, "de gegevensmap komt uit %USERPROFILE%")

    # 7. commentaar in [Code] zonder accolade-paren (27 okt 2026). Jan kreeg een compileerfout op
    #    een notitie over `{userprofile}`: die sloot zichzelf, want Pascal kent geen geneste
    #    commentaren - de eerste `}` beeindigde het commentaar en de rest werd als code gelezen.
    #    Dit is de fout die geen enkele controle hierboven kon zien: het script is geen bestand
    #    kwijt, het nummer klopt, de constanten zijn goed - en toch compileert het niet.
    problemen = keur_commentaren(code_deel)
    meld(not problemen, "commentaar in [Code] zonder accolade-paren",
         "; ".join("regel %d: %s" % (nr, r) for nr, r in problemen[:3]) if problemen else "")

    # 8. een ontbrekend versie.iss geeft een leesbare melding in plaats van "Cannot open file".
    #    Het bestand staat niet in de repo (het is afgeleid), dus in een verse kopie ontbreekt het.
    meld("#if FileExists(" in tekst and "#error" in tekst,
         "een ontbrekend versie.iss levert een leesbare melding op")

    # 9. één programma tegelijk (28 okt 2026). Bij Jan lukte het installeren van een nieuwe versie
    #    terwijl het programma draaide niet: Inno probeerde het venster te sluiten, dat lukte niet, en
    #    daarna was het programma ook niet meer netjes af te sluiten. Nu maakt de app een mutex en
    #    weigert de installer. Twee dingen kunnen daarbij stil fout gaan: de namen lopen uit elkaar
    #    (dan herkent de installer een draaiend programma nooit) en de regel ontbreekt (dan probeert
    #    Inno alsnog te sluiten). De naam wordt uit `schil/server.py` gelezen, niet hier overgetypt.
    server_pad = os.path.join(PROJECT, "schil", "server.py")
    app_bron = open(server_pad, encoding="utf-8").read() if os.path.isfile(server_pad) else ""
    app_naam = re.search(r'^MUTEX_NAAM\s*=\s*"([^"]+)"', app_bron, flags=re.M)
    iss_naam = re.search(r'^AppMutex=(\S+)\s*$', tekst, flags=re.M)
    meld(bool(app_naam) and bool(iss_naam) and app_naam.group(1) == iss_naam.group(1),
         "de mutexnaam in het script is die van de app",
         "%s (app) vs %s (script)" % (app_naam.group(1) if app_naam else "?",
                                      iss_naam.group(1) if iss_naam else "?"))
    meld("maak_mutex()" in app_bron, "de app maakt de mutex bij het starten")
    meld(re.search(r'^CloseApplications=no\s*$', tekst, flags=re.M) is not None,
         "de installer sluit het draaiende programma niet zelf")
    bericht = re.search(r'^SetupAppRunningError=(.+)$', tekst, flags=re.M)
    meld(bool(bericht) and "Afsluiten" in bericht.group(1) and "Annuleren" in bericht.group(1),
         "de weigering noemt de sluitweg (Bestand > Afsluiten) en de annuleerknop",
         (bericht.group(1).strip()[:60] + "...") if bericht else "(geen eigen regel)")

    print()
    if fout:
        print("Niet in orde: %d van %d controles." % (len(fout), len(goed) + len(fout)))
        return 1
    print("In orde: %d controles geslaagd. (De Pascal-code zelf wordt op Windows gecompileerd.)"
          % len(goed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
