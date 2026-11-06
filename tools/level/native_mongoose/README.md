# Native Mongoose experiments

The drivers behind `docs/ce_native_support.md`: they built the Mongoose on its own
skeleton, tags and rider and read it back in game. They are one-vehicle experiment
scripts, not a finished tool. The rules they use live in `tools/level/ce_vehicle_*.py`.

Set `HCE_PAKS` to the game's Paks folder and `MJ_NATIVE_WORK` to a folder outside
the repository. Decoded map and tag data stays there: this repository takes no game
content.

| Script | Does |
|---|---|
| `ce_dump.py`, `ce_dump_rider.py` | Decode a CE map's vehicle and rider into JSON |
| `build_native.py` | Build skel, coll, phmo, jmad, hlmt and vehi for one vehicle |
| `mklevel_nmg.py`, `mk_rider_level.py` | The test level, with and without its own player rows |
| `read_refs.py` | Run in a match: which model references survived load |
| `rider_read.py`, `simnodes.py` | Run in a match: sim node matrices for rider and vehicle |
| `read_bones.lua` | Run through the game bridge: drawn bones against their bind pose |
