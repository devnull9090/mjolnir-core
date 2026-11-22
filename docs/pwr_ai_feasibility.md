# Covenant AI on Pelican Warfare: feasibility

Research for [pelican_warfare_waves.md](pelican_warfare_waves.md) section 4
(Covenant waves), 2026-11-22. Nothing here is shipped code. The measurements
were made offline on the released map's sealed inputs (map 0.1.1,
`saturday.45/map-input`) and the shipped campaign scenarios. The game was not
run. Tools and outputs are in `out/pwr-ai/` (listed at the end).

## Verdict in one paragraph

Feasible, but not with the bots lane as it stands. PWR's walkable ground is
not in the BSP's collision shell. It lives in 151 instanced-geometry
definitions: 1.2 million unwelded triangles. The bots lane only reads the
shell, so on PWR it "succeeds" while producing nothing usable: one sector on
a box floor 42 wu under the map. Bungie's own pathfinding has the shape PWR
needs. Every shipped campaign BSP keeps its sectors on instanced geometry
(`object refs`), merges many collision triangles into each sector, and goes
past 32,767 links. The terrain is also friendly: one connected area joins
both bases, all three sites and both flight-start grounds, and the routes
are close to straight lines. The work is a new pathfinding generator, an
"instances" mode that builds coarse convex sectors over the welded terrain.
That is the first step and the biggest risk, because the one earlier attempt
at object-ref pathfinding crashed the game. After it, the AI side reuses
what Bungie's own missions do: a Spirit loaded with `vehicle_load_magic`,
objectives and tasks over zones of firing positions, and `ai_set_task` when
the target changes.

## 1. Can the bots lane generate pathfinding for PWR?

**It runs, and the result is unusable.** The bake input was the shipped
`pwr.level.json` with the loader-only keys removed and `defs/level/bots.json`
added as `blam.bots`, exactly as `tools/level/add_bots.py` builds it. It was
baked into `out/pwr-ai/bake/` from the shipped map container's BSP and world.

| | |
|---|---|
| Wall time | 51 s (`level bake`, release build, PC 1) |
| Exit | 0, with no warning |
| Pathfinding | 1 sector, 4 links, 4 vertices, 9 surface refs, 151 instance refs (all -1) |
| Spawns | "16 of 16 on the main walkable ground" (false: see below) |
| Firing positions | 1,849, widened to a 15.38 wu grid to fit the 2,048 cap |
| Squads | 180 (12 kinds x 15) |
| Output | `pakchunk997-MJOLNIRMAP-PWR_P` 397.4 MB (shipped 402.7 MB). Package-by-package, only `PWR-scenario.uasset/.ubulk` differ (scenario bulk 237,714 -> 453,373 bytes). The BSP, world and lighting packages are byte-identical; the smaller `.ucas` is compression. |

Why the result is useless:

