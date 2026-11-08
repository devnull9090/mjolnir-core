"""Take published hub maps' teleporter ends off team 0 (#346): set their owner
team to the eighth team in the shipped scenario and the level file, and pack
the next release of the same listing. Publishes nothing: the packs stay in
<out> until someone uploads them.

    python tools/level/fix_teleporter_teams.py <pack.mjolnir>... --paks <Paks> [--sign]

gen_ce_level.py placed `teleporter_sender`, `teleporter_receiver` and
`teleporter_2way` scenery without an owner team until 2026-11-07, so the sim
gave them team 0. Its respawn search (0x2f84e0) takes any scenery with a
multiplayer block that the player's team owns, so red respawned on teleporter
pads in every team game, by the blue base too. The generator now places them
on the eighth team, which no game type plays; who may use a pad does not
depend on its team (0x3e5820 lists teleporters of any team). This brings maps
built before that up to the same placements.

Nothing is rebaked. A rebake does not always give back the shipped scenario:
the bots' pathfinding seams are numbered in hash-map order, and maps baked
before a bake change (Crossline's equipment palette, which saved Forge
layouts index) would pick it up. So the shipped scenario's payload has each
teleporter end's `multiplayer data.owner team` set with `mjolnir tag-file`,
and the map container is rebuilt around it (`replace_chunk`, through the
writer `level bake` uses). Then:

- the payload differs from the shipped one in one byte per end, 0 become 7,
  and `mjolnir tagdiff` finds those owner teams changed and nothing else;
- every other package of the map container comes out byte for byte;
- the level file differs only in its teleporter ends' owner team;
- the new pack differs from the old only in the map container and the level
  file, the manifest only in its version.

The version gets a patch bump unless --version or --version-bump says
otherwise. Work goes to <work>/<CODE>/; packs to <out>/<slug>-<version>.mjolnir.
"""
import argparse
import copy
import json
import os
import sys

import add_objectives
from add_bots import CLI, EXTRACT, REPO, container_dir, packages, run, sha
from ce_objectives import MARKER_TEAM

REPLACE = os.environ.get("REPLACE_CHUNK", os.path.join(REPO, "target", "debug", "examples", "replace_chunk.exe"))
TEAM = "multiplayer data.owner team"
TELEPORTERS = "objects\\multi\\teleporters\\"
# The sim's team indices: red 0 ... the eighth team 7 (the owner byte, MP+0x19).
MARKER_TEAM_INDEX = 7


def is_teleporter(o):
    return o.get("group") == "scenery" and o.get("tag", "").startswith(TELEPORTERS)


def park(level):
    """A copy of a level with every teleporter end on the eighth team, and how
    many ends that moved."""
    level = copy.deepcopy(level)
    moved = 0
    for o in level["blam"]["objects"]:
        if is_teleporter(o) and o.get("set", {}).get(TEAM) != MARKER_TEAM:
            o.setdefault("set", {})[TEAM] = MARKER_TEAM
            moved += 1
    return level, moved


def level_changes(old, new):
    """What differs between two level files but teleporter ends' owner team,
    as messages."""
    if len(old["blam"]["objects"]) != len(new["blam"]["objects"]):
        return ["the object count changed"]
    undone = copy.deepcopy(new)
    for before, after in zip(old["blam"]["objects"], undone["blam"]["objects"]):
        if not is_teleporter(before) or not is_teleporter(after) or before.get("tag") != after.get("tag"):
            continue
        if after["set"].get(TEAM) != MARKER_TEAM:
            return [f"{after['tag']} is not on {MARKER_TEAM}"]
        if TEAM in before.get("set", {}):
            after["set"][TEAM] = before["set"][TEAM]
        else:
            del after["set"][TEAM]
            if not after["set"] and "set" not in before:
                del after["set"]
    return [] if undone == old else ["something other than teleporter teams changed"]


def block(values, name):
    """A top-level block of a `values --json` tree."""
    found = [c for c in values["fields"] if c.get("kind") == "block" and c.get("name") == name]
    if len(found) != 1:
        sys.exit(f"the scenario has {len(found)} `{name}` blocks")
    return found[0]


