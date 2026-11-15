# Medals

Halo Reach and Halo 3 show medals for multi-kills, sprees, headshots,
revenge kills and the like. CU4's simulation keeps Reach's whole medal
system: the rules that decide when one is earned, and a 116-entry medal
table. It already tells the UE side about every one of them, by name,
through the same incident hook the kill feed uses. Nothing has to be found
in the binary to display or count them.

Researched 2026-11-10 from the shipped tags (`mjolnir values`) and the hub's
recorded public matches (172 matches, read-only query of `match_events`).

## Where the rules live

Three tags in `globals/`:

| Tag | Group | What it holds |
|---|---|---|
| `incident/game_incident` | `incident_globals_definition` (`ingd`) | 418 incidents. Each says how it is raised, which other incidents it hides, and per game mode which engine event, medal and achievement it answers with. 100 of them award a medal in multiplayer. |
| `medals` | `game_medal_globals` (`gmeg`) | 116 medals: string id name and description, class (special, role spree, spree, multikill, objectives, circumstance, finesse), rank, a sprite index. |
| `incident_properties` | `incident_global_properties_definition` (`igpd`) | Timings: multiplayer multi-kill window 4 s (campaign and Firefight 1.5 s), low health 0.3, lifesaver damage 1.7, avenger dead time 2 s. Lists the six `ingd` tags. |

The other `ingd` tags (`survival_game_incident`, `achievements`,
`collectibles`, `game_activities`, `mission_progression`) cover Firefight,
achievements and the campaign.

An incident is raised one of three ways:

- **By engine code**: `Kill`, `assist`, `headshot_kill`, `revenge_kill`,
  `killjoy`, `close_call`, `first_blood`, the hijacks and the like.
- **As a specialisation of another incident**: a `kill` whose damage type
  is the sniper rifle also raises `sniper_kill`; sword, hammer, laser and
  shotgun work the same way.
- **By an accumulator** counting other incidents: `multikill_xN` is N
  kills, each within 4 s of the last; `N_in_a_row` is N kills without
  dying; `sniper_5x`, `splatter_10x` and the rest are N of that kill
  without dying.