- **The shell is a 9-surface box.** Its only floor is at z -6.56 wu
  (-20 m, the scenario's lower bound). `pathfinding::shell_collision` reads
  only that, so the lane makes one sector there. Every spawn "stands on" it
  because `sector_at` takes the highest floor under the point, and that floor
  is 42 wu below the actual ground. The firing positions all lie under the
  terrain.
- **The ground is in instances.** There are 151 instances, each of its own
  definition. Instance 0 / definition 0 is a copy of the box. The other 150
  hold the terrain, the bases and the rocks, in definitions of up to 8,192
  surfaces each, 1,199,995 in all. Edges and vertices are both exactly
  3 x surfaces: every triangle has its own three vertices and edges, so no
  two triangles share an edge. 268,595 triangles are walkable
  (normal z >= 0.65). By count, 20.8% of the triangles face down, 34.6% are
  walls, 22.2% are steep and 22.4% walkable. By area, 38.8% are nearly flat
  floor. Most of the downward and wall area is the box (definition 0, a
  656 x 656 wu floor, ceiling and walls). Every definition's surfaces have an
  edge loop (`first_edge` >= 0 on all of them).
- **Every instance ref is -1**, so an AI standing on the terrain is on no
  sector. That is the Blood Gulch "copy" failure (path follower state 3,
  cannot plan a path; docs/re/ai_in_multiplayer.md), but over the whole map.
- **The current generator could not do it even if pointed at the
  definitions.** One sector per walkable triangle, summed over the
  definitions, gives 268,595 sectors, 1,089,160 links and 810,929 vertices.
  That is 4 to 17 times over the engine's limits, and the triangles are
  unwelded, so the sectors would not connect to each other.

The lane should refuse this case loudly instead of passing. For example:
stop when the chosen spawn sector lies more than about 2 wu below the spawn,
or when the shell has under some minimum of walkable area while instances
hold more.

**Engine limits, checked against shipped data** (census of the 13 shipped
Halo 1 scenarios, `out/pwr-ai/census.txt`):

| Block | Limit | Largest shipped |
|---|---|---|
| sectors | 65,534 (tag max) | A30 BSP 3: 17,301 |
| links | 16-bit indices | A30 BSP 3: **59,826**, forward/reverse up to 59,356 |
| vertices | 65,535 (tag max) | A30 BSP 3: 42,028 |
| object refs | 8,192 | 44 (C45) |
| instanced geometry refs | 16,384 | 11,813 (D40) |
| bsp2d refs per object entry | 262,136 | 9,228 |
| hints | 32,767 | 1,335 |

Bungie's link indices go past 32,767, so the sim reads them as unsigned
16-bit numbers. The generator's cap of 32,767 (`pathfinding.rs`, i16 types)
is half the real budget of about 65,535 links and vertices.

Two more facts from the census decide the generator's design:

- **No shipped BSP uses the structure's own refs** (`bsp2d refs` = 0
  everywhere). Every sector sits on instanced geometry through `object refs`
  (one per definition, each with its own `bsp2d refs`, one per collision
  surface, and a `vertex offset`). Every instance maps to an object through
  `instanced geometry refs`.
- **Sectors merge triangles.** A30 BSP 3's object 9 has 9,228 surface refs:
  4,614 none, 426 into `bsp2d nodes` (a surface split between sectors), and
  the rest naming only 1,706 sectors. B40 BSP 8 has 632 sectors and 2,377
  links in all. Sector flags are mostly 0x11. 0x15 (adds `mobile`) is rare
  on A30 but about a quarter of B40 BSP 8's sectors (149 of 632), and B40
  also has step sectors (0x1045, 0x1085, 0x1105, 0x1205).

**Which definitions own the ground.** Measured on the raster below:

- 18 large terrain tiles (instances 126-143) own 96.5% of the main walkable
  top, each as one big patch or two. So the definitions are spatial tiles.
  Their bounds look wide only because a tile's box reaches across its
  neighbours.
- 131 other instances (rocks, the bases, props) own the rest, in 1,419
  patches under 10 cells: mostly rock tops.
- Tile-to-tile seams total 8,387 wu. Seams that involve a smaller owner
  total 9,908 wu.

