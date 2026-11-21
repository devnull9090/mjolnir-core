"""Compare inherited and rebuilt BSP vertices along every cut edge, in actual native coordinates."""

import json
import numpy as np
import cook_headwater_collision as c


def perimeter(tri):
    # Match native floats before converting to metres to avoid approximate XY bins.
    xy, ids = np.unique(tri[:, :, :2].reshape(-1, 2), axis=0, return_inverse=True)
    faces = ids.reshape(-1, 3)
    edges, counts = np.unique(
        np.sort(faces[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1),
        axis=0,
        return_counts=True,
    )
    vertices = np.unique(edges[counts == 1])
    height = np.empty(len(xy))
    height[ids.ravel()] = tri[:, :, 2].ravel()
    border = edges[counts == 1]
    return {tuple(xy[i]): height[i] for i in vertices}, np.searchsorted(
        vertices, border
    )


def main():
    base = c.W / "out/pwr/river-apron/native/physics"
    out = c.OUT / "native/physics"
    manifest = json.loads((out / "collision_scene.json").read_text())
    previous = json.loads(
        (c.W / "out/pwr/river-apron/native/landscape-collision.json").read_text()
    )
    if c.filehash(base / "pwr.sbsp") != previous["sbsp"]:
        raise ValueError("Wrong parent collider")
    old = np.memmap(base / "collision_scene.bin", "u1", "r")
    new = np.memmap(out / "collision_scene.bin", "u1", "r")
    layout = c.collision_arrays(new, manifest)
    first = json.loads(c.PLAN.read_text())["provenance"]["terrain_source_first"]

    def view(raw, name, type, n):
        offset, stride, count = layout[name]
        return np.ndarray(
            (count, n), dtype=type, buffer=raw, offset=offset, strides=(stride, 4)
        )

    surfs = view(new, "surfaces", "<i4", 2)
    edges = view(new, "edges", "<i4", 6)
    vi = np.column_stack(
        (edges[surfs[:, 1], 0], edges[surfs[:, 1], 1], edges[edges[surfs[:, 1], 2], 1])
    )
    previous_points = view(old, "vertices", "<f4", 3)
    current_points = view(new, "vertices", "<f4", 3)
    changed = np.load(out / "terrain-replacement.npz")["source_indices"]
    inherited = np.load(base / "terrain-replacement.npz")["source_indices"]
    retained = np.setdiff1d(inherited, changed)
    if not np.array_equal(
        previous_points[vi[retained + first]], current_points[vi[retained + first]]
    ):
        raise ValueError("Inherited terrain coordinates altered")
    indices = vi[first + changed]
    previous_ring, previous_edges = perimeter(previous_points[indices])
    new_ring, new_edges = perimeter(current_points[indices])
    # Surface authoring quantizes the intersected perimeter to 10 micrometres before triangulation.
    from scipy.spatial import cKDTree

    old_xy = np.array(list(previous_ring))
    new_xy = np.array(list(new_ring))
    xyerr, idx = cKDTree(old_xy).query(new_xy)
    if (
        len(old_xy) != len(new_xy)
        or len(np.unique(idx)) != len(idx)
        or max(xyerr) * c.UNIT > 0.00025
    ):
        raise ValueError(
            ("Basin edge mismatch", len(old_xy), len(new_xy), max(xyerr) * c.UNIT)
        )
    old_edges = {tuple(e) for e in np.sort(previous_edges, axis=1)}
    mapped_edges = {tuple(e) for e in np.sort(idx[new_edges], axis=1)}
    if mapped_edges != old_edges:
        raise ValueError("Basin boundary topology differs from its adjoining terrain")
    dz = (
        np.abs(
            np.array(list(previous_ring.values()))[idx]
            - np.array(list(new_ring.values()))
        )
        * c.UNIT
    )
    if max(dz) > 0.0001:
        raise ValueError(("Native perimeter elevations disagree", max(dz)))
    proof = dict(
        vertices_before=len(old_xy),
        vertices_after=len(new_xy),
        same_perimeter=True,
        matching_perimeter_edges=len(old_edges),
        worst_vertical_join_m=float(max(dz)),
        count_join_larger_than_2cm=int(np.count_nonzero(dz > 0.02)),
        native_perimeter_vertices=len(dz),
        max_vertical_join_m=float(max(dz)),
        max_horizontal_join_m=float(max(xyerr) * c.UNIT),
        preserved_terrain_faces=len(retained),
        preserved_terrain_vertices_byte_identical=True,
    )
    (out / "seam-survey.json").write_text(json.dumps(proof, indent=2))
    print(proof)


if __name__ == "__main__":
    main()
