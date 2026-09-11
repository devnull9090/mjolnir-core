# UE4SS AOB signatures (Halo Campaign Evolved, Steam)

What UE4SS scans for to find engine internals in the shipping binary. All four
are verified resolving **uniquely** against CU3
(`2026.07.25.1112544.4-Rel-i343-Meteorite-2607-CU3`, host SHA-256
`4D20DC56…D367753` — see [`config/hce-build.lock.json`](../config/hce-build.lock.json)):

```bash
python tools/pe/aob_scan.py "<Win64>/HaloCampaignEvolved.exe"
```

| signature | resolves |
| --- | --- |
| `FName_Constructor.lua` | `FName::FName` |
| `GUObjectArray.lua` | `GUObjectArray` |
| `GUObjectHashTables.lua` | `FUObjectHashTables::Get()` |
| `ProcessLocalScriptFunction.lua` | `ProcessLocalScriptFunction` |

Game Pass signatures are not kept here — the runtime build takes those from
upstream's `zCustomGameConfigs.zip`, under `gamepass/`.

## The rule: never bake a displacement into a pattern

A RIP-relative displacement encodes the distance from an instruction to a
global. That distance changes in **every** shipped build, so a pattern
containing one is guaranteed to rot at the next game update.

Wildcard the displacement and decode it at runtime instead. `GUObjectArray.lua`
is the reference:

```lua
function Register()
    return "45 84 C0 48 C7 41 10 00 00 00 00 48 8D 05 ? ? ? ? ..."
end                                        -- ^^^^^^^ wildcarded

function OnMatchFound(MatchAddress)
    local LeaInstruction = MatchAddress + 0xB
    local NextInstruction = LeaInstruction + 0x7
    local DisplacementAddress = LeaInstruction + 0x3
    return NextInstruction + DerefToInt32(DisplacementAddress)
end
```

The instruction *shape* is what identifies the function; the displacement is
build-specific noise. The same applies to `E8` call targets — wildcard the
rel32 and decode it, as upstream's `gamepass/GUObjectHashTables.lua` does.

This is not theoretical. On 2026-08-01 a game update broke exactly one
signature: `GUObjectHashTables.lua`, the only file that had two displacements
(`39 05 12 39 C5 09`, `48 8D 05 B1 CA 74 09`) committed as literal bytes.
UE4SS retried the scan 1476 times and then killed the process with a fatal
error. The other three resolved fine, because they follow the rule.

Also wildcard TLS slot indices (`B9 <slot>`) — how many slots a binary
allocates is a build-time detail. Short branches (`75 <rel8>`, `EB <rel8>`) are
the same class of noise: the displacement shifts whenever anything between the
branch and its target changes size.

## The second rule: one match, or it is still broken

Wildcarding can go too far. Strip enough bytes and the pattern stops describing
a function and starts describing an idiom the compiler emits everywhere.

`GUObjectHashTables.lua` did exactly this. After the displacements were
wildcarded it matched **195** functions on CU3, because what was left is the
thread-safe accessor MSVC generates for every function-local static. UE4SS does
not complain about that — it logs an address and carries on. The wrong address
then fails somewhere else entirely, which is far harder to diagnose than a scan
that never resolved.

So a signature has to match **exactly once**, and that is not something the log
tells you. Check it directly:

```bash
python tools/pe/aob_scan.py "<Win64>/HaloCampaignEvolved.exe"
```

It reports `OK`, `NO MATCH`, or `AMBIGUOUS xN` per signature and exits nonzero
unless all four resolve uniquely. When a pattern cannot be made unique on its
own, anchor on a call site and decode the `E8` rel32 instead — that is what
`GUObjectHashTables.lua` now does.

## After a game update

1. Run `aob_scan.py` against the new executable. This is the check that catches
   both failure modes; do it before launching anything.
2. Refresh the build lock and confirm what actually changed:
   ```bash
   python tools/build_lock.py "<install root>" --verify config/hce-build.lock.json
   ```
3. For a signature that failed, disassemble the old pattern and check whether the
   broken bytes are a displacement. If so, wildcard them — that is usually the
   whole fix, and it prevents the next break too. Then re-run step 1 to confirm
   you have not traded a missing match for an ambiguous one.
4. Launch and read `ue4ss/UE4SS.log`. Each signature logs either
   `<name> address: 0x...` or `Was unable to find AOB for '<name>'`. Treat this
   as confirmation, not as the check — it cannot see ambiguity.
5. Re-scan only after clearing any cache: UE4SS's `InvalidateCacheIfDLLDiffers`
   watches its own DLL, **not** the game executable, so a game update does not
   invalidate a cached scan on its own.

This bit on the 2026-07-31 CU3 update: `FName_Constructor.lua` failed even though
its pattern was verified present — exactly once — both in the CU3 exe on disk and
in the live process via `ReadProcessMemory`. The pattern was fine. Recovery was
deleting `ue4ss/cache` and relaunching (with `SigScannerNumThreads = 1` also set;
which of the two mattered was not bisected). Clear the cache **first**, before
touching any pattern — a stale cache can impersonate a broken signature.

Known looseness: `GUObjectHashTables.lua` resolved to different addresses on
different CU3 launches at the same image base, so its pattern matches more than
one site. It has worked regardless; tighten it if hash-table lookups ever
misbehave.

## The tag module's anchors (`crates/blam-live/src/tagtable.rs`)

`HaloSimulation_tag_release.dll` keeps the tag table, the segment table and
the string-id registry behind eight globals. A measured profile pins them by
the module's hash; when no profile matches, four anchors recover them from
the module on disk, each matched exactly once on CU4 and each chosen for
what the code does rather than where it is:

| Global | Pattern | The instruction shape |
|---|---|---|
| tag table pointer | `48 89 1D ? ? ? ? C6 43 31 01 48 8B CB` | the table's constructor storing the new object, then setting its `+0x31` flag |
| segment table | `4C 8D 35 ? ? ? ? 48 63 C2 49 8D 0C 80 49 C1 E8 1C` | the encoded-offset decode: words × 4, top nibble as the segment |
| string-id storage | `48 89 05 ? ? ? ? BA 00 F8 0F 00 41 B8 00 FC 07 00` | the registry's constructor storing its storage pointer, then sizing the hash table (0xFF800 buckets, 0x7FC00 max) |
| string-id builtins | `48 8D 05 ? ? ? ? 8B 04 F8 89 44 24 70 EB 20` | a builtin-id lookup, `mov eax, [rax+rdi*8]` |

The other five registry globals sit at fixed offsets from the storage
pointer (`+8` used, `+0x10` strings, `+0x18` count, `+0x30` map). The gated
test `anchors_reproduce_the_measured_profile` checks the derived profile
against the measured one on the installed module.
