"""Make projected PCG candidates from PWR's authoritative terrain, not final instances.

Grid placement is deterministic and contains no random selection/yaw/scale.
The saved UE graph owns density selection and all transform variation.
"""
import argparse
import functools
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pcg_foliage
import numpy as np
from heightfield import load_heightfield


def write_requests(repo, out, tree, grass, seed):
    upgrade = json.loads((repo / "levels/warfare/pwr/upgrade.json").read_text(encoding="utf-8-sig"))["PWR"]
    tree_palette = upgrade.get("pcg_tree_palette", {"recipe": "Lrg_A"})
    # Palette choice uses PCG's exported asset_draw; it never moves or resizes
    # the engine's selected points. Validate before launching any editor jobs.
    pcg_foliage.choose_recipe(tree_palette, .5)
    palette = {"kinds": {"tree": tree_palette, "grass": {
        "meshes": ["/Game/Env/Bio/Plant/GroundcoverClump/Grass_GroundcoverClump_A/SM_Grass_GroundcoverClump_A.SM_Grass_GroundcoverClump_A"],
        "rule": "short grass", "cull": [5000,12000], "bands": 3, "shadow": False, "static": True}}}
    # Match the stock path used and verified by scatter_foliage's short grass.
    from scatter_foliage import RULES, object_path
    palette["kinds"]["grass"]["meshes"] = [object_path(m[0]) for r in RULES if r["name"] == "short grass" for m in r["meshes"]]
    (out / "palette.json").write_text(json.dumps(palette, indent=2), encoding="utf-8")
    jobs = []
    for kind, source, lo, hi in (("trees",tree,.7,1.3), ("grass",grass,.7,1.1)):
        for suffix in ("", "_repeat"):
            jobs.append({"input": str(source), "output": str(out / f"{kind}{suffix}.pcg.json"),
                         "graph": f"/Game/MJOLNIR/PCGAuthoring/PWR/PCG_{kind}{suffix}",
                         "seed": seed, "scale_min":lo, "scale_max":hi})
    (out / "request.json").write_text(json.dumps({"jobs":jobs}, indent=2), encoding="utf-8")


