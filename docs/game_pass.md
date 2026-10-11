# The Xbox app (Game Pass) build

The Xbox app ships the same version of Halo Campaign Evolved as Steam (CU4,
1.112.1610.0), built for the WinGDK platform. MJOLNIR's Lua mods and cooked
containers run on it unchanged; the native halves did not until 2026-10-10,
because they call into the exe at addresses measured on the Steam build.

## What differs

| | Steam | Xbox app |
| --- | --- | --- |
| Install root | `steamapps\common\Halo Campaign Evolved` | `XboxGames\Halo- Campaign Evolved\Content` |
| Binaries | `Meteorite\Binaries\Win64` | `Meteorite\Binaries\WinGDK` |
| Exe | `HaloCampaignEvolved.exe`, PE timestamp `0x8a03f777` | `HaloCampaignEvolved.exe`, PE timestamp `0x3d94a571` |
| Simulation DLL | timestamp `0x6a7a740a` | timestamp `0x6a7a741d` |
| PlayFab / Party | `PlayFabMultiplayerWin.dll`, `PartyWin.dll` | `PlayFabMultiplayerGDK.dll`, `Party.dll` |
| Online subsystem | Steam | GDK (Xbox Live) |
| Containers | `pakchunk<N>-Windows.*` | `pakchunk<N>-WinGDK.*` |

- **The simulation DLL is the same code.** The two copies differ in 29 bytes
  (timestamp, checksum, debug id) plus Steam's signature. Every simulation
  RVA and byte patch holds for both.
- **The exe is a separate link of the same engine code.** Engine functions
  match instruction for instruction at other addresses. Platform code differs:
  the Xbox app's exe has no Steam subsystem.
- **The exe cannot be read on disk.** The Xbox app's file protection refuses
  even an administrator. The DLLs beside it can be read. To study the exe,
  dump it from the running game: `OpenProcess` + `ReadProcessMemory` over
  `SizeOfImage` from the module base. The image comes out relocated to the
  load base, so for Ghidra rewrite each section's raw pointer and size to its
  virtual ones, and set `ImageBase` to the load base.
- **The game is a packaged app.** It starts through
  `shell:AppsFolder\Microsoft.198377053870B_8wekyb3d8bbwe!AppHaloCampaignEvolvedShipping`.
  The launcher derives that id from the install's `appxmanifest.xml`. No
  `ms-xbl-<product id>://` link is registered for it. `C:\Program
  Files\WindowsApps\Microsoft.198377053870B_…` is a junction to the
  `XboxGames` folder, so files installed there are what the game sees.

## Porting addresses

`native/map_registry` keeps one address set per exe (`exe_profiles`, keyed by
the PE timestamp). The Xbox app's set was found from Steam's with
`native/signatures/port_rvas.py`:

```
python -P native/signatures/port_rvas.py <steam exe> <dump> --dump 36D29F0 ... gD349040 ...
```

All eight functions matched whole. The three globals were read back from 5
to 8 functions each. `FModuleManager::Get` needs a longer pattern than the
script's first try, because it differs only in a thread-local slot index
(`0x154` on Steam, `0x13c` on the Xbox app). Do the same after a game
update.

| | Steam | Xbox app |
| --- | --- | --- |
| `FModuleManager::Get` | `0x36D29F0` | `0x32EBF10` |
| `FModuleManager::GetModule` | `0x36D3540` | `0x32ECA60` |
| FName hash | `0x3709650` | `0x33214B0` |
| FName from a view | `0x36FCC60` | `0x3316080` |
| `FCoreDelegates::MountPak` | `0xD349040` | `0xC31C940` |
| `HandleMountPakDelegate` | `0x4694C00` | `0x4239420` |
| `FCoreDelegates::OnUnmountPak` | `0xD349248` | `0xC31CB48` |
| `HandleUnmountPakDelegate` | `0x4694CC0` | `0x42394E0` |
| `GMalloc` | `0xD4B7428` | `0xC47DF60` |
| levels glue `Get` | `0x7B7DFC0` | `0x7749E60` |
| levels glue row insert | `0x7BAC140` | `0x7777F20` |

The AssetRegistry's `GetFirstPackageByName` is slot 30 on both builds.

`native/lobby` finds everything by code pattern. On the Xbox app every
pattern matches once, as on Steam, except two. One is the Steam join hook,
replaced as described below. The other is the presence session's 4-player
literal, which does not exist on the Xbox app. The fireteam still shows
16 slots there.

## Joins by connection string

On Steam a join is the task manager's own `GameRichPresenceJoinRequested_t`
handler, called from `OnlineTick` (docs/multiplayer_servers.md). The Xbox
app's counterpart is the invite handler that `FOnlineSessionGDK` registers
with `XGameInviteRegisterForEvent`:

- **The handler** (`0x663bf40`, `(session, const char *uri)`). It reads
  `connectionString`, `sender` (or `joineeXuid`) and `invitedUser` (or
  `joinerXuid`) from the URI's query: `name=` up to the next `&`, with no
  URL decoding. It then queues the join on the subsystem's next tick. That
  path is taken while a console variable reads true (it does in CU4). The
  other path reads an MPSD `handle`.
- **The invited user** must be a signed-in user. The queued task looks the
  XUID up with `XUserFindUserById`. A miss starts `XUserAddByIdWithUiAsync`
  and waits for it on the game thread.
- **The queued task** stores a pending invite (sender, the user handle, the
  connection string), which the session acts on later. The sender XUID is
  only stored.

`mjolnir_lobby` delivers the request from the GDK subsystem's own tick:

- `FTSTickerObjectBase::Tick` at `subsystem+0x70` (`0x6686270`), whose first
  act is to service the invite's task queue.
- The session is at `subsystem+0xF8`, and points back at `+0x2D8`.
- The player's XUID is the first live key of the subsystem's XUID →
  `XUserHandle` map at `+0x208` (0x38-byte elements).

The URI it sends is
`ms-xbl-mjolnir://inviteHandleAccept/?invitedUser=<xuid>&sender=<id>&connectionString=<string>`.
PlayFab connection strings (`cv2:<lobby>|<n>|kv1:<key>`) contain no `&`.

Verified 2026-10-10 on the Xbox app: every hook installed, a converted map
started from the MULTIPLAYER menu, and a join request was delivered to the
invite handler (`join: delivered`). A join between two players is still
untested.
