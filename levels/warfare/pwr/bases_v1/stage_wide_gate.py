"""Seal the audited .6 art and collision against the immutable .5 archive."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np

from stage_base_polish import ROOT, WORLD, checked_world, unpack_map, seal_release
from stage_world_playtest import jsonfile, write_json, sha, load_container, read_chunk


def contents(path):
    container = load_container(path)
    files = {i:name for name,i in container.files.items()}
    result = {}
    for chunk in container.chunks:
        label = files.get(chunk.index,f"<{chunk.type_name}:{chunk.chunk_id:x}:{chunk.chunk_index}>")
        result[label] = hashlib.sha256(read_chunk(container,chunk)).hexdigest()
    return result


def gate_witnesses(args,physics):
    # The native reader writes the actual unpacked world-space rings of the
    # affected surface interval of each instance. Intersect those saved rings.
    receipt = jsonfile(args.collision/"native-collision-receipt.json")
    patch = jsonfile(args.patch)
    old_count = receipt["source_surfaces"]-physics["added_surfaces"]
    target = set(range(old_count,receipt["source_surfaces"]))
    site_ids = {k:[] for k in physics["site_origins_blender_m"]}
    for casting in physics["legacy_gate_objects"]:
        ids = list(range(*casting["source_range"]))
        site_ids[casting["site"]].extend(ids)
        target.update(ids)
    rings = {}
    for piece in receipt["pieces"]:
        interval = piece["source_surface_range"]
        if not interval:
            continue
        selected = sorted(target.intersection(range(*interval)))
        if not selected:
            continue
        path = args.collision/f"instance-{piece['instance']}-surfaces.f32"
        raw = np.fromfile(path,dtype="<f4").reshape((-1,3,3))
        if len(raw) != selected[-1]-selected[0]+1:
            raise ValueError("Cooked gate witness data has a truncated face span")
        bounds = piece["bounds_wu"]
        if np.any(raw < np.array(bounds["min"])-1e-4) or np.any(raw > np.array(bounds["max"])+1e-4):
            raise ValueError("Revised gate physical polygons lie outside their registered native body")
        rings.update((i,raw[i-selected[0]]) for i in selected)
    measurements = {}
    for site,ids in site_ids.items():
        tr = np.array([rings[i] for i in ids],dtype=float)*3.048-physics["site_origins_blender_m"][site]
        first,second = tr[:,1]-tr[:,0], tr[:,2]-tr[:,0]
        measurements[site] = {}
        for name,test in patch["validation"][site]["structural_witnesses"].items():
            origin = np.array(test["origin_m"])
            direction = np.array(test["direction"])
            h = np.cross(direction,second)
            denom = np.einsum("ij,ij->i",first,h)
            inv = np.divide(1.,denom,out=np.zeros(len(denom)),where=np.abs(denom)>1e-10)
            src = origin-tr[:,0]
            u = np.einsum("ij,ij->i",src,h)*inv
            q = np.cross(src,first)
            v = (q@direction)*inv
            d = np.einsum("ij,ij->i",q,second)*inv
            hits = d[(np.abs(denom)>1e-10)&(u>=-1e-6)&(v>=-1e-6)&(u+v<=1+1e-6)&(d>=0)]
            if not len(hits):
                raise ValueError(f"No native material at {site}/{name}")
            hit = origin + direction*hits.min()
            error = float(np.linalg.norm(hit-test["point_m"]))
            if error > .10:
                raise ValueError(f"Gate core disagrees with beveled visual witness at {site}/{name}: {error} m")
            measurements[site][name] = {"point_m":hit.tolist(),"beveled_visual_error_m":error}
    return measurements


def stage(args,out):
    inputs,info,expected,old_manifest = unpack_map(args.baseline,out)
    physics = jsonfile(args.collision/"collision-proof.json")
    visual = jsonfile(args.visual)
    physical_art = jsonfile(args.art/"base-polish.json")
    if (physics["base_sbsp"] != info["collision"]["sbsp"] or not physics["root_and_definition_havok_verified_per_face"]
        or not physics["all_other_native_surface_geometry_unchanged"]):
        raise ValueError("Gate physics does not descend from the paired .5 BSP")
    if (visual["core_export_sha256"] != physics["core_export_sha256"] or physical_art["scene_sha256"]!=visual["scene_sha256"]
        or sha(Path(physical_art["scene"])) != visual["scene_sha256"]):
        raise ValueError("Art and physics came from different gate scenes")
    world = checked_world(inputs,args,physics)
    measured = gate_witnesses(args,physics)
    if not visual["evidence"] or any(not Path(s).is_file() for s in visual["evidence"]):
        raise ValueError("Missing visual readback evidence")
    arch, = [Path(c["stem"]).parent for c in visual["containers"] if Path(c["stem"]).name.startswith("pakchunk955-")]
    aperture = jsonfile(arch/"aperture-and-frame-check.json")
    if not aperture["passed_clearance"] or set(aperture["sites"])!={"red","blue","green"}:
        raise ValueError("Visual aperture readback is incomplete")
    for site,tests in aperture["sites"].items():
        after = tests["after"]
        frame = after["tangent_frames"]["edited_gate_rendered"]
        if (after["nanite_faces_crossing_driving_volume"] or after["fallback_faces_crossing_driving_volume"]
            or frame["zero_tangents"] or frame["zero_normals"] or frame["invalid_handedness"]
            or frame["nonunit_tangents"] or frame["nonunit_normals"] or frame["maximum_abs_tangent_normal_dot"] > .001):
            raise ValueError(f"Visible gate clearance or native shading failed for {site}")
    changed_chunks = {}
    containers = visual["containers"]
    if {Path(c["stem"]).name.split("-")[0] for c in containers} != {"pakchunk953","pakchunk954","pakchunk955"}:
        raise ValueError("Expected only the additive mesh, portal guide, and original base art packages")
    for record in containers:
        stem = Path(record["stem"])
        old_toc, = inputs.glob(stem.name.split("-")[0]+"-*.utoc")
        if old_toc.stem != stem.name:
            raise ValueError("Replacement container changed its map-owned identity")
        previous = contents(old_toc)
        new = contents(stem.with_suffix(".utoc"))
        if previous.keys() != new.keys():
            raise ValueError(f"Unexpected asset or internal chunk inventory change for {stem.name}")
        changes = [k for k,v in previous.items() if new[k] != v]
        listed = set(record["changed_files"])
        if set(changes) != listed or not changes:
            raise ValueError(f"Readback changed unexpected assets in {stem.name}: {set(changes)^listed}")
        # The authorized meshes retain the exact public package identities;
        # existing base shader archives, terrain and art outside this
        # revision cannot change through an incidental whole-chunk recook.
        allowed = ("sm_pwr_basepolish_red","sm_pwr_basepolish_blue","sm_pwr_basepolish_green",
                   "sm_pwr_portalguides_red","sm_pwr_portalguides_blue","sm_pwr_portalguides_green",
                   "sm_pwr_red_architecture","sm_pwr_blue_architecture","sm_pwr_green_architecture",
                   "mi_pwr_alloy","mi_pwr_ramp_finish","mi_pwr_apron_finish",
                   "mi_pwr_apron_finish_v0","mi_pwr_apron_finish_v1","mi_pwr_apron_finish_v2")
        for key in changes:
            if key.startswith("<ContainerHeader:"):
                continue
            if Path(key).stem.lower() not in allowed:
                raise ValueError("Unrelated baked asset changed: "+key)
        for ext in (".utoc",".ucas"):
            src = stem.with_suffix(ext)
            if sha(src) != record["files"][ext]:
                raise ValueError("Release input differs from its visual readback")
            dst = inputs/src.name
            shutil.copyfile(src,dst)
            expected["content/"+dst.name] = sha(dst)
        changed_chunks[stem.name] = changes
    for ext in (".utoc",".ucas"):
        dst = inputs/(WORLD+ext)
        shutil.copyfile(args.bake/dst.name,dst)
        expected["content/"+dst.name] = sha(dst)
    level_path = inputs/"pwr.level.json"
    level = jsonfile(level_path)
    replacements = {row["id"]:row for row in visual["decor"]}
    allowed_ids = {prefix+site+suffix for site in ("red","blue","green") for prefix,suffix in
                   (("pwr_portal_guides_",""),("pwr_base_polish_",""),("pwr_newbase_","_architecture"))}
    if len(replacements) != len(visual["decor"]) or not replacements.keys() <= allowed_ids:
        raise ValueError("Unexpected spawn changes")
    changed_actors = []
    for i,old in enumerate(level["decor"]):
        if old["id"] not in replacements:
            continue
        row = replacements.pop(old["id"])
        if {k:v for k,v in old.items() if k not in ("pos","scale")} != {k:v for k,v in row.items() if k not in ("pos","scale")}:
            raise ValueError("Existing gameplay flags or asset identity changed for "+old["id"])
        if (len(row["pos"])!=3 or len(row["scale"])!=3 or not np.isfinite(row["pos"]).all()
            or not np.isfinite(row["scale"]).all() or min(row["scale"])<=0):
            raise ValueError("Invalid updated base art placement")
        if old != row:
            level["decor"][i] = row
            changed_actors.append(old["id"])
    if replacements:
        raise ValueError("New presentation tried to replace missing map actors")
    if changed_actors:
        write_json(level_path,level)
        expected["map/level.json"] = sha(level_path)
    seal_release(args,out,inputs,info,expected,old_manifest,{"world_packages":world,"collision":physics,
        "art_scene_sha256":visual["scene_sha256"],"native_visual_changes":changed_chunks,
        "visual_readback":str(args.visual.resolve()),"visual_readback_sha256":sha(args.visual),"native_gate_witnesses":measured,
        "level_sections":["decor"] if changed_actors else [],"changed_actors":changed_actors})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("baseline","control","bake","baseline-bsp","art","visual","collision","patch","out"):
        parser.add_argument("--"+k,type=Path,required=True)
    parser.add_argument("--version",default="0.1.0-playtest.6")
    parser.add_argument("--cli",type=Path,default=ROOT/"target/release/mjolnir.exe")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Choose a fresh output directory")
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.out.parent) as scratch:
        release = Path(scratch)/"release"
        release.mkdir()
        stage(args,release)
        os.rename(release,args.out)
    print(args.out)
