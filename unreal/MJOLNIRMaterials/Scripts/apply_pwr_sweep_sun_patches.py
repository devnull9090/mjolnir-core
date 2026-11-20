"""Place and independently reopen the selected bounded Southwest sunlight patches."""

import hashlib
import json
import math
import os
from pathlib import Path

import unreal as ue

WORLD = "/Game/Levels/Halo1/Solo/LPE/LPE"
PREFIX = "PWR_SweepSunPatch"


def location(v):
    return [v.x, v.y, v.z]


def rotation(r):
    return [r.pitch, r.yaw, r.roll]


def audit(actor, row):
    light = actor.get_component_by_class(ue.SpotLightComponent)
    col = light.get_light_color()
    ch = light.get_editor_property("lighting_channels")
    report = {
        "name": actor.get_name(),
        "location_cm": location(actor.get_actor_location()),
        "rotation_deg": rotation(actor.get_actor_rotation()),
        "color_linear": [col.r, col.g, col.b],
        "channels": [ch.channel0, ch.channel1, ch.channel2],
        "intensity_units": int(light.get_editor_property("intensity_units").value),
    }
    for key, prop in [
        ("intensity", "intensity"),
        ("radius_cm", "attenuation_radius"),
        ("inner_degrees", "inner_cone_angle"),
        ("outer_degrees", "outer_cone_angle"),
        ("falloff_exponent", "light_falloff_exponent"),
        ("specular_scale", "specular_scale"),
        ("source_radius_cm", "source_radius"),
        ("cast_shadows", "cast_shadows"),
        ("affect_translucent_lighting", "affect_translucent_lighting"),
        ("volumetric_scattering_intensity", "volumetric_scattering_intensity"),
        ("use_inverse_squared", "use_inverse_squared_falloff"),
    ]:
        report[key] = light.get_editor_property(prop)
    for key, actual in report.items():
        if key in (
            "name",
            "channels",
            "cast_shadows",
            "use_inverse_squared",
            "intensity_units",
        ):
            if actual != row[key]:
                raise RuntimeError(f"{row['name']} {key} readback {actual} differs")
        elif isinstance(actual, list):
            limit = 0.012 if key == "color_linear" else 0.12
            if math.dist(actual, row[key]) > limit:
                raise RuntimeError(f"{row['name']} {key} differs: {actual}")
        elif abs(actual - row[key]) > 0.05:
            raise RuntimeError(f"{row['name']} {key} differs: {actual}")
    return report


def apply():
    art = Path(os.environ["PWR_SWEEP_ART"]).resolve()
    verify = os.environ.get("PWR_SUN_PATCH_VERIFY") == "1"
    if (
        Path(ue.Paths.convert_relative_path_to_full(ue.Paths.project_dir())).resolve()
        != (art / "editor/Meteorite").resolve()
    ):
        raise ValueError("Different PWR editor project")
    src = art / "light/bend-sun-patches.json"
    spec = json.loads(src.read_text())
    rows = spec["spots"]
    if any(not r["name"].startswith(PREFIX) for r in rows) or len(
        {r["name"] for r in rows}
    ) != len(rows):
        raise ValueError("Invalid bounded light roster")
    levels = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
    actors = ue.get_editor_subsystem(ue.EditorActorSubsystem)
    if not levels.load_level(WORLD):
        raise RuntimeError("PWR road level failed to open")
    current = {
        a.get_name(): a
        for a in actors.get_all_level_actors()
        if a.get_name().startswith(PREFIX)
    }
    if set(current) - {r["name"] for r in rows}:
        raise ValueError("Unexpected bounded light actor in scene")
    result = []
    for row in rows:
        name = row["name"]
        actor = current.get(name)
        pos = ue.Vector(*row["location_cm"])
        pitch, yaw, roll = row["rotation_deg"]
        rot = ue.Rotator(pitch=pitch, yaw=yaw, roll=roll)
        if not verify and actor is None:
            actor = actors.spawn_actor_from_class(ue.SpotLight, pos, rot)
            if not actor:
                raise RuntimeError("Could not spawn " + name)
            actor.rename(name)
            actor.set_actor_label(name)
        if not actor or not isinstance(actor, ue.SpotLight):
            raise RuntimeError("Missing native spot " + name)
        light = actor.get_component_by_class(ue.SpotLightComponent)
        if not verify:
            actor.modify()
            light.modify()
            light.set_mobility(ue.ComponentMobility.MOVABLE)
            actor.set_actor_location_and_rotation(pos, rot, False, False)
            light.set_intensity_units(ue.LightUnits.UNITLESS)
            light.set_editor_property(
                "use_inverse_squared_falloff", row["use_inverse_squared"]
            )
            light.set_light_falloff_exponent(row["falloff_exponent"])
            light.set_attenuation_radius(row["radius_cm"])
            light.set_outer_cone_angle(row["outer_degrees"])
            light.set_inner_cone_angle(row["inner_degrees"])
            light.set_light_color(ue.LinearColor(*row["color_linear"], 1), True)
            light.set_intensity(row["intensity"])
            light.set_cast_shadows(row["cast_shadows"])
            light.set_specular_scale(row["specular_scale"])
            light.set_source_radius(row["source_radius_cm"])
            light.set_lighting_channels(*row["channels"])
            light.set_editor_property(
                "affect_translucent_lighting", row["affect_translucent_lighting"]
            )
            light.set_editor_property(
                "volumetric_scattering_intensity",
                row["volumetric_scattering_intensity"],
            )
        result.append(audit(actor, row))
    if not verify and not levels.save_current_level():
        raise RuntimeError("Could not save PWR bounded light pass")
    suffix = "reopened" if verify else "applied"
    (src.parent / f"editor-sun-patches-{suffix}.json").write_text(
        json.dumps(
            {
                "spec_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
                "spots": result,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    apply()
