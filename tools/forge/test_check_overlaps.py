"""Collision and z-fighting regressions for the reference packs and maps."""
import copy
import json
import unittest

import numpy as np

import check_overlaps as check

REPO = check.REPO
MAPS = ["crossline/crossline", "blank/forge_canvas", "roadworks/roadworks_circuit"]


def level(*objects):
    return {"blam": {"objects": [{"tag": f"{check.PREFIX}{pack}\\{ident}",
                                  "pos": [x * 100, -y * 100, z * 100], "rot": [0, -yaw, 0]}
                                 for pack, ident, (x, y, z), yaw in objects]}}


class OverlapTests(unittest.TestCase):
    def test_a_lamp_inside_a_teleporter_housing_is_refused(self):
        # Crossline 0.3 placed each base's pylon on the housing's end.
        found = check.problems(level(("foundry", "light_pylon_red", (-20, -68, 4.5), 0),
                                     ("foundry-wide", "teleporter_housing", (-16, -68, 4.5), 0)))
        self.assertTrue(any(f["fault"] == "penetrates" for f in found))
        clear = check.problems(level(("foundry", "light_pylon_red", (-22.5, -68, 4.5), 0),
                                     ("foundry-wide", "teleporter_housing", (-16, -68, 4.5), 0)))
        self.assertEqual(clear, [])

    def test_touching_pieces_pass_and_shared_faces_fight(self):
        side_by_side = level(("foundry-wide", "floor_2x2", (0, 0, 0), 0),
                             ("foundry-wide", "floor_2x2", (8, 0, 0), 0))
        self.assertEqual(check.overlaps(side_by_side), [])
        # Two identical walls overlapping along their run share every face.
        overlapping = level(("foundry-wide", "wall_long", (0, 0, 0), 0),
                            ("foundry-wide", "wall_long", (15, 0, 0), 0))
        faults = {f["fault"] for f in check.overlaps(overlapping)}
        self.assertEqual(faults, {"penetrates", "coplanar"})
        self.assertTrue(any(f["fault"] == "coplanar" for f in check.problems(overlapping)))

    def test_a_closed_glass_box_against_its_frame_fights(self):
        sided = check.two_sided("foundry-wide")
        piece = copy.deepcopy(check.pieces("foundry-wide")["glass_wall"])
        glass = next(p for p in piece["visual"] if p["material"] == "glass")
        # The 0.12 m slab the pane used to be: its end faces meet the jambs.
        glass.update(next(h for h in piece["collision"]["hulls"]
                          if max(abs(v[1]) for v in h["vertices"]) < 0.1))
        shapes = check.parts(piece, {"origin": np.zeros(3), "yaw": 0}, sided)
        pane = next(s for s in shapes if s["material"] == "glass")
        self.assertTrue(any(check.coplanar(pane, s) for s in shapes if s is not pane))

    def test_reference_packs_have_no_fighting_parts(self):
        for pack in ("foundry", "foundry-wide", "roadworks"):
            self.assertEqual(check.pack_faults(pack), [], pack)

    def test_reference_maps_only_overlap_at_deliberate_joins(self):
        for name in MAPS:
            path = REPO / "forge-maps" / f"{name}.level.json"
            found = check.problems(json.loads(path.read_text(encoding="utf-8")))
            self.assertEqual([check.describe(f) for f in found], [], name)


if __name__ == "__main__":
    unittest.main()
