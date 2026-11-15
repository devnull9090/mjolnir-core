"""Author PWR's native Gaea landforms; build via the licensed Gaea UI.

No image luminance is used as elevation. Broad Alpine mountain primitives and
lower foothills feed two hydraulic erosion passes. Roads and sites are applied
later against the frozen gameplay contract, not baked into the geomorphology.
"""
from pathlib import Path
import argparse
import json
import itertools

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "out/pwr/gaea-world-v5"
ids = itertools.count(1000)


def obj(**values):
    return {"$id": str(next(ids)), **values}


def node(kind, ident, name, x, y, inputs=(), **settings):
    n = obj(**{"$type": f"QuadSpinner.Gaea.Nodes.{kind}, Gaea.Nodes"},
            **settings, Id=ident, Name=name, Position=obj(X=x, Y=y))
    ports = []
    if not inputs:
        ports.append(obj(Name="In", Type="PrimaryIn", IsExporting=True,
                         Parent={"$ref": n["$id"]}))
    for port, source, source_port in inputs:
        ports.append(obj(Name=port, Type="PrimaryIn, Required" if port == "In" else "In",
                         Record=obj(From=source, To=ident, FromPort=source_port,
                                    ToPort=port, IsValid=True), IsExporting=True,
                         Parent={"$ref": n["$id"]}))
    for port in (["Out", "Flow", "Wear", "Deposits"] if kind == "Erosion2" else ["Out"]):
        ports.append(obj(Name=port, Type="PrimaryOut" if port == "Out" else "Out",
                         IsExporting=True, Parent={"$ref": n["$id"]}))
    # Gaea's native Node.Out accessor expects slot 1 even for primitives.
    ports.sort(key=lambda p: 0 if p["Name"] == "In" else 1 if p["Name"] == "Out" else 2)
    n["Ports"] = obj(**{"$values": ports})
    n["Modifiers"] = obj(**{"$values": []})
    return n


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", default="v5")
    parser.add_argument("--southeast-x", type=float, default=.95)
    parser.add_argument("--peripheral-shoulders", action="store_true")
    args = parser.parse_args()
    destination = ROOT / ("out/pwr/gaea-world-" + args.variant)
    doc = json.loads((HERE / "pwr_world_refined.terrain").read_text())
    asset = doc["Assets"]["$values"][0]
    terrain = asset["Terrain"]
    nodes = {"$id": "5"}
    # Irregular broad mountain masses at the valley margins. Coordinates are
    # native Gaea normalized positions; source export is calibrated separately.
    masses = [
        (101, "Northwest massif", .12, .17, .32, 2.8, 14206),
        (102, "Western shoulder", .03, .53, .30, 2.35, 61828),
        (103, "Southwest massif", .13, .94, .29, 2.6, 14637),
        (104, "Northeast massif", .89, .10, .34, 3.0, 29158),
        (105, "Eastern escarpment", .99, .49, .29, 2.5, 1222),
        (106, "Southeast massif", args.southeast_x, .92, .27, 2.3, 32534),
        (107, "Western foothills", .30, .44, .46, .55, 19271),
        (108, "Eastern foothills", .73, .34, .43, .65, 43919),
        (109, "Northern saddle", .51, .02, .36, .85, 56719),
        (110, "Southern foothills", .42, .90, .42, .45, 49217),
    ]
    if args.peripheral_shoulders:
        replacements = {102: (-.08, .53), 103: (-.04, 1.02), 105: (1.08, .49)}
        masses = [(ident, name, *replacements.get(ident, (x, y)), scale, height, seed)
                  for ident, name, x, y, scale, height, seed in masses]
    for index, (ident, name, x, y, scale, height, seed) in enumerate(masses):
        nodes[str(ident)] = node("Mountain", ident, name, 26000, 25200 + index * 170,
                                Scale=scale, Height=height, Style="Alpine", Seed=seed, X=x, Y=y)
    # Max combines preserve the individual drainages rather than stacking peaks.
    combine_ids = []
    for group, members in enumerate([masses[:4], masses[4:8], masses[8:]]):
        ident = 120 + group
        inputs = [("In" if i == 0 else f"Input{i+1}", m[0], "Out") for i, m in enumerate(members)]
        nodes[str(ident)] = node("Combine", ident, "Landform group", 26400, 25400 + group*450,
                                inputs, PortCount=len(inputs), Ratio=1.0, Mode="Max")
        combine_ids.append(ident)
    nodes["125"] = node("Combine", 125, "Complete watershed relief", 26800, 26000,
                        [("In" if i == 0 else f"Input{i+1}", v, "Out") for i, v in enumerate(combine_ids)],
                        PortCount=3, Ratio=1.0, Mode="Max")
    nodes["130"] = node("Erosion2", 130, "Primary drainage erosion", 27200, 26000,
                        [("In", 125, "Out")], Duration=24.0, Downcutting=.28,
                        ErosionScale=240.0, Seed=20569,
                        SuspendedLoadDischargeAmount=.25, CoarseSedimentsDischargeAmount=.35,
                        Shape=.12, ShapeSharpness=.25, ShapeDetailScale=.08, Version=2)
    nodes["131"] = node("Erosion2", 131, "Talus and foothill settling", 27600, 26000,
                        [("In", 130, "Out")], Duration=12.0, Downcutting=.05,
                        ErosionScale=90.0, Seed=52371, CoarseSedimentsDischargeAmount=.7,
                        CoarseSedimentsDischargeAngle=28.0, Shape=0.0, Version=2)
    for index, port in enumerate(["Out", "Flow", "Wear", "Deposits"]):
        ident = 200 + index
        name = "pwr_height" if port == "Out" else "pwr_" + port.lower()
        n = node("Export", ident, name, 28000, 25800 + index*200,
                 [("In", 131, port)], Format="FloatRaw32")
        n["SaveDefinition"] = obj(Node=ident, Filename=name, Format="FloatRaw32", IsEnabled=True,
                                  DisabledInProfiles=obj(**{"$values": []}))
        nodes[str(ident)] = n
    terrain["Nodes"] = nodes
    terrain.update(Width=2000.0, Height=400.0, Ratio=.2)
    tab = terrain["GraphTabs"]["$values"][0]
    tab.update(ZoomFactor=.4)
    tab["ViewportLocation"].update(X=25300, Y=24700)
    asset["BuildDefinition"].update(Destination=str(destination), Resolution=1024, BakeResolution=1024)
    asset["State"].update(SelectedNode=200, PreviewResolution=512)
    doc["Metadata"].update(Name="PWR native Gaea watershed v5", Description=__doc__.strip())
    path = HERE / ("pwr_world_native_" + args.variant + ".terrain")
    path.write_text(json.dumps(doc, indent=2) + "\n")
    destination.mkdir(parents=True, exist_ok=True)
    print(path)


if __name__ == "__main__":
    main()
