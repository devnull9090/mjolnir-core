#!/usr/bin/env python3
"""A Custom Edition vehicle's engine as a Wwise bank of its own.

    ce_vehicle_audio.py <sounds dir> <out dir> --class BP_VHTMongoose_C --code RWC
        --name Mongoose --actor <folder>/pakchunk987-MJOLNIRVACTOR-RWC_P [--paks <Paks>]

<sounds dir> is ce_vehicle_sounds.py's output: its `vehicle_sounds.json` row for
--class and the waves in `sounds/`. That row is this build's input, read from the
vehicle's tags. It doesn't ship: a vehicle built here plays through the game's own
audio, so the loader's vehicle_sounds.lua has nothing to do for it.

Writes to <out dir>, every container three files:

- pakchunk996-MJOLNIRBANK-<CODE>_P: the `.pak` holds the bank, and the container
  its Play and Stop events and the HaloAudioSound that names them;
- the actor container, under --actor's name: its Blueprint with the engine loop
  back and pointed at that sound (crates/ue-asset/examples/vehicle_engine.rs);
- audio.json: the ids and what went in.

Everything shipped that this copies comes from the game's own files in --paks.
Ids and package paths carry the map's code, so two maps can each have a Mongoose.

The engine's pitch is the Blueprint's work: Audio_EngineTick sets RTPC_VEH_Speed
from the engine fraction every 33 ms, and the bank's curves do the rest. So a
donor needs `SoundVariant_EngineLoop` in its graph: a Warthog clone has it, the
Banshee does not (docs/custom_vehicles.md). --actor must be a muted clone, as
ce_vehicle.py builds one.

The start and stop clips in the row are not in the bank yet: docs/ce_native_support.md.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wwise_bank as W  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
CLI = os.environ.get("MJOLNIR", os.path.join(REPO, "target", "release", "mjolnir.exe"))
EXAMPLES = os.path.join(REPO, "target", "release", "examples")
STUB = "pakchunk115-Windows.pak"
# The shipped packages cloned. A path substring each, enough to pick one file:
# the leading slash leaves out the events, which end in the same name.
STOP_EVENT = "VEH_Warthog_Horn/Stop_VEH_Warthog_Horn_Loop.uasset"
ENGINE_SOUND = "/VEH_Warthog_Engine_Main.uasset"
DONOR_ACTOR = "/BP_WarthogVehicleActor.uasset"
# package_add wants a package after what it imports.
ACTOR_ORDER = ("SKEL_", "SK_", "ABP_", "BP_")


def run(*cmd):
    done = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if done.returncode:
        sys.exit(f"{os.path.basename(str(cmd[0]))} failed:\n{done.stdout[-1500:]}\n{done.stderr[-800:]}")
    return done.stdout


def example(name):
    path = os.path.join(EXAMPLES, f"{name}.exe")
    if not os.path.exists(path):
        sys.exit(f"no {path}: cargo build --release --example {name}")
    return path


def shipped_bank(paks, bank_id, folder):
    """A bank's bytes, out of the game's .pak archives."""
    run(example("pak_extract"), paks, f"{bank_id}.bnk", folder)
    found = glob.glob(os.path.join(folder, "**", f"{bank_id}.bnk"), recursive=True)
    if len(found) != 1:
        sys.exit(f"{bank_id}.bnk: found {found}")
    with open(found[0], "rb") as stream:
        return stream.read()


def templates(paks, work):
    """What the build copies from the game: three banks and three packages."""
    folder = os.path.join(work, "templates")
    os.makedirs(folder, exist_ok=True)
    banks = {i: shipped_bank(paks, i, folder) for i in (W.SMALL_BANK, W.HOG_BANK, W.PCM_BANK)}
    files = {}
    for name, path in (("stop_event", STOP_EVENT), ("engine_sound", ENGINE_SOUND), ("donor_actor", DONOR_ACTOR)):
        files[name] = os.path.join(folder, f"{name}.uasset")
        run(example("extract_file"), paks, path, files[name])
    return banks, files


def engine_row(sounds, cls):
    with open(os.path.join(sounds, "vehicle_sounds.json"), encoding="utf-8") as stream:
        table = json.load(stream)
    if cls not in table:
        sys.exit(f"no {cls} in the table: it has {sorted(table)}")
    rows = [s for s in table[cls]["sounds"] if s["drive"] == "engine"]
    if len(rows) != 1:
        sys.exit(f"{cls}: {len(rows)} engine sounds, expected one")
    return rows[0]


def wave_of(sounds, r):
    """A range's wave file: `wave` is the package path ce_vehicle_sounds.py gave it."""
    return os.path.join(sounds, "sounds", r["wave"].rsplit(".", 1)[1] + ".wav")


