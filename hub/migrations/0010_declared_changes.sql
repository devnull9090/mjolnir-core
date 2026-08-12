-- Migration number: 0010 	 2026-08-11
-- The declared change list a release archive carries (changes.json),
-- stored as validated JSON at scan time so mod pages and the launcher can
-- show what a release edits without re-reading the archive from R2.
-- NULL means the archive predates the transparency format.

ALTER TABLE mod_releases ADD COLUMN changes_json TEXT;
