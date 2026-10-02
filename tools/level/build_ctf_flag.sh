#!/usr/bin/env bash
# Build what Capture the Flag needs that the game does not ship
# (docs/ce_map_conversion.md, "Capture the Flag"):
#
# - the flag, objects\weapons\multiplayer\flag\flag: a weapon cloned from the
#   assault bomb, which ships whole (model, physics, carry animations) and is
#   carried the same way, but drawn by the oddball's actor with CE's flag
#   mesh put on it at runtime;
# - an entry for it in the multiplayer object type list
#   (multiplayer\globals): a Megalo script can only create an object of a
#   listed type, and the list ships with 18 weapons and no flag. The flag is
#   entry 18, the `--flag-type` `mjolnir megalo write --mode ctf` defaults to;
# - the flag stand, objects\multi\ctf\flag_stand: invisible scenery with
#   multiplayer properties, as the spawn point is built
#   (build_spawn_point.sh). A level places one per team, labelled
#   `ctf_flag_return`, and its boundary is the capture zone.
#
# - Halo CE's health pack, objects\multi\powerups\health_pack: equipment
#   cloned from the battle rifle ammo pickup (no CE map places one, so its
#   actor is the pack's alone; MJOLNIRLevelLoader puts CE's health pack mesh
#   on it), object type list entry 19, which the Megalo variants create
#   (blam_megalo::powerups) on
# - the health pack spot, objects\multi\powerups\health_pack_spot: invisible
#   scenery as the flag stand is, placed where CE put a health pack and
#   labelled `ce_health_pack`.
#
#   HCE_PAKS=".../Meteorite/Content/Paks" tools/level/build_ctf_flag.sh [out dir]
#
# Writes pakchunk990-MJOLNIRFLAG_P, -STAND_P, -HPACK_P, -HPSPOT_P and
# pakchunk990-MJOLNIRMOTL_P. The object type list names the flag and the pack
# by path, so their containers are installed (a stub .pak beside each) before
# the list is packed; with no out dir, everything goes straight into the Paks
# folder.
set -euo pipefail
out="${1:-$HCE_PAKS}"
mjolnir="${MJOLNIR:-target/release/mjolnir}"
stub_for() {
  local stub
  stub=$(ls "$HCE_PAKS"/pakchunk997-MJOLNIRMAP-*_P.pak 2>/dev/null | head -1)
  [ -n "$stub" ] && [ "$out" = "$HCE_PAKS" ] && cp -f "$stub" "$HCE_PAKS/$1_P.pak"
  return 0
}

# The bomb binds no Unreal asset (nothing ships for it), so the flag borrows
# the oddball's actor: that gives every flag an actor which follows it, and
# MJOLNIRLevelLoader puts CE's flag mesh on it (build_ce_flag_mesh.sh).
# (Git Bash would rewrite the /Game path into a Windows one.)
MSYS2_ARG_CONV_EXCL="/Game" "$mjolnir" new-tag --group weapon --from 'multiplayer/assault_bomb/assault_bomb-weapon' \
  --to 'objects\weapons\multiplayer\flag\flag' \
  --asset-reference /Game/Weapons/Melee/Skull/Blueprints/BP_SkullActor \
  --set 'item.pickup message=' \
  --out-dir "$out" --name pakchunk990-MJOLNIRFLAG
stub_for pakchunk990-MJOLNIRFLAG

"$mjolnir" new-tag --group scenery --from cinematic_anchor \
  --to 'objects\multi\ctf\flag_stand' \
  --graft "object.multiplayer object=weapon:assault_rifle-weapon:item.object.multiplayer object" \
  --set 'object.model=hlmt:objects\props\unsc\unsc_data_pad\unsc_data_pad' \
  --set "object.multiplayer object[0].type=ordinary" \
  --set "object.multiplayer object[0].flags=none" \
  --out-dir "$out" --name pakchunk990-MJOLNIRSTAND
stub_for pakchunk990-MJOLNIRSTAND

"$mjolnir" new-tag --group equipment --from 'battle_rifle_ammo/battle_rifle_ammo-equipment' \
  --to 'objects\multi\powerups\health_pack' \
  --out-dir "$out" --name pakchunk990-MJOLNIRHPACK
stub_for pakchunk990-MJOLNIRHPACK

"$mjolnir" new-tag --group scenery --from cinematic_anchor \
  --to 'objects\multi\powerups\health_pack_spot' \
  --graft "object.multiplayer object=weapon:assault_rifle-weapon:item.object.multiplayer object" \
  --set 'object.model=hlmt:objects\props\unsc\unsc_data_pad\unsc_data_pad' \
  --set "object.multiplayer object[0].type=ordinary" \
  --set "object.multiplayer object[0].flags=none" \
  --out-dir "$out" --name pakchunk990-MJOLNIRHPSPOT
stub_for pakchunk990-MJOLNIRHPSPOT

"$mjolnir" pack --group multiplayer_object_type_list \
  --duplicate 'object types[17]' \
  --duplicate 'object types[18]' \
  --set 'object types[18].name=flag' \
  --set 'object types[18].object=weap:objects\weapons\multiplayer\flag\flag' \
  --set 'object types[19].name=health_pack' \
  --set 'object types[19].object=eqip:objects\multi\powerups\health_pack' \
  --out-dir "$out" --name pakchunk990-MJOLNIRMOTL_P
stub_for pakchunk990-MJOLNIRMOTL
