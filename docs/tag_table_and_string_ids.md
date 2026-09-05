# The simulation's tag table and string-id registry

**Build:** `2026.08.11.1121610.2-Rel-i343-Meteorite-2607-CU4` (Steam)
**Date:** 2026-09-05
**Code:** `crates/blam-live/src/tagtable.rs`, `crates/blam-live/src/stringid.rs`,
`crates/blam-live/examples/tagtable_probe.rs`, `mjolnir live`

`HaloSimulation_tag_release.dll` keeps two tables that answer, without a memory sweep, the
two questions live mode has always had to ask: which tags are loaded and where each one's root
element is, and which `string id` names the running game knows. Both hang off globals in the
module. This note records where they are on the current build, how they are laid out, and what
was measured against them in the running game. It supersedes the sweep-first account in
[`live_tag_locating.md`](live_tag_locating.md).

## Summary

| Question | Answer on CU4 |
|---|---|
| Where is every loaded tag's root? | the `tag instance` table, pointer at tag-DLL RVA `0x0182D1E8`; 7,055 tags in A30, every root resolving, bytes matching the shipped tag |
| Which string ids does the game know? | the registry at RVA `0x013574C0`; 64,293 names in A30, dumped to `defs/hce/string-ids.json` |
| Does `tag_is_active` say whether a tag is loaded? | **no** — it returns `false` for a loaded weapon; the HS compiler's `not a loaded tag` error does |
| Do `tag_reload_force` / `tag_load_force` do anything? | **reload works** and relocates the tag; load-force is inert |
| Is there a debug menu behind `DebugMenuSettings`? | yes, a pause-menu panel "Show Tag Debug Names" plus a type legend; its overlay does not render in the shipping build |

## The tag table — pointer-chase, no scan

Two globals, RVAs into `HaloSimulation_tag_release.dll` (hash `C8C14440…3BF7`, `build_lock.md`):

| Global | RVA | What it holds here |
|---|---:|---|
| tag table pointer | `0x0182D1E8` | pointer to a table object whose header begins with the ASCII label `tag instance` |
| segment table | `0x02C2CCC0` | 16 × u64 segment bases; segments 1, 14 and 15 were populated (14 is inside the DLL image itself) |

Table object: `+0x20` element size (`0x30`), `+0x2c` maximum (32,767), `+0x44` high-water,
`+0x48` used, `+0x50` entry array, `+0x58` allocation bitset. At the frontend the table is empty;
in A30 it held **7,055 tags** (E10: 6,054). Per 0x30-byte entry: `+0x00` u16 salt, `+0x04`
big-endian group four-CC, `+0x10` pointer to the NUL-terminated tag path (`objects\weapons\rifle\
assault_rifle\assault_rifle`, backslashes, no extension), `+0x18` the root block descriptor
`{count, encoded data offset, encoded definition offset}`. The handle a tag reference holds in
the resident copy is `salt << 16 | index`.

An encoded offset is `segment = enc >> 28`, `address = segment_base + enc * 4`. This is the
`arena + 4 * words` rule `blam-live` had been deriving per tag (`live_tag_locating.md`), with
the missing half: the arena *is* a segment base, and the top nibble names which. Root data sat
in segment 1, root definitions in segment 14 (the DLL's own static definition tables).

Cross-check against the shipped tag (`mjolnir data --group weapon --tag 'assault_rifle\assault_rifle'`):
the live root's first 12 bytes and the scalars at `+492` (`flags` `00 04 00 00`), `+496`
(`secondary flags` `80 02 00 00`) and `+584` (`heat warning threshold` `1.0`) are byte-identical
to the file. Every one of the 7,055 entries had a resolvable root address.

**Consequence:** the 13 GB census sweep is no longer needed to answer "what is loaded" or "where
is this tag's root". `mjolnir live tags` lists the table; `poke` and the tag editor's live mode
read it first and keep the sweep for a build without a profile.

## The string-id registry

Six globals, all resolving:

| Global | RVA | Value in A30 |
|---|---:|---|
| storage (name bytes) | `0x01357490` | pointer; `used` = 4,004,392 bytes |
| storage used | `0x01357498` | u64 |
| strings (per-id `char*` table) | `0x013574A0` | `[0]=""`, `[1]="default"`, `[2]="reload_1"` |
| count | `0x013574A8` | 64,293 (2,678 at the frontend) |
| mapping hash table | `0x013574C0` | header `buckets 1,046,528 · max 523,264 · value size 4`; buckets at `+0x38` (8 bytes each), nodes `0x1c` bytes: key u64 `+0`, next `+0x10`, storage offset u32 `+0x18` |
| builtin table | `0x0082F0A0` | 2,678 × 16 bytes: u32 id, `char*` at `+8` |

Walking every chain yielded 64,293 `(id, name)` pairs (chains of at most 3) with all 2,678
builtin ids present; `fork_d = 0x1677`, `warthog_d = 0x17D2`. The 62,683 ids in set 0 equal
`1068 + (64,293 - 2,678)`: the builtin ids carry set bits in the high half, every later
registration is sequential from 1068. Names register as tags load, so one mission's set is a
lower bound for another's. The dump is the novel-string-id validator this project lacked (see
`iostore_packaging.md`, *a string-id hazard*): a mod may reference a string id only if the
running build registers it. It is committed as `defs/hce/string-ids.json`; `mjolnir live
string-ids --find <name>` asks the running game directly.

