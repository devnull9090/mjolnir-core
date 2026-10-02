#!/usr/bin/env bash
# Build the multiplayer scenery a converted map places: the spawn point at its
# player starts (objects\multi\spawning\player_spawn) and the two ends of a
# teleporter at its teleporter flags (objects\multi\teleporters\
# teleporter_sender and teleporter_receiver).
#
#   HCE_PAKS=".../Meteorite/Content/Paks" tools/level/build_spawn_point.sh [out dir]
#
# Under the multiplayer (Megalo) engine players spawn only at scenery whose
# multiplayer object type is "player spawn location" (15), and a first spawn
# needs the "valid initial player spawn" flag (docs/re/megalo_engine.md). No
# such scenery ships, so this builds one:
#
# - from objects\cinematics\cinematic_anchor, which binds no Unreal asset
#   (no AssetReference) and so draws nothing;
# - with the assault rifle's multiplayer object block grafted in and retyped;
# - with its Blam model pointed at the data pad's, because the map variant
#   skips an object whose model does not resolve, and that model has no
#   collision.
#
# The teleporters are built the same way, typed "teleporter sender" (13) and
# "teleporter receiver" (14): the simulation keeps Reach's multiplayer
# teleporters, which move what enters a sender's boundary to a receiver on the
# same teleporter channel. The channel and boundary are set per placement
# (tools/level/gen_ce_level.py, from the CE teleporter flags).
#
# The results are mod containers to install beside the map's:
# pakchunk994-MJOLNIRSPAWN_P, pakchunk993-MJOLNIRTELES_P (sender) and
# pakchunk992-MJOLNIRTELER_P (receiver).
set -euo pipefail
out="${1:-.}"
mjolnir="${MJOLNIR:-target/release/mjolnir}"
"$mjolnir" new-tag --group scenery --from cinematic_anchor \
  --to 'objects\multi\spawning\player_spawn' \
  --graft "object.multiplayer object=weapon:assault_rifle-weapon:item.object.multiplayer object" \
  --set 'object.model=hlmt:objects\props\unsc\unsc_data_pad\unsc_data_pad' \
  --set "object.multiplayer object[0].type=player spawn location" \
  --set "object.multiplayer object[0].flags=valid initial player spawn" \
  --out-dir "$out" --name pakchunk994-MJOLNIRSPAWN

for end in sender:TELES:993 receiver:TELER:992; do
  IFS=: read -r kind tag chunk <<<"$end"
  "$mjolnir" new-tag --group scenery --from cinematic_anchor \
    --to "objects\\multi\\teleporters\\teleporter_$kind" \
    --graft "object.multiplayer object=weapon:assault_rifle-weapon:item.object.multiplayer object" \
    --set 'object.model=hlmt:objects\props\unsc\unsc_data_pad\unsc_data_pad' \
    --set "object.multiplayer object[0].type=teleporter $kind" \
    --set "object.multiplayer object[0].flags=none" \
    --out-dir "$out" --name "pakchunk$chunk-MJOLNIR$tag"
done
