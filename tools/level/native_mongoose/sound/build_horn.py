#!/usr/bin/env python3
"""Build every file of the Wwise spike into out/.

    set HCE_PAKS, then: python build_horn.py

out/1_bank/   pakchunk996-MJOLNIRBANK-horn_P.{pak,utoc,ucas}
              the .pak carries Meteorite/Content/WwiseAudio/<id>.bnk; the
              container carries the three events and two HaloAudioSounds.
out/2_horn_events/  pakchunk997-MJOLNIRBANK-hornplay_P.*, -hornstop_P.*: overrides of
              the Warthog horn's two events, carrying the new bank and event ids.
out/3_tag_pickup/  pakchunk998-MJOLNIRBANK-horntag_P.*: a new snd! tag bound to BS_MJ_CE_Horn_Once;
              pakchunk999-MJOLNIRBANK-hornpickup_P.*: the magnum, its pickup sound repointed.
out/test/     the Lua the test pastes.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.environ["MJ_NATIVE_WORK"], "sound")
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
REL = f"{REPO}/target/release"
PAKS = os.environ["HCE_PAKS"]
WORK = os.path.join(DATA, "out", "work")
TOOL = os.path.join(HERE, "tool", "target", "release")
BANK = "pakchunk996-MJOLNIRBANK-horn_P"
HOOK_PLAY = "pakchunk997-MJOLNIRBANK-hornplay_P"
HOOK_STOP = "pakchunk997-MJOLNIRBANK-hornstop_P"
TAG = "pakchunk998-MJOLNIRBANK-horntag_P"
FALLBACK = "pakchunk995-MJOLNIRBANK-warthogbank_P"
ZOOM = "pakchunk999-MJOLNIRBANK-hornpickup_P"


def run(*cmd):
    print("$", " ".join(os.path.basename(str(c)) if i == 0 else str(c) for i, c in enumerate(cmd)))
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    print(r.stdout[-2500:], r.stderr[-1500:])
    if r.returncode:
        sys.exit(f"failed: {cmd[0]}")
    return r.stdout


def stub_from_shipped(dest):
    shutil.copyfile(os.path.join(PAKS, "pakchunk115-Windows.pak"), dest)


def main():
    subprocess.check_call([sys.executable, os.path.join(HERE, "gen_bank.py"), WORK])
    d = json.load(open(os.path.join(WORK, "ids.json")))
    i = d["ids"]
    x = os.path.join(DATA, "x")
    out = run(os.path.join(TOOL, "mkpkgs.exe"), f"{x}/ev_stop.uasset", f"{x}/hs_veh.uasset", WORK, i["bank"],
              i["ev_play_once"], i["ev_play_loop"], i["ev_stop"], round(d["seconds"], 4), f"{x}/bs_ammo.uasset")
    specs = [l for l in out.splitlines() if l.startswith("/Game/")]

    d1 = os.path.join(DATA, "out", "1_bank")
    os.makedirs(d1, exist_ok=True)
    args = [PAKS, d1, "--name", BANK]
    for s in specs:
        args += ["--package", s]
    run(f"{REL}/examples/package_add.exe", *args)
    # The bank pak is the container's .pak sibling: one triplet to install.
    pak = open(os.path.join(WORK, "bank.pak"), "rb").read()
    open(os.path.join(d1, BANK + ".pak"), "wb").write(pak)

    # Route (b): the patched shipped bank alone in a triplet of its own. The
    # container holds one extra copy of an event so its shape matches the others.
    d0 = os.path.join(DATA, "out", "0_fallback")
    os.makedirs(d0, exist_ok=True)
    stop_spec = next(s for s in specs if "Stop_MJ" in s)
    run(f"{REL}/examples/package_add.exe", PAKS, d0, "--name", FALLBACK, "--package",
        stop_spec.replace("/CEHorn/", "/CEHornFallback/", 1))
    shutil.copyfile(os.path.join(WORK, "fallback.pak"), os.path.join(d0, FALLBACK + ".pak"))

    d2 = os.path.join(DATA, "out", "2_horn_events")
    os.makedirs(d2, exist_ok=True)
    root = "/Game/MJOLNIR/Audio/CEHorn"
    for leaf, name in (("Play_VEH_Warthog_Horn_Loop", HOOK_PLAY), ("Stop_VEH_Warthog_Horn_Loop", HOOK_STOP)):
        run(f"{REL}/examples/package_override.exe", PAKS, f"VEH_Warthog_Horn/{leaf}.uasset",
            f"{WORK}/override_{leaf}.uasset", d2, "--name", name)
        stub_from_shipped(os.path.join(d2, name + ".pak"))

    d3 = os.path.join(DATA, "out", "3_tag_pickup")
    os.makedirs(d3, exist_ok=True)
    run(f"{REL}/mjolnir.exe", "new-tag", "--group", "sound", "--from", "magnum/magnum_ammo",
        "--to", "sound\\mjolnir\\ce_horn\\horn_once", "--asset-reference", f"{root}/BS_MJ_CE_Horn_Once",
        "--out-dir", d3, "--name", TAG.removesuffix("_P"))
    if not os.path.exists(os.path.join(d3, TAG + ".pak")):
        stub_from_shipped(os.path.join(d3, TAG + ".pak"))
    # The field: the magnum's pickup sound. Its stock tag has a live binding; the sniper's zoom sounds have none.
    run(f"{REL}/mjolnir.exe", "pack", "--group", "weapon", "--tag", "magnum/magnum-weapon",
        "--set", r"pickup sound=snd!:sound\mjolnir\ce_horn\horn_once", "--out-dir", d3, "--name", ZOOM)
    stub_from_shipped(os.path.join(d3, ZOOM + ".pak"))


if __name__ == "__main__":
    main()
