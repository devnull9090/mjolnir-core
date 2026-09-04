# How the simulation resolves collision BSP data at runtime (Ghidra, 2026-09-04)

Why a resized `scenario_structure_bsp` collision table crashes the sim on load
while a same-size edit works. RVAs are image-relative in
`HaloSimulation_tag_release.dll` (CU3/CU4, image base `0x180000000`); the `.c`
files here are the Ghidra decompilations. Ghidra project lives in the session
scratch (`scratchpad/ghidra`), imported from a copy of the DLL — the analyzer
chokes on the parentheses in the Steam path, and Avast will kill the run, so
import from a plain directory.

## The arena model

Resident tag data is scattered across up to 16 memory **arenas**. A reference
into that data is one 32-bit word:

    ref = (arena_id << 28) | (dword_offset & 0x0fffffff)

and it resolves through a 16-entry base table at `.data DAT_182c2ccc0`
(VA `0x1802c2ccc0`):

    addr = *(void**)(0x1802c2ccc0 + (ref >> 0x1c) * 8) + (ref & 0x0fffffff) * 4

Every collision accessor uses exactly this. A block field on disk is 12 bytes
`{count, 0, 0}` (`examples/block_headers.rs`); the two zero words are the data
ref and the struct-def ref, and they are **filled at load** — the two `0`s
become real `(arena<<28)|offset` words in the resident copy.

## The load path (`fn_43ee00`)

`FUN_18043ee00(... int *block_field, ... allocator)` is the block
deserializer. For each block it:

1. resolves the struct-def ref (`block_field[2]`) to read the element size at
   `+0x28` and a "has children" bit at `+0x4a`,
2. allocates a resident array through the allocator vtable,
3. copies `count` elements from the resolved data ref (`block_field[1]`),
4. recurses into child blocks via an iterator (`FUN_180296230`),
5. `fn_43f3a0` is the sibling that, after visiting a block's elements, frees
   the source array and zeroes the field (`block_field[0]=0; block_field[1]=0`).

The resident structure-BSP record lands in a global table:
`DAT_1813d45a8 + bsp_index * 0x490`. `fn_2c54a0` reads its block refs at
`+0x68`, `+0x74`, `+0x438`; `fn_2c48b0` (per-instance collision, instance
stride `0x94`) reads the collision-bsp ref at `context+0x18 -> +0x1c`.

## The crash

Every stalling launch faulted at `FUN_1802eb130+0x320` (`0x2eb450`), the kd
**supernode walk** (`fn_2eb130`), reading `word ptr [rax + rcx*4]` with
`rax == 0`. `rax` is `arena_base[ref >> 0x1c]`, so the collision block's ref
word selected an **arena slot holding null** — an uninitialized / wrongly
relocated reference. The exception record's address is `0x0`. The walk reaches
a leaf and hands off to `fn_2eb3d0`.

## What correlates

| build | change to a definition's collision counts | result |
|---|---|---|
| `shift_defs` (P0b) | none — moves vertices/planes in place, same counts, same file size | **loads, pawn stands** |
| `def_transplant` | grows the tables (424 → 5305 surfaces) | crash on load |
| `def_copy` (shipped 178 → 159) | changes counts, byte-valid shipped data | crash on load |
| `bg_allclear` | empties every definition | crash on load |

So the trigger is **changing a nested collision block's element count**, not
the byte content and not the total size (the all-clear build is 5 MB, a third
of the original, and still crashes). A same-size in-place edit is fine.

## What this means

The load-time relocation that turns on-disk `{count,0,0}` fields into resident
arena refs is not tolerant of a count change under `raw_items`, even though the
rewritten tag walks byte-exact through the ordinary reader and every tgbl/tgst
size and parent inline count is updated. The exact writer populates the 0x490
record through a passed pointer (no static rip-relative store to grep), so the
next step is a **live memory diff**: dump `DAT_1813d45a8 + 8*0x490` for a
shipped B40 load and for a resized-tag load, and see which ref field
(`+0x68/+0x74/+0x438/...`) goes null. That names the block whose relocation
breaks, far cheaper than decompiling the pointer-passed writer blind.

Practical consequence for the CE map pipeline: transplanting Blood Gulch by
resizing a shipped BSP's collision tables is blocked here. The world-shell
route hit the same wall. A same-size route cannot hold Blood Gulch's 5,098
surfaces in any shipped definition (largest is 3,205), so the options are
(a) crack the relocation via the live diff and rewrite whatever count-derived
structure is stale, or (b) drop the tag-resize approach for collision.
