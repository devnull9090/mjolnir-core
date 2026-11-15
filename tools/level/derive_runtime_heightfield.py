"""Freeze the exact quantized UE Landscape grid as the shared runtime surface.

The approved source heightfield and geometry remain immutable. Native terrain
collision and PCG must use the result's triangle_nw_se surface, not a bilinear
interpolation of either the old 1024 raster or this new 1009 raster.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from build_landscape import heightfield_geometry, encode_master_heights
from heightfield import load_heightfield, write_heightfield, sha256

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"levels/warfare/pwr/terrain/final-v3/final-master.json"
OUTPUT=ROOT/"levels/warfare/pwr/terrain/runtime-v3/runtime-master.json"
EVIDENCE={"source":"UE5.5 installed source, Landscape/Private/LandscapeRender.cpp:3276-3290",
          "unreal_indices":[["i00","i11","i10"],["i00","i01","i11"]],
          "authoring_diagonal":"NW(x0,y1) to SE(x1,y0), because UE import reverses authoring Y",
          "authoring_triangles":[["SW","SE","NW"],["SE","NE","NW"]],
          "scope":"Landscape LOD0 grid; lower visual LODs and material displacement require separate verification"}


def error_summary(error):
    absolute=np.abs(np.asarray(error))
    return {"samples":int(absolute.size),"max_m":float(absolute.max()) if absolute.size else 0,
            "p95_m":float(np.percentile(absolute,95)) if absolute.size else 0,
            "rms_m":float(np.sqrt(np.mean(absolute**2))) if absolute.size else 0}


def preservation_report(field, heights):
    """Check a constrained field against immutable baseline bytes, not its claims."""
    contract=field.metadata.get("preservation")
    if contract is None:return None
    baseline_path=(field.path.parent/contract["baseline_manifest"]).resolve()
    baseline=load_heightfield(baseline_path)
    if (baseline.manifest_sha256!=contract["baseline_manifest_sha256"]
            or baseline.metadata["height"]["sha256"]!=contract["baseline_height_sha256"]):
        raise ValueError("Preserved baseline hash mismatch")
    if (field.dimensions!=baseline.dimensions or field.origin_m!=baseline.origin_m
            or field.spacing_m!=baseline.spacing_m):
        raise ValueError("Preserved baseline grid changed")
    name=contract["protected_mask"]
    mask=field.masks.get(name)
    if mask is None or not np.isin(mask,[0,1]).all() or not mask.any():
        raise ValueError("Preservation requires a nonempty binary protected mask")
    selected=mask.astype(bool)
    delta=np.asarray(heights,dtype=float)[selected]-baseline.heights_m[selected]
    if np.any(delta!=0):
        raise ValueError(f"Protected runtime heights changed by {np.max(np.abs(delta)):.9g} m")
    if field.metadata["geometry_sha256"]!=contract["geometry_sha256"] or contract["geometry_sha256"]!=baseline.metadata["geometry_sha256"]:
        raise ValueError("Preserved geometry contract changed")
    layout=(field.path.parent/contract["layout"]).resolve()
    if sha256(layout)!=contract["layout_sha256"]:
        raise ValueError("Preserved layout hash mismatch")
    policy=field.metadata.get("landscape_encoding_policy",{})
    encoding=baseline.metadata.get("landscape_encoding",{})
    for key in ("centre_cm","z_scale","components","size","origin_cm","quad_cm"):
        if policy.get(key)!=encoding.get(key):raise ValueError("Preserved Landscape encoding changed: "+key)
    return {"baseline_manifest_sha256":baseline.manifest_sha256,
            "baseline_height_sha256":baseline.metadata["height"]["sha256"],
            "geometry_sha256":contract["geometry_sha256"],"layout_sha256":contract["layout_sha256"],
            "protected_vertices":int(selected.sum()),"protected_max_abs_error_m":0.0,
            "protected_mask_sha256":field.metadata["masks"][name]["sha256"],
            "protected_runtime_heights_exact":True}


def derive(source_path=SOURCE, output_path=OUTPUT, components=16):
    source=load_heightfield(source_path)
    output=Path(output_path).resolve()
    if output==source.path or output.with_suffix(".heights.npy")==((source.path.parent/source.metadata["height"]["path"]).resolve()):
        raise ValueError("Runtime derivation must not overwrite the approved source")
    if "preservation" in source.metadata:
        baseline_path=(source.path.parent/source.metadata["preservation"]["baseline_manifest"]).resolve()
        baseline=load_heightfield(baseline_path)
        protected_geometry=(baseline.path.parent/baseline.metadata["geometry"]).resolve()
        if output.parent in (baseline.path.parent,protected_geometry.parent):
            raise ValueError("Runtime derivation must not overwrite the preservation baseline")
    geometry=(source.path.parent/source.metadata["geometry"]).resolve()
    if sha256(geometry)!=source.metadata["geometry_sha256"]:
        raise ValueError("Source geometry hash does not match the approved master")
    prepared=heightfield_geometry(source,components)
    fixed=source.metadata.get("landscape_encoding_policy")
    raw,centre,scale,quantization=encode_master_heights(prepared["heights_cm"],fixed)
    decoded=(centre+(raw.astype(np.float64)-32768)*scale/128)[::-1]/100
    size=prepared["size"]
    low,high=source.bounds_m
    x=np.linspace(low[0],high[0],size)[None,:]
    y=np.linspace(low[1],high[1],size)[:,None]
    # Identical physical grids need no interpolation. Floating point coordinate
    # division otherwise turns hard0/1 protection into tiny fractional values.
    masks=({name:values.copy() for name,values in source.masks.items()} if source.dimensions==(size,size)
           else {name:source.sample_mask(name,x,y) for name in source.masks})
    excluded={"schema","coordinates","origin_m","spacing_m","dimensions","row_order","height","masks"}
    metadata={k:v for k,v in source.metadata.items() if k not in excluded}
    metadata.update(generator="derive_runtime_heightfield.py v1",
        geometry=os.path.relpath(geometry,output.parent).replace("\\","/"),
        surface_interpolation="triangle_nw_se",
        runtime_source={"manifest":os.path.relpath(source.path,output.parent).replace("\\","/"),
                        "manifest_sha256":source.manifest_sha256,"height_sha256":source.metadata["height"]["sha256"],
                        "geometry_sha256":source.metadata["geometry_sha256"]},
        landscape_encoding={"components":prepared["components"],"quads_per_component":63,
                            "size":size,"origin_cm":prepared["origin"].tolist(),"quad_cm":prepared["quad"],
                            "centre_cm":centre,"z_scale":scale,
                            "r16_sha256":hashlib.sha256(raw.tobytes()).hexdigest()},
        triangulation_evidence=EVIDENCE)
    # Float32 storage is the common heightfield format. Prove that it preserves
    # this encoding before publishing a runtime manifest.
    stored=decoded.astype(np.float32)
    preservation=preservation_report(source,stored)
    if "preservation" in metadata:
        metadata["preservation"]=dict(metadata["preservation"])
        for key in ("baseline_manifest","layout"):
            metadata["preservation"][key]=os.path.relpath((source.path.parent/source.metadata["preservation"][key]).resolve(),output.parent).replace("\\","/")
    test_raw,test_centre,test_scale,_=encode_master_heights(stored[::-1].astype(np.float64)*100,fixed)
    if not np.array_equal(raw,test_raw) or centre!=test_centre or scale!=test_scale:
        raise ValueError("This height encoding is not idempotent through float32; refuse a different rendered surface")
    runtime=write_heightfield(output,stored,low,[(high[0]-low[0])/(size-1),(high[1]-low[1])/(size-1)],masks,**metadata)
    if preservation is not None:preservation_report(runtime,runtime.heights_m)
    rebuilt=heightfield_geometry(runtime,components)
    actual_raw,actual_centre,actual_scale,_=encode_master_heights(rebuilt["heights_cm"],fixed)
    if (not np.array_equal(raw,actual_raw) or centre!=actual_centre or scale!=actual_scale
            or not np.array_equal(prepared["origin"],rebuilt["origin"]) or prepared["quad"]!=rebuilt["quad"]
            or source.bounds_m!=runtime.bounds_m):
        raise ValueError("Runtime Landscape roundtrip failed exact encoded grid/transform verification")
    if sha256(source.path)!=source.manifest_sha256 or sha256(geometry)!=source.metadata["geometry_sha256"]:
        raise ValueError("Approved source changed during derivation")
    raw_path=output.with_suffix(".r16");raw_path.write_bytes(raw.tobytes())
    width,height=source.dimensions
    sx=np.linspace(low[0],high[0],width)[None,:]
    sy=np.linspace(low[1],high[1],height)[:,None]
    difference=runtime.sample(sx,sy)-source.heights_m
    region_errors={name:error_summary(difference[mask>.5]) for name,mask in source.masks.items()}
    a,b=decoded[:-1,:-1],decoded[:-1,1:]
    c,d=decoded[1:,:-1],decoded[1:,1:]
    report={"schema":"pwr-runtime-heightfield-derivation-v1",
            "source_manifest_sha256":source.manifest_sha256,"source_height_sha256":source.metadata["height"]["sha256"],
            "runtime_manifest_sha256":runtime.manifest_sha256,"runtime_height_sha256":runtime.metadata["height"]["sha256"],
            "geometry_sha256":source.metadata["geometry_sha256"],"source_dimensions":list(source.dimensions),
            "runtime_dimensions":list(runtime.dimensions),"bounds_m":[list(low),list(high)],
            "source_preserved":True,"landscape_r16_bit_identical":True,"landscape_transform_identical":True,
            "height_quantization":quantization,"float32_storage_max_error_m":float(np.max(np.abs(stored.astype(float)-decoded))),
            "encoded_r16_file":raw_path.name,"encoded_r16_sha256":hashlib.sha256(raw.tobytes()).hexdigest(),
            "triangle_vs_bilinear_cell_center_max_m":float(np.max(np.abs((b+c-a-d)/4))),
            "source_to_runtime_at_original_vertices":error_summary(difference),"source_mask_regions":region_errors,
            "surface_interpolation":"triangle_nw_se","triangulation_evidence":EVIDENCE,
            "scope":"Exact original Landscape LOD0 encoded vertices/transform and analytic triangle sampling. Native coarse-mesh fidelity and cooked/runtime LOD appearance are separate acceptance gates."}
    if preservation is not None:report["preservation"]=preservation
    receipt=output.with_suffix(".receipt.json")
    receipt.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,default=SOURCE)
    parser.add_argument("--out",type=Path,default=OUTPUT)
    parser.add_argument("--components",type=int,default=16)
    args=parser.parse_args()
    report=derive(args.source,args.out,args.components)
    print(json.dumps({k:report[k] for k in ("runtime_dimensions","runtime_manifest_sha256","landscape_r16_bit_identical","landscape_transform_identical","surface_interpolation")}))


if __name__=="__main__":main()
