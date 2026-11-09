# Pushing players from the simulation thread (Halo 2 lifts)

**Build:** CU4 (`HaloSimulation_tag_release.dll`, TimeDateStamp `0x6a7a740a`)
**Date:** 2026-11-08
**Code:** `native/lobby/lifts_core.h`, `native/lobby/lifts_runtime.h`,
`mods/MJOLNIRLevelLoader/Scripts/lifts.lua`

## Summary

Halo 2's gravity lifts, jump pads and vents (#235) push players through
phantoms the conversion writes into the level file (`lifts`). Until
MJOLNIRLobby 0.25.0 the Lua side found each local Spartan through UE4SS
every 50 ms near a lift and wrote an `object_set_velocity` line to a file for
the lobby DLL to run on the next simulation tick. Now the DLL does the whole
push on the simulation thread, once per tick: everything it needs is in the
simulation's own tables, and the only engine call is `object_set_velocity`'s
own body. Lua hands over the phantoms, in simulation units, when they
change.

## What the push reads

All of it hangs off the simulation thread's TLS block (the tag module's own
TLS slot; [game_state_reader.md](../game_state_reader.md) has the walk and
the data-array header).

| Where | What | How it is known |
|---|---|---|
| TLS `+0x30` | players data array, `0x4B0` a player | game_state_reader.md |
| player `+0x00` | salt (0 = free slot) | game_state_reader.md |
| player `+0x28` | the unit the player controls, a handle (`-1` none) | game_state_reader.md, `player_get` |
| TLS `+0x118` | the player-to-local-user map | below |
| map `+0x34 + 4p` | player p's input user, 0–3; `-1` when no local user controls it | below |
| map `+0x74 + 4p` | player p's output user, likewise | below |
| TLS `+0x20` | object table (`0x18` an entry: salt `+0`, type `+4`, datum size `+6`, own index `+0xC`, datum `+0x10`) | game_state_reader.md |
| object `+0x14` | parent object handle, `-1` when free | game_state_reader.md |
| object `+0x44` | position, world units; the parent's frame when attached | game_state_reader.md, the teleport tooling |
| object `+0x50`, `+0x5C` | forward and up unit vectors | game_state_reader.md, `object_set_velocity` below |
| object `+0x68` | translational velocity, **world units per second, world frame** | `object_set_velocity` below |
| TLS `+0x98` | time globals: `+6` ticks a second (i16), `+0x0C` the tick (i32) | the Forge doors (`forge_doors_tick`) |
| TLS `+0x60` | game globals: `+0` 0 and `+1` 1 while a game runs, `+0x18` the game instance | `fade_in_tick` |

**The local-user map.** Forge's per-player input loop (sim `0x302260`) skips
a player whose `+0x74 + 4p` entry is `-1`, and reads its input user from
`+0x34 + 4p`; the Forge DLL takes "local user 0" from the same `+0x34` array.
A player of another machine has no local user, so its entries are `-1`.
The lift push takes a player as this game's own when its input user is 0–3:
the old Lua pushed exactly the Spartans whose pawn was locally controlled
(splitscreen guests included), and a push the host sends a joiner's unit does
nothing (two PCs, 2026-10-25).

## `object_set_velocity`

The four-argument definition (`object`, three `real`s) sits at `.rdata`
`0x818f68`; its evaluator (`0x1b64f0`) reads the arguments and calls
`0x663b90(object, forward, left, up)`, which:

1. takes the object's forward `F` (`+0x50`) and up `U` (`+0x5C`);
2. writes `forward·F + left·(U × F) + up·U` to `+0x68`, as given: no per-tick
   scaling, so `+0x68` is in world units per second;
3. hands the same vector to the physics (`0x2e1510`), and when it is not
   zero wakes the object and marks it changed (`0x5a5eb0`, `0x59f470`,
   `0x5aa740`, the sequence the Forge doors use after a move).

So for an orthonormal `F`, `U` the arguments for a wanted world velocity `v`
are `v·F`, `v·(U × F)`, `v·U` (`lift_unit_frame`). No yaw approximation is
needed. The simulation's `+y` is left of `+x` (Unreal's `-Y`). The
two-argument definition (`0x818fb8`, evaluator `0x1b6320`) calls the same
function.

