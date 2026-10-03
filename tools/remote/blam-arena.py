"""blam-arena.py: snapshot and diff the running game's Blam game-state arenas.

Blam keeps its game state in a few arenas per thread (sim 0x2a4010 allocates
from heap type k: base TLS+0x570+8k, bytes in use at sim 0x13e0020 + k*0x1850).
To find the field that a game event changes, take two snapshots before it
(bytes that differ between them are noise) and one after, then diff:

    python tools/remote/blam-arena.py snap a1
    python tools/remote/blam-arena.py snap a2
    ... the event ...
    python tools/remote/blam-arena.py snap b
    python tools/remote/blam-arena.py diff a1 a2 b [--max 200]

Snapshots go to %TEMP%/blam-arena-<name>.bin with a small index. Each diff line
is "heap k +offset: before -> after" (offsets from the arena base; the game
globals G sit in one of them). Read-only.
"""
import ctypes
import ctypes.wintypes as w
import json
import os
import struct
import subprocess
import sys
import tempfile

import pefile

HEAPS = range(0, 12)


def attach():
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-Process HaloCampaignEvolved).Id"],
                         capture_output=True, text=True).stdout.strip()
    if not out:
        sys.exit("the game is not running")
    pid = int(out.splitlines()[0])
    k = ctypes.WinDLL("kernel32")
    psapi = ctypes.WinDLL("psapi")
    nt = ctypes.WinDLL("ntdll")
    h = k.OpenProcess(0x0410, False, pid)
    mods = (ctypes.c_void_p * 2048)()
    need = w.DWORD()
    psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 3)
    sim = sim_path = None
    for m in mods[:need.value // 8]:
        name = ctypes.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(h, ctypes.c_void_p(m), name, 260)
        if name.value.lower().startswith("halosimulation"):
            sim = m
            full = ctypes.create_unicode_buffer(1024)
            psapi.GetModuleFileNameExW(h, ctypes.c_void_p(m), full, 1024)
            sim_path = full.value

    def read(address, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not address or not k.ReadProcessMemory(h, ctypes.c_void_p(address), buf, n, ctypes.byref(got)):
            return None
        return buf.raw

    def q(address):
        raw = read(address, 8)
        return struct.unpack("<Q", raw)[0] if raw else 0

    tls_dir = pefile.PE(sim_path, fast_load=True).OPTIONAL_HEADER.DATA_DIRECTORY[9]
    tls_index = struct.unpack("<I", read(q(sim + tls_dir.VirtualAddress + 0x10), 4))[0]

    class TE(ctypes.Structure):
        _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ThreadID", w.DWORD),
                    ("th32OwnerProcessID", w.DWORD), ("tpBasePri", ctypes.c_long),
                    ("tpDeltaPri", ctypes.c_long), ("dwFlags", w.DWORD)]

    snapshot = k.CreateToolhelp32Snapshot(4, 0)
    te = TE()
    te.dwSize = ctypes.sizeof(TE)
    more = k.Thread32First(snapshot, ctypes.byref(te))
    while more:
        if te.th32OwnerProcessID == pid:
            thread = k.OpenThread(0x40, False, te.th32ThreadID)
            info = (ctypes.c_byte * 48)()
            if thread and nt.NtQueryInformationThread(thread, 0, info, 48, None) == 0:
                teb = struct.unpack_from("<Q", bytes(info), 8)[0]
                tls = q(teb + 0x58)
                block = q(tls + tls_index * 8) if tls else 0
                g = q(block + 0x60) if block else 0
                head = read(g, 2) if g else None
                if head and head[1]:
                    return read, q, sim, block, g
        more = k.Thread32Next(snapshot, ctypes.byref(te))
    sys.exit("no thread with a running game")


def path_of(name):
    return os.path.join(tempfile.gettempdir(), f"blam-arena-{name}")


def snap(name):
    read, q, sim, block, g = attach()
    index = {"g": g, "heaps": []}
    with open(path_of(name) + ".bin", "wb") as out:
        for heap in HEAPS:
            base = q(block + 0x570 + heap * 8)
            used = q(sim + 0x13e0020 + heap * 0x1850)
            if not base or not used or used > 0x20000000:
                continue
            data = bytearray()
            for at in range(0, used, 0x100000):
                chunk = read(base + at, min(0x100000, used - at))
                data += chunk if chunk else bytes(min(0x100000, used - at))
            index["heaps"].append({"heap": heap, "base": base, "size": used, "offset": out.tell()})
            out.write(data)
    with open(path_of(name) + ".json", "w") as f:
        json.dump(index, f)
    print(f"{name}: G {g:x}; " + ", ".join(f"heap {h['heap']} {h['size']:#x} at {h['base']:x}" for h in index["heaps"]))


def load(name):
    index = json.load(open(path_of(name) + ".json"))
    blob = open(path_of(name) + ".bin", "rb").read()
    return index, {h["heap"]: (h, blob[h["offset"]:h["offset"] + h["size"]]) for h in index["heaps"]}


def diff(a1, a2, b, limit):
    _, A1 = load(a1)
    _, A2 = load(a2)
    ib, B = load(b)
    g = ib["g"]
    shown = 0
    for heap, (hb, db) in B.items():
        if heap not in A1 or heap not in A2:
            continue
        d1, d2 = A1[heap][1], A2[heap][1]
        n = min(len(d1), len(d2), len(db))
        for i in range(n):
            if d1[i] == d2[i] and db[i] != d2[i]:
                address = hb["base"] + i
                where = f" (G+{address - g:#x})" if 0 <= address - g < 0x30000 else ""
                print(f"heap {heap} +{i:#x}{where}: {d2[i]:02x} -> {db[i]:02x}")
                shown += 1
                if shown >= limit:
                    print("...")
                    return


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "snap":
        snap(sys.argv[2])
    elif len(sys.argv) >= 5 and sys.argv[1] == "diff":
        limit = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 300
        diff(sys.argv[2], sys.argv[3], sys.argv[4], limit)
    else:
        print(__doc__)
