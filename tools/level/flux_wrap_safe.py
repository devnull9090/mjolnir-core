"""Make baked Fluid Flux states safe at their borders.

The loader imports each state's EXRs with KismetRenderingLibrary.ImportFileAsTexture2D,
whose textures sample with wrap addressing (and a runtime Texture2D cannot be switched
to clamp from script: the sampler only changes on UpdateResource). A surface vertex on
a domain's border therefore blends that edge's last texel with the OPPOSITE edge's
first. Where the far edge holds high ground (PWR: the river tile's north edge, ~107 m
dry fill over 130 m terrain, against its south edge at the river, ~88 m) the blend lifts
the surface into a curtain several metres above the water along the whole border.

Here the outermost `--band` texels on every side are rewritten as dry water tucked under
the lower terrain of the two opposite edges, so any wrap blend stays underground. Ground
is unchanged; depth, velocity and foam there are zeroed. Every map with baked Flux states
gets this from its level.json; the state's *_sha256 entries are updated in place.

    python flux_wrap_safe.py <map folder with level.json> [--band 2]

Packagers call make_level_safe(level.json, root) (upgrade_ce_map.flux_state, PWR's release stage).
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import OpenEXR

UNDER_M = 1.0   # how far under the lower edge's terrain the border water sits


def read(path):
    ch = OpenEXR.File(str(path)).channels()
    if "RGBA" in ch:
        return ch["RGBA"].pixels.astype(np.float32)
    return np.stack([ch[k].pixels for k in "RGBA"], axis=-1).astype(np.float32)


def write(path, rgba):
    half = np.ascontiguousarray(rgba, dtype=np.float16)
    if not np.isfinite(half).all():
        raise ValueError(f"Nonfinite state in {path}")
    OpenEXR.File({"compression": OpenEXR.ZIP_COMPRESSION, "type": OpenEXR.scanlineimage}, {"RGBA": half}).write(str(path))
    if not np.array_equal(read(path), half.astype(np.float32)):
        raise ValueError(f"EXR round trip failed at {path}")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def border_floor(terrain, band):
    """Per texel of each border band: the lower terrain of that band and its wrapped partner, minus UNDER_M."""
    rows = np.minimum(terrain[:band].min(0), terrain[-band:].min(0)) - UNDER_M       # per column
    cols = np.minimum(terrain[:, :band].min(1), terrain[:, -band:].min(1)) - UNDER_M  # per row
    return rows, cols


def make_safe(height, velocity, ground, state, band):
    # Encodings, as written by the bake tools: surface z cm = height + capture; terrain z cm = centre z - ground.
    terrain = (state["centre"][2] - ground[..., 0]) / 100.0
    rows, cols = border_floor(terrain, band)
    h, v = height.copy(), velocity.copy()
    for sl in (np.s_[:band], np.s_[-band:]):
        h[sl, :, 0] = h[sl, :, 1] = rows[None, :] * 100 - state["capture"]
        v[sl, :, :3] = 0
    h[:, :band, 0] = h[:, :band, 1] = cols[:, None] * 100 - state["capture"]
    h[:, -band:, 0] = h[:, -band:, 1] = cols[:, None] * 100 - state["capture"]
    # Corners belong to both bands: keep the lower of the two floors.
    for r in (np.s_[:band], np.s_[-band:]):
        for c in (np.s_[:band], np.s_[-band:]):
            low = np.minimum(rows[c][None, :], cols[r][:, None]) * 100 - state["capture"]
            h[r, c, 0] = h[r, c, 1] = low
    v[:, :band, :3] = 0
    v[:, -band:, :3] = 0
    return h, v, terrain


def wrap_blend_above_ground(height, terrain, state):
    """Largest height (m) a border vertex reaches above the terrain under it when blended with its wrap partner."""
    surf = (height[..., 0] + state["capture"]) / 100.0
    worst = 0.0
    for a, b in ((np.s_[-1], np.s_[0]), (np.s_[0], np.s_[-1])):
        blend = (surf[a] + surf[b]) / 2
        worst = max(worst, float((blend - terrain[a]).max()))
        blend = (surf[:, a] + surf[:, b]) / 2
        worst = max(worst, float((blend - terrain[:, a]).max()))
    return worst


def make_state_safe(root, st, band=2):
    """Rewrite one state's border bands in place; returns (changed file paths relative to root, report)."""
    root = Path(root)
    height, velocity, ground = (read(root / st[k]) for k in ("height", "velocity", "ground"))
    terrain = (st["centre"][2] - ground[..., 0]) / 100.0
    before = wrap_blend_above_ground(height, terrain, st)
    h, v, _ = make_safe(height, velocity, ground, st, band)
    after = wrap_blend_above_ground(h, terrain, st)
    if after > 0:
        raise ValueError(f"A Flux border still blends {after:.2f} m above ground")
    changed = []
    for key, arr, old in (("height", h, height), ("velocity", v, velocity)):
        if not np.array_equal(arr.astype(np.float16), old.astype(np.float16)):
            write(root / st[key], arr)
            changed.append(st[key])
        st[key + "_sha256"] = sha(root / st[key])
    st["wrap_safe_band"] = band
    # The state's own copy beside its textures carries the same hashes.
    own = (root / st["height"]).parent / "state.json"
    if own.is_file():
        mine = json.loads(own.read_text())
        mine.update({k: st[k] for k in ("height_sha256", "velocity_sha256", "wrap_safe_band")})
        own.write_text(json.dumps(mine, indent=2) + "\n")
        changed.append(own.relative_to(root).as_posix())
    return changed, dict(border_blend_above_ground_m=dict(before=round(before, 2), after=round(after, 2)))


def make_level_safe(level_path, root, band=2):
    """Every baked state of a level.json; rewrites level.json. Returns changed paths (relative to root, plus the level)."""
    level_path = Path(level_path)
    level = json.loads(level_path.read_text())
    changed, report = [], []
    for d in (level.get("flux") or {}).get("domains", []):
        if d.get("state"):
            files, row = make_state_safe(root, d["state"], band)
            changed += files
            report.append(dict(row, domain=d.get("id")))
    if report:
        level_path.write_text(json.dumps(level, indent=2))
    return changed, report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path, help="map folder: level.json beside flux_state/")
    ap.add_argument("--band", type=int, default=2)
    a = ap.parse_args()
    changed, report = make_level_safe(a.folder / "level.json", a.folder, a.band)
    print(json.dumps(dict(report=report, changed=changed)))


if __name__ == "__main__":
    main()
