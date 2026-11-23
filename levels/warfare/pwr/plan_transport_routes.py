"""Choose where Pelican Warfare's transports wait out of sight, and how high
they fly to clear the mountains on the way in.

The distant mountains are a render-only mesh outside the 2 km simulation box
(SM_PWR_DistantApron). A vehicle can sit out there asleep, but the
simulation removes any awake object outside the BSP, whatever the scenario's
world bounds say (tested 2026-11-22: a Spirit or Pelican given a velocity
out there vanished at once). So every transport starts inside the box. For
every capture spot (each site's candidates, classic first) and each team's
reinforcement Pelican, this walks outward from the spot (or the team's
flight start) to the box's edge and takes the first point there where a
transport 25 m above the ground is hidden from both homes and every capture
spot by the ground between ("behind"). Where none is, it takes the point at
the edge ("edge"), and the native code keeps the transport hidden
(object_hide) until it has climbed (a Spirit) or reached its flight start (a
Pelican). The cruise height clears every point of the ground on the way in
by 60 m.

Writes `transport_routes_m` into layout.json (with --write):
  {"pelicans": {"red": {"staging": [x, y, z], "path": [[x, y, z], ...]}, "blue": ...},
   "spirits": [[{"entry": [x, y, z], "yaw": deg, "hidden": "behind"|"edge",
                 "path": [[x, y, z], ...]}, ...], ...]}
A path's points follow its start: a Pelican's ends at its flight start, a
Spirit's at its hover (HOVER m over the spot).
Yaw is the direction of travel in authoring axes (degrees from +x toward +y).

    python levels/warfare/pwr/plan_transport_routes.py --apron <apron.source.npz> [--write]
"""
import argparse
import json
import math
import re
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
LAYOUT = HERE / "layout.json"
TERRAIN_H = HERE.parents[2] / "native" / "lobby" / "warfare_flight_terrain.h"
CELL = 20.0              # apron raster, m
EXTENT = 4000.0
BOX = 1000.0
EYE = 1.8                # viewer eye height, m
LIFT = 25.0              # a waiting transport's height over the ground, m
CLEAR = 60.0             # cruise clearance, m
SEARCH = (880.0, 980.0, 10.0)  # inside the box's edge, m from the centre line
HOVER = 8.0              # a Spirit's hover over the ground it unloads on, m
MAX_POINTS = 6           # a route's points, the native table's width
MARGIN = 2.0             # ground above the sight line by this much hides, m


def apron_raster(npz):
    v = np.load(npz)["vertices_m"]
    n = int(2 * EXTENT / CELL) + 1
    grid = np.full((n, n), -np.inf)
    ix = np.clip(((v[:, 0] + EXTENT) / CELL).round().astype(int), 0, n - 1)
    iy = np.clip(((v[:, 1] + EXTENT) / CELL).round().astype(int), 0, n - 1)
    np.maximum.at(grid, (iy, ix), v[:, 2])
    # Cells no vertex fell in take their neighbours' height.
    for _ in range(8):
        empty = ~np.isfinite(grid)
        if not empty.any():
            break
        padded = np.pad(grid, 1, constant_values=-np.inf)
        neigh = np.max([padded[1 + dy:n + 1 + dy, 1 + dx:n + 1 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)], axis=0)
        grid[empty] = neigh[empty]
    return grid


def box_terrain():
    text = TERRAIN_H.read_text()
    x0 = float(re.search(r"WF_TERRAIN_X0 (-?[\d.]+)f", text).group(1))
    y0 = float(re.search(r"WF_TERRAIN_Y0 (-?[\d.]+)f", text).group(1))
    step = float(re.search(r"WF_TERRAIN_STEP ([\d.]+)f", text).group(1))
    body = text[text.index("wf_terrain_surface"):]
    body = body[body.index("{") + 1:]
    rows = re.findall(r"\{([-\d,\s]+)\}", body[:body.index("};")])
    return x0, y0, step, np.array([[float(v) for v in r.split(",") if v.strip()] for r in rows])


class Ground:
    def __init__(self, npz):
        self.apron = apron_raster(npz)
        self.x0, self.y0, self.step, self.box = box_terrain()

    def __call__(self, x, y):
        if abs(x) <= BOX and abs(y) <= BOX:
            u = min(max((x - self.x0) / self.step, 0), self.box.shape[1] - 1.001)
            v = min(max((y - self.y0) / self.step, 0), self.box.shape[0] - 1.001)
            i, j = int(u), int(v)
            u, v = u - i, v - j
            b = self.box
            return (1 - v) * ((1 - u) * b[j, i] + u * b[j, i + 1]) + v * ((1 - u) * b[j + 1, i] + u * b[j + 1, i + 1])
        n = self.apron.shape[0]
        i = int(round((x + EXTENT) / CELL)); j = int(round((y + EXTENT) / CELL))
        return float(self.apron[min(max(j, 0), n - 1), min(max(i, 0), n - 1)])


def hidden(ground, viewers, p):
    for v in viewers:
        d = math.dist(v[:2], p[:2])
        steps = max(2, int(d / 25))
        for k in range(1, steps):
            f = k / steps
            x, y = v[0] + (p[0] - v[0]) * f, v[1] + (p[1] - v[1]) * f
            if ground(x, y) > v[2] + (p[2] - v[2]) * f + MARGIN:
                break
        else:
            return False
    return True


