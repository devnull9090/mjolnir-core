# Locating loaded tags in the running game: sweep today, pointer-chase tomorrow

Live mode has to answer two questions about the running game:

1. **Which tags are loaded, and what level is this?**
2. **Where is a given tag's data buffer, so a field can be poked?**

Today both are answered by the census — one ~13 GB scan of the process's
writable memory that fingerprints every loaded tag by its own bytes
(`blam_live::census`, `apps/tag-editor/src-tauri/src/census.rs`). It works and
is cached, but a scan is a blunt instrument. This note records what we learned
about doing it the classic way instead: a known engine global plus fixed
offsets, resolved once per build and chased by pointer thereafter — no scan.

Measured 2026-09-01 against the shipped build (`…Meteorite-2607-CU3`) in mission
a30, 369 tags verified loaded.

## Finding 1 — the loaded *list* needs no scan at all

Loaded Blam tags are UE `UObject`s named `Blam<Group>TagDataAsset`
(`BlamBipedTagDataAsset`, `BlamWeaponTagDataAsset`, …). The engine keeps every
live `UObject` in **`GUObjectArray`**, which this repo already resolves with a
stable UE4SS signature (`signatures/GUObjectArray.lua`; the AOB wildcards the
RIP-relative displacement and decodes it at runtime, so it survives updates —
see `signatures/README.md`).

Enumerating them is instant. Via the game bridge (UE4SS Lua):

```
FindAllOf("BlamBipedTagDataAsset")  -- 25 biped assets, addresses in hand
```

116 asset UObjects across four classes came back with no measurable delay.

**Implication:** the tag editor (a separate process) can read `GUObjectArray`
over `ReadProcessMemory` — resolve the global once per build from the on-disk
exe (the `tools/pe/aob_scan.py` machinery already does AOB scans), walk the
`FUObjectItem` array, deref each `UObject`, read its class and object `FName`,
and filter to `*TagDataAsset`. That is a bounded read of a few MB, not a 13 GB
sweep, and it answers "what is loaded / which level" in well under a second —
and more reliably than fingerprinting the scenario tag. This is the recommended
next step and does **not** depend on Finding 2.

## Finding 2 — the pokeable buffer is *not* reachable from the UObject

The obvious hope — `UObject + fixed offset → data buffer` — does not hold.
For all 32 name-matched biped/weapon/vehicle/scenario UObjects, the census's
verified buffer address (`base`, and `base + r0` the resident-allocation start)
appears **nowhere** in the UObject's first 8 KB, and **nowhere** one pointer
hop away through any heap-pointer slot in that window. Zero of 32, both targets.

This confirms the long-standing comment in `crates/blam-live/src/lib.rs`: the
tag asset UObject holds its payload as *unloaded bulk data*. The buffer the
simulation actually reads lives in a **separate Blam-side runtime structure**,
not the UE wrapper. `GUObjectArray` gets you the list, but not the buffer.

## Finding 3 — the buffers live in scattered per-tag records that store `base`

A pointer scan (sweep for aligned 64-bit values equal to a verified buffer
address) found **259 holders covering 240 of 369 tags**. Every holder stored
`base` — the *synthetic* "payload byte 0" address (`data_start − r0`), never
`base + r0`. So the engine keeps each buffer positioned such that a field is
read at `base + file_offset`, exactly the addressing `blam_live` already uses.
That is strong independent confirmation the located address is the real thing.

The holders do **not** form one dense array (no fixed-stride table emerged).
They sit ~0x420–0x1040 bytes apart in heap regions — i.e. one runtime structure
of ~1–4 KB per loaded tag, each holding the buffer pointer plus metadata. The
8 bytes after the pointer are *not* the data-section length (`r1 − r0`); the
record layout past the pointer is not yet decoded.

## What's left to make poke scan-free

The remaining unknown is the path from something static to those per-tag
records. Two candidate routes, in order of promise:

1. **A Blam tag-cache root.** The 259 records are presumably owned by a Blam
   tag manager. Find its root (signature on the code that allocates or indexes
   these records, or a `.data` global pointing at the record pool), then index
   by tag id / path. Chase: `global → record[tag] → buffer`.
2. **A deeper UObject link.** The `UObject → buffer` path may exist but be more
   than one hop, through the UE property graph rather than raw offsets — best
   walked with UE4SS reflection, then frozen into offsets once the shape is
   known.

Until then the census sweep stays as the fallback that needs no engine
knowledge, and Finding 1 removes the sweep from the common case (knowing what
is loaded). The scan probes that produced these numbers are not committed —
they were throwaway `#[ignore]`d tests reading a JSON dump of verified hits;
this note has enough to reconstruct them.


