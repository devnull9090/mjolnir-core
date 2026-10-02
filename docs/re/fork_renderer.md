# The fork's renderer contract

**Status:** 2026-09-30. Halo: Campaign Evolved runs on 343's fork of UE 5.5.4.
Materials cooked in a stock UE 5.5.4 editor (`unreal/MJOLNIRMaterials`) load in the game
through our chunk 988 container. They bind and shade correctly only when the
editor reproduces the places where the fork's renderer differs from stock.
This page lists those places, how each was found, and what reproduces it.

Shaders are compiled offline and only run in the game, so every difference
between the two engines that ends up inside a compiled shader has to be
recreated before the cook compiles anything. The `MjolnirForkLayouts` plugin
in `unreal/MJOLNIRMaterials/Plugins` does this. It has two modules.

## 1. Uniform buffer layouts (`MjolnirForkLayouts`, PostEngineInit)

24 global uniform buffers carry members stock does not. Among them:
- View/InstancedView: first-person members.
- Primitive: `InstanceVSMInvalidationDisableDistance`.
- Scene: Nanite ownership visibility, view data.
- SceneTextures: `PrevFrameSceneColor`.
- ForwardLightData: the MegaLights restructure.
- DeferredLight and LumenCardPass.

Several nested structs differ too.

A shader records each uniform buffer it reads by layout hash, and the RHI
binds a static buffer by looking that hash up
(`RHICore::InitStaticUniformBufferSlots`). With stock layouts the hash is not
found and the buffer is left unbound, and the renderer crashed on the first
draw.

`tools/ue/ub_dump.py` reads every `FShaderParametersMetadata` out of the
running game into `unreal/MJOLNIRMaterials/Config/ForkUniformBuffers.json`. The module
rewrites the editor's definitions to match and checks all 145 global hashes
against the game's. Renamed or removed members keep compiling: a `#define`
covers each rename, and a same-length `static` covers each removed scalar.

Also required: `r.CompileShadersForDevelopment=0`. With it on (the PC
default), every pixel shader lerps its emissive towards a `SelectionColor`
parameter. The game feeds that parameter, so the output came out black.

## 2. GPU-scene primitive layout (`MjolnirForkShaders`, PostConfigInit)

Vertex factories read each primitive's transform, bounds and custom data from
GPUScene's primitive buffer, at `PrimitiveId * PRIMITIVE_SCENE_DATA_STRIDE`
float4s plus a fixed element index (`Shared/SceneDefinitions.h`,
`Private/SceneData.ush`). The fork stores **44** float4s per primitive where
stock stores 43:

- **Stride:** every game shader that indexes the buffer multiplies by 44
  (stock: 43).
- **Elements up to 32 are unchanged.** Across ~4,000 base-pass shaders from
  pakchunk130/230/520 and the global compute shaders, the fork reads them at
  stock indices: 4, 17–19 and 26–27 in materials; 18–21 and 28–29 in
  `GPUSceneDebugRenderCS`; the Nanite hierarchy offset at 25; the packed
  Nanite flags at 30.
- **Custom primitive data starts at 35.** Game shaders read 35, 36, 38, 39 and
  42 and never 34. So the extra float4 sits just ahead of the custom data, and
  the custom data occupies 35–43.

With the stock stride, our probes rendered fully shaded but at another
primitive's place and size: they turned up below the map. Where they belonged,
only a black depth-prepass silhouette showed.

The module maps the virtual directories `/Engine/Shared` and `/Engine/Private`
to copies under `Intermediate/MjolnirForkShaders`. Those copies are
regenerated from the installed engine at every start, with two edits:

- the stride, 43 → 44;
- the custom data base, 34 → 35.

The most specific mapping wins, so the override applies to this project only.
The engine install, and every other project on the machine, keeps stock
shaders. Each edit has to match its stock text exactly once; if it doesn't,
the module logs an error and leaves the shaders stock.

