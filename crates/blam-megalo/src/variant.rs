//! A Megalo game variant as the simulation's decoder reads it
//! (HaloSimulation CU4 `0x392a40`; the full grammar is in
//! docs/re/megalo_variant_format.md).
//!
//! Only what a scripted mode needs is modelled: the score to win, teams, the
//! rules' script (conditions, actions, triggers), variables, the string
//! table and object filters (labels), the object types the script creates,
//! and the entry points. Everything else is written as a fixed default and
//! read back as it is, so [`Variant::write`] always emits a complete,
//! well-formed stream and [`Variant::read`] checks that it is one.
//!
//! Operands, conditions and actions follow the decoder's own numbering,
//! which is Halo Reach's (ReachVariantTool's opcode list matches it type for
//! type); each is noted with the CU4 function that reads or runs it.

use crate::bits::{BitReader, BitWriter};
use crate::Error;

/// Encoding versions the decoder accepts. `0x6b` adds a trailing block of
/// MCC-era tuning values this crate does not model, so it writes `0x6a`.
pub const VERSION: u32 = 0x6a;

/// A player reference (`u5`, HaloSimulation `0x441380`).
pub mod player {
    /// No player.
    pub const NONE: u8 = 0;
    /// `global.player[i]`, i in 0..8.
    pub const fn global(i: u8) -> u8 {
        17 + i
    }
    /// The player the current trigger iterates over.
    pub const CURRENT: u8 = 25;
    /// The killer of the object-death event being handled.
    pub const KILLER: u8 = 28;
}

/// An object reference (`u5`, HaloSimulation `0x441530`).
pub mod object {
    /// No object.
    pub const NONE: u8 = 0;
    /// `global.object[i]`, i in 0..16.
    pub const fn global(i: u8) -> u8 {
        1 + i
    }
    /// The object the current trigger iterates over (a label loop's).
    pub const CURRENT: u8 = 17;
}

/// A team reference (`u5`, stored minus one; HaloSimulation `0x441610`).
/// These are the stored values.
pub mod team {
    /// No team.
    pub const NONE: i8 = -1;
    /// Team `i` (0 red, 1 blue, ... 7).
    pub const fn team(i: i8) -> i8 {
        i
    }
    pub const NEUTRAL: i8 = 8;
    /// `global.team[i]`, i in 0..8.
    pub const fn global(i: i8) -> i8 {
        9 + i
    }
    /// The team the current trigger iterates over.
    pub const CURRENT: i8 = 17;
}

/// A number operand (`u6` kind, then its payload; `0x421a00`, evaluated by
/// `0x420580`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Number {
    /// Kind 0.
    Constant(i16),
    /// Kind 2: `object.number[index]`.
    ObjectNumber { object: u8, index: u8 },
    /// Kind 4: `global.number[index]`.
    GlobalNumber(u8),
    /// Kind 7: a team's score (stored team reference, see [`team`]).
    TeamScore(i8),
    /// Kind 8: a player's score.
    PlayerScore(u8),
    /// Kind 16: the variant's score to win.
    ScoreToWin,
}

/// A player operand (`u2` kind 0: a player reference; `0x41fab0`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Player(pub u8);

/// An object operand (`u3` kind; `0x422640`, evaluated by `0x421c90`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Object {
    /// Kind 0: an object reference (see [`object`]).
    Ref(u8),
    /// Kind 1: `player.object[index]`.
    PlayerObject { player: u8, index: u8 },
    /// Kind 2: `object.object[index]`.
    ObjectObject { object: u8, index: u8 },
    /// Kind 4: the player's biped.
    PlayerBiped(u8),
}

/// A team operand (`u3` kind; `0x420480`, evaluated by `0x41fb90`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Team {
    /// Kind 0: a team reference (stored value, see [`team`]).
    Ref(i8),
    /// Kind 4: the player's team.
    PlayerOwner(u8),
    /// Kind 5: the object's owner team.
    ObjectOwner(u8),
}

/// A variable operand (`u3` kind; `0x4227d0`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Var {
    Number(Number),
    Player(Player),
    Object(Object),
    Team(Team),
}

/// Comparison operators (condition 1). For players, objects and teams only
/// `Equal` means equal; anything else means not equal.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum Compare {
    Less = 0,
    Greater = 1,
    Equal = 2,
    LessOrEqual = 3,
    GreaterOrEqual = 4,
    NotEqual = 5,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConditionKind {
    /// Type 1.
    Compare { a: Var, b: Var, op: Compare },
    /// Type 2: `object` (a biped's bounds, or the object's position) is
    /// inside `shape`'s multiplayer boundary.
    InBoundary { object: Object, shape: Object },
    /// Type 3: bit `1 << death type` of this tick's death record for the
    /// player.
    KillerTypeIs { player: Player, flags: u8 },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Condition {
    pub kind: ConditionKind,
    pub negate: bool,
    /// Consecutive conditions with the same value are OR-ed; a new value
    /// starts an AND.
    pub or_sequence: u16,
    /// The condition gates the trigger's actions from this index on. A
    /// condition that fails stops the trigger (`0x423a70`).
    pub action_offset: u16,
}

/// Arithmetic operators (`0x408730`). Players, objects and teams take
/// `Set` only.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum Op {
    Add = 0,
    Subtract = 1,
    Set = 4,
}

/// Who an object's waypoint or pickup permission applies to (`u3`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum PlayerSet {
    NoOne = 0,
    Everyone = 1,
    Allies = 2,
    Enemies = 3,
    Default = 5,
}

/// The cause or effect of an incident (`u2` kind, then the operand).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Subject {
    /// Kind 0.
    Team(Team),
    /// Kind 1.
    Player(Player),
    /// Kind 2: none.
    None,
}

/// Whose score an action changes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ScoreTarget {
    Team(Team),
    Player(Player),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Action {
    /// Type 1.
    ModifyScore {
        target: ScoreTarget,
        op: Op,
        value: Number,
    },
    /// Type 2 (`0x41c3b0`): create an object of a multiplayer object type
    /// (an index into `multiplayer_object_type_list`) at `at`, offset by
    /// `offset` tenths of a world unit, with filter `label`. Flags: 1 never
    /// garbage-collect, 2 suppress the spawn effect, 4 keep `at`'s full
    /// orientation (otherwise only its yaw).
    CreateObject {
        object_type: Option<u16>,
        out: Object,
        at: Object,
        label: Option<u8>,
        flags: u8,
        offset: [i8; 3],
        name: Option<u8>,
    },
    /// Type 3.
    DeleteObject(Object),
    /// Type 4.
    SetWaypointVisibility { object: Object, who: PlayerSet },
    /// Type 5: an icon index (7 flag, 6 bomb, 8 skull; 11 territory is not
    /// modelled).
    SetWaypointIcon { object: Object, icon: u8 },
    /// Type 9: `a op= b`.
    ModifyVariable { a: Var, b: Var, op: Op },
    /// Type 12: who may pick the object up.
    SetPickupPermissions { object: Object, who: PlayerSet },
    /// Type 19: the player holding the weapon, or none.
    GetCarrier { object: Object, out: Player },
    /// Type 20: run a trigger (a subroutine).
    CallTrigger(u16),
    /// Type 21.
    EndRound,
    /// Type 29: the killer of `victim` this tick, into `out`.
    GetKiller { victim: Player, out: Player },
    /// Type 44: 0 normal, 1 high (hold to pick up), 2 automatic.
    SetWeaponPickupPriority { object: Object, priority: u8 },
    /// Type 54: the object's shields as a percentage (full = 100), into `out`
    /// (a writable number: a global or object number).
    GetShields { object: Object, out: Number },
    /// Type 55: the object's health as a percentage (full = 100).
    GetHealth { object: Object, out: Number },
    /// Type 64: `shields op= value`, a percentage (100 = full; more is an
    /// overcharge).
    ModifyShields {
        object: Object,
        op: Op,
        value: Number,
    },
    /// Type 65: `health op= value`, a percentage (100 = full).
    ModifyHealth {
        object: Object,
        op: Op,
        value: Number,
    },
    /// Type 66: the distance between two objects, in feet (a world unit is
    /// ten).
    GetDistance { a: Object, b: Object, out: Number },
    /// Type 75 (`0x41df50`): raise an incident, an index into the incident
    /// definitions in `globals\incident_properties` order (game_incident's
    /// first: `flag_grabbed` is 110). With a value it is type 76, and the
    /// value reaches Unreal as the incident's `CustomValue`.
    SendIncident {
        incident: u16,
        cause: Subject,
        effect: Subject,
        value: Option<Number>,
    },
}

