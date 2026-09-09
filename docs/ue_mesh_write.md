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

**`/Engine/BasicShapes/Cylinder` is the donor to use.** It has no Nanite, one
inlined LOD, one material, a `(50, 50, 50)` box with a `70.71` sphere, and
nothing references it: the shipped B40 world imports no engine basic shape at
all, and the level loader places only `Cube` and `Sphere` (plus
`BasicShapeMaterial` for tinting). `Cone` is an equivalent second choice.
`Plane` is not usable — its box is flat, so there is nothing to normalise
into.

Do **not** use `Cube`. It works, but the level loader's own placeholder decor
is made of cubes, so overriding it turns every one of them into the terrain.

The engine culls against the donor's box *and* its sphere, so both have to
hold. Blood Gulch normalises to a bounding sphere of `62.0` inside
Cylinder's `70.71`, which the tool reports so the fit can be checked before
anything is packed.

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

## A brand-new package does not work (yet)

The tidier answer would be a package of our own rather than shadowing a
shipped one, and all the machinery for it exists and produces something
verifiably correct:

```bash
cargo run -p ue-asset --example mesh_rewrite -- ... --rename /Game/MJOLNIR/Meshes/SM_Bloodgulch
cargo run -p blam-pack --example package_add --     "<paks>" /Game/MJOLNIR/Meshes/SM_Bloodgulch SM_Bloodgulch.uasset <out>     /Engine/EngineMaterials/WorldGridMaterial
```

`mesh_rewrite --rename` renames the package and its mesh export and
recomputes the export's public hash, keeping `CookedHeaderSize` a constant
distance from the real header size; `package_add` registers the new
`FPackageId` and its imports in a `ContainerHeader`. The container installs,
the game mounts it, and our own reader parses the package back out of the
installed container as 5,762 vertices with no Nanite.

**The game will not resolve the name.** `StaticFindObject` finds nothing and
`LoadAsset` returns an invalid object for
`/Game/MJOLNIR/Meshes/SM_Bloodgulch.SM_Bloodgulch`, while
`/Engine/BasicShapes/Cylinder.Cylinder` resolves in the same breath. Adding
the new id to the B40 world's store-entry import list with
`relink_container` does not help either: the level still loads, and the
package still is not there.

So a brand-new **Blam tag** package registers and loads (that is how PG1
works), but a brand-new **Unreal asset** package does not, at least by name.
Until that is understood, ship geometry by overriding a shipped mesh nothing
places. Removing the override is deleting the three
`pakchunk989-MJOLNIRMESH-Windows_P.*` files.
