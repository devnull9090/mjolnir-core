#!/usr/bin/env bash
# Convert a classic Halo CE map into a standalone multiplayer map for Halo:
# Campaign Evolved, in one command.
#
#   HCE_PAKS=".../Meteorite/Content/Paks" \
#     tools/level/convert_ce_map.sh <map.map | halo2ue staging dir> <CODE> <out dir> [--install]
#
#   CODE   three characters, the new scenario's codename (e.g. BGL)
#
# Steps, each a tool of its own:
#
#   1. halo2ue-export (HalcyonRing/tools/halo2ue) stages the .map: collision,
#      placements, netgame flags. Skipped when given a staging directory.
#   2. mjolnir level collision --own-bsp builds the structure BSP from the CE
#      collision alone (docs/ce_terrain_collision.md): the tree in the world
#      shell and in one instance, and the static Havok body over its surfaces.
#   3. The terrain mesh (docs/ue_mesh_write.md): the staged render geometry
#      written into /Engine/BasicShapes/Cylinder in the game's own
#      serialisation, as an override container (pakchunk989-MJOLNIRMESH),
#      with its lightmap UVs, bump tangents and incident radiosity directions.
#      Its materials are real ones (docs/ce_map_conversion.md, "Materials"):
#      tools/level/ce_material_spec.py lists every (shader, lightmap page),
#      the Unreal project unreal/MJOLNIRMaterials imports the CE bitmaps and lightmaps,
#      the cook ships them with its CE shader_environment masters as
#      pakchunk988-MJOLNIRMAT, and the level loader makes a dynamic instance
#      of a master per mesh slot with that entry's textures and parameters. Without the Unreal editor (CE_COOK=0) it falls
#      back to tools/level/ce_textures.py, one composited texture per shader
#      on a runtime material, overriding the shipped cylinder (one such map
#      at a time).
#   4. tools/level/gen_ce_level.py writes the level file: player spawn points,
#      vehicles, weapons and pickups through defs/level/ce-tag-map.json, the
#      map variant palette, the zone set trimmed to the map's own BSP, the
#      terrain decor, and "multiplayer": true.
#   5. mjolnir level bake --standalone CODE --bsp 8=... bakes the scenario and
#      its registration.
#   6. tools/level/build_spawn_point.sh builds the spawn-point and
#      teleporter scenery the level places (shared by every converted map).
#
# Maps install side by side: each has its own scenario, world and mesh
# containers, and the registration container (pakchunk996-MJOLNIRREG_P) is
# rebuilt from every installed map's record (MJOLNIRLevelLoader/registry).
#
# The map gets an empty Unreal world of its own (level bake --world), renamed
# to its codename: defs/level/empty_world.umap, the MapKit's bare world
# (unreal/MJOLNIRMapKit; any /X/X world package renames). WORLD=<.umap> picks
# another; WORLD=none keeps the canvas mission's world. It needs
# MJOLNIRLevelLoader's native half to resolve the world by name.
#
# With --install the containers go straight into the game's Paks folder and
# the level file into MJOLNIRLevelLoader's levels folder; the loader's native
# half then starts the map under the Megalo engine
# (docs/re/megalo_engine.md).
set -euo pipefail

