# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "scipy", "pillow"]
# ///
"""Author the Southwest Sweep mineral and duff material from the packaged Halo scans."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree
from southwest_bend_survey import SHOULDER_POCKETS, SHALLOW_WASH, fit_station_curve, graded_apex, trace, traffic_lanes

from bake_alpine_roadbed import (
    CAPTURES, GEOMETRY, MASTER, ROOT, SIZE, SPAN, STEP, TILES, TREES, densify,
    load, load_heightfield, noise, sha, smooth,
)


OUT = ROOT / "out/pwr/sweep-polish/earth"
PREVIOUS = ROOT / "out/pwr/alpine-target"
STOCK_PAKS = ROOT / "out/pwr/playtest-20261121/rehearsal-game/Meteorite/Content/Paks"
CLI = ROOT / "target/release/mjolnir.exe"
ASSETS = {
    "scree": "T_Scree_NSVT_A30_D",
    "scree_n": "T_gravel_ground_vl1oabbfw_NSVT_N",
    "scree_h": "T_gravel_ground_vl1oabbfw_NSVT_ORHG",
    "stone": "T_Gravel_Natural_vglndb0g_4K_NSVT_D",
    "stone_n": "T_Gravel_Natural_vglndb0g_4K_NSVT_N",
    "stone_h": "T_Gravel_Natural_vglndb0g_NSVT_ORHG",
    "earth": "T_Trampled_Forest_Path_ub4jdihkw_NSVT_D",
    "moss": "T_Mossy_Ground_xiboab2r_4K_D",
    "moss_n": "T_Mossy_Ground_xiboab2r_4K_N",
    **{f"needle{i}": f"T_PineNeedle_0{i}_D" for i in (1, 2, 3)},
}


def stocks(folder):
    folder.mkdir(exist_ok=True, parents=True)
    pixels, files = {}, {}
    for key, name in ASSETS.items():
        path = folder / (name + ".png")
        mip = 0 if key.startswith("needle") else 1
        if not path.is_file():
            subprocess.run([CLI, "texture", "export", "--paks", STOCK_PAKS, "--asset", name,
                            "--mip", str(mip), "--out", path], check=True, capture_output=True)
        pixels[key] = np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32) / 255
        expected = 512 if key.startswith("needle") else 1024
        if pixels[key].shape != (expected, expected, 4):
            raise ValueError(f"Unexpected stock source size for {name}")
        files[key] = {"asset": name, "mip": mip, "sha256": sha(path)}
    return pixels, files


def normalized(a, lo, hi):
    return np.clip((a-lo)/(hi-lo), 0, 1)


NEEDLE_FANS = 8200


def needle_litter(images, count=NEEDLE_FANS, long_fibers=False, windrows=False):
    # A pair of fallen needles is 45–125 mm. Their natural silhouette is already
    # present in the stock particle textures; paint the red BC4 silhouettes on a
    # periodic 2.40 m square forest floor and retain layers of overlap.
    rng = np.random.default_rng(731201)
    side = 1024
    knots = rng.uniform(0, side, size=(54, 2))
    if windrows:
        knots = knots[:31]
        pitch = rng.uniform(0,360,len(knots))
        axes = np.stack((np.cos(np.deg2rad(pitch)),np.sin(np.deg2rad(pitch))),axis=1)
    stock = []
    for key in ("needle1", "needle2", "needle3"):
        im = Image.fromarray((images[key][..., 0]*255).astype("uint8"))
        stock.append(im.crop(im.point(lambda x: 255 if x > 30 else 0).getbbox()))
    relief = np.zeros((side, side), np.float32)
    colour = relief.copy()
    for i in range(count):
        if windrows:
            k = rng.integers(len(knots))
            axis = axes[k]
            p = knots[k] + rng.normal(0,57)*axis + rng.normal(0,19)*axis[::-1]*[-1,1]
            angle = 90 - pitch[k] + rng.normal(0,22) + 180*rng.integers(2)
            if i%9==0:
                p = rng.uniform(0,side,2)
                angle = rng.uniform(0,360)
        else:
            p = (knots[rng.integers(len(knots))] + rng.normal(0, 58, 2)
                 if i % 4 else rng.uniform(0, side, 2))
        kind = rng.choice([0, 1, 2], p=[.045, .48, .475])
        original = stock[kind]
        size = int(rng.uniform(27, 66) * (1.32 if kind == 0 else 1) * (1.42 if long_fibers else 1))
        blade = original.resize((max(3, round(size * original.width/original.height)), size),
                                Image.Resampling.LANCZOS)
        blade = blade.rotate(float(angle if windrows else rng.uniform(0, 360)), resample=Image.Resampling.BICUBIC,
                             expand=True)
        mask = np.asarray(blade) / 255.
        b = min(float(mask.max()) + .001, .91)
        mask = smooth(.10, b, mask)
        h, w = mask.shape
        iy = (round(p[1])+np.arange(h)) % side
        ix = (round(p[0])+np.arange(w)) % side
        rr = np.ix_(iy, ix)
        colour[rr] = colour[rr] * (1-mask) + mask * rng.uniform(.53, 1.)
        relief[rr] = np.minimum(.99, relief[rr]*(1-.65*mask) + mask*.83)
    return colour, relief


def bark_chips():
    """Embed the splintered cambium and broken twigs below the fresh needle fans."""
    rng = np.random.default_rng(45103)
    grid = Image.new("L",(1024,1024))
    draw = ImageDraw.Draw(grid)
    for _ in range(97):
        x,y = rng.uniform(0,1024,2)
        length = rng.uniform(29,142)
        angle = rng.uniform(-np.pi,np.pi)
        axis = np.array([np.cos(angle), np.sin(angle)])
        perp = np.array([-axis[1],axis[0]])
        width = rng.uniform(1.1,5.0)
        mid = rng.uniform(.32,.64)*length*axis + rng.uniform(-5.,5.)*perp
        polygon = np.array([axis*0,mid+width*perp,axis*length,mid-.70*width*perp])
        value = int(rng.uniform(85,223))
        for ox in (-1024,0,1024):
            for oy in (-1024,0,1024):
                vertices = polygon + [x+ox,y+oy]
                draw.polygon([tuple(p) for p in vertices],fill=value)
    return np.asarray(grid).astype(np.float32)/255.


def detail_source(images, revision):
    y, x = np.mgrid[:1024, :1024] / 1024.
    # All macro waves close on the texture boundary. Two different photogrammetry
    # sources supply coherent rock faces, coarse sediment and tangent normals.
    blend = smooth(-.60, .40, .52*np.sin(2*np.pi*(x + .13)) +
                   .38*np.cos(2*np.pi*(y - .18)) + .25*np.sin(2*np.pi*(2*x+y)))
    mix = lambda a,b: a*(1-blend) + b*blend
    lum = lambda rgb: np.dot(rgb[..., :3], [.2126,.7152,.0722])
    a, b = lum(images["scree"]), lum(images["stone"])
    ar, br = images["scree_h"], images["stone_h"]
    local = lambda z: z - gaussian_filter(z, 8, mode="wrap")
    scree_peak = normalized(.50 + local(ar[...,2])*1.85 + local(a)*2.0 +
                            (ar[...,0]-.68)*.58, 0, 1)
    stone_peak = normalized(.37 + local(br[...,2])*2.1 + local(b)*2.8 +
                            (br[...,0]-.56)*.54, 0, 1)
    rock = np.stack((mix(normalized(a,.12,.78),normalized(b,.04,.59)),
                     mix(scree_peak,stone_peak),mix(images["scree_n"][...,0],images["stone_n"][...,0]),
                     mix(images["scree_n"][...,1],images["stone_n"][...,1])),axis=2)
    if revision>=18:
        # Retain each face's actual scanned oxide/stone/dust colour. Store the
        # RGB in its source transfer curve and its independent relief in alpha.
        gravel = images["stone"][...,:3]*[1.33,1.29,1.25]
        scree = images["scree"][...,:3]*[.90,.87,.84]
        full_colour = scree*(1-blend[...,None])+gravel*blend[...,None]
        rock=np.dstack((full_colour,rock[...,1]))
    stamp_count = 6300 if revision>=17 else NEEDLE_FANS
    needles, relief = needle_litter(images,stamp_count,long_fibers=revision>=16,windrows=revision>=17)
    if revision>=16:
        # Dark wood and amber fibers can read together in the albedo even when
        # the camera is too far away to resolve every 1–2 mm needle edge.
        chips = bark_chips()
        strength = .49 if revision>=17 else 1.
        needles = np.maximum(needles, chips*.86*strength)
        relief = np.maximum(relief, chips*strength)
    moss = images["moss"]
    moss_patch = smooth(-.04,.12,moss[...,1]-moss[...,0]+.016) * (.42+.58*blend)
    bed = .56*normalized(lum(images["earth"]),.12,.69) + .44*normalized(lum(moss),.07,.55)
    if revision>=16:
        moss_patch *= .57+.20*np.cos(2*np.pi*(x-y))
    litter = bed*(1-relief) + needles
    # Encode a continuous material index: soil 0, moss .44, fresh needle .90.
    semantic = (.04+.46*moss_patch)*(1-relief) + relief*(.79+.21*needles)
    basis = images["moss_n"][...,:2]*2-1
    slope_x = .30 * (np.roll(relief,1,axis=1)-np.roll(relief,-1,axis=1))
    slope_y = .30 * (np.roll(relief,-1,axis=0)-np.roll(relief,1,axis=0))
    duff = np.stack((litter,semantic,.5+.34*basis[...,0]+slope_x,
                     .5+.34*basis[...,1]+slope_y),axis=2)
    def tile(arr,width=1008):
        values = np.rint(np.clip(arr,0,1)*255).astype("uint8")
        if revision>=17:
            # Pillow premultiplies RGBA before resizing. The last channel is
            # a signed normal component and must never weight the other data.
            resized = np.stack([np.asarray(Image.fromarray(channel).resize((width,1008),
                                Image.Resampling.LANCZOS)) for channel in values.transpose(2,0,1)],axis=2)
        else:
            resized = np.asarray(Image.fromarray(values).resize((width,1008),Image.Resampling.LANCZOS))
        return np.pad(resized,((8,8),(8,8),(0,0)),mode="wrap")
    panels=[tile(rock),tile(duff)]
    repack={}
    if revision>=22:
        from sweep_scanned_verge import verge_strip
        accent, note=verge_strip(images)
        panels=[panels[0],tile(duff,768),accent]
        old=np.asarray(Image.open(OUT.parent/"round21/earth/sweep-floor-detail.png").convert("RGBA"))
        fresh=np.concatenate(panels,axis=1)
        def region(lo,hi):
            a,b=old[:,lo:hi],fresh[:,lo:hi]
            return dict(x=[lo,hi],changed_pixels=int(np.sum(np.any(a!=b,axis=-1))),
                previous_pixels_sha256=hashlib.sha256(a.tobytes()).hexdigest(),
                pixels_sha256=hashlib.sha256(b.tobytes()).hexdigest())
        note.update(parent_detail_sha256=sha(OUT.parent/"round21/earth/sweep-floor-detail.png"),
                    regions=[region(0,1024),region(1024,1808),region(1808,2048)])
        if note["regions"][0]["changed_pixels"]:
            raise ValueError("Protected Southwest mineral scan changed")
        repack["detail_repack"]=note
    return Image.fromarray(np.concatenate(panels,axis=1)), {
        **repack,
        "detail_uv_period_m": [3.35, 2.40],
        "needle_fans_stamped": stamp_count,
        "needle_coverage": round(float(np.mean(relief > .40)), 4),
        "rock_visible_high_relief": round(float(np.mean(rock[...,-1 if revision>=18 else 1]>.67)), 4),
        "padding_texels": 8,
    }


def field_source(revision, folder):
    previous = np.asarray(Image.open(PREVIOUS / "earth/alpine-roadbed.png").convert("RGBA"))
    if previous.shape != (SIZE, SIZE*2, 4):
        raise ValueError("Unexpected .14 survey")
    active = previous[:,SIZE:,0].astype(float)/255.
    axis=(np.arange(SIZE)+.5)*STEP-SPAN/2
    cx, cy = TILES[1][2]
    x,y = np.meshgrid(cx+axis,cy-axis)
    xy = np.column_stack([x.ravel(),y.ravel()])
    route = next(r for r in load(GEOMETRY)["roads"] if r["id"]=="southwest_sweep")
    line = densify(np.asarray(route["centreline_m"])[:,:2])
    st = np.r_[0.,np.cumsum(np.linalg.norm(np.diff(line,axis=0),axis=1))]
    _,i = cKDTree(line).query(xy)
    tang = line[np.minimum(len(line)-1,i+1)] - line[np.maximum(0,i-1)]
    tang /= np.linalg.norm(tang,axis=1)[:,None]
    side = ((xy[:,1]-line[i,1])*tang[:,0] - (xy[:,0]-line[i,0])*tang[:,1]).reshape(x.shape)
    station = st[i].reshape(x.shape)
    broad = noise(x,y,6.8,42)
    fine = noise(x,y,1.64,501)
    # Widths come from the field camera projected onto the heightfield,
    # including the left verge reaching u=.12 at v=.76 at station 128 m.
    s = [0, 92, 108, 117, 124, 128, 130, 139, 166, st[-1]]
    left = np.interp(station,s,[5.9,5.6,5.9,5.65,5.55,5.11,4.38,5.1,6.2,6.1])
    right = np.interp(station,s,[7.0,7.6,9.4,9.05,7.9,7.6,7.2,6.9,7.6,7.2])
    edge = np.where(side < 0, -side-left, side-right)
    waviness = .70 * fine + 1.05*broad
    outside = smooth(-.75,1.45,edge + waviness)
    roots = np.asarray([i["position"][:2] for i in load(TREES)["instances"]])
    proposed = [v["position_m"][:2] for v in load(PREVIOUS/"verges/structural.json")
                if v["kind"]=="Pine"]
    dist = cKDTree(np.vstack([roots, proposed])).query(xy)[0].reshape(x.shape)
    root = 1-smooth(2.2,12.5+2*broad,dist)
    duff = outside*np.clip(.70+.27*root+.13*fine+.07*broad,0,1)
    wander = -.44+.36*np.sin(station*.046)+.21*np.sin(station*.106)
    wheel = np.abs(np.abs(side-wander)-1.46)
    worn = (1-smooth(.22,1.02+.17*broad,wheel+.075*fine))*(.92+.06*broad)
    worn += .18 * (1-smooth(.2,1.4,abs(abs(side-wander)-3.55))) * (1-outside)
    field = load_heightfield(MASTER)
    height = field.sample(x,y)
    hollow = gaussian_filter(height,3.4/STEP) - height
    # Anchor small drain patches to the grade on the two wheel runs. Irregular
    # secondary pockets use the naturally concave surfaces elsewhere on the bend.
    wet = .52*(1-smooth(.10,.64,wheel))*smooth(-.012,.042,hollow)*smooth(.02,.57,.64*fine+.36*broad)
    pools = [(128.6,-.55,1.05,.55), (121.8,-2.0,1.70,.55), (115.7,1.16,1.4,.54),
             (104.4,-2.,1.34,.63),(141.9,.9,1.60,.61),(154.1,-1.3,1.40,.52)]
    for place,off,length,width in pools:
        pos = np.hypot((station-place)/length,(side-off)/width) + .20*fine
        wet = np.maximum(wet,1-smooth(.30,1.10,pos))
    wet = np.clip(wet,0,1)*(1-duff)
    bed = np.clip(worn,0,1)
    sweep_notes = {}
    if revision>=16:
        left -= np.interp(station,[0,100,118,129,143,st[-1]],[.30,.45,.43,.97,.47,.30])
        right -= np.interp(station,[0,105,122,135,st[-1]],[.3,.35,.70,.50,.3])
        edge = np.where(side<0,-side-left,side-right)
        outside = smooth(-1.1,1.02,edge+.48*fine+.53*broad)
        duff = outside*np.clip(.78+.17*root+.07*fine+.06*broad,0,1)
        # Reserve the top of this channel for the tight junction between each
        # true trunk flare and its organic soil. No circular tint under rocks.
        fibre = noise(x,y,.8,603)
        contact = (1-smooth(.54,1.25+.15*fibre,dist))*outside
        duff = duff*.87*(1-contact) + contact
        # Swaths follow successive wheel passes in opposite directions.
        # In the driver view their centres converge with the real bend.
        shift = .23*np.sin(station*.047)+.18*np.sin(station*.083)
        wheel = np.minimum(abs(side+3.13-shift),abs(side-2.23+shift*.43))
        worn = (1-smooth(.47,1.52+.15*broad,wheel+.06*fine))*(.95+.045*broad)
        median = 1-smooth(.70,2.38,abs(side+.28+shift*.48))
        verge = 1-smooth(.45,2.36,abs(edge+.70))
        braided = .65*noise(station,side*2.4,6.4,89)+.35*noise(station,side*1.6,1.85,511)
        patch = smooth(-.58,.47,braided+.18*broad)
        deposits = np.clip((.09+.81*np.maximum(median,verge))*(.20+.80*patch),0,1)*(1-.98*worn)
        # A signed packing gives a sparse wash (0..0.49), clean compactable
        # soil (0.50) and wheel wear (0.51..1) their own ranges in one channel.
        bed = .5 + .49*worn - .49*deposits
        wet.fill(0.)
        # Each corner pair is a separate shallow basin. The asymmetric lobes
        # and narrow stone bars avoid smooth disks in the broad terrain mip.
        pools = [(128.55,-.51,.73,.42),(121.95,-1.94,1.26,.48),(115.7,1.16,1.05,.44),
                 (104.4,-2.,.96,.51),(141.9,.9,1.2,.5),(154.1,-1.3,1.05,.43)]
        for place,off,length,width in pools:
            along = (station-place)/length
            across = (side-off-.21*np.clip(along,-1.,1.))/width
            plain = np.hypot(along,across)
            tongue = np.hypot((along-.44)*1.32,(across+.67)*1.71)
            notch = np.exp(-((along+.31)**2*11+(across-.52)**2*13))
            shape = np.minimum(plain,tongue) + .58*notch + .18*fine
            wet=np.maximum(wet,1-smooth(.11,1.31,shape))
        wet *= 1-duff
        reading = (active>.8)&(station>112)&(station<134)&(abs(side)<8)
        sweep_notes = dict(median_and_verge_gravel_occupancy=round(float(np.mean(deposits[reading]>.45)),4),
                           cleared_wheel_swath_width_m=[.94,3.04],
                           pine_contact_radius_m=[.54,1.4], contact_texels=int(np.sum((duff>.91)&(active>.9))),
                           mean_wear_in_driver_swaths=round(float(worn[reading&(wheel<.47)].mean()),4))
    if revision>=17:
        # The inside and outside passes splay toward the far side of the
        # switchback. Survey stations are metres on the actual drive spline.
        steps = [0,94,106,115,121,128,134,142,166,st[-1]]
        track_l = np.interp(station,steps,[-2.7,-2.8,-3.0,-3.25,-3.65,-3.55,-3.00,-2.7,-2.9,-2.65])
        track_r = np.interp(station,steps,[2.0,2.38,3.25,3.62,3.03,2.35,2.10,2.25,2.50,2.1])
        drift=.16*np.sin(station*.145)+.15*np.sin(station*.066)
        track_l += drift
        track_r += drift*.62
        wheel = np.minimum(abs(side-track_l),abs(side-track_r))
        worn = 1-smooth(.64,1.77+.12*broad,wheel+.10*fine)
        mid = (track_l+track_r)*.5 + .28*noise(station,side*2.,4.8,332)
        braided = .66*noise(station,side*3.,6.1,89)+.34*noise(station,side*2.2,1.9,511)
        driftbed = 1-smooth(.54,1.94+.28*braided,abs(side-mid))
        shoulder = 1-smooth(.35,1.66,abs(edge+.35+.25*fine))
        deposits = np.clip(.09+np.maximum(driftbed,shoulder*.84)*(.76+.25*braided)+.08*fine,0,.99)
        deposits *= 1-.985*worn
        bed = np.clip(.5+.49*worn-.49*deposits,.01,.99)
        # Washouts interrupt the verge into fingers of needles, pebbles and bare soil.
        # Preserve the dark contact at real pivots independently of the washed patches.
        finger = .62*noise(station,side*2.1,2.75,941)+.38*noise(x,y,.82,237)
        outside = smooth(-1.10,.98,edge+.53*fine+.49*broad+.60*finger)
        wash = (1-smooth(.9,3.9,abs(edge)))*smooth(-.32,.36,finger)
        duff = outside*np.clip(.81+.15*root+.08*fine-.58*wash,0,1)
        contact = (1-smooth(.54,1.25+.15*fibre,dist))*outside
        duff = duff*.87*(1-contact)+contact
        sweep_notes.update(median_and_verge_gravel_occupancy=round(float(np.mean(deposits[reading]>.45)),4),
                           cleared_wheel_swath_width_m=[1.28,3.54],
                           contact_texels=int(np.sum((duff>.91)&(active>.9))),
                           mean_wear_in_driver_swaths=round(float(worn[reading&(wheel<.47)].mean()),4),
                           mean_gravel_in_driver_median=round(float(deposits[reading&(abs(side-mid)<.7)].mean()),4))
    if revision>=18:
        photo=load(PREVIOUS/"bench/sweep-17/photos/comparison.json")["captures"]["southwest-forest-road-driver"]
        pose=photo["after"]["camera_before"]
        marks=trace(field,pose,line,st)
        lt,rt=traffic_lanes(station, marks)
        wheel=np.minimum(abs(side-lt),abs(side-rt))
        median=fit_station_curve(station,marks["median"],-.24,15.)
        median=np.clip(median,lt+.8,rt-.8)
        left_line=fit_station_curve(station,marks["duff_edge"],-5.15,14.)
        # Continue the organic shoulder into the far bend with the left run.
        left_line=np.where(station<110.5,np.maximum(left_line,lt-1.4),left_line)
        left_line+=.18
        right_line=rt+np.interp(station,[0,98,119,131,170,st[-1]],[3.8,2.05,3.18,4.9,3.7,3.8])
        edge=np.maximum(left_line-side,side-right_line)
        fingers=.63*noise(station,side*1.6,2.1,544)+.37*noise(x,y,.9,513)
        outside=smooth(-.39,.41,edge+.34*fingers+.14*fine)
        # A connected litter bed under the actual near-left bank. Local soil
        # openings live inside the texture and the last half metre of its edge.
        wash=(1-smooth(.1,1.2,abs(edge)))*smooth(-.07,.49,fingers)
        duff=outside*np.clip(.90+.065*root+.055*fine-.24*wash,0,.98)
        contact=(1-smooth(.54,1.25+.15*fibre,dist))*outside
        duff=duff*.89*(1-contact)+contact
        braid=.52*noise(station,side*2.35,3.6,334)+.29*noise(station,side,1.20,537)+.19*broad
        worn=(1-smooth(.31,1.65+.17*braid,wheel+.12*fingers))*(.81+.14*fine+.07*broad)
        # The wash is a loose collection of sediment islands, never a strip
        # of uniform-density chips. Slight accumulation spills into both paths.
        seam=1-smooth(.20,1.92+.36*braid,abs(side-median+.24*fingers))
        verge=1-smooth(.15,1.48,abs(edge+.36+.17*braid))
        patch=smooth(-.29,.43,braid+.22*noise(x,y,6.3,811))
        deposits=np.clip(.09+(.21+.63*patch)*np.maximum(seam,.76*verge)+.10*fine,0,.94)
        deposits*=1-.69*worn
        bed=np.clip(.5+.49*worn-.49*deposits,.01,.99)
        wet.fill(0.)
        # Surveyed broad damp rims enclose discrete millimetre-deep pools in
        # the material. Each rim follows a real point on this turning median.
        pools=[(128.577,-.736,.94,.58),(121.95,-1.20,1.17,.45),(116.0,.40,1.04,.54),
               (104.4,5.5,1.12,.40),(141.9,.9,1.18,.53),(154.1,-1.3,.97,.48)]
        for place,off,length,width in pools:
            along=(station-place)/length
            across=(side-off-.20*np.clip(along,-1.,1.))/width
            bowl=np.minimum(np.hypot(along,across),np.hypot((along-.34)*1.41,(across+.57)*1.62))
            wet=np.maximum(wet,1-smooth(.22,1.40,bowl+.13*fingers))
        wet*=1-duff
        sweep_notes.update(reference_landmarks=marks,reference_camera_pose=pose[:6],
                           median_and_verge_gravel_occupancy=round(float(np.mean(deposits[reading]>.45)),4),
                           mean_gravel_in_driver_median=round(float(deposits[reading&(abs(side-median)<.7)].mean()),4),
                           cleared_wheel_swath_width_m=[.62,3.30],
                           contact_texels=int(np.sum((duff>.91)&(active>.9))),
                           mean_wear_in_driver_swaths=round(float(worn[reading&(wheel<.47)].mean()),4))
    if revision >= 19:
        # The fitted centre lines are survey data. The driving surface has a
        # compact core, a low rolled edge and a gravel wash between the two.
        # With a 50 cm terrain atlas texel a clean core needs two full samples
        # before the soft wall of the rut begins.
        wobble = .065 * fingers + .055 * broad
        radius = abs(wheel + wobble)
        worn = 1 - smooth(.48, 1.40 + .11 * braid, radius)
        worn *= .97 + .025 * fine
        shoulder_roll = 1 - smooth(.05, .41, abs(radius - 1.32))
        # Gravel fans cross the median in broken groups following drainage.
        # Retain mineral fines between fans so both wear paths remain legible
        # at the apex, even where resolved stones disappear into lower mips.
        mid_distance = abs(side - median + .28 * fingers)
        island = smooth(-.43, .47, .68 * braid + .32 * broad)
        seam = 1 - smooth(.49, 1.88 + .48 * island, mid_distance)
        edge_fan = 1 - smooth(.10, 1.13, abs(edge + .26 + .30 * braid))
        deposits = np.clip(.06 + seam * (.64 + .31 * island)
                           + edge_fan * (.25 + .47 * island)
                           + .15 * shoulder_roll + .09 * fine, 0, 1)
        deposits *= 1 - .96 * worn
        bed = np.clip(.5 + .495 * worn - .495 * deposits, .005, .995)
        sweep_notes.update(
            mean_wear_in_driver_swaths=round(float(worn[reading & (wheel < .47)].mean()), 4),
            mean_gravel_in_driver_median=round(float(deposits[reading & (mid_distance < .70)].mean()), 4),
            median_and_verge_gravel_occupancy=round(float(np.mean(deposits[reading] > .45)), 4),
            cleared_wheel_swath_width_m=[.96, 2.80],
        )
    if revision >= 20:
        # The original main-road footprint becomes patchy where the widened
        # S-curve crosses its old shoulder. Cover the whole drivable section,
        # including the ground between the fitted wheel lines.
        apex = graded_apex(station, side, lt, rt)
        active = np.maximum(active, apex)
        duff *= 1 - apex
        local = smooth(54, 68, station) * (1-smooth(145, 154, station))
        across = np.maximum(lt-side, side-rt)
        extent = local * (1-smooth(2.7, 3.6, across))
        # Native pebbles occupy many of the same elongated fluvial deposits.
        # Preserve the smaller grit in the surrounding muddy hollows. These
        # lenses span at most part of the road width, leaving visible bare dirt.
        lenses = np.zeros_like(station)
        for point, half_length, half_width, lateral in [
                (78.9,1.7,.64,.2), (86.2,2.85,.77,-.34), (91.7,1.2,.45,.34),
                (97.4,2.2,.59,-.22), (104.3,1.13,.81,.44), (109.5,1.7,.61,-.12),
                (116.8,1.4,.67,.48), (122.3,1.0,.63,-.48), (126.6,.78,.53,.64),
                (128.5,.65,.44,-.49), (129.85,.83,.62,.53), (135.7,1.52,.62,-.26),
                (142.2,1.43,.71,.37)]:
            a=(station-point)/half_length
            b=(side-median-lateral-.21*fingers-.14*np.clip(a,-1.4,1.4))/half_width
            lenses=np.maximum(lenses,1-smooth(.23,1.61,np.hypot(a,b)))
        braid_bank = smooth(-.28, .58, .64*braid+.36*fingers)
        loose = np.clip(.05 + seam * (.25 + .27*braid_bank + .65*lenses)
                        + edge_fan * (.22+.47*island) + .11*shoulder_roll + .055*fine, 0, .99)
        loose *= 1 - .97*worn
        # Smoother narrow cores still read as wheels at grazing angles.
        worn_core = 1-smooth(.37,1.15+.10*braid,radius)
        worn_core *= .975+.02*fine
        fitted = np.clip(.5+.496*worn_core-.496*loose,.003,.997)
        bed += extent*(fitted-bed)
        permitted = ((station>=53)&(station<=154)&(across<=3.61))
        mask=np.zeros(previous.shape[:2],dtype=np.uint8)
        mask[:,SIZE:]=permitted.astype(np.uint8)*255
        allow_file=folder/"route-coverage.png"
        Image.fromarray(mask).save(allow_file)
        sweep_notes.update(route_authorization=allow_file.name,
            route_authorization_sha256=sha(allow_file),
            median_and_verge_gravel_occupancy=round(float(np.mean(loose[reading]>.45)),4),
            mean_gravel_in_driver_median=round(float(loose[reading&(mid_distance<.7)].mean()),4),
            cleared_wheel_swath_width_m=[.74,2.30])
    if revision >= 21:
        # Compound material signal on the verges: chips with copper duff and
        # dry needles washed up at the same positions as the native pebbles.
        shoulder=np.zeros_like(station)
        for hand, knots in SHOULDER_POCKETS.items():
            distance=lt-side if hand=="left" else side-rt
            for knot, spread in knots:
                u=(station-knot)/(1.35*spread)
                v=(distance-1.47-.16*np.clip(u,-1.,1.)-.22*fingers)/.81
                lens=1-smooth(.18,1.43,np.hypot(u,v)+.25*braid)
                shoulder=np.maximum(shoulder,lens*smooth(.69,1.24,distance))
        shoulder*=permitted
        bed+=shoulder*(.061-bed)
        duff+=shoulder*(.72-duff)
        # Atlas A gates the broader damp earth. Each optically shallow pool
        # uses the same oriented metric frame to resolve its silty bank in the shader.
        wash=np.zeros_like(station)
        frames=[]
        def route_frame(knot, off):
            j=np.clip(np.searchsorted(st,knot),1,len(line)-1)
            tangent=line[j]-line[j-1]
            tangent=tangent/np.linalg.norm(tangent)
            normal=np.array([-tangent[1],tangent[0]])
            xy=line[j-1]+tangent*(knot-st[j-1])+normal*off
            return xy*np.array([1.,-1.]),tangent*np.array([1.,-1.])
        for number,(knot,off,half_l,half_w,shear,shelf,strength) in enumerate(SHALLOW_WASH):
            centre,direction=route_frame(knot,off)
            if number==0:
                centre=np.array([-588.944,541.320])
            # World-projected coordinates avoid quantising the small bank and
            # guarantee that the analytic pool and its survey alpha agree.
            dx,dy=x-centre[0],-y-centre[1]
            u=(dx*direction[0]+dy*direction[1])/half_l
            v=((dx*direction[1]-dy*direction[0])/half_w)-shear*u
            bowl=np.hypot(u,v*(1-.23*np.tanh(shelf*v)))
            wash=np.maximum(wash,1-smooth(.29,2.31,bowl+.18*fingers))
            frames.append(dict(centre_m=centre.round(5).tolist(),direction=direction.round(7).tolist(),
                   half_axes_m=[half_l,half_w],shear=shear,shelf=shelf,strength=strength))
        wet=np.where(permitted,wash*(1-duff),wet)
        centre,direction=route_frame(116.,.1)
        sweep_notes.update(wash_frames=frames,finish_frame=dict(centre=centre.round(5).tolist(),
                direction=direction.round(7).tolist()),verge_patch_count=sum(map(len,SHOULDER_POCKETS.values())),
                verge_active_texels=int(np.sum((shoulder>.35)&(active>.75))))
    if revision>=22:
        # Outer deposits sit beyond wheel clearance. Tie them to the same
        # graded arc and real scattered verge actors, with bare gaps between.
        verge=np.zeros_like(station)
        for hand, cluster in SHOULDER_POCKETS.items():
            ds=lt-side if hand=="left" else side-rt
            chosen=((117.1,1.6),(124.8,1.8),(131.0,1.7)) if hand=="left" else cluster
            for knot,spread in chosen:
                t=(station-knot)/(spread*1.32)
                across=(ds-(2.1+.29*np.clip(t,-1.3,1.3))-.34*fingers)/1.17
                body=1-smooth(.15,1.45,np.hypot(t,across)+.23*braid)
                verge=np.maximum(verge,body*smooth(.81,1.52,ds))
        verge*=permitted
        # Compound signed wear/duff separates these windrows from compact
        # tracks and mineral-only centre deposits. Give the graded edge enough
        # cover to retain bright facets against the underlying grassy terrain.
        active=np.maximum(active,verge*.93)
        bed+=verge*(.047-bed)
        duff+=verge*(.646-duff)
        sweep_notes.update(scan_verge_wheel_exclusion_m=.81,scan_verge_peak_texels=int(np.sum(verge>.55)))
    channels = np.stack([active,active*bed,active*duff,active*wet], axis=-1)
    packed = np.rint(channels*255).astype("uint8")
    new = previous.copy()
    new[:,SIZE:] = packed
    exact_coverage = np.array_equal(packed[...,0],previous[:,SIZE:,0])
    if not np.array_equal(new[:,:SIZE],previous[:,:SIZE]) or (revision < 20 and not exact_coverage):
        raise ValueError("Protected terrain or earlier footprint changed")
    if revision >= 20:
        prior_path=OUT.parent/f"round{revision-1}/earth/alpine-roadbed.png"
        prior=np.asarray(Image.open(prior_path).convert("RGBA"))
        changed=np.any(new!=prior,axis=-1)
        if np.any(changed & (mask==0)):
            raise ValueError("Surface changes exceeded the Southwest S-bend authorization")
        sweep_notes.update(previous_survey_sha256=sha(prior_path),
            changed_pixels=int(changed.sum()), changed_coverage_pixels=int(np.sum(new[...,0]!=prior[...,0])),
            exact_outside_authorized_route=True)
    def site(sta,offset,channel):
        j = np.unravel_index(np.argmin(np.hypot(station-sta,side-offset)),station.shape)
        return round(float(packed[j][channel])/255,3)
    return Image.fromarray(new), {
        "atlas_channels_southwest": ["coverage from .14","gravel deposits / wheel wear" if revision>=16 else "paired worn paths","pine litter","wet depressions"],
        "teton_texels_exact": SIZE*SIZE, "active_footprint_exact": bool(exact_coverage),
        "route": route["id"], "terrain_shape_changes": 0,
        "trunk_litter": round(float(np.median(duff[(dist<2.5) & (active>.8) & (outside>.9)])),3),
        "wet_anchors": [site(sta,offset,3) for sta,offset,_,_ in pools],
        "left_margin_driver_samples": [site(q,-6.1,2) for q in (117,124,128,130)],
        "mean_wear_in_tyre_band": round(float(worn[(wheel<.38)&(active>.95)].mean()),3),
        "mean_wear_between_wheels": round(float(worn[(abs(side-wander)<.51)&(active>.95)].mean()),3),
        **sweep_notes,
    }


def clip_verge_to_grade(folder, gain_file):
    """Reuse .22 art unchanged; describe the surveyed S curve in the shader's metric frame."""
    prior=OUT.parent/"round22/earth"
    spec=load(prior/"roadbed.json")
    for filename,digest in ((spec["file"],spec["sha256"]),(spec["detail_file"],spec["detail_sha256"]),
                            (spec["route_authorization"],spec["route_authorization_sha256"])):
        if sha(prior/filename)!=digest:
            raise ValueError(f"Changed parent terrain art: {filename}")
        shutil.copyfile(prior/filename,folder/filename)
    if gain_file is not None and load(gain_file)!=spec["material_gains"]:
        raise ValueError("This material correction retains the original .22 terrain gains")
    line=densify(np.asarray(next(r for r in load(GEOMETRY)["roads"] if r["id"]=="southwest_sweep")["centreline_m"])[:,:2])
    st=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(line,axis=0),axis=1))]
    ref=spec["finish_frame"]
    axis=np.asarray(ref["direction"]); right=axis[::-1]*[1.,-1.]
    tangent=np.gradient(line,axis=0);tangent/=np.linalg.norm(tangent,axis=1)[:,None]
    normal=tangent[:,::-1]*[-1.,1.]
    stations=np.arange(58.,157.,2.)
    bounds=[]
    for wheel in traffic_lanes(st,spec["reference_landmarks"]):
        xy=(line+wheel[:,None]*normal)*[1.,-1.]-ref["centre"]
        u,v=116.+xy@axis,xy@right
        near=(st>40)&(st<170)
        # Offset wheel polylines can double back a few centimetres at an apex.
        # Intersect the actual segments; select the inward edge where a plane
        # crosses twice instead of sorting otherwise unrelated vertices.
        u,v=u[near],v[near]
        edge=[]
        for plane in stations:
            spans=((u[:-1]-plane)*(u[1:]-plane)<=0)&(np.abs(np.diff(u))>.00001)
            if not spans.any():
                raise ValueError("Material grade plane missed the measured bend")
            fractions=(plane-u[:-1][spans])/np.diff(u)[spans]
            crossings=v[:-1][spans]+fractions*np.diff(v)[spans]
            edge.append(crossings.min() if bounds else crossings.max())
        bounds.append(edge)
    rows=np.column_stack(bounds).round(5)
    spec.update(revision=23,previous_survey_sha256=spec["sha256"],changed_pixels=0,
                changed_coverage_pixels=0, detail_inherited_from=22,
                previous_detail_sha256=spec["detail_sha256"],
                grade_clip=dict(station_start=58.,station_step=2.,wheel_edges=rows.tolist(),
                                clearance_fade_m=[2.58,2.97],native_route_limit_m=3.61))
    (folder/"roadbed.json").write_text(json.dumps(spec,indent=2)+"\n")


