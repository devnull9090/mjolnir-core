//! Capture the Flag, Halo CE rules, as a Megalo script.
//!
//! The map places a flag stand for each team: an object labelled
//! `ctf_flag_return`, owned by the team, whose multiplayer boundary is the
//! capture zone. The script creates each team's flag (a multiplayer object
//! type the map's object type list adds: one for red and one for blue, or
//! one for both) on its stand, labelled `ctf_flag`, and every tick:
//!
//! - a flag an enemy holds is away; carried into the carrier's own stand's
//!   boundary while the carrier's own flag is home, it scores for the
//!   carrier's team and goes back to its stand;
//! - a dropped flag goes back to its stand when its own team touches it, or
//!   after the reset time on the ground;
//! - a team at the score to win ends the round.
//!
//! The events raise the game's own incidents (`flag_grabbed`, `flag_scored`
//! ...), which reach Unreal's incident handler like any other.
//!
//! A trigger stops at its first failed condition (`0x423a70`), so each
//! branch is a subroutine of its own; and a label loop leaves its last
//! object as the current one, so the flag being handled is kept in a global.
//!
//! Why a type per team: the simulation's team colours (change colours from
//! the owner team) never reach Unreal, but an object's model variant does,
//! as the actor's `GetVariantName()`. The blue flag's tag defaults to the
//! assault bomb model's `blue` variant and the red flag's to `default`, so
//! MJOLNIRLevelLoader reads each flag's team from the actor itself
//! (docs/game_modes.md, 2.2). A variant set after creation would not reach
//! clients; a tag's default comes with the tag.

use crate::script::{compare, constant, eq, obj, set, Builder, Item};
use crate::variant::{
    object, player, team, Action, Compare, ConditionKind, Filter, Number, Object, Op, Player,
    PlayerSet, ScoreTarget, Subject, Team, TriggerKind, Var, Variables, Variant, ATTR_INIT,
    ATTR_NORMAL,
};

/// Incident indices (`globals\incident\game_incident`, first in
/// `globals\incident_properties`).
pub mod incident {
    pub const CTF_GAME_START: u16 = 108;
    pub const FLAG_GRABBED: u16 = 110;
    pub const FLAG_DROPPED: u16 = 112;
    pub const FLAG_SCORED: u16 = 116;
    pub const FLAG_RESET: u16 = 118;
    pub const FLAG_RECOVERED: u16 = 119;
}

/// The label a flag stand carries (a placement's `megalo label`).
pub const STAND_LABEL: &str = "ctf_flag_return";
/// The label the script gives the flags it creates.
pub const FLAG_LABEL: &str = "ctf_flag";

/// Waypoint icon: a flag.
const ICON_FLAG: u8 = 7;
/// Weapon pickup priority: walk over it.
const PICKUP_AUTOMATIC: u8 = 2;
/// Create-object flags: never garbage-collect the flag.
const NEVER_GARBAGE_COLLECT: u8 = 1;

// Filters.
const STANDS: u8 = 0;
const FLAGS: u8 = 1;
/// Spawn point labels (tools/level/gen_ce_level.py), in filter order after
/// the flags', and the team each gets: CE's red and blue starts, and the
/// starts CTF does not use parked on a team no player is on.
const SPAWN_LABELS: [(&str, i8); 3] = [
    ("ctf_spawn_red", 0),
    ("ctf_spawn_blue", 1),
    ("ctf_spawn_none", 2),
];

// Globals.
const NEW_FLAG: u8 = object::global(0);
const STAND: u8 = object::global(1);
const HOME_FLAG: u8 = object::global(2);
const FLAG: u8 = object::global(3);
const CARRIER: u8 = player::global(0);

// object.number[] on a flag.
const AWAY: u8 = 0;
const CARRIED: u8 = 1;
const COUNTDOWN: u8 = 2;
/// The flag's team as a number, 0 red or 1 blue: incidents carry it as
/// their value (Unreal's `CustomValue`), the only team an incident brings
/// to the announcer.
const TEAM_INDEX: u8 = 3;
// object.object[0]: a flag's stand, a stand's flag.
const LINK: u8 = 0;

