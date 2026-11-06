#!/usr/bin/env python3
"""A Wwise bank of our own, built from shipped banks' records.

Everything structural is copied from shipped banks: the header from the smallest
bank, the Sound, Action and Event records from the Warthog's horn, the parent
mixers and the attenuation from the Burden of Proof bank (which, like every
vehicle bank, repeats the same parent ids). Only ids, the source fields and child
lists change. Media is embedded (DIDX/DATA), PCM, mono 48 kHz, in the layout of
shipped embedded PCM media.

A bank's ids are names hashed, so `stem` decides them all: two maps with the same
vehicle need different stems, or their banks and events collide
(tools/level/ce_vehicle_audio.py).

This module takes shipped data as bytes and touches no game files or tools.
tools/tests have nothing to do with it; tools/level/test_wwise_bank.py does.
"""
import hashlib
import math
import struct
import wave

# The shipped banks this reads, by id: pakchunk0's Meteorite/Content/WwiseAudio/.
SMALL_BANK = 3609677928
HOG_BANK = 833622567
PCM_BANK = 3313310561
PCM_MEDIA = 353083959  # shipped embedded PCM, the shape `wem` copies

# Shipped ids reused verbatim.
ATTENUATION = 412582714  # 8000 cm, the one the Warthog's mixers name
VEHICLE_MIXER = 862465646  # bus 0x4DF8F084, under RTPC_Volume_SFX_Gameplay
ROOT_MIXER = 680038844  # bus 0xE2B7BC37, Master
HOG_MIXER = 83437938  # VE_Warthog's mixer: -12 dB, attenuation, 3D
HOG_HORN_SOUND = 464867416
HOG_HORN_PLAY = 902797433
HOG_HORN_STOP = 1033331626

PLUGIN_PCM = 0x00010001
PROP_VOLUME, PROP_LOOP = 0x00, 0x54
PARAM_VOLUME, PARAM_PITCH = 0, 1
LINEAR = 4
# vehicle_sounds.lua's CROSS: the pitch either side of a bound two ranges share.
CROSS = 0.04
# Under the mount; the game reads banks by id from here.
BANK_DIR = "Meteorite/Content/WwiseAudio/"


def fnv1(name):
    """Wwise's id of a name: 32-bit FNV-1 of its lower case."""
    h = 2166136261
    for c in name.lower().encode():
        h = (h * 16777619) & 0xFFFFFFFF
        h ^= c
    return h


RTPC_SPEED = fnv1("RTPC_VEH_Speed")


# Reading


def sections(bank):
    """A bank's sections: magic -> (offset of its body, size)."""
    at, found = 0, {}
    while at + 8 <= len(bank):
        magic = bank[at:at + 4]
        size = struct.unpack_from("<I", bank, at + 4)[0]
        found[magic] = (at + 8, size)
        at += 8 + size
    return found


def objects(bank):
    """A bank's HIRC: id -> (type, body after the id)."""
    at, _ = sections(bank)[b"HIRC"]
    count = struct.unpack_from("<I", bank, at)[0]
    at += 4
    found = {}
    for _ in range(count):
        kind = bank[at]
        size = struct.unpack_from("<I", bank, at + 1)[0]
        oid = struct.unpack_from("<I", bank, at + 5)[0]
        found[oid] = (kind, bank[at + 9:at + 5 + size])
        at += 5 + size
    return found


