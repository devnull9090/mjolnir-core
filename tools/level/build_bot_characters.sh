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

# The --set lines that give a character the vitality of a body's model: the
# players' Spartan, so a Spartan bot takes the hits a player takes and its
# shield comes back as theirs does. The Marine's character, the Spartan bot's
# donor, has no shield (0) and a body that regenerates, which the players'
# model does not. A character's vitality block overrides its unit's model for
# an AI unit, so the model's damage info is copied into it: body = maximum
# vitality; shield = maximum shield vitality; delay = the shield's stun time
# less a second (below); recharge = its recharge time. The same numbers go in the normal and
# legendary slots: a player's body is the same at every difficulty. $1 is a
# model path substring.
vitality_sets() {
    "$mjolnir" values --group model --tag "$1" --json --elements 1 --depth 6 > "$work/model.json"
    python - "$work/model.json" <<'PY'
import json, sys
fields = {f["name"]: f for f in json.load(open(sys.argv[1]))["fields"]}

def child(f, name):
    for c in f.get("children", []):
        if c.get("name") == name:
            return c
    raise SystemExit(f"model has no {name!r}")

def value(f, name):
    return float(child(f, name)["value"])

info = fields["new damage info"]["children"][0]
body, shield = child(info, "body"), child(info, "shield")
body_max = value(body, "maximum vitality")
shield_max = value(shield, "maximum shield vitality")
delay = value(shield, "stun time")
recharge = value(shield, "recharge time")
if shield_max <= 0 or recharge <= 0:
    raise SystemExit("the model has no shield to copy")
v = "vitality properties[0]."
for slot in ("normal", "legendary"):
    print(f"{v}{slot} body vitality={body_max}")
    print(f"{v}{slot} shield vitality={shield_max}")
# A player's shield starts back a second before the model's stun time says:
# measured 2026-11-21 on Blood Gulch, a player and a bot damaged by the same
# command, frame for frame alike with the bot's delay at stun - 1 (6 s for
# stun 7) and a second late at 7. The rate (1 / recharge time) matched as is.
# Where the player's second goes is not known; no globals or trait field
# holds a shield delay for Megalo.
print(f"{v}shield recharge delay time={max(0.0, delay - 1.0)}")
print(f"{v}shield recharge time={recharge}")
print(f"{v}runtime_shield_recharge_velocity={1.0 / recharge}")
# A player's body does not heal on its own (the model's body recharge never
# comes: stun 999); health packs do that.
print(f"{v}body recharge fraction=0")
print(f"{v}body recharge delay time=0")
print(f"{v}body recharge time=0")
print(f"{v}runtime_body_recharge_velocity=0")
PY
}

# name, level, donor (a path substring), new path, extra --set arguments
build() {
    local name="$1" level="$2" donor="$3" to="$4"
    shift 4
    level_sets "$donor" "$level" > "$work/$name.sets"
    # More --set lines for this character alone (new-tag takes one file).
    if [ -n "${EXTRA_SETS:-}" ]; then cat "$EXTRA_SETS" >> "$work/$name.sets"; fi
    "$mjolnir" new-tag --group character --from "$donor" --to "$to" \
        --set-file "$work/$name.sets" "$@" \
        --out-dir "$out" --name "pakchunk995-MJOLNIRBOT-$name"
}

spartan_body='objects\characters\spartans\spartans'
# The players' biped's model (its `model` reference), by asset path: values
# matches tags by that, case and all.
vitality_sets "characters/Spartans/spartans-model" > "$work/spartan-vitality.sets"

for level in normal heroic legendary; do
    generic="objects\characters\ai\mjolnir_bot_generic_$level"
    build "generic-$level" "$level" "ai/generic-character" "$generic"
    EXTRA_SETS="$work/spartan-vitality.sets" build "spartan-$level" "$level" "marine/ai/trooper-character" \
        "objects\characters\spartans\ai\mjolnir_bot_spartan_$level" \
        --set "unit=bipd:$spartan_body" --set "parent character=char:$generic"
    build "elite-$level" "$level" "Elite/ai/elite-character" \
        "objects\characters\elite\ai\mjolnir_bot_elite_$level" --set "parent character=char:$generic"
    build "grunt-$level" "$level" "grunt/ai/grunt-character" \
        "objects\characters\grunt\ai\mjolnir_bot_grunt_$level" --set "parent character=char:$generic"
    build "jackal-$level" "$level" "Jackal/ai/jackal-character" \
        "objects\characters\jackal\ai\mjolnir_bot_jackal_$level" --set "parent character=char:$generic"
done
