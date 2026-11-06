# Native support for CE tag data

**Status:** 2026-11-05, experiments 1 to 3, the skinned Mongoose, rider limbs, map players and the driver's CE pose passed in game; see Results. Marks: V verified, I inferred,
NF not found, F seen only in secondary research and to be confirmed against
`sapien.exe` before anything depends on it. Addresses are the sim DLL unless marked.

## Principle

A CE object's own tags decide what it does and how it looks. Tools translate
fields by rule. Nothing is measured, posed or tuned per vehicle.

## How CE works

- **Tick** (F): unit and vehicle update, damage, function export, nodes with
  function-driven overlays, children, rider IK.
- **Attachments** (F): built once, each scaled by an object function.
- **Rider** (F): root attaches to the seat marker, no offset field. The seat label
  picks the rider's antr mode; IK targets vehicle markers named in that antr.
- **Jet:** `speed` seeks raw throttle (V, Sapien 0x66415f), so the tag's 4.0 is
  unreachable (limit of 1: F). Zero throttle gives zero lift (F); powered points
  have no antigrav flag (V). Function D peaks at 0.25, so `jet_engine` stays at
  quarter scale (I).
- **Mongoose:** body vitality 0 (V, tag); no body damage (F).

## Design

**Blam side.** One translator per tag group, emitting real fields:

- skel, coll, phmo and jmad carry CE's hierarchy, as one unit. The hlmt load
  (0x180281850) silently blanks any ref whose nodes disagree (V).
- A general N-node jmad writer. `vehicle suspension`, `vehicle:steering` and
  `vehicle:ground_speed` are the homes for moving parts (I).
- Physics: translate first. Wheel mass points become friction points (I). CE's
  thrust and lift have no field (NF). A native port is untested, not excluded.
- A weap and proj route, splitting CE's trigger into `new triggers` plus `barrels`.

**Unreal side.** One generic actor: a drawn SkeletalMesh with bones named as the
sim's nodes, cloning `ABP_B40_Elevator`. `BlamSyncPose` (exe 0x147cf66f0) matches
by FName with no count check (V), so rig scale goes (I). An identity `pedestal`
sits above an off-origin CE root, as node 0 does on the Warthog and shipped
Mongoose (V), so CE's locals stay verbatim.
`tools/level/ce_vehicle_nodes.py` builds the tag side from the mesh's `bones.json`.

## What replaces each shortcut

| Shortcut | Replacement |
|---|---|
| Borrowed rig, 0.589 scale | Own hierarchy |
| Static handlebars, suspension | jmad blocks above |
| Ghost pose, measured IK | CE antr modes, `ik points` (674 maps at most) |
| Lua lights | `ligh` if it draws, else `effe` bound to a BP |
| Lua sounds | `lsnd` with a real AkAudioEvent |
| Donor weapons | Real weap and proj |
| Banshee handling | Clear slide, boost, tricks, cruising throttle |
| Ratio numbers | Tag rules; `wheel circumferance` 1, CE's value (effect untested) |

A CE function evaluator may be partly redundant: the sim names `speed_absolute`
and `driver_seat_power` (V), but their handler is NF.

## Order of work

First lift the importer gates: `fit()` and `rigid_check` turn away 537+ maps.

| # | Unknown | First experiment |
|---|---|---|
| 1 | SK, ABP cook | SK with Warthog bone names, ABP clone, cloned BP |
| 2 | Node agreement | Mongoose skel, coll, phmo, jmad; hlmt refs survive load |
| 3 | jmad writer | Rewrite `any:idle` for N nodes, re-decode |
| 4 | Rider | CE mode in a Spartan override; Megalo action 42 |
| 5 | Functions | Which names evaluate on a vehicle |
| 6 | Effects, lights | `antigrav_lift-effect` clone to a BP; find `ligh` schema |
| 7 | Sound | Find what `lsnd` to AkAudioEvent needs |
| 8 | Speed | Unit of `maximum forward speed`: 22.7 or 30 wu/s |

## Results

Measured in game on PC 1, 2026-11-05, one player, on a B40 canvas.

**1. Skeletal rig: passed.** A SkeletalMesh, Skeleton and animation Blueprint of
our own loaded in a cloned actor, with all 119 Warthog bone names. Driving it
spun and steered the wheels, moved the suspension and turned the steering wheel
while a parked stock Warthog stayed still. The test boxes drew, with no crash.
A mesh saved before its skeleton is renamed keeps the old path and cooks with no
Skeleton; the mesh then loads and draws but gets no anim instance, silently.

**2. Node agreement: passed.** Mongoose skel, coll, phmo and jmad on 14 nodes
kept all four hlmt refs and 14 runtime nodes (the shipped control has 119).

| Variant | Node names | Root | Result |
|---|---|---|---|
| NAS | registered | origin | boards, drives |
| NAO | CE | origin | boards, drives |
| NAT | CE | CE | refs survive; floats about a metre; not boarded |
| NAR | registered | CE | not run; NAO and NAT isolate the root |

