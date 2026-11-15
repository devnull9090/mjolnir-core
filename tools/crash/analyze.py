#!/usr/bin/env python3
"""Read the game's crash dumps: where each crash happened, as a stack, and
which crashes are the same.

    python tools/crash/analyze.py                      # every crash folder, grouped
    python tools/crash/analyze.py <crash folder> [...] # one crash in full
    python tools/crash/analyze.py --last               # the newest crash in full

A crash folder is %LOCALAPPDATA%\\Meteorite\\Saved\\Crashes\\UECC-Windows-<id>_0000
(or one unzipped from a crash report). Its CrashContext.runtime-xml lists
modules and offsets only, and that list is not reliable; UEMinidump.dmp holds
every thread's registers and stack. This reads the dump directly (no
debugger, no symbols):

- The crashing thread: the exception stream's thread. An assert or fatal
  error is raised on purpose, so its "exception" is the reporter's own; the
  thread whose stack holds the fatal-error path is the one that failed,
  found as the thread with the most game frames above KERNELBASE's raise.
- Its frames: return addresses on the stack, kept only when they point into a
  module's code just after a call instruction (read from the module's file on
  disk). Stack scanning can keep a stale address; the call check drops most
  of them.
- Each frame is named by the function that contains it, from the module's
  own unwind table (.pdata), as `FUN_<address>` the way Ghidra names it in
  the analysed exe (tools/ghidra/decompile.ps1 decompiles one), plus names
  from tools/crash/names.json where we know them.
- The Level Loader's breadcrumbs (ue4ss/MJOLNIRLevelLoader/breadcrumbs.txt,
  the steps of the last map load) when they were written within a minute of
  the crash.

The grouping signature is the error message (asserts) or exception code,
plus the first frames in the game's own modules.
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import struct
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
CRASHES = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Meteorite", "Saved", "Crashes")
INSTALL = r"C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved"
BREADCRUMBS = os.path.join(INSTALL, "Meteorite", "Binaries", "Win64", "ue4ss", "Mods", "MJOLNIRLevelLoader",
                           "breadcrumbs.txt")
GAME_MODULES = ("HaloCampaignEvolved", "HaloSimulation_tag_release", "UE4SS", "mjolnir_")
SYSTEM = ("ntdll", "KERNELBASE", "KERNEL32", "kernel32", "win32u", "user32", "ucrtbase", "VCRUNTIME", "msvcp")

THREAD_LIST, MODULE_LIST, MEMORY_LIST, EXCEPTION, MEMORY64_LIST = 3, 4, 5, 6, 9


class Dump:
    def __init__(self, path):
        self.f = open(path, "rb")
        sig, _ver, count, rva = struct.unpack("<4sIII", self.f.read(16))
        if sig != b"MDMP":
            raise ValueError(f"{path}: not a minidump")
        self.streams = {}
        self.f.seek(rva)
        for _ in range(count):
            kind, size, at = struct.unpack("<III", self.f.read(12))
            self.streams.setdefault(kind, (at, size))
        self.ranges = []  # (start, size, file offset)
        self._memory()
        self.modules = self._modules()
        self.threads = self._threads()
        self.exception = self._exception()

    def read(self, at, n):
        self.f.seek(at)
        return self.f.read(n)

    def _memory(self):
        if MEMORY64_LIST in self.streams:
            at, _ = self.streams[MEMORY64_LIST]
            n, base = struct.unpack("<QQ", self.read(at, 16))
            data = self.read(at + 16, 16 * n)
            off = base
            for i in range(n):
                start, size = struct.unpack_from("<QQ", data, 16 * i)
                self.ranges.append((start, size, off))
                off += size
        if MEMORY_LIST in self.streams:
            at, _ = self.streams[MEMORY_LIST]
            (n,) = struct.unpack("<I", self.read(at, 4))
            data = self.read(at + 4, 16 * n)
            for i in range(n):
                start, size, rva = struct.unpack_from("<QII", data, 16 * i)
                self.ranges.append((start, size, rva))
        self.ranges.sort()

    def mem(self, addr, n):
        for start, size, off in self.ranges:
            if start <= addr < start + size:
                n = min(n, start + size - addr)
                return self.read(off + addr - start, n)
        return b""

    def _string(self, rva):
        (n,) = struct.unpack("<I", self.read(rva, 4))
        return self.read(rva + 4, n).decode("utf-16-le", "replace")

    def _modules(self):
        at, _ = self.streams[MODULE_LIST]
        (n,) = struct.unpack("<I", self.read(at, 4))
        out = []
        for i in range(n):
            e = self.read(at + 4 + 108 * i, 108)
            base, size, _cs, _ts, name_rva = struct.unpack_from("<QIIII", e)
            path = self._string(name_rva)
            out.append({"base": base, "size": size, "path": path,
                        "name": os.path.splitext(os.path.basename(path.replace("\\", "/")))[0]})
        return out

    def _threads(self):
        at, _ = self.streams[THREAD_LIST]
        (n,) = struct.unpack("<I", self.read(at, 4))
        out = []
        for i in range(n):
            e = self.read(at + 4 + 48 * i, 48)
            tid, _sc, _pc, _pr, _teb, stack_start, stack_size, stack_rva, ctx_size, ctx_rva = \
                struct.unpack_from("<IIIIQQIIII", e)
            ctx = self.read(ctx_rva, ctx_size)
            rsp, rip = (struct.unpack_from("<Q", ctx, 0x98)[0], struct.unpack_from("<Q", ctx, 0xF8)[0]) \
                if len(ctx) >= 0x100 else (stack_start, 0)
            out.append({"tid": tid, "rsp": rsp, "rip": rip, "stack": (stack_start, stack_size, stack_rva)})
        return out

    def _exception(self):
        if EXCEPTION not in self.streams:
            return None
        at, _ = self.streams[EXCEPTION]
        tid, _align, code, _flags, _rec, addr = struct.unpack("<IIIIQQ", self.read(at, 32))
        return {"tid": tid, "code": code, "address": addr}

    def module_at(self, addr):
        for m in self.modules:
            if m["base"] <= addr < m["base"] + m["size"]:
                return m
        return None


class Image:
    """A module's file on disk: its sections and unwind table, for call checks
    and function starts."""
    cache = {}

    @classmethod
    def get(cls, path):
        if path not in cls.cache:
            try:
                cls.cache[path] = cls(path)
            except (OSError, ValueError, struct.error):
                cls.cache[path] = None
        return cls.cache[path]

    def __init__(self, path):
        self.data = open(path, "rb").read()
        d = self.data
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        if d[pe:pe + 4] != b"PE\0\0":
            raise ValueError("not a PE")
        nsec, opt_size = struct.unpack_from("<H", d, pe + 6)[0], struct.unpack_from("<H", d, pe + 20)[0]
        opt = pe + 24
        self.image_base = struct.unpack_from("<Q", d, opt + 24)[0]
        exc_rva, exc_size = struct.unpack_from("<II", d, opt + 112 + 3 * 8)
        self.sections = []
        for i in range(nsec):
            s = opt + opt_size + 40 * i
            vsize, va, raw_size, raw = struct.unpack_from("<IIII", d, s + 8)
            chars = struct.unpack_from("<I", d, s + 36)[0]
            self.sections.append((va, max(vsize, raw_size), raw, bool(chars & 0x20000000)))
        self.funcs = []
        off = self.file_offset(exc_rva)
        if off is not None:
            for i in range(exc_size // 12):
                b, e, _u = struct.unpack_from("<III", d, off + 12 * i)
                self.funcs.append((b, e))
            self.funcs.sort()
        self.starts = [b for b, _ in self.funcs]

    def file_offset(self, rva):
        for va, size, raw, _x in self.sections:
            if va <= rva < va + size:
                return raw + rva - va
        return None

    def executable(self, rva):
        return any(va <= rva < va + size and x for va, size, _raw, x in self.sections)

    def after_call(self, rva):
        off = self.file_offset(rva)
        if off is None or off < 7:
            return False
        b = self.data[off - 7:off]
        if b[2] == 0xE8:  # call rel32
            return True
        # call r/m64 (FF /2): 2 to 7 bytes long
        for n in range(2, 8):
            i = 7 - n
            if b[i] == 0xFF and (b[i + 1] >> 3) & 7 == 2:
                return True
            if i > 0 and b[i - 1] in (0x41, 0x48, 0x49) and b[i] == 0xFF and (b[i + 1] >> 3) & 7 == 2:
                return True
        return False

    def function(self, rva):
        import bisect
        i = bisect.bisect_right(self.starts, rva) - 1
        if i >= 0 and self.funcs[i][0] <= rva < self.funcs[i][1]:
            return self.funcs[i][0]
        return None


def load_names():
    path = os.path.join(HERE, "names.json")
    if not os.path.exists(path):
        return {}
    raw = json.load(open(path, encoding="utf-8"))
    SKIP.update(raw.get("_skip", []))
    return {mod: {int(k, 16): v for k, v in table.items() if not k.startswith("_")}
            for mod, table in raw.items() if not mod.startswith("_")}


SKIP = set()  # names.json "_skip": the fatal-error and crash-handler helpers
NAMES = load_names()


def frame_name(m, img, rva):
    start = img.function(rva) if img else None
    known = NAMES.get(m["name"], {})
    if start is not None and start in known:
        return f"{known[start]}+0x{rva - start:x}"
    if start is not None:
        base = img.image_base if img else 0
        return f"FUN_{base + start:x}+0x{rva - start:x}"
    return f"+0x{rva:x}"


def stack_frames(dump, thread, limit=40):
    """Return addresses on the thread's stack that follow a call in a module."""
    start, size, rva = thread["stack"]
    lo = max(thread["rsp"], start) if start <= thread["rsp"] < start + size else start
    # A full-memory dump keeps the stack in its memory list and leaves the
    # thread's own descriptor empty.
    data = dump.read(rva + (lo - start), start + size - lo) if rva and size else b""
    if not data:
        data = dump.mem(thread["rsp"], 512 * 1024)
    frames = []
    first = dump.module_at(thread["rip"]) if thread["rip"] else None
    if first:
        frames.append((thread["rip"], first))
    for i in range(0, len(data) - 7, 8):
        (v,) = struct.unpack_from("<Q", data, i)
        m = dump.module_at(v)
        if not m:
            continue
        img = Image.get(m["path"])
        r = v - m["base"]
        if img and (not img.executable(r) or not img.after_call(r)):
            continue
        frames.append((v, m))
        if len(frames) >= limit:
            break
    return frames


