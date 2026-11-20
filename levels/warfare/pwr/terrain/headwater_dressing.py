"""Seat the shipped .31 headwater rocks and PCG foliage on the revised terrain."""
import argparse
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile

import numpy as np
from scipy.spatial import ConvexHull, cKDTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "tools/level"))
from b30_collision import rotator_matrix
from heightfield import load_heightfield, sha256
from pcg_foliage import read_mjf_groups
from finalize_terrain import inside_polygon

PLAYTEST = ROOT / "out/pwr/sweep-polish/round31/saturday.31/map-input"
EXACT = ROOT / "out/pwr/visual-v7/landscape-grass-pilot-v7land/filtered-foliage"
HULLS = ROOT / "out/pwr/pcg-v3/rocks/hulls"
TREES = ROOT / "out/pwr/visual-v6/scenery/trees/trees.selected.json"
HEADWATER = ROOT / "out/pwr/headwater-lake"
RECORD = np.dtype([("xyz", "<f4", 3), ("attributes", "V7")])
UE_TO_WORLD = np.array([.01, -.01])
EPS = 1.e-7

# Reuse identifiable drowned boulders and their exact native hulls. Larger
# rocks frame the outlet, small irregular fragments pick out the spring and
# the steeper west margin. Leave the shallow eastern beach mostly open.
ANCHORS = {
    "pcg_v4_shore_35933": ("outlet_east", -291., 820.),
    "pcg_v4_shore_35934": ("outlet_west", -308., 819.),
    "pcg_v4_shore_36124": ("outlet_west", -312., 826.),
    "pcg_v4_shore_37101": ("west_bank", -419., 899.),
    "pcg_v4_shore_37296": ("west_bank", -431., 929.),
    "pcg_v4_shore_37688": ("spring_west", -403., 982.),
    "pcg_v4_shore_37689": ("spring_east", -396., 981.),
    "pcg_v4_shore_37890": ("spring_east", -391., 976.),
    "pcg_v4_shore_38085": ("spring_toe", -386., 970.),
    "pwr_v6_riparian_6200039": ("west_bank", -433., 941.),
    "pwr_v6_riparian_6200040": ("west_bank", -426., 957.),
    "pwr_v6_riparian_6200041": ("west_bank", -418., 961.),
    "pwr_v6_riparian_6200042": ("outlet_west", -307., 813.),
    "pwr_v6_riparian_6200043": ("outlet_east", -290., 829.),
    "pwr_v6_riparian_6200197": ("west_bank", -408., 880.),
    "pcg_rock_8866": ("east_bank", -310., 916.),
}

# Stock .31 hulls reused in the .34 outlet: the buried eastern anchor, a lower
# upstream companion, and the smaller stone at the downstream end of its wake.
FLOW_ROCKS = {
    "pcg_rock_8680": ("river_anchor", -293.4, 822.6, 2.40),
    "pcg_v4_shore_35539": ("river_companion", -304.8, 826.9, 1.20),
    "pcg_v4_shore_35934": ("river_riffle", -299.9, 810.4, .73),
}

# Direct translations of .31 actors. The crown heights and positions were fit
# against the clipped, projected native hulls in the registered outlet view.
APRON_FLOW_ROCKS = {
    "pcg_rock_8680": ("river_anchor", -292.8065, 820.5370, 3.0488),
    "pcg_rock_8104": ("river_companion", -300.7001, 816.0938, 2.04),
    "pcg_v4_shore_35539": ("river_riffle", -297.4878, 807.2065, .9867),
}
APRON_DRY_ANCHORS = {
    "pcg_v4_shore_35933": ("east_bank", -275., 845.),
    "pcg_v4_shore_35934": ("west_bank", -328., 815.),
    "pcg_v4_shore_36124": ("west_bank", -345., 821.),
    "pwr_v6_riparian_6200042": ("west_bank", -318., 806.),
    "pwr_v6_riparian_6200043": ("east_bank", -274., 834.),
}


