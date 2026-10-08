#!/usr/bin/env python3
"""Extract a classic CE map's ambient sound: its sound scenery (placed looping
emitters, such as the teleporter hum) and its background sound (the BSP's
ambient bed), with every sound they play decoded to audio files.

    ce_sounds.py <map.map> <sounds.map> <staging dir> <out dir>
    ce_sounds.py --events <sounds.map> <out dir>

The second form extracts the shared event sounds instead: the announcer and
the UI sounds the game engine's events play (EVENT_SOUNDS).

Reads Custom Edition maps (cache version 609). Their sound tags are indexed:
the map keeps the main struct and `sounds.map` holds the whole tag as the
resource `<path>` (main struct 0xA4, then the pitch ranges, 0x48 each, then
each pitch range's permutations, 0x7C each) and the samples as
`<path>__permutations`, which every permutation's data reference points into.
Looping sound tags (lsnd) are not indexed and are read from the map:
tracks at +0x3C (0xA0 each: gain +0x04, fade in/out +0x08/+0x0C, start, loop
and end sounds +0x30/+0x40/+0x50), detail sounds at +0x48 (0x68 each: sound
+0x00, random period +0x10, gain +0x18, yaw/pitch/distance bounds +0x50..).

Samples: compression 0 is 16-bit PCM, 1 Xbox ADPCM (36-byte blocks per
channel: a 4-byte header with the first sample and step index, then 32 bytes
of nibbles, 65 samples), 3 Ogg Vorbis (kept as .ogg; Unreal imports it).
A permutation continues in the one its `next permutation` names; the chain is
joined into one file.

Background sounds are the lsnd tags the BSP block references (it sits before
the tag data). Sound scenery comes from the staging's placement.json
(`kind: sound_scenery`, halo2ue), and so do the looping sounds placed objects
carry as attachments (an entry's `sounds`), each an emitter at its marker.

Writes `<out>/sounds/*.wav|.ogg` and `<out>/sounds.json`.
"""
import json
import math
import os
import struct
import sys
import wave

MEM = 0x40440000
LSND_TRACKS, LSND_DETAILS, LSND_MAX_DISTANCE = 0x3C, 0x48, 0x20
SND_MAIN, SND_PITCH, SND_PERM = 0xA4, 0x48, 0x7C

IMA_STEPS = [7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66,
             73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408,
             449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066,
             2272, 2499, 2749, 3024, 3327, 3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630,
             9493, 10442, 11487, 12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794,
             32767]
IMA_INDEX = [-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8]


def cstr(b, at):
    # A protected map's path pointers can point anywhere (or nowhere).
    if not 0 <= at < len(b):
        return ""
    end = b.find(b"\0", at)
    return b[at:end if end >= 0 else len(b)].decode("latin1")


def xbox_adpcm(data, channels):
    """Xbox IMA ADPCM to interleaved 16-bit PCM."""
    block = 36 * channels
    out = []
    for b0 in range(0, len(data) - block + 1, block):
        chans = []
        for c in range(channels):
            pred, idx = struct.unpack_from("<hB", data, b0 + 4 * c)
            idx = min(max(idx, 0), 88)
            samples = [pred]
            # Nibble data: per channel, 4-byte words interleaved after the headers.
            body = bytearray()
            for w in range(8):
                at = b0 + 4 * channels + (w * channels + c) * 4
                body += data[at:at + 4]
            for byte in body:
                for nib in (byte & 0x0F, byte >> 4):
                    step = IMA_STEPS[idx]
                    diff = step >> 3
                    if nib & 1:
                        diff += step >> 2
                    if nib & 2:
                        diff += step >> 1
                    if nib & 4:
                        diff += step
                    pred = pred - diff if nib & 8 else pred + diff
                    pred = max(-32768, min(32767, pred))
                    idx = min(max(idx + IMA_INDEX[nib], 0), 88)
                    samples.append(pred)
            chans.append(samples)
        for i in range(len(chans[0])):
            for c in range(channels):
                out.append(chans[c][i])
    return struct.pack(f"<{len(out)}h", *out)


