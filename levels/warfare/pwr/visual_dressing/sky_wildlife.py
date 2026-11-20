"""Compose PWR's campaign sky, flying wildlife and baked lake surface finish."""

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
B30_SKY = HERE / "b30-clear-afternoon.json"
GULL = "/Game/FX/Library/Environment/PNW/Creatures/Birds/Gull/NS_GullFlyCircle.NS_GullFlyCircle"
GEOMETRY = Path(__file__).resolve().parents[1] / "terrain/final-v5/terrain.geometry.json"


def apply(level):
    """Update the assembled level in place. Distances in the returned placements are UE cm."""
    if level.get("name", "").lower() != "pwr":
        raise ValueError("The campaign vista is authored for Pelican Warfare")

    # B30's original scenario references sky/clear afternoon/clear afternoon.
    # SM_PWR_Sky is the native conversion of that model. Preserve its off-centre
    # import pivot, seven ordered material sections, texture transforms and cloud scroll.
    dome = json.loads(B30_SKY.read_text(encoding="utf-8"))
    old_ids = {dome["id"], "pwr_halo_ring_vista"}
    level["decor"] = [item for item in level["decor"]
                      if item["id"] not in old_ids and item.get("mesh") != dome["mesh"]]
    level["decor"].append(dome)
    level["environment"].pop("clouds", None)

    # The broad lake is visible at grazing angles from the banks and almost
    # straight down from a Pelican. This look was checked from both views on
    # the Coastline material. Keep the upper river's whitewater settings.
    coast = next(domain for domain in level["flux"]["domains"] if domain["id"] == "lower_lake")
    coast["surface_vectors"].update({
        "SurfaceScattering0": [.12, .28, .37, .00345],
        "SurfaceScattering1": [.07, .181, .255, .00125],
        "SurfaceAbsorption0": [600, 1250, 1900, .65],
        "SurfaceAbsorption1": [440, 980, 1670, .8],
        "SurfaceScatteringShoreline": [.58, .77, .73, .0002],
    })
    coast["surface_scalars"].update({
        "DetailWaveHeight": 26, "DetailWaveLength": 735, "WaterRoughnessMin": .086,
    })

    # The two lake points were checked against the baked wet cells. Use the
    # actual lake plane and the measured upstream splash, so bird height
    # follows the same water as the player sees. Authoring +Y is UE -Y.
    geometry = json.loads(GEOMETRY.read_text(encoding="utf-8"))
    lake = next(lake for lake in geometry["lakes"] if lake["id"] == "southeast_lake")
    water_z = lake["water_z_m"] * 100
    upper_splash = next(
        effect["pos"] for fall in sorted(level["waterfalls"], key=lambda f: f["pos"][1])
        for effect in fall["effects"] if effect.get("pos")
    )
    flight_centers = [
        ("reservoir", [31100, 72400, water_z + 3100], 22),
        ("reeds", [61100, 68400, water_z + 1900], -51),
        ("rapids", [upper_splash[0], upper_splash[1], upper_splash[2] + 2500], 103),
    ]
    fx = level["effects"]
    owned = {f"pwr_gulls_{name}" for name, _, _ in flight_centers}
    fx["placed"] = [entry for entry in fx["placed"] if entry.get("id") not in owned]
    for name, position, yaw in flight_centers:
        fx["placed"].append({"id": f"pwr_gulls_{name}", "system": GULL, "pos": position, "rot": [0, yaw, 0]})
    return level
