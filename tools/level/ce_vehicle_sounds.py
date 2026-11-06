#!/usr/bin/env python3
"""A Custom Edition vehicle's own sounds, for MJOLNIRLevelLoader to play.

    ce_vehicle_sounds.py <map> <sounds.map> <vehicle tag> <out dir> [--staging dir]
        [--code VHT] [--name mongoose] [--skip <lsnd>] [--merge vehicle_sounds.json] [--cook]

A tag in this game can only point at a shipped Wwise event, so CE samples cannot
ride the vehicle's tags. They play through Unreal's audio engine instead, as a
map's ambient sound does: this decodes them, build_ce_sounds.py makes them
SoundWaves beside the vehicle's materials, and
mods/MJOLNIRLevelLoader/Scripts/vehicle_sounds.lua plays them on the vehicle.

Every looping sound the vehicle carries as an attachment is read. What starts it
is the attachment's scale (A to D out) and that function's input on the vehicle:
`engine` (engine hack, 35) runs while the driver's seat is taken, and its value
bends the pitch; `crouch` (11) runs while the driver holds crouch, which is how
CE builds a horn. An attachment on any other input is reported and left out.

Sound tags come from sounds.map or from the map itself: a map keeps its custom
sounds whole, with the samples at the permutation's file offset. Each pitch
range of a loop becomes one looping wave, its permutations back to back. The
game runs all of them and fades between them, where CE switches at a boundary.

The suspension, crash and foot sounds are listed, not extracted: on a Warthog
clone the donor's tags already play them, and a CE vehicle often names the same
ones (the Mongoose does). `kept` in the output says what the CE vehicle names.

Writes to <out dir>:
- `sounds/*` and `sounds.json`, in the shape build_ce_sounds.py imports;
- `vehicle_sounds.json`: { "<class>": { top_speed, sounds: [...], kept } }, the
  loader's table, read from beside the level file. --merge starts from another
  table, so one file serves every vehicle of a map.

--cook imports the waves and cooks the map's chunk, and copies it to <out dir> as
pakchunk985-MJOLNIRCOOK-<CODE>_P: the same container ce_vehicle_materials.py
makes, the vehicle's materials still in it. Waves go under
/Game/MJOLNIR/Maps/<CODE>/Vehicles, the one folder its chunk check allows.

--skip drops a looping sound by tag path. Yoyorast's Mongoose has one that
sometimes plays a song clip when the engine starts: `protected\\lsnd\\1057`.
"""
import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ce_sounds as ce  # noqa: E402

CM = 304.8
TICKS = 30
# The vehicle's definition, from the tag's start.
ATTACHMENTS, ATTACHMENT_SIZE = 0x140, 72
FORWARD_SPEED, FUNCTION_INPUTS = 0x2F8, 0x31C
KEPT = {"suspension": 0x3B0, "crash": 0x3C0, "foot": 0x3D0, "effect": 0x3E0}
# Vehicle function inputs (A to D in) a sound can follow.
DRIVES = {35: "engine", 11: "crouch"}