The editor's own GPUScene still uploads 43-float4 primitives. The project is
for cooking, not for rendering in the editor; `-MjolnirStockShaders` turns the
override off.

## 3. Material instances are not shipped

A `MaterialInstanceConstant` cooked here crashes the game while it loads the
package. The crash is on the async loading thread, reading address
`0x0000000500000047`, inside `UMaterialInstance` serialization:
`MaterialInstanceCachedData`, then `MaterialCachedExpressionData`
(`HaloCampaignEvolved.exe` +0x627faa0 and +0x6293d90, both named by the
struct-name strings they reference).

Cooked packages store properties unversioned, in the order the writer's
classes declare them. The fork's versions of these structs therefore don't
match stock, and the editor cannot be given the fork's C++ reflection without
rebuilding the engine. By contrast, materials (`UMaterial`) and textures
cooked here load and render.

So the cook ships only the master materials and the textures. The level
loader creates a dynamic instance of a master per mesh slot, with the textures
(as object paths) and the scalar and vector parameters the level file lists.
The same reasoning dropped a `MaterialParameterCollection` for live exposure
tuning: `Exposure` is a scalar parameter on every instance instead.

## 4. What happens to a colour after the material

The probe was an unlit `M_CE_Environment` cube with a 50% grey base map,
read off the screen. That grey should reach the screen as 128/255.

| Pipeline | Grey (128 expected) |
|---|---|
| The game's defaults | 82 |
| No filmic curve (`ToneCurveAmount 0`) | 92 |
| Plus local exposure off | 80, and it moved with the sky's brightness |
| Plus manual exposure (`AutoExposureMethod` manual, bias 0, no physical camera exposure) | 77, steady |

With all of that neutralised, the response was a clean function. Linear in
→ sRGB out: 0.05 → 36, 0.214 → 77, 0.5 → 111, 1.0 → 152, 3.0 → 248.

That is the shown sRGB colour multiplied by about 0.6. It is the game's own
colour correction for its brightness setting
(`HaloGlobalGameUserSettings.ini` `ColorCorrectionBrightness=0.5`, the
default). An exposure bias does not move the result, so `EyeAdaptationInverse`
in the material does cancel the camera exposure.

How converted levels deal with it:

- **The level's post-process volume** (MJOLNIRLevelLoader `environment.post`)
  turns off the filmic curve, gamut expansion, blue correction and local
  exposure, and fixes the exposure.
- **The CE masters** divide by `DisplayGain` (0.6) before decoding to linear.

With both, a CE colour reaches the screen as CE drew it: 126 against 128. The
player's brightness slider still applies on top.

## 5. A rewritten mesh is drawn only in its donor slot's passes

A rewritten mesh keeps its donor's material slots (one, for the basic
shapes). Its other sections get their materials as component overrides. That
draws them, but Unreal works out which passes the mesh joins (opaque,
translucency) from the mesh's own slots.

With an opaque material in slot 0, every translucent section was silently
skipped: the sky, lights and teleporter fields. The same translucent material
drew on a stock cube.

So the transparent sections are a second mesh (over `/Engine/BasicShapes/Cone`)
whose slot 0 is one of them (`tools/level/build_terrain_meshes.py`).

## Finding the next difference

1. Extract shaders from both sides:
   `cargo run --release -p ue-iostore --example shader_extract -- <paks> <container> <out> <frequency> <max>`.
   Then disassemble them with the Windows SDK's `dxc -dumpbin`.
2. Every D3D12 shader blob starts with its `FShaderResourceTable`, whose
   `ResourceTableLayoutHashes` lists the uniform buffers it binds. Compare
   them against the hashes in `ForkUniformBuffers.json`.
3. Constant offsets in the DXIL show which fields a shader reads: a
   `cbufferLoadLegacy` register for a uniform buffer member, an `add` to the
   `mul … stride` result for a GPUScene element.
