#!/usr/bin/env python3
"""A new Wwise bank holding the CE Mongoose horn, and the .pak that carries it.

    gen_bank.py <out dir>

Everything structural is copied from shipped banks: the header from the
smallest bank, the Sound/Action/Event records from the Warthog's horn, the
parent mixers and the attenuation from the BurdenOfProof bank (which, like
every vehicle bank, repeats the same parent ids). Only ids, the source fields
and child lists change. The media is embedded (DIDX/DATA), PCM, mono 48 kHz,
in the layout of shipped embedded PCM media (3313310561.bnk, media 353083959).

Reads x/p0/*.bnk (pakchunk0's banks) and the decoded CE wave.
Writes <id>.bnk, the .wem, ids.json and bank pak bytes (see write_pak).
"""
import hashlib
import json
import os
import struct
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.environ["MJ_NATIVE_WORK"], "sound")
sys.path.insert(0, HERE)
import hirc  # noqa: E402

WAV = os.path.join(DATA, "ce", "wav", "843_horn_loop_0.wav")
SMALL = os.path.join(DATA, "x", "p0", "3609677928.bnk")
HOG = os.path.join(DATA, "x", "p0", "833622567.bnk")
PCM_TEMPLATE = os.path.join(DATA, "x", "pcm_emb.wem")

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


def fnv1(name):
    h = 2166136261
    for c in name.lower().encode():
        h = (h * 16777619) & 0xFFFFFFFF
        h ^= c
    return h


NAMES = {
    "bank": "MJ_CE_Horn",
    "media": "mj_ce_horn_media",
    "mixer": "mj_ce_horn_mixer",
    "sound_loop": "mj_ce_horn_sound_loop",
    "sound_once": "mj_ce_horn_sound_once",
    "act_play_loop": "mj_ce_horn_action_play_loop",
    "act_stop": "mj_ce_horn_action_stop",
    "act_play_once": "mj_ce_horn_action_play_once",
    "ev_play_loop": "Play_MJ_CE_Horn_Loop",
    "ev_stop": "Stop_MJ_CE_Horn_Loop",
    "ev_play_once": "Play_MJ_CE_Horn_Once",
}
ID = {k: fnv1(v) for k, v in NAMES.items()}


