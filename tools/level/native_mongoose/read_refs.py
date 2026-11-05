#!/usr/bin/env python3
"""Run with the game in a match. Reads, never writes: what each Mongoose model's
four references hold after the load, and how many runtime nodes it took.

    python read_refs.py nat          # or nar, nao

A blanked reference reads -1. The shipped Mongoose is the control: all four set,
119 nodes. The offsets are the model tag's own field order, 16 bytes a reference,
the datum in the last four; runtime nodes are a block at 0x118.
"""
import ctypes
import os
import re
import subprocess
import sys
import tempfile

MJ = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "target", "release", "mjolnir.exe")
FIELDS = (("collision model", 0x0C), ("animation", 0x1C), ("physics_model", 0x2C), ("skeleton model", 0x3C))
RUNTIME_NODES = 0x118
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.restype = ctypes.c_void_p
k32.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]


def live(*args):
    return subprocess.run([MJ, "live", *args], text=True, capture_output=True, check=True).stdout


def read_i32(handle, address):
    value = ctypes.c_int32()
    done = ctypes.c_size_t()
    if not k32.ReadProcessMemory(handle, address, ctypes.byref(value), 4, ctypes.byref(done)):
        raise OSError(f"cannot read 0x{address:X}")
    return value.value


def main():
    code = sys.argv[1].lower()
    pid = int(re.search(r"pid\s+(\d+)", live("status")).group(1))
    handle = k32.OpenProcess(0x0010, False, pid)  # PROCESS_VM_READ
    path = os.path.join(tempfile.gettempdir(), "nat_hlmt.tsv")
    live("tags", "--group", "hlmt", "--filter", "mjolnir", "--tsv", path)
    rows = [line.split("\t") for line in open(path, encoding="utf-8") if line.strip()]
    found = False
    for row in rows:
        name, root = row[3], row[4].strip()
        name_l = name.lower().replace(chr(92), "/")
        if not (f"mjolnir/{code}/" in name_l or "mjolnir/vht/mongoose" in name_l):
            continue
        found = found or f"mjolnir/{code}/" in name_l
        if root == "-":
            print(name, "has no root")
            continue
        base = int(root, 16)
        refs = {f: read_i32(handle, base + o) for f, o in FIELDS}
        print(name, "runtime nodes", read_i32(handle, base + RUNTIME_NODES))
        for f, v in refs.items():
            print(f"  {f:16} 0x{v & 0xFFFFFFFF:08X}" + ("  BLANKED" if v == -1 else ""))
    print("native model loaded" if found else "native model NOT in the tag table")


if __name__ == "__main__":
    main()
