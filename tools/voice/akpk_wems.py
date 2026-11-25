"""Unpack the streamed sounds of a Wwise AKPK package (.pck) to WAV.

  python akpk_wems.py <package.pck> --out DIR [--vgmstream PATH] [--min-seconds 0.6]

MCC's Halo 4 keeps its voice in sound/pc/english(us)/soundstream.pck. AKPK:
"AKPK", u32 header size, u32 version, then the sizes of the language map,
the bank table and the stream table (and, when the header has room, an
external table), then those tables in that order. A table is a u32 count and
entries of {id, block size, size, start block, language} (u32 each, or a u64
id in 64-bit-id packages); a file starts at start block x block size. The
streamed files are .wem, which vgmstream decodes. There are no names: pick
voices by ear or with speaker_filter.py. Writes DIR/<id>.wav and DIR/clips.tsv
(id, seconds). Game audio stays out of the repository.
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile
import wave


def entries(f, at, size):
    f.seek(at)
    table = f.read(size)
    count = struct.unpack_from("<I", table)[0]
    if count == 0:
        return []
    width = (size - 4) // count
    out = []
    for n in range(count):
        o = 4 + n * width
        if width == 24:
            ident, block, length, start, lang = struct.unpack_from("<QIIII", table, o)
        else:
            ident, block, length, start, lang = struct.unpack_from("<5I", table, o)
        out.append((ident, start * block, length))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("package")
    ap.add_argument("--out", required=True)
    ap.add_argument("--vgmstream", default=r"D:\hce-voice\tools\vgmstream\vgmstream-cli.exe")
    ap.add_argument("--min-seconds", type=float, default=0.6)
    a = ap.parse_args()
    with open(a.package, "rb") as f:
        head = f.read(0x20)
        if head[:4] != b"AKPK":
            sys.exit("not an AKPK package")
        _, _, lang_size, bank_size, stream_size, external_size = struct.unpack_from("<6I", head, 4)
        # The language map follows the header words (magic, size, version,
        # the four table sizes): 0x1C. External files (u64 ids) come last.
        at = 0x1C + lang_size + bank_size
        streams = entries(f, at, stream_size) + (entries(f, at + stream_size, external_size) if external_size > 4 else [])
        print(f"{len(streams)} streamed files", file=sys.stderr)
        os.makedirs(a.out, exist_ok=True)
        rows = []
        tmp = tempfile.mkdtemp(prefix="akpk")
        for n, (ident, offset, length) in enumerate(streams, 1):
            dest = os.path.join(a.out, f"{ident}.wav")
            if not os.path.exists(dest):
                f.seek(offset)
                wem = os.path.join(tmp, f"{ident}.wem")
                with open(wem, "wb") as w:
                    w.write(f.read(length))
                done = subprocess.run([a.vgmstream, "-o", dest, wem], capture_output=True)
                os.remove(wem)
                if done.returncode != 0 or not os.path.exists(dest):
                    continue
            with wave.open(dest) as w:
                seconds = w.getnframes() / w.getframerate()
            if seconds < a.min_seconds:
                os.remove(dest)
                continue
            rows.append(f"{ident}\t{seconds:.2f}")
            if n % 200 == 0:
                print(f"{n}/{len(streams)}", file=sys.stderr)
        os.rmdir(tmp)
    with open(os.path.join(a.out, "clips.tsv"), "w", encoding="utf-8") as out:
        out.write("id\tseconds\n" + "\n".join(rows) + "\n")
    print(f"{len(rows)} clips, {sum(float(r.split(chr(9))[1]) for r in rows) / 60:.1f} minutes -> {a.out}")


if __name__ == "__main__":
    main()
