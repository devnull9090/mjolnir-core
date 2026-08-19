# Build Lock

**Current build:** `2026.08.11.1121610.2-Rel-i343-Meteorite-2607-CU4` (Steam), Unreal Engine 5.5.4
**Locked:** 2026-08-18
**Lock file:** [`config/hce-build.lock.json`](../config/hce-build.lock.json)

Every finding in `docs/` is only true of the build it was measured on, and the game updates without
asking. Before CU3 each note restated its own hash, which meant eight places to update and eight
chances to miss one. This is the single place that answers "what am I running, and is it what the
notes describe".

---

## Headline hashes

| Artifact | Bytes | SHA-256 |
|:--|--:|:--|
| `HaloCampaignEvolved.exe` | 230,866,704 | `EB1DACA659207F2B5C8A6FD922917195AE9C8AE19E771E396E08906282A4B152` |
| `HaloSimulation_tag_release.dll` | 14,668,560 | `C8C144404ADF61A9DE821C996682A7E66ABADD7E530397D3BBDE31C123203BF7` |
| `PartyWin.dll` | 4,002,840 | `037CAFB5B3682A4EAB8D55A72ED79BBE8D2A73EAC524AD65377217AC67B9F222` |
| `PlayFabMultiplayerWin.dll` | 1,845,280 | `8991E3B9ED098FCF4430C790CC3ABEDC9080F7E567E907F258326B52DAF1A756` |
| `libHttpClient.Win32.dll` | 258,320 | `E9BD94CFC493EF97E5473D47BFA2DE67C2310CF401F9C7C4C6CD0206742E9E1C` |

The lock file carries all 252 shipped files — every binary, all 31 IoStore container sets
(`.utoc`/`.ucas`/`.pak`) and the bundled video, 74 GiB in total.

**Not locked, on purpose:**

- `Binaries/Win64/ue4ss/` and `Content/Paks/LogicMods/` — what we installed, not what shipped.
- `*_P.pak`/`.ucas`/`.utoc` override containers — installed mods by the pak loader's own
  naming convention. One (`pakchunk990-MJOLNIRWORLD-Windows_P`) had leaked into the CU3 lock,
  which surfaced when the vanilla CU3 depot download matched all 252 shipped files and
  "missed" exactly the three we had installed ourselves.
- `Binaries/Win64/dwmapi.dll` — the UE4SS proxy. It sits next to the executable rather than inside
  `ue4ss/`, so it looks shipped and is not. A lock that differs between a modded and a vanilla
  install cannot answer the question it exists to answer.
- `*.dmp`, `*.log` — local residue.

---

## What CU4 changed

CU4 landed on **2026-08-11**. Verifying the CU3 lock against it reported 49 changed files and
none added or removed: the host executable, the simulation DLL, 17 of the 31 container sets
(`global`, `pakchunk0`, and most level chunks), and a third-party sweep (nine `boost` DLLs,
`libHttpClient`, `OpenColorIO`, `tbb`, `CrashReportClient`).

CU3 was overwritten in place, but its depot manifest was still on Steam's CDN:
`tools/steam_depot_fetch.py` recovered it bit-for-bit (all 252 shipped files matched this
lock), both builds are snapshotted, and the CU3 → CU4 tag diff ran for real. See
[`game_update_pipeline.md`](game_update_pipeline.md) for the pipeline and what that diff
found.

---

## Using it

Regenerate after a game update, or verify an install against the committed lock:

```bash
python tools/build_lock.py "<install root>" --generated <date> -o config/hce-build.lock.json
```

```bash
python tools/build_lock.py "<install root>" --verify config/hce-build.lock.json
```

`--verify` reports the version mismatch first, then every changed and missing file, and exits
nonzero if the install is not the locked build. `--binaries-only` skips the 74 GiB content pass
and takes a few seconds, which is usually all you need to answer "did the executable move".

`tools/game_snapshot.py snapshot <root> --lock-out config/hce-build.lock.json` hashes the same
files once and produces both the snapshot and the lock, so after an update prefer it to running
the full pass twice.

