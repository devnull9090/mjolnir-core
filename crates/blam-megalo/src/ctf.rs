//! Capture the Flag, Halo CE rules, as a Megalo script.
//!
//! The map places a flag stand for each team: an object labelled
//! `ctf_flag_return`, owned by the team, whose multiplayer boundary is the
//! capture zone. The script creates each team's flag (a multiplayer object
//! type the map's object type list adds) on its stand, labelled `ctf_flag`,
//! and every tick:
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

use crate::script::{constant, eq, obj, set, Builder, Item};
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
    /// The flag's index in `multiplayer_object_type_list`.
    pub flag_type: u16,
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
                .map(|label| Filter { label })
                .collect(),
            object_types: vec![c.flag_type],
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
        let blue = b.sub(
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

        // Every tick: a stand without a flag makes one.
        b.trigger(
            TriggerKind::EachObjectWithLabel(STANDS),
            ATTR_NORMAL,
            vec![
                eq(link(object::CURRENT), obj(object::NONE)),
                Item::Do(Action::CreateObject {
                    object_type: Some(c.flag_type),
                    out: Object::Ref(NEW_FLAG),
                    at: Object::Ref(object::CURRENT),
                    label: Some(FLAGS),
                    flags: NEVER_GARBAGE_COLLECT,
                    offset: [0, 0, 2],
                    name: None,
                }),
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
                Item::Do(Action::CallTrigger(blue)),
            ],
        );

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
    use crate::variant::ATTR_SUBROUTINE;

    fn ctf() -> Variant {
        Variant::ctf(Ctf {
            flag_type: 18,
            score_to_win: 3,
            reset_ticks: 900,
            debug: true,
        })
    }

    #[test]
    fn ctf_reads_back_exactly() {
        let v = ctf();
        let bytes = v.write().unwrap();
        assert_eq!(Variant::read(&bytes).unwrap(), v);
        assert!(bytes.len() < 0x5000, "{} bytes", bytes.len());
    }

    #[test]
    fn ctf_triggers_cover_their_conditions_and_actions() {
        let v = ctf();
        check_ranges(&v);
        for a in &v.actions {
            if let Action::CallTrigger(t) = a {
                assert_eq!(v.triggers[*t as usize].attribute, ATTR_SUBROUTINE);
            }
        }
    }
}