def actor_container(a, sound, donor, out, work):
    """--actor's packages again, its Blueprint with the engine back."""
    src = os.path.abspath(a.actor)
    stem = os.path.basename(src)
    folder = os.path.join(work, "actor_src")
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    for e in ("utoc", "ucas"):
        shutil.copyfile(f"{src}.{e}", os.path.join(folder, f"{stem}.{e}"))
    shutil.copyfile(os.path.join(a.paks, STUB), os.path.join(folder, f"{stem}.pak"))
    listing = run(CLI, "container", "--paks", a.paks, os.path.join(folder, f"{stem}.utoc"))
    paths = sorted({w for w in listing.split() if w.endswith(".uasset") and "/Content/" in w})
    if not paths:
        sys.exit(f"{stem}: no packages")

    def rank(path):
        leaf = path.rsplit("/", 1)[1]
        return next((i for i, p in enumerate(ACTOR_ORDER) if leaf.startswith(p)), len(ACTOR_ORDER))

    packages = os.path.join(work, "actor")
    os.makedirs(packages, exist_ok=True)
    args = [a.paks, out, "--name", stem]
    blueprints = 0
    for path in sorted(paths, key=lambda p: (rank(p), p)):
        rel = path.split("/Content/", 1)[1]
        leaf = rel.rsplit("/", 1)[1]
        file = os.path.join(packages, leaf)
        run(example("extract_file"), folder, rel, file)
        if leaf.startswith("BP_"):
            blueprints += 1
            muted = file + ".muted"
            os.replace(file, muted)
            run(example("vehicle_engine"), muted, donor, sound, file)
        args += ["--package", f"/Game/{rel[:-len('.uasset')]}={file}"]
    if blueprints != 1:
        sys.exit(f"{stem}: {blueprints} Blueprints, expected one")
    run(example("package_add"), *args)
    shutil.copyfile(os.path.join(a.paks, STUB), os.path.join(out, f"{stem}.pak"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sounds", help="ce_vehicle_sounds.py's output")
    ap.add_argument("out")
    ap.add_argument("--class", dest="cls", required=True, help="the row in vehicle_sounds.json")
    ap.add_argument("--code", required=True, help="the map's code: ids and paths carry it")
    ap.add_argument("--name", default="Mongoose", help="the vehicle's name in ids and paths")
    ap.add_argument("--actor", required=True, help="the actor container, without its extension")
    ap.add_argument("--stem", help="the bank's name, for ids; default MJ_<CODE>_<name>_Engine")
    ap.add_argument("--paks", default=os.environ.get("HCE_PAKS"))
    a = ap.parse_args()
    if not a.paks:
        sys.exit("set HCE_PAKS or pass --paks")
    out = os.path.abspath(a.out)
    work = os.path.join(out, "work")
    os.makedirs(work, exist_ok=True)

    stem = a.stem or f"MJ_{a.code}_{a.name}_Engine"
    root = f"/Game/MJOLNIR/Audio/{a.code}/{a.name}"
    container = f"pakchunk996-MJOLNIRBANK-{a.code}_P"
    row = engine_row(a.sounds, a.cls)
    banks, files = templates(a.paks, work)

    bank, ids, report = W.engine_bank(banks, stem, row, lambda r: W.mono48(wave_of(a.sounds, r)))
    print(f"{ids['bank']}.bnk: {len(bank)} bytes, {len(row['ranges'])} ranges", flush=True)

    made = os.path.join(work, "packages")
    os.makedirs(made, exist_ok=True)
    listing = run(example("vehicle_audio"), files["stop_event"], files["engine_sound"], made, root, stem, stem,
                  ids["bank"], ids["ev_play"], ids["ev_stop"])
    specs = [line for line in listing.splitlines() if line.startswith("/Game/")]
    args = [a.paks, out, "--name", container]
    for spec in specs:
        args += ["--package", spec]
    run(example("package_add"), *args)
    with open(os.path.join(out, f"{container}.pak"), "wb") as stream:
        stream.write(W.bank_pak(container, ids["bank"], bank))

    sound = f"{root}/HS_{stem}"
    actor_container(a, sound, files["donor_actor"], out, work)
    with open(os.path.join(out, "audio.json"), "w", encoding="utf-8") as stream:
        json.dump({"class": a.cls, "code": a.code, "stem": stem, "sound": sound, "container": container,
                   "bank_bytes": len(bank), "ids": ids, "report": report}, stream, indent=1)
    print(f"{container}: {sound}", flush=True)


if __name__ == "__main__":
    main()
