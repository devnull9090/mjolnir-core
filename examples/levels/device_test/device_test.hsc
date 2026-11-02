; Device replication test (docs/re/ce_map_scripts.md).
;
; elevator_a_control_2 (the switch at the top of the elevator shaft) is cut
; from the elevator's device group by the level's blam.set, so pressing it
; only moves the switch itself. This script then opens blamdevicemachine28,
; the door beside it, the way Yoyorast Island's scripts drive its gates: watch
; the control's position, move the machine, reset both after a while.
; elevator_a_control_1 (bottom) still drives the elevator natively.
;
; The counters below prove each script form runs in a Megalo match (all do,
; 2026-11-02, once the bake kept the source and its stub lost an unregistered
; string id). Read them with fades through mjolnir_sim_script, e.g.
;   (if (and mj_started (> mj_ticks 5)) (fade_out 0 1 0 5) (fade_out 1 0 0 5))

(global boolean mj_started false)
(global real mj_rticks 0)
(global short mj_ticks 0)
(global short mj_loop_ticks 0)
(global short mj_presses 0)

; The plainest proofs: a startup script that sets a flag, and a real counter.
(script startup mj_mark
    (set mj_started true))

(script continuous mj_rbeat
    (set mj_rticks (+ mj_rticks 1.0))
    (sleep 30))

; One count per second, as a continuous script.
(script continuous mj_heartbeat
    (set mj_ticks (+ mj_ticks 1))
    (sleep 30))

; One count per second, as a startup loop.
(script startup mj_heartbeat_loop
    (sleep_until
        (begin
            (set mj_loop_ticks (+ mj_loop_ticks 1))
            false)
        30))

(script static void mj_door_cycle
    (set mj_presses (+ mj_presses 1))
    (device_set_power blamdevicemachine28 1.0)
    (device_set_position blamdevicemachine28 1.0)
    (sleep 300)
    (device_set_position blamdevicemachine28 0.0)
    (device_set_position elevator_a_control_2 0.0)
    (sleep 30))

(script startup mj_scripted_door_loop
    (sleep_until
        (begin
            (sleep_until (>= (device_get_position elevator_a_control_2) 1.0) 1)
            (mj_door_cycle)
            false)
        1))
