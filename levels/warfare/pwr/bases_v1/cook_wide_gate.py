"""Reprofile the named rear jambs in the .5 collision and append new closed modules."""
import argparse
from pathlib import Path
import struct
import subprocess

import numpy as np

from cook_polish_collision import (
    ROOT, FORMATS, MAX_SURFACES, arrays, extend_arrays, jsonfile, sha,
    triangles_intersect_box, verify_cores, write_json,
)


def rings(source, ids):
    surfaces = np.frombuffer(source["surfaces"], dtype="<i4").reshape(-1,3)
    edges = np.frombuffer(source["edges"], dtype="<i4").reshape(-1,6)
    vertices = np.frombuffer(source["vertices"], dtype="<f4").reshape(-1,4)
    first = surfaces[ids,1]
    ring = np.stack([first,edges[first,2],edges[edges[first,2],2]],axis=1)
    if not np.array_equal(edges[ring[:,2],2],first) or not np.all(edges[ring,4] == ids[:,None]):
        raise ValueError("Changes must target independently owned triangular rings")
    vertex_ids = edges[ring,0]
    return surfaces[ids,0],vertex_ids,vertices[vertex_ids,:3].astype(float)


def check_apertures(arrays_new, manifest, origins, boxes):
    first = manifest["counts"]["surfaces"]-manifest["scenery_surfaces"]["surfaces"]
    for start in range(first,manifest["counts"]["surfaces"],65000):
        end = min(start+65000,manifest["counts"]["surfaces"])
        points = rings(arrays_new,np.arange(start,end))[2]
        for site,bounds in boxes.items():
            for box in bounds:
                lo = (np.array(box["min"])+origins[site])/3.048
                hi = (np.array(box["max"])+origins[site])/3.048
                hits = triangles_intersect_box(points,lo,hi)
                if len(hits):
                    raise ValueError(f"{site} clear opening intersects source face(s) {(hits[:8]+start).tolist()}, {box}")


