-- What a release needs of the launcher that installs it: a JSON array of
-- feature names (src/lib/api/clients.ts), NULL for none. Measured at scan and
-- publish, never declared: `local-chunk-numbers` when a shader library sits
-- under a number an old launcher cannot load, or shares its library chunk
-- with another mod's published release (docs/chunk_numbering.md). A release
-- scanned before this column reads as needing nothing.
ALTER TABLE mod_releases ADD COLUMN requires TEXT;
