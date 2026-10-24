# Forge

**Status:** 2026-10-24. Host only, on any converted multiplayer map. Not
released yet: it needs the CE runtime pack with the monitor fix
(`pakchunk990-MJOLNIRFORGEMON_P`) and the mods named below.
**How it works:** [re/forge_engine.md](re/forge_engine.md).

Halo Reach's Forge is still inside Halo: Campaign Evolved's simulation.
MJOLNIR switches it on: you turn into the Monitor, fly around the map, and
pick up, move, drop and delete its objects. The game's own Forge engine does
the work; MJOLNIR gives it keys and a HUD.

## Starting a Forge game

1. MULTIPLAYER → HOST GAME, pick a map.
2. Pick **FORGE** as the game type. It is listed once MJOLNIRForge is
   installed and the CE runtime pack has the monitor fix.
3. Start. A panel at the top left says `FORGE`.

For scripts and tests: `mjolnir_auto host <CODE> forge private` at the
console.

## The HUD

![Holding an assault rifle as the Monitor: the target card with the weapon's silhouette, the distance bar and the control bar](images/forge-hud-holding.jpg)

- **Top left:** FORGE, whether you are the Monitor or your Spartan, and the
  map.
- **Centre:** the Monitor's cursor. Blue when it rests on nothing, white
  on an object, green while you hold one.
- **Beside the cursor:** what you aim at or hold. It shows the kind of object,
  its name, the game's own picture for a weapon, and what the keys do to it.
  While you hold something, a bar shows how far out it is (1 to 60 m).
- **Bottom:** every key, dimmed when it does nothing right now, and a short
  note of what the last key did ("DELETED Shotgun").

![Aiming at a shotgun: WEAPON, Shotgun, and the keys that act on it](images/forge-hud-aiming.jpg)

The HUD ships in the CE runtime pack (`pakchunk980-MJOLNIRFORGEUI-Windows`).
Without it, a plain text panel shows the same things.

## Keys

| Key | What it does |
|---|---|
| **B** | Turn into the Monitor, or back into your Spartan |
| **V** | Pick up what the cursor is on; press again to drop it |
| **Page Up / Page Down** | Push a held object away, or pull it in |
| **Delete** | Delete what you hold (or, holding nothing, what you aim at) |
| **N** | Duplicate the target at the cursor |

As the Monitor you move with your usual movement keys and the mouse; jump
flies up.

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