def project_master_candidates(field, kind, spacing, target, projection_field=None):
    """Build deterministic candidate cells; UE PCG owns selection/yaw/scale.

    The scalar woodland field creates irregular connected patches, while the
    final terrain masks enforce roads, water, foundations and slope exclusions.
    Tree recipe choice does not affect position or scale: saplings stay saplings.
    """
    if kind not in ("tree", "grass") or spacing <= 0 or target <= 0:
        raise ValueError("Expected tree/grass, positive spacing and target")
    low, high = field.bounds_m
    width = int((high[0] - low[0] - 60) // spacing)
    height = int((high[1] - low[1] - 60) // spacing)
    cols, rows = np.meshgrid(np.arange(width), np.arange(height))
    x = low[0] + 30 + (cols + .5) * spacing
    y = low[1] + 30 + (rows + .5) * spacing
    # Candidate offsets happen before projection and do not move graph outputs.
    # Co-prime spatial waves avoid conspicuous regular rows in final woodlands.
    amount = .32 if kind == "tree" else .20
    x += amount * spacing * np.sin(cols * 2.399963 + rows * 1.113)
    y += amount * spacing * np.sin(rows * 2.173 + cols * 1.719)
    x, y = x.ravel(), y.ravel()
    z = field.sample(x, y)
    delta = min(field.spacing_m) * .5
    dx = (field.sample(x + delta, y) - field.sample(x - delta, y)) / (2 * delta)
    dy = (field.sample(x, y + delta) - field.sample(x, y - delta)) / (2 * delta)
    norm = np.sqrt(1 + dx * dx + dy * dy)
    normal = np.c_[-dx / norm, -dy / norm, 1 / norm]
    road = field.sample_mask("road", x, y)
    water = field.sample_mask("water", x, y)
    shore = field.sample_mask("shore", x, y)
    bases = field.sample_mask("bases", x, y)
    allowed = (road < .01) & (water < .01) & (bases < .01)
    if kind == "tree":
        forest = field.sample_mask("forest", x, y)
        allowed &= (forest > .08) & (normal[:, 2] >= .85)
        woodland = .5 + .25 * np.sin(x / 177 + .7 * np.sin(y / 113)) + .25 * np.cos(y / 149 + .7 * np.sin(x / 121))
        patch = np.clip((woodland - .28) / .62, 0, 1)
        # Small peripheral probability creates natural woodland transitions.
        density = forest * (.08 + .92 * patch * patch * (3 - 2 * patch))
    else:
        allowed &= (shore < .25) & (normal[:, 2] >= .8) & (field.sample_mask("walkable", x, y) > .5)
        density = .78 + .18 * np.sin(x / 31) * np.cos(y / 43)
    density = np.where(allowed, density, 0)
    # Solve density scale without adding/removing points in Python. The graph
    # still makes every selection from the published candidate probability.
    wanted = min(float(target), float(allowed.sum()) * .98)
    low_factor, high_factor = 0.0, 100.0
    for _ in range(48):
        factor = (low_factor + high_factor) / 2
        if np.minimum(density * factor, 1).sum() < wanted:
            low_factor = factor
        else:
            high_factor = factor
    density = np.minimum(density * ((low_factor + high_factor) / 2), 1)
    projected = projection_field or field
    if projection_field is not None:
        # Keep IDs, XY, density and biome decisions from the approved field.
        # Only the support height/normal follows the actual rendered UE grid.
        z = projected.sample(x, y)
        delta = min(projected.spacing_m) * .5
        dx = (projected.sample(x + delta, y) - projected.sample(x - delta, y)) / (2 * delta)
        dy = (projected.sample(x, y + delta) - projected.sample(x, y - delta)) / (2 * delta)
        norm = np.sqrt(1 + dx * dx + dy * dy)
        normal = np.c_[-dx / norm, -dy / norm, 1 / norm]
    points = [{"id": i, "position": [round(float(x[i]), 6), round(float(y[i]), 6), round(float(z[i]), 6)],
               "normal": [round(float(v), 8) for v in normal[i]], "density": round(float(density[i]), 6),
               "biome_mask": int(allowed[i]), "kind": kind, "biome": "woodland" if kind == "tree" else "meadow"}
              for i in range(len(x))]
    return {"schema": 1, "align_to_normal": kind == "grass", "master_sha256": projected.manifest_sha256,
            "height_sha256": projected.metadata["height"]["sha256"],
            "biome_master_sha256": field.manifest_sha256, "points": points}, {
                "candidates": len(points), "allowed": int(allowed.sum()),
                "expected_selected": round(float(density.sum()), 3), "grid_spacing_m": spacing}


def prepare_master(repo, out, manifest, target=290000, trees=2300, seed=20568, projection=None):
    repo, out = Path(repo).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    field = load_heightfield(manifest)
    projected = load_heightfield(projection) if projection else field
    for name in ("road", "water", "shore", "bases", "forest", "walkable"):
        if name not in field.masks:
            raise ValueError(f"Final master is missing required PCG mask: {name}")
    receipt = {"master": str(projected.path), "master_sha256": projected.manifest_sha256,
               "height_sha256": projected.metadata["height"]["sha256"],
               "biome_master_sha256": field.manifest_sha256, "seed": seed}
    sources = {}
    for kind, spacing, count in (("tree", 18.0, trees), ("grass", 2.0, target)):
        document, stats = project_master_candidates(field, kind, spacing, count, projected)
        source = out / ("trees.candidates.json" if kind == "tree" else "grass.candidates.json")
        source.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
        receipt[kind] = {**stats, "sha256": pcg_foliage.digest(source)}
        sources[kind] = source
    # Reload to verify hashes even if an external finalizer replaced a raster.
    current = load_heightfield(manifest)
    if current.manifest_sha256 != field.manifest_sha256:
        raise RuntimeError("Master changed during PCG projection; rerun after terrain freeze")
    if load_heightfield(projected.path).manifest_sha256 != projected.manifest_sha256:
        raise RuntimeError("Runtime projection master changed during PCG generation")
    write_requests(repo, out, sources["tree"], sources["grass"], seed)
    (out / "inputs.receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def prepare(repo, out, target=290000):
    repo, out = Path(repo).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    layout_path = repo / "levels/warfare/pwr/layout.py"
    layout_source = layout_path.read_bytes()
    layout_hash = hashlib.sha256(layout_source).hexdigest()
    spec = importlib.util.spec_from_file_location("pwr_pcg_layout", layout_path)
    layout = importlib.util.module_from_spec(spec)
    exec(compile(layout_source, str(layout_path), "exec"), layout.__dict__)
    height = functools.lru_cache(maxsize=None)(layout.height)

    def projected(x, y):
        g = layout.GRID
        x0, y0 = math.floor(x/g)*g, math.floor(y/g)*g
        u, v = (x-x0)/g, (y-y0)/g
        a, b, c, d = height(x0,y0), height(x0+g,y0), height(x0+g,y0+g), height(x0,y0+g)
        if u >= v:
            z, dx, dy = a+(b-a)*u+(c-b)*v, (b-a)/g, (c-b)/g
        else:
            z, dx, dy = a+(c-d)*u+(d-a)*v, (c-d)/g, (d-a)/g
        n = math.sqrt(dx*dx+dy*dy+1)
        return z, [-dx/n, -dy/n, 1/n]

    points = []
    # 2.5m candidate grid, staggered rows. The final graph selects only some
    # points; every candidate is projected after the positional offset.
    for row in range(720):
        y = -898.75 + row*2.5
        for col in range(720):
            x = -898.75 + col*2.5 + (.6 if row % 2 else -.6)
            z, normal = projected(x, y)
            road, water = layout.road_distance(x,y), layout.water_distance(x,y)
            allowed = road >= 18 and water >= 12 and layout.foundation_weight(x,y) <= .01 and normal[2] >= .7 and z > layout.WATER_Z+.5
            density = (.78+.18*math.sin(x/31)*math.cos(y/43)) if allowed else 0.0
            points.append({"id": len(points), "position": [x,y,round(z,6)],
                           "normal": [round(v,8) for v in normal], "density": density,
                           "biome_mask": int(allowed), "kind": "grass", "biome": "meadow"})
    expected = sum(p["density"] for p in points)
    factor = min(1.0, target/expected)
    for p in points: p["density"] = round(p["density"]*factor, 6)
    grass = out / "grass.candidates.json"
    if layout_path.read_bytes() != layout_source:
        raise RuntimeError("authoritative layout changed while projecting PCG candidates; rerun")
    grass.write_text(json.dumps({"schema": 1, "align_to_normal": True,
        "layout_sha256": layout_hash, "points": points}, separators=(",",":")), encoding="utf-8")
    tree = repo / "levels/warfare/pwr/pcg-candidates.json"
    write_requests(repo, out, tree, grass, layout.SEED)
    receipt = {"candidates":len(points), "allowed":sum(p["biome_mask"] for p in points),
               "expected_selected":round(sum(p["density"] for p in points)),
               "layout_sha256":layout_hash, "grass_sha256":pcg_foliage.digest(grass)}
    (out / "inputs.receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out", default="out/pwr/pcg")
    parser.add_argument("--target", type=int, default=290000)
    parser.add_argument("--heightfield", help="final immutable master; replaces the legacy analytical layout")
    parser.add_argument("--projection-heightfield", help="exact rendered UE grid; retains source candidate XY and biome decisions")
    parser.add_argument("--trees", type=int, default=2300)
    parser.add_argument("--seed", type=int, default=20568)
    args = parser.parse_args()
    if args.heightfield:
        print(json.dumps(prepare_master(args.repo, args.out, args.heightfield, args.target, args.trees, args.seed,
                                       args.projection_heightfield)))
    else:
        print(json.dumps(prepare(args.repo, args.out, args.target)))
