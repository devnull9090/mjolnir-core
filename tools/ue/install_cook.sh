#!/usr/bin/env bash
# Copy the Meteorite cook project's chunk 988 container (our materials and
# textures) into the game as pakchunk988-MJOLNIRMAT. The game must be closed:
# it keeps mounted containers open.
#
#   HCE_PAKS=".../Meteorite/Content/Paks" tools/ue/install_cook.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
src="$here/../../unreal/MJOLNIRMaterials/Saved/StagedBuilds/Windows/Meteorite/Content/Paks"
: "${HCE_PAKS:?set HCE_PAKS to Meteorite/Content/Paks in the game install}"
for e in pak utoc ucas; do
  cp -f "$src/pakchunk988-Windows.$e" "$HCE_PAKS/pakchunk988-MJOLNIRMAT-Windows.$e"
done
cmp -s "$src/pakchunk988-Windows.ucas" "$HCE_PAKS/pakchunk988-MJOLNIRMAT-Windows.ucas"
echo "installed pakchunk988-MJOLNIRMAT ($(stat -c %s "$src/pakchunk988-Windows.ucas") bytes)"
