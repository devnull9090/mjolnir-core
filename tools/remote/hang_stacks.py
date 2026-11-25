"""Each thread of a minidump (tools/remote/hangdump.ps1, hangwatch.ps1): where its
instruction pointer is, where the thread started, and the return addresses its
stack holds, as module+offset. A scan of the stack, not an unwind, so some
entries are stale; the game's main thread starts in HaloCampaignEvolved.exe.

    python -I tools/remote/hang_stacks.py <dump> [filter]

Needs the `minidump` package (pip install minidump)."""
import sys, struct
from minidump.minidumpfile import MinidumpFile

path = sys.argv[1]
only = sys.argv[2] if len(sys.argv) > 2 else None
md = MinidumpFile.parse(path)
reader = md.get_reader()
mods = [(m.baseaddress, m.baseaddress + m.size, m.name.split("\\")[-1]) for m in md.modules.modules]

def where(addr):
    for lo, hi, name in mods:
        if lo <= addr < hi:
            return "%s+%x" % (name, addr - lo)
    return None

contexts = {}
if md.threads:
    for t in md.threads.threads:
        contexts[t.ThreadId] = t

info = {}
if md.thread_info:
    for t in md.thread_info.infos:
        info[t.ThreadId] = t

for t in md.threads.threads:
    tid = t.ThreadId
    ctx = t.ContextObject
    rip = getattr(ctx, "Rip", None)
    rsp = getattr(ctx, "Rsp", None)
    start = info.get(tid)
    startaddr = getattr(start, "StartAddress", None) if start else None
    frames = []
    try:
        stack = t.Stack
        base, size = stack.StartOfMemoryRange, stack.MemoryLocation.DataSize
        lo = max(rsp or base, base)
        data = reader.read(lo, base + size - lo)
        for i in range(0, len(data) - 7, 8):
            v = struct.unpack_from("<Q", data, i)[0]
            w = where(v)
            if w and not w.startswith("HaloCampaignEvolved.exe+0 "):
                frames.append(w)
            if len(frames) >= 24:
                break
    except Exception as e:
        frames.append("stack unreadable: %s" % e)
    line = "tid %6d rip %s start %s" % (tid, where(rip) if rip else "?", where(startaddr) if startaddr else "?")
    if only and only not in line and not any(only in f for f in frames):
        continue
    print(line)
    print("    " + " < ".join(frames[:24]))
