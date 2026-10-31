"""Blender-authored permissions for procedural dressing on CE surfaces.

Coordinates in the sidecar are Blender world metres (Z up). Query points are
UE centimetres, before foliage lift/sink or cliff protrusion. Masks restrict
existing rules; they do not replace slope, biome, support or collision checks.
"""
import itertools
import json
import math
from collections import defaultdict

POLICIES = {"AUTO": (True, True), "NONE": (False, False),
            "GROUND": (True, False), "CLIFF": (False, True), "BOTH": (True, True)}


class SurfacePolicy:
    def __init__(self, document, tolerance=.05, cell=5.0):
        if document.get("schema_version") != 1 or document.get("coordinates") != "blender_world_metres_z_up":
            raise ValueError("Unsupported surface policy schema or coordinates")
        self.tolerance, self.cell = tolerance, cell
        self.grid = defaultdict(list)
        self.matched = self.rejected = 0
        for entry in document["triangles"]:
            policy = entry["policy"]
            if policy not in POLICIES:
                raise ValueError(f"Unknown PCG policy: {policy}")
            points = entry["vertices"]
            if len(points) != 3 or any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in points):
                raise ValueError("Invalid surface triangle")
            a, b, c = points
            u, v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
            n = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
            length = math.sqrt(sum(x*x for x in n))
            if length < 1e-10:
                continue
            n = [x/length for x in n]
            uu, uv, vv = sum(x*x for x in u), sum(x*y for x,y in zip(u,v)), sum(x*x for x in v)
            record = (a, u, v, n, uu, uv, vv, uu*vv-uv*uv, POLICIES[policy])
            ranges = [range(math.floor((min(p[k] for p in points)-tolerance)/cell),
                            math.floor((max(p[k] for p in points)+tolerance)/cell)+1) for k in range(3)]
            for key in itertools.product(*ranges):
                self.grid[key].append(record)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as stream:
            return cls(json.load(stream))

    def allows(self, x, y, z, channel):
        if channel not in {"ground", "cliff"}:
            raise ValueError(channel)
        p = (x/100, -y/100, z/100)
        key = tuple(math.floor(value/self.cell) for value in p)
        matched, allowed = False, True
        for a,u,v,n,uu,uv,vv,denom,permissions in self.grid.get(key, ()):
            delta = [p[i]-a[i] for i in range(3)]
            if abs(sum(delta[i]*n[i] for i in range(3))) > self.tolerance:
                continue
            du, dv = sum(delta[i]*u[i] for i in range(3)), sum(delta[i]*v[i] for i in range(3))
            s, t = (vv*du-uv*dv)/denom, (uu*dv-uv*du)/denom
            if s < -1e-5 or t < -1e-5 or s+t > 1.00001:
                continue
            matched = True
            allowed &= permissions[0 if channel == "ground" else 1]
        self.matched += int(matched)
        self.rejected += int(not allowed)
        return allowed
