"""Write TST's CE scenario from authored placements, using Halo Toolset 425.

Run with normal Python (Blender is not needed)::

    python levels/test/tst/build_scenario.py --placements levels/test/tst/placements.json

Positions in the JSON are metres in the Blender scene's X/Y/Z axes. One
Halo world unit is 3.048 metres; rotations are degrees. Tag paths are relative
to HEK/tags, without extensions. The output references the BSP compiled from
tst.jms. Run this after ``tool structure`` and before lightmaps/cache build.

Only the tutorial scenario's empty field structure is reused. Its placements,
scripts, editor state, BSP and sky references are replaced. Stock tag assets
remain in the HEK installation and are not copied into the source repository.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys


METRES_PER_WORLD_UNIT = 3.048
DEFAULT_HEK = Path(r"C:\haloce\hek")
DEFAULT_ADDON = Path(r"C:\haloce\tools\halo-blender-425\addons\io_scene_halo")
TST_TAG = r"levels\test\tst\tst"
MODES = {"none": 0, "ctf": 1, "slayer": 2, "all": 12}
GROUP_EXTENSIONS = {
    "scen": "scenery", "vehi": "vehicle", "itmc": "item_collection",
    "lifi": "device_light_fixture", "sky ": "sky", "sbsp": "scenario_structure_bsp",
}


def load_toolset(addon: Path):
    interface_dir = addon / "file_tag" / "tag_interface"
    if not (interface_dir / "tag_interface.py").is_file():
        raise FileNotFoundError(f"Halo Toolset 425 tag interface not found: {interface_dir}")
    sys.path.insert(0, str(interface_dir))
    import tag_common
    import tag_interface
    from tag_definitions import h1

    # The upstream parser normally dumps hundreds of merged XML files.
    h1.DUMP_XML = False
    definitions = h1.generate_defs(tag_common.h1_defs_directory, "")
    return tag_interface, tag_common, definitions


def enum(value: int) -> dict:
    return {"type": "ShortEnum", "value": value, "value name": ""}


def tag_reference(group: str, path: str) -> dict:
    return {"group name": group, "unk1": 0, "length": len(path), "unk2": -1,
            "path": path.replace("/", "\\")}


def world_position(position_m) -> list[float]:
    if len(position_m) != 3 or not all(math.isfinite(float(v)) for v in position_m):
        raise ValueError(f"Expected three finite metre coordinates, got {position_m!r}")
    return [float(v) / METRES_PER_WORLD_UNIT for v in position_m]


def mode_fields(modes=("ctf", "slayer")) -> dict:
    if not 1 <= len(modes) <= 4:
        raise ValueError("Each placement needs between one and four game modes")
    values = [MODES[m] for m in modes]
    return {f"type {i}": enum(values[i] if i < len(values) else 0) for i in range(4)}


def team_index(value) -> int:
    team = {"red": 0, "blue": 1}.get(value, value)
    if team not in (0, 1):
        raise ValueError(f"TST team must be red/0 or blue/1, got {value!r}")
    return int(team)


def object_placement(item: dict, palette_index: int) -> dict:
    return {
        "type": palette_index, "name": -1, "not placed": 0,
        "desired permutation": int(item.get("permutation", 0)),
        "position": world_position(item["position_m"]),
        "rotation": [float(item.get("yaw_degrees", 0)),
                     float(item.get("pitch_degrees", 0)),
                     float(item.get("roll_degrees", 0))],
        "bsp indices": 0, "appearance player index": 0,
    }


def build_tag(template: dict, placements: dict, tags_dir: Path) -> dict:
    result = copy.deepcopy(template)
    result["TagName"] = TST_TAG + ".scenario"
    data = result["Data"]
    for key, value in list(data.items()):
        if isinstance(value, list):
            data[key] = []
        elif isinstance(value, dict) and "encoded" in value:
            # No tutorial editor state, compiled scripts or script strings.
            data[key] = {"length": 0, "unk1": 0, "unk2": 0, "unk3": 0,
                         "unk4": 0, "encoded": ""}
        elif isinstance(value, dict) and "group name" in value:
            data[key] = tag_reference(value["group name"], "")

    data["type"] = enum(1)  # multiplayer
    data["flags"] = 0
    data["local north"] = 0.0
    data["skies"] = [{"sky": tag_reference("sky ", placements.get(
        "sky", r"sky\clear afternoon\clear afternoon"))}]
    data["structure bsps"] = [{"bsp start": 0, "bsp size": 0, "bsp address": 0,
                               "structure bsp": tag_reference("sbsp", TST_TAG)}]

    def add_object(item, block, palette, group):
        path = item["tag"].replace("/", "\\")
        existing = [v["name"]["path"] for v in data[palette]]
        if path not in existing:
            data[palette].append({"name": tag_reference(group, path)})
            existing.append(path)
        obj = object_placement(item, existing.index(path))
        data[block].append(obj)
        return obj

    for item in placements.get("scenery", []):
        add_object(item, "scenery", "scenery palette", "scen")

    for item in placements.get("vehicles", []):
        obj = add_object(item, "vehicles", "vehicle palette", "vehi")
        obj.pop("bsp indices")  # Vehicles use the unit placement layout.
        obj.update({"body vitality": 1.0, "flags": 0,
                    "multiplayer team index": team_index(item.get("team", 0)),
                    # Default and permitted for CTF and Slayer.
                    "multiplayer spawn flags": 0x0303})

    for item in placements.get("spawns", []):
        data["player starting locations"].append({
            "position": world_position(item["position_m"]),
            "facing": float(item.get("yaw_degrees", 0)),
            "team index": team_index(item["team"]), "bsp index": 0,
            **mode_fields(item.get("modes", ["ctf", "slayer"])),
        })

    def add_flag(position_m, yaw, kind, usage):
        data["netgame flags"].append({
            "position": world_position(position_m), "facing": float(yaw),
            "type": enum(kind), "usage id": int(usage),
            "weapon group": tag_reference("itmc", ""),
        })

    for item in placements.get("flags", []):
        add_flag(item["position_m"], item.get("yaw_degrees", 0), 0,
                 team_index(item["team"]))

    for item in placements.get("pickups", []):
        data["netgame equipment"].append({
            "flags": 0, **mode_fields(item.get("modes", ["ctf", "slayer"])),
            "team index": 0, "spawn time": int(item.get("spawn_seconds", 30)),
            "unknown_ffffffff": 0xFFFFFFFF,
            "position": world_position(item["position_m"]),
            "facing": float(item.get("yaw_degrees", 0)),
            "item collection": tag_reference("itmc", item["tag"]),
        })

    # CE reads starting equipment by mode. Both modes begin with the same kit.
    starting = {"flags": 0, **mode_fields()}
    weapons = placements.get("starting_weapons", [
        r"item collections\single weapons\assault rifle",
        r"item collections\single weapons\pistol",
    ])
    if len(weapons) > 6:
        raise ValueError("CE starting equipment supports at most six item collections")
    for index in range(6):
        starting[f"item collection {index + 1}"] = tag_reference(
            "itmc", weapons[index] if index < len(weapons) else "")
    data["starting equipment"] = [starting]

    channels = set()
    for item in placements.get("teleporters", []):
        channel = int(item.get("channel", 0))
        if channel in channels:
            raise ValueError(f"Duplicate teleporter channel: {channel}")
        channels.add(channel)
        add_flag(item["from_m"], item.get("from_yaw_degrees", 0), 6, channel)
        add_flag(item["to_m"], item.get("to_yaw_degrees", 0), 7, channel)
        if item.get("scenery", True):
            for side in ("from", "to"):
                add_object({"tag": r"scenery\teleporter_base\teleporter_base",
                            "position_m": item[f"{side}_m"],
                            "yaw_degrees": item.get(f"{side}_yaw_degrees", 0)},
                           "scenery", "scenery palette", "scen")

    for item in placements.get("lights", []):
        obj = add_object(item, "light fixtures", "light fixture palette", "lifi")
        color = item.get("color", [1.0, 0.88, 0.72])
        obj.update({"power group": -1, "position group": -1, "device flags": 0,
                    "color": dict(zip(("R", "G", "B"), color)),
                    "intensity": float(item.get("intensity", 1.0)),
                    "falloff angle": float(item.get("falloff_degrees", 45)),
                    "cutoff angle": float(item.get("cutoff_degrees", 90))})

    if {v["usage id"] for v in data["netgame flags"] if v["type"]["value"] == 0} != {0, 1}:
        raise ValueError("TST requires a red and a blue CTF flag")
    if {v["team index"] for v in data["player starting locations"]} != {0, 1}:
        raise ValueError("TST requires player starts for both teams")

    missing = []

    def check_references(value):
        if isinstance(value, dict):
            if "group name" in value and value.get("path"):
                group, path = value["group name"], value["path"]
                # Structure compilation creates this reference before cache build.
                if group != "sbsp":
                    file = tags_dir / (path + "." + GROUP_EXTENSIONS[group])
                    if not file.is_file():
                        missing.append(str(file))
            else:
                for child in value.values():
                    check_references(child)
        elif isinstance(value, list):
            for child in value:
                check_references(child)

    check_references(data)
    if missing:
        raise FileNotFoundError("Missing HEK tags:\n" + "\n".join(sorted(set(missing))))
    return result


def verify_roundtrip(expected: dict, actual: dict):
    """Check the authored gameplay fields survived the binary tag writer."""
    def compare(want, got, location):
        if isinstance(want, dict):
            for key, value in want.items():
                if key in {"unk1", "unk2", "length", "value name"}:
                    continue
                compare(value, got[key], f"{location}/{key}")
        elif isinstance(want, list):
            if len(want) != len(got):
                raise ValueError(f"Roundtrip count differs: {location}")
            for index, (a, b) in enumerate(zip(want, got)):
                compare(a, b, f"{location}/{index}")
        elif isinstance(want, float):
            if not math.isclose(want, got, rel_tol=1e-6, abs_tol=1e-5):
                raise ValueError(f"Roundtrip value differs: {location}: {want} != {got}")
        elif want != got:
            raise ValueError(f"Roundtrip value differs: {location}: {want!r} != {got!r}")

    for key in ("type", "skies", "scenery", "scenery palette", "vehicles",
                "vehicle palette", "player starting locations", "netgame flags",
                "netgame equipment", "starting equipment", "light fixtures",
                "light fixture palette", "structure bsps"):
        compare(expected["Data"][key], actual["Data"][key], key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--placements", type=Path, default=Path(__file__).with_name("placements.json"))
    parser.add_argument("--hek", type=Path, default=DEFAULT_HEK)
    parser.add_argument("--addon", type=Path, default=DEFAULT_ADDON)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    tags_dir = args.hek / "tags"
    template_path = tags_dir / "levels/test/tutorial/tutorial.scenario"
    output = args.output or tags_dir / "levels/test/tst/tst.scenario"
    interface, common, definitions = load_toolset(args.addon)
    kwargs = {"engine_tag": common.EngineTag.H1Latest.value}
    template = interface.read_file(definitions, str(tags_dir), str(template_path), **kwargs)
    placements = json.loads(args.placements.read_text(encoding="utf-8-sig"))
    authored = build_tag(template, placements, tags_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Upstream write_file mutates its header dictionary; keep expected data intact.
    interface.write_file(definitions, copy.deepcopy(authored), interface.obfuscation_buffer_prepare(),
                         str(output), **kwargs)
    actual = interface.read_file(definitions, str(tags_dir), str(output), **kwargs)
    verify_roundtrip(authored, actual)
    counts = {key: len(actual["Data"][key]) for key in (
        "scenery", "vehicles", "player starting locations", "netgame flags",
        "netgame equipment", "light fixtures")}
    print(json.dumps({"scenario": str(output.resolve()), "counts": counts,
                      "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                      "roundtrip": "passed"}, indent=2))


if __name__ == "__main__":
    main()