def preserve_native_art(folder,gain_file,revision):
    # The .24 cut is a local material redistribution; source art and game
    # footprints are exactly those from the accepted .23 curve.
    prior=OUT.parent/f"round{revision-1}/earth"
    spec=load(prior/"roadbed.json")
    for name,digest in (("file","sha256"),("detail_file","detail_sha256"),("route_authorization","route_authorization_sha256")):
        item=prior/spec[name]
        if sha(item)!=spec[digest]:
            raise ValueError(f"Changed parent terrain source {item}")
        shutil.copyfile(item,folder/item.name)
    if gain_file and load(gain_file)!=spec["material_gains"]:
        raise ValueError("The near-puddle grit retains the calibrated .23 gains")
    spec.update(revision=revision,previous_survey_sha256=spec["sha256"],previous_detail_sha256=spec["detail_sha256"],
                detail_inherited_from=revision-1,changed_pixels=0,changed_coverage_pixels=0,
                near_puddle_grit=dict(centre_m=spec["wash_frames"][0]["centre_m"],along_extent_m=[-1.38,2.14],
                  across_extent_m=[-1.34,1.53],minimum_wheel_clearance_m=1.13,wet_reflection_excluded=True))
    if revision>=25:
        spec.update(stochastic_forest=dict(original_scan_period_m=2.40,blend_cell_m=2.67,stand_scale_m=12.8,
                    raw_wear_clip=[.245,.51],raw_duff_range=[.20,.61],wet_clip=.025,lookup_cost=[1,3,4]),
                    weathered_asphalt_source="pwr_weathered_asphalt.ush")
    (folder/"roadbed.json").write_text(json.dumps(spec,indent=2)+"\n")


