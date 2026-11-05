# Custom vehicles

A Custom Edition vehicle runs here as two clones of a shipped one: its tags,
which the simulation drives, and its Blueprint, which draws it. Halo CE's
Mongoose from Yoyorast Island V2 was the first, driven in game on the test map
`VHT` on 2026-11-04.

    python tools/level/ce_vehicle_materials.py ...           # CE shaders as material instances
    python tools/level/ce_vehicle_mesh.py ... --instances    # CE parts as meshes, one per node
    python tools/level/ce_vehicle_numbers.py <map> <tags.json> <vehicle tag> <out>
    HCE_PAKS=... python tools/level/ce_vehicle.py <manifest.json> <out dir> --numbers <out>/numbers.json \
        --driver-pose ghost_d --driver-offset=-0.02,0,0.262 --passenger-offset=-0.407,0,0.097 \
        --skel-set-file tools/level/data/mongoose_rider_ik.sets

Everything lands in the out dirs; copy the containers to the Paks folder with
the game closed. One vehicle per code, and never a map's own code:
`convert_ce_map.sh` uses the same `985` and `986` container names, so a vehicle
built under `YOY` would replace the map's textures and terrain.

A level then places it with `tag` ([level_format.md](level_format.md)). A test
map's `level bake --install-test` registers only the maps in the loader's
`registry/`, so hub maps such as Yoyorast drop out of `pakchunk996-MJOLNIRREG_P`
and `maps.json`. Run `mjolnir level register` after it, with the game closed: it
rebuilds both from every installed map.

## Donors

`--donor` names a profile in `tools/level/data/donors/`, default `warthog`: the
actor, its tags, the rig's export, the bone parts ride, the seats and the handling
type. `ce_vehicle_numbers.py --baseline-map` reads the baseline from another map
when the vehicle's own lacks it, as Coldsnap lacks every stock vehicle.

Coldsnap's `jet2_v2` is the first build on `banshee`, on the test map `JTT`. It
draws, boards and flies, but launches itself on boarding (the Banshee's cruising
throttle) and its pilot sits low:

    python tools/level/ce_vehicle_numbers.py coldsnap.map "" vehicles/jet2/jet2_v2 <out> \
        --baseline vehicles/banshee/banshee_mp --baseline-map bloodgulch.map
    python tools/level/ce_vehicle.py <manifest.json> <out dir> --numbers <out>/numbers.json --donor banshee \
        --code JET --name jet --label Jet --variant jet_35=35 --variant jet_91=ce

- **Fit.** There are no wheels to fit to. The hull is centred on the Banshee's
  physics box and stood on its floor, 52 cm below the origin, and every part rides
  `Hull_M`, 136 cm up. The jet is 1.68 times the Banshee's length, but the rig stays
  at 1 (`--rig-scale`): nothing in the simulation depends on it, and a rider is
  drawn at the rig's scale. The Banshee's effects stay at its own size for now.
- **Damage.** The hull region's five permutations each hold every part, and the
  other regions are empty.
- **Pilot.** The Banshee's seat is `invisible`, so the clones clear that bit. The
  `banshee_d` marker takes CE's `driver`. The two boarding seats stay: `--resize`
  reaches root blocks only.
- **Numbers.** Shipped value times CE jet over CE `banshee_mp`: acceleration 600,
  deceleration 562.5, turn rate 14.5, top speed 90.9 (`ce`) against the 35 clamp.
- **Stock parts.** Collision and physics stay the Banshee's (`"chassis": "stock"`),
  so boarding means aiming where the Banshee would be. `vehicle_mute` does not
  apply: the Banshee's graph has no `SoundVariant_EngineLoop` statement.

## How it works

- **Tags.** `new-tag` clones the donor's skeleton, model and vehicle. Model
  variant `none` drops the Warthog's turret.
- **Blueprint.** `crates/ue-asset/examples/vehicle_actor.rs` clones the donor's
  actor under `/Game/MJOLNIR/Vehicles/`, so stock vehicles stay stock.
