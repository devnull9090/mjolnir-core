#!/usr/bin/env python3
"""Show a custom vehicle's own name in its prompts ("Drive Mongoose").

    ce_vehicle_name.py <out dir> --code VHT --name mongoose [--label "Mongoose"] [--actor BP.uasset]

Writes the actor container again, under ce_vehicle.py's name for it, now holding
the actor and a data asset with the name (crates/ue-asset/examples/vehicle_name.rs).
`--actor` defaults to the actor installed in HCE_PAKS. Copy all three files to
the Paks folder with the game closed.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = os.path.join(HERE, "..", "..", "target", "release", "examples")


def run(*args):
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    r = subprocess.run([str(a) for a in args], env=env, text=True, encoding="utf-8",
                       errors="replace", capture_output=True)
    if r.returncode:
        sys.exit(f"{args[0]} failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout


def named(paks, out, actor, label):
    """`--package` arguments for package_add: the actor, named, and its data asset."""
    text = run(os.path.join(EXAMPLES, "vehicle_name.exe"), paks, actor, label, out)
    print(text.splitlines()[0].encode("ascii", "replace").decode())
    return [x for m in re.finditer(r"^package (.+)$", text, re.M) for x in ("--package", m.group(1))]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out")
    ap.add_argument("--code", default="VHT")
    ap.add_argument("--name", default="mongoose")
    ap.add_argument("--label", help="the name players read, any text; defaults to --name capitalized")
    ap.add_argument("--actor", help="the actor's .uasset, if not the installed one")
    a = ap.parse_args()
    paks = os.environ.get("HCE_PAKS") or sys.exit("set HCE_PAKS")
    os.makedirs(a.out, exist_ok=True)
    packages = named(paks, a.out, a.actor or f"BP_{a.code}{a.name.capitalize()}", a.label or a.name.capitalize())
    container = f"pakchunk987-MJOLNIR{a.code}-actor_P"
    print(run(os.path.join(EXAMPLES, "package_add.exe"), paks, a.out, "--name", container, *packages).strip())
    stub = next(f for f in sorted(os.listdir(paks)) if re.match(r"pakchunk997-MJOLNIRMAP-.*_P\.pak$", f))
    shutil.copyfile(os.path.join(paks, stub), os.path.join(a.out, container + ".pak"))


if __name__ == "__main__":
    main()
