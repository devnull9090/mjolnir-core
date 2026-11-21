"""Editor commandlet: write the xy (UE cm) of every plant-like instance in LPE to PWR_PLANT_POINTS (.f32 pairs).

Plant-like: any instanced component whose mesh path names grass, fern, fescue, sedge, rush, litter,
weed, flower or shrub. Rocks, trees, bark and branches are left out. meadow_life.py treats ground within
2.5 m of these as natural, plantable ground: every earlier pass found it free of paving and obstacles.
"""
import os, re, struct
import unreal as ue
ue.get_editor_subsystem(ue.LevelEditorSubsystem).load_level("/Game/Levels/Halo1/Solo/LPE/LPE")
plant = re.compile(r"grass|fern|fescue|sedge|rush|litter|weed|flower|shrub|balsam|clover", re.I)
buf, comps = bytearray(), 0
for a in ue.get_editor_subsystem(ue.EditorActorSubsystem).get_all_level_actors():
    for c in a.get_components_by_class(ue.InstancedStaticMeshComponent):
        m = c.get_editor_property("static_mesh")
        if not m or not plant.search(m.get_path_name()):
            continue
        comps += 1
        for i in range(c.get_instance_count()):
            t = c.get_instance_transform(i, True).translation
            buf += struct.pack("<2f", t.x, t.y)
open(os.environ["PWR_PLANT_POINTS"], "wb").write(bytes(buf))
ue.log(f"plant points: {len(buf) // 8} from {comps} components")