def main(folder,revision,gain_file=None):
    protected = [OUT] + [OUT.parent/f"round{old}/earth" for old in range(16,revision)]
    if revision>=16 and folder.resolve() in [p.resolve() for p in protected]:
        raise ValueError("Use a separate art folder for the later material")
    folder.mkdir(parents=True,exist_ok=True)
    if revision >= 24:
        preserve_native_art(folder,gain_file,revision)
        return
    if revision==23:
        clip_verge_to_grade(folder,gain_file)
        return
    pixels, originals = stocks((OUT if revision>=16 else folder)/"stock")
    detail, tile = detail_source(pixels,revision)
    detail_file = folder/"sweep-floor-detail.png"
    detail.save(detail_file)
    field, survey = field_source(revision,folder)
    atlas = folder/"alpine-roadbed.png"
    field.save(atlas)
    receipt = {**survey, **tile, "revision":revision,"size": list(field.size), "file": atlas.name, "sha256": sha(atlas),
               "detail_file": detail_file.name, "detail_size": list(detail.size),
               "detail_sha256": sha(detail_file), "stock": originals,
               "baseline_atlas_sha256": sha(PREVIOUS/"earth/alpine-roadbed.png")}
    if gain_file is not None:
        if revision < 20:
            raise ValueError("Use a new revision when selecting calibrated values")
        receipt["material_gains"] = json.loads(gain_file.read_text())
        receipt["gain_selection_sha256"] = sha(gain_file)
    (folder/"roadbed.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps({**survey, **tile},indent=2))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--out",type=Path)
    cli.add_argument("--revision",type=int,default=15)
    cli.add_argument("--gains",type=Path,help="JSON object of native scalar defaults from the accepted in-engine lighting and soil study")
    args=cli.parse_args()
    if args.revision < 15:
        cli.error("The Southwest Sweep surface starts at revision 15")
    destination=args.out or (OUT if args.revision==15 else OUT.parent/f"round{args.revision}/earth")
    main(destination.resolve(),args.revision,args.gains)
