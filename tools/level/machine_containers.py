"""The tag containers a map's own objects need beyond its scenario, meshes
and cooks: one list for the install (upgrade_ce_map.py) and the packs
(pack_local_map.py, pack_remastered.py), so a pack carries what the tested
install did. Zanzibar's first pack would have shipped with no gate, gears or
movable props: the install knew of the machines, the pack tools of none, and
the props' tags were in the game only as local builds installed by hand
(2026-11-15).

Each function returns [(container path without extension, build name)]. The
build name is the container's name less its `pakchunk<N>-` and `_P`; a
machine's or a prop's starts `MJOLNIRMACH-<CODE>-`, which is how `mjolnir map
pack` finds a map's tag containers in a pack folder's `machines/`.
"""
import glob
import json
import os


def gear_containers(conv):
    """The machines a conversion placed (its `machines` folder): turning
    parts' (h2_machines.py) and doors' (h2_door_machines.py), their tags'
    containers and their actors' (pakchunk987-MJOLNIRGEAR, -MJOLNIRACT). A
    fresh conversion's door actors are here and nowhere else: Containment's
    remaster installed its gate tags without the actors that draw them
    (2026-11-16)."""
    out = []
    for utoc in sorted(glob.glob(os.path.join(conv, "machines", "pakchunk98[67]-MJOLNIR*_P.utoc"))):
        stem = os.path.basename(utoc)[:-len("_P.utoc")]
        if any(k in stem for k in ("-MJOLNIRMACH-", "-MJOLNIRGEAR-", "-MJOLNIRACT-")):
            out.append((utoc[:-len(".utoc")], stem.split("-", 1)[1]))
    return out


def door_containers(m):
    """A Halo 2 door's machines and control: tags of their own, a container
    each, and their actors' (h2_door_machines), written beside doors.json."""
    out = []
    if m.get("doors") and os.path.exists(m["doors"]):
        for door in json.load(open(m["doors"], encoding="utf-8")):
            for owner in (door.get("machines") or []) + [door.get("sim_control") or {}]:
                for stem in owner.get("containers") or []:
                    item = (os.path.join(os.path.dirname(m["doors"]), f"{stem}_P"), stem.split("-", 1)[1])
                    # The map's machine actors share one container.
                    if item not in out:
                        out.append(item)
    return out


def prop_containers(m, code):
    """The movable props' crate tags (h2_physics_props.py's
    physics_props.json `tags`, in `tags/` beside it): named for the map here,
    as its machines' are, since the tags are the map's own
    (objects\\mjolnir\\<code>\\...)."""
    path = m.get("physics_props")
    if not isinstance(path, str) or not os.path.exists(path):
        return []
    out = []
    for prop in json.load(open(path, encoding="utf-8")):
        for stem in prop.get("tags") or []:
            # A build name holds letters, digits and dashes only.
            rest = stem[:-len("_P")].split("-MJOLNIRPROP-", 1)[-1].replace("_", "-")
            item = (os.path.join(os.path.dirname(path), "tags", stem), f"MJOLNIRMACH-{code}-PROP-{rest}")
            if item not in out:
                out.append(item)
    return out


def extra_containers(m, code, repo, used=()):
    """`extra_containers`: further containers the map owns, which neither
    its conversion nor its bake makes. Each entry is a container's path
    without its extension, under the repository or absolute, or a pattern of
    such paths (`*`). A CE map's scripted devices (ce_machines.py: a tag
    container a machine) and a custom vehicle's containers
    (ce_place_vehicles.py) are built once and tested, and a rebuild carries
    them from here: Yoyorast's 2026-11-18 rebuild knew of neither, and
    shipped with no gate, button or Mongoose.

    A build name must hold the map's code and be the only one of its name,
    among these and the names in `used`."""
    entries = m.get("extra_containers", [])
    if not isinstance(entries, list):
        raise ValueError("extra_containers must be a list of map-owned container stems")
    out, names = [], set(used)
    for entry in entries:
        if not isinstance(entry, str):
            raise ValueError("Invalid extra container stem")
        path = os.path.abspath(os.path.join(repo, entry))
        stems = [path]
        if glob.has_magic(path):
            stems = sorted(f[:-len(".utoc")] for f in glob.glob(path + ".utoc"))
            if not stems:
                raise ValueError(f"Extra container pattern matches nothing: {entry}")
        for stem in stems:
            base_name = os.path.basename(stem)
            name = base_name[len("pakchunk"):].split("-", 1)[-1][:-2]
            if (not base_name.startswith("pakchunk") or not base_name.endswith("_P") or code not in name
                    or name in names):
                raise ValueError("Extra container must have a unique map-owned package name")
            names.add(name)
            out.append((stem, name))
    return out


def extra_pack_path(stem, code):
    """Where an extra container goes in a pack folder, under its own name
    and chunk number (one with a shader library keeps its shaders): a tag
    container in `machines/`, the others beside the map's own, where `map
    pack` takes every `-<CODE>_P`."""
    base_name = os.path.basename(stem)
    if f"-MJOLNIRMACH-{code}-" in base_name:
        return os.path.join("machines", base_name)
    return base_name if base_name.endswith(f"-{code}_P") else base_name[:-2] + f"-{code}_P"


def map_tag_containers(code, m, conv):
    """Every one of them, for a map (its upgrade config `m`), one per build
    name: an upgrade's own doors (`doors`, Zanzibar's) win over the
    conversion's containers of the same name."""
    out, names = [], set()
    for path, name in door_containers(m) + gear_containers(conv) + prop_containers(m, code):
        if name not in names:
            names.add(name)
            out.append((path, name))
    return out


def pack_path(name):
    """Where a container of that build name goes in a pack folder: a tag
    container in `machines/`, the others (the machines' and gears' actors,
    named `-<CODE>`) beside the map's own."""
    if name.startswith("MJOLNIRMACH-"):
        return os.path.join("machines", f"pakchunk986-{name}_P")
    return f"pakchunk987-{name}_P"
