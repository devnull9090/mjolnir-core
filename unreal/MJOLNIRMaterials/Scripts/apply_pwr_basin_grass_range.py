"""Move the new .38 bank grasses to distance cohorts without touching other foliage."""
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import traceback
import unreal as ue

ROOT=Path(os.environ["PWR_HEADWATER_ROOT"])
BASE=ROOT/"out/pwr/river-basin"
OUT=BASE/"shore-contact/native"
VERIFY=os.environ.get("PWR_HEADWATER_VERIFY")=="1"
OWNER="PWR_BasinShoreGrass"
BANDS=8
SPEC={
    "fine_a":("PWR_FineMeadow","PWRBlade_MJFol_1_1_0",18800,31800),
    "fine_b":("PWR_FineMeadow","PWRBlade_MJFol_2_1_0",19600,32700),
    "sedge":("MJOLNIR_Foliage","MJFol_2_1_0",20400,33500),
}


def read(path):
    return json.loads(path.read_text())


def components():
    result={}
    for actor in ue.get_editor_subsystem(ue.EditorActorSubsystem).get_all_level_actors():
        if actor.get_actor_label() in {OWNER,"PWR_FineMeadow","MJOLNIR_Foliage"}:
            for comp in actor.get_components_by_class(ue.InstancedStaticMeshComponent):
                result[actor.get_actor_label(),comp.get_name()]=(actor,comp)
    return result


def pack(t):
    return struct.pack("<10f",*t.translation.to_tuple(),*t.rotation.to_tuple(),*t.scale3d.to_tuple())


def prefix_digest(c,count):
    h=hashlib.sha256()
    for i in range(count):h.update(pack(c.get_instance_transform(i,True)))
    return h.hexdigest()


def visible(camera,p):
    # Horizontal FOV at native 16:9 (the gallery persists Unreal pitch then yaw).
    px,py,pz,pitch,yaw,fov=camera
    cp,sp=math.cos(math.radians(pitch)),math.sin(math.radians(pitch))
    cy,sy=math.cos(math.radians(yaw)),math.sin(math.radians(yaw))
    x,y,z=(p[0]-px,p[1]-py,p[2]-pz)
    along=(x*cy+y*sy)*cp+z*sp
    horizontal=-x*sy+y*cy
    vertical=-(x*cy+y*sy)*sp+z*cp
    radius=math.tan(.5*math.radians(fov))*along
    return along>0 and abs(horizontal)<=radius and abs(vertical)<=radius*9./16.


def protective_names(levels):
    cs=components()
    for g in range(1,len(SPEC)+1):
        for b in range(1,BANDS+1):
            bare=f"MJFol_{g}_{b}_0"
            name=f"PWRShore_{g}_{b}"
            if (OWNER,bare) in cs:
                comp=cs[OWNER,bare][1]
                comp.modify();comp.rename(name)
                if comp.get_name()!=name:raise ValueError("Failed to reserve native shore HISM name")
            elif (OWNER,name) not in cs:
                raise ValueError("Missing "+name)
    if not levels.save_current_level():raise ValueError("Could not save protected shore HISM names")
    (OUT/"protected-names.json").write_text(json.dumps(dict(prefix="PWRShore_",components=24)))

