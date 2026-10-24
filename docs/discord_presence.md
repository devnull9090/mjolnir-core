# Discord Rich Presence and public game invites

MJOLNIR publishes its current game to the running Windows Discord desktop
client as **MJOLNIR Core**, using application **1533237469259104458**. The
game owns the connection, so closing the launcher does not stop presence.
The launcher registers Discord's launch protocol so an invite can start
MJOLNIR when the game is closed.

The code-mod update consists of MJOLNIRLobby 0.17.0 (including its rebuilt
native DLL) and MJOLNIRHud 0.12.0. Ship them together, plus the launcher
change for cold starts. These version increments let the existing updater
recognize the changed code mods.

## Discord setup

There is **no Social SDK download, bot token, OAuth client secret, redirect
URI, or Public Client setting required for this implementation**. It uses
Discord's documented local RPC over IPC transport for Rich Presence and
the `ACTIVITY_JOIN` event. The app's existing Hub OAuth configuration can
stay as it is. The activity explicitly sends `name: "MJOLNIR Core"`; the
developer portal application can remain named MJOLNIR Hub.

Players need the Discord desktop application running and signed in, with
activity sharing enabled for their intended audience. The browser-only
Discord client cannot receive the game's local IPC connection. They also
need the MJOLNIR launcher installed and run once to register the launch
protocol. Joining continues to use MJOLNIR's existing Hub sign-in and map
installation/version checks.

The app's Rich Presence Art Assets page initially contains no assets. Map
names and stats work without uploaded artwork. Artwork is optional and
must use asset keys actually uploaded to this application; do not publish
guessed map keys. Custom artwork is unset by default. To enable it, create
`MJOLNIRLobby/native/discord_assets.json` with a `default` image and optional
lowercase map codes mapped to uploaded keys (or supported external image
URLs), for example:

```json
{"default":"mjolnir_logo","bgl":"blood_gulch"}
```

If a future feature needs the full Social SDK (for example an in-game
Discord friends list), complete **Games > Social SDK > Getting Started**
in the developer portal, accept Discord's terms, download its Windows C++
SDK, and integrate/package `discord_partner_sdk.dll`. That is a separate
integration; adding the SDK DLL alone does not enable new features here.

## Presence and statistics

The lobby publishes the current menu, public/private lobby, loading,
match, and post-match state. The HUD contributes the current map, game
type, local player's observed kills/deaths, and session start time through
a bounded, fresh snapshot. Kills for presence are counted separately from
the Team Slayer score's betrayal penalty. These are observed local-session
statistics, not a replicated authoritative match total; a late join
cannot reconstruct earlier incidents.

Lua refreshes `MJOLNIRLobby/native/discord_activity.json` and calls the
native export `mjolnir_discord_update` once per second. The native half
copies the snapshot, then handles Discord I/O on a worker thread. It
coalesces routine changes, reconnects when Discord starts/restarts, and
clears stale presence if the game stops refreshing it. The payload uses
the game process ID, never the launcher's PID.

To opt out locally, create `MJOLNIRLobby/native/discord_disabled.txt`.
Remove that file to enable presence again. Discord's own activity-sharing
settings also control its visibility.

## Public Join Game

Only a confirmed public, fresh, non-full, joinable session publishes a
join secret. The host's public session identity is shared with its
participants so their cards can expose the same game. Private/offline
sessions, stale listings, full games, and matches with joining disabled
do not advertise Join Game.

The secret is `mjolnir:v1:<public hub lobby ID>`. It contains no account
key, host token, or PlayFab connection string. A received secret is
validated, then queued as `MJOLNIRLobby/native/pending_join.txt` using the
same `lobby=...` / `at=...` format as website join links. No secret is
executed as a command. The game's existing main-menu consumer fetches
the current public list and joins through the authenticated Hub endpoint;
an old invitation cannot bypass private/full/stale session checks.

The launcher registers `discord-1533237469259104458://` as a launch-only
protocol. Discord retains the actual join and delivers it over IPC once
the game connects. Launch intent passes through the normal launcher
preflight; a running game is not started again. If the player is already
in a match, the existing pending-join consumer waits until they return to
the signed-in main menu. It does not interrupt their match. Discord holds
a cold-start invite for about 180 seconds: if installation/preflight or
startup takes longer, click Join again after the game is ready. Once
received by the game, the existing pending-join queue expires after ten
minutes.

## Verification

Run the Lua presence/session tests, native Discord transport tests, and
launcher link tests before shipping:

```powershell
lua54 tools/tests/test_discord_presence.lua
./native/lobby/test-discord.ps1
cargo test --manifest-path apps/launcher/src-tauri/Cargo.toml --lib links::tests
cargo test --manifest-path apps/launcher/src-tauri/Cargo.toml --lib discord
```

The native tests use a private mock pipe and do not change a real Discord
account's activity. CI runs the Lua, native transport, and launcher tests; a production
lobby build includes the Discord source in the existing DLL and release
artifact, with no additional runtime DLL to distribute.

Live acceptance requires two Discord accounts on two machines:

1. Run the updated launcher once, then start the updated game with Discord
   open. Inspect the profile from the second account for MJOLNIR Core,
   current map/mode, observed kills/deaths, player count, and elapsed time.
2. Host a public game with space. Join from the host's card and from a
   participant's card. Verify the usual sign-in and map-download/version
   prompts still work.
3. Repeat with the joining game closed and with the launcher already open.
   Verify only one game starts and the pending join survives startup.
4. Make the game private, full, or unavailable for joining during a match;
   verify the join action disappears after the presence update and an old
   invite cannot bypass the current Hub checks.
5. Restart Discord, return to the main menu, leave the session, disable
   presence, and exit the game. Verify recovery and removal of old stats
   and join availability.

Automated tests do not establish Discord's visual presentation or an
end-to-end Steam/Xbox network join. Record those two-account results
separately before announcing live verification.

On 2026-10-24, a live local Discord desktop IPC check accepted application
1533237469259104458, acknowledged the `ACTIVITY_JOIN` subscription, and
echoed `name: "MJOLNIR Core"` and `supported_platforms: ["desktop"]` in its
successful `SET_ACTIVITY` response. The temporary activity was labeled
"Integration test" and then cleared with an acknowledged null activity.
This verifies these wire fields against the desktop client; it does not
replace the two-account game test above.

## Protocol references

- [Discord RPC over IPC, SET_ACTIVITY, SUBSCRIBE, ACTIVITY_JOIN](https://docs.discord.com/developers/topics/rpc)
- [Rich Presence fields and unauthenticated desktop presence](https://docs.discord.com/developers/discord-social-sdk/development-guides/setting-rich-presence)
- [Invite configuration, launch registration, and pending joins](https://docs.discord.com/developers/discord-social-sdk/development-guides/managing-game-invites)
- [Discord's Windows launch registration implementation](https://github.com/discord/discord-rpc/blob/master/src/discord_register_win.cpp)
