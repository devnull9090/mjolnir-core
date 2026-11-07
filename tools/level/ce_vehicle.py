#!/usr/bin/env python3
"""Put a Custom Edition vehicle on a shipped chassis, as tags and a Blueprint.

    ce_vehicle.py <manifest.json> <out dir> --numbers numbers.json [--code VHT] [--name mongoose] [--donor warthog]

`manifest.json` is tools/level/ce_vehicle_mesh.py's: the vehicle's parts as
meshes, one per CE node. `numbers.json` is tools/level/ce_vehicle_numbers.py's:
the CE vehicle's handling and collision. `--donor` names a profile in
tools/level/data/donors/: what is known of one shipped chassis. This builds what
wears them, every container in the out dir:

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

A donor with no wheels (the Banshee) has nothing to fit its rig to. The CE hull
is centred on the donor's physics box and stood on its floor, every part rides
the profile's chassis bone, and the rig stays at `rig_scale`: nothing in the
simulation depends on it, and a rider is drawn at its scale. A profile with
`"chassis": "stock"` keeps the donor's collision and physics models. --variant
then builds one vehicle tag per entry, sharing the Blueprint and the model.
"""
import argparse
import json
import os
import re
import shutil
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

DONORS = os.path.join(HERE, "data", "donors")


def run(*args, capture=False):
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    r = subprocess.run([str(a) for a in args], env=env, text=True, encoding="utf-8",
                       errors="replace", capture_output=True)
    if r.returncode:
        sys.exit(f"{args[0]} failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout if capture else None


def region_rows(donor):
    """{region: {permutation: (static count, skeletal count)}} of the donor."""
    out = run(MJOLNIR, "ue", "get", "--package", donor["actor_package"], "--export", "0",
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


def fit(manifest, bones):
    """The rig's scale and the shift that puts its wheel bones on the CE tyres."""
    tyres = {}
    for node in manifest["nodes"]:
        m = re.match(r"frame ([lr][fb])_tire$", node["name"])
        if m:
            tyres[m.group(1)] = node["rest_vehicle"]["ue_cm"]["translation"]
    if set(tyres) != set(bones):
        sys.exit(f"expected four tyres, got {sorted(tyres)}")
    front = sum(tyres[k][0] for k in ("lf", "rf")) / 2
    back = sum(tyres[k][0] for k in ("lb", "rb")) / 2
    bone_front = sum(bones[k][0] for k in ("lf", "rf")) / 2
    bone_back = sum(bones[k][0] for k in ("lb", "rb")) / 2
    scale = (front - back) / (bone_front - bone_back)
    shift_x = scale * (bone_front + bone_back) / 2 - (front + back) / 2
    tyre_z = sum(t[2] for t in tyres.values()) / 4
    return scale, shift_x, tyres, tyre_z


def fit_hull(manifest, model):
    """The shift that centres the CE hull on the donor's physics box and stands
    it on the box's floor. Returns it with the length ratio, which is for the
    reader: a rig scale is a choice here, not a fit."""
    lo, hi = physics.polyhedra_box(model)
    box = manifest["bounds_cm"]
    shift_x = (lo[0] + hi[0]) / 2 * CM - (box["min"][0] + box["max"][0]) / 2
    shift_z = lo[2] * CM - box["min"][2]
    return shift_x, shift_z, (box["max"][0] - box["min"][0]) / ((hi[0] - lo[0]) * CM)


def actor_edits(manifest, donor, scale, shift_x, shift_z, lift):
    rows = region_rows(donor)
    edits = []
    wheels = donor["wheels"]
    regions = wheels["regions"] if wheels else {}
    bone = donor["chassis_bone"]
    chassis = donor["chassis_cm"]

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
        m = wheels and re.match(r"([lr][fb])_tire$", mesh["node"])
        if m:
            tyres[m.group(1)] = mesh
        else:
            body.append(mesh)
    for region, perms in rows.items():
        wheel = next((k for k, r in regions.items() if r == region), None)
        hull = region in donor["hull_regions"]
        for perm, (statics, skeletals) in perms.items():
            base = f"RuntimeRegions{{{region}}}.Permutations{{{perm}}}"
            if skeletals:
                edits.append(f"0|{base}.SkeletalMeshes|@len=0")
            want = 1 if wheel else len(body) if hull else 0
            if want and not statics:
                print(f"  {region}{{{perm}}} has no part to copy: it stays empty")
                continue
            if statics != want:
                edits.append(f"0|{base}.StaticMeshes|@len={want}")
            if wheel:
                mesh = tyres[wheel]
                part(f"{base}.StaticMeshes[0]", mesh["soft_path"], region, (0, 0, 0), wheels["yaw"],
                     mesh["component_scale"] / scale)
            elif hull:
                for i, mesh in enumerate(body):
                    rest = mesh["rest_vehicle"]["ue_cm"]
                    t = rest["translation"]
                    world = (t[0] + shift_x - chassis[0] * scale, t[1] - chassis[1] * scale,
                             t[2] + shift_z - lift - chassis[2] * scale)
                    part(f"{base}.StaticMeshes[{i}]", mesh["soft_path"], bone,
                         tuple(c / scale for c in world), rest["rotation_xyzw"],
                         mesh["component_scale"] / scale)
    leader = donor["leader"]
    edits += [
        f"{leader}|RelativeScale3D|{scale:.5f},{scale:.5f},{scale:.5f}",
        f"{leader}|RelativeLocation|0,0,{lift:.3f}",
        f"{leader}|bRenderInMainPass|false",
        f"{leader}|bRenderInDepthPass|false",
        f"{leader}|CastShadow|false",
    ]
    edits += [f"{x}|bVisible|false" for x in donor["hide"]]
    return edits


def wheel_markers(donor, scale, wheel_z):
    """{marker: position in wu} for the clone's wheels, at the drawn tyres."""
    bones = donor["wheels"]["bones"]
    return {marker: (bones[key][0] * scale / CM, -bones[key][1] * scale / CM, wheel_z)
            for key, marker in donor["wheels"]["markers"].items()}


def skeleton_sets(groups, donor, scale, wheel_z, seats, shift, offsets):
    """Wheels at the drawn tyres, riders on CE's seat markers, moved with the
    drawn parts."""
    def wu(cm):
        return cm / CM
    sets = list(wheel_markers(donor, scale, wheel_z).items()) if donor["wheels"] else []
    for seat in donor["seats"]:
        marker = seat["marker"]
        at = next((seats[n] for n in seat["ce"] if n in seats), None)
        if at is None:
            sys.exit(f"the CE model has no {marker} marker")
        lift = offsets[seat["offset"]]
        sets.append((marker, (at[0] + wu(shift[0]) + lift[0], at[1] + lift[1], at[2] + wu(shift[1]) + lift[2])))
    sets += list(donor["enter"].items())
    return [f"marker groups[{groups[n]}].markers[0].translation={p[0]:.6f},{p[1]:.6f},{p[2]:.6f}"
            for n, p in sets]


def collision_plan(manifest, donor, ce, folder, regions, materials, scale, shift_x, shift_z, wheel_z, keep_regions):
    """The BSPs and where they go: the hull at its drawn place, each tyre on
    the wheel bone that carries the drawn tyre."""
    rest = {n["name"]: n["rest_vehicle"]["ce_wu"]["translation"] for n in manifest["nodes"]}
    hull = rest["frame hull"]
    hull_at = [hull[0] + shift_x / CM, hull[1], hull[2] + shift_z / CM]

    def part(region, node, offset):
        return {"region": regions[region], "material": materials[region], "node": donor["root_node"],
                "bsp": os.path.join(folder, ce["collision"][node]), "offset": offset}

    parts = [part("hull", "frame hull", hull_at)]
    for key, region in donor["wheels"]["regions"].items():
        x, y = donor["wheels"]["bones"][key]
        parts.append(part(region, f"frame {key}_tire", [x * scale / CM, -y * scale / CM, wheel_z]))
    return {"blank_others": not keep_regions, "parts": parts}, hull_at


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("manifest")
    ap.add_argument("out")
    ap.add_argument("--code", default="VHT")
    ap.add_argument("--name", default="mongoose")
    ap.add_argument("--donor", default="warthog", help="a profile in tools/level/data/donors")
    ap.add_argument("--rig-scale", type=float, help="the hidden rig's scale on a donor with no wheels; default the profile's")
    ap.add_argument("--variant", action="append", default=[], metavar="TAG=SPEED",
                    help="a flyer: one vehicle tag of that leaf, at SPEED wu/s, or `ce` for CE's ratio")
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
    donor = json.load(open(os.path.join(DONORS, a.donor + ".json"), encoding="utf-8"))
    wheels = donor["wheels"]
    os.makedirs(a.out, exist_ok=True)

    donor_tag = donor["tag"]
    skeleton = values("skeleton_model", donor_tag + "-skeleton_model")
    vehicle = values("vehicle", donor["vehicle"])
    model = values("physics_model", donor_tag + "-physics_model")
    if wheels:
        scale, shift_x, tyres, tyre_z = fit(manifest, wheels["bones"])
        radius = max(m["extent_cm"][0] for m in manifest["meshes"] if m["node"].endswith("_tire"))  # a half size
        lift = max(0.0, wheels["ground_z"] + radius - scale * wheels["bone_z"])
        shift_z = (wheels["ground_z"] + radius) - tyre_z
    else:
        shift_x, shift_z, length = fit_hull(manifest, model)
        scale, lift = a.rig_scale or donor["rig_scale"], 0.0
        print(f"hull {length:.3f} times the donor's length")
    print(f"rig scale {scale:.4f}, parts shifted {shift_x:.1f} cm forward, {shift_z:.1f} up, rig lifted {lift:.1f}")

    leaf = "BP_" + a.code + a.name.capitalize()
    actor = f"/Game/MJOLNIR/Vehicles/{a.code}/{leaf}"
    edits = os.path.join(a.out, leaf + ".edits.txt")
    with open(edits, "w", encoding="utf-8") as f:
        f.write("\n".join(actor_edits(manifest, donor, scale, shift_x, shift_z, lift)) + "\n")
    uasset = os.path.join(a.out, leaf + ".uasset")
    print(run(os.path.join(EXAMPLES, "vehicle_actor.exe"), paks, donor["actor"], actor, uasset, "@" + edits,
              capture=True).strip())
    if donor["mute"]:
        print(run(os.path.join(EXAMPLES, "vehicle_mute.exe"), uasset, uasset, capture=True).strip())
    run(os.path.join(EXAMPLES, "package_add.exe"), paks, a.out, "--name",
        f"pakchunk987-MJOLNIR{a.code}-actor_P",
        *ce_vehicle_name.named(paks, a.out, uasset, a.label or a.name.capitalize()))
    # The game mounts a .utoc/.ucas pair only beside a .pak.
    shutil.copyfile(os.path.join(paks, "pakchunk115-Windows.pak"),
                    os.path.join(a.out, f"pakchunk987-MJOLNIR{a.code}-actor_P.pak"))

    tag = B.join(["objects", "mjolnir", a.code.lower(), a.name])
    groups = marker_groups(skeleton)

    wheel_z = tyre = None
    if wheels:
        # The donor's ground, in the object's space, under a sphere the tyre's size.
        marker = skeleton[f"marker groups[{groups['vh_wheel_front_left']}].markers[0].translation"]
        ground = physics.contact_height(vehicle, physics.vec(marker)[2])
        tyre = radius / CM
        wheel_z = ground + tyre
        print(f"ground {ground:.4f} wu, tyre radius {tyre:.4f}, wheel markers at z {wheel_z:.4f}")

    def set_file(name, sets):
        path = os.path.join(a.out, name + ".sets.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(sets) + "\n")
        return path

    def new(group, source, suffix, *args):
        name = f"pakchunk996-MJOLNIR{a.code}-{suffix}"
        to = () if "--to" in args else ("--to", tag)
        print(run(MJOLNIR, "new-tag", "--group", group, "--from", source, *to, "--out-dir", a.out,
                  "--name", name, *args, capture=True).splitlines()[0])
        stub = next(f for f in sorted(os.listdir(paks)) if re.match(r"pakchunk997-MJOLNIRMAP-.*_P\.pak$", f))
        with open(os.path.join(paks, stub), "rb") as src, open(os.path.join(a.out, name + "_P.pak"), "wb") as dst:
            dst.write(src.read())

    offsets = {"driver": a.driver_offset, "passenger": a.passenger_offset}
    sets = [x for s in skeleton_sets(groups, donor, scale, wheel_z, ce["markers"], (shift_x, shift_z), offsets)
            for x in ("--set", s)]
    if a.skel_set_file:
        sets += ["--set-file", a.skel_set_file]
    new("skeleton_model", donor_tag + "-skeleton_model", "skel", *sets)
    model_sets = ["--set", f"skeleton model=skel:{tag}"]
    if donor["chassis"] == "ce":
        coll = values("collision_model", donor_tag + "-collision_model")

        def names(block):
            return {coll[f"{block}[{i}].name"]: i for i in range(physics.count(coll, block))}

        folder = os.path.dirname(os.path.abspath(a.numbers))
        plan, hull_at = collision_plan(manifest, donor, ce, folder, names("regions"), names("materials"),
                                       scale, shift_x, shift_z, wheel_z, a.keep_regions)
        plan_path = os.path.join(a.out, "collision.plan.json")
        json.dump(plan, open(plan_path, "w", encoding="utf-8"), indent=1)
        payload = os.path.join(a.out, a.name + ".collision_model")
        print(run(MJOLNIR, "level", "machine-collision", "--plan", plan_path, "--donor",
                  donor_tag + "-collision_model", "--out", payload, capture=True).strip())

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
        new("collision_model", donor_tag + "-collision_model", "coll", "--payload", payload,
            "--set-file", set_file("coll", physics.pathfinding_sets(coll, scale)))
        boxes = None
        if wheels:
            clone = wheel_markers(donor, scale, wheel_z)
            boxes = ({n: physics.vec(skeleton[f"marker groups[{groups[n]}].markers[0].translation"]) for n in clone},
                     clone, tyre / float(vehicle[f"{physics.HAVOK}.friction points[0].radius"]))
        new("physics_model", donor_tag + "-physics_model", "phmo",
            "--set-file", set_file("phmo", physics.physics_sets(model, stretch, mass, centre, boxes)))
        model_sets += ["--set", f"collision model=coll:{tag}", "--set", f"physics_model=phmo:{tag}"]
    new("model", donor_tag + "-model", "model", *model_sets)

    def vehicle_tag(to, suffix, handling):
        sets = handling + a.vehi_set
        if a.driver_pose:
            sets.append(f"unit.seats[0].label={a.driver_pose}")
        for seat, bits in donor.get("clear_seat_flags", {}).items():
            path = f"unit.seats[{seat}].flags"
            sets.append(f"{path}={hex(int(vehicle[path].rsplit('(', 1)[1].rstrip(')'), 16) & ~bits)}")
        variant = ["--set", f"unit.object.default model variant={donor['model_variant']}"] if donor["model_variant"] else []
        new("vehicle", donor["vehicle"], suffix, "--to", to, "--asset-reference", actor,
            "--set", f"unit.object.model=hlmt:{tag}", *variant, "--set-file", set_file(suffix, sets))
        print("tag", to)

    if donor["physics"] == "jeep":
        vehicle_tag(tag, "vehi", physics.vehicle_sets(vehicle, ce, tyre))
    else:
        for entry in a.variant or [f"{a.name}=ce"]:
            leaf, speed = entry.split("=")
            to = B.join(["objects", "mjolnir", a.code.lower(), leaf])
            vehicle_tag(to, leaf, physics.fighter_sets(vehicle, ce, None if speed == "ce" else float(speed)))
    print("actor", actor, "container in", a.out)


if __name__ == "__main__":
    main()
