"""The ground and water a map actually ships, read from its baked Fluid Flux states.

A planting tool seats plants on the terrain heightfield it was given. Where the terrain was
reshaped later (PWR's north headwater: a hill carved into a lake) that heightfield is stale, and
plants seated on it hang in the air or stand in the lake. Each baked Flux domain carries the
terrain it was solved on (`ground`) and the water surface (`height`), so inside a domain this is
the truth: `Shipped(map folder).check(x, y, z)` says, per point (Unreal centimetres), whether the
given height is off the shipped ground and whether the point is under water.
"""
import json
from pathlib import Path

import numpy as np

from flux_wrap_safe import read


class Shipped:
    def __init__(self, root):
        self.domains = []
        root = Path(root)
        level = json.loads((root / "level.json").read_text())
        for dom in (level.get("flux") or {}).get("domains", []):
            path = root / "flux_state" / dom["id"] / "state.json"
            if dom.get("playback") != "baked" or not path.exists():
                continue
            state = json.loads(path.read_text())
            ground = read(root / state["ground"])[..., 0]
            height = read(root / state["height"])[..., 0]
            terrain = state["centre"][2] - ground                    # cm
            self.domains.append((state, terrain, height + state["capture"] - terrain))

    def check(self, x, y, z, tolerance=40.0, wet=15.0):
        """(off the shipped ground by more than `tolerance` cm, under more than `wet` cm of water)."""
        x, y, z = (np.asarray(v, float) for v in (x, y, z))
        stale = np.zeros(len(x), bool)
        under = np.zeros(len(x), bool)
        for state, terrain, depth in self.domains:
            res = state["res"]
            c = np.floor((x - state["centre"][0]) / state["cell"] + res[0] / 2).astype(int)
            r = np.floor((y - state["centre"][1]) / state["cell"] + res[1] / 2).astype(int)
            # The outer texels are rewritten dry (flux_wrap_safe): not evidence either way.
            ins = (c >= 3) & (c < res[0] - 3) & (r >= 3) & (r < res[1] - 3)
            stale[ins] |= np.abs(z[ins] - terrain[r[ins], c[ins]]) > tolerance
            under[ins] |= depth[r[ins], c[ins]] > wet
        return stale, under
