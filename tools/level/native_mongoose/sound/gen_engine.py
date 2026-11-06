#!/usr/bin/env python3
"""A new Wwise bank holding CE's Mongoose engine, its pitch on RTPC_VEH_Speed.

    gen_engine.py <out dir>

The four pitch ranges of CE's looping sound become four looping Sounds that one
event starts together. Each carries two RTPC curves on RTPC_VEH_Speed (0..1, the
Blueprint sets it from GetEngineAngularVelocityFraction): Pitch, and a Volume that
gives the range its share. Shipped nodes hold the same records: 18 Pitch curves on
this RTPC, param 1, scaling 0, x 0..1; Volume curves param 0, scaling 2, y -1..0.

Values are CE's: the loop's pitch bounds 1..2 over the scale, each range's natural
pitch and bounds, gain 0.6. The crossfade width is vehicle_sounds.lua's CROSS.
"""
import hashlib
import json
import math
import os
import struct
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.environ["MJ_NATIVE_WORK"], "sound")
sys.path.insert(0, HERE)
import gen_bank as G  # noqa: E402
import hirc  # noqa: E402
import wv  # noqa: E402

CE = os.path.join(DATA, "ce")
RTPC_SPEED = G.fnv1("RTPC_VEH_Speed")
assert RTPC_SPEED == 162356596
CROSS = 0.04
PARAM_VOLUME, PARAM_PITCH = 0, 1
LINEAR = 4
BANK = "MJ_CE_Engine"


def ids(ranges):
    d = {"bank": G.fnv1(BANK), "mixer": G.fnv1("mj_ce_engine_mixer"),
         "ev_play": G.fnv1("Play_MJ_CE_Engine"), "ev_stop": G.fnv1("Stop_MJ_CE_Engine")}
    for r in ranges:
        for kind in ("media", "sound", "act_play", "act_stop", "curve_pitch", "curve_volume"):
            d[f"{kind}_{r['name']}"] = G.fnv1(f"mj_ce_engine_{kind}_{r['name']}")
    return d


def mono48(path):
    """A CE loop as mono 48 kHz int16. The FFT resample treats it as periodic, so the
    loop point stays seamless."""
    w = wave.open(path)
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


def share(p, r, first, last):
    """vehicle_sounds.lua's weight: a range's part of the sound at pitch p."""
    up = 1.0 if first else min(1.0, max(0.0, (p - (r["low"] - CROSS)) / (2 * CROSS)))
    down = 1.0 if last else min(1.0, max(0.0, ((r["high"] + CROSS) - p) / (2 * CROSS)))
    return min(up, down)


def curve(rtpc, param, curve_id, scaling, points):
    """One RTPC record: id, type, accumulation, param, curve id, scaling, points."""
    b = struct.pack("<IBBB", rtpc, 0, 2, param) + struct.pack("<IBH", curve_id, scaling, len(points))
    for x, y in points:
        b += struct.pack("<ffI", x, y, LINEAR)
    return b


def curves(r, i, n, pitch, d):
    low, high = pitch
    span = high - low
    # Pitch: cents from the sample's natural pitch to CE's pitch at each scale.
    pts = [(s / 20, 1200 * math.log2((low + span * s / 20) / r["natural"])) for s in range(21)]
    pitch_rec = curve(RTPC_SPEED, PARAM_PITCH, d[f"curve_pitch_{r['name']}"], 0, pts)
    # Volume: y = gain - 1 at the corners of the range's share.
    corners = {0.0, 1.0}
    for p in (r["low"] - CROSS, r["low"] + CROSS, r["high"] - CROSS, r["high"] + CROSS):
        s = (p - low) / span
        if 0 < s < 1:
            corners.add(round(s, 5))
    vol = [(s, share(low + span * s, r, i == 0, i == n - 1) - 1.0) for s in sorted(corners)]
    vol_rec = curve(RTPC_SPEED, PARAM_VOLUME, d[f"curve_volume_{r['name']}"], 2, vol)
    return [vol_rec, pitch_rec], pts, vol


def with_rtpc(body, recs):
    r = wv.node(2, body)
    assert not r["rtpc"] and r["end"] == len(body), "template has RTPCs or does not parse"
    return body[:r["rtpc_at"]] + struct.pack("<H", len(recs)) + b"".join(recs) + body[r["end"]:]


