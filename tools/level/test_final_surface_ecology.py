import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('final_ecology',ROOT/'levels/warfare/pwr/finalize_surface_ecology.py')
final=importlib.util.module_from_spec(spec);spec.loader.exec_module(final)


class FinalEcologyTests(unittest.TestCase):
    def test_selection_rejects_stale_roots_duplicates_and_count(self):
        field=SimpleNamespace(sample=lambda x,y:np.full_like(x,20.))
        document={'schema':1,'selected_count':2,'instances':[
            {'id':1,'kind':'tree','position':[0,0,20.001],'recipe':'Pine_Optimized'},
            {'id':2,'kind':'tree','position':[5,5,20.],'recipe':'Pine_Sapling_A'}]}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'trees.json'
            def write():path.write_text(json.dumps(document))
            write();report=final.checked_selection(path,field)
            self.assertEqual(report['selected_count'],2)
            self.assertAlmostEqual(report['max_root_height_error_m'],.001)
            document['instances'][0]['position'][2]=20.1;write()
            with self.assertRaisesRegex(ValueError,'runtime triangles'):final.checked_selection(path,field)
            document['instances'][0]['position'][2]=20.
            document['instances'][1]['id']=1;write()
            with self.assertRaisesRegex(ValueError,'unique'):final.checked_selection(path,field)
            document['selected_count']=3;write()
            with self.assertRaisesRegex(ValueError,'exact count'):final.checked_selection(path,field)


if __name__=='__main__':unittest.main()
