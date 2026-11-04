"""Display the runtime's exact MJF3 records with shared native mesh instances."""
import json
import math
from pathlib import Path
import struct
import bpy
from mathutils import Quaternion
from .native import import_reference
from .native_scene import bind_material


def foliage_rotation(yaw,nx,ny):
    """Port of Foliage.rotation in MJOLNIRLevelLoader, reflected to Blender Y."""
    hz,hw=math.sin(yaw/2),math.cos(yaw/2)
    s2=nx*nx+ny*ny
    if s2<1e-6: return Quaternion((hw,0,0,-hz))
    nz=math.sqrt(max(1-s2,0)); half=math.acos(min(nz,1))/2
    k=math.sin(half)/math.sqrt(s2)
    ax,ay,aw=-ny*k,nx*k,math.cos(half)
    return Quaternion((aw*hw,-(ax*hw+ay*hz),ay*hw-ax*hz,-aw*hz))


def instance_points(target,template,name,positions,rotations,scales):
    mesh=bpy.data.meshes.new(name); mesh.from_pydata(positions,[],[]); mesh.update()
    mesh.attributes.new('pcg_rotation','FLOAT_VECTOR','POINT').data.foreach_set('vector',[c for r in rotations for c in r])
    mesh.attributes.new('pcg_scale','FLOAT','POINT').data.foreach_set('value',scales)
    obj=bpy.data.objects.new(name,mesh); target.objects.link(obj); obj['mjolnir_preview_only']=True
    group=bpy.data.node_groups.new(name,'GeometryNodeTree')
    group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    nodes,links=group.nodes,group.links
    source=nodes.new('NodeGroupInput'); output=nodes.new('NodeGroupOutput')
    info=nodes.new('GeometryNodeCollectionInfo'); info.inputs['Collection'].default_value=template
    inst=nodes.new('GeometryNodeInstanceOnPoints')
    links.new(source.outputs['Geometry'],inst.inputs['Points'])
    links.new(info.outputs['Instances'],inst.inputs['Instance'])
    for name,kind,socket in [('pcg_rotation','FLOAT_VECTOR','Rotation'),('pcg_scale','FLOAT','Scale')]:
        attr=nodes.new('GeometryNodeInputNamedAttribute'); attr.data_type=kind; attr.inputs['Name'].default_value=name
        links.new(attr.outputs['Attribute'],inst.inputs[socket])
    links.new(inst.outputs['Instances'],output.inputs['Geometry'])
    mod=obj.modifiers.new('Shared actual game meshes','NODES'); mod.node_group=group
    return obj


def load_pcg(path,target):
    doc=json.loads(Path(path).read_text()); source=json.loads(Path(doc['foliage']).read_text())
    raw=(Path(doc['foliage']).parent/source['file']).read_bytes()
    magic,version,groups=struct.unpack_from('<4sII',raw)
    if magic!=b'MJF3' or version!=3 or groups!=len(source['groups']): raise ValueError('Unsupported foliage file')
    unit=bpy.context.scene.unit_settings.scale_length
    templates={}; cursor=12; counts={}
    for index,g in enumerate(source['groups']):
        asset=g['mesh']; count=struct.unpack_from('<I',raw,cursor)[0]; cursor+=4
        key=(asset,tuple(g.get('tint',[])))
        if key not in templates:
            template=bpy.data.collections.new('PCG ASSET - '+asset.rsplit('/',1)[-1])
            template['mjolnir_preview_only']=True
            _,objects=import_reference(doc['models'][asset],template)
            settings={**doc['materials'][asset]}
            if g.get('tint'): settings['tint']=g['tint']
            mat=bind_material(objects,settings,asset.rsplit('/',1)[-1])
            # Hidden LODs cannot remain children of a Geometry Nodes collection
            # instance: collection-info evaluates their geometry regardless of
            # render hiding. Remove those objects from this isolated import.
            for obj in list(objects):
                if obj.hide_render: bpy.data.objects.remove(obj,do_unlink=True)
            templates[key]=template
        positions=[]; rotations=[]; scales=[]
        for _ in range(count):
            x,y,z,yaw,scale,nx,ny,*color=struct.unpack_from('<fffBBbbBBB',raw,cursor); cursor+=19
            positions.append((x/100/unit,-y/100/unit,z/100/unit))
            rotations.append(tuple(foliage_rotation(yaw*math.pi/128,nx/127,ny/127).to_euler()))
            scales.append(scale/100)
        obj=instance_points(target,templates[key],f"PCG {g['rule']} {index} ({count})",positions,rotations,scales)
        obj['ue_asset']=asset; obj['runtime_rule']=g['rule']; obj['instance_count']=count
        counts[g['rule']]=counts.get(g['rule'],0)+count
    if cursor!=len(raw): raise ValueError('Foliage binary length mismatch')
    return {'manifest':str(Path(path).resolve()),'instances':counts,'unique_meshes':len(doc['models']),'fidelity':doc['fidelity']}
