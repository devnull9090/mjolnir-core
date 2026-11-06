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

## Sound spike

`sound/` built result 12 in `docs/ce_native_support.md`: a Wwise bank of our own, with events and tags that play it. Like the rest of this folder it is experiment code. The engine and horn have moved on to `tools/level/ce_vehicle_audio.py` and `wwise_bank.py`, which take nothing by hand: use those.

It reads from `$MJ_NATIVE_WORK/sound`, which you fill by hand: `x/` holds packages and banks extracted from the game, and `ce/` holds decoded CE sounds. `actor/w` under `MJ_NATIVE_WORK` holds the native actor container for the engine's third step. Build the tools with `cargo build --release` in `sound/tool`, and the repository's `mjolnir` and `ue-asset` examples in release.

| Script | Does |
|---|---|
| `gen_bank.py`, `gen_engine.py` | Write the horn and engine banks and the `.pak` that carries them |
| `hirc.py`, `wv.py` | Read and write bank records, and read CE sound data |
| `build_horn.py`, `build_engine.py` | Build every test container into `out/` |
| `tool/` | Clone shipped event, sound and actor packages under new names |
| `lua/` | Run through the game bridge: load, post, loop, stop, and read the engine values |
| `meter.ps1` | The game's output level, from Windows. The game must have focus. It reads 0 for a Blueprint's engine and horn, so listen instead |
