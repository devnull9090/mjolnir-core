//! Timed objectives: Oddball, King and Juggernaut, free-for-all and team. All
//! score and ownership changes run in the replicated simulation; the Unreal
//! loader only supplies presentation.
//!
//! A team game scores the same way, per player: a team's score is its
//! players' sum (team scoring 0), and the engine ends the round when a team
//! reaches the score to win, so a team script has no end trigger of its own.
use crate::race::{self, on_each_spawn};
use crate::script::{compare, constant, eq, obj, set, Builder, Item};
use crate::variant::{
    object, player, team, Action, Compare, ConditionKind, Number, Object, Op, Player, PlayerSet,
    ScoreTarget, Subject, Team, Traits, TriggerKind, Var, Variables, Variant, ATTR_NORMAL,
    DEATH_ANY, DEATH_KILL,
};

/// Incident indices (`globals\incident_properties` order).
pub mod incident {
    pub const HILL_CONTROLLED: u16 = 69;
    pub const HILL_MOVED: u16 = 73;
    pub const BALL_TAKEN: u16 = 76;
    pub const NEW_JUGGERNAUT: u16 = 151;
}

/// The label every hill carries (a placement's `megalo label`).
pub const HILL_LABEL: &str = "koth_hill";

/// Waypoint icons.
const ICON_SKULL: u8 = 7;
const ICON_CROWN: u8 = 8;

/// A contested hill's rule, the one switch between two readings of King:
/// `false`, it scores nobody, and one player (or one team) alone on the hill
/// earns the points. `true` is CE's own rule: everyone on the hill scores, at
/// most one point a second per team, and a contest changes only the sounds.
pub const CONTESTED_HILL_SCORES: bool = false;

/// Trait values: a stored value indexes the simulation's table for its trait
/// (variant.rs, [`TRAITS`](crate::variant::TRAITS)), so these are positions,
/// not percentages.
pub mod trait_value {
    /// `damage` and `melee_damage`: x1.5 dealt, CE's extra damage. CE scales
    /// every hit; the simulation splits melee off, so a set needs both. They
    /// share one table.
    pub const DAMAGE_150: u8 = 9;
    /// `damage_resistance`: a factor that divides the damage taken (the last
    /// entry, invulnerable, is 1000), so 200% is CE's x0.5 taken. 50% would
    /// be double damage.
    pub const RESISTANCE_200: u8 = 7;
    /// `speed`: CE's slow carrier, x0.75.
    pub const SPEED_75: u8 = 4;
    /// `speed`: the table has no 125%, CE's fast carrier, only 120% and 130%.
    /// This is the one Bungie's own speed boost uses.
    pub const SPEED_120: u8 = 8;
    pub const SPEED_150: u8 = 11;
    /// `camo`: "good", the host's Invisible Players option, proven in game.
    pub const CAMO_GOOD: u8 = 4;
}

/// A named trait set: name, description, and trait values by name.
type TraitSet = (&'static str, &'static str, &'static [(&'static str, u8)]);

const JUGGERNAUT_TRAITS: TraitSet = (
    "Juggernaut",
    "Half as much damage again.",
    &[
        ("damage", trait_value::DAMAGE_150),
        ("melee_damage", trait_value::DAMAGE_150),
    ],
);
const STALKER_TRAITS: TraitSet = (
    "Stalker",
    "Unseen and fast.",
    &[
        ("speed", trait_value::SPEED_120),
        ("camo", trait_value::CAMO_GOOD),
    ],
);
const HUNTER_TRAITS: TraitSet = (
    "Hunter",
    "Half damage taken.",
    &[("damage_resistance", trait_value::RESISTANCE_200)],
);
const TAGGED_TRAITS: TraitSet = (
    "It",
    "Slow while it.",
    &[("speed", trait_value::SPEED_75)],
);
const TRAIT_TEST_TRAITS: TraitSet = (
    "Trait test",
    "Fast, strong and unseen.",
    &[
        ("damage", trait_value::DAMAGE_150),
        ("melee_damage", trait_value::DAMAGE_150),
        ("speed", trait_value::SPEED_150),
        ("camo", trait_value::CAMO_GOOD),
    ],
);

/// A game of one player who is "it": Juggernaut and its relatives.
#[derive(Debug, Clone, Copy)]
struct ItGame {
    score_to_win: u16,
    /// "It" scores a point every this many ticks, and kills score nothing.
    /// `None` is Juggernaut's points for kills.
    ticks_per_point: Option<i16>,
    /// Applied to "it" every tick.
    it: Option<TraitSet>,
    /// Applied to everyone else every tick, whether or not anybody is it.
    others: Option<TraitSet>,
}

fn add_traits(b: &mut Builder, (name, description, values): TraitSet) -> u8 {
    let mut traits = Traits::unchanged();
    for &(field, value) in values {
        traits.set(field, value).expect("a trait in the table");
    }
    b.script_traits(name, description, traits)
}

fn apply_traits(who: u8, traits: u8) -> Item {
    Item::Do(Action::ApplyPlayerTraits {
        player: Player(who),
        traits,
    })
}

