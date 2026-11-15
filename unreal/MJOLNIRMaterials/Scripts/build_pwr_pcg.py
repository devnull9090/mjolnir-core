"""Run saved stock UPCGGraphs from a JSON request; editor only, no game install.

MJ_PCG_REQUEST = {jobs:[{input,output,graph,seed,scale_min,scale_max}]}
Each job's source points become a saved PCGDataAsset beside its saved graph.
"""
import json
import os
import hashlib
from pathlib import Path

import unreal

request_path = Path(os.environ["MJ_PCG_REQUEST"])
request = json.loads(request_path.read_text(encoding="utf-8"))
world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
if not world:
    raise RuntimeError("PCG requires an editor world")
results = []
for job in request["jobs"]:
    source = Path(job["input"]).resolve()
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    output = Path(job["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    if not unreal.MjolnirPCGLibrary.generate_points(
        world, str(source), job["graph"], str(output.resolve()),
        int(job["seed"]), float(job.get("scale_min", .85)), float(job.get("scale_max", 1.15))
    ):
        raise RuntimeError(f"PCG generation failed: {job['graph']}")
    result = json.loads(output.read_text(encoding="utf-8"))
    if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError("PCG source changed during editor generation")
    result["source_sha256"] = source_hash
    output.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    results.append({"graph": result["graph"], "input_count": result["input_count"],
                    "output_count": len(result["points"]), "seed": result["seed"],
                    "output": str(output.resolve())})
receipt = {"schema": 1, "engine": unreal.SystemLibrary.get_engine_version(),
           "jobs": results, "runtime_pcg": False}
request_path.with_suffix(".receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
unreal.log("MJOLNIR PCG graph jobs completed: " + json.dumps(results))
