#!/usr/bin/env python3
"""Build the engine spike into out/. Set HCE_PAKS, then: python build_engine.py

out/1_bank/   pakchunk996-MJOLNIRBANK-engine_P.*: .pak = the bank; container = Play/Stop events,
              HS_MJ_CE_Engine (HaloAudioSound), BL_MJ_CE_Engine (BlamAudioLoopingSound).
out/2_lsnd/   pakchunk998-MJOLNIRBANK-enginetag_P.*: new lsnd tag bound to BL_MJ_CE_Engine;
              pakchunk996-MJOLNIRNMG-vehi_P.*: rider6's vehi, attachment 3 repointed at it.
out/3_actor/  pakchunk987-MJOLNIRNMG-actor_P.*: nm's actor, engine PlaySound back, SoundVariant_EngineLoop
              -> HS_MJ_CE_Engine. Other four packages unchanged.
"""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.environ["MJ_NATIVE_WORK"], "sound")
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
REL = f"{REPO}/target/release"
MJ = f"{REL}/mjolnir.exe"
PAKS = os.environ["HCE_PAKS"]
WORK = os.path.join(DATA, "out", "work")
TOOL = os.path.join(HERE, "tool", "target", "release")
ROOT = "/Game/MJOLNIR/Audio/CEEngine"
TAG = "sound\\mjolnir\\ce_engine\\engine"
BP = "/Game/MJOLNIR/Vehicles/NMG/BP_NMGMongoose"


def run(*cmd):
    print("$", os.path.basename(str(cmd[0])), *[str(c)[:90] for c in cmd[1:8]])
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    print(r.stdout[-1800:], r.stderr[-800:])
    if r.returncode:
        sys.exit(f"failed: {cmd[0]}")
    return r.stdout


def stub(dest):
    shutil.copyfile(os.path.join(PAKS, "pakchunk115-Windows.pak"), dest)


def main():
    subprocess.check_call([sys.executable, os.path.join(HERE, "gen_engine.py"), WORK])
    d = json.load(open(os.path.join(WORK, "ids.json")))["ids"]
    x = os.path.join(DATA, "x")
    out = run(f"{TOOL}/mkengine.exe", f"{x}/ev_stop.uasset", f"{x}/hs_engine.uasset", f"{x}/bl_engine.uasset",
              WORK, d["bank"], d["ev_play"], d["ev_stop"])
    specs = [l for l in out.splitlines() if l.startswith("/Game/")]

    d1 = os.path.join(DATA, "out", "1_bank")
    os.makedirs(d1, exist_ok=True)
    bank = "pakchunk996-MJOLNIRBANK-engine_P"
    args = [PAKS, d1, "--name", bank]
    for s in specs:
        args += ["--package", s]
    run(f"{REL}/examples/package_add.exe", *args)
    shutil.copyfile(os.path.join(WORK, "bank.pak"), os.path.join(d1, bank + ".pak"))

    # The same container and ids, a bank with one loop: swap it in for the blend.
    d1b = os.path.join(DATA, "out", "1_bank_one")
    os.makedirs(d1b, exist_ok=True)
    one = os.path.join(DATA, "out", "work_one")
    subprocess.check_call([sys.executable, os.path.join(HERE, "gen_engine.py"), one, "one"])
    for e in ("ucas", "utoc"):
        shutil.copyfile(os.path.join(d1, f"{bank}.{e}"), os.path.join(d1b, f"{bank}.{e}"))
    shutil.copyfile(os.path.join(one, "bank.pak"), os.path.join(d1b, bank + ".pak"))

    d2 = os.path.join(DATA, "out", "2_lsnd")
    os.makedirs(d2, exist_ok=True)
    tag = "pakchunk998-MJOLNIRBANK-enginetag"
    run(MJ, "new-tag", "--group", "sound_looping", "--from", "warthog_engine_lod/warthog_engine_lod", "--to", TAG,
        "--asset-reference", f"{ROOT}/BL_MJ_CE_Engine", "--out-dir", d2, "--name", tag)
    if not os.path.exists(os.path.join(d2, tag + "_P.pak")):
        stub(os.path.join(d2, tag + "_P.pak"))
    # rider6's vehi body, one reference changed; donor wrapper and binding as nm built it.
    body = os.path.join(x, "vehi.ubulk")
    edited = os.path.join(x, "vehi_engine.ubulk")
    run(MJ, "tag-file", "--file", body, "--field", "unit.object.attachments[3].type",
        "--value", f"lsnd:{TAG}", "--out", edited)
    vehi = "pakchunk996-MJOLNIRNMG-vehi"
    # A view of the Paks folder with the new tag in it, so the wrapper preloads it.
    view = os.path.join(x, "paks_view")
    os.makedirs(view, exist_ok=True)
    for f in os.listdir(PAKS):
        if f.endswith((".utoc", ".ucas")) and not os.path.exists(os.path.join(view, f)):
            os.link(os.path.join(PAKS, f), os.path.join(view, f))
    for e in ("utoc", "ucas"):
        shutil.copyfile(os.path.join(d2, f"{tag}_P.{e}"), os.path.join(view, f"{tag}_P.{e}"))
    run(MJ, "new-tag", "--paks", view, "--group", "vehicle", "--from", "mjolnir/vht/mongoose-vehicle",
        "--to", "objects\\mjolnir\\nmg\\mongoose", "--payload", edited, "--asset-reference", BP,
        "--out-dir", d2, "--name", vehi)
    stub(os.path.join(d2, vehi + "_P.pak"))
    for f in os.listdir(view):
        os.remove(os.path.join(view, f))
    os.rmdir(view)

    d3 = os.path.join(DATA, "out", "3_actor")
    os.makedirs(d3, exist_ok=True)
    actor = "pakchunk987-MJOLNIRNMG-actor"
    src = os.path.join(os.environ["MJ_NATIVE_WORK"], "actor", "w")
    pk = os.path.join(x, "actor")
    folder = "/Game/MJOLNIR/Vehicles/NMG"
    for leaf in ("ABP_NMGMongoose", "DA_NMGMongoose_HUD", "SKEL_NMGMongoose", "SK_NMGMongoose"):
        run(f"{REL}/examples/extract_file.exe", src, f"NMG/{leaf}.uasset", os.path.join(pk, leaf + ".uasset"))
    run(f"{TOOL}/engactor.exe", f"{src}/BP_NMGMongoose.uasset", f"{x}/bp_warthog.uasset",
        f"{ROOT}/HS_MJ_CE_Engine", f"{pk}/BP_NMGMongoose.uasset")
    args = [PAKS, d3, "--name", actor + "_P"]
    for leaf in ("SKEL_NMGMongoose", "SK_NMGMongoose", "ABP_NMGMongoose", "BP_NMGMongoose", "DA_NMGMongoose_HUD"):
        args += ["--package", f"{folder}/{leaf}={pk}/{leaf}.uasset"]
    run(f"{REL}/examples/package_add.exe", *args)
    stub(os.path.join(d3, actor + "_P.pak"))


if __name__ == "__main__":
    main()
