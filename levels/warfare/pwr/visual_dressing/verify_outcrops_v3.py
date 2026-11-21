# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "scipy==1.17.0", "shapely>=2,<3", "pillow>=11,<13"]
# ///
"""Read-only final artifact verification, then write an isolated hash seal."""
import json
import numpy as np
from finish_outcrops_v3 import OUT,ROOT,World,ROCKS,TREES,PAVING,MASTER,MATERIAL,placed,dump
from heightfield import sha256
import pcg_foliage
import pcg_tree_decor

def verify():
    world=World();new_path=OUT/'outcrops.authored-decor.json';new=json.loads(new_path.read_text())['decor']
    # Load the additional small stock models through the generator's canonical
    # definition, without regenerating or editing any output.
    from finish_outcrops_v3 import scree
    scree(world,json.loads((OUT/'bank.json').read_text()))
    original=json.loads(ROCKS.read_text())['decor'];merged=json.loads((OUT/'rocks-and-outcrops.authored-decor.json').read_text())['decor']
    assert merged==original+new and len(original)==574
    assert len({str(x['id']) for x in merged})==len(merged)
    assert MATERIAL==json.loads((ROOT/'out/pwr/visual-v5/surface-v4/rock-material.json').read_text())
    assert all(x['materials']==[MATERIAL] for x in new)
    proof_path=OUT/'native-hulls.proof.json';proof=json.loads(proof_path.read_text())
    assert proof['objects']==len(new) and set(proof['materials'])=={'hard_terrain_stone'}
    assert proof['skip_entries']==[]
    at=0;largest=0.;triangles=np.array(proof['triangles'],float)
    for row in new:
        model,points=placed(world,row);faces=model['faces'][:,[0,2,1]]
        exact=np.round((points/3.048)[faces],4);count=len(faces)
        error=float(np.abs(exact-triangles[at:at+count]).max());largest=max(largest,error)
        assert error<1e-9,(row['id'],error)
        assert np.isfinite(exact).all()
        at+=count
    assert at==len(triangles)==len(proof['materials'])
    base=json.loads(TREES.read_text());filtered=json.loads((OUT/'trees.selected.json').read_text())
    prior={x['id']:x for x in base['instances']};survivors=filtered['instances']
    recipe_path=ROOT/'tools/level/data/b30_tree_recipes.json'
    converted=pcg_tree_decor.convert(filtered,json.loads(recipe_path.read_text()),max_trees=4600)
    assert len(converted['background_trees'])==len(survivors)==filtered['selected_count']
    assert sum(filtered['selected_by_recipe'].values())==len(survivors)
    assert filtered['structural_exclusion']['new_pcg_run'] is False
    assert all(prior[x['id']]==x for x in survivors)
    assert len({x['id'] for x in survivors})==len(survivors)
    receipt=json.loads((OUT/'receipt.json').read_text())
    actual_removed=set(prior)-{x['id'] for x in survivors}
    assert actual_removed==set(receipt['foliage']['trees']['removed_ids'])
    source=ROOT/'out/pwr/visual-v5/outcrops-v2/grass/foliage.json'
    _,before=pcg_foliage.read_mjf_groups(source);_,after=pcg_foliage.read_mjf_groups(OUT/'grass/foliage.json')
    assert len(before)==len(after)
    for old,new_group in zip(before,after):
        assert old[0]==new_group[0]
        original_records=np.frombuffer(old[2]['xf'],dtype=np.dtype((np.void,40)))
        final_records=np.frombuffer(new_group[2]['xf'],dtype=np.dtype((np.void,40)))
        cursor=0
        # Retained transforms must be a stable byte-exact subsequence, including
        # duplicate values; a set comparison would conceal reordering.
        for record in final_records:
            while cursor<len(original_records) and original_records[cursor]!=record:cursor+=1
            assert cursor<len(original_records),'Grass transform changed/reordered'
            cursor+=1
    assert receipt['runtime_master_sha256']==world.field.manifest_sha256
    assert receipt['paving_sha256']==sha256(PAVING)
    preview=json.loads((OUT/'combined-preview.receipt.json').read_text())
    assert preview['proposal_sha256']==sha256(new_path),'Preview is stale'
    paths=[new_path,OUT/'rocks-and-outcrops.authored-decor.json',OUT/'trees.selected.json',OUT/'receipt.json',proof_path,
           OUT/'grass/foliage.json',OUT/'grass/foliage.bin',OUT/'combined-preview.receipt.json',PAVING,MASTER]
    paths+=[recipe_path]
    if (OUT/'tree-conversion.receipt.json').is_file():paths.append(OUT/'tree-conversion.receipt.json')
    paths+=sorted((OUT/'grass').glob('foliage.bin.*'))+sorted((OUT/'hulls').glob('SM_*.json'))
    seal={'schema':'pwr-outcrops-v3-seal-v1','runtime_master_sha256':world.field.manifest_sha256,
       'existing574_rocks_exact':True,'remaining_tree_records_exact':True,'remaining_grass_transforms_stable_byte_exact':True,
       'native_proof_triangles':at,'native_proof_maximum_coordinate_difference_wu':largest,
       'render_material_matches_verified_source':True,'preview_current':True,
       'actual_tree_adapter_passed':True,'tree_budget':4600,
       'new_props':len(new),'total_rocks':len(merged),'trees':len(survivors),'grass':sum(x[3] for x in after),
       'actual_native_compile_and_live_review_pending':True,
       'files':[{'path':str(p),'sha256':sha256(p)} for p in paths]}
    dump(OUT/'seal.json',seal)
    print(json.dumps({k:seal[k] for k in ('new_props','total_rocks','trees','grass','native_proof_triangles','preview_current')}))

if __name__=='__main__':verify()
