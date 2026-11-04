; scenario <zteam>
; object names: gateflag1_machine gateflag2_machine gatemain_machine gateramp_machine gatemain_control gateramp_control gateflag2_control gateflag1_control panicbal_control panicroom_control panicbal_machine panichall1_machine panichall2_machine gatepath_machine panichill_control panichall1_control panichall2_control gatepath_control panicroom_machine hogturretv mongoose_3 mongoose_4 yohog_1 yohog_2 yohog_3 yohog_4 yohog_5 yohog_6 banshee_1 mongoose_1 mongoose_2 rhog_1 ghost_1 ghost_2 is_dedicated is_race_check server_exsists server_exsists_biped rock_scaled telepip_blue telepip_red atvbase_biped beachbase_biped bluedanube_biped campingspot_biped centralroom_biped creditroom_biped garage_biped ghostbase_biped panicbalcony_biped paniccorridor_biped panichill_biped panicroom_biped sniperno1_biped sniperno2_biped thecrater_biped telehog rock_scaled_2 panichill_machine server_checker is_server_hog is_server_biped rock_scaled_3 host_check_2 optimize_out_1 optimize_out_2 optimize_out_3 optimize_out_4 optimize_out_5 optimize_out_6 optimize_out_7 optimize_out_8 optimize_out_9 optimize_out_10 optimize_out_11 optimize_out_12 optimize_out_13 optimize_out_14 optimize_out_15 optimize_out_16 optimize_out_17 optimize_out_18 optimize_out_19 optimize_out_20 optimize_out_21 optimize_out_22 optimize_out_23 optimize_out_24 optimize_out_25 platform_hog panicroom_open_biped panicroom_closed_biped panicroom_crusher panicbal_open_biped panicbal_closed_biped panicbal_crusher panichall1_open_biped panichall1_closed_biped panichall2_open_biped panichall2_closed_biped panichall1_crusher panichall2_crusher panichill_open_biped panichill_closed_biped panichill_crusher gateflag1_open_biped gateflag1_closed_biped gateflag2_open_biped gateflag2_closed_biped gateflag1_crusher gateflag2_crusher gatemain_open_biped gatemain_closed_biped gateramp_open_biped gateramp_closed_biped gatepath_open_biped gatepath_closed_biped gatemain_crusher gateramp_crusher gatepath_crusher optimize_out_26 optimize_out_27 optimize_out_29 optimize_out_30 optimize_out_31 optimize_out_32 optimize_out_33 optimize_out_34 banshee_2 tele_block_1 tele_block_2 optimize_out_35
; device groups: []
(global boolean is_server false)
(global boolean is_race false)
(global boolean check_1 false)
(global boolean check_2 false)
(global boolean check_3 false)
(global boolean check_4 false)
(global short plyrnum 0)
(global string destination "atvbase")
(global short destination_number 0)

(script continuous void increase_plyrnum
    (begin (begin (set plyrnum (+ plyrnum 1.0)))))

(script continuous void reset_plyrnum
    (begin (if (= (> plyrnum 15) true) (begin (set plyrnum 0)))))

(script startup void cutscenes
    (begin
    (object_set_scale rock_scaled 2.0 1)
    (object_set_scale rock_scaled_2 1.25 1)
    (object_set_scale rock_scaled_3 1.25 1)
    (begin
        (cinematic_show_letterbox false)
        (cinematic_set_title loading)
        (camera_control true)
        (camera_set spawn 100)
        (sleep 150)
        (camera_control false)
        (cinematic_show_letterbox false))))

(script startup void is_server check
    (begin
    (object_create is_server_biped)
    (sleep 30)
    (if
        (= (unit_get_health is_server_biped) 1.0)
        (begin (set check_1 true))
        (begin (set check_1 false)))))

(script continuous void is_server defined
    (begin
    (if
        (= check_1 true)
        (begin
            (object_create is_server_hog)
            (object_teleport is_server_hog is_server_flag)
            (sleep 10)))))

