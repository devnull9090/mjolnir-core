#!/usr/bin/env python3
"""Run ce_translate.py over the halomaps mirror and compile what it writes.

    check_corpus.py <halomaps root> <out dir> [--only <fid>...] [--mjolnir PATH] [--devices]

Writes <out dir>/corpus.json: per map, its scripts before and after, what the
compiler said, and the tallies of everything left out. `--devices` keeps to
maps whose scripts move a device. The figure to hold is `failed`: a map whose
output the compiler refuses.
"""
import argparse
import collections
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ce_translate  # noqa: E402

SKIP = ("bitmaps.map", "sounds.map", "loc.map", "ui.map")
MOVES = ("device_set_position", "device_set_position_immediate", "device_set_power", "device_group_set",
         "device_group_set_immediate", "device_operates_automatically_set")


def maps(root, only, survey=None, devices=False):
    if survey:
        # survey.py's survey.json already knows which maps have scripts.
        with open(survey, encoding="utf-8") as f:
            for r in json.load(f)["rows"]:
                if r.get("scripts") and (not only or r["fid"] in only) and (not devices or any(c in (r.get("calls") or {}) for c in MOVES)):
                    yield r["fid"], os.path.join(root, r["map"])
        return
    for meta in sorted(glob.glob(os.path.join(root, "maps", "*", "meta.json"))):
        fid = os.path.basename(os.path.dirname(meta))
        if only and fid not in only:
            continue
        for mp in glob.glob(os.path.join(os.path.dirname(meta), "files", "**", "*.map"), recursive=True):
            if os.path.basename(mp).lower() not in SKIP:
                yield fid, mp


def check(fid, path, a):
    t = ce_translate.Translator(path)
    if not t.scripts:
        return None
    moved = any(isinstance(e, ce_translate.Call) and e.fn in MOVES
                for s in t.scripts for x in s.body for e in ce_translate.walk(x))
    if a.devices and not moved:
        return None
    before = len(t.scripts)
    t.run()
    stem = os.path.join(a.out, "hsc", f"{fid}_{os.path.basename(path)[:-4].replace(' ', '_')}")
    report = t.report()
    with open(stem + ".hsc", "w", encoding="utf-8") as f:
        f.write(t.text())
    with open(stem + ".names.json", "w", encoding="utf-8") as f:
        json.dump(report["names"], f)
    r = subprocess.run([a.mjolnir, "compile", stem + ".hsc", "--names", stem + ".names.json"], capture_output=True,
                       text=True, cwd=ce_translate.REPO)
    return {"fid": fid, "map": os.path.basename(path), "before": before, "after": len(t.scripts), "moved": moved,
            "rules": len(report["notes"].get("rule", {})), "signals": len(report["notes"].get("signal", {})),
            "ok": r.returncode == 0, "errors": [x for x in r.stderr.splitlines() if x.strip()][:6],
            "notes": report["notes"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root")
    ap.add_argument("out")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--devices", action="store_true")
    ap.add_argument("--survey", help="survey.py's survey.json, to skip maps with no scripts")
    ap.add_argument("--mjolnir", default=os.path.join(ce_translate.REPO, "target", "release", "mjolnir"))
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, "hsc"), exist_ok=True)
    rows, crashes = [], []
    for fid, path in maps(a.root, set(a.only or []), a.survey, a.devices):
        try:
            row = check(fid, path, a)
        except Exception as e:  # noqa: BLE001 - one protected map must not stop the run
            crashes.append({"fid": fid, "map": os.path.basename(path), "error": repr(e)[:200]})
            continue
        if row:
            rows.append(row)
    failed = [r for r in rows if not r["ok"]]
    tally = collections.defaultdict(collections.Counter)
    for r in rows:
        for kind, what in r["notes"].items():
            for name in what:
                tally[kind][name] += 1
    with open(os.path.join(a.out, "corpus.json"), "w", encoding="utf-8") as f:
        json.dump({"maps": len(rows), "failed": len(failed), "crashes": crashes, "rows": rows,
                   "tally": {k: dict(v.most_common(200)) for k, v in tally.items()}}, f, indent=0)
    print(f"{len(rows)} map(s), {len(failed)} refused by the compiler, {len(crashes)} crashed; "
          f"{sum(1 for r in rows if r['rules'])} with device rules, {sum(1 for r in rows if r['signals'])} with signals")
    errors = collections.Counter(e.split(":", 1)[-1].strip()[:70] for r in failed for e in r["errors"][:1])
    for e, n in errors.most_common(12):
        print(f"  {n:4} {e}")
    for c in crashes[:8]:
        print("  crash", c["fid"], c["error"][:120])


if __name__ == "__main__":
    main()
