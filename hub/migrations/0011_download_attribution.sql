-- Migration number: 0011 	 2026-08-12
-- Attributed downloads, so a profile can say what an account has installed.
--
-- `mods.download_count` and `mod_releases.download_count` stay exactly what
-- they were: anonymous rollups of every download, signed in or not. This
-- table answers a different question — which accounts pulled which release —
-- and only ever gains a row when the download request carried a credential
-- (a session cookie, or a paired client's API key). Anonymous downloads are
-- counted, never attributed, and nothing here backfills the ones that
-- happened before this migration.
--
-- One row per (account, release): re-downloading the same release is not new
-- activity, and `created_at` therefore records the first pull, not the last.
-- `mod_id` is denormalised off the release so "how many distinct mods" is an
-- index-only count rather than a join.

CREATE TABLE mod_downloads (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  mod_id TEXT NOT NULL REFERENCES mods(id) ON DELETE CASCADE,
  release_id TEXT NOT NULL REFERENCES mod_releases(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (user_id, release_id)
);

-- The profile query: distinct mods for one account, newest first.
CREATE INDEX idx_mod_downloads_user ON mod_downloads(user_id, mod_id);
