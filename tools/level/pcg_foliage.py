"""Adapt actual UE PCG output into MJF3/exact HISM transforms and collision placements.

This module never selects points or invents random transforms. Those decisions
are outputs of MjolnirPCGLibrary's scheduled UPCGGraph in Unreal Editor.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def finite_vector(value, size, name):
    if not isinstance(value, list) or len(value) != size or any(
        isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in value
    ):
        raise ValueError(f"invalid {name}")
    return value


def validate_output(source, generated):
    if generated.get("schema") != 1 or not generated.get("generator", "").startswith("UE5.5 UPCGGraph"):
        raise ValueError("expected actual editor UPCGGraph output")
    candidates = {p["id"]: p for p in source["points"]}
    if len(candidates) != len(source["points"]) or generated.get("input_count") != len(candidates):
        raise ValueError("duplicate candidates or source count mismatch")
    selected, seen = [], set()
    for p in generated["points"]:
        pid = p["id"]
        if pid not in candidates or pid in seen:
            raise ValueError("unknown or duplicate generated point")
        seen.add(pid)
        original = candidates[pid]
        if not original.get("allowed", True) or original.get("biome_mask", 1) < .5 or original["density"] <= 0:
            raise ValueError(f"PCG violated exclusion for {pid}")
        position = finite_vector(p["position_cm"], 3, "position")
        expected = [original["position"][0] * 100, -original["position"][1] * 100, original["position"][2] * 100]
        if max(abs(a-b) for a, b in zip(position, expected)) > .001:
            raise ValueError(f"PCG moved projected collision point {pid}")
        quat = finite_vector(p["rotation_xyzw"], 4, "quaternion")
        scale = finite_vector(p["scale_xyz"], 3, "scale")
        if abs(sum(x*x for x in quat) - 1) > .0001 or min(scale) <= 0 or max(scale)-min(scale) > .00001:
            raise ValueError("expected normalized rotation and positive uniform scale")
        draw = p["asset_draw"]
        if not isinstance(draw, (int, float)) or not math.isfinite(draw) or not 0 <= draw <= 1:
            raise ValueError("invalid PCG asset draw")
        selected.append((original, p))
    return sorted(selected, key=lambda pair: pair[0]["id"])


def authored_yaw(quat):
    x, y, z, w = quat
    return (-math.degrees(math.atan2(2*(w*z+x*y), 1-2*(y*y+z*z)))) % 360


def choose_recipe(rule, draw):
    """Map the engine's existing asset draw onto an authored weighted palette."""
    if "recipes" not in rule:
        return rule.get("recipe")
    entries = rule["recipes"]
    if rule.get("recipe") or rule.get("meshes") or not isinstance(entries, list) or not entries:
        raise ValueError("Recipe palette must be nonempty and cannot also select meshes or one recipe")
    for entry in entries:
        if (not isinstance(entry, dict) or not isinstance(entry.get("recipe"), str) or not entry["recipe"]
                or isinstance(entry.get("weight"), bool) or not isinstance(entry.get("weight"), (int, float))
                or not math.isfinite(entry["weight"]) or entry["weight"] <= 0):
            raise ValueError("Invalid weighted PCG tree recipe")
    target = draw * sum(entry["weight"] for entry in entries)
    for entry in entries:
        target -= entry["weight"]
        if target < 0:
            return entry["recipe"]
    return entries[-1]["recipe"]


