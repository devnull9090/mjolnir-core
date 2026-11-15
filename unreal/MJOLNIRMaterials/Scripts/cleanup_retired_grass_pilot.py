"""One-time exact retired pilot cleanup; requires verified CPU backup first."""
import hashlib
import json
from pathlib import Path
import unreal

ROOT = Path(__file__).resolve().parents[3]
backup = ROOT/"out/pwr/visual-v7/retired-PWRGrassPilot-before-LPG"
receipt = json.loads((backup/"backup.receipt.json").read_text())
folder = ROOT/"Unreal/MJOLNIRMaterials/Content/Levels/Halo1/Solo/PWRGrassPilot"
identities = {
    "PAL_PWRGrassPilotWorld.uasset": "/Game/Levels/Halo1/Solo/PWRGrassPilot/PAL_PWRGrassPilotWorld",
    "PWRGrassPilot.umap": "/Game/Levels/Halo1/Solo/PWRGrassPilot/PWRGrassPilot",
}
assert {p.name for p in folder.iterdir()} == set(identities), "Unexpected retired folder contents"
assert len(receipt["files"]) == 2
for row in receipt["files"]:
    source, saved = Path(row["source"]), Path(row["backup"])
    assert source.resolve().parent == folder.resolve() and source.name in identities
    assert saved.resolve().parent == backup.resolve() and saved.name == source.name
    assert hashlib.sha256(source.read_bytes()).hexdigest() == row["sha256"]
    assert hashlib.sha256(saved.read_bytes()).hexdigest() == row["sha256"]

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assert les.load_level("/Game/__MJOLNIR_GrassPilotScratch"), "Could not release retired world"
eal = unreal.EditorAssetLibrary
for package in identities.values():
    assert eal.delete_asset(package), "Failed retired pilot asset deletion: " + package
assert not any(folder.iterdir()), "Retired pilot files remain"
for package in identities.values():
    assert not eal.does_asset_exist(package), "Retired pilot asset remains registered"
(backup/"cleanup.receipt.json").write_text(json.dumps({
    "schema":"pwr-grass-pilot-retired-cleanup-v1",
    "removed_packages":list(identities.values()),
    "verified_backups":receipt["files"],
    "asset_registry_absent":True,
},indent=2)+"\n")
unreal.log("MJOLNIR retired PWRGrassPilot world and label removed; verified backup retained")
