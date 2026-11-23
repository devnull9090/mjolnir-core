"""Fail closed before reusing PWR layout3 with a replacement terrain.

--terrain-only is an intermediate gate; only a matching prepared level and
compiled collision receipt can produce layout3_permitted=true. No game calls,
installs, source rewrites, or automatic contract/version changes occur here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools/level"))
sys.path.insert(0, str(ROOT / "native/lobby"))
from heightfield import load_heightfield, sha256
from generate_warfare_layout import marker_points, validate as validate_native_layout

CONTRACT = HERE / "native-contract-v3/contract.json"
# Accepted artifacts, never values inferred from the candidate being checked.
ACCEPTED_RUNTIME = "814c7a8b3796394f2a8027c10b9577424acff5c23972d65265f9d86f3b7fd3ec"
ACCEPTED_GEOMETRY = "2bad0fc72f4204932d8f66e2fc096e8d47f4a0c901d4a246a5ac0bb0b425f7c4"
ACCEPTED_LAYOUT_CANONICAL = "97cea925cada8e9f527bfd0eb550e96f983060b4f4b8ad1bc19cc1a1b64f415b"
ACCEPTED_LEVEL_GAMEPLAY = "476515ca94247ba38aa722cf69e52453455d9a9d66e4c861ed13a13a94a10274"
LAYOUT_KEYS = ("schema", "code", "seed", "protocol", "layout_revision", "coordinates",
    "play_area_m", "scenario_bounds_m", "homes_m", "captures_m", "capture_radius_m",
    "warmup_m", "spawns_m", "flights_m", "insertion_seconds", "forced_exit_seconds", "descent_timeout_seconds")
ENCODING_KEYS = ("components", "quads_per_component", "size", "origin_cm", "quad_cm", "centre_cm", "z_scale")
MASK_THRESHOLDS = {"road": .001, "bases": .5, "flat": .5, "water": .01, "shore": .5}
ACCEPTED_ENVELOPE = {"flight_altitude_m": 550, "ceiling_m": 650,
    "maximum_terrain_reserved_structure_m": 400, "reserved_structure_height_m": 120,
    "maximum_accepted_static_collision_m": 418.2203327636719}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def differences(expected, actual, label="contract"):
    """Exact semantic numeric comparison; no five-centimetre runtime tolerance."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict): return [label + ": expected an object"]
        result = [label + ": key set changed"] if expected.keys() != actual.keys() else []
        for key in expected.keys() & actual.keys():
            result.extend(differences(expected[key], actual[key], label + "." + key))
        return sorted(result)
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual): return [label + ": sequence length changed"]
        return [error for index, (a, b) in enumerate(zip(expected, actual))
                for error in differences(a, b, f"{label}[{index}]")]
    if isinstance(expected, bool) != isinstance(actual, bool) or expected != actual:
        return [f"{label}: {expected!r} != {actual!r}"]
    return []


def assert_equal(expected, actual, label):
    errors = differences(expected, actual, label)
    require(not errors, "; ".join(errors[:12]))


def gameplay_layout(layout):
    validate_native_layout(layout)
    require(set(layout) == set(LAYOUT_KEYS) | {"title", "flight_envelope_status", "provenance", "reinforcement", "capture_candidates_m", "transport_routes_m"},
            "Unreviewed layout fields require an explicit gameplay contract decision")
    return {key: layout[key] for key in LAYOUT_KEYS}


def gameplay_level(level):
    # All native scenario inputs are frozen. Only terrain acceptance flags are
    # replaceable: their geometry/hash MUST change with new compiled chunks.
    blam = json.loads(json.dumps(level["blam"]))
    blam["cutscene_flags"] = [flag for flag in blam.get("cutscene_flags", [])
                              if not flag.get("name", "").startswith("terrain_probe_")]
    return {**{key: level[key] for key in ("schema_version", "name", "game", "multiplayer",
            "warfare", "variant", "modes", "koth_hills", "vehicle_sets")},
            "canvas": level["canvas"], "blam": blam}


