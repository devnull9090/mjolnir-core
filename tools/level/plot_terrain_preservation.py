"""Scientific height/slope/earthwork comparisons; these are not in-game renders."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource, TwoSlopeNorm
from heightfield import load_heightfield


def plot(source,baseline,out,candidate=None,diagnostic=None):
    source=load_heightfield(source);baseline=load_heightfield(baseline)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    current=load_heightfield(candidate) if candidate else None
    if current:
        heights=current.heights_m;protected=current.masks["protected"]>.5
        label="Constrained candidate (offline; live validation pending)"
        candidate_hash=current.manifest_sha256
    else:
        if diagnostic is None:raise ValueError("Candidate or rejected-fit diagnostic required")
        doc=np.load(diagnostic,allow_pickle=False)
        heights=doc["heights"].astype(float);protected=doc["protected"]
        label="REJECTED FIT — diagnostic only"
        candidate_hash=None
    new=source.resample_grid(baseline.dimensions);old=baseline.heights_m
    if heights.shape!=old.shape:raise ValueError("Candidate/baseline grid mismatch")
    lo,hi=baseline.bounds_m;extent=[lo[0],hi[0],lo[1],hi[1]]
    spacing=baseline.spacing_m;light=LightSource(azdeg=315,altdeg=45)
    cm=plt.get_cmap("gist_earth")
    minimum=min(float(a.min()) for a in (old,new,heights));maximum=max(float(a.max()) for a in (old,new,heights))
    fig,axes=plt.subplots(1,3,figsize=(18,6.5),constrained_layout=True)
    for ax,a,title in zip(axes,(old,new,heights),("Frozen v3 runtime relief","New procedural Gaea source",label)):
        rgba=light.shade(a,cmap=cm,vmin=minimum,vmax=maximum,vert_exag=1,dx=spacing[0],dy=spacing[1],blend_mode="soft")
        ax.imshow(rgba,origin="lower",extent=extent)
        ax.set(title=title,xlabel="Authoring X (m)",ylabel="Authoring Y (m)")
    fig.suptitle("PWR terrain comparison — same elevation colors, physical slope and lighting",fontsize=15)
    fig.savefig(out/"relief-comparison.png",dpi=150);plt.close(fig)
    change=heights-new;dy,dx=np.gradient(heights,*spacing[::-1]);slope=np.degrees(np.arctan(np.hypot(dx,dy)))
    fig,axes=plt.subplots(2,2,figsize=(13,12),constrained_layout=True)
    fields=[(heights,"Final height (m)","terrain",{}),(protected.astype(float),"Protected runtime vertices","gray",{"vmin":0,"vmax":1}),
            (change,"Earthworks relative to new Gaea (m)","RdBu_r",{"norm":TwoSlopeNorm(vcenter=0,vmin=-max(.01,float(np.abs(change).max())),vmax=max(.01,float(np.abs(change).max())))}),
            (slope,"Final slope angle (degrees)","magma",{"vmin":0,"vmax":80})]
    for ax,(a,title,cmap,options) in zip(axes.flat,fields):
        im=ax.imshow(a,origin="lower",extent=extent,cmap=cmap,**options)
        ax.set(title=title,xlabel="Authoring X (m)",ylabel="Authoring Y (m)")
        fig.colorbar(im,ax=ax,shrink=.8)
    fig.suptitle(label+"\nNumerical diagnostics, not an Unreal screenshot",fontsize=15)
    fig.savefig(out/"height-slope-protection.png",dpi=150);plt.close(fig)
    receipt={"source_manifest_sha256":source.manifest_sha256,"baseline_manifest_sha256":baseline.manifest_sha256,
             "candidate_manifest_sha256":candidate_hash,"status":label,"protected_fraction":float(protected.mean()),
             "plots":["relief-comparison.png","height-slope-protection.png"]}
    (out/"plots.receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    return receipt


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True);p.add_argument("--baseline",required=True);p.add_argument("--out",required=True)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument("--candidate");group.add_argument("--diagnostic")
    a=p.parse_args();print(json.dumps(plot(a.source,a.baseline,a.out,a.candidate,a.diagnostic)))