def describe(frames):
    out = []
    for addr, m in frames:
        img = Image.get(m["path"])
        r = addr - m["base"]
        out.append((m["name"], r, frame_name(m, img, r)))
    return out



def call_chain(named):
    """The frames that failed, without the crash handler above them: an assert
    raises through KERNELBASE, and everything the stack scan finds above the
    last raise in the top of the stack is exception dispatch and the crash
    reporter. Repeated addresses (stale copies) are dropped."""
    top = named[:45]
    raises = [i for i, (mod, _r, _n) in enumerate(top) if mod in ("KERNELBASE", "ntdll")]
    cut = raises[-1] + 1 if raises and any(m.startswith(GAME_MODULES) for m, _r, _n in named[raises[-1] + 1:]) else 0
    seen, out = set(), []
    for mod, r, n in named[cut:]:
        if (mod, r) in seen:
            continue
        seen.add((mod, r))
        out.append((mod, r, n))
    return out


def crash_thread(dump):
    """The thread that failed. A fatal error is raised deliberately (its
    exception sits in KERNELBASE), so prefer the thread with the most game
    frames among those that reach KERNELBASE or the exception thread."""
    by_tid = {t["tid"]: t for t in dump.threads}
    ex = dump.exception
    best, best_score = None, -1
    for t in dump.threads:
        named = describe(stack_frames(dump, t, 60))
        game = sum(1 for mod, _r, _n in named if mod.startswith(GAME_MODULES))
        raised = any(mod == "KERNELBASE" for mod, _r, _n in named[:6])
        score = game + (100 if ex and t["tid"] == ex["tid"] else 0) + (50 if raised else 0)
        if score > best_score:
            best, best_score = t, score
    return best or (by_tid.get(ex["tid"]) if ex else None)


