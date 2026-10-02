#!/usr/bin/env bash
# Build the CE runtime pack's containers: everything converted maps share
# (docs/map_distribution.md, "The CE runtime pack").
#
#   HCE_PAKS=".../Meteorite/Content/Paks" \
#     tools/level/build_ce_runtime.sh <folder of CE .maps> <out dir>
#
# The folder needs bloodgulch.map (for the CTF flag's model and textures) and
# sounds.map (for the announcer and event sounds). Writes into <out dir>:
#
#   pakchunk988-MJOLNIRMAT-Windows   the CE material masters and their shader
#                                    library, the cooked CTF flag textures, the
#                                    event sounds (one cook of
#                                    unreal/MJOLNIRMaterials, chunk 988)
#   pakchunk984-MJOLNIRUI-Windows    the multiplayer screens and HUD widgets
#                                    (Scripts/build_mjolnir_ui.py, same cook,
#                                    chunk 984; docs/custom_ui.md)
#   pakchunk990-MJOLNIRCTFMESH_P     the CE flag mesh (/Game/MJOLNIR/CTF)
#   pakchunk990-MJOLNIRFLAG_P, -STAND_P, -MOTL_P   the CTF flag, its stand,
#                                    and the object type list that adds it
#                                    (build_ctf_flag.sh)
#   pakchunk994-MJOLNIRSPAWN_P, 993-MJOLNIRTELES_P, 992-MJOLNIRTELER_P
#                                    spawn point and teleporter scenery
#                                    (build_spawn_point.sh)
#   pakchunk985-MJOLNIRMENU_P        the main menu with its own MULTIPLAYER
#                                    button, which opens the lobby in chunk 984
#                                    (`mjolnir ue menu-button`; rebuild after
#                                    every game update: it replaces the menu)
#
# Every map converted into the same Unreal project also cooks into chunk 988
# when it predates per-map chunks (/Game/MJOLNIR/Levels); a map with a code of
# its own (/Game/MJOLNIR/Maps/<CODE>) cooks into its own chunk and stays out
# of this pack.
set -euo pipefail
maps="$1"
out="$2"
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
mjolnir="${MJOLNIR:-$repo/target/release/mjolnir}"
examples="${MJOLNIR_EXAMPLES:-$repo/target/release/examples}"
exporter="${HALO2UE_EXPORT:-$HOME/prj/HalcyonRing/tools/halo2ue/exporter/target/release/halo2ue-export}"
ue="$repo/tools/ue"
: "${HCE_PAKS:?set HCE_PAKS to Meteorite/Content/Paks in the game install}"
mkdir -p "$out"

echo "== 1/5 the CTF flag model and textures"
staging="$out/flag_staging"
[ -d "$staging/models" ] || "$exporter" --map "$maps/bloodgulch.map" --out "$staging" --no-collision > "$out/flag_staging.log"
python "$here/ce_flag_textures.py" "$staging" "$out/ctf_textures"

echo "== 2/5 the event sounds"
python "$here/ce_sounds.py" --events "$maps/sounds.map" "$out/events"

echo "== 3/5 masters, flag textures and event sounds (chunk 988) and the UI (chunk 984)"
run() { powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$ue/editor_cmd.ps1")" -Script "$1" | grep -E "editor exit|MJOLNIR"; }
run Scripts/build_ce_materials.py
MSYS2_ENV_CONV_EXCL="MJ_CE_TEXTURE_ROOT" MJ_CE_TEXTURES="$(cygpath -w "$out/ctf_textures")" \
  MJ_CE_TEXTURE_ROOT="/Game/MJOLNIR/CE/CTF" run Scripts/build_ce_textures.py
MSYS2_ENV_CONV_EXCL="MJ_CE_SOUND_ROOT" MJ_CE_SOUNDS="$(cygpath -w "$out/events")" \
  MJ_CE_SOUND_ROOT="/Game/MJOLNIR/Sounds/Events" run Scripts/build_ce_sounds.py
run Scripts/build_mjolnir_ui.py
powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$ue/cook.ps1")"
staged="$repo/unreal/MJOLNIRMaterials/Saved/StagedBuilds/Windows/Meteorite/Content/Paks"
for e in utoc ucas; do
  cp -f "$staged/pakchunk988-Windows.$e" "$out/pakchunk988-MJOLNIRMAT-Windows.$e"
  cp -f "$staged/pakchunk984-Windows.$e" "$out/pakchunk984-MJOLNIRUI-Windows.$e"
done

echo "== 4/5 the flag mesh"
# CE's flag model, rewritten into a package of our own (docs/ue_mesh_write.md).
# The loader attaches it to each flag actor at the transform mesh_rewrite
# prints (gen_ce_level.py FLAG_MESH).
material=/Game/MJOLNIR/CE/M_CE_EnvironmentMaskedTwoSided
mkdir -p "$out/mesh"
(cd "$repo" && MSYS2_ARG_CONV_EXCL="/Game;s_" "$examples/mesh_rewrite" "$HCE_PAKS" basicshapes/cylinder \
  "$staging/models/weapons_flag_flag__weap.gltf" "$out/mesh/SM_CE_Flag.uasset" --offset 0,0,0 \
  --rename /Game/MJOLNIR/CTF/SM_CE_Flag \
  --material "s_blade=$material=flag_blade|*" --material "s_metal=$material=flag_brightmetal" \
  --material "s_handle=$material=flag_handle") | grep -E "SPAWN|MATCHES"
MSYS2_ARG_CONV_EXCL="/Game" "$examples/package_add" "$HCE_PAKS" "$(cygpath -m "$out")" \
  --name pakchunk990-MJOLNIRCTFMESH_P \
  --package "/Game/MJOLNIR/CTF/SM_CE_Flag=$(cygpath -m "$out/mesh/SM_CE_Flag.uasset")" | tail -1
# CE's health pack, which the loader puts on the pack's actor the same way
# (gen_ce_level.py HEALTH_PACK_MESH).
(cd "$repo" && MSYS2_ARG_CONV_EXCL="/Game;s_" "$examples/mesh_rewrite" "$HCE_PAKS" basicshapes/cylinder \
  "$staging/models/powerups_health_pack__eqip.gltf" "$out/mesh/SM_CE_HealthPack.uasset" --offset 0,0,0 \
  --rename /Game/MJOLNIR/CE/Powerups/SM_CE_HealthPack \
  --material "s_pack=$material=healthpack|*") | grep -E "SPAWN|MATCHES"
MSYS2_ARG_CONV_EXCL="/Game" "$examples/package_add" "$HCE_PAKS" "$(cygpath -m "$out")" \
  --name pakchunk990-MJOLNIRHPMESH_P \
  --package "/Game/MJOLNIR/CE/Powerups/SM_CE_HealthPack=$(cygpath -m "$out/mesh/SM_CE_HealthPack.uasset")" | tail -1

echo "== 5/5 the multiplayer scenery, the CTF tags and the main menu's MULTIPLAYER button"
MJOLNIR="$mjolnir" "$here/build_spawn_point.sh" "$out" > "$out/spawn_point.log"
MJOLNIR="$mjolnir" "$here/build_ctf_flag.sh" "$out" > "$out/ctf_flag.log"
"$mjolnir" ue menu-button --out-dir "$(cygpath -m "$out")" | tail -1
rm -f "$out"/*.pak
ls "$out"/*.utoc
echo "done: $out"
echo "package it: mjolnir map runtime $out --version <x.y.z> --sign"
