-- The map block a release's manifest carries, as its scan saw it. A held release
-- keeps it here until it publishes, so `map_listings` only ever says what a
-- published release said, and while the release is in the review queue it holds
-- the block's code against other mods (docs/map_distribution.md). NULL for a
-- release with no map block, and for one scanned before this column.
ALTER TABLE mod_releases ADD COLUMN map_json TEXT;
