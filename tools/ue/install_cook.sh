#!/usr/bin/env bash
# Copy the Meteorite cook project's chunk 988 container (our materials and
# textures) into the game as pakchunk988-MJOLNIRMAT, and chunk 981 (the Halo 2
# masters, Scripts/build_h2_materials.py) as pakchunk981-MJOLNIRH2 when it was
# cooked. The game must be closed: it keeps mounted containers open.
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
if [ -f "$src/pakchunk981-Windows.utoc" ]; then
  for e in pak utoc ucas; do
    cp -f "$src/pakchunk981-Windows.$e" "$HCE_PAKS/pakchunk981-MJOLNIRH2-Windows.$e"
  done
  echo "installed pakchunk981-MJOLNIRH2 ($(stat -c %s "$src/pakchunk981-Windows.ucas") bytes)"
fi