## 2026-09-01 — the tag-cache hunt (tag editor 0.16.0 branch)

Probes: `tests/tag_cache.rs`, `tests/tag_cache_root.rs`, `tests/tag_cache_nodes.rs`
(shared helpers in `tests/common/`). Same session as the census dump they read.

### Settled: the buffer descriptor, decoded

Each resident tag's buffer is owned by a **32-byte descriptor**:

```
+0x00  ptr      the buffer — payload byte 0 (`base`), so field = ptr + file_offset
+0x08  u32      size — NOT the data length (r1-r0) and NOT r1; smaller than r1,
                so not a byte length from `base` either. Undecoded.
+0x0C  u32      always 1
+0x10  u64      always 0
+0x18  u8,u8    always 00 01, then 6 bytes of uninitialised padding
```

The `+0xC == 1 / +0x10 == 0 / +0x18 == 00 01` constants held on every one of
167 descriptors and make the record shape-checkable. What Finding 3 above
called "scattered per-tag records" is this: the descriptors are **individually
allocated from the engine's 32-byte small-block pools**, so they sit at 32-byte
stride among *unrelated* 32-byte objects (one pool slot held UTF-16 text).
There is no tag array at this level — which is exactly why the 259 holders
never clustered.

### Settled: one node per tag, above the descriptor

Scanning for pointers *to* the descriptors finds **173 holders for 167
descriptors** — one node per tag, packed into five regions ~10 MB apart, with
slot addresses split almost exactly 50/50 between `mod 32 = 0` and `16`. That
alternation is the fingerprint of a fixed **48-byte element stride**
(16·odd): the nodes are elements of one container. **No node references the
tag's `UObject`** (0 of 172 checked; 0 of 400 windows held *any* tag object),
consistent with the object graph being a shell.

### Why a naive upward walk fails

Scanning for "who points at a node" returns holders *inside the same five
regions* — 1,595 at the next level, 15,916 after that, 57,421 after that. The
nodes point at each other (list/hash sibling links), so a scan that follows
every pointer chases siblings forever and never leaves the pool; no static
holder was reached in five levels. The fix, in `tag_cache_nodes.rs`, is to
**exclude holders that live in the nodes' own pages** — only *external*
references can be the owner — and to determine the node's true start by
scanning for `slot − k` over every plausible `k` and keeping the `k` whose
external holders form one clean container.

### Settled: there is no owner chain to walk up (Phases D and E)

Decoding the slots that hold descriptor pointers (`tag_cache_nodes.rs`)
found **no identity field of any kind** — not the tag's `FName` id, not its
package's, not its class pointer, not a catalog index — and after excluding
same-pool siblings, **one or two external holders in total**, zero at the next
level. The dumps show what the slots really are: **small inline pointer
buffers** (5–10 entries, zero-padded) embedded in assorted objects, often
beside UTF-16 path strings, holding pointers to *consecutively allocated*
32-byte pool blocks. Four different objects reference one tag's descriptor.
These are per-consumer references, not a registry.

Mapping them as arrays (`tag_cache_owner.rs`) confirmed it the other way: the
walks ran through 25k–99k-element pointer-dense regions with descriptors at
0.3–1.5 % density, because the descriptor's `{ptr, u32, 1, 0}` shape is far
too common in UE (it matches refcount control blocks), and **nothing points at
any mapped start**. Upward walking from the buffer has no next step short of
disassembly.

The remaining top-down route: the Blam runtime shares `/Script/
BlamSynchronization` with the tag classes, so its manager is likely a
`UObject` — findable **by class name** through the object table, a root that
needs no static address. `tag_cache_by_name.rs` searches downward from every
live `Blam*` instance for anything reaching a descriptor, slot or buffer.

### Phase F: the Blam runtime *is* exposed as UObjects — 107 classes

`tag_cache_by_name.rs` listed 107 `Blam*` classes with live instances. The
breadth-first search from them was useless as designed — with fanout
768·96·24 it visited 100k–380k objects per root, so *every* root reached
descriptors through meaningless three-hop paths and the ranking was noise
(save-game objects "reached" 80 descriptors). But the listing itself is the
find: among the **singletons** are `BlamCookedTagReferencesEngineSubsystem`
(named for exactly this), `BlamEngineSynchronizationManager`,
`BlamEngineAssetManager`, `BlamEngineLoadingManagerEngineSubsystem`,
`BlamSynchronizationEngineGlueSubsystem` and `BlamScenario`. A `UObject`
root is reachable by class name through the object table in a second — no
static address, no signature, relaunch-proof. `tag_cache_subsystem.rs`
follows each singleton's pointer fields one hop into a large window and
counts descriptors there; a registry shows as one field reaching most of
them.