def field(element, path):
    """A field's displayed value in a block element, by dotted path."""
    node = element
    for part in path.split("."):
        node = next((c for c in node.get("children", []) if c.get("name") == part), None)
        if node is None:
            return None
    return node.get("value")


def scenario_values(container, elements):
    return json.loads(run([CLI, "values", "--paks", container, "--group", "scenario", "--json",
                           "--elements", str(elements)]))


def teleporter_scenery(container):
    """The scenario's scenery entries whose palette type is a teleporter end,
    as (index, owner team shown)."""
    counts = scenario_values(container, 1)
    n = max(block(counts, "scenery")["count"], block(counts, "scenery palette")["count"], 1)
    values = scenario_values(container, n)
    palette = [field(e, "name") or "" for e in block(values, "scenery palette")["children"]]
    scenery = block(values, "scenery")["children"]
    if len(scenery) != block(values, "scenery")["count"]:
        sys.exit("the scenery block was not read whole")
    ends = []
    for i, e in enumerate(scenery):
        t = field(e, "type") or "none"
        if t.startswith("#") and palette[int(t[1:])].startswith(TELEPORTERS):
            ends.append((i, field(e, "multiplayer data.owner team")))
    return ends


def patch_scenario(p, container, ends):
    """The shipped scenario payload and a copy with each end's owner team set,
    checked to differ in one byte per end, 0 become 7; and the bulk package's
    path in the container."""
    bulk = [x for x in packages(container, f"pakchunk997-MJOLNIRMAP-{p.code}_P", p.paks)
            if x.endswith("-scenario.ubulk")]
    if len(bulk) != 1:
        sys.exit(f"{p.code}: {len(bulk)} scenario payloads in the map container")
    shipped = os.path.join(p.w, "scenario.shipped")
    patched = os.path.join(p.w, "scenario.patched")
    run([EXTRACT, container, bulk[0], shipped])
    with open(shipped, "rb") as stream:
        old = stream.read()
    with open(patched, "wb") as stream:
        stream.write(old)
    for i, _ in ends:
        out = run([CLI, "tag-file", "--file", patched, "--field", f"scenery[{i}].{TEAM}",
                   "--value", MARKER_TEAM, "--out", patched])
        if "differs  1 byte(s) from the original" not in out or "re-read  eighth party (7)" not in out:
            sys.exit(f"{p.code}: scenery[{i}]: tag-file did not set one byte:\n{out}")
    with open(patched, "rb") as stream:
        new = stream.read()
    if len(new) != len(old):
        sys.exit(f"{p.code}: the payload grew from {len(old)} to {len(new)} bytes")
    diff = [(i, x, y) for i, (x, y) in enumerate(zip(old, new)) if x != y]
    if len(diff) != len(ends) or any((x, y) != (0, MARKER_TEAM_INDEX) for _, x, y in diff):
        sys.exit(f"{p.code}: the payload differs in {[(hex(i), x, y) for i, x, y in diff[:8]]} "
                 f"for {len(ends)} ends")
    return shipped, patched, bulk[0]


def check_container(p, src, built, bulk, patched, ends):
    """The rebuilt map container: the patched payload, every other package
    byte for byte, and tagdiff's word that only the ends' owner team moved."""
    stem = f"pakchunk997-MJOLNIRMAP-{p.code}_P"
    shipped = packages(src, stem, p.paks)
    new = packages(built, stem, p.paks)
    if new != shipped:
        sys.exit(f"{p.code}: the rebuilt container holds {new}, the shipped one {shipped}")
    x = os.path.join(p.w, "x.bin")
    for pkg in shipped:
        run([EXTRACT, built, pkg, x])
        want = patched if pkg == bulk else os.path.join(p.w, "y.bin")
        if pkg != bulk:
            run([EXTRACT, src, pkg, want])
        if sha(x) != sha(want):
            sys.exit(f"{p.code}: {pkg} is not as intended in the rebuilt container")
    report = os.path.join(p.w, "tagdiff.json")
    run([CLI, "tagdiff", "--paks-a", src, "--paks-b", built, "--elements", "100000", "--json", report])
    with open(report, encoding="utf-8") as stream:
        d = json.load(stream)
    if d["added"] or d["removed"] or d["unreadable"] or len(d["changed"]) != 1:
        sys.exit(f"{p.code}: tagdiff: {len(d['changed'])} changed, added {d['added']}, "
                 f"removed {d['removed']}, unreadable {d['unreadable']}")
    fields = {f["path"]: (f["before"], f["after"]) for f in d["changed"][0]["fields"]}
    want = {f"scenery[{i}]/multiplayer data/owner team": (before, "eighth party (7)") for i, before in ends}
    if d["changed"][0]["group"] != "scenario" or fields != want:
        sys.exit(f"{p.code}: tagdiff found {sorted(fields.items())[:8]}, expected {sorted(want.items())}")
    print(f"  {len(shipped) - 1} other package(s) unchanged; tagdiff: {len(ends)} owner teams, nothing else",
          flush=True)


