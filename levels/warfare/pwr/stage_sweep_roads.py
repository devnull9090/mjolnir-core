# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "scipy>=1.15", "pillow>=11", "shapely>=2", "trimesh>=4"]
# ///
"""Seal Southwest Sweep art as a native map revision of the verified .14 release."""

import argparse
import hashlib
import json
from pathlib import Path
import os
import re
import shutil
import struct
import tempfile

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

from stage_alpine_roads import cook_collision, inspect_foliage, require, matrices
from stage_world_playtest import (
    ROOT,
    LAND,
    WORLD,
    jsonfile,
    sha,
    verify_world,
    world_entries,
    write_json,
    load_container,
    read_chunk,
)
from stage_ground_life import OODLE
from package_landscape_revision import build, run
from bases_v1.stage_base_polish import unpack_map, seal_release
from bases_v1.verify_runtime_visuals import read_mesh
from visual_dressing.verify_distance_terrain import shader_receipt, load_name_batch
from visual_dressing.prepare_alpine_verges import (
    verify_world as verify_sweep_components,
)

FAMILY = ROOT / "out/pwr/alpine-target"
BASE = FAMILY / "saturday.14"
BSP = FAMILY / "verges/physics/pwr.sbsp"
BASE_HASH = "2135412efedd6dd1b7ab51a35ac2b939b6e530a6346a838ad3cea7c9422725cf"
CONTROL_TILE = np.s_[:, :512]
DETAIL = "T_PWR_SweepFloorDetail"
FIELD = "T_PWR_AlpineRoadbed"
OUTCROP_SPLIT = (
    ("PWR_AlpineVerges", "PWRVerge_Outcrop"),
    ("PWR_SweepBanks", "PWRSweepBank_NoSnow"),
)
BANK_PACKAGES = {
    "SM_PWR_SweepMossBanks",
    "M_PWR_SweepBank",
    "T_PWR_SweepBank_D",
    "T_PWR_SweepBank_N",
}
LITTER_PACKAGES = {
    "SM_PWR_SweepLitter_A",
    "SM_PWR_SweepLitter_B",
    "SM_PWR_SweepLitter_C",
    "SM_PWR_SweepDeadPine",
    "M_PWR_SweepLitter",
    "T_PWR_SweepLitter_D",
    "T_PWR_SweepLitter_N",
}


def check_surveyed_corridor(xy):
    from bake_alpine_roadbed import GEOMETRY, densify
    route = next(r for r in jsonfile(GEOMETRY)["roads"] if r["id"] == "southwest_sweep")
    line = densify(np.asarray(route["centreline_m"])[:, :2])
    along = np.r_[0, np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))]
    distance, closest = cKDTree(line).query(np.asarray(xy))
    station = along[closest]
    require(np.all((station >= 45) & (station <= 170) & (distance < 31)),
            "Changed road sample lies outside the Southwest bend and its two shoulders")


EXTRA_ACTORS = {
    "pine": ("PWR_SweepBendPine", "PWRSweepBend_"),
    "accents": ("PWR_SweepVergeAccents", "PWRVergeAccent_"),
    "paved-verges": ("PWR_MainRoadVerges", "PWRMainRoadVerge_"),
    "paved-edge": ("PWR_MainRoadEdgeGravel", "PWRMainRoadEdge_"),
}
PAVED_ACTORS = ("paved-verges", "paved-edge")
PINE_STOCK = "/Game/MJOLNIR/Scenery/PWR/SM_PWR_MaturePine_A"
PINE_OPEN = "/Game/MJOLNIR/GrassPilot/Playable/SM_PWR_SweepBendPine_OpenA"


def has_open_pine(art):
    path = art / "pine/verges.json"
    return path.is_file() and jsonfile(path)["groups"][0]["mesh"].split(".")[0] == PINE_OPEN


def verify_parent_scenery(art, before):
    for local in ("alpine-edits", "floor", "verges"):
        src, dst = before / local, art / local
        previous, current = (jsonfile(d / "verges.json") for d in (src,dst))
        require(previous == current, "Parent vegetation manifest changed: " + local)
        for i,g in enumerate(current["groups"],1):
            suffix = current["file"] + f".xf{i}"
            require(sha(src / suffix) == sha(dst / suffix) == g["transform_sha256"],
                    "Prior vegetation transforms changed outside the added actors")
    require(sha(before/"road-dressing.json") == sha(art/"road-dressing.json"), "Parent dressing scope changed")


def inherited_dressing_release(control):
    seen = set()
    while (control.parent / "pine/verges.json").is_file():
        receipt = jsonfile(control / "receipt.json")
        parent = receipt["surface_comparison"]
        release = parent["baseline"].split("playtest.")[-1].split(".")[0]
        require(release.isdigit() and release not in seen, "Invalid inherited road-dressing ancestry")
        seen.add(release)
        control = control.parent.parent / ("round" + release) / ("saturday." + release)
        require(jsonfile(control / "receipt.json")["sha256"] == parent["baseline_sha256"],
                "Inherited road-dressing parent differs from its sealed comparison")
    return control


def verify_parent_actors(art, before, extra, permitted_new=()):
    inherited={k for k in EXTRA_ACTORS if (before / k / "verges.json").is_file()}
    require(inherited<=set(extra) and set(extra)-inherited<=set(permitted_new),
            "An inherited bend actor is missing from the new world")
    for local in inherited:
        dst, src = art / local, before / local
        a, b = (jsonfile(d / "verges.json") for d in (dst, src))
        if local == "pine" and has_open_pine(art) and not has_open_pine(before):
            old, new = b["groups"][0], a["groups"][0]
            require(old["mesh"].split(".")[0] == PINE_STOCK and
                    {k for k in old.keys() | new.keys() if old.get(k)!=new.get(k)} == {"mesh"} and
                    {k for k in a.keys() | b.keys() if a.get(k)!=b.get(k)} <= {"binary_sha256", "groups"} and
                    a["binary_sha256"] == sha(dst / a["file"]), "Unexpected property change on the isolated bend pine")
        else:
            require(a == b, "An inherited bend actor's mesh, culls, materials or transforms changed")
        for i, group in enumerate(b["groups"], 1):
            sidecar = b["file"] + f".xf{i}"
            require(sha(src / sidecar) == sha(dst / sidecar) == group["transform_sha256"],
                    "Inherited bend actor native transform differs from the sealed candidate")


