-- Migration number: 0002 	 2026-08-01
-- Fixed-window rate counters for write endpoints.
--
-- key is "<subject>|<bucket>|<window-start>": one row per subject per
-- window, upserted on every counted request. Stale windows are deleted
-- opportunistically by the same upsert path, so no cron is needed.

CREATE TABLE rate_counters (
  key TEXT PRIMARY KEY,
  count INTEGER NOT NULL DEFAULT 0,
  window_start INTEGER NOT NULL -- unix seconds, for cleanup
);
CREATE INDEX idx_rate_window ON rate_counters(window_start);
