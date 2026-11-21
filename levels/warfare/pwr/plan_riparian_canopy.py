"""Plant the registered outlet lips and lake shore in coherent wet-meadow colonies."""
from pathlib import Path
import json
import struct
import subprocess
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, map_coordinates
from scipy.spatial import ConvexHull, cKDTree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "terrain"))
import headwater_dressing as dress
import outlet_apron as apron

ROOT = dress.ROOT
BASIN = ROOT / "out/pwr/river-basin"
OUT = ROOT / "out/pwr/river-riparian/planting"
BANDS = 3
# Each entry references a previously extracted stock mesh and its true cooked bounds.
# Tall rye has a broad tuft, rush B is narrow, willow 17 is upright, and willow 10
# is a shorter, spreading crown. Use the pivot and masked material of each original.
SPECIES = {
    "Rye": ("distance", 3, 26000, 33500),
    "RushFan": ("understory", 13, 25000, 32500),
    "RushStem": ("understory", 14, 26000, 34000),
    "WillowCrown": ("understory", 17, 35000, 41000),
    "WillowTall": ("understory", 18, 35000, 42500),
    "SunRye": ("wind", 1, 26300, 33400),
    "SunWild": ("wind", 2, 25800, 33000),
}
MATERIALS = {"SunRye": "MI_PWR_RiparianCanyon", "SunWild": "MI_PWR_RiparianWild",
             "WillowTall": "MI_PWR_RiparianWillow", "WillowCrown": "MI_PWR_RiparianWillow"}


def save(name, value, pretty=False):
    (OUT / name).write_text(json.dumps(value, allow_nan=False, indent=2 if pretty else None,
                                      separators=None if pretty else (",", ":")) + "\n", encoding="utf-8")


def make_runtime_probe(spec):
    header = ["local expected = {}"]
    for s in spec:
        first, last = s["cull"]
        for band in range(s["bands"]):
            far = int(first + (last - first) * (band + 1) / s["bands"])
            count = len(range(band, s["count"], s["bands"]))
            key = f"PWRRiparian_{s['name']}_{band+1}"
            mat=s.get("material", "")
            header.append(f'expected["{key}"] = {{{count}, {far-5600}, {far}, "{s["mesh"]}", "{mat}"}}')
    code = """
local found,total={},0
for _,c in ipairs(FindAllOf("HierarchicalInstancedStaticMeshComponent") or {}) do
    if c and c:IsValid() and c:GetFullName():find("/PWR/PWR.PWR:PersistentLevel.",1,true) then
        local owner=c:GetOwner()
        if owner and owner:IsValid() and owner:GetFName():ToString()=="PWR_RiparianCanopy" then
            local key=c:GetFName():ToString()
            local e=assert(expected[key],"Unknown riparian component "..key)
            assert(not found[key],"Duplicate riparian component "..key)
            found[key]=true
            local n,a,b=c:GetInstanceCount(),tonumber(c.InstanceStartCullDistance),tonumber(c.InstanceEndCullDistance)
            assert(n==e[1] and a==e[2] and b==e[3] and c:IsVisible(),"Riparian settings mismatch "..key)
            local mesh=c.StaticMesh
            assert(mesh and mesh:IsValid() and mesh:GetFullName():find(e[4],1,true),"Stock mesh mismatch "..key)
            if e[5]~="" then
                local mat=c:GetMaterial(0)
                assert(mat and mat:IsValid() and mat:GetFName():ToString()==e[5],"Local riparian palette missing "..key)
            end
            print(string.format("PWR_RIPARIAN_VEGETATION %s %d %d %d",key,n,a,b))
            total=total+n
        end
    end
end
for key in pairs(expected) do assert(found[key],"Missing riparian component "..key) end
print(string.format("PWR_RIPARIAN_VEGETATION PASS %d",total))
"""
    (OUT / "foliage-readback.lua").write_text("\n".join(header) + "\n" + code, encoding="utf-8")


