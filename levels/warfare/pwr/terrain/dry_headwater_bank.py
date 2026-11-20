"""Remove the isolated capture-edge water behind the PWR spring from a staged copy."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

import numpy as np
from scipy import ndimage

from bake_headwater_flux import read, write, write_exr
from audit_flux_state import texture
from flux_heightfield import sha256, state_matches, verify_state_files
from heightfield import load_heightfield


def dry_bank(source, master, geometry, destination):
    if destination.exists():
        raise FileExistsError(f"Choose a new output directory: {destination}")
    flux = read(source / "flux.json")
    report = read(source / "receipt.json")
    field = load_heightfield(master)
    if report["inputs"]["terrain"] != sha256(master) or report["inputs"]["geometry"] != sha256(geometry):
        raise ValueError("Terrain differs from the published lake")
    upper = next(d for d in flux["domains"] if d["id"] == "upper_river")
    state = upper["state"]
    verify_state_files(source, state)
    old = {key: texture(source / state[key]) for key in ("height", "velocity", "ground")}
    step = state["cell"] / 100
    nx, ny = state["res"]
    east = state["centre"][0]/100 + (np.arange(nx) + .5 - nx/2)*step
    north = -state["centre"][1]/100 - (np.arange(ny) + .5 - ny/2)*step
    xx, yy = np.meshgrid(east, north)
    river = next(c for c in read(geometry)["watercourses"] if c["id"] == "headwater_spring")
    spring = np.asarray(river["surface_centreline_m"][0])
    neighbourhood = (np.abs(xx - spring[0]) <= 72) & (yy >= spring[1] - 37)
    row = np.abs(north-spring[1]).argmin()
    col = np.abs(east-spring[0]).argmin()
    depth = old["velocity"][..., 2]
    structure = np.ones((3,3), dtype=bool)
    labels, _ = ndimage.label(depth > 0, structure)
    main = labels[row,col]
    if not main:
        raise ValueError("Spring source is dry")
    fragment_ids = np.setdiff1d(np.unique(labels[neighbourhood]), [0,main])
    leftover = np.isin(labels, fragment_ids)
    if not leftover.any() or np.any(leftover & ~neighbourhood):
        raise ValueError("Stray water is absent or extends outside the examined hillside")
    # Keep the main river and its shoreline intact. Two dry texels around
    # each remnant keep filtering and half-float rounding below the grass.
    clean = ndimage.binary_dilation(leftover, structure, iterations=2)
    if np.any(clean & ndimage.binary_dilation(labels == main, structure, iterations=2)):
        raise ValueError("An isolated fragment is too close to the real spring")
    new_height = old["height"].copy()
    new_velocity = old["velocity"].copy()
    grade = np.minimum(field.sample(xx[clean],yy[clean]),
                       (state["centre"][2] - old["ground"][...,0][clean]) / 100)
    cleared_surface = (grade - .65)*100 - state["capture"]
    cleared_wet_history = (grade - .40)*100 - state["capture"]
    new_height[...,0][clean] = np.minimum(new_height[...,0][clean], cleared_surface)
    new_height[...,1][clean] = np.minimum(new_height[...,1][clean], cleared_wet_history)
    new_velocity[clean] = 0
    prior_files = {name: sha256(source/name) for name in report["files"]}
    if prior_files != report["files"]:
        raise ValueError("Input state failed its parent receipt")
    with tempfile.TemporaryDirectory(dir=destination.parent) as scratch:
        staged = Path(scratch)/"water"
        shutil.copytree(source/"flux_state", staged/"flux_state")
        for key, array in (("height",new_height), ("velocity",new_velocity)):
            write_exr(staged/state[key], array)
            state[key+"_sha256"] = sha256(staged/state[key])
        upper["provenance"]["headwater_bank_cleanup_sha256"] = sha256(Path(__file__))
        state["provenance"] = upper["provenance"].copy()
        write(staged/"flux_state/upper_river/state.json", state)
        write(staged/"flux.json", flux)
        for entry in flux["domains"]:
            verify_state_files(staged, entry["state"])
            if not state_matches(entry["state"],entry):
                raise ValueError("State/domain mismatch")
        checked_height = texture(staged/state["height"])
        checked_velocity = texture(staged/state["velocity"])
        if (not np.array_equal(checked_height[~clean],old["height"][~clean])
                or not np.array_equal(checked_velocity[~clean],old["velocity"][~clean])):
            raise ValueError("Screened-off native texel changed")
        wet, _ = ndimage.label(checked_velocity[...,2] > 0, structure)
        if not wet[row,col] or set(np.unique(wet[neighbourhood])) != {0, wet[row,col]}:
            raise ValueError("Detached water remains or spring was removed")
        gap = grade - (checked_height[...,0][clean] + state["capture"]) / 100
        if gap.min() < .60 or np.any(checked_velocity[clean]):
            raise ValueError("Cleaned crest can still render above grass")
        # Screenshot ray/terrain intersection through the primary sliver.
        r, c = np.abs(north-997.02).argmin(), np.abs(east+416.39).argmin()
        if depth[r,c] < 4 or checked_velocity[r,c,2] != 0:
            raise ValueError("The screenshot landmark was not dried")
        report["files"] = {name: sha256(staged/name) for name in prior_files}
        diffs = {name for name in prior_files if prior_files[name] != report["files"][name]}
        if diffs != {"flux_state/upper_river/"+n for n in ("height.exr","velocity.exr","state.json")}:
            raise ValueError(f"Unexpected changes: {diffs}")
        report["bank_cleanup"] = {
            "parent_release": "0.1.0-playtest.32", "parent_flux_sha256": sha256(source/"flux.json"),
            "input_receipt_sha256": sha256(source/"receipt.json"), "script_sha256": sha256(Path(__file__)),
            "screenshot_landmark": {"native_basin_pixel":[993,183], "projected_xy_m":[-416.39,997.02],
                "pixel_xy":[int(c),int(r)], "texel_centre_xy_m":[east[c],north[r]],
                "parent_depth_cm":depth[r,c], "new_depth_cm":checked_velocity[r,c,2],
                "height_wet_rg":checked_height[r,c,:2].tolist(), "ground_r":old["ground"][r,c,0]},
            "search_bounds_m":[spring[0]-72,spring[1]-37,spring[0]+72,north[0]],
            "orphan_component_pixels":[int(np.sum(labels == i)) for i in fragment_ids],
            "measurably_wet_pixels_removed":int(np.sum(leftover & (depth>.7))),
            "cleared_pixels_including_dry_margin":int(clean.sum()),
            "outside_mask_texels_verified_per_upper_texture":int((~clean).sum()),
            "minimum_surface_below_grade_m":float(gap.min()),
            "remaining_wet_components_in_search_area":1,"unchanged_upper_ground_and_lower_tile":True,
            "changed_files":sorted(diffs),
        }
        # The launcher's ready signal is receipt.json. Publish its directory
        # only after every texture and the final receipt have verified.
        write(staged/"receipt.json", report)
        staged.rename(destination)
    print(json.dumps(report["bank_cleanup"], indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "master", "geometry", "destination"):
        parser.add_argument("--"+name, type=Path, required=True)
    dry_bank(**{k:v.resolve() for k,v in vars(parser.parse_args()).items()})