def verify_added_actor(art, local, name, prefix, world):
    folder = art / local
    spec = jsonfile(folder / "verges.json")
    require(spec["actor"] == name and len(spec["groups"]) > 0, "Unexpected native actor")
    if local == "paved-edge":
        from visual_dressing import bake_main_road_edge as edge
        survey = jsonfile(folder / "survey.json")
        selected = jsonfile(folder / "points.json")["points"]
        repeat = edge.pcg_foliage.compare(folder / "candidates.json", folder / "points.json",
                                          folder / "points_repeat.json")
        require(survey["actor"] == edge.OWNER and survey["seed"] == edge.SEED and
                spec["count"] == survey["count"] == len(selected) and
                survey["road_field_sha256"] == sha(edge.NETWORK) and
                repeat == survey["deterministic_repeat"] and
                {group["key"] for group in spec["groups"]} == set(edge.KEYS),
                "Road-edge stone graph, repeat, atlas or inventory differs from its survey")
        reference = {g["key"]: g for g in jsonfile(art / "floor/verges.json")["groups"]}
        per_mesh = {key: [] for key in edge.KEYS}
        for point in selected:
            per_mesh[edge.mesh_key(point)].append(point["position_cm"][:2])
        atlas = np.asarray(Image.open(edge.NETWORK).convert("RGBA"))
    if local=="paved-verges":
        from visual_dressing import bake_main_road_verges as verge
        road=jsonfile(folder/"survey.json")
        reference={g["key"]:g for g in jsonfile(art/"floor/verges.json")["groups"]}
        require({g["key"] for g in spec["groups"]}==set(verge.KEYS) and
                road["count"]==spec["count"] and road["road_field_sha256"]==sha(verge.ROAD),
                "Paved verge road field, group or point inventory changed")
        for group in spec["groups"]:
            prior=reference[group["key"]]
            require(all(group.get(prop)==prior.get(prop) for prop in ("mesh","material","material_package","cull","wpo","flags")),
                    "Paved verge did not preserve original render/wind/cull settings")
        repeat=verge.pcg_foliage.compare(folder/"candidates.json",folder/"points.json",folder/"points_repeat.json")
        require(repeat==road["deterministic_repeat"], "Native PCG repeat confirmation differs")
        _,verge_distance=verge.maps()
    if local == "accents":
        prior = {g["key"]: g for part in ("floor", "verges")
                 for g in jsonfile(art / part / "verges.json")["groups"]}
        require({g["key"] for g in spec["groups"]} == {"Gravel1", "Gravel2", "Gravel3", "Bark", "Branch", "FescueA"},
                "Unexpected material or foliage in the new shoulder pockets")
        for g in spec["groups"]:
            require(all(g.get(prop) == prior[g["key"]].get(prop)
                        for prop in ("mesh", "material", "material_package", "cull", "wpo", "flags")),
                    "A shoulder group changed its stock material, shadows, wind or distance settings")
    for idx,g in enumerate(spec["groups"],1):
        source = folder / (spec["file"] + f".xf{idx}")
        require(sha(source) == g["transform_sha256"], "Added actor transform signature mismatch")
        rows=np.fromfile(source, "<f4").reshape(-1,10)
        require(len(rows)==g["count"] and np.all(np.isfinite(rows)) and np.all(rows[:,7:]>0),
                "Invalid added native foliage transforms")
        if local == "pine":
            require(len(rows)==1 and len(spec["groups"])==1 and g["key"]=="Pine" and
                    g["mesh"].split(".")[0] in {PINE_STOCK, PINE_OPEN} and
                    np.allclose(rows[0,:3],[-60780,56540,10286.815],atol=.1,rtol=0) and
                    abs(np.dot(rows[0,3:7], [0,0,np.sin(np.radians(-85)),np.cos(np.radians(-85))])) > .999999 and
                    np.allclose(rows[0,7:],1.06,atol=.001,rtol=0), "Off-site or different shadow pine")
        elif local=="accents":
            check_surveyed_corridor(rows[:,:2]*[.01,-.01])
        elif local=="paved-verges":
            gaps=verge.sample(verge_distance,rows[:,:2]*[.01,-.01])
            require(np.all((gaps>1.05)&(gaps<6.6)),
                    "A baked verge pivot escaped the guaranteed clearance along the actual asphalt")
        elif local == "paved-edge":
            require(all(g.get(k) == reference[g["key"]].get(k)
                        for k in ("mesh", "material", "material_package", "cull", "wpo", "flags")),
                    "Native gravel render settings differ from the original scanned stone")
            expected = np.asarray(per_mesh[g["key"]])
            distances, indices = cKDTree(rows[:, :2]).query(expected)
            require(len(expected) == len(rows) == len(np.unique(indices)) and np.max(distances) < .02,
                    "Baked gravel pivots differ from the native PCG graph output")
            xy = rows[:, :2] * [.01, -.01]
            side = np.abs((edge.sample(atlas, xy)[:, 2] - .5) * 32)
            require(np.all((side > 8.56) & (side < 12.66) & (edge.weights(atlas, xy) > .099)),
                    "Road-edge gravel leaked onto a drive lane, a trail or outside the shoulder")
    verify_sweep_components(world, folder=folder, prefix=prefix)
    return jsonfile(folder / "cooked-world.json")


def verify_bend_mask(art, base):
    manifest = jsonfile(art / "earth/roadbed.json")
    mask = art / "earth" / manifest["route_authorization"]
    require(sha(mask) == manifest["route_authorization_sha256"], "Road boundary mask differs from source")
    previous = base.parent / "earth/alpine-roadbed.png"
    require(sha(previous) == manifest["previous_survey_sha256"], "Different previous terrain survey")
    with Image.open(mask) as im:
        require(im.mode == "L" and im.size == (1024,512), "Expected a full 1024px registered mask")
        permitted = np.asarray(im) > 0
    before = np.asarray(Image.open(previous).convert("RGBA"))
    after = np.asarray(Image.open(art / "earth/alpine-roadbed.png").convert("RGBA"))
    changed = np.any(before != after, axis=2)
    require(not permitted[:, :512].any() and not changed[~permitted].any(), "Terrain field changed outside the road bend")
    row, col = np.nonzero(permitted)
    xy = np.column_stack((-580 + (col - 767.5)*.5, -540 - (row-255.5)*.5))
    check_surveyed_corridor(xy)
    stats={"changed_pixels": int(changed.sum()), "changed_coverage_pixels": int(np.sum(before[:,:,0] != after[:,:,0]))}
    require(all(manifest[k] == n for k,n in stats.items()), "Incorrect changed road texel count")
    return dict(stats, mask_sha256=sha(mask), authorized_pixels=int(permitted.sum()), exact_outside=True)


def verify_repacked_detail(art, control):
    spec = jsonfile(art / "earth/roadbed.json")
    plan = spec["detail_repack"]
    dst, src = (p / "earth/sweep-floor-detail.png" for p in (art,control.parent))
    require(sha(src)==plan["parent_detail_sha256"] and sha(dst)==spec["detail_sha256"],
            "Unexpected source texture at the scan repack boundary")
    a,b = [np.asarray(Image.open(p).convert("RGBA")) for p in (src,dst)]
    require(a.shape == b.shape == (1024,2048,4), "Detail tile footprint or channel packing changed")
    regions = plan["regions"]
    require([r["x"] for r in regions] == [[0,1024],[1024,1808],[1808,2048]] and
            plan["scan_panel_bbox"] == [1808,0,2048,1024],"The new debris strip lies outside its designed area")
    for r in regions:
        lo,hi = r["x"]
        previous, current = a[:,lo:hi], b[:,lo:hi]
        count = int(np.count_nonzero(np.any(previous != current,axis=2)))
        require(count == r["changed_pixels"] and (lo != 0 or count==0) and
                hashlib.sha256(previous.tobytes()).hexdigest()==r["previous_pixels_sha256"] and
                hashlib.sha256(current.tobytes()).hexdigest()==r["pixels_sha256"],
                "Detail scan or preserved mineral panel differs from its authored pixels")
    return plan


def verified_shader_binding(old, new, maps):
    require(len(old)==len(new), "Unexpected world layout change in a shader-only pass")
    header = struct.unpack_from("<13I",old)
    require(old[:header[1]]==new[:header[1]], "Native export, package, name or import table changed")
    names = load_name_batch(old,52)[0]
    delta = np.flatnonzero(np.frombuffer(old,np.uint8) != np.frombuffer(new,np.uint8))
    require(len(delta)>0,"Missing world-to-shader binding change")
    for index,offset in enumerate(range(header[8],header[9],72)):
        pos, size, key, num = struct.unpack_from("<QQII",old,offset)
        pos += header[1]
        if names[key & 0x3fffffff]!="LandscapeMaterialInstanceConstant" or not pos<=delta[0]<=delta[-1]<pos+size:
            continue
        signature = []
        for data, known in zip((old,new), maps):
            export = data[pos:pos+size]
            code = [h for h in known if bytes.fromhex(h) in export]
            require(len(code)==1,"Static landscape permutation lacks its verified cooked shader map")
            signature.extend(code)
        require(signature[0]!=signature[1],"Compiled landscape permutation was not updated")
        relative = delta-pos
        changes = hashlib.sha256(relative.astype("<u4").tobytes() +
                                 np.frombuffer(old,np.uint8)[delta].tobytes() +
                                 np.frombuffer(new,np.uint8)[delta].tobytes()).hexdigest()
        return {"export":index,"name":"LandscapeMaterialInstanceConstant","instance":num,"size":size,
                "changed_bytes":int(len(delta)),"first_changed":int(relative[0]),"last_changed":int(relative[-1]),
                "modification_signature":changes,"shader_hash_before_after":signature}
    raise ValueError("World bytes changed outside a single verified terrain shader permutation")