So a generator that works per definition and joins seams with intersection
links (Bungie's way) fits PWR's layout, at a cost of a few thousand
intersection links and hints (the hint limit is 32,767). Small rock tops
should get ref -1, which removes most of the second kind of seam. The BSP
itself does not need re-chunking.

## 2. Is a graph usable on a 2 km heightfield?

This was measured on a 1 wu (3.05 m) raster of the topmost upward-facing
instance surface: `out/pwr-ai/probe/probe.txt`, with a walkable map in
`probe/walkable.pgm`. A raster is a stand-in for the real graph: it misses
tree trunks and anything thinner than 3 m, so its obstacle count is a floor.

- **Slopes.** Of the top surface, 55.8% is under 10 degrees, then 15.5%
  (10-20), 13.9% (20-30), 10.9% (30-40), 2.4% (40-50) and 1.2% steeper.
  99% of covered ground passes the 49-degree walkable rule.
- **Connectivity.** 423,967 wu^2 is walkable. One component holds 420,635
  cells (99.2%). There are 291 components in all, 223 of them under 10
  cells. Both homes, all three sites (on their layout positions, with the
  raster height matching the layout height to within 0.01 wu) and the ground
  under both flight starts are on the main component.
- **Routes** (Dijkstra on the raster). Home to near site: 121 to 123 wu,
  1.03-1.04x the straight line. Home to far site: 277 to 298 wu. Site to
  site: 157 to 255 wu, 1.01-1.08x. Base to base: 392 wu.
- **Water.** The simulation has no water: Fluid Flux is Unreal-only, so the
  river and lake beds are ordinary walkable collision. Estimated from the
  flux sources' heights and the lake level (55 m), 35,080 wu^2 lies under
  water and 30,330 wu^2 of it deeper than 0.5 wu (1.5 m). The shortest
  route crosses water on 6 of the 10 pairs tested, up to 1.1-1.3 wu (3.4 to
  4 m) deep: an AI would walk along the river bed under the surface. Each of
  those pairs also has a dry route, 2% to 14% longer. The dry routes pass
  the river at two places only: around (-23, -84) m and (-75, 209) m, on
  terrain tile 143, where the ground is about 20 m above the nearest flux
  source's height. **So the navmesh must leave out water deeper than about
  0.5 wu**, taken from the flux state, which the level already ships.
- **Bridges and roads: unverified.** `layout.py` puts the three main
  bridges at y -350, 0 and 350 m and fords at y ±800 m. The two dry
  crossings above do not obviously match, so they may be a bridge deck
  merged into the tile, a high bank, or a gap in the water estimate: it only
  knows water within 15 wu of a flux source point. No bridge deck shows as a
  separate layer in the core. The 10,186 cells with a walkable floor more
  than 2 wu under the top cluster at the map's edges (around |x| or |y| of
  450 to 840 m). Before the navmesh cuts water out, the bridges must be
  confirmed in collision (`pf_where dump` at the bridge positions), and the
  water mask built from the baked height fields rather than source points.
  Roads are part of the terrain surface.
- **Obstacles.** The play area has 2,215 blobs of non-walkable ground
  (rocks, steep bumps, cut-offs): 1,977 of 1-2 cells (1,931 of those cells
  steep), 176 of 3-20 cells, and 62 larger (largest 2,079 cells).

**Graph size.** A coarse navmesh fits the engine, though not the
generator's present cap. These are estimates on the raster, made with a
right-triangle bisection (RTIN): a triangle splits until it is all main
walkable ground and its heights fit one plane. RTIN is about 2x worse than a
proper polygon or Delaunay decomposition, so the real counts should come in
lower:

| Coverage | Sectors | Links (~1.6x) |
|---|---|---|
| Whole map, every obstacle, plane fit 1 wu | 34,417 | ~55,000 |
| Whole map, every obstacle, plane fit 2 wu | 30,388 | ~48,600 |
| Whole map, 1-2 cell bumps ignored, 2 wu | 20,578 | ~32,900 |
| Central band \|x\| <= 450 m (sites, not bases), bumps ignored, 2 wu | 7,723 | ~12,400 |

A quadtree is worse: 26,600 to 36,900 sectors and 72,000 to 94,000 links,
which is over budget. What drives the count is the obstacle edges, not the
terrain's curvature.

Recommendation: a polygonal navmesh (welded walkable triangles, deep water
and obstacles cut out, then merged into convex regions under a height
tolerance), aiming at 10-25k sectors and under 50k links. The central band
can be the first cut. Two things are open:

- **Height tolerance** of a coarse sector. The AI finds its sector through
  the collision surface it stands on (bsp2d refs), so a sector need not be
  flat. How far its vertices may stray before paths or firing positions look
  wrong is not known; Bungie's sectors follow their surfaces exactly.
