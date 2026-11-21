"""A level's ambient sound from its own water: environment.sounds for MJOLNIRLevelLoader.

Every map with baked Fluid Flux states and waterfalls gets the same treatment from a sound
palette (which waves, how loud): stream loops wherever the baked flow actually moves (the
state's velocity, so a still lake stays quiet and rapids are loudest), a waterfall loop at
each `waterfalls` entry's splash, and the palette's map-wide background beds.

Emitters follow the loader's format (the same tools/level/gen_ce_level.ambient_sounds
writes for converted CE maps): pos and inner/falloff in Unreal centimetres, gain,
fade_in, and `max` (how many of one wave play at once; the loader keeps the nearest).

    python flux_ambience.py <map folder with level.json> <palette.json> [--write]

Packagers call sounds(level, root, palette) (PWR's release stage, stage_vista.py).
"""
import argparse
import json
from pathlib import Path

import numpy as np

from flux_wrap_safe import read

WET_M = 0.15          # water this deep counts as water


def flowing_points(root, state, spec):
    """Spread points over a state's moving water: greedy, densest flow first, `spacing_m` apart."""
    height, velocity, ground = (read(Path(root) / state[k]) for k in ("height", "velocity", "ground"))
    terrain = (state["centre"][2] - ground[..., 0]) / 100.0
    depth = (height[..., 0] + state["capture"]) / 100.0 - terrain
    speed = np.hypot(velocity[..., 0], velocity[..., 1])
    band = 3   # flux_wrap_safe dries the borders; stay off them
    moving = (depth > WET_M) & (speed >= spec["min_speed"])
    moving[:band], moving[-band:], moving[:, :band], moving[:, -band:] = False, False, False, False
    rows, cols = np.nonzero(moving)
    order = np.argsort(-speed[rows, cols])
    cell, (cx, cy, _) = state["cell"], state["centre"]
    res = state["res"]
    spacing = spec["spacing_m"] * 100.0
    picked = []
    for i in order:
        r, c = rows[i], cols[i]
        # Texel column -> UE X, row -> UE Y (checked against the terrain the state was baked on).
        x = cx + (c + 0.5 - res[0] / 2) * cell
        y = cy + (r + 0.5 - res[1] / 2) * cell
        if all((x - p[0]) ** 2 + (y - p[1]) ** 2 >= spacing ** 2 for p in picked):
            z = float(height[r, c, 0]) + state["capture"]
            picked.append((float(x), float(y), z, float(speed[r, c])))
    return picked


def sounds(level, root, palette):
    root = Path(root)
    base = palette["root"].rstrip("/")

    def wave(name):
        return f"{base}/{name}.{name}"

    out = {"background": [], "emitters": []}
    for bed in palette.get("background", []):
        out["background"].append({"wave": wave(bed["wave"]), "gain": bed["gain"], "fade_in": bed.get("fade_in", 2.0),
                                  "source": "palette background"})
    water = palette.get("flowing_water")
    report = {"flowing": 0, "waterfalls": 0}
    if water:
        lo, hi = water["gain"]
        top = water.get("loud_speed", 2.0)
        for dom in (level.get("flux") or {}).get("domains", []):
            if dom.get("playback") != "baked":
                continue
            state_path = root / "flux_state" / dom["id"] / "state.json"
            if not state_path.exists():
                continue
            state = json.loads(state_path.read_text())
            for x, y, z, speed in flowing_points(root, state, water):
                t = min(1.0, max(0.0, (speed - water["min_speed"]) / max(top - water["min_speed"], 1e-3)))
                out["emitters"].append({"pos": [round(x, 1), round(y, 1), round(z, 1)], "wave": wave(water["wave"]),
                                        "gain": round(lo + (hi - lo) * t, 3), "fade_in": 2.0,
                                        "inner": water["inner_m"] * 100.0, "falloff": water["falloff_m"] * 100.0,
                                        "max": water.get("max", 8), "source": "flux flow " + dom["id"]})
                report["flowing"] += 1
    falls = palette.get("waterfall")
    if falls:
        for w in level.get("waterfalls") or []:
            # Where the water lands: the mean of the entry's splash effects, else its own position.
            spots = [e["pos"] for e in w.get("effects", []) if "pos" in e] or [w["pos"]]
            pos = [round(sum(p[k] for p in spots) / len(spots), 1) for k in range(3)]
            out["emitters"].append({"pos": pos, "wave": wave(falls["wave"]), "gain": falls["gain"], "fade_in": 2.0,
                                    "inner": falls["inner_m"] * 100.0, "falloff": falls["falloff_m"] * 100.0,
                                    "max": falls.get("max", 4), "source": "waterfall"})
            report["waterfalls"] += 1
    report["background"] = len(out["background"])
    return out, report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("map", type=Path)
    ap.add_argument("palette", type=Path)
    ap.add_argument("--write", action="store_true", help="write environment.sounds into the map's level.json")
    a = ap.parse_args()
    level_path = a.map / "level.json"
    level = json.loads(level_path.read_text())
    result, report = sounds(level, a.map, json.loads(a.palette.read_text()))
    if a.write:
        level.setdefault("environment", {})["sounds"] = result
        level_path.write_text(json.dumps(level, indent=2))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
