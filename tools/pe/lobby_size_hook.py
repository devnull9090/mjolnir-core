"""Force the co-op lobby size the game asks PlayFab for.

The host tells the service how big the lobby may be. `PFLobbyCreateConfiguration`
carries `maxMemberCount` as its first field, and the exe passes that struct to
`PFMultiplayerCreateAndJoinLobby` from exactly one call site. Raising it is
therefore a matter of editing one dword on the way past.

The alternative — finding the object that owns the value — needs the instance,
and that object is not a UObject: its method is delegate-invoked, it appears in
no vtable, and no reflected class has the right layout. See
`docs/coop_player_cap.md`. Hooking the import boundary avoids the search
entirely and fires on the first lobby the host creates.

The hook is a small stub written into the target process, installed by
overwriting one Import Address Table slot:

    inc  dword ptr [rip+N]     ; fire counter, read back by --status
    test r8, r8                ; the config pointer
    jz   tail                  ; leave a null alone
    mov  dword ptr [r8], N     ; maxMemberCount
    tail:
    mov  rax, <original>
    jmp  rax

The counter exists so a failed experiment can be told apart from an experiment
that never ran. Without it, "the lobby still seated four" cannot distinguish
`the stub was never called` from `the service refused the number`.

The IAT slot is resolved by walking the on-disk import table for the export
name, never by a baked address, so a game update moves it without breaking this.

This does not make the service agree. PlayFab validates the request against the
title's limits, and whether an eight-member lobby is accepted is unverified.

Usage:
    python tools/pe/lobby_size_hook.py --status
    python tools/pe/lobby_size_hook.py --size 8
    python tools/pe/lobby_size_hook.py --revert
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wintypes
import struct
import sys
from pathlib import Path

IMPORT_NAME = b"PFMultiplayerCreateAndJoinLobby"
IMPORT_DLL = "playfabmultiplayerwin.dll"
EXE_NAME = "HaloCampaignEvolved.exe"

PROCESS_ACCESS = 0x0008 | 0x0010 | 0x0020 | 0x0400   # VM_OPERATION|VM_READ|VM_WRITE|QUERY_INFO
MEM_COMMIT_RESERVE = 0x1000 | 0x2000
MEM_RELEASE = 0x8000
PAGE_RW = 0x04
PAGE_RX = 0x20
PAGE_RWX = 0x40
TH32CS_SNAPMODULE = 0x00000008 | 0x00000010

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.restype = wintypes.HANDLE
k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
k32.VirtualAllocEx.restype = ctypes.c_void_p
k32.VirtualAllocEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
                               wintypes.DWORD, wintypes.DWORD]
k32.VirtualFreeEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD]
k32.VirtualProtectEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
                                 wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD), ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD), ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
        ("modBaseSize", wintypes.DWORD), ("hModule", wintypes.HMODULE),
        ("szModule", wintypes.WCHAR * 256), ("szExePath", wintypes.WCHAR * 260),
    ]


def modules(pid: int) -> dict[str, tuple[int, int, str]]:
    """{lowercase name: (base, size, path)} for every module in the process."""
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid)
    if snap == wintypes.HANDLE(-1).value:
        raise OSError(f"snapshot failed: {ctypes.get_last_error()}")
    out = {}
    ent = MODULEENTRY32W()
    ent.dwSize = ctypes.sizeof(ent)
    ok = k32.Module32FirstW(snap, ctypes.byref(ent))
    while ok:
        out[ent.szModule.lower()] = (ctypes.cast(ent.modBaseAddr, ctypes.c_void_p).value,
                                     ent.modBaseSize, ent.szExePath)
        ok = k32.Module32NextW(snap, ctypes.byref(ent))
    k32.CloseHandle(snap)
    return out


def find_pid(name: str) -> int | None:
    import subprocess
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) > 1 and parts[0].lower() == name.lower():
            return int(parts[1])
    return None


def iat_rva_for(exe_path: Path, dll: str, symbol: bytes) -> int:
    """RVA of the IAT slot holding `symbol`, found by walking the import table."""
    data = exe_path.read_bytes()
    e = struct.unpack_from("<I", data, 0x3C)[0]
    coff = e + 4
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    n_sections = struct.unpack_from("<H", data, coff + 2)[0]
    table = opt + opt_size
    secs = []
    for i in range(n_sections):
        o = table + i * 40
        _vs, vaddr, rsize, raddr = struct.unpack_from("<IIII", data, o + 8)
        secs.append((vaddr, rsize, raddr))

    def off(rva):
        for vaddr, rsize, raddr in secs:
            if vaddr <= rva < vaddr + rsize:
                return raddr + (rva - vaddr)
        return None

    imp_rva = struct.unpack_from("<I", data, opt + 112 + 8)[0]
    o = off(imp_rva)
    while True:
        oft, _t, _f, name_rva, first = struct.unpack_from("<IIIII", data, o)
        if oft == 0 and name_rva == 0 and first == 0:
            break
        no = off(name_rva)
        this_dll = data[no:data.find(b"\0", no)].decode().lower()
        if this_dll == dll:
            thunk = off(oft or first)
            idx = 0
            while True:
                ent = struct.unpack_from("<Q", data, thunk + idx * 8)[0]
                if ent == 0:
                    break
                if not (ent >> 63):                     # imported by name
                    ho = off(ent & 0x7FFFFFFF)
                    nm = data[ho + 2:data.find(b"\0", ho + 2)]
                    if nm == symbol:
                        return first + idx * 8
                idx += 1
        o += 20
    raise LookupError(f"{symbol.decode()} not imported from {dll}")


class Target:
    def __init__(self, pid: int):
        self.pid = pid
        self.h = k32.OpenProcess(PROCESS_ACCESS, False, pid)
        if not self.h:
            raise OSError(f"OpenProcess({pid}) failed: {ctypes.get_last_error()}. "
                          "Try an elevated shell.")
        self.mods = modules(pid)

    def read(self, addr: int, n: int) -> bytes:
        buf = (ctypes.c_ubyte * n)()
        got = ctypes.c_size_t(0)
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
            raise OSError(f"read {addr:#x} failed: {ctypes.get_last_error()}")
        return bytes(buf[:got.value])

    def write(self, addr: int, payload: bytes) -> None:
        buf = (ctypes.c_ubyte * len(payload))(*payload)
        got = ctypes.c_size_t(0)
        if not k32.WriteProcessMemory(self.h, ctypes.c_void_p(addr), buf, len(payload),
                                      ctypes.byref(got)):
            raise OSError(f"write {addr:#x} failed: {ctypes.get_last_error()}")

    def write_protected(self, addr: int, payload: bytes) -> None:
        """Writes through a read-only page, restoring its protection afterwards."""
        old = wintypes.DWORD(0)
        if not k32.VirtualProtectEx(self.h, ctypes.c_void_p(addr), len(payload),
                                    PAGE_RW, ctypes.byref(old)):
            raise OSError(f"unprotect {addr:#x} failed: {ctypes.get_last_error()}")
        try:
            self.write(addr, payload)
        finally:
            again = wintypes.DWORD(0)
            k32.VirtualProtectEx(self.h, ctypes.c_void_p(addr), len(payload),
                                 old, ctypes.byref(again))

    def alloc_exec(self, payload: bytes) -> int:
        """RWX because the stub increments its own fire counter in this page."""
        addr = k32.VirtualAllocEx(self.h, None, max(len(payload), 0x1000),
                                  MEM_COMMIT_RESERVE, PAGE_RWX)
        if not addr:
            raise OSError(f"VirtualAllocEx failed: {ctypes.get_last_error()}. "
                          "A process with ACG enabled will refuse this.")
        self.write(addr, payload)
        return addr


# Byte offsets into the stub built below, for reading a live one back:
#    0  inc dword ptr [rip+0x1a]        -> counter at 0x20
#    6  test r8, r8
#    9  jz +7                           -> lands on 18, skipping the mov
#   11  mov dword ptr [r8], imm32       -> size imm at 0x0E
#   18  mov rax, imm64                  -> original at 0x14
#   28  jmp rax
STUB_SIZE_OFFSET = 0x0E
STUB_ORIGINAL_OFFSET = 0x14
STUB_COUNTER_OFFSET = 0x20


def build_stub(size: int, original: int) -> bytes:
    code = (
        b"\xFF\x05" + struct.pack("<i", STUB_COUNTER_OFFSET - 6)  # inc [rip+disp]
        + b"\x4D\x85\xC0"                                         # test r8, r8
        + b"\x74\x07"                                             # jz -> tail
        + b"\x41\xC7\x00" + struct.pack("<I", size)               # mov [r8], size
        + b"\x48\xB8" + struct.pack("<Q", original)               # mov rax, original
        + b"\xFF\xE0"                                             # jmp rax
    )
    assert len(code) == 30, len(code)
    return code + b"\xCC" * (STUB_COUNTER_OFFSET - len(code)) + struct.pack("<I", 0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pid", type=int, help="defaults to the running game")
    ap.add_argument("--size", type=int, default=8, help="maxMemberCount to request")
    ap.add_argument("--status", action="store_true", help="report without changing anything")
    ap.add_argument("--revert", action="store_true", help="restore the original import")
    args = ap.parse_args()

    pid = args.pid or find_pid(EXE_NAME)
    if not pid:
        print(f"error: {EXE_NAME} is not running", file=sys.stderr)
        return 2

    t = Target(pid)
    exe = t.mods.get(EXE_NAME.lower())
    dll = t.mods.get(IMPORT_DLL)
    if not exe or not dll:
        print("error: game or PlayFab module not found in the process", file=sys.stderr)
        return 2
    exe_base, _, exe_path = exe
    dll_base, dll_size, _ = dll

    slot = exe_base + iat_rva_for(Path(exe_path), IMPORT_DLL, IMPORT_NAME)
    current = struct.unpack("<Q", t.read(slot, 8))[0]
    in_dll = dll_base <= current < dll_base + dll_size
    print(f"pid {pid}  exe {exe_base:#x}  {IMPORT_DLL} {dll_base:#x}")
    print(f"IAT slot   {slot:#x}")
    print(f"  -> {current:#x}  ({'original export' if in_dll else 'HOOKED'})")

    if args.status:
        if not in_dll:
            stub_orig = struct.unpack("<Q", t.read(current + STUB_ORIGINAL_OFFSET, 8))[0]
            size = struct.unpack("<I", t.read(current + STUB_SIZE_OFFSET, 4))[0]
            fired = struct.unpack("<I", t.read(current + STUB_COUNTER_OFFSET, 4))[0]
            print(f"  stub requests maxMemberCount = {size}, original {stub_orig:#x}")
            print(f"  lobby creations intercepted   = {fired}")
            if fired == 0:
                print("  (the stub has not run; no lobby has been created since it was installed)")
        return 0

    if args.revert:
        if in_dll:
            print("nothing to revert")
            return 0
        original = struct.unpack("<Q", t.read(current + STUB_ORIGINAL_OFFSET, 8))[0]
        if not (dll_base <= original < dll_base + dll_size):
            print("error: stub does not carry a plausible original; refusing", file=sys.stderr)
            return 1
        t.write_protected(slot, struct.pack("<Q", original))
        k32.VirtualFreeEx(t.h, ctypes.c_void_p(current), 0, MEM_RELEASE)
        print(f"reverted -> {original:#x}")
        return 0

    if not in_dll:
        print("already hooked; use --revert first")
        return 1
    if not 1 <= args.size <= 32:
        print("error: --size must be between 1 and 32", file=sys.stderr)
        return 2

    stub = t.alloc_exec(build_stub(args.size, current))
    t.write_protected(slot, struct.pack("<Q", stub))
    now = struct.unpack("<Q", t.read(slot, 8))[0]
    if now != stub:
        print("error: IAT slot did not take the new pointer", file=sys.stderr)
        return 1
    print(f"stub       {stub:#x}  ({len(build_stub(args.size, current))} bytes)")
    print(f"IAT slot   -> {now:#x}")
    print(f"lobbies will now be created with maxMemberCount = {args.size}")
    print("PlayFab still validates this; acceptance is unverified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
