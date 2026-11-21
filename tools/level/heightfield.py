"""Hash-checked master terrain shared by rendering, placement and collision.

The origin is always minimum authoring X/Y, in metres. Input row_order=-y
means row zero is maximum Y; loaded arrays are canonical +y. Heights decode
as offset_m + stored_value * scale_m. No automatic range normalization occurs.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import numpy as np

SCHEMA = "pwr-heightfield-v1"

def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            digest.update(block)
    return digest.hexdigest()

def _read_raster(root, spec, dimensions, mask=False):
    path=(root/str(spec["path"])).resolve()
    expected=str(spec.get("sha256","")).lower()
    if len(expected)!=64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError(f"{path}: an explicit SHA-256 is required")
    if sha256(path)!=expected:
        raise ValueError(f"{path}: SHA-256 mismatch")
    encoding=spec["encoding"]
    if encoding in ("uint16_png","uint8_png","uint16_tiff","float32_tiff"):
        from PIL import Image  # Optional for NumPy/raw consumers such as Blender.
        with Image.open(path) as image:
            data=np.array(image)
        if data.ndim!=2:
            raise ValueError(f"{path}: expected a single-channel raster")
        if encoding.startswith("uint"):
            limit=255 if encoding.startswith("uint8") else 65535
            if data.dtype.kind not in "ui" or np.min(data)<0 or np.max(data)>limit:
                raise ValueError(f"{path}: invalid {encoding} samples")
            if encoding.startswith("uint16") and data.dtype.itemsize<2:
                raise ValueError(f"{path}: an 8-bit image cannot be declared as 16-bit terrain")
            if encoding.startswith("uint8") and data.dtype.itemsize!=1:
                raise ValueError(f"{path}: an 8-bit mask image is required")
        elif data.dtype.kind!="f" or data.dtype.itemsize!=4:
            raise ValueError(f"{path}: float TIFF required")
    elif encoding=="float32_npy":
        data=np.load(path,allow_pickle=False)
        if data.dtype.kind!="f" or data.dtype.itemsize!=4:
            raise ValueError(f"{path}: expected float32 NPY")
    elif encoding in ("uint16_raw_le","float32_raw_le"):
        dtype=np.dtype("<u2" if encoding.startswith("uint16") else "<f4")
        size=dimensions[0]*dimensions[1]
        if path.stat().st_size!=size*dtype.itemsize:
            raise ValueError(f"{path}: raw byte length does not match dimensions")
        data=np.fromfile(path,dtype=dtype).reshape(dimensions[1],dimensions[0])
    else:
        raise ValueError(f"Unsupported raster encoding: {encoding}")
    if data.shape!=(dimensions[1],dimensions[0]):
        raise ValueError(f"{path}: raster dimensions {data.shape[::-1]} != {dimensions}")
    offset=float(spec.get("offset_m",0) if not mask else spec.get("offset",0))
    scale=float(spec.get("scale_m",1) if not mask else spec.get("scale",1/255 if encoding=="uint8_png" else 1))
    if not np.isfinite(offset) or not np.isfinite(scale) or scale<=0:
        raise ValueError(f"{path}: finite offset and positive scale required")
    data=data.astype(np.float64)*scale+offset
    if not np.all(np.isfinite(data)):
        raise ValueError(f"{path}: non-finite raster sample")
    if mask and (np.min(data)<0 or np.max(data)>1):
        raise ValueError(f"{path}: mask must decode to [0,1]")
    return data

@dataclass
class Heightfield:
    heights_m: np.ndarray
    origin_m: tuple[float,float]
    spacing_m: tuple[float,float]
    masks: dict[str,np.ndarray]
    metadata: dict
    manifest_sha256: str
    path: Path

    @property
    def dimensions(self):
        return self.heights_m.shape[1],self.heights_m.shape[0]

    @property
    def bounds_m(self):
        w,h=self.dimensions
        return self.origin_m,(self.origin_m[0]+(w-1)*self.spacing_m[0],self.origin_m[1]+(h-1)*self.spacing_m[1])

    def _sample(self,data,x,y,bounds_error,triangulated=False):
        x,y=np.broadcast_arrays(np.asarray(x,dtype=float),np.asarray(y,dtype=float))
        u=(x-self.origin_m[0])/self.spacing_m[0]
        v=(y-self.origin_m[1])/self.spacing_m[1]
        w,h=self.dimensions
        if not np.all(np.isfinite(u)) or not np.all(np.isfinite(v)):
            raise ValueError("Non-finite sample coordinate")
        if bounds_error and (np.any(u < -1e-7) or np.any(v < -1e-7) or np.any(u>w-1+1e-7) or np.any(v>h-1+1e-7)):
            raise ValueError("Sample outside master heightfield")
        u=np.clip(u,0,w-1);v=np.clip(v,0,h-1)
        i=np.minimum(np.floor(u).astype(np.int64),w-2)
        j=np.minimum(np.floor(v).astype(np.int64),h-2)
        a,b=u-i,v-j
        if triangulated:
            return np.where(a+b<=1,
                data[j,i]+a*(data[j,i+1]-data[j,i])+b*(data[j+1,i]-data[j,i]),
                data[j+1,i+1]+(1-a)*(data[j+1,i]-data[j+1,i+1])+(1-b)*(data[j,i+1]-data[j+1,i+1]))
        return ((1-a)*(1-b)*data[j,i]+a*(1-b)*data[j,i+1]+
                (1-a)*b*data[j+1,i]+a*b*data[j+1,i+1])

    def sample(self,x,y,bounds_error=True):
        return self._sample(self.heights_m,x,y,bounds_error,self.metadata.get("surface_interpolation")=="triangle_nw_se")

    def sample_mask(self,name,x,y,default=0.0,bounds_error=True):
        if name not in self.masks:
            return np.broadcast_arrays(np.asarray(x),np.asarray(y))[0]*0+default
        return self._sample(self.masks[name],x,y,bounds_error)

    def resample_grid(self,dimensions):
        w,h=dimensions
        if w<2 or h<2: raise ValueError("At least two grid samples per axis are required")
        lo,hi=self.bounds_m
        return self.sample(np.linspace(lo[0],hi[0],w)[None,:],np.linspace(lo[1],hi[1],h)[:,None])

def load_heightfield(path):
    path=Path(path).resolve()
    doc=json.loads(path.read_text(encoding="utf-8-sig"))
    if doc.get("schema")!=SCHEMA or doc.get("coordinates")!="authoring_metres_z_up":
        raise ValueError("Unsupported master heightfield schema or coordinates")
    dimensions=tuple(doc["dimensions"])
    if len(dimensions)!=2 or any(type(v)!=int or v<2 for v in dimensions):
        raise ValueError("dimensions must contain two integer sizes >=2")
    origin=tuple(float(v) for v in doc["origin_m"])
    spacing=tuple(float(v) for v in doc["spacing_m"])
    if len(origin)!=2 or len(spacing)!=2 or not all(np.isfinite(v) for v in origin+spacing) or min(spacing)<=0:
        raise ValueError("Invalid heightfield origin or spacing")
    if doc.get("row_order") not in ("+y","-y"):
        raise ValueError("row_order must explicitly be +y or -y")
    if doc.get("surface_interpolation","bilinear") not in ("bilinear","triangle_nw_se"):
        raise ValueError("Unsupported height surface interpolation")
    if "scale_m" not in doc["height"] or "offset_m" not in doc["height"]:
        raise ValueError("Height scale_m and offset_m must be explicit")
    heights=_read_raster(path.parent,doc["height"],dimensions)
    masks={key:_read_raster(path.parent,value,dimensions,mask=True) for key,value in doc.get("masks",{}).items()}
    if doc["row_order"]=="-y":
        heights=heights[::-1].copy();masks={k:v[::-1].copy() for k,v in masks.items()}
    return Heightfield(heights,origin,spacing,masks,doc,sha256(path),path)

def write_heightfield(path,heights_m,origin_m,spacing_m,masks=None,**metadata):
    """Write float32 source fixtures/imports with explicit scale and content hashes."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    heights=np.asarray(heights_m,dtype=np.float32)
    if heights.ndim!=2: raise ValueError("Height data must be a 2D array")
    data_path=path.with_suffix(".heights.npy");np.save(data_path,heights)
    doc={**metadata,"schema":SCHEMA,"coordinates":"authoring_metres_z_up","origin_m":list(origin_m),
         "spacing_m":list(spacing_m),"dimensions":[heights.shape[1],heights.shape[0]],"row_order":"+y",
         "height":{"path":data_path.name,"encoding":"float32_npy","offset_m":0,"scale_m":1,"sha256":sha256(data_path)},"masks":{}}
    for name,data in (masks or {}).items():
        target=path.with_suffix("."+name+".npy");np.save(target,np.asarray(data,dtype=np.float32))
        doc["masks"][name]={"path":target.name,"encoding":"float32_npy","sha256":sha256(target)}
    path.write_text(json.dumps(doc,indent=2)+"\n",encoding="utf-8")
    return load_heightfield(path)