/// Trigger kinds (`u3`).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TriggerKind {
    Do,
    EachPlayer,
    EachTeam,
    /// Each object an object filter (label) matches; the filter index.
    EachObjectWithLabel(u8),
}

/// Trigger attributes: the host's per-tick loop runs `NORMAL` ones;
/// `SUBROUTINE` ones run only when an action calls them.
pub const ATTR_NORMAL: u8 = 0;
pub const ATTR_SUBROUTINE: u8 = 1;
/// An entry point's trigger (the variant's `init`), which the per-tick loop
/// leaves alone.
pub const ATTR_INIT: u8 = 2;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Trigger {
    pub kind: TriggerKind,
    pub attribute: u8,
    pub first_condition: u16,
    pub condition_count: u16,
    pub first_action: u16,
    pub action_count: u16,
}

/// Entry points, in the order the stream carries them.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct EntryPoints {
    pub init: Option<u16>,
    pub local_init: Option<u16>,
    pub host_migration: Option<u16>,
    pub double_host_migration: Option<u16>,
    pub object_death: Option<u16>,
    pub local: Option<u16>,
    pub pregame: Option<u16>,
}

/// Variables the script declares; numbers start at 0, the rest at none.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct Variables {
    /// `global.number[]` (0..=12).
    pub global_numbers: u8,
    /// `global.player[]` (0..=8).
    pub global_players: u8,
    /// `global.object[]` (0..=16).
    pub global_objects: u8,
    /// `object.number[]` on every object with multiplayer properties (0..=8).
    pub object_numbers: u8,
    /// `object.object[]` (0..=4).
    pub object_objects: u8,
}

/// An object filter: the objects whose multiplayer label (a placement's
/// `megalo label`, or a created object's) is a string of the variant's
/// table.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Filter {
    /// Index into [`Variant::strings`].
    pub label: u8,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Variant {
    pub score_to_win: u16,
    /// Teams on: teams 0 (red) and 1 (blue) are enabled.
    pub teams: bool,
    /// Seconds before a round's first spawn (the respawn options' loadout
    /// camera time, 0..=15). The script's first tick runs before it ends, so
    /// spawn points the script sets up are ready for it.
    pub initial_spawn_delay: u8,
    /// Rounds in a game (1..=31, the misc options' u5 at `o+0x2bb`). The
    /// game ends after the last; an earlier `EndRound` resets the round.
    pub rounds: u8,
    pub conditions: Vec<Condition>,
    pub actions: Vec<Action>,
    pub triggers: Vec<Trigger>,
    pub vars: Variables,
    pub entry_points: EntryPoints,
    /// The main string table (labels).
    pub strings: Vec<String>,
    pub filters: Vec<Filter>,
    /// Multiplayer object types the script creates: each must be an entry
    /// of `multiplayer_object_type_list` with a tag, or the simulation wipes
    /// the script (`0x409c40`).
    pub object_types: Vec<u16>,
}

impl Variant {
    /// A variant with no rules: players spawn and nothing scores.
    pub fn empty(score_to_win: u16) -> Variant {
        Variant {
            score_to_win,
            teams: false,
            initial_spawn_delay: 0,
            rounds: 1,
            conditions: Vec::new(),
            actions: Vec::new(),
            triggers: Vec::new(),
            vars: Variables::default(),
            entry_points: EntryPoints::default(),
            strings: Vec::new(),
            filters: Vec::new(),
            object_types: Vec::new(),
        }
    }

    /// Free-for-all Slayer: a kill scores 1 for the killer, and the round
    /// ends when a player reaches the score to win.
    ///
    /// Every tick, for each player: if the player died this tick by another
    /// player's hand (death type "kill"), look the killer up into
    /// `global.player[0]` and, unless that is the player themselves, add one
    /// to the killer's score. Then, for each player, end the round if their
    /// score has reached the score to win.
    pub fn slayer(score_to_win: u16) -> Variant {
        let current = Player(player::CURRENT);
        let killer = Player(player::global(0));
        Variant {
            conditions: vec![
                // Trigger 0: the current player died a kill death this tick...
                Condition {
                    kind: ConditionKind::KillerTypeIs {
                        player: current,
                        flags: DEATH_KILL,
                    },
                    negate: false,
                    or_sequence: 0,
                    action_offset: 0,
                },
                // ...and whoever killed them was someone else.
                Condition {
                    kind: ConditionKind::Compare {
                        a: Var::Player(killer),
                        b: Var::Player(current),
                        op: Compare::NotEqual,
                    },
                    negate: false,
                    or_sequence: 1,
                    action_offset: 1,
                },
                // Trigger 1: the current player has reached the score to win.
                Condition {
                    kind: ConditionKind::Compare {
                        a: Var::Number(Number::PlayerScore(player::CURRENT)),
                        b: Var::Number(Number::ScoreToWin),
                        op: Compare::GreaterOrEqual,
                    },
                    negate: false,
                    or_sequence: 0,
                    action_offset: 0,
                },
            ],
            actions: vec![
                Action::GetKiller {
                    victim: current,
                    out: killer,
                },
                Action::ModifyScore {
                    target: ScoreTarget::Player(killer),
                    op: Op::Add,
                    value: Number::Constant(1),
                },
                Action::EndRound,
            ],
            triggers: vec![
                Trigger {
                    kind: TriggerKind::EachPlayer,
                    attribute: ATTR_NORMAL,
                    first_condition: 0,
                    condition_count: 2,
                    first_action: 0,
                    action_count: 2,
                },
                Trigger {
                    kind: TriggerKind::EachPlayer,
                    attribute: ATTR_NORMAL,
                    first_condition: 2,
                    condition_count: 1,
                    first_action: 2,
                    action_count: 1,
                },
            ],
            vars: Variables {
                global_players: 1,
                ..Variables::default()
            },
            ..Variant::empty(score_to_win)
        }
    }

