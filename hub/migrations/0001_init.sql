-- Migration number: 0001 	 2026-08-01
-- MJOLNIR Hub initial schema.
--
-- The data model from docs/hub_architecture.md §6. Forward-only: never edit
-- an applied migration, add a new one.
--
-- The production database carried the tables of the pre-migrations
-- schema.sql, applied by hand and never written to — verified all-empty on
-- 2026-08-01 before this migration was authored. Clearing them here lets one
-- migration serve both that database and a fresh local one.

DROP TABLE IF EXISTS match_players;
DROP TABLE IF EXISTS matches;
DROP TABLE IF EXISTS player_stats;
DROP TABLE IF EXISTS mod_versions;
DROP TABLE IF EXISTS mods;
DROP TABLE IF EXISTS users;

-- ── Identity ────────────────────────────────────────────────────────────

CREATE TABLE users (
  id TEXT PRIMARY KEY,
  discord_id TEXT UNIQUE NOT NULL,
  discord_username TEXT NOT NULL,
  discord_avatar TEXT,
  display_name TEXT,
  role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'moderator', 'admin')),
  -- Earned standing; gates things like publishing without pre-moderation.
  trust_level INTEGER NOT NULL DEFAULT 0,
  banned_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Third-party tool credentials. Only a hash of the key is stored; the
-- prefix (mjc_ plus a few visible chars) exists so users can tell keys apart.
CREATE TABLE api_keys (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  key_hash TEXT UNIQUE NOT NULL,
  key_prefix TEXT NOT NULL,
  -- Space-separated scope list: mods:read mods:write ratings:write comments:write
  scopes TEXT NOT NULL DEFAULT 'mods:read',
  last_used_at TEXT,
  expires_at TEXT,
  revoked_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_api_keys_user ON api_keys(user_id);

-- ── Mods ────────────────────────────────────────────────────────────────

CREATE TABLE mods (
  id TEXT PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  -- One-line card text vs. full markdown page body.
  summary TEXT,
  description_md TEXT,
  owner_id TEXT NOT NULL REFERENCES users(id),
  -- Trust tier, not genre: content is open upload, script/native ship only
  -- from this repo's signed CI releases (docs/hub_architecture.md §2).
  type TEXT NOT NULL DEFAULT 'content' CHECK (type IN ('content', 'script', 'native')),
  category TEXT NOT NULL DEFAULT 'gameplay',
  license TEXT,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'published', 'hidden', 'removed')),
  nsfw INTEGER NOT NULL DEFAULT 0,
  -- Rollups, recomputed from events/ratings; never the source of truth.
  download_count INTEGER NOT NULL DEFAULT 0,
  rating_count INTEGER NOT NULL DEFAULT 0,
  rating_mean REAL,
  -- Wilson lower bound of the positive share; what listings sort by.
  rating_wilson REAL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_mods_status_category ON mods(status, category);
CREATE INDEX idx_mods_owner ON mods(owner_id);
CREATE INDEX idx_mods_rating ON mods(rating_wilson);

-- Co-authorship; the owner also appears here so one join lists everyone.
CREATE TABLE mod_authors (
  mod_id TEXT NOT NULL REFERENCES mods(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'author' CHECK (role IN ('owner', 'author', 'contributor')),
  PRIMARY KEY (mod_id, user_id)
);

-- ── Releases ────────────────────────────────────────────────────────────

-- Immutable once published; yanking hides, it never rewrites.
CREATE TABLE mod_releases (
  id TEXT PRIMARY KEY,
  mod_id TEXT NOT NULL REFERENCES mods(id) ON DELETE CASCADE,
  version TEXT NOT NULL,
  channel TEXT NOT NULL DEFAULT 'stable' CHECK (channel IN ('stable', 'beta')),
  changelog_md TEXT,
  r2_key TEXT,
  file_size INTEGER,
  sha256 TEXT,
  -- Ed25519 over the release manifest, for signed (script/native) releases.
  signature TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'scanning', 'published', 'rejected', 'yanked')),
  -- Game-build compatibility window as declared; verified per build via scans
  -- and community signals.
  build_min TEXT,
  build_max TEXT,
  download_count INTEGER NOT NULL DEFAULT 0,
  yanked_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (mod_id, version)
);
CREATE INDEX idx_releases_mod ON mod_releases(mod_id, created_at);
CREATE INDEX idx_releases_status ON mod_releases(status);

-- Files inside a release archive, as verified by the scanner.
CREATE TABLE release_artifacts (
  id TEXT PRIMARY KEY,
  release_id TEXT NOT NULL REFERENCES mod_releases(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('container', 'manifest', 'doc', 'other')),
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size INTEGER NOT NULL
);
CREATE INDEX idx_artifacts_release ON release_artifacts(release_id);

-- The conflict index. One row per IoStore chunk a release's containers
-- claim; two releases conflict iff they share a chunk_id here. The 12 bytes
-- are stored raw, exactly as they sit in the .utoc.
CREATE TABLE release_chunks (
  release_id TEXT NOT NULL REFERENCES mod_releases(id) ON DELETE CASCADE,
  chunk_id BLOB NOT NULL CHECK (length(chunk_id) = 12),
  PRIMARY KEY (release_id, chunk_id)
);
CREATE INDEX idx_chunks_by_id ON release_chunks(chunk_id);