So CE's node names work as they are in tags (V).
The root node looks to need the origin, with CE's root offset moved into the next
node (I: one look at an unboarded vehicle; an offset in phmo is not excluded).

**3. jmad writer: passed.** A rewritten Warthog `any:idle` with `hood_base`
turned 30 degrees put the drawn bone about 30 degrees of pitch from `Body` on the
same actor; without the rewrite the two matched. The game accepts our members and
they reach the mesh.

**4. Skinned Mongoose: passed.** CE's model on its own 15-bone mesh (`pedestal`
above CE's 14 nodes), own skeleton, animation Blueprint and six skinned materials,
beside the shipped Mongoose. All four hlmt refs and 15 runtime nodes survive, it
draws with CE's textures, boards and drives. Parked, every drawn bone matches the
sim's node to the reading's precision: 0.15 cm, 0.001 of axis.

Driven, from the sim's own node matrices:

| Part | Measured |
|---|---|
| Tires | all four spin forward, rate tied to speed: about 31 rad/s near 6 wu/s |
| Suspension | each corner moves on its own: 1 to 13 cm over one run on the deck |
| Steering | front tires 25.6 degrees left on A; `frame steering` turns with them |

The sim turns a node's string id into an Unreal name with spaces as underscores:
`frame hull` reaches `BlamSyncPose` as `frame_hull` (V, read from the node's bone
array). A bone named with the space takes no transform and stays at its bind pose,
with no error. Tags keep CE's name; the mesh takes `frame_hull`.

`bNoSkeletonUpdate` reading true on a driven vehicle is normal: the flag came back
about 120 times a second after being cleared, so the sync looks to wake the mesh
for one refresh at a time (I).

**5. Rider limbs: passed, torso open.** The seat's IK proxies moved to CE's own
limb ends: hands to CE's wrists after its IK, on `frame steering`; feet to CE's
idle ankles on `frame hull`. The mode is still `ghost_d`. Read from the sim's
Spartan nodes, in the vehicle's frame, cm:

| Joint | Driver | CE | Miss |
|---|---|---|---|
| Ankles | -50.5, 38.1, 87.4 and -45.0, -36.7, 86.4 | same | 0.0, 0.1 |
| Wrists | 2.2, 31.4, 158.9 and 1.3, -33.5, 158.3 | 8.8, 32.6, 158.0 and 7.3, -34.1, 157.4 | 6.8, 6.1 |
| Hips | -73.0, -0.2, 116.1 | -61.7, -1.2, 129.0 | 17.2 |
| Head | -42.4, -4.1, 181.8 | -18.7, -1.3, 171.0 | 26.2 |

Limbs land on the marker's position, and CU4 stops an arm at its reach: the wrists
stop short along the arm (I). Hands follow the bars, but at full lock the far hand
falls short (right wrist 0, -42 against about 40, -50 on a left turn). The
passenger's ankles land on target and the left wrist within 3 cm. The arms-up pose
was the IK proxies left at VHT's height when the seat moved to CE's place.

Hips, head and knees are the mode's: only a CE idle on a Spartan mode moves them.
No shipped mode comes closer than 20.9 cm of torso error.

**6. A map's own player: passed.** `blam.player_representations` in a level writes
`override player representations` and sets `override globals`. On NMG the player
spawned as a cloned biped, with first person and HUD intact; hosting Rat Race next
gave the stock Spartan. A cloned model and full graph (111 MB uncompressed) also
loaded: all four hlmt refs hold, 122 runtime nodes, and the seated joints match the
stock graph's. The stock graph stays loaded beside the clone, so a map pays the
memory twice. Give all three rows: the copy replaces the globals' block (I).
Not tested: bots, Elite rows, armour customisation, two PCs.

**7. CE's seat pose on a Spartan: passed for the driver.** `tools/level/ce_vehicle_rider.py`
translates CE's seat idle onto `ghost_d:idle`, `ghost_d:grip` and
`warthog_p:rifle:idle` in the map's cloned graph, by one joint table per rig pair.
`Clip` now carries chain data, so IK survives the edit. Driver in game, against CE, cm:

| Joint | Miss |
|---|---|
| Pelvis | 0.4 |
| Wrists | 0.0, 0.0 |
| Ankles | 0.0, 0.1 |
| Head | 8.6 |
| Knees | 6.7, 7.2 |

These match the offline build, so the overlays leave the pose alone, and it holds
after driving. At full lock the hands stay on the bars. The knees are over the
6 cm goal: the Spartan's hips sit 7 cm off CE's and its shin is longer, so with
ankles pinned the knee has nowhere to go. The head is proportion.

The passenger pose is built (offline: pelvis 0.0, wrists 0.0 and 1.3, knees 9.1),
but it was not read in game: the seat could not be boarded on this run. Its right
arm sits at 98% of reach, with no chain on it. Enter, exit and other weapon classes
stay the donor's. CE's idles do not close their loop, so a small step shows at the seam.

