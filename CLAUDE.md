# MJOLNIR working rules

These hold for every change in this repository.

## Let the engine do the work; Lua last

Choose the cheapest route that works, in this order:

1. **The Blam simulation.** It owns collision, networking and timing. Anything
   that moves with collision or must look the same for every player is a
   simulation object (device machines, controls, scenery), so it syncs and
   collides with no code of ours.
2. **Unreal natively.** Attach a mesh to the simulation actor's moving
   component instead of copying its pose. Use engine components and
   materials (rotating/movement components, material time and panner nodes,
   Niagara, audio attached to a component) instead of script.
3. **Cooked or baked data**: whatever can be decided at build time
   (tools/level, upgrade_ce_map.py) is decided there, not at load.
4. **Lua, for setup only**: find, bind, attach, hide, then stop. A Lua loop
   that polls or poses every frame is a last resort. Write down why 1-3
   cannot do it, pace it (a slow idle rate, fast only while something
   changes), cache bound UFunctions, and allocate nothing per run. Every
   loop's garbage comes back as 10-15 ms collector frames.

## Respect the tags; no one-map special cases

If something moves, glows, breaks, opens or plays a sound on one map, it is
because a tag says so: a machine type, a device group, an animation, a shader
flag. Read that field and handle it in the tool, so every map whose tags say
the same gets it with no further work. Map configs carry only what the tags
cannot say, such as which textures were hand-redrawn. A map's name may appear
in a comment as an example. It must never be a condition in code. Before
calling a feature done, check that a second map with the same tag data builds
it too.
