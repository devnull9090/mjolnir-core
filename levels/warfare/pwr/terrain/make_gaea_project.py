"""Author the PWR refinement graph using inspected official Gaea node schemas.

This writes a project only. Community evaluation/build/export remains in the UI.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = HERE / "reference/SimpleErosion.terrain"
PROJECT = HERE / "pwr_world_refined.terrain"
SEED = HERE / "world-height-seed-v2.png"
OUTPUT = ROOT / "out/pwr/gaea-world-v2"


def verify(document):
    ids, refs = set(), []
    def walk(item):
        if isinstance(item, dict):
            if "$id" in item:
                assert item["$id"] not in ids, "duplicate serialization identity"
                ids.add(item["$id"])
            if "$ref" in item:
                refs.append(item["$ref"])
            for value in item.values():
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)
    walk(document)
    assert all(ref in ids for ref in refs), "dangling serialization reference"
    asset = document["Assets"]["$values"][0]
    nodes = asset["Terrain"]["Nodes"]
    node_ids = {node["Id"] for node in nodes.values() if isinstance(node, dict)}
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        for port in node["Ports"]["$values"]:
            record = port.get("Record")
            if record:
                assert record["To"] == node["Id"] and record["From"] in node_ids
                parent = nodes[str(record["From"])]
                assert any(p["Name"] == record["FromPort"] for p in parent["Ports"]["$values"])
    assert asset["BuildDefinition"]["Resolution"] == 1024
    assert asset["Terrain"]["Width"] == 2000 and asset["Terrain"]["Height"] == 400
    assert not asset["Automation"]["Bindings"]["$values"]


def make():
    document = json.loads(SOURCE.read_text(encoding="utf-8-sig"))
    asset = document["Assets"]["$values"][0]
    terrain, automation = asset["Terrain"], asset["Automation"]
    nodes = terrain["Nodes"]
    # The official template includes a SatMap/color branch, which this data
    # handoff does not need. All retained graph IDs and connection records stay.
    del nodes["436"]
    del nodes["650"]
    for key in ("Bindings", "Expressions", "VariablesEx", "Variables"):
        original = automation[key]
        automation[key] = {"$id": original["$id"]}
        if key == "Bindings":
            automation[key]["$values"] = []
    file_node, erosion = nodes["755"], nodes["701"]
    file_node.update(FileName=str(SEED), RelativePath=False, IsRGB=False, Name="Approved World Height Seed")
    # Exact modifier schema copied from the bundled
    # Structure - Side Carved Mountains.terrain, node154/modifier$id53.
    # Factor is deliberately small to soften RGB8 height terraces without
    # replacing the approved river/lake and mountain composition.
    file_node["Modifiers"]["$values"] = [{
        "$id": "122", "$type": "QuadSpinner.Gaea.Nodes.Modifiers.Blur, Gaea.Nodes",
        "Factor": 0.02, "Name": "Blur", "Parent": {"$ref": file_node["$id"]},
        "HasUI": True, "Intrinsic": True,
    }]
    # All keys below occur in bundled Erosion2 examples. Duration4 is also
    # present in Technical - Using Loops; Downcutting/Scale are in Canyon River.
    erosion.update(Name="Restrained Watershed Refinement", Duration=4.0,
        Downcutting=0.1, ErosionScale=120.0, Seed=20568,
        SuspendedLoadDischargeAmount=0.15, BedLoadDischargeAmount=0.1,
        CoarseSedimentsDischargeAmount=0.1, Shape=0.0, ShapeDetailScale=0.02)
    exports = {"737": "pwr_height", "673": "pwr_flow", "211": "pwr_wear", "121": "pwr_deposits"}
    for node_id, name in exports.items():
        node = nodes[node_id]
        # GaeaRaw is the observed enum value in the official project. Root
        # selects Float Raw32 in the UI and calibrates that exported format;
        # inventing an enum string here would make deserialization fragile.
        node.update(Name=name, Format="GaeaRaw", Location="Explicit", OutputPath=str(OUTPUT / (name + ".graw")))
        node["SaveDefinition"].update(Filename=name, IsEnabled=True)
    terrain.update(Width=2000.0, Height=400.0, Ratio=0.2)
    description = ("PWR approved world reference v1, height seed v2. File + restrained native Erosion2; "
        "not a finished terrain until UI import, visual inspection, height calibration and export pass. "
        "Terrains powered by QuadSpinner Gaea. Adapted from the official Gaea2Houdini SimpleErosion example; "
        "see reference/LICENSE.Gaea2Houdini.")
    terrain["Metadata"].update(Name="PWR World Watershed Refinement", Description=description)
    document["Metadata"].update(Name="PWR World Watershed Refinement", Description=description)
    asset["BuildDefinition"].update(Type="Standard", Destination=str(OUTPUT), Resolution=1024,
        BakeResolution=1024, BucketResolution=1024, PostBuildScript="")
    asset["State"].update(PreviewResolution=512, BakeResolution=1024, SelectedNode=701)
    verify(document)
    PROJECT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    receipt = {
        "schema": "pwr-gaea-project-v1", "project": PROJECT.name,
        "source_url": "https://github.com/QuadSpinner/Gaea2Houdini/blob/main/src/misc/gaea/SimpleErosion.terrain",
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "project_sha256": hashlib.sha256(PROJECT.read_bytes()).hexdigest(),
        "source_license": "reference/LICENSE.Gaea2Houdini",
        "required_credit": "Terrains powered by QuadSpinner Gaea.",
        "seed": SEED.name, "seed_exists_at_authoring": SEED.exists(),
        "width_m": 2000, "height_scale_m": 400, "resolution": 1024,
        "output_directory": str(OUTPUT), "configured_format": "GaeaRaw",
        "requested_final_format": "float32_raw_le, selected and calibrated in Gaea UI",
        "state": "authored; awaiting Gaea UI open/build/export validation",
        "earlier_terrain_seed_v1": "EXPERIMENTAL, superseded by approved world reference",
    }
    (HERE / "pwr_world_refined.receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(PROJECT)
    print("Validated 6 nodes, all graph links and serialization references; pending Gaea UI validation.")


if __name__ == "__main__":
    make()
