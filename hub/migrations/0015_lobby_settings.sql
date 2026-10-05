-- Migration number: 0015 	 2026-10-05
-- A listed game's rules: the host's game settings line
-- (docs/host_game_settings.md), `key=value;...` of Megalo variant fields
-- with a score to win per game type. /join hands it to a player joining the
-- game, whose level loader patches it into its own copy of the variant, so a
-- player who arrives mid-match plays by the host's rules. NULL for a host
-- from before game settings: the variant's own rules.
ALTER TABLE lobbies ADD COLUMN settings TEXT;
