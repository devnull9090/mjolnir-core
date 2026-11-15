"""Private PWR wrapper: verify/package new base chunk before sealing map cook."""
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tools/level'))
import upgrade_ce_map

original_cook=upgrade_ce_map.stage_cook


def cook_then_package(maps):
    original_cook(maps)
    # The standard pipeline seals required_external_assets immediately after
    # stage_cook. Create and read back the independent 955 package first.
    subprocess.run([sys.executable,str(Path(__file__).with_name('package_runtime_visuals.py'))],cwd=ROOT,check=True)


if __name__=='__main__':
    upgrade_ce_map.CONFIG=str(Path(__file__).parent.parent/'upgrade-bases-v1.json')
    upgrade_ce_map.stage_cook=cook_then_package
    sys.argv=[sys.argv[0],'PWR','--work','C:/haloce/ce_conversions/warfare/PWR/expansion/world-bases-v1/upgrade',*sys.argv[1:]]
    upgrade_ce_map.main()
