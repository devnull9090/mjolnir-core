"""Author the three lake features into a single persistent world and verify them on reload."""
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
import unreal as ue

root = Path(os.environ["PWR_HEADWATER_ROOT"])
work = root / "out/pwr/river-riparian"
sys.path.insert(0, str(root / "unreal/MJOLNIRMaterials/Scripts"))
verify = os.environ.get("PWR_HEADWATER_VERIFY") == "1"

def run():
    import apply_pwr_cutbank_roots as cutbank
    import apply_pwr_riparian_canopy as canopy
    import apply_pwr_spring_cascade as cascade
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    if not levels.load_level("/Game/Levels/Halo1/Solo/LPE/LPE"):
        raise RuntimeError("Could not load the lake world")
    cutbank.apply(work, verify)
    cascade.apply(work / "cascade", verify)
    canopy.run(verify=verify)
    if not verify and not levels.save_current_level():
        raise RuntimeError("Could not save the lake world")
    if verify:
        paths = {}
        stems=["M_PWR_SpringCascade","SM_PWR_SpringCascade","M_PWR_CutbankRoots","SM_PWR_CutbankRoots"]
        if int(os.environ.get("PWR_SHORE_VERSION","40"))>=41:
            stems.extend(("M_PWR_RiparianSun","MI_PWR_RiparianCanyon","MI_PWR_RiparianWild",
                          "MI_PWR_RiparianWillow","T_PWR_RiparianWillow"))
        for stem in stems:
            asset = ue.EditorAssetLibrary.load_asset("/Game/MJOLNIR/GrassPilot/Playable/" + stem)
            if not asset:
                raise ValueError("Missing reopened native package " + stem)
            paths[stem] = asset.get_path_name()
        modules = {m.__name__:hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (cutbank,canopy,cascade)}
        (work/"editor-verified.json").write_text(json.dumps(dict(assets=paths,modules=modules), indent=2))

try:
    run()
except Exception:
    (work / ("verify-error.txt" if verify else "apply-error.txt")).write_text(traceback.format_exc())
    raise
