"""Split a packaged distant apron into angular sectors the engine can cull.

The apron (package_apron.py) is one render-only mesh ringing the whole map:
3.24M triangles in one section. Its bounds always hold the camera, so the
engine draws every triangle every frame, behind the player and under the
floor included. On a GTX 1080 Ti that was 0.9-1.6 ms of GPU whichever way
the camera faced (docs/performance.md, 2026-11-26). Cut into sectors, each
its own mesh and its own bounds, the engine frustum-culls the sectors out of
view. The triangles are the apron's own, untouched: same vertices, normals
and UVs, so the joins are exact and the look is the same.

Reads a finished apron directory (apron.gltf/.bin, receipt.json,
runtime_decor.json), checks the geometry against its receipt, and writes to
--out: one glTF and one cooked mesh per sector (mesh_rewrite, the apron's own
donor and material slot), one container holding them all (package_add), and
runtime_decor.json with a row per sector. The first row keeps the apron's id
(`pwr_distant_apron`), which other tools look the material up by.

    python split_apron.py --apron-dir <out/pwr/vista/apron-v9b> --out <dir> [--sectors 12]
"""
import argparse
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
PAKS = Path("C:/Program Files (x86)/Steam/steamapps/common/Halo Campaign Evolved/Meteorite/Content/Paks")
STEM = "pakchunk963-MJOLNIRPWRVISTA_P"
TOOLS = REPO / "target/release/examples"  # cargo build --release -p ue-asset --example mesh_rewrite; -p blam-pack --example package_add


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load(apron):
    gltf = json.loads((apron / "apron.gltf").read_text(encoding="utf-8"))
    raw = (apron / "apron.bin").read_bytes()
    views, acc = gltf["bufferViews"], gltf["accessors"]
    prim = gltf["meshes"][0]["primitives"][0]

    def read(index, dtype, width):
        a, v = acc[index], views[acc[index]["bufferView"]]
        start = v.get("byteOffset", 0) + a.get("byteOffset", 0)
        out = np.frombuffer(raw, dtype=dtype, count=a["count"] * width, offset=start)
        return out.reshape(a["count"], width) if width > 1 else out

    at = prim["attributes"]
    return gltf, {
        "POSITION": read(at["POSITION"], np.float32, 3),
        "NORMAL": read(at["NORMAL"], np.float32, 3),
        "TEXCOORD_0": read(at["TEXCOORD_0"], np.float32, 2),
    }, read(prim["indices"], np.uint32, 1).reshape(-1, 3)


def sector_of(attrs, tris, count):
    """Each triangle's sector by its centroid's angle about the ring's axis
    (glTF Y is up), cut at equal triangle counts so no sector is heavy."""
    p = attrs["POSITION"]
    c = (p[tris[:, 0]] + p[tris[:, 1]] + p[tris[:, 2]]) / 3.0
    angle = np.arctan2(c[:, 2], c[:, 0])
    cuts = np.quantile(angle, np.linspace(0, 1, count + 1)[1:-1])
    return np.searchsorted(cuts, angle, side="right"), cuts


def write_sector(gltf, attrs, tris, path):
    used, local = np.unique(tris, return_inverse=True)
    local = local.reshape(-1, 3).astype(np.uint32)
    parts, views, accessors = [], [], []
    offset = 0
    for name, width in (("POSITION", 3), ("NORMAL", 3), ("TEXCOORD_0", 2)):
        data = np.ascontiguousarray(attrs[name][used], dtype=np.float32)
        acc = {"bufferView": len(views), "componentType": 5126, "count": len(used),
               "type": "VEC%d" % width}
        if name == "POSITION":
            acc["min"], acc["max"] = data.min(0).tolist(), data.max(0).tolist()
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": data.nbytes})
        accessors.append(acc)
        parts.append(data.tobytes())
        offset += data.nbytes
    idx = np.ascontiguousarray(local.reshape(-1))
    views.append({"buffer": 0, "byteOffset": offset, "byteLength": idx.nbytes})
    accessors.append({"bufferView": len(views) - 1, "componentType": 5125, "count": len(idx), "type": "SCALAR"})
    parts.append(idx.tobytes())
    out = copy.deepcopy({k: v for k, v in gltf.items() if k not in ("accessors", "bufferViews", "buffers")})
    out["asset"]["generator"] = gltf["asset"].get("generator", "") + " / split_apron sector"
    out["accessors"], out["bufferViews"] = accessors, views
    out["buffers"] = [{"uri": path.stem + ".bin", "byteLength": offset + idx.nbytes}]
    (path.parent / (path.stem + ".bin")).write_bytes(b"".join(parts))
    path.write_text(json.dumps(out), encoding="utf-8")
    return len(used), len(idx) // 3


