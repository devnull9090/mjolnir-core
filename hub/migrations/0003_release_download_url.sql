-- Migration number: 0003 	 2026-08-02
-- Script/native mod releases live in the signed releases bucket, not the
-- upload bucket, so a release can now carry an external download URL.
-- The download endpoint redirects to it (still counting) instead of
-- streaming from MODS_BUCKET.

ALTER TABLE mod_releases ADD COLUMN download_url TEXT;
