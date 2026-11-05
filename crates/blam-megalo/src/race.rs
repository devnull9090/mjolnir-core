//! Halo CE's Race and Rally, on foot or in any vehicle.
//!
//! The map places one marker per CE race track flag: an object labelled
//! `race_flag`, its spawn order the flag's rank (0, 1, ... with no gaps; CE's
//! indices have them, and tools/level/ce_objectives.py closes them), and its
//! multiplayer boundary the zone to touch. The label is one filter whatever
//! the map, as King's hills are.
//!
//! Race: every player has their own next rank, a player number that lives
//! through deaths. Touching that flag moves it on; past the last it goes back
//! to rank 0, and touching rank 0 then is a lap, a point. The first touch of
//! rank 0 is the start line and scores nothing. The score to win is in laps.
//!
//! Rally: one flag is live for everybody. Whoever touches it scores, and it
//! moves to a random other flag.
//!
//! Team games score per player too, and a team's score is its players' sum,
//! so the engine ends the round on the team's total. CE's Team Race can also
//! take the slowest or fastest player's laps; a sum is all the engine has.
//!
//! No waypoint reaches Unreal (docs/game_modes.md, B4), and each racer's next
//! flag differs, so the script tells the HUD by incident: see [`incident`].
//! The health packs have `lap_complete`, so these scripts never raise it.

use crate::objectives::{add, alive, call, end_at_score, number, score_point, score_snapshot};
use crate::script::{compare, constant, eq, obj, set, Builder, Item};
use crate::variant::{
    object, player, Action, Compare, ConditionKind, Number, Object, Op, Player, Subject,
    TriggerKind, Var, Variables, Variant, ATTR_NORMAL,
};

/// The label a race flag carries (a placement's `megalo label`).
pub const FLAG_LABEL: &str = "race_flag";

/// Incident indices (`globals\incident_properties` order).
pub mod incident {
    /// `checkpoint_reached`. In Race the cause is the player and the value
    /// their next rank, on each advance and each spawn. In Rally the cause
    /// is everybody and the value the live flag's rank, on each move and
    /// again on any spawn, which also tells a player who has just joined.
    pub const CHECKPOINT: u16 = 102;
    /// `final_lap`, used as the score snapshot: cause the player, value their
    /// score. The race incidents around `lap_complete` are the ones seen
    /// reaching Unreal (the CTF debug markers), so a score does not hang on
    /// `checkpoint_reached` arriving.
    pub const SCORE: u16 = 105;
}

/// Tell the HUD something each time a player spawns: `spawned` is a player
/// number, 1 while they live. `health` and `living` are scratch globals.
pub(crate) fn on_each_spawn(b: &mut Builder, health: u8, living: u8, spawned: u8, notice: Item) {
    let spawned = Var::Number(Number::PlayerNumber {
        player: player::CURRENT,
        index: spawned,
    });
    let mut is_alive = alive(player::CURRENT, health);
    is_alive.push(set(number(living), constant(1)));
    let is_alive = b.sub(TriggerKind::Do, is_alive);
    let came_back = b.sub(
        TriggerKind::Do,
        vec![
            eq(number(living), constant(1)),
            eq(spawned.clone(), constant(0)),
            set(spawned.clone(), constant(1)),
            notice,
        ],
    );
    let died = b.sub(
        TriggerKind::Do,
        vec![
            eq(number(living), constant(0)),
            set(spawned, constant(0)),
        ],
    );
    b.trigger(
        TriggerKind::EachPlayer,
        ATTR_NORMAL,
        vec![
            set(number(living), constant(0)),
            call(is_alive),
            call(came_back),
            call(died),
        ],
    );
}

/// The conditions that pass for a living player touching `flag`.
fn touching(flag: u8, health: u8) -> Vec<Item> {
    let mut items = alive(player::CURRENT, health);
    items.push(Item::If(ConditionKind::InBoundary {
        object: Object::PlayerBiped(player::CURRENT),
        shape: Object::Ref(flag),
    }));
    items
}

impl Variant {
    /// Race: the score to win is in laps.
    pub fn race(laps: u16) -> Self {
        Self::race_game(laps, false)
    }

    /// Team Race: the score to win is the team's total laps.
    pub fn team_race(laps: u16) -> Self {
        Self::race_game(laps, true)
    }

    /// Rally: the score to win is in flags touched.
    pub fn rally(flags: u16) -> Self {
        Self::rally_game(flags, false)
    }

