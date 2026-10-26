#!/usr/bin/env bash
# Build the AI characters bots use (docs/bots.md):
#
#   objects\characters\ai\mjolnir_bot_generic          the base every bot inherits
#   objects\characters\spartans\ai\mjolnir_bot_spartan the Marine's AI in the players' Spartan body
#   objects\characters\elite\ai\mjolnir_bot_elite
#   objects\characters\grunt\ai\mjolnir_bot_grunt
#   objects\characters\jackal\ai\mjolnir_bot_jackal
#
#   HCE_PAKS=".../Meteorite/Content/Paks" tools/level/build_bot_characters.sh [out dir]
#
# Accuracy: AI take theirs from per-weapon "accuracy bounds" and "accuracy
# time" for normal, heroic and legendary. A Megalo match always plays at
# Normal (the simulation's difficulty reads are gated to campaign and
# Firefight), so every bot character carries the Legendary values in its
# Normal slots: mjolnir_bot_generic is ai\generic so tuned, and each bot
# character is a clone of its kind's character with that parent and its own
# weapon entries tuned the same way.
#
# Spartan: no Spartan AI character ships, so the Marine's character
# (objects\characters\marine\ai\trooper: human weapons, grenades, cover) is
# pointed at the players' own biped, objects\characters\spartans\spartans.
# Marines are on the human team, so a map's bot kind sets `team` (covenant).
#
# The results are mod containers, pakchunk995-MJOLNIRBOT-<name>_P, that every
# machine in a match with bots needs beside the map's.
set -euo pipefail

: "${HCE_PAKS:?set HCE_PAKS to Meteorite/Content/Paks in the game install}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
mjolnir="${MJOLNIR:-$repo/target/release/mjolnir}"
out="${1:-$HCE_PAKS}"
work="$(mktemp -d)"
trap 'rm -r "$work"' EXIT

# The --set lines that copy a character's legendary accuracy into its normal
# slots, one per weapon entry it has.
legendary_sets() {
    "$mjolnir" values --group character --tag "$1" --json --elements 200 > "$work/donor.json"
    python - "$work/donor.json" <<'PY'
import json, sys
fields = {f["name"]: f for f in json.load(open(sys.argv[1]))["fields"]}
for i, e in enumerate(fields["weapons properties"].get("children", [])):
    v = {f["name"]: f.get("value") for f in e["children"]}
    print(f"weapons properties[{i}].normal accuracy bounds={v['legendary accuracy bounds']}")
    print(f"weapons properties[{i}].normal accuracy time={v['legendary accuracy time']}")
PY
}

# name, donor (a path substring), new path, extra --set arguments
build() {
    local name="$1" donor="$2" to="$3"
    shift 3
    legendary_sets "$donor" > "$work/$name.sets"
    "$mjolnir" new-tag --group character --from "$donor" --to "$to" \
        --set-file "$work/$name.sets" "$@" \
        --out-dir "$out" --name "pakchunk995-MJOLNIRBOT-$name"
}

generic='objects\characters\ai\mjolnir_bot_generic'
build generic "ai/generic-character" "$generic"
build spartan "marine/ai/trooper-character" 'objects\characters\spartans\ai\mjolnir_bot_spartan' \
    --set 'unit=bipd:objects\characters\spartans\spartans' --set "parent character=char:$generic"
build elite "Elite/ai/elite-character" 'objects\characters\elite\ai\mjolnir_bot_elite' \
    --set "parent character=char:$generic"
build grunt "grunt/ai/grunt-character" 'objects\characters\grunt\ai\mjolnir_bot_grunt' \
    --set "parent character=char:$generic"
build jackal "Jackal/ai/jackal-character" 'objects\characters\jackal\ai\mjolnir_bot_jackal' \
    --set "parent character=char:$generic"