**8. Lights: the Blueprint's own.** The Warthog's light components hang from
names like `VFX_Headlight_L`. `ce_vehicle_skin.py --markers` adds each as an unskinned
bone on CE's `headlight` and `taillight` markers, so the components stay and switch
with the Blueprint: headlight intensity 0 parked, 18 with a driver, brake 12. No Lua
moves them. CE's markers can sit behind the body (outer headlights 10 cm, tail lights
3.5 cm), which buried the glow, so each moves along its facing to 1 cm past the surface.
The sim leaves those bones at their bind pose. Socket fields are read-only to editor
Python, which is why they are bones.

**9. Two PCs: passed for the driver.** On Roadworks, a map with its own world, the
joiner spawned as the map's cloned Spartan and drew the host's native Mongoose. Read
on the joiner while the host drove: engine state, tires spinning and turned 32
degrees, handlebars 18.6, and the rider on CE's pose (pelvis within 0.3 cm of the
host's reading, wrists on the bars through the turn, ankles exact).
A joiner cannot enter a map that borrows a canvas world, with or without a map's own
player: the host puts it in the game, its session leaves, and it returns to the menu.
So test a vehicle on a map with its own world.

**10. A small graph over the stock one: passed.** `mjolnir jmad child` keeps only the
animations a map changes and names the stock Spartan graph as its parent. The sim
rebuilds the rest at load: the child holds 3 animations and 3 resource groups in
526,650 bytes, and reads 50 modes in memory. A map carries 0.5 MB instead of 111 MB,
and the graph no longer costs memory twice. A row a child keeps merges with the
parent's, so `ghost_d` keeps its enter and exit. The driver's pose matches the full
clone's to within 0.3 cm, and it holds through driving, getting out, walking and
firing. A cut Warthog mode also played correctly through a parent. Not read yet: a
child on two PCs, or the passenger's pose.

**11. Seats of their own: passed for the driver.** Result 10's child overwrites
`ghost_d` and `warthog_p`, so a real Ghost or Warthog passenger on the map would take
the Mongoose's pose. `mjolnir jmad child --mode` now carries those modes under
`mongoose_d` and `mongoose_p`, the seats' labels come from `SEATS` in
`ce_vehicle_rider.py`, and the parent keeps the donors' rows. The child grows from
0.5 MB to 9.5 MB, nearly all of it the passenger's other weapon classes. Offline, the
edited frames match the full clone's and every pool entry is reachable. In game, on one
map: a real Ghost's rider matches stock `ghost_d` (head 30.9, 65.7 cm from the pelvis
against 31.2, 65.5), a Warthog passenger matches stock `warthog_p`, and the Mongoose
driver stays on CE's pose (pelvis 0.8 cm, wrists and ankles 0.0 to 0.1). Not read: the
Mongoose passenger on `mongoose_p`, or this build on two PCs. A hub map reads
`vehicle_sounds.json` from its own folder. See `docs/jmad_format.md`.

**12. Vehicle sounds from a bank: passed for the horn and engine pitch.** A `.pak` of
our own carrying a real `.bnk` mounts beside the game's banks, and new `AkAudioEvent`,
`HaloAudioSound` and `snd!` packages play from it, so CE's horn played through a tag. An
`lsnd` attachment only starts and stops its loop. Engine pitch comes from the
Blueprint's `Audio_EngineTick`, which sets `RTPC_veh_speed` from
`GetEngineAngularVelocityFraction`, so the Mongoose's Blueprint keeps that tick. Pitch
moved on an idle-only bank, and the user confirmed it by ear. From Lua,
`AkGameplayStatics:PostEventAtLocation` is silent for every sound, and
`HaloAudioBlueprintFunctionLibrary:PlaySoundAtPosition` works. The game mutes when
unfocused, which looks like a silent bank. Not read: the four-sample engine blend, or
the range of the engine fraction. These are spike scripts in
`tools/level/native_mongoose/sound/`, not yet part of a map build, and
`vehicle_sounds.json` is still what a published map uses.

Not covered: a joiner in the driver or passenger seat. At top speed wheel rate implies a radius of 0.197 wu against 0.174
for the model, so `wheel circumferance` needs a steady-state check. Whether the
25.6 degrees is CE's limit is unchecked. The prompt needs E held, not tapped.

## Stays approximate

- Handling: CE's solver is not this one.
- Lights are the Warthog's look on CE's places, until a `ligh` tag draws. The sim
  creates a light datum (0x1805a0fc0), but no tags ship (V).
- Sounds stay Lua in published maps until the bank route in result 12 joins the map build.

## Open questions

- `allows weapons`: the clone's driver also has `gunner (player only)` and
  `prevents weapon stowing`; interaction unknown.
- Why did the clone, at vitality 500, take no rifle damage? Compare a stock Warthog.
- 177 maps teleport named vehicles; the variant holds no names.
- Stock weapons lose CE numbers too: assault rifle 36 rounds, not 60.
