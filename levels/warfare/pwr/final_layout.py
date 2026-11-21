"""Derive native/map gameplay data from one hash-checked finalized terrain.

This writes layout.json only. It never modifies the master terrain or geometry.
Run after terrain finalization freezes, then regenerate the native header.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools/level"))
from heightfield import load_heightfield, sha256

POLICY = HERE / "runtime-layout-policy.json"


def finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(label + " must be finite")
    return float(value)


def position(value, label, count=3):
    if not isinstance(value, list) or len(value) != count:
        raise ValueError(label + " has invalid dimensions")
    return [finite(v, label) for v in value]


def derive(master, geometry, policy):
    if geometry.get("schema") != "pwr-terrain-geometry-v1" or geometry.get("coordinates") != "authoring_metres_z_up":
        raise ValueError("Unsupported finalized geometry")
    if policy.get("schema") != "pwr-runtime-layout-policy-v1" or (policy.get("protocol"), policy.get("layout_revision")) != (20569, 3):
        raise ValueError("Unsupported native layout policy")
    low, high = master.bounds_m
    if any(abs(v-w) > 1e-6 for v,w in zip((*low,*high), (-1000,-1000,1000,1000))):
        raise ValueError("Layout3 requires the finalized 2 km centered terrain")
    sites = {site["id"]: site for site in geometry["sites"]}
    if len(sites) != len(geometry["sites"]):
        raise ValueError("Duplicate finalized site")
    required = {"red_home", "blue_home", "warmup", "citadel_plateau", "capture_a", "capture_b", "capture_c"}
    if not required.issubset(sites):
        raise ValueError("Missing required finalized site")
    centers = {key: position(sites[key]["position_m"], key) for key in required}
    apron = position(policy["home_apron_offset_m"], "home apron", 2)
    spawn_offsets = [position(p, "spawn offset", 2) for p in policy["spawn_offsets_m"]]
    if len(spawn_offsets) != 8 or len({tuple(p) for p in spawn_offsets}) != 8:
        raise ValueError("Exactly eight distinct home spawns are required")
    home_lift, warmup_lift, capture_lift = (finite(policy[k], k) for k in
        ("home_plaza_lift_m", "warmup_plaza_lift_m", "capture_floor_lift_m"))
    spawn_lift = finite(policy["spawn_origin_above_floor_m"], "spawn origin")
    if min(home_lift, warmup_lift, capture_lift) < 0 or not .5 <= spawn_lift <= 2:
        raise ValueError("Invalid support/spawn clearance")
    def floor_at(point):
        ground = float(master.sample(point[0], point[1]))
        # A visual plaza must not bury a spawn or float it far above terrain.
        if point[2] < ground-.25 or point[2] > ground+5:
            raise ValueError("Finalized support floor disagrees with terrain at " + str(point))
        return point
    homes, spawns = {}, {}
    for team in ("red", "blue"):
        center = centers[team + "_home"]
        homes[team] = floor_at([center[0]+apron[0], center[1]+apron[1], center[2]+home_lift])
        spawns[team] = []
        for dx,dy in spawn_offsets:
            floor = floor_at([center[0]+dx, center[1]+dy, center[2]+home_lift])
            spawns[team].append([floor[0], floor[1], floor[2]+spawn_lift])
    warmup = centers["warmup"].copy(); warmup[2] += warmup_lift; floor_at(warmup)
    captures = []
    for label in "abc":
        point = centers["capture_"+label].copy(); point[2] += capture_lift
        captures.append(floor_at(point))
    radii = {finite(sites["capture_"+label]["radius_m"], "capture radius") for label in "abc"}
    if len(radii) != 1 or not 5 <= next(iter(radii)) <= 50:
        raise ValueError("Capture radii must be identical and within 5..50m")
    border, inset = (finite(policy[k], k) for k in ("play_border_m", "route_end_inset_m"))
    if not 0 < border < inset < 500:
        raise ValueError("Flight endpoint margin must exceed the play border")
    structure_height = finite(policy["maximum_authored_structure_height_m"], "structure envelope")
    clearance = finite(policy["flight_clearance_m"], "flight clearance")
    increment = finite(policy["flight_altitude_step_m"], "altitude step")
    ceiling_margin = finite(policy["flight_ceiling_margin_m"], "flight ceiling")
    if structure_height < 0 or clearance < 100 or increment <= 0 or ceiling_margin < 50:
        raise ValueError("Unsafe flight clearance policy")
    terrain_max = float(master.heights_m.max())
    obstacle_max = max(terrain_max, max(centers[k][2] for k in ("red_home", "blue_home", "citadel_plateau"))+structure_height)
    if "fixed_flight_altitude_m" in policy:
        altitude = finite(policy["fixed_flight_altitude_m"], "fixed flight altitude")
        if altitude != 550 or altitude < finite(policy["minimum_flight_altitude_m"], "minimum altitude"):
            raise ValueError("Layout3 frozen flight altitude must remain 550m")
        if ceiling_margin != 100:
            raise ValueError("Layout3 frozen ceiling must remain 650m")
        if obstacle_max > altitude-clearance:
            raise ValueError("Layout3 terrain/reserved structure envelope exceeds 400m; revise terrain or native contract")
        floor = -20
        if float(master.heights_m.min()) <= floor+2:
            raise ValueError("Layout3 terrain must remain above its frozen membership floor")
    else:
        altitude = max(finite(policy["minimum_flight_altitude_m"], "minimum altitude"), math.ceil((obstacle_max+clearance)/increment)*increment)
        floor = min(-20, math.floor(float(master.heights_m.min()))-20)
    ceiling = altitude+ceiling_margin
    lateral = finite(policy["route_lateral_fraction"], "route separation") * (high[1]-low[1])
    if not 0 < lateral < (high[1]-low[1])/2-border:
        raise ValueError("Invalid route separation")
    flights = {"red": {"start": [low[0]+inset,-lateral,altitude], "end": [high[0]-inset,-lateral,altitude], "yaw": 0},
               "blue": {"start": [high[0]-inset,lateral,altitude], "end": [low[0]+inset,lateral,altitude], "yaw": 180}}
    duration = finite(policy["insertion_seconds"], "insertion time")
    forced = finite(policy["forced_exit_seconds"], "forced exit")
    timeout = max(finite(policy["minimum_descent_timeout_seconds"], "descent timeout"), math.ceil(((altitude-floor)/6+15)/10)*10)
    if not 0 < forced < duration <= 500 or (high[0]-low[0]-2*inset)/duration > 30 or timeout > 300:
        raise ValueError("Unsafe flight or descent timing")
    play_low = [low[0]+border,low[1]+border,floor]
    play_high = [high[0]-border,high[1]-border,ceiling]
    for point in list(homes.values())+[warmup]+captures+sum(spawns.values(), []):
        if any(not play_low[k] < point[k] < play_high[k] for k in range(3)):
            raise ValueError("Gameplay placement lies outside play bounds")
    policy_sha = hashlib.sha256(json.dumps(policy,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return {"schema":"pwr-layout-v3", "code":"PWR", "title":"Pelican Warfare", "seed":policy["seed"],
            "protocol":policy["protocol"], "layout_revision":policy["layout_revision"],
            "coordinates":{"authoring":"metres, Z up", "unreal":"[100*x, -100*y, 100*z] centimetres", "blam":"metres / 3.048", "origin_m":[0,0,0]},
            "play_area_m":{"min":play_low,"max":play_high},
            "scenario_bounds_m":{"min":[*low,floor],"max":[*high,ceiling]},
            "homes_m":homes,"captures_m":captures,"capture_radius_m":next(iter(radii)),"warmup_m":warmup,"spawns_m":spawns,
            "flights_m":flights,"insertion_seconds":duration,"forced_exit_seconds":forced,"descent_timeout_seconds":timeout,
            "flight_envelope_status":"derived from final master and reserved structure envelope; requires live physics validation",
            "provenance":{"master_manifest_sha256":master.manifest_sha256,"master_height_sha256":master.metadata["height"]["sha256"],
                          "geometry_sha256":master.metadata["geometry_sha256"],"policy_sha256":policy_sha,
                          "terrain_max_m":terrain_max,"reserved_obstacle_max_m":obstacle_max,"minimum_flight_clearance_m":altitude-obstacle_max,
                          "placement_semantics":"homes/captures/warmup are support floors; spawn origins already include +0.8m; prepare_runtime named flags add home/capture +1.2m and warmup +0.8m"}}


def load_and_derive(master_path, policy_path=POLICY):
    master = load_heightfield(master_path)
    geometry_path = master.path.parent / master.metadata["geometry"]
    if sha256(geometry_path) != master.metadata["geometry_sha256"]:
        raise ValueError("Final geometry hash does not match master terrain")
    geometry = json.loads(geometry_path.read_text(encoding="utf-8-sig"))
    policy = json.loads(Path(policy_path).read_text(encoding="utf-8-sig"))
    result = derive(master, geometry, policy)
    # Check both sources again after sampling to reject concurrent finalization.
    if sha256(master.path) != master.manifest_sha256 or sha256(geometry_path) != master.metadata["geometry_sha256"]:
        raise ValueError("Final terrain changed during layout generation; wait for the freeze")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master",type=Path,default=HERE/"terrain/final-v3/final-master.json")
    parser.add_argument("--policy",type=Path,default=POLICY)
    parser.add_argument("--out",type=Path,default=HERE/"layout.json")
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args()
    result=load_and_derive(args.master,args.policy)
    text=json.dumps(result,indent=2)+"\n"
    if args.check:
        if not args.out.exists() or json.loads(args.out.read_text()) != result:
            raise SystemExit("PWR layout is stale relative to finalized terrain/policy")
    else:
        args.out.write_text(text,encoding="utf-8")
    print("PWR layout", "verified" if args.check else "generated",args.out)


if __name__=="__main__":
    main()
