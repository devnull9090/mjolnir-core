-- Migration number: 0016 	 2026-10-09
-- Which release of its map a listed game runs (docs/live_map_install.md):
-- the hub release id the host installed, and its version for display. A
-- player who joins with another release of the map would not start with the
-- host, so FIND GAMES compares, and the game installs the host's exact
-- release first. NULL for a host from before, or a map not from the hub.
ALTER TABLE lobbies ADD COLUMN map_release_id TEXT;
ALTER TABLE lobbies ADD COLUMN map_version TEXT;
