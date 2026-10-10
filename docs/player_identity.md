# Hub identities in game, player reports, matchmaking bans

Everyone who plays online signs the MJOLNIR launcher in with Discord, so in
game a player is shown by their hub account, its name and avatar, instead of
their Steam or Xbox name. From the post-game screen a player can report
another. Moderators review reports at `/moderation`, and can ban a player
from matchmaking. Status as of 2026-10-10: the hub, the HUD and the Lobby
work end to end on one PC against a local hub. The two-PC exchange (a
joiner proving itself to a host) is still untested.

## Who is who

A name is the host's to trust or not: anyone can call themselves anything,
and the scoreboard, the kill feed and above all a report must not name the
wrong account. So each player proves its account to the host with a ticket
from the hub:

```text
joiner's game                          hub                          host's game
  POST /identity/tickets  ───────────▶  ticket for (joiner,
  {platform_name, audience=host}         audience host, in-game
                                         name), 15 minutes
  iam|<ticket>  ─────────────────────────────────────────────────▶  (ServerExecRPC)
                                        POST /identity/tickets/resolve  ◀─ {tickets}
                                        ──▶ {platform_name, player, reports, matchmaking_ban}
                                                                     checks platform_name ==
                                                                     the sender's in-game name
  ids|<host account>|<roster>  ◀────────────────────────────────────  (ClientMessage)
```

- **The audience.** Only the host the ticket names can trade it. A host that
  took a joiner's ticket and passed it to another host would get nothing for
  it. The joiner learns the host's account from the host's own `ids`
  broadcast.
- **The in-game name.** The hub returns the name the ticket was issued for.
  The host keeps the answer only if it is the name of the controller that
  sent the ticket. Even with a valid audience, a ticket stolen in transit
  names nobody else.
- **The host itself** asks `POST /identity/tickets` with no audience. That
  makes no ticket and just answers who it is and whether it is banned.

The roster is keyed by in-game name, as everything else between the host
and its fireteam already is (ballots, bans, seats). Each entry is the
account id, its name (display name, else the Discord username) and its
public report count. `ids` goes out when the roster changes, every 30 s
while anyone else is connected, and when a client asks (`whois`, sent by a
client that has not heard one).

Every machine writes what it knows to `MJOLNIRLobby\identities.txt`, one
line per player: `<in-game name>\t<account id>\t<hub name>\t<reports>`.
MJOLNIRHud reads that file; it never touches the hub itself.

### Where the hub name shows

- **Tab scoreboard** (MJOLNIRHud): the name, plus the avatar in a new
  `Avatar<i>` image per row.
- **Kill feed and winner line**: the name. A joiner's "joined the game"
  line waits up to 8 s for its account (its ticket lands a few seconds after
  the join), then falls back to the in-game name.
- **The game's FIRETEAM panel** (top right of the main menu): each row's
  `NameText`. The game's view model rewrites its names every few seconds,
  and each row writes its text again in `OnBackingDataChanged`, so
  `squadpanel.lua` hooks that (and `OnListItemObjectSet`) and sets the hub
  name after it. Renaming the view model's `DisplayName` does not stick.
- **Our lobby's player list** (`WBP_MJOLNIRLobby`): the name.
- **Name tags over teammates**: the hub name is written into the game's
  `PlayerNameValue` when a tag is shown. This one is untested; the game may
  write its own name back.
- **Post-game screen** (MJOLNIRLobby): the name and avatar per row.

`p.name` stays the in-game name everywhere it is a key: match seats and
claims, host bans, ballots. Only what is drawn changes.

### Avatars

The game's hub call reaches nothing but the hub (`mjolnir_lobby.c` refuses
another host, and must not carry the launcher key to one). So the hub
proxies avatars: `GET /api/v1/users/{id}/avatar` returns the Discord
avatar at 64 px, or Discord's default one for an account without one. It
is a PNG, cached at Cloudflare for a day and in browsers for an hour.

The Lobby fetches each account's avatar once a session with the hub call's
`FILE` mode, into `MJOLNIRMaps\_covers\av_<id>.png`. Lobby and HUD read the
file into a texture with `ImportFileAsTexture2D`, the way map covers are
read. No native change was needed.

## Reporting a player

On the post-game screen every row is now a button (`RowButton<i>`). A row
is enabled when its player has a hub account and is not you; clicking it
opens the report panel:

- who: avatar, hub name, the in-game name if different, and the public
  report count;
- **WHY**: one of CHEATING, BETRAYING, HARASSMENT, GRIEFING / AFK, QUITTING,
  NAME OR AVATAR, OTHER;
- **WHAT HAPPENED**: an optional note of up to 1000 characters, in a
  `MultiLineEditableTextBox` (typing works on the menu stack);
- SEND REPORT / CANCEL.

The report is `POST /api/v1/players/reports` with:
- the account the host resolved for that seat;
- the reason and the note;
- the in-game name the reporter saw;
- the match's id: the host's own record, or the id the host told the
  client. MJOLNIRHud now writes it into `last_match.txt` (field 8 of the
  `match` line).

Each `player` line in `last_match.txt` gained three fields: the account id,
the hub name and the report count. One report per reporter, player and
match: a second one gets 409, and the panel says it was already sent.

The vote lasts 20 s, which is not enough to write a report. While anyone
has the panel open, the host holds the countdown:
- opening or closing the panel sends `reporting|1` or `reporting|0`;
- the hold lasts at most 90 s per vote, and a player's hold lapses after
  120 s;
