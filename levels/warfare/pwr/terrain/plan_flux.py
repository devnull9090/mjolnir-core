"""Plan two terrain-bound Flux domains; no installation or game calls.

Sources prime the authored profile, then retain only inlet/seam/lake controls.
The final saved-state bake still requires measured level and seam acceptance.
"""
import argparse
import copy
import json
import math
from pathlib import Path
import sys

import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "tools/level"))
from heightfield import load_heightfield
from flux_heightfield import build_capture_bed, provenance, sha256
from prepare_flux_probe import package_bed

LOOK = {
    "color_preset": "/Game/FluidFlux/Surface/Templates/Color/CP_OceanBlue_01.CP_OceanBlue_01",
    "surface_vectors": {
        "SurfaceScattering0": [.06, .48, .42, .008], "SurfaceAbsorption0": [140, 800, 650, .65],
        "SurfaceScattering1": [.04, .32, .30, .003], "SurfaceAbsorption1": [100, 450, 600, .8],
        "ColorBehind0": [.8, 1, 1, 1], "ColorBehind1": [.7, .95, 1, 1],
        "FoamColorBase": [.85, .94, 1, .65]},
    "surface_scalars": {"FoamSoftIntensity": .12, "FoamColorAlpha": .1,
                        "StateFoamSlope": .5, "StateFoamDivergence": .3},
    "simulation": {"FoamFadeSpeed": .35, "FoamShallowGenerate": .08,
                   "FoamShallowDepth": 25, "FoamWaveGenerate": 1.2}}


def inside(points, polygon):
    points = np.asarray(points); polygon = np.asarray(polygon)
    x, y = points[..., 0], points[..., 1]
    result = np.zeros(x.shape, dtype=bool)
    for a, b in zip(polygon, np.roll(polygon, -1, axis=0)):
        if a[1] == b[1]:
            continue
        result ^= ((a[1] > y) != (b[1] > y)) & (x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])
    return result


def profile_samples(points, step=20):
    points = np.asarray(points, dtype=float)
    arc = np.r_[0., np.cumsum(np.linalg.norm(np.diff(points[:, :2], axis=0), axis=1))]
    positions = np.r_[np.arange(0, arc[-1], step), arc[-1]]
    return np.column_stack([np.interp(positions, arc, points[:, axis]) for axis in range(3)])


def source(point, *, scale=2.5, prime=False, mode=2, volume=1, role=""):
    return {"pos": [round(float(point[0])*100, 4), round(-float(point[1])*100, 4), round(float(point[2])*100, 4)],
            "scale": scale, "prime": prime, "mode": mode, "volume": volume, "role": role}


def capture_domain(field, rectangle, resolution):
    x0, y0, x1, y1 = rectangle
    if not math.isclose(x1-x0, y1-y0):
        raise ValueError("Domain plan requires square world cells")
    # Include covering original-grid vertices; extrema inside a triangle occur
    # at its vertices, so this conservatively covers the exact capture surface.
    lo = np.floor((np.array([x0, y0])-field.origin_m)/field.spacing_m).astype(int)
    hi = np.ceil((np.array([x1, y1])-field.origin_m)/field.spacing_m).astype(int)
    if np.any(lo < 0) or np.any(hi >= field.dimensions):
        raise ValueError("Domain exceeds exact field coverage")
    tile = field.heights_m[lo[1]:hi[1]+1, lo[0]:hi[0]+1]
    low, high = float(tile.min()), float(tile.max())
    plane = math.ceil(high+5)
    # In this installed Blueprint CaptureOffset=actorZ-0.75*AreaWorldHeight.
    # Keep that reference below the lowest bed as well as the capture plane
    # above the highest bed; negative simulation-ground values are unnecessary.
    height = math.ceil((plane-low+5)/.75)
    if height > 320:
        raise ValueError(f"Capture range {height} m exceeds documented 320 m; split this domain")
    return {"centre": [(x0+x1)*50, -(y0+y1)*50, plane*100],
            "res": [resolution, resolution], "cell": (x1-x0)*100/resolution, "height": height*100}, {
                "bounds_m": [[x0, y0], [x1, y1]], "bed_min_m": low, "bed_max_m": high,
                "capture_plane_m": plane, "capture_offset_m": plane-.75*height,
                "capture_range_m": height, "resolution": resolution}


