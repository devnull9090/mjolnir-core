"""Seal only new basin-distance HISM ownership into the existing .38 map."""
import json
import shutil
import subprocess
import package_pwr_headwater as p

BASE=p.ROOT/"out/pwr/river-basin"
OUT=BASE/"shore-contact/native"
PRIOR=BASE/"native/map-input"
PARENT="6cbce87c3f0153aaf46538eea8db27e1cb1acbbe122eca54c65c3275ada3b60f"


def main():
    parent=BASE/"saturday.38/pelican-warfare-0.1.0-playtest.38.mjolnir"
    if p.sha(parent)!=PARENT:raise ValueError("Wrong .38 parent")
    previous=json.loads((BASE/"native/landscape-collision.json").read_text())
    for name,digest in previous["native_members"].items():
        if p.sha(PRIOR/name)!=digest:raise ValueError("Modified .38 input")
    readback=json.loads((OUT/"editor-verified.json").read_text())
    if readback["points"]!=3646 or readback["max_new_hism"]!=24:raise ValueError("Wrong native local population")
    p.out=OUT;p.n=OUT/"packaging";p.n.mkdir(exist_ok=True);p.maps=OUT/"map-input";p.old=PRIOR;p.apron=False;p.basin=False
    p.prepare(require_material_change=False)
    land=json.loads((p.n/"land-diff.json").read_text())
    allowed_maps = {k for k in land if k.endswith(("/LPE/LPE.umap","/LPE/LPE.ubulk"))}
    others = set(land)-allowed_maps
    if "Levels/Halo1/Solo/LPE/LPE.umap" not in allowed_maps or any(not k.endswith(".ushaderbytecode") for k in others):
        raise ValueError("Unexpected native landscape/material change: "+str(list(land)))
    filename=p.LAND+".utoc"
    fresh=p.load_container(p.maps/filename)
    parent_land=p.load_container(PRIOR/filename)
    def package_ids(container):
        return {path:(container.chunks[index].chunk_id,container.chunks[index].chunk_index,container.chunks[index].chunk_type)
                for path,index in container.files.items()}
    if package_ids(fresh)!=package_ids(parent_land):raise ValueError("A package or bulk identity changed")
    def references(folder):
        r=subprocess.run([str(p.examples/"world_imports.exe"),str(folder),"Levels/Halo1/Solo/LPE/LPE.umap","/game/"],capture_output=True,text=True,check=True)
        imports=[line.strip() for line in r.stdout.splitlines() if "import pkg:" in line or "name:" in line and "/game/" in line.lower()]
        if len(imports)<10:raise ValueError("No Zen world import proof")
        return imports
    base_refs=references(PRIOR); fresh_refs=references(p.maps)
    if sorted(base_refs)!=sorted(fresh_refs):raise ValueError(("New imported/soft package in local grass scene",set(base_refs)^set(fresh_refs)))
    replacement=p.n/"map-replacements"
    for path in allowed_maps:
        file=replacement/path;file.parent.mkdir(exist_ok=True,parents=True)
        file.write_bytes(p.read_chunk(fresh,fresh.chunks[fresh.files[path]]))
    import tempfile
    with tempfile.TemporaryDirectory(dir=p.n) as restored:
        from pathlib import Path
        folder=Path(restored)
        p.run([p.examples/"replace_members.exe",PRIOR/filename,replacement,folder],p.n/"retain-parent-shaders.log")
        corrected=p.changes(PRIOR/filename,folder/filename)
        if set(corrected)!=allowed_maps or any(corrected[k]!=land[k] for k in allowed_maps):raise ValueError("Independent .38 patch audit failed")
        for ext in (".utoc",".ucas"):shutil.copyfile((folder/filename).with_suffix(ext),p.maps/(p.LAND+ext))
        land=corrected
    dependencies=dict(unchanged_named_package_ids=len(package_ids(parent_land)),same_imports_and_soft_paths=len(base_refs),
                      unchanged_shader_and_graph=True,changed_land_members=sorted(land))
    (p.n/"dependency-proof.json").write_text(json.dumps(dependencies,indent=2))
    bsp=BASE/"native/physics/pwr.sbsp"
    if p.sha(bsp)!=previous["sbsp"]:raise ValueError("Unrecognised parent physics")
    world=p.n/"world-bake"
    p.run([p.cli,"level","bake",BASE/"native/native-level.json","--paks",p.paks,"--standalone","PWR",
           "--bsp","8="+str(bsp.resolve()),"--out-dir",world,"--world",p.n/"LPE.umap"],p.n/"world-bake.log")
    toc=p.WORLD+".utoc"
    diff=p.changes(PRIOR/toc,world/toc)
    if not any(k.endswith("/PWR/PWR.umap") for k in diff) or not all(k.endswith(("/PWR/PWR.umap","/PWR/PWR.ubulk")) for k in diff):raise ValueError("Unrelated gameplay change "+str(list(diff)))
    for ext in (".utoc",".ucas"):shutil.copyfile(world/(p.WORLD+ext),p.maps/(p.WORLD+ext))
    sealed={file.name:p.sha(file) for file in p.maps.iterdir()}
    if sealed.keys()!=previous["native_members"].keys():raise ValueError("Wrong final member inventory")
    proof=dict(parent_map_sha256=PARENT,native_members=sealed,parent_native_members=previous["native_members"],
               retained_bsp_sha256=previous["sbsp"],retained_terrain_sha256=previous["terrain_manifest_sha256"],
               retained_dressing_ledger_sha256=previous["dressing_ledger_sha256"],land_changed=land,world_changed=diff,
               editor_readback=readback,dependency_proof=dependencies,rebuild="levels/warfare/pwr/build_basin_grass_range.ps1")
    tmp=OUT/"receipt.pending"
    tmp.write_text(json.dumps(proof,indent=2)+"\n");tmp.replace(OUT/"receipt.json")
    print(sealed)

if __name__=="__main__":main()
