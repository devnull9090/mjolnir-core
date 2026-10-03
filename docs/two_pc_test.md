# Two-PC multiplayer test

The first converted-map game with two real players. PC 1 hosts; PC 2 runs a
second Steam account. Both run the same MJOLNIR install, copied as a bundle
(`tools/mp/make_test_bundle.ps1`).

It answers, in order:

1. Does a second player join the host's fireteam from our lobby's INVITE
   FRIENDS, follow the host into a converted map, and play? Do kills between
   two players reach the kill feed and the scoreboard on both screens?
2. Does PlayFab accept a co-op lobby bigger than four
   ([fireteam_join_and_cap.md](fireteam_join_and_cap.md))?
3. What does the end of a match do to the fireteam? Today everyone lands on
   the main menu and the second player is out of the fireteam. Which way of
   ending a game causes it ([re/megalo_engine.md](re/megalo_engine.md),
   "Rounds, the end of a game, and the next map")?
4. Does the post-game screen and vote work across the fireteam?

## Setup

**Both PCs:**
- Steam is up to date (the same game build; CU4 when this was written).
- The two accounts are Steam friends, so the invite shows up.

**PC 2, once:**
1. Unzip the bundle.
2. Close the game.
3. Run `powershell -ExecutionPolicy Bypass -File .\install_test_bundle.ps1`.
   - It finds the game through Steam; otherwise pass
     `-Game "<...>\Halo Campaign Evolved"`.
   - Anything it overwrites is backed up in the game folder.
   - `-Uninstall` removes it all again.
4. Start the game from Steam. A UE4SS console window opens beside it; that is
   expected.
5. Sign in at "press start". The main menu should have **MULTIPLAYER** between
   CAMPAIGN and PLAY CO-OP.

## Phase 1: invite, join, play

1. **PC 1:** MULTIPLAYER → INVITE FRIENDS → **+ Invite** next to the second
   account.
