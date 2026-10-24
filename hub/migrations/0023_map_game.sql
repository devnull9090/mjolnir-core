-- Migration number: 0023 	 2026-10-23
-- Which game a map comes from (docs/map_distribution.md): Halo CE or
-- Halo 2. Halo 2's multiplayer maps are joining the catalog beside the
-- Halo CE ones, and a player looking for Lockout should not have to scroll
-- past Blood Gulch to find it.
--
-- Nullable like the 0017 metadata: a map whose author never said is
-- unknown. A release's manifest sets it (`map.game`); the owner, its
-- authors and moderators edit it with PATCH /maps/{code}. GET /maps takes
-- `game=` as an exact-match filter, so an unknown map is left out of a
-- filtered list but still in the unfiltered one.
--
-- Every map published before this migration is a Halo CE map: the 19
-- classics and the converted Custom Edition maps.
--
-- No new index, for the reason 0017 gives: the catalog is tens of rows.
ALTER TABLE map_listings ADD COLUMN game TEXT CHECK (game IN ('halo1', 'halo2'));

UPDATE map_listings SET game = 'halo1' WHERE game IS NULL;