pub(crate) fn number(i: u8) -> Var {
    Var::Number(Number::GlobalNumber(i))
}
pub(crate) fn add(i: u8, delta: i16) -> Item {
    Item::Do(Action::ModifyVariable {
        a: number(i),
        b: constant(delta),
        op: Op::Add,
    })
}
pub(crate) fn call(trigger: u16) -> Item {
    Item::Do(Action::CallTrigger(trigger))
}

/// Items that move `order` to another place of `count`, by a step that grows
/// each time, so the walk looks random and never stays put. The sim's own
/// random pick (action 96) found nothing on Blood Gulch while it worked on
/// Prisoner: with vehicle filters added, on 2026-11-04.
pub(crate) fn walk(b: &mut Builder, order: u8, count: u8, step: u8) -> Vec<Item> {
    let step_wrap = b.sub(
        TriggerKind::Do,
        vec![
            compare(number(step), number(count), Compare::GreaterOrEqual),
            set(number(step), constant(1)),
        ],
    );
    let order_wrap = b.sub(
        TriggerKind::Do,
        vec![
            compare(number(order), number(count), Compare::GreaterOrEqual),
            Item::Do(Action::ModifyVariable {
                a: number(order),
                b: number(count),
                op: Op::Subtract,
            }),
        ],
    );
    vec![
        add(step, 1),
        call(step_wrap),
        Item::Do(Action::ModifyVariable {
            a: number(order),
            b: number(step),
            op: Op::Add,
        }),
        call(order_wrap),
    ]
}

