"""Split rebuild preflight must refuse conflicting inputs without writes."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from test_partition_tst_facility import write_jms

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / 'levels/test/tst/rebuild.ps1'


class SplitRebuildPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hek = self.root / 'hek'
        self.addon = self.root / 'addon'
        self.mcc = self.root / 'mcc'
        for folder in (self.hek / 'tags', self.hek / 'maps', self.addon, self.mcc):
            folder.mkdir(parents=True)
        self.bundle = self.root / 'bundle'

    def run_rebuild(self, *args):
        return subprocess.run(['pwsh', '-NoProfile', '-File', str(SCRIPT),
            '-HekRoot', str(self.hek), '-AddonRoot', str(self.addon),
            '-MccTagsRoot', str(self.mcc), *map(str, args)],
            cwd=REPO, capture_output=True, text=True, encoding='utf-8', errors='replace')

    def assert_refused(self, process, message):
        self.assertNotEqual(process.returncode, 0)
        self.assertIn(message, process.stdout + process.stderr)

    def test_split_requires_new_geometry_not_skip(self):
        result = self.run_rebuild('-SplitFacilityDetail', '-FacilityOutputDir', self.bundle, '-SkipGeometry')
        self.assert_refused(result, 'requires a fresh full geometry export')
        self.assertFalse(self.bundle.exists())

    def test_existing_bundle_is_preserved(self):
        self.bundle.mkdir()
        marker = self.bundle / 'user.txt'
        marker.write_text('keep', encoding='utf-8')
        result = self.run_rebuild('-SplitFacilityDetail', '-FacilityOutputDir', self.bundle)
        self.assert_refused(result, 'Facility output already exists')
        self.assertEqual(marker.read_text(encoding='utf-8'), 'keep')

    def test_existing_hek_tst_output_is_preserved(self):
        jms = self.hek / 'data/levels/test/tst/models/tst.JMS'
        jms.parent.mkdir(parents=True)
        jms.write_bytes(b'user geometry')
        result = self.run_rebuild('-SplitFacilityDetail', '-FacilityOutputDir', self.bundle)
        self.assert_refused(result, 'requires an unused TST HEK destination')
        self.assertEqual(jms.read_bytes(), b'user geometry')
        self.assertFalse(self.bundle.exists())

    def test_bundle_inside_hek_is_rejected(self):
        result = self.run_rebuild('-SplitFacilityDetail', '-FacilityOutputDir', self.hek / 'bundle')
        self.assert_refused(result, 'outside the HEK and map source directories')
        self.assertFalse((self.hek / 'bundle').exists())

    def test_standard_skip_does_not_enter_split_preflight(self):
        result = self.run_rebuild('-SkipGeometry')
        self.assert_refused(result, 'Required rebuild input is missing')
        self.assertNotIn('requires a fresh full geometry export', result.stdout + result.stderr)
        self.assertFalse(self.bundle.exists())


@unittest.skipUnless(os.name == 'nt' and shutil.which('rustc') and
                     Path('C:/Program Files/Blender Foundation/Blender 5.1/blender.exe').is_file(),
                     'Synthetic orchestration needs Windows, rustc and Blender 5.1')
class SplitRebuildOrchestrationTests(unittest.TestCase):
    """Run the real wrapper with harmless fake tools, never a real HEK."""
    @classmethod
    def setUpClass(cls):
        cls.tools = tempfile.TemporaryDirectory()
        rust = Path(cls.tools.name) / 'tool.rs'
        cls.exe = Path(cls.tools.name) / 'tool.exe'
        rust.write_text(r'''
use std::{env,fs,path::Path};
fn put(p:&str, d:&str) { let x=Path::new(p); fs::create_dir_all(x.parent().unwrap()).unwrap(); fs::write(x,d).unwrap(); }
fn main() { let a:Vec<String>=env::args().collect(); match a[1].as_str() {
 "structure" => { put("tags/levels/test/tst/tst.scenario_structure_bsp","new bsp");
                  put("tags/levels/test/tst/tst.scenario","structure stub");
                  println!("structure bsp levels/test/tst/tst; 1 clusters; without debug information"); },
 "lightmaps" => { put("tags/levels/test/tst/tst.bitmap","new bitmap");
                  println!("finished levels\\test\\tst\\tst done");
                  if env::var("TST_TEST_LIGHTMAP_FAILURE").is_ok() { println!("EXCEPTION_ACCESS_VIOLATION"); } },
 "build-cache-file" => { put("maps/tst.map","new map"); println!("successfully built cache file.");
                  if env::var("TST_TEST_CACHE_FAILURE").is_ok() { put("maps/bitmaps.map","new placeholder"); println!("EXCEPTION_ACCESS_VIOLATION"); } },
 _ => std::process::exit(1) } }
''', encoding='utf-8')
        result = subprocess.run(['rustc', str(rust), '-o', str(cls.exe)], capture_output=True, text=True)
        if result.returncode:
            cls.tools.cleanup()
            raise unittest.SkipTest('Cannot compile synthetic HEK tool: ' + result.stderr[-500:])

    @classmethod
    def tearDownClass(cls):
        cls.tools.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'repo'
        self.source = self.repo / 'levels/test/tst'
        self.hek = self.root / 'hek'
        self.addon = self.root / 'addon'
        self.mcc = self.root / 'mcc'
        self.bundle = self.root / 'new-bundle'
        self.source.mkdir(parents=True)
        shutil.copy2(SCRIPT, self.source / 'rebuild.ps1')
        self.hek.mkdir(exist_ok=True)
        shutil.copy2(self.exe, self.hek / 'tool.exe')
        self.put(self.addon / 'file_tag/tag_interface/tag_interface.py', '')
        self.put(self.source / 'bundle_textures.py', '')
        self.put(self.source / 'terrain_form.py', '')
        self.put(self.source / 'perimeter_architecture.py', '')
        self.put(self.source / 'perimeter_dressing.py', '')
        self.put(self.source / 'amber_light.json', '{}')
        surfaces = {}
        for role in ('facility_armor', 'structure'):
            shader = f'tst_metal_{role}'
            surfaces[role] = {'shader': shader, 'tag': f'levels/test/tst/shaders/{shader}',
                'fallback': 'metal panels generic ext', 'albedo': 'art/textures/test.png',
                'roughness_map': 'art/textures/test.png', 'tint': [1, 1, 1],
                'roughness': [.2, .8], 'metallic': .1, 'soften': 0}
        surface = {'version': 1, 'surfaces': surfaces}
        self.put(self.source / 'surfaces.json', json.dumps(surface))
        write_jms(self.source / 'fixture.JMS')
        geometry = '''from pathlib import Path\nimport sys,shutil\na=sys.argv; out=Path(a[a.index("--out-dir")+1]); (out/"data/levels/test/tst/models").mkdir(parents=True,exist_ok=True); shutil.copyfile(Path(__file__).with_name("fixture.JMS"),out/"data/levels/test/tst/models/tst.JMS"); (out/"tst.blend").write_bytes(b"blend"); (out/"placements.json").write_text("{}"); (out/"art/textures").mkdir(parents=True); (out/"art/textures/test.png").write_bytes(b"texture")\n'''
        self.put(self.source / 'build_geometry.py', geometry)
        annotate = '''from pathlib import Path\nimport sys\na=sys.argv; p=Path(a[a.index("--blend")+1]); p.write_bytes(b"annotated")\n'''
        self.put(self.source / 'annotate_blend.py', annotate)
        self.put(self.source / 'amber_light.py', '''from pathlib import Path\nimport sys\na=sys.argv; p=Path(a[a.index("--output")+1]); p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b"amber")\n''')
        self.put(self.source / 'build_scenario.py', '''from pathlib import Path\nimport sys,json,hashlib\na=sys.argv; p=Path(a[a.index("--hek")+1])/"tags/levels/test/tst/tst.scenario"; p.write_bytes(b"authored scenario"); print(json.dumps({"scenario":str(p),"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"roundtrip":"passed"}))\n''')
        self.put(self.repo / 'tools/level/placeholder', '')
        for filename in ('partition_tst_facility.py', 'authored_surfaces.py', 'make_tst_facility_receipt.py'):
            shutil.copy2(REPO / 'tools/level' / filename, self.repo / 'tools/level' / filename)
        shutil.copy2(REPO / 'tools/level/verify_tst_facility_receipt.py', self.repo / 'tools/level/real_verify_tst_facility_receipt.py')
        verify = '''from real_verify_tst_facility_receipt import *\nif __name__ == "__main__":\n import os,sys\n if os.environ.get("TST_TEST_VERIFY_FAILURE"): sys.exit(2)\n main()\n'''
        self.put(self.repo / 'tools/level/verify_tst_facility_receipt.py', verify)
        for name in ('bitmaps.map', 'sounds.map', 'loc.map'):
            self.put(self.hek / 'maps' / name, 'original ' + name)
        self.put(self.hek / 'tags/levels/b30/shaders/water.shader_transparent_water', 'water')
        self.put(self.hek / 'tags/levels/test/bloodgulch/shaders/mp lights small strips.shader_environment', 'atlas')
        self.put(self.hek / 'tags/levels/b30/shaders/metal panels generic ext.shader_environment', 'fallback')
        for relative in ('levels/b30/shaders/beach.shader_environment',
                         'levels/b30/shaders/cliffs.shader_environment', 'levels/b30/bitmaps/beach.bitmap'):
            self.put(self.mcc / relative, 'stock')
            self.put(self.hek / 'tags' / relative, 'stock')

    @staticmethod
    def put(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='utf-8')

    def invoke(self, failure=None):
        env = os.environ.copy()
        if failure:
            env['TST_TEST_' + failure.upper() + '_FAILURE'] = '1'
        return subprocess.run(['pwsh', '-NoProfile', '-File', str(self.source / 'rebuild.ps1'),
            '-HekRoot', str(self.hek), '-AddonRoot', str(self.addon), '-MccTagsRoot', str(self.mcc),
            '-BlenderExe', 'C:/Program Files/Blender Foundation/Blender 5.1/blender.exe',
            '-SplitFacilityDetail', '-FacilityOutputDir', str(self.bundle)],
            cwd=self.repo, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')

    def test_success_keeps_full_jms_and_publishes_receipt_after_cache(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        full = self.bundle / 'authoring/data/levels/test/tst/models/tst.JMS'
        reduced = self.hek / 'data/levels/test/tst/models/tst.JMS'
        self.assertEqual(full.read_bytes(), (self.source / 'fixture.JMS').read_bytes())
        self.assertNotEqual(reduced.read_bytes(), full.read_bytes())
        self.assertEqual(reduced.read_bytes(), (self.bundle / 'partition/tst-ce-structure.JMS').read_bytes())
        self.assertEqual((self.bundle / 'tst.map').read_text(), 'new map')
        self.assertTrue((self.bundle / 'tst-facility-ce-build-receipt.json').is_file())
        self.assertEqual((self.hek / 'maps/bitmaps.map').read_text(), 'original bitmaps.map')
        self.assertEqual((self.bundle / 'authoring/art/textures/test.png').read_bytes(), b'texture')

    def test_failed_receipt_verification_leaves_no_canonical_receipt(self):
        result = self.invoke(failure='verify')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('facility-receipt-verify', result.stdout + result.stderr)
        self.assertFalse((self.bundle / 'tst-facility-ce-build-receipt.json').exists())
        self.assertTrue((self.bundle / '.tst-facility-ce-build-receipt.pending').exists())
        self.assertEqual((self.hek / 'maps/bitmaps.map').read_text(), 'original bitmaps.map')

    def test_lightmap_exception_cannot_publish_receipt_or_build_cache(self):
        result = self.invoke(failure='lightmap')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('exception', (result.stdout + result.stderr).lower())
        self.assertFalse((self.bundle / 'tst-facility-ce-build-receipt.json').exists())
        self.assertFalse((self.hek / 'maps/tst.map').exists())
        self.assertEqual((self.hek / 'maps/bitmaps.map').read_text(), 'original bitmaps.map')

    def test_cache_exception_restores_bitmap_and_never_publishes_receipt(self):
        result = self.invoke(failure='cache')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('exception', (result.stdout + result.stderr).lower())
        self.assertFalse((self.bundle / 'tst-facility-ce-build-receipt.json').exists())
        self.assertEqual((self.hek / 'maps/bitmaps.map').read_text(), 'original bitmaps.map')
        self.assertEqual((self.hek / 'maps/bitmaps.map.tst-build-created').read_text(), 'new placeholder')


if __name__ == '__main__':
    unittest.main()