def main():
    levels=ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    assert levels.load_level("/Game/Levels/Halo1/Solo/LPE/LPE")
    if os.environ.get("PWR_SHORE_PROTECT_NAMES")=="1":
        protective_names(levels);return
    world=ue.get_editor_subsystem(ue.UnrealEditorSubsystem).get_editor_world()
    counts=read(BASE/"basin-plant-counts.json")
    planted=read(BASE/"basin-plants.json")
    cameras=read(ROOT/"out/pwr/alpine-target/bench/river-basin-38/water/photos.json")["views"]
    cs=components()
    owner={}
    previous=read(OUT/"grass-applied.json") if VERIFY else {}
    placements={}; visuals={}
    binary=OUT/"shore-grass.bin"
    groups=bytearray(b"MJF3"+struct.pack("<II",3,len(SPEC)))
    for group,(kind,(label,name,start,end)) in enumerate(SPEC.items(),1):
        a,c=cs[label,name]
        base=counts[kind]["before"];n=counts[kind]["added"]
        if c.get_instance_count()!=base+(0 if VERIFY else n):raise ValueError((kind,"source count",base,n,c.get_instance_count()))
        if c.get_editor_property("num_custom_data_floats")!=0:raise ValueError("Unexpected custom instance payload")
        vis=dict(overrides=[m.get_path_name() if m else None for m in c.get_editor_property("override_materials")],
                 cast_shadow=c.get_editor_property("cast_shadow"),mesh=c.get_editor_property("static_mesh").get_path_name(),
                 wpo=bool(c.get_editor_property("evaluate_world_position_offset")),
                 wpo_disable=c.get_editor_property("world_position_offset_disable_distance"),
                 previous_cull=[c.get_editor_property(n) for n in ("instance_start_cull_distance","instance_end_cull_distance")])
        visuals[kind]=vis
        prefix=prefix_digest(c,base)
        if VERIFY:
            if prefix!=previous[kind]["prefix"] or vis!=previous[kind]["visual"]:raise ValueError("Pre-.38 game vegetation changed: "+kind)
            exact=Path(str(binary)+".xf"+str(group)).read_bytes()
            placements[kind]=[struct.unpack_from("<10f",exact,i*40) for i in range(n)]
        else:
            a.modify();c.modify();exact=bytearray();items=[]
            for i,r in enumerate(planted[kind]):
                t=c.get_instance_transform(base+i,True)
                if math.dist(t.translation.to_tuple(),r["position"])>.1:raise ValueError("Source is not registered .38 bank")
                raw=pack(t);exact.extend(raw);items.append(struct.unpack("<10f",raw))
            Path(str(binary)+".xf"+str(group)).write_bytes(exact)
            groups.extend(struct.pack("<I",n))
            for item in items:groups.extend(struct.pack("<3fBBbb3B",*item[:3],0,100,0,0,255,255,255))
            placements[kind]=items
            previous[kind]=dict(prefix=prefix,visual=vis,source_before=base+n,retained=base,
                                positions_sha256=hashlib.sha256(exact).hexdigest())
    if not VERIFY:
        if any(owner==OWNER for owner,_ in cs):raise ValueError("Duplicate local shore cohort")
        binary.write_bytes(groups)
        count=ue.MjolnirUIBuilderLibrary.bake_foliage(world,str(binary),OWNER,[visuals[k]["mesh"] for k in SPEC],
                    [BANDS]*len(SPEC),[ue.Vector2D(v[2],v[3]) for v in SPEC.values()],
                    [32+int(v["cast_shadow"])+(0 if v["wpo"] else 2) for v in visuals.values()])
        if count!=sum(map(len,placements.values())):raise ValueError("Native cohort count mismatch")
        # The shipping foliage loader remaps any generic MJFol_* component by group index.
        # These native scene-owned groups must not enter that loader.
        for g in range(1,len(SPEC)+1):
            for b in range(1,BANDS+1):
                comp=components()[OWNER,f'MJFol_{g}_{b}_0'][1]
                comp.modify();comp.rename(f'PWRShore_{g}_{b}')
        cs=components()
    proof={};coverage={k:dict(in_frustum=0,distance_visible_before=0,distance_visible_after=0,frustum_visible_before=0,frustum_visible_after=0) for k in cameras}
    for group,(kind,(label,name,start,end)) in enumerate(SPEC.items(),1):
        source=cs[label,name][1]
        old=previous[kind];items=placements[kind];vis=visuals[kind];cuts=[]
        if not VERIFY:
            # All new points occupy the tail of the pre-existing component. Reverse removal leaves every prefix index untouched.
            for i in range(old["source_before"]-1,old["retained"]-1,-1):
                if not source.remove_instance(i):raise ValueError("Cannot migrate tail of "+kind)
            if prefix_digest(source,old["retained"])!=old["prefix"]:raise ValueError("Original foliage ordered transforms changed")
        for b in range(BANDS):
            new=cs[OWNER,f"PWRShore_{group}_{b+1}"][1]
            far=int(start+(end-start)*(b+1)/BANDS)
            near=max(0,far-6400)
            if not VERIFY:
                new.modify()
                for i,path in enumerate(vis["overrides"]):
                    if path:new.set_material(i,ue.load_asset(path))
                new.set_evaluate_world_position_offset(vis["wpo"])
                new.set_world_position_offset_disable_distance(vis["wpo_disable"])
                new.set_cull_distances(near,far)
            if [new.get_editor_property(k) for k in ("instance_start_cull_distance","instance_end_cull_distance")]!=[near,far]:raise ValueError("Shore range not retained")
            if new.get_editor_property("static_mesh").get_path_name()!=vis["mesh"] or [m.get_path_name() if m else None for m in new.get_editor_property("override_materials")]!=vis["overrides"]:raise ValueError("Mesh/material identity changed")
            rows=items[b::BANDS]
            if new.get_instance_count()!=len(rows):raise ValueError("New bank cohort length mismatch")
            for i,r in enumerate(rows):
                t=new.get_instance_transform(i,True);actual=struct.unpack("<10f",pack(t))
                if math.dist(r[:3],actual[:3])>.03 or math.dist(r[7:],actual[7:])>.0001 or min(math.dist(r[3:7],actual[3:7]),math.dist([-x for x in r[3:7]],actual[3:7]))>.0001:raise ValueError("New bank foliage pose changed")
                for camera_key,cam in cameras.items():
                    dist=math.dist(r[:3],cam[:3]);previously=dist<vis["previous_cull"][1];after=dist<far
                    inframe=visible(cam,r[:3]);v=coverage[camera_key];v["in_frustum"]+=inframe;v["distance_visible_before"]+=previously;v["distance_visible_after"]+=after
                    v["frustum_visible_before"]+=bool(inframe and previously);v["frustum_visible_after"]+=bool(inframe and after)
            cuts.append(dict(start_m=near/100,end_m=far/100,count=len(rows)))
        proof[kind]=dict(count=len(items),original_cull_m=[x/100 for x in vis["previous_cull"]],cohorts=cuts,
                         retained_source_instances=old["retained"],unchanged_prefix_sha256=old["prefix"],
                         retained_transform_data_sha256=old["positions_sha256"],wpo_disable_m=vis["wpo_disable"]/100)
    if VERIFY:
        for cam in ("outlet","basin","overhead","waterline","east-bank"):
            if coverage[cam]["distance_visible_after"]<=.43*3646:raise ValueError("Insufficient coverage at "+cam)
        (OUT/"editor-verified.json").write_text(json.dumps(dict(points=sum(map(len,placements.values())),max_new_hism=len(SPEC)*BANDS,
            groups=proof,cameras=coverage,fading="Eight spatially interleaved groups per species with staggered native endpoints and 64 m fade intervals; actual masked opacity depends on the mesh material."),indent=2))
    else:
        assert levels.save_current_level()
        (OUT/"grass-applied.json").write_text(json.dumps(previous,indent=2))
        (OUT/"protected-names.json").write_text(json.dumps(dict(prefix="PWRShore_",components=24)))

try:main()
except:
    (OUT/("verify.err" if VERIFY else "apply.err")).write_text(traceback.format_exc());raise