def write_json(path, value):
    path.write_text(json.dumps(value, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def local_mask(xy, bounds):
    return np.all((xy >= bounds[0]) & (xy <= bounds[1]), axis=-1)


def sample(field, xy):
    return field.sample(xy[..., 0], xy[..., 1])


def mask(field, name, xy):
    return field.sample_mask(name, xy[..., 0], xy[..., 1])


def world_foot(row, cache):
    mesh = row["mesh"]
    if mesh not in cache:
        path = HULLS / (mesh.rsplit(".", 1)[-1] + ".json")
        hull = read(path)
        if hull["mesh"] != mesh:
            raise ValueError(f"Mesh and native hull differ for {mesh}")
        cache[mesh] = np.asarray(hull["points"], dtype=float)
    return cache[mesh] * np.asarray(row["scale"]) @ rotator_matrix(*row["rot"])


def seat_rock(row, rotated, xy, old_field, field):
    # Preserve the depth of its buried physical toe, sampled across its
    # actual rotated native hull (the actor pivot can sit well off-centre).
    footprint = rotated[:, :2] * UE_TO_WORLD
    old_xy = np.asarray(row["pos"][:2]) * UE_TO_WORLD
    old_floor = sample(old_field, old_xy + footprint)
    old_above = old_floor * -100. + row["pos"][2] + rotated[:, 2]
    height = np.ptp(rotated[:, 2])
    buried = np.clip(-old_above.min(), .08*height, .38*height)
    new_floor = sample(field, xy + footprint)
    new_z = float(np.max(new_floor*100. - rotated[:, 2]) - buried)
    above = new_z + rotated[:, 2] - new_floor*100.
    if not above.min() < 0 < above.max():
        raise ValueError(f"{row['id']} would float or disappear")
    return new_z, (float(above.min()/100), float(above.max()/100))


def pick(anchor, footprint, radius, occupied, trees, field):
    # Prefer the hand-placed point, shifting only if a hull occupies the flow
    # opening, a tree root or another rock. Search in metres, deterministically.
    offsets = [(x*x+y*y, x, y) for x in range(-5, 6) for y in range(-5, 6)]
    for _, dx, dy in sorted(offsets):
        xy = np.asarray(anchor) + [dx, dy]
        if trees.query(xy)[0] < radius + 1.0:
            continue
        if any(np.linalg.norm(xy - centre) < radius + r + .35 for centre, r in occupied):
            continue
        check = xy + footprint
        if mask(field, "water", xy) > .15 or np.max(mask(field, "water", check)) > .57:
            continue
        if np.max(mask(field, "road", check)) > .01 or np.max(mask(field, "bases", check)) > .01:
            continue
        return xy
    raise ValueError(f"No dry and clear shore rock placement near {anchor}")


def dress_rocks(decor, old_field, field, bounds, trees, river=None, apron=False):
    cache, moved, footprints, occupied, pending = {}, [], [], [], []
    result = copy.deepcopy(decor)
    anchors = dict(ANCHORS)
    flow_rocks = APRON_FLOW_ROCKS if apron else FLOW_ROCKS
    if apron:
        anchors.update(APRON_DRY_ANCHORS)
    if river is not None:
        anchors.update({rid:site[:3] for rid,site in flow_rocks.items()})
    fluid = []
    for i, row in enumerate(decor):
        xy = np.asarray(row["pos"][:2])*UE_TO_WORLD
        if not local_mask(xy, bounds):
            continue
        if "SM_Rock_Glacial_" not in row["mesh"]:
            if abs(sample(old_field, xy)-sample(field, xy)) > EPS:
                raise ValueError(f"Additional altered-ground decor requires review: {row['id']}")
            continue
        rotated = world_foot(row, cache)
        foot = rotated[:, :2]*UE_TO_WORLD
        radius = np.linalg.norm(foot,axis=1).max()
        site = anchors.get(row["id"])
        delta = sample(field, xy+foot) - sample(old_field, xy+foot)
        # Unaffected physical footprints retain every original bit.
        if site or np.any(abs(delta) > EPS) or abs(sample(field, xy)-sample(old_field, xy)) > EPS:
            pending.append((i, row, xy, rotated, site))
        if not site:
            occupied.append((xy, radius))
    if {row["id"] for _,row,_,_,site in pending if site} != set(anchors):
        raise ValueError("The sealed map differs from surveyed rock IDs")
    # Reserve the three surveyed obstacle sites before choosing dry surrounds.
    if river is not None:
        for _,row,_,rotated,site in pending:
            if row["id"] in flow_rocks:
                occupied.append((np.asarray(site[1:]),np.linalg.norm(rotated[:,:2]*UE_TO_WORLD,axis=1).max()))
    for i,row,old_xy,rotated,site in pending:
        foot = rotated[:, :2]*UE_TO_WORLD
        radius = np.linalg.norm(foot,axis=1).max()
        xy = old_xy
        flow = river is not None and row["id"] in flow_rocks
        if site:
            if flow:
                xy = np.asarray(site[1:])
                if (np.max(mask(field,"water",xy+foot)) < .5 or trees.query(xy)[0]<radius+1.
                    or any(np.max(mask(field,k,xy+foot))>.01 for k in ("road","bases"))):
                    raise ValueError("Invalid in-channel rock position for "+row["id"])
            else:
                xy = pick(site[1:], foot, radius, occupied, trees, field)
                occupied.append((xy, radius))
        z, exposure = seat_rock(row, rotated, xy, old_field, field)
        if flow:
            station = np.linalg.norm(river[:,:2]-xy,axis=1).argmin()
            surface = float(river[station,2])
            if apron:
                from outlet_apron import surface as apron_surface
                surface = float(apron_surface(xy,river))
            crown_z = 100.*(surface+flow_rocks[row["id"]][3])-rotated[:,2].max()
            z = crown_z if apron else min(z,crown_z)
            world = np.column_stack((xy+foot,(z+rotated[:,2])/100.))
            above = world[:,2]-sample(field,world[:,:2])
            exposure = (float(above.min()),float(above.max()))
            if not exposure[0]<0<exposure[1] or world[:,2].max() <= surface+.18:
                raise ValueError("An outlet rock is floating or submerged: "+row["id"])
            hull = read(HULLS/(row["mesh"].rsplit(".",1)[-1]+".json"))
            fluid.append(dict(id=row["id"],role=site[0],mesh=row["mesh"],
                centre_m=xy.tolist(),surface_z_m=surface,top_z_m=world[:,2].max(),
                vertices_m=world.tolist(),faces=hull["faces"],
                footprint_m=(xy+foot[ConvexHull(foot).vertices]).tolist()))
        pos = [*row["pos"][:2], z]
        if site:
            pos[:2] = (xy/UE_TO_WORLD).tolist()
            footprints.append((xy, radius, xy+foot[ConvexHull(foot).vertices]))
        result[i]["pos"] = pos
        delta = np.asarray(pos)-np.asarray(row["pos"])
        moved.append(dict(level_index=i, id=row["id"], mesh=row["mesh"], old_pos_ue_cm=row["pos"],
                          new_pos_ue_cm=pos, delta_ue_cm=delta.tolist(), rot=row["rot"],scale=row["scale"],
                          location=site[0] if site else "original_bank", hull_height_vs_ground_m=exposure))
    return result, moved, footprints, fluid


def grass_changes(records, old_field, field, bounds, footprints):
    xyz = records["xyz"]
    world = xyz[:, :2].astype(float)*UE_TO_WORLD
    indices = np.flatnonzero(local_mask(world, bounds))
    xy = world[indices]
    z_old, z_new = sample(old_field, xy), sample(field, xy)
    old_wet, wet = mask(old_field, "water", xy), mask(field, "water", xy)
    old_shore, shore = mask(old_field, "shore", xy), mask(field, "shore", xy)
    edited = (abs(z_new-z_old)>EPS) | (abs(old_wet-wet)>EPS) | (abs(old_shore-shore)>EPS)
    # Keep existing dry vegetation above the strand. Below it, clip the
    # existing PCG points rather than reseeding its wind or patch pattern.
    below = edited & (wet >= .15)
    inside_rock = np.zeros(len(xy), dtype=bool)
    for centre, radius, polygon in footprints:
        near = np.flatnonzero(np.linalg.norm(xy-centre, axis=1) <= radius+.01)
        inside_rock[near] |= inside_polygon(*xy[near].T, polygon)
    removed = below | inside_rock
    target_z = (xyz[indices, 2].astype(float) + 100.*(z_new-z_old)).astype("<f4")
    moves = ~removed & (target_z != xyz[indices, 2])
    return (indices[removed], indices[moves], target_z[moves],
            {"wet_removed":int(below.sum()),"additional_rock_exclusions":int((inside_rock & ~below).sum())})


def dress_grass(out, level, old_field, field, bounds, footprints):
    if sha256(PLAYTEST/"foliage.bin") != sha256(EXACT/"foliage.bin"):
        raise ValueError("The full-precision sidecars are for a different playtest")
    spec, groups = read_mjf_groups(EXACT/"foliage.json")
    if spec["groups"] != level["foliage"]["groups"]:
        raise ValueError("PCG group ordering differs from sealed level")
    ledger, provenance = [], {}
    with (out/"foliage.bin").open("wb") as stream:
        stream.write(b"MJF3"+struct.pack("<II",3,len(groups)))
        for i,(group,payload,sidecars,count) in enumerate(groups):
            original = np.frombuffer(payload,RECORD, offset=4)
            exact = np.frombuffer(sidecars["xf"],"<f4").reshape(count,10).copy()
            if len(original) != count or not np.array_equal(exact[:,:3],original["xyz"]):
                raise ValueError(f"Packed and exact positions differ in {group['mesh']}")
            removed, moved, target_z, stats = grass_changes(original,old_field,field,bounds,footprints)
            records = original.copy()
            records["xyz"][moved,2] = target_z
            exact[moved,2] = target_z
            keep = np.ones(count,dtype=bool)
            keep[removed] = False
            unchanged = keep.copy()
            unchanged[moved] = False
            if records[unchanged].tobytes() != original[unchanged].tobytes():
                raise ValueError("Changed a protected foliage record")
            stream.write(struct.pack("<I",int(keep.sum())))
            stream.write(records[keep].tobytes())
            filename = f"foliage.bin.xf{i+1}"
            (out/filename).write_bytes(exact[keep].tobytes())
            provenance[filename] = sha256(EXACT/filename)
            ledger.append(dict(group_index=i,mesh=group["mesh"],source_count=count,target_count=int(keep.sum()),
                removed_source_indices=removed.tolist(),
                moved=[dict(source_index=int(j), old_pos_ue_cm=original["xyz"][j].tolist(),
                            new_pos_ue_cm=records["xyz"][j].tolist()) for j in moved], **stats))
    return ledger,provenance


def build(out, terrain=None):
    old_field = load_heightfield(HERE/"runtime-v5/runtime-master.json")
    terrain = terrain or HEADWATER/"terrain"
    field = load_heightfield(terrain/"runtime-master.json")
    seal = read(terrain/"headwater-terrain.receipt.json")
    if [old_field.manifest_sha256,field.manifest_sha256] != [seal["parent_terrain_sha256"],seal["runtime_manifest_sha256"]]:
        raise ValueError("Incorrect terrain pair")
    # Expand by four native grid cells and stock boulder radius, to include
    # changes between vertex centres and ground under a wide rock's edge.
    bounds = np.array(seal["changed_bounds_m"]).reshape(2,2)+np.array([[-12.,-12.],[12.,12.]])
    level_path = PLAYTEST/"pwr.level.json"
    level = read(level_path)
    trees = cKDTree([t["position"][:2] for t in read(TREES)["instances"]])
    geometry = read(terrain/field.metadata["geometry"])
    main = next(row for row in geometry["watercourses"] if row["id"]=="central_river")
    river = np.asarray(main["erosion_reach"]["centreline_m"]) if "erosion_reach" in main else None
    basin_changes=None
    if "registered_basin" in geometry["lakes"][-1]:
        from basin_dressing import dress
        decorated,moved,footprints,fluid,basin_changes=dress(level["decor"],field,trees)
    else:
        decorated, moved, footprints, fluid = dress_rocks(level["decor"], old_field,field,bounds,trees,river,apron="apron" in main)
    out = out.resolve()
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out.parent,prefix=".headwater-dressing-") as tmp:
        stage = Path(tmp)/"dressing"
        stage.mkdir()
        groups, xf_pins = dress_grass(stage,level,old_field,field,bounds,footprints)
        if fluid:
            write_json(stage/"flow-rocks.json",dict(schema="pwr-fluid-obstacles-v1",
                coordinates="world metres east north up",terrain_sha256=field.manifest_sha256,rocks=fluid))
        if basin_changes is not None:
            write_json(stage/"basin-rock-seating.json",dict(terrain_sha256=field.manifest_sha256,
                affected_hulls=len(basin_changes),rocks=basin_changes))
        write_json(stage/"level-decor.json", decorated)
        write_json(stage/"decor-moves.json",dict(schema="pwr-headwater-dressing-transforms-v1",
            coordinates="Unreal centimetres", index_basis="zero-based source indices (before removal)",
            decor=moved,groups=groups))
        write_json(stage/"foliage.json",dict(file="foliage.bin",groups=level["foliage"]["groups"]))
        # Parse the files that will be consumed by the native scene builder.
        _, reread = read_mjf_groups(stage/"foliage.json")
        if [n for _,_,_,n in reread] != [g["target_count"] for g in groups]:
            raise ValueError("Native transform counts differ after serialization")
        source_count = sum(g["source_count"] for g in groups)
        target_count = sum(g["target_count"] for g in groups)
        receipt = dict(schema="pwr-headwater-dressing-v1", terrain_sha256=field.manifest_sha256,
            original_level_sha256=sha256(level_path), original_foliage_sha256=sha256(PLAYTEST/"foliage.bin"),
            original_exact_sidecars_sha256=xf_pins, decor_count=len(decorated),
            rock_translations=len(moved), rock_relocations=len(footprints),
            rock_exposure_above_ground_m=[min(v["hull_height_vs_ground_m"][1] for v in moved),
                                          max(v["hull_height_vs_ground_m"][1] for v in moved)],
            source_foliage=source_count,target_foliage=target_count,removed_foliage=source_count-target_count,
            reprojected_foliage=sum(len(g["moved"]) for g in groups),
            files_sha256={p.name:sha256(p) for p in sorted(stage.iterdir())})
        write_json(stage/"dressing-receipt.json",receipt)
        if out.exists():
            if any(not (out/p.name).is_file() or sha256(p)!=sha256(out/p.name) for p in stage.iterdir()):
                raise ValueError(f"Non-identical build already exists: {out}")
        else:
            stage.rename(out)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,default=HEADWATER/"dressing")
    parser.add_argument("--terrain",type=Path,help="Published terrain directory")
    args=parser.parse_args()
    print(json.dumps(build(args.out,args.terrain),indent=2))