(script continuous void host_check_secondary
    (begin
    (set is_server false)
    (sleep 150)
    (begin
        (effect_new "effects\sniped" boom_headshot)
        (sleep 30)
        (if
            (<= (unit_get_health host_check_2) 0.0)
            (begin (set check_2 false))
            (begin (set check_2 true))))
    (sleep -1)))

(script startup void host_check_3
    (begin
    (if (<= (list_count (players)) 1) (begin (set check_3 true)) (begin (set check_3 false)))))

(script startup void host_check_4
    (begin
    (object_create_anew platform_hog)
    (sleep 150)
    (if
        (= (volume_test_object platform_trigger platform_hog) true)
        (begin (set check_4 true))
        (begin (set check_4 false)))))

(script startup void is_server_active
    (begin
    (sleep_until (and (= check_1 true) (= check_2 true) (= check_3 true) (= check_4 true)))
    (set is_server true)))

(script startup void is_race check
    (begin
    (object_create is_race_check)
    (sleep_until (<= (unit_get_health is_race_check) 0.0))
    (set is_race true)))

(script dormant void optimize_on
    (begin
    (begin
        (rasterizer_decals_flush)
        (object_destroy_containing "optimize_out_")
        (render_lights false))
    (sleep 30)))

(script dormant void optimize_off
    (begin
    (begin
        (rasterizer_decals_flush)
        (object_create_anew_containing "optimize_out_")
        (render_lights true))
    (sleep 30)))

(script continuous void deadwer
    (begin
    (begin
        (if
            (= (volume_test_object deathbox (list_get (players) plyrnum)) true)
            (begin (unit_kill (unit (list_get (players) plyrnum))))))))

(script continuous void niggalyncha
    (begin
    (begin
        (if
            (or
                (volume_test_object nigger (list_get (players) plyrnum))
                (volume_test_object lyncher (list_get (players) plyrnum)))
            (begin
                (if
                    (or (volume_test_object nigger banshee_2) (volume_test_object lyncher banshee_2))
                    (begin (sleep 1))
                    (begin (unit_kill (unit (list_get (players) plyrnum))))))))))

(script startup void vehicle spawn
    (begin
    (sleep_until (= is_server true))
    (sleep_until (<= (unit_get_health is_race_check) 0.0))
    (sleep 90)
    (if
        (and (= is_server true) (= is_race true))
        (begin
            (object_create_anew rhog_1)
            (object_create_anew yohog_1)
            (object_create_anew yohog_2)
            (object_create_anew yohog_3)
            (object_create_anew yohog_4)
            (object_create_anew yohog_5)
            (object_create_anew yohog_6)
            (object_create_anew mongoose_1)
            (object_create_anew mongoose_2)
            (object_create_anew mongoose_3)
            (object_create_anew mongoose_4)))))

(script startup void vehicle spawn 2
    (begin
    (sleep_until (= is_server true))
    (sleep 90)
    (if
        (= is_server true)
        (begin
            (object_create_anew ghost_1)
            (object_create_anew ghost_2)
            (object_create_anew hogturretv)
            (object_create_anew panicroom_crusher)
            (object_create_anew panicbal_crusher)
            (object_create_anew panichall1_crusher)
            (object_create_anew panichall2_crusher)
            (object_create_anew panichill_crusher)
            (object_create_anew gateflag1_crusher)
            (object_create_anew gateflag2_crusher)
            (object_create_anew gatemain_crusher)
            (object_create_anew gateramp_crusher)
            (object_create_anew gatepath_crusher)
            (object_create_anew server_exsists)
            (object_create_anew telehog)))))

