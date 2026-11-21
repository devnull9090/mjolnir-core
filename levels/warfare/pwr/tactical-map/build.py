"""Deterministic geographic HUD art. CPU-only; no engine, UI or package writes.

uv run --python 3.12 --with-requirements tools/level/requirements-alpine.txt python levels/warfare/pwr/tactical-map/build.py
"""
from pathlib import Path
import hashlib,json,sys
import numpy as np
from PIL import Image,ImageDraw
from scipy.ndimage import gaussian_filter,distance_transform_edt

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'out/pwr/tactical-map-v1'
sys.path.insert(0,str(ROOT/'tools/level'))
from heightfield import load_heightfield

SIZE=2048
BOUNDS=(-1000.,-1000.,1000.,1000.)

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def uv(x,y):return (np.asarray(x)+1000)/2000,(1000-np.asarray(y))/2000
def pixel(points):return [(float(uv(x,y)[0]*SIZE-.5),float(uv(x,y)[1]*SIZE-.5)) for x,y,*_ in points]
def mix(rgb,color,weight):
    w=np.clip(weight,0,1)[...,None]
    return rgb*(1-w)+np.asarray(color,dtype=np.float32)*w

def mask_polygons(polygons):
    image=Image.new('L',(SIZE,SIZE));d=ImageDraw.Draw(image)
    for poly in polygons:
        d.polygon(pixel(poly[0]),fill=255)
        for hole in poly[1:]:d.polygon(pixel(hole),fill=0)
    return np.asarray(image,dtype=np.float32)/255

def map_background():
    master=ROOT/'levels/warfare/pwr/terrain/runtime-v5/runtime-master.json'
    field=load_heightfield(master)
    assert field.bounds_m==((-1000.,-1000.),(1000.,1000.))
    geography=json.loads((HERE/'geography.json').read_text())
    geo_path=ROOT/'levels/warfare/pwr/terrain/final-v5/terrain.geometry.json'
    geo=json.loads(geo_path.read_text())
    assert digest(geo_path)==field.metadata['geometry_sha256']
    # Pixel centres, not edges. Row zero is north/+authoring Y, matching UE -Y.
    x=-1000+(np.arange(SIZE)+.5)*2000/SIZE
    y=1000-(np.arange(SIZE)+.5)*2000/SIZE
    xx,yy=np.meshgrid(x,y)
    h=field.sample(xx,yy).astype(np.float32)
    water=field.sample_mask('water',xx,yy).astype(np.float32)
    shore=field.sample_mask('shore',xx,yy).astype(np.float32)
    ground=gaussian_filter(h,.85)
    gy,gx=np.gradient(ground,2000/SIZE)
    normal=np.stack((-gx,gy,np.ones_like(h)),axis=-1)
    normal/=np.linalg.norm(normal,axis=-1,keepdims=True)
    light=np.array([-.55,.45,.78]);light/=np.linalg.norm(light)
    shade=np.clip(normal@light,0,1)
    # A restrained, cool cartographic palette leaves bright HUD markers legible.
    stops=[48,90,150,220,300,390]
    colors=np.array([[51,76,65],[66,84,70],[79,91,80],[102,110,103],[130,137,133],[155,160,156]])
    rgb=np.stack([np.interp(h,stops,colors[:,i]) for i in range(3)],axis=-1).astype(np.float32)
    slope=np.hypot(gx,gy)
    rgb=mix(rgb,[111,119,116],np.clip((slope-.23)*1.15,0,.62))
    rgb*=np.clip(.68+.44*shade+(ground-gaussian_filter(ground,18))*.009,.55,1.17)[...,None]
    # Soft forest patches are reconstructed from actual native tree placements.
    density=np.zeros_like(h)
    for tx,ty,scale in geography['tree_canopy_centres_m']:
        u,v=uv(tx,ty);ix,iy=int(u*SIZE),int(v*SIZE)
        if 0<=ix<SIZE and 0<=iy<SIZE:density[iy,ix]+=scale**2
    density=gaussian_filter(density,7.0*SIZE/2000)
    canopy=np.clip(density*125,0,.72)
    rgb=mix(rgb,[30,59,49],canopy)
    # Thin topographic contours, weakened on flats and under actual water.
    phase=np.mod(h+10,20)-10
    contour=np.clip(1-np.abs(phase)/np.maximum(slope*.55,.12),0,1)
    contour*=np.clip(slope*3,0,1)*(1-np.clip(water,0,1))*.13
    rgb=mix(rgb,[16,36,33],contour)
    rgb=mix(rgb,[112,121,99],np.clip(shore,0,1)*.22)
    # Native water mask respects the actual lake islands and river corridor.
    wet=water>.5
    shore_distance=distance_transform_edt(wet)*2000/SIZE
    depth_factor=np.clip(shore_distance/35,0,1)
    water_rgb=np.array([43,108,118])[None,None,:]*(1-depth_factor[...,None])+np.array([22,62,79])[None,None,:]*depth_factor[...,None]
    water_rgb+=((h-gaussian_filter(h,10))*0.1)[...,None]
    w=np.clip((water-.12)/.76,0,1)[...,None]
    rgb=rgb*(1-w)+water_rgb*w
    # The 24m driveable footprint comes from every real graded cross-section.
    road_polygons=[];bridge_polygons=[]
    for road in geo['roads']:
        offsets=road['cross_section_offsets_m'];lo=offsets.index(-12);hi=offsets.index(12)
        sections=road['cross_sections_m']
        poly=[r[lo][:2] for r in sections]+[r[hi][:2] for r in reversed(sections)]
        road_polygons.append([poly])
        if road.get('structure'):bridge_polygons.append([poly])
    road=mask_polygons(road_polygons)
    outer=gaussian_filter(road,1.5)
    rgb=mix(rgb,[28,39,36],outer*.5)
    rgb=mix(rgb,[160,157,130],road*.84)
    bridge=mask_polygons(bridge_polygons)
    rgb=mix(rgb,[179,184,166],bridge*.7)
    paving_polygons=[]
    for feature in geography['paving']['features']:
        g=feature['geometry'];paving_polygons.extend(g['coordinates'] if g['type']=='MultiPolygon' else [g['coordinates']])
    paving=mask_polygons(paving_polygons)
    rgb=mix(rgb,[130,146,142],paving*.86)
    image=Image.fromarray(np.uint8(np.clip(rgb,0,255)),'RGB')
    draw=ImageDraw.Draw(image)
    for piece in geography['structural_footprints']:
        points=pixel(piece['polygon_m'])
        draw.polygon(points,fill=(57,80,82),outline=(176,196,187),width=1)
    image.save(HERE/'overview.png',optimize=True)
    Image.fromarray(np.uint8(np.clip(water,0,1)*255)).save(OUT/'water-mask.png')
    Image.fromarray(np.uint8(road*255)).save(OUT/'road-mask.png')
    image.resize((1024,1024),Image.Resampling.LANCZOS).save(OUT/'overview-preview.png')
    return field,geo

