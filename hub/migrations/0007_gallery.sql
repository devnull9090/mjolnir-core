-- Migration number: 0007 	 2026-08-06
-- The community gallery: any signed-in user may submit screenshots and
-- videos to a mod's page, and nothing shows publicly until a moderator
-- approves it (docs/hub_architecture.md §6).
--
-- The media table is rebuilt because SQLite cannot alter CHECK constraints:
-- `kind` gains 'video', and each item now carries a moderation status plus
-- a view counter. Every pre-existing row was uploaded by a mod owner under
-- the old owner-only rule, so they grandfather in as 'approved'.

CREATE TABLE media_new (
  id TEXT PRIMARY KEY,
  mod_id TEXT NOT NULL REFERENCES mods(id) ON DELETE CASCADE,
  uploader_id TEXT NOT NULL REFERENCES users(id),
  r2_key TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'screenshot' CHECK (kind IN ('screenshot', 'thumbnail', 'video')),
  -- Required, deliberately: every image ships with a description.
  alt_text TEXT NOT NULL CHECK (length(alt_text) > 0),
  width INTEGER,
  height INTEGER,
  position INTEGER NOT NULL DEFAULT 0,
  -- Moderation gate. Only 'approved' rows are publicly listed or served;
  -- the uploader can see their own pending/rejected items.
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  view_count INTEGER NOT NULL DEFAULT 0,
  file_size INTEGER,
  reviewed_by TEXT REFERENCES users(id),
  reviewed_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO media_new (id, mod_id, uploader_id, r2_key, kind, alt_text,
                       width, height, position, created_at, status)
  SELECT id, mod_id, uploader_id, r2_key, kind, alt_text,
         width, height, position, created_at, 'approved'
  FROM media;

DROP TABLE media;
ALTER TABLE media_new RENAME TO media;

CREATE INDEX idx_media_mod ON media(mod_id, position);
CREATE INDEX idx_media_status ON media(status, created_at);

-- Mod page views, incremented through the view beacon (one count per
-- viewer per hour, enforced by the rate-counter table). A rollup like
-- download_count: display data, never the source of truth.
ALTER TABLE mods ADD COLUMN view_count INTEGER NOT NULL DEFAULT 0;

-- Moderation is by appointment, and today exactly one person holds it:
-- devnull. Clear any previously elevated role, then seat the super admin
-- by Discord snowflake. The OAuth callback re-asserts this on every login
-- (SUPER_ADMIN_DISCORD_ID in wrangler.jsonc), so this also works if the
-- account has never signed in when the migration runs.
UPDATE users SET role = 'user', updated_at = datetime('now') WHERE role <> 'user';
UPDATE users SET role = 'admin', updated_at = datetime('now')
  WHERE discord_id = '867190209217429514';