CREATE TABLE release_deps (
  release_id TEXT NOT NULL REFERENCES mod_releases(id) ON DELETE CASCADE,
  dep_slug TEXT NOT NULL,
  semver_range TEXT NOT NULL DEFAULT '*',
  PRIMARY KEY (release_id, dep_slug)
);

-- Automated verdicts, kept so a rejection can be appealed against findings
-- rather than a shrug.
CREATE TABLE release_scans (
  id TEXT PRIMARY KEY,
  release_id TEXT NOT NULL REFERENCES mod_releases(id) ON DELETE CASCADE,
  verdict TEXT NOT NULL CHECK (verdict IN ('pass', 'fail')),
  findings TEXT NOT NULL DEFAULT '[]', -- JSON array
  scanner_version TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_scans_release ON release_scans(release_id);

-- ── Community ───────────────────────────────────────────────────────────

CREATE TABLE media (
  id TEXT PRIMARY KEY,
  mod_id TEXT NOT NULL REFERENCES mods(id) ON DELETE CASCADE,
  uploader_id TEXT NOT NULL REFERENCES users(id),
  r2_key TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'screenshot' CHECK (kind IN ('screenshot', 'thumbnail')),
  -- Required, deliberately: every image ships with a description.
  alt_text TEXT NOT NULL CHECK (length(alt_text) > 0),
  width INTEGER,
  height INTEGER,
  position INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_media_mod ON media(mod_id, position);

CREATE TABLE ratings (
  mod_id TEXT NOT NULL REFERENCES mods(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
  review_md TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (mod_id, user_id)
);

CREATE TABLE comments (
  id TEXT PRIMARY KEY,
  mod_id TEXT NOT NULL REFERENCES mods(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id),
  parent_id TEXT REFERENCES comments(id),
  body_md TEXT NOT NULL,
  -- Soft delete keeps thread structure; the body is blanked at delete time.
  deleted_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_comments_mod ON comments(mod_id, created_at);
CREATE INDEX idx_comments_parent ON comments(parent_id);

CREATE TABLE reports (
  id TEXT PRIMARY KEY,
  reporter_id TEXT NOT NULL REFERENCES users(id),
  subject_type TEXT NOT NULL CHECK (subject_type IN ('mod', 'release', 'comment', 'media', 'user')),
  subject_id TEXT NOT NULL,
  reason TEXT NOT NULL CHECK (reason IN ('malware', 'stolen', 'broken', 'nsfw', 'spam', 'other')),
  detail TEXT,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'dismissed')),
  resolved_by TEXT REFERENCES users(id),
  resolved_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_reports_status ON reports(status, created_at);

-- ── Collections ─────────────────────────────────────────────────────────

-- A shareable profile: references to mods, never bytes.
CREATE TABLE collections (
  id TEXT PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  description_md TEXT,
  owner_id TEXT NOT NULL REFERENCES users(id),
  is_public INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE collection_items (
  collection_id TEXT NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
  mod_id TEXT NOT NULL REFERENCES mods(id) ON DELETE CASCADE,
  version_range TEXT NOT NULL DEFAULT '*',
  -- Load order within the collection, lowest mounts first.
  position INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (collection_id, mod_id)
);

-- ── Moderation trail ────────────────────────────────────────────────────

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, -- append-only, ordered
  actor_id TEXT REFERENCES users(id),
  action TEXT NOT NULL,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  detail TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_audit_subject ON audit_log(subject_type, subject_id);

-- ── Multiplayer (future; carried over from the old schema.sql) ──────────

CREATE TABLE player_stats (
  id TEXT PRIMARY KEY,
  user_id TEXT REFERENCES users(id),
  gamertag TEXT NOT NULL,
  kills INTEGER NOT NULL DEFAULT 0,
  deaths INTEGER NOT NULL DEFAULT 0,
  assists INTEGER NOT NULL DEFAULT 0,
  matches_played INTEGER NOT NULL DEFAULT 0,
  matches_won INTEGER NOT NULL DEFAULT 0,
  total_playtime_seconds INTEGER NOT NULL DEFAULT 0,
  last_seen TEXT NOT NULL DEFAULT (datetime('now')),
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_player_stats_gamertag ON player_stats(gamertag);

CREATE TABLE matches (
  id TEXT PRIMARY KEY,
  map_name TEXT NOT NULL,
  game_mode TEXT NOT NULL DEFAULT 'slayer',
  started_at TEXT NOT NULL,
  ended_at TEXT,
  player_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_matches_started ON matches(started_at);

CREATE TABLE match_players (
  id TEXT PRIMARY KEY,
  match_id TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
  player_stat_id TEXT NOT NULL REFERENCES player_stats(id),
  team TEXT,
  kills INTEGER NOT NULL DEFAULT 0,
  deaths INTEGER NOT NULL DEFAULT 0,
  assists INTEGER NOT NULL DEFAULT 0,
  score INTEGER NOT NULL DEFAULT 0,
  won INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_match_players_match ON match_players(match_id);
