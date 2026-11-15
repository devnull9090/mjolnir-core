"""Fluid Flux capture geometry and bake provenance from the rendered terrain.

The capture mesh keeps the runtime field's original grid and triangle diagonal.
It is render-only, shown to the Flux ground capture, never native collision.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np

from heightfield import load_heightfield, sha256

PROVENANCE_SCHEMA = "mjolnir-flux-provenance-v1"
HASH_KEYS = ("terrain_manifest_sha256", "terrain_samples_sha256", "water_geometry_sha256",
             "capture_bed_sha256", "settings_sha256")


def stable_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def validate_domain(domain):
    if not isinstance(domain, dict):
        raise ValueError("Flux domain must be an object")
    centre = np.asarray(domain.get("centre", []), dtype=float)
    res = np.asarray(domain.get("res", []), dtype=float)
    cell, height = float(domain.get("cell", 0)), float(domain.get("height", 0))
    if centre.shape != (3,) or res.shape != (2,) or not np.all(np.isfinite(centre)):
        raise ValueError("Flux domain needs finite centre[3] and res[2]")
    if not np.all(np.isfinite(res)) or np.any(res != res.astype(int)) or np.any(res <= 0):
        raise ValueError("Flux resolution must contain positive integers")
    if np.any(res > 1024) or np.any((res.astype(int) & (res.astype(int) - 1)) != 0):
        raise ValueError("New Flux domains require power-of-two resolution <=1024")
    if not np.isfinite(cell) or not np.isfinite(height) or cell <= 0 or not 0 < height <= 32000:
        raise ValueError("Flux cell must be positive; capture height must be in (0,32000] cm")
    return centre, res.astype(int), cell, height


def build_capture_bed(manifest, domains, output):
    field = load_heightfield(manifest)
    if field.metadata.get("surface_interpolation") != "triangle_nw_se":
        raise ValueError("Flux capture requires the decoded runtime triangle_nw_se field")
    rectangles = []
    for domain in domains:
        centre, res, cell, _ = validate_domain(domain)
        half = res * cell / 200.0
        authored_centre = np.array([centre[0], -centre[1]]) / 100.0
        rectangles.append((authored_centre - half, authored_centre + half))
    if not rectangles:
        raise ValueError("At least one Flux domain is required")
    lo = np.min([r[0] for r in rectangles], axis=0)
    hi = np.max([r[1] for r in rectangles], axis=0)
    field_lo, field_hi = map(np.asarray, field.bounds_m)
    if np.any(lo < field_lo - 1e-6) or np.any(hi > field_hi + 1e-6):
        raise ValueError("Flux capture rectangle exceeds the runtime terrain; provide real terrain coverage")
    start = np.maximum(0, np.floor((lo-field_lo)/field.spacing_m).astype(int))
    end = np.minimum(np.array(field.dimensions)-1, np.ceil((hi-field_lo)/field.spacing_m).astype(int))
    xx = np.arange(start[0], end[0]+1)
    yy = np.arange(start[1], end[1]+1)
    x, y = np.meshgrid(field.origin_m[0]+xx*field.spacing_m[0],
                       field.origin_m[1]+yy*field.spacing_m[1])
    z = field.heights_m[np.ix_(yy, xx)]
    positions = np.stack((x*100, -y*100, z*100), axis=-1).reshape(-1, 3)
    h, w = z.shape
    a = (np.arange(h-1)[:, None]*w+np.arange(w-1)[None, :]).ravel()
    b, c, d = a+1, a+w, a+w+1
    # Authored NW->SE diagonal, reflected to Unreal Y. Both windings are
    # deliberate: the shipped capture culls one-sided beds in some setups.
    triangles = np.stack((np.stack((a,c,b),1), np.stack((d,b,c),1),
                          np.stack((a,b,c),1), np.stack((d,c,b),1)),1).reshape(-1,3)
    # Multiple rectangles need only their union, not the empty corners of the
    # enclosing box. Keep whole original cells intersecting a capture rectangle.
    if len(rectangles)>1:
        cell_x,cell_y=x[:-1,:-1],y[:-1,:-1]
        keep=np.zeros(cell_x.shape,dtype=bool)
        for lower,upper in rectangles:
            keep |= ((cell_x+field.spacing_m[0]>lower[0]-1e-8)&(cell_x<upper[0]+1e-8)
                     &(cell_y+field.spacing_m[1]>lower[1]-1e-8)&(cell_y<upper[1]+1e-8))
        triangles=triangles[np.repeat(keep.ravel(),4)]
        used=np.unique(triangles)
        remap=np.full(len(positions),-1,dtype=np.int64);remap[used]=np.arange(len(used))
        triangles=remap[triangles];positions=positions[used]
    document = {"item":"", "slots":[0], "names":["flux_runtime_bed"],
                "positions":positions.tolist(), "normals":[[0,0,1]]*len(positions),
                "indices":triangles.ravel().tolist(), "sections":[0]*len(triangles),
                "weight":[1.0]*len(positions), "nanite":False,
                "material":"/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial"}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
    receipt = {"schema":"mjolnir-flux-bed-v1", "terrain_manifest_sha256":field.manifest_sha256,
               "terrain_samples_sha256":field.metadata["height"]["sha256"],
               "capture_bed_sha256":sha256(output), "source_grid_rect":[start.tolist(),end.tolist()],
               "bounds_m":[[float(x.min()),float(y.min())],[float(x.max()),float(y.max())]],
               "vertices":len(positions), "triangles_double_sided":len(triangles),
               "source_vertex_error_m":float(np.max(np.abs(positions[:,2]/100-field.sample(positions[:,0]/100,-positions[:,1]/100)))),
               "surface_interpolation":"triangle_nw_se", "native_collision":False}
    output.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2)+"\n", encoding="utf-8")
    return receipt


def provenance(manifest, water_geometry, bed, domain, sources, simulation=None):
    field = load_heightfield(manifest)
    receipt = json.loads(Path(bed).with_suffix(".receipt.json").read_text(encoding="utf-8"))
    if receipt.get("terrain_manifest_sha256") != field.manifest_sha256 or receipt.get("capture_bed_sha256") != sha256(bed):
        raise ValueError("Flux bed is stale or modified; rebuild it for this terrain")
    validate_domain(domain)
    settings={"domain":domain,"sources":sources,"capture_policy":"explicit_bed_components_v1"}
    if simulation:settings["simulation"]=simulation
    return {"schema":PROVENANCE_SCHEMA, "terrain_manifest_sha256":field.manifest_sha256,
            "terrain_samples_sha256":field.metadata["height"]["sha256"],
            "water_geometry_sha256":sha256(water_geometry), "capture_bed_sha256":sha256(bed),
            "settings_sha256":stable_hash(settings)}


def state_matches(state, spec):
    """Strict for new terrain-backed states; preserves legacy domain-only bakes."""
    d = spec.get("domain", {})
    try:
        a, b = state["centre"], d["centre"]
        fits = (len(a)==len(b)==3 and all(np.isfinite(a)) and all(abs(x-y)<1 for x,y in zip(a,b))
                and state["res"]==d["res"] and state["cell"]==d["cell"] and state["height_cm"]==d["height"])
    except (KeyError, TypeError, ValueError):
        return False
    expected = spec.get("provenance")
    if expected is not None:
        capture=state.get("capture")
        if not isinstance(capture,(int,float)) or not np.isfinite(capture):
            return False
        for key in ("height","velocity","ground"):
            relative=state.get(key)
            if not isinstance(relative,str) or not relative.startswith("flux_state/") or ".." in relative or not relative.endswith(".exr"):
                return False
        fits = fits and expected.get("schema")==PROVENANCE_SCHEMA and all(
            isinstance(expected.get(k),str) and len(expected[k])==64
            and all(c in "0123456789abcdef" for c in expected[k]) for k in HASH_KEYS)
        fits = fits and state.get("provenance")==expected
        fits = fits and state.get("origin")==spec.get("origin", [0,0,0])
    return bool(fits)


def verify_state_files(root, state):
    """Validate real EXR dimensions and seal files before packaging a new bake."""
    root = Path(root).resolve()
    for key in ("height", "velocity", "ground"):
        relative = state.get(key, "")
        path = (root / relative).resolve()
        if not isinstance(relative,str) or not relative.startswith("flux_state/") or not path.is_relative_to(root / "flux_state"):
            raise ValueError("Flux state texture must be inside flux_state")
        raw = path.read_bytes()
        if len(raw)<16 or struct.unpack_from("<I",raw)[0]!=20000630:
            raise ValueError(f"Flux {key} is not an EXR")
        offset, dimensions = 8, None
        while offset < len(raw) and raw[offset]:
            stop=raw.index(0,offset); name=raw[offset:stop]; offset=stop+1
            stop=raw.index(0,offset); kind=raw[offset:stop]; offset=stop+1
            size=struct.unpack_from("<I",raw,offset)[0]; offset+=4
            if offset+size>len(raw): raise ValueError("Truncated Flux EXR header")
            if name==b"dataWindow" and kind==b"box2i" and size==16:
                x0,y0,x1,y1=struct.unpack_from("<4i",raw,offset)
                dimensions=[x1-x0+1,y1-y0+1]
            offset+=size
        if dimensions!=state.get("res"):
            raise ValueError(f"Flux {key} EXR dimensions do not match domain")
        digest=sha256(path)
        if state.get(key+"_sha256",digest)!=digest:
            raise ValueError(f"Flux {key} EXR changed after its bake was sealed")
        state[key+"_sha256"]=digest
    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heightfield", required=True)
    parser.add_argument("--spec", required=True, help="JSON with domain or domains[{domain}]")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    domains = [v["domain"] for v in spec["domains"]] if "domains" in spec else [spec["domain"]]
    print(json.dumps(build_capture_bed(args.heightfield, domains, args.out), indent=2))
