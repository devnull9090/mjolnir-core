-- Migration number: 0020 	 2026-10-17
-- Match chat: what players said in a match, for moderators only
-- (docs/match_stats.md, docs/player_identity.md).
--
-- The host's game records every chat line its match carried and sends the
-- whole log to the hub, at checkpoints during the match and once more at the
-- end; each send replaces the last. A report filed from that match can then
-- be judged by what was actually said. Nothing here is ever shown in public:
-- the only read is the moderation queue's.
--
-- Keyed by the host's own id for the match, not `matches.id`: a private game
-- is never reported as a match, and its chat still has to be there when one
-- of its players is reported.
CREATE TABLE match_chat_logs (
  host_match_id TEXT PRIMARY KEY,
  -- The host whose game sent it; only that account may send it again.
  -- No cascade: this is what a ban was decided on.
  reporter_user_id TEXT NOT NULL REFERENCES users(id),
  map_code TEXT,
  -- The host's clock, in the form `matches.started_at` takes.
  started_at TEXT,
  line_count INTEGER NOT NULL DEFAULT 0,
  received_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- One line as the host's game saw it. `player_index` is the simulation's
-- (-1 for a line no player sent); `name` is the in-game (Steam or Xbox)
-- name. `user_id` and `display_name` are the hub account the host's game
-- resolved for that seat, when it had one: the host's word, so no foreign
-- key, and kept even if the account goes.
CREATE TABLE match_chat_lines (
  host_match_id TEXT NOT NULL REFERENCES match_chat_logs(host_match_id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  t_ms INTEGER NOT NULL,
  player_index INTEGER NOT NULL,
  name TEXT NOT NULL,
  user_id TEXT,
  display_name TEXT,
  team TEXT CHECK (team IN ('red', 'blue')),
  channel TEXT NOT NULL DEFAULT 'all' CHECK (channel IN ('all', 'team')),
  text TEXT NOT NULL,
  PRIMARY KEY (host_match_id, seq)
) WITHOUT ROWID;
CREATE INDEX idx_match_chat_lines_user ON match_chat_lines(user_id) WHERE user_id IS NOT NULL;
