"""Bucket survey function use against the CU4 HS table and the compiler corpus."""
import json
import sys

survey = json.load(open(sys.argv[1]))
console = json.load(open(sys.argv[2]))
corpus = json.load(open(sys.argv[3]))
fs = {f["name"]: f for f in console["functions"]}
globs = {g["name"]: g for g in console["globals"]}
cnames = {(o["name"] if isinstance(o, dict) else o) for o in
          (corpus["functions"].values() if isinstance(corpus["functions"], dict) else corpus["functions"])}
rows = survey["rows"]
# Dedupe by fid: a map counts once per download.
by_fid = {}
for r in rows:
    if r.get("calls"):
        by_fid.setdefault(r["fid"], set()).update(r["calls"])
n_scripted = len(by_fid)
per = {}
for fid, calls in by_fid.items():
    for c in calls:
        per[c] = per.get(c, 0) + 1
buckets = {"live": [], "live_not_in_compiler": [], "stub": [], "missing": []}
for fn, n in sorted(per.items(), key=lambda kv: -kv[1]):
    f = fs.get(fn)
    if f is None:
        buckets["missing"].append((fn, n, "global" if fn in globs else ""))
    elif f["stub"]:
        buckets["stub"].append((fn, n))
    elif fn not in cnames:
        buckets["live_not_in_compiler"].append((fn, n))
    else:
        buckets["live"].append((fn, n))
dev = {}
for r in rows:
    if "error" in r:
        continue
    d = dev.setdefault(r["fid"], [0, 0, 0])
    d[0] = max(d[0], r.get("machines", 0))
    d[1] = max(d[1], r.get("controls", 0))
    d[2] = max(d[2], r.get("device_groups", 0))
out = {
    "maps": len({r["fid"] for r in rows}),
    "map_files": len(rows),
    "errors": sum(1 for r in rows if "error" in r),
    "maps_with_scripts": n_scripted,
    "maps_with_machines": sum(1 for d in dev.values() if d[0]),
    "maps_with_controls": sum(1 for d in dev.values() if d[1]),
    "maps_with_device_groups": sum(1 for d in dev.values() if d[2]),
    "buckets": {k: v for k, v in buckets.items()},
}
json.dump(out, open(sys.argv[4], "w"), indent=1)
for k in ("maps", "map_files", "errors", "maps_with_scripts", "maps_with_machines",
          "maps_with_controls", "maps_with_device_groups"):
    print(k, out[k])
for k, v in buckets.items():
    print("\n==", k, len(v), "functions; map-uses", sum(x[1] for x in v))
    print(", ".join("%s %d%s" % (x[0], x[1], (" [" + x[2] + "]") if len(x) > 2 and x[2] else "") for x in v[:70]))
