# The safety envelope of a networked variant (CU4)

**Status:** 2026-10-21. Static reading only (Ghidra over GhidraMCP, no game
launch). **Binary:** `HaloSimulation_tag_release.dll`, CU4, image base
`0x180000000`; every RVA below is into that build. Companion to
[megalo_engine.md](megalo_engine.md) (how a variant runs) and
[megalo_variant_format.md](megalo_variant_format.md) (the bitstream grammar the
decoder reads).

## The exposure, stated plainly

A fireteam host delivers its game variant to every joining member as an ordinary
**session parameter**, replicated peer-to-peer. The payload is the **encoded
Megalo bitstream**, and each joiner **decodes it on receipt** through CU4's
variant decoder (`0x392a40`). That decoder trusts the stream: past a size cap on
the transport buffer, a version check and a transit checksum, it applies no
semantic bounds. Counts are read as raw bit-fields and their records are written
to fixed offsets in a fixed-size destination with no check against that
destination's size. The action count in particular (`u11`, up to 2047) overruns
the `0xfc08`-byte stack buffer the joiner decodes into, with attacker-chosen
bytes — a classic stack buffer overflow, i.e. **controlled memory corruption on
the joining client, not merely a crash.**

The decode is the sim's **networked multiplayer-session** path (session modes
3/4) — the same layer MJOLNIR switches on. It runs **before** MJOLNIR's own
staging touches the game, so MJOLNIR's native layer provides no guard against it.
A malicious host is the threat; a well-behaved host never sends a malformed
variant, and the transit checksum is the sender's own (it defends against line
noise, not a hostile host).

**Resolved (2026-10-23) — the live network vector is not real; the risk is a
malformed `.mglo` in distributed content.** Both the static read and a real
two-PC fireteam show the sim's game-variant session parameter is **never
populated** — not in retail (which delivers the variant as a bounded Unreal
struct), not on a MJOLNIR host or joiner (which use the local `.mglo` file
loader). `0x51d1b0` is a latent, unused path, so a malicious fireteam host cannot
reach a joiner's decoder through it. The first draft's "every fireteam decodes
the host's variant" framing was wrong. What the unbounded decoder *does* process
is the `.mglo` **file** each client stages, so the real exposure is a crafted
`.mglo` riding in a hub map/mod — see "Live results" and "Is this reachable"
below. Mitigation belongs at the file-loader staging point, not the network.

> This document is a defensive finding for the maintainers. It locates the
> trust boundary and proposes a guard. It is deliberately not a recipe: the
> overflow is characterised only as far as is needed to justify the mitigation.

## The path (RVAs, with confidence)

| step | RVA(s) | what | confidence |
|---|---|---|---|
| transport | `0x51d0c0` / `0x51d1b0` (variant A), `0x51d480` / `0x51d550` (variant B) | the game-variant session parameter's chunk serialize / reassemble vtable methods; data buffer at session `+0x1f8e8` (0x5000 bytes), chunked at 0x200 | **VERIFIED** |
| registry | tables at `0x9548dc` / `0x82c9a68c` (4-byte RVAs) | the replication engine's generic parameter-handler registry; these handlers are registered like any other session parameter | **VERIFIED** |
| reassemble + gate | `0x51d1b0` | stores received chunks into the 0x5000 buffer; rejects chunk count outside 1..40 and total size `>0x5000`; CRC32s the reassembled bytes (table `0x85c500`) against the sender's checksum; on the last chunk, decodes | **VERIFIED** |
| decode dispatch | parameter vtable slot `+0x98` (variant A) / `+0xa8` (variant B) | virtual "decode this bitstream into the variant object"; dispatched per engine type by a runtime thunk (`movsxd; jmp [obj+disp]`), so the concrete callee is not pinned statically | **VERIFIED** it is called with `(bitstream, dest)`; **INFERRED (strong)** that for a Megalo variant it is the Megalo codec below |
| variant decode | `0x398550` (full: body + engine selector at `+0xf860`) → `0x392a40` (body) → `0x3949c0` (string table) | the unbounded decoder, the variant object's own vtable slots 28 / 5 (vtable `0x83c3b8`) | **VERIFIED** |
| destination | stack buffer in `0x51d1b0`, 0xfc08 bytes; on success copied to the parameter object `+0x88` | the decode writes here; the variant object is `0xf860` (Megalo), so 0xfc08 is the whole object plus slack | **VERIFIED** |
| into options | `0x55c730` (in-game session-state update, lifecycle state 3) → `0x55e1c0` (options from session) → store `0x216300` | later copies the already-decoded variant struct into the game options; **does not** itself decode (no call to `0x392a40`/`0x398550`), so it is not where the danger is — it only confirms the decoded variant is consumed as the game variant | **VERIFIED** (the no-decode point); runs-per-peer is the replication model, not re-derived here |

