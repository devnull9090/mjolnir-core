"""Bake the measured, bounded Southwest forest fill into the native level."""
import json
import math
import os
from pathlib import Path

import unreal as ue


WORLD = "/Game/Levels/Halo1/Solo/LPE/LPE"
OWNER = "PWR_SweepCanopyFill"


def apply(spec_path, verify):
    spec = json.loads(spec_path.read_text())
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
    if not levels.load_level(WORLD):
        raise RuntimeError("Could not open the authored landscape")
    existing = {a.get_name(): a for a in actors.get_all_level_actors()
                if a.get_name().startswith(OWNER)}
    expected = {OWNER + str(i + 1) for i in range(len(spec["lights"]))}
    if set(existing) - expected:
        raise RuntimeError("Unexpected existing Southwest fill sources")
    readback = []
    for i, row in enumerate(spec["lights"]):
        name = OWNER + str(i + 1)
        actor = existing.get(name)
        position = ue.Vector(*row["position_cm"])
        if not actor and not verify:
            actor = actors.spawn_actor_from_class(ue.PointLight, position)
            if not actor:
                raise RuntimeError("Could not create " + name)
            actor.rename(name)
            actor.set_actor_label(name)
        if not actor or not isinstance(actor, ue.PointLight):
            raise RuntimeError("Missing native lighting actor " + name)
        comp = actor.get_component_by_class(ue.PointLightComponent)
        if not verify:
            actor.modify()
            comp.modify()
            comp.set_mobility(ue.ComponentMobility.MOVABLE)
            actor.set_actor_location(position, False, False)
            comp.set_editor_property("use_inverse_squared_falloff", False)
            comp.set_intensity_units(ue.LightUnits.UNITLESS)
            comp.set_light_falloff_exponent(row["exponent"])
            comp.set_attenuation_radius(row["radius_cm"])
            comp.set_light_color(ue.LinearColor(*row["color_linear"], 1.0), True)
            comp.set_intensity(row["intensity"])
            comp.set_cast_shadows(False)
            comp.set_specular_scale(0)
            comp.set_lighting_channels(True, True, False)
            comp.set_editor_property("affect_translucent_lighting", False)
            comp.set_editor_property("volumetric_scattering_intensity", 0)
        location = actor.get_actor_location()
        color = comp.get_light_color()
        channels = comp.get_editor_property("lighting_channels")
        actual = {"actor": name, "position_cm": [location.x, location.y, location.z],
                  "intensity": comp.get_editor_property("intensity"),
                  "radius_cm": comp.get_editor_property("attenuation_radius"),
                  "exponent": comp.get_editor_property("light_falloff_exponent"),
                  "color_linear": [color.r, color.g, color.b],
                  "shadows": comp.get_editor_property("cast_shadows"),
                  "specular": comp.get_editor_property("specular_scale"),
                  "inverse_squared": comp.get_editor_property("use_inverse_squared_falloff"),
                  "lighting_channels": [channels.channel0, channels.channel1, channels.channel2]}
        if (math.dist(actual["position_cm"], row["position_cm"]) > .15
            or any(abs(actual[k] - row[k]) > .01 for k in ("intensity", "radius_cm", "exponent"))
            or math.dist(actual["color_linear"], row["color_linear"]) > .012
            or actual["lighting_channels"] != [True, True, False]
            or actual["inverse_squared"] or actual["shadows"] or actual["specular"] != 0):
            raise RuntimeError("Native canopy fill differs from its measured settings: " + str(actual))
        readback.append(actual)
    if not verify and not levels.save_current_level():
        raise RuntimeError("Could not save canopy light")
    dest = spec_path.parent / ("editor-light-reloaded.json" if verify else "editor-light-applied.json")
    dest.write_text(json.dumps(readback, indent=2) + "\n")


if __name__ == "__main__":
    apply(Path(os.environ["PWR_SWEEP_LIGHT"]), os.environ.get("PWR_SWEEP_LIGHT_VERIFY") == "1")