    /// A smoke test for the interpreter: every tick, every player scores one,
    /// and the round ends at the score to win. Nothing about it needs a
    /// second player, so a lone player's score climbing proves the script
    /// runs.
    pub fn tick(score_to_win: u16) -> Variant {
        let mut v = Variant::slayer(score_to_win);
        // Keep Slayer's end-of-round trigger (condition 2, action 2); replace
        // the kill trigger with an unconditional score for the current player.
        v.conditions = vec![v.conditions.remove(2)];
        v.actions = vec![
            Action::ModifyScore {
                target: ScoreTarget::Player(Player(player::CURRENT)),
                op: Op::Add,
                value: Number::Constant(1),
            },
            Action::EndRound,
        ];
        v.triggers = vec![
            Trigger {
                kind: TriggerKind::EachPlayer,
                attribute: ATTR_NORMAL,
                first_condition: 0,
                condition_count: 0,
                first_action: 0,
                action_count: 1,
            },
            Trigger {
                kind: TriggerKind::EachPlayer,
                attribute: ATTR_NORMAL,
                first_condition: 0,
                condition_count: 1,
                first_action: 1,
                action_count: 1,
            },
        ];
        v.vars.global_players = 0;
        v
    }
}

/// Death-type bit for a kill by another player (Reach's numbering, which the
/// decoder's condition 3 tests against the death record; guardians 0,
/// suicide 1, kill 2, betrayal 3, quit 4). Inferred, not yet seen live.
pub const DEATH_KILL: u8 = 1 << 2;

// ----------------------------------------------------------------- writing

fn put(w: &mut BitWriter, v: u64, bits: u32) -> Result<(), Error> {
    w.write(v, bits)
}

fn zeros(w: &mut BitWriter, fields: &[u32]) -> Result<(), Error> {
    for &b in fields {
        put(w, 0, b)?;
    }
    Ok(())
}

/// A stored value written plus one (`v-1` fields: 0 encodes -1).
fn put_minus_one(w: &mut BitWriter, v: i64, bits: u32) -> Result<(), Error> {
    if v < -1 {
        return Err(Error::TooWide { value: v, bits });
    }
    put(w, (v + 1) as u64, bits)
}

/// An optional value: a bit set for absent, else the value.
fn put_opt(w: &mut BitWriter, v: Option<u64>, bits: u32) -> Result<(), Error> {
    match v {
        None => {
            w.bool(true);
            Ok(())
        }
        Some(v) => {
            w.bool(false);
            put(w, v, bits)
        }
    }
}

/// The five trait groups, all "unchanged".
const TRAIT_FIELDS: [&[u32]; 5] = [
    &[4, 3, 4, 3, 4, 4, 2, 3, 2, 2],
    &[4, 4, 8, 8, 4, 2, 2, 2, 2, 2, 2, 8],
    &[5, 4, 4, 2],
    &[3, 2, 2, 3, 4],
    &[3, 3, 2],
];

fn write_traits(w: &mut BitWriter) -> Result<(), Error> {
    zeros(w, TRAIT_FIELDS[0])?;
    zeros(w, TRAIT_FIELDS[1])?;
    zeros(w, TRAIT_FIELDS[2])?;
    w.bool(false); // no u9 movement value
    zeros(w, TRAIT_FIELDS[3])?;
    zeros(w, TRAIT_FIELDS[4])
}

/// A string table: every string present in all twelve languages at the
/// same offset, the data uncompressed UTF-8, each string NUL-terminated.
fn write_strings(
    w: &mut BitWriter,
    strings: &[String],
    cw: u32,
    ow: u32,
    sw: u32,
) -> Result<(), Error> {
    put(w, strings.len() as u64, cw)?;
    let mut data = Vec::new();
    for s in strings {
        let offset = data.len() as u64;
        for _ in 0..12 {
            w.bool(true);
            put(w, offset, ow)?;
        }
        data.extend_from_slice(s.as_bytes());
        data.push(0);
    }
    if !strings.is_empty() {
        put(w, data.len() as u64, sw)?;
        w.bool(false); // not compressed
        for b in data {
            put(w, b as u64, 8)?;
        }
    }
    Ok(())
}

/// The content header (`0x38f5d0`): a game variant, activity 3, game mode 3,
/// the Megalo engine, no map, `title` as its name.
fn write_content_header(w: &mut BitWriter, title: &str) -> Result<(), Error> {
    put(w, 6 + 1, 4)?; // content type, v-1: game variant
    put(w, 0, 32)?;
    for _ in 0..4 {
        put(w, 0, 64)?;
    }
    put(w, 3 + 1, 3)?; // activity, v-1
    put(w, 3, 3)?; // game mode
    put(w, 2, 3)?; // engine: Megalo
    put(w, 0xffff_ffff, 32)?; // map id: none
    put(w, 0xff, 8)?; // engine category
    for _ in 0..2 {
        // author: two u64, an empty NUL-terminated name, a bit
        put(w, 0, 64)?;
        put(w, 0, 64)?;
        put(w, 0, 8)?;
        put(w, 0, 1)?;
    }
    for c in title.encode_utf16().take(127) {
        put(w, c as u64, 16)?;
    }
    put(w, 0, 16)?; // title NUL
    put(w, 0, 16)?; // empty description
    put(w, 0, 8)?; // stored content type 6: one byte
    Ok(())
}

/// The base variant's map options (`o+0x2fc`), Reach's order: grenades on
/// map (bit 0), shortcuts (1), armor abilities (2), powerups (3), turrets
/// (4), indestructible vehicles (5). The map variant's object creation
/// (`0x5ee0d0`) refuses a multiplayer object of type grenade, equipment,
/// powerup or turret whose bit is clear, so at 0 no placed grenade,
/// overshield or camouflage appeared. With these bits Danger Canyon had all
/// 23 of its placed grenades, overshield and camouflage in play (2026-10-01).
const MAP_FLAGS: u8 = 0b01_1111;

fn write_base(
    w: &mut BitWriter,
    teams: bool,
    initial_spawn_delay: u8,
    rounds: u8,
) -> Result<(), Error> {
    write_content_header(w, "MJOLNIR")?;
    w.bool(false);
    // misc: teams on/off and 3 flags, no time limit, the rounds, u4, no
    // sudden death, no grace
    w.bool(teams);
    zeros(w, &[1, 1, 1])?;
    put(w, 0, 8)?;
    put(w, rounds as u64, 5)?;
    put(w, 0, 4)?;
    put(w, 0, 7)?;
    put(w, 0, 5)?;
    // respawn: 4 flags, unlimited lives, 5 s respawn and penalties
    zeros(w, &[1, 1, 1, 1])?;
    put(w, 0, 6)?;
    put(w, 0, 7)?;
    put(w, 5, 8)?;
    put(w, 5, 8)?;
    put(w, 5, 8)?;
    put(w, 0, 4)?; // respawn growth
    put(w, initial_spawn_delay as u64, 4)?; // loadout camera time
    put(w, 0, 6)?;
    write_traits(w)?;
    w.bool(false);
    // social
    put(w, 0, 2)?;
    zeros(w, &[1, 1, 1, 1, 1])?;
    // map: what the map variant may place, base traits, weapon and vehicle
    // sets -2 ("as placed"), powerups
    put(w, MAP_FLAGS as u64, 6)?;
    write_traits(w)?;
    put(w, 0xfe, 8)?;
    put(w, 0xfe, 8)?;
    for _ in 0..3 {
        write_traits(w)?;
    }
    zeros(w, &[7, 7, 7])?;
    // teams: with teams on, red and blue are enabled (flag bit 0)
    put(w, 0, 3)?;
    put(w, 0, 3)?;
    put(w, 0, 2)?;
    for t in 0..8u64 {
        put(w, u64::from(teams && t < 2), 4)?;
        write_strings(w, &[], 1, 5, 6)?;
        put(w, t + 1, 4)?; // initial designator, v-1
        put(w, 0, 1)?;
        zeros(w, &[32, 32, 32])?;
        put(w, 1, 5)?;
    }
    // loadouts: none named, all zero
    put(w, 0, 2)?;
    for _ in 0..30 {
        put(w, 0, 1)?;
        w.bool(true); // no name
        zeros(w, &[8, 8, 8, 4])?;
    }
    Ok(())
}

