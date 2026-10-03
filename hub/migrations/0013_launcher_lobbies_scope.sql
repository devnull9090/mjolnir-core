-- Migration number: 0013 	 2026-10-02
-- Launcher keys paired before lobbies:write existed get it.
--
-- A launcher that pairs without asking for scopes gets DEVICE_SCOPES
-- (src/lib/api/device.ts), and lobbies:write joined that set with the games
-- list. Keys paired earlier carry the older set, so the game could find
-- public games but never list one (403 insufficient_scope) until the player
-- signed in again (docs/multiplayer_servers.md). This brings every live
-- launcher key to today's set instead.
--
-- Only keys the launcher paired: device pairing names a key after its client
-- ("MJOLNIR Launcher"); keys made on the account page are left alone.
-- lobbies:write lists the caller's own game and nothing else.
UPDATE api_keys
SET scopes = scopes || ' lobbies:write'
WHERE name = 'MJOLNIR Launcher'
  AND revoked_at IS NULL
  AND (' ' || scopes || ' ') NOT LIKE '% lobbies:write %';
