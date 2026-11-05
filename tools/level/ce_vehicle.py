#!/usr/bin/env python3
"""Put a Custom Edition vehicle on a shipped chassis, as tags and a Blueprint.

    ce_vehicle.py <manifest.json> <out dir> --numbers numbers.json [--code VHT] [--name mongoose]

`manifest.json` is tools/level/ce_vehicle_mesh.py's: the vehicle's parts as
meshes, one per CE node. `numbers.json` is tools/level/ce_vehicle_numbers.py's:
the CE vehicle's handling and collision. This builds what wears them, every
container in the out dir:

- a clone of the donor Blueprint (crates/ue-asset/examples/vehicle_actor.rs)
  with every donor part removed from its RuntimeRegions and the CE parts in,
  its rig hidden and scaled so the donor's wheel bones land on the CE tyres;
- clones of the donor's skeleton, model and vehicle tags, with the wheel,
  seat and entry markers moved. Markers reach the simulation; a skeleton
  node's translation does not reach the drawn bones, which is why the rig is
  scaled rather than its nodes moved;
- the CE collision in the donor's hull and wheel regions and the donor's other
  regions emptied, and the donor's physics model stretched to the CE hull with
  CE's handling on the vehicle (tools/level/ce_vehicle_physics.py).

Collision hangs from the root node, in the object's space. The simulation's
nodes keep the donor's size, so wheel regions cannot ride wheel nodes: a tyre's
BSP stands where the drawn tyre rests and does not turn.

Rigid parts ride a bone by name. A wheel bone turns about its X axis, which
points across the vehicle, so a tyre is yawed a quarter turn onto it. Parts
that do not turn ride b_chassis, the object's own origin and rotation.
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ce_vehicle_name  # noqa: E402
import ce_vehicle_physics as physics  # noqa: E402

REPO = os.path.join(HERE, "..", "..")
MJOLNIR = os.path.join(REPO, "target", "release", "mjolnir.exe")
EXAMPLES = os.path.join(REPO, "target", "release", "examples")
B = chr(92)
CLASS = "/Game/Blueprints/CVW/BPC_StaticMesh.BPC_StaticMesh_C"
CM = 304.8

# The Warthog chassis: wheel bones in the actor's space (cm, measured in
# game), and the exports of its Blueprint this edits.
DONOR_ACTOR = "BP_WarthogVehicleActor"
DONOR_TAG = "human/warthog/warthog"
DONOR_VEHICLE = "warthog/warthog-vehicle"
BONES = {"lf": (204.8, -123.9), "rf": (203.3, 126.2), "lb": (-188.1, -129.3), "rb": (-189.6, 126.8)}
BONE_Z = 72.0
GROUND_Z = -9.0
LEADER, ANTENNA = 126, 127
ROOT_NODE = 2
WHEEL_REGION = {"lf": "wheel_front_left", "rf": "wheel_front_right",
                "lb": "wheel_back_left", "rb": "wheel_back_right"}
YAW90 = (0.0, 0.0, 0.70710678, 0.70710678)


def run(*args, capture=False):
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    r = subprocess.run([str(a) for a in args], env=env, text=True, encoding="utf-8",
                       errors="replace", capture_output=True)
    if r.returncode:
        sys.exit(f"{args[0]} failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout if capture else None


def region_rows():
    """{region: {permutation: (static count, skeletal count)}} of the donor."""
    out = run(MJOLNIR, "ue", "get", "--package", DONOR_ACTOR, "--export", "0",
              "--filter", "RuntimeRegions{", capture=True)
    rows = {}
    for m in re.finditer(r"RuntimeRegions\{([^}]+)\}\.Permutations\{([^}]+)\}\.(Static|Skeletal)Meshes = \[(\d+) item", out):
        region, perm, kind, n = m.groups()
        cell = rows.setdefault(region, {}).setdefault(perm, [0, 0])
        cell[0 if kind == "Static" else 1] = int(n)
    if not rows:
        sys.exit("no RuntimeRegions rows in the donor")
    return rows


def values(group, tag):
    """A donor tag as {path: value}."""
    tree = json.loads(run(MJOLNIR, "values", "--group", group, "--tag", tag, "--json",
                          "--elements", "65536", capture=True))
    return physics.flatten(tree["fields"])


def marker_groups(skeleton):
    """{marker name: group index} of the donor skeleton."""
    return {skeleton[f"marker groups[{i}].name"]: i for i in range(physics.count(skeleton, "marker groups"))}


def fit(manifest):
    """The rig's scale and the shift that puts its wheel bones on the CE tyres."""
    tyres = {}
    for node in manifest["nodes"]:
        m = re.match(r"frame ([lr][fb])_tire$", node["name"])
        if m:
            tyres[m.group(1)] = node["rest_vehicle"]["ue_cm"]["translation"]
    if set(tyres) != set(BONES):
        sys.exit(f"expected four tyres, got {sorted(tyres)}")
    front = sum(tyres[k][0] for k in ("lf", "rf")) / 2
    back = sum(tyres[k][0] for k in ("lb", "rb")) / 2
    bone_front = sum(BONES[k][0] for k in ("lf", "rf")) / 2
    bone_back = sum(BONES[k][0] for k in ("lb", "rb")) / 2
    scale = (front - back) / (bone_front - bone_back)
    shift_x = scale * (bone_front + bone_back) / 2 - (front + back) / 2
    tyre_z = sum(t[2] for t in tyres.values()) / 4
    return scale, shift_x, tyres, tyre_z