if [ $# -lt 3 ]; then
  sed -n '2,43p' "$0"
  exit 2
fi
src="$1"
code="$2"
out="$3"
install="${4:-}"
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
mjolnir="${MJOLNIR:-$repo/target/release/mjolnir}"
examples="${MJOLNIR_EXAMPLES:-$repo/target/release/examples}"
# For sections no CE shader texture covers: shipped, world-projected (the
# terrain is normalised into the donor and scaled back up ~440x at spawn, so a
# UV-mapped material with its own textures stretches into a mirror sheet).
terrain_material="${TERRAIN_MATERIAL:-/Game/Env/Bio/Rock/Canyon/Materials/MI_Rock_Canyon_Generic}"
# The parent of every runtime material: a shipped instance that samples one
# colour texture ("Diffuse") and one normal map ("Normal") on UV0 and nothing
# else, from the synchronisation-test prototypes nothing in the game places.
texture_parent="${TEXTURE_PARENT:-/Game/_Prototypes/SynchronizationTestContent/Assets/weapons/dmr/M_dmr_Inst.M_dmr_Inst}"
exporter="${HALO2UE_EXPORT:-$HOME/prj/HalcyonRing/tools/halo2ue/exporter/target/release/halo2ue-export}"
: "${HCE_PAKS:?set HCE_PAKS to Meteorite/Content/Paks in the game install}"

if [ "${#code}" -ne 3 ]; then
  echo "CODE must be exactly three characters (the scenario rename is same-length surgery)" >&2
  exit 2
fi
mkdir -p "$out"

if [ -d "$src" ]; then
  staging="$src"
else
  staging="$out/staging"
  echo "== 1/6 staging $src"
  "$exporter" --map "$src" --out "$staging"
fi
name="$(basename "$(cd "$staging" && pwd)")"
[ "$name" = "staging" ] && name="$(basename "$src" .map)"
# Custom maps carry spaces and capitals ("Yoyorast Island V2.map"); the name
# becomes file and asset names, so it is kept to [a-z0-9_].
name="$(printf '%s' "$name" | tr 'A-Z ' 'a-z_' | tr -cd 'a-z0-9_')"

collision="$staging/bsp/collision_0.json"
if [ -e "$staging/bsp/collision_1.json" ]; then
  echo "note: $name has more than one BSP; only BSP 0 is converted" >&2
fi

echo "== 2/6 collision"
# The scenery's collision models (rocks, trees), as surfaces the Havok MOPP
# covers, and the surface materials: grass split from sand and dirt, a
# material for each piece of scenery (tools/level/merge_ce_collision.py).
python "$here/merge_ce_collision.py" "$staging" "$out/collision_scene.json"
collision="$out/collision_scene.json"
# DELTA="dx dy dz" moves the whole map (CE world units), for a map whose own
# coordinates fall outside the canvas's space.
delta_args=()
[ -n "${DELTA:-}" ] && delta_args=(--delta $DELTA)
# The map's BSP is its scenario's only one (BSP 0); the bake trims the
# canvas's others away (blam.single_bsp). CANVAS_BSPS=1 keeps them all.
bsp_args=(--bsp-index 0)
[ "${CANVAS_BSPS:-0}" = "1" ] && bsp_args=()
"$mjolnir" level collision "$collision" --out "$out/$name.sbsp" --own-bsp "${bsp_args[@]}" "${delta_args[@]}"

echo "== 3/6 terrain mesh and materials"
delta="$(python -c "import json,sys; d=json.load(open(sys.argv[1]))['delta']; print(f'{d[0]*304.8},{-d[1]*304.8},{d[2]*304.8}')" "$out/$name.sbsp.transform.json")"
ue_editor="C:/Program Files/Epic Games/UE_5.5/Engine/Binaries/Win64/UnrealEditor-Cmd.exe"
cook="${CE_COOK:-$([ -x "$ue_editor" ] && echo 1 || echo 0)}"
if [ "$cook" = "1" ]; then
  # The scenery the scenario places and the sky join the BSP's sections
  # (tools/level/merge_ce_scene.py); the transparent ones (sky, lights,
  # teleporter fields) are a mesh of their own, because a rewritten mesh
  # enters Unreal's translucency pass only through its single donor slot.
  # The sky is a mesh of its own: kilometres across, it cost the map's
  # transparent pieces their precision when they shared one.
  python "$here/merge_ce_scene.py" "$staging" "$out/scene.gltf" --translucent "$out/scene_translucent.gltf" \
    --sky "$out/scene_sky.gltf"
  # What the lightmaps leave out, one texture per lightmap page
  # (crates/ue-texture lightmap_bake): the corners' ambient occlusion and
  # where CE's sun reaches, traced against the merged scene. The masters
  # darken the corners with the one and keep object shadows to the sunlit
  # ground with the other; gen_ce_level.py measures the lightmap's shadow and
  # sun levels against it.
  page0="$(python -c "import json,sys; p=json.load(open(sys.argv[1]))['bsps'][0].get('lightmap_pages') or ['']; print(p[0])" "$staging/manifest.json")"
  page0="${page0%%[[:space:]]}"
  if [ -n "$page0" ] && [ -x "$examples/lightmap_bake" -o -x "$examples/lightmap_bake.exe" ]; then
    "$examples/lightmap_bake" "$out/scene.gltf" "$staging/textures/$page0" "$out/bake" --ao-rays 64 | sed 's/ -> .*//'
  fi
  # One material per glTF material, i.e. per (shader, lightmap page).
  python "$here/ce_material_spec.py" --code "$code" --bake "$out/bake" "$staging" "$name" "$out/materials.spec.json" \
    "$out/scene_sky.gltf" "$out/scene_translucent.gltf" "$out/scene.gltf"
  # The three meshes, packages of the map's own beside its materials
  # (<root>/SM_<map>_Terrain, _Translucent and _Sky), built from the shipped
  # cylinder, cone and sphere, in one container per map.
  root="$(python -c "import json,sys; print(json.load(open(sys.argv[1]))['root'])" "$out/materials.spec.json")"
  root="${root%%[[:space:]]}"   # Windows Python ends its lines with CRLF
  leaf="${root##*/}"
  MSYS2_ARG_CONV_EXCL="/Game" python "$here/build_terrain_meshes.py" --paks "$HCE_PAKS" \
    --spec "$out/materials.spec.json" --out "$out" --name "$name" --offset "$delta" \
    --fallback "$terrain_material" --examples "$examples" \
    --container "pakchunk986-MJOLNIRMESH-${code}_P" \
    "$out/scene.gltf=basicshapes/cylinder=$root/SM_${leaf}_Terrain" \
    "$out/scene_translucent.gltf=basicshapes/cone=$root/SM_${leaf}_Translucent" \
    "$out/scene_sky.gltf=basicshapes/sphere=$root/SM_${leaf}_Sky"
else
  python "$here/ce_textures.py" "$staging" "$out/textures/$name" --prefix "textures/$name" | tail -1
  # One slot per composited shader, keyed on the glTF material names
  # (`<shader>__lm<N>`, so `cap_ramp__` never claims `cap_ramp_blue__lm0`);
  # anything left over keeps slot 0 and the fallback material.
  slots=()
  while IFS= read -r shader; do
    shader="${shader%%[[:space:]]*}"   # Windows Python ends its lines with CRLF
    slots+=(--material "slot:$shader=$texture_parent=${shader}__")
  done < <(python -c "import json,sys; [print(e['shader']) for e in json.load(open(sys.argv[1]))]" "$out/textures/$name/materials.json")
  # mesh_rewrite reads defs/ue/*.usmap relative to the repository root.
  (cd "$repo" && MSYS2_ARG_CONV_EXCL="slot:;Terrain=" "$examples/mesh_rewrite" "$HCE_PAKS" basicshapes/cylinder "$staging/bsp/bsp_0.gltf" "$out/terrain.uasset"   --offset "$delta" --material "Terrain=$terrain_material=*" "${slots[@]}") | tee "$out/terrain.log" | grep -E "SPAWN|MATCHES|world box|slot 0"
  "$examples/package_override" "$HCE_PAKS" basicshapes/cylinder "$out/terrain.uasset" "$out" | grep -E "verify|wrote"
  # Object paths go through the environment, excluded from Git Bash's habit
  # of rewriting anything that starts with "/" into a Windows path.
  MSYS2_ENV_CONV_EXCL="FALLBACK;PARENT" FALLBACK="$terrain_material" PARENT="$texture_parent" python - "$out/terrain.log" "$out/terrain.json" "$name" "$out" <<'PY'
# The spawn transform as mesh_rewrite printed it, and one material per slot:
# slot 0 the fallback, then a runtime material per composited shader.
import json, os, re, sys
log, out, name, work = sys.argv[1:]
fallback, parent = os.environ["FALLBACK"], os.environ["PARENT"]
text = open(log).read()
m = re.search(r"SPAWN: location \(([-\d.]+), ([-\d.]+), ([-\d.]+)\) cm, uniform scale ([\d.]+)", text)
x, y, z, s = map(float, m.groups())
leaf = fallback.rsplit("/", 1)[-1]
materials = [f"{fallback}.{leaf}"]
for e in json.load(open(os.path.join(work, "textures", name, "materials.json"))):
    materials.append({
        "parent": parent,
        "textures": {"Diffuse": e["diffuse"], "Normal": "/Engine/EngineMaterials/FlatNormal.FlatNormal"},
        "shader": e["shader"],
    })
json.dump({"id": f"{name}_terrain", "mesh": "/Engine/BasicShapes/Cylinder.Cylinder",
           "pos": [x, y, z], "scale": [s, s, s], "materials": materials},
          open(out, "w"), indent=2)
PY
fi
if [ "$cook" = "1" ]; then
  # The materials: masters (once per project, cheap to redo), this level's
  # bitmaps and instances, then the cook. Every converted level built so far
  # stays in the project, so one container carries them all.
  ue="$repo/tools/ue"
  powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$ue/editor_cmd.ps1")" -Script Scripts/build_ce_materials.py | head -1
  MJ_CE_SPEC="$(cygpath -w "$out/materials.spec.json")" powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$ue/editor_cmd.ps1")" -Script Scripts/build_ce_level.py | grep -E "editor exit|MJOLNIR CE level"
  # The ambient sound (sound scenery and the BSP's background loops), from
  # the CE map and sounds.map beside it, imported beside the materials.
  sounds_map="${SOUNDS_MAP:-$(dirname "$src")/sounds.map}"
  if [ -f "$src" ] && [ -f "$sounds_map" ]; then
    python "$here/ce_sounds.py" "$src" "$sounds_map" "$staging" "$out/sounds_out"
    # The sound root is an object path: kept out of Git Bash's rewriting of
    # "/"-led environment values into Windows paths (C:/Program Files/Git/Game/...).
    MSYS2_ENV_CONV_EXCL="MJ_CE_SOUND_ROOT" MJ_CE_SOUNDS="$(cygpath -w "$out/sounds_out")" MJ_CE_SOUND_ROOT="/Game/MJOLNIR/Maps/$code/Sounds"       powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$ue/editor_cmd.ps1")" -Script Scripts/build_ce_sounds.py | grep -E "editor exit|MJOLNIR CE sounds"
  fi
  powershell -NoProfile -ExecutionPolicy Bypass -File "$(cygpath -w "$ue/cook.ps1")"
  # The map's own packages (/Game/MJOLNIR/Maps/<CODE>: its textures and
  # ambient sounds) cook into a chunk of their own (ce_material_spec.py
  # cook_chunk), which its map pack ships as MJOLNIRCOOK-<CODE>
  # (docs/map_distribution.md).
  chunk="$(python -c "import json,sys; print(json.load(open(sys.argv[1]))['chunk'])" "$out/materials.spec.json")"
  chunk="${chunk%%[[:space:]]}"
  staged="$repo/unreal/MJOLNIRMaterials/Saved/StagedBuilds/Windows/Meteorite/Content/Paks"
  for e in utoc ucas; do
    cp -f "$staged/pakchunk${chunk}-Windows.$e" "$out/pakchunk985-MJOLNIRCOOK-${code}_P.$e"
  done
  echo "  cooked   pakchunk${chunk} -> pakchunk985-MJOLNIRCOOK-${code}_P"
fi

echo "== 4/6 level file"
sound_args=()
[ -f "$out/sounds_out/sounds.json" ] && sound_args=(--sounds "$out/sounds_out")
# TITLE="Yoyorast Island" names a custom map in the menus (stock maps have
# theirs in gen_ce_level.py).
title_args=()
[ -n "${TITLE:-}" ] && title_args=(--title "$TITLE")
python "$here/gen_ce_level.py" "$staging" "$out/$name.sbsp.transform.json" "$out/$name.level.json"   --name "$name" --code "$code" --terrain "$out/terrain.json" "${sound_args[@]}" "${title_args[@]}"

echo "== 5/6 bake"
bake=("$mjolnir" level bake "$out/$name.level.json" --standalone "$code" --bsp "8=$out/$name.sbsp" --out-dir "$out")
world="${WORLD:-$repo/defs/level/empty_world.umap}"
[ "$world" != "none" ] && bake+=(--world "$world")
[ "$install" = "--install" ] && bake+=(--install-test)
"${bake[@]}"

echo "== 6/6 spawn points and teleporters"
if [ "$install" = "--install" ]; then
  MJOLNIR="$mjolnir" "$here/build_spawn_point.sh" "$HCE_PAKS"
  # A stub .pak sibling is what makes the game mount a .utoc/.ucas pair.
  stub="$HCE_PAKS/pakchunk997-MJOLNIRMAP-${code}_P.pak"
  for c in pakchunk994-MJOLNIRSPAWN pakchunk993-MJOLNIRTELES pakchunk992-MJOLNIRTELER pakchunk991-MJOLNIRTELE2; do
    cp -f "$stub" "$HCE_PAKS/${c}_P.pak"
  done
  # The terrain meshes: with the cooked materials, the map's own packages
  # (986, one container per map, so maps install side by side); without,
  # an override of the shipped cylinder (989).
  for c in "pakchunk986-MJOLNIRMESH-${code}_P" "pakchunk985-MJOLNIRCOOK-${code}_P" pakchunk989-MJOLNIRMESH-Windows_P; do
    [ -e "$out/$c.utoc" ] || continue
    cp -f "$out/$c.utoc" "$out/$c.ucas" "$HCE_PAKS"/
    cp -f "$stub" "$HCE_PAKS/$c.pak"
  done
  if [ "$cook" = "1" ]; then
    # Shipped-shape overrides from older conversions would replace the
    # cylinder and cone everywhere.
    rm -f "$HCE_PAKS"/pakchunk989-MJOLNIRMESH-Windows_P.* "$HCE_PAKS"/pakchunk987-MJOLNIRMESHT-Windows_P.*
  fi
  loader="$HCE_PAKS/../../Binaries/Win64/ue4ss/Mods/MJOLNIRLevelLoader"
  if [ "$cook" = "1" ]; then
    # The cooked materials and textures (pakchunk988-MJOLNIRMAT).
    "$repo/tools/ue/install_cook.sh"
  else
    # The composited shader textures the level's runtime materials read.
    [ -n "$name" ] && rm -rf -- "${loader:?}/textures/$name"
    mkdir -p "$loader/textures"
    cp -r "$out/textures/$name" "$loader/textures/$name"
  fi
  # The game mode the level names ("variant": "slayer"); MJOLNIRLevelLoader
  # hands it to the simulation's variant loader when the map starts.
  variants="$HCE_PAKS/../../Binaries/Win64/ue4ss/Mods/MJOLNIRLevelLoader/variants"
  mkdir -p "$variants"
  "$mjolnir" megalo write --mode slayer --score "${SCORE:-25}" --out "$variants/slayer.mglo"
else
  MJOLNIR="$mjolnir" "$here/build_spawn_point.sh" "$out"
  "$mjolnir" megalo write --mode slayer --score "${SCORE:-25}" --out "$out/slayer.mglo"
fi
echo "done: $out"