fn write_player(w: &mut BitWriter, p: Player) -> Result<(), Error> {
    put(w, 0, 2)?;
    put(w, p.0 as u64, 5)
}

fn write_object(w: &mut BitWriter, o: Object) -> Result<(), Error> {
    match o {
        Object::Ref(r) => {
            put(w, 0, 3)?;
            put(w, r as u64, 5)
        }
        Object::PlayerObject { player, index } => {
            put(w, 1, 3)?;
            put(w, player as u64, 5)?;
            put(w, index as u64, 2)
        }
        Object::ObjectObject { object, index } => {
            put(w, 2, 3)?;
            put(w, object as u64, 5)?;
            put(w, index as u64, 2)
        }
        Object::PlayerBiped(p) => {
            put(w, 4, 3)?;
            put(w, p as u64, 5)
        }
    }
}

fn write_team(w: &mut BitWriter, t: Team) -> Result<(), Error> {
    match t {
        Team::Ref(r) => {
            put(w, 0, 3)?;
            put_minus_one(w, r as i64, 5)
        }
        Team::PlayerOwner(p) => {
            put(w, 4, 3)?;
            put(w, p as u64, 5)
        }
        Team::ObjectOwner(o) => {
            put(w, 5, 3)?;
            put(w, o as u64, 5)
        }
    }
}

fn write_number(w: &mut BitWriter, n: &Number) -> Result<(), Error> {
    match n {
        Number::Constant(c) => {
            put(w, 0, 6)?;
            w.write_signed(*c as i64, 16)
        }
        Number::ObjectNumber { object, index } => {
            put(w, 2, 6)?;
            put(w, *object as u64, 5)?;
            put(w, *index as u64, 3)
        }
        Number::GlobalNumber(i) => {
            put(w, 4, 6)?;
            put(w, *i as u64, 4)
        }
        Number::TeamScore(t) => {
            put(w, 7, 6)?;
            put_minus_one(w, *t as i64, 5)
        }
        Number::PlayerScore(p) => {
            put(w, 8, 6)?;
            put(w, *p as u64, 5)
        }
        Number::ScoreToWin => put(w, 16, 6),
    }
}

fn write_var(w: &mut BitWriter, v: &Var) -> Result<(), Error> {
    match v {
        Var::Number(n) => {
            put(w, 0, 3)?;
            write_number(w, n)
        }
        Var::Player(p) => {
            put(w, 1, 3)?;
            write_player(w, *p)
        }
        Var::Object(o) => {
            put(w, 2, 3)?;
            write_object(w, *o)
        }
        Var::Team(t) => {
            put(w, 3, 3)?;
            write_team(w, *t)
        }
    }
}

fn write_player_set(w: &mut BitWriter, who: PlayerSet) -> Result<(), Error> {
    put(w, who as u64, 3)
}

fn write_subject(w: &mut BitWriter, s: Subject) -> Result<(), Error> {
    match s {
        Subject::Team(t) => {
            put(w, 0, 2)?;
            write_team(w, t)
        }
        Subject::Player(p) => {
            put(w, 1, 2)?;
            write_player(w, p)
        }
        Subject::None => put(w, 2, 2),
    }
}

fn write_condition(w: &mut BitWriter, c: &Condition) -> Result<(), Error> {
    let ty = match c.kind {
        ConditionKind::Compare { .. } => 1,
        ConditionKind::InBoundary { .. } => 2,
        ConditionKind::KillerTypeIs { .. } => 3,
    };
    put(w, ty, 5)?;
    w.bool(c.negate);
    put(w, c.or_sequence as u64, 9)?;
    put(w, c.action_offset as u64, 10)?;
    match &c.kind {
        ConditionKind::Compare { a, b, op } => {
            write_var(w, a)?;
            write_var(w, b)?;
            put(w, *op as u64, 3)
        }
        ConditionKind::InBoundary { object, shape } => {
            write_object(w, *object)?;
            write_object(w, *shape)
        }
        ConditionKind::KillerTypeIs { player, flags } => {
            write_player(w, *player)?;
            put(w, *flags as u64, 5)
        }
    }
}

fn write_action(w: &mut BitWriter, a: &Action) -> Result<(), Error> {
    match a {
        Action::ModifyScore { target, op, value } => {
            put(w, 1, 7)?;
            match target {
                ScoreTarget::Player(p) => {
                    put(w, 1, 2)?;
                    write_player(w, *p)?;
                }
                ScoreTarget::Team(t) => {
                    put(w, 0, 2)?;
                    write_team(w, *t)?;
                }
            }
            put(w, *op as u64, 4)?;
            write_number(w, value)
        }
        Action::CreateObject {
            object_type,
            out,
            at,
            label,
            flags,
            offset,
            name,
        } => {
            put(w, 2, 7)?;
            put_opt(w, object_type.map(u64::from), 11)?;
            write_object(w, *out)?;
            write_object(w, *at)?;
            put_opt(w, label.map(u64::from), 4)?;
            put(w, *flags as u64, 3)?;
            for c in offset {
                put(w, *c as u8 as u64, 8)?;
            }
            put_minus_one(w, name.map_or(-1, i64::from), 8)
        }
        Action::DeleteObject(o) => {
            put(w, 3, 7)?;
            write_object(w, *o)
        }
        Action::SetWaypointVisibility { object, who } => {
            put(w, 4, 7)?;
            write_object(w, *object)?;
            write_player_set(w, *who)
        }
        Action::SetWaypointIcon { object, icon } => {
            if *icon == 11 {
                return Err(Error::Unsupported("territory waypoint icon".into()));
            }
            put(w, 5, 7)?;
            write_object(w, *object)?;
            put_minus_one(w, *icon as i64, 5)
        }
        Action::ModifyVariable { a, b, op } => {
            put(w, 9, 7)?;
            write_var(w, a)?;
            write_var(w, b)?;
            put(w, *op as u64, 4)
        }
        Action::SetPickupPermissions { object, who } => {
            put(w, 12, 7)?;
            write_object(w, *object)?;
            write_player_set(w, *who)
        }
        Action::GetCarrier { object, out } => {
            put(w, 19, 7)?;
            write_object(w, *object)?;
            write_player(w, *out)
        }
        Action::CallTrigger(t) => {
            put(w, 20, 7)?;
            put(w, *t as u64, 9)
        }
        Action::EndRound => put(w, 21, 7),
        Action::GetKiller { victim, out } => {
            put(w, 29, 7)?;
            write_player(w, *victim)?;
            write_player(w, *out)
        }
        Action::SetWeaponPickupPriority { object, priority } => {
            put(w, 44, 7)?;
            write_object(w, *object)?;
            put(w, *priority as u64, 2)
        }
        Action::GetShields { object, out } | Action::GetHealth { object, out } => {
            put(
                w,
                if matches!(a, Action::GetShields { .. }) {
                    54
                } else {
                    55
                },
                7,
            )?;
            write_object(w, *object)?;
            write_number(w, out)
        }
        Action::ModifyShields { object, op, value }
        | Action::ModifyHealth { object, op, value } => {
            put(
                w,
                if matches!(a, Action::ModifyShields { .. }) {
                    64
                } else {
                    65
                },
                7,
            )?;
            write_object(w, *object)?;
            put(w, *op as u64, 4)?;
            write_number(w, value)
        }
        Action::GetDistance {
            a: from,
            b: to,
            out,
        } => {
            put(w, 66, 7)?;
            write_object(w, *from)?;
            write_object(w, *to)?;
            write_number(w, out)
        }
        Action::SendIncident {
            incident,
            cause,
            effect,
            value,
        } => {
            put(w, if value.is_some() { 76 } else { 75 }, 7)?;
            put_minus_one(w, *incident as i64, 10)?;
            write_subject(w, *cause)?;
            write_subject(w, *effect)?;
            match value {
                Some(n) => write_number(w, n),
                None => Ok(()),
            }
        }
    }
}

