# AI in a Megalo (multiplayer) game

Issue #247 (bots to fill lobbies), route B: can the simulation's own AI play in
a Slayer match? Spike run 2026-10-25 on CU4, one PC, host only.

## The test map

`examples/levels/bot_b40_beach.level.json`, baked as the standalone codename
`BOT`:

```bash
mjolnir level bake examples/levels/bot_b40_beach.level.json --standalone BOT --install-test
```

It is B40 (The Silent Cartographer) under the Megalo engine on B40's **stock**
BSP 8 (`bsp_01_1_start`, the Forerunner interior at insertion point 0), with
the mission's squads, squad groups, zones, AI objectives, character palette and
`ai pathfinding data` kept (`clear.squads: false`, none of those in
`clear.blocks`). No `single_bsp`: squad spawn points name their BSP by index
(`structure bsp #8`) and the single-BSP pass does not remap them. Four player
starts and `player_spawn` scenery sit on B40's own insertion-0 starts.
Only four squads stand on BSP 8: `insertion_cov_grunts_flee`,
`insertion_cov_grunts_interior`, `insertion_cov_elites`,
`pelican_arrival_squad`.

Hosted with `mjolnir_auto host BOT slayer private`. AI is placed with
`mjolnir_sim_script` lines (MJOLNIRLobby's DLL, sim thread), never with the
Blam console from Lua mid-game.

The script path reports nothing back, so results were read with colour fades:
`(if (> (ai_living_count insertion_cov_elites) 0) (fade_out 0 1 0 5) (fade_out 0 0 1 5))`
turns the screen green or blue.

## Findings

1. **`ai_place` is a no-op in a multiplayer game.** Its core
   (`sim+0xfd810`, called from the `ai_place` evaluator `sim+0x1c0240`) runs
   only when the game options' mode byte (`[TLS+0x60]+0x10`, the same options
   block whose `+0x15f0` holds the live variant) is 1 (campaign) or 2
   (Firefight, with options `+0` or `+1` set). A Megalo match is mode 3, so
   the squad is never placed. `ai_enabled` is true throughout.

   ```text
   sim+0xfd839  80 78 10 01   cmp byte [rax+10h], 1
   sim+0xfd83d  74 22         jz  +0x22   ; campaign: place
   ...                                    ; else mode 2 check, else return
   ```

   Patching `sim+0xfd83d` `74 22` → `eb 22` (always place) makes `ai_place`
   work in the Megalo game. No other gate was needed for what follows.

2. **Placed AI think, path and fight under Megalo.** Elites and Grunts spawned
   at their squad spawn points, walked tens of metres through the BSP towards
   the player (pathfinding from the kept `ai pathfinding data`), shot, and
   killed the player. The Pelican of `pelican_arrival_squad` flew in. Placing
   the same squad again adds its members again.

3. **Incidents carry AI kills both ways**, through the same
   `BPC_MeteoriteIncidentHandlerComponent:OnIncident_Event` the HUD hooks:

   | Event | Cause | Effect |
   |---|---|---|
   | AI kills the player: `death` (no `Kill`) | index −1, `CauseObjectActor` = `BP_GruntBipedActor_C`, damage `PlasmaPistol` | index 0, `BP_SpartansBipedActor_C` |
   | player kills AI: `Kill`, `auto_kill`, `kill_elite` / `kill_grunt`, `kill_enemy_leader`, `headshot_kill` ... | index 0, the player's biped, damage `AssaultRifle` | index −1, `BP_EliteBipedActor_C` / `BP_GruntBipedActor_C` |

   Megalo respawned the dead player after the variant's 5 s, with the usual
   `respawn_tick` / `player_spawn` incidents.

So a bot's kills and deaths can be told apart from players' by player index
−1 and recognised by their biped actor. A scoreboard row for a bot is
bookkeeping in the HUD's match model, keyed by the AI biped, with no sim work.

## Open

- **Megalo score**: not read. The MJOLNIR HUD never started on BOT because the
  map runs in B40's own Unreal world and the HUD keys its match by world name,
  and `mjolnir live players` has no score. Slayer's kill trigger fires on a
  *player* killed, so AI kills likely do not score; a score-to-win end may need
  the HUD's own count or a variant change.
- **Fireteam clients**: whether a joiner sees and fights the host's AI in the
  distributed sim is untested (needs the two-PC setup, docs/two_pc_test.md).
- **AI teams**: B40's Covenant are all on one team, so they fight players, not
  each other. Free-for-all bots need a team per bot or
  `berserk_hostile_to_all`.
- **Looks**: no shipped Spartan AI character (`spartans_ai` ships only as a
  stimuli character). A `new-tag` clone of `trooper` pointed at the
  `spartans` biped is the likely route.
- **Converted maps have no pathfinding of their own**: their BSP 8 replaces
  B40's geometry, but `ai pathfinding data[8]` is still B40's. Bots on
  converted maps need pathfinding data generated for the new BSP.