- **A sector is a union of whole collision triangles**, or the triangles it
  cuts need `bsp2d nodes` (Bungie uses both). The estimates above ignore
  that constraint.

## 3. The Havok proxy budget

What is known for certain (Ghidra on `HaloSimulation_tag_release.dll`,
project `C:\ghidra_proj\sim`):

- `FUN_180375470` creates the data array `"havok proxies"` with a fixed
  maximum of **16** (0x10) entries of 0x50 bytes, stored at `[TLS+0x268]`.
  This matches the memory note.
- `game_performance_throttle` (`globals\default`, referenced by the
  scenario) has one profile, for 3 or more players: `maximum havok proxy
  count` 0, ragdolls 3, impacts 10. Proxies are a throttled resource like
  ragdolls.
- A physics model material has a `proxy collision group`. The Spirit's
  (`tuning_fork`) material 0 is `machine`, the grunt's `NONE`.

What is not known: which objects take a proxy, and what happens when all 16
are in use. The allocation sites were not found within the time box.

**Leading hypothesis: proxies are switched off in any real match.** The
throttle profile is restrictive (3 ragdolls, 10 impacts) and sets the proxy
maximum to 0 from 3 players up. That would explain both readings:

- the Blood Gulch reading (4 Warthogs plus one per live biped = 13, with
  eight bots and a host) was taken with one human player, below the
  profile's threshold;
- PWR places 18 vehicles (8 Warthogs, 4 Scorpions, 4 Banshees, 2 Pelicans)
  and plays with players on top, which would be over 16 if every vehicle
  and biped held one.

Whether bots count toward "player count" is unknown, and "0" could also
mean "no limit". Nobody has seen a failure caused by proxies either way.

**A safe wave size cannot be derived from "16".** Until it is measured:

- one Spirit carrying **8 AI** (two squads of 4: 2 elites and 6 grunts or
  jackals), and at most **12 live Covenant** on the map;
