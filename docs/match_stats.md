# Match history and stats

Every public multiplayer match is reported to the hub when it ends: the final
standings, and every incident the simulation raised, in order, with where the
players involved stood. The hub shows the history at `/matches`, one match at
`/matches/<id>`, a player's matches at `/players/<name>`, and a linked
account's on its profile (`/users/<id>`). Matchmaking and ranking will build
on the same records later; for now the job is to collect everything.

## The pieces

```text
host's game                                         hub (mjolnircore.com)
  MJOLNIRHud   Scripts/matchlog.lua                   POST /api/v1/matches
    records incidents + positions,                    POST /api/v1/matches/claims
    writes match_<id>.json        ─┐                  GET  /api/v1/matches[/{id}]
  MJOLNIRLobby Scripts/matches.lua │ match_outbox.txt  GET  /api/v1/players/{name}/stats
    sends the outbox to the hub  <─┘                  GET  /api/v1/users/{id}/match-stats
                                                      D1: matches, match_players,
participant's game                                        match_events, match_claims
  MJOLNIRHud   asks the host for the match id,        (migrations/0014_matches.sql)
               writes claim_<id>.json
  MJOLNIRLobby sends it
```

### Recording (the host)

The host's incident handler gets every player's incidents; a fireteam client's
gets almost none (multiplayer_hud.md), so only the host records. MJOLNIRHud
already hooks `OnIncident_Event` for the kill feed. While its match log is
recording, the hook also reads `K2_GetActorLocation()` of the incident's
`CauseObjectActor` and `EffectObjectActor`: for a kill, the killer's and the
victim's bipeds, at the moment the incident arrives. Every incident is kept
except the respawn countdown (`respawn_tick`, `respawn_final_tick`): kills,
deaths, suicides, spawns (with the spawn point), medals and commendations,
flags, joins and quits, the end.

Positions are the map's Unreal world space, in centimetres, Z up. They are
real biped positions (checked 2026-10-03 on Blood Gulch: a bot standing still
died a few centimetres from where it spawned). The cause object can be a
vehicle when the killer drove one.

A match is **public** if MJOLNIRLobby listed it on the hub at any point while
it ran: the Lobby writes the listing's id to `MJOLNIRLobby\listing.txt` while
listed, and the HUD reads it every five seconds. A private match is recorded
and thrown away at its end.

The record is `MJOLNIRHud\match_<id>.json`, already in the shape the hub's
`MatchReport` takes. It is rewritten every 30 seconds as an *abandoned* match,
so a crash leaves what happened up to then. `match_current.txt` names the match
being recorded; found at the next start, it marks a match a crash cut short,
whose checkpoint is then sent. At the end (`round_over`, `game_over`, or the
host leaving the map: abandoned) the file is written a last time and its id is
appended to `match_outbox.txt`. An abandoned match under a minute long with no
kill is not kept.

The id is 32 random hex digits, made by the host. The hub never shows it; it is
what a participant cites to claim its seat.

### Sending

MJOLNIRLobby's `matches.lua` reads `match_outbox.txt` every 15 seconds and
sends one file at a time through the native hub call public games use
(`mjolnir_hub_call`, the launcher's key). A file is deleted once the hub has it
(200/201) or refuses it for good (400, 409, 413, 422). No connection, a 429 or
a 5xx retry in a minute; 401/403 (an old launcher sign-in) and 404 (a hub
without these routes) in ten. Lua has no directory listing, hence the outbox.
The HUD only appends to it; the Lobby rewrites it to the entries whose files
remain. Both run on the game thread, so they never interleave.

### Seats and accounts

A seat is a player as the host's game named them. Names are not identities,
so each participant's own game claims its seat with its own hub key:

1. A client's HUD asks the host: `ServerExecRPC("MJOLNIR|matchid")`, every ten
   seconds until answered.
2. The host's HUD hook (`self` is the asker's controller) answers on that
   controller: `ClientMessage("MJOLNIR|match|<id>|<public>|<index>|<name>",
   "MJOLNIR")`, with the seat as the host recorded it. The host ignores its
   own outgoing answers, which its hook also sees.
3. If public, the client writes `claim_<id>.json` and queues it. A private
   answer is asked again every 30 seconds, since a game can go public.

These are the RPCs MJOLNIRLobby's messages already ride
(multiplayer_postgame.md); the Lobby and the level loader ignore the new verbs.
No object scans on either side.

The hub keeps claims apart from seats (`match_claims`) so either can arrive
first; whichever lands second links the seat (`match_players.user_id`). A
claim links only a seat of the same name, one account per seat and one seat
per account per match; a newer claim replaces the account's own older one. The
host's seat is linked by the report itself (`host_index`).

Both writes take the `lobbies:write` scope every launcher key already has
(migration 0013), so nobody signs in again.

## The hub

`hub/src/lib/api/matches.ts`. The report is validated (16 seats, 20,000
events, six hours), stored in one D1 batch, seats and events each inserted by
a single `json_each` statement (D1 counts statements against a request's
budget). The hub works out each seat's place and outcome (win, loss, draw; none
for an abandoned match) and the match's winner: the team with more points, or
the top score alone (a shared top is a draw). The host's clock is trusted only
to the last week and never ahead of the hub's. Reporting the same id twice from
the same account is a no-op; from another, 409. A listing id that still exists
must be the caller's.

Pages: `/matches` (filters by game type and map, player search),
`/matches/<id>` (scoreboard by team, the timeline, and a top-down plot of kill
and death positions, per player with `?p=<index>`), `/players/<name>` (totals,
most-used weapons, matches), and a Multiplayer section on `/users/<id>`.

## Trust

A report is the host's word. The hub records who reported it, and seats link
only to the accounts that claim them, but standings are not verified. Ranking
built on this should weigh hosts (agreement between participants' own views,
per-host history) before it trusts a report.

## Migration

`0014_matches.sql`. Migration 0001 carried unused placeholder `matches` and
`match_players` tables; 0014 renames them to `legacy_*` rather than dropping
them unseen. Like every migration it must be applied to production by hand
before the hub deploy that uses it (`pnpm db:migrate:prod`).

## Testing

- Hub: `hub` dev server with local D1 (`pnpm db:migrate`), a seeded user and
  key, then POST reports and claims. Claim before and after the report,
  a wrong name, a taken seat, a duplicate report, another account's id.
- Game, one PC (2026-10-03): host BGL Slayer with a `CreatePlayer` bot and a
  hand-written `listing.txt`; `blam unit_kill (unit (list_get (players) 1))`
  for deaths; `mjolnir_auto endgame`. The record, posted to the local hub,
  rendered as written.
- Two PCs (2026-10-03, `tools/remote/jip-test.mjs`, PC 2 joining PC 1's
  public BGL match under way): PC 2 claimed seat 1 in the match PC 1
  recorded. The host's record held two real kills (an assault rifle first
  blood; a Warthog splatter, `WarthogDriver` modifier 3, the cause position
  the vehicle's), with positions for both players. Posted to a local hub,
  claim first, both seats linked. The first run had claimed seat 0: a joiner
  reads index 0 on the host for a few seconds after it is seated, so the host
  now answers only with the asker's own recorded seat.
- A host's ban list kicks a banned joiner about a second in; an old ban of
  the test account looked like a failed join until it was cleared.

## Next

- Heatmaps across matches per map, from `match_events` (indexed by type).
- Periodic position samples (where players walk, not just where they die).
- Ranking: per-account ratings from linked seats in completed matches.
