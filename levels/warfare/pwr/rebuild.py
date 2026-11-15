"""Rebuild PWR in an isolated HEK copy; never changes the shared HEK or game install.

python levels/warfare/pwr/rebuild.py --source-dir C:/haloce/ce_conversions/warfare/PWR/expansion/world-v3/source-build --skip-geometry
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Defaults to --source-dir; legacy research uses expansion/source-build")
    parser.add_argument("--hek", type=Path, default=Path("C:/haloce/hek"))
    parser.add_argument("--skip-geometry", action="store_true")
    parser.add_argument("--source-dir",type=Path,help="Prepared v3 source directory; requires --skip-geometry")
    parser.add_argument("--legacy-scaffold",action="store_true",help="Explicitly build the obsolete analytic prototype for research")
    args = parser.parse_args()
    if not args.source_dir and not args.legacy_scaffold:
        parser.error("Use --source-dir <world-v3/source-build> --skip-geometry for the current world; --legacy-scaffold is obsolete research only")
    default_output=args.source_dir or Path("C:/haloce/ce_conversions/warfare/PWR/expansion/source-build")
    output, original = (args.output or default_output).resolve(), args.hek.resolve()
    source=args.source_dir.resolve() if args.source_dir else ROOT
    if args.source_dir and not args.skip_geometry:raise ValueError("Prepared source directory requires --skip-geometry")
    if output == original or original in output.parents:
        raise ValueError("Build output must be outside the installed HEK")
    hek, logs = output / "hek", output / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    if not hek.exists():
        hek.mkdir()
        print("PWR: copying external HEK dependencies into isolated output", flush=True)
        shutil.copytree(original / "tags", hek / "tags")
        (hek / "maps").mkdir()
        for name in ("tool.exe", "ogg.dll", "vorbis.dll", "vorbisenc.dll", "vorbisfile.dll", "EulaHEK.dll"):
            shutil.copy2(original / name, hek / name)
        for name in ("sounds.map", "loc.map"):
            shutil.copy2(original / "maps" / name, hek / "maps" / name)
        (hek / ".pwr-isolated-build").write_text(str(original))
    elif not (hek / ".pwr-isolated-build").is_file():
        raise ValueError("Existing HEK output lacks its PWR isolation marker")
    # No bitmaps.map is installed in this private HEK: cache embeds its lightmap.
    if (hek / "maps/bitmaps.map").exists() and (hek / "maps/bitmaps.map").stat().st_size:
        raise ValueError("Isolated PWR HEK must embed bitmaps; found nonempty shared cache")

    def stage(name, command, expected=None, hek_stage=False):
        print("PWR:", name, flush=True)
        debug = hek / "debug.txt"
        before = debug.read_text(errors="replace") if debug.exists() else ""
        stamp = expected.stat().st_mtime_ns if expected and expected.exists() else -1
        # Stream output straight to a file: HEK can prompt for missing shaders;
        # an in-progress diagnostic must remain readable while it runs.
        log_path = logs / (name + ".log")
        with log_path.open("wb") as log:
            process = subprocess.run([str(c) for c in command], cwd=hek if hek_stage else REPO,
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        text = log_path.read_text(errors="replace")
        if hek_stage and debug.exists():
            after = debug.read_text(errors="replace")
            text += "\nHEK debug additions:\n" + (after[len(before):] if after.startswith(before) else after)
        (logs / (name + ".log")).write_text(text)
        if process.returncode:
            raise RuntimeError(f"{name} failed ({process.returncode}); see {logs / (name+'.log')}")
        if expected and (not expected.exists() or expected.stat().st_size == 0 or expected.stat().st_mtime_ns <= stamp):
            raise RuntimeError(f"{name} did not refresh {expected}")
        errors=[]
        for line in text.splitlines():
            if "toolbeta.map" in line or line.startswith(("PIL not found", "lxml not found")):
                continue
            if name == "cache" and "successfully built cache file" in text and (
                    "Failed to read data file header bitmaps" in line or "FAILED TO OPEN DATA-CACHE FILE" in line):
                continue
            if re.search(r"###\s*ERROR|\bERROR:|\bEXCEPTION\b|assertion failed|\bFATAL\b|Traceback \(most recent",line,re.I):
                errors.append(line)
        if errors:
            raise RuntimeError(f"{name} logged errors: {errors[0]}; see {logs}")
        if name == "cache" and "successfully built cache file" not in text:
            raise RuntimeError("HEK did not report cache success")
        print("PWR:", name, "passed", flush=True)

    source_jms=source/"data/levels/warfare/pwr/models/pwr.JMS"
    if not args.skip_geometry:
        payload=logs/"mcp-geometry-args.json"
        code="import runpy,sys\nsys.argv=['build_geometry.py']\nrunpy.run_path("+repr(str(ROOT/"build_geometry.py"))+",run_name='__main__')"
        payload.write_text(json.dumps({"code":code,"user_prompt":"Rebuild Pelican Warfare through Blender MCP."}))
        stage("geometry",["uvx","--from","mcp-for-blender==2.2.7","python",REPO/"tools/blender/mcp_client.py",
                          "execute_blender_code","--args-file",payload,"--out",logs/"mcp-geometry-receipt.json","--timeout","900"],source_jms)
    # Asset-marked Blender datablocks retain fake users. Reject auto-numbered
    # duplicate material names before HEK's interactive missing-shader loop.
    header=source_jms.read_text().splitlines()[:40]
    if any(re.fullmatch(r"[A-Za-z_+ !]+\.\d{3}",line.strip()) for line in header):
        raise RuntimeError("Auto-numbered shader in JMS; regenerate with a clean owned Blender scene")
    shader=hek/"tags/levels/warfare/pwr/shaders/pwr_cliffs.shader_environment"
    shader.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(hek/"tags/levels/b30/shaders/cliffs.shader_environment",shader)
    water=hek/"tags/levels/warfare/pwr/shaders/pwr_water.shader_transparent_water"
    shutil.copy2(hek/"tags/levels/b30/shaders/water.shader_transparent_water",water)
    shutil.copy2(hek/"tags/levels/test/bloodgulch/shaders/blood ground.shader_environment",
                 hek/"tags/levels/warfare/pwr/shaders/pwr_road.shader_environment")
    model=hek/"data/levels/warfare/pwr/models/pwr.JMS"
    model.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source_jms,model)
    bsp=hek/"tags/levels/warfare/pwr/pwr.scenario_structure_bsp"
    scenario=hek/"tags/levels/warfare/pwr/pwr.scenario"
    bitmap=hek/"tags/levels/warfare/pwr/pwr.bitmap"
    tool=hek/"tool.exe"
    stage("structure",[tool,"structure",r"levels\warfare\pwr","pwr"],bsp,True)
    stage("scenario",[sys.executable,ROOT/"build_scenario.py","--hek",hek,"--placements",source/"placements.json","--output",scenario],scenario)
    stage("lightmaps",[tool,"lightmaps",r"levels\warfare\pwr\pwr","pwr","0","0.1"],bitmap,True)
    cache=hek/"maps/pwr.map"
    stage("cache",[tool,"build-cache-file",r"levels\warfare\pwr\pwr"],cache,True)
    receipt={"schema":"pwr-ce-build-v1","map":str(cache),"map_sha256":digest(cache),
             "inputs":{str(path):digest(path) for path in [ROOT/"build_world_v3.py" if args.source_dir else ROOT/"build_geometry.py",source/"layout.json",source/"placements.json",source_jms]},
             "compiled":{"bsp_sha256":digest(bsp),"scenario_sha256":digest(scenario),"lightmap_sha256":digest(bitmap)},
             "validation":"Blender manifold check, HEK structure/lightmaps/cache success and scenario roundtrip. Runtime untested."}
    (output/"build-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print("PWR_BUILD_COMPLETE",cache,flush=True)


if __name__ == "__main__":
    main()
