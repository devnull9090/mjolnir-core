"""Re-species PWR's converted CE groundcover (MJOLNIR_Foliage) in place, at the same positions.

The 612k shipped groundcover instances (GroundcoverClump, Sedges_A_Leaves_C, Tall_Grass) carry the
whole meadow look: one green clump and one dark drooping sedge everywhere. Their positions are already
validated natural ground (no paving, roads, water or obstacles), so this pass keeps every position
and decides per instance, from the meadow-life zones and noise fields, what grows there: dry and dead
grass, straw, wildflower drifts, seed weeds and ferns, or the original clump; some drop out. The total
can only shrink, so it costs no more than .43 to draw.

  python meadow_remix.py <groundcover-export> <out>
The export comes from unreal/MJOLNIRMaterials/Scripts/export_pwr_groundcover.py. The output is a
meadow-life group set (owner PWR_MeadowRemix) plus clear.json, the MJOLNIR_Foliage components the
apply step empties before baking.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from build_sweep_banks import pack_groups
from meadow_life import KINDS, ROOT, noise
from prepare_alpine_verges import Site, sha256

sys.path.insert(0, str(ROOT / "tools/level"))
from foliage_bake import PAKS, mesh_info

SEED = 26112003
OWNER = "PWR_MeadowRemix"
GC = "SM_Grass_GroundcoverClump_A"
SEDGE = "SM_Grass_Sedges_A_Leaves_C"
TALL = "SM_Tall_Grass_rbeki_01"
# PWR_WindMeadow's tussocks (wild grass and canyon rye) dominate the base shoulders: keep one in ten
# at 40% scale (KEEP_SCALE), turn about half into fine fescue, drop the rest.
WIND = {"SM_Grass_CanyonPrinceWildRye", "S_Wild_Grass_vlkhcbxia_0_Var1_lod0", "S_Wild_Grass_vlkhcbxia_0_Var12_lod0",
        "S_Wild_Grass_vlkhcbxia_0_Var16_lod0"}
WIND_RECIPE = [("keep", 10), ("fescue", 45), ("meadowgrass", 5), (None, 40)]
KEEP_SCALE = {leaf: 0.4 for leaf in WIND}
EXTRA = {"meadowgrass": (["/Game/Megascans/3D_Plants/Wild_Grass_vlkhcbxia/S_Wild_Grass_vlkhcbxia_0_Var12_lod0."
                          "S_Wild_Grass_vlkhcbxia_0_Var12_lod0"], (4500, 7000), 34, 3000, (0.8, 1.15), False),
         # The map's own fine fescue blades (map-owned, real editor assets).
         "fescue": (["/Game/MJOLNIR/GrassPilot/Playable/SM_PWR_FineFescue_A.SM_PWR_FineFescue_A",
                     "/Game/MJOLNIR/GrassPilot/Playable/SM_PWR_FineFescue_B.SM_PWR_FineFescue_B"], (2500, 4500), 34, 2500, (0.8, 1.2), False)}


def table(rows):
    """[(kind or 'keep' or None, weight)] -> (names, cumulative probabilities)."""
    names = [k for k, _ in rows]
    w = np.array([v for _, v in rows], float)
    return names, np.cumsum(w / w.sum())


# Recipes per source mesh and zone. None drops the instance.
RECIPES = {
    SEDGE: {"forest": [("fern", 30), ("ladyfern", 15), ("litter", 25), (None, 30)],
            "dry": [("drygrass", 30), ("straw", 45), ("myricaria", 5), (None, 20)],
            "bloom": [("windflower", 20), ("meadowgrass", 30), ("straw", 25), (None, 25)],
            "plain": [("straw", 35), ("meadowgrass", 30), ("seedweed", 3), (None, 32)]},
    GC: {"forest": [("fern", 25), ("litter", 25), ("fescue", 10), (None, 40)],
         "dry": [("fescue", 30), ("drygrass", 12), ("straw", 25), (None, 33)],
         "bloom": [("fescue", 30), ("windflower", 22), ("periwinkle", 8), ("seedweed", 4), (None, 36)],
         "plain": [("fescue", 45), ("meadowgrass", 15), ("straw", 10), (None, 30)]},
    TALL: {"forest": [("keep", 40), ("fern", 30), (None, 30)],
           "dry": [("keep", 30), ("drygrass", 55), (None, 15)],
           "bloom": [("keep", 55), ("windflower", 20), (None, 25)],
           "plain": [("keep", 60), ("drygrass", 20), (None, 20)]},
}


for _leaf in WIND:
    RECIPES[_leaf] = {z: WIND_RECIPE for z in ("forest", "dry", "bloom", "plain")}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("export", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--actor", default="MJOLNIR_Foliage", help="the source actor the export came from")
    ap.add_argument("--owner", default=OWNER, help="the actor the replacement groups bake under")
    a = ap.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    kinds = dict(KINDS, **EXTRA)
    rng = np.random.default_rng(SEED)
    site = Site()
    comps = json.loads((a.export / "components.json").read_text())
    clear, rows, keep_by_component = [], {}, {}
    for c in comps:
        leaf = c["mesh"].rsplit("/", 1)[-1].split(".")[0]
        if leaf not in RECIPES:
            continue
        clear.append(c["component"])
        xf = np.fromfile(a.export / f"{c['index']}.xf", "<f4").reshape(-1, 10)
        if not len(xf):
            continue
        xy = xf[:, :2] * [0.01, -0.01]
        d = site.trunks.query(xy, workers=-1)[0]
        x, y = xy.T
        dry = noise(x, y, 41, 57, 0.4)
        bloom = noise(x + 300, y - 120, 17, 23, 1.9)
        zone = np.select([d < 9, dry > 0.56, bloom > 0.62], ["forest", "dry", "bloom"], default="plain")
        draw = rng.random(len(xf))
        for z in ("forest", "dry", "bloom", "plain"):
            names, cum = table(RECIPES[leaf][z])
            sel = zone == z
            pick = np.searchsorted(cum, draw[sel])
            for kind_i, name in enumerate(names):
                if name is None:
                    continue
                t = xf[sel][pick == kind_i].copy()
                if not len(t):
                    continue
                if name == "keep":
                    # Kept clumps go back into the very component they came from: its material,
                    # cull bands and shading stay exactly as shipped (optionally smaller).
                    t[:, 7:10] *= KEEP_SCALE.get(leaf, 1.0)
                    keep_by_component.setdefault(c["component"], []).append(t)
                    continue
                variants, cull, flags, wpo, (s0, s1), tall = kinds[name]
                v = rng.integers(0, len(variants), len(t))
                s = rng.uniform(s0, s1, len(t)).astype("<f4")
                t[:, 7:10] = s[:, None]
                t[:, 2] -= 1.0
                for vi, mesh in enumerate(variants):
                    if (v == vi).any():
                        rows.setdefault(mesh, (name, []))[1].append(t[v == vi])
    cli = str(ROOT / "target/release/mjolnir.exe")
    entries = []
    for mesh, (name, parts) in sorted(rows.items()):
        data = np.concatenate(parts).astype("<f4")
        info = (dict(origin=[0, 0, 0], extent=[100, 100, 100], slots=["Slot0"]) if mesh.startswith("/Game/MJOLNIR/")
                else mesh_info(cli, PAKS, mesh))
        variants, cull, flags, wpo, _, _ = kinds[name]
        definition = dict(key=f"{name}{variants.index(mesh) + 1}", mesh=mesh, cull=list(cull), flags=flags, wpo=wpo)
        definition.update(material=None, origin=info["origin"], extent=info["extent"], standin_slots=info["slots"])
        entries.append((definition, data))
    pack_groups(out, a.owner, entries)
    keep = {}
    for i, (component, parts) in enumerate(sorted(keep_by_component.items())):
        data = np.concatenate(parts).astype("<f4")
        data.tofile(out / f"keep{i}.xf")
        keep[component] = dict(file=f"keep{i}.xf", count=len(data), sha256=sha256(out / f"keep{i}.xf"))
    (out / "keep.json").write_text(json.dumps(keep, indent=1))
    total_in = sum(c["count"] for c in comps if c["component"] in clear)
    total_out = sum(len(r) for _, r in entries) + sum(k["count"] for k in keep.values())
    (out / "clear.json").write_text(json.dumps(dict(actor=a.actor, components=clear, instances=total_in), indent=1))
    (out / "survey.json").write_text(json.dumps(dict(actor=a.owner, seed=SEED, source=str(a.export), cleared=total_in,
                                                     planted=total_out, groups={d["key"]: len(r) for d, r in entries},
                                                     verges_sha256=sha256(out / "verges.json")), indent=1))
    print(f"remixed {total_in} groundcover instances into {total_out} in {len(entries)} groups:",
          {d["key"]: len(r) for d, r in entries})


if __name__ == "__main__":
    main()
