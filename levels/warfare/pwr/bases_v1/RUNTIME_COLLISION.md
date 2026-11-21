# Replacement base collision

`runtime_collision.py` prepares the three integrated bases in the isolated
`world-bases-v1` build. It never runs Blender, Unreal, the native compiler, or the
game. Do not run the general terrain/runtime preparer over these frozen sources.

The replacement keeps all 135,836 terrain triangles and 1,808 bridge triangles
exactly. It removes the 1,968 old base triangles and 4,560 old detail triangles,
then appends 25,824 triangles from 1,908 structural modules. The global source
count is 1,190,565, within the existing 1,200,000 surface budget.

Collision preserves separate walls, floors, roofs, ramps, courts and door
surrounds. It omits fine engraving, lights and trim overlays. The 36 expensive
native lining assets each receive a compact measured box; there is no whole-base
convex hull. The six facade fields retain their exact concave door outlines while
omitting tiny Boolean engraving cuts. Normalization welds exact duplicate
vertices, removes zero-area clipping triangles, verifies closed consistent edge
rings and repairs inward components. It does not blindly reverse mirrored blue
geometry a second time.

The source audit checks all three main tunnels, side galleries and bypass routes
against a conservative vehicle envelope, including 8,019 floor support samples.
It also checks the open cannon reservation, native player/ground-vehicle support
positions, and floor/roof positions used by the separate live probe plan. These
are geometry checks, not claims about live physics.

After the native compiler finishes, run:

```powershell
python levels/warfare/pwr/bases_v1/runtime_collision.py compiled `
  C:/haloce/ce_conversions/warfare/PWR/expansion/world-bases-v1/source-build/base-architecture-contract.json `
  C:/haloce/ce_conversions/warfare/PWR/expansion/world-bases-v1/upgrade/PWR/native-collision-receipt.json
python levels/warfare/pwr/bases_v1/prepare_base_probe.py build
```

The compiled proof verifies every appended triangle against the actual native
source binary at float32 precision, checks exact instance ownership of the whole
tail, and repeats support/clearance checks on those coordinates. Compiler source
and output hashes bind that proof to the compiled SBSP.

`refresh_native_probes.py --architecture-contract ... --additional-probe-plan ...`
requires this explicit replacement contract, performs its own compiled readback,
preserves the 12 ordinary terrain probes and adds the separate base probe flags.
It checks patch idempotence and the unchanged native gameplay contract before
atomic publication. Baking, installation and live base traversal acceptance are
subsequent operations controlled by the pipeline owner.