class Map:
    def __init__(self, path, staging=None):
        self.d = open(path, "rb").read()
        self.version = struct.unpack_from("<I", self.d, 4)[0]
        self.tio = struct.unpack_from("<I", self.d, 0x10)[0]
        tap, _scen, _id, count = struct.unpack_from("<IIII", self.d, self.tio)
        self.tags = []
        for i in range(count):
            e = self.d[(tap - MEM) + self.tio + i * 32:][:32]
            cls = e[0:4][::-1].decode("latin1")
            datum, pp, doff, indexed = struct.unpack_from("<IIII", e, 12)
            path = cstr(self.d, (pp - MEM) + self.tio) if pp > MEM else ""
            self.tags.append({"cls": cls, "datum": datum, "path": path, "doff": doff, "indexed": indexed})
        # A protected map's junk classes and placeholder paths, as halo2ue
        # repaired them (staging tags.json; map-core deprotect.rs).
        fixed = staging and os.path.join(staging, "tags.json")
        if fixed and os.path.exists(fixed):
            for t, f in zip(self.tags, json.load(open(fixed, encoding="utf-8"))["tags"]):
                if t["datum"] == f["datum"]:
                    t["cls"], t["path"] = f["class"].ljust(4), f["path"]
        self.by_datum = {t["datum"]: t for t in self.tags}

    def off(self, ptr):
        return ptr - MEM + self.tio

    def tag(self, cls, path):
        return next((t for t in self.tags if t["cls"] == cls and t["path"] == path), None)

    def dep(self, at):
        """A 16-byte tag dependency: the referenced tag's path, or None."""
        datum = struct.unpack_from("<I", self.d, at + 12)[0]
        t = self.by_datum.get(datum)
        return t["path"] if t else None

    def background_sounds(self):
        """lsnd tags the BSP block (before the tag data) depends on."""
        ids = {t["datum"]: t["path"] for t in self.tags if t["cls"] == "lsnd"}
        found, i = [], 0
        while True:
            i = self.d.find(b"dnsl", i)
            if i < 0 or i >= self.tio:
                break
            path = ids.get(struct.unpack_from("<I", self.d, i + 12)[0])
            if path and path not in found:
                found.append(path)
            i += 4
        return found

    def looping_sound(self, path):
        t = self.tag("lsnd", path)
        if not t:
            return None
        o = self.off(t["doff"])
        d = self.d
        out = {"max_distance": struct.unpack_from("<f", d, o + LSND_MAX_DISTANCE)[0], "tracks": [], "details": []}
        n, ptr = struct.unpack_from("<II", d, o + LSND_TRACKS)
        for k in range(n):
            e = self.off(ptr) + k * 0xA0
            gain, fade_in, fade_out = struct.unpack_from("<fff", d, e + 4)
            out["tracks"].append({"gain": gain, "fade_in": fade_in, "fade_out": fade_out,
                                  "start": self.dep(e + 0x30), "loop": self.dep(e + 0x40),
                                  "end": self.dep(e + 0x50), "alternate_loop": self.dep(e + 0x80)})
        n, ptr = struct.unpack_from("<II", d, o + LSND_DETAILS)
        for k in range(n):
            e = self.off(ptr) + k * 0x68
            period = struct.unpack_from("<ff", d, e + 0x10)
            gain = struct.unpack_from("<f", d, e + 0x18)[0]
            yaw = struct.unpack_from("<ff", d, e + 0x50)
            pitch = struct.unpack_from("<ff", d, e + 0x58)
            dist = struct.unpack_from("<ff", d, e + 0x60)
            out["details"].append({"sound": self.dep(e), "period": list(period), "gain": gain,
                                   "yaw": list(yaw), "pitch": list(pitch), "distance": list(dist)})
        return out


