"""Cast wing inserts with recessed channels for all three Forerunner gatehouses."""
import bpy
from mathutils import Matrix
from polish_home import Assembly
from finishing_materials import finish_scene_geometry

def build():
    red,blue,green = (next(c for c in bpy.data.collections if c.name.startswith(p)) for p in ('01_RED','02_BLUE','03_GREEN'))
    armor=Assembly('recessed flank web castings', .024)
    insert=Assembly('flank incision lenses',0)
    # The lower edge rises over the secondary door. Channels and cast faces
    # share one projection plane and never enter the gallery passage.
    sections=[(11.61,9.04,9.28,.53), (13.18,6.85,9.29,.52),
              (15.22,3.91,9.29,.50), (17.35,3.94,9.29,.50),
              (18.46,6.40,9.29,.47), (19.20,6.56,9.29,.57),
              (23.74,6.57,9.29,.57), (24.91,6.46,9.27,.58),
              (25.51,7.00,9.15,.58), (25.77,7.44,8.82,.55)]
    def y(depth): return lambda z: -17.057-(10.567-z)*.24138-depth
    for sign in (-1,1):
        lower=[(x,lo) for x,lo,hi,t in sections]
        upper=[(x,hi) for x,lo,hi,t in sections]
        channel=[(x,lo+(hi-lo)*t) for x,lo,hi,t in sections]
        armor.plate(lower+upper[::-1],y(.316),y(.088),sign,'shadow')
        lower_edge=[(x,z-.031) for x,z in channel]
        upper_edge=[(x,z+.031) for x,z in channel]
        armor.plate(lower+lower_edge[::-1],y(.349),y(.285),sign,'graphite')
        armor.plate(upper_edge+upper[::-1],y(.353),y(.286),sign,'graphite')
        # Short secondary machining pass over the door, with a quiet end taper.
        trace=[(15.25,8.96),(18.31,8.96),(18.69,8.64),(21.23,8.64),
               (21.12,8.57),(18.56,8.57),(18.23,8.88),(15.31,8.88)]
        insert.plate(trace,y(.358),y(.346),sign,'shadow')
        for x in (22.45,23.04):
            strip=[(x,8.51),(x+.17,8.51),(x+.38,8.82),(x+.21,8.82)]
            insert.plate(strip,y(.36),y(.347),sign,'team')
    result=[]
    for batch in (armor,insert):
        master,peer=batch.objects(red,blue)
        copy=master.copy();copy.name='03_GREEN/'+master.name;green.objects.link(copy)
        copy.matrix_world=Matrix.Translation((0,150,0))@master.matrix_world
        copy['pwr_polish_site']='green';copy['source_object_name']=master.name
        for slot in copy.material_slots:
            if slot.material == bpy.data.materials['TEAM • red recessed energy']:
                slot.link='OBJECT';slot.material=bpy.data.materials['TEAM • green recessed energy']
        result.extend((master,peer,copy))
    finish_scene_geometry({},objects=result)
    bpy.context.view_layer.update()
    return result
