"""Read back the changed Pelican Warfare headwater faces through both native physics trees."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from cook_headwater_collision import W, OUT, BASE, UNIT, collision_arrays, filehash


def main():
    out = OUT / "native/physics"
    receipt = json.loads((out / "native-collision-receipt.json").read_text())
    path = out / "pwr.sbsp"
    if filehash(path) != receipt["output_sha256"]:
        raise ValueError("BSP checkout is not the requested compile")
    manifest = json.loads((out / "collision_scene.json").read_text())
    original = np.memmap(BASE / "collision_scene.bin", dtype="u1", mode="r")
    new = np.memmap(out / "collision_scene.bin", dtype="u1", mode="r")
    a = collision_arrays(new, manifest)

    def view(raw, k, n, typ):
        offset, stride, count = a[k]
        return np.ndarray(
            (count, n), dtype=typ, buffer=raw, offset=offset, strides=(stride, 4)
        )

    vertices = view(new, "vertices", 3, "<f4")
    baseline = view(original, "vertices", 3, "<f4")
    edges = view(new, "edges", 6, "<i4")
    surfaces = view(new, "surfaces", 2, "<i4")
    e = surfaces[9:, 1]
    vi = np.column_stack((edges[e, 0], edges[e, 1], edges[edges[e, 2], 1]))
    changed = np.flatnonzero(np.any(vertices[vi] != baseline[vi], axis=(1, 2))) + 9
    instances = []
    scratch = out / "readback"
    scratch.mkdir(exist_ok=True)
    for p in receipt["pieces"]:
        span = p["source_surface_range"]
        if not span:
            continue
        choice = changed[(changed >= span[0]) & (changed < span[1])]
        if len(choice):
            instances.append((p, choice))

    def inspect(row):
        p, ids = row
        base = p["source_surface_range"][0]
        start, end = int(ids[0]) - base, int(ids[-1]) + 1 - base
        target = scratch / f"instance-{p['instance']}.f32"
        argv = [
            str(W / "target/release/examples/readback_surfaces.exe"),
            str(path),
            str(p["instance"]),
            str(start),
            str(end),
            str(target),
        ]
        process = subprocess.run(argv, capture_output=True)
        if process.returncode:
            raise RuntimeError((argv, process.stderr.decode(errors="replace")[-700:]))
        tri = (
            np.fromfile(target, dtype="<f4")
            .reshape(-1, 3, 3)[ids - base - start]
            .astype(float)
        )
        expected = vertices[vi[ids - 9]].astype(float)
        distances = [
            np.linalg.norm(tri - np.roll(expected, r, axis=1), axis=2).max(1)
            for r in range(3)
        ]
        maximum = float(np.min(distances, axis=0).max() * UNIT)
        if maximum > 0.003:
            raise ValueError((p["instance"], maximum))
        return {
            "instance": p["instance"],
            "verified_faces": len(ids),
            "read_range": [start, end],
            "max_error_m": maximum,
        }

    with ThreadPoolExecutor(max_workers=2) as pool:
        verified = list(pool.map(inspect, instances))
    if sum(v["verified_faces"] for v in verified) != len(changed):
        raise ValueError("Native instance ownership differs")
    summary = dict(
        compiled_bsp_sha256=receipt["output_sha256"],
        verified_changed_faces=len(changed),
        largest_vertex_error_m=max(v["max_error_m"] for v in verified),
        root_and_definition_havok_queries=True,
        instances=verified,
    )
    (out / "native-readback.json").write_text(json.dumps(summary, indent=2))
    print({k: v for k, v in summary.items() if k != "instances"})


if __name__ == "__main__":
    main()
