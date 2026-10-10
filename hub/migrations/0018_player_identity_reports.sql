-- Migration number: 0018 	 2026-10-10
-- Hub identities in game, player reports, and matchmaking bans
-- (docs/player_identity.md).
--
-- In game a player is whatever Steam or Xbox calls them; on the hub the same
-- person is their Discord account. Every multiplayer player signs the
-- launcher in, so the game can show the hub name and avatar instead, but a
-- host cannot take a joiner's word for who it is. Hence tickets: a player's
-- game asks the hub for one, naming the host's account (the audience) and
-- its own in-game name, and hands it to the host; the host trades it back
-- for the account. Only the named host can trade it, and only for the
-- in-game name it was issued for, so a ticket passed on to another host is
-- worthless. Only the hash is stored, like an API key.
CREATE TABLE identity_tickets (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  audience_user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
  platform_name TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at TEXT NOT NULL
);
CREATE INDEX idx_identity_tickets_expires ON identity_tickets(expires_at);

-- A player reporting another from the post-game screen. Its own table, not
-- `reports`: that one's reason is a CHECK enum about mods (malware, stolen,
-- ...) that SQLite cannot widen in place, and these carry a match to judge
-- them by. One report per reporter, subject and match; a report from outside
-- a match (no host_match_id) is one per pair until decided.
--
-- `subject_name` is the name the reporter saw in game, kept because names
-- are what reporters remember. `host_match_id` is the id the host's game
-- made (docs/match_stats.md); the match it names may arrive at the hub
-- after the report or never (a private game), so it is not a foreign key.
CREATE TABLE player_reports (
  id TEXT PRIMARY KEY,
  reporter_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  subject_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  reason TEXT NOT NULL CHECK (reason IN
    ('cheating', 'betraying', 'harassment', 'griefing', 'quitting', 'name', 'other')),
  detail TEXT,
  subject_name TEXT,
  host_match_id TEXT,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'upheld', 'dismissed')),
  decided_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  decided_at TEXT,
  decision_note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  CHECK (reporter_id <> subject_id)
);
CREATE UNIQUE INDEX idx_player_reports_once
  ON player_reports(reporter_id, subject_id, COALESCE(host_match_id, ''));
CREATE INDEX idx_player_reports_subject ON player_reports(subject_id, status);
CREATE INDEX idx_player_reports_status ON player_reports(status, created_at);

-- A ban from matchmaking, not from the hub: the account still signs in,
-- downloads and comments (that is `users.banned_at`). A banned player cannot
-- list a game or join one from the browser, and a public game's host removes
-- them when it learns who they are. Rows are kept when a ban ends or is
-- lifted, so an account's history stays readable; the active ban is the one
-- not lifted and not expired. expires_at NULL is permanent.
CREATE TABLE matchmaking_bans (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  reason TEXT NOT NULL,
  banned_by TEXT REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at TEXT,
  lifted_at TEXT,
  lifted_by TEXT REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX idx_matchmaking_bans_user ON matchmaking_bans(user_id, lifted_at);
