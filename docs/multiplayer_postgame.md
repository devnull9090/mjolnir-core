# The end of a match: standings, the vote, the next game

A custom game ends with everyone still together: the final standings in the
map, then a post-game screen on the menu where the fireteam votes on the next
game, and the host starts it. Nobody leaves the fireteam. Status as of
2026-10-02.

## What the game does on its own, and why we don't use it

- A Megalo variant's `EndRound` (action 21) with rounds left raises
  `round_over` and resets the round in place: everyone respawns on the same
  map with no travel. At the last round it raises `game_over`. About 15 s
  later the host goes back to the menu.
- That return sends every client
  `ClientTravelInternal("/Game/Levels/UI/Frontend/Frontend", TRAVEL_Absolute,
  bSeamless=false)` (two PCs, 2026-10-02). Each client loads its own menu and
  disconnects, and so leaves the fireteam. This is Unreal's "host returns
  to the main menu" behaviour, not an error.
- A *seamless* travel to the frontend keeps the clients:
  `servertravel /Game/Levels/UI/Frontend/Frontend` on the host sends
  `b=2 c=true`, and the client arrives in the client lobby, still connected.
  The host swaps its controller for a `BP_FrontendPlayerController` and can
  start the next game from there as usual.
- Switching straight to the next map from inside a map does not start a game
  under Megalo ([re/megalo_engine.md](re/megalo_engine.md), "Rounds, the end
  of a game, and the next map"). That is why the vote happens on the menu.

So MJOLNIR's variants give a game 31 rounds (`mjolnir megalo write
--rounds`, default 31), and a match is the first round. The game never
reaches `game_over`, and the host ends the match itself.

## The flow

1. **In the map** (MJOLNIRHud): the first `round_over` is the end. Every
   machine freezes its tallies, shows the scoreboard as the final standings
   (winner, game type, map, "RETURNING TO THE LOBBY"), and writes them to
   `MJOLNIRHud\last_match.txt` (`Scoreboard.results`). The round the game
   resets behind the standings does not score.
2. **The host** waits 7 s (`FINAL_SECONDS`), then runs the seamless
   `servertravel` to the frontend. A `game_over` (an older 1-round variant)
   makes it travel at once, before the game's own return.
3. **On the menu** (MJOLNIRLobby), the host finds fresh standings (under
   180 s old, not shown yet) and pushes `WBP_MJOLNIRPostGame`. It holds the
   standings and the vote on four options: the same game again, then other
   maps in a random order with the same game type where they have it.
4. **The vote** lasts 20 s. Everyone votes on their own copy of the screen.
   - When it ends, or the host presses START NOW, the most votes win; a tie
     goes to the earlier option. With no votes, the rotation moves on to the
     second option.
   - The host starts the winner through the same calls as START GAME, and
     the fireteam follows into the map.
   - LOBBY, or Back on the host, ends the vote and opens the lobby to pick
     by hand.
5. **Joiners** get our lobby instead of the game's CLIENT LOBBY whenever the
   host is in it: the host's map and game type, with START GAME, CHANGE MAP
   and GAME TYPE hidden.

Each machine shows its own standings. They agree because every machine
counted the same incidents ([multiplayer_hud.md](multiplayer_hud.md)).

## Messages between the host and its fireteam

There is no replicated class of our own. Two of the engine's
`PlayerController` RPCs carry the messages (`mods/MJOLNIRLobby/Scripts/net.lua`):

| Direction | RPC | Why it is safe |
|---|---|---|
| client to host | `ServerExecRPC(Msg)` | Its body is compiled out of Shipping builds. The host's hook reads `Msg`; `self` is the sender's controller. |
| host to client | `ClientMessage(S, Type, MsgLifeTime)`, `Type = "MJOLNIR"` | The engine prints only the `None` and `Say` types. The client's hook reads `S`. |

A message is `MJOLNIR|<verb>|<field>...`:

| Verb | From | Fields |
|---|---|---|
| `vote` | host, every second | id, seconds left, options (`CODE:mode:again;...`), counts, chosen option |
| `ballot` | anyone, the host included | id, option |
| `cancel` | host | id |
| `lobby` | host, while its lobby is up | map code, game type |

Hooks on both functions (native, with parameters) ran on CU4 without trouble
(2026-10-02). The host never sends a client RPC to a controller with no
player or player state: a controller left over from the previous world would
run it locally.

## Files

- `mods/MJOLNIRHud/Scripts/main.lua`: `finishMatch`, the final standings, the
  host's travel.
- `mods/MJOLNIRHud/Scripts/scoreboard.lua`: `Board.winner`, `Board.results`.
- `mods/MJOLNIRLobby/Scripts/main.lua`, "After a match": the post-game screen,
  the vote and the client lobby.
- `mods/MJOLNIRLobby/Scripts/net.lua`: the messages.
- `unreal/MJOLNIRMaterials/Scripts/build_mjolnir_ui.py`, `build_post_game`:
  `WBP_MJOLNIRPostGame`, in chunk 984 with the other screens.
- `mods/MJOLNIRLevelLoader/Scripts/main.lua`: a travel that names no scenario
  (the way back to the menu) leaves the Megalo patches alone. Restoring them
  under a client's running Megalo game froze it mid-travel.

## Open

- Two PCs: the vote end to end (a client's ballot reaching the host, every
  screen following the outcome) and the client lobby. Steps:
  [two_pc_test.md](two_pc_test.md), Phase 4.
- A client that joins during the vote sees it from the next broadcast; one
  that joins mid-match is not handled yet.
- The tallies are HUD-side. Reading the Megalo score itself would make a
  client's standings authoritative.