def make_habitat(field, geo):
    water_distance = distance_transform_edt(field.masks["water"] < .42, sampling=field.spacing_m[::-1])
    road_distance = distance_transform_edt((field.masks["road"] < .01) & (field.masks["bases"] < .01),
                                          sampling=field.spacing_m[::-1])
    spring = next(s for s in geo["watercourses"] if s["id"] == "headwater_spring")
    spring_tree = cKDTree(spring["control_points_m"])
    centreline = np.array(geo["watercourses"][0]["erosion_reach"]["centreline_m"])
    slope = np.hypot(*np.gradient(field.heights_m, *field.spacing_m[::-1]))
    hulls, cache = [], {}
    for rock in dress.read(BASIN / "dressing/decor-moves.json")["decor"]:
        foot = dress.world_foot(rock, cache)[:, :2] * dress.UE_TO_WORLD
        hulls.append(foot[ConvexHull(foot).vertices] + np.array(rock["new_pos_ue_cm"][:2]) * dress.UE_TO_WORLD)

    def query(points, fringe=False):
        x, y = points.T
        indices = ((points - field.origin_m) / field.spacing_m).T[::-1]
        gap = map_coordinates(water_distance, indices, order=1)
        protected = map_coordinates(road_distance, indices, order=1) < 5.
        grade = map_coordinates(slope, indices, order=1)
        z = field.sample(x, y)
        fwd, side = apron.coordinates(points)
        level = np.full(len(points), 142.4)
        near = fwd < 66.
        if np.any(near):
            level[near] = apron.surface(points[near], centreline)
        rise = z - level
        px, py = apron.project(np.c_[points, z]).T
        # Keep water and the inlet waterfall readable; no tall plants across the inlet view.
        clear = (spring_tree.query(points)[0] > (3.9 if fringe else 11.)) & ~((fwd > 100) & (abs(px - 800.) < (16. if fringe else 55.)))
        live = ((fwd > 13.) & (fwd < 243.) & (px > -90.) & (px < 1690.) & (py < 1040.)
                & (rise > (.045 if fringe else .12)) & (rise < 8.) & (gap > (.32 if fringe else .55))
                & (gap < (22. if fringe else 15.)) & (grade < .79)
                & (field.sample_mask("water", x, y) < (.19 if fringe else .08)) & ~protected & clear)
        for poly in hulls:
            subset = np.where(live & (x >= poly[:, 0].min()) & (x <= poly[:, 0].max())
                              & (y >= poly[:, 1].min()) & (y <= poly[:, 1].max()))[0]
            if len(subset):
                live[subset] &= ~dress.inside_polygon(x[subset], y[subset], poly)
        return live, z, gap, fwd, side, px
    return query


def make_plants(query):
    rng = np.random.default_rng(400919)
    # Jittered colony sites with ellipses tangent to the real waterline. Local
    # samples underneath each ellipse fall away from a dense irregular core.
    xx, yy = np.meshgrid(np.arange(-496., -216., 3.85), np.arange(787., 997., 3.85))
    xy = np.c_[xx.ravel(), yy.ravel()] + rng.uniform(-1.55, 1.55, (xx.size, 2))
    valid, _, gap, fwd, side, px = query(xy)
    xy, gap, fwd, side, px = [v[valid] for v in (xy, gap, fwd, side, px)]
    proposals, family, bias = [], [], []
    for pos, depth, reach, lateral, u in zip(xy, gap, fwd, side, px):
        # Near rock and root pockets expose the cut face and gravel toe. Keep some
        # openings between colonies rather than drawing another uniform shoreline band.
        wave = .5 + .5 * np.sin(pos[0] * .087 + pos[1] * .145 + .9 * np.cos(pos[1] * .095))
        if rng.random() > .46 + .48 * wave:
            continue
        willow_chance = (.19 if reach < 78 else .34) * min(1., max(0., (depth - 1.) / 3.5))
        willow = rng.random() < willow_chance and not (reach < 62. and abs(u - 800.) < 420.)
        count = rng.integers(13, 27) if reach < 73 else rng.integers(10, 22)
        _, _, g, _, _, _ = query(pos + np.array([[.8, 0.], [-.8, 0.], [0., .8], [0., -.8]]))
        normal = np.array([g[0] - g[1], g[2] - g[3]])
        if np.linalg.norm(normal) < .00001:
            a = rng.uniform(-np.pi, np.pi)
            normal = np.array([np.cos(a), np.sin(a)])
        normal /= np.linalg.norm(normal)
        tangent = np.array([-normal[1], normal[0]])
        shape = rng.normal(size=(count, 2))
        drift = pos + shape[:, :1] * tangent * rng.uniform(1.35, 2.85) + shape[:, 1:] * normal * rng.uniform(.65, 1.45)
        for k, seed in enumerate(drift):
            if willow and k < (3 if reach > 77 else 2):
                kind = "WillowTall" if k == 0 else "WillowCrown"
            else:
                kind = rng.choice(("Rye", "RushFan", "RushStem"), p=(.41, .34, .25))
            proposals.append(seed)
            family.append(kind)
            bias.append(.75 + .25 * np.exp(-.3 * np.dot(shape[k], shape[k])))
    points = np.array(proposals)
    valid, z, gaps, reach, side, px = query(points)
    groups = {k: [] for k in SPECIES}
    for i in np.flatnonzero(valid):
        kind, h = family[i], bias[i]
        if kind == "WillowTall":
            height, width = rng.uniform(190, 285), rng.uniform(.79, 1.10)
        elif kind == "WillowCrown":
            height, width = rng.uniform(125, 205), rng.uniform(.85, 1.14)
        else:
            height, width = rng.uniform(72, 145), rng.uniform(.81, 1.20)
        if gaps[i] < 2.2:
            height *= .76
        groups[kind].append((np.r_[points[i], z[i]], h * height, width, rng.uniform(-np.pi, np.pi)))
    add_outlet_clusters(groups, query, rng)
    add_blade_turf(groups, query)
    return groups


