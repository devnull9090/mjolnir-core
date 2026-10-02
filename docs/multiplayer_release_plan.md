# Multiplayer release plan

Classic Halo CE maps as multiplayer in Halo: Campaign Evolved, from the hub
and the launcher, with games anyone can find and join. One PR at the end,
from `work/halo-ce-map-conversion-f72214`. Status as of 2026-10-01.

## Done (on the branch)

- **The maps:**
  - 20 classic maps convert to map packs (format v1,
    [map_distribution.md](map_distribution.md));
  - each map is its own single-BSP scenario
    ([ce_map_conversion.md](ce_map_conversion.md));
  - health packs, grenades and power-ups, CTF, lights and lens flares.
- **Our own UI:** cooked Widget Blueprints ([custom_ui.md](custom_ui.md)):
  - the lobby, map select and INVITE FRIENDS
    ([multiplayer_menu.md](multiplayer_menu.md));
  - the kill feed, respawn countdown, Tab scoreboard and team-only name tags
    ([multiplayer_hud.md](multiplayer_hud.md)).
- **Two PCs, two Steam accounts, verified:**
  - invite, join and play Slayer;
  - a client's sim is switched on its travel;
  - the client knows its own player index.
- **The game type reaches clients** through the insertion point index
  (needs the rebuilt maps; Blood Gulch and Danger Canyon have it).
- **Research:** joins need only a PlayFab lobby connection string. The caps
  toward 16 are mapped ([fireteam_join_and_cap.md](fireteam_join_and_cap.md)).

## To do, in order

1. **Verify CTF across two PCs** (patch 4), then **Phase 2**: a 16-member
   lobby request ([two_pc_test.md](two_pc_test.md)).
2. **Rebuild all 20 maps** with every fix (scratchpad `convert_all.sh`, CPU
   pinned), re-pack, re-register. Spot-check a few in game.
3. **The launcher installs everything multiplayer needs:**
   - UE4SS, the mods and mods.txt;
   - the runtime and UI containers;
   - map packs, then registration;
   - updates and uninstall. Steam first, Game Pass where the paths allow.
4. **Hub maps:**
   - a Maps section with the 20 official maps as defaults and community
     uploads beside them;
   - an upload, validation and review queue;
   - packs in R2 (game-derived bytes never in git).
5. **Lobby search** (hub Worker + D1, polled):
   - hosts register and heartbeat a game: map, game type, players and max,
     version, region, connection string;
   - FIND GAMES lists and filters by map, game type, players and ping. Ping
     is an estimate from each side's Cloudflare location until players can
     probe each other.
   - A native piece hands a chosen game's connection string to the game's
     own join path.
6. **End of game and map rotation:** built 2026-10-02, solo-verified, two
   PCs next ([multiplayer_postgame.md](multiplayer_postgame.md)):
   - a match is the first of 31 rounds, so the game never runs its own
     return to the menu, which drops every client from the fireteam;
   - final standings in the map, then the host's seamless travel back to
     the menu with the fireteam still connected;
   - a post-game screen with the standings and a vote on the next game;
     the host starts the winner;
   - fireteam clients see our lobby instead of CLIENT LOBBY.
7. **The player cap toward 16**, after Phase 2:
   - the lobby size;
   - the presence session's literal 4;
   - the Party limits;
   - GameSession;
   - the sim's network check.
8. **Release:**
   - version bumps (MJOLNIRHud new; Lobby, LevelLoader and ConsoleEnabler
     changed; the CLI);
   - changelog entries;
   - luacheck clean;
   - R2 uploads;
   - the PR.

## Open questions

- PlayFab may refuse lobbies larger than four (Phase 2 answers it).
- Where the sim raises its network co-op refusal, and the Party ini values.
- Whether a client's Megalo variant comes from its own file or from the host.
  The insertion point slot keeps both machines on the same game type either
  way.
- Game Pass: the PlayFab path should match; UE4SS on the Game Pass binary is
  untested.
