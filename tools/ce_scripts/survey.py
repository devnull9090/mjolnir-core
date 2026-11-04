"""Decompile every halomaps .map's scripts; tally function use per map."""
import glob
import io
import json
import os
import struct
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))
import ce_hs  # noqa: E402

root = sys.argv[1]
out_dir = sys.argv[2]
os.makedirs(os.path.join(out_dir, "hsc"), exist_ok=True)
per_fn = {}
rows = []
for meta in sorted(glob.glob(os.path.join(root, "maps", "*", "meta.json"))):
    fid = os.path.basename(os.path.dirname(meta))
    try:
        title = json.load(open(meta, encoding="utf-8")).get("title", "")
    except Exception:
        title = ""
    for mp in glob.glob(os.path.join(os.path.dirname(meta), "files", "**", "*.map"), recursive=True):
        base = os.path.basename(mp).lower()
        if base in ("bitmaps.map", "sounds.map", "loc.map", "ui.map"):
            continue
        row = {"fid": fid, "title": title, "map": os.path.relpath(mp, root)}
        try:
            m, s, syntax, strings, scripts, globs, info = ce_hs.load(mp)
            b = m.b
            row["machines"] = struct.unpack_from("<I", b, s + 0x294)[0]
            row["controls"] = struct.unpack_from("<I", b, s + 0x2AC)[0]
            row["device_groups"] = len(info["device_groups"])
            row["scripts"] = len(scripts)
            row["globals"] = len(globs)
            calls = {}
            if syntax:
                expr, calls = ce_hs.decompiler(syntax, strings)
                buf = io.StringIO()
                with redirect_stdout(buf):
                    for name, t, init in globs:
                        print("(global %s %s)" % (name, expr(init)))
                    for name, (st, rt, rootx) in scripts:
                        print("\n(script %s %s\n    %s)" % (
                            ce_hs.SCRIPT_TYPES[st] if st < 5 else st, name, expr(rootx)))
                with open(os.path.join(out_dir, "hsc", "%s_%s.hsc" % (fid, base[:-4].replace(" ", "_"))),
                          "w", encoding="utf-8") as f:
                    f.write(buf.getvalue())
            row["calls"] = calls
            for fn in calls:
                per_fn[fn] = per_fn.get(fn, 0) + 1
        except Exception as e:  # noqa: BLE001
            row["error"] = repr(e)[:200]
        rows.append(row)
json.dump({"per_fn": per_fn, "rows": rows}, open(os.path.join(out_dir, "survey.json"), "w"), indent=0)
print(len(rows), "maps;", sum(1 for r in rows if r.get("scripts")), "with scripts;",
      sum(1 for r in rows if "error" in r), "errors")
