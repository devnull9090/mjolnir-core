"""Append reviewed armour cores to the verified Saturday collision and cook the native BSP."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / "tools/level"), str(HERE.parent)]
from merge_ce_collision import FORMATS, TWO_SIDED
from runtime_collision import contains_point, triangles_intersect_box, MAX_SURFACES
from stage_world_playtest import sha, jsonfile, write_json


def arrays(path, manifest):
    raw = memoryview(path.read_bytes())
    cursor = 0
    result = {}
    for key in manifest["array_order"]:
        count, = struct.unpack_from("<I", raw, cursor)
        size = struct.calcsize(FORMATS[key])
        if count != manifest["counts"][key] or size != manifest["element_sizes"][key]:
            raise ValueError("Unexpected collision layout for " + key)
        start = cursor + 4
        cursor = start + size * count
        result[key] = raw[start:cursor]
    if cursor != len(raw):
        raise ValueError("Trailing or truncated native source data")
    return result


def extend_arrays(triangles, original, material):
    added = defaultdict(bytearray)
    for i, triangle in enumerate(triangles):
        a,b,c = triangle
        norm = np.cross(b-a,c-a)
        length = np.linalg.norm(norm)
        if length < 1e-9:
            raise ValueError("Degenerate structural core face")
        norm /= length
        surface = i + original["surfaces"]
        vertex = 3*i + original["vertices"]
        edge = 3*i + original["edges"]
        plane = i + original["planes"]
        added["planes"] += struct.pack(FORMATS["planes"], *norm, norm@a)
        added["surfaces"] += struct.pack(FORMATS["surfaces"], plane, edge, TWO_SIDED, -1, material)
        for j, point in enumerate(triangle):
            k = (j+1) % 3
            added["edges"] += struct.pack(FORMATS["edges"], vertex+j, vertex+k, edge+k, -1, surface, -1)
            added["vertices"] += struct.pack(FORMATS["vertices"], *point, edge+j)
    return added


def verify_cores(art, cores):
    probes = {
        "west split monolith": (-2.9,24.1,33), "east split monolith": (2.9,24.3,33),
        "west observation pinnacle": (-24.5,22.7,20), "east observation pinnacle": (24.5,22.7,20),
        "west sweeping support": (-10.7,23.,17.2), "east sweeping support": (10.7,23.,17.2),
        "recessed aperture spine": (0.,24.6,21.),
    }
    passed = set()
    for site, records in cores.items():
        for name, triangle in records:
            boxes = {k:v["protected_bounds_m"] for k,v in art["clearances"][site].items()}
            if site == "green":
                boxes["open_crown_sightline"] = {"min":[-.02,14.,32.],"max":[.02,34.,36.]}
                for suffix, point in probes.items():
                    if name.endswith(suffix) and contains_point(triangle,point):
                        passed.add(suffix)
            for key, box in boxes.items():
                lo, hi = np.array(box["min"]), np.array(box["max"])
                if len(triangles_intersect_box(triangle, lo, hi)) or contains_point(triangle, (lo+hi)/2):
                    raise ValueError(f"Collision {name} blocks {key}")
    if passed != set(probes):
        raise ValueError(f"Missing closed physical cores at {set(probes)-passed}")
    return probes


def verify_native_surfaces(cooked, start, triangles, out):
    """Read the shipped definition ring, frame and Havok keys for each new face."""
    reader = ROOT/"target/release/examples/readback_surfaces.exe"
    native = np.empty_like(triangles)
    owners = np.zeros(len(triangles), dtype=np.int32)
    for piece in cooked["pieces"]:
        span = piece["source_surface_range"]
        if not span or span[1] <= start:
            continue
        first = max(span[0],start)
        begin,end = first-start,span[1]-start
        region = triangles[begin:end]
        bounds = piece["bounds_wu"]
        if np.any(region < np.array(bounds["min"])-1e-4) or np.any(region > np.array(bounds["max"])+1e-4):
            raise ValueError("Cooked native instance bounds miss actual added triangles")
        target = out/f"instance-{piece['instance']}-surfaces.f32"
        subprocess.run([str(reader),str(out/"pwr.sbsp"),str(piece["instance"]),str(first-span[0]),
                        str(span[1]-span[0]),str(target)],check=True)
        native[begin:end] = np.fromfile(target,dtype="<f4").reshape(-1,3,3)
        owners[begin:end] += 1
    if not np.all(owners == 1):
        raise ValueError("Cooked bodies do not own the added structural surfaces exactly once")
    distances = [np.linalg.norm(native-np.roll(triangles,r,axis=1),axis=2).max(axis=1) for r in range(3)]
    error_m = float(np.minimum.reduce(distances).max()) * 3.048
    if error_m > .0005:
        raise ValueError(f"Cooked physical polygons differ from authored triangles by {error_m} m")
    return error_m


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "art", "level", "out", "cli", "paks"):
        parser.add_argument("--"+key, type=Path, required=True)
    parser.add_argument("--oodle", type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    base = jsonfile(args.source / "native-collision-receipt.json")
    src = args.source / "collision_scene.json"
    original = jsonfile(src)
    binary = args.source/original["bin"]
    if (sha(binary),sha(src),sha(args.source/"pwr.sbsp")) != (
        base["source_binary_sha256"],base["source_manifest_sha256"],base["output_sha256"]):
        raise ValueError("Original world collision disagrees with the existing native receipt")
    before = arrays(binary, original)
    manifest = jsonfile(src)
    art = jsonfile(args.art/"base-polish.json")
    core_file = args.art/"solid-cores.json"
    if sha(core_file) != art["collision_sha256"]:
        raise ValueError("Collision export changed after Blender review")
    level = jsonfile(args.level)
    groups = {}
    anchors = {}
    triangles = []
    for team, objects in jsonfile(core_file).items():
        placement, = [r for r in level["decor"] if r["id"] == f"pwr_newbase_{team}_architecture"]
        if placement["scale"] != [1,1,1] or placement["rot"] != [0,0,0]:
            raise ValueError("Unknown base transform for " + team)
        anchors[team] = np.array(placement["pos"]) * np.array([.01,-.01,.01])
        groups[team] = []
        for ob in objects:
            points = np.array(ob["points"])[ob["faces"]]
            triangles.extend((points+anchors[team])/3.048)
            groups[team].append((ob["name"],len(points)))
    triangles = np.array(triangles)
    expected = len(triangles) + original["counts"]["surfaces"]
    if expected > MAX_SURFACES:
        raise ValueError(f"{expected} surfaces exceeds native budget")
    metal, = [m["index"] for m in manifest["materials"] if m.get("game_material") == "hard_metal_thick"]
    added = extend_arrays(triangles, original["counts"], metal)
    with (out/binary.name).open("xb") as stream:
        for key in manifest["array_order"]:
            manifest["counts"][key] += len(added[key])//struct.calcsize(FORMATS[key])
            stream.write(struct.pack("<I",manifest["counts"][key]))
            stream.write(before[key])
            stream.write(added[key])
    manifest["scenery_surfaces"]["objects"] += sum(len(v) for v in groups.values())
    manifest["scenery_surfaces"]["surfaces"] += len(triangles)
    for bound, op in (("min",np.minimum),("max",np.maximum)):
        extreme = getattr(triangles,bound)(axis=(0,1))
        manifest["world_bounds"][bound] = op(manifest["world_bounds"][bound],extreme).tolist()
    write_json(out/src.name,manifest)
    after = arrays(out/binary.name, manifest)
    for key in manifest["array_order"]:
        if after[key][:len(before[key])] != before[key]:
            raise ValueError(f"Previously playable {key} changed in the new source")
    first_edge = np.frombuffer(after["surfaces"][len(before["surfaces"]):], dtype="<i4").reshape(-1,3)[:,1]
    edges = np.frombuffer(after["edges"],dtype="<i4").reshape(-1,6)
    vertices = np.frombuffer(after["vertices"],dtype="<f4").reshape(-1,4)
    ring = np.stack([first_edge, edges[first_edge,2], edges[edges[first_edge,2],2]],axis=1)
    actual = vertices[edges[ring,0],:3]
    if not np.array_equal(actual,triangles.astype("<f4")) or not np.array_equal(edges[ring[:,2],2],first_edge):
        raise ValueError("Cook input failed triangulated edge-ring readback")
    readback = {}
    pos = 0
    for team, group in groups.items():
        readback[team] = []
        for name, n in group:
            readback[team].append((name,actual[pos:pos+n].astype(float)*3.048-anchors[team]))
            pos += n
    probes = verify_cores(art,readback)
    del before, after, actual, vertices, edges
    cmd = [args.cli,"level","collision",out/src.name,"--paks",args.paks,"--own-bsp","--bsp-index","0",
           "--receipt",out/"native-collision-receipt.json","--out",out/"pwr.sbsp"]
    if args.oodle:
        cmd.extend(["--oodle",args.oodle])
    with (out/"native.log").open("w") as logfile:
        subprocess.run(cmd,stdout=logfile,stderr=subprocess.STDOUT,check=True)
    cooked = jsonfile(out/"native-collision-receipt.json")
    if (cooked["source_surfaces"] != expected or cooked["output_sha256"] != sha(out/"pwr.sbsp")
        or cooked["source_binary_sha256"] != sha(out/binary.name) or cooked["source_manifest_sha256"] != sha(out/src.name)
        or cooked["delta_wu"] != [0,0,0] or cooked["tail_linked_in_host"]):
        raise ValueError("Native cook disagrees with audited core input")
    start = original["counts"]["surfaces"]
    error_m = verify_native_surfaces(cooked,start,triangles,out)
    write_json(out/"collision-proof.json",{"source_receipt_sha256":sha(args.source/"native-collision-receipt.json"),
        "base_input":base["source_binary_sha256"],"base_sbsp":base["output_sha256"],"sbsp":cooked["output_sha256"],
        "preserved_source_surfaces":start,"added_surfaces":len(triangles),"core_objects":groups,
        "site_origins_blender_m":{site:xyz.tolist() for site,xyz in anchors.items()},
        "core_export_sha256":sha(core_file),"source_arrays_prefix_exact":True,"compiled_instance_bounds_checked":True,
        "crown_inside_probes":probes,"protected_art_and_collision_clear":True,"live_physics_tested":False,
        "cooked_surface_maximum_error_m":error_m,"root_and_definition_havok_verified_per_face":True})


if __name__ == "__main__":
    main()
