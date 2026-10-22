//! Free-for-all timed objectives. All score and ownership changes run in the
//! replicated simulation; the Unreal loader only supplies presentation.
use crate::script::{compare, constant, eq, obj, set, Builder, Item};
use crate::variant::{
    object, player, Action, Compare, ConditionKind, Number, Object, Op, Player, PlayerSet,
    ScoreTarget, Subject, TriggerKind, Var, Variables, Variant, ATTR_NORMAL,
};

fn number(i: u8) -> Var {
    Var::Number(Number::GlobalNumber(i))
}
fn add(i: u8, delta: i16) -> Item {
    Item::Do(Action::ModifyVariable {
        a: number(i),
        b: constant(delta),
        op: Op::Add,
    })
}
fn end_at_score(b: &mut Builder) {
    b.trigger(
        TriggerKind::EachPlayer,
        ATTR_NORMAL,
        vec![
            compare(
                Var::Number(Number::PlayerScore(player::CURRENT)),
                Var::Number(Number::ScoreToWin),
                Compare::GreaterOrEqual,
            ),
            Item::Do(Action::EndRound),
        ],
    );
}

// The existing objective incidents carry an absolute score in CustomValue.
// Positive values are quiet score snapshots in the HUD/loader; zero retains
// the ordinary pickup/control announcement. Absolute values tolerate relays.
fn score_snapshot(incident: u16, who: u8) -> Item {
    Item::Do(Action::SendIncident {
        incident,
        cause: Subject::Player(Player(who)),
        effect: Subject::None,
        value: Some(Number::PlayerScore(who)),
    })
}

