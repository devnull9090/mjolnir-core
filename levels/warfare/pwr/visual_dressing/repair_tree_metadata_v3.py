# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2,<3", "scipy==1.17.0", "shapely>=2,<3", "pillow>=11,<13"]
# ///
"""One-time metadata repair; prove every previously sealed instance is unchanged."""
import copy,json,subprocess,sys
from finish_outcrops_v3 import ROOT,OUT,TREES,dump,filtered_tree_metadata
from heightfield import sha256

def main():
    path=OUT/'trees.selected.json';doc=json.loads(path.read_text());before=copy.deepcopy(doc['instances']);before_sha=sha256(path)
    filtered_tree_metadata(json.loads(TREES.read_text()),doc)
    assert doc['instances']==before
    dump(path,doc)
    recipes=ROOT/'tools/level/data/b30_tree_recipes.json';base=ROOT/'out/pwr/world-v5/authored-decor.json'
    target=OUT/'pcg-authored-decor.integration.json'
    command=[sys.executable,str(ROOT/'tools/level/pcg_tree_decor.py'),str(path),str(recipes),str(target),'--base',str(base),'--max-trees','4600']
    result=subprocess.run(command,capture_output=True,text=True,check=True)
    converted=json.loads(target.read_text())
    report={'schema':'pwr-filtered-tree-adapter-v1','metadata_only':True,'all_4264_instance_records_unchanged':doc['instances']==before,
       'source_sha256_before':before_sha,'source_sha256_after':sha256(path),'recipes_sha256':sha256(recipes),
       'base_sha256':sha256(base),'output_sha256':sha256(target),'command':command,'stdout':result.stdout.strip(),
       'selected_count':doc['selected_count'],'selected_by_recipe':doc['selected_by_recipe'],
       'converted_tree_count':len(converted['background_trees']),'max_trees':4600,'new_pcg_run':False}
    dump(OUT/'tree-conversion.receipt.json',report)
    receipt_path=OUT/'receipt.json';receipt=json.loads(receipt_path.read_text())
    receipt['foliage']['trees'].update(selected_count=doc['selected_count'],selected_by_recipe=doc['selected_by_recipe'],
         metadata_only_repair=True,actual_tree_adapter_passed=True)
    dump(receipt_path,receipt)
    print(result.stdout.strip())

if __name__=='__main__':main()
