//! Pelican Warfare's authoritative rules, executed by the native Megalo VM.
//!
//! Only the host runs normal triggers; declared variables and team scores
//! replicate through the existing simulation. Native transport reads the
//! public slots below. Lua does not run capture, scoring or match timers.
//! The three neutral `koth_hill` markers have spawn sequences 0, 1 and 2.
//! Their owner-team field is never changed (it would affect spawn selection).

use crate::objectives::{alive, call, number};
use crate::script::{compare, constant, eq, obj, set, Builder, Item};
use crate::variant::{
    object, player, Action, BaseOptions, Compare, ConditionKind, Number, Object, Op, Player,
    ScoreTarget, Team, Traits, TriggerKind, Var, Variables, Variant, ATTR_NORMAL,
};
use crate::Error;

pub const MAGIC: i16 = 20569;
pub const PHASE: u8 = 0;
pub const PHASE_TICKS: u8 = 1;
pub const MAGIC_SLOT: u8 = 2;
pub const ACTIVE_SECONDS: u8 = 3;
/// Slot3 carries the configured insertion duration in phases0/1; phase2
/// resets it and begins the existing combat-elapsed-seconds clock.
pub const DEPLOYMENT_SECONDS: u8 = ACTIVE_SECONDS;
pub const PLAYER_COUNT: u8 = 4;
pub const HEALTH: u8 = 5;
pub const SUBSECOND: u8 = 6;
pub const RED_SCORE: u8 = 7;
pub const BLUE_SCORE: u8 = 8;
pub const FIRST_OWNER: u8 = 9;
pub const HILL_LABEL: &str = "koth_hill";

#[derive(Debug, Clone, Copy)]
pub struct Warfare {
    pub score_to_win: u16,
    pub tick_rate: u16,
    pub minimum_players: u8,
    pub warmup_seconds: u16,
    pub insertion_seconds: u16,
    pub capture_seconds: u16,
    pub match_minutes: u8,
}

impl Default for Warfare {
    fn default() -> Self {
        Self {
            score_to_win: 500,
            tick_rate: 60,
            minimum_players: 2,
            warmup_seconds: 30,
            insertion_seconds: 60,
            capture_seconds: 8,
            match_minutes: 20,
        }
    }
}

fn modify(a: Var, amount: i16, op: Op) -> Item {
    Item::Do(Action::ModifyVariable {
        a,
        b: constant(amount),
        op,
    })
}

fn hill_number(index: u8) -> Var {
    Var::Number(Number::ObjectNumber {
        object: object::global(0),
        index,
    })
}

