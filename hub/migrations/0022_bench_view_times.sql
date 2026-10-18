-- Migration number: 0022 	 2026-10-18
-- Where a bench was taken and where its frame went (docs/performance.md).
--
-- The first players' reports (2026-10-18) were one map twice, 19.6 ms and
-- 8.2 ms, with nothing to say why: the bench holds the camera where the
-- player stands, and the report did not say where that was. Nor whether the
-- frame waited on the game thread, the render thread or the GPU, which is
-- what decides whether taking something away helps at all.
--
-- `view_*` is the held camera: world position (cm) and pitch and yaw (deg).
-- `base_times_json` is stat unit's split of the base frame, in ms:
-- {"game", "game_cp", "draw", "draw_cp", "rhit", "gpu"} (MJOLNIRHud's
-- native\mjolnir_frame_times.dll, native/frame_times). Each result in
-- `results_json` may carry the same split as `times`. Reports from clients
-- before MJOLNIRHud 0.11.0 have none of these.
ALTER TABLE bench_reports ADD COLUMN view_x REAL;
ALTER TABLE bench_reports ADD COLUMN view_y REAL;
ALTER TABLE bench_reports ADD COLUMN view_z REAL;
ALTER TABLE bench_reports ADD COLUMN view_pitch REAL;
ALTER TABLE bench_reports ADD COLUMN view_yaw REAL;
ALTER TABLE bench_reports ADD COLUMN base_times_json TEXT;
