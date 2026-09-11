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

## Materials

The donor arrives with one material slot, so a transplanted mesh renders in
default grey until something says otherwise. Two halves:

1. **Sections.** `mesh_rewrite --material Slot=/Game/Path/MI_X=pat1|pat2`
   groups the glTF's own materials into numbered slots — every primitive whose
   material name contains one of the patterns gets that slot's index in its
   render-data section — and prints the slot-to-material table. A pattern of
   `*` claims slot 0, the donor's own, so unmatched primitives get it too. For
   Blood Gulch:

   ```bash
   cargo run -p ue-asset --example mesh_rewrite -- "<paks>" basicshapes/cylinder        <staging>/bloodgulch/bsp/bsp_0.gltf out.uasset        --material Ground=/Game/Env/Bio/Ground/Soil/Ground_Soil_Pile_D/Materials/MI_Ground_Soil_Pile_D=blood_ground|cap_moss        --material Rock=/Game/Env/Bio/Rock/Canyon/Materials/MI_Rock_Canyon_Generic=cap_cliff|boulder        --material "Metal=/Game/Env/HS/FR/Gen/+Materials/MI_FR_Gen_Metal_Simple_01_Grey_MidDark=metal|cap_ramp|light|teleporter"
   ```

   which puts 2,449 triangles on Ground, 1,382 on Rock and 1,672 on Metal.

2. **Materials.** The level file's `decor` entry carries a `materials` list and
   `MJOLNIRLevelLoader` assigns them to the *component* at spawn
   ([level_format.md](level_format.md)). Only shipped materials can be named —
   nothing new is cooked, the mesh just points at what the game already has.

**The mesh's own slots do not survive the load.** `--asset-imports` writes the
materials into the package properly: `StaticMaterials` grows to four entries,
each a package import with the right `FPackageId` and public export hash, the
export's dependency bundle lists them, and `blam-pack --example
package_override` takes the imported package paths and writes a store entry so
the runtime can turn an import's index into a package id — without that store
entry the load faults with an access violation, because the shipped entry still
describes the shipped one-import list, and the asset's parallel array is what
the index counts against. All of that installs, and the package still comes up
in game reporting the donor's *one* slot with `DefaultMaterial` in it, the three
material packages never loaded. The bytes in the installed container decode as
four (`ue-asset --example props_diff`), so something at load or `PostLoad`
shortens it; unexplained. Hence the component route above, which works and is
what a level file wants anyway.

Two probes came out of this and are worth keeping:
`ue-asset --example store_entries` compares every package's store entry against
its own imported-package list (85,176 of 87,165 in `pakchunk0` agree byte for
byte, the rest only where an FName number makes the name-derived id differ),
and `ue-asset --example zen_header` dumps the header a rewrite has to
reproduce.

Materials are chosen for scale, not just for looks: at the 442x the terrain is
spawned with, a material that samples UV0 stretches badly, while the
world-projected `Env/Bio` rock and soil hold up. That is why the cliffs read
well and the base floors read as polished sheet.

## Original textures

Borrowed materials make Blood Gulch look like a Campaign Evolved level; the
classic look wants the classic bitmaps. Nothing new can be cooked, but a
shipped texture's pixels can be replaced in place (`mjolnir texture swap`,
[texture_swapping.md](texture_swapping.md)), so the route is:

1. **Hosts.** Pick shipped materials that nothing in the game places, whose
   textures are swappable (DXT1/DXT5 colour, BC5 normal) and that sample UV0
   plainly. `/Game/_Prototypes/SynchronizationTestContent/Assets` is full of
   them — the Pelican and Ghost placeholder vehicles, the ammo-box gear, the
   DMR and concussion-rifle instances — each a simple diffuse + normal
   material with its own textures. Nine of them cover Blood Gulch's cliff,
   ground, boulder, cap metal, flat metal, two panel variants, the unearthed
   panels and the ramps; the lights and teleporter share the cap metal.
2. **Pixels.** One `texture swap` call with `--pair` per extra texture puts
   the CE bitmap on each host's `_D` and a `flat-normal` on each `_N`, so the
   host's own bump map stops showing through. The CE bitmaps are 256–512
   px; upscale them to the host's size first — a noisy 512 stretched by the
   encoder's resampler fails the readback gate — and set their alpha to
   opaque, since CE stored specular masks there and the DXT5 hosts read
   alpha. Real-ESRGAN's portable build (`realesrgan-ncnn-vulkan -n
   realesrgan-x4plus -s 4`) does the upscale well: it invents plausible rock
   grain and plate edges where Lanczos only blurs, and the DXT readback error
   stays under 5/255. Run it on the RGB bitmaps, then fit to the host size.
3. **Sections and slots.** `mesh_rewrite --material` with one slot per CE
   shader group, keyed on the glTF material names, and the level file's
   `materials` list pointing at the host materials. `tools/level/
   gen_bloodgulch_level.py` carries the table.

Classic textures keep their tail mips (everything below 128x128) inline in
the export, which the swap refused until now; it rewrites the export body
too and packs the `.uasset` beside the `.ubulk`, both the same length as
shipped. The readback gate compares only the channels a format carries — a
BC5 normal map has two, and grading its missing blue channel is what made a
perfect flat normal read as an 85/255 error.

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
