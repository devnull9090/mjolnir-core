#!/usr/bin/env python3
"""A Custom Edition vehicle's engine and horn as Wwise banks of their own.

    ce_vehicle_audio.py <sounds dir> <out dir> --class BP_VHTMongoose_C --code RWC
        --name Mongoose --actor <folder>/pakchunk987-MJOLNIRVACTOR-RWC_P [--paks <Paks>]
        [--vehi <folder>/pakchunk996-MJOLNIRVVEHI-RWC_P --vehi-tag <vehicle tag path>]

<sounds dir> is ce_vehicle_sounds.py's output: its `vehicle_sounds.json` row for
--class and the waves in `sounds/`. That row is this build's input, read from the
vehicle's tags. It doesn't ship: a vehicle built here plays through the game's own
audio, so the loader's vehicle_sounds.lua has nothing to do for it.

Writes to <out dir>, every container three files:

- pakchunk996-MJOLNIRBANK-<CODE>_P: the `.pak` holds the banks, and the container
  their Play and Stop events, the HaloAudioSounds that name them and, with --vehi,
  the horn's Blueprint;
- the actor container, under --actor's name: its Blueprint with the engine loop
  back and pointed at that sound (crates/ue-asset/examples/vehicle_engine.rs);
- with --vehi, pakchunk996-MJOLNIRVWEAP-<CODE>_P, a clone of the Warthog's horn
  weapon bound to that Blueprint, and the vehicle tag again under --vehi's name,
  its driver weapon repointed at the clone;
- audio.json: the ids and what went in.

Everything shipped that this copies comes from the game's own files in --paks.
Ids and package paths carry the map's code, so two maps can each have a Mongoose.

The engine's pitch is the Blueprint's work: Audio_EngineTick sets RTPC_VEH_Speed
from the engine fraction every 33 ms, and the bank's curves do the rest. So a
donor needs `SoundVariant_EngineLoop` in its graph: a Warthog clone has it, the
Banshee does not (docs/custom_vehicles.md). --actor must be a muted clone, as
ce_vehicle.py builds one.

The horn is the driver's weapon, played by holding fire. Its `lsnd` attachment
names events with no bank behind them: BP_WarthogHornWeaponActor is what plays it.
So a vehicle's horn is its own clone of that Blueprint, and a stock Warthog keeps
its horn. CE's horn runs on crouch; this one keeps the game's trigger.

The start and stop clips in the rows are not in the banks yet: docs/ce_native_support.md.
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
HORN_SOUND = "/VEH_Warthog_Horn_Loop.uasset"
DONOR_ACTOR = "/BP_WarthogVehicleActor.uasset"
HORN_ACTOR = "BP_WarthogHornWeaponActor"
HORN_WEAPON = "warthog_horn/warthog_horn"
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
    for name, path in (("stop_event", STOP_EVENT), ("engine_sound", ENGINE_SOUND), ("horn_sound", HORN_SOUND),
                       ("donor_actor", DONOR_ACTOR)):
        files[name] = os.path.join(folder, f"{name}.uasset")
        run(example("extract_file"), paks, path, files[name])
    return banks, files


def sound_row(sounds, cls, drive):
    """The vehicle's one sound that this drives: `engine`, or `crouch` for its horn."""
    with open(os.path.join(sounds, "vehicle_sounds.json"), encoding="utf-8") as stream:
        table = json.load(stream)
    if cls not in table:
        sys.exit(f"no {cls} in the table: it has {sorted(table)}")
    rows = [s for s in table[cls]["sounds"] if s["drive"] == drive]
    if len(rows) != 1:
        sys.exit(f"{cls}: {len(rows)} {drive} sounds, expected one")
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
    blueprints = []
    for path in sorted(paths, key=lambda p: (rank(p), p)):
        rel = path.split("/Content/", 1)[1]
        leaf = rel.rsplit("/", 1)[1]
        file = os.path.join(packages, leaf)
        run(example("extract_file"), folder, rel, file)
        if leaf.startswith("BP_"):
            blueprints.append(f"/Game/{rel[:-len('.uasset')]}")
            muted = file + ".muted"
            os.replace(file, muted)
            run(example("vehicle_engine"), muted, donor, sound, file)
        args += ["--package", f"/Game/{rel[:-len('.uasset')]}={file}"]
    if len(blueprints) != 1:
        sys.exit(f"{stem}: {blueprints}, expected one Blueprint")
    run(example("package_add"), *args)
    shutil.copyfile(os.path.join(a.paks, STUB), os.path.join(out, f"{stem}.pak"))
    return blueprints[0]