#[derive(Debug, Clone, Copy)]
pub struct Ctf {
    /// The red flag's index in `multiplayer_object_type_list` (entry 18,
    /// tools/level/build_ctf_flag.sh); both teams' flag when there is no
    /// blue type.
    pub flag_type: u16,
    /// The blue flag's index (entry 20), made on the blue team's stand.
    /// `None` writes the script from before the blue flag tag, byte for
    /// byte: one type for both teams. The variant names every type it
    /// creates, and the simulation wipes the whole script when the
    /// installed list lacks one (`0x409c40` -> `0x40a310`), so a blue type
    /// needs a CE runtime pack with `pakchunk990-MJOLNIRFLAGB_P` and its
    /// object type list.
    pub blue_flag_type: Option<u16>,
    pub score_to_win: u16,
    /// Ticks a dropped flag lies before it resets.
    pub reset_ticks: i16,
    /// Raise marker incidents as the capture check passes each of its tests
    /// (`lap_complete`, `final_lap`, `final_lap_team`, `flag_dropped_neutral`),
    /// for the loader to log.
    pub debug: bool,
}

/// A marker incident when debugging, else nothing.
fn marker(debug: bool, incident: u16) -> Vec<Item> {
    if !debug {
        return Vec::new();
    }
    vec![Item::Do(Action::SendIncident {
        incident,
        cause: Subject::None,
        effect: Subject::None,
        value: None,
    })]
}

fn flag_number(index: u8) -> Var {
    Var::Number(Number::ObjectNumber {
        object: FLAG,
        index,
    })
}

fn flag_team_index() -> Number {
    Number::ObjectNumber {
        object: FLAG,
        index: TEAM_INDEX,
    }
}

fn link(of: u8) -> Var {
    Var::Object(Object::ObjectObject {
        object: of,
        index: LINK,
    })
}

/// Send `FLAG` back: unlink it from its stand (whose loop then makes a new
/// one) and delete it.
fn reset_flag(items: &mut Vec<Item>) {
    items.push(set(obj(STAND), link(FLAG)));
    items.push(set(link(STAND), obj(object::NONE)));
    items.push(Item::Do(Action::DeleteObject(Object::Ref(FLAG))));
}

