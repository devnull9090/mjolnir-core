"""Export deterministic terrain masks and candidates; no runtime geometry spawning."""
import json
import math
from pathlib import Path
import random
import layout

def export_candidates(out):
    rng=random.Random(layout.SEED)
    points=[]
    for y0 in range(-864,865,32):
        for x0 in range(-864,865,32):
            x,y=x0+rng.uniform(-8,8),y0+rng.uniform(-8,8)
            z=layout.sampled_height(x,y)
            dx=(layout.sampled_height(x+1,y)-layout.sampled_height(x-1,y))/2
            dy=(layout.sampled_height(x,y+1)-layout.sampled_height(x,y-1))/2
            n=math.sqrt(dx*dx+dy*dy+1)
            density=layout.forest_weight(x,y)
            if math.hypot(dx,dy)>.65: density=0
            points.append({"id":len(points),"position":[round(x,5),round(y,5),round(z,5)],
                           "normal":[-dx/n,-dy/n,1/n],"density":density,"kind":"tree","biome":"forest",
                           "biome_mask":int(density>0),"road_distance_m":layout.road_distance(x,y),
                           "water_distance_m":layout.water_distance(x,y)})
    doc={"schema":1,"seed":layout.SEED,"coordinates":"authoring metres Z up","points":points}
    (Path(out)/"pcg-candidates.json").write_text(json.dumps(doc,separators=(",",":"))+"\n")
    cells=[]
    for y in range(-1000,1001,25):
        for x in range(-1000,1001,25):
            cells.append([x,y,layout.height(x,y),layout.road_distance(x,y),layout.water_distance(x,y),layout.foundation_weight(x,y),layout.forest_weight(x,y)])
    (Path(out)/"terrain-masks.json").write_text(json.dumps({"schema":1,"seed":layout.SEED,"spacing_m":25,
        "columns":["x","y","height","road_distance","water_distance","foundation_weight","forest_weight"],"cells":cells},separators=(",",":"))+"\n")
    return {"candidates":len(points),"allowed":sum(p["biome_mask"] for p in points),"expected_selected":round(sum(p["density"] for p in points))}

if __name__=="__main__":
    print(export_candidates(Path(__file__).resolve().parent))
