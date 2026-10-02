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
