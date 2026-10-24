# Forge

**Status:** 2026-10-24. Host only, on any converted multiplayer map. Not
released yet: it needs the CE runtime pack with the monitor fix
(`pakchunk990-MJOLNIRFORGEMON_P`) and the mods named below.
**How it works:** [re/forge_engine.md](re/forge_engine.md).

Halo Reach's Forge is still inside Halo: Campaign Evolved's simulation.
MJOLNIR switches it on: you turn into the Monitor, fly around the map, and
pick up, move, drop and delete its objects. The game's own Forge engine does
the work; MJOLNIR gives it keys and a small panel.

## Starting a Forge game

1. MULTIPLAYER → HOST GAME, pick a map.
2. Pick **FORGE** as the game type. It is listed once MJOLNIRForge is
   installed and the CE runtime pack has the monitor fix.
3. Start. A panel at the top left says `FORGE`.

For scripts and tests: `mjolnir_auto host <CODE> forge private` at the
console.

## Keys

| Key | What it does |
|---|---|
| **B** | Turn into the Monitor, or back into your Spartan |
| **V** | Pick up what the cursor is on; press again to drop it |
| **Page Up / Page Down** | Push a held object away, or pull it in |
| **Delete** | Delete what you hold (or, holding nothing, what you aim at) |
| **N** | Duplicate the target at the cursor |

As the Monitor you move with your usual movement keys and the mouse; jump
flies up. The panel shows what you are holding or aiming at, and what the
last key did.

To use other keys, create `keys.txt` in the MJOLNIRForge mod folder with
lines like `grab=F7` (actions `toggle`, `grab`, `duplicate`, `delete`,
`nearer`, `farther`; key names as UE4SS spells them, such as `PAGE_UP`).
The defaults are keys the game does not use. G, C, Z and X are taken.

## Not there yet

- **Placing new objects.** Duplicate (N) answers "this map's palette has no
  entry for that object" on today's converted maps: they have no Forge
  palette yet.
- **Saving a layout.** Changes last until the game ends.
- **Playing with your fireteam.** Players who join start Slayer instead.
- **A Forge menu** (object lists, properties, rotation).
- The cursor only reaches things in plain view: it stops at walls and the
  ground.