impl Variant {
    pub fn warfare(c: Warfare) -> Result<Self, Error> {
        if c.tick_rate == 0
            || c.tick_rate > 1000
            || !(1..=16).contains(&c.minimum_players)
            || c.capture_seconds == 0
            || c.insertion_seconds == 0
            || c.score_to_win == 0
            || c.score_to_win > 30000
            || c.match_minutes == 0
        {
            return Err(Error::Unsupported(
                "invalid warfare timing/player/score limits".into(),
            ));
        }
        let ticks = |seconds: u16| {
            i16::try_from(u32::from(seconds) * u32::from(c.tick_rate))
                .map_err(|_| Error::Unsupported("warfare phase exceeds 32767 ticks".into()))
        };
        let warmup = ticks(c.warmup_seconds)?;
        let insertion = ticks(c.insertion_seconds)?;
        let capture = ticks(c.capture_seconds)?;
        let mut b = Builder::new(Variant {
            teams: true,
            rounds: 31,
            base: BaseOptions {
                team_scoring: 3,
                respawn_seconds: 5,
                suicide_seconds: 0,
                betrayal_seconds: 0,
                ..BaseOptions::default()
            },
            vars: Variables {
                global_numbers: 12,
                global_number_priorities: [2, 2, 2, 2, 1, 0, 0, 2, 2, 2, 2, 2],
                global_objects: 2,
                object_numbers: 4,
                player_numbers: 1,
                ..Variables::default()
            },
            ..Variant::empty(c.score_to_win)
        });
        let label = b.label(HILL_LABEL);
        let mut safe = Traits::unchanged();
        safe.set("damage_resistance", 12)?;
        safe.set("cannot_die", 2)?;
        let safe = b.script_traits(
            "Deployment protection",
            "Protected before combat begins",
            safe,
        );

        // A normal guarded initializer also supports the existing loader's
        // variant installation at round reset without relying on an entry event.
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![
                compare(number(MAGIC_SLOT), constant(MAGIC), Compare::NotEqual),
                set(number(MAGIC_SLOT), constant(MAGIC)),
            ],
        );
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![
                compare(number(PHASE), constant(2), Compare::Less),
                set(number(DEPLOYMENT_SECONDS), constant(c.insertion_seconds as i16)),
            ],
        );
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![set(number(PLAYER_COUNT), constant(0))],
        );
        b.trigger(
            TriggerKind::EachPlayer,
            ATTR_NORMAL,
            vec![modify(number(PLAYER_COUNT), 1, Op::Add)],
        );
        b.trigger(
            TriggerKind::EachPlayer,
            ATTR_NORMAL,
            vec![
                compare(number(PHASE), constant(2), Compare::Less),
                Item::Do(Action::ApplyPlayerTraits {
                    player: Player(player::CURRENT),
                    traits: safe,
                }),
            ],
        );
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![
                eq(number(PHASE), constant(0)),
                compare(
                    number(PLAYER_COUNT),
                    constant(i16::from(c.minimum_players)),
                    Compare::Less,
                ),
                set(number(PHASE_TICKS), constant(0)),
            ],
        );
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![
                eq(number(PHASE), constant(0)),
                compare(
                    number(PLAYER_COUNT),
                    constant(i16::from(c.minimum_players)),
                    Compare::GreaterOrEqual,
                ),
                modify(number(PHASE_TICKS), 1, Op::Add),
                compare(
                    number(PHASE_TICKS),
                    constant(warmup),
                    Compare::GreaterOrEqual,
                ),
                set(number(PHASE), constant(1)),
                set(number(PHASE_TICKS), constant(0)),
            ],
        );
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![
                eq(number(PHASE), constant(1)),
                modify(number(PHASE_TICKS), 1, Op::Add),
                compare(
                    number(PHASE_TICKS),
                    constant(insertion),
                    Compare::GreaterOrEqual,
                ),
                set(number(PHASE), constant(2)),
                set(number(PHASE_TICKS), constant(0)),
                set(number(ACTIVE_SECONDS), constant(0)),
            ],
        );

        // A fixed bounded scan: at most three markers times sixteen players.
        // Occupants count once per team, so stacking players does not speed capture.
        let mut scan = alive(player::CURRENT, HEALTH);
        scan.extend([
            Item::Do(Action::GetPlayerVehicle {
                player: Player(player::CURRENT),
                out: Object::Ref(object::global(1)),
            }),
            eq(obj(object::global(1)), obj(object::NONE)),
        ]);
        scan.push(Item::If(ConditionKind::InBoundary {
            object: Object::PlayerBiped(player::CURRENT),
            shape: Object::Ref(object::global(0)),
        }));
        for side in 0..2 {
            let mark = b.sub(
                TriggerKind::Do,
                vec![
                    eq(
                        Var::Team(Team::PlayerOwner(player::CURRENT)),
                        Var::Team(Team::Ref(side)),
                    ),
                    set(hill_number(2 + side as u8), constant(1)),
                ],
            );
            scan.push(call(mark));
        }
        let scan = b.sub(TriggerKind::EachPlayer, scan);
        let mut update = vec![
            eq(number(PHASE), constant(2)),
            compare(
                Var::Number(Number::SpawnSequence(object::CURRENT)),
                constant(0),
                Compare::GreaterOrEqual,
            ),
            compare(
                Var::Number(Number::SpawnSequence(object::CURRENT)),
                constant(3),
                Compare::Less,
            ),
            set(obj(object::global(0)), obj(object::CURRENT)),
            set(hill_number(2), constant(0)),
            set(hill_number(3), constant(0)),
            call(scan),
        ];
        for side in 0..2u8 {
            let direction = if side == 0 { 1 } else { -1 };
            let advance = b.sub(
                TriggerKind::Do,
                vec![
                    eq(hill_number(2 + side), constant(1)),
                    eq(hill_number(3 - side), constant(0)),
                    compare(
                        hill_number(1),
                        constant(direction * capture),
                        if side == 0 {
                            Compare::Less
                        } else {
                            Compare::Greater
                        },
                    ),
                    modify(hill_number(1), direction, Op::Add),
                ],
            );
            let neutralize = b.sub(
                TriggerKind::Do,
                vec![
                    eq(hill_number(1), constant(0)),
                    set(hill_number(0), constant(0)),
                ],
            );
            let captured = b.sub(
                TriggerKind::Do,
                vec![
                    eq(hill_number(1), constant(direction * capture)),
                    set(hill_number(0), constant(i16::from(side + 1))),
                ],
            );
            // Owned empty sites keep scoring. An enemy in the zone blocks
            // payout immediately, including while ownership is being neutralized.
            let pay = b.sub(
                TriggerKind::Do,
                vec![
                    eq(number(SUBSECOND), constant(c.tick_rate as i16)),
                    eq(hill_number(0), constant(i16::from(side + 1))),
                    eq(hill_number(3 - side), constant(0)),
                    Item::Do(Action::ModifyScore {
                        target: ScoreTarget::Team(Team::Ref(side as i8)),
                        op: Op::Add,
                        value: Number::Constant(1),
                    }),
                ],
            );
            update.extend([call(advance), call(neutralize), call(captured), call(pay)]);
        }
        for site in 0..3u8 {
            let publish = b.sub(
                TriggerKind::Do,
                vec![
                    eq(
                        Var::Number(Number::SpawnSequence(object::CURRENT)),
                        constant(i16::from(site)),
                    ),
                    set(number(FIRST_OWNER + site), hill_number(0)),
                ],
            );
            update.push(call(publish));
        }
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![
                eq(number(PHASE), constant(2)),
                modify(number(SUBSECOND), 1, Op::Add),
            ],
        );
        b.trigger(TriggerKind::EachObjectWithLabel(label), ATTR_NORMAL, update);
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![
                eq(number(PHASE), constant(2)),
                compare(
                    number(SUBSECOND),
                    constant(c.tick_rate as i16),
                    Compare::GreaterOrEqual,
                ),
                set(number(SUBSECOND), constant(0)),
                modify(number(ACTIVE_SECONDS), 1, Op::Add),
            ],
        );
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![
                eq(number(PHASE), constant(2)),
                compare(number(PHASE_TICKS), constant(32760), Compare::Less),
                modify(number(PHASE_TICKS), 1, Op::Add),
            ],
        );
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![
                set(number(RED_SCORE), Var::Number(Number::TeamScore(0))),
                set(number(BLUE_SCORE), Var::Number(Number::TeamScore(1))),
            ],
        );
        for score in [RED_SCORE, BLUE_SCORE] {
            // TeamScore returns -1 for a side with no participant in CU4
            // (verified in PWR's solo preview). Publish zero to the native
            // presentation bridge without modifying the engine's team score.
            b.trigger(
                TriggerKind::Do,
                ATTR_NORMAL,
                vec![
                    compare(number(score), constant(0), Compare::Less),
                    set(number(score), constant(0)),
                ],
            );
            b.trigger(
                TriggerKind::Do,
                ATTR_NORMAL,
                vec![
                    eq(number(PHASE), constant(2)),
                    compare(
                        number(score),
                        Var::Number(Number::ScoreToWin),
                        Compare::GreaterOrEqual,
                    ),
                    set(number(PHASE), constant(3)),
                    set(number(PHASE_TICKS), constant(0)),
                    Item::Do(Action::EndRound),
                ],
            );
        }
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![
                eq(number(PHASE), constant(2)),
                compare(
                    number(ACTIVE_SECONDS),
                    constant(i16::from(c.match_minutes) * 60),
                    Compare::GreaterOrEqual,
                ),
                set(number(PHASE), constant(3)),
                set(number(PHASE_TICKS), constant(0)),
                Item::Do(Action::EndRound),
            ],
        );
        Ok(b.v)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn warfare_validates_and_roundtrips_with_script_only_team_scores() {
        let v = Variant::warfare(Warfare::default()).unwrap();
        let bytes = v.write().unwrap();
        Variant::validate(&bytes).unwrap();
        assert_eq!(Variant::read(&bytes).unwrap(), v);
        let raw = crate::raw::decode(&bytes).unwrap();
        assert_eq!(crate::raw::encode(&raw).unwrap(), bytes,
            "independent CU4 grammar agrees with team scoring and vehicle query encoding");
        crate::variant::tests::check_ranges(&v);
        assert!(v.teams);
        assert_eq!(v.vars.global_number_priorities, [2, 2, 2, 2, 1, 0, 0, 2, 2, 2, 2, 2]);
        assert_eq!(v.base.team_scoring, 3);
        assert_eq!((v.base.lives, v.base.team_lives), (0, 0));
        assert!(
            v.object_types.is_empty(),
            "no dependency on a new object-type table"
        );
        assert!(
            !v.conditions
                .iter()
                .any(|c| matches!(c.kind, ConditionKind::KillerTypeIs { .. })),
            "kills, suicides and betrayals must not score"
        );
    }

    #[test]
    fn invalid_timing_and_capacity_are_rejected() {
        for c in [
            Warfare {
                minimum_players: 17,
                ..Warfare::default()
            },
            Warfare {
                capture_seconds: 600,
                ..Warfare::default()
            },
            Warfare {
                score_to_win: 0,
                ..Warfare::default()
            },
        ] {
            assert!(Variant::warfare(c).is_err());
        }
    }
}
