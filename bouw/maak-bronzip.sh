#!/usr/bin/env bash
# De bronzip die naast de .exe hoort.
#
# Het programma staat onder de AGPL-3.0, en de Over-tab in het programma zegt het ook: "de
# broncode wordt meegeleverd bij iedere verspreiding". Deze zip maakt dat waar. Maak hem van
# dezelfde commit als waarmee de .exe gebouwd is - niet van de werkmap, want daarin kan van
# alles tussendoor staan.
#
# Gebruik:   bash bouw/maak-bronzip.sh [commit]
# Uitvoer:   uitgave/astrologie-studio-bron-<datum>-<korte commit>.zip  + de sha256
set -euo pipefail

cd "$(dirname "$0")/.."
ref="${1:-HEAD}"

if [ -n "$(git status --porcelain)" ]; then
    echo "LET OP: de werkmap is niet schoon. De zip komt uit $ref, niet uit wat er nu ligt:"
    git status --short | sed 's/^/    /'
    echo
fi

kort=$(git rev-parse --short "$ref")
datum=$(git log -1 --format=%cd --date=format:%Y-%m-%d "$ref")
volledig=$(git rev-parse "$ref")
naam="astrologie-studio-bron-${datum}-${kort}.zip"

mkdir -p uitgave
git archive --format=zip --prefix="astrologie-studio-${kort}/" -o "uitgave/$naam" "$ref"

sha=$(sha256sum "uitgave/$naam" | cut -d' ' -f1)
grootte=$(du -h "uitgave/$naam" | cut -f1)

echo "bronzip:  uitgave/$naam  ($grootte)"
echo "commit:   $kort  ($volledig)"
echo "sha256:   $sha"
echo
echo "Leg deze zip naast de .exe. Wie het programma krijgt, hoort beide te krijgen - dat is wat"
echo "de AGPL-3.0 vraagt en wat de Over-tab belooft. Zet de sha256 in je begeleidende bericht,"
echo "dan kan de ontvanger controleren dat hij heeft gekregen wat er is gemaakt."