def cruise_over(ground, a, b):
    d = math.dist(a[:2], b[:2])
    top = max(ground(a[0] + (b[0] - a[0]) * k / 100, a[1] + (b[1] - a[1]) * k / 100) for k in range(101)) if d else ground(*a[:2])
    return round(max(top + CLEAR, a[2] + 30.0), 1)


def waypoints(ground, a, b, hover_lift):
    """The way from a hidden start `a` to a hover `hover_lift` m over `b`:
    straight up to the height that clears the highest ground ahead, along to
    over that ground, then down along the upper hull of the ground ahead
    (CLEAR over it), so the descent follows the mountainside instead of
    diving at the end. At most MAX_POINTS points; the last is the hover."""
    n = 120
    pts = [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]
    need = [float(ground(x, y)) + CLEAR for x, y in pts]
    hover = (b[0], b[1], float(ground(b[0], b[1])) + hover_lift)
    crest = max(range(n + 1), key=lambda k: need[k])
    top = max(need[crest], a[2] + 30.0)
    # Upper hull of (k, need) from the crest to the hover.
    hull = [(crest, top)]
    for k, z in [(k, need[k]) for k in range(crest + 1, n)] + [(n, hover[2])]:
        while len(hull) >= 2:
            (k1, z1), (k2, z2) = hull[-2], hull[-1]
            if (z2 - z1) * (k - k1) <= (z - z1) * (k2 - k1):
                hull.pop()
            else:
                break
        hull.append((k, z))
    # Keep the steepest bends while there are too many.
    while len(hull) > MAX_POINTS - 1:
        bends = [abs((hull[i + 1][1] - hull[i][1]) / max(1, hull[i + 1][0] - hull[i][0])
                     - (hull[i][1] - hull[i - 1][1]) / max(1, hull[i][0] - hull[i - 1][0])) for i in range(1, len(hull) - 1)]
        i = 1 + bends.index(min(bends))
        z_line = hull[i - 1][1] + (hull[i + 1][1] - hull[i - 1][1]) * (hull[i][0] - hull[i - 1][0]) / (hull[i + 1][0] - hull[i - 1][0])
        if z_line < hull[i][1]:
            # Dropping it would cut the hill: lift its neighbours instead.
            lift = hull[i][1] - z_line
            hull[i - 1] = (hull[i - 1][0], hull[i - 1][1] + lift)
        hull.pop(i)
    out = [[a[0], a[1], top]]
    for k, z in hull:
        if k == n:
            out.append(list(hover))
        else:
            out.append([pts[k][0], pts[k][1], z])
    return [[round(float(c), 1) for c in w] for w in out]


def outward(spot):
    x, y = spot[0], spot[1]
    if math.hypot(x, y) < 100:
        return (0.0, 1.0)
    r = math.hypot(x, y)
    return (x / r, y / r)


def start_for(ground, viewers, origin):
    ux, uy = outward(origin)
    last = None
    s = 0.0
    while True:
        s += SEARCH[2]
        p = (origin[0] + ux * s, origin[1] + uy * s)
        reach = max(abs(p[0]), abs(p[1]))
        if reach > SEARCH[1]:
            break
        if reach < SEARCH[0]:
            continue
        candidate = (p[0], p[1], ground(*p) + LIFT)
        if hidden(ground, viewers, candidate):
            return [round(c, 1) for c in candidate], "behind"
        last = [round(c, 1) for c in candidate]
    return last, "edge"


def plan(npz):
    layout = json.loads(LAYOUT.read_text())
    ground = Ground(npz)
    sites = [[layout["captures_m"][i]] + layout.get("capture_candidates_m", [[], [], []])[i] for i in range(3)]
    viewers = [[*h[:2], h[2] + EYE] for h in layout["homes_m"].values()]
    viewers += [[*s[:2], s[2] + EYE] for site in sites for s in site]
    spirits = []
    for site in sites:
        routes = []
        for spot in site:
            entry, how = start_for(ground, viewers, spot)
            yaw = math.degrees(math.atan2(spot[1] - entry[1], spot[0] - entry[0]))
            routes.append({"entry": entry, "yaw": round(yaw, 1), "hidden": how,
                           "path": waypoints(ground, entry, spot, HOVER)})
        spirits.append(routes)
    pelicans = {}
    for team, flight in layout["flights_m"].items():
        start = flight["start"]
        staging, how = start_for(ground, viewers, start)
        top = max(cruise_over(ground, staging, start), round(start[2], 1))
        pelicans[team] = {"staging": staging, "hidden": how,
                          "path": [[staging[0], staging[1], top], [round(start[0], 1), round(start[1], 1), round(start[2], 1)]]}
    return layout, {"pelicans": pelicans, "spirits": spirits}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apron", required=True)
    p.add_argument("--write", action="store_true")
    a = p.parse_args()
    layout, routes = plan(a.apron)
    for team, r in routes["pelicans"].items():
        print(f"pelican {team}: waits at {r['staging']} ({r['hidden']}), then {r['path']}")
    for i, site in enumerate(routes["spirits"]):
        for k, r in enumerate(site):
            print(f"site {'ABC'[i]} spot {k}: enters at {r['entry']} ({r['hidden']}), then {r['path']}")
    if a.write:
        out = {}
        for key, value in layout.items():
            if key == "transport_routes_m":
                continue
            out[key] = value
            if key == "capture_candidates_m":
                out["transport_routes_m"] = routes
        out.setdefault("transport_routes_m", routes)
        LAYOUT.write_text(json.dumps(out, indent=2) + "\n")
        print(f"wrote transport_routes_m into {LAYOUT}")


if __name__ == "__main__":
    main()
