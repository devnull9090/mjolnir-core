# The bot

A driver that plays the local player in a running game: for automated tests
that need real kills (medals, objectives), and as the start of our own bot
players. It walks the map's navmesh, fights at the skill a preset sets, dives
out of the way, picks up better weapons, and prints a tally of what it did.
Nothing touches the desktop's mouse or keyboard.

```bash
# The map's navmesh, once per map (game content: keep it out of the repo).
mjolnir extract --group scenario_structure_bsp --filter BGL --out <dir>
mjolnir level navmesh --sbsp <dir>/Levels/Halo1/Solo/BGL/_Generated_/BSP_01_1_Start.scenario_structure_bsp --out bgl.navmesh.json

# In a match (for example `mjolnir_auto host BGL slayer private`, then `mjolnir_bots 3`):
node tools/bot/drive.mjs --navmesh bgl.navmesh.json --skill legendary --seconds 120 --log
```

Options: `--skill recruit|regular|heroic|legendary`, `--set field=value` (any
preset field, repeatable), `--player N` (which player it is), `--no-dive`,
`--goto x,y[,z]` (walk to a point in world units instead of hunting: a route
test), `--log` (a line a tick). The last line printed is the tally:
`{"skill":"legendary","seconds":101,"kills":3,"deaths":0,"dives":13,...}`.

It stops by itself when the match ends (MJOLNIRHud writes `last_match.txt`
seconds before it takes everyone back to the lobby). Without that the game
crashed: the level's actors are freed on the way out, and the bot's Lua was
still calling one.

## Skill presets

`presets.mjs` holds every number the bot's skill is made of; nothing about
skill is hard-coded anywhere else. The four presets differ like this:

| | recruit | regular | heroic | legendary |
|---|---|---|---|---|
| Reaction to a new target | 0.75 s | 0.4 s | 0.22 s | 0.08 s |
| Turn speed onto a target | 140°/s | 220°/s | 320°/s | 540°/s |
| Aim wander (one sigma) | 3.5° | 1.8° | 0.8° | 0.15° |
| Leads a moving target by | 0 | 0.05 s | 0.1 s | 0.15 s |
| Locks onto the bone within | never | never | 2° | 8° |
| Aims for the head | 10% | 35% | 65% | 95% |
| Engages out to | 22 m | 30 m | 40 m | 60 m |
| Trigger | 0.5 s bursts | 0.9 s bursts | held | held |
| Side-steps in a fight | never | half the time | mostly | always |
| Crouches and jumps | no | a little | some | a lot |
| Dives when hit | never | 15% | 50% | 90% |
| Dives when aimed at | never | never | sometimes | nearly always |
| Between dives | - | 8 s | 5 s | 2.5 s |
| Backs off below shields | never | 15% | 30% | 40% |
| Grenades | never | every 20 s | every 10 s | every 6 s |
| Goes for better weapons | no | within 25 m | within 40 m | within 60 m |
| Goes for ammunition | only when empty | yes | yes | yes |
| Prefers a wounded enemy | no | no | a little | strongly |

Measured on Blood Gulch against three AI bots (one run each, so indicative
only): recruit kept its aim a median 3.6° off the bone while fighting (worst
tenth 19.8°); legendary 1.3° (worst tenth 7.1°), with 13 dives and no deaths
in 100 s.

## How it works

| Part | Where | What |
|---|---|---|
| Navmesh | `mjolnir level navmesh` (crates/blam-cli/src/level_navmesh.rs) | the AI pathfinding `level bake` builds from the map's collision (docs/bots.md): convex areas and the doorways between them, in world units |
| Routes | `navmesh.mjs` | the area under a point, A* across areas around blocked ones, then a funnel that pulls the route tight so it turns only at corners |
| The simulation | `world.mjs` (`mjolnir live objects`, about two reads a second) | the bot's shield and body, every living enemy and where it faces, weapons on the ground and in hand. A dead biped stays an object, and an enemy's actor is hidden until it is close, so the simulation picks the target |
| The view | one `game_lua` call a tick, in `drive.mjs` | the camera; whether `MyHUD.AimAssistInfo.FullyTargetedActor` is an enemy (the red reticle); the target's bone (`Head_M` or `Chest_M`), looked for where the target was last seen |
| Decisions | `brain.mjs` (pure functions) | which enemy, which weapon to fetch, and each tick of a fight: aim wander, trigger, side-steps, crouch and jump, melee, grenades, dives, weapon swap, backing off |
| Input | `mjolnir_test_input.dll` (native/test_input) | keys change only when they should, so W stays down; `glide dx dy ms` spreads each turn over the frames so the view never snaps |

Tests: `node --test tools/bot/test_brain.mjs tools/bot/test_drive.mjs tools/bot/test_navmesh.mjs`.

**Firing.** The reticle only reddens inside the weapon's auto-aim range
(about 30 m with the assault rifle), so the bot fires on the red reticle or
when its aim is within a body's width of the bone.