def validated_shader_worlds(args, control, comparison, shaders, land, previous_world, world, scratch):
    maps = [comparison["shader_readback"]["landscape_world"],shaders["landscape_world"]]
    sources = [control.parent/"native/LPE.umap", args.native/"LPE.umap"]
    reference = verified_shader_binding(*(p.read_bytes() for p in sources),maps)
    props=[]
    for i,source in enumerate(sources):
        log=scratch/f"shader-world-properties-{i}.log"
        run([ROOT/"target/release/examples/props_dump.exe",ROOT/"out/pwr/world-art/foliage-r2/cooked-proof/world-paks",
             ROOT/"defs/ue/Meteorite-2607-CU3.usmap",source,str(reference["export"])],log)
        props.append(log.read_text(encoding="utf-8"))
    require(props[0]==props[1] and "bHasStaticPermutationResource = true" in props[0], "Material instance properties changed")
    tail = re.search(r"LandscapeMaterialInstanceConstant \(native tail (\d+) bytes\)",props[0])
    require(tail and reference["first_changed"] >= reference["size"]-int(tail.group(1)),
            "Change precedes the native compiled material payload")
    def world_bytes(toc):
        c=load_container(toc)
        k,=[key for key in c.files if key.lower().endswith(("/pwr/pwr.umap","/lpe/lpe.umap"))]
        return read_chunk(c,c.chunks[c.files[k]],oodle_roots=[OODLE])
    checked={}
    for name, original, revised in (("landscape",control/"map-input"/(LAND+".utoc"),land),
                                    ("playable",previous_world,world)):
        data = verified_shader_binding(world_bytes(original),world_bytes(revised),maps)
        require(data["modification_signature"]==reference["modification_signature"],
                "Source shader binding change differs from the native "+name+" world")
        checked[name]=data
    checked["source"]=reference
    checked["all_material_properties_identical"]=True
    return checked


def verify_local_patch_world(before, after, allowed_roots):
    from visual_dressing import verify_distance_colonies as native

    def scene(path):
        stream = path.read_bytes()
        header = struct.unpack_from("<13I",stream)
        names = load_name_batch(stream,52)[0]
        entries = [struct.unpack_from("<IIQ",stream,i+16) for i in range(header[8],header[9],72)]
        def full_name(index):
            key,num,outer = entries[index]
            name = names[key&0x3fffffff] + ("_"+str(num-1) if num else "")
            return (full_name(outer)+"/" if outer<len(entries) else "")+name
        objects={full_name(i) for i in range(len(entries))}
        require(len(objects)==len(entries),"Ambiguous scene export path")
        # Read every original placed mesh and all 256 native landscape tiles.
        result={}
        for row in native.decode(path,native.GAME)["exports"]:
            key=full_name(row["export"])
            props=row["properties"]
            values={p:v for p,v in props.items() if p.startswith(("RelativeLocation","RelativeRotation",
                    "RelativeScale3D","InstanceStartCullDistance","InstanceEndCullDistance","SectionBase",
                    "ComponentSizeQuads","SubsectionSizeQuads","NumSubsections"))}
            if row["class"] in {"StaticMeshComponent","HierarchicalInstancedStaticMeshComponent"}:
                values["mesh"]=native.package(row,"StaticMesh")
            if row["class"]=="HierarchicalInstancedStaticMeshComponent":
                count=int(native.number(props["NumBuiltInstances"]))
                values["count"]=count
                values["matrices_sha256"]=hashlib.sha256(native.native_matrices(stream,row,count).tobytes()).hexdigest()
            result[key]=(row["class"],values)
        return objects,result
    a,old=scene(before); b,new=scene(after)
    require(a<=b and all(key in new and new[key]==val for key,val in old.items()),
            "An existing actor, mesh instance, landscape tile, cull distance or placement changed")
    added=b-a
    roots=sorted(k for k in added if k.count("/")==2)
    require(len(roots)==len(allowed_roots) and
            all(sum(p.rsplit("/",1)[-1] in (name,name+"1") for p in roots)==1 for name in allowed_roots) and
            all(any(p==k or p.startswith(k+"/") for k in roots) for p in added),
            "Scene changed beyond the selected native actors: "+str(sorted(added)))
    return {"matched_scene_exports":len(a),"matched_placement_components":len(old),
            "added_actor_exports":sorted(added),"existing_native_transforms_identical":True}


def verify_near_puddle_shader(art,control):
    prior,current = [(p/"earth/actual-graph.hlsl").read_text(encoding="cp1252")
                     for p in (control.parent,art)]
    evidence=jsonfile(art/"earth/surface-scope.json")
    begin=current.index("    // Submerged fines")
    end=current.index("    n*=rsqrt",begin)
    subset=current[begin:end]
    require(prior==current[:begin]+current[end:] and
            all(hashlib.sha256(s.encode()).hexdigest()==evidence[key] for s,key in [
                (prior,"previous_shader_sha256"),(current,"candidate_shader_sha256"),(subset,"inserted_hlsl_sha256")]),
            "Terrain graph changed beyond the near-puddle margin")
    require("pool<=0." in subset and "outsideWheel< -1.13" in subset and "survey.x<.505" in subset and
            "Texture" not in subset and ".Sample" not in subset,"Puddle update changed wheel, water or sampling scope")
    return evidence


def verify_dressing_edits(art, control):
    survey = jsonfile(art / "road-dressing.json")
    expected = {(row["actor"], row["component"]): row for row in survey["groups"]}
    require(len(expected)==len(survey["groups"]), "Duplicate road-dressing edit")
    edited, trimmed, published = set(), {}, {}
    for origin, dest, prefix in [
        (control.parent / "floor", art / "floor", "PWRSweep_"),
        (control.parent / "verges", art / "verges", "PWRSweepBank_"),
        (FAMILY / "verges", art / "alpine-edits", "PWRVerge_")]:
        a_path, b_path = origin / "verges.json", dest / "verges.json"
        a, b = jsonfile(a_path), jsonfile(b_path)
        require(a["actor"] == b["actor"] and len(a["groups"]) == len(b["groups"]), "Different vegetation component inventory")
        for i, (old, new) in enumerate(zip(a["groups"], b["groups"]),1):
            key = old["key"]
            native_key=(a["actor"],prefix+key)
            historical = native_key[1].startswith("PWRVerge_")
            if historical and key=="Outcrop":
                # The manifest predates the two .16 Southwest outcrop transfers.
                # The native split validator checks all three against the sealed world.
                continue
            from_path=origin/(a["file"]+f".xf{i}")
            to_path=dest/(b["file"]+f".xf{i}")
            require({k for k in old.keys() | new.keys() if old.get(k)!=new.get(k)} <= {"count","transform_sha256"},
                    "Vegetation configuration changed: "+str(native_key))
            if native_key not in expected:
                require(old == new and sha(from_path) == sha(to_path), "Unsurveyed vegetation edits: "+str(native_key))
                continue
            change=expected[native_key]
            require(key in {"Gravel1","Gravel2","Gravel3","Fern14","Fern15","FescueA","FescueB","Moss","Sedge","Tufts","Ferns","LitterA","LitterB","LitterC","Bark","Branch"},
                    "Unexpected trimming of a solid landmark")
            require((ROOT/change["source_manifest"]).resolve()==a_path.resolve() and (ROOT/change["target_manifest"]).resolve()==b_path.resolve() and
                    (ROOT/change["source_transforms"]).resolve()==from_path.resolve() and (ROOT/change["target_transforms"]).resolve()==to_path.resolve(),
                    "Transforms are not bound to the selected source and candidate")
            src=np.fromfile(from_path,"<f4").reshape(-1,10)
            dst=np.fromfile(to_path,"<f4").reshape(-1,10)
            rm=np.asarray(change["removed_indices"],dtype=int)
            require(sha(from_path)==old["transform_sha256"]==change["base_sha256"] and sha(to_path)==new["transform_sha256"]==change["sha256"],"Placement hashes differ")
            require(old["count"]==len(src)==change["base_count"] and new["count"]==len(dst)==change["count"],"Placement counts differ")
            require(len(np.unique(rm))==len(rm) and np.all((rm>=0)&(rm<len(src))),"Invalid vegetation removal indices")
            keep=np.ones(len(src),dtype=bool)
            keep[rm]=False
            removed, kept = src[rm],src[keep]
            added=dst[len(kept):]
            require(np.array_equal(dst[:len(kept)],kept) and len(added)==change["added_count"],"Unlisted vegetation movement")
            require(hashlib.sha256(added.tobytes()).hexdigest()==change["append_sha256"],"Different added vegetation")
            touched=np.concatenate((removed,added))
            require(len(touched)>0 and np.all(np.isfinite(touched)) and np.all(touched[:,7:]>0), "Invalid vegetation edit")
            check_surveyed_corridor(touched[:,:2]*[.01,-.01])
            if historical:
                require(len(added)==0,"Legacy vegetation can only be trimmed")
                trimmed[native_key]=matrices(from_path)[rm]
            edited.add(native_key)
            published[".".join(native_key)]={"removed":len(rm),"added":len(added),"kept":len(kept),"sha256":new["transform_sha256"]}
    require(edited==expected.keys(),"Unknown or missing modified vegetation component")
    return published, trimmed


