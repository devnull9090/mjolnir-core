# Test bot

A driver that plays the local player in a running game, for automated tests
(medals, objectives, anything that needs real kills) and as the start of our
own bot code. It walks the map's navmesh to the closest living enemy, turns
smoothly, and fires while the reticle is locked on. Nothing touches the
desktop's mouse or keyboard.

```bash
# The map's navmesh, once per map (game content: keep it out of the repo).
mjolnir extract --group scenario_structure_bsp --filter BGL --out <dir>
mjolnir level navmesh --sbsp <dir>/Levels/Halo1/Solo/BGL/_Generated_/BSP_01_1_Start.scenario_structure_bsp --out bgl.navmesh.json

# In a match (for example `mjolnir_auto host BGL slayer private`, then `mjolnir_bots 3`):
node tools/bot/drive.mjs --navmesh bgl.navmesh.json --seconds 120 --log
```

Options: `--bone` (the target bone, default `Head_M`; `Chest_M`, `Spine1_M`,
`Neck_M` also exist), `--engage` (metres within which a showing target is
aimed at, default 30), `--stop` (metres at which it stops walking in, default 6),
`--goto x,y[,z]` (walk to a point in world units instead of hunting: a route
test; the log line carries the speed and position).

## How it works

| Part | Where | What |
|---|---|---|
| Navmesh | `mjolnir level navmesh` (crates/blam-cli/src/level_navmesh.rs) | the AI pathfinding `level bake` builds from the map's collision (docs/bots.md): convex areas and the doorways between them, in world units |
| Routes | `navmesh.mjs` | the area under a point, A* across areas through doorway midpoints (skipping blocked areas), then a funnel that pulls the route tight so it turns only at corners. `node --test tools/bot/test_navmesh.mjs tools/bot/test_drive.mjs` |
| Enemies | `mjolnir live objects --group bipd`, every second | positions and who is alive. A dead biped stays an object, and an enemy's actor is hidden until it is close, so the simulation picks the target |
| View | one `game_lua` call a tick | the camera; whether `MyHUD.AimAssistInfo.FullyTargetedActor` is an enemy (the red reticle); the target bone's position once its actor shows |
| Input | `mjolnir_test_input.dll` (native/test_input) | keys change only when they should, so W stays down; `glide dx dy ms` spreads each turn over the frames so the view never snaps, and each tick's glide replaces the last |

The target is the living enemy closest by route, not in a straight line. The
view turns toward the route's next corner while walking, at most 200°/s, and
toward the bone once the target shows within `--engage`, more tightly. Shift
is held with W on a straight stretch (sprint: about 9 m/s against 5.7). Fire
is held while the reticle is red. Walking that makes no progress for 1.5 s
jumps and steps aside.

**Obstacles.** What stands on a converted map's ground (trees, rocks) is
collision the AI pathfinding does not see: on Blood Gulch the trees are in the
BSP's instanced geometry, which the pathfinding never reads, so a route ran
straight into a trunk and the player slid along it. The exporter now marks an
area `blocked` when a steep surface of the shell or the instances stands
inside it (Blood Gulch: 446 of 2947), routes go around blocked areas, and the
export lists those surfaces' sides as `walls`. Close in, the driver checks the
line ahead against them at body height and bends past the whole obstacle on
the side that turns less. Walking the line through a Blood Gulch tree now
passes its trunk 5.5 m off one way and 7 m the other.

## Limits

- About 10 ticks a second, limited by the Lua bridge (60-140 ms a call).
  The decisions could move into the input DLL's per-frame hook, which runs on
  the simulation's thread, to drive real bot players.
- No line of sight check beyond the actor showing and the reticle.
- The navmesh joins only what the AI's does: jumps, hoists, ladders and
  teleporters are not routes.
- It plays whatever weapon it holds. For headshot medals give it a pistol:
  `blam (cheat_all_weapons)` drops one near the player.