impl Variant {
    pub fn ctf(c: Ctf) -> Variant {
        let mut b = Builder::new(Variant {
            teams: true,
            // Long enough for the first tick to give the spawn points
            // their teams (a first spawn at tick 0 used them neutral).
            initial_spawn_delay: 2,
            vars: Variables {
                global_players: 1,
                global_objects: 4,
                object_numbers: 4,
                object_objects: 1,
                ..Variables::default()
            },
            strings: [STAND_LABEL, FLAG_LABEL]
                .into_iter()
                .chain(SPAWN_LABELS.iter().map(|(l, _)| *l))
                .map(String::from)
                .collect(),
            filters: (0..2 + SPAWN_LABELS.len() as u8)
                .map(|label| Filter { label, team: None })
                .collect(),
            object_types: std::iter::once(c.flag_type)
                .chain(c.blue_flag_type)
                .collect(),
            ..Variant::empty(c.score_to_win)
        });
        let carrier = Var::Player(Player(CARRIER));
        let no_player = Var::Player(Player(player::NONE));
        let flag_team = Team::ObjectOwner(FLAG);

        // Each stand, as the current object: if the carrier's team owns it,
        // the carrier stands in it and its own flag is home, score.
        let mut score = marker(c.debug, 104);
        score.push(eq(
            Var::Team(Team::ObjectOwner(object::CURRENT)),
            Var::Team(Team::PlayerOwner(CARRIER)),
        ));
        score.extend(marker(c.debug, 105));
        score.push(Item::If(ConditionKind::InBoundary {
            object: Object::PlayerBiped(CARRIER),
            shape: Object::Ref(object::CURRENT),
        }));
        score.extend(marker(c.debug, 106));
        score.push(set(obj(HOME_FLAG), link(object::CURRENT)));
        score.push(eq(
            Var::Number(Number::ObjectNumber {
                object: HOME_FLAG,
                index: AWAY,
            }),
            constant(0),
        ));
        score.extend(marker(c.debug, 111));
        score.extend([
            Item::Do(Action::ModifyScore {
                target: ScoreTarget::Team(Team::PlayerOwner(CARRIER)),
                op: Op::Add,
                value: Number::Constant(1),
            }),
            Item::Do(Action::SendIncident {
                incident: incident::FLAG_SCORED,
                cause: Subject::Player(Player(CARRIER)),
                effect: Subject::Team(flag_team),
                value: Some(flag_team_index()),
            }),
        ]);
        reset_flag(&mut score);
        let score = b.sub(TriggerKind::EachObjectWithLabel(STANDS), score);

        // The flag has just been picked up.
        let grab = b.sub(
            TriggerKind::Do,
            vec![
                eq(flag_number(CARRIED), constant(0)),
                Item::Do(Action::SendIncident {
                    incident: incident::FLAG_GRABBED,
                    cause: Subject::Player(Player(CARRIER)),
                    effect: Subject::Team(flag_team),
                    value: Some(flag_team_index()),
                }),
                set(flag_number(CARRIED), constant(1)),
                set(flag_number(AWAY), constant(1)),
            ],
        );

        let carried = b.sub(
            TriggerKind::Do,
            vec![
                Item::If(ConditionKind::Compare {
                    a: carrier.clone(),
                    b: no_player.clone(),
                    op: Compare::NotEqual,
                }),
                Item::Do(Action::CallTrigger(grab)),
                set(flag_number(COUNTDOWN), constant(c.reset_ticks)),
                Item::Do(Action::CallTrigger(score)),
            ],
        );

        // The flag has just been dropped.
        let drop = b.sub(
            TriggerKind::Do,
            vec![
                eq(flag_number(CARRIED), constant(1)),
                Item::Do(Action::SendIncident {
                    incident: incident::FLAG_DROPPED,
                    cause: Subject::None,
                    effect: Subject::Team(flag_team),
                    value: Some(flag_team_index()),
                }),
                set(flag_number(CARRIED), constant(0)),
            ],
        );

        // Lying away from its stand too long.
        let mut timeout = vec![
            Item::If(ConditionKind::Compare {
                a: flag_number(COUNTDOWN),
                b: constant(0),
                op: Compare::LessOrEqual,
            }),
            Item::Do(Action::SendIncident {
                incident: incident::FLAG_RESET,
                cause: Subject::None,
                effect: Subject::Team(flag_team),
                value: Some(flag_team_index()),
            }),
        ];
        reset_flag(&mut timeout);
        let timeout = b.sub(TriggerKind::Do, timeout);

        // Touched by its own team. After a reset the flag is gone and its
        // team reads as none, which no player matches.
        let mut recover = vec![
            eq(
                Var::Team(Team::PlayerOwner(player::CURRENT)),
                Var::Team(flag_team),
            ),
            Item::If(ConditionKind::InBoundary {
                object: Object::PlayerBiped(player::CURRENT),
                shape: Object::Ref(FLAG),
            }),
            Item::Do(Action::SendIncident {
                incident: incident::FLAG_RECOVERED,
                cause: Subject::Player(Player(player::CURRENT)),
                effect: Subject::Team(flag_team),
                value: Some(flag_team_index()),
            }),
        ];
        reset_flag(&mut recover);
        let recover = b.sub(TriggerKind::EachPlayer, recover);

        let away = b.sub(
            TriggerKind::Do,
            vec![
                eq(flag_number(AWAY), constant(1)),
                Item::Do(Action::ModifyVariable {
                    a: flag_number(COUNTDOWN),
                    b: constant(1),
                    op: Op::Subtract,
                }),
                Item::Do(Action::CallTrigger(timeout)),
                Item::Do(Action::CallTrigger(recover)),
            ],
        );

        let loose = b.sub(
            TriggerKind::Do,
            vec![
                eq(carrier.clone(), no_player),
                Item::Do(Action::CallTrigger(drop)),
                Item::Do(Action::CallTrigger(away)),
            ],
        );

        // A new flag's team index: 0 unless blue.
        let team_index = b.sub(
            TriggerKind::Do,
            vec![
                eq(
                    Var::Team(Team::ObjectOwner(NEW_FLAG)),
                    Var::Team(Team::Ref(team::team(1))),
                ),
                set(
                    Var::Number(Number::ObjectNumber {
                        object: NEW_FLAG,
                        index: TEAM_INDEX,
                    }),
                    constant(1),
                ),
            ],
        );

        // The spawn points take their CTF teams (they are placed neutral, for
        // every other game type): at init, which runs before the round's
        // first spawn (a per-tick trigger came too late for it, 2026-10-01),
        // and every tick after.
        let spawn_teams: Vec<Item> = SPAWN_LABELS
            .iter()
            .enumerate()
            .map(|(i, (_, t))| {
                let label = b.sub(
                    TriggerKind::EachObjectWithLabel(2 + i as u8),
                    vec![set(
                        Var::Team(Team::ObjectOwner(object::CURRENT)),
                        Var::Team(Team::Ref(team::team(*t))),
                    )],
                );
                Item::Do(Action::CallTrigger(label))
            })
            .collect();
        let init = b.trigger(TriggerKind::Do, ATTR_INIT, spawn_teams.clone());
        b.v.entry_points.init = Some(init);
        b.trigger(TriggerKind::Do, ATTR_NORMAL, spawn_teams);

        // Every tick: a stand without a flag makes one. A flag made on the
        // current stand, `NEW_FLAG`, is linked to it both ways, takes its
        // owner team, can be picked up by the enemy only, shows everyone a
        // waypoint, and gets its team index.
        let create = |object_type: u16| {
            Item::Do(Action::CreateObject {
                object_type: Some(object_type),
                out: Object::Ref(NEW_FLAG),
                at: Object::Ref(object::CURRENT),
                label: Some(FLAGS),
                flags: NEVER_GARBAGE_COLLECT,
                offset: [0, 0, 2],
                name: None,
            })
        };
        let setup = vec![
            set(link(object::CURRENT), obj(NEW_FLAG)),
            set(link(NEW_FLAG), obj(object::CURRENT)),
            set(
                Var::Team(Team::ObjectOwner(NEW_FLAG)),
                Var::Team(Team::ObjectOwner(object::CURRENT)),
            ),
            Item::Do(Action::SetPickupPermissions {
                object: Object::Ref(NEW_FLAG),
                who: PlayerSet::Enemies,
            }),
            Item::Do(Action::SetWeaponPickupPriority {
                object: Object::Ref(NEW_FLAG),
                priority: PICKUP_AUTOMATIC,
            }),
            Item::Do(Action::SetWaypointVisibility {
                object: Object::Ref(NEW_FLAG),
                who: PlayerSet::Everyone,
            }),
            Item::Do(Action::SetWaypointIcon {
                object: Object::Ref(NEW_FLAG),
                icon: ICON_FLAG,
            }),
            Item::Do(Action::CallTrigger(team_index)),
        ];
        let mut stand = vec![eq(link(object::CURRENT), obj(object::NONE))];
        match c.blue_flag_type {
            None => {
                stand.push(create(c.flag_type));
                stand.extend(setup);
            }
            Some(blue_type) => {
                // The red type on a red stand, the blue type on a blue one,
                // each a subroutine of its own. A subroutine sees the
                // caller's current object, the stand: the call action saves
                // and restores it, and a plain trigger never sets it
                // (`0x399110` action 20, `0x39ed40`). NEW_FLAG is cleared
                // first, so a stand on any other team makes no flag and the
                // setup leaves the last stand's flag alone.
                let mut make = |team: i8, object_type: u16| {
                    b.sub(
                        TriggerKind::Do,
                        vec![
                            eq(
                                Var::Team(Team::ObjectOwner(object::CURRENT)),
                                Var::Team(Team::Ref(team::team(team))),
                            ),
                            create(object_type),
                        ],
                    )
                };
                let red = make(0, c.flag_type);
                let blue = make(1, blue_type);
                let mut made = vec![compare(obj(NEW_FLAG), obj(object::NONE), Compare::NotEqual)];
                made.extend(setup);
                let made = b.sub(TriggerKind::Do, made);
                stand.extend([
                    set(obj(NEW_FLAG), obj(object::NONE)),
                    Item::Do(Action::CallTrigger(red)),
                    Item::Do(Action::CallTrigger(blue)),
                    Item::Do(Action::CallTrigger(made)),
                ]);
            }
        }
        b.trigger(TriggerKind::EachObjectWithLabel(STANDS), ATTR_NORMAL, stand);

        // Every tick: each flag, carried or loose.
        b.trigger(
            TriggerKind::EachObjectWithLabel(FLAGS),
            ATTR_NORMAL,
            vec![
                set(obj(FLAG), obj(object::CURRENT)),
                Item::Do(Action::GetCarrier {
                    object: Object::Ref(FLAG),
                    out: Player(CARRIER),
                }),
                Item::Do(Action::CallTrigger(carried)),
                Item::Do(Action::CallTrigger(loose)),
            ],
        );

        // Every tick: a team at the score to win ends the round.
        b.trigger(
            TriggerKind::EachTeam,
            ATTR_NORMAL,
            vec![
                Item::If(ConditionKind::Compare {
                    a: Var::Number(Number::TeamScore(team::CURRENT)),
                    b: Var::Number(Number::ScoreToWin),
                    op: Compare::GreaterOrEqual,
                }),
                Item::Do(Action::EndRound),
            ],
        );

        b.v
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::variant::tests::check_ranges;
    use crate::variant::{Condition, ATTR_SUBROUTINE};

    /// As released: a 30 s reset at the simulation's 60 ticks a second.
    fn ctf(blue_flag_type: Option<u16>, debug: bool) -> Variant {
        Variant::ctf(Ctf {
            flag_type: 18,
            blue_flag_type,
            score_to_win: 3,
            reset_ticks: 1800,
            debug,
        })
    }

    fn conditions(v: &Variant, t: u16) -> &[Condition] {
        let t = &v.triggers[t as usize];
        &v.conditions[t.first_condition as usize..][..t.condition_count as usize]
    }

    fn actions(v: &Variant, t: u16) -> &[Action] {
        let t = &v.triggers[t as usize];
        &v.actions[t.first_action as usize..][..t.action_count as usize]
    }

    fn stand_trigger(v: &Variant) -> u16 {
        let stands = v
            .triggers
            .iter()
            .enumerate()
            .filter(|(_, t)| {
                t.kind == TriggerKind::EachObjectWithLabel(STANDS) && t.attribute == ATTR_NORMAL
            })
            .map(|(i, _)| i as u16)
            .collect::<Vec<_>>();
        assert_eq!(stands.len(), 1, "one per-tick trigger over the stands");
        stands[0]
    }

    #[test]
    fn ctf_reads_back_exactly() {
        for blue in [Some(20), None] {
            let v = ctf(blue, true);
            let bytes = v.write().unwrap();
            assert_eq!(Variant::read(&bytes).unwrap(), v);
            assert!(bytes.len() < 0x5000, "{} bytes", bytes.len());
        }
    }

    /// The single-type script (`blue_flag_type: None`, `megalo write
    /// --single-flag`) is the one released before the blue flag tag, byte
    /// for byte: the length and rolling hash of `Variant::ctf` alone, taken
    /// from the writer before the blue type was added (2026-10-21).
    #[test]
    fn the_single_type_script_is_unchanged() {
        let bytes = Variant::ctf(Ctf {
            flag_type: 18,
            blue_flag_type: None,
            score_to_win: 3,
            reset_ticks: 900,
            debug: false,
        })
        .write()
        .unwrap();
        let sum = bytes
            .iter()
            .fold(0u32, |h, &b| h.wrapping_mul(31).wrapping_add(b as u32));
        assert_eq!((bytes.len(), sum), (1700, 0xcdee_fd5d));
    }

    /// The two-type stand logic as `megalo dump` lists it: the object
    /// types 18 and 20; one create of each, alone in a subroutine gated on
    /// the stand's owner team; the stand trigger clears `NEW_FLAG` and calls
    /// red, blue and the setup; and the setup is the single-type script's,
    /// action for action, gated on a flag having been made.
    #[test]
    fn each_team_makes_its_own_flag_type() {
        let v = ctf(Some(20), false);
        assert_eq!(v.object_types, vec![18, 20]);

        let creates: Vec<(u16, u16)> = v
            .triggers
            .iter()
            .enumerate()
            .flat_map(|(t, _)| {
                actions(&v, t as u16).iter().filter_map(move |a| match a {
                    Action::CreateObject {
                        object_type: Some(ty),
                        ..
                    } => Some((t as u16, *ty)),
                    _ => None,
                })
            })
            .collect();
        assert_eq!(
            creates.iter().map(|c| c.1).collect::<Vec<_>>(),
            vec![18, 20],
            "a create of each flag type and nothing else"
        );
        for (&(t, ty), team) in creates.iter().zip([0i8, 1]) {
            let trigger = &v.triggers[t as usize];
            assert_eq!(trigger.kind, TriggerKind::Do);
            assert_eq!(trigger.attribute, ATTR_SUBROUTINE);
            let conds = conditions(&v, t);
            assert_eq!(conds.len(), 1, "type {ty}: one condition");
            assert_eq!(
                conds[0].kind,
                ConditionKind::Compare {
                    a: Var::Team(Team::ObjectOwner(object::CURRENT)),
                    b: Var::Team(Team::Ref(team::team(team))),
                    op: Compare::Equal,
                }
            );
            assert!(!conds[0].negate);
            assert_eq!(
                actions(&v, t),
                &[Action::CreateObject {
                    object_type: Some(ty),
                    out: Object::Ref(NEW_FLAG),
                    at: Object::Ref(object::CURRENT),
                    label: Some(FLAGS),
                    flags: NEVER_GARBAGE_COLLECT,
                    offset: [0, 0, 2],
                    name: None,
                }]
            );
        }

        let stand = stand_trigger(&v);
        let conds = conditions(&v, stand);
        assert_eq!(conds.len(), 1, "the stand trigger asks only for no flag");
        let acts = actions(&v, stand);
        let calls: Vec<u16> = acts[1..]
            .iter()
            .map(|a| match a {
                Action::CallTrigger(t) => *t,
                other => panic!("the stand trigger does {other:?}"),
            })
            .collect();
        assert_eq!(
            acts[0],
            Action::ModifyVariable {
                a: obj(NEW_FLAG),
                b: obj(object::NONE),
                op: Op::Set,
            }
        );
        assert_eq!(&calls[..2], &[creates[0].0, creates[1].0]);
        assert_eq!(calls.len(), 3);
        let made = calls[2];
        assert_eq!(v.triggers[made as usize].kind, TriggerKind::Do);
        assert_eq!(
            conditions(&v, made)
                .iter()
                .map(|c| (c.kind.clone(), c.action_offset))
                .collect::<Vec<_>>(),
            vec![(
                ConditionKind::Compare {
                    a: obj(NEW_FLAG),
                    b: obj(object::NONE),
                    op: Compare::NotEqual,
                },
                0
            )]
        );

        let single = ctf(None, false);
        assert_eq!(single.object_types, vec![18]);
        let single_acts = actions(&single, stand_trigger(&single));
        assert!(matches!(
            single_acts[0],
            Action::CreateObject {
                object_type: Some(18),
                ..
            }
        ));
        assert_eq!(actions(&v, made), &single_acts[1..]);
    }

    #[test]
    fn ctf_triggers_cover_their_conditions_and_actions() {
        for blue in [Some(20), None] {
            let v = ctf(blue, true);
            check_ranges(&v);
            for a in &v.actions {
                if let Action::CallTrigger(t) = a {
                    assert_eq!(v.triggers[*t as usize].attribute, ATTR_SUBROUTINE);
                }
            }
        }
    }
}
