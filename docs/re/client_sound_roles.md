# Client game sounds in multiplayer: how "first person" is decided

Players report that reload, grenade and similar sounds do not always play for
them in MJOLNIR multiplayer; the host never has the problem. This records what
the binaries say about the path a game sound takes, read on 2026-10-24 with the
Ghidra projects in `C:\ghidra_proj` (CU4; sim DLL base `0x180000000`, exe base
`0x140000000`). Nothing here has been confirmed with a second machine yet.

## The simulation side (HaloSimulation_tag_release.dll)

- hs `sound_impulse_start` evaluates into `FUN_1802d42f0` (sound, position,
  object, node, scale, permutation, out), the sim's sound-impulse start. Before
  anything it runs `FUN_1802daf10`: the tag must be `snd!`, flag bit 3 clear,
  the skip fraction passes a random draw, and the sound's promotion rules
  allow another instance. Nothing in it looks at the network.
- The sound is then handed to the exe through the shell's audio interface
  (`FUN_18000cdc0()` -> vtable `+0xa0` -> object -> vtable `[0]`): slot `+0x18`
  plays attached to an object, `+0x28` at a position, `+0x30` in 2D, `+0x38`
  stops. The returned handle is kept; `-1` means the exe refused it.
- When the game globals' mode byte `G[0x11]` is 5 (a networked host) and
  `G[0x1da]` is 0, the start is also sent to the peers as a simulation event:
  `FUN_1805136e0(0x1ffff, 0x16, 1, &object, 0x10, payload)` for attached
  sounds, `FUN_1805135c0(0x17, ...)` for 2D and `(0x18, ...)` for positional.
  The receive handlers are `FUN_1805838b0` (0x16), `FUN_1805839c0` (0x17) and
  `FUN_180583ab0` (0x18); they call the same `FUN_1802d42f0`. The 0x16 handler
  resolves the object reference with `FUN_1805013e0` and **drops the sound
  silently** when the entity is unknown or its object is not created yet. The
  host's side (`FUN_1805017d0`) needs the object's entity (`header+0xfc`) and a
  per-entity state bit; a per-view queue of 0x7fe events caps the rest.
- `debug_sound_listeners` exists as an hs global (`0x182c3466c`) but no code in
  the tag_release build reads it.

## The exe side (HaloAudio and the Blam-to-UE bridge)

Whether a sound is mixed as the player's own ("first person") is not a sim
decision. The HaloAudio layer asks, per sound source, which local users see the
source as first person (`UHaloAudioPlayerRoleProviderComponent::
GetFirstPersonUserIds(RelevantLocalPlayersOut)`), and compares the answer with
each listener's user id (`FUN_147535d30`). `UHaloAudioPlayerVariant` assets
carry a `PlayerSound` and a `NonPlayerSound`.

`FUN_147533650` answers the question for an emitter:

1. If the source actor is a `Pawn` whose `Controller` is a `PlayerController`
   whose `Player` is a `ULocalPlayer`, that user's id.
2. Otherwise `FUN_147533770` walks the actor's `Owner` chain: a role-provider
   component (native, or a Blueprint override called through `ProcessEvent`)
   answers, or a pawn with a local `PlayerController` does.

The source actor is the UE actor of the Blam object. `FUN_14754e7b0` returns
`0x24` and plays nothing when the Blam object has no UE actor/emitter or the
sound asset cannot be found (`FUN_147545080`).

### What owns a biped

Measured on a solo host (BGL, 2026-10-24): the local `BP_SpartansBipedActor_C`
and its `BP_FP_AssaultRifle_WeaponActor_C` have `Owner = BP_MeteoritePawn_C`,
whose `Owner` is the local `BP_MeteoritePlayerController_C`; an AI
`BP_EliteBipedActor_C` has no owner. No biped carries a
`HaloAudioPlayerRoleProviderComponent`, so rule 2 (owner chain to the pawn) is
what makes a player's sounds first person. The biped Blueprint agrees: its
first-person shield effects and `GetThisActorPlayerControllerID` go
`GetOwner()` -> `BP_Meteorite_Pawn` -> `Controller` -> `IsLocallyControlled`.