/// Items for a walk of a label: keep `count` one past the highest spawn order.
pub(crate) fn count_places(count: u8) -> Vec<Item> {
    let order = Var::Number(Number::SpawnSequence(object::CURRENT));
    vec![
        compare(order.clone(), number(count), Compare::GreaterOrEqual),
        set(number(count), order),
        add(count, 1),
    ]
}
pub(crate) fn plr(p: u8) -> Var {
    Var::Player(Player(p))
}
/// The conditions that pass for a living player: a biped, with health left.
/// A dead biped stays attached for a moment. `health` is a scratch number.
pub(crate) fn alive(who: u8, health: u8) -> Vec<Item> {
    let biped = Object::PlayerBiped(who);
    vec![
        compare(Var::Object(biped), obj(object::NONE), Compare::NotEqual),
        Item::Do(Action::GetHealth {
            object: biped,
            out: Number::GlobalNumber(health),
        }),
        compare(number(health), constant(0), Compare::Greater),
    ]
}
/// Add one to a player's score.
pub(crate) fn score_point(who: u8) -> Item {
    Item::Do(Action::ModifyScore {
        target: ScoreTarget::Player(Player(who)),
        op: Op::Add,
        value: Number::Constant(1),
    })
}
pub(crate) fn end_at_score(b: &mut Builder) {
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
pub(crate) fn score_snapshot(incident: u16, who: u8) -> Item {
    Item::Do(Action::SendIncident {
        incident,
        cause: Subject::Player(Player(who)),
        effect: Subject::None,
        value: Some(Number::PlayerScore(who)),
    })
}

/// King of the Hill's rules.
#[derive(Debug, Clone, Copy)]
pub struct King {
    pub score_to_win: u16,
    /// Simulation ticks per second: a hill pays a point every this many.
    pub tick_rate: i16,
    /// Ticks between moves to a random other hill; `None` keeps the first
    /// hill, the one of spawn order 0, all game.
    pub move_ticks: Option<i16>,
    pub teams: bool,
    /// [`CONTESTED_HILL_SCORES`], unless a test wants the other rule.
    pub contested_scores: bool,
}

impl Variant {
    /// One neutral skull. Score once per second held; an abandoned/destroyed
    /// skull returns to the authored origin. The supplied type must be a
    /// carryable weapon with a skull presentation (the CE runtime's type 18).
    pub fn oddball(score: u16, ball_type: u16, tick_rate: i16, reset_ticks: i16) -> Self {
        Self::oddball_game(score, ball_type, tick_rate, reset_ticks, false)
    }

    /// Oddball between Red and Blue: the carrier's seconds count for the
    /// carrier's team.
    pub fn team_oddball(score: u16, ball_type: u16, tick_rate: i16, reset_ticks: i16) -> Self {
        Self::oddball_game(score, ball_type, tick_rate, reset_ticks, true)
    }

    fn oddball_game(
        score: u16,
        ball_type: u16,
        tick_rate: i16,
        reset_ticks: i16,
        teams: bool,
    ) -> Self {
        let mut b = Builder::new(Variant {
            teams,
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
                score_point(carrier),
                score_snapshot(incident::BALL_TAKEN, carrier),
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
                    icon: ICON_SKULL,
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
        if !teams {
            end_at_score(&mut b);
        }
        b.v
    }

    /// King: the hill of spawn order 0, all game.
    pub fn koth(score: u16, tick_rate: i16) -> Self {
        Self::king(King {
            score_to_win: score,
            tick_rate,
            move_ticks: None,
            teams: false,
            contested_scores: CONTESTED_HILL_SCORES,
        })
    }

    /// Crazy King: King, the hill moving to a random other one every
    /// `move_ticks`.
    pub fn crazy_king(score: u16, tick_rate: i16, move_ticks: i16) -> Self {
        Self::king(King {
            score_to_win: score,
            tick_rate,
            move_ticks: Some(move_ticks),
            teams: false,
            contested_scores: CONTESTED_HILL_SCORES,
        })
    }

    /// Team King: Crazy King between Red and Blue.
    pub fn team_koth(score: u16, tick_rate: i16, move_ticks: i16) -> Self {
        Self::king(King {
            score_to_win: score,
            tick_rate,
            move_ticks: Some(move_ticks),
            teams: true,
            contested_scores: CONTESTED_HILL_SCORES,
        })
    }

    /// One live hill. A living player inside its boundary holds it; alone (or
    /// with only teammates) they earn a point a second, and a team's point
    /// goes to one player on the hill. See [`CONTESTED_HILL_SCORES`] for two
    /// sides on the hill.
    ///
    /// One file serves every map: CE maps carry 1 to 14 hills, and a label
    /// each would pass the simulation's 16 filters. Every hill has the label
    /// `koth_hill`, its spawn order names it, and the walk of the label each
    /// tick finds the live one. The hill's own team is never written, or the
    /// spawn search would start using the marker.
    pub fn king(k: King) -> Self {
        // Numbers: the live hill's order, ticks since it moved, sides on the
        // hill this tick, ticks held, a scratch health and a scratch "alive".
        const ORDER: u8 = 0;
        const MOVED: u8 = 1;
        const SIDES: u8 = 2;
        const HELD: u8 = 3;
        const HEALTH: u8 = 4;
        const LIVING: u8 = 5;
        // On a moving hill: how many hills, and the walk's step.
        const COUNT: u8 = 6;
        const STEP: u8 = 7;
        // Player number, on a moving hill: 1 while alive.
        const SPAWNED: u8 = 0;
        let moves = k.move_ticks.is_some();
        let mut b = Builder::new(Variant {
            teams: k.teams,
            vars: Variables {
                global_numbers: if moves { 8 } else { 5 },
                global_objects: 1,
                global_players: if k.teams { 2 } else { 1 },
                player_numbers: if moves { 1 } else { 0 },
                ..Variables::default()
            },
            ..Variant::empty(k.score_to_win)
        });
        let label = b.label(HILL_LABEL);
        let hill = object::global(0);
        let none = plr(player::NONE);
        let mut on_hill = alive(player::CURRENT, HEALTH);
        on_hill.push(Item::If(ConditionKind::InBoundary {
            object: Object::PlayerBiped(player::CURRENT),
            shape: Object::Ref(hill),
        }));

        // Who is on the hill: one player for each side, the first the walk
        // meets of a team, the last of a free-for-all.
        let sides: Vec<u8> = (0..b.v.vars.global_players).map(player::global).collect();
        let mut scan = on_hill.clone();
        if k.teams {
            for (i, &side) in sides.iter().enumerate() {
                let mark = b.sub(
                    TriggerKind::Do,
                    vec![
                        eq(
                            Var::Team(Team::PlayerOwner(player::CURRENT)),
                            Var::Team(Team::Ref(team::team(i as i8))),
                        ),
                        eq(plr(side), none.clone()),
                        add(SIDES, 1),
                        set(plr(side), plr(player::CURRENT)),
                    ],
                );
                scan.push(call(mark));
            }
        } else {
            scan.extend([add(SIDES, 1), set(plr(sides[0]), plr(player::CURRENT))]);
        }
        let scan = b.sub(TriggerKind::EachPlayer, scan);

        // A point, each second a hill pays: to the side's player, or under
        // CE's rule in a free-for-all, to everyone on it.
        let mut pay = vec![compare(
            number(HELD),
            constant(k.tick_rate),
            Compare::GreaterOrEqual,
        )];
        if k.contested_scores && !k.teams {
            let mut everyone = on_hill;
            everyone.extend([
                score_point(player::CURRENT),
                score_snapshot(incident::HILL_CONTROLLED, player::CURRENT),
            ]);
            pay.push(call(b.sub(TriggerKind::EachPlayer, everyone)));
        } else {
            for &side in &sides {
                let credit = b.sub(
                    TriggerKind::Do,
                    vec![
                        compare(plr(side), none.clone(), Compare::NotEqual),
                        score_point(side),
                        score_snapshot(incident::HILL_CONTROLLED, side),
                    ],
                );
                pay.push(call(credit));
            }
        }
        pay.push(set(number(HELD), constant(0)));
        let pay = b.sub(TriggerKind::Do, pay);

        let (holds, idles) = if k.contested_scores {
            (
                compare(number(SIDES), constant(1), Compare::GreaterOrEqual),
                eq(number(SIDES), constant(0)),
            )
        } else {
            (
                eq(number(SIDES), constant(1)),
                compare(number(SIDES), constant(1), Compare::NotEqual),
            )
        };
        let held = b.sub(TriggerKind::Do, vec![holds, add(HELD, 1), call(pay)]);
        let idle = b.sub(TriggerKind::Do, vec![idles, set(number(HELD), constant(0))]);

        if let Some(ticks) = k.move_ticks {
            // The value is the new hill's spawn order, for the HUD.
            let counted = count_places(COUNT);
            let count = b.sub(TriggerKind::Do, counted);
            b.trigger(TriggerKind::EachObjectWithLabel(label), ATTR_NORMAL, vec![call(count)]);
            let mut moved = walk(&mut b, ORDER, COUNT, STEP);
            moved.extend([
                set(number(HELD), constant(0)),
                Item::Do(Action::SendIncident {
                    incident: incident::HILL_MOVED,
                    cause: Subject::None,
                    effect: Subject::None,
                    value: Some(Number::GlobalNumber(ORDER)),
                }),
            ]);
            let pick = b.sub(TriggerKind::Do, moved);
            let rotate = b.sub(
                TriggerKind::Do,
                vec![
                    compare(number(MOVED), constant(ticks), Compare::GreaterOrEqual),
                    set(number(MOVED), constant(0)),
                    call(pick),
                ],
            );
            b.trigger(
                TriggerKind::Do,
                ATTR_NORMAL,
                vec![add(MOVED, 1), call(rotate)],
            );
            // Each spawn says where the hill is, for a player who joined
            // since it moved. Not by `hill_moved`, which has a sound
            // (events.json): `checkpoint_reached` is silent and relayed.
            let tell = Item::Do(Action::SendIncident {
                incident: race::incident::CHECKPOINT,
                cause: Subject::None,
                effect: Subject::None,
                value: Some(Number::GlobalNumber(ORDER)),
            });
            on_each_spawn(&mut b, HEALTH, LIVING, SPAWNED, tell);
        }

        let order = Var::Number(Number::SpawnSequence(object::CURRENT));
        let mut live = vec![
            Item::Do(Action::SetWaypointVisibility {
                object: Object::Ref(object::CURRENT),
                who: PlayerSet::NoOne,
            }),
            eq(order, number(ORDER)),
            set(obj(hill), obj(object::CURRENT)),
            set(number(SIDES), constant(0)),
        ];
        if k.teams {
            live.extend(sides.iter().map(|&side| set(plr(side), none.clone())));
        }
        live.extend([
            Item::Do(Action::SetWaypointVisibility {
                object: Object::Ref(hill),
                who: PlayerSet::Everyone,
            }),
            Item::Do(Action::SetWaypointIcon {
                object: Object::Ref(hill),
                icon: ICON_CROWN,
            }),
            call(scan),
            call(held),
            call(idle),
        ]);
        b.trigger(TriggerKind::EachObjectWithLabel(label), ATTR_NORMAL, live);
        if !k.teams {
            end_at_score(&mut b);
        }
        b.v
    }

    /// Juggernaut, CE's rule: no ball and no change of weapon; the Juggernaut
    /// deals extra damage, CE's Standard bank at normal speed. The first
    /// killer takes the free slot, and killing the Juggernaut takes it from
    /// them. A point for killing the Juggernaut, for the Juggernaut's own
    /// kills, and for any kill while nobody is it; other kills score nothing.
    /// A killer already dead scores but does not take the slot. A Juggernaut
    /// who dies any other way, or leaves, frees it. Every spawn names them
    /// again, for a player who joined after the slot last changed.
    pub fn juggernaut(score: u16) -> Self {
        Self::it_game(ItGame {
            score_to_win: score,
            ticks_per_point: None,
            it: Some(JUGGERNAUT_TRAITS),
            others: None,
        })
    }

    /// Stalker, CE's: Juggernaut's scoring, the Juggernaut invisible and
    /// fast, everyone else resistant to damage.
    pub fn stalker(score: u16) -> Self {
        Self::it_game(ItGame {
            score_to_win: score,
            ticks_per_point: None,
            it: Some(STALKER_TRAITS),
            others: Some(HUNTER_TRAITS),
        })
    }

    /// Reverse Tag, CE's: the slot passes as in Juggernaut, but kills score
    /// nothing and "it" earns a point a second, slowed while it. Nobody is
    /// it until the first kill.
    pub fn reverse_tag(score: u16, tick_rate: i16) -> Self {
        Self::it_game(ItGame {
            score_to_win: score,
            ticks_per_point: Some(tick_rate),
            it: Some(TAGGED_TRAITS),
            others: None,
        })
    }

    /// Slayer that gives every living player a measurable set of traits, to
    /// test them in game. Not a released mode.
    pub fn trait_test(score: u16) -> Self {
        const HEALTH: u8 = 0;
        let slayer = Self::slayer(score);
        let mut b = Builder::new(Variant {
            vars: Variables {
                global_numbers: 1,
                ..slayer.vars
            },
            ..slayer
        });
        let traits = add_traits(&mut b, TRAIT_TEST_TRAITS);
        let mut items = alive(player::CURRENT, HEALTH);
        items.push(apply_traits(player::CURRENT, traits));
        b.trigger(TriggerKind::EachPlayer, ATTR_NORMAL, items);
        b.v
    }

    fn it_game(game: ItGame) -> Self {
        const HEALTH: u8 = 0;
        const SEEN: u8 = 1;
        const LIVING: u8 = 2;
        // Ticks "it" has held the slot since the last point, in a game of
        // time.
        const HELD: u8 = 3;
        // Player number: 1 while alive.
        const SPAWNED: u8 = 0;
        let mut b = Builder::new(Variant {
            vars: Variables {
                global_numbers: if game.ticks_per_point.is_some() { 4 } else { 3 },
                global_players: 2,
                player_numbers: 1,
                ..Variables::default()
            },
            ..Variant::empty(game.score_to_win)
        });
        let it = player::global(0);
        let killer = player::global(1);
        let current = plr(player::CURRENT);
        let none = plr(player::NONE);
        let freed = Item::Do(Action::SendIncident {
            incident: incident::NEW_JUGGERNAUT,
            cause: Subject::None,
            effect: Subject::None,
            value: Some(Number::Constant(0)),
        });

        // A game of time pays no points for kills.
        let award = match game.ticks_per_point {
            Some(_) => None,
            None => Some(call(b.sub(
                TriggerKind::Do,
                vec![
                    score_point(killer),
                    score_snapshot(incident::BALL_TAKEN, killer),
                ],
            ))),
        };
        let mut take = alive(killer, HEALTH);
        take.push(set(plr(it), plr(killer)));
        if game.ticks_per_point.is_some() {
            take.push(set(number(HELD), constant(0)));
        }
        take.push(Item::Do(Action::SendIncident {
            incident: incident::NEW_JUGGERNAUT,
            cause: Subject::Player(Player(killer)),
            effect: Subject::None,
            value: Some(Number::Constant(1)),
        }));
        let take = b.sub(TriggerKind::Do, take);
        // In this order, so one kill matches one branch: only taking the
        // slot changes who is it, and that is after the test for the
        // Juggernaut's own kills.
        let mut kill = vec![
            Item::If(ConditionKind::KillerTypeIs {
                player: Player(player::CURRENT),
                flags: DEATH_KILL,
            }),
            compare(plr(killer), none.clone(), Compare::NotEqual),
            compare(plr(killer), current.clone(), Compare::NotEqual),
        ];
        if let Some(award) = &award {
            let by_it = vec![eq(plr(killer), plr(it)), award.clone()];
            kill.push(call(b.sub(TriggerKind::Do, by_it)));
        }
        for test in [eq(current.clone(), plr(it)), eq(plr(it), none.clone())] {
            let mut branch = vec![test];
            branch.extend(award.clone());
            branch.push(call(take));
            kill.push(call(b.sub(TriggerKind::Do, branch)));
        }
        let kill = b.sub(TriggerKind::Do, kill);
        let vacate = b.sub(
            TriggerKind::Do,
            vec![
                eq(current.clone(), plr(it)),
                set(plr(it), none.clone()),
                freed.clone(),
            ],
        );
        b.trigger(
            TriggerKind::EachPlayer,
            ATTR_NORMAL,
            vec![
                Item::If(ConditionKind::KillerTypeIs {
                    player: Player(player::CURRENT),
                    flags: DEATH_ANY,
                }),
                set(plr(killer), none.clone()),
                Item::Do(Action::GetKiller {
                    victim: Player(player::CURRENT),
                    out: Player(killer),
                }),
                call(kill),
                call(vacate),
            ],
        );

        // Not every death has a record to read: the sim writes none for a
        // death that raises only `death`, every AI kill among them, and a
        // Juggernaut who left has no death at all. So the slot needs someone
        // alive in it. The kills above run first, and a kill passes the slot
        // on before this looks; if health runs out a tick ahead of the
        // record, that kill finds the slot free and scores and takes the same.
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![set(number(SEEN), constant(0))],
        );
        let mut seen = vec![eq(current.clone(), plr(it))];
        seen.extend(alive(player::CURRENT, HEALTH));
        seen.push(set(number(SEEN), constant(1)));
        b.trigger(TriggerKind::EachPlayer, ATTR_NORMAL, seen);
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![
                compare(plr(it), none.clone(), Compare::NotEqual),
                eq(number(SEEN), constant(0)),
                set(plr(it), none.clone()),
                freed,
            ],
        );

        // After the check above, so only a living "it" earns time or traits.
        if let Some(ticks) = game.ticks_per_point {
            let pay = b.sub(
                TriggerKind::Do,
                vec![
                    compare(number(HELD), constant(ticks), Compare::GreaterOrEqual),
                    score_point(it),
                    score_snapshot(incident::BALL_TAKEN, it),
                    set(number(HELD), constant(0)),
                ],
            );
            b.trigger(
                TriggerKind::Do,
                ATTR_NORMAL,
                vec![
                    compare(plr(it), none.clone(), Compare::NotEqual),
                    add(HELD, 1),
                    call(pay),
                ],
            );
        }
        if let Some(set) = game.it {
            let traits = add_traits(&mut b, set);
            b.trigger(
                TriggerKind::Do,
                ATTR_NORMAL,
                vec![
                    compare(plr(it), none.clone(), Compare::NotEqual),
                    apply_traits(it, traits),
                ],
            );
        }
        if let Some(set) = game.others {
            let traits = add_traits(&mut b, set);
            b.trigger(
                TriggerKind::EachPlayer,
                ATTR_NORMAL,
                vec![
                    compare(current, plr(it), Compare::NotEqual),
                    apply_traits(player::CURRENT, traits),
                ],
            );
        }

        // Nobody to name while the slot is free.
        let resend = b.sub(
            TriggerKind::Do,
            vec![
                compare(plr(it), none, Compare::NotEqual),
                Item::Do(Action::SendIncident {
                    incident: incident::NEW_JUGGERNAUT,
                    cause: Subject::Player(Player(it)),
                    effect: Subject::None,
                    value: Some(Number::Constant(1)),
                }),
            ],
        );
        on_each_spawn(&mut b, HEALTH, LIVING, SPAWNED, call(resend));
        end_at_score(&mut b);
        b.v
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::powerups::HealthPacks;
    use crate::variant::Condition;

    fn timed_variants() -> Vec<(&'static str, Variant)> {
        vec![
            ("oddball", Variant::oddball(120, 18, 60, 1800)),
            ("team_oddball", Variant::team_oddball(120, 18, 60, 1800)),
            ("koth", Variant::koth(120, 60)),
            ("crazy_king", Variant::crazy_king(120, 60, 3600)),
            ("team_koth", Variant::team_koth(120, 60, 3600)),
            ("juggernaut", Variant::juggernaut(15)),
            ("stalker", Variant::stalker(10)),
            ("reverse_tag", Variant::reverse_tag(120, 60)),
        ]
    }

    /// Who each action applying traits names, with the set's changed values.
    fn applied(v: &Variant) -> Vec<(u8, Vec<(&'static str, u8)>)> {
        v.actions
            .iter()
            .filter_map(|a| match a {
                Action::ApplyPlayerTraits { player, traits } => Some((
                    player.0,
                    v.script_traits[*traits as usize].traits.changed(),
                )),
                _ => None,
            })
            .collect()
    }

    /// The trigger holding the action at `index`.
    fn trigger_of(v: &Variant, index: usize) -> &crate::variant::Trigger {
        v.triggers
            .iter()
            .find(|t| {
                (t.first_action as usize..(t.first_action + t.action_count) as usize)
                    .contains(&index)
            })
            .unwrap()
    }

    /// Every action of a variant raising `incident`.
    fn raised(v: &Variant, incident: u16) -> Vec<&Action> {
        v.actions
            .iter()
            .filter(|a| matches!(a, Action::SendIncident { incident: i, .. } if *i == incident))
            .collect()
    }

    fn ends_at_score(v: &Variant) -> bool {
        v.conditions.iter().any(|c: &Condition| {
            matches!(
                &c.kind,
                ConditionKind::Compare {
                    b: Var::Number(Number::ScoreToWin),
                    ..
                }
            )
        })
    }

    #[test]
    fn timed_objectives_roundtrip_with_shared_health_and_vehicle_filters() {
        for (name, v) in timed_variants() {
            let v = v
                .with_time_limit()
                .with_health_packs(HealthPacks {
                    object_type: 19,
                    respawn_ticks: 900,
                    reach_feet: 8,
                })
                .unwrap();
            crate::variant::tests::check_ranges(&v);
            let bytes = v.write().unwrap();
            assert_eq!(Variant::read(&bytes).unwrap(), v, "{name}");
            Variant::validate(&bytes).unwrap();
            assert!(v.filters.len() < 16, "{name}");
        }
    }

    #[test]
    fn team_games_leave_the_end_of_the_round_to_the_engine() {
        for (name, v) in timed_variants() {
            let teams = name.starts_with("team_");
            assert_eq!(v.teams, teams, "{name}");
            assert_eq!(ends_at_score(&v), !teams, "{name}");
        }
    }

    #[test]
    fn koth_is_one_label_whatever_the_map() {
        let v = Variant::koth(120, 60);
        assert_eq!(v.filters.len(), 1);
        assert_eq!(v.strings[v.filters[0].label as usize], "koth_hill");
    }

    #[test]
    fn plain_king_never_moves_its_hill() {
        let v = Variant::koth(120, 60);
        assert!(raised(&v, incident::HILL_MOVED).is_empty());
        assert!(raised(&v, race::incident::CHECKPOINT).is_empty());
    }

    #[test]
    fn a_moving_hill_walks_by_spawn_order() {
        for v in [
            Variant::crazy_king(120, 60, 3600),
            Variant::team_koth(120, 60, 3600),
        ] {
            assert_eq!(raised(&v, incident::HILL_MOVED).len(), 1);
            let told = raised(&v, race::incident::CHECKPOINT);
            assert_eq!(told.len(), 1, "the place again, on each spawn");
            assert!(matches!(
                told[0],
                Action::SendIncident {
                    cause: Subject::None,
                    value: Some(Number::GlobalNumber(0)),
                    ..
                }
            ));
            assert!(!v
                .actions
                .iter()
                .any(|a| matches!(a, Action::GetRandomObject { .. })));
        }
    }

    /// The hill's own team is the one thing a script must not write: the
    /// spawn search would use the marker.
    #[test]
    fn nothing_writes_a_hill_team() {
        for (name, v) in timed_variants() {
            assert!(
                !v.actions.iter().any(|a| matches!(
                    a,
                    Action::ModifyVariable {
                        a: Var::Team(_),
                        ..
                    }
                )),
                "{name}"
            );
        }
    }

    /// The other reading of a contested hill, one constant away: it builds,
    /// reads back, and no longer gates scoring on exactly one side.
    #[test]
    fn the_contested_rule_flips_with_one_field() {
        let exactly_one = |v: &Variant| {
            v.conditions.iter().any(|c| {
                matches!(
                    &c.kind,
                    ConditionKind::Compare {
                        a: Var::Number(Number::GlobalNumber(2)),
                        b: Var::Number(Number::Constant(1)),
                        op: Compare::Equal,
                    }
                )
            })
        };
        for teams in [false, true] {
            let rules = |contested_scores| King {
                score_to_win: 120,
                tick_rate: 60,
                move_ticks: Some(3600),
                teams,
                contested_scores,
            };
            let ce = Variant::king(rules(true));
            crate::variant::tests::check_ranges(&ce);
            assert_eq!(Variant::read(&ce.write().unwrap()).unwrap(), ce);
            assert!(!exactly_one(&ce));
            assert!(exactly_one(&Variant::king(rules(false))));
        }
    }

    #[test]
    fn team_king_counts_red_and_blue_as_two_sides() {
        let v = Variant::team_koth(120, 60, 3600);
        assert_eq!(v.vars.global_players, 2);
        for i in [0, 1] {
            assert!(v.conditions.iter().any(|c| matches!(
                &c.kind,
                ConditionKind::Compare {
                    a: Var::Team(Team::PlayerOwner(player::CURRENT)),
                    b: Var::Team(Team::Ref(t)),
                    op: Compare::Equal,
                } if *t == i
            )));
        }
    }

    #[test]
    fn juggernaut_is_free_for_all_and_raises_who_is_it() {
        let v = Variant::juggernaut(15);
        assert!(!v.teams);
        assert!(v.filters.is_empty());
        let raises = raised(&v, incident::NEW_JUGGERNAUT);
        let taken = raises
            .iter()
            .filter(|a| {
                matches!(
                    a,
                    Action::SendIncident {
                        cause: Subject::Player(Player(p)),
                        value: Some(Number::Constant(1)),
                        ..
                    } if *p == player::global(1)
                )
            })
            .count();
        // One for the slot taken, one each for a recorded death and for a
        // slot with nobody alive in it, one for the resend.
        assert_eq!((raises.len(), taken), (4, 1));
        assert_eq!(raised(&v, incident::BALL_TAKEN).len(), 1);
    }

    /// A joiner learns who is it from the next spawn: the slot's holder,
    /// named by the global, and only while someone holds it.
    #[test]
    fn juggernaut_is_named_again_on_each_spawn() {
        let v = Variant::juggernaut(15);
        assert_eq!(v.vars.player_numbers, 1);
        let resends = raised(&v, incident::NEW_JUGGERNAUT)
            .into_iter()
            .filter(|a| {
                matches!(
                    a,
                    Action::SendIncident {
                        cause: Subject::Player(Player(p)),
                        value: Some(Number::Constant(1)),
                        ..
                    } if *p == player::global(0)
                )
            })
            .count();
        assert_eq!(resends, 1);
    }

    /// The sim writes no death record for an AI kill, so the slot check has
    /// to read the holder's health itself.
    #[test]
    fn a_dead_juggernaut_does_not_hold_the_slot() {
        let v = Variant::juggernaut(15);
        let reads = |who: u8| {
            v.actions
                .iter()
                .filter(|a| {
                    matches!(
                        a,
                        Action::GetHealth {
                            object: Object::PlayerBiped(p),
                            ..
                        } if *p == who
                    )
                })
                .count()
        };
        // The slot check and the spawn resend; `take` reads the killer.
        assert_eq!(reads(player::CURRENT), 2);
        assert_eq!(reads(player::global(1)), 1);
    }

    #[test]
    fn juggernaut_deals_extra_damage_and_nobody_else_changes() {
        let v = Variant::juggernaut(15);
        assert_eq!(
            applied(&v),
            [(
                player::global(0),
                vec![
                    ("damage", trait_value::DAMAGE_150),
                    ("melee_damage", trait_value::DAMAGE_150)
                ]
            )]
        );
    }

    #[test]
    fn oddball_changes_no_traits() {
        for v in [
            Variant::oddball(120, 18, 60, 1800),
            Variant::team_oddball(120, 18, 60, 1800),
        ] {
            assert!(v.script_traits.is_empty());
            assert!(applied(&v).is_empty());
        }
    }

    #[test]
    fn stalker_hides_the_juggernaut_and_toughens_the_rest() {
        let v = Variant::stalker(10);
        assert_eq!(
            applied(&v),
            [
                (
                    player::global(0),
                    vec![
                        ("speed", trait_value::SPEED_120),
                        ("camo", trait_value::CAMO_GOOD)
                    ]
                ),
                (
                    player::CURRENT,
                    vec![("damage_resistance", trait_value::RESISTANCE_200)]
                ),
            ]
        );
        // Scored as Juggernaut.
        let scored = |v: &Variant| raised(v, incident::BALL_TAKEN).len();
        assert_eq!(scored(&v), scored(&Variant::juggernaut(15)));
    }

    /// A set runs every tick, gated on someone holding the slot or on not
    /// being the one who does.
    #[test]
    fn traits_are_applied_each_tick_from_normal_triggers() {
        for v in [Variant::stalker(10), Variant::reverse_tag(120, 60)] {
            for (i, a) in v.actions.iter().enumerate() {
                if !matches!(a, Action::ApplyPlayerTraits { .. }) {
                    continue;
                }
                let t = trigger_of(&v, i);
                assert_eq!(t.attribute, ATTR_NORMAL);
                assert_eq!(t.condition_count, 1);
                let c = &v.conditions[t.first_condition as usize];
                assert!(matches!(
                    c.kind,
                    ConditionKind::Compare {
                        a: Var::Player(_),
                        b: Var::Player(_),
                        op: Compare::NotEqual,
                    }
                ));
            }
        }
    }

    #[test]
    fn reverse_tag_pays_time_not_kills() {
        let v = Variant::reverse_tag(120, 60);
        assert_eq!(
            applied(&v),
            [(player::global(0), vec![("speed", trait_value::SPEED_75)])]
        );
        let it = player::global(0);
        let paid: Vec<&Action> = v
            .actions
            .iter()
            .filter(|a| matches!(a, Action::ModifyScore { .. }))
            .collect();
        assert_eq!(paid.len(), 1, "one payment, and no kill scores");
        assert!(matches!(
            paid[0],
            Action::ModifyScore {
                target: ScoreTarget::Player(Player(p)),
                ..
            } if *p == it
        ));
        let snapshots = raised(&v, incident::BALL_TAKEN);
        assert_eq!(snapshots.len(), 1);
        assert!(matches!(
            snapshots[0],
            Action::SendIncident {
                value: Some(Number::PlayerScore(p)),
                ..
            } if *p == it
        ));
        assert!(v.conditions.iter().any(|c| matches!(
            &c.kind,
            ConditionKind::Compare {
                a: Var::Number(Number::GlobalNumber(3)),
                b: Var::Number(Number::Constant(60)),
                op: Compare::GreaterOrEqual,
            }
        )));
    }

    /// The slot passes the same way, so the HUD's beacon reads the same
    /// incidents.
    #[test]
    fn reverse_tag_names_who_is_it_as_juggernaut_does() {
        let count = |v: &Variant| raised(v, incident::NEW_JUGGERNAUT).len();
        assert_eq!(
            count(&Variant::reverse_tag(120, 60)),
            count(&Variant::juggernaut(15))
        );
    }

    #[test]
    fn a_new_it_starts_a_fresh_second() {
        let v = Variant::reverse_tag(120, 60);
        let (i, _) = v
            .actions
            .iter()
            .enumerate()
            .find(|(_, a)| {
                matches!(
                    a,
                    Action::SendIncident {
                        cause: Subject::Player(Player(p)),
                        ..
                    } if *p == player::global(1)
                )
            })
            .unwrap();
        assert_eq!(
            v.actions[i - 1],
            Action::ModifyVariable {
                a: number(3),
                b: constant(0),
                op: Op::Set
            }
        );
    }

    #[test]
    fn trait_test_is_slayer_with_every_trait_to_measure() {
        let v = Variant::trait_test(25);
        crate::variant::tests::check_ranges(&v);
        assert_eq!(Variant::read(&v.write().unwrap()).unwrap(), v);
        assert_eq!(
            applied(&v),
            [(
                player::CURRENT,
                vec![
                    ("damage", trait_value::DAMAGE_150),
                    ("melee_damage", trait_value::DAMAGE_150),
                    ("speed", trait_value::SPEED_150),
                    ("camo", trait_value::CAMO_GOOD)
                ]
            )]
        );
        let slayer = Variant::slayer(25);
        assert_eq!(v.actions[..slayer.actions.len()], slayer.actions[..]);
    }

    /// A set on the base traits' zeros would hand out weapon 0.
    #[test]
    fn script_traits_leave_weapons_and_abilities_alone() {
        for (name, v) in timed_variants() {
            for s in v.script_traits {
                let unchanged = crate::variant::SIGNED_UNCHANGED;
                assert_eq!(s.traits.values[12], unchanged, "{name} primary");
                assert_eq!(s.traits.values[13], unchanged, "{name} secondary");
                assert_eq!(s.traits.values[21], unchanged, "{name} ability");
            }
        }
    }

    #[test]
    fn icons_are_the_grammars() {
        let icons = |v: &Variant| -> Vec<u8> {
            v.actions
                .iter()
                .filter_map(|a| match a {
                    Action::SetWaypointIcon { icon, .. } => Some(*icon),
                    _ => None,
                })
                .collect()
        };
        assert_eq!(icons(&Variant::oddball(120, 18, 60, 1800)), [7]);
        assert_eq!(icons(&Variant::koth(120, 60)), [8]);
    }
}