def build(table):
    _, _, small = hirc.load(G.SMALL)
    _, _, hog = hirc.load(G.HOG)
    ranges, pitch, gain = table["ranges"], table["pitch"], table["gain"]
    d = ids(ranges)
    volume = 20 * math.log10(gain)
    snd_tpl = hog[G.HOG_HORN_SOUND][1]
    play_tpl = hog[G.HOG_HORN_PLAY][1]
    stop_tpl = hog[G.HOG_HORN_STOP][1]

    def play(target):
        b = bytearray(play_tpl)
        struct.pack_into("<I", b, 2, target)
        assert struct.unpack_from("<I", b, len(b) - 8)[0] == 833622567
        struct.pack_into("<I", b, len(b) - 8, d["bank"])
        return bytes(b)

    def stop(target):
        b = bytearray(stop_tpl)
        struct.pack_into("<I", b, 2, target)
        return bytes(b)

    def event(actions):
        return bytes([len(actions)]) + b"".join(struct.pack("<I", a) for a in actions)

    media, sounds, plays, stops, report = {}, [], [], [], {}
    for i, r in enumerate(ranges):
        name = r["name"]
        pcm, seconds = mono48(os.path.join(CE, "sounds", f"mongoose_a3_{name}_loop.wav"))
        blob = G.wem(pcm)
        media[d[f"media_{name}"]] = blob
        recs, pts, vol = curves(r, i, len(ranges), pitch, d)
        body = G.sound(snd_tpl, d["mixer"], d[f"media_{name}"], len(blob), True, volume)
        sounds.append(G.obj(2, d[f"sound_{name}"], with_rtpc(body, recs)))
        plays.append(G.obj(3, d[f"act_play_{name}"], play(d[f"sound_{name}"])))
        stops.append(G.obj(3, d[f"act_stop_{name}"], stop(d[f"sound_{name}"])))
        report[name] = {"seconds": round(seconds, 3), "pitch_cents": [round(y, 1) for _, y in pts[::5]],
                        "volume_gain_minus_one": [(round(x, 3), round(y, 3)) for x, y in vol]}

    objs = [G.obj(14, G.ATTENUATION, small[G.ATTENUATION][1]), *sounds,
            G.obj(7, d["mixer"], G.children(hog[G.HOG_MIXER][1], [d[f"sound_{r['name']}"] for r in ranges])),
            G.obj(7, G.VEHICLE_MIXER, G.children(small[G.VEHICLE_MIXER][1], [d["mixer"]])),
            G.obj(7, G.ROOT_MIXER, small[G.ROOT_MIXER][1]),
            *plays, G.obj(4, d["ev_play"], event([d[f"act_play_{r['name']}"] for r in ranges])),
            *stops, G.obj(4, d["ev_stop"], event([d[f"act_stop_{r['name']}"] for r in ranges]))]
    hirc_body = struct.pack("<I", len(objs)) + b"".join(objs)

    didx, data = bytearray(), bytearray()
    for mid in sorted(media):
        while len(data) % 16:
            data.append(0)
        didx += struct.pack("<III", mid, len(data), len(media[mid]))
        data += media[mid]

    head = bytearray(open(G.SMALL, "rb").read()[8:48])
    struct.pack_into("<I", head, 4, d["bank"])
    head[24:40] = hashlib.md5(bytes(data) + hirc_body).digest()
    while (8 + len(head) + 8 + len(didx) + 8) % 16:
        head += b"\0"

    def section(tag, body):
        return tag + struct.pack("<I", len(body)) + bytes(body)

    out = section(b"BKHD", head) + section(b"DIDX", didx) + section(b"DATA", data) + section(b"HIRC", hirc_body)
    return out, d, report


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DATA, "out", "work")
    os.makedirs(out, exist_ok=True)
    t = json.load(open(os.path.join(CE, "vehicle_sounds.json"), encoding="utf-8"))
    table = next(s for s in t["BP_VHTMongoose_C"]["sounds"] if s["drive"] == "engine")
    if len(sys.argv) > 2 and sys.argv[2] == "one":
        # One loop: idle's sample over the whole scale, no crossfade to doubt.
        table = dict(table, ranges=table["ranges"][:1])
    data, d, report = build(table)
    name = f"{d['bank']}.bnk"
    open(os.path.join(out, name), "wb").write(data)
    pak = G.write_pak([("Meteorite/Content/WwiseAudio/", name, data)], G.fnv1("pakchunk996-MJOLNIRBANK-engine_P"))
    open(os.path.join(out, "bank.pak"), "wb").write(pak)
    json.dump({"ids": d, "bank_file": name, "bank_bytes": len(data), "report": report},
              open(os.path.join(out, "ids.json"), "w"), indent=1)
    print(f"{name}: {len(data)} bytes; pak {len(pak)} bytes")


if __name__ == "__main__":
    main()
