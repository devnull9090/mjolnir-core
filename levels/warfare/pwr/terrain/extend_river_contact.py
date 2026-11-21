"""Test a native river rendering margin at the north/coast tile junction.

Eight completely dry rows at the far north give a southern skirt. Reindexing
retains every occupied original sample exactly in world space, including all
rocks and wakes. Additional skirt values sample the lower tile, whose real
state remains authoritative across the overlap.
"""
import json
from pathlib import Path
import shutil
import tempfile

import numpy as np

from bake_eroded_river import (WORK, attach_native_probe, capture_rock_geometry, load_heightfield,
                               read, sha256, smooth, state_matches, texture, verify_state_files, write, write_exr)


def build(folder, work=WORK, source=None):
    if source is None:
        source=work/"water-fix"
    reference=read(source/"receipt.json")
    flux=read(source/"flux.json")
    upper,lower=flux["domains"]
    u,l=upper["state"],lower["state"]
    for d in (upper,lower):
        verify_state_files(source,d["state"])
        assert state_matches(d["state"],d)
    prior={k:texture(source/u[k]) for k in ("ground","height","velocity")}
    south={k:texture(source/l[k]) for k in prior}
    if u["cell"]!=l["cell"] or upper["domain"]["res"]!=lower["domain"]["res"]:
        raise ValueError("Original tiles do not share a pixel scale")
    rows=8
    width,height=u["res"]; cell=u["cell"]/100.
    if np.any(prior["velocity"][:rows,:,:3]!=0):
        raise ValueError("Far north margin contains water or current")
    xoff=(l["centre"][0]-u["centre"][0])/u["cell"]
    if not xoff.is_integer(): raise ValueError("Tiles are not aligned to identical world texel centres")
    offset=int(xoff)
    original_centre=u["centre"].copy()
    upper["domain"]["centre"]=original_centre.copy()
    upper["domain"]["centre"][1]+=rows*u["cell"]
    u["centre"]=upper["domain"]["centre"].copy()
    base=work/"terrain"
    master,geometry=base/"runtime-master.json",base/"terrain.geometry.json"
    rock_file=work/"dressing/flow-rocks.json"
    upper["provenance"]=capture_rock_geometry(folder,master,geometry,upper,read(rock_file)["rocks"])
    for key in ("erosion_solve_sha256","rock_geometry_sha256"):
        upper["provenance"][key]=u["provenance"][key]
    upper["provenance"]["junction_margin_sha256"]=sha256(Path(__file__))
    u["provenance"]=upper["provenance"].copy()
    field=load_heightfield(master)
    east=u["centre"][0]/100+(np.arange(width)+.5-width/2)*cell
    north=-u["centre"][1]/100-(np.arange(height)+.5-height/2)*cell
    xx,yy=np.meshgrid(east,north[-rows:])
    terrain=field.sample(xx,yy)
    result={k:v.copy() for k,v in prior.items()}
    for k in result:
        result[k][:-rows]=prior[k][rows:]
    newground=result["ground"][-rows:]; newheight=result["height"][-rows:];newv=result["velocity"][-rows:]
    newground[:]=[0,0,0,1]; newheight[:]=[0,0,0,1];newv[:]=0
    newground[...,0]=u["centre"][2]-terrain*100
    newheight[...,:2]=(terrain[...,None]-.40)*100-u["capture"]
    south_width=width-offset
    newground[:,offset:]=south["ground"][:rows,:south_width]
    newground[:,offset:,0]+=u["centre"][2]-l["centre"][2]
    newheight[:,offset:]=south["height"][:rows,:south_width]
    newheight[:,offset:,:2]+=l["capture"]-u["capture"]
    newv[:,offset:]=south["velocity"][:rows,:south_width]
    # At the seam, preserve all world heights and copied currents. Beyond
    # the lower surface's 2m rendering guard band, tuck the upper duplicate
    # gently beneath the actual liquid and finally beneath the bed. The far
    # end is fully dry before the mesh reaches its own native guard band.
    south_y=-yy
    behind=smooth(2.05,5.0,south_y)
    under=smooth(4.00,6.3,south_y)
    old_z=(newheight[...,0]+u["capture"])/100
    bed_z=(u["centre"][2]-newground[...,0])/100
    wet=newv[...,2]>.01
    dip=np.maximum(.38*behind,under*np.maximum(.42,old_z-bed_z+.40))
    for channel in (0,1):
        newheight[...,channel]-=100*dip*wet
    newv[...,2]=np.where(wet,np.maximum(0,newv[...,2]-100*dip),newv[...,2])
    newv[wet&(newv[...,2]<=0)]=0
    shutil.copytree(source/"flux_state/lower_lake",folder/"flux_state/lower_lake")
    for k,values in result.items():
        write_exr(folder/u[k],values)
        u[k+"_sha256"]=sha256(folder/u[k])
    write(folder/"flux_state/upper_river/state.json",u)
    write(folder/"flux.json",flux)
    checked={k:texture(folder/u[k]) for k in prior}
    for k in checked:
        assert np.array_equal(checked[k][:-rows],prior[k][rows:])
    old_n=-original_centre[1]/100-(np.arange(height)+.5-height/2)*cell
    np.testing.assert_array_equal(old_n[rows:],north[:-rows])
    for d in (upper,lower):
        verify_state_files(folder,d["state"])
        assert state_matches(d["state"],d)
    assert all(sha256(folder/u)==sha256(source/u) for u in reference["files"] if u.startswith("flux_state/lower_lake/"))
    physical_wet=south["velocity"][:rows,:south_width,2]>1
    upper_surface=(checked["height"][-rows:,offset:,0]+u["capture"])/100
    actual=(south["height"][:rows,:south_width,0]+l["capture"])/100
    diff=np.abs(upper_surface[:2]-actual[:2])[physical_wet[:2]]
    assert diff.max()<.05 and not np.any(checked["velocity"][-2:,:,2]>0)
    section=np.flatnonzero(physical_wet[0])
    assert 5<len(section)<80
    probe=int(section[len(section)//2]+offset)
    proof=dict(reference)
    proof["inputs"]=dict(reference["inputs"],contact_source=sha256(Path(__file__)),original_water=sha256(source/"flux.json"))
    proof["files"]={f.relative_to(folder).as_posix():sha256(f) for f in sorted((folder/"flux_state").rglob("*")) if f.is_file()}
    proof["junction"]={"parent":".34","original_centre_cm":original_centre,"new_centre_cm":u["centre"],
        "native_cell_size_m":cell,"retained_rows":height-rows,"retained_world_aligned_texels_per_map":width*(height-rows),
        "discarded_rows_max_water_depth_cm":float(prior["velocity"][:rows,:,2].max()),
        "new_render_margin_m":rows*cell,"lower_tile_byte_identical":True,
        "first_two_rows_max_height_error_m":float(diff.max()),
        "first_two_rows_depth_and_velocity_equal":bool(np.array_equal(checked["velocity"][-rows:-rows+2,offset:],
                                                south["velocity"][:2,:south_width])),
        "lower_authoritative_depth_at_old_contact_m":float(south["velocity"][0,probe-offset,2]/100),
        "terminal_upper_depth_cm":float(checked["velocity"][-2:,:,2].max()),
        "original_spring_hill":"Outside new coverage, in the fully dry discarded northern band",
        "contact_depths_cm":[float(v) for v in checked["velocity"][-rows:,probe,2]]}
    assert proof["junction"]["first_two_rows_depth_and_velocity_equal"]
    # The published .34 checks are in the old tile's coordinate system.
    previous=[(name,int(c),int(r)-rows) for name,c,r in reference["readback_texels"] if int(r)>=rows]
    previous += [("spring_hill_guard",323,0),("contact_north",probe,height-rows-1),
                 ("contact_middle",probe,height-rows+1),("contact_end",probe,height-1)]
    for entry in proof.get("rocks", []):
        for key in ("crest_texel","wake_texel"):
            if key in entry:
                entry[key][1]-=rows
    attachment=folder/"river_flux_readback.lua"
    attach_native_probe(folder,u,checked,[],{})
    code=attachment.read_text()
    start=code.index("local probes = {");end=code.index("local maps =",start)
    records=[]
    for name,c,r in previous:
        h=checked["height"][r,c,0];a,b,d,f=checked["velocity"][r,c]; g=checked["ground"][r,c,0]
        records.append(f'    {{"{name}",{c},{r},{h},{a},{b},{d},{g},{f}}},')
    attachment.write_text(code[:start]+"local probes = {\n"+"\n".join(records)+"\n}\n"+code[end:])
    proof["readback_texels"]=previous
    write(folder/"receipt.json",proof)


if __name__=="__main__":
    target=WORK/"junction/contact-candidate"
    if target.exists(): raise FileExistsError(target)
    with tempfile.TemporaryDirectory(dir=target.parent) as temp:
        stage=Path(temp)/"water"
        stage.mkdir()
        build(stage)
        stage.rename(target)
    print(target)