Paths are recorded relative to the install root, so two machines on the same build produce
identical locks.

---

## What has been re-verified on CU4

**Verified** on the CU4 binaries above (2026-08-18):

| Claim | Where |
|:--|:--|
| All four UE4SS AOB signatures resolve, and resolve *uniquely* | `tools/pe/aob_scan.py`, 4/4 |
| `FName::FName` at RVA `0x36fd000` | `signatures/FName_Constructor.lua` |
| `GUObjectArray` at RVA `0x379bfc0` | `signatures/GUObjectArray.lua` |
| `FUObjectHashTables::Get()` at VA `0x1436800b3` | `signatures/GUObjectHashTables.lua` |
| `ProcessLocalScriptFunction` at RVA `0x394e460` | `signatures/ProcessLocalScriptFunction.lua` |
| The tag corpus grew to 12,292 tags; 12,290 parse and pass every structural check | `mjolnir validate --all` |
| The 101-group sample re-serialises byte for byte | `mjolnir roundtrip` |
| The tag *definitions* are unchanged from CU2 — 101 groups, 1,779 structs, 13,250 fields, identical | `mjolnir defs`, corpus diff |
| The lock round-trips: 252 files hashed, snapshot verifies 252/252 | `game_snapshot.py verify` |
| CU3 recovered from the depot history hashes identical to its lock, 252/252 | `steam_depot_fetch.py`, manifest `457322918737678760` |

**Verified in the running game** (CU4, 2026-08-18):

| Claim | Evidence |
|:--|:--|
| All 13 mods load with zero Lua errors | `UE4SS.log` |
| The in-game bridge answers at the frontend and in-mission | `game_status` ping |
| Campaign resume works; mission A30 loads and plays | bridge world report |
| `blam-live` finds a loaded tag payload in memory and reads its live value | `mjolnir poke --locate-only`: spartans biped located, `jump velocity` reads 2.3 = shipped |

`defs/hce/tag-definitions.json` and `defs/hce/scripting.json` are regenerated from the CU4
containers and stamped CU4 — the first corpus regeneration since CU2, which also retires the
CU2-label caveat the previous revision of this note carried.

New tag content in CU4, per the CU3 → CU4 `tagdiff`: exactly one tag, the
`a10/unsc_cryo_capsule` animation graph. The oddly named
`Cinematics/020la_sword/.../jorge_turret` graph is present all the way back in vanilla CU2 —
it is launch-era content, not update content. The two tags the full validation cannot parse
fail identically on CU2, CU3 and CU4 — a long-standing decoder gap, not an update regression
(see the pipeline note's known issues).

## What is still CU3-or-earlier-measured

These notes carry an older build stamp and have **not** been re-measured against CU4. Most
describe file formats, which move far less often than code addresses — and the CU4 corpus
validating 100% structurally is indirect evidence the container and tag layout notes still hold
— but nothing here should be cited as CU4-verified:

- [`halosimulation_tag_release.md`](halosimulation_tag_release.md) — offsets into the simulation
  DLL, which is a different binary on CU4. Most likely to have drifted. `blam-live` locating and
  reading a live payload correctly is evidence the *layout* assumptions held, not the offsets.
- [`multiplayer_investigation_notes.md`](multiplayer_investigation_notes.md) — the runtime
  reflection passes, session state captures and Ghidra results.
- The 13 root world package paths hardcoded in `mjolnir_maps` and `tools/mcp/game/game.mjs` were
  enumerated on CU3 and have not been re-enumerated, though A30 loading and playing on CU4 says
  the list is not entirely stale.
- [`tag_data_pipeline.md`](tag_data_pipeline.md), [`tag_body_format.md`](tag_body_format.md),
  [`iostore_packaging.md`](iostore_packaging.md) — container and tag layout.
- [`ue_texture_format.md`](ue_texture_format.md), [`wwise_audio_format.md`](wwise_audio_format.md),
  [`blam_script.md`](blam_script.md).