def read_sound(m, snd, path):
    """Any sound tag, every pitch range: ce_sounds.Sounds.sound's fields plus
    `pitch` (the scale's bounds) and `ranges` of { name, natural, low, high,
    chains }, a chain being permutations in ce_sounds' shape."""
    t = m.tag("snd!", path)
    if t is None:
        sys.exit(f"no sound tag {path}")
    if t["indexed"]:
        if path not in snd.res:
            sys.exit(f"{path} is not in sounds.map")
        off, size = snd.res[path]
        body, base = snd.s[off:off + size], 0
        count = struct.unpack_from("<I", body, 0x98)[0]
        at = ce.SND_MAIN + count * ce.SND_PITCH
        ranges = []
        for p in range(count):
            e = ce.SND_MAIN + p * ce.SND_PITCH
            n = struct.unpack_from("<I", body, e + 0x3C)[0]
            ranges.append((e, at, n))
            at += n * ce.SND_PERM
    else:
        base = m.off(t["doff"])
        body = m.d
        count, ptr = struct.unpack_from("<II", body, base + 0x98)
        ranges = []
        for p in range(count):
            e = m.off(ptr) + p * ce.SND_PITCH
            n, perms = struct.unpack_from("<II", body, e + 0x3C)
            ranges.append((e, m.off(perms), n))
    flags, cls, rate = struct.unpack_from("<IHH", body, base)
    near, far = struct.unpack_from("<ff", body, base + 0x08)
    info = {"rate": 44100 if rate == 1 else 22050, "class": cls, "min_distance": near, "max_distance": far,
            "channels": 2 if struct.unpack_from("<H", body, base + 0x6C)[0] == 1 else 1,
            "compression": struct.unpack_from("<H", body, base + 0x6E)[0],
            "pitch": [struct.unpack_from("<f", body, base + 0x44)[0], struct.unpack_from("<f", body, base + 0x5C)[0]],
            "ranges": []}
    for e, start, n in ranges:
        raw = []
        for k in range(n):
            q = start + k * ce.SND_PERM
            comp, nxt = struct.unpack_from("<HH", body, q + 0x28)
            size, dflags, offset = struct.unpack_from("<III", body, q + 0x40)
            # Bit 0: the samples are in sounds.map.
            source = snd.s if dflags & 1 else m.d
            raw.append({"name": ce.cstr(body, q), "compression": comp, "next": nxt,
                        "data": source[offset:offset + size]})
        chains = []
        actual = struct.unpack_from("<H", body, e + 0x2C)[0]
        for k in range(min(actual or n, n)):
            chain, seen, j = [], set(), k
            while j != 0xFFFF and j < n and j not in seen:
                seen.add(j)
                chain.append(raw[j])
                j = raw[j]["next"]
            chains.append(chain)
        low, high = struct.unpack_from("<ff", body, e + 0x24)
        info["ranges"].append({"name": ce.cstr(body, e), "natural": struct.unpack_from("<f", body, e + 0x20)[0],
                               "low": low, "high": high, "chains": chains})
    return info


class Writer:
    """Wave files and build_ce_sounds.py's manifest."""

    def __init__(self, out, root):
        self.dir, self.root, self.sounds = os.path.join(out, "sounds"), root, {}
        os.makedirs(self.dir, exist_ok=True)

    def path(self, stem):
        return f"{self.root}/{stem}.{stem}"

    def one_shots(self, stem, info):
        """The permutations of a start or end sound: wave paths and the longest
        one's seconds. Unreal reads a name's trailing `_<digits>` as a number,
        so a name ends in a letter and digit. A silent permutation stays, so
        the odds of the real ones are CE's."""
        waves, seconds = [], 0.0
        for k, chain in enumerate(c for r in info["ranges"] for c in r["chains"]):
            name = f"{stem}_v{k}"
            if chain[0]["compression"] == 3:
                # Length unknown here: Unreal decodes it.
                with open(os.path.join(self.dir, name + ".ogg"), "wb") as f:
                    f.write(b"".join(p["data"] for p in chain))
                self.sounds[name] = {"files": [name + ".ogg"]}
            else:
                pcm = ce.permutation_pcm(chain, info)
                ce.write_wav(os.path.join(self.dir, name + ".wav"), pcm, info)
                self.sounds[name] = {"files": [name + ".wav"]}
                seconds = max(seconds, len(pcm) / (2 * info["channels"] * info["rate"]))
            waves.append(self.path(name))
        return waves, round(seconds, 3)

    def loop(self, stem, chains, info):
        """One pitch range as one looping wave."""
        name = stem + "_loop"
        if chains[0][0]["compression"] == 3:
            with open(os.path.join(self.dir, name + ".ogg"), "wb") as f:
                f.write(b"".join(p["data"] for p in chains[0]))
            self.sounds[name] = {"files": [], "loop": name + ".ogg"}
        else:
            pcm = b"".join(ce.permutation_pcm(c, info) for c in chains)
            ce.write_wav(os.path.join(self.dir, name + ".wav"), pcm, info)
            self.sounds[name] = {"files": [], "loop": name + ".wav"}
        return self.path(name)