def horn_pcm():
    """The CE loop as mono 48 kHz int16. The FFT resample treats the signal as
    periodic, so the loop point stays seamless."""
    w = wave.open(WAV)
    rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
    assert w.getsampwidth() == 2
    x = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float64).reshape(-1, ch).mean(axis=1)
    m = round(n * 48000 / rate)
    spec = np.fft.rfft(x)
    out = np.zeros(m // 2 + 1, dtype=complex)
    k = min(len(spec), len(out))
    out[:k] = spec[:k]
    y = np.fft.irfft(out, m) * (m / n)
    return np.clip(np.round(y), -32768, 32767).astype("<i2").tobytes(), m / 48000


def wem(pcm):
    """Shipped embedded PCM's exact chunks: fmt (24, extensible), hash, junk, data."""
    t = open(PCM_TEMPLATE, "rb").read()
    assert t[12:16] == b"fmt " and t[44:48] == b"hash" and t[68:72] == b"junk" and t[88:92] == b"data"
    head = bytearray(t[12:92])
    head[40:56] = hashlib.md5(pcm).digest()  # hash chunk body
    body = bytes(head) + struct.pack("<I", len(pcm)) + pcm
    if len(pcm) & 1:
        body += b"\0"
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body


def obj(kind, oid, body):
    return bytes([kind]) + struct.pack("<II", len(body) + 4, oid) + body


def sound(template, parent, media, size, loop, volume):
    """A shipped streaming Vorbis sound as an embedded PCM one. Layout:
    plugin, stream type, media, size, bits (14); FX and metadata override
    flags (4); override bus; parent; bits; prop count, ids, values; the rest."""
    b = template
    assert struct.unpack_from("<I", b, 18)[0] == 0 and b[27] == 1 and b[28] == PROP_VOLUME
    head = struct.pack("<IBIIB", PLUGIN_PCM, 0, media, size, 0) + b[14:22]
    head += struct.pack("<I", parent) + b[26:27]
    if loop:
        props = bytes([2, PROP_VOLUME, PROP_LOOP]) + struct.pack("<fI", volume, 0)
    else:
        props = bytes([1, PROP_VOLUME]) + struct.pack("<f", volume)
    return head + props + b[33:]


def children(body, kids):
    """Replace the child list that ends a container's body."""
    # The list is the last thing in the record: count, then ids.
    for n in range(1, 64):
        at = len(body) - 4 - 4 * n
        if at > 0 and struct.unpack_from("<I", body, at)[0] == n:
            return body[:at] + struct.pack("<I", len(kids)) + b"".join(struct.pack("<I", k) for k in sorted(kids))
    raise SystemExit("no child list")


def bank():
    _, _, small = hirc.load(SMALL)
    _, _, hog = hirc.load(HOG)
    pcm, seconds = horn_pcm()
    media = wem(pcm)

    bank_id = ID["bank"]
    volume = 0.0  # against the shipped horn's -12/-14: the chain still takes 18 dB off
    snd_tpl = hog[HOG_HORN_SOUND][1]
    play_tpl = hog[HOG_HORN_PLAY][1]
    stop_tpl = hog[HOG_HORN_STOP][1]
    assert play_tpl[:2] == b"\x03\x04" and stop_tpl[:2] == b"\x03\x01"
    assert struct.unpack_from("<I", play_tpl, 2)[0] == 0x16E4AB3B

    def play(target):
        b = bytearray(play_tpl)
        struct.pack_into("<I", b, 2, target)
        at = len(b) - 8  # bank id, bank type
        assert struct.unpack_from("<I", b, at)[0] == 833622567
        struct.pack_into("<I", b, at, bank_id)
        return bytes(b)

    def stop(target):
        b = bytearray(stop_tpl)
        struct.pack_into("<I", b, 2, target)
        return bytes(b)

    def event(action):
        return b"\x01" + struct.pack("<I", action)

    objs = [
        obj(14, ATTENUATION, small[ATTENUATION][1]),
        obj(2, ID["sound_loop"], sound(snd_tpl, ID["mixer"], ID["media"], len(media), True, volume)),
        obj(2, ID["sound_once"], sound(snd_tpl, ID["mixer"], ID["media"], len(media), False, volume)),
        obj(7, ID["mixer"], children(hog[HOG_MIXER][1], [ID["sound_loop"], ID["sound_once"]])),
        obj(7, VEHICLE_MIXER, children(small[VEHICLE_MIXER][1], [ID["mixer"]])),
        obj(7, ROOT_MIXER, small[ROOT_MIXER][1]),
        obj(3, ID["act_play_loop"], play(ID["sound_loop"])),
        obj(4, ID["ev_play_loop"], event(ID["act_play_loop"])),
        obj(3, ID["act_stop"], stop(ID["sound_loop"])),
        obj(4, ID["ev_stop"], event(ID["act_stop"])),
        obj(3, ID["act_play_once"], play(ID["sound_once"])),
        obj(4, ID["ev_play_once"], event(ID["act_play_once"])),
    ]
    hirc_body = struct.pack("<I", len(objs)) + b"".join(objs)

    didx = struct.pack("<III", ID["media"], 0, len(media))
    # BKHD is padded so DATA's payload lands on 16 bytes, as shipped banks do.
    ref = open(SMALL, "rb").read()
    head = bytearray(ref[8:48])
    struct.pack_into("<I", head, 4, bank_id)
    head[24:40] = hashlib.md5(media + hirc_body).digest()
    while (8 + len(head) + 8 + len(didx) + 8) % 16:
        head += b"\0"

    def section(tag, body):
        return tag + struct.pack("<I", len(body)) + body

    out = section(b"BKHD", bytes(head)) + section(b"DIDX", didx) + section(b"DATA", media) + section(b"HIRC", hirc_body)
    return out, media, seconds


def patched_warthog(media):
    """Route (b): the shipped Warthog bank with the horn's two sounds pointed at
    our embedded PCM. Same bank id, same event ids, same object ids; only the
    source fields, DIDX and DATA change."""
    b, secs, objs = hirc.load(HOG)
    d_at, d_size = secs[b"DIDX"]
    data_at = secs[b"DATA"][0]
    entries = [struct.unpack_from("<III", b, d_at + 12 * i) for i in range(d_size // 12)]
    blobs = {e[0]: b[data_at + e[1]:data_at + e[1] + e[2]] for e in entries}
    assert entries == sorted(entries, key=lambda e: e[0]) and ID["media"] not in blobs
    blobs[ID["media"]] = media
    didx, data = bytearray(), bytearray()
    for mid in sorted(blobs):
        while len(data) % 16:
            data.append(0)
        didx += struct.pack("<III", mid, len(data), len(blobs[mid]))
        data += blobs[mid]
    h_at, h_size = secs[b"HIRC"]
    hbody = bytearray(b[h_at:h_at + h_size])
    for sid in (HOG_HORN_SOUND, 384084795):
        at = objs[sid][2] - h_at + 9  # past type, size, id
        assert struct.unpack_from("<I", hbody, at)[0] == 0x00040001 and hbody[at + 4] == 2
        struct.pack_into("<IBIIB", hbody, at, PLUGIN_PCM, 0, ID["media"], len(media), 0)
    head = bytearray(b[8:48])
    while (8 + len(head) + 8 + len(didx) + 8) % 16:
        head += b"\0"

    def section(tag, body):
        return tag + struct.pack("<I", len(body)) + bytes(body)

    return section(b"BKHD", head) + section(b"DIDX", didx) + section(b"DATA", data) + section(b"HIRC", hbody)


def sha1(b):
    return hashlib.sha1(b).digest()


def fnv64_path(path, seed):
    h = (0xCBF29CE484222325 + seed) & (2**64 - 1)
    for c in path.lower().encode("utf-16le"):
        h ^= c
        h = (h * 0x100000001B3) & (2**64 - 1)
    return h


def fstring(s):
    b = s.encode() + b"\0"
    return struct.pack("<i", len(b)) + b


def write_pak(files, seed):
    """UE5 pak v11, nothing compressed: files is [(dir below the mount, name, bytes)].
    Same shape as pakchunk0: mount ../../../, ancestors listed in the directory
    index, encoded entries, a path hash index and a full directory index."""
    data = bytearray()
    encoded = bytearray()
    where = []
    for d, name, body in files:
        off = len(data)
        # FPakEntry, inline: offset 0, size, uncompressed, method, hash, flags, block size.
        data += struct.pack("<QQQI", 0, len(body), len(body), 0) + sha1(body) + b"\0" + struct.pack("<I", 0)
        data += body
        loc = len(encoded)
        encoded += struct.pack("<III", 0xE0000000, off, len(body))
        where.append((d, name, loc))
    path_hash = bytearray(struct.pack("<I", len(where)))
    for d, name, loc in where:
        path_hash += struct.pack("<Qi", fnv64_path(d + name, seed), loc)
    path_hash += struct.pack("<I", 0)  # pruned directory index: empty, as shipped

    dirs = {"/": []}
    for d, name, loc in where:
        parts = d.strip("/").split("/")
        for i in range(1, len(parts)):
            dirs.setdefault("/".join(parts[:i]) + "/", [])
        dirs.setdefault(d, []).append((name, loc))
    full = bytearray(struct.pack("<I", len(dirs)))
    for d, entries in dirs.items():
        full += fstring(d) + struct.pack("<I", len(entries))
        for name, loc in entries:
            full += fstring(name) + struct.pack("<i", loc)

    index_size = 4 + len(b"../../../\0") + 4 + 8 + (4 + 8 + 8 + 20) * 2 + 4 + len(encoded) + 4
    index_off = len(data)
    ph_off = index_off + index_size
    fd_off = ph_off + len(path_hash)
    index = fstring("../../../") + struct.pack("<iQ", len(where), seed)
    index += struct.pack("<iQQ", 1, ph_off, len(path_hash)) + sha1(bytes(path_hash))
    index += struct.pack("<iQQ", 1, fd_off, len(full)) + sha1(bytes(full))
    index += struct.pack("<I", len(encoded)) + bytes(encoded) + struct.pack("<i", 0)
    assert len(index) == index_size
    footer = bytes(16) + b"\0" + struct.pack("<IIQQ", 0x5A6F12E1, 11, index_off, index_size) + sha1(index) + bytes(160)
    assert len(footer) == 221
    return bytes(data) + index + bytes(path_hash) + bytes(full) + footer


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DATA, "out", "work")
    os.makedirs(out, exist_ok=True)
    data, media, seconds = bank()
    bank_name = f"{ID['bank']}.bnk"
    open(os.path.join(out, bank_name), "wb").write(data)
    open(os.path.join(out, f"{ID['media']}.wem"), "wb").write(media)
    pak = write_pak([("Meteorite/Content/WwiseAudio/", bank_name, data)], fnv1("pakchunk996-MJOLNIRBANK-horn_P"))
    open(os.path.join(out, "bank.pak"), "wb").write(pak)
    stock = patched_warthog(media)
    pak_b = write_pak([("Meteorite/Content/WwiseAudio/", "833622567.bnk", stock)], fnv1("pakchunk995-MJOLNIRBANK-warthogbank_P"))
    open(os.path.join(out, "fallback.pak"), "wb").write(pak_b)
    open(os.path.join(out, "fallback_833622567.bnk"), "wb").write(stock)
    json.dump({"ids": ID, "names": NAMES, "bank_file": bank_name, "seconds": seconds,
               "bank_bytes": len(data), "media_bytes": len(media)},
              open(os.path.join(out, "ids.json"), "w"), indent=1)
    print(f"{bank_name}: {len(data)} bytes, media {len(media)} bytes, {seconds:.3f} s; pak {len(pak)} bytes")


if __name__ == "__main__":
    main()
