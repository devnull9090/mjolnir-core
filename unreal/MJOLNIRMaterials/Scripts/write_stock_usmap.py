"""Write the stock engine's property schemas (this editor, UE 5.5) to
defs/ue/UE-5.5-stock.usmap, for re-encoding stock-cooked packages in the
game's layout (ue-asset's retarget; the landscape spike, 2026-10-11).

    powershell -File tools/ue/editor_cmd.ps1 -Script Scripts/write_stock_usmap.py
"""
import os

import unreal

out = os.path.normpath(os.path.join(unreal.Paths.project_dir(), "..", "..", "defs", "ue", "UE-5.5-stock.usmap"))
if not unreal.MjolnirUIBuilderLibrary.write_usmap(out):
    raise RuntimeError(f"write_usmap {out} failed")
unreal.log(f"MJOLNIR stock usmap written: {out}")