def verify_gravel_revision(folder, baseline):
    """Read back the existing .18 prefix and constrain new rows to the surveyed road."""
    current = jsonfile(folder / "verges.json")
    baseline_folder = baseline.parent / "floor"
    previous = jsonfile(baseline_folder / "verges.json")
    require(current["actor"] == previous["actor"] == "PWR_SweepForestFloor", "Unexpected floor actor")
    require(len(current["groups"]) == len(previous["groups"]), "Floor component inventory changed")
    change_record = jsonfile(folder / "gravel-edit.json")
    require(change_record["base_manifest_sha256"] == sha(baseline_folder / "verges.json"), "Gravel field targets a different reference")
    scopes = {}
    for i, (new, old) in enumerate(zip(current["groups"], previous["groups"]), 1):
        key = old["key"]
        metadata = {k for k in old.keys() | new.keys() if old.get(k) != new.get(k)}
        require(metadata <= {"count", "transform_sha256"}, "Changed native floor binding: " + key)
        old_file = baseline_folder / (previous["file"] + f".xf{i}")
        new_file = folder / (current["file"] + f".xf{i}")
        original = old_file.read_bytes()
        effective = new_file.read_bytes()
        require(sha(old_file) == old["transform_sha256"] and sha(new_file) == new["transform_sha256"], "Invalid transform digest for " + key)
        require(len(effective) == 40 * new["count"] and len(original) == 40 * old["count"], "Inconsistent transform count " + key)
        require(effective.startswith(original), "Existing floor instances moved: " + key)
        if len(effective) == len(original):
            continue
        require(key in {"Gravel1", "Gravel2", "Gravel3"}, "New instances outside gravel groups: " + key)
        rows = np.frombuffer(effective[len(original):], "<f4").reshape(-1, 10)
        require(np.all(np.isfinite(rows)) and np.all(rows[:, 7:] > 0), "Invalid gravel placements")
        recorded = change_record["groups"][key]
        subset = {"base_count": old["count"], "count": new["count"], "added_count": len(rows),
                  "base_sha256": old["transform_sha256"], "sha256": new["transform_sha256"],
                  "append_sha256": hashlib.sha256(effective[len(original):]).hexdigest()}
        require(all(recorded[k] == v for k, v in subset.items()), "Gravel survey references a different transform stream: " + key)
        require(recorded["highest_mesh_bottom_cm"] <= 0 and recorded["maximum_exposed_cm"] <= 3.5, "Stones protrude above the surveyed drive bed")
        scopes[key] = recorded
    require(scopes.keys() == change_record["groups"].keys(), "Unexpected gravel survey coverage")
    return scopes


def verify_cumulative_floor(folder):
    previous_folder = ROOT / "out/pwr/sweep-polish/verges"
    previous = jsonfile(previous_folder / "verges.json")
    current = jsonfile(folder / "verges.json")
    require(
        previous["actor"] == current["actor"] == "PWR_SweepForestFloor",
        "Wrong forest-floor owner",
    )
    require(
        len(current["groups"]) == len(previous["groups"]) == 10,
        "Forest-floor inventory changed",
    )
    for i, (old, new) in enumerate(zip(previous["groups"], current["groups"]), 1):
        source = previous_folder / (previous["file"] + f".xf{i}")
        effective = folder / (current["file"] + f".xf{i}")
        if old["key"] == new["key"] == "Moss":
            edits = jsonfile(folder.parent / "verges/legacy-edits.json")
            require(
                sha(previous_folder / "verges.json")
                == edits["baseline_moss_source_sha256"]
                and sha(source) == old["transform_sha256"],
                "Moss edits target a different source",
            )
            rows = (
                np.fromfile(source, "<f4").reshape(-1, 10)[edits["moss_indices"]].copy()
            )
            rows[:, 7:9] *= 0.56
            rows[:, 9] *= 0.45
            require(
                old["mesh"] == new["mesh"]
                and new["count"] == len(rows)
                and rows.tobytes() == effective.read_bytes(),
                "Unexpected moss replacement",
            )
            continue
        require(old == new, "Non-moss forest-floor group changed: " + old["key"])
        require(
            sha(source) == sha(effective),
            "Earlier forest-floor instances moved: " + old["key"],
        )


def native_world(args):
    base = jsonfile(args.baseline / "receipt.json")
    require(base["sha256"] == BASE_HASH, "Expected the reviewed .14 source")
    level = jsonfile(args.baseline / "map-input/pwr.level.json")
    env = args.art / "light/environment.json"
    if env.is_file():
        replacement = jsonfile(env)
        baseline = level["environment"]
        require(
            {
                k
                for k in baseline.keys() | replacement.keys()
                if baseline.get(k) != replacement.get(k)
            }
            <= {"sun"},
            "Only the selected sun may change",
        )
        old, new = baseline["sun"], replacement["sun"]
        require(
            {k for k in old.keys() | new.keys() if old.get(k) != new.get(k)}
            <= {"source_angle", "pitch", "yaw"},
            "Unexpected global light changes",
        )
        level["environment"] = replacement
    write_json(
        args.art / "native-level.json",
        {
            k: v
            for k, v in level.items()
            if k not in {"landscape", "waterfalls", "flux", "effects"}
        },
    )
    if not (args.native / "native.json").is_file():
        build(
            argparse.Namespace(
                staged=args.staged,
                baseline=args.baseline,
                level=args.art / "native-level.json",
                bsp=BSP,
                paks=args.paks,
                cook_log=args.art / "cook.log",
                out=args.native,
                cli=args.bake_cli,
            )
        )
    require(
        jsonfile(args.native / "native.json")["sealed_baseline"] == BASE_HASH,
        "Different native control",
    )
    for stem in ("global", "pakchunk965-Windows"):
        for ext in (".utoc", ".ucas"):
            name = stem + ext
            require(
                sha(args.staged / name) == sha(args.native / "stock" / name),
                "Native revision targets a different cook",
            )
    selection = args.art / "light/selected-native-pilot.json"
    if selection.is_file():
        p = jsonfile(selection)["parameters"]
        env = level["environment"]
        require(
            [env["skylight"]["intensity"], env["sun"]["pitch"], env["sun"]["yaw"]]
            == p["sky_sun"]
            and env["sun"]["source_angle"] == p["source_angle"],
            "Native scenario lighting differs from selected Halo study",
        )
    return level