def support_points(layout, frozen_level):
    points = list(layout["homes_m"].values()) + [layout["warmup_m"]] + layout["captures_m"]
    points += [point for side in layout["spawns_m"].values() for point in side]
    # Aircraft have no ground pad; every ground fleet/pickup/start location does.
    for key in ("vehicles", "weapons", "equipment", "objects", "player_starts"):
        for item in frozen_level["blam"].get(key, []):
            if item.get("placed") is False or "pelican" in item.get("type", ""):
                continue
            if "pos" in item:
                p = item["pos"]
                points.append([p[0] / 100, -p[1] / 100, p[2] / 100])
    return np.asarray(points, dtype=float)


def required_protected_mask(baseline, layout, frozen_level):
    mask = np.zeros(baseline.heights_m.shape, dtype=bool)
    for name, threshold in MASK_THRESHOLDS.items():
        require(name in baseline.masks, "Frozen baseline is missing mask " + name)
        mask |= baseline.masks[name] > threshold
    width, height = baseline.dimensions
    for point in support_points(layout, frozen_level):
        u = (point[0] - baseline.origin_m[0]) / baseline.spacing_m[0]
        v = (point[1] - baseline.origin_m[1]) / baseline.spacing_m[1]
        require(0 <= u <= width-1 and 0 <= v <= height-1, "Frozen support lies outside baseline")
        i, j = min(math.floor(u), width-2), min(math.floor(v), height-2)
        mask[j:j+2, i:i+2] = True
    # Two whole cells preserve support interpolation and adjacent contact.
    padded = np.pad(mask, 2)
    return np.logical_or.reduce([padded[y:y+height, x:x+width] for y in range(5) for x in range(5)])


def load_frozen_contract(path=CONTRACT):
    path = Path(path).resolve()
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    require(doc["schema"] == "pwr-frozen-native-contract-v1", "Unsupported frozen contract")
    assert_equal(ACCEPTED_ENVELOPE, doc["envelope"], "accepted v3 flight envelope")
    def read_reference(key):
        spec = doc[key]; target = (path.parent / spec["path"]).resolve()
        require(sha256(target) == spec["sha256"], "Frozen reference changed: " + key)
        return target
    layout = json.loads(read_reference("layout").read_text())
    level = json.loads(read_reference("level_gameplay").read_text())
    require(doc["level_gameplay"]["sha256"] == ACCEPTED_LEVEL_GAMEPLAY, "Gameplay reference is not accepted v3")
    baseline = load_heightfield(read_reference("runtime_master"))
    geometry_path = read_reference("geometry")
    require(baseline.manifest_sha256 == ACCEPTED_RUNTIME and sha256(geometry_path) == ACCEPTED_GEOMETRY
            and canonical_sha(layout) == ACCEPTED_LAYOUT_CANONICAL, "References are not the accepted v3 artifacts")
    require(baseline.metadata["height"]["sha256"] == doc["runtime_height_sha256"], "Frozen runtime height changed")
    required = required_protected_mask(baseline, layout, level)
    require(hashlib.sha256(required.tobytes()).hexdigest() == doc["required_protected_mask_sha256"],
            "Frozen protected-mask definition changed")
    return doc, layout, level, baseline, json.loads(geometry_path.read_text()), required