class Sounds:
    def __init__(self, path):
        self.s = open(path, "rb").read()
        _type, po, ho, n = struct.unpack_from("<IIII", self.s, 0)
        self.res = {}
        for i in range(n):
            pa, size, off = struct.unpack_from("<III", self.s, ho + 12 * i)
            self.res[cstr(self.s, po + pa)] = (off, size)

    def sound(self, path):
        if path not in self.res:
            return None
        off, size = self.res[path]
        t = self.s[off:off + size]
        flags, cls, rate = struct.unpack_from("<IHH", t, 0)
        min_d, max_d = struct.unpack_from("<ff", t, 0x08)
        channels = 2 if struct.unpack_from("<H", t, 0x6C)[0] == 1 else 1
        compression = struct.unpack_from("<H", t, 0x6E)[0]
        n_pitch = struct.unpack_from("<I", t, 0x98)[0]
        perms = []
        at = SND_MAIN + n_pitch * SND_PITCH
        ranges = []
        for p in range(n_pitch):
            pr = SND_MAIN + p * SND_PITCH
            actual = struct.unpack_from("<H", t, pr + 0x2C)[0]
            count = struct.unpack_from("<I", t, pr + 0x3C)[0]
            ranges.append((actual, at, count))
            at += count * SND_PERM
        # The first pitch range only: ambience has one.
        actual, start, count = ranges[0] if ranges else (0, at, 0)
        raw = []
        for k in range(count):
            e = start + k * SND_PERM
            name = cstr(t, e)
            gain = struct.unpack_from("<f", t, e + 0x24)[0]
            comp, nxt = struct.unpack_from("<HH", t, e + 0x28)
            dsize, dflags, doff = struct.unpack_from("<III", t, e + 0x40)
            raw.append({"name": name, "gain": gain, "compression": comp, "next": nxt,
                        "data": self.s[doff:doff + dsize]})
        # Chains: the first `actual` permutations start them.
        for k in range(min(actual or count, count)):
            chain, seen, j = [], set(), k
            while j != 0xFFFF and j < count and j not in seen:
                seen.add(j)
                chain.append(raw[j])
                j = raw[j]["next"]
            perms.append(chain)
        return {"rate": 44100 if rate == 1 else 22050, "channels": channels, "compression": compression,
                "min_distance": min_d, "max_distance": max_d, "class": cls, "permutations": perms}


def safe(path):
    return path.replace("\\", "_").replace(" ", "_").replace(".", "_").lower()


def permutation_pcm(chain, info):
    """16-bit PCM for one permutation chain, or None (Ogg, IMA ADPCM)."""
    pcm = b""
    for part in chain:
        if part["compression"] == 1:
            pcm += xbox_adpcm(part["data"], info["channels"])
        elif part["compression"] == 0:
            pcm += part["data"]
        else:
            return None
    return pcm


def write_wav(path, pcm, info):
    with wave.open(path, "wb") as w:
        w.setnchannels(info["channels"])
        w.setsampwidth(2)
        w.setframerate(info["rate"])
        w.writeframes(pcm)
    return os.path.basename(path)


