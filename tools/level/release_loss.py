"""What a map pack lacks that the release it replaces has.

    python tools/level/release_loss.py <old.mjolnir> <new.mjolnir>

A rebuild starts from a conversion, and a map's later work may have gone into
its published pack alone: its King, Oddball and Race placements, its scripted
devices, a custom vehicle. Such a rebuild packs without them and nothing says
so. The 2026-11-18 rebuild shipped eleven maps without three game types, and
Yoyorast without its gates, buttons, Mongooses and script.

This compares kinds, not counts: a release may place fewer of something, but
when the old release has a kind of thing and the new one has none, that kind
is named. The kinds:

- a game type in `modes`;
- a top-level key of the level file, or a key of its `blam` (the bake's lanes:
  `script`, `trigger_volumes`, `object_names`, ...);
- a group of `blam.objects` (`machines`, `controls`, `crates`), a Megalo label
  among them (`koth_hill`), and a team a label's objects stand on (health
  pack spots on the eighth team);
- a vehicle's own tag;
- a file under `map/` (`map/vehicle_sounds.json`), or a folder of them;
- a family of containers: `MJOLNIRMACH`, `MJOLNIRVMESH`, ... (a container's
  name less its chunk number and the map's code).

Nothing here is a map's name or a tag's: whatever the old release holds is
what the new one is asked for. Exits 1 when something is lost.
"""
import json
import re
import sys
import zipfile

LABEL = "multiplayer data.megalo label"
TEAM = "multiplayer data.owner team"
# A shipped level names its bots only when they are its own; the squads a
# pack plays are in map/bots.json, which is a file like any other here.
UNCOMPARED_BLAM = {"bots"}


def family(member):
    """A container's family: `content/pakchunk986-MJOLNIRMACH-YOY-0C_P.utoc`
    is MJOLNIRMACH. None for a member that is no container."""
    m = re.match(r"(?:content/)?pakchunk\d+-([A-Za-z0-9]+)[-_].*\.(?:utoc|ucas)$", member)
    return m.group(1) if m else None


def map_entry(member):
    """A `map/` member as the file it is, or the folder it is in."""
    if not member.startswith("map/"):
        return None
    rest = member[len("map/"):]
    return f"map/{rest.split('/', 1)[0]}/" if "/" in rest else member


def kinds(names, level):
    """Every kind of thing a release holds, as {kind: a phrase for it}."""
    out = {}
    for mode in level.get("modes") or []:
        out[("mode", mode)] = f"the game type {mode}"
    for key in level:
        out[("level", key)] = f"`{key}` in the level file"
    blam = level.get("blam") or {}
    for key in blam:
        if key not in UNCOMPARED_BLAM:
            out[("blam", key)] = f"`blam.{key}`"
    for o in blam.get("objects") or []:
        group = o.get("group")
        if group:
            out[("group", group)] = f"{group} in `blam.objects`"
        label = (o.get("set") or {}).get(LABEL)
        if label:
            out[("label", label)] = f"objects labelled {label}"
            team = (o.get("set") or {}).get(TEAM)
            if team:
                out[("team", label, team)] = f"{label} objects on the team `{team}`"
    for v in blam.get("vehicles") or []:
        if v.get("tag"):
            out[("vehicle", v["tag"])] = f"the vehicle {v['tag']}"
    for name in names:
        entry = map_entry(name)
        if entry:
            out[("file", entry)] = entry
        fam = family(name)
        if fam:
            out[("containers", fam)] = f"{fam} containers"
    return out


def lost(old_names, old_level, new_names, new_level):
    """What the new release has none of and the old one has, as phrases."""
    old, new = kinds(old_names, old_level), kinds(new_names, new_level)
    # A label with no objects left is one loss, not one per team it stood on.
    gone = {k for k in old if k not in new}
    gone = {k for k in gone if not (k[0] == "team" and ("label", k[1]) in gone)}
    return sorted(old[k] for k in gone)


def pack(path):
    """A pack's member names and its level file."""
    with zipfile.ZipFile(path) as z:
        return z.namelist(), json.loads(z.read("map/level.json"))


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    missing = lost(*pack(sys.argv[1]), *pack(sys.argv[2]))
    for line in missing:
        print(f"lost: {line}")
    if missing:
        sys.exit(1)
    print("nothing lost")


if __name__ == "__main__":
    main()
