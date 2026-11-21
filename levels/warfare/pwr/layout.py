"""Seeded 2 km Warfare contract: metres, Z up, shared by every generation stage."""
import json
import math
from pathlib import Path

CODE, TITLE = "PWR", "Pelican Warfare"
METRES_PER_WU = 3.048
SEED, PROTOCOL, REVISION = 20568, 20568, 2
HALF_X = HALF_Y = 1000.0
SKY_Z, WATER_Z, CAPTURE_RADIUS, GRID = 350.0, 12.0, 20.0, 25
HOMES = {"red": [-760.0, 0.0, 36.0], "blue": [760.0, 0.0, 36.0]}
CAPTURES = [[-450.0, 240.0, 36.4], [0.0, 0.0, 36.4], [450.0, -240.0, 36.4]]
WARMUP = [-500.0, 780.0, 37.0]
SATELLITES = [[-620.0, -590.0, 36.0], [620.0, 590.0, 36.0]]
FLIGHTS = {
    "red": {"start": [-850.0, -180.0, 240.0], "end": [850.0, -180.0, 240.0], "yaw": 0.0},
    "blue": {"start": [850.0, 180.0, 240.0], "end": [-850.0, 180.0, 240.0], "yaw": 180.0},
}
LAKES = [(80.0, 650.0, 155.0, 135.0), (-80.0, -520.0, 150.0, 115.0)]
BRIDGES = [-350.0, 0.0, 350.0]

def ue(p):
    return [round(p[0]*100,4), round(-p[1]*100,4), round(p[2]*100,4)]

def smooth(a,b,x):
    t=max(0.0,min(1.0,(x-a)/(b-a)))
    return t*t*(3-2*t)

def river_x(y):
    return 55*math.sin(y/210)+25*math.sin(y/93)

def water_distance(x,y):
    d=abs(x-river_x(y))-(32+5*math.sin(y/110))
    for cx,cy,rx,ry in LAKES:
        d=min(d,(math.hypot((x-cx)/rx,(y-cy)/ry)-1)*min(rx,ry))
    return d

def road_distance(x,y):
    lines=[(abs(x-650),abs(y)<=800),(abs(x+650),abs(y)<=800),
           (abs(y-650),250<=abs(x)<=760),(abs(y+650),250<=abs(x)<=760),
           (abs(y),abs(x)<=850),(abs(y-350),abs(x)<=650),(abs(y+350),abs(x)<=650),
           (abs(y-800),abs(x)<=650),(abs(y+800),abs(x)<=650),(abs(x+500),650<=y<=800)]
    d=min([v for v,ok in lines if ok] or [1e6])
    for cx,cy,_ in CAPTURES+SATELLITES:
        side=-650 if cx<0 else 650
        if min(side,cx)-10 <= x <= max(side,cx)+10:
            d=min(d,abs(y-cy))
    return d

def road(x,y):
    return road_distance(x,y)<16

def foundation_weight(x,y):
    w=0.0
    for cx,cy,_ in list(HOMES.values())+CAPTURES+SATELLITES+[WARMUP]:
        size=105 if abs(cx)==760 else 70 if [cx,cy]==WARMUP[:2] else 65
        w=max(w,1-smooth(size,size+30,max(abs(x-cx),abs(y-cy))))
    return w

def height(x,y):
    rolling=36+11*math.sin(x/178)*math.cos(y/163)+7*math.sin((x+y)/117)
    h=rolling+(36-rolling)*(1-smooth(25,55,road_distance(x,y)))
    h+=(36-h)*foundation_weight(x,y)
    d=water_distance(x,y)
    bed=7+2*math.sin(y/175)
    ford=min(abs(y-800),abs(y+800))
    bed+=(11.65-bed)*(1-smooth(25,60,ford))
    h=bed+(h-bed)*smooth(-12,42,d)
    if ford<60:
        target=11.65+(36-11.65)*smooth(35,210,abs(x-river_x(y)))
        h+=(target-h)*(1-smooth(25,60,ford))
    crown=smooth(860,995,max(abs(x),abs(y)))
    return h+(165+27*math.sin(x/96)*math.cos(y/111)-h)*crown

def sampled_height(x,y):
    """Exact interpolation of the 25 m triangle shell for source placements."""
    x0=max(-1000,min(975,math.floor(x/GRID)*GRID)); y0=max(-1000,min(975,math.floor(y/GRID)*GRID))
    u,v=(x-x0)/GRID,(y-y0)/GRID
    a,b,c,d=(height(x0,y0),height(x0+GRID,y0),height(x0+GRID,y0+GRID),height(x0,y0+GRID))
    return a+(b-a)*u+(c-b)*v if u>=v else a+(c-d)*u+(d-a)*v

def forest_weight(x,y):
    if abs(x)>850 or abs(y)>850 or water_distance(x,y)<60 or road_distance(x,y)<28 or foundation_weight(x,y)>.02:
        return 0.0
    return max(0.0,min(1.0,.55+.4*math.sin(x/127)*math.cos(y/109)+.2*math.sin((x-y)/73)))

def document():
    return {"schema":"pwr-layout-v2","code":CODE,"title":TITLE,"seed":SEED,
        "protocol":PROTOCOL,"layout_revision":REVISION,
        "coordinates":{"authoring":"metres, Z up","unreal":"[100*x, -100*y, 100*z] centimetres","blam":"metres / 3.048","origin_m":[0,0,0]},
        "play_area_m":{"min":[-950,-950,-20],"max":[950,950,SKY_Z]},
        "scenario_bounds_m":{"min":[-1000,-1000,-20],"max":[1000,1000,SKY_Z]},
        "homes_m":HOMES,"captures_m":CAPTURES,"capture_radius_m":CAPTURE_RADIUS,
        "warmup_m":WARMUP,"satellites_m":SATELLITES,"flights_m":FLIGHTS,
        "insertion_seconds":60,"forced_exit_seconds":54,"descent_timeout_seconds":90,
        "flight_envelope_status":"authored 2 km candidate; requires new native physics validation",
        "terrain":{"grid_m":GRID,"water_level_m":WATER_Z,"lakes_m":LAKES,"bridge_y_m":BRIDGES,"ford_y_m":[-800,800]},
        "vehicle_roads":{"width_m":24,"shoulder_m":4,"maximum_ford_depth_m":.35},
        "forest":{"seed":SEED,"candidate_spacing_m":32,"target_count":800}}

if __name__=="__main__":
    Path(__file__).with_suffix(".json").write_text(json.dumps(document(),indent=2)+"\n")