def adapt(source_path, generated_path, palette_path, output_dir, name="foliage"):
    source, generated, palette = load(source_path), load(generated_path), load(palette_path)
    if generated.get("source_sha256", digest(source_path)) != digest(source_path):
        raise ValueError("PCG source changed since generation")
    selected = validate_output(source, generated)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    groups, placements = {}, []
    for original, point in selected:
        kind = original.get("kind", "grass")
        rule = palette["kinds"][kind]
        meshes = rule.get("meshes", [])
        mesh = meshes[min(len(meshes)-1, int(point["asset_draw"]*len(meshes)))] if meshes else None
        q, scale = point["rotation_xyzw"], point["scale_xyz"][0]
        placement = {"id": original["id"], "position": original["position"],
                     "normal": original.get("normal", [0, 0, 1]), "yaw_degrees": authored_yaw(q),
                     "scale": scale, "mesh": mesh, "kind": kind,
                     "biome": original.get("biome"), "recipe": choose_recipe(rule, point["asset_draw"]),
                     "position_cm": point["position_cm"], "rotation_xyzw": q,
                     "scale_xyz": point["scale_xyz"]}
        placements.append(placement)
        if mesh:
            groups.setdefault((kind, mesh), []).append(point)
    ordered = sorted(groups)
    group_spec = []
    with (out / f"{name}.bin").open("wb") as stream:
        stream.write(b"MJF3" + struct.pack("<II", 3, len(ordered)))
        for index, (kind, mesh) in enumerate(ordered, 1):
            rule, points = palette["kinds"][kind], groups[kind, mesh]
            stream.write(struct.pack("<I", len(points)))
            exact = bytearray()
            for p in points:
                # MJF remains loader-readable; exact sidecar prevents yaw/scale
                # quantization from changing PCG's renderer/collision contract.
                yaw = (-authored_yaw(p["rotation_xyzw"])) % 360
                scale = p["scale_xyz"][0]
                stream.write(struct.pack("<fffBBbbBBB", *p["position_cm"],
                                         int(yaw/360*256) % 256, max(1, min(255, round(scale*100))),
                                         0, 0, 255, 255, 255))
                exact.extend(struct.pack("<10f", *p["position_cm"], *p["rotation_xyzw"], *p["scale_xyz"]))
            (out / f"{name}.bin.xf{index}").write_bytes(exact)
            group_spec.append({"mesh": mesh, "rule": rule.get("rule", kind),
                               "cull": rule.get("cull", [5000, 9000]), "bands": rule.get("bands", 1),
                               "shadow": rule.get("shadow", kind != "grass"),
                               "static": rule.get("static", True), "exact": True})
    (out / f"{name}.json").write_text(json.dumps({"file": f"{name}.bin", "groups": group_spec}, indent=2), encoding="utf-8")
    receipt = {"schema": 1, "generator": generated["generator"], "graph": generated["graph"],
               "seed": generated["seed"], "source_sha256": digest(source_path),
               "pcg_output_sha256": digest(generated_path), "input_count": len(source["points"]),
               "selected_count": len(placements), "instances": placements}
    (out / f"{name}.selected.json").write_text(json.dumps(receipt, separators=(",", ":")), encoding="utf-8")
    return receipt


def compare(source_path, first_path, second_path, different_seed_path=None):
    source, first, second = load(source_path), load(first_path), load(second_path)
    for result in (first, second):
        if result.get("source_sha256", digest(source_path)) != digest(source_path):
            raise ValueError("PCG source changed since generation")
    a, b = validate_output(source, first), validate_output(source, second)
    if a != b:
        raise ValueError("identical-seed PCG output differs")
    if different_seed_path:
        changed = validate_output(source, load(different_seed_path))
        if a == changed:
            raise ValueError("changed PCG seed had no effect")
    return {"schema": 1, "deterministic": True, "exclusions": True, "projection_preserved": True,
            "input_count": len(source["points"]), "output_count": len(a),
            "output_sha256": digest(first_path), "changed_seed_effect": bool(different_seed_path)}


def read_mjf_groups(spec_path):
    """Read complete validated groups before any in-place merge rewrites files."""
    spec_path = Path(spec_path)
    spec = load(spec_path)
    binary = spec_path.parent / spec["file"]
    raw = binary.read_bytes()
    if len(raw) < 12 or raw[:4] != b"MJF3": raise ValueError("PCG merge requires MJF3")
    version, count = struct.unpack_from("<II", raw, 4)
    if version != 3 or count != len(spec["groups"]): raise ValueError("MJF group count mismatch")
    at, result = 12, []
    for index, group in enumerate(spec["groups"], 1):
        if at+4 > len(raw): raise ValueError("truncated MJF count")
        n = struct.unpack_from("<I", raw, at)[0]
        end = at+4+n*19
        if end > len(raw): raise ValueError("truncated MJF records")
        sidecars = {}
        for flag, suffix, stride in (("exact","xf",40),("custom","xc",16)):
            if group.get(flag):
                data = Path(f"{binary}.{suffix}{index}").read_bytes()
                if len(data) != n*stride: raise ValueError("invalid MJF sidecar length")
                sidecars[suffix] = data
        result.append((group, raw[at:end], sidecars, n))
        at = end
    if at != len(raw): raise ValueError("trailing MJF bytes")
    return spec, result


