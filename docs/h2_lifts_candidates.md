# Halo 2 lifts: candidate packs, 2026-11-04

Nothing here is tagged or published. The packs wait for an in-game test and
a go-ahead.

Candidates: `C:/haloce/ce_conversions/h2/lifts_packs/<slug>-1.3.0.mjolnir`,
signed, built by `tools/level/add_lifts.py` from the 1.2.0 packs in
`C:/haloce/ce_conversions/bots/packs_v3`.

## What changed

Only `map/level.json`, which gains `lifts`. The script stops unless every
other file in the pack matches 1.2.0 by CRC, the rest of the level file is
unchanged, and the manifest differs only in its version. So the scenario and
`map/bots.json` are the 1.2.0 ones, and the runtime range stays `^1.16.0`.

No map was reconverted. `lifts` is read only by the loader, and a reconvert
would have replaced the bot-baked scenario. Each shipped level file was
byte-identical to its `ce_conversions/h2/batch2/<CODE>` conversion, so the
transforms are the ones the maps were built with.

## Results by map

"Entered" counts phantoms the host was inside on PC 1, with the loader
pushing. The host was flown in by script, so most entries were not from a
lift's normal way in.

| Map | Code | Phantoms | Entered | Seen |
| --- | --- | --- | --- | --- |
| Lockout | LOK | 2 | 2 | Full ride from the foot: about 12.3 m/s, out onto the upper floor |
| Ascension | ASC | 1 | 1 | Jump pad: about 32 m/s, 3.7 s arc |
| Gemini | GEM | 1 | 1 | Jump pad: about 7 m up, repeats while standing on it |
| Colossus | COL | 1 | 1 | About 21 m straight up |
| Desolation | DSL | 2 | 2 | Both team lifts throw the host up and out |
| Relic | RLC | 2 | 2 | Watchtower lift and pod |
| Midship | MID | 5 | 4 | Power lifts and pillar lifts |
| Ivory Tower | IVT | 6 | 5 | Vents push |
| Warlock | WLK | 4 | 3 | Lifts drop the host on the deck above |
| Foundation | FND | 8 | 4 | Vents push |
| Backwash | BWS | 12 | 4 | `hvac_lift_short` only; `backwash_lift` not reached (test script stopped on its own error) |
| Tombstone | TBS | 2 | 1 | Vent pushes |
| Coagulation | COA | 4 | 0 | Not reached: lifts are inside the bases |
| Headlong | HDL | 4 | 0 | Not reached: steam lifts are enclosed |

Total: 30 of 54 phantoms, on 12 of 14 maps.

These 11 maps have no phantom that pushes players, so they get no new pack:
Beaver Creek, Burial Mounds, Containment, District, Elongation, Sanctuary,
Terminal, Turf, Uplift, Waterworks, Zanzibar. That matches the census in
`docs/h2_map_conversion.md`.

## Not tested

- **A joiner riding a real lift on two PCs.** Not run; the user asked to
  leave PC 2 alone. PR #241's box stays unticked.
- **Bots with the 1.3.0 files, other than on Lockout.** Lockout ran on its
  installed 1.2.0 hub containers with the candidate level file, and other
  bipeds were active in that match. The other 13 maps ran on PC 1's older test
  installs of the same conversions, with the candidate level file in the
  loader's `levels/` folder.
- **A 1.3.0 pack installed as a pack.** Only level files were swapped; no
  pack went through the launcher.
- **The hub scan.** `hub/src/lib/api/scan.ts` was read, not run: it needs
  `map/level.json` to be valid JSON and does not restrict its keys.
- **Against MCC.** Speeds and heights were not compared with Halo 2.
- **Full vent rides.** Only Lockout was ridden from the foot. Vent shafts were
  entered near the top, so a walk-in from the bottom is still to check.

## What to try in game

Walk into Coagulation's and Headlong's lifts, a Backwash `backwash_lift`, and
one vent from its bottom. Check that Gemini's and Ascension's pads feel right
against MCC.

## PC 1 state

All 14 level files are restored. Backups:
`C:/haloce/install_backup/h2-lifts-20261104/<CODE>/level.json`.
