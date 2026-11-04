; Yoyorast Island V2's scripts, for a simulation that replicates its devices.
; The original is decompiled in docs/re/yoyorast_island_v2.decompiled.hsc.
;
; CE 1.0 could not replicate a device, so the original drives a vehicle onto
; one of two bipeds and every machine moves its own door when one dies, and
; works out which machine is the host from four probes. None of that is
; needed: these scripts run on the host only (a client starts no startup or
; continuous script, sim 0x1fca30), and it owns the devices. Each door is one
; rule over its control and the original's reset after 1800 (60 seconds).
;
; A press raises the barrier for those 60 seconds: gatepath's position 0 is
; its closed one, the others' position 1.
;
; A panic shield is a machine parked under the map at position 0
; (tools/level/ce_machines.py), not one that is created and destroyed.
;
; Not carried yet: the teleporter's direction pips (scenery permutations),
; the respawn teleports, anti-cheat and the banshee volumes, which need
; named vehicles, and race detection.

(global short plyrnum 0)
(global short destination_number 0)

(script continuous increase_plyrnum
    (set plyrnum (+ plyrnum 1))
    (if (> plyrnum 15) (set plyrnum 0)))

(script continuous kill_volume
    (if (volume_test_object deathbox (list_get (players) plyrnum))
        (unit_kill (unit (list_get (players) plyrnum)))))

(script continuous gatemain_rule
    (if (= (device_get_position gatemain_control) 1.0)
        (device_set_position gatemain_machine 1.0)
        (device_set_position gatemain_machine 0.0))
    (sleep 15))

(script continuous gatemain_auto
    (sleep_until (= (device_get_position gatemain_control) 1.0))
    (sleep 1800)
    (device_set_position gatemain_control 0.0))

(script continuous gateramp_rule
    (if (= (device_get_position gateramp_control) 1.0)
        (device_set_position gateramp_machine 1.0)
        (device_set_position gateramp_machine 0.0))
    (sleep 15))

(script continuous gateramp_auto
    (sleep_until (= (device_get_position gateramp_control) 1.0))
    (sleep 1800)
    (device_set_position gateramp_control 0.0))

(script startup gatepath_start
    (device_set_position_immediate gatepath_machine 1.0))

(script continuous gatepath_rule
    (if (= (device_get_position gatepath_control) 1.0)
        (device_set_position gatepath_machine 0.0)
        (device_set_position gatepath_machine 1.0))
    (sleep 15))

(script continuous gatepath_auto
    (sleep_until (= (device_get_position gatepath_control) 1.0))
    (sleep 1800)
    (device_set_position gatepath_control 0.0))

(script continuous gateflag1_rule
    (if (= (device_get_position gateflag1_control) 1.0)
        (device_set_position gateflag1_machine 1.0)
        (device_set_position gateflag1_machine 0.0))
    (sleep 15))

(script continuous gateflag1_auto
    (sleep_until (= (device_get_position gateflag1_control) 1.0))
    (sleep 1800)
    (device_set_position gateflag1_control 0.0))

(script continuous gateflag2_rule
    (if (= (device_get_position gateflag2_control) 1.0)
        (device_set_position gateflag2_machine 1.0)
        (device_set_position gateflag2_machine 0.0))
    (sleep 15))

(script continuous gateflag2_auto
    (sleep_until (= (device_get_position gateflag2_control) 1.0))
    (sleep 1800)
    (device_set_position gateflag2_control 0.0))

(script continuous panicroom_rule
    (if (= (device_get_position panicroom_control) 1.0)
        (device_set_position panicroom_machine 1.0)
        (device_set_position panicroom_machine 0.0))
    (sleep 15))

(script continuous panicroom_auto
    (sleep_until (= (device_get_position panicroom_control) 1.0))
    (sleep 1800)
    (device_set_position panicroom_control 0.0))

(script continuous panicbal_rule
    (if (= (device_get_position panicbal_control) 1.0)
        (device_set_position panicbal_machine 1.0)
        (device_set_position panicbal_machine 0.0))
    (sleep 15))