impl Variant {
    /// One neutral skull. Score once per second held; an abandoned/destroyed
    /// skull returns to the authored origin. The supplied type must be a
    /// carryable weapon with a skull presentation (the CE runtime's type 18).
    pub fn oddball(score: u16, ball_type: u16, tick_rate: i16, reset_ticks: i16) -> Self {
        let mut b = Builder::new(Variant {
            vars: Variables {
                global_numbers: 3,
                global_objects: 2,
                global_players: 1,
                ..Variables::default()
            },
            object_types: vec![ball_type],
            ..Variant::empty(score)
        });
        let origin = b.label("oddball_spawn");
        let ball_label = b.label("oddball_ball");
        let ball = object::global(0);
        let home = object::global(1);
        let carrier = player::global(0);
        let no_carrier = Var::Player(Player(player::NONE));
        let reset = b.sub(
            TriggerKind::Do,
            vec![
                compare(number(1), constant(reset_ticks), Compare::GreaterOrEqual),
                Item::Do(Action::DeleteObject(Object::Ref(ball))),
                set(obj(ball), obj(object::NONE)),
                set(number(0), constant(0)),
                set(number(1), constant(0)),
            ],
        );
        let score_tick = b.sub(
            TriggerKind::Do,
            vec![
                compare(number(0), constant(tick_rate), Compare::GreaterOrEqual),
                Item::Do(Action::ModifyScore {
                    target: ScoreTarget::Player(Player(carrier)),
                    op: Op::Add,
                    value: Number::Constant(1),
                }),
                score_snapshot(76, carrier), // game_incident: ball_taken
                set(number(0), constant(0)),
            ],
        );
        let held = b.sub(
            TriggerKind::Do,
            vec![
                compare(
                    Var::Player(Player(carrier)),
                    no_carrier.clone(),
                    Compare::NotEqual,
                ),
                Item::Do(Action::GetHealth {
                    object: Object::PlayerBiped(carrier),
                    out: Number::GlobalNumber(2),
                }),
                compare(number(2), constant(0), Compare::Greater),
                set(number(1), constant(0)),
                add(0, 1),
                Item::Do(Action::CallTrigger(score_tick)),
            ],
        );
        let loose = b.sub(
            TriggerKind::Do,
            vec![
                eq(Var::Player(Player(carrier)), no_carrier),
                set(number(0), constant(0)),
                add(1, 1),
                Item::Do(Action::CallTrigger(reset)),
            ],
        );
        b.trigger(
            TriggerKind::EachObjectWithLabel(origin),
            ATTR_NORMAL,
            vec![
                eq(obj(ball), obj(object::NONE)),
                set(obj(home), obj(object::CURRENT)),
                Item::Do(Action::CreateObject {
                    object_type: Some(ball_type),
                    out: Object::Ref(ball),
                    at: Object::Ref(home),
                    label: Some(ball_label),
                    flags: 1,
                    offset: [0, 0, 2],
                    name: None,
                }),
                Item::Do(Action::SetPickupPermissions {
                    object: Object::Ref(ball),
                    who: PlayerSet::Everyone,
                }),
                Item::Do(Action::SetWeaponPickupPriority {
                    object: Object::Ref(ball),
                    priority: 2,
                }),
                Item::Do(Action::SetWaypointVisibility {
                    object: Object::Ref(ball),
                    who: PlayerSet::Everyone,
                }),
                Item::Do(Action::SetWaypointIcon {
                    object: Object::Ref(ball),
                    icon: 8,
                }),
            ],
        );
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![
                compare(obj(ball), obj(object::NONE), Compare::NotEqual),
                Item::Do(Action::GetCarrier {
                    object: Object::Ref(ball),
                    out: Player(carrier),
                }),
                Item::Do(Action::CallTrigger(held)),
                Item::Do(Action::CallTrigger(loose)),
            ],
        );
        end_at_score(&mut b);
        b.v
    }

    /// Moving free-for-all hill. Exactly one living player in the current
    /// authored boundary scores; contested or empty hills award no points.
    pub fn koth(score: u16, tick_rate: i16, move_ticks: i16, hills: u8) -> Self {
        let mut b = Builder::new(Variant {
            vars: Variables {
                global_numbers: 5,
                global_objects: 1,
                global_players: 1,
                ..Variables::default()
            },
            ..Variant::empty(score)
        });
        let hill = object::global(0);
        let occupant = player::global(0);
        let scan = b.sub(
            TriggerKind::EachPlayer,
            vec![
                compare(
                    Var::Object(Object::PlayerBiped(player::CURRENT)),
                    obj(object::NONE),
                    Compare::NotEqual,
                ),
                Item::Do(Action::GetHealth {
                    object: Object::PlayerBiped(player::CURRENT),
                    out: Number::GlobalNumber(4),
                }),
                compare(number(4), constant(0), Compare::Greater),
                Item::If(ConditionKind::InBoundary {
                    object: Object::PlayerBiped(player::CURRENT),
                    shape: Object::Ref(hill),
                }),
                add(2, 1),
                set(
                    Var::Player(Player(occupant)),
                    Var::Player(Player(player::CURRENT)),
                ),
            ],
        );
        let score_tick = b.sub(
            TriggerKind::Do,
            vec![
                compare(number(3), constant(tick_rate), Compare::GreaterOrEqual),
                Item::Do(Action::ModifyScore {
                    target: ScoreTarget::Player(Player(occupant)),
                    op: Op::Add,
                    value: Number::Constant(1),
                }),
                score_snapshot(69, occupant), // game_incident: hill_controlled
                set(number(3), constant(0)),
            ],
        );
        let held = b.sub(
            TriggerKind::Do,
            vec![
                eq(number(2), constant(1)),
                add(3, 1),
                Item::Do(Action::CallTrigger(score_tick)),
            ],
        );
        let contested = b.sub(
            TriggerKind::Do,
            vec![
                compare(number(2), constant(1), Compare::NotEqual),
                set(number(3), constant(0)),
            ],
        );
        let wrap = b.sub(
            TriggerKind::Do,
            vec![
                compare(
                    number(0),
                    constant(i16::from(hills)),
                    Compare::GreaterOrEqual,
                ),
                set(number(0), constant(0)),
            ],
        );
        let rotate = b.sub(
            TriggerKind::Do,
            vec![
                compare(number(1), constant(move_ticks), Compare::GreaterOrEqual),
                add(0, 1),
                set(number(1), constant(0)),
                set(number(3), constant(0)),
                Item::Do(Action::CallTrigger(wrap)),
            ],
        );
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![add(1, 1), Item::Do(Action::CallTrigger(rotate))],
        );
        for i in 0..hills {
            let label = b.label(&format!("koth_hill_{i}"));
            b.trigger(
                TriggerKind::EachObjectWithLabel(label),
                ATTR_NORMAL,
                vec![
                    Item::Do(Action::SetWaypointVisibility {
                        object: Object::Ref(object::CURRENT),
                        who: PlayerSet::NoOne,
                    }),
                    eq(number(0), constant(i16::from(i))),
                    set(obj(hill), obj(object::CURRENT)),
                    set(number(2), constant(0)),
                    Item::Do(Action::SetWaypointVisibility {
                        object: Object::Ref(hill),
                        who: PlayerSet::Everyone,
                    }),
                    Item::Do(Action::SetWaypointIcon {
                        object: Object::Ref(hill),
                        icon: 7,
                    }),
                    Item::Do(Action::CallTrigger(scan)),
                    Item::Do(Action::CallTrigger(held)),
                    Item::Do(Action::CallTrigger(contested)),
                ],
            );
        }
        end_at_score(&mut b);
        b.v
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::powerups::HealthPacks;
    #[test]
    fn timed_objectives_roundtrip_with_shared_health_and_vehicle_filters() {
        for v in [
            Variant::oddball(120, 18, 30, 900),
            Variant::koth(120, 30, 1800, 3),
        ] {
            let v = v
                .with_time_limit()
                .with_health_packs(HealthPacks {
                    object_type: 19,
                    respawn_ticks: 900,
                    reach_feet: 8,
                })
                .unwrap();
            crate::variant::tests::check_ranges(&v);
            assert_eq!(Variant::read(&v.write().unwrap()).unwrap(), v);
            assert!(v.filters.len() < 16);
        }
    }
}