def actor_edits(manifest, scale, shift_x, shift_z, lift):
    rows = region_rows()
    edits = []

    def part(prefix, mesh, bone, translation, rotation, size):
        edits.extend([
            f"0|{prefix}.Asset|{mesh}",
            f"0|{prefix}.Class|{CLASS}",
            f"0|{prefix}.ParentBoneName|{bone}",
            f"0|{prefix}.MaterialOverrides|@len=0",
            f"0|{prefix}.ComponentTags|@len=0",
            f"0|{prefix}.Transform.Translation|{translation[0]:.4f},{translation[1]:.4f},{translation[2]:.4f}",
            f"0|{prefix}.Transform.Rotation|{rotation[0]:.6f},{rotation[1]:.6f},{rotation[2]:.6f},{rotation[3]:.6f}",
            f"0|{prefix}.Transform.Scale3D|{size:.5f},{size:.5f},{size:.5f}",
        ])

    body, tyres = [], {}
    for mesh in manifest["meshes"]:
        m = re.match(r"([lr][fb])_tire$", mesh["node"])
        if m:
            tyres[m.group(1)] = mesh
        else:
            body.append(mesh)
    for region, perms in rows.items():
        wheel = next((k for k, r in WHEEL_REGION.items() if r == region), None)
        for perm, (statics, skeletals) in perms.items():
            base = f"RuntimeRegions{{{region}}}.Permutations{{{perm}}}"
            if skeletals:
                edits.append(f"0|{base}.SkeletalMeshes|@len=0")
            want = 1 if wheel else len(body) if region == "hull" else 0
            if want and not statics:
                print(f"  {region}{{{perm}}} has no part to copy: it stays empty")
                continue
            if statics != want:
                edits.append(f"0|{base}.StaticMeshes|@len={want}")
            if wheel:
                mesh = tyres[wheel]
                part(f"{base}.StaticMeshes[0]", mesh["soft_path"], region, (0, 0, 0), YAW90,
                     mesh["component_scale"] / scale)
            elif region == "hull":
                for i, mesh in enumerate(body):
                    rest = mesh["rest_vehicle"]["ue_cm"]
                    t = rest["translation"]
                    world = (t[0] + shift_x, t[1], t[2] + shift_z - lift)
                    part(f"{base}.StaticMeshes[{i}]", mesh["soft_path"], "b_chassis",
                         tuple(c / scale for c in world), rest["rotation_xyzw"],
                         mesh["component_scale"] / scale)
    edits += [
        f"{LEADER}|RelativeScale3D|{scale:.5f},{scale:.5f},{scale:.5f}",
        f"{LEADER}|RelativeLocation|0,0,{lift:.3f}",
        f"{LEADER}|bRenderInMainPass|false",
        f"{LEADER}|bRenderInDepthPass|false",
        f"{LEADER}|CastShadow|false",
        f"{ANTENNA}|bVisible|false",
    ]
    return edits


def skeleton_sets(groups, scale, wheel_z, seats, shift, driver_offset, passenger_offset):
    """Wheels at the drawn tyres, riders on CE's seat markers, moved with the
    drawn parts."""
    def wu(cm):
        return cm / CM
    sets = []
    for key, marker in (("lf", "vh_wheel_front_left"), ("rf", "vh_wheel_front_right"),
                        ("lb", "vh_wheel_back_left"), ("rb", "vh_wheel_back_right")):
        x, y = BONES[key]
        sets.append((marker, (wu(x * scale), wu(-y * scale), wheel_z)))
    for marker, names in (("driver", ("driver",)), ("passenger", ("gunner", "passenger"))):
        at = next((seats[n] for n in names if n in seats), None)
        if at is None:
            sys.exit(f"the CE model has no {marker} marker")
        lift = driver_offset if marker == "driver" else passenger_offset
        sets.append((marker, (at[0] + wu(shift[0]) + lift[0], at[1] + lift[1], at[2] + wu(shift[1]) + lift[2])))
    sets += [
        ("driver_enter", (-0.10, 0.34, 0.36)),
        ("passenger_enter", (-0.10, -0.34, 0.36)),
    ]
    return [f"marker groups[{groups[n]}].markers[0].translation={p[0]:.6f},{p[1]:.6f},{p[2]:.6f}"
            for n, p in sets]