(script continuous void special condition respawn
    (begin
    (if
        (= (volume_test_object vehicletrigger hogturretv) true)
        (object_teleport hogturretv hogturret))
    (if
        (= (volume_test_object vehicletrigger yohog_1) true)
        (object_teleport yohog_1 yohog_1))
    (if
        (= (volume_test_object vehicletrigger yohog_2) true)
        (object_teleport yohog_2 yohog_2))
    (if
        (= (volume_test_object vehicletrigger yohog_3) true)
        (object_teleport yohog_3 yohog_3))
    (if
        (= (volume_test_object vehicletrigger yohog_4) true)
        (object_teleport yohog_4 yohog_4))
    (if
        (= (volume_test_object vehicletrigger yohog_5) true)
        (object_teleport yohog_5 yohog_5))
    (if
        (= (volume_test_object vehicletrigger yohog_6) true)
        (object_teleport yohog_6 yohog_6))
    (if
        (= (volume_test_object vehicletrigger mongoose_1) true)
        (object_teleport mongoose_1 goose_1))
    (if
        (= (volume_test_object vehicletrigger mongoose_2) true)
        (object_teleport mongoose_2 goose_2))
    (if
        (= (volume_test_object vehicletrigger ghost_1) true)
        (object_teleport ghost_1 ghost_1))
    (if
        (= (volume_test_object vehicletrigger ghost_2) true)
        (object_teleport ghost_2 ghost_2))
    (if
        (= (volume_test_object vehicletrigger mongoose_3) true)
        (object_teleport mongoose_3 goose_3))
    (if
        (= (volume_test_object vehicletrigger mongoose_4) true)
        (object_teleport mongoose_4 goose_4))
    (if (= (volume_test_object vehicletrigger rhog_1) true) (object_teleport rhog_1 rhog_1))))

(script continuous void panicroom_shield_check
    (begin
    (if
        (= (device_get_position panicroom_control) 1.0)
        (begin (object_teleport panicroom_crusher panicroom_open_flag) (sleep 15))
        (begin (object_teleport panicroom_crusher panicroom_closed_flag) (sleep 15)))))

(script continuous void panicroom_shield_auto
    (begin
    (sleep_until (= (device_get_position panicroom_control) 1.0))
    (sleep 1800)
    (device_set_position panicroom_control 0.0)))

(script continuous void panicroom_shield_sync
    (begin
    (if
        (< (unit_get_health panicroom_open_biped) 0.1)
        (begin
            (object_create panicroom_machine)
            (device_set_position panicroom_machine 1.0)
            (object_create_anew panicroom_closed_biped)
            (object_create_anew panicroom_open_biped)
            (sleep 15)))
    (if
        (< (unit_get_health panicroom_closed_biped) 0.1)
        (begin
            (device_set_position panicroom_machine 0.0)
            (object_create_anew panicroom_open_biped)
            (object_create_anew panicroom_closed_biped)
            (sleep 30)
            (object_destroy panicroom_machine)))))

(script continuous void panicbal_shield_check
    (begin
    (if
        (= (device_get_position panicbal_control) 1.0)
        (begin (object_teleport panicbal_crusher panicbal_open_flag) (sleep 15))
        (begin (object_teleport panicbal_crusher panicbal_closed_flag) (sleep 15)))))

(script continuous void panicbal_shield_auto
    (begin
    (sleep_until (= (device_get_position panicbal_control) 1.0))
    (sleep 1800)
    (device_set_position panicbal_control 0.0)))

(script continuous void panicbal_shield_sync
    (begin
    (if
        (< (unit_get_health panicbal_open_biped) 0.1)
        (begin
            (object_create panicbal_machine)
            (object_set_scale panicbal_machine 1.1 1)
            (device_set_position panicbal_machine 1.0)
            (object_create_anew panicbal_closed_biped)
            (object_create_anew panicbal_open_biped)
            (sleep 15)))
    (if
        (< (unit_get_health panicbal_closed_biped) 0.1)
        (begin
            (device_set_position panicbal_machine 0.0)
            (object_create_anew panicbal_open_biped)
            (object_create_anew panicbal_closed_biped)
            (sleep 30)
            (object_destroy panicbal_machine)))))