- the vote message gained a ninth field, `held`, so every screen says
  VOTING PAUSED / A PLAYER IS FILING A REPORT.

### What is public

Only the number. A profile's Multiplayer section (`/users/<id>`) shows
**Reports**: the reports against the account that a moderator has not
dismissed. The same figure is `stats.player_reports` on
`GET /api/v1/users/{id}`, and appears in the report panel and in the
roster. Who reported, and why, is for moderators only.

## Moderation

At `/moderation`, moderators and admins get **Player reports**, grouped by
the player reported (most reports first), with tabs for Open, Upheld and
Dismissed. Each player shows:
- every report against them, with its reason and note;
- who filed it and when;
- the name it was filed under;
- a link to the match when the host reported it, or a flag when either
  player is not linked to a seat in it.

The decisions:

- **Uphold**: the report stands and stays in the public count.
- **Dismiss**: unfounded; it leaves the public count.
- **Ban from matchmaking**: a reason (the player sees it) and 1, 3, 7 or
  30 days, or permanent. It replaces a ban in force, upholds the player's
  open reports, and takes down a game they have listed. Only an admin can
  ban a moderator or an admin.
- **Lift ban**.

**Matchmaking bans** lists the bans in force. Every decision is written to
`audit_log`.

### What a matchmaking ban does

| Where | Effect |
|---|---|
| `POST /lobbies` | 403 `matchmaking_banned`, with the reason and end; the game's status line shows it |
| `GET /lobbies/{id}/join` | the same 403: no connection string |
| `GET /lobbies` | a banned host's games are not listed |
| Ban issued | the banned player's listing is deleted; their heartbeat then 404s and the game stops listing |
| A public game's host | resolves a banned joiner's ticket, sends them back to their menu (`kick`) |

It is not a hub ban (`users.banned_at`): the account still signs in,
downloads and comments.

A banned player can still join a friend's game by invite: that never
touches the hub. Their identity is still resolved there, and they are kicked
only if that game is public.

## The hub

`hub/src/lib/api/players.ts`, `migrations/0018_player_identity_reports.sql`:

- `identity_tickets`: the hash of each ticket, never the ticket. Rows
  expire after 15 minutes and are swept when new ones are issued.
- `player_reports`: its own table, because `reports.reason` is a CHECK enum
  about mods that SQLite cannot widen. A unique index on (reporter,
  subject, match).
- `matchmaking_bans`: kept after they end or are lifted. The ban in force
  is one that is not lifted and has not expired.

| Route | Who |
|---|---|
| `POST /identity/tickets` | `lobbies:write` (every launcher key) |
| `POST /identity/tickets/resolve` | `lobbies:write`, the ticket's audience |
| `GET /users/{id}/avatar` | anyone |
| `POST /players/reports` | `lobbies:write`, 30 an hour |
| `GET /moderation/player-reports`, `POST /moderation/player-reports/{id}` | moderators |
| `GET`/`POST /moderation/matchmaking-bans`, `DELETE /moderation/matchmaking-bans/{user_id}` | moderators |

Like every migration, 0018 must be applied to production by hand before
the hub deploy that uses it (`pnpm db:migrate:prod`).

## The UI container

`build_mjolnir_ui.py` adds three things, so chunk 984 must be rebuilt and
cooked:
- `Avatar<i>` images to the scoreboard and post-game rows;
- `RowButton<i>` around each post-game row;
- the `Report` panel.

An older container still works: the Lua checks each new widget and draws
text only, with no click.

## Testing

One PC, 2026-10-10:
- **Setup.** The game was pointed at a local hub (`MJOLNIR_HUB_URL`). The
  launcher's account was seeded there with only its key's hash. The rebuilt
  chunk 984 replaced `pakchunk900-MJOLNIRHUB-mjolnir-ce-runtime-0_P` (the UI
  container as the runtime ships it).
- **Identity.** The Lobby resolved the account, wrote `identities.txt` and
  cached the avatar. The Tab scoreboard showed the hub name and avatar in
  place of the in-game name.
- **Post-game.** A hand-written `last_match.txt` showed the post-game rows
  with avatars, and a row without an account had none. Clicking a row
  opened the panel and held the vote. Typing reached the text box. SEND
  REPORT filed the report with its reason, note, in-game name and match id,
  then the panel closed and the vote resumed.
- **Fireteam and lobby.** The FIRETEAM panel and our lobby's player list
  showed the hub name, and it survived the view model's refreshes. The
  delayed "joined" line is covered by the Lua tests only: it needs a second
  player.
- **Hub API.** Tickets, the audience check, reports and their duplicates,
  bans refusing `POST /lobbies` and joins, lifting, and the avatar proxy.
  The moderation page and the profile count were checked in a browser.

## Open

- **Two PCs.** A joiner's ticket reaching the host, the roster reaching
  the joiner, and a banned joiner kicked from a public game.
- **Name tags.** Whether the game keeps our hub name in a tag.
- **Unverified players.** A public game could refuse players with no
  resolved account (an old launcher, or no sign-in) after a grace period.
  Not done, because it would send away anyone on a stale sign-in.
- **Reporting from the website.** A participant could report from
  `/matches/<id>` too, for when the post-game screen is gone.
- **Linking seats from tickets.** The host could cite resolved accounts in
  its match report, so seats link without each client's claim.