The DLL calls `0x663b90` directly, found by its bytes, with the unit
handle and the three frame values: the evaluator does nothing else with
them, so it is the same push without compiling
`(object_set_velocity (player_get N) f l u)` every tick. A build whose bytes
no longer match falls back to that line through the script evaluator
(`hs_evaluate`), which is how the Lua pushes ran. The cost of both is
measured below.

## Frames and units

The level file's phantoms are Unreal centimetres relative to the level's
canvas origin (0 on every shipped map). The simulation's frame is Unreal's
at 304.8 cm a world unit with `y` negated, so `lifts.lua` converts each
phantom before it writes the file: points `(x+ox, -(y+oy), z+oz) / 304.8`,
plane normals `(a, -b, c)` with `d' = (d - n·origin) / 304.8`, directions with
`y` negated, accelerations and speeds `/ 304.8`. Gravity on a Spartan is
4.1715 wu/s² (measured below).

## Checked in game

Lockout, a private Slayer game on PC 1, 2026-11-08, read from outside the
game (ReadProcessMemory, the thread walk of `tools/remote/blam-players.py`):

- **Position.** The player's unit read `(-5.4604, 9.2644, -12.6300)` at
  `+0x44` while its `BP_SpartansBipedActor` stood at Unreal
  `(-1664.33, -2823.80, -3849.62)`: the same point, ×304.8 with `y`
  negated, to the hundredth of a centimetre. Phantoms authored against the
  actor's location need no offset.
- **Facing.** `+0x50` read `(0.6089, -0.7933, 0)` for an actor at Unreal yaw
  52.49° (`cos`, `-sin`); `+0x5C` read `(0, 0, 1)`.
- **The user map.** In a solo game `+0x34` and `+0x74` read 0 for player 0
  and `-1` for players 1–15; `+0x04` held player 0's handle (`0xEC700000`)
  and `+0x14` its unit's.
- **The tick.** TLS `+0x98` `+6` read **60**, and `+0x0C` advanced 30 in
  half a second of wall clock. A main tick sometimes runs two simulation
  ticks; the push covers the ticks since the last one.
- **Velocity and gravity.** One `object_set_velocity ... 0 0 2` on a biped
  written into the air read 1.74 at `+0x68` on the next sample and rose
  0.027 wu a tick: world units per second. Falling, the velocity lost
  0.13905 wu/s every other tick, **4.17 wu/s² (1271 cm/s²)** by wall clock
  over 1.2 s. The Lua pushes had assumed Halo 1's 978 cm/s².
- **A biped written to a new position** stays put, asleep, until something
  wakes it, and a wake within a few seconds puts it back where its physics
  last had it (the teleport notes say the same). Test rides therefore write
  the player into the tube with the lifts off, wait 35 s, and hand the set
  back.

### Pushing every tick

The first rides overshot the top speed: along Lockout's tube the speed
climbed to 4.5–5.3 wu/s against a top of 4. A per-push trace showed why. The
velocity read back alternates between losing almost nothing and losing two
ticks of gravity, and the carry (restore the last push's speed when the read
is lower: the ground holds a standing biped still) kept every gain and undid
every loss. The carry now applies only when more than half the speed is gone,
which a gravity step at riding speed never takes; `test_ratchet` in
`native/lobby/test_lifts.c` models the alternate-tick gravity and fails on
the old rule.

### Cost

Through the script evaluator a push took 88–139 µs (worst 297–1036 µs), 60
times a second while a player rides: up to about 8 ms/s on the simulation
thread. Calling `0x663b90` directly removes the compile; its bytes (the
branch and global displacements masked) match once in the Steam and the
Xbox DLL alike. The evaluator stays as the fallback when they do not.

## After a game update

The datum offsets are CU4's. A build that moves them is caught by the reads'
own checks (data-array magic and element size, the object entry's salt, own
index, type 0 and datum size, finite vectors), and a fault turns lifts off
until the next set. To re-check: host a lift map, stand in a lift, and read
`fireteam.log` for `lifts: player N in phantom ...` and the `left the lift`
line with its push count. The Forge editor test (`0x2fe810`) is used only on
the two builds the doors know.