(script continuous void panichall1_shield_check
    (begin
    (if
        (= (device_get_position panichall1_control) 1.0)
        (begin (object_teleport panichall1_crusher panichall1_open_flag) (sleep 15))
        (begin (object_teleport panichall1_crusher panichall1_closed_flag) (sleep 15)))))

(script continuous void panichall1_shield_auto
    (begin
    (sleep_until (= (device_get_position panichall1_control) 1.0))
    (sleep 1800)
    (device_set_position panichall1_control 0.0)))

(script continuous void panichall1_shield_sync
    (begin
    (if
        (< (unit_get_health panichall1_open_biped) 0.1)
        (begin
            (object_create panichall1_machine)
            (device_set_position panichall1_machine 1.0)
            (object_create_anew panichall1_closed_biped)
            (object_create_anew panichall1_open_biped)
            (sleep 15)))
    (if
        (< (unit_get_health panichall1_closed_biped) 0.1)
        (begin
            (device_set_position panichall1_machine 0.0)
            (object_create_anew panichall1_open_biped)
            (object_create_anew panichall1_closed_biped)
            (sleep 30)
            (object_destroy panichall1_machine)))))

(script continuous void panichall2_shield_check
    (begin
    (if
        (= (device_get_position panichall2_control) 1.0)
        (begin (object_teleport panichall2_crusher panichall2_open_flag) (sleep 15))
        (begin (object_teleport panichall2_crusher panichall2_closed_flag) (sleep 15)))))

(script continuous void panichall2_shield_auto
    (begin
    (sleep_until (= (device_get_position panichall2_control) 1.0))
    (sleep 1800)
    (device_set_position panichall2_control 0.0)))

(script continuous void panichall2_shield_sync
    (begin
    (if
        (< (unit_get_health panichall2_open_biped) 0.1)
        (begin
            (object_create panichall2_machine)
            (device_set_position panichall2_machine 1.0)
            (object_create_anew panichall2_closed_biped)
            (object_create_anew panichall2_open_biped)
            (sleep 15)))
    (if
        (< (unit_get_health panichall2_closed_biped) 0.1)
        (begin
            (device_set_position panichall2_machine 0.0)
            (object_create_anew panichall2_open_biped)
            (object_create_anew panichall2_closed_biped)
            (sleep 30)
            (object_destroy panichall2_machine)))))

(script continuous void panichill_shield_check
    (begin
    (if
        (= (device_get_position panichill_control) 1.0)
        (begin (object_teleport panichill_crusher panichill_open_flag) (sleep 15))
        (begin (object_teleport panichill_crusher panichill_closed_flag) (sleep 15)))))

(script continuous void panichill_shield_auto
    (begin
    (sleep_until (= (device_get_position panichill_control) 1.0))
    (sleep 1800)
    (device_set_position panichill_control 0.0)))

(script continuous void panichill_shield_sync
    (begin
    (if
        (< (unit_get_health panichill_open_biped) 0.1)
        (begin
            (object_create panichill_machine)
            (device_set_position panichill_machine 1.0)
            (object_create_anew panichill_closed_biped)
            (object_create_anew panichill_open_biped)
            (sleep 15)))
    (if
        (< (unit_get_health panichill_closed_biped) 0.1)
        (begin
            (device_set_position panichill_machine 0.0)
            (object_create_anew panichill_open_biped)
            (object_create_anew panichill_closed_biped)
            (sleep 30)
            (object_destroy panichill_machine)))))

(script continuous void gateflag1_check
    (begin
    (if
        (= (device_get_position gateflag1_control) 1.0)
        (begin (object_teleport gateflag1_crusher gateflag1_open_flag) (sleep 15))
        (begin (object_teleport gateflag1_crusher gateflag1_closed_flag) (sleep 15)))))