def add_blade_turf(groups, query):
    """An upper sward with shorter scallops along the watered toe and inlet flanks."""
    rng = np.random.default_rng(412019)
    # Substitute fuller crowns among established grass groups as well as filling
    # the holes. This controls both overdraw and the number of distant clumps.
    for old_kind in ("Rye", "RushFan", "RushStem"):
        retain = []
        for p, h, w, angle in groups[old_kind]:
            if rng.random() < (.60 if old_kind == "Rye" else .32):
                new_kind = "SunRye" if rng.random() < .70 else "SunWild"
                groups[new_kind].append((p, h * (.78 if new_kind == "SunWild" else 1.02),
                                         w * rng.uniform(1.05, 1.27), angle))
            else:
                retain.append((p,h,w,angle))
        groups[old_kind] = retain
    x,y = np.meshgrid(np.arange(-493.,-216.,1.23), np.arange(790.,998.,1.23))
    pts = np.c_[x.ravel(),y.ravel()] + rng.uniform(-.43,.43,(x.size,2))
    valid,z,gap,fwd,side,u = query(pts, fringe=True)
    fringe, inlet, banks = 0, 0, 0
    for i in np.flatnonzero(valid):
        e,n = pts[i]
        wave = .5+.5*np.sin(e*.22+n*.075+2.1*np.cos(n*.15))
        inner = gap[i] < 4.6+1.6*wave
        spring = fwd[i] > 170. and abs(u[i]-800.) < 220.
        near = fwd[i]<78.
        p = .17 + .34*inner + .23*near + .18*wave + .12*spring
        if rng.random() >= p:
            continue
        # No canopy in front of the fall mouth. The riparian grass descends its flanks.
        kind = "SunRye" if rng.random() < (.61 if inner else .48) else "SunWild"
        height = rng.uniform(55.,106.) if kind == "SunRye" else rng.uniform(30.,76.)
        height *= (.83 + .32*wave) * (.76 if spring and abs(u[i]-800.)<45. else 1.)
        groups[kind].append((np.r_[pts[i],z[i]],height,rng.uniform(1.05,1.49),rng.uniform(-np.pi,np.pi)))
        fringe += int(inner)
        inlet += int(spring)
        banks += int(near)
    save("upper-sward.json",dict(added_near_outlet=banks,added_within_shore_fringe=fringe,added_on_inlet_flanks=inlet),True)


def make_willow_atlas():
    # The source uses R of its ART texture for leaf and branch opacity. The
    # native mask is retained when changing the lighting response on this lake.
    paths = []
    import os
    default = "C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks"
    paks = os.environ.get("HCE_PAKS", default)
    for stem in ("T_Downy_Willow_wknlfiuqx_8K_D", "T_DownyWillow_wknlfiuqx_8K_ART"):
        mip = "1" if stem.endswith("_D") else "0"
        path = OUT / (stem + "-mip" + mip + ".png")
        if not path.is_file():
            subprocess.run([str(ROOT/"target/release/mjolnir.exe"), "texture", "export", "--paks", paks,
                            "--asset", stem, "--mip", mip, "--out", str(path)], check=True)
        paths.append(path)
    rgba = Image.open(paths[0]).convert("RGBA")
    opacity = Image.open(paths[1]).getchannel("R")
    if rgba.size != opacity.size or not .03 < np.mean(np.asarray(opacity) > 82) < .94:
        raise ValueError("Willow diffuse and coverage atlas do not register")
    rgba.putalpha(opacity)
    rgba.save(OUT/"T_PWR_RiparianWillow.png")