def media(bank, media_id):
    """One embedded media file's bytes."""
    found = sections(bank)
    index, size = found[b"DIDX"]
    data = found[b"DATA"][0]
    for i in range(size // 12):
        mid, offset, length = struct.unpack_from("<III", bank, index + 12 * i)
        if mid == media_id:
            return bank[data + offset:data + offset + length]
    raise KeyError(media_id)


def _varint(b, at):
    value = 0
    while True:
        c = b[at]
        at += 1
        value = (value << 7) | (c & 0x7F)
        if not c & 0x80:
            return value, at


def rtpc_block(body):
    """Where a Sound's RTPC list starts and ends, and how many it holds.

    The walk follows NodeBaseParams of bank version 150 as far as this needs: a
    Sound with 3D automation, or any other shape it doesn't know, raises rather
    than guessing."""
    plugin = struct.unpack_from("<I", body, 0)[0]
    at = 14
    if plugin & 0xF == 2:
        at += 4 + struct.unpack_from("<I", body, at)[0]
    effects = body[at + 1]
    at += 2
    if effects:
        at += 1 + effects * 6
    metadata = body[at + 1]
    at += 2
    if metadata:
        at += 1 + metadata * 6
    at += 8 + 1  # override bus, parent, bits
    count = body[at]
    at += 1 + count + 4 * count
    count = body[at]
    at += 1 + count + 8 * count
    position = body[at]
    at += 1
    if position & 0x02:
        three_d = body[at]
        at += 1
        if three_d & 0x60:
            raise ValueError("3D automation")
    aux = body[at]
    at += 1
    if aux & 0x08:
        at += 16
    at += 4  # reflections aux bus
    at += 6
    state_props, at = _varint(body, at)
    for _ in range(state_props):
        _, at = _varint(body, at)
        at += 2
    groups, at = _varint(body, at)
    for _ in range(groups):
        at += 5
        states, at = _varint(body, at)
        for _ in range(states):
            at += 4
            props, at = _varint(body, at)
            for _ in range(props):
                _, at = _varint(body, at)
                at += 4
    start = at
    count = struct.unpack_from("<H", body, at)[0]
    at += 2
    for _ in range(count):
        at += 6
        _, at = _varint(body, at)
        size = struct.unpack_from("<H", body, at + 5)[0]
        at += 7 + 12 * size
    return start, at, count


# Writing


def wem(template, pcm):
    """Shipped embedded PCM's exact chunks: fmt (24, extensible), hash, junk, data."""
    t = template
    assert t[12:16] == b"fmt " and t[44:48] == b"hash" and t[68:72] == b"junk" and t[88:92] == b"data"
    head = bytearray(t[12:92])
    head[40:56] = hashlib.md5(pcm).digest()  # the hash chunk's body
    body = bytes(head) + struct.pack("<I", len(pcm)) + pcm
    if len(pcm) & 1:
        body += b"\0"
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body


def obj(kind, oid, body):
    return bytes([kind]) + struct.pack("<II", len(body) + 4, oid) + body


def sound(template, parent, media_id, size, loop, volume):
    """A shipped streaming Vorbis sound as an embedded PCM one. Layout: plugin,
    stream type, media, size, bits (14); FX and metadata override flags (4);
    override bus; parent; bits; prop count, ids, values; the rest."""
    b = template
    assert struct.unpack_from("<I", b, 18)[0] == 0 and b[27] == 1 and b[28] == PROP_VOLUME
    head = struct.pack("<IBIIB", PLUGIN_PCM, 0, media_id, size, 0) + b[14:22]
    head += struct.pack("<I", parent) + b[26:27]
    if loop:
        props = bytes([2, PROP_VOLUME, PROP_LOOP]) + struct.pack("<fI", volume, 0)
    else:
        props = bytes([1, PROP_VOLUME]) + struct.pack("<f", volume)
    return head + props + b[33:]


def children(body, kids):
    """Replace the child list that ends a container's body: count, then ids."""
    for n in range(1, 64):
        at = len(body) - 4 - 4 * n
        if at > 0 and struct.unpack_from("<I", body, at)[0] == n:
            return body[:at] + struct.pack("<I", len(kids)) + b"".join(struct.pack("<I", k) for k in sorted(kids))
    raise ValueError("no child list")


def curve(rtpc, param, curve_id, scaling, points):
    """One RTPC record: id, type, accumulation, param, curve id, scaling, points."""
    b = struct.pack("<IBBB", rtpc, 0, 2, param) + struct.pack("<IBH", curve_id, scaling, len(points))
    for x, y in points:
        b += struct.pack("<ffI", x, y, LINEAR)
    return b


def with_rtpc(body, records):
    """A Sound with these RTPC records, in a template that has none."""
    start, end, count = rtpc_block(body)
    assert count == 0 and end == len(body), "template has RTPCs or does not parse"
    return body[:start] + struct.pack("<H", len(records)) + b"".join(records) + body[end:]


def assemble(small, bank_id, hirc_objects, media_blobs):
    """A whole bank: BKHD from the small bank, with DATA's payload on 16 bytes."""
    hirc = struct.pack("<I", len(hirc_objects)) + b"".join(hirc_objects)
    index, data = bytearray(), bytearray()
    for mid in sorted(media_blobs):
        while len(data) % 16:
            data.append(0)
        index += struct.pack("<III", mid, len(data), len(media_blobs[mid]))
        data += media_blobs[mid]
    head = bytearray(small[8:48])
    struct.pack_into("<I", head, 4, bank_id)
    head[24:40] = hashlib.md5(bytes(data) + hirc).digest()
    while (8 + len(head) + 8 + len(index) + 8) % 16:
        head += b"\0"

    def section(tag, body):
        return tag + struct.pack("<I", len(body)) + bytes(body)

    return section(b"BKHD", head) + section(b"DIDX", index) + section(b"DATA", data) + section(b"HIRC", hirc)


# A vehicle's engine


def mono48(path):
    """A CE loop as mono 48 kHz int16. The FFT resample treats it as periodic, so
    the loop point stays seamless."""
    import numpy as np

    with wave.open(path) as w:
        rate, channels, frames = w.getframerate(), w.getnchannels(), w.getnframes()
        assert w.getsampwidth() == 2
        raw = w.readframes(frames)
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64).reshape(-1, channels).mean(axis=1)
    m = round(frames * 48000 / rate)
    spectrum = np.fft.rfft(x)
    out = np.zeros(m // 2 + 1, dtype=complex)
    k = min(len(spectrum), len(out))
    out[:k] = spectrum[:k]
    y = np.fft.irfft(out, m) * (m / frames)
    return np.clip(np.round(y), -32768, 32767).astype("<i2").tobytes(), m / 48000


def engine_ids(stem, ranges):
    lower = stem.lower()
    ids = {"bank": fnv1(stem), "mixer": fnv1(f"{lower}_mixer"),
           "ev_play": fnv1(f"Play_{stem}"), "ev_stop": fnv1(f"Stop_{stem}")}
    for r in ranges:
        for kind in ("media", "sound", "act_play", "act_stop", "curve_pitch", "curve_volume"):
            ids[f"{kind}_{r['name']}"] = fnv1(f"{lower}_{kind}_{r['name']}")
    return ids


def share(p, r, first, last):
    """vehicle_sounds.lua's weight: a range's part of the sound at pitch p."""
    up = 1.0 if first else min(1.0, max(0.0, (p - (r["low"] - CROSS)) / (2 * CROSS)))
    down = 1.0 if last else min(1.0, max(0.0, ((r["high"] + CROSS) - p) / (2 * CROSS)))
    return min(up, down)


def range_curves(r, i, n, pitch, ids):
    """A range's two RTPC curves on RTPC_VEH_Speed, 0 to 1 over the Blueprint's
    engine fraction. Pitch: cents from the sample's natural pitch to CE's pitch at
    each scale. Volume: y = gain - 1 at the corners of the range's share, the shape
    of shipped nodes (param 0, scaling 2, y -1 to 0)."""
    low, high = pitch
    span = high - low
    points = [(s / 20, 1200 * math.log2((low + span * s / 20) / r["natural"])) for s in range(21)]
    pitch_record = curve(RTPC_SPEED, PARAM_PITCH, ids[f"curve_pitch_{r['name']}"], 0, points)
    corners = {0.0, 1.0}
    for p in (r["low"] - CROSS, r["low"] + CROSS, r["high"] - CROSS, r["high"] + CROSS):
        s = (p - low) / span
        if 0 < s < 1:
            corners.add(round(s, 5))
    volume = [(s, share(low + span * s, r, i == 0, i == n - 1) - 1.0) for s in sorted(corners)]
    volume_record = curve(RTPC_SPEED, PARAM_VOLUME, ids[f"curve_volume_{r['name']}"], 2, volume)
    return [volume_record, pitch_record], points, volume


def engine_bank(banks, stem, table, pcm_of):
    """The bank for one engine: each pitch range of CE's looping sound becomes a
    looping Sound, and one event starts them together. Each carries Pitch and
    Volume on RTPC_VEH_Speed, so the Blueprint's tick does the rest.

    `banks` maps the shipped bank ids at the top of this file to their bytes,
    `table` is the sound's row in ce_vehicle_sounds.py's table, and `pcm_of(range)`
    gives a range's mono 48 kHz bytes and seconds. Returns the bank, its ids and
    what went in, for the build's report."""
    small, hog = objects(banks[SMALL_BANK]), objects(banks[HOG_BANK])
    template = media(banks[PCM_BANK], PCM_MEDIA)
    ranges, pitch, gain = table["ranges"], table["pitch"], table["gain"]
    ids = engine_ids(stem, ranges)
    volume = 20 * math.log10(gain)
    sound_template = hog[HOG_HORN_SOUND][1]
    play_template = hog[HOG_HORN_PLAY][1]
    stop_template = hog[HOG_HORN_STOP][1]

    def play(target):
        b = bytearray(play_template)
        struct.pack_into("<I", b, 2, target)
        assert struct.unpack_from("<I", b, len(b) - 8)[0] == HOG_BANK
        struct.pack_into("<I", b, len(b) - 8, ids["bank"])
        return bytes(b)

    def stop(target):
        b = bytearray(stop_template)
        struct.pack_into("<I", b, 2, target)
        return bytes(b)

    def event(actions):
        return bytes([len(actions)]) + b"".join(struct.pack("<I", a) for a in actions)

    blobs, sounds, plays, stops, report = {}, [], [], [], {}
    for i, r in enumerate(ranges):
        name = r["name"]
        pcm, seconds = pcm_of(r)
        blob = wem(template, pcm)
        blobs[ids[f"media_{name}"]] = blob
        records, points, shares = range_curves(r, i, len(ranges), pitch, ids)
        body = sound(sound_template, ids["mixer"], ids[f"media_{name}"], len(blob), True, volume)
        sounds.append(obj(2, ids[f"sound_{name}"], with_rtpc(body, records)))
        plays.append(obj(3, ids[f"act_play_{name}"], play(ids[f"sound_{name}"])))
        stops.append(obj(3, ids[f"act_stop_{name}"], stop(ids[f"sound_{name}"])))
        report[name] = {"seconds": round(seconds, 3), "pitch_cents": [round(y, 1) for _, y in points[::5]],
                        "volume_gain_minus_one": [(round(x, 3), round(y, 3)) for x, y in shares]}

    hirc = [obj(14, ATTENUATION, small[ATTENUATION][1]), *sounds,
            obj(7, ids["mixer"], children(hog[HOG_MIXER][1], [ids[f"sound_{r['name']}"] for r in ranges])),
            obj(7, VEHICLE_MIXER, children(small[VEHICLE_MIXER][1], [ids["mixer"]])),
            obj(7, ROOT_MIXER, small[ROOT_MIXER][1]),
            *plays, obj(4, ids["ev_play"], event([ids[f"act_play_{r['name']}"] for r in ranges])),
            *stops, obj(4, ids["ev_stop"], event([ids[f"act_stop_{r['name']}"] for r in ranges]))]
    return assemble(banks[SMALL_BANK], ids["bank"], hirc, blobs), ids, report


# The .pak that carries a bank


def _sha1(b):
    return hashlib.sha1(b).digest()


def _fnv64_path(path, seed):
    h = (0xCBF29CE484222325 + seed) & (2**64 - 1)
    for c in path.lower().encode("utf-16le"):
        h ^= c
        h = (h * 0x100000001B3) & (2**64 - 1)
    return h


def _fstring(s):
    b = s.encode() + b"\0"
    return struct.pack("<i", len(b)) + b


def write_pak(files, seed):
    """UE5 pak v11, nothing compressed: files is [(dir below the mount, name, bytes)].
    Same shape as pakchunk0: mount ../../../, ancestors listed in the directory
    index, encoded entries, a path hash index and a full directory index."""
    data, encoded, where = bytearray(), bytearray(), []
    for directory, name, body in files:
        offset = len(data)
        # FPakEntry, inline: offset 0, size, uncompressed, method, hash, flags, block size.
        data += struct.pack("<QQQI", 0, len(body), len(body), 0) + _sha1(body) + b"\0" + struct.pack("<I", 0)
        data += body
        location = len(encoded)
        encoded += struct.pack("<III", 0xE0000000, offset, len(body))
        where.append((directory, name, location))
    path_hash = bytearray(struct.pack("<I", len(where)))
    for directory, name, location in where:
        path_hash += struct.pack("<Qi", _fnv64_path(directory + name, seed), location)
    path_hash += struct.pack("<I", 0)  # pruned directory index: empty, as shipped

    dirs = {"/": []}
    for directory, name, location in where:
        parts = directory.strip("/").split("/")
        for i in range(1, len(parts)):
            dirs.setdefault("/".join(parts[:i]) + "/", [])
        dirs.setdefault(directory, []).append((name, location))
    full = bytearray(struct.pack("<I", len(dirs)))
    for directory, entries in dirs.items():
        full += _fstring(directory) + struct.pack("<I", len(entries))
        for name, location in entries:
            full += _fstring(name) + struct.pack("<i", location)

    index_size = 4 + len(b"../../../\0") + 4 + 8 + (4 + 8 + 8 + 20) * 2 + 4 + len(encoded) + 4
    index_at = len(data)
    path_hash_at = index_at + index_size
    full_at = path_hash_at + len(path_hash)
    index = _fstring("../../../") + struct.pack("<iQ", len(where), seed)
    index += struct.pack("<iQQ", 1, path_hash_at, len(path_hash)) + _sha1(bytes(path_hash))
    index += struct.pack("<iQQ", 1, full_at, len(full)) + _sha1(bytes(full))
    index += struct.pack("<I", len(encoded)) + bytes(encoded) + struct.pack("<i", 0)
    assert len(index) == index_size
    footer = bytes(16) + b"\0" + struct.pack("<IIQQ", 0x5A6F12E1, 11, index_at, index_size) + _sha1(index) + bytes(160)
    assert len(footer) == 221
    return bytes(data) + index + bytes(path_hash) + bytes(full) + footer


def bank_pak(container, bank_id, bank):
    """The .pak beside a container that carries its bank, seeded from the
    container's name as the shipped ones are."""
    return write_pak([(BANK_DIR, f"{bank_id}.bnk", bank)], fnv1(container))