(script continuous void gateflag1_auto
    (begin
    (sleep_until (= (device_get_position gateflag1_control) 1.0))
    (sleep 1800)
    (device_set_position gateflag1_control 0.0)))

(script continuous void gateflag1_sync
    (begin
    (if
        (< (unit_get_health gateflag1_open_biped) 0.1)
        (begin
            (device_set_position gateflag1_machine 1.0)
            (object_create_anew gateflag1_closed_biped)
            (object_create_anew gateflag1_open_biped)
            (sleep 15)))
    (if
        (< (unit_get_health gateflag1_closed_biped) 0.1)
        (begin
            (device_set_position gateflag1_machine 0.0)
            (object_create_anew gateflag1_open_biped)
            (object_create_anew gateflag1_closed_biped)
            (sleep 15)))))

(script continuous void gateflag2_check
    (begin
    (if
        (= (device_get_position gateflag2_control) 1.0)
        (begin (object_teleport gateflag2_crusher gateflag2_open_flag) (sleep 15))
        (begin (object_teleport gateflag2_crusher gateflag2_closed_flag) (sleep 15)))))

(script continuous void gateflag2_auto
    (begin
    (sleep_until (= (device_get_position gateflag2_control) 1.0))
    (sleep 1800)
    (device_set_position gateflag2_control 0.0)))

(script continuous void gateflag2_sync
    (begin
    (if
        (< (unit_get_health gateflag2_open_biped) 0.1)
        (begin
            (device_set_position gateflag2_machine 1.0)
            (object_create_anew gateflag2_closed_biped)
            (object_create_anew gateflag2_open_biped)
            (sleep 15)))
    (if
        (< (unit_get_health gateflag2_closed_biped) 0.1)
        (begin
            (device_set_position gateflag2_machine 0.0)
            (object_create_anew gateflag2_open_biped)
            (object_create_anew gateflag2_closed_biped)
            (sleep 15)))))

(script continuous void gatemain_check
    (begin
    (if
        (= (device_get_position gatemain_control) 1.0)
        (begin (object_teleport gatemain_crusher gatemain_open_flag) (sleep 15))
        (begin (object_teleport gatemain_crusher gatemain_closed_flag) (sleep 15)))))

(script continuous void gatemain_auto
    (begin
    (sleep_until (= (device_get_position gatemain_control) 1.0))
    (sleep 1800)
    (device_set_position gatemain_control 0.0)))

(script continuous void gatemain_sync
    (begin
    (if
        (< (unit_get_health gatemain_open_biped) 0.1)
        (begin
            (device_set_position gatemain_machine 1.0)
            (object_create_anew gatemain_closed_biped)
            (object_create_anew gatemain_open_biped)
            (sleep 15)))
    (if
        (< (unit_get_health gatemain_closed_biped) 0.1)
        (begin
            (device_set_position gatemain_machine 0.0)
            (object_create_anew gatemain_open_biped)
            (object_create_anew gatemain_closed_biped)
            (sleep 15)))))

(script continuous void gateramp_check
    (begin
    (if
        (= (device_get_position gateramp_control) 1.0)
        (begin (object_teleport gateramp_crusher gateramp_open_flag) (sleep 15))
        (begin (object_teleport gateramp_crusher gateramp_closed_flag) (sleep 15)))))

(script continuous void gateramp_auto
    (begin
    (sleep_until (= (device_get_position gateramp_control) 1.0))
    (sleep 1800)
    (device_set_position gateramp_control 0.0)))

(script continuous void gateramp_sync
    (begin
    (if
        (< (unit_get_health gateramp_open_biped) 0.1)
        (begin
            (device_set_position gateramp_machine 1.0)
            (object_create_anew gateramp_closed_biped)
            (object_create_anew gateramp_open_biped)
            (sleep 15)))
    (if
        (< (unit_get_health gateramp_closed_biped) 0.1)
        (begin
            (device_set_position gateramp_machine 0.0)
            (object_create_anew gateramp_open_biped)
            (object_create_anew gateramp_closed_biped)
            (sleep 15)))))