- **Parts.** Every donor part leaves the actor's `RuntimeRegions`, and the CE
  parts go in. Each rides a bone by name with its own `Transform`. Tyres ride
  the wheel bones, yawed a quarter turn because a wheel bone spins about its X
  axis. Parts that do not turn ride `b_chassis`.
- **Size.** The rig is scaled (0.589 for the Mongoose on the Warthog), which
  lands the donor's wheel bones on the CE tyres. Parts divide by that scale.
- **Look.** CE's shaders become cooked material instances on the `M_CE_*`
  masters, named by the mesh slots, so nothing happens at spawn and joiners get
  the same parts. The masters come from the CE runtime, which must be installed.
- **Collision.** `level machine-collision --plan` writes CE's hull and tyre BSPs
  into the donor's collision model, in the regions the plan names. The physics
  model keeps the donor's bodies with its shapes shrunk to the CE vehicle.
- **Handling.** Each number is the shipped Warthog's times CE Mongoose over CE
  Warthog: mass 1650, steering two thirds.
- **Lights.** The donor's lights ride VFX sockets of its rig, so they keep the
  Warthog's shape at the rig's scale and float off a CE body. Niagara components
  can't be edited in the cooked Blueprint (`NiagaraVariable` is refused), so
  `ce_vehicle_lights.py` adds a `lights` entry to `vehicle_sounds.json`, and
  `vehicle_sounds.lua` moves them onto CE's `headlight` and `taillight` markers at
  spawn and hides the Warthog's roof pair. That file sits in each level's folder.
- **Name.** The prompt's `{ItemName}` comes from no tag and no string table: the
  Blueprint's `BlamVehicleComponent.VehicleUIDataAsset` is read by
  `WBP_InteractPrompt`. `ce_vehicle_name.py` clones the donor's asset with the name
  as literal text and repoints the actor at it, so `--label` takes any name.
  Weapons and equipment have the same asset (`WeaponDataAsset`,
  `EquipmentDataAsset`). Keep `enter seat string` empty: a key outside
  `BlamStrings.csv` draws `<MISSING STRING TABLE ENTRY>`.
- **Markers.** Wheel, seat and entry markers in the skeleton clone reach the
  simulation. A skeleton node's translation does not reach the drawn bones.

## What was measured

| Check | Result |
|---|---|
| Vehicle tag clone, stock Blueprint | loads, boards, drives |
| Rewritten soft path in a shipped Blueprint | draws on the named bone |
| Cloned Blueprint | spawns, boards, drives |
| Mesh of our own through the component, with `Transform.Scale3D` | draws at that scale |
| Model variant `none` | no chaingun objects on the clone |
| Cooked material instances on `M_CE_*` masters | load and draw CE's textures and glass |
| CE collision on a driven vehicle, other regions empty | loads; a biped stops at the hull, 132 cm from centre, and pushes it |
| Shrunk physics model, mass 1650 | drives level, 18.7 wu in 2.6 s |
| Mongoose: seat marker, four wheels, forward, reverse, turning | works; 18.4 wu in 2.6 s, 89 degree turn |

## Riders

A rider's hands and feet are not in its seat animation alone: the mode's idle
carries IK chains to named markers on the vehicle. `ghost_d` wants
`spartan_hand_left/right` and `spartan_foot_left/right`, `warthog_d` wants
`spartan_d_*` and `warthog_p` wants `chief_p_ik_*`. A marker the vehicle lacks
does not fall back to the plain animation: the limb stretches at the map's
origin. A seat offset cannot fix that; it looks like a skew to one side.

The Spartan's `mongoose_d` is a stub and no shipped Spartan graph has a Mongoose
pose, so the driver borrows `ghost_d`, with four unused skeleton marker groups
renamed to what it wants (`tools/level/data/mongoose_rider_ik.sets`), at CE's
wrist and ankle joints from `M-driver idle`, not at its grips and pegs. Markers
sit on the joints, and the rider's position is drawn at the rig's scale, so a
marker move shows at 0.59 of its size. The `driver` marker's rotation pitches the
torso: 20 degrees gives CE's 46 degree lean, and the IK limbs stay put.