def context_xml(folder):
    path = os.path.join(folder, "CrashContext.runtime-xml")
    if not os.path.exists(path):
        return {}
    s = open(path, encoding="utf-8", errors="replace").read()

    def tag(name):
        m = re.search(rf"<{name}>(.*?)</{name}>", s, re.S)
        return html.unescape(m.group(1)).strip() if m else ""

    return {"type": tag("CrashType"), "message": tag("ErrorMessage"), "build": tag("BuildVersion"),
            "engine": tag("EngineVersion")}


def film(folder):
    for f in os.listdir(folder):
        if f.endswith(".film-unreal"):
            return f.split("_dist")[0]
    return ""


def analyse(folder):
    dmp = os.path.join(folder, "UEMinidump.dmp")
    info = context_xml(folder)
    info["folder"] = folder
    info["time"] = dt.datetime.fromtimestamp(os.path.getmtime(folder))
    info["film"] = film(folder)
    if not os.path.exists(dmp):
        info["frames"] = []
        return info
    dump = Dump(dmp)
    ex = dump.exception
    info["code"] = f"0x{ex['code']:08X}" if ex else ""
    em = dump.module_at(ex["address"]) if ex else None
    info["fault"] = f"{em['name']}+0x{ex['address'] - em['base']:x}" if em else ""
    t = crash_thread(dump)
    info["thread"] = t["tid"] if t else None
    info["frames"] = call_chain(describe(stack_frames(dump, t, 80)))[:30] if t and t["rsp"] else []
    info["stackless"] = not info["frames"]
    if info["stackless"] and em:
        # Some dumps carry no thread records (their stacks and registers are
        # zero); the exception record still says where the fault was.
        info["frames"] = describe([(ex["address"], em)])
    return info


