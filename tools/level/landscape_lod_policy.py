"""Pin audited Landscape components beneath close-fitting render-only surfaces.

The policy changes render LOD only. It never modifies heights, native collision,
or the meshes being supported. Generation needs Shapely; editor validation does
not, so commandlets can fail closed without adding Python packages.
"""
from pathlib import Path
import hashlib
import json
import math

SCHEMA = "mjolnir-landscape-lod-policy-v1"
GRID_KEYS = ("size", "components", "sections", "quads", "location", "scale")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_policy(policy, spec, source_dir):
    if policy.get("schema") != SCHEMA or policy.get("forced_lod") != 0:
        raise ValueError("Unsupported Landscape LOD policy")
    if policy.get("grid") != {key: spec[key] for key in GRID_KEYS}:
        raise ValueError("Landscape LOD policy grid differs from build inputs")
    if digest(Path(source_dir) / spec["heights"]) != policy.get("heights_sha256"):
        raise ValueError("Landscape LOD policy height bytes changed")
    for source in policy.get("sources", []):
        if digest(source["path"]) != source["sha256"]:
            raise ValueError("Landscape LOD policy source changed: " + source["path"])
    count, step = spec["components"], spec["sections"] * spec["quads"]
    if count < 1 or step < 1 or count * step + 1 != spec["size"]:
        raise ValueError("Invalid Landscape component grid")
    def coordinates(key):
        rows = policy.get(key)
        if not isinstance(rows, list) or not rows:
            raise ValueError("Missing Landscape LOD policy " + key)
        result = set()
        for row in rows:
            if (not isinstance(row, list) or len(row) != 2
                    or any(type(v) is not int or v < 0 or v >= count * step or v % step for v in row)):
                raise ValueError("Invalid Landscape section base: " + repr(row))
            if tuple(row) in result:
                raise ValueError("Duplicate Landscape section base")
            result.add(tuple(row))
        return result
    core, forced = coordinates("core_section_bases"), coordinates("forced_section_bases")
    # UE's CalcLOD blends against a neighboring section near its boundary.
    # A complete ring keeps those morphing edges outside every core component.
    required = {(x + dx * step, y + dy * step) for x, y in core
                for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                if 0 <= x + dx * step < count * step and 0 <= y + dy * step < count * step}
    if forced != required:
        raise ValueError("Landscape LOD policy must include exactly the core and its complete guard ring")
    clearance = policy.get("minimum_paving_to_morph_boundary_m")
    minimum = step * min(spec["scale"][:2]) / 100
    if (not isinstance(clearance, (int, float)) or not math.isfinite(clearance)
            or clearance < minimum - 1e-6):
        raise ValueError("Landscape LOD morph boundary clearance is unproved")
    return forced


def apply_policy(landscape, component_class, policy, spec, source_dir):
    """Set actual UE components and read every property back, including defaults."""
    forced = validate_policy(policy, spec, source_dir)
    count, step = spec["components"], spec["sections"] * spec["quads"]
    expected = {(x * step, y * step) for x in range(count) for y in range(count)}
    seen, rows = set(), []
    for component in landscape.get_components_by_class(component_class):
        key = (component.get_editor_property("section_base_x"),
               component.get_editor_property("section_base_y"))
        if key not in expected or key in seen:
            raise RuntimeError("Unexpected or duplicate Landscape component: " + repr(key))
        seen.add(key)
        value = 0 if key in forced else -1
        component.set_forced_lod(value)
        actual = component.get_editor_property("forced_lod")
        if actual != value:
            raise RuntimeError(f"Landscape component {key} ForcedLOD requested {value}, read back {actual}")
        rows.append({"section_base": list(key), "forced_lod": actual})
    if seen != expected:
        raise RuntimeError("Landscape component inventory is incomplete")
    return {"schema": "mjolnir-landscape-lod-readback-v1", "policy": SCHEMA,
            "forced_components": len(forced), "automatic_components": len(seen - forced),
            "components": sorted(rows, key=lambda row: row["section_base"]),
            "scope": "Editor component property readback; cooked runtime appearance/FPS still requires acceptance."}


def generate(land_dir, paving_path, out):
    from shapely.geometry import box, shape
    from shapely.ops import transform, unary_union
    land_dir, paving_path, out = Path(land_dir).resolve(), Path(paving_path).resolve(), Path(out).resolve()
    spec = json.loads((land_dir / "landscape.json").read_text())
    count, step = spec["components"], spec["sections"] * spec["quads"]
    sx, sy = [value * step / 100 for value in spec["scale"][:2]]
    ox, oy = [value / 100 for value in spec["location"][:2]]
    doc = json.loads(paving_path.read_text())
    # Authoring +Y maps to Unreal -Y. Component indices are Unreal-local.
    paving = transform(lambda x, y, z=None: (x, -y),
                       unary_union([shape(row["geometry"]) for row in doc["features"]]))
    boxes = {(i, j): box(ox + i * sx, oy + j * sy, ox + (i + 1) * sx, oy + (j + 1) * sy)
             for i in range(count) for j in range(count)}
    world = box(ox, oy, ox + count * sx, oy + count * sy)
    if paving.difference(world).area > 1e-8:
        raise ValueError("Paving footprint lies outside the Landscape")
    core = {key for key, cell in boxes.items() if paving.intersects(cell)}
    forced = {(i + di, j + dj) for i, j in core for di in (-1, 0, 1) for dj in (-1, 0, 1)
              if (i + di, j + dj) in boxes}
    covered = unary_union([boxes[key] for key in forced])
    # Outer world edges clamp to the boundary component; no outside LOD exists.
    morph_boundary = covered.boundary.difference(world.boundary.buffer(1e-7))
    clearance = paving.distance(morph_boundary)
    uncovered = paving.difference(covered).area
    if uncovered > 1e-8 or clearance < min(sx, sy) - 1e-6:
        raise ValueError("Courtyard LOD guard ring does not cover the measured footprint")
    result = {"schema": SCHEMA, "forced_lod": 0,
              "grid": {key: spec[key] for key in GRID_KEYS},
              "heights_sha256": digest(land_dir / spec["heights"]),
              "sources": [{"path": str(paving_path), "sha256": digest(paving_path)}],
              "core_section_bases": [[i * step, j * step] for i, j in sorted(core)],
              "forced_section_bases": [[i * step, j * step] for i, j in sorted(forced)],
              "minimum_paving_to_morph_boundary_m": clearance,
              "uncovered_paving_area_m2": uncovered, "guard_ring_components": 1,
              "full_lod0_triangles_in_forced_components": len(forced) * 2 * step * step,
              "native_collision_or_height_changes": False,
              "status": "Offline policy candidate; editor/cooked/live verification pending"}
    validate_policy(result, spec, land_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--land", type=Path, required=True)
    parser.add_argument("--paving", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = generate(args.land, args.paving, args.out)
    print(json.dumps({"core": len(result["core_section_bases"]),
                      "forced_with_guard": len(result["forced_section_bases"]),
                      "minimum_clearance_m": result["minimum_paving_to_morph_boundary_m"],
                      "full_lod0_triangles": result["full_lod0_triangles_in_forced_components"]}))