- the first live test reads the proxy array (the `[TLS+0x268]` data array:
  count, then each datum's object handle at +0x44) across the throttle
  threshold: a PWR match with 2 players, then with 3 or more. In each, read
  it with no AI, then 8 and 16 AI plus the Spirit. Check that the last AI
  placed still stands on the ground and is hit by vehicles;
- raise the cap only on that evidence. Shipped missions run dozens of AI
  (B40 loads 2-3 squads per Spirit), so AI count is not otherwise the limit.

## 4. Making the AI "smart"

Everything below is what CE/Reach AI data already does, in shipped
missions. The bake should generate it per candidate spot, from tag data and
never from the map's name.

### What Bungie's B40 does with a Spirit (decompiled, `out/pwr-ai/scripts/B40.hsc` ~line 1596, 1897)

```
(ai_place sq_..._dropship)                                    ; pilot squad with the Spirit
(set v (ai_vehicle_get_from_starting_location sq_..._dropship/pilot_spawn))
(ai_place gr_..._drop_e)                                      ; the passengers
(vehicle_load_magic v "fork" (ai_actors sq_..._ge))           ; seat name substring: any fork_p_* seat
; command script on the pilot:
(cs_enable_pathfinding_failsafe true) (cs_ignore_obstacles true)
(cs_vehicle_speed 0.66) (cs_fly_to ps_dropship_a_flightpath/p0 0.1)
(unit_open v)
(begin_random (begin (vehicle_unload v "fork_p_r1") (sleep 5)) ... "fork_p_l8")
(unit_close v) (cs_fly_by ps_..._flightpath/p1) ...           ; and away
```

All of these calls are in the shipped script corpus (`defs/hce/scripting.json`):
`ai_place`, `vehicle_load_magic`, `vehicle_unload`, `unit_open`,
`ai_set_objective`, `ai_set_task`, `ai_vehicle_enter`,
`ai_vehicle_reserve_seat`, `cs_fly_to`, `cs_vehicle_speed`,
`cs_run_command_script`, `ai_magically_see`, `ai_set_team`,
`object_wake_physics`, `ai_task_count`, `ai_living_count`. `ai_force_active`
and `ai_get_unit` are not in the corpus, but MJOLNIRHud's bots already use
them.

Two ways to fly the Spirit:

- **AI pilot** (Bungie's way, and the simulation-first choice in
  CLAUDE.md). This needs point sets (`scripting data` is cleared on PWR
  today) and a command script per drop compiled through `blam.script`.
  Flight here uses `cs_ignore_obstacles` and does not need the ground
  navmesh. A command script running in a Megalo game is untested.
- **Native host flight**, like the Pelicans, as the waves doc plans. That is
  proven for Pelicans, but it is more code of ours.

Spike the AI pilot first.

### Who the Covenant fight

An AI marks a unit an enemy when either campaign team is -1 or the
allegiance matrix says so. Players have campaign team -1 in a Megalo game
unless the lobby DLL's team table gives them one. So with no team table in
force (no red/blue bots in the same match), Covenant squads already treat
both teams as enemies. No `ai_set_team` and no new table are needed, which
is simpler than the waves doc's "human and player" mapping. If red/blue bots
are wanted alongside the Covenant, the table must map red and blue to two
teams that are both hostile to `covenant` (for example `human` and
`player`), and that case needs its own test.

### Generated data per map

Proposed names. The inputs are the `koth_hill` candidate markers (spawn
sequence `site*10 + candidate`, waves doc section 3), the capture radius and
the flight starts.

| Block | Generated | Count (3 sites x 10 candidates) | Limit |
|---|---|---|---|
| pathfinding | object refs per terrain definition, coarse sectors, bsp2d refs/nodes, intersection links across definition seams, deep water cut out | 150 objects, 10-25k sectors | see section 1 |
| zones | `cov_site_<s>` (one per site) | 3 | 128 |
| areas (per zone) | `c<k>_core` (inside the capture radius), `c<k>_ring` (20-45 m), `c<k>_approach` (45-90 m, toward the map's centre) | 30 per zone | 128 |
| firing positions | ~60 per area. Flags `partial`/`closed` where an obstacle blob or rise stands between the position and the core, `open` elsewhere. Facing toward the core. | ~1,800 per zone | 2,048 |
| LZ areas | `c<k>_lz`, preset `dropship`, for the Spirit's hover point | 30 | (same zone) |
| objectives | `cov_site_<s>` | 3 | 64 |
| tasks (per objective) | `c<k>_assault` (approach + ring, attitude aggressive, movement run), `c<k>_hold` (core + ring, defensive, capacity bounds), `c<k>_fallback` (ring + approach, inhibit nothing), plus `roam` | 31 | 100 |
| squads | `cov_<kind>_<n>` (elite/grunt/jackal, characters `mjolnir_bot_*_legendary`), `cov_spirit_<n>` (vehicle squad + pilot) | ~24 + 4 | 512 |
| squad groups | `cov_wave_<n>` | 4-8 | 130 |
| point sets | `ps_spirit_<s><k>`: entry at a map edge, approach, hover over `c<k>_lz`, exit | 30 | 200 x 32 points |

### Runtime orders

Native, on the host only, issued once per event. This is not a Lua poll.

1. **Match start**, once the candidates are chosen: nothing to send if task
   activation can read the choice (below). Otherwise remember the three
   chosen candidates.
2. **Wave k** (on the combat clock):
   `(ai_place cov_spirit_0)` `(ai_place cov_wave_0)`
   `(vehicle_load_magic (ai_vehicle_get_from_starting_location cov_spirit_0/pilot) "fork" (ai_actors cov_wave_0))`
   `(ai_set_objective cov_wave_0 cov_site_a)`
   `(ai_set_task cov_wave_0 cov_site_a c3_assault)`
   `(cs_run_command_script cov_spirit_0/pilot cs_spirit_a3)`.
   Target the site the Covenant hold least, or the one being captured.
3. **At the hover**, in the command script: `unit_open` and `vehicle_unload`
   per seat. Then from native `(ai_force_active cov_wave_0 true)` and
   `(object_wake_physics ...)` per unit (bots.md: AI far from players go
   idle, and still bodies fall asleep).
4. **On a zone event** (site captured, held, contested): re-task the squads
   that serve it, for example `c3_hold` once inside, or the next site's
   `c<k>_assault` after the site falls. Use `ai_task_count` and
   `ai_living_count` to decide.

**Re-targeting without orders** (to test): a task's `activation script` is
a script fragment the objective system evaluates itself. If the bake can
compile one per task, such as `(= g_site_a 3)` on `c3_*`, then native sets
three globals once at warmup and the objectives pick the current spot with
no per-squad orders. Whether `level bake` can write task fragments today is
unchecked. The `ai_set_task` route above works without them.

**Smart behaviour knobs** that already exist:

- task `attitude`, `movement`, `inhibit groups` (leave Cover and Vehicles
  on), `capacity` (spreads squads over tasks), `priority` and
  `exhaustion delay`;
- task `filter` (`strength < 0.5` for a fallback task);
- the bot characters' per-level accuracy;
- cover-flagged firing positions (open, partial, closed);
- `ai_magically_see` on landing, so they engage at once.

Contesting a zone is a separate piece. The host counts living Covenant
bipeds within the capture radius (native already reads the zone positions),
as the waves doc plans.

## 5. Risks

1. **Our object-ref writer is unproven.** Object refs as such work in a
   Megalo match: the first bots spike (BOT, on B40's stock BSP 8) ran
   Bungie's own object-ref pathfinding in Slayer. What crashed on Blood
   Gulch was our attempt: an object for the shell copy, reusing the shell's
   refs, with no sectors or vertices of its own, crashed 2-5 s after the
   bots moved. The risk is getting Bungie's layout exactly right (own
   sectors, a `vertex offset`, node trees), and BOT is the control to test
   against. The fallback is decimated terrain in the shell, but the
   collision-source notes say that route needs the kd hierarchy and
   structure physics rebuilt for a 2 km world.
2. **Unsigned 16-bit indices** are inferred from shipped data (A30 has
   59,826 links). The generator's types are i16 and need widening, and the
   sim's treatment of 0xFFFF as "none" must hold.
3. **The proxy budget** is unknown (section 3).
4. **Activation at 2 km.** AI far from every player go idle;
   `ai_force_active` covers that. Perception and engagement ranges are
   campaign-sized, which may suit PWR's open ground poorly.
5. **AI pilot and command scripts in Megalo** are untested. So is
   compiling the point sets and scripts into PWR's generated scenario.
6. **Water** looks wrong if deep water is not cut out of the navmesh (AI
   walking under the Flux surface).
7. **Network.** AI far from a joiner lag a few metres (two-PC test,
   2026-10-25). With 16 players and 12 AI over 2 km this is unmeasured.
8. **A map republish is needed.** All AI data lives in the scenario, and
   every machine needs the same scenario. The bake changes only the
   scenario packages (verified above), so the map container changes in the
   `add_bots.py` style, plus the HUD and native changes. The release also
   needs the bot character containers (CE runtime 1.16.0 or later) and a
   container for the cloned Spirit.
9. **The bots lane's silent pass** on maps like PWR (section 1) could ship
   broken data by accident.

## Step list (in order, each with its test)

1. **Template from B40** (offline). Run `pf_dump` raw and summary on B40
   BSP 8 with its sbsp, to confirm whether object vertices are
   definition-local (`vertex offset`), how sector rings cross definition
   seams (intersection hints), the node trees and flags 0x11/0x15.
   *Test:* write B40's own pathfinding back through the new writer and
   compare byte for byte.
2. **Widen the indices** in `blam_sbsp::pathfinding` to u16 (65,535).
   *Test:* unit tests, plus a round-trip of A30 BSP 3's 59,826-link block.
3. **"Instances" generator.** Weld each definition's triangles; take the
   walkable ones; cut out water deeper than 0.5 wu (from flux state) and
   obstacles; merge into convex sectors per definition; write object refs,
   bsp2d refs/nodes and vertex offsets; join definition seams with
   intersection links; point instanced refs at their objects; give
   definition 0 (the box) none. *Test:* offline. Every sector ring closes
   (`check_rings`). Homes, sites and flight-start grounds are on one
   component. Route lengths are within 15% of the raster's. The counts fit.
4. **Guard the bots lane.** Refuse when spawns stand far above their
   sector, or when instances hold the walkable ground. *Test:* PWR fails
   loudly, and the 48 hub maps bake unchanged (the `add_bots.py
   --bake-only` sweep).
5. **First live run, the crash gate.** A private PWR test install, one
   player, one placed grunt squad ordered between two far areas, with BOT
   (Bungie's own object refs) as the control. Watch for the Blood Gulch
   crash (2-30 s), follower state (actor +0x874 in state 1, not 3) and the
   sector under the unit. *Test:* 10 minutes with no crash and the squad
   walking 300 wu across a river crossing.
6. **Proxy measurement** (section 3). *Test:* read the proxy array with 2
   players and then with 3 or more (across the throttle threshold), each
   with 0, 8 and 16 AI plus a Spirit; check that the last AI placed still
   collides. This sets the wave cap.
7. **Zones, objectives and squads** from the candidate markers (needs the
   moving-zones work). *Test:* `pf_where`-style offline check that each
   area's positions are on the main component, and that every task reaches
   its areas.
8. **The Spirit.** Clone `tuning_fork`, generate point sets, AI pilot with
   command scripts; native fallback if command scripts fail in Megalo.
   *Test:* solo, the Spirit reaches its hover point, unloads 8 AI on the
   ground, and leaves; then on two game copies, the joiner sees the drop.
9. **Native wave director and contest.** Waves on the combat clock,
   targeting, re-tasking on zone events, the AI presence count blocking
   capture. *Test:* `test_warfare.c` cases, then one solo and one
   two-copy match.
10. **Tuning against players**, by the owner. *Test:* the owner plays it.
    No release before that.

## What was not tested

- Nothing ran in the game. The crash risk of object-ref pathfinding, the
  proxy behaviour, AI flight in Megalo and AI replication over 2 km are all
  open.
- The graph counts are raster estimates, not a built navmesh. A real
  generator was not written.
- The water depths are an estimate from flux sources (nearest source within
  15 wu) and the lake level, not the baked water height fields.
- The havok proxy allocation sites were not found.
- Task activation-script compiling in `level bake` was not checked.

## Files (`out/pwr-ai/`, not tracked)

| | |
|---|---|
| `bake/`, `bake.log`, `pwr.bots.level.json` | the bots-lane bake of PWR (51 s) |
| `pfprobe/` (`src/main.rs`, `src/bin/pfcensus.rs`) | the probe and the shipped-pathfinding census (`cargo build --release` with `CARGO_TARGET_DIR=C:/haloce/target`) |
| `probe/probe.txt`, `probe/walkable.pgm` | instance census, raster, routes, water, graph estimates |
| `census.txt` | every shipped Halo 1 BSP's pathfinding sizes |
| `instances.txt` | PWR's 151 instances |
| `scripts/*.hsc` | decompiled shipped mission scripts (B40's Spirit drops) |
| `ghidra_375470.c` | the `havok proxies` array creation |
| `water.json` | flux source heights and lake bounds used for the water estimate |
| `tags/`, `shipped/`, `gptd/`, `src/`, `PWR.umap` | extracted game and map content (local only) |

## Update, 2026-11-22: the format is settled and a generator exists

The first step and biggest risk above is done offline. The findings moved to
the engine reference, which is now the one place for how pathfinding works:
[AI pathfinding: sectors, links and how the simulation finds them](engine_ai_pathfinding.md).
In short, and correcting sections 1, 4 and 5 above:

- **The lookup is traced.** An instance's sectors are read only when its
  `pathfinding policy` is `static`. All 151 PWR instances say `none`, so the
  terrain tiles must be set `static` in the BSP (a change to the BSP package,
  not only the scenario).
- **Objects are per instance, not per definition.** Each static instance gets
  its own object ref, with one ref per surface of its definition.
- **The writer is proved.** B40 BSP 8's object refs rebuild byte for byte. The
  Blood Gulch crash is most likely the missing child blocks of the earlier
  writer.
- **Indices are 16-bit unsigned** in our generator now (65,535 links and
  vertices).
- **The generator is built** (`blam_sbsp::navmesh`). On B40 BSP 8 it picks the
  same walkable surfaces as Bungie's data on 2,075 of 2,078. On PWR it gives
  one connected ground over all 18 terrain tiles in 8 seconds: 15,197 sectors
  and 51,844 links with sector borders allowed to move by 1 wu, or 19,290 and
  62,109 at 0.6 wu. With exactly convex sectors of whole triangles PWR does
  not fit (about 98,000 links).
- **Three structures are separate pieces**: the two bases (near (-590, -80) m
  and (600, -80) m) and one more of the same size at (0, 690) m. They sit on
  the terrain without sharing its edges, so nothing joins them to it yet.
  Covenant waves that land at the sites do not need them; AI that should walk
  into a base does.
- **Water was not cut out in that run.** River and lake beds counted as
  floor. Section 2 above says deep water must be left out; whether the ground
  stays connected then is not measured.

**Run live on B40 (same day).** `level bake` now takes `blam.pathfinding` and
writes the generated sectors as object refs. On B40's BSP 8 an Elite walked
generated sectors across three instances to the player and killed them; the
control with Bungie's data behaved the same way. One thing the first run
taught: firing positions store the sector they stand on, and must be looked up
again when sectors change. Details in the engine article.

**Run live on PWR (same day).** With `instances: "ground"` the bake picks the
24 instances that carry ground, sets them `static` in the BSP, adds their 24
object refs, and the bots lane puts its spawns and 1,854 firing positions on
the generated sectors. Four AI placed at the capture sites and ordered to
distant areas all arrived, the furthest after 365 wu (1.1 km), with no crash
in about six minutes. One PC, one player, in warm-up.

The remaining steps, in order:

1. **Capture platforms and bases: done (same day).** The bake cuts the
   terrain away under a floor that lies on it (`headroom`), so the two end on
   one line and a seam joins them. All three bases and the four pads are now
   part of the main ground, an AI on a pad has a sector, and an Elite walked
   from open terrain onto the west base's floor. Not yet watched: an AI
   walking onto the centre platform. Details in the engine article,
   "Structures on the terrain".
2. **Water: done (same day).** The bake reads the map's two baked Flux
   states and leaves out floor more than 0.5 wu under the surface (27,788
   wu²). Both banks and both bases stay one piece of ground, and Elites
   ordered across the river in both directions arrived without a position
   sample in water. Details in the engine article, "Water".
3. **Zones and tasks per capture candidate** in place of the bots lane's one
   map-wide zone (section 4), so squads assault and hold the site in play.
4. **A second player, and a fight.** One placed squad walking 300 wu across tiles, with the
   looser and the tighter border setting, to choose between them.
4. Steps 6 to 10 of the list above (proxy budget, zones and objectives, the
   Spirit, the wave director, tuning).

If the looser borders misbehave, the alternative is to cut triangles with
`bsp2d nodes` as Bungie does. The lookup for those is traced; a node writer is
not built.