def attachments(m, at):
    """(index, lsnd path, scale 0 to 4) of each looping sound attached."""
    n, ptr = struct.unpack_from("<II", m.d, at + ATTACHMENTS)
    for i in range(n):
        e = m.off(ptr) + i * ATTACHMENT_SIZE
        # By the tag named, not the group in the reference: a protected map's
        # groups can be junk.
        t = m.by_datum.get(struct.unpack_from("<I", m.d, e + 12)[0])
        if t and t["cls"] == "lsnd":
            yield i, t["path"], struct.unpack_from("<H", m.d, e + 0x30)[0]


def distance(track_info, lsnd):
    """Inner radius and falloff in cm, from the sound's bounds, or the looping
    sound's reach when it has none."""
    near, far = track_info["min_distance"], track_info["max_distance"]
    if far <= 0:
        near, far = 0.0, lsnd["max_distance"]
    return round(near * CM, 1), round(max(far - near, 0.1) * CM, 1)


def vehicle(m, snd, tag, writer, name, skip):
    at = m.off(m.tag("vehi", tag)["doff"])
    inputs = struct.unpack_from("<4H", m.d, at + FUNCTION_INPUTS)
    entry = {"top_speed": round(struct.unpack_from("<f", m.d, at + FORWARD_SPEED)[0] * TICKS * CM, 1),
             "sounds": [], "kept": {}}
    for i, path, scale in attachments(m, at):
        drive = DRIVES.get(inputs[scale - 1]) if 1 <= scale <= 4 else None
        if path in skip:
            print(f"  attachment {i}: {path} skipped")
            continue
        if not drive:
            print(f"  attachment {i}: {path} follows input {inputs[scale - 1] if 1 <= scale <= 4 else None}: left out")
            continue
        lsnd = m.looping_sound(path)
        if lsnd["details"]:
            print(f"  attachment {i}: {len(lsnd['details'])} detail sound(s) left out")
        for t, track in enumerate(lsnd["tracks"]):
            stem = f"{name}_a{i}" + (f"t{t}" if t else "")
            one = {"drive": drive, "source": path, "gain": round(track["gain"], 3),
                   "fade_in": track["fade_in"], "fade_out": track["fade_out"],
                   "start": [], "start_s": 0.0, "end": [], "end_s": 0.0, "ranges": [], "pitch": [1.0, 1.0]}
            shape = None
            for key in ("start", "end"):
                if track[key]:
                    info = read_sound(m, snd, track[key])
                    shape = shape or info
                    one[key], one[key + "_s"] = writer.one_shots(f"{stem}_{key}", info)
            if track["loop"]:
                info = read_sound(m, snd, track["loop"])
                shape = info
                one["pitch"] = info["pitch"]
                for r in sorted(info["ranges"], key=lambda r: r["low"]):
                    wave = writer.loop(f"{stem}_{ce.safe(r['name'])}", r["chains"], info)
                    one["ranges"].append({"name": r["name"], "wave": wave, "natural": round(r["natural"], 4),
                                          "low": round(r["low"], 4), "high": round(r["high"], 4)})
            if shape is None:
                continue
            one["inner"], one["falloff"] = distance(shape, lsnd)
            entry["sounds"].append(one)
            print(f"  attachment {i}: {path}, {drive}: {len(one['ranges'])} loop(s), "
                  f"{len(one['start'])} start, {len(one['end'])} end, gain {one['gain']}, "
                  f"{one['inner']:.0f} + {one['falloff']:.0f} cm")
    for key, offset in KEPT.items():
        path = m.dep(at + offset)
        if path:
            entry["kept"][key] = path
    return entry


