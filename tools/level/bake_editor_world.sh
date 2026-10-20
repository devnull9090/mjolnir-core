#!/usr/bin/env bash
# Bake a converted map with a world authored in the editor (a Landscape, say)
# in place of the bare MapKit world.
#
#   tools/level/bake_editor_world.sh <world package> <chunk> <level.json> <sbsp> <CODE> <out dir>
#   e.g. /Game/Levels/Halo1/Solo/LTS/LTS 979 .../deathisland.level.json .../deathisland.sbsp DTI out/
#
# The world is cooked first by unreal/MJOLNIRMaterials (tools/ue/cook.ps1
# -Map <world package>, its folder labelled for <chunk>). This takes it out
# of the staged container, re-encodes its properties in the game's layout
# (ue-asset's retarget: stock-cooked components are misread otherwise, see
# unreal/MJOLNIRMapKit/README.md) and bakes the map around it
# (`mjolnir level bake --standalone CODE --world`). Writes to <out dir>:
#
#   pakchunk997-MJOLNIRMAP-<CODE>_P.utoc/.ucas   the map, with the world
#   pakchunk<chunk>-MJOLNIRLAND-Windows.*         the staged container as is:
#                                                 the shader library of the
#                                                 world's own materials
#
# Install both (game closed): the shader library is opened by the pakchunk
# number in the container's name, so the second keeps <chunk>.
#
# MJOLNIR (the CLI) and EXAMPLES (a cargo target dir's examples, with
# extract_file and retarget_package built) default to this checkout's.
set -euo pipefail
if [ $# -lt 6 ]; then
  sed -n '2,25p' "$0"
  exit 2
fi
pkg="$1" chunk="$2" level="$3" sbsp="$4" code="$5" out="$6"
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
mjolnir="${MJOLNIR:-$repo/target/release/mjolnir}"
examples="${EXAMPLES:-$repo/target/debug/examples}"
: "${HCE_PAKS:?set HCE_PAKS to Meteorite/Content/Paks in the game install}"
staged="$repo/unreal/MJOLNIRMaterials/Saved/StagedBuilds/Windows/Meteorite/Content/Paks"
leaf="${pkg##*/}"
rel="${pkg#/Game/}"

mkdir -p "$out/staged"
for e in utoc ucas; do
  cp -f "$staged/pakchunk$chunk-Windows.$e" "$out/staged/"
done
cp -f "$staged/global.utoc" "$staged/global.ucas" "$out/staged/"
"$examples/extract_file" "$out/staged" "$rel.umap" "$out/$leaf.stock.umap"
ubulk=0
if "$examples/extract_file" "$out/staged" "$rel.ubulk" "$out/$leaf.ubulk" 2>/dev/null; then ubulk=1; fi
"$examples/retarget_package" "$out/staged" "$repo/defs/ue/UE-5.5-stock.usmap" \
  "$repo/defs/ue/Meteorite-2607-CU3.usmap" "$out/$leaf.stock.umap" "$out/$leaf.umap" | grep -v "^export .*kept$" || true
# The bake reads the bulk data beside the world, by the same stem.
[ "$ubulk" = 1 ] || rm -f "$out/$leaf.ubulk"
"$mjolnir" level bake "$level" --paks "$HCE_PAKS" --standalone "$code" --bsp "8=$sbsp" --out-dir "$out" \
  --world "$out/$leaf.umap" | grep -E "world|wrote.*997|rror"
stub="$HCE_PAKS/pakchunk115-Windows.pak"
for e in utoc ucas; do
  cp -f "$out/staged/pakchunk$chunk-Windows.$e" "$out/pakchunk$chunk-MJOLNIRLAND-Windows.$e"
done
cp -f "$stub" "$out/pakchunk$chunk-MJOLNIRLAND-Windows.pak"
echo "done: $out/pakchunk997-MJOLNIRMAP-${code}_P.* and $out/pakchunk$chunk-MJOLNIRLAND-Windows.*"