def icon(name):
    # Supersampled geometric silhouettes; white RGB remains white through alpha.
    n=512;alpha=Image.new('L',(n,n));d=ImageDraw.Draw(alpha)
    def poly(p,fill=255):d.polygon([(x*4,y*4) for x,y in p],fill=fill)
    def rect(box,fill=255,radius=0):
        box=tuple(v*4 for v in box)
        if radius:d.rounded_rectangle(box,radius=radius*4,fill=fill)
        else:d.rectangle(box,fill=fill)
    def line(p,width=4,fill=255):d.line([(x*4,y*4) for x,y in p],fill=fill,width=width*4,joint='curve')
    if name=='player':
        poly([(64,9),(105,111),(64,88),(23,111)])
        poly([(64,39),(64,76),(41,95)],0)
    elif name=='hog':
        # Four wide wheels, hood, open cabin and rear gun station.
        for x in (22,88):
            for y in (29,82):rect((x,y,x+18,y+26),radius=5)
        poly([(45,15),(83,15),(88,38),(88,107),(40,107),(40,38)])
        rect((48,39,80,67),0,radius=3)
        rect((55,75,73,89),0,radius=2)
        rect((61,65,67,95))
        line([(64,77),(64,63)],4)
    elif name=='tank':
        # Distinct twin tracks and centred forward gun barrel.
        rect((18,31,39,112),radius=5);rect((89,31,110,112),radius=5)
        poly([(44,32),(84,32),(89,100),(80,112),(48,112),(39,100)])
        poly([(50,46),(78,46),(86,68),(80,85),(48,85),(42,68)],0)
        poly([(53,50),(75,50),(81,68),(76,79),(52,79),(47,68)])
        rect((60,8,68,64),radius=2)
        for y in (43,57,71,85,99):
            line([(21,y),(36,y)],2,0);line([(92,y),(107,y)],2,0)
    elif name=='banshee':
        # Swept crescent wings, two raised forward tips, compact cockpit.
        poly([(9,28),(19,18),(35,54),(53,62),(56,33),(64,24),(72,33),(75,62),(93,54),(109,18),(119,28),(110,73),(86,90),(73,95),(64,113),(55,95),(42,90),(18,73)])
        poly([(22,37),(30,65),(49,76),(33,73)],0)
        poly([(106,37),(98,65),(79,76),(95,73)],0)
        poly([(61,43),(67,43),(70,65),(64,72),(58,65)],0)
    elif name=='pelican':
        # Broad angular transport wings, paired engines and a long tail.
        poly([(55,10),(73,10),(79,38),(115,51),(119,70),(84,66),(75,85),(72,111),(56,111),(53,85),(44,66),(9,70),(13,51),(49,38)])
        rect((22,39,36,79),radius=3);rect((92,39,106,79),radius=3)
        poly([(56,105),(40,116),(40,121),(64,116),(88,121),(88,116),(72,105)])
        poly([(59,24),(69,24),(72,37),(56,37)],0)
        rect((60,63,68,89),0,radius=2)
    elif name=='base':
        # Open chevron fortification, no baked team colour.
        poly([(64,11),(111,43),(111,98),(92,109),(92,55),(64,36),(36,55),(36,109),(17,98),(17,43)])
        poly([(64,50),(83,63),(83,105),(64,117),(45,105),(45,63)])
        poly([(59,72),(69,72),(69,102),(59,102)],0)
    elif name=='capture':
        poly([(64,8),(120,64),(64,120),(8,64)])
        poly([(64,23),(105,64),(64,105),(23,64)],0)
        poly([(64,44),(84,64),(64,84),(44,64)])
    else:raise ValueError(name)
    alpha=alpha.resize((128,128),Image.Resampling.LANCZOS)
    output=Image.new('RGBA',(128,128),(255,255,255,0));output.putalpha(alpha)
    output.save(HERE/f'{name}.png',optimize=True)
    return output

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    field,geo=map_background()
    names=['player','hog','tank','banshee','pelican','base','capture']
    sheet=Image.new('RGB',(7*160,180),(19,31,39))
    for i,name in enumerate(names):
        art=icon(name);sheet.paste(art,(i*160+16,16),art)
        ImageDraw.Draw(sheet).text((i*160+16,154),name,fill=(195,216,216))
    sheet.save(OUT/'icons-preview.png')
    layout=json.loads((HERE.parent/'layout.json').read_text())
    anchors=[]
    for name,p in [('red_home',layout['homes_m']['red']),('blue_home',layout['homes_m']['blue'])]+[(f'capture_{i}',p) for i,p in enumerate(layout['captures_m'])]:
        u,v=uv(*p[:2]);rx=2000*u-1000;ry=1000-2000*v
        assert abs(rx-p[0])<1e-9 and abs(ry-p[1])<1e-9
        anchors.append({'id':name,'authoring_m':p,'uv':[float(u),float(v)],'pixel_center_xy':[float(u*SIZE-.5),float(v*SIZE-.5)]})
    files=[HERE/'overview.png']+[HERE/f'{name}.png' for name in names]
    inputs=[Path(__file__),HERE/'geography.json',field.path,HERE.parent/'terrain/final-v5/terrain.geometry.json',HERE.parent/'layout.json',ROOT/'tools/level/heightfield.py']
    inputs += [field.path.parent/field.metadata['height']['path']]+[field.path.parent/v['path'] for v in field.metadata['masks'].values()]
    manifest={'schema':'pwr-tactical-map-art-v1','bounds_authoring_m':[[-1000,-1000],[1000,1000]],'size':[SIZE,SIZE],
        'north':'authoring +Y (UE -Y), image top','east':'authoring +X (UE +X), image right','uv_from_authoring_metres':['(x+1000)/2000','(1000-y)/2000'],
        'uv_from_unreal_cm':['(X+100000)/200000','(Y+100000)/200000'],'uv_from_native_ce':['(3.048*x+1000)/2000','(1000-3.048*y)/2000'],
        'pixel_mapping':'pixel-center coordinate = uv*2048 - 0.5; UI marker position within map = uv*display_size',
        'icon_heading':'Every directional silhouette points north/up; white RGBA masks for runtime tint; geometric symbols, not miniature renders.',
        'overview':'Shaded actual terrain, subtle 20m contours, actual water mask with cartographic shore-distance tint, actual 24m graded roads, existing paving/closed macro-body footprints and measured tree density. No labels, grid, teammates, objectives or proposed V9 geometry baked in.',
        'water_color_limit':'The shore-distance colour ramp is a cartographic cue, not a bathymetric depth measurement.',
        'geography_counts':{'roads':len(geo['roads']),'watercourses':len(geo['watercourses']),'lakes':len(geo['lakes']),'tree_centres':4702},
        'alignment_checks':anchors,
        'files':[{'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p),'bytes':p.stat().st_size} for p in files],
        'inputs':[{'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p)} for p in inputs]}
    (HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (OUT/'art.receipt.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'overview':str(files[0]),'size':[SIZE,SIZE],'icons':names,'anchors':anchors},indent=2))

if __name__=='__main__':main()