fn write_trigger(w: &mut BitWriter, t: &Trigger) -> Result<(), Error> {
    let (kind, label) = match t.kind {
        TriggerKind::Do => (0, None),
        TriggerKind::EachPlayer => (1, None),
        TriggerKind::EachTeam => (3, None),
        TriggerKind::EachObjectWithLabel(l) => (5, Some(l)),
    };
    put(w, kind, 3)?;
    put(w, t.attribute as u64, 3)?;
    if kind == 5 {
        put_opt(w, label.map(u64::from), 4)?;
    }
    put(w, t.first_condition as u64, 9)?;
    put(w, t.condition_count as u64, 10)?;
    put(w, t.first_action as u64, 10)?;
    put(w, t.action_count as u64, 11)
}

/// `count` declarations of a number variable (default 0, priority 0).
fn write_numbers(w: &mut BitWriter, count: u8, bits: u32) -> Result<(), Error> {
    put(w, count as u64, bits)?;
    for _ in 0..count {
        write_number(w, &Number::Constant(0))?;
        put(w, 0, 2)?;
    }
    Ok(())
}

/// `count` declarations of a player or object variable (priority 0).
fn write_handles(w: &mut BitWriter, count: u8, bits: u32) -> Result<(), Error> {
    put(w, count as u64, bits)?;
    for _ in 0..count {
        put(w, 0, 2)?;
    }
    Ok(())
}

impl Variant {
    /// The variant as the simulation's decoder reads it, zero-padded to a
    /// whole byte.
    pub fn write(&self) -> Result<Vec<u8>, Error> {
        let v = &self.vars;
        for (value, max, bits) in [
            (v.global_numbers, 12, 4),
            (v.global_players, 8, 4),
            (v.global_objects, 16, 5),
            (v.object_numbers, 8, 4),
            (v.object_objects, 4, 3),
        ] {
            if value > max {
                return Err(Error::TooWide {
                    value: value as i64,
                    bits,
                });
            }
        }
        if !(1..=31).contains(&self.rounds) {
            return Err(Error::TooWide {
                value: self.rounds as i64,
                bits: 5,
            });
        }
        let mut w = BitWriter::new();
        put(&mut w, VERSION as u64, 32)?;
        put(&mut w, 0, 32)?;
        write_base(&mut w, self.teams, self.initial_spawn_delay, self.rounds)?;
        put(&mut w, 0, 5)?; // player traits
        put(&mut w, 0, 5)?; // user options
        write_strings(&mut w, &self.strings, 7, 15, 15)?; // main string table
        put(&mut w, 0, 7)?; // base name: none
        write_strings(&mut w, &[], 1, 9, 9)?; // name
        write_strings(&mut w, &[], 1, 12, 12)?; // description
        write_strings(&mut w, &[], 1, 9, 9)?; // category
        put(&mut w, 0, 5)?; // icon: none
        put(&mut w, 0, 5)?; // category: none
        put(&mut w, 0, 6)?; // map permissions
        w.bool(false);
        for _ in 0..15 {
            put(&mut w, 0, 32)?;
        }
        put(&mut w, 0, 1)?;
        put(&mut w, self.score_to_win as u64, 16)?;
        w.bool(false);
        w.bool(false);
        for _ in 0..80 {
            put(&mut w, 0, 32)?; // engine option toggles
        }
        put(&mut w, 0, 32)?; // megalo option toggles
        put(&mut w, 0, 32)?;

        put(&mut w, self.conditions.len() as u64, 10)?;
        for c in &self.conditions {
            write_condition(&mut w, c)?;
        }
        put(&mut w, self.actions.len() as u64, 11)?;
        for a in &self.actions {
            write_action(&mut w, a)?;
        }
        put(&mut w, self.triggers.len() as u64, 9)?;
        for t in &self.triggers {
            write_trigger(&mut w, t)?;
        }

        put(&mut w, 0, 3)?; // statistics
                            // global scope: numbers, timers, teams, players, objects
        write_numbers(&mut w, v.global_numbers, 4)?;
        zeros(&mut w, &[4, 4])?;
        write_handles(&mut w, v.global_players, 4)?;
        write_handles(&mut w, v.global_objects, 5)?;
        zeros(&mut w, &[4, 3, 3, 3, 3])?; // player scope
                                          // object scope
        write_numbers(&mut w, v.object_numbers, 4)?;
        zeros(&mut w, &[3, 2, 3])?;
        write_handles(&mut w, v.object_objects, 3)?;
        zeros(&mut w, &[4, 3, 3, 3, 3])?; // team scope
        put(&mut w, 0, 3)?; // HUD widgets
        let e = &self.entry_points;
        for p in [
            e.init,
            e.local_init,
            e.host_migration,
            e.double_host_migration,
            e.object_death,
            e.local,
            e.pregame,
        ] {
            put(&mut w, p.map_or(0, |i| i as u64 + 1), 9)?;
        }
        let mut words = [0u32; 64];
        for &t in &self.object_types {
            if t >= 2048 {
                return Err(Error::TooWide {
                    value: t as i64,
                    bits: 11,
                });
            }
            words[t as usize / 32] |= 1 << (t % 32);
        }
        for word in words {
            put(&mut w, word as u64, 32)?;
        }
        put(&mut w, self.filters.len() as u64, 5)?;
        for f in &self.filters {
            put_minus_one(&mut w, f.label as i64, 7)?;
            put(&mut w, 0, 3)?; // no type, team or number constraint
            put(&mut w, 0, 7)?; // minimum count
        }
        Ok(w.finish())
    }
}

