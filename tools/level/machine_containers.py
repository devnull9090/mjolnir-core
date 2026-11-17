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
    """Halo 2's turning parts' machines (h2_machines.py, in the conversion's
    `machines` folder): their tags' containers and their actors'
    (pakchunk987-MJOLNIRGEAR)."""
    out = []
    for utoc in sorted(glob.glob(os.path.join(conv, "machines", "pakchunk98[67]-MJOLNIR*_P.utoc"))):
        stem = os.path.basename(utoc)[:-len("_P.utoc")]
        if "-MJOLNIRMACH-" in stem or "-MJOLNIRGEAR-" in stem:
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


def map_tag_containers(code, m, conv):
    """Every one of them, for a map (its upgrade config `m`)."""
    return door_containers(m) + gear_containers(conv) + prop_containers(m, code)


def pack_path(name):
    """Where a container of that build name goes in a pack folder: a tag
    container in `machines/`, the others (the machines' and gears' actors,
    named `-<CODE>`) beside the map's own."""
    if name.startswith("MJOLNIRMACH-"):
        return os.path.join("machines", f"pakchunk986-{name}_P")
    return f"pakchunk987-{name}_P"