2. **PC 2:** accept the invite (Steam overlay, or the game's invite toast).
   - **Expect:** PC 2 joins PC 1's fireteam. Both show FIRETEAM 2/4, and PC 1's
     lobby lists both players under PLAYERS.
3. **PC 1:** CHANGE MAP → Blood Gulch, game type Slayer → SELECT → START GAME.
   Use Slayer: the game type travels to the host's loader only, and a client
   would run its map's default (Slayer).
4. **Both:**
   - Do both load into Blood Gulch, spawn, and see each other?
   - Shoot each other a few times. Does the kill feed name the right killer,
     victim and weapon on both screens? Does Tab show both players with the
     right kills and deaths?
   - Pick up a health pack, take a vehicle, use a teleporter. Does each work
     for both players?
5. **PC 1:** quit to the menu. Does PC 2 follow, or get a message?

**Record, if anything fails:** which step, what each screen showed, and
PC 2's `...\Meteorite\Binaries\Win64\ue4ss\UE4SS.log`. Copy it to PC 1 before
PC 2 restarts the game, because each start overwrites it.

## Phase 2: a lobby bigger than four

The co-op lobby is created when the first invite goes out or the first player
joins. The host asks PlayFab for `maxMemberCount` = 4.
`tools/pe/lobby_size_hook.py` rewrites that number on PC 1, in the running
game only, and counts each time it fires.

1. **Both:** restart the game, so the next lobby is a new one.
2. **PC 1**, at the main menu and before inviting:
   `python tools/pe/lobby_size_hook.py --size 16`.
3. Repeat Phase 1, steps 1–2.
4. **PC 1:** `python tools/pe/lobby_size_hook.py --status`.

| Hook fired (`--status`) | PC 2 joined | Reading |
|---|---|---|
| 0 | either | The lobby came from another path; the hook proves nothing |
| ≥ 1 | yes | PlayFab accepted a 16-member lobby: the service-side cap is not 4 |
| ≥ 1 | no | Likely refused for its size. Run `--revert`, restart, and repeat once to rule out the hook itself |

The Party network, the Steam presence session's literal 4 and the
simulation's network check are separate caps. Reaching five or more players
needs those too, and more than two PCs to test.

## Phase 3: what a match end does to the fireteam

The bundle's Slayer is a short test game: **score to win 1, two rounds**.
The first kill ends round 1, and everyone should respawn on the same map.
The second kill ends the game, and about 15 s later the game returns to the
main menu. To get the normal Slayer back, reinstall the regular mods.

Both PCs log what the test needs to UE4SS.log:
- `[MJOLNIR Lobby] fireteam: <world> | fireteam <n> [<names>]` whenever the
  world or the fireteam changes;
- `[MJOLNIR Hud] round over: ...` and `game over: ...` with each player's
  kills and deaths.

Each test starts the same way: both PCs at the main menu, PC 2 in PC 1's
fireteam (Phase 1, steps 1–2; both show FIRETEAM 2/4). Then PC 1 starts
Blood Gulch, Slayer.

**A. The game's own end (score to win).**
1. One player kills the other. **Expect:** both respawn on Blood Gulch, and
   neither leaves the map.
2. A second kill. **Expect:** both return to the main menu.
3. **Record on each PC:** where it landed, the FIRETEAM count, and any
   message or toast.

**B. The host quits mid-match.** Only if A dropped PC 2. Re-invite, start
again, and before any kill PC 1 quits to the main menu from the pause menu.
Record the same things.

**C. The host leaves through the campaign flow.** Only if B also dropped
PC 2. Re-invite and start again. PC 1 runs
`FindFirstOf("BlamCampaignFlowGameSubsystem"):LeaveGame()` (`game_lua`).
Record the same things.

**After the tests:** copy PC 2's
`...\Meteorite\Binaries\Win64\ue4ss\UE4SS.log` to PC 1 before PC 2
restarts the game.

| Outcome | Reading |
|---|---|
| A keeps PC 2 | The return to the menu is harmless. The post-game screen and vote can live on the frontend, and START GAME carries on |
| A drops PC 2, and B or C keeps it | The end-of-game return leaves the session. End games ourselves through the path that keeps it |
| All three drop PC 2 | Any return to the menu breaks the fireteam. The next map has to start from inside the match (today that starts no game, see the Megalo notes) |

## Phase 4: the post-game screen and the vote

Phase 3 found the kick (the game's own return) and the fix (a seamless
return). Phase 4 tests the whole flow built on it
([multiplayer_postgame.md](multiplayer_postgame.md)). The bundle's Slayer
ends at **3 kills**, and its CTF at **1 capture**; both have 31 rounds, so
the game never ends on its own.

1. **Both:** PC 2 joins PC 1's fireteam. Once PC 1 opens MULTIPLAYER, PC 2
   should show our lobby (the host's map and game type, no START GAME)
   instead of CLIENT LOBBY.
2. **PC 1:** start Blood Gulch, Slayer.
3. **Play to 3 kills.** **Expect on both:** the final standings with the
   winner, "RETURNING TO THE LOBBY", and about 7 s later both on the
   POST-GAME screen with the same four options.
4. **PC 2:** vote for an option. **Expect:** its count goes up on both
   screens, and the footer reads "1 OF 2 VOTED".
5. **PC 1:** vote, or press START NOW. **Expect:** both screens show
   "NEXT / <map / game type>", and a moment later both travel into it.
6. **Once more:** play to 3 kills, and on the post-game screen PC 1 presses
   LOBBY. **Expect:** the vote closes on both, PC 1 is in the lobby, and PC 2
   is back in our lobby view.

**Record:** where it stops, and both UE4SS.logs. The lines to look for are
`[MJOLNIR Hud] round over`, `final standings shown`,
`[MJOLNIR Lobby] post-game: ...` and `fireteam: ...`.
