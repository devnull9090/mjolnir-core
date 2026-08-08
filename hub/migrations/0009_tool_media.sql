-- Migration number: 0009 	 2026-08-06
-- Photo previews for the tools pages (/tools/{slug}).
--
-- A tool is not a row in `mods` — it is an entry in the code registry at
-- src/lib/tools.ts — so its gallery cannot hang off `mod_id`. Rather than a
-- second media table with a second copy of the serve, delete, view and
-- moderation paths, `media` gains a `tool_slug` and `mod_id` becomes
-- nullable: exactly one of the two identifies what an item belongs to.
--
-- The table is rebuilt because SQLite cannot drop a NOT NULL constraint.
-- Every existing row belongs to a mod and carries `tool_slug` NULL, so the
-- CHECK below holds for all of them.

CREATE TABLE media_new (
  id TEXT PRIMARY KEY,
  -- Nullable now: set for a mod's gallery, NULL for a tool's.
  mod_id TEXT REFERENCES mods(id) ON DELETE CASCADE,
  -- The slug in src/lib/tools.ts. Deliberately not a foreign key: tools are
  -- defined in code, and the API validates the slug against that registry
  -- before it ever writes a row here.
  tool_slug TEXT,
  uploader_id TEXT NOT NULL REFERENCES users(id),
  r2_key TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'screenshot' CHECK (kind IN ('screenshot', 'thumbnail', 'video')),
  alt_text TEXT NOT NULL CHECK (length(alt_text) > 0),
  width INTEGER,
  height INTEGER,
  position INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  view_count INTEGER NOT NULL DEFAULT 0,
  file_size INTEGER,
  reviewed_by TEXT REFERENCES users(id),
  reviewed_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  -- One owner, never both, never neither.
  CHECK ((mod_id IS NULL) <> (tool_slug IS NULL))
);

INSERT INTO media_new (id, mod_id, uploader_id, r2_key, kind, alt_text, width, height,
                       position, status, view_count, file_size, reviewed_by, reviewed_at,
                       created_at)
  SELECT id, mod_id, uploader_id, r2_key, kind, alt_text, width, height,
         position, status, view_count, file_size, reviewed_by, reviewed_at,
         created_at
  FROM media;

DROP TABLE media;
ALTER TABLE media_new RENAME TO media;

CREATE INDEX idx_media_mod ON media(mod_id, position);
CREATE INDEX idx_media_status ON media(status, created_at);
-- The tool gallery read: every approved item for one tool, in gallery order.
CREATE INDEX idx_media_tool ON media(tool_slug, position);