def check_terrain(candidate, candidate_layout, frozen, frozen_layout, frozen_level, baseline, geometry, required):
    assert_equal(gameplay_layout(frozen_layout), gameplay_layout(candidate_layout), "native gameplay")
    assert_equal(marker_points(frozen_layout), marker_points(candidate_layout), "native marker coordinates")
    require(candidate.metadata.get("surface_interpolation") == "triangle_nw_se", "Runtime terrain must use UE triangle interpolation")
    assert_equal(list(baseline.dimensions), list(candidate.dimensions), "runtime dimensions")
    assert_equal(list(baseline.origin_m), list(candidate.origin_m), "runtime origin")
    assert_equal(list(baseline.spacing_m), list(candidate.spacing_m), "runtime spacing")
    require(candidate.metadata["geometry_sha256"] == frozen["geometry"]["sha256"], "Protected geometry hash changed")
    geometry_path = candidate.path.parent / candidate.metadata["geometry"]
    require(sha256(geometry_path) == frozen["geometry"]["sha256"], "Protected geometry bytes changed")
    allowed_layout_sources = {candidate.manifest_sha256, candidate.metadata.get("runtime_source", {}).get("manifest_sha256")}
    require(candidate_layout["provenance"]["master_manifest_sha256"] in allowed_layout_sources,
            "Candidate layout provenance is stale relative to the candidate runtime/source master")
    envelope = frozen["envelope"]
    terrain_max = float(candidate.heights_m.max())
    sites = {s["id"]: s for s in geometry["sites"]}
    reserved_max = max(sites[name]["position_m"][2] for name in ("red_home", "blue_home", "citadel_plateau")) + envelope["reserved_structure_height_m"]
    require(max(terrain_max, reserved_max) <= envelope["maximum_terrain_reserved_structure_m"],
            "Frozen terrain/reserved-structure obstacle envelope exceeded")
    require(float(candidate.heights_m.min()) >= frozen_layout["scenario_bounds_m"]["min"][2], "Terrain falls outside the native shell")
    encoding = candidate.metadata.get("landscape_encoding", {})
    assert_equal({k: baseline.metadata["landscape_encoding"][k] for k in ENCODING_KEYS},
                 {k: encoding.get(k) for k in ENCODING_KEYS}, "Landscape encoding")
    raw_path = candidate.path.with_suffix(".r16")
    require(raw_path.exists() and sha256(raw_path) == encoding.get("r16_sha256"), "Missing or changed actual Landscape R16")
    raw = np.fromfile(raw_path, dtype="<u2")
    require(raw.size == candidate.heights_m.size, "Landscape R16 dimensions changed")
    decoded = (encoding["centre_cm"] + (raw.reshape(candidate.heights_m.shape).astype(float)-32768)*encoding["z_scale"]/128)[::-1]/100
    require(np.array_equal(decoded, candidate.heights_m), "Runtime master is not the actual encoded Landscape surface")
    is_baseline = candidate.manifest_sha256 == baseline.manifest_sha256
    if is_baseline:
        protected = required
    else:
        preservation = candidate.metadata.get("preservation", {})
        require(preservation.get("baseline_manifest_sha256") == baseline.manifest_sha256
                and preservation.get("baseline_height_sha256") == baseline.metadata["height"]["sha256"]
                and preservation.get("geometry_sha256") == frozen["geometry"]["sha256"]
                and preservation.get("layout_sha256") == frozen["layout"]["sha256"], "Missing/stale frozen preservation provenance")
        name = preservation.get("protected_mask")
        require(name in candidate.masks, "Protected mask missing")
        mask = candidate.masks[name]
        require(np.all((mask == 0) | (mask == 1)), "Protected mask must be exact binary data")
        protected = mask == 1
        require(np.all(protected[required]), "Candidate protection silently omits required roads/sites/support cells")
    require(np.array_equal(candidate.heights_m[protected], baseline.heights_m[protected]),
            "Protected runtime floor vertices changed")
    points = support_points(frozen_layout, frozen_level)
    require(np.array_equal(candidate.sample(points[:, 0], points[:, 1]), baseline.sample(points[:, 0], points[:, 1])),
            "Native gameplay support interpolation changed")
    return {"candidate_is_baseline": is_baseline, "runtime_manifest_sha256": candidate.manifest_sha256,
            "runtime_height_sha256": candidate.metadata["height"]["sha256"], "protected_vertices": int(protected.sum()),
            "required_vertices": int(required.sum()), "protected_max_abs_error_m": 0,
            "support_samples": len(points), "terrain_max_m": terrain_max, "reserved_structure_max_m": reserved_max,
            "flight_altitude_m": envelope["flight_altitude_m"], "ceiling_m": envelope["ceiling_m"]}


def check_collision(receipt_path, frozen):
    path = Path(receipt_path).resolve(); doc = json.loads(path.read_text())
    require(doc.get("schema") == "mjolnir-collision-pieces-v1" and doc.get("delta_wu") == [0, 0, 0], "Unsupported collision receipt")
    source = Path(doc["source_manifest"])
    require(sha256(source) == doc["source_manifest_sha256"] and sha256(source.with_suffix(".bin")) == doc["source_binary_sha256"]
            and sha256(Path(doc["output"])) == doc["output_sha256"], "Compiled collision receipt hashes are stale")
    heights = [piece["bounds_wu"]["max"][2]*3.048 for piece in doc["pieces"]]
    require(heights and all(math.isfinite(z) for z in heights), "Invalid static collision bounds")
    maximum = max(heights)
    require(maximum <= frozen["envelope"]["maximum_accepted_static_collision_m"] + .001,
            "Static collision exceeds the accepted v3 obstacle envelope; new envelope review required")
    return {"receipt_sha256": sha256(path), "compiled_collision_sha256": doc["output_sha256"],
            "static_collision_max_m": maximum, "global_clearance_above_static_m": 550-maximum}