def readback_textures(args, land, scratch):
    folder = scratch / "textures"
    folder.mkdir()
    for toc in [args.staged / "global.utoc", land]:
        for ext in (".utoc", ".ucas"):
            p = toc.with_suffix(ext)
            try:
                os.link(p, folder / p.name)
            except OSError:
                shutil.copyfile(p, folder / p.name)
    proofs = {}
    source_spec = jsonfile(args.art / "earth/editor-verified.json")
    for leaf, file in [
        (FIELD, "alpine-roadbed.png"),
        (DETAIL, "sweep-floor-detail.png"),
    ]:
        source = args.art / "earth" / file
        wanted = np.asarray(Image.open(source).convert("RGBA"))
        lossless = leaf == FIELD or "BC7" not in source_spec["detail_format"].upper()
        info = folder / (leaf + "-texture.log")
        run([args.cli, "texture", "info", "--paks", folder, "--asset", leaf], info)
        text = info.read_text(encoding="utf-8")
        format_name = "PF_B8G8R8A8" if lossless else "PF_BC7"
        require(
            format_name in text,
            "Native texture format differs from authored shader data: " + leaf,
        )
        if leaf == FIELD:
            baseline = np.asarray(
                Image.open(FAMILY / "earth/alpine-roadbed.png").convert("RGBA")
            )
            require(
                wanted.shape == baseline.shape
                and np.array_equal(wanted[CONTROL_TILE], baseline[CONTROL_TILE]),
                "Teton tile changed",
            )
        assertions = {}
        for lod in (0, 2):
            dest = folder / f"{leaf}-{lod}.png"
            run(
                [
                    args.cli,
                    "texture",
                    "export",
                    "--paks",
                    folder,
                    "--asset",
                    leaf,
                    "--mip",
                    str(lod),
                    "--out",
                    dest,
                ],
                folder / (dest.stem + ".log"),
            )
            actual = np.asarray(Image.open(dest).convert("RGBA"))
            size = wanted.shape[1] >> lod, wanted.shape[0] >> lod
            reference = np.stack(
                [
                    np.asarray(Image.fromarray(c).resize(size, Image.Resampling.BOX))
                    for c in wanted.transpose(2, 0, 1)
                ],
                axis=-1,
            )
            require(
                actual.shape == reference.shape, "Cooked texture dimensions changed"
            )
            error = np.abs(actual.astype(np.int16) - reference)
            rmse = float(np.sqrt(np.mean(error.astype(float) ** 2)))
            channel_stats = []
            if lossless:
                require(
                    int(error.max()) <= int(lod != 0),
                    "Painted linear coverage mismatch",
                )
            else:
                # The four independent data channels do not share the colour line
                # that BC7 fits to each block. Verify content and orientation in
                # each half/channel while recording the loss from that GPU format.
                for part in np.array_split(np.arange(size[0]), 2):
                    for channel in range(4):
                        lhs = actual[:, part, channel].ravel()
                        rhs = reference[:, part, channel].ravel()
                        correlation = float(np.corrcoef(lhs, rhs)[0, 1])
                        bias = float(np.mean(lhs.astype(float) - rhs))
                        require(
                            correlation > 0.65 and abs(bias) < 2,
                            "BC7 scan channel, region or transfer function disagrees with its input",
                        )
                        channel_stats.append(
                            {"correlation": correlation, "signed_mean_error": bias}
                        )
            assertions[str(lod)] = {
                "size": size,
                "rmse": rmse,
                "p95": float(np.percentile(error, 95)),
                "max": int(error.max()),
                "tile_channel_checks": channel_stats,
            }
        proofs[leaf] = {
            "source_sha256": sha(source),
            "mips": assertions,
            "native_format": format_name,
        }
    return proofs


def inspect_lights(args, world_path, scratch):
    """Resolve the native actor and its child by export ownership and decode its light."""
    source = args.art / "light/editor-light-reloaded.json"
    if not source.is_file():
        source = ROOT / "out/pwr/sweep-polish/light/editor-light-reloaded.json"
    previous = jsonfile(source)
    data = world_path.read_bytes()
    names, _ = load_name_batch(data, 52)
    begin, end = struct.unpack_from("<II", data, 32)
    exports = []
    for offset in range(begin, end, 72):
        base, n, outer = struct.unpack_from("<IIQ", data, offset + 16)
        name = names[base & 0x3FFFFFFF] + ("_" + str(n - 1) if n else "")
        exports.append((name, outer))
    report = []
    for spec in previous:
        (actor,) = [i for i, (name, _) in enumerate(exports) if name == spec["actor"]]
        candidates = [i for i, (_, outer) in enumerate(exports) if outer == actor]
        for idx in candidates:
            dest = scratch / f"light-{idx}.log"
            run(
                [
                    ROOT / "target/release/examples/props_dump.exe",
                    ROOT / "out/pwr/world-art/foliage-r2/cooked-proof/world-paks",
                    ROOT / "defs/ue/Meteorite-2607-CU3.usmap",
                    world_path,
                    str(idx),
                ],
                dest,
            )
            body = dest.read_text(encoding="utf-8")
            if " PointLightComponent " not in body.splitlines()[0]:
                continue
            props = dict(
                line.strip().split(" = ", 1)
                for line in body.splitlines()[1:]
                if " = " in line
            )
            require(
                abs(float(props["Intensity"].split()[0]) - spec["intensity"]) < 0.01,
                "Native lamp intensity changed",
            )
            require(
                abs(float(props["AttenuationRadius"].split()[0]) - spec["radius_cm"])
                < 0.01,
                "Native lamp extent changed",
            )
            require(
                abs(float(props["LightFalloffExponent"].split()[0]) - spec["exponent"])
                < 0.01,
                "Native lamp attenuation changed",
            )
            report.append(
                {
                    "actor": spec["actor"],
                    "component": exports[idx][0],
                    "properties": props,
                }
            )
        require(
            len([v for v in report if v["actor"] == spec["actor"]]) == 1,
            "Missing or duplicate cooked point light",
        )
    selection = args.art / "light/selected-native-pilot.json"
    if selection.is_file():
        p = jsonfile(selection)
        (chosen,) = [
            s.split() for s in p["readback"].splitlines() if s.startswith("BAKED_FILL ")
        ]
        (_, intensity, red, green, blue, *_) = chosen
        (actual,) = report
        q = actual["properties"]
        require(
            float(q["Intensity"].split()[0]) == float(intensity)
            and q["LightColor"].split(",")[:3] == [blue, green, red],
            "Packaged fill differs from selected Halo rehearsal",
        )
    return report


