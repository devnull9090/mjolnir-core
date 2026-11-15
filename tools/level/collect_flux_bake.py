"""Copy and seal completed native Flux exports; never alters installed files."""
import argparse
import json
from pathlib import Path
import shutil

from flux_heightfield import state_matches, verify_state_files, sha256


def collect(spec_path,source,out):
    source=Path(source).resolve();out=Path(out).resolve()
    if out.exists():raise ValueError("Choose a new output folder for an immutable bake")
    spec=json.loads(Path(spec_path).read_text(encoding="utf-8"))
    prepared=[]
    for entry in spec["domains"]:
        state_path=source/"flux_state"/entry["id"]/"state.json"
        state=json.loads(state_path.read_text(encoding="utf-8"))
        if not state_matches(state,entry):raise ValueError("Export no longer matches authoring spec: "+entry["id"])
        verify_state_files(source,state)
        prepared.append((entry,state))
    out.mkdir(parents=True)
    for entry,state in prepared:
        for key in ("height","velocity","ground"):
            path=out/state[key];path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source/state[key],path)
        (out/"flux_state"/entry["id"]/"state.json").write_text(json.dumps(state,indent=2)+"\n")
        entry["state"]=state;entry["playback"]="baked"
    (out/"flux.spec.json").write_text(json.dumps(spec,indent=2)+"\n")
    receipt={"schema":"mjolnir-flux-collected-v1","authoring_spec_sha256":sha256(spec_path),
             "files":{p.relative_to(out).as_posix():sha256(p) for p in out.rglob("*") if p.is_file()}}
    (out/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt,indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("spec","source","out"):p.add_argument("--"+name,required=True)
    a=p.parse_args();collect(a.spec,a.source,a.out)