// ----------------------------------------------------------------- reading

fn get(r: &mut BitReader, bits: u32) -> Result<u64, Error> {
    r.read(bits)
}

fn get_minus_one(r: &mut BitReader, bits: u32) -> Result<i64, Error> {
    Ok(get(r, bits)? as i64 - 1)
}

fn get_opt(r: &mut BitReader, bits: u32) -> Result<Option<u64>, Error> {
    if r.bool()? {
        Ok(None)
    } else {
        Ok(Some(get(r, bits)?))
    }
}

fn skip(r: &mut BitReader, fields: &[u32]) -> Result<(), Error> {
    for &b in fields {
        r.read(b)?;
    }
    Ok(())
}

fn read_traits(r: &mut BitReader) -> Result<(), Error> {
    skip(r, TRAIT_FIELDS[0])?;
    skip(r, TRAIT_FIELDS[1])?;
    skip(r, TRAIT_FIELDS[2])?;
    if r.bool()? {
        r.read(9)?;
    }
    skip(r, TRAIT_FIELDS[3])?;
    skip(r, TRAIT_FIELDS[4])
}

/// A string table, each string read at its first language's offset.
fn read_strings(r: &mut BitReader, cw: u32, ow: u32, sw: u32) -> Result<Vec<String>, Error> {
    let count = get(r, cw)?;
    let mut offsets = Vec::new();
    for _ in 0..count {
        let mut first = None;
        for _ in 0..12 {
            if r.bool()? {
                let o = get(r, ow)? as usize;
                first.get_or_insert(o);
            }
        }
        offsets.push(first);
    }
    if count == 0 {
        return Ok(Vec::new());
    }
    let size = get(r, sw)?;
    if r.bool()? {
        return Err(Error::Unsupported("a compressed string table".into()));
    }
    let mut data = Vec::new();
    for _ in 0..size {
        data.push(r.read(8)? as u8);
    }
    Ok(offsets
        .into_iter()
        .map(|o| {
            let Some(o) = o.filter(|&o| o < data.len()) else {
                return String::new();
            };
            let end = data[o..]
                .iter()
                .position(|&b| b == 0)
                .map_or(data.len(), |e| o + e);
            String::from_utf8_lossy(&data[o..end]).into_owned()
        })
        .collect())
}

fn read_content_header(r: &mut BitReader) -> Result<(), Error> {
    let ty = get(r, 4)?.wrapping_sub(1);
    r.read(32)?;
    for _ in 0..4 {
        r.read(64)?;
    }
    r.read(3)?;
    let mode = get(r, 3)?;
    r.read(3)?;
    r.read(32)?;
    r.read(8)?;
    for _ in 0..2 {
        r.read(64)?;
        r.read(64)?;
        for _ in 0..16 {
            if r.read(8)? == 0 {
                break;
            }
        }
        r.read(1)?;
    }
    for _ in 0..2 {
        for _ in 0..128 {
            if r.read(16)? == 0 {
                break;
            }
        }
    }
    match ty {
        3 | 4 => {
            r.read(32)?;
        }
        6 => {
            r.read(8)?;
        }
        _ => {}
    }
    match mode {
        1 => skip(r, &[8, 2, 2, 8, 32])?,
        2 => skip(r, &[2, 32])?,
        _ => {}
    }
    Ok(())
}

/// The base section; returns whether teams are on, the initial spawn delay
/// and the rounds.
fn read_base(r: &mut BitReader) -> Result<(bool, u8, u8), Error> {
    read_content_header(r)?;
    r.bool()?;
    let teams = r.bool()?;
    skip(r, &[1, 1, 1, 8])?;
    let rounds = get(r, 5)? as u8;
    skip(r, &[4, 7, 5])?;
    skip(r, &[1, 1, 1, 1, 6, 7, 8, 8, 8, 4])?;
    let initial_spawn_delay = get(r, 4)? as u8;
    r.read(6)?;
    read_traits(r)?;
    r.bool()?;
    skip(r, &[2, 1, 1, 1, 1, 1])?;
    r.read(6)?;
    read_traits(r)?;
    skip(r, &[8, 8])?;
    for _ in 0..3 {
        read_traits(r)?;
    }
    skip(r, &[7, 7, 7])?;
    skip(r, &[3, 3, 2])?;
    for _ in 0..8 {
        r.read(4)?;
        read_strings(r, 1, 5, 6)?;
        skip(r, &[4, 1, 32, 32, 32, 5])?;
    }
    r.read(2)?;
    for _ in 0..30 {
        r.read(1)?;
        if !r.bool()? {
            r.read(7)?;
        }
        skip(r, &[8, 8, 8, 4])?;
    }
    Ok((teams, initial_spawn_delay, rounds))
}

fn read_player(r: &mut BitReader) -> Result<Player, Error> {
    match get(r, 2)? {
        0 => Ok(Player(get(r, 5)? as u8)),
        kind => Err(Error::Unsupported(format!("player operand kind {kind}"))),
    }
}

fn read_object(r: &mut BitReader) -> Result<Object, Error> {
    Ok(match get(r, 3)? {
        0 => Object::Ref(get(r, 5)? as u8),
        1 => Object::PlayerObject {
            player: get(r, 5)? as u8,
            index: get(r, 2)? as u8,
        },
        2 => Object::ObjectObject {
            object: get(r, 5)? as u8,
            index: get(r, 2)? as u8,
        },
        4 => Object::PlayerBiped(get(r, 5)? as u8),
        kind => return Err(Error::Unsupported(format!("object operand kind {kind}"))),
    })
}

fn read_team(r: &mut BitReader) -> Result<Team, Error> {
    Ok(match get(r, 3)? {
        0 => Team::Ref(get_minus_one(r, 5)? as i8),
        4 => Team::PlayerOwner(get(r, 5)? as u8),
        5 => Team::ObjectOwner(get(r, 5)? as u8),
        kind => return Err(Error::Unsupported(format!("team operand kind {kind}"))),
    })
}

fn read_number(r: &mut BitReader) -> Result<Number, Error> {
    Ok(match get(r, 6)? {
        0 => Number::Constant(r.read_signed(16)? as i16),
        2 => Number::ObjectNumber {
            object: get(r, 5)? as u8,
            index: get(r, 3)? as u8,
        },
        4 => Number::GlobalNumber(get(r, 4)? as u8),
        7 => Number::TeamScore(get_minus_one(r, 5)? as i8),
        8 => Number::PlayerScore(get(r, 5)? as u8),
        16 => Number::ScoreToWin,
        kind => return Err(Error::Unsupported(format!("number operand kind {kind}"))),
    })
}

fn read_var(r: &mut BitReader) -> Result<Var, Error> {
    Ok(match get(r, 3)? {
        0 => Var::Number(read_number(r)?),
        1 => Var::Player(read_player(r)?),
        2 => Var::Object(read_object(r)?),
        3 => Var::Team(read_team(r)?),
        kind => return Err(Error::Unsupported(format!("variable operand kind {kind}"))),
    })
}

fn read_player_set(r: &mut BitReader) -> Result<PlayerSet, Error> {
    Ok(match get(r, 3)? {
        0 => PlayerSet::NoOne,
        1 => PlayerSet::Everyone,
        2 => PlayerSet::Allies,
        3 => PlayerSet::Enemies,
        5 => PlayerSet::Default,
        other => return Err(Error::Unsupported(format!("player set {other}"))),
    })
}