def merge_foliage(base_path, addition_path):
    """Replace legacy grass with PCG output, retaining rock/cliff/detail groups.

    Idempotent: previously imported PCG groups carry an explicit marker and are
    replaced too. Sidecars are loaded before rewriting/renumbering any groups.
    """
    base_path, addition_path = Path(base_path), Path(addition_path)
    if base_path.resolve() == addition_path.resolve(): raise ValueError("cannot merge a file into itself")
    spec, base = read_mjf_groups(base_path)
    _, addition = read_mjf_groups(addition_path)
    replace = {"grass","short grass","tall grass","tufts","lip grass","weeds"}
    kept = [g for g in base if g[0].get("rule") not in replace and not g[0].get("pcg")]
    added = [(dict(g, pcg=True), payload, sidecars, n) for g,payload,sidecars,n in addition]
    final = kept + added
    binary = base_path.parent / spec["file"]
    raw = b"MJF3" + struct.pack("<II",3,len(final)) + b"".join(row[1] for row in final)
    binary.write_bytes(raw)
    for index, (_,_,sidecars,_) in enumerate(final,1):
        for suffix,data in sidecars.items(): Path(f"{binary}.{suffix}{index}").write_bytes(data)
    # Old sidecars can remain harmlessly unreferenced; do not remove unrelated files.
    spec["groups"] = [row[0] for row in final]
    base_path.write_text(json.dumps(spec,indent=2),encoding="utf-8")
    return {"kept_groups":len(kept),"pcg_groups":len(added),"pcg_instances":sum(row[3] for row in added)}


def proof(directory):
    out = Path(directory).resolve()
    out.mkdir(parents=True, exist_ok=True)
    points = []
    for i in range(256):
        x, y = (i % 16) * 8 - 60, (i // 16) * 8 - 60
        points.append({"id": i, "position": [x, y, 8 + .03*x], "normal": [-.03, 0, 1],
                       "density": 0 if i % 13 == 0 else (.6 if i % 3 else 1),
                       "biome_mask": 0 if abs(x) < 12 or abs(y) < 12 else 1,
                       "kind": "grass", "biome": "proof"})
    source = out / "candidates.json"
    source.write_text(json.dumps({"schema": 1, "points": points}), encoding="utf-8")
    jobs = [{"input": str(source), "output": str(out / f"{name}.json"),
             "graph": f"/Game/MJOLNIR/PCGAuthoring/PWR/PCG_Proof_{name}", "seed": seed}
            for name, seed in (("a", 20568), ("b", 20568), ("changed", 20569))]
    request = out / "request.json"
    request.write_text(json.dumps({"jobs": jobs}, indent=2), encoding="utf-8")
    return request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("proof"); p.add_argument("directory")
    p = sub.add_parser("adapt")
    for name in ("source", "generated", "palette", "output"): p.add_argument(name)
    p.add_argument("--name", default="foliage")
    p = sub.add_parser("verify")
    for name in ("source", "first", "second"): p.add_argument(name)
    p.add_argument("--changed-seed"); p.add_argument("--receipt")
    p = sub.add_parser("merge"); p.add_argument("base"); p.add_argument("addition")
    args = parser.parse_args()
    if args.command == "proof": print(proof(args.directory))
    elif args.command == "adapt":
        result = adapt(args.source, args.generated, args.palette, args.output, args.name)
        print(f"PCG adapter: {result['selected_count']} / {result['input_count']} points")
    elif args.command == "merge": print(json.dumps(merge_foliage(args.base,args.addition)))
    else:
        result = compare(args.source, args.first, args.second, args.changed_seed)
        if args.receipt: Path(args.receipt).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))


if __name__ == "__main__": main()
