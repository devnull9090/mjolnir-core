"""Re-skin a level's Forerunner ground with the Forerunner floor master (pwr_forerunner_floor.py).

Every decor slot drawn through the flat paving master (M_CE_PWRPaving) moves to M_PWR_FRFloor,
keeping its tint (its place in the design: plate, joint, trim, accent) and its plate layout; base
court meshes whose slots are named `court` / `recess` (bases_v1 runtime_visuals) get the floor and
its dark trim; the bare-rock ground between them becomes mossy tundra ground. Slot names come from the cooked meshes (mjolnir ue get), so any map whose decor
carries these meshes or bindings gets the same treatment.

    python forerunner_surfaces.py <level.json> [--paks <copy's Paks>] [--check]
"""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FLOOR = "/Game/MJOLNIR/GrassPilot/Playable/M_PWR_FRFloor.M_PWR_FRFloor"
PAVING = "M_CE_PWRPaving"
# Court plates read as polished Forerunner alloy; the recess as the darker frame metal around them.
ROLES = {
    "court": dict(FloorTint=[0.27, 0.29, 0.31, 1], FloorScale=[560, 2600, 900, 7000],
                  FloorFinish=[0.45, 0.7, 0.35, 0.6], FloorLayout=[1600, 800, 5, 0.5], FloorAxis=[0, 0, 0, 0]),
    "recess": dict(FloorTint=[0.11, 0.12, 0.13, 1], FloorScale=[300, 2000, 700, 6000],
                   FloorFinish=[0.25, 0.55, 0.9, 0.45], FloorLayout=[1600, 800, 4, 0], FloorAxis=[0, 0, 0, 0]),
}


MS = "/Game/Megascans/Surfaces/"
# Ground between the courts: the bare Jagged Rock scan read as gravel poured into polygons. Mossy tundra
# ground with stones belongs to the alpine meadow outside, so the beds read as planted ground.
GROUND = {
    "Rock_Jagged_udemcebew": dict(textures={
        "RockD": MS + "Tundra_mossy_ground_vjulbjjr/T_Tundra_mossy_ground_vjulbjjr_NSVT_D.T_Tundra_mossy_ground_vjulbjjr_NSVT_D",
        "RockN": MS + "Tundra_mossy_ground_vjulbjjr/T_Tundra_mossy_ground_vjulbjjr_NSVT_N.T_Tundra_mossy_ground_vjulbjjr_NSVT_N"},
        vectors={"RockTint": [0.92, 0.98, 0.9, 1], "RockParams": [320, 0.9, 0.55, 0]}),
}


def from_ground(m):
    tex = " ".join((m.get("textures") or {}).values())
    for key, swap in GROUND.items():
        if key in tex:
            out = json.loads(json.dumps(m))
            out["textures"] = dict(out.get("textures") or {}, **swap["textures"])
            out["vectors"] = dict(out.get("vectors") or {}, **swap["vectors"])
            return out
    return None


def toned(role, k):
    v = {key: list(val) for key, val in ROLES[role].items()}
    v["FloorTint"] = [c * k for c in v["FloorTint"][:3]] + [1]
    # The role rides along (the loader reads only parent/vectors/textures/scalars) so a later run re-tunes it.
    return {"parent": FLOOR, "vectors": v, "forerunner_role": [role, k]}


# Exterior floor slots of architecture meshes (bases_v1 runtime_visuals): only these are re-skinned,
# every other slot (walls, ramps, interiors, trim, lights) keeps the mesh's own material ("" = leave alone).
FLOOR_SLOTS = {"apron_finish_v0": ("court", 0.94), "apron_finish_v1": ("court", 1.0), "apron_finish_v2": ("court", 1.06),
               "floor": ("court", 1.0), "dark_floor": ("recess", 1.0)}