Megalo scripts can raise incidents too (`SendIncident`). That is how Reach's
objective medals worked; see [Gaps](#gaps).

## What reaches Lua

`BPC_MeteoriteIncidentHandlerComponent.OnIncident_Event` gets a
`BlamIncident` (fields in [multiplayer_hud.md](../multiplayer_hud.md#where-the-data-comes-from)).
Facts that matter for a medal display:

- **It carries the incident name, not the medal.** `close_call` is the
  Berserker medal, `revenge_kill` is Revenge, `sniper_headshot_kill` is
  the Sniper medal. The table below is the mapping.
- **Mode gating does not stop delivery.** Several medals answer only in
  matchmaking (`first_blood`, `revenge_kill`, `killjoy`), yet in custom
  games they arrive all the time (`revenge_kill` 304 times). The tag's
  per-mode responses decide what the sim's own HUD and stats would do; they
  do not filter the hook.
- **Suppression does not stop delivery either.** The tag says a sniper
  headshot hides the plain headshot, but all 191 recorded
  `sniper_headshot_kill` came with a `headshot_kill` at the same moment.
  A display has to apply the "Hides" column itself or one sniper headshot
  shows two medals (and the hub counts two).
- **Order:** a kill's medals come in the same tick, before the `Kill`
  line ([multiplayer_hud.md](../multiplayer_hud.md#what-arrives-blood-gulch-slayer-2026-10-01)).
- **Fireteam clients** get few incidents of their own; the host relays
  what the HUD shows. Every medal added to the display must be added to the
  relay's set too.
- **No medal art ships.** The only medal texture in the paks is ours
  (`T_MJHud_Medal`); the `medals` tag's sprite indices point at Reach
  bitmaps CE never had. The names' localised strings (`*_description`) are
  in the string-id table, but the HUD would need its own titles anyway.

## Every multiplayer medal

"Hides" is the tag's suppression list (apply it client-side). "Seen" counts
the incident across the 172 recorded public matches.

| Class | Incident (what Lua sees) | Medal (tag name) | Raised by | Hides | Seen in 172 matches |
|---|---|---|---|---|---|
| objectives | `vip_kill` | `medal_vip_player_kill_vip` (not in the medal table) | engine code | `kill` | - |
| circumstance | `close_call` | `berserker` | engine code | `kill` | 38 |
| circumstance | `driver_assist_gunner` | `medal_driver_assist_gunner` | engine code | `assist` | 2 |
| circumstance | `highjack` | `medal_vehicle_hijack` | engine code |  | 10 |
| circumstance | `kill_from_the_grave` | `medal_deadplayer_kill_player` | engine code | `kill` | 20 |
| circumstance | `killjoy` | `medal_player_kill_spreeplayer` | engine code | `kill` | 44 |
| circumstance | `lifesaver` | `lifesaver` | engine code |  | 1 |
| circumstance | `opportunist_kill` | `opportunist` | engine code | `kill` | 115 |
| circumstance | `revenge_kill` | `revenge` | engine code | `kill` | 304 |
| circumstance | `shotgun_kill_sword` | `medal_shotgun_kill_sword` | engine code | `kill` | - |
| circumstance | `skyjack` | `medal_aircraft_hijack` | engine code |  | 4 |
| finesse | `finishing_move_kill` | `assassination` | engine code | `kill`, `yoink` | - |
| finesse | `firebird` | `firebird` | engine code |  | - |
| finesse | `laser_kill` | `medal_spartanlaser_kill` | engine code (kill with spartan laser) | `kill` | - |
| finesse | `melee_kill` | `medal_bash_kill` | engine code | `kill`, `kill_as_juggernaut` | 207 |
| finesse | `pull_kill` | `pull_kill` | engine code | `kill` | - |
| finesse | `second_wind` | `second_wind` | engine code |  | - |
| finesse | `showstopper` | `showstopper` | engine code | `kill` | - |
| finesse | `sniper_headshot_kill` | `medal_sniper_kill` | engine code (kill with sniper rifle) | `headshot_kill`, `kill` | 191 |
| finesse | `splatter_kill` | `medal_vehicle_impact_kill` | engine code | `kill` | 33 |
| finesse | `sprinting_kill` | `sprinting_kill` | engine code |  | 27 |
| finesse | `sticky_grenade_kill` | `medal_stickygrenade_kill` | engine code | `grenade_kill` | 7 |
| finesse | `yoink` | `yoink` | engine code | `kill` | - |
| multikill | `multikill_x2` | `medal_multikill_2` | 2x `kill` within 4 s of each other |  | 81 |
| multikill | `multikill_x3` | `medal_multikill_3` | 3x `kill` within 4 s of each other |  | 6 |
| multikill | `multikill_x4` | `medal_multikill_4` | 4x `kill` within 4 s of each other |  | - |
| multikill | `multikill_x5` | `medal_multikill_5` | 5x `kill` within 4 s of each other |  | - |
| multikill | `multikill_x6` | `medal_multikill_6` | 6x `kill` within 4 s of each other |  | - |
| multikill | `multikill_x7` | `medal_multikill_7` | 7x `kill` within 4 s of each other |  | - |
| multikill | `multikill_x8` | `medal_multikill_8` | 8x `kill` within 4 s of each other |  | - |
| multikill | `multikill_x9` | `medal_multikill_9` | 9x `kill` within 4 s of each other |  | - |
| multikill | `multikill_x10` | `medal_multikill_10` | 10x `kill` within 4 s of each other |  | - |
| objectives | `ball_carrier_kill` | `medal_oddball_player_kill_oddball` | engine code |  | - |
| objectives | `bomb_carrier_kill` | `medal_assault_player_kill_carrier` | engine code | `kill` | - |
| objectives | `bomb_planted` | `medal_assault_bomb_planted` | engine code |  | - |
| objectives | `flag_scored` | `medal_ctf_flag_captured` | engine code |  | 19 |
| objectives | `flagcarrier_kill` | `medal_ctf_flag_player_kill_carrier` | engine code | `kill` | - |
| objectives | `inf_last_man` | `medal_infection_survive` | engine code |  | - |
| objectives | `infection_survive` | `medal_infection_survive` | engine code |  | - |
| objectives | `juggernaut_kill` | `medal_juggernaut_player_kill_juggernaut` | engine code | `kill` | - |
| objectives | `juggernaut_5x` | `medal_juggernaut_5` | 5x `kill_as_juggernaut` without dying | `gravity_hammer_5x` | - |
| objectives | `juggernaut_10x` | `medal_juggernaut_10` | 10x `kill_as_juggernaut` without dying | `gravity_hammer_10x` | - |
| objectives | `juggernaut_15x` | `medal_juggernaut_15` | 15x `kill_as_juggernaut` without dying | `gravity_hammer_15x` | - |
| objectives | `kill_with_flag` | `medal_ctf_flag_carrier_kill_player` | engine code (kill with flag melee damage) | `kill`, `melee_kill` | - |
| objectives | `kill_with_oddball` | `medal_oddball_carrier_kill_player` | engine code (kill with ball melee damage) | `kill`, `melee_kill` | - |
| role spree | `assist_5x` | `assist_5` | 5x `assist` without dying | `assist` | - |
| role spree | `assist_10x` | `assist_10` | 10x `assist` without dying | `assist` | - |
| role spree | `assist_15x` | `assist_15` | 15x `assist` without dying | `assist` | - |
| role spree | `gravity_hammer_5x` | `hammer_kill_5x` | 5x `hammer_kill` without dying |  | - |
| role spree | `gravity_hammer_10x` | `hammer_kill_10x` | 10x `hammer_kill` without dying |  | - |
| role spree | `gravity_hammer_15x` | `medal_hammerkill_15` | 15x `hammer_kill` without dying |  | - |
| role spree | `infection_5x` | `medal_zombie_5` | 5x `infection_kill` without dying |  | - |
| role spree | `infection_10x` | `medal_zombie_10` | 10x `infection_kill` without dying |  | - |
| role spree | `infection_15x` | `medal_zombie_15` | 15x `infection_kill` without dying |  | - |
| role spree | `koth_spree` | `medal_koth_5` | 5x `kill_within_hill` without dying | `kill` | - |
| role spree | `laser_5x` | `laser_5` | 5x `laser_kill` without dying |  | - |
| role spree | `laser_10x` | `laser_10` | 10x `laser_kill` without dying |  | - |
| role spree | `laser_15x` | `laser_15` | 15x `laser_kill` without dying |  | - |
| role spree | `shotgun_5x` | `medal_shotgun_5` | 5x `shotgun_kill` without dying |  | 5 |
| role spree | `shotgun_10x` | `medal_shotgun_10` | 10x `shotgun_kill` without dying |  | 1 |
| role spree | `shotgun_15x` | `medal_shotgun_15` | 15x `shotgun_kill` without dying |  | - |
| role spree | `sniper_5x` | `medal_sniper_5` | 5x `sniper_kill` without dying |  | 9 |
| role spree | `sniper_10x` | `medal_sniper_10` | 10x `sniper_kill` without dying |  | 1 |
| role spree | `sniper_15x` | `medal_sniper_15` | 15x `sniper_kill` without dying |  | - |
| role spree | `splatter_5x` | `medal_splatter_5` | 5x `splatter_kill` without dying |  | - |
| role spree | `splatter_10x` | `medal_splatter_10` | 10x `splatter_kill` without dying |  | - |
| role spree | `splatter_15x` | `medal_splatter_15` | 15x `splatter_kill` without dying |  | - |
| role spree | `sticky_grenade_5x` | `sticky_grenade_5x` | 5x `sticky_grenade_kill` without dying |  | - |
| role spree | `sticky_grenade_10x` | `sticky_grenade_10x` | 10x `sticky_grenade_kill` without dying |  | - |
| role spree | `sticky_grenade_15x` | `medal_sticky_15` | 15x `sticky_grenade_kill` without dying |  | - |
| role spree | `sword_5x` | `medal_sword_5` | 5x `sword_kill` without dying |  | - |
| role spree | `sword_10x` | `medal_sword_10` | 10x `sword_kill` without dying |  | - |
| role spree | `sword_15x` | `medal_sword_15` | 15x `sword_kill` without dying |  | - |
| role spree | `wheelman_5x` | `wheelman_5` | 5x `driver_assist_gunner` without dying | `driver_assist_gunner`, `assist_5x` | - |
| role spree | `wheelman_10x` | `wheelman_10` | 10x `driver_assist_gunner` without dying | `driver_assist_gunner`, `assist_10x` | - |
| role spree | `wheelman_15x` | `wheelman_15` | 15x `driver_assist_gunner` without dying | `driver_assist_gunner`, `assist_15x` | - |
| role spree | `wingman_5x` | `wingman_5x` | 5x `wingman_spawn` without dying |  | - |
| role spree | `wingman_10x` | `wingman_10x` | 10x `wingman_spawn` without dying |  | - |
| role spree | `wingman_15x` | `wingman_15x` | 15x `wingman_spawn` without dying |  | - |
| role spree | `zombie_kill_5x` | `medal_survivor_5` | 5x `zombie_kill_kill` without dying |  | - |
| role spree | `zombie_kill_10x` | `medal_survivor_10` | 10x `zombie_kill_kill` without dying |  | - |
| role spree | `zombie_kill_15x` | `medal_survivor_15` | 15x `zombie_kill_kill` without dying |  | - |
| special | `assassination_kill` | `medal_bashbehind_kill` | engine code | `melee_kill`, `kill` | 71 |
| special | `assist` | `assist` | engine code |  | 191 |
| special | `avenger` | `avenger` | engine code |  | 2 |
| special | `emp_assist` | `emp_assist` | engine code |  | - |
| special | `extermination` | `medal_extermination` | engine code |  | - |
| special | `first_blood` | `first_blood` | engine code | `kill` | 46 |
| special | `headshot_kill` | `headshot_kill` | engine code | `kill` | 422 |
| special | `perfection` | `medal_perfection` | engine code |  | - |
| special | `skullamanjaro` | `skullamanjaro` | engine code |  | - |
| special | `supercombine_kill` | `supercombine_kill` | engine code (kill with needler, needle rifle) |  | 6 |
| spree | `5_in_a_row` | `medal_kill_spree_5` | 5x `kill` without dying |  | 52 |
| spree | `10_in_a_row` | `medal_kill_spree_10` | 10x `kill` without dying |  | 6 |
| spree | `15_in_a_row` | `medal_kill_spree_15` | 15x `kill` without dying |  | 2 |
| spree | `20_in_a_row` | `medal_kill_spree_20` | 20x `kill` without dying |  | - |
| spree | `25_in_a_row` | `medal_kill_spree_25` | 25x `kill` without dying |  | - |
| spree | `30_in_a_row` | `medal_kill_spree_30` | 30x `kill` without dying |  | - |
| spree | `35_in_a_row` | `medal_kill_spree_35` | 35x `kill` without dying | `kill` | - |
| spree | `40_in_a_row` | `medal_kill_spree_40` | 40x `kill` without dying |  | - |

## What MJOLNIR does with them

- **HUD** (MJOLNIRHud 0.21.0, MJOLNIRLobby 0.27.0): every medal above.
  The catalogue, the hiding and the order live in C
  (`native/lobby/medals_core.h`, tests in `test_medals.c`); the HUD's one
  incident hook and the drawing stay in Lua, because the hook also feeds the
  kill feed and the match log and a bot's incidents name it by its actor
  ([multiplayer_hud.md](../multiplayer_hud.md)). Multi-kills, sprees, weapon
  sprees, objective medals and `first_blood` are feed lines; the "how" and
  "what was going on" medals are the earner's callout only.
- **Hub** (`hub/src/lib/api/player-record.ts`, `MEDAL_TYPES`): counts the
  medals for the player's medal case, with a headshot that came with a
  sniper headshot (and a melee kill that came with a beat down) counted
  once.
- **Sounds** (`MJOLNIRLevelLoader/events.json`): announcer lines for the
  sprees. `10_in_a_row` plays the "running riot" line while the HUD calls it
  Killing Frenzy, as Reach's names go.

## Gaps

- **Not seen yet because the sandbox lacks the weapon**: sword, gravity
  hammer and Spartan laser kills and sprees; `shotgun_kill_sword`.
  Converted maps with those weapons would raise them as is.
- **Rare**: Overkill and up, Rampage (20) and up. Nothing to do.
- **Objective medals need our variants**: `flagcarrier_kill`,
  `ball_carrier_kill`, `bomb_carrier_kill`, `juggernaut_kill`,
  `vip_kill`, `kill_within_hill` (and so `koth_spree`), the infection
  ones. Our scripts (`crates/blam-megalo/src/ctf.rs` and friends) send flag,
  hill and juggernaut incidents but none of these. Adding a `SendIncident`
  where a carrier dies would make the engine do the rest.
  `kill_with_flag`/`kill_with_oddball` are specialisations of melee kills
  with the flag or ball's melee damage type, which CE's flag may not use.