def cook(out, root, code, mjolnir):
    """The waves into the project and the map's chunk out of it."""
    from ce_material_spec import cook_chunk
    from ce_vehicle_materials import REPO, STAGED, powershell
    paks = os.environ.get("HCE_PAKS") or sys.exit("set HCE_PAKS")
    ue = os.path.join(REPO, "tools", "ue")
    report = powershell(os.path.join(ue, "editor_cmd.ps1"), "-Script", "Scripts/build_ce_sounds.py",
                        env={"MJ_CE_SOUNDS": os.path.abspath(out), "MJ_CE_SOUND_ROOT": root})
    print(report.strip()[-300:])
    result = powershell(os.path.join(ue, "cook.ps1"), env={"MJOLNIR": mjolnir})
    if "cook exit 0" not in result or "BUILD SUCCESSFUL" not in result:
        sys.exit("the cook failed: see unreal/MJOLNIRMaterials/Saved_cook.log; no chunk copied")
    chunk = cook_chunk(code)
    listing = subprocess.run([os.path.join(REPO, "target", "release", "examples", "container_ls.exe"), STAGED,
                              f"pakchunk{chunk}-"], capture_output=True, text=True).stdout
    if not re.search(r"Sounds/.*\.uasset", listing):
        sys.exit(f"no waves in chunk {chunk}:\n{listing}")
    stem = f"pakchunk985-MJOLNIRCOOK-{code}_P"
    for e in ("utoc", "ucas"):
        shutil.copyfile(os.path.join(STAGED, f"pakchunk{chunk}-Windows.{e}"), os.path.join(out, f"{stem}.{e}"))
    # The game mounts a .utoc/.ucas pair only beside a .pak.
    shutil.copyfile(os.path.join(paks, "pakchunk115-Windows.pak"), os.path.join(out, f"{stem}.pak"))
    print(f"pakchunk{chunk} -> {os.path.join(out, stem)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("map")
    ap.add_argument("sounds_map")
    ap.add_argument("tag", help="the vehi tag's path in the map")
    ap.add_argument("out")
    ap.add_argument("--staging", help="halo2ue staging of a protected map: its tags.json names the tags")
    ap.add_argument("--code", default="VHT")
    ap.add_argument("--name", default="mongoose")
    ap.add_argument("--skip", action="append", default=[], metavar="LSND", help="leave out this looping sound")
    ap.add_argument("--merge", help="an existing vehicle_sounds.json to add this vehicle to")
    ap.add_argument("--cook", action="store_true", help="import, cook and copy the chunk")
    ap.add_argument("--mjolnir", default=os.path.join(HERE, "..", "..", "target", "release", "mjolnir.exe"))
    a = ap.parse_args()
    m, snd = ce.Map(a.map, a.staging), ce.Sounds(a.sounds_map)
    if m.version != 609:
        sys.exit(f"{a.map}: cache version {m.version}; only Custom Edition (609) maps are read")
    if not m.tag("vehi", a.tag):
        sys.exit(f"no vehicle {a.tag} in {a.map}")
    os.makedirs(a.out, exist_ok=True)
    root = f"/Game/MJOLNIR/Maps/{a.code}/Vehicles/Sounds/{a.name.capitalize()}"
    writer = Writer(a.out, root)
    entry = vehicle(m, snd, a.tag, writer, a.name, set(a.skip))
    print(f"  kept: {entry['kept']}")
    with open(os.path.join(a.out, "sounds.json"), "w", encoding="utf-8") as f:
        json.dump({"sounds": writer.sounds}, f, indent=1)
    table = json.load(open(a.merge, encoding="utf-8")) if a.merge else {}
    # ce_vehicle.py's Blueprint: BP_<CODE><Name>, its class with _C.
    key = f"BP_{a.code}{a.name.capitalize()}_C"
    # ce_vehicle_lights.py's entry is not this tool's to drop.
    if "lights" in table.get(key, {}):
        entry["lights"] = table[key]["lights"]
    table[key] = entry
    path = os.path.join(a.out, "vehicle_sounds.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(table, f, indent=1)
    print(f"{len(writer.sounds)} wave(s) under {root} -> {path}")
    if a.cook:
        cook(a.out, root, a.code, os.path.abspath(a.mjolnir))


if __name__ == "__main__":
    main()