The decode-dispatch hop is the only one not pinned to an exact callee: the
parameter's `+0x98`/`+0xa8` slots are per-engine-type dispatch thunks, so a
static reader cannot see the Megalo branch without the runtime table. The
inference that it is `0x398550`/`0x392a40` rests on: the decode's signature is
`(self, bitstream, variantptr) -> bool`; the destination is `0xfc08` ≈ the game
variant (`0xfc04`, Megalo object `0xf860`); the decoded result becomes the game
options' variant; and `0x392a40`/`0x398550` are the only bitstream→variant
decoders in the image. The round-trip clone `0x216a50` (below) uses the
identical 0x5000-buffer-plus-`0x392a40` pattern.

## Q1 — bitstream or struct copy, and what is checked

**It is the encoded bitstream, decoded on the client** (not an in-memory struct
memcpy). The transport parameter is a ≤0x5000-byte buffer; `0x51d1b0` builds a
bit-reader over it and runs the decoder, exactly as the on-disk `.mglo` loader
does (`0x3f8a00` → slot 5; megalo_engine.md, "A variant from a file"). The two
differ only in where the bytes come from.

Checks the joiner applies **before** the decoder writes anything:

- **Transport size cap — present.** `0x51d1b0` rejects a first chunk whose total
  size is `>0x5000` or whose chunk count is outside 1..40 (`40*0x200 = 0x5000`).
  So the *input* bitstream is bounded to 0x5000 bytes. (The variant-B reassembler
  `0x51d550` omits the explicit `>0x5000` test and relies on the chunk-count cap
  alone; noted, not the game-variant path.)
- **Version gate — present.** `0x392a40` returns immediately unless the 32-bit
  encoding version is `0x6a` or `0x6b` (`if (1 < version - 0x6a) return;`).
- **Transit checksum — present but not a trust boundary.** The CRC32 is the
  sender's own; a hostile host computes a valid one for its payload.

Checks the decoder does **not** apply (the semantic bounds that matter):

- **String-table size vs the `0x4c00` buffer — none.** `0x3949c0` reads a 15-bit
  uncompressed size (up to `0x7fff`) and, uncompressed, copies that many
  attacker bytes straight into `variant+0x11b8` whose capacity is `0x4c00`
  (the size itself is stored at `+0x4c00`, immediately after the buffer). The
  compressed path inflates (`0x32a620`) up to the *claimed* uncompressed size
  into the same buffer. Neither caps at `0x4c00`.
- **Counts vs destination array sizes — none.** Conditions `u10` (≤1023,
  store `+0x7304` stride 0x10), **actions `u11` (≤2047, store `+0x930c` stride
  0x14)**, triggers `u9` (≤511, store `+0x63fc` stride 0x0c), player traits
  `u5` (≤31, store `+0x5dcc` stride 0x30) and the other block counts are read as
  raw bit-fields and looped with no comparison to any maximum (`0x392a40` lines
  at the condition/action/trigger loops; the running index at `+0x72fc`/`+0x9304`
  /`+0x63f4` is only incremented).
- **Nested-trigger / block recursion depth — none found** (consistent with the
  earlier research pass; not re-derived here).

The post-decode validator `0x40a310` / `0x409c40` (object-type bitset sanity,
megalo_variant_format.md) runs **after** the decoder has already written, so it
can wipe a bad script but cannot prevent the memory writes.

## Q2 — who decodes it, and when, relative to MJOLNIR

