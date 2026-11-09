"""Build the CTF flag's cloth master, into shader chunk 966 beside KOTH's.

M_CE_FlagCloth is M_CE_EnvironmentMaskedTwoSided (build_ce_materials.py
build_environment, the cloth's material before this one) with a World
Position Offset that waves the sheet on the GPU. MJOLNIRLevelLoader
(teams.lua CLOTH) hangs the cloth as `n` strips of /Engine/BasicShapes/Plane
from the flag's pole, each with its slice of the texture (BaseXform). It used
to bend the sheet by moving every strip from Lua, up to 30 times a second;
each move costs the game thread ~60 us (docs/lua_native_audit.md). With this
master the strips stay laid out straight and each frame's bend is computed
here, from the material's Time. Lua sets ClothWave only while a flag is
carried (its trail and quicker ripple), and draws the strips the old way
where the master is missing (a CE runtime pack from before it).

Its own folder, cooked into KOTH's chunk 966 (docs/koth_visuals.md): the
runtime pack's 988 masters are not rebuilt for it, and it needs no shader
chunk number of its own. The game opens a container's shader library by the
number in its file name, the launcher numbers every other hub container
900 + its place in the load order, and the launcher counts only
`pakchunk9NN-MJOLNIR...` as ours, so any new 9NN number would be some
player's map container (971 was Battle Creek's on PC 1). Run via
tools/ue/editor_cmd.ps1 (after build_koth_materials.py, so the cook carries
both), then tools/ue/cook.ps1; tools/level/build_ce_runtime.sh ships it in
pakchunk966-MJOLNIRKOTH-Windows.
"""
import importlib.util
import os
from pathlib import Path

import unreal

ROOT = "/Game/MJOLNIR/Cloth"
CHUNK = 966

# Library mode only imports the graph helpers; no CE assets or labels are
# built. The environment builder and its default textures write to the
# module's ROOT, read at call time.
os.environ["MJ_CE_LIBRARY"] = "1"
module_spec = importlib.util.spec_from_file_location(
    "cloth_ce_graphs", Path(__file__).with_name("build_ce_materials.py"))
ce = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(ce)
ce.ROOT = ROOT

# The sheet as teams.lua lays it: strip k of n (1-based) spans the sheet
# from (k - 1) / n to k / n, its local +X running out from the pole, local
# +Z its face. Strip j turns a_j = swing + amp * (j / n) * sin(phase -
# j * crest / n) about the pole (local Y), phase = Time * rate + offset
# (ClothWave: swing, amp, rate, offset). A vertex t of the way along strip k
# sits where strips 1..k-1 end, plus t of strip k, each strip turned by its
# own angle: the chain teams.lua's layCloth built by moving the strips. Its
# offset is that place minus the straight sheet's. BaseXform gives k and n
# (R = 1/n, B = (k - 1)/n); ClothOn 0 holds the sheet straight.
CLOTH_WPO_CODE = r"""
float n = max(round(1.0 / max(Xform.x, 0.0001)), 1.0);
float k = round(Xform.z * n) + 1.0;
float t = saturate(Local.x * 0.01 + 0.5);
float len = length(AxisX) * 100.0;
float3 D = AxisX / max(length(AxisX), 0.0001);
float3 F = AxisZ / max(length(AxisZ), 0.0001);
float phase = Time * Wave.z + Wave.w;
float3 off = float3(0.0, 0.0, 0.0);
for (int j = 1; j <= 16; j++)
{
    if (j > k) break;
    float a = Wave.x + Wave.y * (j / n) * sin(phase - j * Crest / n);
    float f = j < k ? 1.0 : t;
    off += f * len * (sin(a) * F + (cos(a) - 1.0) * D);
}
return off * On;
"""


def local_axis(g, axis):
    """The strip's local `axis` (a unit vector) in world space, its scale
    included."""
    c = g.node(unreal.MaterialExpressionConstant3Vector, x=-1300, constant=unreal.LinearColor(*axis, 0.0))
    t = g.node(unreal.MaterialExpressionTransform, x=-1100,
               transform_source_type=unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_LOCAL,
               transform_type=unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    ce.link(c, "", t, "")
    return t


def cloth_offset(g, m):
    world_position = g.node(unreal.MaterialExpressionWorldPosition, x=-1300)
    local_position = g.node(unreal.MaterialExpressionTransformPosition, x=-1100,
        transform_source_type=unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_WORLD,
        transform_type=unreal.MaterialPositionTransformSource.TRANSFORMPOSSOURCE_LOCAL)
    ce.link(world_position, "", local_position, "")
    wpo = g.custom(CLOTH_WPO_CODE, [
        ("Xform", g.vector4("BaseXform", (1, 1, 0, 0)), ""),
        ("Local", local_position, ""),
        ("AxisX", local_axis(g, (1.0, 0.0, 0.0)), ""),
        ("AxisZ", local_axis(g, (0.0, 0.0, 1.0)), ""),
        ("Time", g.node(unreal.MaterialExpressionTime), ""),
        # teams.lua WAVE at rest: no swing, idle 0.32 rad, 3.2 rad/s.
        ("Wave", g.vector4("ClothWave", (0.0, 0.32, 3.2, 0.0)), ""),
        ("Crest", g.scalar("ClothCrest", 6.8), ""),
        ("On", g.scalar("ClothOn", 1.0), ""),
    ], description="CTF flag cloth")
    if not unreal.MjolnirUIBuilderLibrary.connect_world_position_offset(m, wpo, ""):
        raise RuntimeError(f"cannot connect World Position Offset on {m.get_name()}")
    # The far edge can swing round to anywhere within the sheet's length
    # (1.22 m) of the pole: the engine pads each strip's bounds by this much
    # (cm), so a strip whose straight rest place is off screen or behind a
    # wall is still drawn where the wave puts it. Lua adds a bounds scale.
    m.set_editor_property("max_world_position_offset_displacement", 300.0)


defaults = ce.build_defaults()
ce.build_environment("M_CE_FlagCloth", True, defaults, two_sided=True, offset=cloth_offset)
label = ce.fresh(ROOT, "PAL_MJOLNIR_Cloth", unreal.PrimaryAssetLabel, unreal.DataAssetFactory())
rules = label.get_editor_property("rules")
rules.set_editor_property("chunk_id", CHUNK)
rules.set_editor_property("priority", 20)
rules.set_editor_property("apply_recursively", True)
rules.set_editor_property("cook_rule", unreal.PrimaryAssetCookRule.ALWAYS_COOK)
label.set_editor_property("rules", rules)
label.set_editor_property("label_assets_in_my_directory", True)
ce.eal.save_loaded_asset(label)
unreal.log("MJOLNIR flag cloth master ready: " + ROOT + "/M_CE_FlagCloth chunk " + str(CHUNK))
