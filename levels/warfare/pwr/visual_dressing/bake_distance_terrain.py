"""Build mip-stable meadow, forest floor and wet-ground variation for the actual LPE landscape."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as nd


ROOT = Path(__file__).resolve().parents[4]
MASTER = ROOT / "levels/warfare/pwr/terrain/runtime-v5"
BASELINE = ROOT / "out/pwr/world-art/foliage-r2"
MASKS = ROOT / "out/pwr/visual-v8/surface-cooked-final"
SIZE = 1024
METRES = 2000.0 / SIZE


def smooth(lo, hi, value):
    t = np.clip((value - lo) / (hi - lo), 0, 1)
    return t*t*(3 - 2*t)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def landscape(out, vegetation=None):
    out.mkdir(exist_ok=True, parents=True)
    inputs = {}

    def image(path, mode):
        inputs[str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)] = digest(path)
        with Image.open(path) as im:
            return np.asarray(im.convert(mode).resize((SIZE, SIZE), Image.Resampling.BILINEAR),
                              dtype=np.float32) / 255.0

    def field(name):
        path = MASTER / f"runtime-master.{name}.npy"
        inputs[str(path.relative_to(ROOT))] = digest(path)
        # Source samples have +Y/north at the last row. The cooked landscape is -Y in UE.
        im = Image.fromarray(np.load(path)[::-1].copy())
        return np.asarray(im.resize((SIZE, SIZE), Image.Resampling.BILINEAR))

    prev_image = image(BASELINE / "biome-color.png", "RGB")
    prev = prev_image * (255.0/128.0)
    base = image(MASKS / "T_LandBase.png", "RGBA")
    eco = image(MASKS / "T_LandEcology.png", "RGBA")
    old_edge, reed, old_pine = image(BASELINE / "ecotone-weights.png", "RGB").transpose(2, 0, 1)
    colony, rush, sapling = (image(vegetation, "RGB").transpose(2, 0, 1)
                              if vegetation is not None else (0., 0., 0.))
    height, forest, road, bases, water = [field(n) for n in ("heights", "forest", "road", "bases", "water")]
    waterline, litter, exposed = eco[:, :, :3].transpose(2, 0, 1)
    yy, xx = np.indices(height.shape, dtype=np.float32)
    rng = np.random.default_rng(359393)

    def blur(value, metres):
        return nd.gaussian_filter(value, metres/METRES, mode="nearest")

    def variation(metres):
        # Interpolate nonperiodic random knots outside the map, with a common low-frequency warp
        # to keep the smaller openings and grass-colour runs nested inside larger meadow shapes.
        step = metres/METRES
        shape = (int(SIZE / step) + 12,) * 2
        knots = rng.standard_normal(shape, dtype=np.float32)
        sample = nd.map_coordinates(knots, [wy/step + 5, wx/step + 5], mode="reflect", order=3)
        return np.tanh(sample * .93)

    wx, wy = xx, yy
    warp_x, warp_y = variation(87), variation(87)
    wx, wy = xx + 14*warp_x, yy + 14*warp_y
    basin, stand, clearing, tussock = [variation(scale) for scale in (93, 39, 15, 5.5)]
    z5, z30 = blur(height, 4.3), blur(height, 27)
    gy, gx = np.gradient(z5, METRES)
    slope = np.hypot(gx, gy)
    hollow = np.tanh((z30 - z5)/2.9)
    lee = np.tanh(2.4*gx + 1.35*gy)
    rock = smooth(.14, .65, base[:, :, 0] + .17*exposed)
    snow = smooth(.04, .67, base[:, :, 1])
    margin = np.minimum.reduce([yy, xx, SIZE - 1 - yy, SIZE - 1 - xx]) * METRES
    # The existing apron and all base pads keep their previous reflectance; a real
    # water surface and a submerged streambed must not acquire standing-ground gloss.
    pad_dist = nd.distance_transform_edt(bases < .04)*METRES
    road_dist = nd.distance_transform_edt(road < .2)*METRES
    water_dist, nearest_water = nd.distance_transform_edt(water < .45, return_indices=True)
    water_dist *= METRES
    elevation_above_bank = height - height[tuple(nearest_water)]
    preserve = smooth(0, 72, margin) * smooth(0, 10, pad_dist) * smooth(0, 3, water_dist)
    grade = preserve*(1 - rock)*(1 - snow)
    nonroad = smooth(1, 7, road_dist)
    woody = np.clip(.68*blur(litter, 5) + .28*forest + .13*old_edge + .12*old_pine + .20*sapling, 0, 1)
    bank = ((1-smooth(3, 48, water_dist))*(1-smooth(4, 16, elevation_above_bank))
            * (.66+.34*waterline))
    soil_water = np.clip(.21+.46*waterline + .30*hollow + .20*lee + .10*stand + .27*bank, 0, 1)

    # Dry limestone shoulders carry straw and sage; moisture collects around swales
    # and tree stands. This contrast survives the grass meshes' last visible LOD.
    dryness = smooth(.28, .71, .71-.63*soil_water+.22*basin+.15*stand+.10*clearing-.10*colony)
    meadow = (1-.82*woody) * nonroad
    patch = .19*basin + .21*stand + .12*clearing + .042*tussock
    meadow_tone = np.stack((.82+.54*dryness, .91+.16*dryness, .94-.22*dryness), axis=-1)
    meadow_tone *= (1+patch)[:, :, None]
    forest_luma = 1 + .14*stand + .09*clearing + .055*tussock
    forest_tone = forest_luma[:, :, None] * np.array([1.02, .92, .80], dtype=np.float32)
    # Stock scanned albedo, rock and snow shading are still the source of fine detail.
    scale = 1 + (meadow_tone-1)*meadow[:, :, None]
    scale += (forest_tone-1) * (woody*nonroad)[:, :, None]
    verge = (1 - smooth(3, 12 + 2*stand, road_dist)) * nonroad
    scale += (np.array([.13, -.075, -.18]) + .085*clearing[:, :, None])*verge[:, :, None]

    # A shallow depression at a 12 m scale, a nearly level floor, and a damp
    # catchment must coincide. The river and lake surfaces themselves stay under Flux.
    radius = 6
    dy, dx = np.ogrid[-radius:radius+1, -radius:radius+1]
    footprint = dx*dx + dy*dy <= radius*radius
    spill_depth = np.maximum(0, nd.grey_closing(z5, footprint=footprint)-z5)
    flat = 1-smooth(.018, .080, slope)
    outline = smooth(.066, .27, spill_depth + .052*clearing + .024*tussock)
    pooling = (flat * outline * smooth(.53, .86, soil_water+.14*bank+.08*rush)
               * smooth(1., 5., water_dist))
    bank_mud = bank*smooth(.28, .75, soil_water+.13*reed+.14*rush)*(1 - smooth(.095, .25, slope))
    swale_mud = (.46*smooth(.72,.94,soil_water)*smooth(.07,.27,spill_depth)
                 + .23*verge*smooth(.52,.84,soil_water))
    wet = np.clip(.44*bank_mud + .55*swale_mud + .93*pooling, 0, 1)
    wet *= grade * smooth(2., 7., road_dist)
    shade = (1-.25*wet)*(1 - .10*bank_mud*nonroad)
    factor = prev * (1 + grade[:, :, None]*(scale*shade[:, :, None]-1))
    rgba = np.dstack((np.clip(np.rint(factor*128), 1, 250), np.rint(255*wet))).astype(np.uint8)
    output = out/"biome-color.png"
    Image.fromarray(rgba).save(output)
    rgb = rgba[:, :, :3]
    original = np.rint(prev_image*255).astype(np.uint8)
    protected = (bases>=.04)|(water>=.45)|(margin==0)
    if np.any(rgb[protected] != original[protected]) or rgba[protected,3].any():
        raise ValueError("The previous pad, wet bed or apron edge values drifted")
    if rgba[road_dist<2,3].any() or np.any((rgba[:,:,3]>175)&(slope>.081)):
        raise ValueError("Standing-water sheen reached a road centre or steep terrain")
    grass_mask = (grade>.98)&(nonroad>.98)&(woody<.36)&(bank<.12)
    if not np.any(grass_mask) or np.max(wet) < .70:
        raise ValueError("No eligible open meadow or perched wet patch")
    measured_meadow = out/"open-meadow-evaluation.png"
    Image.fromarray(np.uint8(grass_mask)*255).save(measured_meadow)
    mip_evidence = {}
    for side in (1024, 256, 128, 64, 32):
        def luma(arr):
            return np.asarray(Image.fromarray(arr).resize((side,side), Image.Resampling.BOX),
                              dtype=np.float32) @ np.array([.2126,.7152,.0722]) / 128
        keep = np.asarray(Image.fromarray(np.uint8(grass_mask)*255).resize((side,side),Image.Resampling.BOX)) > 200
        def spread(arr):
            lo, hi = np.percentile(luma(arr)[keep], [10,90])
            return round(float(hi-lo),3)
        mip_evidence[str(side)] = {"texel_metres": round(2000/side,3), "meadow_p90_p10_before":spread(original),
                                   "meadow_p90_p10_after":spread(rgb)}
    pool_labels, count = nd.label(wet>.68)
    pool_areas = np.bincount(pool_labels.ravel())[1:]*METRES**2
    report = dict(file=output.name, sha256=digest(output), bounds_ue_cm=[-100000,-100000,200000,200000],
                  encoding="RGB = linear reflectance times 128; A = wet surface weight (0 dry, 255 pooled)",
                  used_inputs=inputs, paired_meadow_mips=mip_evidence,
                  measured_meadow={"file":measured_meadow.name,"sha256":digest(measured_meadow)},
                  excluded_pad_bed_edge_pixels=int(protected.sum()), maximum_wet_weight=round(float(wet.max()),4),
                  wet_ground_m2=round(float((wet>.12).sum()*METRES**2)),
                  pooled_ground_m2=round(float(pool_areas.sum())), wet_components=int(count),
                  wet_components_over_16m2=int((pool_areas>16).sum()))
    (out/"terrain-field.json").write_text(json.dumps(report,indent=2)+"\n")
    return report


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("out",type=Path)
    p.add_argument("--vegetation",type=Path,help="North-up PCG colony footprints, RGB grass/rush/saplings")
    args=p.parse_args()
    print(json.dumps(landscape(args.out.resolve(),args.vegetation.resolve() if args.vegetation else None),indent=2))
