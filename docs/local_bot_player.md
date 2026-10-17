# A Second Player Without a Second Account: the Local Bot Seat

**Date**: 2026-08-08
**Status**: The seat works — a script-created second local player becomes a real, fully
embodied splitscreen co-op teammate. Driving it is the open half: every UE-side control
path is overwritten by the Blam simulation, so the bot driver has to speak a layer the
game trusts. The most tractable candidate is an `xinput1_4.dll` proxy.

> Build: CU3 Steam install. Session driven end-to-end through the MCP game tools; the
> account-identity background is in [`dual_instance_notes.md`](dual_instance_notes.md),
> and the player-cap context is in `docs/coop_player_cap.md` (mjolnir/coop8 branch).

## Verified: how to seat the second player

`UGameplayStatics::CreatePlayer(world, 1, true)` mid-mission is **not enough**. It
creates a real `BP_MeteoritePlayerController_C`, a `BP_MeteoritePawn_C`, a PlayerState
with a `BlamNetworkPlayerStateComponent`, and the viewport splits — but the pawn is a
hollow control/camera proxy: no Blam unit, no biped actor, camera stuck on a default
vista, and neither a checkpoint reload nor a full mission restart seats it after the
fact. The simulation's player roster is fixed at campaign launch.

The sequence that works:

1. At the **main menu**, `CreatePlayer(world, 1, true)`. The fireteam panel goes 2/4 by
   itself (also previously verified on the coop8 branch); the second member shows as a
   guest profile, and it **survives menu↔mission transitions**.
2. Start a mission through the normal **CAMPAIGN → NEW GAME** flow (not "Resume solo").
3. The campaign flow launches genuine two-player local splitscreen co-op: both views are
   live first-person gameplay with their own HUD, radar, tutorial prompts and dialogue
   subtitles, and player 2 gets a real **`BP_SpartansBipedActor_C`** — a rendered
   Spartan standing in the world, visible in player 1's view.

No controller needs to be attached; `CanAddSplitscreenPlayer` (a device count) is
advisory only. Player structure: `PlayerController` → `BlamPawn` proxy
(`GetBlamObjectActor()`) → `BP_SpartansBipedActor_C <- BP_BaseBipedActor_C <-
BlamObjectActor`. The visible body is never on the pawn.

## Verified: what cannot drive it

Every UE-reachable control surface on a *seated* player is a dead end, because the Blam
simulation is authoritative and the UE actors are synchronized copies:

| Attempt | Result |
|---|---|
| `Pawn:AddMovementInput` each tick | No movement, seated or not |
| `EnhancedInputLocalPlayerSubsystem:InjectInputVectorForAction(IA_BlamMoveForward, …)` per tick, correct per-player subsystem | No movement |
| `PlayerController:SetControlRotation` | Value sticks on the controller; the Blam camera/aim ignores it |
| `K2_TeleportTo` | Reports success and reads back moved **within the same frame**, then the pawn snaps back to the biped's position on the next sync pass |

The input actions exist and are named for exactly this bridge — `IA_BlamMoveForward`,
`IA_BlamFirePrimary`, `IA_BlamJump`, `IA_BlamMeleeAttack`, `IA_BlamLook*` — but the
injection either doesn't satisfy their trigger path or the sim reads devices below
EnhancedInput. Notably `HaloSimulation_tag_release.dll` imports **DINPUT8 and
xinput1_4 directly**, so the simulation can poll hardware itself.

An unseated (mid-mission) pawn *does* obey teleports and keeps them — useful for camera
probes, useless for a real player.

## The xinput proxy: built and verified driving the bot

**Verified 2026-08-08.** Driver candidate 1 works end to end. A second Spartan walked,
strafed, and emptied its magazine under file-driven pad control, at the input layer the
Blam simulation honours.

The build: [`native/xinput-proxy`](../native/xinput-proxy) — a Rust `cdylib` named
`xinput1_4.dll`. The game exe statically imports **only** `XInputGetState` and
`XInputSetState`, by name, and (confirmed by its import table) does **not** import
`XInputGetCapabilities`, so UE detects controller presence purely from the return code of
`XInputGetState`. The proxy therefore:

- Answers `XInputGetState` for one synthetic user index (default **1**, override
  `MJOLNIR_PAD_INDEX`) with `ERROR_SUCCESS` and a gamepad state parsed from a command
  file; every other index and export passes through to the real DLL, copied beside it as
  `xinput1_4_orig.dll`.
- Reads the command file at most every 4 ms and reverts to a neutral pad once the file is
  older than its TTL, so a dead driver leaves the bot standing still.
- Links the CRT statically, so its only load-time dependencies are `KERNEL32`, an apiset,
  and `ntdll` — it drops in with nothing beside it but the renamed real DLL.
