"""Audit the dry-forest split and every HISM against the .12 world and .13 recipe."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from prepare_forest_floor import OUT, STOCK
from verify_wind_grass import (
    native,
    package,
    matrices,
    number,
    identity_ancestors,
    get_payload,
    load_container,
)

OWNER = "PWR_DryForestFloor"


def order(m):
    return m[np.lexsort(tuple(m[:, 3, j] for j in (2, 1, 0)))]


def hash_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def audit(path, spec, baseline=False):
    doc = native.decode(path, native.GAME)
    raw = path.read_bytes()
    owners = {r["export"]: r for r in doc["exports"]}
    before = {}
    remaining = {}
    introduced = {}
    poserr = 0.0
    basiserr = 0.0
    wanted = {g["mesh"].split(".")[0]: (i, g) for i, g in enumerate(spec["groups"], 1)}
    for r in doc["exports"]:
        if r["class"] != "HierarchicalInstancedStaticMeshComponent":
            continue
        key = (r["outer"], r["name"])
        m = package(r, "StaticMesh")
        p = r["properties"]
        n = int(number(p["NumBuiltInstances"]))
        affine = native.native_matrices(raw, r, n)
        if r["outer"] == OWNER:
            assert not baseline and m in wanted
            i, g = wanted[m]
            assert r["name"] == "PWRFloor_" + g["key"] and n == g["count"]
            assert package(r, "OverrideMaterials[0]") == (
                "/Game/MJOLNIR/GrassPilot/Playable/" + g["material"]
                if g["material"]
                else None
            )
            assert (
                p.get("BodyInstance.CollisionProfileName") == "NoCollision"
                and p.get("bEvaluateWorldPositionOffset", "true") == "true"
            )
            assert [
                number(p.get(k))
                for k in ("InstanceStartCullDistance", "InstanceEndCullDistance")
            ] == g["cull"]
            identity_ancestors(r, owners)
            expected = matrices(OUT / f"floor.bin.xf{i}")
            delta = abs(order(affine) - order(expected))
            poserr = max(poserr, float(delta[:, 3, :3].max()))
            basiserr = max(basiserr, float(delta[:, :3, :3].max()))
            introduced[m] = n
        elif m == STOCK:
            g = next(g for g in spec["source"] if g["component"] == r["name"])
            assert n == g["original" if baseline else "survivors"]
            if not baseline:
                assert (
                    hash_bytes(order(affine).tobytes()) == g["retained_affine_sha256"]
                )
            remaining[r["name"]] = n
        else:
            before[key] = (
                m,
                n,
                hash_bytes(affine.tobytes()),
                r["references"].get("OverrideMaterials[0]"),
                p.get("InstanceStartCullDistance"),
                p.get("InstanceEndCullDistance"),
                p.get("bEvaluateWorldPositionOffset"),
            )
    assert poserr < 0.03 and basiserr < 2.0e-5
    assert len(remaining) == 2 and len(introduced) == (0 if baseline else 6)
    return before, dict(
        remaining=remaining,
        understory=introduced,
        position_error_cm=poserr,
        basis_error=basiserr,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", required=True, type=Path)
    args = parser.parse_args()
    dest = OUT / "cooked-proof"
    dest.mkdir(exist_ok=True)
    path = args.world
    if path.suffix == ".utoc":
        payload = get_payload(load_container(path), "/PWR/PWR.umap")
        path = dest / "PWR.umap"
        path.write_bytes(payload)
    spec = json.loads((OUT / "floor.json").read_text())
    old, prior = audit(OUT.parent / "native.12/LPE.umap", spec, True)
    new, report = audit(path, spec)
    assert old == new
    assert sum(prior["remaining"].values()) == sum(report["remaining"].values()) + sum(
        report["understory"].values()
    )
    report.update(
        preserved_other_components=len(old),
        baseline_pivots=spec["totals"]["original"],
        wetland_pivots_preserved=spec["totals"]["wet_retained"],
        source=str(args.world),
    )
    (dest / "verification.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
