# Bots

AI players that fill a multiplayer match (issue #247): the simulation's own
AI, given a seat and a name on MJOLNIR's scoreboard. They run on the host; a
fireteam client sees them through the simulation's own replication.

Proven on Blood Gulch on 2026-10-25, host and one joiner on two PCs: the bots
walk the map, fight the players and each other, die and respawn, and both
machines' feeds and boards name them and count the same kills. In team games
they play for red and blue (PC 1, 2026-10-31): the two sides fight each other,
a bot leaves the players of its own side alone, and its kills score for its
team.

## The pieces

| Where | What |
|---|---|
| `level bake`, `blam.bots` ([level_format.md](level_format.md)) | bot squads, a zone of firing positions, an objective, AI pathfinding for the map's BSP; `<CODE>.bots.json`, where the squads stand |
| `crates/blam-sbsp/src/pathfinding.rs` | the pathfinding tables, from a structure BSP's collision shell |
| MJOLNIRLobby's DLL, `mjolnir_bots_enable` | lets `ai_place` place squads in a Megalo game |
| MJOLNIRLobby's DLL, `mjolnir_bots_teams` | in a team game, gives AI units the multiplayer team of their side |
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
links, one connected area of 2828 sectors.

Two things cut a converted map's ground that the edges alone miss, and the
bake handles both the way B40's own data does
([re/ai_in_multiplayer.md](re/ai_in_multiplayer.md#steps-and-seams-in-bungies-pathfinding)):

- **Steps.** A riser under 0.1 wu (where the AI globals' hoist step begins)
  between two floors becomes a step sector, walkable, linked to both. Short
  bands of a taller riser, or a slab's side face hanging below its floor, do
  not.
- **Cracks.** Maps built of separate slabs meet floor to floor without
  sharing an edge: edge to edge, overlapping a hair, or across a crack. Two
  floor edges that both drop away, face each other within 0.1 wu and lie
  less than a step apart in height join through an *intersection link*, a
  hint on each floor's edge naming a link that joins the two.

Neither is a jump, a hoist, a ladder or a teleporter: ground those reach
stays apart. On Night Lockout (PC 1, 2026-10-30) bots walked back and forth
across its slab seams (two bots, 14 crossings in two minutes) and one crossed
the lower level to kill the idle player.

**AI stand still without orders.** They hold firing positions in their task's
areas until they see someone, and AI far from every player go idle. Each bot
is forced active when placed (`ai_force_active`), the bake gives the objective
the tasks `area_0` .. `area_15` (a map with fewer areas repeats them, one
with more shares them out, so every task the HUD names is there) and makes
`hunt` follow the players (radius 3 wu, every player slot), and the host's
HUD orders each bot every 8-16 s, waking its body first (see "Bots frozen
in place" below): three times in
four after an enemy, otherwise `(ai_set_task <squad> mjolnir_bots
area_<r>)` to a random area. An enemy human is hunted: the `hunt` task and
`(ai_magically_see_object <squad> (player_get n))`, where `n` counts the
players there are (`player_get` returns the nth player in the players
table, not a seat), so the HUD passes the target's rank among the humans in
seat order. In a team game an enemy is anyone on the other side, a bot too:
a bot is no player, so it gets an area walk and `(ai_magically_see <squad>
<enemy squad>)`. A human whose side the HUD has not read yet is no one's
target in a team game.

**Where bots spawn.** On the map's own player starts. The bake stands each
bot squad on one of the starts on the ground the bots walk (`bots_finish`),
so a bot appears where a player would. Squad `k` of every kind takes the
`k`-th start farthest first: the first start, then each time the one
farthest from those already taken. A level lists its starts a base at a
time, so taken in the level's order (as before 2026-10-31) the first eight
bots on Blood Gulch all stood at one base and fought there. A map with more
starts than squads (15 per kind) never uses the rest.

The bake also writes where each squad stands, `<CODE>.bots.json` (Unreal cm,
by squad index), which the map's pack carries beside its level file
(`map/bots.json`, installed to `ue4ss/MJOLNIRMaps/<CODE>/`; a test install's
goes to MJOLNIRLevelLoader's `levels/`). With it, the host's HUD picks a bot's
squad each time it places the bot, so the bot comes in where its side is.
A side has no base of its own: a converted map's player spawns are all
neutral, and on Blood Gulch Team Slayer the red host's first spawn landed at
the south base in one match and the north in another. So the HUD does what
the game's respawns do for players, in order:

1. a free squad of the bot's kind (none another bot out holds);
2. never within 2 wu of anyone;
3. with an enemy about, a start no enemy is within 25 wu of, or failing that
   the starts farthest from the enemies (within 10 wu of the farthest);
4. with its side about and the enemies clear, the starts nearest one of its
   side (within 8 wu of the nearest);
5. with no one about, its own squad `k` (the farthest-first order);
   otherwise one of what is left at random.

In Free for All everyone is an enemy, so a bot comes in away from all of
them. The first bots wait up to 5 s for the humans' first spawn. A bot's
weapon is its squad's (`weapons[k % n]` of its kind), so it changes from life
to life. On Blood Gulch Team Slayer (PC 1, 2026-10-31) the red host spawned
at the north base: the three red bots came in beside him and the five blue
bots at the south base. A map without the file (every map published before
it) keeps squad `k` for bot `k`, as before.

**Why bots stand still.** Seen on Night Lockout and Blood Gulch: a bot sent
to `hunt` a player it cannot reach (on ground the pathfinding does not join)
waits at the nearest point; the HUD picked `area_<r>` from 0-15 while most
maps baked fewer areas, so those orders went nowhere (every map bakes all
sixteen tasks since 2026-10-31); and on narrow ground `hunt`'s 3 wu radius
found no firing position to stand on until the bake narrowed the grid there.
An AI with no target holds its task's positions: the simulation's own
`search` follows a target it lost, it does not roam.

**Bots frozen in place.** Three things kept bots still for minutes on Blood
Gulch (PC 1, 2026-10-31,
[re/ai_in_multiplayer.md](re/ai_in_multiplayer.md#bots-frozen-in-place)):

- **A sleeping body.** A bot's body falls asleep in the physics when it
  stands still, as anyone's does, and sometimes its AI does not wake it
  again: the AI goes on thinking and its squad takes every order, but the
  body neither moves nor turns, not even when shot. A Spartan stood so on
  open ground for five and a half minutes. `ai_force_active` does not wake a
  body; `(object_wake_physics (ai_get_unit <squad>))` does, and the Spartan
  walked off within a second of it. So every order the HUD gives a bot
  starts with that line, and a bot whose body stays asleep waits for its
  next order (8-16 s), not for minutes.
- **The flag rooms.** No bot on the lower floor under a base's deck, by
  the flag, was seen to find its way out. Ordered anywhere, one walks about
  the room, to a corner or a little way up an exit ramp, turns back and
  stops; a jackal stayed over half an hour, a grunt over 20 minutes. Bots
  walk in through the exits (and elites drop in through the hole in the
  deck), so the rooms can collect bots over a match. Waking them changes
  nothing. Not fixed; the cause is not known.
- **Elites in the side doorways.** The ramp from a base's deck down to each
  side door passes under the door's lintel, 0.82 wu above the ramp at its
  inner edge, and an elite is 0.8 wu tall. An elite walking down jams its
  head there, facing the door, twitching, and stays until it turns back (one
  stood five minutes). Spartans, grunts and jackals pass under it. Elites
  mostly jump off the deck's rim instead. Not fixed.

**Who bots fight** (measured in Team Slayer on Blood Gulch, 2026-10-30;
[re/ai_in_multiplayer.md](re/ai_in_multiplayer.md#teams-in-a-megalo-match)).
Every unit carries a campaign team and a multiplayer team. A player's unit
is on red or blue with no campaign team; the simulation puts a bot's on its
squad's campaign team (covenant) with no multiplayer team, every tick. In a
Megalo game a unit with no multiplayer team is everyone's enemy, and bot
against bot is decided by campaign teams: bots of one team never fight each
other (covenant, flood, sentinel and heretic bots do fight one another).
That is how bots play Free for All: every one covenant, attacking every
player and leaving the other bots alone. No script function gives an AI unit
a multiplayer team (`mp_ai_allegiance` is compiled out, `ai_allegiance` gated
to campaign).

**Red and blue bots.** In a team game each bot plays for a side.
MJOLNIRLobby's DLL (`mjolnir_bots_teams`) turns the unit update's `or dx,
0xff00` (multiplayer team -1) into a call to a few bytes of its own that look
the multiplayer team up by campaign team, in a table the HUD writes
(`native\bot_teams.txt`: covenant 3 plays for red 0, flood 8 for blue 1). A
bot's squad is put on its side's team (`ai_set_team`: covenant for red,
flood for blue) before its `ai_place`, and the new actor takes it. Moved
after placing, a blue bot was red for a tick, and a blue Spartan could keep
the red armour MJOLNIRLevelLoader tinted it as it appeared (seen on PC 1).
Red and blue bots fight on sight and bots of one side leave each other
alone, and the game's damage code knows the sides: a red bot's hit on a red
player is flagged friendly (`bDamagedByFriendly`), and a player's kill of a
bot on their side raises `kill_betrayal`.

**Players get their side's campaign team too.** An AI picks its enemies by
campaign teams alone: when it notices a unit it marks it an enemy if either
campaign team is -1 or the allegiance matrix says so, and never asks the
Megalo team rule
([re/ai_in_multiplayer.md](re/ai_in_multiplayer.md#how-an-ai-picks-its-enemies)).
A player's unit has campaign team -1 in a Megalo game, so before this every
bot took every player for an enemy: in an isolated run a red bot killed the
red host who walked up to it, as covenant, as sentinel and as human. A
player's unit copies its pair from the player every tick, so while the
table is in, the DLL gives each player on red the covenant campaign team and
each player on blue flood. A red bot then sees a red player as one of its
own and a blue player as an enemy. Tested isolated on Blood Gulch
(2026-10-31, PC 1, nobody at the keyboard): a red covenant grunt beside the
red host held fire for 35 s; with the table turned around (flood red,
covenant blue) a grunt moved to flood before its placement held fire beside
the host, now flood, and a covenant elite placed beside them took the host's
shields in seconds.

The DLL changes the code on the simulation thread between ticks, puts
it back when the HUD clears the table (the match ends), and on its own once
the game is not a Megalo one; Free for All leaves it alone. A bot's side is
chosen when it is first placed, for the side with fewer players (humans and
bots); on a tie the side with fewer humans, as a human plays better than a
bot; then blue. It keeps that side for the match, and the board files it
there (its biped reports the side too, so kills of it read right).

**Slayer's score ignores bots.** Its kill trigger counts kills of players, so
the round never ended on bot kills. With bots playing, the host's HUD ends the
match itself when anyone (bot or player) reaches the score to win, the way the
game's own `round_over` does: final standings, then the post-game screen. A
fireteam client gets no `round_over`; it follows the host's travel.

**AI are not players.** Their incidents carry player index -1 and the AI
biped's actor: a player who kills a bot raises `Kill` (no `death`), or
`kill_betrayal` and no `Kill` when the bot is on their side; a bot that kills
a player raises the player's `death` (no `Kill`). The HUD gives bot `k`
the seat 100 + k (the match log records only seats 0-15, so bots never reach
the hub) and translates -1 to the seat by actor, then counts both ways (a
`kill_betrayal` of a bot as a kill: -1 in Team Slayer).

**A bot killed by a bot raises nothing**: no `Kill`, no `death`, only kill
medals such as `first_blood` with no seats. Its body stays an actor where it
fell, so the HUD would have counted it alive and never placed it again. The
HUD reads each bot's unit on its actor instead (`BlamObjectDamage:IsDead()`,
every 0.25 s), and the actor's blueprint keeps each hit's aftermath
(`Blam Aftermath Result`: the damage owner's actor, the damage type and
modifier the incidents carry, and `bBodyDepleted` on the killing blow). When
the owner is another bot, the HUD queues the `Kill` the game would have
raised: the feed, the board, the team score and the fireteam's clients all
have it. A bot that dies with no player's `Kill` naming it within 2 s (a
fall, its own grenade) waits out the respawn time with no line.

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
bots change. In a team game each seat carries its side's letter
(`R100=Nadia (bot);B101=...`), which a client from before sides skips: a
relayed line has no biped to read the side from. Once it has the roster, a
client drops its own copies of AI kills and deaths (they name the AI -1) and
counts the host's.

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
minor version with the new map container in place of the old, and the bake's
`<CODE>.bots.json` as `map/bots.json`. The bots stand on the map's own player
starts. It stops unless every other container, and every package of the map
container but the scenario, comes out byte-identical. Rebaking also brings the map's Forge palettes up to the
current bake's (the only other difference from a 2.1.0 scenario).
`--bake-only` rebakes and checks without packing.

A weapon in `bots.json` that a map's palette lacks is left out of that
map's turn. A map whose level file already has `blam.bots` is refused, and
so is a container with more than one BSP or world.

## Not done

- Spartan bots all wear the default armour colour.
- Slayer's own score counts player kills only: the HUD's board counts bot
  kills, but a round does not end when a bot reaches the score.
- Team games: a bot keeps its side when players join or leave (the teams
  can end uneven). A fireteam client's view of the sides
  (the roster's letters, its own copy of the units' teams) is not tested on
  two PCs.
- Players' campaign teams: in a team game with bots a player's unit is
  covenant (red) or flood (blue) instead of no campaign team. Nothing else
  seen reads it in a Megalo game (player against player follows the
  multiplayer teams), but only Blood Gulch Team Slayer has been played so.
- Not yet seen in a whole match with the fix: what a side's bots do after a
  player of that side shoots one (the AI turns on a betrayer in campaign,
  which until now no one could see, since every bot shot every player
  anyway); whether bots now follow players of their side as allies do in
  campaign; and why, in one isolated run, a flood grunt and a covenant elite
  of the two sides stood 4 wu apart without fighting while the elite killed
  the host.
- Free for All: every bot is covenant, so bots never fight each other.
- A bot that falls or kills itself gets no suicide on the board.
- Maps with more starts than squads (15) leave the rest unused. A map
  published before 2026-10-31 has no `map/bots.json`, so each bot comes back
  on the start it first used, whichever side is there.
- Bots on Blood Gulch's flag-room floors, under the decks, were not seen to
  find their way out, and elites jam under the side doors' lintels ("Bots frozen in
  place" above). The generated pathfinding knows nothing of headroom, so a
  doorway too low for an elite is open to it. Other maps are not checked.
- Why a bot's AI sometimes leaves its sleeping body asleep is not known.
- The HUD sends bots to hunt players they cannot reach. A map published
  before 2026-10-31 still has as many area tasks as it baked areas, so some
  of the HUD's roaming orders go nowhere until it is rebaked.
- No jump, hoist or ladder links, so bots do not use teleporters, lifts or
  man cannons, and ground reached only that way stays apart. Night Lockout's
  two levels meet only by drops and jumps: its bots play the lower one (16
  of its 33 starts; the upper level holds 14).
- Some converted shells keep a copy of the vertices along each seam between
  pieces (13 of the 48 hub maps). Those seams are cracks of width 0 now and
  join like any other.
