-- Migration number: 0017 	 2026-10-09
-- What a player filters the maps catalog by (docs/map_distribution.md):
-- how big a map is, how many players it suits, whether it has vehicles, and
-- where it came from. Community maps are arriving, and nobody browses them
-- by title alone.
--
-- All nullable: a map whose author never said is unknown, not small, and
-- every filter lets an unknown through rather than hiding the map. A
-- release's manifest sets them (never `origin = 'classic'`, which only a
-- moderator or this migration sets); the owner and moderators edit them
-- with PATCH /maps/{code}.
--
-- No new index. The catalog is tens of rows, read through a join to `mods`
-- whose sort keys are already indexed; a scan of map_listings is the
-- cheapest plan there is.
ALTER TABLE map_listings ADD COLUMN size TEXT CHECK (size IN ('small', 'medium', 'large'));
ALTER TABLE map_listings ADD COLUMN players_min INTEGER CHECK (players_min BETWEEN 1 AND 16);
ALTER TABLE map_listings ADD COLUMN players_max INTEGER CHECK (players_max BETWEEN 1 AND 16);
ALTER TABLE map_listings ADD COLUMN vehicles INTEGER CHECK (vehicles IN (0, 1));
ALTER TABLE map_listings ADD COLUMN origin TEXT
  CHECK (origin IN ('classic', 'custom_edition', 'original'));

-- The 19 classic Halo CE maps, by code. Only empty columns are filled, and
-- only on rows that exist: a database without the classics is untouched.
WITH classic (code, size, vehicles, players_min, players_max) AS (
  VALUES
    ('BCK', 'small', 0, 2, 8),
    ('BGL', 'large', 1, 4, 16),
    ('BDA', 'medium', 0, 4, 16),
    ('CHL', 'small', 0, 2, 8),
    ('PTP', 'small', 0, 2, 8),
    ('DMN', 'medium', 0, 4, 12),
    ('DCN', 'large', 1, 8, 16),
    ('DTI', 'large', 1, 8, 16),
    ('DRL', 'small', 0, 2, 8),
    ('GPH', 'large', 1, 8, 16),
    ('HEH', 'medium', 0, 4, 12),
    ('ICE', 'large', 1, 6, 16),
    ('INF', 'large', 1, 8, 16),
    ('LNG', 'small', 0, 2, 6),
    ('PRS', 'small', 0, 2, 8),
    ('RAT', 'medium', 0, 4, 12),
    ('SDW', 'large', 1, 6, 16),
    ('TMB', 'large', 1, 6, 16),
    ('WIZ', 'small', 0, 2, 8)
)
UPDATE map_listings SET
  size = COALESCE(size, (SELECT c.size FROM classic c WHERE c.code = map_listings.code)),
  vehicles = COALESCE(vehicles, (SELECT c.vehicles FROM classic c WHERE c.code = map_listings.code)),
  players_min = COALESCE(players_min, (SELECT c.players_min FROM classic c WHERE c.code = map_listings.code)),
  players_max = COALESCE(players_max, (SELECT c.players_max FROM classic c WHERE c.code = map_listings.code)),
  origin = COALESCE(origin, 'classic')
WHERE code IN (SELECT code FROM classic);
