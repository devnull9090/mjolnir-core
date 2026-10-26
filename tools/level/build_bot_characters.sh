#!/usr/bin/env bash
# Build the AI characters bots use that the game does not ship (docs/bots.md):
# the Spartan bot, objects\characters\spartans\ai\mjolnir_bot_spartan.
#
#   HCE_PAKS=".../Meteorite/Content/Paks" tools/level/build_bot_characters.sh [out dir]
#
# The only Spartan AI character that ships is a stimuli variant, so this clones
# the Marine's character (objects\characters\marine\ai\trooper: human weapons,
# grenades, cover) and points its unit at the players' own biped,
# objects\characters\spartans\spartans. A map's `blam.bots.types` entry names
# it as `character`; the bake adds it to the scenario's character palette.
# Marines are on the human team, so that entry also sets a `team` (covenant)
# for the bots to fight the players.
#
# The result is a mod container, pakchunk995-MJOLNIRBOTCHAR_P, that every
# machine in a match with Spartan bots needs beside the map's.
set -euo pipefail

: "${HCE_PAKS:?set HCE_PAKS to Meteorite/Content/Paks in the game install}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
mjolnir="${MJOLNIR:-$repo/target/release/mjolnir}"
out="${1:-$HCE_PAKS}"

"$mjolnir" new-tag --group character --from "marine/ai/trooper-character" \
  --to 'objects\characters\spartans\ai\mjolnir_bot_spartan' \
  --set 'unit=bipd:objects\characters\spartans\spartans' \
  --out-dir "$out" --name pakchunk995-MJOLNIRBOTCHAR
