#!/usr/bin/env python3
"""Capture OutputDebugString text from every process in this session (the
DBWIN_BUFFER protocol a debugger-less listener uses), one line per message
with the sender's pid, until killed.

    python tools/ue/dbwin.py out.log [pid-or-name-filter]

The D3D12 debug layer (`-d3ddebug`, with the game's own d3d12SDKLayers.dll
in Binaries/Win64/D3D12/x64) reports why it refuses a pipeline here, and the
shipping game writes no log of its own.
"""
import ctypes
import ctypes.wintypes as W
import sys
import time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.CreateEventW.restype = W.HANDLE
k32.CreateFileMappingW.restype = W.HANDLE
k32.MapViewOfFile.restype = ctypes.c_void_p
k32.MapViewOfFile.argtypes = [W.HANDLE, W.DWORD, W.DWORD, W.DWORD, ctypes.c_size_t]
k32.OpenProcess.restype = W.HANDLE
k32.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]

PAGE_READWRITE, FILE_MAP_READ, WAIT_OBJECT_0 = 0x04, 0x0004, 0


def image_of(pid, cache={}):
    if pid not in cache:
        h = k32.OpenProcess(0x1000, False, pid)
        name = "?"
        if h:
            buf = ctypes.create_unicode_buffer(520)
            n = W.DWORD(520)
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                name = buf.value.rsplit("\\", 1)[-1]
            k32.CloseHandle(h)
        cache[pid] = name
    return cache[pid]


def main():
    out = open(sys.argv[1], "a", encoding="utf-8", buffering=1)
    want = sys.argv[2].lower() if len(sys.argv) > 2 else None
    ready = k32.CreateEventW(None, False, False, "DBWIN_BUFFER_READY")
    data = k32.CreateEventW(None, False, False, "DBWIN_DATA_READY")
    mapping = k32.CreateFileMappingW(W.HANDLE(-1), None, PAGE_READWRITE, 0, 4096, "DBWIN_BUFFER")
    view = k32.MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, 4096)
    if not (ready and data and mapping and view):
        sys.exit(f"DBWIN setup failed ({ctypes.get_last_error()}); is another listener running?")
    out.write(f"--- listening {time.strftime('%H:%M:%S')}\n")
    k32.SetEvent(ready)
    while True:
        if k32.WaitForSingleObject(data, 1000) == WAIT_OBJECT_0:
            pid = ctypes.c_uint32.from_address(view).value
            text = ctypes.string_at(view + 4).decode("latin-1", "replace").rstrip("\r\n")
            name = image_of(pid)
            if not want or want in name.lower() or want == str(pid):
                out.write(f"{time.strftime('%H:%M:%S')} [{name}:{pid}] {text}\n")
            k32.SetEvent(ready)


if __name__ == "__main__":
    main()
