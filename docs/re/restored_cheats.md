# Restored cheats

**Build:** CU4 (`HaloSimulation_tag_release.dll`, Steam and Xbox app)
**Date:** 2026-11-01
**Code:** `native/blam_console/mjolnir_blam_console.c`, section *Restored cheats*

## Summary

The release simulation DLL keeps 425 HS functions in its table with their
names and parameter lists, but points their evaluators at one shared stub
(`0x1b2430`: `hs_return(thread, 0)`) — see [`../blam_console.md`](../blam_console.md).
The console DLL now points three of them back at evaluators of its own:

| Function | Index | What it does now |
|---|---:|---|
| `cheat_all_weapons` | 333 | drops every loaded weapon (up to 20) in an arc 2 units in front of the player |
| `cheat_all_vehicles` | 334 | the same for vehicles, 8 units out |
| `drop_safe <tag>` | 339 | drops one object tag 2 units in front of the player |

The patch is one pointer per function, the `evaluate` field (`+0x20`) of the
function's definition in `.rdata`. It is made only when the definition has
the expected name and still points at the stub. Because the evaluator runs
inside HS evaluation on the simulation thread, the functions work from the
console, from `blam (...)` lines and from scripts alike.

## Where the bodies came from

Each MCC engine was checked for the same three names (definition at
`ptr-to-name − 8` for Reach-lineage tables, then the evaluator's sharing
count):

| DLL | `cheat_all_weapons` evaluator |
|---|---|
| CE `HaloSimulation_tag_release.dll` | stub `0x1b2430` (425 of 1,695 functions per `mjolnir console`) |
| MCC `haloreach.dll` | stub `0x86cbc`, shared by about 587 definitions |
| MCC `halo3.dll` | stub `0x1065f4`, shared by about 389 |
| MCC `halo1.dll` | **its own** (`0xb1ffc4`); the definition layout differs (name at +0) |
| MCC `halo4.dll` | no pointer to the name literal; layout not resolved |

The MCC counts come from a quick scratch scan whose name filter misses some
definitions (it found 1,674 of CE's 1,695), so they are approximate. Only
Halo 1 kept a body. `0xb1ffc4` is the usual wrapper
(`call body; hs_return(thread, 0)`); the body `0xb21794` takes the globals
tag's cheat-weapon block if it has entries, otherwise iterates loaded tags of
group `'weap'` (`0x77656170`) up to 16, and hands the list to the drop routine
`0xb21e84`. That matches `cheats.c` in the punpckhdq decomp. None of the H1
code transfers to CE (different lineage); the recipe does. CE's `matg` has no
cheat-weapon block, so only the iteration is used.

## The CE building blocks

All of them are live in CU4 and are what the Forge editor's become-monitor
(`0x3054f0`) uses to create the monitor ([`forge_engine.md`](forge_engine.md)).

| Piece | RVA | Notes |
|---|---:|---|
| function table | `0x81ba20` | definitions: `+0x08` name, `+0x20` evaluate, `+0x38` count, `+0x3a` types |
| `hs_return` | `0x1fe100` | `(thread, value)` |
| `hs_arguments_evaluate` | `0x1feca0` | `(thread, count, types, initialize)` → `int32*`, NULL while still evaluating |
| evaluator shape | | `(short function, int thread, bool initialize)` |
| `object_placement_data_new` | `0x5ee570` | `(placement, tag, owner -1, 0)`; clears 0x330 bytes; position at `+0x1c`, forward `+0x28`, up `+0x34` |
| `object_get_origin` | `0x5a6780` | `(object, float[3])` |
| `object_new` | `0x5a0fc0` | `(placement)` → object, -1 on failure |
| unit facing | object data `+0x204` | 3 floats |
| tag table | `0x182d1e8` | entry `+0` generation, `+4` group, `+0x10` path; handle = `generation << 16 \| index` |

`drop_safe`'s `any_tag` argument arrives as a tag handle, but a path such as
`objects\weapons\rifle\assault_rifle\assault_rifle` is shared by the weapon,
its model and more, so the evaluator swaps a non-object tag for the object tag
of the same path.

The tag table holds vehicle parts in the same groups: the Pelican's chin gun
is a `weap` and a `vehi`, each Warthog gun a `vehi`, a Jackal's shield and a
Skirmisher's bracers `weap`s, the tuning fork's turret a `vehi`. The first
build dropped them all; picking up the chin gun gave an unnamed weapon with
infinite ammo. Weapons are now limited to `objects\weapons\` minus the shields
and bracers, and vehicles to
`objects\vehicles\` without a `\weapons\`, `\attachments\` or `\turrets\`
segment.

## Verified

2026-11-01, Steam CU4, B30 (The Silent Cartographer), solo, PC 1:

- `status.txt` read `cheats=3/3` once installed.
- `drop_safe objects\weapons\rifle\assault_rifle\assault_rifle` created an
  assault rifle next to the player (`mjolnir live objects --group weap`).
- `cheat_all_weapons` created every loaded weapon in an arc; they render on
  the sand with their pickup markers, and walking up to one and holding E
  picked it up, replacing the magnum. What it picked up was a vehicle's gun
  (`NONAME WEAPON`, infinite ammo), which is what led to the filter below.
- `cheat_all_vehicles` created a Pelican and a Warthog beside the player.
- With the path filter (second launch, same spot): `cheat_all_weapons` gave
  20 weapons, all real ones — assault rifle, SMG, battle rifle, magnum, shotgun,
  sniper, rocket launcher, plasma and needle rifles, concussion rifle, spike
  rifle, energy sword, flak cannon, plasma launcher, beam rifle and more (the
  20 cap was hit, so a level with more loaded weapons drops the first 20 by
  slot). The oddball skull and the skirmisher bracers count as weapons too.
  `cheat_all_vehicles` gave the Pelican, a Warthog, the tuning fork (which
  spawned 10 units under the sand and was gone a moment later) and its turret.
- Third launch, with the `\turrets\` rule and the count message: the console
  answered `dropped 20 of 25 loaded weapons (the first by tag slot)` and
  `dropped 3 of 3 loaded vehicles` (no turret). Holding E on a dropped weapon
  picked it up: the live object list showed it parented to the player's unit.
  It was `skirmisher_bracers`, a Skirmisher's AI melee item with no proper
  first-person view, so the bracers were filtered out afterwards; that last
  rule has only been compiled.
- These ran through the native mailbox (`request.txt` + `mjolnir_blam_pump`),
  not Kismet `ExecuteConsoleCommand`.

Not tested: multiplayer. `object_new` on the host should replicate as Forge
objects do, but nothing has been tried on a client, and a client running the
cheat would create objects only in its own simulation.

## After a game update

Every RVA above sits with the console DLL's other `#define`s and is covered
by its PE-timestamp check. `mjolnir console` re-derives the function table
and the stub; the rest come from `0x3054f0` (find it from the Forge notes)
and from any live one-argument evaluator (`objects_delete_by_definition`
shows `hs_arguments_evaluate` and `hs_return`). `defs/hce/console.json` still
says `stub: true` for these three, because it is read from the file on disk;
the Lua mod clears the flag for them.
