#!/usr/bin/env python3
"""Make every multiplayer weapon respawn the way the game's weapons do.

    HCE_PAKS=".../Meteorite/Content/Paks" python tools/level/build_weapon_respawn.py [out dir]
    python tools/level/build_weapon_respawn.py --check

A placed weapon comes back by its tag's `multiplayer object`: its type, what
starts its respawn timer, and its default spawn and abandonment times. The
game's weapons are of type "weapon" with the timer starting "on disturbance":
a new one is made its spawn time after the first is picked up or moved, as
Halo 2's netgame equipment does ("respawn timer starts on pick up"). The
battle rifle alone ships as "ordinary" with the timer starting "on death", so
a new one came only after the one taken was gone (Lockout, 2026-11-28: none
after 90 seconds in hand, one 45 seconds after it was destroyed).

For every weapon in the game's multiplayer weapon list that a level can place
(`trait_weapons` and `weapons` in defs/level/palette-map.json), this reads
the tag's multiplayer object. The first one set up as a weapon is the
reference. Any other that is not gets an override container,
`pakchunk990-MJOLNIRWRESPAWN-<type>_P`, of the same tag with the reference's
four values. Nothing names the battle rifle: a weapon a later game update
ships half set up is fixed the same way, and one the game fixes itself stops
getting a container. The multiplayer flag, ball and bomb are not in the
weapon list and are left alone.

--check prints each weapon's values and what would change, and writes
nothing. With no out dir, the containers go straight into the Paks folder.
tools/level/build_ce_runtime.sh runs this for the CE runtime pack.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
CLI = os.environ.get("MJOLNIR", os.path.join(REPO, "target", "release", "mjolnir.exe"))
PALETTE = os.path.join(REPO, "defs", "level", "palette-map.json")
BLOCK = "item.object.multiplayer object"
FIELDS = ("type", "spawn timer type", "default spawn time", "default abandonment time")
WEAPON, ON_DISTURBANCE = "weapon", "starts on disturbance"


def find(node, name):
    if isinstance(node, dict):
        if node.get("name") == name:
            return node
        node = list(node.values())
    if isinstance(node, list):
        for value in node:
            found = find(value, name)
            if found is not None:
                return found
    return None


def plain(value):
    """A displayed enum without its number: `weapon (1)` is `weapon`."""
    value = str(value or "")
    return value.rsplit(" (", 1)[0] if value.endswith(")") else value


_SHIPPED = {}


def selector(path):
    """A tag path as `mjolnir values --tag` finds it: the shipped file's own
    spelling of folder/name-weapon (the game writes `Rifle/assault_rifle/SMG`,
    and --tag matches case)."""
    if not _SHIPPED:
        run = subprocess.run([CLI, "list", "--group", "weapon", "--limit", "5000"], capture_output=True, text=True)
        if run.returncode:
            sys.exit(run.stderr.strip()[-300:])
        for line in run.stdout.splitlines():
            file = line.split("	")[-1].replace("\\", "/")
            if "/Tags/" in file and file.endswith("-weapon.ubulk"):
                folder, name = file.split("/Tags/", 1)[1].rsplit("/", 1)
                stem = name[: -len(".ubulk")]
                _SHIPPED[f"{folder}/{stem[: -len('-weapon')]}".lower()] = f"{folder.rsplit('/', 1)[-1]}/{stem}"
    want = path.replace("\\", "/").lower()
    if want not in _SHIPPED:
        sys.exit(f"{path}: no such weapon tag in the game")
    return _SHIPPED[want]


def multiplayer_object(path):
    """The four respawn values of a weapon tag, or None with no block."""
    run = subprocess.run([CLI, "values", "--group", "weapon", "--tag", selector(path), "--json", "--elements", "2"],
                         capture_output=True, text=True)
    if run.returncode:
        sys.exit(f"{path}: {run.stderr.strip()[-300:]}")
    block = find(json.loads(run.stdout), "multiplayer object")
    if not block or not block.get("children"):
        return None
    values = {c["name"]: c.get("value") for c in block["children"][0].get("children", []) if "value" in c}
    return {name: plain(values.get(name)) for name in FIELDS}


def is_weapon(values):
    return values["type"] == WEAPON and values["spawn timer type"] == ON_DISTURBANCE


def plan(weapons, read=multiplayer_object):
    """(reference type, its values, {type: values} of the ones to override)
    for `weapons`, an ordered {type: tag path}."""
    read_all = {kind: read(path) for kind, path in weapons.items()}
    reference = next((kind for kind, v in read_all.items() if v and is_weapon(v)), None)
    if reference is None:
        sys.exit("no weapon in the list is set up as a weapon: nothing to copy from")
    change = {kind: v for kind, v in read_all.items() if v and not is_weapon(v)}
    return reference, read_all, change


def main():
    args = [a for a in sys.argv[1:] if a != "--check"]
    check = "--check" in sys.argv[1:]
    paks = os.environ.get("HCE_PAKS")
    if not paks:
        sys.exit("set HCE_PAKS")
    out = args[0] if args else paks
    with open(PALETTE, encoding="utf-8") as stream:
        palette = json.load(stream)
    weapons = {kind: palette["weapons"][kind] for kind in palette["trait_weapons"] if kind in palette["weapons"]}
    reference, values, change = plan(weapons)
    wanted = values[reference]
    for kind, v in values.items():
        if v is None:
            print(f"  {kind}: no multiplayer object")
            continue
        note = " (the reference)" if kind == reference else " -> as the reference" if kind in change else ""
        print(f"  {kind}: {v['type']}, {v['spawn timer type']}, spawn {v['default spawn time'] or 0}, "
              f"abandonment {v['default abandonment time'] or 0}{note}")
    if check:
        return
    for kind in change:
        name = f"pakchunk990-MJOLNIRWRESPAWN-{kind}_P"
        cmd = [CLI, "pack", "--group", "weapon", "--tag", selector(weapons[kind]), "--out-dir", out, "--name", name]
        for field in FIELDS:
            cmd += ["--set", f"{BLOCK}[0].{field}={wanted[field]}"]
        run = subprocess.run(cmd, capture_output=True, text=True)
        if run.returncode:
            sys.exit(f"{kind}: {run.stdout[-600:]}\n{run.stderr[-600:]}")
        print(f"{name}: {kind} respawns as {reference} does")
    if not change:
        print("every weapon in the list is already set up as a weapon")


if __name__ == "__main__":
    main()