## The console's tag commands

`defs/hce/console.json` (CU4) lists `tag_is_active`, `tag_load_force`, `tag_unload_force` and
`tag_reload_force` as **live** functions (flags 4) and `dump_loaded_tags` as a stub.
`mods/MJOLNIRBlamConsole` reaches them. Measured in A30:

| Command | Result |
|---|---|
| `tag_is_active objects\weapons\rifle\assault_rifle\assault_rifle.weapon` | compiles; returns **false** although the tag is in the tag table |
| same path without `.weapon`, or with forward slashes | compiler error `not a loaded tag (at character 15)` |
| `tag_is_active levels\halo1\solo\b40\b40.scenario` (not loaded in A30) | compiler error `not a loaded tag` |
| `tag_reload_force objects\weapons\rifle\assault_rifle\assault_rifle.weapon` | `ok`; the tag's root data moved from `0x238F7E5E640` to `0x239108DF900`, same handle `0xE24A00D6`, same bytes |
| `tag_load_force objects\vehicles\covenant\ghost\ghost.vehicle` (Ghost is not loaded in A30) | `ok`, but the tag table stayed at 7,055 entries and the compile oracle still said `not a loaded tag` two probes later |

So the **HS compiler's tag-literal resolution is a loaded-tag oracle**: a tag literal
(`<path>.<group>`, backslashes) compiles only when the tag is in the loaded set. `tag_is_active`
itself answers `false` for a loaded, in-use weapon, so "active" means something other than
"loaded". The tag table walk is the better oracle anyway: exact, instant, no console needed.

`tag_load_force` has no observable effect in the release build: `console.json` gives it and
`tag_unload_force` the same evaluator address (`0x1b1bb0`), distinct from the shared stub, so it
is most likely a second "accept a string, do nothing" body.

`tag_reload_force` is real and live: the tag was re-read and re-relocated in place, its handle
unchanged. That is the primitive a hot-reload needs; what it re-reads is the mounted container,
which the game holds open, so feeding it new bytes is the open question. It is also why a
remembered root address must be re-verified against the tag's own scalars before a write.

## The debug menu

The settings object `/Script/Meteorite.Default__DebugMenuSettings` exists in A30 with three
`*Shipping` flags `false` and three `*NonShipping` flags `true`; setting the Shipping flags
`true` at runtime changed nothing visible in the pause menu, so the gate is not re-read there.
The widget itself is already instantiated: `W_BlamDebugMenu` (class `UBlamDebugMenuWidget`,
Blueprint `/Game/_Prototypes/SynchronizationTestContent/Widgets/W_BlamDebugMenu`) sits collapsed
inside `WBP_PauseMenu`'s overlay. Forcing it visible (`SetVisibility(4)`) draws a small
**"Debug Menu · Show Tag Debug Names"** checkbox and a **"Tag Types"** legend of twelve coloured
checkboxes (biped, control, crate, creature, effect scenery, equipment, giant, machine,
projectile, scenery, vehicle, weapon) — `W_BlamGameStateObjectDebugMenu`. It is an in-world
tag-name overlay, not a command console. Calling `SetShowTagDebugNames(true, [0..11])` on the
live widget succeeds and ticks every type, but no label appears over any object in A30 — the
overlay's drawing is compiled out of the shipping build along with the rest of the debug draw.

## A brand-new tag package loads by name

Measured 2026-09-05, same session. `mjolnir new-tag` cloned the marine's collision model under
a path the game never shipped — `/Game/Tags/objects/characters/marinf/marinf-collision_model`,
same-length rename surgery on the donor's wrapper, the body untouched — into its own `_P`
container carrying its own `ContainerHeader` (`blam_pack::build_addition`), and `mjolnir pack`
repointed the marine `model` tag's `collision model` reference at
`objects\characters\marinf\marinf`. No import-map change anywhere: nothing declares the new
package as a dependency.

After a relaunch into A30 the table held **7,056** tags, one more than before, and slot 21 was
`coll objects\characters\marinf\marinf`, allocated right after the marine's `model` (slot 20).
The model's resident root reads its collision reference as
`'coll' · name pointer · 0x20 · 0xE1890015` — the new tag's handle. The game played normally.

So, for tags:

- the runtime tag registry is **enumerated from the mounted containers**, not a fixed list;
- a mod container's **own** `ContainerHeader` registers its packages — the store reads it;
- a tag reference resolves by **name**, on demand, with no hard import required;
- a tag reference in the resident copy is `{group four-CC, pointer to the path, path length,
  handle}`.

This is the door the new-scenario work found closed for `scenario` packages
(`new-scenario-door-open`): the refusal there is specific to how a scenario is opened, not to
new packages as such.

## Adding a build

The RVAs above belong to one tag module. On a game update: hash the new
`HaloSimulation_tag_release.dll`, re-measure the eight globals (the label `tag instance` at the
table object and the registry header `00f80f00 00fc0700 04000000` are the anchors to confirm
against), and add a `Profile` in `crates/blam-live/src/tagtable.rs`. Until then the sweep runs.