def add_outlet_clusters(groups, query, rng):
    # Screen coordinates are registered against the locked 1600 x 900 outlet view.
    # The first two numbers are the basal tuft. The third is the top silhouette.
    # These edge silhouettes stay above the gravel lip with an open central basin.
    willow_anchors = [
        (5, 496, 387), (87, 503, 395), (156, 518, 420), (231, 526, 437),
        (303, 534, 459), (351, 541, 484),
        (1293, 542, 484), (1359, 529, 457), (1429, 521, 426),
        (1513, 513, 410), (1588, 507, 393),
    ]
    grass_anchors = [(7, 679), (70, 628), (111, 609), (170, 580), (240, 559),
                     (377, 547), (1203, 554), (1258, 603), (1310, 625), (1435, 674),
                     (1496, 744), (1562, 769), (1588, 831)]
    xx, yy = np.meshgrid(np.arange(-345., -235., .47), np.arange(791., 868., .47))
    xy = np.c_[xx.ravel(), yy.ravel()]
    valid, z, gap, _, _, _ = query(xy)
    xy, z, gap = xy[valid], z[valid], gap[valid]
    projected = apron.project(np.c_[xy, z])
    audit = []
    for idx, target in enumerate(willow_anchors + grass_anchors):
        willow = len(target) == 3
        offset = (projected - target[:2]) * [1., 1.35]
        metric = (offset ** 2).sum(axis=1) + (4. * np.maximum(0., (2.6 if willow else 1.) - gap)) ** 2
        best = np.argmin(metric)
        anchor = xy[best]
        jitter = rng.normal(size=(34 if willow else 19, 2)) * ([1.40, 1.08] if willow else [1.28,.83])
        jitter[0] = 0.
        spots = anchor + jitter
        live, ground, local_gap, _, _, _ = query(spots)
        for k in np.flatnonzero(live):
            basal = np.r_[spots[k], ground[k]]
            u, v = apron.project(basal)
            if willow and k < 7:
                if k == 0:
                    kind = "WillowTall"
                    per_m = v - apron.project(basal + [0., 0., 1.])[1]
                    height = np.clip(100. * (v - target[2]) / per_m, 205., 465.)
                elif k < 3:
                    kind, height = "WillowTall", rng.uniform(175., 307.)
                else:
                    kind, height = "WillowCrown", rng.uniform(120., 210.)
                width = rng.uniform(.67,.97)
                if k == 0:
                    crown = apron.project(basal + [0., 0., .01 * height])
                    audit.append(dict(seed=idx, root_uv=projected[best].round(1).tolist(),
                                      crown_uv=crown.round(1).tolist(), height_cm=round(float(height),1),
                                      silhouette_px=round(float(v - crown[1]),1), gap_m=round(float(gap[best]),2)))
            else:
                kind = rng.choice(("Rye","RushFan","RushStem"), p=(.48,.22,.3))
                height, width = rng.uniform(81.,164.), rng.uniform(.75,1.18)
                if local_gap[k] < 1.3:
                    height *= .77
            groups[kind].append((basal,height,width,rng.uniform(-np.pi,np.pi)))
    save("outlet-composition.json", audit, True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    make_willow_atlas()
    field = dress.load_heightfield(BASIN / "terrain/runtime-master.json")
    habitat = make_habitat(field, dress.read(BASIN / "terrain/terrain.geometry.json"))
    groups = make_plants(habitat)
    wind = dress.read(ROOT / "out/pwr/ground-life/grass/wind-grass.json")["meshes"]
    catalogs = {"wind": [wind["Canyon"],wind["Wild12"]], "understory": dress.read(ROOT / "out/pwr/world-art/foliage-r2/understory-bake.json")["groups"],
                "distance": dress.read(ROOT / "out/pwr/landscape-distance/vegetation/hism.json")["groups"]}
    binary = bytearray(b"MJF3" + struct.pack("<II", 3, len(groups)))
    spec, coverage = [], {}
    for index, (kind, values) in enumerate(groups.items(), 1):
        catalog, row_id, start, end = SPECIES[kind]
        source = catalogs[catalog][row_id - 1]
        origin, extent = np.array(source["origin"]), np.array(source["extent"])
        source_height = 2 * extent[2]
        if not values or source_height < 20.:
            raise ValueError(kind)
        exact = bytearray()
        binary.extend(struct.pack("<I", len(values)))
        regions = {"left_outlet": [], "right_outlet": [], "lake_margin": []}
        for p, height, width, angle in values:
            scale = height / source_height
            # Seat the native mesh's authored root pivot, with at most 4 cm of
            # bedding. Deep material/card bounds do not drive the planting height.
            position = p * np.array([100., -100., 100.])
            position[2] -= min(4., .04 * height)
            quat = [0., 0., np.sin(angle / 2), np.cos(angle / 2)]
            exact.extend(struct.pack("<10f", *position, *quat, width * scale, width * scale, scale))
            binary.extend(struct.pack("<3fBBbb3B", *position, 0, 100, 0, 0, 255, 255, 255))
            px, py = apron.project(p)
            if 0 < px < 1600 and 0 < py < 900:
                distance, lateral = apron.coordinates(p[:2])
                region = "lake_margin" if distance >= 75 else ("left_outlet" if lateral < 0 else "right_outlet")
                top = p + [0., 0., .01 * height]
                regions[region].append([height, py - apron.project(top)[1], np.linalg.norm(p - apron.EYE)])
        (OUT / ("riparian.bin.xf" + str(index))).write_bytes(exact)
        coverage[kind] = {}
        for name, rows in regions.items():
            v = np.asarray(rows)
            if len(v):
                coverage[kind][name] = {"in_frame": len(v), "median_height_cm": round(float(np.median(v[:, 0])), 2),
                                        "median_projected_height_px": round(float(np.median(v[:, 1])), 2),
                                        "max_distance_m": round(float(v[:, 2].max()), 2)}
                if v[:, 2].max() > start * .01:
                    raise ValueError("Far margin exceeds first HISM cohort " + kind)
        spec.append(dict(name=kind, mesh=source["mesh"], material=MATERIALS.get(kind,""), count=len(values), bands=BANDS, cull=[start,end],
                         source_origin_cm=origin.tolist(), source_extent_cm=extent.tolist(),
                         casts_shadow=kind.startswith("Willow"), wind_until_cm=7200 if kind.startswith("Willow") else 5400))
    (OUT / "riparian.bin").write_bytes(binary)
    save("planting.json", {"owner":"PWR_RiparianCanopy", "groups":spec, "terrain_sha256":field.manifest_sha256}, True)
    save("planting-survey.json", coverage, True)
    make_runtime_probe(spec)
    transforms = np.concatenate([np.fromfile(OUT / ("riparian.bin.xf" + str(i)), dtype="<f4").reshape(-1, 10)
                                 for i in range(1, len(spec) + 1)])
    roots = transforms[:, :3] * [.01, -.01, .01]
    support, terrain_z, gap, _, _, _ = habitat(roots[:, :2], fringe=True)
    burial = terrain_z - roots[:, 2]
    unique = len(np.unique(roots[:, :2], axis=0))
    if not support.all() or unique != len(roots) or burial.min() < 0. or burial.max() > .041:
        raise ValueError("Serialized vegetation no longer fits the collision surface or exclusion masks")
    save("planting-verified.json", dict(terrain_sha256=field.manifest_sha256, total=len(roots), unique_roots=unique,
         root_bedding_cm=[round(float(100. * burial.min()), 3), round(float(100. * burial.max()), 3)],
         closest_water_edge_m=round(float(gap.min()), 3),
         max_distance_from_outlet_m=round(float(np.linalg.norm(roots - apron.EYE, axis=1).max()), 3),
         maximum_route_or_base_mask=max(float(field.sample_mask(key, *roots[:, :2].T).max()) for key in ("road","bases")),
         maximum_water_mask=float(field.sample_mask("water", *roots[:, :2].T).max())), True)
    for kind, regions in coverage.items():
        print(kind, [(k, v["in_frame"], v["median_projected_height_px"]) for k, v in regions.items()])


if __name__ == "__main__":
    main()