**The joiner of a multiplayer-session fireteam.** The reassemble-and-decode
handlers are registered in the replication engine's generic parameter registry
(`0x9548dc` / `0x82c9a68c`) and `0x51d1b0`/`0x51d550` run on the peer that
*receives* the parameter, so a joining client decodes the host's variant on
receipt. But this is the sim's networked multiplayer-session machinery (mode-
gated in `0x55a2a0`; options read back in `0x55e1c0`, itself called only inside
`0x55c730`'s session-state branch), **not** a path that every fireteam uses. The
body decoder `0x392a40` runs *before* `0x398550` reads the engine-type selector,
so once this path is taken the dangerous writes happen regardless of the claimed
engine.

## Is this reachable in unmodified retail? (the scope-deciding question)

**Not on the path retail co-op actually uses — static evidence points to the
bounded struct path, with the unbounded path being the cut multiplayer layer
MJOLNIR revives.** This was the decisive follow-up, because it separates a live
retail vulnerability from a latent engine weakness that a mod activates.

- **Retail co-op's variant is a bounded struct, not a bitstream.** The variant
  reaches the sim through the Unreal host's load-map event (`0xe670` event 0xb →
  `0xf650`). `0xf650` builds a default variant (`0x21c4f0(&v, 3)` = campaign) and,
  when the engine is campaign, folds in Unreal's `CampaignVariantStorage` blob
  (payload `+0x5b`) via **`0xfba0`** — then stores it with `0x216300`. `0xfba0`
  is a fixed-layout, field-by-field **struct copy with per-field clamps** (a
  `do…while(i != 4)` over 4 players; every byte range-checked, e.g.
  `if (0xc < bVar5) bVar5 = 0`). No counts drive loops, no string table, no
  bit-reader — it never calls `0x392a40`. **VERIFIED.** So the normal retail
  co-op variant flow does not reach the unbounded decoder over the network.
