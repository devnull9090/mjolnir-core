"""Read the canonical runtime manifest; never regenerate coordinates from a prototype."""
from pathlib import Path
import json
import math
from types import SimpleNamespace

def ue(position):
    return [round(position[0]*100,4),round(-position[1]*100,4),round(position[2]*100,4)]

def load_layout(path=None):
    path=Path(path) if path else Path(__file__).with_name("layout.json")
    doc=json.loads(path.read_text(encoding="utf-8-sig"))
    required=("protocol","layout_revision","homes_m","captures_m","warmup_m","flights_m",
              "scenario_bounds_m","play_area_m","capture_radius_m")
    for key in required:
        if key not in doc:raise ValueError(f"Runtime layout is missing {key}")
    if set(doc["homes_m"])!={"red","blue"} or set(doc["flights_m"])!={"red","blue"} or len(doc["captures_m"])!=3:
        raise ValueError("Warfare requires two home/flight teams and three captures")
    points=list(doc["homes_m"].values())+doc["captures_m"]+[doc["warmup_m"]]
    points += [r[k] for r in doc["flights_m"].values() for k in ("start","end")]
    if any(len(p)!=3 or not all(math.isfinite(float(v)) for v in p) for p in points):
        raise ValueError("Runtime positions must be finite metre-space triples")
    return SimpleNamespace(TITLE=doc.get("title","Pelican Warfare"),PROTOCOL=doc["protocol"],REVISION=doc["layout_revision"],
        HOMES=doc["homes_m"],CAPTURES=doc["captures_m"],WARMUP=doc["warmup_m"],FLIGHTS=doc["flights_m"],
        CAPTURE_RADIUS=float(doc["capture_radius_m"]),METRES_PER_WU=3.048,ue=ue,document=lambda:doc)
