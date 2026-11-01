"""Pure-Python local extraction cache shared by the add-on and preparation CLI."""
import hashlib
import json
from pathlib import Path
import subprocess
import struct


def repair_preview_winding(path):
    """Repair cached CLI glTF faces opposed to their authored vertex normals.

    Observed on the shipped Uluwatu/Kuenovo exports. Only index order changes;
    positions, UVs and normals stay intact. Already-consistent caches are unchanged.
    """
    import numpy as np
    data = bytearray(Path(path).read_bytes())
    length = struct.unpack_from("<I",data,12)[0]
    doc = json.loads(data[20:20+length])
    binary = 28+length
    def accessor(index):
        a=doc["accessors"][index]; view=doc["bufferViews"][a["bufferView"]]
        dtype={5126:"<f4",5125:"<u4",5123:"<u2",5121:"u1"}[a["componentType"]]
        width={"SCALAR":1,"VEC2":2,"VEC3":3,"VEC4":4}[a["type"]]
        offset=binary+view.get("byteOffset",0)+a.get("byteOffset",0)
        stride=view.get("byteStride",np.dtype(dtype).itemsize*width)
        return np.ndarray((a["count"],width),dtype=dtype,buffer=data,offset=offset,
                          strides=(stride,np.dtype(dtype).itemsize))
    flipped=0
    for mesh in doc["meshes"]:
        for primitive in mesh["primitives"]:
            attrs=primitive["attributes"]
            if "NORMAL" not in attrs or primitive.get("mode",4)!=4:
                continue
            pos,norm=accessor(attrs["POSITION"]),accessor(attrs["NORMAL"])
            indices=accessor(primitive["indices"]).reshape(-1,3)
            tri=pos[indices]
            face=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
            dot=np.sum(face*norm[indices].mean(axis=1),axis=1)
            valid=np.abs(dot)>1e-12
            if valid.any() and np.mean(dot[valid]<0)>.9:
                indices[:,[1,2]]=indices[:,[2,1]]
                flipped+=len(indices)
    if flipped:
        Path(path).write_bytes(data)
        Path(str(path)+".winding.json").write_text(json.dumps({"triangles_reoriented":flipped,
            "reason":"Exported winding opposed authored normals; corrected local preview indices only"}),encoding="utf-8")
    return flipped


def cache_asset(cli, paks, cache, asset, kind="mesh"):
    if kind not in {"mesh", "texture"}:
        raise ValueError(kind)
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    package = asset.split(".")[0].removeprefix("/Game/")
    key = hashlib.sha256((str(Path(paks).resolve())+"|"+package).encode()).hexdigest()[:16]
    path = cache/(package.rsplit("/",1)[-1]+"_"+key+(".glb" if kind=="mesh" else ".png"))
    if not path.exists():
        result = subprocess.run([str(cli), kind, "export", "--paks", str(paks),
                                 "--asset", package, "--out", str(path)],
                                capture_output=True, text=True, timeout=180,
                                creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout)[-1800:])
        path.with_suffix(".source.json").write_text(json.dumps({"asset":asset,"paks":str(paks),
            "kind":kind,"note":"Local game extraction; do not redistribute. Rebuild cache after game updates."},indent=2),encoding="utf-8")
    if kind=="mesh":
        repair_preview_winding(path)
    return path
