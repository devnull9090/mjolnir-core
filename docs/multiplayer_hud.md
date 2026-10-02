# Multiplayer HUD: kill feed, respawn countdown, scoreboard

`mods/MJOLNIRHud` draws the HUD for the classic CE maps that
MJOLNIRLevelLoader runs under the simulation's Megalo engine. It uses
MJOLNIR's own cooked widgets ([custom_ui.md](custom_ui.md)):

- **`WBP_MJOLNIRKillFeed`**: six lines at the left of the screen, newest at
  the bottom, each fading out after six seconds. Lines that name the local
  player are gold. It also shows the respawn countdown in the middle.
  A persistent score strip sits at the top center above the native shield
  bar: Red/Blue scores for team modes, or YOU/LEADER for free-for-all,
  including the score to win. The local team is marked `/ YOU`. Opening
  the full scoreboard hides the strip until Tab/View is released.
- **`WBP_MJOLNIRScoreboard`**: shown while **Tab** (or the gamepad's View
  button) is held. It has the game type and map, the score to win (or the
  team scores in CTF and Team Slayer), and up to 16 players with score, kills
  and deaths. Team games have separate Red and Blue sections, with team
  totals and player counts; players without a reported team appear under
  Awaiting assignment. Each section is sorted by score. A gold YOU marker
  identifies the local player in addition to the row highlight.

The console opens on `~` only. `MJOLNIRConsoleEnabler` takes Tab out of
`InputSettings.ConsoleKeys`, as Halo CE on PC had it.

## Where the data comes from

The simulation's incidents reach the game state's
`BPC_MeteoriteIncidentHandlerComponent.OnIncident_Event` as a `BlamIncident`:

| Field | Use |
|---|---|
| `Name` | the incident (see below) |
| `CausePlayerAbsoluteIndex`, `EffectPlayerAbsoluteIndex` | killer and victim; -1 for none |
| `CauseObjectActor`, `EffectObjectActor` | the bipeds |
| `DamageReportingInfo.Modifier` | `EBlamDamageReportingModifier`: Headshot, SilentMelee, CollisionDamage, AttachedDamage, FancyAssassination, ArmorAmplified, ArmorMitigated |
| `DamageReportingInfo.Type` | a gameplay tag naming the weapon: `Blam.DamageReporting.Type.AssaultRifle`, `.FragGrenade`, … (`.Invalid` without damage) |
| `CustomValue` | per incident; `flag_scored` carries the captured flag's team |

A player index becomes a name through the game state's `PlayerArray`. Each
`BlamPlayerState` has a `BlamPlayerStateComponent.BlamAbsolutePlayerIndex`
and `GetPlayerName()`. Use `GameplayStatics.GetPlayerController(…, 0)` for
the local controller: `FindAllOf("PlayerController")` lists the frontend's
leftover controllers first.

## What arrives (Blood Gulch Slayer, 2026-10-01)

Measured with a split-screen second player (`CreatePlayer` at the main menu),
killed by the first.

A kill by player 0 of player 1, one tick, in this order:

```text
first_blood  technician_comm  headshot_kill  headshot_comm
Kill  auto_kill  auto_comm  death
lost_lead (1)  gained_lead (0)
```

Notes on that sequence:

- `Kill` is capitalised, unlike every other incident name.
- Every incident in it carries both players, the modifier and the damage
  type. The medal and commendation incidents (`*_kill`, `*_comm`,
  `first_blood`, the lead changes) are there for a medal display later.
- A grenade that killed both players raised `suicide` + `death` for the
  thrower and `Kill` + `grenade_kill` + `grenades_comm` + `death` for the
  other player.

After a death: `respawn_tick` three times, a second apart, then
`respawn_final_tick` and `player_spawn`. The cause is the respawning
player. The HUD counts the ticks down from 3.

Not seen yet:

- `player_joined`, `player_quit` and `player_booted_player`. They are for
  networked players; the host quitting raised nothing. The HUD has feed lines
  ready for them.
- The `*_comm` incidents carry a `CustomString` not read yet.

## Scores

Scores live only in the simulation, so the HUD keeps its own tallies from
the incidents, by the rules of the variants MJOLNIR writes
(`crates/blam-megalo`):

- **Slayer:** a point per `Kill` of another player; suicides cost nothing.
- **CTF:** a point to the team per `flag_scored`. The captured flag's team
  arrives as the incident's value, so the point goes to the other team.
- **Team Slayer presentation:** shows kills in the score column and totals
  the observed kill incidents by the killer's reported team. Points stay
  with the team that earned them when a player switches or leaves. The
  Team Slayer variant still needs to be installed to offer this mode.

The team reader accepts only Red and Blue from the simulation's
`BlamGameTeam`. It retries a spawn's biped each second because team
assignment can arrive after the spawn incident. Kill/death actors also
refresh known teams. No player index or roster order implies a team.

The HUD still tallies incidents observed during this session; it cannot
recover earlier scores for a late join. This presentation does not add a
replicated authoritative score reader.

## Building and checking

Install the rebuilt UI chunk and the updated Lobby/Hud Lua scripts together;
the scoreboard now has 19 visual rows (16 players and three possible team
headings). `Scripts/scoreboard.lua` must accompany the HUD's `main.lua`.
See [custom_ui.md](custom_ui.md) for the build and cook commands.

`tools/tests/test_multiplayer_ui.lua` exercises grouping, a full and uneven
roster, sorting, CTF captures, Team Slayer kills, delayed assignment,
switching teams, leaving, the live score strip (including tied/leaving
leaders), and holding/releasing the board. Run from the root
with Lua 5.4 or Python with lupa:

```powershell
python -c "from lupa import LuaRuntime; LuaRuntime().execute(open('tools/tests/test_multiplayer_ui.lua').read())"
```

## Not done yet

- Split screen: the widgets go on the whole viewport, not on each player's
  half.
- Medals.
- The game's fonts.