def verify_packed(out, cooked, source_ids, target):
    reader = ROOT/"target/release/examples/readback_surfaces.exe"
    actual = np.empty_like(target)
    covered = np.zeros(len(source_ids),dtype=np.uint8)
    for piece in cooked["pieces"]:
        span = piece["source_surface_range"]
        if not span:
            continue
        selected = np.flatnonzero((source_ids >= span[0]) & (source_ids < span[1]))
        if not len(selected):
            continue
        region = source_ids[selected]
        first,end = int(region.min()),int(region.max()+1)
        result = out/f"instance-{piece['instance']}-surfaces.f32"
        subprocess.run([str(reader),str(out/"pwr.sbsp"),str(piece["instance"]),str(first-span[0]),
                        str(end-span[0]),str(result)],check=True)
        decoded = np.fromfile(result,dtype="<f4").reshape((-1,3,3))
        actual[selected] = decoded[region-first]
        bounds = piece["bounds_wu"]
        if np.any(actual[selected] < np.array(bounds["min"])-1e-4) or np.any(actual[selected] > np.array(bounds["max"])+1e-4):
            raise ValueError("Native instance does not encompass the revised physical faces")
        covered[selected] += 1
    if not np.all(covered == 1):
        raise ValueError("Native instance ranges omitted or double-owned revised faces")
    errors = [np.linalg.norm(actual-np.roll(target,i,axis=1),axis=2).max(axis=1) for i in range(3)]
    error = float(np.minimum.reduce(errors).max()*3.048)
    if error > .0005:
        raise ValueError(f"Cooked gate/structural polygons moved {error} m")
    return error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("physics","baseline-art","art","patch","contract","out","paks","cli"):
        parser.add_argument("--"+arg,type=Path,required=True)
    parser.add_argument("--oodle",type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    base = jsonfile(args.physics/"collision-proof.json")
    old_receipt = jsonfile(args.physics/"native-collision-receipt.json")
    old_path = args.physics/"collision_scene.json"
    old = jsonfile(old_path)
    old_bin = args.physics/old["bin"]
    if (sha(old_bin) != old_receipt["source_binary_sha256"] or sha(old_path) != old_receipt["source_manifest_sha256"]
        or sha(args.physics/"pwr.sbsp") != base["sbsp"] or base["sbsp"] != old_receipt["output_sha256"]):
        raise ValueError("The .5 native physical input has changed")
    previous = arrays(old_bin,old)
    previous_cores = jsonfile(args.baseline_art/"solid-cores.json")
    a = jsonfile(args.art/"base-polish.json")
    cores = jsonfile(args.art/"solid-cores.json")
    if sha(args.art/"solid-cores.json") != a["collision_sha256"] or sha(args.baseline_art/"solid-cores.json") != base["core_export_sha256"]:
        raise ValueError("Art solid cores disagree with their sealed scene")
    origins = {k:np.array(x) for k,x in base["site_origins_blender_m"].items()}
    models = {site:[(ob["name"],np.array(ob["points"])[ob["faces"]]) for ob in group] for site,group in cores.items()}
    verify_cores(a,models)
    appended = []
    new_names = []
    for site,group in cores.items():
        kept = {o["name"]:o for o in previous_cores[site]}
        for ob in group:
            if ob["name"] in kept:
                prior = kept.pop(ob["name"])
                if ob["faces"] != prior["faces"] or not np.allclose(ob["points"],prior["points"],atol=1e-6,rtol=0):
                    raise ValueError(f"Unreviewed modification to old .5 physical core: {ob['name']}")
            else:
                appended.extend((np.array(ob["points"])[ob["faces"]]+origins[site])/3.048)
                new_names.append((site,ob["name"],len(ob["faces"])))
        if kept:
            raise ValueError(f"Lost old .5 physical cores in {site}: {list(kept)}")
    legacy = jsonfile(args.contract)
    frozen_proof = jsonfile(ROOT/"out/pwr/base-runtime/compiled-base-collision-proof.json")
    if (sha(args.contract) != frozen_proof["contract_sha256"] or
        frozen_proof["compiled_collision_sha256"] != base["base_sbsp"]):
        raise ValueError("Legacy per-object contract is not the archived base collision")
    spans = {(r["team"],r["name"]):r for r in legacy["replacement_objects"]}
    offset = legacy["counts"]["expected_global"]-legacy["counts"]["total_extra"]
    patched_planes = bytearray(previous["planes"])
    patched_vertices = bytearray(previous["vertices"])
    source_ids = []
    targets = []
    all_planes = []
    all_vertices = []
    records = []
    patch = jsonfile(args.patch)
    if patch["scene_sha256"] != a["scene_sha256"] or patch["source_sha256"] != jsonfile(args.baseline_art/"base-polish.json")["scene_sha256"]:
        raise ValueError("Gate reshape and additions were exported from different review scenes")
    for ob in patch["objects"]:
        if not ob["structural"]:
            continue
        site,name = ob["site"],ob["name"]
        record = spans[site,name]
        if any(record[k] != v for k,v in ob["previous_native_span"].items()):
            raise ValueError("Stale source range on a revised portal casting: " + name)
        if (not any(part in name for part in ("portal/monolithic outer jamb","portal/dark rebated ring","portal/rear inner armored surround"))
            or record["module_role"] != "portal" or record["surfaces"] != 12):
            raise ValueError("Unexpected structure requested for native surgery: "+name)
        start = offset+record["first_extra_surface"]
        ids = np.arange(start,start+record["surfaces"])
        plane_ids,vert_ids,triangles = rings(previous,ids)
        p = triangles*3.048-origins[site]
        reference = np.array(ob["old_local_m"])
        replacement = np.array(ob["new_local_m"])
        if reference.shape != replacement.shape or not np.isfinite(replacement).all():
            raise ValueError("Invalid authored gate delta")
        distances = np.linalg.norm(p[:,:,None,:] - reference[None,None,:,:],axis=3)
        nearest = np.argmin(distances,axis=2)
        if distances.min(axis=2).max() > .0005:
            raise ValueError(f"Native source disagrees with old visual shell of {site}/{name} by {distances.min(axis=2).max()} m")
        updated = (replacement[nearest]+origins[site])/3.048
        for plane,vertices,t in zip(plane_ids,vert_ids,updated):
            norm = np.cross(t[1]-t[0],t[2]-t[0])
            length = np.linalg.norm(norm)
            if length < 1e-10:
                raise ValueError("Gate deformation collapsed a native face")
            norm /= length
            struct.pack_into(FORMATS["planes"],patched_planes,int(plane)*16,*norm,norm@t[0])
            for vertex,xyz in zip(vertices,t):
                struct.pack_into("<fff",patched_vertices,int(vertex)*16,*xyz)
        all_planes.extend(plane_ids)
        all_vertices.extend(vert_ids.ravel())
        source_ids.extend(ids)
        targets.extend(updated)
        records.append({"site":site,"name":name,"source_range":[int(ids[0]),int(ids[-1])+1]})
    if (len(records) != 63 or len(set(source_ids)) != 756 or len(set(all_planes)) != 756 or
        len(set(all_vertices)) != 3*756 or {r["site"] for r in records} != set(origins)):
        raise ValueError("Expected the 63 unique original gate castings and their exclusive triangle records")
    # Verify that neither the shell nor unrelated standalone surfaces share
    # a selected vertex/plane. Only the first four bytes of a surface name its plane.
    all_surface_planes = np.frombuffer(previous["surfaces"],dtype="<i4").reshape(-1,3)[:,0] & 0x7fffffff
    if np.isin(all_surface_planes,all_planes).sum() != len(all_planes):
        raise ValueError("Some modified planes were shared by another surface")
    edges = np.frombuffer(previous["edges"],dtype="<i4").reshape(-1,6)
    if (np.isin(edges[:,0],all_vertices).sum() != len(all_vertices) or
        np.isin(edges[:,1],all_vertices).sum() != len(all_vertices)):
        raise ValueError("Some modified vertices were shared by another ring")
    additions = np.array(appended)
    if len(new_names) != 3 or {site for site,_,_ in new_names} != set(origins):
        raise ValueError(f"Expected one new structural brow per site: {new_names}")
    original_count = old["counts"]["surfaces"]
    if original_count+len(additions) > MAX_SURFACES:
        raise ValueError("The structural additions exceed the known collision budget")
    material, = [m["index"] for m in old["materials"] if m.get("game_material")=="hard_metal_thick"]
    extra = extend_arrays(additions,old["counts"],material)
    manifest = jsonfile(old_path)
    with (out/old_bin.name).open("xb") as stream:
        for k in old["array_order"]:
            edited = {"planes":patched_planes,"vertices":patched_vertices}.get(k,previous[k])
            manifest["counts"][k] += len(extra[k])//struct.calcsize(FORMATS[k])
            stream.write(struct.pack("<I",manifest["counts"][k]))
            stream.write(edited)
            stream.write(extra[k])
    manifest["scenery_surfaces"]["objects"] += len(new_names)
    manifest["scenery_surfaces"]["surfaces"] += len(additions)
    manifest_path = out/old_path.name
    write_json(manifest_path,manifest)
    revised = arrays(out/old_bin.name,manifest)
    for k in old["array_order"]:
        prefix = revised[k][:len(previous[k])]
        size = struct.calcsize(FORMATS[k])
        if k in ("planes","vertices"):
            selected = all_planes if k=="planes" else all_vertices
            before = np.frombuffer(previous[k],dtype="u1").reshape(-1,size)
            after = np.frombuffer(prefix,dtype="u1").reshape(-1,size)
            changed = np.flatnonzero(np.any(before!=after,axis=1))
            if not set(changed).issubset(selected) or (k=="vertices" and not np.array_equal(before[:,12:],after[:,12:])):
                raise ValueError("Unrelated native records changed")
        elif prefix != previous[k]:
            raise ValueError("Legacy source array changed: "+k)
    checks = {site:[v["route"]["protected_bounds_m"]] for site,v in patch["validation"].items() if v["route"]["passed"]}
    if set(checks)!=set(origins) or any(not v for v in checks.values()):
        raise ValueError("Missing aperture witness volumes")
    check_apertures(revised,manifest,origins,checks)
    source_ids.extend(range(original_count,original_count+len(additions)))
    targets.extend(additions)
    source_ids = np.array(source_ids)
    targets = np.array(targets)
    packed_source = rings(revised,source_ids)[2]
    if not np.array_equal(packed_source.astype("<f4"),targets.astype("<f4")):
        raise ValueError("World-space physical source did not match edited geometry")
    cmd = [args.cli,"level","collision",manifest_path,"--paks",args.paks,"--own-bsp","--bsp-index","0",
           "--receipt",out/"native-collision-receipt.json","--out",out/"pwr.sbsp"]
    if args.oodle:
        cmd.extend(["--oodle",args.oodle])
    with (out/"native.log").open("w") as stream:
        subprocess.run(cmd,check=True,stdout=stream,stderr=subprocess.STDOUT)
    cooked = jsonfile(out/"native-collision-receipt.json")
    if (cooked["source_surfaces"] != manifest["counts"]["surfaces"] or cooked["output_sha256"] != sha(out/"pwr.sbsp")
        or cooked["source_binary_sha256"] != sha(out/old_bin.name) or cooked["source_manifest_sha256"] != sha(manifest_path)):
        raise ValueError("Stale native gate cook")
    error = verify_packed(out,cooked,source_ids,targets)
    write_json(out/"collision-proof.json",{"base_sbsp":base["sbsp"],"sbsp":cooked["output_sha256"],
        "legacy_gate_objects":records,"reprofiled_surfaces":756,"preserved_surfaces":original_count-756,
        "new_solids":new_names,"added_surfaces":len(additions),"core_export_sha256":a["collision_sha256"],
        "opening_witnesses":checks,"readback_max_error_m":error,"root_and_definition_havok_verified_per_face":True,
        "all_other_native_surface_geometry_unchanged":True,"compiled_instance_bounds_checked":True,
        "site_origins_blender_m":base["site_origins_blender_m"],"live_physics_tested":False})


if __name__ == "__main__":
    main()
