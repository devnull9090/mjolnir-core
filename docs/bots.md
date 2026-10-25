# Bots

AI players that fill a multiplayer match (issue #247): the simulation's own
AI, given a seat and a name on MJOLNIR's scoreboard. They run on the host; a
fireteam client sees them through the simulation's own replication.

Proven on Blood Gulch on 2026-10-25, host and one joiner on two PCs: the bots
walk the map, fight the players and each other, die and respawn, and both
machines' feeds and boards name them and count the same kills.

## The pieces

| Where | What |
|---|---|
| `level bake`, `blam.bots` ([level_format.md](level_format.md)) | bot squads, a zone of firing positions, an objective, AI pathfinding for the map's BSP |
| `crates/blam-sbsp/src/pathfinding.rs` | the pathfinding tables, from a structure BSP's collision shell |
| MJOLNIRLobby's DLL, `mjolnir_bots_enable` | lets `ai_place` place squads in a Megalo game |
| MJOLNIRLobby `settings.lua` | BOTS on the PLAYERS page of the host's game settings: `bots=N` in the settings line |
| MJOLNIRHud `Scripts/bots.lua` | places, names, respawns and directs the bots on the host |
| MJOLNIRHud `main.lua`, `relay.lua` | bot seats on the board and in the feed, on the host and its clients |
| MJOLNIRHud `commands.lua` | `/bots <0-15>`: the host changes this match's bots |

## Why each is needed

**`ai_place` refuses multiplayer games.** Its core returns unless the game
mode is campaign or Firefight; a Megalo match is neither. MJOLNIRLobby's DLL
patches that one test (found by its bytes, so an update that moves it is left
alone). Nothing else gates AI: once placed they think, path and fight
([re/ai_in_multiplayer.md](re/ai_in_multiplayer.md)).

**Converted maps have no navigation.** Their BSP replaces B40's geometry, but
the scenario still carries B40's pathfinding for it. The bake builds the
pathfinding from the map's own collision: every walkable shell surface (normal
within about 49 degrees of up, not breakable) is a sector, every collision
edge touching one is a link, oriented so its walkable side is on the left (CE's
winged edges are already the rings the sim walks), and the shell gets one 2D
reference per surface naming its sector. Blood Gulch: 2947 sectors, 4930
links, one connected area of 2828 sectors. No jump, ladder or hint links.

**AI stand still without orders.** They hold firing positions in their task's
areas until they see someone. The bake gives the objective one task per area,
and the host's HUD orders each bot every 12-25 s: half the time
`(ai_set_task bot_k mjolnir_bots area_<r>)` to a random area, otherwise the
`hunt` task and `(ai_magically_see_object bot_k (player_get n))` on a random
human player.

**AI are not players.** Their incidents carry player index -1 and the AI
biped's actor: a player who kills a bot raises `Kill` (no `death`), a bot that
kills a player raises the player's `death` (no `Kill`). The HUD gives bot `k`
the seat 100 + k (the match log records only seats 0-15, so bots never reach
the hub) and translates -1 to the seat by actor, then counts both ways.

## Identity: which actor is which bot

Bot actors come from a pool (`BP_EliteBipedActor_C` and friends; a pooled one
waits at the origin), and an erased AI leaves its actor where it stood for the
next placement to reuse. So bots are placed one at a time, and the bot just
placed is the actor that came out of the pool, or jumped more than 4 m, since
its `ai_place`. An actor is that bot's until the `Kill` that names it.

`FindAllOf` walks the whole object array (about 23 ms a class): the pools are
found once when bots start, and actors made later arrive through
`NotifyOnNewObject`. Scanning six classes every tick held the game thread
135 ms three times a second.

## Names on the clients

A client hears bot seats in the host's relayed incidents
([multiplayer_hud.md](multiplayer_hud.md)) and needs their names. When it
meets a seat it cannot name it asks (`ServerExecRPC "MJOLNIR|bots?"`), holding
those lines up to 3 s; the host answers that player alone with
`MJOLNIR|bots|100=Nadia (bot);101=...`, and tells every player once when its
bots change. Once it has the roster, a client drops its own copies of AI kills
and deaths (they name the AI -1) and counts the host's.

## Making a map with bots

The map needs bot squads and pathfinding in its scenario, so it is baked with
`blam.bots`. Blood Gulch, from the hub install's own files:

```bash
# the installed BSP, as the bake's --bsp payload
mjolnir extract --out tags --filter "solo/bgl/"
# the hub level.json with the loader-only keys left out, plus "bots": {...}
mjolnir level bake bake.level.json --standalone BGL \
  --bsp 8=tags/Levels/Halo1/Solo/BGL/_Generated_/BSP_01_1_Start.scenario_structure_bsp \
  --world-object /Game/Levels/Halo1/Solo/BGL/BGL.BGL --out-dir out
```

Every machine in the match needs the same scenario. The test install put the
result beside the hub's as `pakchunk997-MJOLNIRBOTS-BGL_9_P` (the `_9_P`
outranks the hub release's containers). Shipping bots on hub maps means a new
release of each map, baked this way.

## Not done

- Bots are Elites: no shipped Spartan AI character.
- Slayer's own score counts player kills only: the HUD's board counts bot
  kills, but a round does not end when a bot reaches the score.
- Team games: bots are all on the AI's own team.
- No jump or ladder links, so bots do not use teleporters or man cannons.