- Every export is a real function, not a PE forwarder: Rust's cdylib export generation
  does not compose with `.def`/`/EXPORT` forwarders (the linker treats forwarder targets
  as undefined locals). Since the game imports by name, plain name exports resolve fine.

Command file `<exe dir>/ue4ss/mjolnir-bridge/pad1.txt` (override `MJOLNIR_PAD_FILE`), one
line: `<ttl_ms> <lx> <ly> <rx> <ry> <lt> <rt> <buttons_hex>`. Tooling:
[`scripts/install-xinput-proxy.ps1`](../scripts/install-xinput-proxy.ps1) (also
`-Uninstall`) and [`scripts/write-pad.ps1`](../scripts/write-pad.ps1).

### What the live test measured (E10, Boarding Action, two seated players)

Player 2's controller mapped to **XInput user index 1** exactly as assumed
(`PlayerController.Player.ControllerId == 1`). Reading its `BP_SpartansBipedActor_C`
position over the bridge before/after each command:

| Command (`write-pad.ps1`) | Result on player 2's biped |
|---|---|
| `-LY 1.0 -Ttl 3000` (forward 3 s) | moved **1871 units**; view advanced into the room |
| input left to expire | **0.0 units** over the next 2 s — neutral-on-stale confirmed |
| `-LY -1 -LX -1 -Ttl 2500` (back-left) | moved **2837 units** — both stick axes analog, in 2D |
| `-LX 1.0` (strafe right) | ~5 units — a wall, not a control failure (the diagonal proves the axis) |
| `-RT 1.0 -Ttl 2500` (fire) | assault-rifle ammo **60 → 22**, ~38 rounds fired, muzzle flash on screen |

Move, aim-axis, and fire all reach the simulation. The build string was CU3; the proxy was
uninstalled and the pad neutralized afterward.

### Remaining driver alternatives (not needed, kept for the record)

- **ViGEm virtual gamepad.** Same effect via a signed kernel driver that fabricates a real
  XInput device. More setup (install ViGEmBus), no advantage now that the proxy works.
- **Native control-block writes.** A UE4SS C++ mod or detour writing player 2's control
  state directly in the simulation. The only route toward *sim-level* tricks (AI attach),
  but it is reverse engineering against the stripped simulation DLL that reshuffles every
  content update.

## On "attach the game's own AI to it"

The campaign's companion behavior is real and scriptable — the shipped HSC corpus
includes `ai_player_add_fireteam_squad`, `ai_player_set_fireteam_max`, `ai_set_task`,
`ai_place`, and the fireteam-follow machinery marines already use. Two paths, neither
runtime-cheap:

- **HSC is compile-time only.** There is no runtime eval; changing AI behavior means
  compiling a script into a scenario tag and repacking (`crates/blam-hsc` +
  `mjolnir pack` — the pipeline exists and round-trips 13/13 scenarios). That can
  place, task, and follow squads of marines, i.e. "AI teammates" in the marine sense,
  entirely with shipped machinery.
- **A Blam AI actor driving a *player* unit** has no visible support in the observed
  opcode table (the classic `ai_attach` is absent — the campaign never calls it, and
  the engine's full runtime table is unknown). If it exists, reaching it is the same
  native project as driver candidate 3.

The pragmatic composition, now that the hands exist: the **xinput proxy is the bot's
hands** (verified above), the existing bridge reflection is its **eyes** (positions of
enemies, allies, objectives are all readable), and the "brain" is an external script —
follow the player, face the nearest enemy, hold fire. The game's own AI stays in charge
of actual marines. The next build step is that brain: a loop that reads the nearest enemy
and player positions over the bridge and writes stick/trigger vectors to `pad1.txt`.

Aiming precisely will want the right-stick (`rx`/`ry`) driven as a proportional-control
loop toward a target bearing computed from the bridge, since XInput aim is a *rate*, not
an absolute angle — the same reason `SetControlRotation` alone did not hold.

## Session hygiene notes

- The A30 resume slot starts in the lifeboat intro; input is locked until the pod
  lands, which will make any input-injection test read as a false negative. A15 via
  NEW GAME reaches interactive control faster (skip the cinematic with a held Space).
- A dev **"Test options"** overlay (DEBUG LEVEL SELECT, MISSIONS/SKULLS/TERMINALS
  UNLOCK toggles, build string) appeared on the main menu during this session —
  trigger unidentified, worth investigating.
- Object IDs from UE4SS count **down**; when two controllers exist, identify players
  by `Controller.Player.ControllerId` (0 = primary), never by creation order guesses.
- `FindAllOf("Class")` returns nothing under UE4SS; sweep with `ForEachUObject`.
- With splitscreen active the game renders two full views — at 3840×2160 this is a
  real GPU cost; drop the window size for long experiments.
