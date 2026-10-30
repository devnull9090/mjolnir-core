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
| MJOLNIRLobby `settings.lua` | BOTS, BOT TYPE and BOT DIFFICULTY on the PLAYERS page of the host's game settings: `bots=N;bot_type=K;bot_level=L` in the settings line |
| `tools/level/build_bot_characters.sh` | the bots' characters: the Spartan, and every kind at each difficulty |
| MJOLNIRHud `Scripts/bots.lua` | places, names, respawns and directs the bots on the host |
| MJOLNIRHud `main.lua`, `relay.lua` | bot seats on the board and in the feed, on the host and its clients |
| MJOLNIRHud `commands.lua` | `/bots <0-15> [kind] [level]`: the host changes this match's bots |

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
areas until they see someone, and AI far from every player go idle. Each bot
is forced active when placed (`ai_force_active`), the bake gives the objective
one task per area and makes `hunt` follow the players (radius 3 wu, every
player slot), and the host's HUD orders each bot every 8-16 s: three times in
four the `hunt` task and `(ai_magically_see_object <squad> (player_get n))`
on a random human player, otherwise `(ai_set_task <squad> mjolnir_bots
area_<r>)` to a random area.

**Slayer's score ignores bots.** Its kill trigger counts kills of players, so
the round never ended on bot kills. With bots playing, the host's HUD ends the
match itself when anyone (bot or player) reaches the score to win, the way the
game's own `round_over` does: final standings, then the post-game screen. A
fireteam client gets no `round_over`; it follows the host's travel.

**AI are not players.** Their incidents carry player index -1 and the AI
biped's actor: a player who kills a bot raises `Kill` (no `death`), a bot that
kills a player raises the player's `death` (no `Kill`). The HUD gives bot `k`
the seat 100 + k (the match log records only seats 0-15, so bots never reach
the hub) and translates -1 to the seat by actor, then counts both ways.

## Kinds of bot

A map offers kinds (`blam.bots.types`), each with `count` squads of its own:
`spartan_<k>`, `elite_<k>`, `grunt_<k>`, `jackal_<k>` on Blood Gulch. The
host's BOT TYPE picks one (SPARTANS, ELITES, GRUNTS, JACKALS) or MIXED, which
takes them in turn; `/bots 6 elites` changes it mid-match. A map baked before
kinds has `bot_<k>` squads only, which every kind falls back to.

Every kind plays a character of MJOLNIR's own at each difficulty level
(`tools/level/build_bot_characters.sh`): `mjolnir_bot_<kind>_<level>` for
spartan, elite, grunt and jackal, and normal, heroic and legendary, each with
`mjolnir_bot_generic_<level>` as its parent. A map bakes a squad set per kind
and level (`spartan_legendary_<k>`; 180 squads on Blood Gulch) and the host's
BOT DIFFICULTY (default LEGENDARY) or `/bots 6 elites heroic` picks one. A
map baked before levels has `<kind>_<k>` squads, which a bot falls back to.

- **Accuracy.** AI aim from per-weapon accuracy bounds and times for normal,
  heroic and legendary. A Megalo match always plays at Normal: the
  simulation reads the difficulty (game options `+0x1e4`) in about fifteen
  places, through two helpers and inline copies, all gated to campaign and
  Firefight, and some of them also scale the players. So the bot characters
  carry their level's values in their Normal slots instead:
  `mjolnir_bot_generic_<level>` is `ai\generic` so tuned, and each bot
  character tunes its own weapon entries the same way (normal keeps the
  shipped values). There is no Easy: the characters have no easy accuracy.
- **Spartans.** No Spartan AI character ships, so `mjolnir_bot_spartan` is the
  Marine's (`trooper`: human weapons, grenades, cover) in the players' own
  body, `objects\characters\spartans\spartans`. Their squads are on the
  Covenant team, since a Marine's own team is the players'.

Every machine in the match needs the characters' containers,
`pakchunk995-MJOLNIRBOT-<kind>-<level>_P` (15). They ship in the CE runtime
pack from 1.16.0, which every map with bots requires.

## Identity: which actor is which bot

Bot actors come from a pool (`BP_EliteBipedActor_C` and friends; a pooled one
waits at the origin), and an erased AI leaves its actor where it stood for the
next placement to reuse. So bots are placed one at a time, and the bot just
placed is the actor that came out of the pool, or jumped more than 4 m, since
its `ai_place` (a jump between two scans, 0.25 s apart, which only a teleport
makes). An actor is that bot's until the `Kill` that names it. A Spartan bot's
actor is the players' class, `BP_SpartansBipedActor_C`, so an actor a player
spawned in (their `player_spawn` names it) is never taken for a bot.

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
`blam.bots`. Blood Gulch, from the hub install's own files and
`examples/levels/bloodgulch_bots.bake.level.json` (the hub level.json with the
loader-only keys left out, plus the `bots` block the PC 1 tests used):

```bash
# the installed BSP, as the bake's --bsp payload
mjolnir extract --out tags --filter "solo/bgl/"
mjolnir level bake examples/levels/bloodgulch_bots.bake.level.json --standalone BGL \
  --bsp 8=tags/Levels/Halo1/Solo/BGL/_Generated_/BSP_01_1_Start.scenario_structure_bsp \
  --world-object /Game/Levels/Halo1/Solo/BGL/BGL.BGL --out-dir out
```

Every machine in the match needs the same scenario. The test install put the
result beside the hub's as `pakchunk997-MJOLNIRBOTS-BGL_9_P` (the `_9_P`
outranks the hub release's containers).

### Giving a published map bots

Bots cannot be added at run time: the simulation reads the squads, zone,
objective and pathfinding from the scenario when the map loads. But nothing
except the scenario changes, so a published map pack is all it takes:

```bash
HCE_PAKS=".../Meteorite/Content/Paks"   python tools/level/add_bots.py ce-blood-gulch-2.1.0.mjolnir --runtime ^1.16.0 --sign
```

For each pack, `tools/level/add_bots.py` takes the map container's BSP and
world out of the pack, bakes the shipped level file (less the keys only the
loader reads) with `defs/level/bots.json` as `blam.bots`, and packs the next
minor version with the new map container in place of the old. The bots stand
on the map's own player starts. It stops unless every other container, and
every package of the map container but the scenario, comes out
byte-identical. Rebaking also brings the map's Forge palettes up to the
current bake's (the only other difference from a 2.1.0 scenario).
`--bake-only` rebakes and checks without packing.

A weapon in `bots.json` that a map's palette lacks is left out of that
map's turn. A map whose level file already has `blam.bots` is refused, and
so is a container with more than one BSP or world.

## Not done

- Spartan bots all wear the default armour colour.
- Slayer's own score counts player kills only: the HUD's board counts bot
  kills, but a round does not end when a bot reaches the score.
- Team games: bots are all on the AI's own team.
- No jump or ladder links, so bots do not use teleporters or man cannons.