def collision_plan(manifest, ce, folder, regions, materials, scale, shift_x, shift_z, wheel_z, keep_regions):
    """The BSPs and where they go: the hull at its drawn place, each tyre on
    the wheel bone that carries the drawn tyre."""
    rest = {n["name"]: n["rest_vehicle"]["ce_wu"]["translation"] for n in manifest["nodes"]}
    hull = rest["frame hull"]
    hull_at = [hull[0] + shift_x / CM, hull[1], hull[2] + shift_z / CM]

    def part(region, node, offset):
        return {"region": regions[region], "material": materials[region], "node": ROOT_NODE,
                "bsp": os.path.join(folder, ce["collision"][node]), "offset": offset}

    parts = [part("hull", "frame hull", hull_at)]
    for key, region in WHEEL_REGION.items():
        x, y = BONES[key]
        parts.append(part(region, f"frame {key}_tire", [x * scale / CM, -y * scale / CM, wheel_z]))
    return {"blank_others": not keep_regions, "parts": parts}, hull_at


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("manifest")
    ap.add_argument("out")
    ap.add_argument("--code", default="VHT")
    ap.add_argument("--name", default="mongoose")
    ap.add_argument("--numbers", required=True, help="ce_vehicle_numbers.py's numbers.json")
    ap.add_argument("--driver-pose", help="the rider animation mode of the driver seat, e.g. ghost_d for a straddle")
    ap.add_argument("--driver-offset", type=lambda t: tuple(float(v) for v in t.split(",")), default=(0.0, 0.0, 0.0),
                    metavar="X,Y,Z", help="wu added to CE's driver marker: the shipped pose's root is not CE's "
                                          "(ghost_d wants -0.02,0,0.262, measured against CE's camera and foot markers)")
    ap.add_argument("--passenger-offset", type=lambda t: tuple(float(v) for v in t.split(",")), default=(0.0, 0.0, 0.0),
                    metavar="X,Y,Z", help="wu added to CE's passenger marker (warthog_p on the Mongoose: -0.407,0,0.097)")
    ap.add_argument("--skel-set-file", help="further skeleton edits: rider IK markers")
    ap.add_argument("--label", help="the name the game shows, as in Drive Mongoose; default --name")
    ap.add_argument("--keep-regions", action="store_true",
                    help="leave the donor's other collision regions as they are, not empty")
    ap.add_argument("--vehi-set", action="append", default=[], metavar="PATH=VALUE",
                    help="one more vehicle edit, last so it wins, for tuning")
    a = ap.parse_args()
    paks = os.environ.get("HCE_PAKS") or sys.exit("set HCE_PAKS")
    manifest = json.load(open(a.manifest, encoding="utf-8"))
    ce = json.load(open(a.numbers, encoding="utf-8"))
    os.makedirs(a.out, exist_ok=True)

    scale, shift_x, tyres, tyre_z = fit(manifest)
    radius = max(m["extent_cm"][0] for m in manifest["meshes"] if m["node"].endswith("_tire"))  # a half size
    lift = max(0.0, GROUND_Z + radius - scale * BONE_Z)
    shift_z = (GROUND_Z + radius) - tyre_z
    print(f"rig scale {scale:.4f}, parts shifted {shift_x:.1f} cm forward, {shift_z:.1f} up, rig lifted {lift:.1f}")

    leaf = "BP_" + a.code + a.name.capitalize()
    actor = f"/Game/MJOLNIR/Vehicles/{a.code}/{leaf}"
    edits = os.path.join(a.out, leaf + ".edits.txt")
    with open(edits, "w", encoding="utf-8") as f:
        f.write("\n".join(actor_edits(manifest, scale, shift_x, shift_z, lift)) + "\n")
    uasset = os.path.join(a.out, leaf + ".uasset")
    print(run(os.path.join(EXAMPLES, "vehicle_actor.exe"), paks, DONOR_ACTOR, actor, uasset, "@" + edits,
              capture=True).strip())
    print(run(os.path.join(EXAMPLES, "vehicle_mute.exe"), uasset, uasset, capture=True).strip())
    run(os.path.join(EXAMPLES, "package_add.exe"), paks, a.out, "--name",
        f"pakchunk987-MJOLNIR{a.code}-actor_P",
        *ce_vehicle_name.named(paks, a.out, uasset, a.label or a.name.capitalize()))

    tag = B.join(["objects", "mjolnir", a.code.lower(), a.name])
    skeleton = values("skeleton_model", DONOR_TAG + "-skeleton_model")
    vehicle = values("vehicle", DONOR_VEHICLE)
    model = values("physics_model", DONOR_TAG + "-physics_model")
    coll = values("collision_model", DONOR_TAG + "-collision_model")
    groups = marker_groups(skeleton)

    # The donor's ground, in the object's space, under a sphere the tyre's size.
    marker = skeleton[f"marker groups[{groups['vh_wheel_front_left']}].markers[0].translation"]
    ground = physics.contact_height(vehicle, physics.vec(marker)[2])
    tyre = radius / CM
    wheel_z = ground + tyre
    print(f"ground {ground:.4f} wu, tyre radius {tyre:.4f}, wheel markers at z {wheel_z:.4f}")

    def names(block):
        return {coll[f"{block}[{i}].name"]: i for i in range(physics.count(coll, block))}

    folder = os.path.dirname(os.path.abspath(a.numbers))
    plan, hull_at = collision_plan(manifest, ce, folder, names("regions"), names("materials"),
                                   scale, shift_x, shift_z, wheel_z, a.keep_regions)
    plan_path = os.path.join(a.out, "collision.plan.json")
    json.dump(plan, open(plan_path, "w", encoding="utf-8"), indent=1)
    payload = os.path.join(a.out, a.name + ".collision_model")
    print(run(MJOLNIR, "level", "machine-collision", "--plan", plan_path, "--donor",
              DONOR_TAG + "-collision_model", "--out", payload, capture=True).strip())

    bounds = json.load(open(plan["parts"][0]["bsp"], encoding="utf-8"))["world_bounds"]
    stretch = physics.Stretch(*physics.shape_box(model),
                              [bounds["min"][k] + hull_at[k] for k in range(3)],
                              [bounds["max"][k] + hull_at[k] for k in range(3)])
    shipped = physics.shipped_centre_of_mass(model)
    centre = [ce["vehicle"]["center_of_mass"][k] + scale * (shipped[k] - ce["baseline"]["center_of_mass"][k])
              for k in range(3)]
    centre = [centre[0] + shift_x / CM, centre[1], centre[2] + shift_z / CM]
    mass = float(model["mass"]) * physics.ratios(ce)["mass"]
    print(f"mass {mass:g}, shapes stretched {[round(x, 4) for x in stretch.scale]}, "
          f"centre of mass {[round(x, 4) for x in centre]}")

    def set_file(name, sets):
        path = os.path.join(a.out, name + ".sets.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(sets) + "\n")
        return path

    def new(group, donor, suffix, *args):
        name = f"pakchunk996-MJOLNIR{a.code}-{suffix}"
        print(run(MJOLNIR, "new-tag", "--group", group, "--from", donor, "--to", tag, "--out-dir", a.out,
                  "--name", name, *args, capture=True).splitlines()[0])
        stub = next(f for f in sorted(os.listdir(paks)) if re.match(r"pakchunk997-MJOLNIRMAP-.*_P\.pak$", f))
        with open(os.path.join(paks, stub), "rb") as src, open(os.path.join(a.out, name + "_P.pak"), "wb") as dst:
            dst.write(src.read())

    sets = [x for s in skeleton_sets(groups, scale, wheel_z, ce["markers"], (shift_x, shift_z),
                                                 a.driver_offset, a.passenger_offset) for x in ("--set", s)]
    if a.skel_set_file:
        sets += ["--set-file", a.skel_set_file]
    new("skeleton_model", DONOR_TAG + "-skeleton_model", "skel", *sets)
    new("collision_model", DONOR_TAG + "-collision_model", "coll", "--payload", payload,
        "--set-file", set_file("coll", physics.pathfinding_sets(coll, scale)))
    new("physics_model", DONOR_TAG + "-physics_model", "phmo",
        "--set-file", set_file("phmo", physics.physics_sets(model, stretch, mass, centre)))
    new("model", DONOR_TAG + "-model", "model", "--set", f"skeleton model=skel:{tag}",
        "--set", f"collision model=coll:{tag}", "--set", f"physics_model=phmo:{tag}")
    vehi = physics.vehicle_sets(vehicle, ce, tyre) + a.vehi_set
    if a.driver_pose:
        vehi.append(f"unit.seats[0].label={a.driver_pose}")
    new("vehicle", DONOR_VEHICLE, "vehi", "--asset-reference", actor,
        "--set", f"unit.object.model=hlmt:{tag}", "--set", "unit.object.default model variant=none",
        "--set-file", set_file("vehi", vehi))
    print("tag", tag)
    print("actor", actor, "container in", a.out)


if __name__ == "__main__":
    main()