def inspect_native_geometry(args, mount, source, mesh):
    landform = jsonfile(source)
    wanted = np.asarray(landform["positions"])[:, [0, 2, 1]] * 0.01
    faces = np.asarray(landform["faces"])
    glb = mount / (mesh + ".glb")
    log = mount / (mesh + ".log")
    run(
        [
            args.cli,
            "mesh",
            "export",
            "--paks",
            mount,
            "--asset",
            glb.stem,
            "--out",
            glb,
        ],
        log,
    )
    (native,) = read_mesh(glb)
    gltf = glb.read_bytes()
    doc = json.loads(gltf[20 : 20 + struct.unpack_from("<I", gltf, 12)[0]])
    lod_triangles = [
        sum(doc["accessors"][p["indices"]]["count"] // 3 for p in m["primitives"])
        for m in doc["meshes"]
    ]
    actual = native["position"]
    unique_points, source_indices = np.unique(wanted, axis=0, return_inverse=True)
    mapping = cKDTree(unique_points).query(actual)
    error = max(float(mapping[0].max()), float(cKDTree(actual).query(wanted)[0].max()))
    require(error < 0.015, "Rendered bank vertices differ by more than 1.5 cm")
    authored_uv = np.asarray(landform["uv"])
    source_points = np.column_stack((wanted, authored_uv))
    rendered_points = np.column_stack((actual, native["uv"]))
    corners, source_corners = np.unique(source_points, axis=0, return_inverse=True)
    uv_delta, rendered_corners = cKDTree(corners).query(rendered_points)
    uv_error = max(
        float(uv_delta.max()),
        float(cKDTree(rendered_points).query(source_points)[0].max()),
    )
    require(uv_error < 0.002, "Rendered bank UVs or positions changed")
    expected = sorted(map(tuple, np.sort(source_indices[faces], axis=1)))
    cooked = sorted(map(tuple, np.sort(mapping[1][native["triangles"]], axis=1)))
    require(
        expected == cooked,
        "Cooked bank triangles differ from the source and physical surface",
    )
    # Ring seams and cut ends deliberately share 3D coordinates with distinct UVs.
    source_triangles = sorted(map(tuple, np.sort(source_corners[faces], axis=1)))
    rendered_triangles = sorted(
        map(tuple, np.sort(rendered_corners[native["triangles"]], axis=1))
    )
    require(
        source_triangles == rendered_triangles,
        "Native triangle-to-UV seam assignments changed: " + mesh,
    )
    return {
        "source_sha256": sha(source),
        "triangles": len(faces),
        "max_position_error_m": error,
        "slot": native["slot"],
        "lod_triangles": lod_triangles,
        "max_position_uv_error": uv_error,
        "mesh_report": log.read_text(encoding="utf-8").strip(),
        "uv_min": native["uv"].min(axis=0).tolist(),
        "uv_max": native["uv"].max(axis=0).tolist(),
    }


def inspect_bank_geometry(args, mount):
    evidence = inspect_native_geometry(
        args, mount, args.art / "verges/landform.json", "SM_PWR_SweepMossBanks"
    )
    atlas = args.art / "verges/bank-D.png"
    with Image.open(atlas) as source_atlas:
        alpha = np.asarray(source_atlas.convert("RGBA"))[:, :, 3]
    if alpha.min() < 255:
        dest = mount / "bank-atlas.png"
        run(
            [
                args.cli,
                "texture",
                "export",
                "--paks",
                mount,
                "--asset",
                "T_PWR_SweepBank_D",
                "--mip",
                "0",
                "--out",
                dest,
            ],
            mount / "bank-alpha.log",
        )
        actual_alpha = np.asarray(Image.open(dest).convert("RGBA"))[:, :, 3]
        require(
            actual_alpha.shape == alpha.shape
            and alpha.min() == 0
            and alpha.max() == 255,
            "Bank material lacks the intended opacity range",
        )
        # Native material clips interpolated alpha at 0.48.
        cut_level = int(np.ceil(0.48 * 255))
        cut = alpha >= cut_level
        decoded = actual_alpha >= cut_level
        mismatch = float(np.mean(cut != decoded))
        require(
            mismatch < 0.02
            and float(np.mean(cut)) > 0.05
            and float(np.mean(~cut)) > 0.05,
            "Native opacity texture lacks the bank transition",
        )
        dump = mount / "bank-material.log"
        run(
            [
                args.cli,
                "ue",
                "get",
                "--paks",
                mount,
                "--package",
                "M_PWR_SweepBank",
            ],
            dump,
        )
        rows = [
            row.strip()
            for row in dump.read_text(encoding="utf-8").splitlines()
            if "BlendMode =" in row
        ]
        require(
            any(
                "Masked" in row or row.partition("=")[2].strip().split()[0] == "1"
                for row in rows
            ),
            "Cooked bank material is not masked",
        )
        clip = [
            row.strip()
            for row in dump.read_text(encoding="utf-8").splitlines()
            if "OpacityMaskClipValue =" in row
        ]
        require(
            any(
                abs(float(row.partition("=")[2].strip().split()[0]) - 0.48) < 0.001
                for row in clip
            ),
            "Cooked opacity threshold differs",
        )
        evidence["opacity"] = {
            "source_sha256": sha(atlas),
            "covered_fraction": float(cut.mean()),
            "native_classification_mismatch": mismatch,
            "linked_material": rows,
            "clip": clip,
        }
    return evidence


def inspect_litter_geometry(args, mount):
    spec = jsonfile(args.art / "verges/litter.json")
    made = {}
    for mesh in spec["meshes"]:
        leaf = mesh["name"]
        require(
            leaf in LITTER_PACKAGES
            and mesh["package"] == "/Game/MJOLNIR/GrassPilot/Playable/" + leaf,
            "Unexpected litter package",
        )
        proof = inspect_native_geometry(
            args, mount, args.art / "verges" / mesh["file"], leaf
        )
        require(
            proof["source_sha256"] == mesh["sha256"]
            and proof["triangles"] == mesh["triangles"]
            and proof["slot"] == mesh["slot"],
            "Litter geometry or native material slot differs: " + leaf,
        )
        made[leaf] = proof
    require(
        set(made) == {p for p in LITTER_PACKAGES if p.startswith("SM_")},
        "Missing litter mesh",
    )
    # Unreal stores diffuse as sRGB and normal XY as linear BC data.
    texture_proof = {}
    texture_sources = jsonfile(args.art / "verges/litter-textures.json")["images"]
    for kind, channels in (("D", 3), ("N", 2)):
        leaf = "T_PWR_SweepLitter_" + kind
        src = args.art / "verges" / ("litter-" + kind + ".png")
        require(
            texture_sources[kind]["sha256"] == sha(src)
            and texture_sources[kind]["package"].endswith("/" + leaf),
            "Litter texture differs from approved source",
        )
        actual = mount / (leaf + ".png")
        run(
            [
                args.cli,
                "texture",
                "export",
                "--paks",
                mount,
                "--asset",
                leaf,
                "--mip",
                "0",
                "--out",
                actual,
            ],
            mount / (leaf + ".log"),
        )
        with Image.open(src) as a, Image.open(actual) as b:
            require(a.size == b.size, "Incorrect cooked forest litter texture size")
            av = np.asarray(a.convert("RGB"))[:, :, :channels].astype(float)
            bv = np.asarray(b.convert("RGB"))[:, :, :channels].astype(float)
        corr = [
            float(np.corrcoef(av[:, :, i].ravel(), bv[:, :, i].ravel())[0, 1])
            for i in range(channels)
        ]
        require(
            min(corr) > 0.75,
            "Native litter atlas lost a color/normal channel or orientation",
        )
        texture_proof[leaf] = {
            "source_sha256": sha(src),
            "size": list(av.shape[:2]),
            "channel_correlation": corr,
        }
    return {"meshes": made, "textures": texture_proof}


def stage(args, level, release):
    inputs, old, expected, manifest = unpack_map(args.baseline, release)
    control = args.comparison_release
    comparison = jsonfile(control / "receipt.json") if control else None
    shader_only = args.terrain_shader_only
    sun_patches = args.local_sun_patches
    paved_update=args.paved_road_update
    if shader_only or sun_patches or paved_update:
        require(control and has_open_pine(control.parent) and has_open_pine(args.art),
                "Shader isolation requires the verified open-canopy comparison world")
        for rel in ("earth/alpine-roadbed.png", "earth/sweep-floor-detail.png", "light/environment.json",
                    "light/editor-light-reloaded.json", "light/selected-native-pilot.json",
                    "pine/open-canopy.glb", "pine/canopy.json", "pine/structural.json", "pine/physics/pwr.sbsp"):
            require(sha(control.parent / rel) == sha(args.art / rel), "Shader-only pass changed " + rel)
        if paved_update:
            for rel in ("light/bend-sun-patches.json","light/spot-pilot.json","light/editor-sun-patches-reopened.json",
                        "paved/survey.json","paved/forest-floor-pose.json"):
                require(sha(control.parent / rel)==sha(args.art / rel),"Inherited lighting or road survey changed: "+rel)
            before_shader=(control.parent/"earth/actual-graph.hlsl").read_text(encoding="cp1252")
            after_shader=(args.art/"earth/actual-graph.hlsl").read_text(encoding="cp1252")
            start=before_shader.index("    // Submerged fines")
            stop=before_shader.index("    n*=rsqrt",start)
            require(before_shader[start:stop] in after_shader,"Previously reviewed puddle-rim transfer changed")
    if comparison:
        require(comparison["sha256"] == sha(control / comparison["archive"]), "Different comparison map archive")
        require(level == jsonfile(control / "map-input/pwr.level.json"), "Scenario or environment changed from comparison")
    require(old["sha256"] == BASE_HASH, "Unexpected source archive")
    before = inputs / (WORLD + ".utoc")
    world = args.native / "world-final" / before.name
    proof = verify_world(before, world)
    old_land = inputs / (LAND + ".utoc")
    (land,) = list((args.native / "land").glob("*.utoc"))
    a, b = world_entries(old_land), world_entries(land)
    added = set(b) - set(a)
    require(set(a) <= set(b), "A baseline landscape asset is missing")
    expected_add = {DETAIL + ".uasset", DETAIL + ".ubulk"}
    banks = (args.art / "floor/verges.json").is_file()
    litter = (args.art / "verges/litter.json").is_file()
    additions = BANK_PACKAGES | LITTER_PACKAGES if litter else BANK_PACKAGES
    opened = has_open_pine(args.art)
    if opened:
        additions = additions | {PINE_OPEN.rsplit("/", 1)[1]}
    if banks:
        new_terrain = {k for k in added if Path(k).name not in expected_add}
        require(
            {Path(k).stem for k in new_terrain if k.endswith(".uasset")} == additions,
            "Missing authored bank material/geometry",
        )
        require(
            all(
                k.endswith((".uasset", ".ubulk"))
                and Path(k).stem in additions
                and k.startswith("MJOLNIR/GrassPilot/Playable/")
                for k in new_terrain
            ),
            "Unexpected bank package: " + str(new_terrain),
        )
    else:
        new_terrain = set()
    require(
        {Path(k).name for k in added - new_terrain} == expected_add,
        "Unexpected native terrain additions: " + str(added),
    )
    changed = sorted(k for k in a if a[k] != b[k])
    allowed = {
        "M_PWRPilot.uasset",
        FIELD + ".uasset",
        FIELD + ".ubulk",
        "LPE.umap",
        "LPE.ubulk",
    }
    require(
        all(Path(k).name in allowed or k.endswith(".ushaderbytecode") for k in changed),
        "Unexpected terrain edit: " + str(changed),
    )
    require(
        {"LPE.umap", "M_PWRPilot.uasset", FIELD + ".ubulk"}
        <= {Path(k).name for k in changed},
        "Cook lacks structural, shader or coverage edit",
    )
    materials = sorted(k for k in additions if k.startswith("M_")) if banks else []
    shaders = shader_receipt(land, OODLE, materials)
    baseline_shaders = shader_receipt(old_land, OODLE)
    for target in ("master", "landscape_world"):
        require(
            set(shaders[target]) != set(baseline_shaders[target]),
            "Compiled .14 shader survived in " + target,
        )
        require(
            any(v.get("PS", 0) > 0 for v in shaders[target].values()),
            "Native pixel shaders missing",
        )
    cont = load_container(land)
    if litter:
        (litter_material,) = [
            k for k in cont.files if k.endswith("/M_PWR_SweepLitter.uasset")
        ]
        mat = read_chunk(
            cont, cont.chunks[cont.files[litter_material]], oodle_roots=[OODLE]
        )
        package_names = load_name_batch(mat, struct.unpack_from("<i", mat, 48)[0])[0]
        require(
            all(
                "/Game/MJOLNIR/GrassPilot/Playable/T_PWR_SweepLitter_" + suffix
                in package_names
                for suffix in ("D", "N")
            ),
            "Litter material missing cooked color or normal map",
        )
    (key,) = [k for k in cont.files if k.endswith("/M_PWRPilot.uasset")]
    raw = read_chunk(cont, cont.chunks[cont.files[key]], oodle_roots=[OODLE])
    names = load_name_batch(raw, struct.unpack_from("<i", raw, 48)[0])[0]
    require(
        all("/Game/MJOLNIR/GrassPilot/Playable/" + s in names for s in (DETAIL, FIELD)),
        "Native material is missing authoring textures",
    )
    with tempfile.TemporaryDirectory(dir=release.parent) as tmp:
        scratch = Path(tmp)
        pixels = readback_textures(args, land, scratch)
        new_canopy = None
        if opened:
            from visual_dressing.verify_sweep_open_pine import verify as verify_native_canopy
            geometry = verify_native_canopy(args.staged, args.art, args.cli)
            leaf = PINE_OPEN.rsplit("/", 1)[1]
            shipping = world_entries(args.staged / "pakchunk965-Windows.utoc")
            def canopy_members(entries):
                return {Path(k).name: digest for k,digest in entries.items() if Path(k).stem == leaf}
            packed_mesh = canopy_members(b)
            require(leaf + ".uasset" in packed_mesh and packed_mesh == canopy_members(shipping),
                    "Canopy authored and checked in Shipping differs from the packaged map geometry")
            new_canopy = {"source_and_cooked": geometry, "shipping_to_map_members_sha256": packed_mesh}
        floor = args.art / ("floor" if banks else "verges")
        physics = old["collision"]
        extra = {key: val for key,val in EXTRA_ACTORS.items() if (args.art / key / "verges.json").is_file()}
        pine = args.art / "pine" if "pine" in extra else None
        inherited_pine = pine and control and (control.parent / "pine/verges.json").is_file()
        if banks:
            bank_geometry = inspect_bank_geometry(args, scratch / "textures")
            if litter:
                bank_geometry["forest_debris"] = inspect_litter_geometry(
                    args, scratch / "textures"
                )
            trimmed = None
            if pine and control:
                verify_parent_scenery(args.art, control.parent)
                if inherited_pine:
                    verify_parent_actors(args.art, control.parent, extra, PAVED_ACTORS if paved_update else ())
                dressing_release = inherited_dressing_release(control)
                earlier = dressing_release.parent.parent / "round19/saturday.19"
                dressing_parent = jsonfile(dressing_release / "receipt.json")["surface_comparison"]
                require(jsonfile(earlier / "receipt.json")["sha256"] == dressing_parent["baseline_sha256"],
                        "Different base for inherited roadside clearances")
                gravel_edit, trimmed = verify_dressing_edits(dressing_release.parent, earlier)
            elif (args.art / "road-dressing.json").is_file() and control:
                gravel_edit, trimmed = verify_dressing_edits(args.art, control)
            else:
                gravel_edit = verify_gravel_revision(floor, control) if control else {}
            if control is None:
                verify_cumulative_floor(floor)
            structural_dir = pine or args.art / "verges"
            structural = jsonfile(structural_dir / "structural.json")
            parent_bsp = control.parent / "verges/physics/pwr.sbsp" if pine else None
            if pine:
                reference_bsp = comparison["collision"]["base_sbsp" if inherited_pine else "sbsp"]
                require(sha(parent_bsp) == reference_bsp and len(structural) == 1,
                        "Single new trunk must extend the compared release's verified collision")
            world, physics, members = cook_collision(
                args, world, scratch, base_bsp=BSP, expected_objects=len(structural),
                structural_folder=structural_dir, previous_bsp=parent_bsp)
            require(
                {s["name"]: s["faces"] for s in structural}
                == {o["name"]: o["surfaces"] for o in physics["objects"]},
                "Appended hull objects differ from structure",
            )
            if comparison:
                previous_world = control / "map-input" / (WORLD + ".utoc")
                if pine and not inherited_pine:
                    require(physics["base_sbsp"] == comparison["collision"]["sbsp"] and len(physics["objects"])==1,
                            "Tree collision does not extend the selected world")
                    old_world, current_world = world_entries(previous_world), world_entries(world)
                    require(old_world.keys()==current_world.keys(), "Unexpected native world package inventory change")
                    modified = sorted(k for k,h in old_world.items() if current_world[k]!=h)
                    require(set(modified)-set(members)=={"Meteorite/Content/Levels/Halo1/Solo/PWR/PWR.umap"}
                            and set(members)<=set(modified), "Unexpected native changes outside the tree and Unreal scenery")
                    same_world={"changed":modified}
                else:
                    require(physics == comparison["collision"], "Native collision proof differs from the comparison build")
                    if shader_only:
                        a_world, b_world = world_entries(previous_world), world_entries(world)
                        changed_world = [k for k in set(a_world) | set(b_world) if a_world.get(k)!=b_world.get(k)]
                        require(len(changed_world)==1 and changed_world[0].endswith("/PWR/PWR.umap"),
                                "Native world differs outside the terrain material permutation: "+str(changed_world))
                        shader_world = validated_shader_worlds(args,control,comparison,shaders,land,previous_world,world,scratch)
                        same_world = {"changed":changed_world}
                    else:
                        same_world = verify_world(previous_world, world)
                        if sun_patches or paved_update:
                            require(len(same_world["changed"])==1 and same_world["changed"][0].endswith("/PWR/PWR.umap"),
                                    "World bulk changed in a bounded lighting and surface pass")
                            allowed_roots=[r["name"] for r in jsonfile(args.art/"light/bend-sun-patches.json")["spots"]] if sun_patches else (
                                [EXTRA_ACTORS[k][0] for k in PAVED_ACTORS if k in extra and
                                 not (control.parent / k / "verges.json").is_file()])
                            patch_scene = verify_local_patch_world(control.parent/"native/LPE.umap",args.native/"LPE.umap",
                                allowed_roots)
                old_assets = world_entries(control / "map-input" / (LAND + ".utoc"))
                new_only = set(b) - set(old_assets)
                created_mesh = PINE_OPEN.removeprefix("/Game/")
                if opened and not has_open_pine(control.parent):
                    require(created_mesh + ".uasset" in new_only and
                            new_only <= {created_mesh + ext for ext in (".uasset",".ubulk")},
                            "Unexpected native package beyond the isolated bend canopy")
                else:
                    require(not new_only, "Native asset added without a scoped source geometry")
                require(set(old_assets)<=set(b), "Native playtest assets removed from comparison")
                different = sorted(k for k in old_assets if old_assets[k] != b[k])
                surface_assets = {"M_PWRPilot.uasset", FIELD + ".uasset", FIELD + ".ubulk", DETAIL + ".uasset", DETAIL + ".ubulk", "LPE.umap", "LPE.ubulk"}
                require(all(Path(k).name in surface_assets or k.endswith(".ushaderbytecode") for k in different), "Unrelated comparison terrain packages changed: " + str(different))
                if shader_only or sun_patches or paved_update:
                    require({Path(k).name for k in different} == {"M_PWRPilot.uasset", "LPE.umap",
                                "ShaderArchive-Meteorite_Chunk965-PCD3D_SM6-PCD3D_SM6.ushaderbytecode"},
                            "Unexpected native change beyond the terrain shader: "+str(different))
                same_bank = jsonfile(control.parent / "verges/verges.json")
                if not (args.art / "road-dressing.json").exists():
                    require(same_bank == jsonfile(args.art / "verges/verges.json"), "Bank, litter or root setup changed")
                comparison_scope = {"baseline": comparison["archive"], "baseline_sha256": comparison["sha256"],
                                    ("appended_collision_sha256" if pine and not inherited_pine else "unchanged_collision_sha256"): physics["sbsp"], "changed_world": same_world["changed"],
                                    "changed_landscape": different, "added_landscape": sorted(new_only), "gravel_groups": gravel_edit}
            proof["changed"] = sorted(proof["changed"] + members)
            for name in members:
                del proof["preserved"][name]
        foliage = inspect_foliage(
            args,
            world,
            scratch,
            component_prefix="PWRSweep_",
            folder=floor,
            split=OUTCROP_SPLIT if banks else None,
            trimmed=trimmed if banks else None,
            extra_actors=tuple(v[0] for v in extra.values()),
        )
        verify_sweep_components(
            scratch / "candidate-PWR.umap", folder=floor, prefix="PWRSweep_"
        )
        foliage["component_readback"] = jsonfile(floor / "cooked-world.json")
        if banks:
            bank = jsonfile(args.art / "verges/verges.json")
            (outcrop,) = [g for g in bank["groups"] if g["key"] == "NoSnow"]
            (stock,) = [
                g
                for g in jsonfile(FAMILY / "verges/verges.json")["groups"]
                if g["key"] == "Outcrop"
            ]
            require(
                bank["actor"] == OUTCROP_SPLIT[1][0]
                and outcrop["mesh"] == stock["mesh"]
                and outcrop["count"] == 2,
                "Wrong snow-free split",
            )
            require(
                outcrop["material_package"]
                == "/Game/Env/Bio/Rock/Glacial/Rock_Glacial_Med_A/Materials/MI_Rock_Glacial_Med_A_NoSnow",
                "Wrong snow-free material",
            )
            verify_sweep_components(
                scratch / "candidate-PWR.umap",
                folder=args.art / "verges",
                prefix="PWRSweepBank_",
            )
            foliage["bank_readback"] = jsonfile(args.art / "verges/cooked-world.json")
        for local,(name,prefix) in extra.items():
            foliage[local+"_readback"] = verify_added_actor(args.art,local,name,prefix,scratch / "candidate-PWR.umap")
        lights = inspect_lights(args, scratch / "candidate-PWR.umap", scratch)
        if sun_patches or paved_update:
            from visual_dressing.verify_sweep_sun_patches import verify as verify_sun_patches
            native_spots=verify_sun_patches(args.art,scratch/"candidate-PWR.umap",scratch)
        for src, dst in ((world, before), (land, old_land)):
            for ext in (".ucas", ".utoc"):
                p = dst.with_suffix(ext)
                shutil.copyfile(src.with_suffix(ext), p)
                expected["content/" + p.name] = sha(p)
    prior = jsonfile(inputs / "pwr.level.json")
    if prior != level:
        require(
            all(prior[k] == v for k, v in level.items() if k != "environment"),
            "Scenario gameplay data changed",
        )
        write_json(inputs / "pwr.level.json", level)
        expected["map/level.json"] = sha(inputs / "pwr.level.json")
    revision = {
        k: old[k]
        for k in (
            "collision",
            "baseline_collision_sha256",
            "art_scene_sha256",
            "native_gate_witnesses",
            "ridge_geometry",
            "ridge_native",
            "ridge_material",
            "foothill_contacts",
            "geology_pixels",
            "alpine_foliage",
        )
    }
    revision.update(
        world_packages=proof,
        terrain_assets_added=sorted(added),
        terrain_assets_changed=changed,
        environment=level["environment"],
        level_sections=["environment"] if prior != level else [],
        baseline_map=old["archive"],
        earth_finish=jsonfile(args.art / "earth/editor-verified.json"),
        sweep_textures=pixels,
        sweep_floor=foliage,
        shader_readback=shaders,
        sweep_lights=lights,
        fluid_flux_and_play_rules_preserved=True,
    )
    if banks:
        revision.update(
            collision=physics,
            baseline_collision_sha256=physics["base_sbsp"],
            sweep_bank_geometry=bank_geometry,
        )
    if new_canopy:
        revision["bend_canopy"] = new_canopy
    if comparison:
        if "detail_repack" in jsonfile(args.art / "earth/roadbed.json"):
            if shader_only or sun_patches or paved_update:
                src_spec = jsonfile(args.art / "earth/roadbed.json")
                require(src_spec["detail_repack"] == comparison["surface_comparison"]["detail_repack"] and
                        src_spec["previous_detail_sha256"] == sha(control.parent/"earth/sweep-floor-detail.png"),
                        "Inherited mineral, duff or pocket strip provenance changed")
                comparison_scope["detail_repack"] = src_spec["detail_repack"]
                comparison_scope["changed_detail_pixels"] = 0
            else:
                comparison_scope["detail_repack"] = verify_repacked_detail(args.art, control)
        if (args.art / "earth/route-coverage.png").exists():
            if not (shader_only or sun_patches or paved_update) and pine and sha(args.art / "earth/alpine-roadbed.png") == sha(control.parent / "earth/alpine-roadbed.png"):
                comparison_scope["bounded_road_coverage"] = comparison["surface_comparison"]["bounded_road_coverage"]
            else:
                comparison_scope["bounded_road_coverage"] = verify_bend_mask(args.art, control)
        revision["surface_comparison"] = comparison_scope
        if shader_only:
            revision["terrain_shader_only"] = True
            revision["native_landscape_shader_bindings"] = shader_world
        if sun_patches or paved_update:
            revision["bounded_local_sun"] = native_spots
            revision["unchanged_ground_and_scene"] = patch_scene
        if sun_patches:
            revision["puddle_margin_shader"] = verify_near_puddle_shader(args.art,control)
    seal_release(args, release, inputs, old, expected, manifest, revision)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--art", type=Path, default=ROOT / "out/pwr/sweep-polish")
    p.add_argument("--baseline", type=Path, default=BASE)
    p.add_argument("--comparison-release", type=Path, help="Verified sweep release whose collision, scenery and other assets must be preserved")
    p.add_argument("--terrain-shader-only", action="store_true", help="Require the native world, physical terrain and scenery assets to be identical to the compared release")
    p.add_argument("--local-sun-patches", action="store_true", help="Allow selected native spotlights and the terrain shader while preserving the entire previous road and scenery")
    p.add_argument("--paved-road-update", action="store_true", help="Keep existing road/scene/lighting and allow the single authored main-road verge actor and terrain shader")
    p.add_argument("--version", default="0.1.0-playtest.15")
    p.add_argument("--out", type=Path)
    p.add_argument(
        "--paks",
        type=Path,
        default=Path(
            "C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks"
        ),
    )
    p.add_argument("--cli", type=Path, default=ROOT / "target/release/mjolnir.exe")
    p.add_argument(
        "--bake-cli",
        type=Path,
        default=ROOT / "out/pwr/toolchain-grass-v7/r2/mjolnir.exe",
    )
    args = p.parse_args()
    args.art = args.art.resolve()
    args.staged = (
        args.art / "editor/Meteorite/Saved/StagedBuilds/Windows/Meteorite/Content/Paks"
    )
    args.native = args.art / "native"
    if args.native.exists():
        staged_toc = args.staged / "pakchunk965-Windows.utoc"
        cached = args.native / "stock" / staged_toc.name
        if (
            not cached.is_file()
            or sha(staged_toc) != sha(cached)
            or not (args.native / "native.json").is_file()
        ):
            args.native = args.art / (
                "native-" + args.version.rsplit(".", 1)[-1] + "-" + sha(staged_toc)[:12]
            )
    args.out = args.out or args.art / ("saturday." + args.version.rsplit(".", 1)[1])
    if args.out.exists():
        raise FileExistsError(args.out)
    level = native_world(args)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as tmp:
        release = Path(tmp) / "release"
        release.mkdir()
        stage(args, level, release)
        release.rename(args.out)
    print("Sealed", args.out)


if __name__ == "__main__":
    main()