def check_probe_plan(plan_path, candidate, candidate_layout_path, collision, prepared_level):
    plan_path = Path(plan_path)
    probe = json.loads(plan_path.read_text())
    require(probe.get("schema") == "pwr-terrain-probe-v1" and probe.get("protocol") == 20569
            and probe.get("layout_revision") == 3 and probe["master_manifest_sha256"] == candidate.manifest_sha256
            and probe["height_sha256"] == candidate.metadata["height"]["sha256"]
            and probe["provenance"].get("compiled_boundaries_verified") is True, "Probe plan belongs to another terrain")
    provenance = probe["provenance"]
    require(len(probe["probes"]) == 12 and len({p["flag"] for p in probe["probes"]}) == 12,
            "Expected twelve distinct compiled terrain probe flags")
    require(provenance["receipt_sha256"] == collision["receipt_sha256"]
            and provenance["compiled_tag_sha256"] == collision["compiled_collision_sha256"], "Probe/collision receipts disagree")
    for key in ("ordered", "terrain_receipt"):
        require(sha256(Path(provenance[key+"_path"])) == provenance[key+"_sha256"], "Verified probe source changed: " + key)
    if "adaptive_proof_path" in provenance:
        require(sha256(Path(provenance["adaptive_proof_path"]))==provenance["adaptive_proof_sha256"],"Adaptive boundary proof changed")
    require(provenance["layout_sha256"] == sha256(candidate_layout_path), "Probe layout is stale")
    flags = prepared_level["blam"]["cutscene_flags"]
    require(sum(f["name"] == "terrain_probe_hash_"+sha256(plan_path)[:12] for f in flags) == 1,
            "Prepared level has a stale probe-plan stamp")
    for point in probe["probes"]:
        matching = [f for f in flags if f["name"] == point["flag"]]
        require(len(matching) == 1, "Missing/duplicate terrain probe flag")
        x, y, z = point["position_m"]
        assert_equal([100*x, -100*y, 100*z], matching[0]["pos"], "terrain probe coordinates")
        assert_equal(point["yaw"], matching[0]["yaw"], "terrain probe yaw")
    return sha256(plan_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--level", type=Path)
    parser.add_argument("--collision-receipt", type=Path)
    parser.add_argument("--probe-plan", type=Path)
    parser.add_argument("--vehicle-spawn-policy", type=Path,
                        help="Explicit sealed eight-vehicle spawn-height exception; all other native fields remain exact")
    parser.add_argument("--terrain-only", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    require(args.terrain_only or (args.level and args.collision_receipt and args.probe_plan),
            "Full acceptance needs --level, --collision-receipt and --probe-plan; use explicit --terrain-only for the intermediate gate")
    frozen, layout, level, baseline, geometry, required = load_frozen_contract()
    candidate = load_heightfield(args.runtime)
    report = check_terrain(candidate, json.loads(args.layout.read_text()), frozen, layout, level, baseline, geometry, required)
    require(not args.vehicle_spawn_policy or args.level, "A vehicle-spawn correction requires a prepared level")
    if args.level:
        prepared = json.loads(args.level.read_text())
        if args.vehicle_spawn_policy:
            from vehicle_spawn_policy import validate_level
            prepared, report["vehicle_spawn_policy"] = validate_level(prepared, args.vehicle_spawn_policy)
        assert_equal(level, gameplay_level(prepared), "prepared gameplay scenario")
    if args.collision_receipt:
        report["collision"] = check_collision(args.collision_receipt, frozen)
    if args.probe_plan:
        # This plan was built by exhaustive ordered-triangle/source verification;
        # its receipt must bind to this candidate, never to the accepted old mesh.
        require(args.level and args.collision_receipt, "Probe acceptance requires prepared level and compiled collision")
        report["probe_plan_sha256"] = check_probe_plan(args.probe_plan, candidate, args.layout,
            report["collision"], json.loads(args.level.read_text()))
    report = {"schema": "pwr-native-contract-preflight-v1", "protocol": 20569, "layout_revision": 3,
              "terrain_contract_compatible": True, "layout3_permitted": not args.terrain_only,
              "live_acceptance_required": True, **report}
    text = json.dumps(report, indent=2)+"\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
