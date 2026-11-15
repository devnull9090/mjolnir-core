"""Author terrain-independent geography traced from the approved PWR reference.

Control points are route guides. The finalizer must fit curves, enforce grades,
stamp earthworks into the shared heightfield and validate water crossings.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
REFERENCE = ROOT / "docs/images/pwr-world-topdown-v1.png"


def xy(uv):
    return [round(2000 * (uv[0] - 0.5), 4), round(2000 * (0.5 - uv[1]), 4)]


def make():
    points = {
        "red_base": ([.205, .540], "base"),
        "red_gate": ([.266, .610], "base_approach"),
        "west_mid": ([.355, .515], "junction"),
        "west_upper": ([.365, .397], "junction"),
        "upper_w": ([.440, .390], "bridge_abutment"),
        "upper_e": ([.489, .390], "bridge_abutment"),
        "east_upper": ([.602, .403], "junction"),
        "east_high": ([.682, .302], "junction"),
        "east_mid": ([.681, .476], "junction"),
        "citadel_gate": ([.587, .236], "base_approach"),
        "citadel_plaza": ([.500, .245], "capture"),
        "middle_w": ([.457, .536], "bridge_abutment"),
        "middle_e": ([.518, .536], "bridge_abutment"),
        "east_crossroads": ([.579, .529], "junction"),
        "blue_gate": ([.737, .642], "base_approach"),
        "blue_base": ([.800, .540], "base"),
        "east_lakeside": ([.749, .691], "junction"),
        "lower_e": ([.633, .740], "bridge_abutment"),
        "lower_w": ([.562, .740], "bridge_abutment"),
        "west_inner": ([.350, .735], "junction"),
        "west_outer": ([.223, .711], "junction"),
        "west_south": ([.260, .862], "junction"),
        "braid_w": ([.414, .790], "culvert_approach"),
        "braid_e": ([.453, .790], "culvert_approach"),
        "south_view": ([.440, .948], "turnaround"),
        "east_shore_view": ([.865, .755], "turnaround"),
        "capture_a": ([.384, .578], "capture"),
        "capture_c": ([.620, .585], "capture"),
    }
    nodes = [{"id": key, "position_uv": uv, "position_m": xy(uv), "role": role}
             for key, (uv, role) in points.items()]
    roads = []

    def road(name, start, end, via=(), **extra):
        uv = [points[start][0], *[list(v) for v in via], points[end][0]]
        roads.append({"id": name, "from": start, "to": end,
            "control_points_uv": uv, "control_points_m": [xy(p) for p in uv],
            "width_m": 24, "shoulder_m": 6, "vegetation_clearance_m": 12,
            "max_grade": .10, "target_min_radius_m": 25,
            "curve_fit": "smooth_interpolating_spline; exact named endpoints; enforce radius during finalization",
            **extra})

    road("red_apron", "red_base", "red_gate", [[.231, .574]])
    road("red_upper_approach", "red_gate", "west_mid", [[.285, .568], [.319, .539]])
    road("west_bank_upper", "west_mid", "west_upper", [[.379, .477], [.375, .437]])
    road("west_upper_switchback", "west_upper", "upper_w", [[.337, .365], [.326, .332], [.348, .301], [.376, .280], [.393, .304], [.401, .352]])
    road("upper_w_approach", "west_upper", "upper_w", [[.398, .394]])
    road("bridge_upper", "upper_w", "upper_e", [[.4645, .390]], structure="bridge", earthwork="abutments_only")
    road("upper_e_approach", "upper_e", "east_upper", [[.532, .398], [.570, .412]])
    road("citadel_climb", "east_upper", "citadel_gate", [[.594, .365], [.620, .321], [.625, .282], [.650, .245], [.638, .211], [.610, .188]])
    road("citadel_apron", "citadel_gate", "citadel_plaza", [[.560, .258], [.530, .262]], max_grade=.06)
    road("northeast_flank", "east_upper", "east_high", [[.631, .351], [.654, .316]])
    road("east_high_loop", "east_high", "east_mid", [[.739, .290], [.796, .314], [.804, .352], [.779, .379], [.731, .404]])
    road("east_bank_upper", "east_upper", "east_mid", [[.631, .435], [.653, .458]])
    road("middle_w_approach", "west_mid", "middle_w", [[.389, .508], [.418, .524]])
    road("bridge_middle", "middle_w", "middle_e", [[.4875, .536]], structure="bridge", earthwork="abutments_only")
    road("middle_e_approach", "middle_e", "east_crossroads", [[.548, .537]])
    road("east_bank_middle", "east_crossroads", "east_mid", [[.622, .510], [.652, .493]])
    road("blue_upper_approach", "east_mid", "blue_gate", [[.678, .529], [.687, .586], [.709, .626]])
    road("blue_apron", "blue_gate", "blue_base", [[.758, .600], [.783, .570]])
    road("blue_lower_approach", "east_crossroads", "blue_gate", [[.609, .565], [.650, .601], [.688, .606], [.714, .618]])
    road("east_lakeside_approach", "blue_gate", "east_lakeside", [[.739, .665]])
    road("lower_e_approach", "east_lakeside", "lower_e", [[.710, .708], [.676, .735]])
    road("bridge_lower", "lower_w", "lower_e", [[.5975, .740]], structure="bridge", earthwork="abutments_only")
    road("lower_w_approach", "braid_e", "lower_w", [[.481, .791], [.514, .770], [.539, .750]])
    road("braid_culvert", "braid_w", "braid_e", [[.4335, .790]], structure="culvert", earthwork="preserve_channel")
    road("west_inner_lakeside", "west_inner", "braid_w", [[.358, .771], [.385, .788]])
    road("red_inner_loop", "red_gate", "west_inner", [[.299, .653], [.325, .693]])
    road("red_outer_loop", "red_gate", "west_outer", [[.250, .660]])
    road("west_crosslink", "west_outer", "west_inner", [[.263, .706], [.286, .737], [.312, .750]])
    road("southwest_sweep", "west_outer", "west_south", [[.203, .750], [.211, .807], [.232, .841]])
    road("southwest_return", "west_south", "braid_w", [[.304, .845], [.348, .835], [.378, .807]])
    road("south_lake_overlook", "west_south", "south_view", [[.306, .908], [.361, .935], [.406, .948]], terminal_turnaround_radius_m=32)
    road("east_lake_overlook", "east_lakeside", "east_shore_view", [[.793, .699], [.833, .715], [.855, .735]], terminal_turnaround_radius_m=32)
    road("capture_a_access", "west_mid", "capture_a", [[.366, .548]], max_grade=.08)
    road("capture_c_access", "east_crossroads", "capture_c", [[.593, .557]], max_grade=.08)

    river = [[.306,.018],[.322,.067],[.354,.096],[.372,.143],[.378,.204],[.390,.254],
             [.420,.291],[.432,.337],[.4645,.390],[.461,.433],[.477,.478],[.4875,.536],
             [.500,.583],[.490,.633],[.513,.669],[.554,.694],[.582,.718],[.5975,.740],[.620,.800]]
    braid = [[.490,.633],[.462,.674],[.433,.704],[.414,.744],[.4335,.790],[.415,.839],[.443,.872],[.495,.894]]
    lake = [[.495,.873],[.531,.855],[.552,.828],[.581,.815],[.602,.784],[.638,.773],
            [.663,.759],[.689,.777],[.720,.756],[.749,.744],[.779,.742],[.799,.765],
            [.824,.750],[.850,.777],[.867,.821],[.876,.862],[.861,.904],[.867,.939],
            [.842,.963],[.800,.973],[.759,.967],[.727,.984],[.681,.978],[.653,.982],
            [.617,.968],[.581,.965],[.552,.944],[.536,.920],[.503,.914],[.479,.894]]
    islands = [
        {"id":"island_west", "polygon_uv":[[.533,.883],[.553,.867],[.580,.867],[.600,.882],[.584,.896],[.555,.900],[.536,.893]]},
        {"id":"island_southeast", "polygon_uv":[[.711,.884],[.738,.868],[.764,.868],[.786,.877],[.809,.892],[.811,.910],[.784,.928],[.752,.931],[.731,.913],[.704,.903]]},
    ]
    for island in islands:
        island.update(polygon_m=[xy(p) for p in island["polygon_uv"]], shoreline="irregular_smooth", elevation="above_lake; sample_or_restore_original_landform")
    watercourses = []
    for name, uv, width, depth, relative in [
        ("central_river",river,30,3.5,[[0,1.0],[.25,.80],[.46,.56],[.62,.39],[.78,.20],[1,0]]),
        ("western_braid",braid,18,2.0,[[0,.36],[.35,.22],[.7,.09],[1,0]])]:
        watercourses.append({"id":name,"control_points_uv":uv,"control_points_m":[xy(p) for p in uv],
            "channel_width_m":width,"bank_blend_m":18,"target_water_depth_m":depth,
            "flow_direction":"listed_start_to_end", "relative_water_profile":relative,
            "profile_units":"[normalized_arc_length, relative_head_above_lake]; finalizer assigns absolute levels",
            "outlet":"southeast_lake"})
    crossings = []
    watercourses[1]["source"] = {"watercourse":"central_river", "position_uv":[.490,.633],
        "position_m":xy([.490,.633]), "level_policy":"inherit parent water level exactly at junction"}
    for road_id, watercourse, uv, kind in [
        ("bridge_upper","central_river",[.4645,.390],"bridge"),
        ("bridge_middle","central_river",[.4875,.536],"bridge"),
        ("bridge_lower","central_river",[.5975,.740],"bridge"),
        ("braid_culvert","western_braid",[.4335,.790],"culvert")]:
        r = next(r for r in roads if r["id"] == road_id)
        crossings.append({"id":road_id,"road":road_id,"watercourse":watercourse,"type":kind,
            "position_uv":uv,"position_m":xy(uv),"alignment_m":[r["control_points_m"][0],r["control_points_m"][-1]],
            "road_width_m":24,"minimum_freeboard_m":8 if kind=="bridge" else 2,
            "deck_height":"derive_from_road_grade_and_local_water_level; no river-bed fill"})
    sites = []
    def site(name, uv, role, size, team=None, polygon=None, **extra):
        sites.append({"id":name,"position_uv":uv,"position_m":xy(uv),"role":role,"team":team,
            "size_m":size,"footprint_uv":polygon,"footprint_m":[xy(p) for p in polygon] if polygon else None,
            "height_policy":"fit_local_terrain_then_localized_cut_fill; never global constantZ",**extra})
    site("red_home",[.205,.540],"permanent_base",[230,280],"red",
         [[.155,.462],[.216,.450],[.264,.518],[.264,.585],[.231,.622],[.175,.606],[.137,.549]], access_node="red_base")
    site("blue_home",[.800,.540],"permanent_base",[230,280],"blue",
         [[.779,.450],[.830,.461],[.861,.516],[.865,.572],[.826,.616],[.764,.620],[.728,.560]], access_node="blue_base")
    site("citadel_plateau",[.500,.155],"dominant_northern_citadel",[360,470],None,
         [[.462,.027],[.524,.021],[.568,.058],[.590,.116],[.593,.197],[.566,.261],[.518,.290],[.468,.279],[.423,.231],[.403,.158],[.414,.082]],
         access_node="citadel_gate", preserve_silhouette=True, earthwork="terrace interior only; retain irregular cliff apron")
    site("capture_a",points["capture_a"][0],"capture",[48,48],capture_index=0,radius_m=20,access_node="capture_a")
    site("capture_b",points["citadel_plaza"][0],"capture",[48,48],capture_index=1,radius_m=20,access_node="citadel_plaza")
    site("capture_c",points["capture_c"][0],"capture",[48,48],capture_index=2,radius_m=20,access_node="capture_c")
    site("warmup",[.216,.565],"predeployment_social_area",[42,42], terrace="red_home", access_node="red_base")
    data = {
        "schema":"pwr-site-plan-v3","status":"authored XY plan; pending heightfield calibration, curve fitting and gameplay validation",
        "reference":{"path":"docs/images/pwr-world-topdown-v1.png","sha256":hashlib.sha256(REFERENCE.read_bytes()).hexdigest(),
            "interpretation":"geographic trace, not photogrammetric measurement; full reference image maps to a square2000m footprint"},
        "coordinates":{"primary":"normalized_uv", "u":"left_to_right","v":"top_to_bottom","units":"authoring_metres_z_up",
            "world_xy":"x=2000*(u-0.5); y=2000*(0.5-v)","extent_m":[2000,2000],"origin_min_m":[-1000,-1000],"absolute_z":"unassigned"},
        "constraints":{"road_width_m":24,"target_min_curve_radius_m":25,"main_road_max_grade":.10,"base_apron_max_grade":.06,
            "junction_policy":"segment endpoints reference shared node IDs; route fitting must preserve these exact junctions",
            "terrain_policy":"localized earthworks generate a NEW final master heightfield; collision/render/PCG consume the same final hash",
            "validation_required":["fit radii and grades", "no undeclared water crossing", "bridge clearance and abutment collision", "road shoulders dry except approved structures", "lake islands remain above water", "vehicle turning and complete route traversal"]},
        "nodes":nodes,"roads":roads,"watercourses":watercourses,
        "lakes":[{"id":"southeast_lake","polygon_uv":lake,"polygon_m":[xy(p) for p in lake],"relative_water_level":0,
            "target_depth_m":[3,14],"shore_blend_m":22,"islands":islands}],"crossings":crossings,"sites":sites,
        "exclusions":{"roads":"24m carriageway plus6m shoulder each side; foliage setback12m beyond shoulders",
            "waters":"suppress ordinary grass/trees inside water polygons and channels; allow authored riparian zones",
            "bases":"site footprint plus access apron; no automatic cliff or tree placement"},
        "notes":["Three major Forerunner bridges and one minor western-braid culvert follow the reference's circulation.",
            "Two linked vehicle loops flank the central river; separate northeast and southwest loops provide alternatives.",
            "South and east lake viewpoints are deliberate wide turnarounds, not implied lake-spanning roads.",
            "The citadel access is a long curved climb; finalizer must lower or reroute its switchbacks if the10% grade limit cannot be met.",
            "No layout.py, native route, base spawnZ or water surface elevation is changed by this plan."]}
    validate(data)
    output = HERE / "site-plan-v3.json"
    output.write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8")
    print(output)
    print(f"Validated {len(nodes)} connected junctions, {len(roads)} road segments,3 bridges,1 culvert,2 islands.")
    return data


def validate(data):
    nodes={n["id"]:n for n in data["nodes"]}
    assert len(nodes)==len(data["nodes"])
    graph={key:set() for key in nodes}
    for road in data["roads"]:
        assert road["from"] in nodes and road["to"] in nodes
        assert road["control_points_m"][0]==nodes[road["from"]]["position_m"]
        assert road["control_points_m"][-1]==nodes[road["to"]]["position_m"]
        assert road["width_m"]==24 and road["target_min_radius_m"]>=25
        graph[road["from"]].add(road["to"]);graph[road["to"]].add(road["from"])
        for uv,metres in zip(road["control_points_uv"],road["control_points_m"]):
            assert all(.015<=p<=.985 for p in uv) and metres==xy(uv)
    seen=set();pending=[next(iter(nodes))]
    while pending:
        key=pending.pop()
        if key in seen:continue
        seen.add(key);pending.extend(graph[key]-seen)
    assert seen==set(nodes),"disconnected road network"
    for crossing in data["crossings"]:
        road=next(r for r in data["roads"] if r["id"]==crossing["road"])
        water=next(w for w in data["watercourses"] if w["id"]==crossing["watercourse"])
        assert crossing["position_m"] in road["control_points_m"]
        assert crossing["position_m"] in water["control_points_m"]
    for water in data["watercourses"]:
        profile=water["relative_water_profile"]
        assert profile[0][0]==0 and profile[-1]==[1,0]
        assert all(a[0]<b[0] and a[1]>=b[1] for a,b in zip(profile,profile[1:]))
    # Centerline checks catch graph crossings hidden inside a road segment,
    # accidental water crossings, and lake encroachment before earthwork.
    def cross(a,b):return a[0]*b[1]-a[1]*b[0]
    def hit(a,b,c,d):
        r=[b[i]-a[i] for i in range(2)];s=[d[i]-c[i] for i in range(2)]
        delta=[c[i]-a[i] for i in range(2)];den=cross(r,s)
        if abs(den)<1e-9:return None
        t=cross(delta,s)/den;u=cross(delta,r)/den
        if -1e-8<=t<=1+1e-8 and -1e-8<=u<=1+1e-8:
            return [a[i]+t*r[i] for i in range(2)]
        return None
    def intersections(a,b):
        return [h for x,y in zip(a,a[1:]) for z,w in zip(b,b[1:]) if (h:=hit(x,y,z,w)) is not None]
    lake=data["lakes"][0]["polygon_m"];ring=lake+[lake[0]]
    def contains(point, polygon):
        # Standard even/odd ray crossing; used for island enclosure only.
        x,y=point;inside=False
        for a,b in zip(polygon,polygon[1:]+polygon[:1]):
            if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:inside=not inside
        return inside
    for i,road in enumerate(data["roads"]):
        for water in data["watercourses"]:
            hits=intersections(road["control_points_m"],water["control_points_m"])
            allowed=[c for c in data["crossings"] if c["road"]==road["id"] and c["watercourse"]==water["id"]]
            assert not hits or len(allowed)==1,("undeclared water crossing",road["id"],water["id"])
            for point in hits:
                assert sum((point[k]-allowed[0]["position_m"][k])**2 for k in (0,1))<.01
        assert not intersections(road["control_points_m"],ring),("road enters lake",road["id"])
        assert not any(contains(p,lake) for p in road["control_points_m"]),("road inside lake",road["id"])
        for other in data["roads"][i+1:]:
            if {road["from"],road["to"]}&{other["from"],other["to"]}:continue
            assert not intersections(road["control_points_m"],other["control_points_m"]),("undeclared road junction",road["id"],other["id"])
    for island in data["lakes"][0]["islands"]:
        assert all(contains(p,lake) for p in island["polygon_m"]),"island outside lake"
    for water in data["watercourses"]:
        assert contains(water["control_points_m"][-1],lake),"watercourse must enter its outlet lake"
    assert len([c for c in data["crossings"] if c["type"]=="bridge"])==3
    assert len(data["lakes"][0]["islands"])==2


if __name__ == "__main__":
    make()