def from_paving(m):
    """A paving binding as a floor binding: same tint family, a touch brighter (the metal is now reflective)."""
    v = m.get("vectors", {})
    tint = v.get("PavingTint", [0.27, 0.29, 0.29, 1])
    layout = v.get("PavingLayout", [1600, 800, 3, 0])
    lum = 0.2126 * tint[0] + 0.7152 * tint[1] + 0.0722 * tint[2]
    joint = lum < 0.12                       # the dark joint/frame bands of a design
    out = dict(ROLES["recess" if joint else "court"])
    out = {k: list(val) for k, val in out.items()}
    out["FloorTint"] = [min(1.0, c * (1.0 if joint else 1.06)) for c in tint[:3]] + [1]
    out["FloorLayout"] = [max(layout[0], 400), max(layout[1], 400), max(layout[2], 2), 0.55 if layout[3] > 0 and not joint else 0]
    # The original paving binding rides along, so a later run recomputes from it.
    return {"parent": FLOOR, "vectors": out, "forerunner_paving": m.get("forerunner_paving") if isinstance(m.get("forerunner_paving"), dict) else m}


def slot_names(cli, paks, mesh, cache):
    pkg = mesh.split(".", 1)[0]
    if pkg in cache:
        return cache[pkg]
    names = []
    env = dict(os.environ, MSYS2_ARG_CONV_EXCL="*")
    listing = subprocess.run([cli, "ue", "get", "--paks", paks, "--package", pkg], capture_output=True, text=True, env=env).stdout
    idx = next((m.group(1) for m in re.finditer(r"export (\d+): \S+ : StaticMesh\b", listing)), None)
    if idx is not None:
        rows = subprocess.run([cli, "ue", "get", "--paks", paks, "--package", pkg, "--export", idx],
                              capture_output=True, text=True, env=env).stdout
        found = {}
        for line in rows.splitlines():
            m = re.match(r"\s*StaticMaterials\[(\d+)\]\.MaterialSlotName = (\S+)", line)
            if m:
                found[int(m.group(1))] = m.group(2)
        names = [found[i] for i in sorted(found)]
    cache[pkg] = names
    return names


def reskin(level, cli, paks):
    cache, report = {}, []
    for d in level.get("decor", []):
        mats = d.get("materials")
        changed = 0
        if mats:
            # Ground swaps belong to base site finishes only: decor that also lays Forerunner paving.
            # (The same rock scan is the map's cliff material everywhere else.)
            site = any(isinstance(m, dict) and (PAVING in m.get("parent", "") or m.get("forerunner_paving")) for m in mats)
            for i, m in enumerate(mats):
                if isinstance(m, dict) and m.get("forerunner_role") and m["forerunner_role"][0] in ROLES:
                    mats[i] = toned(*m["forerunner_role"]); changed += 1
                elif isinstance(m, dict) and isinstance(m.get("forerunner_paving"), dict):
                    mats[i] = from_paving(m["forerunner_paving"]); changed += 1
                elif isinstance(m, dict) and PAVING in m.get("parent", ""):
                    mats[i] = from_paving(m); changed += 1
                elif site and isinstance(m, dict) and from_ground(m):
                    mats[i] = from_ground(m); changed += 1
        elif d.get("mesh") and paks:
            names = slot_names(cli, paks, d["mesh"], cache)
            if names and all(n in ROLES for n in names):
                d["materials"] = [toned(n, 1.0) for n in names]
                changed = len(names)
            elif names and any(n in FLOOR_SLOTS for n in names):
                d["materials"] = [toned(*FLOOR_SLOTS[n]) if n in FLOOR_SLOTS else "" for n in names]
                changed = sum(n in FLOOR_SLOTS for n in names)
        if changed:
            report.append((d["id"], changed))
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("level", type=Path)
    ap.add_argument("--paks", help="Paks folder holding the map's cooked meshes (for slot names)")
    ap.add_argument("--cli", default=str(HERE.parents[1] / "target/release/mjolnir.exe"))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    level = json.loads(a.level.read_text())
    report = reskin(level, a.cli, a.paks)
    if not a.check:
        a.level.write_text(json.dumps(level, indent=2))
    print(json.dumps(report))


if __name__ == "__main__":
    main()
