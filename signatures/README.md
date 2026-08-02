# UE4SS AOB signatures (Halo Campaign Evolved, Steam)

What UE4SS scans for to find engine internals in the shipping binary. All four
are verified resolving against the 2026-08-01 game build.

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
allocates is a build-time detail.

## After a game update

1. Launch and read `ue4ss/UE4SS.log`. Each signature logs either
   `<name> address: 0x...` or `Was unable to find AOB for '<name>'`.
2. For anything that failed, disassemble the old pattern and check whether the
   broken bytes are a displacement. If so, wildcard them — that is usually the
   whole fix, and it prevents the next break too.
3. Re-scan only after clearing any cache: UE4SS's `InvalidateCacheIfDLLDiffers`
   watches its own DLL, **not** the game executable, so a game update does not
   invalidate a cached scan on its own.
