# /// script
# dependencies = ["numpy", "shapely>=2.1,<3"]
# ///
"""Original Forerunner paving, clipped to exact runtime Landscape triangles.

    uv run levels/warfare/pwr/base_paving.py

Writes an isolated, render-only review candidate. It never edits terrain,
installed files, PCG placement or collision. Native packaging is a later step.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np
from shapely import constrained_delaunay_triangles
from shapely.geometry import LineString, MultiPoint, Point, Polygon, box, mapping
from shapely.ops import unary_union
from shapely.prepared import prep

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/level"))
from heightfield import load_heightfield, sha256
from forerunner_kit import pieces

MATERIALS = [
    "/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_B_Mid_Rough1_Low.MI_FR_Metal_Diagonal_01_B_Mid_Rough1_Low",
    "/HaloMaterialLibrary/Env/Material/HS/FR/MI_FR_Metal_Diagonal_01_C_Dark_Rough1_Low.MI_FR_Metal_Diagonal_01_C_Dark_Rough1_Low",
]


def polar(radius, angle):
    a = math.radians(angle)
    return radius * math.cos(a), radius * math.sin(a)


def design(inner, outer):
    """Reusable 3-arm motif; angular paving surrounds grass-filled courts."""
    delta = outer - inner
    shapes = []
    # Deliberately broken dodecagons, not a circular solid extension.
    for radius, width in ((inner + delta * .38, 7.0), (outer, 5.5)):
        for i in range(12):
            a, b = i * 30 + 3.5, (i + 1) * 30 - 3.5
            shapes.append(Polygon([polar(radius-width, a), polar(radius, a),
                                   polar(radius, b), polar(radius-width, b)]))
    # Three broad inter-arm spokes and three narrow secondary links.
    for angle, width in [(30, 10), (150, 10), (270, 10), (90, 4), (210, 4), (330, 4)]:
        shapes.append(LineString([polar(inner, angle), polar(outer-2, angle)]).buffer(width/2, cap_style=2))
    # Hollow triangular garden motifs: retain green within each chevron.
    for angle in (0, 60, 120, 180, 240, 300):
        tri = Polygon([polar(inner+delta*.27, angle-8), polar(inner+delta*.27, angle+8),
                       polar(outer-8, angle)])
        shapes.append(tri.difference(tri.buffer(-2.1, join_style=2)))
    return unary_union(shapes).difference(Point(0, 0).buffer(inner-.1, quad_segs=96))


def design_courts(inner, outer):
    """Broad angular service courts with recessed gardens and clear joints.

    All surfaces still drape onto the authoritative floor. The larger panels
    make the compound legible at insertion altitude, while interrupted outer
    circuits and the six planted courts avoid a solid circular metal disk.
    """
    delta = outer - inner
    shapes = []
    for radius, width in ((inner + delta * .28, 9.), (outer, 8.)):
        for i in range(12):
            a, b = i * 30 + 1.5, (i + 1) * 30 - 1.5
            shapes.append(Polygon([polar(radius-width, a), polar(radius, a),
                                   polar(radius, b), polar(radius-width, b)]))
    # Six faceted service pads, broad at the existing plaza and tapered out.
    # Chamfered corners are geometry, not a noisy all-over texture pattern.
    for angle in range(0, 360, 60):
        corners = [polar(inner+.3, angle-18), polar(inner+delta*.44, angle-18),
                   polar(outer-9, angle-10), polar(outer-7, angle-6),
                   polar(outer-7, angle+6), polar(outer-9, angle+10),
                   polar(inner+delta*.44, angle+18), polar(inner+.3, angle+18)]
        panel = Polygon(corners).buffer(-1.4,join_style=2).buffer(1.4,join_style=3)
        # Three large green courts alternate with solid vehicle-service pads.
        if angle % 120 == 0:
            garden = Polygon([polar(inner+delta*.30,angle-7),
                              polar(inner+delta*.30,angle+7),
                              polar(outer-15,angle+3),polar(outer-15,angle-3)])
            panel = panel.difference(garden)
        shapes.append(panel)
    for angle, width in [(30,16),(150,16),(270,16),(90,7),(210,7),(330,7)]:
        shapes.append(LineString([polar(inner,angle),polar(outer-1,angle)])
                      .buffer(width/2,cap_style=2))
    boundary=Polygon([polar(outer,i*30) for i in range(12)])
    return unary_union(shapes).intersection(boundary).difference(
        Point(0,0).buffer(inner-.1,quad_segs=96))


def polygon_parts(geometry):
    if geometry.is_empty:
        return
    if geometry.geom_type == "Polygon":
        yield geometry
    elif hasattr(geometry, "geoms"):
        for part in geometry.geoms:
            yield from polygon_parts(part)


def drape(geometry, field, lift=.015):
    """Split at every actual NW-SE terrain diagonal, then triangulate clips.

    Sampling only motif corners would let long faces cut through the terrain.
    Here every output triangle is wholly inside one exact source triangle.
    """
    if field.metadata.get("surface_interpolation") != "triangle_nw_se":
        raise ValueError("Paving requires the verified Landscape triangle topology")
    if not 0 < lift <= .02:
        raise ValueError("Paving lift must be positive and no more than 2 cm")
    ox, oy = field.origin_m
    dx, dy = field.spacing_m
    x0, y0, x1, y1 = geometry.bounds
    i0, i1 = max(0, math.floor((x0-ox)/dx)), min(field.dimensions[0]-2, math.floor((x1-ox)/dx))
    j0, j1 = max(0, math.floor((y0-oy)/dy)), min(field.dimensions[1]-2, math.floor((y1-oy)/dy))
    prepared = prep(geometry)
    vertices, triangles = [], []
    projected_area = 0.
    for j in range(j0, j1+1):
        for i in range(i0, i1+1):
            x, y = ox+i*dx, oy+j*dy
            for corners in (((x,y),(x+dx,y),(x,y+dy)), ((x+dx,y+dy),(x,y+dy),(x+dx,y))):
                cell = Polygon(corners)
                if not prepared.intersects(cell):
                    continue
                clip = cell.intersection(geometry)
                for poly in polygon_parts(clip):
                    if poly.area < 1e-10:
                        continue
                    for tri in constrained_delaunay_triangles(poly).geoms:
                        xy = np.asarray(tri.exterior.coords)[:3]
                        # Upward winding in authored Z-up, including clipped edges.
                        a,b=xy[1]-xy[0],xy[2]-xy[0]
                        if a[0]*b[1]-a[1]*b[0] < 0:
                            xy = xy[[0,2,1]]
                        z = field.sample(xy[:,0], xy[:,1]) + lift
                        start = len(vertices)
                        vertices.extend(np.c_[xy,z].tolist())
                        triangles.append([start,start+1,start+2])
                        projected_area += tri.area
    if abs(projected_area-geometry.area) > max(1e-5, geometry.area*1e-9):
        raise ValueError(f"Triangulation lost footprint: {projected_area} != {geometry.area}")
    v, t = np.asarray(vertices, dtype=np.float64), np.asarray(triangles, dtype=np.int32)
    # Interior probes prove whole-face alignment, not merely vertex placement.
    centroids = v[t].mean(1)
    errors = centroids[:,2] - field.sample(centroids[:,0],centroids[:,1]) - lift
    if float(np.max(np.abs(errors))) > 1e-6:
        raise ValueError("Paving crosses a terrain triangle edge")
    return v, t, float(np.max(np.abs(errors)))


def obstacles(geometry, sites, road_margin=1., building_margin=.4):
    roads = unary_union([LineString(np.asarray(r.get("centreline_m",r.get("deck_centreline_m")))[:,:2])
                        .buffer(float(r.get("width_m",24))/2, cap_style=2)
                        for r in geometry["roads"] if len(r.get("centreline_m",r.get("deck_centreline_m",[])))>1])
    # Reserve the complete footprint, including flat road endpoints. Expanding
    # only line width left zero margin at those caps after float32 packaging.
    if road_margin:roads=roads.buffer(road_margin,join_style=2)
    buildings = []
    for site in sites:
        for part in pieces(site["id"],site["position_m"],citadel=site["id"]=="citadel_plateau"):
            buildings.append(MultiPoint(np.asarray(part["vertices_m"])[:,:2]).convex_hull.buffer(building_margin))
    return roads, unary_union(buildings)


def overlap_report(footprint, trees_path, decor_path, bounds_path):
    trees = json.loads(trees_path.read_text())["instances"]
    tree_hits = []
    for tree in trees:
        point = Point(tree["position"][:2])
        if footprint.distance(point) <= 3*float(tree["scale"]):
            tree_hits.append({"id":tree["id"],"recipe":tree.get("recipe"),"position_m":tree["position"],
                              "root_on_paving":footprint.covers(point),
                              "clearance_to_paving_m":footprint.distance(point),
                              "proposed_exclusion_radius_m":3*float(tree["scale"])})
    catalogue = {x["path"]:x for x in json.loads(bounds_path.read_text())}
    rock_hits, unchecked = [], []
    for item in json.loads(decor_path.read_text())["decor"]:
        if "rock" not in item["mesh"].lower():
            continue
        source = catalogue.get(item["mesh"])
        if source is None:
            unchecked.append(item["id"])
            continue
        # Conservative transformed stock AABB footprint. No claim of a hull
        # intersection from this review; collision geometry is never changed.
        low, high = np.asarray(source["min"]),np.asarray(source["max"])
        xy = np.array([[x,y] for x in (low[0],high[0]) for y in (low[1],high[1])])*np.asarray(item["scale"][:2])
        yaw=math.radians(item["rot"][1]); rot=np.array([[math.cos(yaw),-math.sin(yaw)],[math.sin(yaw),math.cos(yaw)]])
        xy=(xy@rot.T+np.asarray(item["pos"][:2]))*np.array([.01,-.01])
        overlap=MultiPoint(xy).convex_hull.intersection(footprint).area
        if overlap>1e-6:
            rock_hits.append({"id":item["id"],"mesh":item["mesh"],"conservative_overlap_m2":overlap})
    return {"trees":tree_hits,"rocks":rock_hits,"unchecked_rock_ids":unchecked,
            "recommendation":"If accepted, subtract paving buffered by 0.75 m from grass. Only remove a tree if root_on_paving is true; nearby crowns may overhang naturally. Review listed conservative rock footprints before proposing any movement. No placements or collision changed."}


def rock_courts(decor_path,bounds_path,margin=1.5):
    """Conservative planted pockets around existing rocks, preserving scenery."""
    from b30_collision import rotator_matrix
    catalogue={x['path']:x for x in json.loads(bounds_path.read_text())}
    footprints=[]
    for item in json.loads(decor_path.read_text())['decor']:
        if 'rock' not in item['mesh'].lower():continue
        source=catalogue.get(item['mesh'])
        if source is None:raise ValueError('Missing rock bounds: '+item['mesh'])
        lo,hi=np.asarray(source['min']),np.asarray(source['max'])
        corners=np.array([[x,y,z] for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])])
        world=(corners*np.asarray(item['scale']))@rotator_matrix(*item['rot'])+np.asarray(item['pos'])
        footprints.append(MultiPoint(world[:,:2]*np.array([.01,-.01])).convex_hull.buffer(margin,join_style=2))
    return unary_union(footprints)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master",type=Path,default=ROOT/"levels/warfare/pwr/terrain/runtime-v5/runtime-master.json")
    parser.add_argument("--geometry",type=Path,default=ROOT/"levels/warfare/pwr/terrain/final-v5/terrain.geometry.json")
    parser.add_argument("--out",type=Path,default=ROOT/"out/pwr/visual-v5/base-paving")
    parser.add_argument("--trees",type=Path,default=ROOT/"out/pwr/pcg-v5/trees.selected.json")
    parser.add_argument("--decor",type=Path,default=ROOT/"out/pwr/world-v5/authored-decor.json")
    parser.add_argument("--rock-bounds",type=Path,default=ROOT/"out/pwr/visual-v4/assets/rock-bounds.json")
    parser.add_argument("--design",choices=("rings","courts"),default="rings")
    parser.add_argument("--home-outer",type=float,default=130.)
    parser.add_argument("--citadel-outer",type=float,default=165.)
    parser.add_argument("--respect-rocks",action="store_true")
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    if not 100<=args.home_outer<=180 or not 140<=args.citadel_outer<=210:
        raise ValueError("Court radii exceed the reviewed base surroundings")
    field=load_heightfield(args.master);geometry=json.loads(args.geometry.read_text())
    sites=[s for s in geometry["sites"] if s["id"] in ("red_home","blue_home","citadel_plateau")]
    roads,buildings=obstacles(geometry,sites)
    reserved_rocks=rock_courts(args.decor,args.rock_bounds) if args.respect_rocks else Polygon()
    all_footprints=[];parts=[];features=[]
    from shapely.affinity import translate
    for site in sites:
        citadel=site["id"]=="citadel_plateau"
        inner,outer=(118.2,args.citadel_outer) if citadel else (82.,args.home_outer)
        cx,cy=site["position_m"][:2]
        pattern=translate((design_courts if args.design=="courts" else design)(inner,outer),cx,cy)
        pattern=pattern.difference(roads.union(buildings).union(reserved_rocks)).buffer(0)
        # Dark flush joints are geometric inlays, never stacked/copanar skins.
        middle=pattern.buffer(-.65,join_style=2)
        trim=pattern.difference(middle)
        for label,poly,slot in (("panels",middle,0),("joints",trim,1)):
            vertices,triangles,error=drape(poly,field)
            name=site["id"]+"_"+label
            np.savez_compressed(args.out/(name+".npz"),vertices_m=vertices,triangles=triangles)
            parts.append({"id":name,"site":site["id"],"material_slot":slot,"mesh_file":name+".npz",
                          "triangles":len(triangles),"area_m2":poly.area,"max_face_alignment_error_m":error})
        all_footprints.append(pattern)
        features.append({"type":"Feature","properties":{"id":site["id"],"radius_m":outer},"geometry":mapping(pattern)})
        print(site["id"],"area",round(pattern.area,1),"m2",flush=True)
    footprint=unary_union(all_footprints)
    overlap=overlap_report(footprint,args.trees,args.decor,args.rock_bounds)
    (args.out/"overlaps.json").write_text(json.dumps(overlap,indent=2)+"\n")
    (args.out/"footprints.geojson").write_text(json.dumps({"type":"FeatureCollection","features":features})+"\n")
    receipt={"schema":"pwr-base-paving-v1","coordinates":"authoring_metres_z_up","render_only":True,
             "lift_m":.015,"collision":False,"design":args.design,"rock_garden_margin_m":1.5 if args.respect_rocks else 0,
             "native_packaging":"not performed; preview review required",
             "placement_inputs":{"trees_sha256":sha256(args.trees),"decor_sha256":sha256(args.decor),"rock_bounds_sha256":sha256(args.rock_bounds)},
             "master_sha256":field.manifest_sha256,"geometry_sha256":sha256(args.geometry),
             "source_sha256":sha256(Path(__file__)),"materials":MATERIALS,"parts":parts,
             "triangles":sum(p["triangles"] for p in parts),"total_paving_m2":footprint.area,
             "road_overlap_m2":footprint.intersection(roads).area,"existing_structure_overlap_m2":footprint.intersection(buildings).area,
             "tree_candidates":len(overlap["trees"]),"rock_candidates":len(overlap["rocks"]),
             "unverified_rock_bounds":len(overlap["unchecked_rock_ids"]),
             "files":{p.name:sha256(p) for p in args.out.glob("*.npz")}}
    (args.out/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps({k:receipt[k] for k in ("triangles","total_paving_m2","road_overlap_m2","existing_structure_overlap_m2","tree_candidates","rock_candidates","unverified_rock_bounds")},indent=2))


if __name__=="__main__":
    main()