- **The unbounded path belongs to the multiplayer session layer retail does not
  run.** `0x51d1b0`'s decode is reached through `0x55a2a0`/`0x55e1c0`/`0x55c730`,
  all mode-3/4 (multiplayer) session machinery. MJOLNIR has to byte-patch exactly
  these functions — `0xf6db` (ask for the Megalo engine), `0x55af56` (session-
  readiness mask), `0x55e8c7` (options builder), `0x45b1a3` — to make the sim
  enter and accept that path. That those patches are *necessary* is strong
  evidence the path is otherwise not taken (megalo_engine.md; the project's prior
  finding that the sim's `net_*` layer is stubbed and "networking goes through
  Unreal"). **VERIFIED** that MJOLNIR patches these; **INFERRED (strong)** that
  unmodified retail never drives `0x51d1b0` for a remote variant.
- **Residual uncertainty — why a live check is still needed.** Static analysis
  can show the retail variant path is bounded and that the unbounded path is the
  mode-3/4 layer, but it cannot cheaply *prove the negative* that no vestigial
  retail flow (a matchmaking stub, a co-op session that quietly uses a mode-3/4
  parameter set) ever populates and decodes the game-variant session parameter.
  That is settled by observing a real session, not by reading more code.

**Consequence for disclosure.** If the live check shows retail never populates
the parameter, this is a **latent engine weakness that MJOLNIR (and its public
lobbies) activate**, fixed by the MJOLNIR guard below; a Microsoft/CVE report
would be about defense-in-depth in their decoder, not "retail players are
exploitable today." If the check shows retail *does* drive it, it is a live
remote memory-corruption bug in a shipped Microsoft product and warrants
coordinated disclosure to MSRC. Do not report upstream until the check decides.

**Before MJOLNIR's staging.** The receipt-time decode sits in the session layer,
ahead of options building (`0x55c730` → `0x55e1c0`) and far ahead of game/round
start. MJOLNIR's native half (`native/map_registry/mjolnir_map_registry.c`) does
two things, both later and neither touching the session parameter:

1. `mjolnir_megalo_on` applies the seven byte patches of the Megalo switch
   (`MEGALO[]`, around `mjolnir_map_registry.c:1193`).
2. `mjolnir_megalo_variant` copies a staged `.mglo` **file** into the HotReload
   directory and sets the loader's name buffer (`0x152a7c0`), so the **round
   reset** `0x2ad560` reads it at game/round start.

So the exposure order on a joiner is: receive session parameter → **decode
(unguarded)** → build options → game start → round reset → MJOLNIR's file
variant. MJOLNIR's file loader (its only variant touchpoint) never sees the
network variant, and nothing MJOLNIR ships validates it.

## Q3 — crash only, or controlled writes

**Controlled writes, with attacker-chosen content.** The headline is the action
loop: the decoder writes `count` records of `0x14` bytes from `+0x930c`, with
`count` a raw `u11` up to 2047. The decode destination in `0x51d1b0` is a
`0xfc08`-byte stack buffer. Records past offset `~0xfc08` land beyond the buffer;
`0x930c + count*0x14` crosses `0xfc08` once `count` exceeds ~1344 (and crosses
the `0xf860` variant object itself above ~1309), reaching `0x2330c` at the
field's maximum of 2047 — an overrun of up to ~0x1370c bytes of
attacker-influenced record data over the stack. That is a stack-based buffer
overflow, the kind of primitive that is a crash in the benign case and memory
corruption in the hostile one.

The string table adds a second, buffer-internal corruption: up to `0x7fff`
attacker bytes written over the `0x4c00` field at `+0x11b8`, clobbering the
trait/user-option/condition state decoded just before it (contained within the
`0xfc08` buffer, but still attacker-controlled bytes over live variant fields
the interpreter then trusts as indices and counts).

Whether this is weaponisable to code execution is **not assessed here** and was
not attempted. The static facts — a linear, attacker-controlled, out-of-bounds
write reachable from an untrusted peer before any MJOLNIR guard — are enough to
treat it as a serious memory-safety exposure rather than a mere denial of
service.

## The safe read-only reachability check (two machines, retail, no mods)

Goal: decide whether unmodified retail co-op ever populates and decodes the
game-variant **session parameter** on a joiner. Purely observational — sample
memory, inject nothing, send no crafted data, touch no stranger's game.

Setup: the two machines on the user's own accounts, a **private** campaign co-op
game between just them, on the **unmodified retail** build — `mjolnir_map_registry.dll`
**not** loaded (if MJOLNIR's switch is on you are testing MJOLNIR, not retail).
Use the out-of-process reader probe built for exactly this —
`crates/blam-live/examples/variant_param_probe.rs` — which samples sim memory
from outside the process and writes nothing:

```
cargo run -p blam-live --example variant_param_probe      # on the joiner (pc2)
```

It polls once a second and prints ENGINE / MODE / VARIANT / SESSION, flagging any
change, so you can watch the transitions as the joiner connects and loads. The
three readings below are what it reports; do not hook, patch, or write.

On the **joiner** (the machine that joins the host's game), read, before and
during the co-op session:

1. **Session mode / lifecycle.** Session object `*0xca3480`, mode at `+0x28`, and
   the lifecycle state (`0xca3428`). If the mode stays campaign (1) and the state
   never enters the mode-3/4 (multiplayer) states, the parameter layer is dormant.
2. **Is the game-variant parameter buffer filled from the wire?** On the joiner,
   read the parameter object's receive buffer at `session+0x1f8e8`, its total
   size `+0x248e8`, chunk count `+0x248f0`, and last-received index `+0x1f8e4`
   (and the variant-B buffer at `+0x248f4`). If these stay zero/`-1` throughout a
   normal co-op session, `0x51d1b0` never ran → the decoder is never fed over the
   network in retail. If they fill as the joiner connects, the path is live and
   this becomes an MSRC matter.
3. **Did the decoder touch the live variant?** Read the live variant's encoding
   version (`variant_object+0x5dc0`): the decoder leaves `0x6a`/`0x6b`, an
   untouched default stays as built by `0x21c4f0`. Corroborates (2) without any
   write.

Interpreting it: buffers empty + mode 1 across a full co-op session = retail does
not use this path (expected from the static read) → MJOLNIR-only exposure, no
upstream report needed. Buffers populated on the joiner = retail drives it →
coordinated MSRC disclosure. Either way, nothing malformed is ever sent; a crash
repro (if later wanted for a report) must also be against these two machines
only, never a public lobby, and is a separate decision.

## Live results (2026-10-23, two PCs) — CONFIRMED

Run with the probe above on a second PC (VENUS) through the two-PC agent, as both
a host and a joiner. **The network decode path is confirmed unused.**

```
ENGINE 2 MEGALO   MODE 3   VARIANT type 2 MEGALO, encver 0x6a (DECODED)
SESSION 0x7ffe61774d50   PARAM none (scanned 0x60000, 0 markers)
```

- **The probe is validated.** It attaches to the live sim and reads the engine
  index, the game variant and the session object correctly; in the lobby it read
  ENGINE 0 / VARIANT type 0 / PARAM none, and in the match ENGINE 2 / VARIANT
  type 2.
- **The live variant is decoded, via the file loader.** `encver 0x6a` is exactly
  the version a decoded `.mglo` **file** leaves (`0x6b` is the untouched default;
  megalo_engine.md, "The variant file loader, fixed"). So the unbounded decoder
  `0x392a40` *did* run — fed by MJOLNIR's file loader (`mjolnir_map_registry`
  stages `mjolnir.mglo`, the round reset `0x2ad560` decodes it), not by the
  network.
- **The networked session parameter is empty.** A full scan of the 384 KB
  session object found **zero** variant-bitstream markers — no `0x51d1b0`
  payload is parked anywhere in it. So on this host the game-variant session
  parameter is not populated at all.

**What this means.** MJOLNIR appears to distribute the variant as a **local file
on each client** (the `.mglo` rides with the map/mod content and each client's
`mjolnir_map_registry` stages and decodes it), **not** through the sim's
game-variant session parameter. Combined with the static finding that retail
co-op uses the bounded Unreal struct, that leaves the `0x51d1b0` network-decode
path looking **unused in practice by both retail and MJOLNIR** — a latent code
path. The decode that actually happens is the **file loader**.

**The exposure therefore re-centres on distributed content, not a live peer.** A
malformed `.mglo` reaches the unbounded decoder through the file loader on every
client that installs and plays the map/mod carrying it. The live network-peer
vector is not confirmed; a malicious **hub map/mod** carrying a crafted `.mglo`
is the realistic path, and it hits the same decoder (`0x392a40`), bounded only to
0x5000 input by MJOLNIR's sixth switch patch — the internal count/string
overflows still apply.

**The joiner measurement (the decisive one).** pc2 then joined a game hosted by
the other PC (Blood Gulch, Slayer) and was sampled continuously through the join
handshake, the map load, and in-match play — a verified real joiner (in the map,
AR in hand, Slayer HUD "TO WIN 25"). Every sample:

```
ENGINE 2 MEGALO   VARIANT type 2 MEGALO, encver 0x6b   PARAM none (scanned 0x60000, 0 markers)
```

- **The session parameter is empty on the joiner too** — 0 markers across the
  whole join and match, full-scan. The `0x51d1b0` network-decode path is never
  fed. A 90-second continuous burst over the join caught no transient either.
- **The joiner isn't even running the host's variant** — `encver 0x6b` is the
  *default* (`0x21c4f0`), not the host's file-decoded `0x6a`. So the variant does
  not travel to the joiner through the sim at all; MJOLNIR's Slayer scoring is
  host-authoritative (the HUD's "TO WIN 25" is MJOLNIR's own replication, not the
  joiner's local sim variant).

**Conclusion: the live network vector is not real.** Across static analysis and a
real two-PC fireteam, the sim's game-variant session parameter is never
populated — not in retail (Unreal struct), not on a MJOLNIR host (file loader),
not on a MJOLNIR joiner (default variant, host-authoritative). `0x51d1b0` is a
latent, unused path. **No MSRC / live-network report is warranted.** The decode
that actually runs is the **file loader**, so the exposure is a content-safety
problem: a malformed `.mglo` in distributed hub map/mod content reaches the
unbounded decoder on every client that installs and plays it. That is where the
mitigation belongs. (Caveat: tested one config — BGL/Slayer, two-player LAN
fireteam; MJOLNIR's file-loader architecture makes other configs behave the same,
but public FIND GAMES lobbies and other game types were not separately measured.)

## Mitigation (implemented 2026-10-23)

The live test moved the threat from a live network peer to a malformed `.mglo`
in distributed content, decoded by the file loader. The decoder is engine code
we cannot change, so the fix validates the `.mglo` against the simulation's own
grammar and store capacities **before it is installed**, and refuses anything
that would overrun the decoder. One validator, reused everywhere.

1. **The validator lives in `crates/blam-megalo`** — the crate that already
   reads and writes this exact format, so the grammar has one source.
   `Variant::validate(bytes)` runs `Variant::read` (which already refuses player
   traits, user options, compressed string tables and the variable kinds it does
   not model) and then enforces the caps the engine omits, as named constants
   tied to the simulation's offsets: `MAX_BYTES` 0x5000, `MAX_STRING_DATA`
   0x4c00, `MAX_WIDGETS` 4, and the 0xf860-object store capacities
   `MAX_CONDITIONS` / `MAX_ACTIONS` (1297, the count that matters —
   `(0xf860−0x930c)/0x14`) / `MAX_TRIGGERS`, plus `MAX_FILTERS` 16. `read` itself
   now rejects an over-size string table and more than four HUD widgets at the
   point it meets them. Unit tests cover a normal variant (accepted), an oversize
   file and an over-capacity action count (both refused).
2. **The CLI exposes it:** `mjolnir megalo validate <file>` returns non-zero on a
   malformed or out-of-bounds `.mglo`, for pipelines and manual checks; and
   `mjolnir megalo write` now validates what it produces before writing.
3. **The client refuses to install a bad variant.** The launcher validates every
   `.mglo` as it extracts hub content — both the code-mod path (`install_entry`)
   and the signed release/map path — and aborts the install with a clear message
   rather than letting a crafted variant reach disk, where the file loader would
   decode it. This is the gate for distributed content, on the client, before
   the simulation ever sees the file.
4. **Last-line native guard at the staging point.** The native half
   (`native/map_registry/mjolnir_map_registry.c`, `mjolnir_megalo_variant`) now
   validates the staged `.mglo` immediately before it hands it to the file
   loader, and refuses to stage one that fails (the simulation keeps its default
   variant). It reuses the *same* grammar: `crates/mjolnir-mglo-cabi` is a tiny
   `extern "C"` staticlib over `blam_megalo::Variant::validate`, linked into the
   DLL by `build.ps1` (adds a `cargo build`; final DLL ~182 KB, the linker strips
   the unused Rust std). This catches a `.mglo` that reached disk past the
   launcher — a sideloaded map, say.
5. **Pack-time guard.** `mjolnir map pack` / `map runtime` validate every `.mglo`
   member before the uploadable `.mjolnir` archive is even written
   (`write_archive`), so the tooling cannot produce or upload a malformed one.

**Not done / follow-ups.** Server-side validation on hub **upload** is not in
place: the Worker (TypeScript) stores the `.mjolnir` blob to R2 without unzipping
it (`publish.ts`), so a server-side check would need the Worker to unzip and run
the grammar — best done by compiling `blam-megalo` to WASM rather than
reimplementing the format in TypeScript. The realistic distribution path is
already covered on the client (install-time + staging-time), so this is
belt-and-suspenders against a hand-crafted direct API upload. The nested-block
recursion depth is bounded by `Variant::read` consuming the stream, not by an
explicit depth cap; worth an explicit limit if the format's block actions are
ever modelled.

## Reproduction of the static trace (for re-checking)

Ghidra headless (megalo_engine.md / ghidra_mcp.md), then, with VA = base + RVA:

```text
0x51d1b0  reassemble+decode (buffer +0x1f8e8, 0x5000 cap, CRC, vtable +0x98 decode)
0x51d550  sibling for buffer +0x248f4 (vtable +0xa8)
0x51d0c0 / 0x51d480   the matching chunk serializers
0x392a40  body decoder: version gate; uncapped condition/action/trigger/trait loops
0x3949c0  string table: u15 size into the 0x4c00 buffer at +0x11b8, no cap
0x398550  full decoder (body + engine selector +0xf860), variant vtable slot 28
0x216a50  encode→decode round-trip clone (same 0x5000 + 0x392a40 pattern)
0x55e1c0  options-from-session: copies the decoded struct, does not decode
0x2ad560  round reset: MJOLNIR's file variant, later than all of the above

Retail variant path (the bounded one, for contrast):
0xe670    shell event drain, event 0xb = load map (Unreal-driven)
0xf650    builds the variant; folds in CampaignVariantStorage when engine==3
0xfba0    CampaignVariantStorage -> variant: fixed 4-player struct copy, clamped,
          no bitstream, never calls 0x392a40
0x55a2a0  session readiness: mode-gated (iVar9==3); the multiplayer-session layer
```
