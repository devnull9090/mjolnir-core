"""Large native cliff formations shared by Blender and the runtime swap stage.

The closed BSP provides the boundary; these actual native cliff meshes supply
fracture depth and an irregular skyline beyond it. Positions use Unreal cm.
"""
import math
from terrain_form import height

CLIFF='/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Cliff_B/SM_Rock_Uluwatu_Cliff_B.SM_Rock_Uluwatu_Cliff_B'
ROCK='/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_B/SM_Rock_Uluwatu_Med_B.SM_Rock_Uluwatu_Med_B'
ROCK_A='/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_A/SM_Rock_Uluwatu_Med_A.SM_Rock_Uluwatu_Med_A'
ROCK_C='/Game/Env/Bio/Rock/Uluwatu/Rock_Uluwatu_Med_C/SM_Rock_Uluwatu_Med_C.SM_Rock_Uluwatu_Med_C'
STRATA='/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_A/SM_Rock_Desert_Cliff_A.SM_Rock_Desert_Cliff_A'
BROKEN='/Game/Env/Bio/Rock/Desert/Rock_Desert_Cliff_C/SM_Rock_Desert_Cliff_C.SM_Rock_Desert_Cliff_C'
SHELF='/Game/Env/Bio/Rock/CliffFlat/Rock_CliffFlat_Kit_B/SM_Rock_CliffFlat_Kit_B.SM_Rock_CliffFlat_Kit_B'


