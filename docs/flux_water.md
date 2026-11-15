# Terrain-backed Fluid Flux

The new opt-in path is `flux.schema = "mjolnir-flux-v2"` with `domains`.
Existing single-domain/coast maps retain their previous loader behavior.
Authoring uses `playback: "simulate"`; release assembly requires
`playback: "baked"` and a matching saved state. Baked playback spawns a native
surface (River by default), imports the state textures, and calls the installed
`SetSimulationState(State)` function. No simulation domain or source modifiers
are created by that path.

Cooked Blueprint inspection matters here: `SetSimulationState` assigns the state
and invokes `InitializeStates`. This game's `StopSimulation` talks only to its
editor helper, so calling it is not evidence of stopped runtime simulation.
The author documents direct surface playback from a saved state, and recommends
bounded simulation resolution and capture-only slopes for difficult cascades:
[Fluid Flux documentation](https://imaginaryblend.com/2025/01/10/fluid-flux-documentation/).

## Inputs and capture geometry

Upgrade config `flux.heightfield` names the decoded runtime master, with
`surface_interpolation: "triangle_nw_se"`; `flux.water_geometry` names the 3D
water/profile geometry. Each entry in `flux.domains` contains `id`, `domain`,
`sources`, and optionally `playback`, `prime_ms`, `surface`, `color_preset`, and
`surface_vectors`, `surface_scalars`, and native `simulation` foam parameters.
Domain positions, cell size and height use Unreal centimetres;
the master uses authoring metres with Y reflected into Unreal.

`tools/level/flux_heightfield.py` retains original grid vertices and the same
diagonal as Landscape, without resampling. It writes a double-sided,
capture-only mesh plus a receipt. Domain rectangles outside actual terrain
coverage fail rather than inventing a floor. The helper rejects resolutions
above 1024 or non-power-of-two dimensions and capture height above 32,000 cm.
This is a capture mesh, not an additional Blam collision mesh.

The current fork's Flux capture does not reliably capture Landscape. The older
CE-based `flux_bed` path therefore cannot be reused for PWR's buried coarse core.
The new bed is built from actual rendered terrain. Bridges, foliage and other
overhead decor are excluded from capture; the capture bed is hidden afterward.
The new path sets the native SceneCapture to `UseShowOnlyList` and populates
`ShowOnlyActorComponents` from the explicit bed IDs. A tag exclusion list is
insufficient: streamed terrain can exist outside the loader's actor dictionary.
This was caught by comparing every captured pixel with the final field while
authoring v5 water inside the older v3 visual world. Before the allowlist, old
mountains entered capture; afterward every pixel matched within the exported
half-float depth precision. Do not replace this with a broader scene capture.

## Bake validity and playback

Five SHA-256 values bind a bake to its terrain manifest, decoded terrain data,
3D water geometry, capture mesh, and domain/source/simulation settings. The settings
hash also binds the explicit-bed capture policy. Domain geometry and
canvas origin must match as well. Assembly validates EXR headers/dimensions and
seals the texture hashes. A new terrain with unchanged domain bounds still
invalidates the old bake. All named states live under `flux_state/<id>/` and
contain `state.json`, `height.exr`, `velocity.exr`, and `ground.exr`.
Ground is required by the native surface material, even without a solver.
UE5.5's Kismet exporter writes EXR only for RGBA16F targets, so the height and
ground maps are copied through RGBA16F before export. The source capture mesh
retains exact terrain vertices; the exported depth has half-float quantization.
All-baked assembly omits the capture bed actor entirely. Its mesh and receipt
remain offline inputs for provenance validation; they are not runtime surfaces.

Authoring commands are `mjolnir_flux_status` and
`mjolnir_flux_bake <id|all>`. Baking records current GPU state; removal of primers
does **not** certify settled or visually correct flow. Review shoreline depth,
cascade continuity and bridge clearance first, then export, assemble with
`playback: "baked"`, reload and confirm `simulation_domain:false`.
Release packaging rejects authoring modes or any missing named state.

Fluid Flux remains presentation here. Native player and vehicle support stays
with the Blam bed, ford and bridge collision. This change does not implement
swimming, drowning, buoyancy, or replicated fluid forces.

## Temporary proof and tests

`levels/warfare/pwr/terrain/prepare_flux_probe.py --heightfield <runtime-master>
--geometry <terrain.geometry.json> --out <proof-directory> --package` builds an
isolated 512 m upper-cascade capture tile. It does not install or call the game.
`tools/level/flux_probe_install.py install|restore --proof <proof-directory>`
requires a closed game, snapshots exact installed metadata/helper hashes, and
touches only narrow loader hooks plus temporary chunk 962. No DLL or main map
container is replaced. `tools/level/flux_probe_readback.lua` reads actual surface,
solver and capture-bed transforms through the existing bridge.

Offline checks:

```powershell
lua tools/tests/test_flux_runtime.lua
python -m unittest discover -s tools/level -p test_flux_heightfield.py
python -m unittest discover -s tools/level -p test_upgrade_ce_map.py
python -m unittest discover -s tools/level -p test_pack_local_map.py
```

Tests cover exact source vertices/diagonal, stale terrain/water/settings,
modified capture/EXR files, missing bakes, two independent baked surfaces with
zero solver/modifier allocation, invalid paths, failure cleanup and stale
callbacks and the explicit capture-component allowlist.

The temporary v3 upper-cascade proof completed three-texture saved-state reload:
zero domains, zero source modifiers, one native river surface. Its source-bed
vertex error was zero; exported capture depth differed by at most 0.1625 m.
`out/pwr/flux-proof-v3/final-baked-cascade.png` and the later screenshot show
the same saved surface. The original installed helper/metadata and camera poses
were restored by hash, and the temporary container removed with the game closed.
That proof is not relabelled as a v5 state.

## PWR final-source domains

`levels/warfare/pwr/terrain/plan_flux.py` derives capture planes from the accepted
runtime grid and writes the isolated capture package, authoring spec, release
config fragment, and receipt. It does not install or call the game.

```powershell
python levels/warfare/pwr/terrain/plan_flux.py `
  --heightfield levels/warfare/pwr/terrain/runtime-v5/runtime-master.json `
  --geometry levels/warfare/pwr/terrain/final-v5/terrain.geometry.json `
  --out out/pwr/flux-v5 --package
```

The accepted manifest is `cfa587ac8c9bc565270c035ee3a281b8611c8197fb7c6c0833990b1b6c4ee45f`.
Two 1024² domains use 0.9765625 m cells. The upper rectangle covers authored
X[-732,268], Y[0,1000] m; the lower covers X[-232,768], Y[-1000,0] m.
The upper capture plane/range is 295/282 m; the lower is 130/116 m. Both keep
the capture reference below the minimum bed and the camera above the maximum.
The grids align at Y=0, with a shared authored head of 92.22669 m. Native Adjust
controls hold that head and the 55 m lake during authoring. They are removed
with the solver for saved-state playback. This does not imply automatic fluid
transfer between domains.

Lake controls stay 90 m from elevated river mouths: a broad modifier holding
55 m across a higher channel drains it and creates a dry gap. Primers are removed
after 60 seconds; steady inlet/seam/lake controls remain only for baking. Native
foam generation is restrained so calm reaches stay teal and cascades retain
localized highlights. Free flow alone settled roughly 1.5–1.7 m below the
authored profile in the initial proof; authored targets are not measurements.
Narrow inlet controls additionally require their entire footprint plus margin
to stay below the lake level. They fill the reservoir closer to incoming falls
without draining the elevated channel above them.

`tools/level/audit_flux_state.py` reads the exported textures and reports all-pixel
capture error, centreline wetness, lake level and seam differences. It requires
NumPy and OpenEXR (`tools/level/requirements-flux.txt`).

The final v5-source bake and a fresh-process playback proof completed on
2026-11-09. Evidence is under `out/pwr/flux-v5/`:

- `final/flux_state/` contains the two sealed states, with six EXRs.
  `final/receipt.json` hashes every file; `final/flux.spec.json` embeds matching
  provenance. The states were copied to the final upgrade work folder.
- `final.audit.json` measures all 2,097,152 captured pixels. Maximum absolute
  error is 0.16292 m in the upper tile and 0.08 m in the lower tile, from the
  half-float exported depth. The capture mesh retains the exact runtime grid
  (floating-point comparison error about 1e-12 m).
- All 1,245 main-river/braid centreline samples are wet. The adjacent seam edges
  differ by 0.035 m, with no dry seam samples. The calm reservoir's 201,820
  measured pixels are within -0.07/+0.01 m of 55 m. Turbulent inlet pockets are
  reported separately: the whole lake footprint ranges -2.055/+0.22 m from 55 m.
  The simulated flowing reaches also settle below the design profiles; the lower
  final cascade has a local maximum profile difference of 6.61 m. These are fluid
  results, not terrain/collision errors or a claim of flat water everywhere.
- `clean-start.readback.txt` and `clean-start-later.readback.txt` observe the PWR
  world in a new game process: **two native river surfaces, zero simulation
  domains, zero modifier sources, zero capture-bed actors**. All six input maps
  are `Texture2D`, not render targets. The temporary capture container was
  physically removed before that launch. `clean-start-cascade.png`,
  `clean-start-lake.png`, `clean-start-mouth.png`, and `clean-start-seam.png`
  show the saved-state water inside the older installed visual world.
- `cleanup.json` verifies the original installed helper/metadata hashes and
  camera poses were restored, generated proof states removed, game closed, and
  temporary container absent. No DLL or main map container was replaced.

`tools/level/collect_flux_bake.py` seals completed native exports into a fresh
output directory and produces the baked spec without changing installed files.
The final assembled v5 world's appearance, remote behavior and performance
remain separate acceptance gates. Fluid Flux forces still do not drive Blam
players or vehicles.

## Optional baked lake waves

A baked domain can opt into the shipped Coastline material and a native
`BP_FluxOceanWave` actor. This is presentation over the existing saved state:
it does not change its bounds, source controls, provenance, or six EXR files.
Merge `out/pwr/flux-v5/lower-lake-wave.fragment.json` into the existing
`lower_lake` entry; it is a partial fragment, not a replacement domain.

```json
{
  "surface": "/Game/FluidFlux/Surface/Templates/Coastline/BP_FluxSurface_Coastline.BP_FluxSurface_Coastline_C",
  "ocean_wave": {
    "height_cm": 18,
    "length_cm": 1800,
    "choppiness": 0,
    "offset_cm": 0,
    "water_height_cm": 5500
  }
}
```

The hook requires baked playback and that exact Coastline class. All five
numbers are mandatory and finite; unknown keys fail before any actor or delayed
callback is created. Height is bounded to 0.01–50 cm, wavelength to 100–10,000 cm,
choppiness to 0–1, and vertical offset to ±50 cm. The water plane plus offset
must stay inside the domain's captured vertical range. Its XY follows the
domain centre; the canvas origin is added once to XYZ. World position must stay
inside the native Flux coordinate radius.

Before native construction finishes, the wave receives `UseRenderTarget=false`
and the explicit parameters. Coastline receives `SurfaceMeshMode=5`, the baked
state and `OceanWaveActor` before its construction finishes. The installed
volume texture animates in the native material; the wave actor does not tick or
create its own render target. Coastline's additional detail displacement is
disabled through `WaveDetailWPOScale=0`, including after delayed colour setup.
Normal-map ripples remain. These are native amplitude controls, not an
analytical proof that every shaded vertex stays within ±18 cm.

Both actors enter the loader's ordinary actor registry. Partial startup failure
destroys them, and reload/travel invalidates pending work. No per-frame Lua,
solver domain, source modifier, capture bed, or extra fluid bake is introduced.
Offline tests exercise construction ordering, transformed coordinates, failure
cleanup, the actual loader reload cleanup, invalid option rejection, and
unchanged simulation provenance. The default River path remains covered.

The 2026-11-09 temporary native probe showed the finite lake and islands with
the existing lower waterfall still visible. Evidence is in
`out/pwr/visual-v5-qa/pwr_v5_water_wave_close-2026-11-09T17-25-24-161Z.png` and
`pwr_v5_wave_footprint-2026-11-09T17-26-50-388Z.png`. Native readback confirmed
`UseRenderTarget=false`, `VT_OceanWave`, and disabled actor tick. The temporary
actors were removed and the original surface restored afterward. A final fresh
process using the production hook still needs its own receipt.

Execute `tools/level/flux_wave_readback.lua` through the existing read-only game
bridge after that launch. It requires zero domains/sources/beds, one River,
one Coastline, one non-ticking wave, finite mesh mode 5, three linear Texture2D
maps per state, the expected wave settings and installed VolumeTexture. It
prints surface/state/wave transforms for review. Whole-domain shore, island and
upper/lower seam screenshots remain separate visual acceptance checks.

The official [surface template documentation](https://imaginaryblend.github.io/imaginaryblend-docs/core-systems/surface-actor)
describes Coastline as a combined renderer. Its generic
[ocean setup](https://imaginaryblend.github.io/imaginaryblend-docs/core-systems/simulation-domain#recreating-ocean)
uses an infinite mesh and simulation border blending; this finite-lake hook
deliberately retains mode 5 and the existing saved simulation bounds.
