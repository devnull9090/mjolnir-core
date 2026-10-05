-- Migration number: 0014 	 2026-10-03
-- Match history: what happened in each public multiplayer match
-- (docs/match_stats.md).
--
-- The host of a public game reports each match it ran when the match ends:
-- the final standings and every incident the simulation raised, in order,
-- with where the players involved stood. Standings feed the player pages
-- now and ranking later; the events are the time series (and, with their
-- positions, the heatmaps) built on later.
--
-- A player is who the host's game named them. A participant's own game can
-- claim its seat with its own hub key, which links the seat to their hub
-- account; the host's own seat is linked by the report itself.

-- 0001 carried placeholder `matches` and `match_players` tables over from
-- the pre-migrations schema ("Multiplayer (future)"). Nothing has ever read
-- or written them, but this renames rather than drops them, so whatever a
-- hand might have put there survives until someone checks and drops them.
-- (`player_stats`, their third, is left as it is.)
ALTER TABLE match_players RENAME TO legacy_match_players;
ALTER TABLE matches RENAME TO legacy_matches;

CREATE TABLE matches (
  id TEXT PRIMARY KEY,
  -- The host's own id for the match: the id its fireteam's claims cite.
  -- Never shown; a seat is claimable only by those who were told it.
  host_match_id TEXT NOT NULL UNIQUE,
  reporter_user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  -- The listing it was played under. No reference: listings are swept
  -- minutes after their game ends.
  lobby_id TEXT,
  map_code TEXT NOT NULL,
  game_type TEXT NOT NULL,
  team_game INTEGER NOT NULL DEFAULT 0 CHECK (team_game IN (0, 1)),
  score_to_win INTEGER,
  started_at TEXT NOT NULL,
  ended_at TEXT NOT NULL,
  duration_ms INTEGER NOT NULL,
  -- round_over / game_over: played to the end. abandoned: the host left
  -- it, ended it early, or lost it to a crash.
  end_reason TEXT NOT NULL CHECK (end_reason IN ('round_over', 'game_over', 'abandoned')),
  red_score INTEGER,
  blue_score INTEGER,
  -- 'red' / 'blue' for a team win, a player index for a free-for-all win,
  -- 'draw', or NULL for an abandoned match.
  winner TEXT,
  player_count INTEGER NOT NULL,
  event_count INTEGER NOT NULL DEFAULT 0,
  client_version TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_matches_ended ON matches(ended_at DESC);
CREATE INDEX idx_matches_map ON matches(map_code, game_type, ended_at DESC);

-- A seat in a match: the final line of the scoreboard.
CREATE TABLE match_players (
  match_id TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
  -- The simulation's absolute player index: what the events name.
  player_index INTEGER NOT NULL CHECK (player_index BETWEEN 0 AND 15),
  name TEXT NOT NULL,
  team TEXT CHECK (team IN ('red', 'blue')),
  score INTEGER NOT NULL DEFAULT 0,
  kills INTEGER NOT NULL DEFAULT 0,
  deaths INTEGER NOT NULL DEFAULT 0,
  suicides INTEGER NOT NULL DEFAULT 0,
  captures INTEGER NOT NULL DEFAULT 0,
  -- 1 = top of the scoreboard; shared on a tie.
  place INTEGER NOT NULL,
  -- 'win' / 'loss' / 'draw'; NULL for an abandoned match.
  outcome TEXT CHECK (outcome IN ('win', 'loss', 'draw')),
  -- Quit or was booted before the end.
  left_early INTEGER NOT NULL DEFAULT 0 CHECK (left_early IN (0, 1)),
  is_host INTEGER NOT NULL DEFAULT 0 CHECK (is_host IN (0, 1)),
  -- The hub account behind the seat, once linked (host report or claim).
  user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
  PRIMARY KEY (match_id, player_index)
);
CREATE INDEX idx_match_players_user ON match_players(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX idx_match_players_name ON match_players(name COLLATE NOCASE);

-- Everything the simulation raised during a match, in order: kills, deaths,
-- spawns, medals, flags. `cause` and `effect` are player indices (-1 for
-- none): for a kill the killer and the victim. Positions are where the
-- cause's and the effect's objects (bipeds, or the vehicle a player drove)
-- stood when the incident arrived, in the map's Unreal world space
-- (centimetres, Z up).
CREATE TABLE match_events (
  match_id TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  t_ms INTEGER NOT NULL,
  type TEXT NOT NULL,
  cause INTEGER NOT NULL DEFAULT -1,
  effect INTEGER NOT NULL DEFAULT -1,
  value INTEGER,
  weapon TEXT,
  modifier INTEGER,
  cause_x REAL, cause_y REAL, cause_z REAL,
  effect_x REAL, effect_y REAL, effect_z REAL,
  PRIMARY KEY (match_id, seq)
) WITHOUT ROWID;
CREATE INDEX idx_match_events_type ON match_events(type, match_id);

-- A participant's own game claiming its seat. Kept apart from the seat so
-- either can arrive first: whichever lands second links the seat, and only
-- when the claimed name is the seat's.
CREATE TABLE match_claims (
  host_match_id TEXT NOT NULL,
  player_index INTEGER NOT NULL CHECK (player_index BETWEEN 0 AND 15),
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (host_match_id, player_index),
  UNIQUE (host_match_id, user_id)
);
CREATE INDEX idx_match_claims_created ON match_claims(created_at);
