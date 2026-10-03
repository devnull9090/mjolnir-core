"""blam-players.py: the running game's Blam players, read from outside the game.

The simulation keeps its players array per thread (TLS slot of
HaloSimulation_tag_release.dll, +0x30; 0x4b0 bytes a player; the game globals
at +0x60). This walks every thread of HaloCampaignEvolved, finds the one with
a running game, and prints each player: salt, flags (+4: bit 0 active, bit 3
waiting for its first spawn, 0x8000 joined in progress), machine (+0x1a) and
unit (+0x28, -1 = no biped). tools/remote/jip-test.mjs reads it to tell a
joiner that spawned from one that did not. Read-only.

    python tools/remote/blam-players.py [--json]
"""
import ctypes
import ctypes.wintypes as w
import json
import struct
import subprocess
import sys

import pefile

k = ctypes.WinDLL("kernel32")
psapi = ctypes.WinDLL("psapi")
nt = ctypes.WinDLL("ntdll")


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ThreadID", w.DWORD),
                ("th32OwnerProcessID", w.DWORD), ("tpBasePri", ctypes.c_long),
                ("tpDeltaPri", ctypes.c_long), ("dwFlags", w.DWORD)]


def main():
    out = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-Process HaloCampaignEvolved).Id"],
                         capture_output=True, text=True).stdout.strip()
    if not out:
        print(json.dumps({"error": "the game is not running"}) if "--json" in sys.argv else "the game is not running")
        return 1
    pid = int(out.splitlines()[0])
    h = k.OpenProcess(0x0410, False, pid)
    mods = (ctypes.c_void_p * 2048)()
    need = w.DWORD()
    psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 3)
    sim = None
    sim_path = None
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

    result = {"players": []}
    snapshot = k.CreateToolhelp32Snapshot(4, 0)
    entry = THREADENTRY32()
    entry.dwSize = ctypes.sizeof(THREADENTRY32)
    more = k.Thread32First(snapshot, ctypes.byref(entry))
    while more and not result["players"]:
        if entry.th32OwnerProcessID == pid:
            thread = k.OpenThread(0x40, False, entry.th32ThreadID)
            info = (ctypes.c_byte * 48)()
            if thread and nt.NtQueryInformationThread(thread, 0, info, 48, None) == 0:
                teb = struct.unpack_from("<Q", bytes(info), 8)[0]
                tls = q(teb + 0x58)
                block = q(tls + tls_index * 8) if tls else 0
                g = q(block + 0x60) if block else 0
                head = read(g, 2) if g else None
                if head and head[1]:
                    players = q(block + 0x30)
                    data = q(players + 0x50)
                    capacity = struct.unpack("<i", read(players + 0x2c, 4))[0]
                    for i in range(min(capacity, 16)):
                        e = read(data + i * 0x4b0, 0x30)
                        salt = struct.unpack_from("<H", e, 0)[0]
                        if salt:
                            result["players"].append({
                                "index": i, "salt": salt, "flags": struct.unpack_from("<I", e, 4)[0],
                                "machine": struct.unpack_from("<h", e, 0x1a)[0],
                                "unit": struct.unpack_from("<i", e, 0x28)[0],
                            })
                    result["machines"] = struct.unpack("<I", read(g + 0x26c, 4))[0]
            if thread:
                k.CloseHandle(thread)
        more = k.Thread32Next(snapshot, ctypes.byref(entry))
    if "--json" in sys.argv:
        print(json.dumps(result))
    else:
        if not result["players"]:
            print("no running game")
        for p in result["players"]:
            print(f"player {p['index']}: salt {p['salt']:04x} flags {p['flags']:08x} machine {p['machine']} unit {p['unit']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