def signature(info):
    msg = re.sub(r"\s+", " ", info.get("message", ""))
    msg = re.sub(r"0x[0-9a-fA-F]+|\b\d{3,}\b", "#", msg)[:90]
    game = [(re.sub(r"\+0x[0-9a-f]+$", "", n) if mod == "HaloCampaignEvolved" else f"{mod}!" + re.sub(r"\+0x[0-9a-f]+$", "", n))
            for mod, _r, n in info.get("frames", []) if mod.startswith(GAME_MODULES)]
    # Everything down to the last fatal-error helper is the error path itself;
    # the caller below it is what failed.
    last = max((i for i, n in enumerate(game) if n in SKIP), default=-1)
    game = game[last + 1:last + 4]
    head = msg or info.get("code", "") or info.get("type", "")
    return head + " | " + (" < ".join(game) or "?") + (" (no stack in dump)" if info.get("stackless") else "")


def crumbs_near(when):
    if not os.path.exists(BREADCRUMBS):
        return None
    t = dt.datetime.fromtimestamp(os.path.getmtime(BREADCRUMBS))
    if abs((t - when).total_seconds()) > 60:
        return None
    lines = open(BREADCRUMBS, encoding="utf-8", errors="replace").read().splitlines()
    return lines[-15:]


def print_one(info):
    print(f"{info['time']:%Y-%m-%d %H:%M:%S}  {os.path.basename(info['folder'])}")
    print(f"  {info.get('type', '')}: {info.get('message', '').splitlines()[0] if info.get('message') else ''}")
    if len((info.get("message") or "").splitlines()) > 1:
        for line in info["message"].splitlines()[1:4]:
            if line.strip():
                print(f"    {line.strip()}")
    print(f"  build {info.get('build', '')}  match {info.get('film', '') or '-'}  "
          f"exception {info.get('code', '')} at {info.get('fault', '')}  thread {info.get('thread')}")
    if info.get("stackless"):
        print("  (the dump has no thread records: only the faulting address is known)")
    for mod, rva, name in info.get("frames", []):
        print(f"    {mod:28s} +0x{rva:08x}  {name}")
    crumbs = crumbs_near(info["time"])
    if crumbs:
        print("  Level Loader breadcrumbs (last steps before the crash):")
        for line in crumbs:
            print(f"    {line}")
    print(f"  signature: {signature(info)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folders", nargs="*")
    ap.add_argument("--last", action="store_true", help="the newest crash in full")
    ap.add_argument("--since", help="only crashes after this date, YYYY-MM-DD[THH:MM]")
    ap.add_argument("--dir", default=CRASHES)
    a = ap.parse_args()
    if a.folders or a.last:
        folders = a.folders or [max((os.path.join(a.dir, f) for f in os.listdir(a.dir)), key=os.path.getmtime)]
        for f in folders:
            print_one(analyse(f))
            print()
        return
    since = dt.datetime.fromisoformat(a.since) if a.since else None
    groups = defaultdict(list)
    for f in sorted(os.listdir(a.dir)):
        path = os.path.join(a.dir, f)
        if not os.path.isdir(path):
            continue
        if since and dt.datetime.fromtimestamp(os.path.getmtime(path)) < since:
            continue
        try:
            info = analyse(path)
        except Exception as e:  # a truncated dump must not stop the census
            print(f"{f}: unreadable ({e})", file=sys.stderr)
            continue
        groups[signature(info)].append(info)
    for sig, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        items.sort(key=lambda i: i["time"])
        maps = Counter(i["film"].split("_")[1] if i["film"].count("_") else "-" for i in items)
        print(f"{len(items):3d}x  {sig}")
        print(f"      {items[0]['time']:%m-%d %H:%M} .. {items[-1]['time']:%m-%d %H:%M}  maps {dict(maps)}  "
              f"newest {os.path.basename(items[-1]['folder'])}")


if __name__ == "__main__":
    main()
