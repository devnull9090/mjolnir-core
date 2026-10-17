-- Migration number: 0019 	 2026-10-17
-- Crash reports from the launcher (docs/crash_reports.md).
--
-- When the game crashes the launcher asks the player, and on a yes files
-- the crash here with a small bundle: the redacted crash context, a slim
-- dump (thread stacks only), the UE4SS log and the installed mods. The hub
-- groups crashes by `signature`, a hash of the build, the crash type and
-- where it crashed, and asks for the full memory dump only while it holds
-- fewer than a few for that signature and build; the player says yes again
-- before that goes.
--
-- `crash_id` is UE's crash folder name, unique per crash, so a launcher that
-- sends the same crash twice gets the report it already made. The files
-- live in R2 under crashes/<id>/ (MODS_BUCKET, which is never served
-- directly) and go after 90 days with the row.
CREATE TABLE crash_reports (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  crash_id TEXT NOT NULL,
  signature TEXT NOT NULL,
  build_version TEXT NOT NULL,
  crash_type TEXT NOT NULL,
  fault TEXT NOT NULL,
  error_message TEXT,
  crashed_at TEXT NOT NULL,
  seconds_since_start INTEGER,
  mode TEXT,
  map TEXT,
  role TEXT,
  launcher_version TEXT,
  -- What the launcher said it would upload, checked when it does.
  bundle_sha256 TEXT NOT NULL,
  bundle_bytes INTEGER NOT NULL,
  dump_bytes INTEGER,
  bundle_key TEXT,
  -- The hub asked this report for its full dump.
  dump_wanted INTEGER NOT NULL DEFAULT 0,
  dump_key TEXT,
  dump_zip_bytes INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX idx_crash_reports_once ON crash_reports(user_id, crash_id);
CREATE INDEX idx_crash_reports_signature ON crash_reports(signature, build_version, created_at);
CREATE INDEX idx_crash_reports_created ON crash_reports(created_at);