(script continuous void gatepath_check
    (begin
    (if
        (= (device_get_position gatepath_control) 1.0)
        (begin (object_teleport gatepath_crusher gatepath_open_flag) (sleep 15))
        (begin (object_teleport gatepath_crusher gatepath_closed_flag) (sleep 15)))))

(script continuous void gatepath_auto
    (begin
    (sleep_until (= (device_get_position gatepath_control) 1.0))
    (sleep 1800)
    (device_set_position gatepath_control 0.0)))

(script continuous void gatepath_sync
    (begin
    (if
        (< (unit_get_health gatepath_open_biped) 0.1)
        (begin
            (device_set_position gatepath_machine 0.0)
            (object_create_anew gatepath_closed_biped)
            (object_create_anew gatepath_open_biped)
            (sleep 15)))
    (if
        (< (unit_get_health gatepath_closed_biped) 0.1)
        (begin
            (device_set_position gatepath_machine 1.0)
            (object_create_anew gatepath_open_biped)
            (object_create_anew gatepath_closed_biped)
            (sleep 15)))))

(script continuous void anti-cheat
    (begin
    (if
        (= (volume_test_object ghost_cheat_1 ghost_1) true)
        (begin
            (vehicle_unload ghost_1 "g-driver")
            (unit_set_enterable_by_player ghost_1 false)
            (sleep 90)
            (unit_set_enterable_by_player ghost_1 true)))
    (if
        (= (volume_test_object ghost_cheat_1 ghost_2) true)
        (begin
            (vehicle_unload ghost_2 "g-driver")
            (unit_set_enterable_by_player ghost_2 false)
            (sleep 90)
            (unit_set_enterable_by_player ghost_2 true)))))

(script continuous void randomize teleport
    (begin
    (begin
        (object_create_anew atvbase_biped)
        (object_create_anew beachbase_biped)
        (object_create_anew bluedanube_biped)
        (object_create_anew campingspot_biped)
        (object_create_anew centralroom_biped)
        (object_create_anew creditroom_biped)
        (object_create_anew garage_biped)
        (object_create_anew ghostbase_biped)
        (object_create_anew panicbalcony_biped)
        (object_create_anew paniccorridor_biped)
        (object_create_anew panichill_biped)
        (object_create_anew panicroom_biped)
        (object_create_anew sniperno1_biped)
        (object_create_anew sniperno2_biped)
        (object_create_anew thecrater_biped))
    (begin_random
        (begin (set destination_number 0) (object_teleport telehog atvbase_flag))
        (begin (set destination_number 0) (object_teleport telehog atvbase_flag))
        (begin (set destination_number 0) (object_teleport telehog atvbase_flag))
        (begin (set destination_number 1) (object_teleport telehog beachbase_flag))
        (begin (set destination_number 1) (object_teleport telehog beachbase_flag))
        (begin (set destination_number 1) (object_teleport telehog beachbase_flag))
        (begin (set destination_number 2) (object_teleport telehog bluedanube_flag))
        (begin (set destination_number 3) (object_teleport telehog campingspot_flag))
        (begin (set destination_number 3) (object_teleport telehog campingspot_flag))
        (begin (set destination_number 3) (object_teleport telehog campingspot_flag))
        (begin (set destination_number 4) (object_teleport telehog centralroom_flag))
        (begin (set destination_number 5) (object_teleport telehog creditroom_flag))
        (begin (set destination_number 5) (object_teleport telehog creditroom_flag))
        (begin (set destination_number 6) (object_teleport telehog garage_flag))
        (begin (set destination_number 6) (object_teleport telehog garage_flag))
        (begin (set destination_number 6) (object_teleport telehog garage_flag))
        (begin (set destination_number 7) (object_teleport telehog ghostbase_flag))
        (begin (set destination_number 7) (object_teleport telehog ghostbase_flag))
        (begin (set destination_number 8) (object_teleport telehog panicbalcony_flag))
        (begin (set destination_number 9) (object_teleport telehog paniccorridor_flag))
        (begin (set destination_number 10) (object_teleport telehog panichill_flag))
        (begin (set destination_number 10) (object_teleport telehog panichill_flag))
        (begin (set destination_number 10) (object_teleport telehog panichill_flag))
        (begin (set destination_number 10) (object_teleport telehog panichill_flag))
        (begin (set destination_number 11) (object_teleport telehog panicroom_flag))
        (begin (set destination_number 11) (object_teleport telehog panicroom_flag))
        (begin (set destination_number 11) (object_teleport telehog panicroom_flag))
        (begin (set destination_number 11) (object_teleport telehog panicroom_flag))
        (begin (set destination_number 12) (object_teleport telehog sniperno1_flag))
        (begin (set destination_number 13) (object_teleport telehog sniperno2_flag))
        (begin (set destination_number 14) (object_teleport telehog thecrater_flag))
        (begin (set destination_number 14) (object_teleport telehog thecrater_flag)))
    (sleep 900)))

