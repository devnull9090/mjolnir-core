# Original Forge canvas collision

`crates/blam-sbsp/examples/forge_canvas.rs` builds an original rectangular slab
and an open build volume. It does not use Blood Gulch or another converted
map's geometry. The local shipped `BSP_03_1_Chasm_old` tag supplies the engine's
structure and physics wrappers; extracted and generated game data stays in
ignored build folders.

```powershell
cargo run -p blam-sbsp --example forge_canvas -- `
  forge-packs/foundry/build/donors/Levels/Halo1/Solo/B40/_Generated_/BSP_03_1_Chasm_old.scenario_structure_bsp `
  forge-packs/foundry/build/canvas/blank.sbsp

cargo run -p blam-sbsp --example forge_canvas -- `
  forge-packs/foundry/build/donors/Levels/Halo1/Solo/B40/_Generated_/BSP_03_1_Chasm_old.scenario_structure_bsp `
  forge-packs/foundry/build/canvas/arena.sbsp --width-m 24 --depth-m 40
```

The output directory must exist. Options, all in metres:

| Option | Default | Meaning |
|---|---:|---|
| `--width-m` | 64 | Slab width on X, centred at zero |
| `--depth-m` | 64 | Slab depth on Y, centred at zero |
| `--thickness-m` | 1 | Slab extends from `-thickness` to Z=0 |
| `--extent-m` | 64 | Playable X/Y range is `-extent` to `+extent` |
| `--below-m` | 8 | Playable volume extends to `-below` on Z |
| `--height-m` | 64 | Playable volume extends to `+height` on Z |

The output uses Blam world units (metres divided by 3.048) and BSP index zero.
The sibling `<output>.canvas.json` records the exact bounds for the scenario
and centimetre dimensions for a matching visible slab. World bounds, cluster
bounds and every supernode AABB cover the build volume, independently of the
floor's vertex bounds. Two unreferenced vertices at the volume's minimum and
maximum extend only the world shell's query bounds; they have no edges or
surfaces and are added after building the actual floor's Havok collision.
The floor definition stays compact. The volume has no ceiling or boundary
walls.

This is required for selection above a flat floor: the engine rebuilds its
global ray-query box from all shell vertices, unions instance bounds and
adds 0.1 world units (CU4 `0x2c1aa1..0x2c1e20`). It does not use the authored
world bounds for that initial rejection. Without the extra vertices, a ray
above Z=0.1 was rejected before dynamic objects were tested, although a direct
ray against the same Forge block hit. The regression preserves every
collision table except the two added vertices and checks that elevated space
remains open.

Bot navigation is not provided by these maps. The shell's two extra vertices
also prevent the current `pathfinding::copy_drops` matcher (which requires
equal vertex counts) from recognizing the compact floor instance, so the bake
does not apply its usual 0.001-wu copy lowering. Future navigation support
must account for unreferenced bounds vertices when matching collision copies.

For a standalone B40-based level, use `active_bsps: [8]`, `single_bsp: 8`, the
reported bounds at scenario BSP index 8, `--bsp 8=<output>`, and the bare
`defs/level/empty_world.umap`. The bake renumbers the scenario to the BSP's
index zero. Supply original rendering, valid multiplayer spawn scenery,
lighting, and a kill floor separately. Decorative meshes do not supply Blam
collision. Forge pack palettes require `blam.map_variant: true`, the pack
references, and the pack containers available during the bake.

Each build checks the source collision and both emitted collision trees with
13,068 floor, edge and elevated-space probes, then verifies the emitted volume
bounds. It fails before writing if geometry or bounds disagree. Pure tests
cover square and rectangular slabs, packed collision, and invalid dimensions:

```powershell
cargo test -p blam-sbsp --example forge_canvas
```

These are offline checks; traversal and object placement still need a game
test of the final standalone map.
