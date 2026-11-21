"""Author the finalized Gaea world through Blender MCP, preserving a reusable kit.

Requires matching final-master and adaptive collision receipts. No game install.
Run only after the current Blender scene owner hands off the authoring session.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
sys.path.insert(0,str(REPO/"tools/level"));sys.path.insert(0,str(HERE))
from heightfield import load_heightfield,sha256
from world_geometry import sealed_air,base_parts,bridge_parts,road_surfaces,orient_closed

WU=3.048

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--master",type=Path,required=True)
    p.add_argument("--collision-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--sky-z",type=float,default=650)
    p.add_argument("--allow-unverified-collision",action="store_true")
    p.add_argument("--no-export",action="store_true")
    p.add_argument("--static-terrain",action="store_true",help="Small membership core; terrain physics supplied by separate native static pieces")
    a=p.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    field=load_heightfield(a.master)
    report=json.loads((a.collision_dir/"collision-report.json").read_text())
    if report["master_manifest_sha256"]!=field.manifest_sha256:
        raise ValueError("Collision mesh does not match the final master heightfield")
    if not report["accuracy_and_mesh_budget_pass"] and not a.allow_unverified_collision:
        raise ValueError("Collision accuracy/budget gate failed; review the report before a research-only build")
    geometry_path=a.master.parent/field.metadata["geometry"]
    if sha256(geometry_path)!=field.metadata["geometry_sha256"]:
        raise ValueError("Finalized road/site geometry hash mismatch")
    geometry=json.loads(geometry_path.read_text())
    arrays=np.load(a.collision_dir/"collision-surface.npz",allow_pickle=False)
    if a.static_terrain:
        lo,hi=field.bounds_m
        floor_z=-20.
        if floor_z>=field.heights_m.min()-2:raise ValueError("Membership floor must be entirely below actual terrain")
        vertices=np.array([[lo[0],lo[1],floor_z],[hi[0],lo[1],floor_z],[hi[0],hi[1],floor_z],[lo[0],hi[1],floor_z]])
        triangles=np.array([[0,1,2],[0,2,3]])
    else:vertices,triangles=arrays["vertices_m"],arrays["triangles"]
    vertices,faces,ground_count=sealed_air(vertices,triangles,a.sky_z)
    parts=base_parts(geometry,REPO/"out/pwr/architecture-stock/hulls")+bridge_parts(geometry,field)
    # The direct Landscape road mask supplies the final PBR path material.
    # Keep authoritative cross-sections for decks, without CE dirt overlays.
    roads=[]
    output=a.out.resolve();output.mkdir(parents=True,exist_ok=True)

    import bpy,bmesh
    from mathutils import Matrix,Vector
    from mathutils.geometry import tessellate_polygon
    if not a.no_export:
        import addon_utils
        sys.path.insert(0,os.environ.get("HALO_BLENDER_ADDONS",r"C:\haloce\tools\halo-blender-425\addons"))
        assert addon_utils.enable("io_scene_halo",default_set=True,persistent=False)
    for old in list(bpy.data.objects):bpy.data.objects.remove(old,do_unlink=True)
    for old in list(bpy.data.meshes):bpy.data.meshes.remove(old,do_unlink=True)
    for old in list(bpy.data.materials):bpy.data.materials.remove(old,do_unlink=True)
    scene=bpy.context.scene
    scene.unit_settings.system="METRIC";scene.unit_settings.scale_length=WU
    if hasattr(scene,"halo"):scene.halo.game_title="halo1"
    frame=bpy.data.objects.new("frame",None);scene.collection.objects.link(frame)
    kit=bpy.data.collections.new("PWR_v3_SOURCE_reusable_kit")
    scene.collection.children.link(kit);kit.hide_render=True;kit.hide_viewport=True
    mats={}
    for key,name,color,policy in (
        ("ground","beach",(.25,.34,.16),"GROUND"),
        ("sky","+sky",(.3,.45,.6),"NONE"),
        ("metal","metal panels generic ext!",(.33,.4,.42),"NONE"),
        ("floor","metal plate floor ext!",(.2,.26,.28),"NONE"),
        ("clip","metal panels generic ext@",(.3,.3,.3),"NONE"),
        ("energy","dangercanyon_decor_strip_blue!",(.03,.58,.85),"NONE"),
        ("road","pwr_road!",(.25,.21,.16),"NONE"),
        ("water","pwr_water!",(.035,.23,.28),"NONE")):
        mat=bpy.data.materials.new(name);mat.diffuse_color=(*color,1);mat.use_nodes=True
        mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value=(*color,1)
        mat["mjolnir_pcg_policy"]=policy;mats[key]=mat

    def mesh(name,points,polygons,materials,indices=None):
        data=bpy.data.meshes.new(name);data.from_pydata([tuple(float(v)/WU for v in q) for q in points],[],polygons);data.update()
        obj=bpy.data.objects.new(name,data);scene.collection.objects.link(obj);obj.parent=frame
        for material in materials:data.materials.append(material)
        if indices is not None:
            for face,index in zip(data.polygons,indices):face.material_index=index
        return obj

    air=mesh("PWR_final_master_collision_shell",vertices,faces,[mats["ground"],mats["sky"]],
             [0]*ground_count+[1]*(len(faces)-ground_count))
    bm=bmesh.new();bm.from_mesh(air.data);bmesh.ops.reverse_faces(bm,faces=list(bm.faces));bm.to_mesh(air.data);bm.free()
    retained=[]
    native_parts=[]
    for index,part in enumerate(parts):
        polygons=orient_closed(part["vertices_m"],part["faces"]) if part["collision"] else part["faces"]
        obj=mesh(part["name"],part["vertices_m"],polygons,[mats[part["material"]]])
        source=obj.copy();source.data=obj.data.copy();source.parent=None;source.name="SOURCE_"+obj.name
        source.hide_render=True;source["mjolnir_preview_only"]=True;kit.objects.link(source);source.hide_set(True)
        coordinates=np.asarray(part["vertices_m"]);anchor=(coordinates.min(0)+coordinates.max(0))*.5/WU
        source.data.transform(Matrix.Translation(-Vector(anchor)));source.location=anchor
        source.data.asset_mark();source.data.asset_data.description="Original PWR "+part["module"]
        retained.append({"name":part["name"],"module":part["module"],"asset":source.data.name,
                         "position_m":(anchor*WU).tolist(),"collision":part["collision"]})
        if part["collision"]:
            native_parts.append(part)
        if part["material"]=="clip":
            bpy.data.objects.remove(obj,do_unlink=True)
            continue
        if index%20==0:print("PWR_V3_HULL",index,len(parts),flush=True)
    bm=bmesh.new();bm.from_mesh(air.data);bmesh.ops.reverse_faces(bm,faces=list(bm.faces))
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.001)
    bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.001)
    bmesh.ops.dissolve_limit(bm,angle_limit=.00001,verts=list(bm.verts),edges=list(bm.edges),delimit={"MATERIAL"})
    bmesh.ops.triangulate(bm,faces=list(bm.faces));bm.normal_update()
    # Boolean cuts can leave an almost collinear triangle along an otherwise
    # flat polygon boundary. HEK discards it and opens three collision edges.
    # Rotate its longest internal diagonal, retaining the boundary vertex and
    # surface rather than deleting the sliver or moving gameplay geometry.
    repaired=0
    for _ in range(64):
        bad=[f for f in bm.faces if len(f.verts)==3 and f.calc_area()<max(e.calc_length()**2 for e in f.edges)*1e-5]
        if not bad:break
        changed=False
        for face in bad:
            if not face.is_valid:continue
            edge=max(face.edges,key=lambda e:e.calc_length())
            if len(edge.link_faces)!=2:continue
            other=next(f for f in edge.link_faces if f!=face)
            if len(other.verts)!=3 or face.material_index!=other.material_index:continue
            if abs(face.normal.dot(other.normal))<.999:continue
            result=bmesh.ops.rotate_edges(bm,edges=[edge],use_ccw=False)
            if result.get("edges"):changed=True;repaired+=1
        bm.normal_update()
        if not changed:raise RuntimeError("Unrepairable precision-degenerate collision triangle")
    wire=[edge for edge in bm.edges if not edge.link_faces]
    if wire:bmesh.ops.delete(bm,geom=wire,context="EDGES")
    if any(not edge.is_manifold for edge in bm.edges):raise RuntimeError("Final world shell is not closed manifold")
    bm.to_mesh(air.data);bm.free();air.data.update()
    if len(air.data.polygons)>32767:raise RuntimeError("Final source shell exceeds native surface limit")
    for part in roads:mesh(part["name"],part["vertices_m"],part["faces"],[mats["road"]])

    for water in geometry["watercourses"]:
        line=np.asarray(water["surface_centreline_m"],dtype=float)
        tangent=np.gradient(line[:,:2],axis=0);tangent/=np.linalg.norm(tangent,axis=1)[:,None]
        normal=np.c_[-tangent[:,1],tangent[:,0]]
        width=float(water["channel_width_m"])*.5
        points=[]
        for q,n in zip(line,normal):
            points.extend([(q[0]-n[0]*width,q[1]-n[1]*width,q[2]),(q[0]+n[0]*width,q[1]+n[1]*width,q[2])])
        polygons=[]
        for i in range(len(line)-1):polygons.extend([(i*2,(i+1)*2,(i+1)*2+1),(i*2,(i+1)*2+1,i*2+1)])
        mesh(water["id"]+"_water_surface",points,polygons,[mats["water"]])
    for lake in geometry["lakes"]:
        polygon=[Vector((x,y,lake["water_z_m"])) for x,y in lake["polygon_m"]]
        points=[];polygons=[]
        for tri in tessellate_polygon([polygon]):
            start=len(points);points.extend([tuple(polygon[p] if isinstance(p,int) else p) for p in tri]);polygons.append((start,start+1,start+2))
        mesh(lake["id"]+"_lake_surface",points,polygons,[mats["water"]])

    for obj in scene.objects:
        if obj.type!="MESH" or obj.parent!=frame:continue
        obj.data.update();uv=obj.data.uv_layers.new(name="UVMap")
        for face in obj.data.polygons:
            dominant=max(range(3),key=lambda i:abs(face.normal[i]));axes=[i for i in range(3) if i!=dominant]
            period=32 if obj==air and obj.data.materials[face.material_index]==mats["ground"] else 8
            for loop in face.loop_indices:
                point=obj.data.vertices[obj.data.loops[loop].vertex_index].co*WU
                uv.data[loop].uv=(point[axes[0]]/period,point[axes[1]]/period)
    bpy.context.view_layer.objects.active=air
    bpy.ops.wm.save_as_mainfile(filepath=str(output/"pwr.blend"))
    sys.path.insert(0,str(REPO/"tools/blender"))
    from mjolnir_level.surface import write_surface_policy
    write_surface_policy(scene,output/"pwr.surfaces.json")
    (output/"assembly.json").write_text(json.dumps({"schema":"pwr-modular-assembly-v3","modules":retained},indent=2)+"\n")
    hull_triangles=[]
    for part in native_parts:
        vertices=np.asarray(part["vertices_m"])/WU
        for face in orient_closed(part["vertices_m"],part["faces"]):
            for j in range(1,len(face)-1):hull_triangles.append(vertices[[face[0],face[j],face[j+1]]].tolist())
    (output/"architecture-collision-extra.json").write_text(json.dumps({"triangles":hull_triangles,
        "materials":["hard_metal_thick"]*len(hull_triangles),"objects":len(native_parts),"skip_entries":[],
        "geometry_sha256":sha256(geometry_path),"coordinates":"ce_world_units_z_up"},separators=(",",":")))
    from world_placements import placements
    layout=json.loads((HERE/"layout.json").read_text())
    (output/"placements.json").write_text(json.dumps(placements(layout,geometry,field),indent=2)+"\n")
    (output/"layout.json").write_text(json.dumps(layout,indent=2)+"\n")
    receipt={"schema":"pwr-world-source-v3","master_manifest_sha256":field.manifest_sha256,
             "geometry_sha256":sha256(geometry_path),"collision_report_sha256":sha256(a.collision_dir/"collision-report.json"),
             "collision_accuracy_pass":report["accuracy_and_mesh_budget_pass"],"native_shell_triangles":len(air.data.polygons),
             "collision_strategy":"standalone_static_terrain" if a.static_terrain else "core_terrain",
             "requires_terrain_extra":a.static_terrain,
             "precision_diagonal_repairs":repaired,
             "static_architecture_triangles":len(hull_triangles),
             "modules":len(parts),"sky_z_m":a.sky_z,"runtime_validated":False}
    (output/"geometry-report.json").write_text(json.dumps(receipt,indent=2)+"\n")
    if not a.no_export:
        target=output/"data/levels/warfare/pwr/models";target.mkdir(parents=True,exist_ok=True)
        result=bpy.ops.export_scene.jms(filepath=str(target/"pwr.jms"),game_title="halo1",jms_version="8200",folder_type="1",folder_structure=False,scale_enum="1",use_scene_properties=False,export_render=True,export_collision=False,export_physics=False,hidden_geo=False,nonrender_geo=False,apply_modifiers=True,triangulate_faces=True,loop_normals=True,edge_split=False,clean_normalize_weights=False,fix_rotations=False,write_textures=False,generate_checksum=True)
        assert result=={"FINISHED"},result
    print("PWR_WORLD_V3",json.dumps(receipt),flush=True)

if __name__=="__main__":main()