    /// Team Rally: the score to win is the team's total flags.
    pub fn team_rally(flags: u16) -> Self {
        Self::rally_game(flags, true)
    }

    fn race_game(score: u16, teams: bool) -> Self {
        // Numbers: the flags counted, a scratch health and a scratch "alive".
        const FLAGS: u8 = 0;
        const HEALTH: u8 = 1;
        const LIVING: u8 = 2;
        // Player numbers: the next rank; 1 once past the last flag, so that
        // rank 0 is a lap and not the start line; and 1 while alive.
        const NEXT: u8 = 0;
        const LAPPING: u8 = 1;
        const SPAWNED: u8 = 2;
        let mut b = Builder::new(Variant {
            teams,
            vars: Variables {
                global_numbers: 3,
                global_objects: 1,
                player_numbers: 3,
                ..Variables::default()
            },
            ..Variant::empty(score)
        });
        let label = b.label(FLAG_LABEL);
        let flag = object::global(0);
        let mine = |index| {
            Var::Number(Number::PlayerNumber {
                player: player::CURRENT,
                index,
            })
        };
        let tell = || {
            Item::Do(Action::SendIncident {
                incident: incident::CHECKPOINT,
                cause: Subject::Player(Player(player::CURRENT)),
                effect: Subject::None,
                value: Some(Number::PlayerNumber {
                    player: player::CURRENT,
                    index: NEXT,
                }),
            })
        };

        let lap = b.sub(
            TriggerKind::Do,
            vec![
                eq(mine(LAPPING), constant(1)),
                set(mine(LAPPING), constant(0)),
                score_point(player::CURRENT),
                score_snapshot(incident::SCORE, player::CURRENT),
            ],
        );
        let wrap = b.sub(
            TriggerKind::Do,
            vec![
                compare(mine(NEXT), number(FLAGS), Compare::GreaterOrEqual),
                set(mine(NEXT), constant(0)),
                set(mine(LAPPING), constant(1)),
            ],
        );
        let mut touch = vec![eq(mine(NEXT), Var::Number(Number::SpawnSequence(flag)))];
        touch.extend(touching(flag, HEALTH));
        touch.extend([
            call(lap),
            Item::Do(Action::ModifyVariable {
                a: mine(NEXT),
                b: constant(1),
                op: Op::Add,
            }),
            call(wrap),
            tell(),
        ]);
        let touch = b.sub(TriggerKind::EachPlayer, touch);

        // The count is whole before anyone can reach the last flag, and a
        // walk of its own keeps a first-tick touch from wrapping on a count
        // still growing.
        let order = Var::Number(Number::SpawnSequence(object::CURRENT));
        b.trigger(
            TriggerKind::EachObjectWithLabel(label),
            ATTR_NORMAL,
            vec![
                compare(order.clone(), number(FLAGS), Compare::GreaterOrEqual),
                set(number(FLAGS), order),
                add(FLAGS, 1),
            ],
        );
        b.trigger(
            TriggerKind::EachObjectWithLabel(label),
            ATTR_NORMAL,
            vec![set(obj(flag), obj(object::CURRENT)), call(touch)],
        );
        on_each_spawn(&mut b, HEALTH, LIVING, SPAWNED, tell());
        if !teams {
            end_at_score(&mut b);
        }
        b.v
    }

    fn rally_game(score: u16, teams: bool) -> Self {
        const HEALTH: u8 = 0;
        const LIVING: u8 = 1;
        const SPAWNED: u8 = 0;
        let mut b = Builder::new(Variant {
            teams,
            vars: Variables {
                global_numbers: 2,
                global_objects: 2,
                player_numbers: 1,
                ..Variables::default()
            },
            ..Variant::empty(score)
        });
        let label = b.label(FLAG_LABEL);
        let live = object::global(0);
        let next = object::global(1);
        let none = obj(object::NONE);
        let tell = || {
            Item::Do(Action::SendIncident {
                incident: incident::CHECKPOINT,
                cause: Subject::None,
                effect: Subject::None,
                value: Some(Number::SpawnSequence(live)),
            })
        };

        // A flag to start, and after that any flag but the live one.
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![
                eq(obj(live), none.clone()),
                Item::Do(Action::GetRandomObject {
                    exclude: Object::Ref(object::NONE),
                    out: Object::Ref(live),
                    label,
                }),
                compare(obj(live), none.clone(), Compare::NotEqual),
                tell(),
            ],
        );
        let moved = b.sub(
            TriggerKind::Do,
            vec![
                Item::Do(Action::GetRandomObject {
                    exclude: Object::Ref(live),
                    out: Object::Ref(next),
                    label,
                }),
                compare(obj(next), none.clone(), Compare::NotEqual),
                set(obj(live), obj(next)),
                tell(),
            ],
        );
        let mut touch = vec![compare(obj(live), none.clone(), Compare::NotEqual)];
        touch.extend(touching(live, HEALTH));
        touch.extend([
            score_point(player::CURRENT),
            score_snapshot(incident::SCORE, player::CURRENT),
            call(moved),
        ]);
        b.trigger(TriggerKind::EachPlayer, ATTR_NORMAL, touch);