(script continuous void sync telepips
    (begin
    (if
        (< (unit_get_health atvbase_biped) 0.1)
        (begin
            (object_set_permutation telepip_red "_unamed" "bluedanube")
            (object_set_permutation telepip_blue "_unamed" "bluedanube")))
    (if
        (< (unit_get_health beachbase_biped) 0.1)
        (begin
            (object_set_permutation telepip_red "_unamed" "beachbase")
            (object_set_permutation telepip_blue "_unamed" "beachbase")))
    (if
        (< (unit_get_health bluedanube_biped) 0.1)
        (begin
            (object_set_permutation telepip_red "_unamed" "atvbase")
            (object_set_permutation telepip_blue "_unamed" "atvbase")))
    (if
        (< (unit_get_health campingspot_biped) 0.1)
        (begin
            (object_set_permutation telepip_red "_unamed" "campingspot")
            (object_set_permutation telepip_blue "_unamed" "campingspot")))
    (if
        (< (unit_get_health centralroom_biped) 0.1)
        (begin
            (object_set_permutation telepip_red "_unamed" "centralroom")
            (object_set_permutation telepip_blue "_unamed" "centralroom")))
    (if
        (< (unit_get_health creditroom_biped) 0.1)
        (begin
            (object_set_permutation telepip_red "_unamed" "creditroom")
            (object_set_permutation telepip_blue "_unamed" "creditroom")))
    (if
        (< (unit_get_health garage_biped) 0.1)
        (begin
            (object_set_permutation telepip_red "_unamed" "garage")
            (object_set_permutation telepip_blue "_unamed" "garage")))
    (if
        (< (unit_get_health ghostbase_biped) 0.1)
        (begin
            (object_set_permutation telepip_red "_unamed" "ghostbase")
            (object_set_permutation telepip_blue "_unamed" "ghostbase")))
    (if
        (< (unit_get_health panicbalcony_biped) 0.1)
        (begin
            (object_set_permutation telepip_red "_unamed" "panicbalcony")
            (object_set_permutation telepip_blue "_unamed" "panicbalcony")))
    (if
        (< (unit_get_health paniccorridor_biped) 0.1)
        (begin
            (object_set_permutation telepip_red "_unamed" "paniccorridor")
            (object_set_permutation telepip_blue "_unamed" "paniccorridor")))
    (if
        (< (unit_get_health panichill_biped) 0.1)
        (begin
            (object_set_permutation telepip_red "_unamed" "panicroom")
            (object_set_permutation telepip_blue "_unamed" "panicroom")))
    (if
        (< (unit_get_health panicroom_biped) 0.1)
        (begin
            (object_set_permutation telepip_red "_unamed" "panichill")
            (object_set_permutation telepip_blue "_unamed" "panichill")))
    (if
        (< (unit_get_health sniperno1_biped) 0.1)
        (begin
            (object_set_permutation telepip_red "_unamed" "sniperno1")
            (object_set_permutation telepip_blue "_unamed" "sniperno1")))
    (if
        (< (unit_get_health sniperno2_biped) 0.1)
        (begin
            (object_set_permutation telepip_red "_unamed" "sniperno2")
            (object_set_permutation telepip_blue "_unamed" "sniperno2")))
    (if
        (< (unit_get_health thecrater_biped) 0.1)
        (begin
            (object_set_permutation telepip_red "_unamed" "thecrater")
            (object_set_permutation telepip_blue "_unamed" "thecrater")))))