def run(args, log):
    result = subprocess.run([str(a) for a in args], cwd=REPO, capture_output=True, text=True)
    text = result.stdout + result.stderr
    log.write_text(text, encoding="utf-8")
    if result.returncode or "MISMATCH" in text:
        raise RuntimeError(f"{args[0]} failed: {text[-2000:]}")
    return text


def split(apron, out, count):
    receipt = json.loads((apron / "receipt.json").read_text(encoding="utf-8"))
    for suffix in ("gltf", "bin"):
        if digest(apron / ("apron." + suffix)) != receipt[suffix + "_sha256"]:
            raise ValueError("apron geometry differs from its receipt")
    decor = json.loads((apron / "runtime_decor.json").read_text(encoding="utf-8"))
    (base,) = [row for row in decor["decor"] if row["id"] == "pwr_distant_apron"]
    package = base["mesh"].split(".")[0]
    material = base["materials"][0]["parent"].split(".")[0]
    gltf, attrs, tris = load(apron)
    which, cuts = sector_of(attrs, tris, count)
    out.mkdir(parents=True, exist_ok=True)
    rows, packages, sectors = [], [], []
    for k in range(count):
        name = f"{package}_S{k:02d}"
        work = out / f"s{k:02d}"
        work.mkdir(exist_ok=True)
        verts, ntris = write_sector(gltf, attrs, tris[which == k], work / "apron.gltf")
        uasset = work / (name.rsplit("/", 1)[-1] + ".uasset")
        log = run([TOOLS / "mesh_rewrite.exe", PAKS, "basicshapes/cylinder", work / "apron.gltf", uasset,
                   "--offset", "0,0,0", "--rename", name, "--material", f"DistantGranite={material}=*",
                   "--asset-imports", "--selftest"], work / "mesh.log")
        m = re.search(r"SPAWN: location \(([-\d.]+), ([-\d.]+), ([-\d.]+)\) cm, uniform scale ([\d.]+)", log)
        if not m:
            raise RuntimeError(f"sector {k}: mesh_rewrite printed no spawn transform")
        x, y, z, scale = map(float, m.groups())
        row = copy.deepcopy(base)
        row["id"] = "pwr_distant_apron" if k == 0 else f"pwr_distant_apron_s{k:02d}"
        row["mesh"] = f"{name}.{name.rsplit('/', 1)[-1]}"
        row["pos"], row["scale"] = [x, y, z], [scale] * 3
        rows.append(row)
        packages += ["--package", f"{name}={uasset}"]
        sectors.append({"sector": k, "vertices": verts, "triangles": ntris, "pos": [x, y, z], "scale": scale})
        print(f"sector {k:2d}: {ntris:8d} triangles, {verts:8d} vertices, at ({x:.0f}, {y:.0f}, {z:.0f}) x{scale:.1f}")
    run([TOOLS / "package_add.exe", PAKS, out, "--name", STEM] + packages, out / "package.log")
    # The container's .pak is the game's empty one, as package_apron copies it.
    (out / (STEM + ".pak")).write_bytes((apron / (STEM + ".pak")).read_bytes())
    others = [row for row in decor["decor"] if row["id"] != "pwr_distant_apron"]
    (out / "runtime_decor.json").write_text(json.dumps(dict(decor, decor=rows + others), indent=2), encoding="utf-8")
    total = sum(s["triangles"] for s in sectors)
    if total != len(tris):
        raise RuntimeError(f"sectors hold {total} triangles, the apron {len(tris)}")
    (out / "split.receipt.json").write_text(json.dumps({
        "schema": "mjolnir-apron-split-v1", "source": str(apron), "source_gltf_sha256": receipt["gltf_sha256"],
        "source_bin_sha256": receipt["bin_sha256"], "sectors": sectors,
        "cuts_radians": [float(c) for c in cuts], "container": str(out / STEM),
        "files": {s: digest(out / (STEM + s)) for s in (".utoc", ".ucas", ".pak")}}, indent=2), encoding="utf-8")
    print(f"{count} sectors, {total} triangles, container {out / STEM}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apron-dir", type=Path, required=True, help="a finished package_apron.py directory")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sectors", type=int, default=12)
    parser.add_argument("--tools", type=Path, help="folder holding mesh_rewrite.exe and package_add.exe (default target/release/examples)")
    a = parser.parse_args()
    if a.sectors < 2:
        raise SystemExit("--sectors must be at least 2")
    if a.tools:
        TOOLS = a.tools.resolve()
    split(a.apron_dir.resolve(), a.out.resolve(), a.sectors)