The owner is set by the pawn. `ABlamPawn` binds (`FUN_147b16b40`) a handler
`FUN_147b18410` to a "unit changed" delegate of its `ABlamCameraManager`
(`PlayerController+0x390`); the handler calls `FUN_147b18450(pawn,
gamestateIdentifier, objectIndex)`, which looks the unit's actor up in the
object tracker (`FUN_147a13a70` by game-state identifier, else
`FUN_147b183a0` by object index) and calls `actor->SetOwner(pawn)` (vtable
`+0x4e8`). A second handler, `FUN_147b177d0`, bound to two delegates on the
player controller (`+0x908`, `+0x920`), re-applies ownership when an expected
actor appears later. Nothing seen so far clears the owner of the previous unit.

### Player identity

`BlamPlayerStateComponent.BlamAbsolutePlayerIndex` (`+0xa8`, replicated, `-1`
unset) names the Blam player behind a `PlayerState`.
`ResolvePlayerStateUsingBlamAbsolutePlayerIndex` scans `GameState.PlayerArray`
and returns the first match. `PlayerState+0x3f8` holds the player's unit object
index; `TryAndGetLocalPlayerControllerForBlamObjectActor` compares it against
each local player's unit actor. [multiplayer_hud.md](../multiplayer_hud.md)
records that a joiner reads the host's index 0 for a few seconds after joining.

## Hypothesis

A client's own sounds stop being first person whenever its biped (or its
first-person weapon actor) ends up without the local pawn as owner. Two ways
that can happen, both only on a client:

- The unit-changed event fires before the client has created the UE actor for
  its unit (clients create objects from network entity updates, so the order
  differs from the host), the tracker lookup fails, and the late-actor path
  does not catch it. Ownership is then fixed only by the next unit change
  (respawn, entering and leaving a vehicle), which would make the fault
  intermittent and per life.
- A joiner's pawn tracks the wrong unit while its player index still reads 0.

Not explained by this: the host hearing other players' pain and breathing
sounds. Pain grunts are ordinary 3D sounds audible to everyone; a remote biped
on the host is owned by the remote pawn, whose controller has no
`ULocalPlayer`, so it would not be first person by the code above.

## What a two-PC run has to record

`tools/remote/audio-roles-test.mjs` runs this ([two_pc_test.md](../two_pc_test.md),
phase 6) with the probe `tools/remote/audio-probe.lua` loaded into both games.
On both machines, once a second after the join and after every spawn:

- every `PlayerArray` entry's `BlamPlayerStateComponent.BlamAbsolutePlayerIndex`;
- each `BP_SpartansBipedActor_C`: `Owner` chain, `BlamUnitComponent:
  GetControllingPlayerDatumIndex()`, and whether a `BP_FP_*_WeaponActor_C` is
  owned by it;
- the local `BP_MeteoritePawn_C` and `PlayerController.Player`.

One trial with PC 2 in the fireteam at start (control), one joining in
progress. A client whose own biped has no owner while its reloads are silent
confirms the mechanism; a client with the correct owner and still no sound
points at the event path (`FUN_1805838b0` dropping unresolvable references, or
the queue cap) instead.

A Lua probe for the host side of this is the one used on 2026-10-24:

```lua
local acClass = StaticFindObject("/Script/Engine.ActorComponent")
for _, a in ipairs(FindAllOf("BlamObjectActor") or {}) do
  local n = a:GetFullName()
  if n:find("SpartansBiped") or n:find("BP_FP_") then
    local chain, cur = {}, a
    for _ = 1, 5 do
      if not (cur and cur:IsValid()) then break end
      chain[#chain + 1] = cur:GetFullName():match("([%w_]+_C_%d+)$") or cur:GetFullName()
      local ok, own = pcall(function() return cur.Owner end)
      if not ok then break end
      cur = own
    end
    print(table.concat(chain, " <- "))
  end
end
```