(script continuous void teleport player
    (begin
    (if
        (= is_server true)
        (if
            (or
                (volume_test_object red_teleport_entrance (list_get (players) plyrnum))
                (volume_test_object blue_teleport_entrance (list_get (players) plyrnum)))
            (begin
                (if
                    (= destination_number 0)
                    (object_teleport (unit (list_get (players) plyrnum)) atvbase))
                (if
                    (= destination_number 1)
                    (object_teleport (unit (list_get (players) plyrnum)) beachbase))
                (if
                    (= destination_number 2)
                    (object_teleport (unit (list_get (players) plyrnum)) bluedanube))
                (if
                    (= destination_number 3)
                    (object_teleport (unit (list_get (players) plyrnum)) campingspot))
                (if
                    (= destination_number 4)
                    (object_teleport (unit (list_get (players) plyrnum)) centralroom))
                (if
                    (= destination_number 5)
                    (object_teleport (unit (list_get (players) plyrnum)) creditroom))
                (if
                    (= destination_number 6)
                    (object_teleport (unit (list_get (players) plyrnum)) garage))
                (if
                    (= destination_number 7)
                    (object_teleport (unit (list_get (players) plyrnum)) ghostbase))
                (if
                    (= destination_number 8)
                    (object_teleport (unit (list_get (players) plyrnum)) panicbalcony))
                (if
                    (= destination_number 9)
                    (object_teleport (unit (list_get (players) plyrnum)) paniccorridor))
                (if
                    (= destination_number 10)
                    (object_teleport (unit (list_get (players) plyrnum)) panichill))
                (if
                    (= destination_number 11)
                    (object_teleport (unit (list_get (players) plyrnum)) panicroom))
                (if
                    (= destination_number 12)
                    (object_teleport (unit (list_get (players) plyrnum)) sniperno1))
                (if
                    (= destination_number 13)
                    (object_teleport (unit (list_get (players) plyrnum)) sniperno2))
                (if
                    (= destination_number 14)
                    (object_teleport (unit (list_get (players) plyrnum)) thecrater)))))))

; calls: {"begin": 165, "if": 89, "object_teleport": 82, "object_create_anew": 82, "=": 66, "sleep": 65, "set": 45, "unit_get_health": 39, "<": 35, "device_set_position": 30, "object_set_permutation": 30, "volume_test_object": 24, "players": 23, "list_get": 22, "device_get_position": 20, "unit": 17, "sleep_until": 15, "object_create": 8, "object_destroy": 5, "object_set_scale": 4, "<=": 4, "unit_set_enterable_by_player": 4, "or": 3, "cinematic_show_letterbox": 2, "camera_control": 2, "and": 2, "rasterizer_decals_flush": 2, "render_lights": 2, "unit_kill": 2, "vehicle_unload": 2, "+": 1, ">": 1, "cinematic_set_title": 1, "camera_set": 1, "effect_new": 1, "list_count": 1, "object_destroy_containing": 1, "object_create_anew_containing": 1, "begin_random": 1}