def one(pack, a):
    p = add_objectives.Pack(pack, a)
    p.paks = a.paks
    level, moved = park(p.level)
    if not moved:
        print(f"== {p.code}: its teleporter ends are already on {MARKER_TEAM}", flush=True)
        return None
    problems = level_changes(p.level, level)
    if problems:
        sys.exit(f"{p.code}: {problems}")
    stem = f"pakchunk997-MJOLNIRMAP-{p.code}_P"
    content = os.path.join(p.unpacked, "content")
    if not os.path.exists(os.path.join(content, f"{stem}.utoc")):
        sys.exit(f"{p.code}: no {stem} in the pack")
    src = container_dir(p.w, "src", os.path.join(content, stem), os.path.join(a.paks, "pakchunk115-Windows.pak"))
    ends = teleporter_scenery(src)
    if len(ends) != moved:
        sys.exit(f"{p.code}: the scenario has {len(ends)} teleporter ends, the level file {moved}")
    kinds = sorted({o["tag"].rsplit("\\", 1)[-1] for o in level["blam"]["objects"] if is_teleporter(o)})
    print(f"== {p.code} ({p.slug}) {p.manifest['version']} -> {p.version}: {moved} teleporter ends "
          f"({', '.join(kinds)}) to {MARKER_TEAM}", flush=True)
    _, patched, bulk = patch_scenario(p, src, ends)
    rebuilt = os.path.join(p.w, "rebuilt")
    run([REPLACE, src, stem, bulk, patched, rebuilt])
    built = container_dir(p.w, "built", os.path.join(rebuilt, stem), os.path.join(a.paks, "pakchunk115-Windows.pak"))
    check_container(p, src, built, bulk, patched, ends)
    bots = os.path.join(p.unpacked, "map", "bots.json")
    return add_objectives.release(p, level, a, built, bots if os.path.exists(bots) else None,
                                  bots_may_change=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("packs", nargs="+")
    ap.add_argument("--version", help="the new version (one map); else --version-bump of each pack's")
    ap.add_argument("--version-bump", choices=("major", "minor", "patch"), default="patch")
    ap.add_argument("--work", default="C:/haloce/ce_conversions/teleporter_teams/patch")
    ap.add_argument("--out", default="C:/haloce/ce_conversions/teleporter_teams/release")
    ap.add_argument("--paks", default=os.environ.get("HCE_PAKS"))
    ap.add_argument("--sign", action="store_true", help="sign with this machine's device key")
    ap.add_argument("--bake-only", action="store_true", help="patch and check, pack nothing")
    a = ap.parse_args()
    # The pack keeps its own runtime range.
    a.runtime = None
    a.packs = [os.path.abspath(p) for p in a.packs]
    a.work, a.out = os.path.abspath(a.work), os.path.abspath(a.out)
    if not a.paks:
        sys.exit("set HCE_PAKS or pass --paks")
    a.paks = os.path.abspath(a.paks)
    if a.version and len(a.packs) > 1:
        sys.exit("--version takes one pack")
    os.chdir(REPO)
    for tool in (CLI, EXTRACT, REPLACE):
        if not os.path.exists(tool):
            sys.exit(f"no {tool}: set MJOLNIR, EXTRACT_FILE or REPLACE_CHUNK, or build it")
    failed = []
    for pack in a.packs:
        try:
            one(pack, a)
        except SystemExit as e:
            print(f"  FAILED: {e}", flush=True)
            failed.append(os.path.basename(pack))
    if failed:
        sys.exit(f"{len(failed)} failed: {failed}")


if __name__ == "__main__":
    main()