def document():
    decor=[]
    def add(mesh,x,y,z,scale,yaw=0,roll=0,pitch=0):
        decor.append({'id':f'tst_geology_{len(decor):03d}','mesh':mesh,
            'pos':[round(x*100,3),round(-y*100,3),round(z*100,3)],
            'rot':[pitch,-yaw,roll], 'scale':list(scale)})
    for side in (-1,1):
        for i,y in enumerate(range(-46,49,15)):
            setback=4 if abs(y)<18 else 0
            add(STRATA if i%3!=1 else BROKEN,side*(77+setback+1.2*math.sin(i*1.7)),y,-2+math.sin(i),
                (.75,.76,1.1+.10*math.cos(i)),side*90+i*19,side*(i%3-1)*6)
        # Rock overhangs widen the silhouette above the rear roof route, with
        # their lowest geometry above the complete player headroom envelope.
        add(BROKEN,side*73,2,11.5,(.7,.8,.75),side*90)
    for i,x in enumerate(range(-90,91,12)):
        add(BROKEN if i%3==1 else STRATA,x,-50+1.8*math.sin(i*1.8),-20 if x==42 else -17,
            (.68,.78,1.1+.07*math.sin(i)),i*31,18+12*math.sin(i))
    # Intersecting fractured crowns interrupt the straight foreground lip.
    # Their bases remain outside the walkable basin, with varied heights/yaw.
    for i,x in enumerate((-68,-47,-26,-7,16,44,66)):
        add(BROKEN if i%2 else STRATA,x,-45-1.2*math.sin(i),-.5+i%3,
            (.58,.48,.38),i*47+15,(i%3-1)*18)
    for i,x in enumerate(range(-85,86,21)):
        add(STRATA if i%2 else BROKEN,x,56+2*math.sin(i),2*math.cos(i*1.8),
            (.95,.8,.72),i*59,8*math.sin(i))
    # Continuous ledge set into the north retaining wall, rather than suspended
    # isolated boulders. Front edge stays behind the balcony landing routes.
    for i,x in enumerate(range(-66,67,17)):
        add(SHELF,x,32.6,3.7,(.55,.65,.8),90+(i%3-1)*8)
    # Broad, tilted blocks sit in overlapping rubble fans. Avoid the earlier
    # evenly spaced tall B-rock columns, which read as additional wall piers.
    for i,(x,y,s) in enumerate(((-64,28.8,1.6),(-54,29.1,1.35),(-45,29.4,1.55),
            (-21,28.8,1.65),(-8,29.6,1.4),(4,29.1,1.6),(19,29.7,1.35),
            (46,29.0,1.7),(56,29.5,1.25),(65,28.8,1.5))):
        add(ROCK if i%2 else ROCK_C,x,y,1.25,(s*1.45,s*.95,s*.66),i*61+24,
            (i%3-1)*18,11 if i%2 else -14)
        add(ROCK_A,x+(-2.9 if i%2 else 2.5),y-1.8,.65,
            (1.35,1.1,.9),i*93+16,22,-9)
    # Embedded fractured wedges reach partway up the retaining foundation;
    # varied lean/width keeps the talus from becoming another vertical row.
    for i,(x,y,s) in enumerate(((-62,26.5,.22),(-44,27.2,.18),(-22,26.6,.21),
                                 (-7,28.2,.16),(13,26.8,.24),(45,27.3,.20),(63,26.4,.17))):
        s*=1.6
        if i==1: x+=1.5; y+=2.8  # Preserve the left field teleporter approach.
        add(BROKEN,x,y-1.1,.15,(s*1.4,s*.95,s*.6),28+i*57,(-1 if i%2 else 1)*5,5)
    # Unequal shoulders cover terrace foundation sides, outside the tread
    # footprint x=+/-33 +/-3.5. Smaller toe fragments fall away into the basin.
    shoulders=((-26.1,26.7,1.45,1.25,31),(-40.1,25.6,1.7,1.1,83),
               (26.0,26.1,1.7,1.15,145),(40.4,27.0,1.3,1.25,207))
    for i,(x,y,z,s,yaw) in enumerate(shoulders):
        add(ROCK_C if i%2 else ROCK,x,y,z,(s*1.15,s*1.55,s*.95),yaw,14,-12)
        toe_x=x+(.7 if x>0 else -.7)
        add(ROCK_A,toe_x,y-3.25,.62,(1.2,1.35,.85),yaw+74,-19,8)
        add(ROCK,toe_x+(-1 if i%2 else 1.2),y-4.9,.28,(.52,.68,.43),yaw+127,21,-17)
    # Low toe fragments blend the cliff into the field. Keep the vehicle lanes
    # and objective markers clear; the native-clearance pass checks this recipe.
    for i,x in enumerate(range(-63,64,7)):
        y=-35.4+.8*math.sin(i*1.9)
        s=.45+.15*math.sin(i*2.1)
        add(ROCK,x,y,height(x,y)+.15,(s*1.5,s,s*.85),i*53)
    for side in (-1,1):
        for i,y in enumerate((-29,-24,23,28)):
            x=side*(63.8+.5*math.sin(i))
            add(ROCK,x,y,height(x,y)+.35,(.65,.8,.55),i*71)
    for i in range(25):
        a=i*math.tau/25+.045*math.sin(i*2.1)
        if i in (1,3,4,9,10,11,12,13,20): continue
        radius=1+.08*math.sin(a*3+.4)+.055*math.cos(a*5-.3)
        x,y=36+12.8*radius*math.cos(a),-23+9.4*radius*math.sin(a)
        s=.52+.16*math.cos(i*2.3)
        add(ROCK if i%3 else ROCK_C,x,y,height(x,y)+s*.45,(s*1.4,s,s*.62),i*71,15*math.sin(i),-11)
        # Broken banks collect in irregular groups rather than a necklace of
        # equally sized stones; the north-east approach keeps its open gaps.
        if i in (0,6,7,15,17,18,22,24):
            tangent=(-math.sin(a),math.cos(a))
            for j,offset in enumerate((-.95,.8)):
                px=x+tangent[0]*offset+.45*math.cos(a)
                py=y+tangent[1]*offset+.45*math.sin(a)
                chip=.34+.08*((i+j)%3)
                add(ROCK_A,px,py,height(px,py)+.12,
                    (chip*1.3,chip,.32),i*81+j*94,17,-14)
    return {'schema_version':1,'coordinates':'unreal_centimetres',
        'note':'Native game geology; same authored transforms feed preview and runtime. No extracted meshes in source.',
        'decor':decor,'leaf_cluster_scale':1.43,
        'background_trees':[{'id':f'tst_ridge_tree_{i}_{j}',
             'position_m':[x+(j-1)*2.3,54+1.5*math.sin(i+j*1.7),18+math.cos(i)],
             'yaw_degrees':i*73+j*47,'height_m':(4.5,5.7,5.0,4.8)[j],
             'variant':'Pine_Optimized'}
             for i,x in enumerate((-73,-57,-35,-17,17,36,57,73))
             for j in range(3+(i%2))]}
