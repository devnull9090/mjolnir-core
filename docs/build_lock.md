# Build Lock

**Current build:** `2026.07.25.1112544.4-Rel-i343-Meteorite-2607-CU3` (Steam), Unreal Engine 5.5.4
**Locked:** 2026-08-05
**Lock file:** [`config/hce-build.lock.json`](../config/hce-build.lock.json)

Every finding in `docs/` is only true of the build it was measured on, and the game updates without
asking. Before CU3 each note restated its own hash, which meant eight places to update and eight
chances to miss one. This is the single place that answers "what am I running, and is it what the
notes describe".

---

## Headline hashes

| Artifact | Bytes | SHA-256 |
|:--|--:|:--|
| `HaloCampaignEvolved.exe` | 230,823,184 | `4D20DC56611B29CD710D591C86CF5DE55B914EB986838C42E719B82CCD367753` |
| `HaloSimulation_tag_release.dll` | 14,668,560 | `82B8A3A006BA3F981D6857DC7F4E4E929AE5282587F31F92F77A3FA78F4B2DAC` |
| `PartyWin.dll` | 4,002,840 | `037CAFB5B3682A4EAB8D55A72ED79BBE8D2A73EAC524AD65377217AC67B9F222` |
| `PlayFabMultiplayerWin.dll` | 1,845,280 | `8991E3B9ED098FCF4430C790CC3ABEDC9080F7E567E907F258326B52DAF1A756` |
| `libHttpClient.Win32.dll` | 258,320 | `6488416D788FAA0CABA39F3CDB8442D827933B72A411E2051F71A7A6DFB02691` |

The lock file carries all 255 shipped files — every binary, all 31 IoStore container sets
(`.utoc`/`.ucas`/`.pak`) and the bundled video, 74 GiB in total.

**Not locked, on purpose:**

- `Binaries/Win64/ue4ss/` and `Content/Paks/LogicMods/` — what we installed, not what shipped.
- `Binaries/Win64/dwmapi.dll` — the UE4SS proxy. It sits next to the executable rather than inside
  `ue4ss/`, so it looks shipped and is not. A lock that differs between a modded and a vanilla
  install cannot answer the question it exists to answer.
- `*.dmp`, `*.log` — local residue.

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

Paths are recorded relative to the install root, so two machines on the same build produce
identical locks.

---

## What has been re-verified on CU3

**Verified** on the CU3 binaries above:

| Claim | Where |
|:--|:--|
| All four UE4SS AOB signatures resolve, and resolve *uniquely* | [`signatures/README.md`](../signatures/README.md) |
| `FName::FName` at RVA `0x36fd130` | `signatures/FName_Constructor.lua` |
| `GUObjectArray` at RVA `0x379c0f0` | `signatures/GUObjectArray.lua` |
| `FUObjectHashTables::Get()` at VA `0x1435993b0` | `signatures/GUObjectHashTables.lua` |
| `ProcessLocalScriptFunction` at RVA `0x394e590` | `signatures/ProcessLocalScriptFunction.lua` |
| The 13 root world package paths are unchanged | `mjolnir_maps`, `tools/mcp/game/game.mjs` |
| The lock round-trips: 255 files matched, 0 changed, 0 missing | `--verify` |

**Verified in the running game** (CU3, 2026-08-05, five launches):

| Claim | Evidence |
|:--|:--|
| The new `GUObjectHashTables` signature resolves to the intended function | UE4SS logged `0x7ff6563b93b0`; module base `0x7ff652e20000` makes that RVA `0x35993b0` |
| The *old* signature resolved to the **wrong** function | previous run logged RVA `0x353a140` — a different function 0x5f270 bytes away |
| All 13 mods load with zero Lua errors | `UE4SS.log` |
| `GameSession.MaxPlayers` = 4, `MaxSplitscreensPerConnection` = 2 | read live at the frontend |
| `AGameSession::KickPlayer` is unreachable from UE4SS | not a `UFUNCTION`; call raises "TrivialObject" |

The world paths were re-enumerated from the CU3 containers rather than assumed:

```bash
python tools/iostore/dump_index.py --paks "<Content>/Paks" --filter "Levels/Halo1/Solo" --out solo.tsv
```

14,224 `.umap` entries, of which exactly 13 are root world packages (`<NAME>/<NAME>.umap`) — the
same A15/A30/A50/B30/B40/C10/C20/C45/D20/D40 plus Extra/E10/E20/E30 that CU2 had. The three places
that hardcode this list are now labelled CU3.

---

## What is still CU2-measured

These notes carry a CU2 build stamp and have **not** been re-measured against CU3. Their findings
may well still hold — most describe file formats, which move far less often than code addresses —
but nothing here should be cited as CU3-verified:

- [`halosimulation_tag_release.md`](halosimulation_tag_release.md) — offsets into the simulation
  DLL, which is a different binary on CU3. Most likely to have drifted.
- [`multiplayer_investigation_notes.md`](multiplayer_investigation_notes.md) — the runtime
  reflection passes, session state captures and Ghidra results. Its root world package list is the
  one part re-verified above.
- [`tag_data_pipeline.md`](tag_data_pipeline.md), [`tag_body_format.md`](tag_body_format.md),
  [`iostore_packaging.md`](iostore_packaging.md) — container and tag layout.
- [`ue_texture_format.md`](ue_texture_format.md), [`wwise_audio_format.md`](wwise_audio_format.md),
  [`blam_script.md`](blam_script.md).
- `defs/hce/tag-definitions.json` and `defs/hce/scripting.json`, both stamped CU2. These are
  *generated* corpora; relabelling them without regenerating would be a lie about their provenance.

### A caveat about the CU2 label

The CU3 update landed on **2026-08-01** — `signatures/README.md` records a signature breaking that
day. Several notes are stamped `CU2` but dated `2026-08-03`, and `crates/blam-live/src/lib.rs` says
"Verified 2026-08-03 against … CU2".

Work done on 2026-08-03 ran against CU3, whichever build the header names. The `CU2` string was
almost certainly copied forward rather than re-checked.

**Observed**, not Verified: this is an inference from the update date, not from a record of which
binary was installed at the time. The labels are left alone rather than rewritten on that inference
— relabelling on a guess would trade a known-stale stamp for a confident wrong one. Re-measuring
any of these against CU3 is what settles it, and `--verify` makes that cheap to start.
