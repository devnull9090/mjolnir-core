-- MJOLNIR Hub D1 Schema
-- Cloudflare D1 (SQLite)

-- Users (Discord OAuth)
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  discord_id TEXT UNIQUE NOT NULL,
  discord_username TEXT NOT NULL,
  discord_avatar TEXT,
  display_name TEXT,
  role TEXT DEFAULT 'user', -- user, mod, admin
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

-- Mods catalog
CREATE TABLE IF NOT EXISTS mods (
  id TEXT PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  author_id TEXT NOT NULL REFERENCES users(id),
  category TEXT DEFAULT 'gameplay',
  version TEXT NOT NULL DEFAULT '1.0.0',
  r2_key TEXT, -- key in mjolnir-mods R2 bucket
  download_count INTEGER DEFAULT 0,
  is_approved INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

-- Mod versions (history)
CREATE TABLE IF NOT EXISTS mod_versions (
  id TEXT PRIMARY KEY,
  mod_id TEXT NOT NULL REFERENCES mods(id) ON DELETE CASCADE,
  version TEXT NOT NULL,
  changelog TEXT,
  r2_key TEXT NOT NULL,
  file_size INTEGER,
  created_at TEXT DEFAULT (datetime('now'))
);

-- Player stats (future multiplayer)
CREATE TABLE IF NOT EXISTS player_stats (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(id),
  gamertag TEXT NOT NULL,
  kills INTEGER DEFAULT 0,
  deaths INTEGER DEFAULT 0,
  assists INTEGER DEFAULT 0,
  matches_played INTEGER DEFAULT 0,
  matches_won INTEGER DEFAULT 0,
  total_playtime_seconds INTEGER DEFAULT 0,
  last_seen TEXT DEFAULT (datetime('now')),
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

-- Match history (future multiplayer)
CREATE TABLE IF NOT EXISTS matches (
  id TEXT PRIMARY KEY,
  map_name TEXT NOT NULL,
  game_mode TEXT DEFAULT 'slayer',
  started_at TEXT NOT NULL,
  ended_at TEXT,
  player_count INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now'))
);

-- Match participants
CREATE TABLE IF NOT EXISTS match_players (
  id TEXT PRIMARY KEY,
  match_id TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
  player_stat_id TEXT NOT NULL REFERENCES player_stats(id),
  team TEXT,
  kills INTEGER DEFAULT 0,
  deaths INTEGER DEFAULT 0,
  assists INTEGER DEFAULT 0,
  score INTEGER DEFAULT 0,
  won INTEGER DEFAULT 0
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_mods_slug ON mods(slug);
CREATE INDEX IF NOT EXISTS idx_mods_author ON mods(author_id);
CREATE INDEX IF NOT EXISTS idx_mods_category ON mods(category);
CREATE INDEX IF NOT EXISTS idx_mod_versions_mod ON mod_versions(mod_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_gamertag ON player_stats(gamertag);
CREATE INDEX IF NOT EXISTS idx_matches_started ON matches(started_at);
CREATE INDEX IF NOT EXISTS idx_match_players_match ON match_players(match_id);
