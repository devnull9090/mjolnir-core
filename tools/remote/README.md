# Remote test PCs

`remote.mjs` drives the game on another Windows PC on the LAN through
`mjolnir-agent.ps1` running there; its header lists every command. Two-PC test
procedures: [docs/two_pc_test.md](../../docs/two_pc_test.md).

Each PC is a named target. `--pc <name>` (anywhere on the command line) or
`MJOLNIR_PC` picks one; without either, the default target is used (PC 2, from
before targets existed):

```
node tools/remote/remote.mjs --pc pc3 status
node tools/remote/remote.mjs --pc pc3 desktop pc3.png     # every monitor, game or not
node tools/remote/remote.mjs --pc pc3 run 'Get-Process steam'
```

Scripts that import `remote.mjs` call `useTarget(name)` first.

`%USERPROFILE%\.mjolnir-remote.json` on the development PC holds the addresses
and tokens, never the repository (a token runs Lua in that PC's game and
PowerShell on its desktop):

```json
{ "url": "http://<pc2>:47820", "token": "...",
  "targets": { "pc3": { "url": "http://<pc3>:47820", "token": "..." } } }
```

## Two ways in

| | SSH (`ssh <alias>`) | Agent (`remote.mjs`) |
|---|---|---|
| Runs as | the user, elevated (admin key) | the user, normal rights |
| Session | a service session with **no desktop** | the signed-in desktop |
| Good for | files, installs, services, processes, logs, restarting the agent | the game, Lua, input, screenshots, Steam and launcher windows (`run`) |

Anything with a window (Steam, the game, the launcher, a screenshot) must start
from the agent, not SSH: a process started over SSH has no desktop.

## Setting up a new PC

1. **On the development PC**, a dedicated key:
   `ssh-keygen -t ed25519 -N "" -C mjolnir-dev-to-<pc> -f ~/.ssh/id_ed25519_<pc>`.
2. **On the new PC**, as the player's account (it asks for admin), with the
   `.pub` contents:
   `powershell -ExecutionPolicy Bypass -File setup-target-pc.ps1 -PublicKey "<key>"`.
   It can run from a network share; the report lands beside it. It sets the
   network to Private (a Public network silently drops SSH, RDP and the agent),
   installs and starts OpenSSH Server, authorizes the key, opens TCP 22 and 47820,
   and turns off sleep. If it says sshd is still missing, reboot and run it again.
3. **On the development PC**, a `Host <pc>` entry in `~/.ssh/config`
   (`HostName`, `User`, `IdentityFile`, `IdentitiesOnly yes`, `BatchMode yes`),
   then `ssh <pc> whoami`.
4. **Over SSH**, the agent and its logon task. Copy `mjolnir-agent.ps1`,
   `register-agent-task.ps1`, `tools/mcp/game/{input,capture}.ps1`,
   `launcher.ps1` and `mods/MJOLNIRBridge/{mod.json,Scripts/main.lua}` into a
   folder in the user's profile (for example `~\mjolnir-agent`), then
   `powershell -ExecutionPolicy Bypass -File ~\mjolnir-agent\register-agent-task.ps1 -Restart`.
   The task starts the agent at every logon, in the desktop session; `-Restart`
   from SSH brings it back after a crash. The agent needs the game installed.
5. **The token**: read `agent-token.txt` beside the agent over SSH straight into
   `.mjolnir-remote.json`'s `targets.<pc>`. Don't print it. Then
   `remote.mjs --pc <pc> status` and `desktop`. Later agent updates go through
   `remote.mjs --pc <pc> deploy-agent`.

**Left to the person at the PC** (passwords and accounts):
- **Auto sign-in after a reboot** (Sysinternals Autologon). The agent only runs
  in a signed-in session.
- **Steam signed in** with "Ask which account to use each time Steam starts"
  off, so it starts with no picker. Two PCs online at once need two Steam
  accounts that own the game.
- **The MJOLNIR launcher** installed once; `remote.mjs launcher update` keeps it
  current from then on.

**Development PCs stay out of public view:** put any file at
`%LOCALAPPDATA%\Meteorite\Saved\mjolnir_dev.txt` on every PC we test on
(`remote.mjs --pc <pc> put <file> saved mjolnir_dev.txt`). MJOLNIRLobby then
opens the lobby private, `mjolnir_auto host` hosts private unless told
`public`, and no match, seat or chat record reaches hub history even when a
test lists a game to be joined (games.lua `Games.dev`). Players never have the
file, so their lobbies open public.

**A live view (Sunshine + Moonlight):** for watching a PC in a movable,
resizable window, install Sunshine there
(`winget install LizardByte.Sunshine --scope machine`, over SSH; a service that
captures the console session and adds its own firewall rules) and Moonlight here
(`winget install MoonlightGameStreamingProject.Moonlight`). Sunshine's web page
refuses saves from any origin but localhost (a CSRF error) until
`csrf_allowed_origins = https://<pc-ip>:47990` is in
`C:\Program Files\Sunshine\config\sunshine.conf` (then
`Restart-Service SunshineService`). Once: open
`https://<pc-ip>:47990` here, set Sunshine's admin login, add the PC in Moonlight,
and type the PIN Moonlight shows into Sunshine's PIN page. Moonlight's settings:
Windowed, 1080p. Moonlight sends input too, so keep the mouse out of its window
while a test drives that PC.

**Remote Desktop:** disconnecting an RDP session leaves the console locked, and
the game and screenshots stop until someone signs in at the PC again. Prefer
SSH and the agent's `desktop` over RDP.