fn read_subject(r: &mut BitReader) -> Result<Subject, Error> {
    Ok(match get(r, 2)? {
        0 => Subject::Team(read_team(r)?),
        1 => Subject::Player(read_player(r)?),
        _ => Subject::None,
    })
}

fn read_compare(v: u64) -> Result<Compare, Error> {
    Ok(match v {
        0 => Compare::Less,
        1 => Compare::Greater,
        2 => Compare::Equal,
        3 => Compare::LessOrEqual,
        4 => Compare::GreaterOrEqual,
        5 => Compare::NotEqual,
        other => return Err(Error::Unsupported(format!("comparison {other}"))),
    })
}

fn read_op(v: u64) -> Result<Op, Error> {
    Ok(match v {
        0 => Op::Add,
        1 => Op::Subtract,
        4 => Op::Set,
        other => return Err(Error::Unsupported(format!("operator {other}"))),
    })
}

fn read_condition(r: &mut BitReader) -> Result<Condition, Error> {
    let ty = get(r, 5)?;
    let negate = r.bool()?;
    let or_sequence = get(r, 9)? as u16;
    let action_offset = get(r, 10)? as u16;
    let kind = match ty {
        1 => {
            let a = read_var(r)?;
            let b = read_var(r)?;
            ConditionKind::Compare {
                a,
                b,
                op: read_compare(get(r, 3)?)?,
            }
        }
        2 => {
            let object = read_object(r)?;
            ConditionKind::InBoundary {
                object,
                shape: read_object(r)?,
            }
        }
        3 => {
            let player = read_player(r)?;
            ConditionKind::KillerTypeIs {
                player,
                flags: get(r, 5)? as u8,
            }
        }
        other => return Err(Error::Unsupported(format!("condition type {other}"))),
    };
    Ok(Condition {
        kind,
        negate,
        or_sequence,
        action_offset,
    })
}

fn read_action(r: &mut BitReader) -> Result<Action, Error> {
    Ok(match get(r, 7)? {
        1 => {
            let target = match get(r, 2)? {
                1 => ScoreTarget::Player(read_player(r)?),
                0 => ScoreTarget::Team(read_team(r)?),
                other => return Err(Error::Unsupported(format!("score target {other}"))),
            };
            let op = read_op(get(r, 4)?)?;
            Action::ModifyScore {
                target,
                op,
                value: read_number(r)?,
            }
        }
        2 => {
            let object_type = get_opt(r, 11)?.map(|t| t as u16);
            let out = read_object(r)?;
            let at = read_object(r)?;
            let label = get_opt(r, 4)?.map(|l| l as u8);
            let flags = get(r, 3)? as u8;
            let mut offset = [0i8; 3];
            for c in offset.iter_mut() {
                *c = get(r, 8)? as u8 as i8;
            }
            let name = get_minus_one(r, 8)?;
            Action::CreateObject {
                object_type,
                out,
                at,
                label,
                flags,
                offset,
                name: (name >= 0).then_some(name as u8),
            }
        }
        3 => Action::DeleteObject(read_object(r)?),
        4 => {
            let object = read_object(r)?;
            Action::SetWaypointVisibility {
                object,
                who: read_player_set(r)?,
            }
        }
        5 => {
            let object = read_object(r)?;
            let icon = get_minus_one(r, 5)?;
            if icon == 11 {
                return Err(Error::Unsupported("territory waypoint icon".into()));
            }
            Action::SetWaypointIcon {
                object,
                icon: icon as u8,
            }
        }
        9 => {
            let a = read_var(r)?;
            let b = read_var(r)?;
            Action::ModifyVariable {
                a,
                b,
                op: read_op(get(r, 4)?)?,
            }
        }
        12 => {
            let object = read_object(r)?;
            Action::SetPickupPermissions {
                object,
                who: read_player_set(r)?,
            }
        }
        19 => {
            let object = read_object(r)?;
            Action::GetCarrier {
                object,
                out: read_player(r)?,
            }
        }
        20 => Action::CallTrigger(get(r, 9)? as u16),
        21 => Action::EndRound,
        29 => {
            let victim = read_player(r)?;
            Action::GetKiller {
                victim,
                out: read_player(r)?,
            }
        }
        44 => {
            let object = read_object(r)?;
            Action::SetWeaponPickupPriority {
                object,
                priority: get(r, 2)? as u8,
            }
        }
        ty @ (54 | 55) => {
            let object = read_object(r)?;
            let out = read_number(r)?;
            if ty == 54 {
                Action::GetShields { object, out }
            } else {
                Action::GetHealth { object, out }
            }
        }
        ty @ (64 | 65) => {
            let object = read_object(r)?;
            let op = read_op(get(r, 4)?)?;
            let value = read_number(r)?;
            if ty == 64 {
                Action::ModifyShields { object, op, value }
            } else {
                Action::ModifyHealth { object, op, value }
            }
        }
        66 => {
            let a = read_object(r)?;
            let b = read_object(r)?;
            Action::GetDistance {
                a,
                b,
                out: read_number(r)?,
            }
        }
        ty @ (75 | 76) => {
            let incident = get_minus_one(r, 10)?;
            let cause = read_subject(r)?;
            let effect = read_subject(r)?;
            Action::SendIncident {
                incident: incident.max(0) as u16,
                cause,
                effect,
                value: if ty == 76 {
                    Some(read_number(r)?)
                } else {
                    None
                },
            }
        }
        other => return Err(Error::Unsupported(format!("action type {other}"))),
    })
}

fn read_trigger(r: &mut BitReader) -> Result<Trigger, Error> {
    let kind = get(r, 3)?;
    let attribute = get(r, 3)? as u8;
    let kind = match kind {
        0 => TriggerKind::Do,
        1 => TriggerKind::EachPlayer,
        3 => TriggerKind::EachTeam,
        5 => match get_opt(r, 4)? {
            Some(l) => TriggerKind::EachObjectWithLabel(l as u8),
            None => return Err(Error::Unsupported("a label loop with no label".into())),
        },
        other => return Err(Error::Unsupported(format!("trigger type {other}"))),
    };
    Ok(Trigger {
        kind,
        attribute,
        first_condition: get(r, 9)? as u16,
        condition_count: get(r, 10)? as u16,
        first_action: get(r, 10)? as u16,
        action_count: get(r, 11)? as u16,
    })
}

fn read_numbers(r: &mut BitReader, bits: u32) -> Result<u8, Error> {
    let n = get(r, bits)? as u8;
    for _ in 0..n {
        read_number(r)?;
        r.read(2)?;
    }
    Ok(n)
}

fn read_handles(r: &mut BitReader, bits: u32) -> Result<u8, Error> {
    let n = get(r, bits)? as u8;
    for _ in 0..n {
        r.read(2)?;
    }
    Ok(n)
}

fn expect_none(r: &mut BitReader, bits: u32, what: &str) -> Result<(), Error> {
    if get(r, bits)? != 0 {
        return Err(Error::Unsupported(what.into()));
    }
    Ok(())
}