def plan(master, geometry, out, resolution=1024, package=False):
    field = load_heightfield(master)
    if field.metadata.get("surface_interpolation") != "triangle_nw_se":
        raise ValueError("Use the decoded Unreal runtime grid")
    data = json.loads(Path(geometry).read_text(encoding="utf-8"))
    river = next(r for r in data["watercourses"] if r["id"] == "central_river")
    points = np.asarray(river["surface_centreline_m"])
    indices = np.where(points[:-1, 1]*points[1:, 1] <= 0)[0]
    if len(indices) != 1:
        raise ValueError("Expected one main-river crossing of the Y=0 domain seam")
    i = indices[0]; t = -points[i, 1]/(points[i+1, 1]-points[i, 1])
    seam = points[i]*(1-t)+points[i+1]*t
    rectangles = [("upper_river", [-732, 0, 268, 1000]), ("lower_lake", [-232, -1000, 768, 0])]
    entries, measurements = [], []
    for name, rectangle in rectangles:
        domain, measurement = capture_domain(field, rectangle, resolution)
        x0, y0, x1, y1 = rectangle
        sources = []
        for course in data["watercourses"]:
            profile = profile_samples(course["surface_centreline_m"])
            selected = profile[(profile[:, 0] >= x0) & (profile[:, 0] <= x1)
                               & (profile[:, 1] >= y0) & (profile[:, 1] <= y1)]
            for p in selected:
                sources.append(source(p, prime=True, role="profile_primer"))
            if len(selected) and course["id"] == "central_river":
                sources.append(source(selected[0], mode=0, volume=2, role="inlet_flow"))
        # Identical boundary head on both grids. These are authoring controls;
        # no implicit cross-domain fluid transfer is claimed or required later.
        sources.append(source(seam, scale=4, role="shared_seam_head"))
        if name == "lower_lake":
            for lake in data["lakes"]:
                polygon = np.asarray(lake["polygon_m"])
                gx = np.arange(math.ceil(polygon[:, 0].min()/60)*60, polygon[:, 0].max(), 60)
                gy = np.arange(math.ceil(polygon[:, 1].min()/60)*60, polygon[:, 1].max(), 60)
                xx, yy = np.meshgrid(gx, gy); xy = np.stack((xx, yy), -1).reshape(-1, 2)
                wet = inside(xy, polygon) & (field.sample(xy[:, 0], xy[:, 1]) < lake["water_z_m"]-.25)
                for island in lake.get("islands", []):
                    wet &= ~inside(xy, island["polygon_m"])
                # A broad lake Adjust modifier at55 must not intersect an
                # elevated river mouth: it would drain that reach to55 and
                # create a dry gap immediately above the final cascade.
                for course in data["watercourses"]:
                    upstream=np.asarray(course["surface_centreline_m"])
                    upstream=upstream[upstream[:,2]>lake["water_z_m"]+.5]
                    if len(upstream):
                        distance=np.linalg.norm(xy[:,None,:]-upstream[None,:,:2],axis=2).min(axis=1)
                        wet &= distance>=90
                for x, y in xy[wet]:
                    sources.append(source([x, y, lake["water_z_m"]], scale=10, role="lake_level_hold"))
                # Narrow controls fill the reservoir up to its incoming falls.
                # Require the entire footprint plus margin to lie below water;
                # this prevents the former55m controls from draining high beds.
                gx=np.arange(math.ceil(polygon[:,0].min()/20)*20,polygon[:,0].max(),20)
                gy=np.arange(math.ceil(polygon[:,1].min()/20)*20,polygon[:,1].max(),20)
                xx,yy=np.meshgrid(gx,gy);xy=np.stack((xx,yy),-1).reshape(-1,2)
                near=np.zeros(len(xy),dtype=bool)
                for course in data["watercourses"]:
                    upstream=np.asarray(course["surface_centreline_m"])
                    upstream=upstream[upstream[:,2]>lake["water_z_m"]+.5]
                    if len(upstream):near|=np.linalg.norm(xy[:,None,:]-upstream[None,:,:2],axis=2).min(axis=1)<110
                safe=inside(xy,polygon)&near
                for dx in (-12,0,12):
                    for dy in (-12,0,12):
                        safe&=field.sample(xy[:,0]+dx,xy[:,1]+dy)<lake["water_z_m"]-.5
                for x,y in xy[safe]:
                    sources.append(source([x,y,lake["water_z_m"]],scale=2,role="lake_inlet_level_hold"))
        entry = dict(copy.deepcopy(LOOK), id=name, playback="simulate", domain=domain,
                     origin=[0, 0, 0], ground=["pwr_flux_bed"], sources=sources,
                     prime_ms=60000, hide=["pwr_terrain_3"])
        entries.append(entry)
        measurements.append(dict(measurement, id=name, sources=len(sources),
                                 retained_sources=sum(not s["prime"] for s in sources)))
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    bed = out/"flux_bed.json"
    receipt = build_capture_bed(master, [e["domain"] for e in entries], bed)
    for entry in entries:
        entry["provenance"] = provenance(master, geometry, bed, entry["domain"], entry["sources"], entry["simulation"])
    spec = {"schema": "mjolnir-flux-v2", "domains": entries}
    (out/"flux.spec.json").write_text(json.dumps(spec, indent=2)+"\n")
    fragment = {"heightfield": str(Path(master).resolve()), "water_geometry": str(Path(geometry).resolve()),
                "playback": "baked", "hide": ["pwr_terrain_3"], "domains": []}
    for e in entries:
        release = {key: copy.deepcopy(value) for key, value in e.items() if key not in ("provenance", "ground", "origin")}
        release["playback"] = "baked"
        fragment["domains"].append(release)
    (out/"flux.config.fragment.json").write_text(json.dumps(fragment, indent=2)+"\n")
    report = {"schema": "pwr-flux-plan-v1", "terrain_manifest_sha256": field.manifest_sha256,
              "water_geometry_sha256": sha256(geometry), "domains": measurements,
              "shared_seam_m": seam.tolist(), "lake_levels_m": {l["id"]: l["water_z_m"] for l in data["lakes"]},
              "acceptance": "pending actual native simulation, level/seam readback and zero-domain reload"}
    (out/"plan.receipt.json").write_text(json.dumps(report, indent=2)+"\n")
    package_bed(out, receipt, package=package)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--heightfield", required=True); p.add_argument("--geometry", required=True)
    p.add_argument("--out", required=True); p.add_argument("--resolution", type=int, default=1024)
    p.add_argument("--package", action="store_true")
    a = p.parse_args(); plan(a.heightfield, a.geometry, a.out, a.resolution, a.package)