def stub_beside(a, out, name):
    """A container needs a .pak sibling to mount, and new-tag may leave one out."""
    path = os.path.join(out, f"{name}_P.pak")
    if not os.path.exists(path):
        shutil.copyfile(os.path.join(a.paks, STUB), path)


def horn_weapon(a, blueprint, out):
    """The Warthog's horn weapon, bound to the vehicle's own Blueprint."""
    tag = "\\".join(["objects", "mjolnir", a.code.lower(), f"{a.name.lower()}_horn"])
    name = f"pakchunk996-MJOLNIRVWEAP-{a.code}"
    run(CLI, "new-tag", "--paks", a.paks, "--group", "weapon", "--from", HORN_WEAPON, "--to", tag,
        "--asset-reference", blueprint, "--out-dir", out, "--name", name)
    stub_beside(a, out, name)
    return tag, name


def vehicle_with_horn(a, weapon, weapon_container, blueprint, out, work):
    """The vehicle tag with its driver weapon repointed. The new tag's wrapper
    preloads what the vehicle names, so it has to see the weapon's container: a view
    of the Paks folder, hard links and that container, removed afterwards."""
    src = os.path.abspath(a.vehi)
    stem = os.path.basename(src)
    folder = os.path.join(work, "vehi_src")
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    for e in ("utoc", "ucas"):
        shutil.copyfile(f"{src}.{e}", os.path.join(folder, f"{stem}.{e}"))
    shutil.copyfile(os.path.join(a.paks, STUB), os.path.join(folder, f"{stem}.pak"))
    body, edited = os.path.join(work, "vehi.ubulk"), os.path.join(work, "vehi_horn.ubulk")
    run(example("extract_file"), folder, "-vehicle.ubulk", body)
    run(CLI, "tag-file", "--file", body, "--field", "unit.weapons[0].weapon", "--value", f"weap:{weapon}",
        "--out", edited)

    view = os.path.join(work, "paks_view")
    shutil.rmtree(view, ignore_errors=True)
    os.makedirs(view)
    name = stem.removesuffix("_P")
    try:
        for f in os.listdir(a.paks):
            if f.endswith((".utoc", ".ucas")):
                os.link(os.path.join(a.paks, f), os.path.join(view, f))
        for e in ("utoc", "ucas"):
            shutil.copyfile(os.path.join(out, f"{weapon_container}_P.{e}"),
                            os.path.join(view, f"{weapon_container}_P.{e}"))
        run(CLI, "new-tag", "--paks", view, "--group", "vehicle", "--from", a.vehi_from, "--to", a.vehi_tag,
            "--payload", edited, "--asset-reference", blueprint, "--out-dir", out, "--name", name)
    finally:
        # Links only: this never touches the game's own files.
        shutil.rmtree(view, ignore_errors=True)
    stub_beside(a, out, name)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sounds", help="ce_vehicle_sounds.py's output")
    ap.add_argument("out")
    ap.add_argument("--class", dest="cls", required=True, help="the row in vehicle_sounds.json")
    ap.add_argument("--code", required=True, help="the map's code: ids and paths carry it")
    ap.add_argument("--name", default="Mongoose", help="the vehicle's name in ids and paths")
    ap.add_argument("--actor", required=True, help="the actor container, without its extension")
    ap.add_argument("--vehi", help="the vehicle tag's container, without its extension: builds the horn")
    ap.add_argument("--vehi-tag", help="the vehicle tag's path, with --vehi")
    ap.add_argument("--vehi-from", default="mjolnir/vht/mongoose-vehicle", help="the tag --vehi wraps like")
    ap.add_argument("--stem", help="the engine bank's name, for ids; default MJ_<CODE>_<name>_Engine")
    ap.add_argument("--paks", default=os.environ.get("HCE_PAKS"))
    a = ap.parse_args()
    if not a.paks:
        sys.exit("set HCE_PAKS or pass --paks")
    if a.vehi and not a.vehi_tag:
        sys.exit("--vehi needs --vehi-tag")
    out = os.path.abspath(a.out)
    work = os.path.join(out, "work")
    os.makedirs(work, exist_ok=True)

    stem = a.stem or f"MJ_{a.code}_{a.name}_Engine"
    root = f"/Game/MJOLNIR/Audio/{a.code}/{a.name}"
    container = f"pakchunk996-MJOLNIRBANK-{a.code}_P"
    banks, files = templates(a.paks, work)
    made = os.path.join(work, "packages")
    os.makedirs(made, exist_ok=True)

    def sound_packages(name, template, ids):
        listing = run(example("vehicle_audio"), files["stop_event"], template, made, root, name, name,
                      ids["bank"], ids["ev_play"], ids["ev_stop"])
        return [line for line in listing.splitlines() if line.startswith("/Game/")]

    def pcm(r):
        return W.mono48(wave_of(a.sounds, r))

    row = sound_row(a.sounds, a.cls, "engine")
    bank, ids, report = W.engine_bank(banks, stem, row, pcm)
    print(f"{ids['bank']}.bnk: {len(bank)} bytes, {len(row['ranges'])} ranges", flush=True)
    specs = sound_packages(stem, files["engine_sound"], ids)
    carried = {ids["bank"]: bank}
    summary = {"class": a.cls, "code": a.code, "stem": stem, "sound": f"{root}/HS_{stem}", "container": container,
               "bank_bytes": len(bank), "ids": ids, "report": report}

    horn_actor = None
    if a.vehi:
        horn_stem = f"MJ_{a.code}_{a.name}_Horn"
        horn, horn_ids, horn_report = W.horn_bank(banks, horn_stem, sound_row(a.sounds, a.cls, "crouch"), pcm)
        print(f"{horn_ids['bank']}.bnk: {len(horn)} bytes", flush=True)
        specs += sound_packages(horn_stem, files["horn_sound"], horn_ids)
        carried[horn_ids["bank"]] = horn
        horn_actor = f"/Game/MJOLNIR/Vehicles/{a.code}/BP_{a.code}{a.name}Horn"
        clone = os.path.join(made, "horn_clone.uasset")
        file = os.path.join(made, horn_actor.rsplit("/", 1)[1] + ".uasset")
        run(example("vehicle_actor"), a.paks, HORN_ACTOR, horn_actor, clone)
        run(example("vehicle_horn"), clone, f"{root}/HS_{horn_stem}", file)
        specs.append(f"{horn_actor}={file}")
        summary["horn"] = {"stem": horn_stem, "actor": horn_actor, "ids": horn_ids, "report": horn_report}

    args = [a.paks, out, "--name", container]
    for spec in specs:
        args += ["--package", spec]
    run(example("package_add"), *args)
    with open(os.path.join(out, f"{container}.pak"), "wb") as stream:
        stream.write(W.bank_pak(container, carried))

    blueprint = actor_container(a, f"{root}/HS_{stem}", files["donor_actor"], out, work)
    if a.vehi:
        weapon, weapon_container = horn_weapon(a, horn_actor, out)
        vehicle_with_horn(a, weapon, weapon_container, blueprint, out, work)
        summary["horn"]["weapon"] = weapon
    with open(os.path.join(out, "audio.json"), "w", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=1)
    print(f"{container}: {summary['sound']}", flush=True)


if __name__ == "__main__":
    main()