impl Variant {
    /// Read a variant the way the simulation's decoder does, and check every
    /// bit was accounted for.
    pub fn read(bytes: &[u8]) -> Result<Variant, Error> {
        let mut r = BitReader::new(bytes);
        let version = get(&mut r, 32)?;
        if version != 0x6a && version != 0x6b {
            return Err(Error::Unsupported(format!("encoding version {version:#x}")));
        }
        r.read(32)?;
        let (teams, initial_spawn_delay, rounds) = read_base(&mut r)?;
        if get(&mut r, 5)? != 0 || get(&mut r, 5)? != 0 {
            return Err(Error::Unsupported("player traits or user options".into()));
        }
        let strings = read_strings(&mut r, 7, 15, 15)?;
        r.read(7)?;
        read_strings(&mut r, 1, 9, 9)?;
        read_strings(&mut r, 1, 12, 12)?;
        read_strings(&mut r, 1, 9, 9)?;
        skip(&mut r, &[5, 5])?;
        let perms = get(&mut r, 6)?;
        for _ in 0..perms {
            r.read(16)?;
        }
        r.bool()?;
        for _ in 0..15 {
            r.read(32)?;
        }
        r.read(1)?;
        let score_to_win = get(&mut r, 16)? as u16;
        r.bool()?;
        r.bool()?;
        for _ in 0..82 {
            r.read(32)?;
        }

        let n = get(&mut r, 10)?;
        let conditions = (0..n)
            .map(|_| read_condition(&mut r))
            .collect::<Result<_, _>>()?;
        let n = get(&mut r, 11)?;
        let actions = (0..n)
            .map(|_| read_action(&mut r))
            .collect::<Result<_, _>>()?;
        let n = get(&mut r, 9)?;
        let triggers = (0..n)
            .map(|_| read_trigger(&mut r))
            .collect::<Result<_, _>>()?;

        let stats = get(&mut r, 3)?;
        for _ in 0..stats {
            skip(&mut r, &[7, 2, 2, 1])?;
        }
        let global_numbers = read_numbers(&mut r, 4)?;
        expect_none(&mut r, 4, "global timers")?;
        expect_none(&mut r, 4, "global teams")?;
        let global_players = read_handles(&mut r, 4)?;
        let global_objects = read_handles(&mut r, 5)?;
        for (bits, what) in [
            (4, "player numbers"),
            (3, "player timers"),
            (3, "player teams"),
            (3, "player players"),
            (3, "player objects"),
        ] {
            expect_none(&mut r, bits, what)?;
        }
        let object_numbers = read_numbers(&mut r, 4)?;
        expect_none(&mut r, 3, "object timers")?;
        expect_none(&mut r, 2, "object teams")?;
        expect_none(&mut r, 3, "object players")?;
        let object_objects = read_handles(&mut r, 3)?;
        for (bits, what) in [
            (4, "team numbers"),
            (3, "team timers"),
            (3, "team teams"),
            (3, "team players"),
            (3, "team objects"),
        ] {
            expect_none(&mut r, bits, what)?;
        }
        let widgets = get(&mut r, 3)?;
        for _ in 0..widgets {
            r.read(4)?;
        }
        let mut entries = [None; 7];
        for e in entries.iter_mut() {
            let v = get(&mut r, 9)?;
            *e = (v != 0).then(|| (v - 1) as u16);
        }
        let mut object_types = Vec::new();
        for word in 0..64u16 {
            let bits = get(&mut r, 32)?;
            for b in 0..32u16 {
                if bits & (1 << b) != 0 {
                    object_types.push(word * 32 + b);
                }
            }
        }
        let n = get(&mut r, 5)?;
        let mut filters = Vec::new();
        for _ in 0..n {
            let label = get_minus_one(&mut r, 7)?;
            let flags = get(&mut r, 3)?;
            if flags != 0 {
                return Err(Error::Unsupported("a filter with constraints".into()));
            }
            r.read(7)?;
            filters.push(Filter {
                label: label.max(0) as u8,
            });
        }
        if version >= 0x6b {
            r.read(32)?;
            for _ in 0..7 {
                r.read(8)?;
            }
        }
        if r.remaining() >= 8 {
            return Err(Error::Unsupported(format!(
                "{} bit(s) left after the variant",
                r.remaining()
            )));
        }
        Ok(Variant {
            score_to_win,
            teams,
            initial_spawn_delay,
            rounds,
            conditions,
            actions,
            triggers,
            vars: Variables {
                global_numbers,
                global_players,
                global_objects,
                object_numbers,
                object_objects,
            },
            entry_points: EntryPoints {
                init: entries[0],
                local_init: entries[1],
                host_migration: entries[2],
                double_host_migration: entries[3],
                object_death: entries[4],
                local: entries[5],
                pregame: entries[6],
            },
            strings,
            filters,
            object_types,
        })
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    #[test]
    fn an_empty_variant_reads_back_exactly() {
        let v = Variant::empty(25);
        let bytes = v.write().unwrap();
        assert_eq!(Variant::read(&bytes).unwrap(), v);
        assert!(
            bytes.len() < 0x5000,
            "{} bytes, past the loader's 0x5000",
            bytes.len()
        );
    }

    #[test]
    fn slayer_reads_back_exactly() {
        let v = Variant::slayer(25);
        let bytes = v.write().unwrap();
        assert_eq!(Variant::read(&bytes).unwrap(), v);
    }

    /// The Slayer variant proven in game (2026-09-30), byte for byte: the
    /// teams, strings, variables and filters support writes the same stream
    /// when none of it is used.
    #[test]
    fn slayer_bytes_are_unchanged() {
        let bytes = Variant::slayer(25).write().unwrap();
        let sum = bytes
            .iter()
            .fold(0u32, |h, &b| h.wrapping_mul(31).wrapping_add(b as u32));
        assert_eq!((bytes.len(), sum), SLAYER_FINGERPRINT);
    }

    /// Length and a rolling hash of the installed `slayer.mglo`
    /// (`megalo write --mode slayer --score 25`) from before the operand
    /// support grew, with the map options' item flags set ([`MAP_FLAGS`];
    /// 0xa685_d97e before).
    const SLAYER_FINGERPRINT: (usize, u32) = (1131, 0xa122_35a1);

    #[test]
    fn the_stream_starts_with_the_version_word() {
        let bytes = Variant::empty(1).write().unwrap();
        assert_eq!(&bytes[..4], &VERSION.to_be_bytes());
    }

    #[test]
    fn tick_reads_back_exactly() {
        let v = Variant::tick(1000);
        let bytes = v.write().unwrap();
        assert_eq!(Variant::read(&bytes).unwrap(), v);
    }

    #[test]
    fn triggers_cover_their_conditions_and_actions() {
        for v in [Variant::slayer(50), Variant::tick(50)] {
            check_ranges(&v);
        }
    }

    pub(crate) fn check_ranges(v: &Variant) {
        for t in &v.triggers {
            assert!((t.first_condition + t.condition_count) as usize <= v.conditions.len());
            assert!((t.first_action + t.action_count) as usize <= v.actions.len());
            for c in &v.conditions[t.first_condition as usize..][..t.condition_count as usize] {
                assert!(
                    c.action_offset < t.action_count,
                    "a condition gating past its trigger's actions"
                );
            }
        }
    }
}