### Phase G: `BlamCookedTagReferencesEngineSubsystem` holds a 10,201-element array

Following each singleton's pointer fields one hop (`tag_cache_subsystem.rs`)
found no field reaching the descriptors — but the subsystem's own layout,
right after the 0x28-byte `UObject` header, is the find:

```
+0x030  TArray   data 0x1a59ec30000, Num 10201, Max 10240
+0x040  TArray   Num 13, Max 14
+0x050  0x1fff   a hash mask — 8192 buckets
```

A 10,201-entry array in the subsystem *named for cooked tag references*
(catalog: 12,292 tags; present: 9,147). The one-hop probe read only the first
128 KB of it and the descriptor is plausibly a further hop from each element,
which is why it scored nothing. The root is reachable **by class name**
through the object table — no static address. `tag_cache_registry.rs`
decodes the array by correlating it with every per-tag identity.

### Phase H: the 10,201-element array is `TArray<FString>` — the name index

Correlating the array against every per-tag identity found nothing, and the
raw dump says why: each 16-byte element is `{TCHAR* Data; int32 Num; int32
Max}` with `Max` rounded to 8 — an `FString`. The subsystem's array is the
cooked tag-reference **path** index, 10,201 strings, and the 160 KB read was
the whole of it. Its element position is the natural tag index for the
runtime to key on, so the buffer table should be a **parallel array of the
same length**. `tag_cache_parallel.rs` decodes the strings into an
index→catalog map and scans for every `TArray` header with a characteristic
`Num` (10,201 / 9,147 / 12,292 / 362) to find and inspect the parallel tables.

### Settled: the runtime's tag name table, and a tag index for every tag

`tag_cache_parallel.rs` decoded the 10,201 `FString`s: every one is a
`/Game/Tags/...` package path and **10,201 of 10,201 map to a catalog tag**
through `Catalog::tag_by_package`. So `BlamCookedTagReferencesEngineSubsystem
+ 0x30` is the runtime's tag name table, and its element position is a
runtime **tag index** — 312 of the 362 census-resident tags sit in it. The
root is found by class name through the object table; nothing static is
needed. The index→catalog map is saved by the probe (`MJOLNIR_NAMEINDEX_OUT`).

The first parallel-table scan drowned: `Num` values as small as 362 match
`{Num, Max}` lookalikes everywhere (12,411 headers), and the `Num = 10201` /
`12292` hits had non-pointer `Data`. `tag_cache_position.rs` uses the tag
index instead of scanning: a parallel table of stride `E` puts tag `pos`'s
slot at `B + pos·E + k`, so the known slots' pairwise `Δslot/Δpos` must agree.

### Settled: nothing is laid out by tag index; the subsystem is the reference graph

`tag_cache_position.rs`: with every descriptor, slot and buffer base given
its runtime tag index, the pairwise `Δaddress/Δposition` ratios agree on **no
stride** — best candidates hold for 1–6 of hundreds of pairs. There is no
parallel table of buffers, descriptors or slots indexed by tag position.

