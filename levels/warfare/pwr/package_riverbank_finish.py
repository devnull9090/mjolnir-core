"""Package the .35 riverbank art without rebuilding or replacing the .34 physical BSP."""
import json
from pathlib import Path
import shutil

import package_pwr_headwater as p

parent=p.ROOT/"out/pwr/river-erosion"
work=parent/"shore-finish"
prior=parent/"saturday.34/map-input"
photos=("T_PWR_RiverCobble_BC","T_PWR_RiverCobble_N")
expected={f"MJOLNIR/GrassPilot/Playable/{name}.{ext}" for name in photos for ext in ("uasset","ubulk")}


def main():
    p.out=work
    p.n=work/"native"
    p.maps=work/"map-input"
    p.old=prior
    observed=json.loads((work/"editor-verified.json").read_text())
    if not observed["transforms_read_back"] or observed["source_plan_sha256"]!=p.sha(work/"planting.json"):
        raise ValueError("Unverified riparian placement list")
    (work/"native").mkdir(exist_ok=True)
    p.prepare(allowed_additions=expected)
    land=json.loads((p.n/"land-diff.json").read_text())
    added=sorted(k for k,v in land.items() if v[0] is None)
    if {s for s in added if s.endswith(".uasset")}!={s for s in expected if s.endswith(".uasset")}:
        raise ValueError("Missing native river scan textures: "+str(added))

    prior_native=parent/"native"
    bsp=prior_native/"physics/pwr.sbsp"
    parent_receipt=json.loads((prior_native/"landscape-collision.json").read_text())
    if p.sha(bsp)!=parent_receipt["sbsp"]:
        raise ValueError("Original playtest physical BSP changed")
    out_world=p.n/"world-bake"
    p.run([p.cli,"level","bake",prior_native/"native-level.json","--paks",p.paks,"--standalone","PWR",
           "--bsp","8="+str(bsp.resolve()),"--out-dir",out_world,"--world",p.n/"LPE.umap"],p.n/"world-bake.log")
    toc=p.WORLD+".utoc"
    diff=p.changes(prior/toc,out_world/toc)
    if not diff or any(not k.endswith(("/PWR/PWR.umap","/PWR/PWR.ubulk")) for k in diff):
        raise ValueError("Unrelated playable package or collision changed: "+str(list(diff)))
    for ext in (".utoc",".ucas"):
        shutil.copyfile(out_world/(p.WORLD+ext),p.maps/(p.WORLD+ext))
    sealed={s.name:p.sha(s) for s in p.maps.iterdir()}
    old_entries=p.world_entries(prior/toc)
    proof={k:h for k,h in old_entries.items() if "structure_bsp." in k}
    scan=json.loads((work/"scans/ganges-river-cobble.json").read_text())
    receipt=dict(native_members=sealed,added_land_entries=added,land_changed=land,world_changed=diff,
                 retained_bsp_sha256=parent_receipt["sbsp"],retained_cooked_physics=proof,
                 retained_dressing_ledger_sha256=parent_receipt["dressing_ledger_sha256"],
                 retained_terrain_sha256=parent_receipt["terrain_manifest_sha256"],
                 material=json.loads((work/"material.json").read_text()),planting=observed,
                 species=json.loads((work/"placements.json").read_text()),scan=scan)
    path=work/"receipt.json"
    temp=path.with_suffix(".pending")
    temp.write_text(json.dumps(receipt,indent=2)+"\n")
    temp.replace(path)
    print(f"Sealed {len(sealed)} cooked files, {len(added)} new texture members")


if __name__=="__main__":
    main()