# The game engine's events (incidents) that CE had a sound for: the name the
# engine raises (BlamIncident.Name, seen through MJOLNIRLevelLoader's incident
# hook) and the CE sound tag. The engine's own sounds for these were cut from
# the build: 336 of the 339 sound tags its event list names do not ship.
EVENT_SOUNDS = {
    "teleporter_used": r"sound\sfx\ui\teleporter_activate",
    # A health pack picked up: blam_megalo::powerups raises Race's
    # lap_complete for it (the incident recharge_health never reaches Unreal).
    "lap_complete": r"sound\sfx\ui\pickup_health",
    "respawn_tick": r"sound\sfx\ui\countdown_for_respawn",
    "respawn_final_tick": r"sound\sfx\ui\player_respawn",
    "hill_moved": r"sound\sfx\ui\hill_move",
    "slayer_start": r"sound\dialog\multiplayer1\slayer",
    "koth_game_start": r"sound\dialog\multiplayer1\king_of_the_hill",
    "ball_game_start": r"sound\dialog\multiplayer1\oddball",
    "ctf_game_start": r"sound\dialog\multiplayer1\capture_the_flag",
    "race_game_start": r"sound\dialog\multiplayer1\race",
    "multikill_x2": r"sound\dialog\multiplayer1\double_kill",
    "multikill_x3": r"sound\dialog\multiplayer1\triple_kill",
    "multikill_x4": r"sound\dialog\multiplayer1\killtacular",
    "5_in_a_row": r"sound\dialog\multiplayer1\killing_spree",
    "10_in_a_row": r"sound\dialog\multiplayer1\running_riot",
    "one_minute_win": r"sound\dialog\multiplayer1\one_minute_to_win",
    "half_minute_win": r"sound\dialog\multiplayer1\30_seconds_to_win",
    "game_over": r"sound\dialog\multiplayer1\game_over",
    "hill_contested": r"sound\dialog\multiplayer1\hill_contested",
    "hill_controlled": r"sound\dialog\multiplayer1\hill_controlled",
    "ball_spawned": r"sound\dialog\multiplayer1\play_ball",
    # CTF lines name a team. The CTF variant raises its flag incidents with
    # the flag's team as the value (0 red, 1 blue), and the loader looks up
    # "<event>:<value>" first: a red flag taken means blue has the flag.
    "flag_grabbed:0": r"sound\dialog\multiplayer1\blue_team_has_the_flag",
    "flag_grabbed:1": r"sound\dialog\multiplayer1\red_team_has_the_flag",
    "flag_scored:0": r"sound\dialog\multiplayer1\blue_team_score",
    "flag_scored:1": r"sound\dialog\multiplayer1\red_team_score",
    "flag_reset:0": r"sound\dialog\multiplayer1\red_team_flag_returned",
    "flag_reset:1": r"sound\dialog\multiplayer1\blue_team_flag_returned",
    "flag_recovered:0": r"sound\dialog\multiplayer1\red_team_flag_returned",
    "flag_recovered:1": r"sound\dialog\multiplayer1\blue_team_flag_returned",
}
# Every multiplayer announcer line CE has, extracted whether or not an event
# plays it yet (team lines need the event's team, the vehicle callouts a
# trigger of their own).
ANNOUNCER_DIR = "sound\\dialog\\multiplayer1\\"
# Where build_ce_sounds.py imports the event sounds (MJ_CE_SOUND_ROOT).
EVENTS_ROOT = "/Game/MJOLNIR/Sounds/Events"


def extract_events(sounds_path, out):
    """The shared event sounds: every CE announcer line and the UI sounds
    EVENT_SOUNDS names, one-shot WAVs, and events.json mapping each event to
    its wave."""
    snd = Sounds(sounds_path)
    wanted = sorted(set(EVENT_SOUNDS.values())
                    | {k for k in snd.res if k.startswith(ANNOUNCER_DIR) and not k.endswith("__permutations")})
    os.makedirs(os.path.join(out, "sounds"), exist_ok=True)
    sounds = {}
    for path in wanted:
        info = snd.sound(path)
        if not info:
            print(f"  no {path} in sounds.map", file=sys.stderr)
            continue
        files = []
        for k, chain in enumerate(info["permutations"]):
            base = os.path.join(out, "sounds", f"{safe(path)}_v{k}")
            if chain[0]["compression"] == 3:
                # The announcer is Ogg Vorbis; Unreal's importer decodes it.
                open(base + ".ogg", "wb").write(b"".join(p["data"] for p in chain))
                files.append(os.path.basename(base + ".ogg"))
                continue
            pcm = permutation_pcm(chain, info)
            if pcm:
                files.append(write_wav(base + ".wav", pcm, info))
        sounds[path] = {"files": files, "rate": info["rate"], "channels": info["channels"]}
    events = {e: [os.path.splitext(f)[0] for f in sounds[p]["files"]] for e, p in EVENT_SOUNDS.items() if p in sounds}
    json.dump({"events": events, "sounds": sounds}, open(os.path.join(out, "sounds.json"), "w", encoding="utf-8"),
              indent=1)
    # MJOLNIRLevelLoader's table (mods/MJOLNIRLevelLoader/events.json): each
    # event's waves as imported under EVENTS_ROOT by build_ce_sounds.py.
    table = {e: [f"{EVENTS_ROOT}/{w}.{w}" for w in waves] for e, waves in sorted(events.items())}
    json.dump(table, open(os.path.join(out, "events.json"), "w", encoding="utf-8"), indent=1)
    print(f"{len(sounds)} sound(s), {len(events)} event(s) -> {os.path.join(out, 'sounds.json')}, events.json")