        // Nothing to tell before the first flag is picked.
        let resend = b.sub(
            TriggerKind::Do,
            vec![compare(obj(live), none, Compare::NotEqual), tell()],
        );
        on_each_spawn(&mut b, HEALTH, LIVING, SPAWNED, call(resend));
        if !teams {
            end_at_score(&mut b);
        }
        b.v
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::powerups::{self, HealthPacks};
    use crate::variant::tests::check_ranges;

    fn variants() -> Vec<(&'static str, Variant)> {
        vec![
            ("race", Variant::race(3)),
            ("team_race", Variant::team_race(6)),
            ("rally", Variant::rally(15)),
            ("team_rally", Variant::team_rally(15)),
        ]
    }

    fn raises(v: &Variant, incident: u16) -> Vec<&Action> {
        v.actions
            .iter()
            .filter(|a| matches!(a, Action::SendIncident { incident: i, .. } if *i == incident))
            .collect()
    }

    #[test]
    fn every_race_mode_reads_back_exactly_with_health_packs() {
        for (name, v) in variants() {
            let v = v
                .with_time_limit()
                .with_health_packs(HealthPacks {
                    object_type: 19,
                    respawn_ticks: 900,
                    reach_feet: 8,
                })
                .unwrap();
            check_ranges(&v);
            let bytes = v.write().unwrap();
            assert_eq!(Variant::read(&bytes).unwrap(), v, "{name}");
            Variant::validate(&bytes).unwrap();
            crate::raw::round_trip(&bytes, 0, &[]).unwrap();
        }
    }

    #[test]
    fn one_label_and_teams_only_in_team_modes() {
        for (name, v) in variants() {
            assert_eq!(v.teams, name.starts_with("team_"), "{name}");
            assert_eq!(v.filters.len(), 1, "{name}");
            assert_eq!(v.strings[v.filters[0].label as usize], FLAG_LABEL);
        }
    }

    /// Health packs own `lap_complete`.
    #[test]
    fn no_race_script_raises_lap_complete() {
        for (name, v) in variants() {
            assert!(
                raises(&v, powerups::incident::HEALTH_PACK_TAKEN).is_empty(),
                "{name}"
            );
        }
    }

    #[test]
    fn a_racer_hears_their_next_rank_on_each_advance_and_spawn() {
        let v = Variant::race(3);
        let tells = raises(&v, incident::CHECKPOINT);
        assert_eq!(tells.len(), 2);
        for a in tells {
            assert!(matches!(
                a,
                Action::SendIncident {
                    cause: Subject::Player(Player(player::CURRENT)),
                    value: Some(Number::PlayerNumber {
                        player: player::CURRENT,
                        index: 0,
                    }),
                    ..
                }
            ));
        }
    }

    #[test]
    fn rally_tells_everyone_the_live_rank() {
        let v = Variant::rally(15);
        for a in raises(&v, incident::CHECKPOINT) {
            assert!(matches!(
                a,
                Action::SendIncident {
                    cause: Subject::None,
                    value: Some(Number::SpawnSequence(_)),
                    ..
                }
            ));
        }
    }

    /// A lap is scored only from the lapping flag, so the start line is free.
    #[test]
    fn only_a_lap_or_a_flag_scores() {
        let scores = |v: &Variant| {
            v.actions
                .iter()
                .filter(|a| matches!(a, Action::ModifyScore { .. }))
                .count()
        };
        assert_eq!(scores(&Variant::race(3)), 1);
        assert_eq!(scores(&Variant::rally(15)), 1);
        assert_eq!(raises(&Variant::race(3), incident::SCORE).len(), 1);
    }
}
