"""List and extract named clips from an MCC FMOD bank (FSB5 + its .info).

MCC's Halo 3 / Reach banks (halo3/fmod/pc/english.fsb) hold every clip as an
FSB5 subsong whose name is the source file's base name; the .info beside it
lists the full tag-source paths ("data\\sound\\dialog\\...\\cortana\\x.aif") in
subsong order. Decoding is vgmstream-cli's (FMOD custom Vorbis).

  python tools/voice/fsb_clips.py list <bank.fsb> [--match REGEX]
  python tools/voice/fsb_clips.py extract <bank.fsb> --match REGEX --out DIR \
      [--vgmstream PATH] [--min-seconds 0.6]

`list` prints index, path. `extract` writes DIR/<index>_<name>.wav (48 kHz
mono as stored) plus DIR/clips.tsv (index, path, seconds). Game audio is
never committed: point --out outside the repository.
"""
import argparse
import os
import re
import subprocess
import sys
import wave

SOURCE = re.compile(rb"data" + re.escape(b"\\") + rb"[ -~]+")


def fsb5_names(bank):
    """Subsong names from the bank's own FSB5 name table (Halo 1's banks have
    no .info; their names alone carry the speaker, e.g. a10_flavor_340_cortana).
    Header: "FSB5", version, count, sample-header size, name-table size, ...;
    the name table is count offsets (relative to its start), then C strings."""
    import struct
    with open(bank, "rb") as f:
        head = f.read(0x40)
        if head[:4] != b"FSB5":
            sys.exit(f"{bank}: not FSB5")
        version, count, sample_size, name_size = struct.unpack_from("<4I", head, 4)
        start = (0x3C if version == 1 else 0x40) + sample_size
        f.seek(start)
        table = f.read(name_size)
    offsets = struct.unpack_from(f"<{count}I", table)
    return [table[o:table.index(b"\0", o)].decode("ascii", "replace") for o in offsets]


def paths(bank):
    """Full source paths in subsong order, from the .info beside the bank,
    with "/" separators (some carry no extension); the FSB5 names when there
    is no .info."""
    if not os.path.exists(bank + ".info"):
        return fsb5_names(bank)
    raw = open(bank + ".info", "rb").read()
    return [m.group().decode("ascii", "replace").replace(chr(92), "/") for m in SOURCE.finditer(raw)]


def stream_name(vgm, bank, index):
    meta = subprocess.run([vgm, "-m", "-s", str(index), bank], capture_output=True, text=True).stdout
    m = re.search(r"stream name: (.+)", meta)
    return m.group(1).strip() if m else None


def check_order(vgm, bank, names):
    """The .info order must be the subsong order: spot-check a few indices."""
    for index in (1, len(names) // 3, len(names) // 2, len(names)):
        got = stream_name(vgm, bank, index)
        want = os.path.splitext(names[index - 1].split("/")[-1])[0]
        if got is None or got.lower() != want.lower():
            sys.exit(f"subsong {index} is {got!r}, the .info says {want!r}: order differs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["list", "extract"])
    ap.add_argument("bank")
    ap.add_argument("--match", default="")
    ap.add_argument("--out")
    ap.add_argument("--vgmstream", default=r"D:\hce-voice\tools\vgmstream\vgmstream-cli.exe")
    ap.add_argument("--min-seconds", type=float, default=0.6)
    a = ap.parse_args()
    names = paths(a.bank)
    pick = re.compile(a.match, re.I)
    chosen = [(i + 1, p) for i, p in enumerate(names) if pick.search(p)]
    if a.command == "list":
        for i, p in chosen:
            print(f"{i}\t{p}")
        print(f"{len(chosen)} of {len(names)}", file=sys.stderr)
        return
    if not a.out:
        sys.exit("--out is required")
    check_order(a.vgmstream, a.bank, names)
    os.makedirs(a.out, exist_ok=True)
    rows = []
    for n, (i, p) in enumerate(chosen, 1):
        base = os.path.splitext(p.split("/")[-1])[0]
        dest = os.path.join(a.out, f"{i:05d}_{base}.wav")
        if not os.path.exists(dest):
            subprocess.run([a.vgmstream, "-s", str(i), "-o", dest, a.bank], capture_output=True, check=True)
        with wave.open(dest) as w:
            seconds = w.getnframes() / w.getframerate()
        if seconds < a.min_seconds:
            os.remove(dest)
            continue
        rows.append(f"{i}\t{p}\t{seconds:.2f}")
        if n % 100 == 0:
            print(f"{n}/{len(chosen)}", file=sys.stderr)
    with open(os.path.join(a.out, "clips.tsv"), "w", encoding="utf-8") as f:
        f.write("index\tpath\tseconds\n" + "\n".join(rows) + "\n")
    total = sum(float(r.split("\t")[2]) for r in rows)
    print(f"{len(rows)} clips, {total / 60:.1f} minutes -> {a.out}")


if __name__ == "__main__":
    main()
