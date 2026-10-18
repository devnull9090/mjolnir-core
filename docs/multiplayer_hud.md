# Multiplayer HUD: kill feed, respawn countdown, scoreboard

`mods/MJOLNIRHud` draws the HUD for the classic CE maps that
MJOLNIRLevelLoader runs under the simulation's Megalo engine. It uses
MJOLNIR's own cooked widgets ([custom_ui.md](custom_ui.md)):

- **`WBP_MJOLNIRKillFeed`**: the kill feed at the bottom left, the medal
  callout and the respawn countdown in the middle, and the score bars at the
  top (see [The kill feed](#the-kill-feed) below). The score bars sit above
  the native shield bar: Red/Blue for team modes, or YOU/LEADER for
  free-for-all, each filling toward the score to win, with the round clock
  between them. The local team is marked `/ YOU`. Opening the full
  scoreboard hides the bars until Tab/View is released.
- **`WBP_MJOLNIRScoreboard`**: shown while **Tab** (or the gamepad's View
  button) is held. It has the game type and map, the score to win (or the
  team scores in CTF and Team Slayer), and up to 16 players with score, kills
  and deaths. Team games have separate Red and Blue sections, with team
  totals and player counts; players without a reported team appear under
  Awaiting assignment. Each section is sorted by score. A gold YOU marker
  identifies the local player in addition to the row highlight.

- **`WBP_MJOLNIRChat`**: match chat, above the kill feed (see
  [Chat](#chat) below).

The console opens on `~` only. `MJOLNIRConsoleEnabler` takes Tab out of
`InputSettings.ConsoleKeys`, as Halo CE on PC had it.

## Chat

`Scripts/chat.lua`. **T** opens all chat, **Y** team chat (all chat in free
for all), **Home** all chat. **Enter** sends, **Esc** cancels. Lines show for
nine seconds, then fade; while the box is open the last ten show on a dark
panel. A line is at most 160 bytes. Each line shows the sender's hub avatar,
round, as the feed and the scoreboard do; MJOLNIRLobby may cache the
picture after the line arrives, so a row asks for it again once a second
for its first 15 seconds.

- **Typing does not move the player.** The Blam simulation reads the
  keyboard through GameInput, so no UE-side input mode stops it. The pause
  menu stops it with `BlamInputProcessorLocalPlayerSubsystem:SetUIActive`
  (seen live, 2026-10-17), and the chat sets the same gate while its box is
  open. On close the gate goes back to what the game last set, so a pause
  menu opened over the box stays in force.
- **The game's own chat** (`WBP_HUD_Main.ChatWidget`, `IA_OpenChat` on Home)
  is PlayFab party chat, which never connects in games joined by connection
  string. It draws nothing.
- **The wire.** A client sends `MJOLNIR|say|<a|t>|<text>` over
  `ServerExecRPC`. The host names the sender from the controller the RPC came
  in on, never from the text, and sends
  `MJOLNIR|chat|<a|t>|<Red|Blue|->|<index>|<name>|<text>` to every player, or
  only to the sender's team for team chat. The host allows five lines in six
  seconds from one sender, and tells a flooder to slow down.
- **The record.** The host keeps every line it relays, with the sender's
  in-game name, the hub account MJOLNIRLobby resolved for it, team and
  channel. It writes `chat_<match id>.json` beside the mod every few seconds,
  and at the end of the match names it in `match_outbox.txt`. MJOLNIRLobby
  sends it to `POST /matches/chat`. Private matches are recorded too, because
  a player report cites the match id whether the game was listed or not.
  Moderators read the log beside each report on `/moderation`; it is never
  public (`GET /moderation/match-chat/{host_match_id}`).
- **Esc** also opens the pause menu, as it does without chat.

## The kill feed

Every line is a row: a coloured bar at its left edge, then the killer, the
weapon, what made the kill special, and the victim. Event lines have a glyph,
a name, and what happened.

```text
| Noble Six  [assault rifle]  Kat
| (o) devnull  [sniper rifle] (+)  Jorge       <- gold rim: names you; (o) avatar
| (>>) devnull  Double Kill
| (+) Emile  joined the game
```

- **Weapons** are the game's own silhouettes, the ones its weapon cradle
  shows (`/Game/UI/Hud/WeaponCradle/Textures/T_UI_*_WeaponIcon`, grenades in
  `GrenadeCradle`). They are channel-packed masks, so they are drawn through
  the game's own icon material: a dynamic instance of
  `MI_HUDCradleIcon_FragGrenade` with the mask as `InputTexture`, `Empty` 0
  and `Equipped` 1, which gives the HUD's cyan. They are mirrored (render
  scale -1) to face the victim. `Scripts/hudicons.lua` maps every
  `Blam.DamageReporting.Type.*` to one; a type with no silhouette shows one
  of our glyphs (melee, fall, splatter ...) or, failing that, its name.
- **Glyphs** are MJOLNIR's own: white silhouettes drawn by
  `tools/ue/draw_hud_icons.py` into `unreal/MJOLNIRMaterials/Art/HudIcons`,
  imported by `build_mjolnir_ui.py` as `/Game/MJOLNIR/UI/Icons/T_MJHud_*` and
  cooked into chunk 984 with the widget (a hidden `IconPalette` references
  them). Lua tints them per line: Headshot, Melee, Assassination, Splatter,
  Stuck, Explosion, Fall, Guardians, Telefrag, Skull, Joined, Left, Kicked,
  Flag, Medal, Spree, FirstBlood.
- **Modifiers** (`DamageReportingInfo.Modifier`): a headshot or a stuck
  grenade adds a glyph after the weapon; an assassination replaces the
  weapon with the knife; a splatter adds the splat after the vehicle.
- **Avatars:** a player with a hub account has their avatar beside their
  name, round with a faint rim (`FeedLeadAvatar<i>`, `FeedTailAvatar<i>`):
  the same picture the scoreboard shows, which MJOLNIRLobby caches
  ([player_identity.md](player_identity.md)). Without an account, or before
  the picture is cached, the slot closes up.
- **Colours:** in team games names take their team's colour; in free for all
  the local player is gold and everyone else near white. A line that names
  the local player has a gold rim and flashes warmer as it arrives. A team
  kill says BETRAYAL.
- **Medals:** `first_blood`, `multikill_x2` (Double Kill) to `multikill_x10`
  (Killionaire) and the sprees (`5_in_a_row` Killing Spree ... `30_in_a_row`
  Invincible) become feed lines after the kill that earned them (they arrive
  before it in the same tick). The local player's own also come up in the
  middle of the screen with their glyph; a burst queues up to three. On a
  fireteam client the multi-kills and sprees come from the host's relay
  (MJOLNIRLevelLoader relays incidents that have a sound); `first_blood` does
  not.
- **Text** uses the game's own fonts, set from Lua over the cooked Roboto:
  Normative Pro for names, Oxanium (the menus' face) for numbers and
  captions.

### Animation

The widget has a pool of seven rows at one anchor. `Scripts/feed.lua` gives
each line a row and stacks them with render translations, newest at the
bottom: a line slides in from the left as it fades in (0.28 s), older lines
rise to make room (0.24 s), and each fades out after six seconds. Past six
on screen, the oldest leaves at once. `Scripts/anim.lua` eases the score bars
to a new score (the fill is a SizeBox width), pops a number that changes,
and brings medals in with a small overshoot.

Every pose is a function of the time alone. The animation runs on a hook of
`BP_MeteoritePlayerController_C:ReceiveTick`, the game's per-frame player
controller tick (as MJOLNIRFlyCam does), and on the 100 ms poll as well. A
host's tick runs once per controller each frame; the hook ignores calls
within 4 ms of the last. The hook is never removed, and is registered again
after a level change collects the hooked function.

### Preview

`mjolnir_feed_demo` (console, in a match) plays a scripted sequence through
the HUD's own drawing with made-up names: kills with several weapons, a
headshot, a melee, a splatter, a stuck grenade, joins, a kick, medals with
their callouts, the score bars moving, and a respawn countdown. Nothing it
shows is counted, and the real scores come back after 14 seconds
(`Scripts/demo.lua`).

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

## On fireteam clients

The host's incident handler gets every player's incidents; a fireteam
client's gets few of them (two-PC notes disagree on which: one run saw only
the joiner's own spawn, another its respawn ticks). So the host relays what
the feed and the tallies need (`Scripts/relay.lua`): after each drain, one
`ClientMessage` of type `MJOLNIR` to every remote player's controller,

```text
MJOLNIR|feed|kill,2,0,0,1,SniperRifle;death,2,0,0,0,SniperRifle
             name,cause,effect,value,modifier,damage type
```

carrying `Kill`, `suicide`, `death`, `first_blood`, the multi-kills and
sprees, `flag_scored`, and the joins, quits and kicks. A client feeds them
through the same handlers. It takes each incident once: one that also came
from its own handler, or from the level loader's sound relay (which carries
the medals), within 2.5 s and with the same name, cause and effect, is
dropped. Two from the same source are never merged, so a quick respawn
killed twice by the same player counts twice. The host ignores its own
relay, which its `ClientMessage` hook also sees.

The host finds its fireteam's controllers once, three seconds into the match
(`FindAllOf`, ~20 ms), then each new one as it is made
(`NotifyOnNewObject`), never with a scan per message. The round clock's
share uses the same list. The first send of a match logs
`relay: the feed to N player(s)`.

A client running an older HUD ignores `MJOLNIR|feed|` messages; a client
whose host runs an older HUD still gets the loader's medals.

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

The HUD's glyphs are PNGs in `unreal/MJOLNIRMaterials/Art/HudIcons`; change
one in `tools/ue/draw_hud_icons.py` (`--sheet preview.png` draws them all
over grey and sky blue), re-run it, then build and cook the UI. The Lua
modules `feed.lua`, `anim.lua`, `hudicons.lua`, `relay.lua` and `demo.lua` ship with
`main.lua`.

`tools/tests/test_multiplayer_ui.lua` exercises grouping, a full and uneven
roster, sorting, CTF captures, Team Slayer kills, delayed assignment,
switching teams, leaving, the live score strip (including tied/leaving
leaders), holding/releasing the board, and the kill feed: which silhouette
or glyph each kill shows, the rim, medals after their kill and the callout,
the stacking, the oldest line leaving, the bars, the feed's model on its
own, and the relay to fireteam clients (the wire format, taking an incident
once, a client's feed and tallies from the host's message alone). Run from the root
with Lua 5.4 or Python with lupa:

```powershell
python -c "from lupa import LuaRuntime; LuaRuntime().execute(open('tools/tests/test_multiplayer_ui.lua').read())"
```

## Not done yet

- Split screen: the widgets go on the whole viewport, not on each player's
  half.
- The scoreboard's own fonts (only the feed, callouts and score bars use the
  game's).
- Medals for kinds the simulation does not raise as incidents (sniper and
  vehicle medals arrive as `*_kill` incidents and are not shown yet).

## The end of a match

The first `round_over` ends the match (MJOLNIR's variants have 31 rounds).
The scoreboard comes up as the final standings, the results go to
`last_match.txt`, and the host takes the fireteam back to the lobby
([multiplayer_postgame.md](multiplayer_postgame.md)).
