"""Extract the actual .8 court art and the Havok base/ground witness triangles."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from base_approach_paths import ROOT, OUT

sys.path.insert(0, str(ROOT / "tools/iostore"))
from iostore import load_container, read_chunk

BASELINE = ROOT / "out/pwr/landscape-distance/saturday.8"
MAP = BASELINE / "map-input"
PRIVATE = ROOT / "out/pwr/playtest-20261121/rehearsal-game/Meteorite/Content/Paks"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def execute(args, log):
    proc = subprocess.run(
        list(map(str, args)), cwd=ROOT, capture_output=True, text=True
    )
    log.write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if proc.returncode or "MISMATCH" in proc.stdout + proc.stderr:
        raise ValueError(str(log) + " " + (proc.stdout + proc.stderr)[-1000:])
    return proc.stdout + proc.stderr


def link(source, target):
    if not target.exists():
        os.link(source, target)
    if not source.samefile(target):
        raise ValueError("Unexpected file at " + str(target))


def witnesses():
    here = OUT / "witnesses"
    here.mkdir(exist_ok=True, parents=True)
    audited = here / "isolated-input"
    audited.mkdir(exist_ok=True)
    release = json.loads((BASELINE / "receipt.json").read_text())
    for p in [*PRIVATE.glob("global.u*"), *MAP.glob("pakchunk955-*.u*")]:
        link(p, audited / p.name)
    cli = ROOT / "target/release/mjolnir.exe"
    for team in ("red", "blue", "green"):
        leaf = "SM_PWR_" + team + "_court"
        execute(
            [
                cli,
                "mesh",
                "export",
                "--paks",
                audited,
                "--asset",
                leaf,
                "--out",
                here / (leaf + ".glb"),
            ],
            here / (leaf + ".log"),
        )
    # Decode the exact shipped scenario_structure_bsp body. This includes the
    # downstream landscape bake's shell landing adjustment, unlike the source BSP.
    world = load_container(next(MAP.glob("pakchunk997*.utoc")))
    (key,) = [
        k
        for k in world.files
        if k.lower().endswith("bsp_01_1_start-scenario_structure_bsp.ubulk")
    ]
    body = read_chunk(world, world.chunks[world.files[key]])
    sbsp = here / "pwr.shipped.sbsp"
    sbsp.write_bytes(body)
    ref = ROOT / "out/pwr/base-polish/rear-gate/physics"
    old = np.fromfile(ref / "pwr.sbsp", dtype=np.uint8)
    delta = np.flatnonzero(old != np.frombuffer(body, dtype=np.uint8))
    if (
        not 1 <= len(delta) <= 16
        or sha(ref / "pwr.sbsp") != release["collision"]["sbsp"]
    ):
        raise ValueError("Cannot connect baked collision to the sealed wide-gate BSP")
    pieces = json.loads((ref / "native-collision-receipt.json").read_text())["pieces"]
    reader = ROOT / "target/release/examples/readback_surfaces.exe"
    selected = []
    for piece in pieces:
        span = piece["source_surface_range"]
        # The appended authoritative landscape and architectures share the last
        # 24 pieces. Earlier scenery duplicates do not describe the main floor.
        if not span or piece["instance"] < 126:
            continue
        path = here / ("piece-%s.f32" % piece["instance"])
        execute(
            [reader, sbsp, piece["instance"], 0, span[1] - span[0], path],
            path.with_suffix(".log"),
        )
        selected.append(path)
    allpts = (
        np.vstack([np.fromfile(p, dtype="<f4").reshape(-1, 3, 3) for p in selected])
        * 3.048
    )
    np.save(here / "base-collision-triangles.npy", allpts)
    report = {
        "baseline_map_receipt_sha256": sha(BASELINE / "receipt.json"),
        "world_utoc_sha256": sha(next(MAP.glob("pakchunk997*.utoc"))),
        "native_source_member": key,
        "shipped_bsp_sha256": sha(sbsp),
        "wide_gate_bsp_sha256": sha(ref / "pwr.sbsp"),
        "shell_adjusted_byte_offsets": delta.tolist(),
        "decoded_base_faces": len(allpts),
        "pieces": [p.name for p in selected],
        "court_exports": {p.name: sha(p) for p in here.glob("*.glb")},
    }
    (here / "source.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    print(witnesses())
