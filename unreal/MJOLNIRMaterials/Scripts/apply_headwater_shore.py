"""Add a gravel and wet-earth margin following the surveyed northern shoreline."""
from hashlib import sha256
from bisect import bisect_right
from math import dist
import json
import os
from pathlib import Path


def bank_spans(polygon, count=48):
    """Sample east and west shore positions at evenly spaced northings in metres."""
    ymin = min(p[1] for p in polygon)
    ymax = max(p[1] for p in polygon)
    rows = []
    edges = list(zip(polygon, polygon[1:] + polygon[:1]))
    for i in range(count):
        y = min(ymax - .001, max(ymin + .001, ymin + i*(ymax-ymin)/(count-1)))
        hits = sorted(x+(u-x)*(y-v)/(w-v) for (x,v),(u,w) in edges if min(v,w) <= y < max(v,w))
        if len(hits) != 2:
            raise ValueError(f"Shore at {y} needs multiple intervals: {hits}")
        rows.append(f"float2({hits[0]:.4f},{hits[1]:.4f})")
    return ymin, ymax, rows


def station_rows(reach, sections, count=32):
    """Pack the local channel coordinate system in uniform northing bands."""
    points = reach["centreline_m"]
    stations = [-reach["sill_station_m"]]
    for a,b in zip(points,points[1:]):
        stations.append(stations[-1]+dist(a[:2],b[:2]))
    rows = sorted(zip(points,stations),key=lambda v:v[0][1])
    y = [p[1] for p,_ in rows]
    widths = [p[0] for p in sections]
    result = []
    for i in range(count):
        north = y[0]+(y[-1]-y[0])*i/(count-1)
        j = min(len(y)-2,max(0,bisect_right(y,north)-1))
        (p,s),(q,t) = rows[j:j+2]
        f = (north-p[1])/(q[1]-p[1])
        station = s+f*(t-s)
        k = min(len(sections)-2,max(0,bisect_right(widths,station)-1))
        l,r = sections[k:k+2]
        g = max(0,min(1,(station-l[0])/(r[0]-l[0])))
        values = (p[0]+f*(q[0]-p[0]),station,p[2]+f*(q[2]-p[2]),.5*(l[1]+g*(r[1]-l[1])))
        result.append("float4(%s)" % ",".join("%.5f" % v for v in values))
    return y[0],y[-1],result


def main():
    import unreal as ue
    root = Path(os.environ["PWR_HEADWATER_ROOT"])
    work = Path(os.environ.get("PWR_HEADWATER_OUTPUT", root/"out/pwr/headwater-lake"))
    scripts = root/"unreal/MJOLNIRMaterials/Scripts"
    geometry = json.loads((work/"terrain/terrain.geometry.json").read_text())
    lake, = [l for l in geometry["lakes"] if l["id"] == "north_headwater_lake"]
    ymin, ymax, rows = bank_spans(lake["polygon_m"])
    fragment = (scripts/"headwater_shore.ush").read_text().replace("SHORE_SPANS",",\n".join(rows))
    fragment = fragment.replace("SHORE_Y_MIN",str(ymin)).replace("SHORE_Y_MAX",str(ymax))
    fragment = fragment.replace("LAKE_HEIGHT",str(lake["water_z_m"]))
    river, = [r for r in geometry["watercourses"] if r["id"]=="central_river"]
    if "erosion_reach" in river:
        reach = river["erosion_reach"]
        low,high,station_table = station_rows(reach,river["section_station_width_depth_m"])
        erosion = (scripts/"pwr_outlet_erosion.ush").read_text()
        erosion = erosion.replace("REACH_ROWS",",\n".join(station_table))
        erosion = erosion.replace("REACH_Y_LOW",str(low)).replace("REACH_Y_HIGH",str(high))
        fragment = ("float3 preShoreColor=originalGround, preShoreNormal=WetNormal;\n"
                    "float preShoreRough=WetRough, preShoreSpec=WetSpec;\n"
                    + fragment + "\n" + erosion)
    mat = ue.load_asset("/Game/MJOLNIR/GrassPilot/Playable/M_PWRPilot")
    lib = ue.MaterialEditingLibrary
    node = lib.get_material_property_input_node(mat,ue.MaterialProperty.MP_BASE_COLOR)
    baseline = (root/"out/pwr/sweep-polish/round31/earth/actual-graph.hlsl").read_text(encoding="cp1252").strip()
    current = node.get_editor_property("code").replace("\r\n","\n").strip()
    end = "return originalGround;"
    if not baseline.endswith(end) or baseline.count(end) != 1:
        raise ValueError("Unrecognised parent terrain shader")
    updated = baseline[:-len(end)] + fragment.rstrip() + "\n" + end
    if current == baseline:
        if os.environ.get("PWR_HEADWATER_VERIFY")=="1":
            raise RuntimeError("Expected shoreline shader is missing from the reopened editor project")
        node.set_editor_property("code",updated)
        lib.recompile_material(mat)
        if not ue.EditorAssetLibrary.save_loaded_asset(mat,False):
            raise RuntimeError("Failed saving the shoreline material")
    elif current != updated:
        raise ValueError("The editor terrain shader differs from the approved parent")
    assert node.get_editor_property("code").replace("\r\n","\n").strip() == updated
    receipt = {"material":mat.get_path_name(),"lake_level_m":lake["water_z_m"],
               "shoreline_spans":len(rows),"new_textures":0,
               "parent_shader_sha256":sha256(baseline.encode()).hexdigest(),
               "shader_sha256":sha256(updated.encode()).hexdigest()}
    if "erosion_reach" in river:
        receipt.update(outlet_station_rows=len(station_table),new_sampler_states=0,
                       sorted_bed="seeded embedded cobble domes over stock gravel and earth, world-space wetline")
    (work/"shore-material.json").write_text(json.dumps(receipt,indent=2))


if __name__ == "__main__":
    main()