(script continuous panicbal_auto
    (sleep_until (= (device_get_position panicbal_control) 1.0))
    (sleep 1800)
    (device_set_position panicbal_control 0.0))

(script continuous panichall1_rule
    (if (= (device_get_position panichall1_control) 1.0)
        (device_set_position panichall1_machine 1.0)
        (device_set_position panichall1_machine 0.0))
    (sleep 15))

(script continuous panichall1_auto
    (sleep_until (= (device_get_position panichall1_control) 1.0))
    (sleep 1800)
    (device_set_position panichall1_control 0.0))

(script continuous panichall2_rule
    (if (= (device_get_position panichall2_control) 1.0)
        (device_set_position panichall2_machine 1.0)
        (device_set_position panichall2_machine 0.0))
    (sleep 15))

(script continuous panichall2_auto
    (sleep_until (= (device_get_position panichall2_control) 1.0))
    (sleep 1800)
    (device_set_position panichall2_control 0.0))

(script continuous panichill_rule
    (if (= (device_get_position panichill_control) 1.0)
        (device_set_position panichill_machine 1.0)
        (device_set_position panichill_machine 0.0))
    (sleep 15))

(script continuous panichill_auto
    (sleep_until (= (device_get_position panichill_control) 1.0))
    (sleep 1800)
    (device_set_position panichill_control 0.0))

; The random teleporter: a new destination every 30 seconds, weighted as the
; original's repeated entries weight it (begin_random runs every branch, in a
; random order, so the last one stands).
(script continuous randomize_teleport
    (begin_random
        (set destination_number 0) (set destination_number 0) (set destination_number 0)
        (set destination_number 1) (set destination_number 1) (set destination_number 1)
        (set destination_number 2)
        (set destination_number 3) (set destination_number 3) (set destination_number 3)
        (set destination_number 4)
        (set destination_number 5) (set destination_number 5)
        (set destination_number 6) (set destination_number 6) (set destination_number 6)
        (set destination_number 7) (set destination_number 7)
        (set destination_number 8)
        (set destination_number 9)
        (set destination_number 10) (set destination_number 10) (set destination_number 10) (set destination_number 10)
        (set destination_number 11) (set destination_number 11) (set destination_number 11) (set destination_number 11)
        (set destination_number 12)
        (set destination_number 13)
        (set destination_number 14) (set destination_number 14))
    (sleep 900))

(script continuous teleport_player
    (if (or (volume_test_object red_teleport_entrance (list_get (players) plyrnum))
            (volume_test_object blue_teleport_entrance (list_get (players) plyrnum)))
        (begin
            (if (= destination_number 0) (object_teleport (unit (list_get (players) plyrnum)) atvbase))
            (if (= destination_number 1) (object_teleport (unit (list_get (players) plyrnum)) beachbase))
            (if (= destination_number 2) (object_teleport (unit (list_get (players) plyrnum)) bluedanube))
            (if (= destination_number 3) (object_teleport (unit (list_get (players) plyrnum)) campingspot))
            (if (= destination_number 4) (object_teleport (unit (list_get (players) plyrnum)) centralroom))
            (if (= destination_number 5) (object_teleport (unit (list_get (players) plyrnum)) creditroom))
            (if (= destination_number 6) (object_teleport (unit (list_get (players) plyrnum)) garage))
            (if (= destination_number 7) (object_teleport (unit (list_get (players) plyrnum)) ghostbase))
            (if (= destination_number 8) (object_teleport (unit (list_get (players) plyrnum)) panicbalcony))
            (if (= destination_number 9) (object_teleport (unit (list_get (players) plyrnum)) paniccorridor))
            (if (= destination_number 10) (object_teleport (unit (list_get (players) plyrnum)) panichill))
            (if (= destination_number 11) (object_teleport (unit (list_get (players) plyrnum)) panicroom))
            (if (= destination_number 12) (object_teleport (unit (list_get (players) plyrnum)) sniperno1))
            (if (= destination_number 13) (object_teleport (unit (list_get (players) plyrnum)) sniperno2))
            (if (= destination_number 14) (object_teleport (unit (list_get (players) plyrnum)) thecrater)))))
