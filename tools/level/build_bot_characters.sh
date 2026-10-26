#!/usr/bin/env bash
# Build the AI characters bots use (docs/bots.md):
#
#   objects\characters\ai\mjolnir_bot_generic_<level>          the base its level's bots inherit
#   objects\characters\spartans\ai\mjolnir_bot_spartan_<level> the Marine's AI in the players' Spartan body
#   objects\characters\elite\ai\mjolnir_bot_elite_<level>
#   objects\characters\grunt\ai\mjolnir_bot_grunt_<level>
#   objects\characters\jackal\ai\mjolnir_bot_jackal_<level>
#
# for <level> normal, heroic and legendary: the host's BOT DIFFICULTY.
#
#   HCE_PAKS=".../Meteorite/Content/Paks" tools/level/build_bot_characters.sh [out dir]
#
# Accuracy: AI take theirs from per-weapon "accuracy bounds" and "accuracy
# time" for normal, heroic and legendary. A Megalo match always plays at
# Normal (the simulation's difficulty reads are gated to campaign and
# Firefight), so each level's characters carry that level's values in their
# Normal slots: mjolnir_bot_generic_<level> is ai\generic so tuned, and each
# bot character is a clone of its kind's character with that parent and its
# own weapon entries tuned the same way. Normal keeps the shipped values.
#
# Spartan: no Spartan AI character ships, so the Marine's character
# (objects\characters\marine\ai\trooper: human weapons, grenades, cover) is
# pointed at the players' own biped, objects\characters\spartans\spartans.
# Marines are on the human team, so a map's bot kind sets `team` (covenant).
#
# The results are mod containers, pakchunk995-MJOLNIRBOT-<kind>-<level>_P, that every
# machine in a match with bots needs beside the map's.
set -euo pipefail

: "${HCE_PAKS:?set HCE_PAKS to Meteorite/Content/Paks in the game install}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
mjolnir="${MJOLNIR:-$repo/target/release/mjolnir}"
out="${1:-$HCE_PAKS}"
work="$(mktemp -d)"
trap 'rm -r "$work"' EXIT

# The --set lines that copy a character's accuracy for difficulty $2 (heroic,
# legendary) into its normal slots, one pair per weapon entry it has; none for
# normal.
level_sets() {
    [ "$2" = normal ] && return 0
    "$mjolnir" values --group character --tag "$1" --json --elements 200 > "$work/donor.json"
    python - "$work/donor.json" "$2" <<'PY'
import json, sys
level = sys.argv[2]
fields = {f["name"]: f for f in json.load(open(sys.argv[1]))["fields"]}
for i, e in enumerate(fields["weapons properties"].get("children", [])):
    v = {f["name"]: f.get("value") for f in e["children"]}
    print(f"weapons properties[{i}].normal accuracy bounds={v[level + ' accuracy bounds']}")
    print(f"weapons properties[{i}].normal accuracy time={v[level + ' accuracy time']}")
PY
}

# name, level, donor (a path substring), new path, extra --set arguments
build() {
    local name="$1" level="$2" donor="$3" to="$4"
    shift 4
    level_sets "$donor" "$level" > "$work/$name.sets"
    "$mjolnir" new-tag --group character --from "$donor" --to "$to" \
        --set-file "$work/$name.sets" "$@" \
        --out-dir "$out" --name "pakchunk995-MJOLNIRBOT-$name"
}

for level in normal heroic legendary; do
    generic="objects\characters\ai\mjolnir_bot_generic_$level"
    build "generic-$level" "$level" "ai/generic-character" "$generic"
    build "spartan-$level" "$level" "marine/ai/trooper-character" \
        "objects\characters\spartans\ai\mjolnir_bot_spartan_$level" \
        --set 'unit=bipd:objects\characters\spartans\spartans' --set "parent character=char:$generic"
    build "elite-$level" "$level" "Elite/ai/elite-character" \
        "objects\characters\elite\ai\mjolnir_bot_elite_$level" --set "parent character=char:$generic"
    build "grunt-$level" "$level" "grunt/ai/grunt-character" \
        "objects\characters\grunt\ai\mjolnir_bot_grunt_$level" --set "parent character=char:$generic"
    build "jackal-$level" "$level" "Jackal/ai/jackal-character" \
        "objects\characters\jackal\ai\mjolnir_bot_jackal_$level" --set "parent character=char:$generic"
done
