-- Migration number: 0012 	 2026-10-01
-- Maps and multiplayer lobbies (docs/multiplayer_release_plan.md, items 4–5).
--
-- A map is a content-tier mod: its archive is IoStore containers and JSON,
-- nothing that executes (docs/map_distribution.md). `mods.type` stays a
-- trust tier, so no CHECK changes and no table rebuilds: `mods` is the parent
-- of every cascade in the schema, and rebuilding it risks them all. Maps get
-- their own side tables instead.

-- What makes a mod a map: its codename, which the game's map registry keys
-- by (one listing per code, ever), its title and game types, and whether it
-- is one of the official classic maps.
CREATE TABLE map_listings (
  mod_id TEXT PRIMARY KEY REFERENCES mods(id) ON DELETE CASCADE,
  code TEXT NOT NULL UNIQUE CHECK (length(code) = 3 AND code = upper(code)),
  title TEXT NOT NULL,
  -- JSON array of game type ids ("slayer", "ctf", ...), from mjolnir.json.
  modes TEXT NOT NULL DEFAULT '["slayer"]',
  -- 1 for the converted classic Halo CE maps the hub lists as defaults.
  official INTEGER NOT NULL DEFAULT 0 CHECK (official IN (0, 1)),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_map_listings_official ON map_listings(official, title);

-- Community map releases wait here between a passing scan and publication.
-- The release itself stays 'pending' until a moderator approves it, so no
-- download route serves it; the scan's findings are already in
-- release_scans.
CREATE TABLE release_reviews (
  release_id TEXT PRIMARY KEY REFERENCES mod_releases(id) ON DELETE CASCADE,
  state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'approved', 'rejected')),
  reason TEXT,
  reviewed_by TEXT REFERENCES users(id),
  reviewed_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_release_reviews_state ON release_reviews(state, created_at);

-- Games players can find and join. A host registers its game, keeps it
-- alive with heartbeats, and removes it when the game ends; rows whose
-- heartbeat is stale are invisible to listings and swept opportunistically.
--
-- connection_string is the host's PlayFab lobby connection string, the only
-- thing a client needs to join (docs/fireteam_join_and_cap.md). It is
-- returned only to signed-in callers.
CREATE TABLE lobbies (
  id TEXT PRIMARY KEY,
  host_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- SHA-256 of the per-lobby secret the host proves on heartbeat and delete.
  host_token_hash TEXT NOT NULL,
  name TEXT NOT NULL,
  map_code TEXT NOT NULL,
  game_type TEXT NOT NULL,
  players INTEGER NOT NULL DEFAULT 1 CHECK (players >= 0),
  max_players INTEGER NOT NULL DEFAULT 4 CHECK (max_players BETWEEN 1 AND 16),
  -- The host's MJOLNIR versions, so clients only see games they can join.
  client_version TEXT NOT NULL,
  game_build TEXT,
  platform TEXT,
  connection_string TEXT NOT NULL,
  -- Where the host is, from Cloudflare's view of its request: the edge
  -- colo and the coarse location the ping estimate is made from.
  colo TEXT,
  country TEXT,
  latitude REAL,
  longitude REAL,
  state TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'in_game', 'full')),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  last_heartbeat TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_lobbies_heartbeat ON lobbies(last_heartbeat);
CREATE INDEX idx_lobbies_map ON lobbies(map_code, game_type);
CREATE INDEX idx_lobbies_host ON lobbies(host_user_id);