The subsystem's `+0x40` array decoded to 13 elements of `{u32 id; TArray;
int32 -1; int32 idx}` — **thirteen loaded containers**, each owning an array
of 4,300–6,900 entries whose `Max` (8188 or 5460) is exactly what fits 8- or
12-byte elements in a 64 KB block: ~75k entries in all, far more than 10,201
tags. That is a **tag→tag reference graph**, per container. So
`BlamCookedTagReferencesEngineSubsystem` is precisely its name — the tag
name table and the cooked reference graph — and not the data cache. Its
reference arrays reach no descriptor or buffer within one hop.

A second `Num = 10201` array (`0x1a5c47822c0`) holds per-tag u64s in the
~2 MB range — sizes or offsets by tag index, not pointers.

The remaining hypothesis, consistent with every negative so far: **there is
no central cache**. Each descriptor is a shared block held by whatever
consumes the tag, living as long as something holds it.
`tag_cache_holders.rs` tests this by resolving each slot to the `UObject`
that contains it.

### Settled: the holders are native, not `UObject`s

`tag_cache_holders.rs` resolved each of the 173 descriptor slots to the
nearest preceding `UObject`: **166 are not within 128 KB of any object**, and
the seven that "resolved" are plainly false positives (a slot 0x11f20 bytes
past a Niagara module; a class default object at +0xff0). The descriptor
holders are **native C++ structures**. The `Num = 10201` per-tag u64 array is
not chunk sizes either (0 of 10,201 match).

That reframes every earlier negative. The cache is native, so its root is a
static global in the image's own writable sections — which the upward walks
never reached (node links drowned them) and the `UObject`-rooted search could
not reach (it is not a `UObject`). `tag_cache_static.rs` starts from the true
top: every heap pointer in the exe's `.data`/`.bss`, followed one hop, kept
if the struct there points into one of the five known node regions, then
scored two hops down. Any survivor is `exe + offset` by construction.

### FOUND: static roots into the node containers

`tag_cache_static.rs` — every heap pointer in the image's `.data` (259,923 of
them, 8 MB), one bounded hop each, kept where the struct points into a known
node region, scored two hops down. Two `.data` globals lead straight there:

| static | → struct | field | → node container | slots+descs in 64 KB |
| --- | --- | --- | --- | --- |
| `exe+0xd3ec3a0` | `T @ 0x1a5b2e4cb30` | `+0x808` | `0x1aaec93cde0` | 28 |
| `exe+0xd3ee678` | `T2 @ 0x1a5b2fb9b60` | `+0x808` | `0x1aaf5fb07a0` | 20 |

The same field offset in both: one struct type, two instances, each owning
one of the two densest node regions. The long tail of "candidates" was an
artifact — those statics point at consecutive 80-byte records and their
decreasing field offsets all resolve to the *same absolute slot*
(`0x1a5b2fba368`) through overlapping 4 KB windows. The word after `+0x808`
is not a sane `Num`, so it is not a `TArray` header; a hash-map node store
is the likely shape. Chain so far: **static → T → +0x808 → node container →
node → descriptor → buffer**. `tag_cache_decode.rs` decodes T and the nodes,
testing node identity against the runtime tag index and the name table's
`FString` pointers — keys no earlier probe had.

### Decoded: the root struct and the hash-map node

`tag_cache_decode.rs`, from both static roots. The root struct `T` holds an
**array of 80-byte map records from `+0x40`**, each with a head-node pointer
at `+0x48` and a count at `+0x18` (node pointers in `T` sit at `+0x128,
+0x3f8, +0x498, +0x718, +0x7b8, +0x808, +0x858, +0x8a8` — all ≡ `0x48 mod
0x50`). The Phase L "consecutive 80-byte records" artifact was these.

A node, relative to the slot holding its descriptor, identical in every dump:

```
-0x70  link → node        -0x18  0x1a5b35a2b80   (same in every node)
-0x60  link → node or 0   -0x10  0x1a5b204fce8   (same in every node)
-0x50  u64 KEY HASH       -0x08  per-node key object*
-0x48  0x02000000         +0x00  descriptor*
-0x38  u32 (varies)       +0x08  1
-0x20  0x7fffffff
```

Two sibling links, a 64-bit hash, two shared back-pointers, a key pointer,
then the descriptor: a hash-map node. The identity tests still found no
plain tag key *in* the node — it is behind the hash and/or the key object.
`tag_cache_walk.rs` traverses every record's chain from the static root
(bounded, no scan), dumps `(hash, path)` pairs for offline identification
(UE's `FPackageId` is CityHash64 of the lowercase UTF-16 package name — the
first candidate), and reads the key objects.

### IDENTIFIED: the node key is `FPackageId` — CityHash64 of the lowercase UTF-16 package name

`tag_cache_walk.rs` walked every record's chain from both static roots —
each reaches the same ~44,290-node component (one global asset cache keyed
by package id; loaded tags are a subset) — and dumped `(hash, tag)` pairs.
`hashtest.py` then tried CityHash64 and FNV-1a 64 over eleven path forms:

```
MATCH x35: ('city64', 'utf16', 'pkg_lower')
```

Thirty-five node hashes equal `CityHash64(lowercase UTF-16LE "/game/tags/
<short>-<group>")` bit for bit — UE's `FPackageId`. A coincidental 64-bit
match is impossible, so the key is computable from the catalog alone. The
scan-free chase is therefore complete on paper:

```
.data global → T → 80-byte map record (+0x40, stride 0x50) → head node (+0x48)
  → walk links (-0x70 / -0x60; a link targets a node start, slot = node + 0x60)
  → node with hash (-0x50) == FPackageId(tag) → descriptor (+0x00)
  → descriptor.ptr = base → field at base + file_offset
```

`tag_cache_lookup.rs` is the acceptance test: walk once, index by hash, and
for every census-resident tag compute its id, look it up, and check the
descriptor's pointer equals the base the census found by sweeping 13 GB.

### First acceptance run: the key resolves 8,591 tags; a package has several nodes

`tag_cache_lookup.rs`, first version: the walk from the two static roots
takes **0.1 s** (44,312 nodes, 37,139 keys), and **8,591 of 12,292 catalog
tags resolve to a node by `FPackageId`** — the key confirmed at scale. But
keeping one node per key resolved only 1 of 362 resident tags to its census
base; the "descriptors" it read were not descriptors (`0x400000000`, static
addresses). A package therefore has several nodes — its chunks — under one
package id, and only the bulk-data node holds the buffer descriptor. The
23 walk pairs that did not hash to their tag were the same effect from the
other side: nodes of *other* packages pointing at a shared descriptor. The
refined test keeps every node per key, validates each candidate by
descriptor shape and pointer, and reports which node field marks the holder.

### PROVEN: 35 resident tags resolved to their exact buffer with no scan

`tag_cache_lookup.rs`, refined to keep every node per package id: walk
0.13 s; 8,591 catalog tags have a node; **35 of 362 census-resident tags
resolved by `FPackageId` to a descriptor whose pointer equals the census
base — zero wrong**. The selector is unambiguous:

| field (rel. to slot) | descriptor-holding node | sibling nodes (452) |
| --- | --- | --- |
| `+0x08` flag | **1** (35/35) | **0** (452/452) |
| `-0x48` | `0x2000000` | `0x1000000` (314) / `0x2000000` (138) |
| `-0x20` | `0x7fffffff` | `0` (314) / `0x7fffffff` (138) |
| `-0x08` key | non-null | null (314) / non-null (138) |

So a package's nodes are its chunks; the one with `+0x08 == 1` holds the
live buffer descriptor. What is incomplete is coverage: the two roots reach
one ~44k-node component (244 holder nodes), and the other resident tags'
buffers live under other `T` instances. `T` carries a strong signature
(`0x0000000400000000` at `+0x48`, `+0x98`, `+0xe8`), so `tag_cache_roots.rs`
enumerates every instance from `.data` and unions their coverage.

### All roots enumerated: the map is a loader-side cache, ~10 % of resident buffers

`tag_cache_roots.rs`: the root signature that works is the shared pointer
every record carries at `+0x30` (the mode over a known root's first 24
records; record 0 is not always a plain record). 22 `.data` pointers pass
it — four distinct `T` instances plus the 80-byte artifact — and the largest
(`exe+0xd3eb080`) reaches a **1.28M-node** component: the global asset
cache. Union over all roots: 3,450 holder nodes, 220 catalog tags with a
live descriptor, **37 of 362 resident tags resolved exactly, 0 wrong**.

So the static-rooted map is real and its lookup is exact, but it holds a
buffer only while the loader references it; in a settled mission most
buffers have been handed to the Blam simulation and dropped from the map.
The remaining ~90 % of resident buffers are referenced from consumer
structures. `tag_cache_table.rs` asks whether *those* holders — the slots
storing a base that are not descriptors (~95 of the 262 found by the
level-0 scan) — sit at a fixed stride by tag index: a Blam tag-instance
table, the classic `table[index] → data`.

### Settled: there is no tag-instance table — the loader's map is the only index

`tag_cache_table.rs`: of 259 slots holding a resident buffer base, 92 are
not descriptors. None is in static data; they fit **no stride** by runtime
tag index (37 points, best agreement 1 pair) and none by catalog index (92
points, best 3 of 91 pairs — noise). Their contexts are assorted consumer
structures — one holds its tag's buffer as a plain `TArray<u8>` field
(`{Data = base, Num, Max}`), others sit among per-object pointer tables.

So the engine keeps **no central, index-addressable table of live tag
data**. Buffers are owned by whatever consumes them; the loader's
`FPackageId`-keyed map is the only index, exact for what it references and
partial once loading settles. That is the end of what memory archaeology
can deliver, and it is enough: the map makes every buffer it references
instantly and exactly pokeable — likely most of them during and just after
a level load — and the byte-fingerprint sweep remains for the rest.

### Wired: `blam_live::cache` behind the census

`crates/blam-live/src/cache.rs` carries the production primitives (root
discovery by a self-referential signature, revalidation of cached root
RVAs, the bounded node walk, and the `FPackageId` lookup;
`package_id.rs` is the hash). The tag editor's census runs a `cache` phase
after the object table: every catalog tag is looked up by id and each hit
is verified against the tag's own bytes like a sweep hit, then adopted as
an instant poke base. Root RVAs are cached per build in live state.