def object_rotation(yaw, pitch, roll):
    """CE object rotation, row-major (as gen_ce_level.py has it): yaw about
    z, then pitch and roll about the world's y and x axes."""
    cy, sy, cp, sp, cr, sr = (math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch),
                              math.cos(roll), math.sin(roll))
    rz = [[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]]
    ry = [[cp, 0, -sp], [0, 1, 0], [sp, 0, cp]]
    rx = [[1, 0, 0], [0, cr, -sr], [0, sr, cr]]

    def mul(a, b):
        return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    return mul(mul(rx, ry), rz)


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--events":
        return extract_events(sys.argv[2], sys.argv[3])
    map_path, sounds_path, staging, out = sys.argv[1:5]
    m, snd = Map(map_path, staging), Sounds(sounds_path)
    if m.version != 609:
        sys.exit(f"{map_path}: cache version {m.version}; only Custom Edition (609) maps are read")
    placement = json.load(open(os.path.join(staging, "placement.json"), encoding="utf-8"))
    emitters = [{"pos": e["pos"], "rot": e.get("rot", [0, 0, 0]), "sound": e.get("sound") or e["asset"]}
                for e in placement["entries"] if e.get("kind") == "sound_scenery"]
    # Looping sounds placed objects carry (halo2ue's `sounds`: the Covenant
    # shield generator's and uplink's hum, the teleporters' loop, klaxons),
    # at the attachment's marker.
    for e in placement["entries"]:
        if e.get("kind") == "sound_scenery":
            continue
        r = object_rotation(*(e.get("rot") or [0, 0, 0]))
        for s in e.get("sounds") or []:
            o = s.get("offset") or [0, 0, 0]
            pos = [e["pos"][k] + sum(r[k][j] * o[j] for j in range(3)) for k in range(3)]
            emitters.append({"pos": pos, "rot": e.get("rot", [0, 0, 0]), "sound": s["sound"],
                             "attached_to": e.get("asset")})
    background = m.background_sounds()

    loops = {}
    for path in [e["sound"] for e in emitters] + background:
        if path not in loops:
            ls = m.looping_sound(path)
            if ls:
                loops[path] = ls
    wanted, looped = [], set()
    for ls in loops.values():
        for t in ls["tracks"]:
            wanted += [s for s in (t["start"], t["loop"], t["end"], t["alternate_loop"]) if s]
            looped.update(s for s in (t["loop"], t["alternate_loop"]) if s)
        wanted += [dd["sound"] for dd in ls["details"] if dd["sound"]]

    os.makedirs(os.path.join(out, "sounds"), exist_ok=True)
    sounds = {}
    for path in dict.fromkeys(wanted):
        info = snd.sound(path)
        if not info:
            print(f"  no {path} in sounds.map", file=sys.stderr)
            continue
        # Names end in a letter-and-digit (`_v0`), never `_<digits>`, which
        # Unreal would read as an FName number.
        files, joined, ogg = [], b"", None
        for k, chain in enumerate(info["permutations"]):
            base = os.path.join(out, "sounds", f"{safe(path)}_v{k}")
            if chain[0]["compression"] == 3:
                open(base + ".ogg", "wb").write(chain[0]["data"])
                files.append(os.path.basename(base + ".ogg"))
                ogg = ogg or files[-1]
                continue
            pcm = permutation_pcm(chain, info)
            if pcm is None:
                continue
            files.append(write_wav(base + ".wav", pcm, info))
            joined += pcm
        sounds[path] = {k: info[k] for k in ("rate", "channels", "compression", "min_distance", "max_distance")}
        sounds[path]["files"] = files
        if path in looped:
            # CE plays a loop's permutations back to back; joined, they make
            # one seamless loop that varies as CE's does.
            sounds[path]["loop"] = (write_wav(os.path.join(out, "sounds", f"{safe(path)}_loop.wav"), joined, info)
                                    if joined else ogg)
        print(f"  {path}: {len(files)} permutation(s), {info['rate']} Hz, "
              f"{info['channels']} ch, compression {info['compression']}")

    json.dump({"emitters": emitters, "background": background, "loops": loops, "sounds": sounds},
              open(os.path.join(out, "sounds.json"), "w", encoding="utf-8"), indent=1)
    print(f"{len(emitters)} emitter(s), {len(background)} background sound(s), {len(sounds)} sound(s) "
          f"-> {os.path.join(out, 'sounds.json')}")


if __name__ == "__main__":
    main()
