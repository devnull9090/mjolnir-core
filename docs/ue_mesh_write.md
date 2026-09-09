# Writing mesh geometry in the game's own serialisation (2026-09-08)

Blood Gulch renders in Halo: Campaign Evolved. This is how, and why the
obvious route does not work.

## Why not just cook the mesh

Content cooked by stock UE 5.5 does not load in this build. Two independent
failures, both read off the game's own crash reports in
`%LOCALAPPDATA%\Meteorite\Saved\Crashes\*\CrashContext.runtime-xml`:

* a cooked **actor** dies with `ObjectSerializationError ... StaticMeshComponent
  ...: Bad export index 201463809/7` — a shipped `/Engine/BasicShapes/Cube`
  fails the same way, so it is the component, not the asset;
* a cooked **`UStaticMesh`** dies on its own with
  `LowLevelFatalError [ContainerHelpers.cpp:8] Trying to resize TArray to an
  invalid size of 2147483650` (`0x80000002`, a garbage element count).

The second was isolated with no actor at all, by adding the mesh's
`FPackageId` to the world's package-store import list with
`ue-iostore --example relink_container`. The game is
`5.5.4-1121610+++Meteorite+Rel-i343-Meteorite-2607-CU4`; stock UE writes this
class differently.

## What works: rewrite a shipped mesh in place

Nothing new is authored. A shipped mesh package is taken exactly as the game
ships it and only the bytes of its `FStaticMeshRenderData` LOD array are
replaced (`ue-asset::mesh_write`). The property block, the native tail and the
Nanite/bounds tail all survive untouched, so the package still deserialises the
way its own engine wrote it. Same trick as the texture swap.

Constraints the donor has to meet:

* **No Nanite pages.** The engine renders the Nanite representation when there
  is one and ignores the classic LOD this writes. `mesh_probe` reports which
  meshes have them; of the engine basic shapes, only `Sphere` does.
* **An inlined LOD**, not one streamed to `.ubulk`.
* **Geometry inside the donor's bounds.** The bounds live in the preserved
  tail and the engine culls against them, so the writer normalises into the
  donor's box and prints the component scale that undoes it.
* **Sections may only name material slots the donor has**, because the slots
  are properties and are not rewritten.

`/Engine/BasicShapes/Cube` is the reference donor: 54 vertices, one material,
one inlined LOD, no Nanite, and it ships.

## The pipeline

```bash
# 1. geometry in, package out; --selftest rewrites the donor with its own
#    geometry first, so a failure says which half is wrong
cargo run -p ue-asset --example mesh_rewrite -- \
    "<paks>" basicshapes/cube staging/bloodgulch/bsp/bsp_0.gltf out.uasset --selftest

# 2. put it in front of the game
cargo run -p blam-pack --example package_override -- \
    "<paks>" basicshapes/cube out.uasset <out dir>
```

The gate at every step is that `ue_asset::mesh::parse_static_mesh` — verified
against the game's own cooked meshes — reads back exactly what was written:
the export, and then the rebuilt package. For Blood Gulch that is 5,762
vertices, 16,509 indices and 42 sections, unchanged through both.

## Axes

halo2ue writes Halo `(x, -y, z)` as glTF `(x, z, y)` in metres, so a vertex is
at `(gx, gz, gy) * 100` centimetres plus the offset the collision transplant
uses, `(-10789.9, -46076.6, 13411.2)`. That reproduces the decor position the
level file already carried, and puts the terrain's world box at
x `[-8990, 29414]`, y `[-32343, 11902]`, z `[13305, 21407]` cm.

## Spawning it

The actor is spawned at runtime, never cooked. The loader's proven order
matters: set `Mobility = Movable` **before** `SetStaticMesh`, because
`StaticMeshActor` ships Static and the setter silently refuses on a registered
static component. `StaticFindObject` returns a non-null garbage pointer for a
path that does not exist, so always confirm with `GetFullName`.

For Blood Gulch: location `(10212.1, -10220.6, 17356.0)` cm, uniform scale
`442.4551`.

## The catch

Overriding `/Engine/BasicShapes/Cube` replaces **every** cube in the game, so
the level loader's own placeholder decor becomes Blood Gulch too. That is fine
for a demo and wrong for a shipping map; a dedicated donor package, or a
`/Game` mesh nothing else places, is the fix. Removing the override is
deleting the three `pakchunk989-MJOLNIRMESH-Windows_P.*` files.