**Line of sight.** The navmesh export lists every collision polygon of the
map (the shell and the instanced geometry: 37,613 on Blood Gulch), and
`mesh.sight(eye, bone)` casts the line between them. A target counts as
visible only when its actor shows and that line is clear, so the bot neither
fights nor fires through a hill, a wall or a tree trunk.

**Turning.** Each tick's turn is spread over the frames by `glide`. The
camera reading a turn is computed from is already tens of milliseconds old,
and the last turn has gone on since; that part is taken off the new turn, or
it is applied twice and the aim swings past the target. A preset with
`lockOn` then sticks to the bone once it is that close: the whole remaining
error in one short glide, with no rate limit.

**Leading.** The aim point is the bone moved by `lead` seconds of the
target's motion less the bot's own (its side-steps swing the view too). Both
velocities are a line fitted through the last half second of positions, so
one noisy reading does not swing the aim.

**No way there.** An enemy somewhere the navmesh does not reach (a roof)
is approached as far as the nearest ground the bot can walk to, never in a
straight line at a wall; with nowhere nearer to go it faces the enemy and
waits.

**Dives.** The Spartan's animation graph has the AI's dives
(`combat:rifle:dive_left`, `_right`, `_front`, `_back`, and pistol, missile
and sword sets). The simulation's `custom_animation` plays one on a player's
unit and it moves the unit about 4 m; the bot calls it through the Blam
console. It dives only to a side with no wall within a dive's length.

**Obstacles.** What stands on a converted map's ground (trees, rocks) is
collision the AI pathfinding does not see: on Blood Gulch the trees are in the
BSP's instanced geometry. The exporter marks an area `blocked` when a steep
surface of the shell or the instances stands inside it (Blood Gulch: 446 of
2947), routes go around blocked areas, and the export lists those surfaces'
sides as `walls`, which the driver steers past close in. Walking that makes
no progress for 1.5 s blocks the ground just ahead for the rest of the run
and backs out, so the next route goes another way.

**Weapons and ammunition.** `mjolnir live objects` reads each weapon's
rounds (magazine and reserve) and which weapon a player has in hand, so the
bot knows what it can fire:

- the weapon in hand is spent (nothing loaded, nothing in reserve): it swaps
  to one that is not, and never pulls the trigger on empty;
- the magazine is empty with rounds in reserve: it reloads;
- a held weapon is on its last magazine: between fights it walks to a weapon
  of the same kind on the ground (walking over it takes its rounds), further
  the lower it is, and at once, even mid-fight, when nothing held can fire;
- nothing held can fire and no ammunition is in reach: it takes any weapon
  with rounds in it, and failing that closes in to melee.

A weapon on the ground is worth fetching when it outranks everything held
that still fires (`WEAPON_RANK` in presets.mjs: rocket launcher, sniper
rifle, fuel rod, shotgun, magnum ...), has rounds in it, and is within the
preset's reach by route. Only ranked weapons are fetched: an Oddball skull is
a weapon to the simulation too. The bot walks onto it holding the pick-up
key, and gives up on one it cannot get after 10 s. Plasma weapons keep a
battery, not rounds, and are taken to be usable; for those the old test
stands (on target for a few seconds with no damage: next weapon).

**Keys** are in `presets.mjs` (`KEYS`), set to the test PC's bindings
(`HaloGlobalGameUserSettings.ini`): melee F, grenade C, crouch Left Ctrl,
swap 1, reload R, sprint Left Shift.

## What it cannot do yet

- **Ten decisions a second, two looks at the simulation.** The Lua bridge
  takes 60-140 ms a call and `mjolnir live objects` half a second, so a hit
  is noticed up to half a second late and "an enemy is aiming at me" is
  half a second old. Moving the brain into the game (the input DLL's hook
  runs every frame on the simulation's thread, and the lobby DLL already
  copies players from the object table each tick) removes both limits, and
  is how these become real bot players rather than a driver for the local
  one.
- **Sight is against the map only.** Vehicles, doors and other objects do
  not block it, and neither do thin things the collision leaves out.
- **Leading is for bullets that arrive at once.** Rockets, plasma and
  needles need the shot's flight time added, which needs the weapon in hand.
  The weapon in hand is known now; shot speeds per weapon are not. The
  simulation's own velocity for the target (it keeps one per object) would
  beat a fit through positions.
- **No battery read.** Plasma weapons' charge is not mapped, so an empty
  one is found out by doing no damage.
- **No cover.** Backing off is straight back with side-steps, not to a spot
  out of the enemy's sight.
- **Dives use the rifle set** whatever is held, and their look in third
  person is unverified (the displacement is measured).
- **Enemies are every other biped.** No teams, no objectives, no vehicles.
- **The navmesh joins only what the AI's does**: jumps, hoists, ladders and
  teleporters are not routes.