| Bone, cm from the actor | CE | In game |
|---|---|---|
| Hips | -41, 0, 118 | -42, -1, 119 |
| Head | 2, 1, 160 | 12, -1, 167 |
| Wrists | 22, +-38, 149 | 30, +-38, 150 |
| Ankles | -27, +-37, 76 | -22, +-38, 79 |

The passenger keeps `warthog_p`, whose three chains (`chief_p_ik_left_arm`,
`left_leg`, `right_leg`) match CE's `M-passenger` IK, so the right arm stays free
to aim. A limb marker is drawn at the rider's origin plus its offset from the
seat, so moving the seat by d moves a limb by 0.41 d the other way: move the seat
first, then the limbs. CE's boots sit inside the rear body; here they stand on
the deck, 39 cm above CE's joint, on purpose.

| Bone, cm from the actor | CE | In game |
|---|---|---|
| Hips | -108, 1, 148 | -107, -2, 148 |
| Head | -69, 5, 200 | -81, -17, 212 |
| Left wrist | -42, -11, 136 (IK marker) | -65, -13, 161 |
| Ankles | -87, -12, 70 / -83, 11, 69 | -86, -12, 109 / -82, 10, 109 |

The marker sets are measured for this vehicle: they do not generate yet.

## Boarding

The prompt and E need the crosshair on the vehicle's collision. A small hull
is easy to miss from a spawn that looks over it: no prompt means aim first, not
a broken seat.

## In a map

A CE map can park vehicles out of reach and teleport them out by script. Here a
vehicle spawns and returns at its placement, so `tools/level/ce_place_vehicles.py`
moves each one to its flag, on the ground, and makes the plan's custom ones `tag`
placements (`tools/level/data/yoy_vehicles.json` for Yoyorast). It also copies the
vehicle's containers with names `map pack` takes, such as
`pakchunk985-MJOLNIRVCOOK-YOY_P`: the contents keep the `VHT` paths, so the tested
bytes ship. `map pack` carries `vehicle_sounds.json` into `map/`. Without
MJOLNIRLevelLoader 0.10.0 and the CE runtime such a map drives silent, with its
lights floating.

## Not done

- The vehicle data asset keeps the Warthog's HUD icons. Kill feed text is not traced.
- 22 rifle rounds at the empty hull did no damage. Stock vehicles were not
  compared, so whether it takes damage at all is unknown. Destroying a wheel is
  untested.
- Handlebars and suspension arms do not move; tyres spin about 24% slow.
- The passenger's left hand stops about 34 cm short of CE's fin grip, and its torso has none of CE's 37 degree lean. Firing from the seat is untested.
- The Spartan is bigger than CE's cyborg, and the idle is the Ghost's, so it has no bob or lean into turns of CE's own.
- Top speed and handling are the ratio recipe, not yet felt out by a player.
- Not tested on a second PC. Yoyorast's build (above) is baked and packs, but has
  not been played yet. Its `rhog_1` stands within 1 wu of a ledge and an overhang.
- Reloading a level in the same world silences the old engine loops, and stock
  maps skip the spawn check: `vehicle_sounds.lua` passes its unit tests on both,
  but neither has run in game.
- Yoyorast holds the same packages as `VHT`, so the two sets must not be installed
  together. Roadworks' Mongooses are only on PC 1 and need these containers too.
- The installed vehicle model has 43 imports where build13's has 45, with the same
  tag payload. Yoyorast ships the installed one, since that was played. A rebake of
  the unchanged level differs from the installed bake by 22 bytes, cause unknown.
- The song clip CE sometimes plays at engine start (`lsnd` 1057) is left out, as it
  is likely licensed.
- Weapons: the same route should hold (first-person actors use the same
  component), but no weapon has been tried.
- Tooling: a `tag` placement is not checked against installed containers, so a
  wrong path bakes and fails in game. Duplicate plan regions and `material` or `node`
  indices are not validated. `ce_vehicle_lights.py` assumes four headlights and two
  taillights. `ce_vehicle.py` and `ce_vehicle_name.py` look up the `997` stub and
  raise if no map is installed. The latest fixes to `ce_vehicle.py`,
  `ce_vehicle_sounds.py` and `ce_vehicle_instances_editor.py` compile but have not
  been run.
