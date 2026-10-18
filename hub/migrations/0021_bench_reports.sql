-- Migration number: 0021 	 2026-10-17
-- Bench reports: what the remastered maps cost on players' own PCs
-- (docs/performance.md).
--
-- A player types /bench in match chat (or `mjolnir_bench send` in the
-- console). MJOLNIRHud holds the camera, times the map as it is against
-- the map without its foliage, the foliage's shadows and its wind, and
-- queues the result; MJOLNIRLobby sends it signed with the launcher's key.
-- The hub shows them by GPU and map, never by account: `user_id` is kept
-- for rate limits, duplicates and deleting an account's data.
--
-- `bench_id` is the game's own id for the run, so a resend lands on the
-- same row.
CREATE TABLE bench_reports (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  bench_id TEXT NOT NULL,
  map_code TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('foliage', 'cvar')),
  label TEXT NOT NULL,
  gpu_name TEXT,
  -- The game's own GPU benchmark (Saved/GpuBenchmark.json); 2060 on an
  -- RTX 5090.
  gpu_score INTEGER,
  cpu TEXT,
  cpu_threads INTEGER,
  -- The size drawn, before r.ScreenPercentage.
  viewport_w INTEGER,
  viewport_h INTEGER,
  window_mode TEXT,
  vsync INTEGER NOT NULL DEFAULT 0,
  fps_limit REAL,
  screen_percentage REAL,
  -- {"ViewDistance": 3, ..., "Foliage": 3}: every sg.*Quality.
  sg_json TEXT NOT NULL,
  foliage_quality INTEGER,
  seconds_in_world INTEGER,
  base_ms REAL NOT NULL,
  base_min_ms REAL,
  base_max_ms REAL,
  -- [{"name": "no foliage", "ms": 6.42}, ...]
  results_json TEXT NOT NULL,
  -- "no foliage" less the base, for a foliage bench: the number the page
  -- sorts and averages.
  foliage_delta_ms REAL,
  client_version TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (user_id, bench_id)
);
CREATE INDEX idx_bench_reports_map ON bench_reports(map_code, created_at);
CREATE INDEX idx_bench_reports_gpu ON bench_reports(gpu_name, map_code);
