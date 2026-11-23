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

/// The rules revision published in slot 2. 20570 moved the warmup countdown
/// into slot 3 (see `CLOCK`). The map's own layout protocol stays 20569.
pub const MAGIC: i16 = 20570;
pub const PHASE: u8 = 0;
pub const PHASE_TICKS: u8 = 1;
pub const MAGIC_SLOT: u8 = 2;
pub const ACTIVE_SECONDS: u8 = 3;
/// Slot 3 is the match clock, by phase: warmup seconds left (`WAITING` until
/// the minimum players are connected), the insertion duration, then combat
/// seconds elapsed.
pub const CLOCK: u8 = ACTIVE_SECONDS;
pub const DEPLOYMENT_SECONDS: u8 = ACTIVE_SECONDS;
pub const WARMUP_LEFT: u8 = ACTIVE_SECONDS;
/// Slot 3 in warmup while fewer than the minimum players are connected.
pub const WAITING: i16 = -1;
pub const PLAYER_COUNT: u8 = 4;
pub const HEALTH: u8 = 5;
pub const SUBSECOND: u8 = 6;
pub const RED_SCORE: u8 = 7;
pub const BLUE_SCORE: u8 = 8;
pub const FIRST_OWNER: u8 = 9;
pub const HILL_LABEL: &str = "koth_hill";
/// Moving zones: each site may have several candidate markers. A marker's
/// spawn sequence is `site + SITES * candidate`, so the classic 0, 1, 2 are
/// candidate 0 and a map with one marker per site plays as before. The host
/// picks one candidate per site when insertion launches and deletes the rest.
pub const SITES: i16 = 3;
pub const MAX_CANDIDATES: i16 = 6;
/// A site's published value adds `CANDIDATE_STRIDE * candidate` (see SiteState).
pub const CANDIDATE_STRIDE: i32 = 1024;
/// Global objects 2..4 hold each site's chosen marker; object number 5 is a
/// marker's random draw.
const CHOSEN: u8 = 2;
const DRAW: u8 = 5;
/// A site marker's object number 6: how many Covenant (AI) stand in its zone.
/// The host's lobby DLL writes it (`warfare_contest` in
/// native/lobby/warfare_runtime.h); these rules only read it. While it is
/// above zero the site is contested: no capture progress and no payout. With
/// no writer it stays 0 and the rules play as before.
pub const COVENANT: u8 = 6;
/// A site marker's object number 7: the Covenant's capture progress, 0 up to
/// the Covenant capture time in ticks. Covenant alone in a zone first drain a
/// team's progress (number 1) to neutral, then fill this; at full the site's
/// owner is `OWNER_COVENANT`. Players alone in it drain this back to 0 before
/// their own progress moves. Numbers 1 and 7 are never both non-zero.
pub const COVENANT_PROGRESS: u8 = 7;
/// Owner value of a site the Covenant hold. It pays nobody.
pub const OWNER_COVENANT: i32 = 3;
/// Added to a site's published value while Covenant stand in its zone. Above
/// the candidate bits: decode with `SiteState`, never `value / CANDIDATE_STRIDE`.
pub const COVENANT_PRESENT: i32 = 8192;
/// Capture progress is published in this many steps toward either team.
pub const PROGRESS_STEPS: i16 = 16;
/// Published progress field values from here up are the Covenant's progress.
const COVENANT_STEP_BASE: i32 = 2 * PROGRESS_STEPS as i32 + 2;

/// A site's public slot (FIRST_OWNER + site) packs its whole state for the HUD:
/// `owner + 4 * (red_present + 2 * blue_present) + 16 * k
/// + CANDIDATE_STRIDE * candidate + COVENANT_PRESENT * covenant_present`,
/// owner 0 neutral / 1 red / 2 blue / 3 Covenant. `k` is `progress + PROGRESS_STEPS + 1`
/// for the teams' progress in steps toward red (positive) or blue (negative), or
/// `COVENANT_STEP_BASE + steps` while the Covenant's progress is above zero. Coarse steps
/// keep the replicated value from changing every tick. A value below 16 carries no
/// progress (an older variant, or before combat): the owner is still its low two bits.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SiteState {
    /// Which of the site's candidate markers this match uses (0 on a map with one).
    pub candidate: i32,
    pub owner: i32,
    pub red_present: bool,
    pub blue_present: bool,
    pub progress: Option<i32>,
    /// Covenant stand in the zone.
    pub covenant_present: bool,
    /// The Covenant's progress in steps of PROGRESS_STEPS (0 when the teams' progress is in use).
    pub covenant_progress: i32,
}

impl SiteState {
    pub fn decode(value: i32) -> Self {
        let covenant_present = value >= COVENANT_PRESENT;
        let value = value % COVENANT_PRESENT;
        let candidate = value / CANDIDATE_STRIDE;
        let value = value % CANDIDATE_STRIDE;
        let k = value >> 4;
        let covenant = k >= COVENANT_STEP_BASE;
        Self {
            candidate,
            owner: value & 3,
            red_present: value & 4 != 0,
            blue_present: value & 8 != 0,
            progress: if covenant { Some(0) } else { (k > 0).then(|| k - i32::from(PROGRESS_STEPS) - 1) },
            covenant_present,
            covenant_progress: if covenant { k - COVENANT_STEP_BASE } else { 0 },
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct Warfare {
    pub score_to_win: u16,
    pub tick_rate: u16,
    pub minimum_players: u8,
    pub warmup_seconds: u16,
    pub insertion_seconds: u16,
    pub capture_seconds: u16,
    /// Seconds for Covenant alone to take a neutral site (a team's site drains
    /// to neutral first, at the teams' rate).
    pub covenant_capture_seconds: u16,
    pub allow_mounted_capture: bool,
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
            capture_seconds: 15,
            covenant_capture_seconds: 30,
            allow_mounted_capture: false,
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

fn add_var(a: Var, b: Var) -> Item {
    Item::Do(Action::ModifyVariable { a, b, op: Op::Add })
}

fn seq() -> Var {
    Var::Number(Number::SpawnSequence(object::CURRENT))
}

fn chosen(site: i16) -> Var {
    obj(object::global(CHOSEN + site as u8))
}

fn draw(of: u8) -> Var {
    Var::Number(Number::ObjectNumber { object: of, index: DRAW })
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
            || c.covenant_capture_seconds == 0
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
        ticks(c.warmup_seconds)?;
        let warmup = c.warmup_seconds as i16;
        let insertion = ticks(c.insertion_seconds)?;
        let capture = ticks(c.capture_seconds)?;
        let covenant_capture = ticks(c.covenant_capture_seconds)?;
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
                global_objects: 5,
                object_numbers: 8,
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
                eq(number(PHASE), constant(0)),
                set(number(CLOCK), constant(WAITING)),
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
                set(number(SUBSECOND), constant(0)),
                set(number(CLOCK), constant(WAITING)),
            ],
        );
        // Warmup counts down whole seconds in the replicated clock slot, so
        // every client can show the same countdown without knowing its length.
        let start_countdown = b.sub(
            TriggerKind::Do,
            vec![
                compare(number(CLOCK), constant(0), Compare::Less),
                set(number(CLOCK), constant(warmup)),
                set(number(SUBSECOND), constant(0)),
            ],
        );
        let count_second = b.sub(
            TriggerKind::Do,
            vec![
                compare(number(SUBSECOND), constant(c.tick_rate as i16), Compare::GreaterOrEqual),
                set(number(SUBSECOND), constant(0)),
                modify(number(CLOCK), 1, Op::Subtract),
            ],
        );
        // The host's random numbers come from one LCG whose seed may repeat
        // from launch to launch, so warmup draws one every tick: how long the
        // warmup lasted scrambles the pick. Slot 5 is scratch outside combat.
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![
                eq(number(PHASE), constant(0)),
                Item::Do(Action::RandomNumber { cap: Number::Constant(1000), out: Number::GlobalNumber(HEALTH) }),
            ],
        );
        // Choose: every candidate draws a number; per site the highest wins.
        let mut choose = vec![Item::Do(Action::RandomNumber {
            cap: Number::Constant(1000),
            out: Number::ObjectNumber { object: object::CURRENT, index: DRAW },
        })];
        for j in 0..SITES * MAX_CANDIDATES {
            let site = j % SITES;
            let first = b.sub(
                TriggerKind::Do,
                vec![eq(chosen(site), obj(object::NONE)), set(chosen(site), obj(object::CURRENT))],
            );
            let better = b.sub(
                TriggerKind::Do,
                vec![
                    compare(draw(object::CURRENT), draw(object::global(CHOSEN + site as u8)), Compare::Greater),
                    set(chosen(site), obj(object::CURRENT)),
                ],
            );
            let consider = b.sub(TriggerKind::Do, vec![eq(seq(), constant(j)), call(first), call(better)]);
            choose.push(call(consider));
        }
        let choose = b.sub(TriggerKind::EachObjectWithLabel(label), choose);
        // The flank sites move together: the last site takes the first site's
        // candidate index when it has one, so a map whose third site mirrors
        // its first (PWR's C mirrors A across the bases' midline) stays fair in
        // every draw. Without a matching candidate its own draw stands.
        let last = SITES - 1;
        let mut follow = Vec::new();
        for k in 0..MAX_CANDIDATES {
            let take = b.sub(
                TriggerKind::Do,
                vec![
                    eq(seq(), constant(last + SITES * k)),
                    eq(Var::Number(Number::SpawnSequence(object::global(CHOSEN))), constant(SITES * k)),
                    set(chosen(last), obj(object::CURRENT)),
                ],
            );
            follow.push(call(take));
        }
        let follow = b.sub(TriggerKind::EachObjectWithLabel(label), follow);
        let launch = b.sub(
            TriggerKind::Do,
            vec![
                compare(number(CLOCK), constant(0), Compare::LessOrEqual),
                set(chosen(0), obj(object::NONE)),
                set(chosen(1), obj(object::NONE)),
                set(chosen(2), obj(object::NONE)),
                call(choose),
                call(follow),
                set(number(PHASE), constant(1)),
                set(number(PHASE_TICKS), constant(0)),
                set(number(SUBSECOND), constant(0)),
                set(number(DEPLOYMENT_SECONDS), constant(c.insertion_seconds as i16)),
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
                call(start_countdown),
                modify(number(PHASE_TICKS), 1, Op::Add),
                modify(number(SUBSECOND), 1, Op::Add),
                call(count_second),
                call(launch),
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
                set(number(SUBSECOND), constant(0)),
                set(number(ACTIVE_SECONDS), constant(0)),
            ],
        );

        // A fixed bounded scan: at most three markers times sixteen players.
        // Occupants count once per team, so stacking players does not speed capture.
        let mut scan = alive(player::CURRENT, HEALTH);
        if !c.allow_mounted_capture {
            scan.extend([
                Item::Do(Action::GetPlayerVehicle {
                    player: Player(player::CURRENT),
                    out: Object::Ref(object::global(1)),
                }),
                eq(obj(object::global(1)), obj(object::NONE)),
            ]);
        }
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
                    eq(hill_number(COVENANT), constant(0)),
                    eq(hill_number(COVENANT_PROGRESS), constant(0)),
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
            // Players alone on a site the Covenant hold, or are taking, push
            // the Covenant's progress back to nothing before their own moves.
            let clear = b.sub(
                TriggerKind::Do,
                vec![
                    eq(hill_number(2 + side), constant(1)),
                    eq(hill_number(3 - side), constant(0)),
                    eq(hill_number(COVENANT), constant(0)),
                    compare(hill_number(COVENANT_PROGRESS), constant(0), Compare::Greater),
                    modify(hill_number(COVENANT_PROGRESS), 1, Op::Subtract),
                ],
            );
            // Neither side's progress: neutral. Not while the Covenant's runs,
            // or a Covenant site would be released every tick.
            let neutralize = b.sub(
                TriggerKind::Do,
                vec![
                    eq(hill_number(1), constant(0)),
                    eq(hill_number(COVENANT_PROGRESS), constant(0)),
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
            // payout immediately, including while ownership is being
            // neutralized, and so do Covenant.
            let pay = b.sub(
                TriggerKind::Do,
                vec![
                    eq(number(SUBSECOND), constant(c.tick_rate as i16)),
                    eq(hill_number(0), constant(i16::from(side + 1))),
                    eq(hill_number(3 - side), constant(0)),
                    eq(hill_number(COVENANT), constant(0)),
                    Item::Do(Action::ModifyScore {
                        target: ScoreTarget::Team(Team::Ref(side as i8)),
                        op: Op::Add,
                        value: Number::Constant(1),
                    }),
                ],
            );
            update.extend([call(clear), call(advance), call(neutralize), call(captured), call(pay)]);
        }
        // The Covenant alone in a zone (number 6 above zero, no player): a
        // team's progress drains toward neutral at the teams' rate, then the
        // Covenant's own progress fills; full, they own it. A Covenant site
        // pays nobody (pay above wants owner 1 or 2).
        let covenant_alone = || {
            vec![
                compare(hill_number(COVENANT), constant(0), Compare::Greater),
                eq(hill_number(2), constant(0)),
                eq(hill_number(3), constant(0)),
            ]
        };
        for (comparison, op) in [(Compare::Greater, Op::Subtract), (Compare::Less, Op::Add)] {
            let mut drain = covenant_alone();
            drain.extend([compare(hill_number(1), constant(0), comparison), modify(hill_number(1), 1, op)]);
            let drain = b.sub(TriggerKind::Do, drain);
            update.push(call(drain));
        }
        let mut take = covenant_alone();
        // Only once the site is neutral: a drained team site is released by
        // `neutralize` first (the next tick), or it would stay theirs.
        take.extend([
            eq(hill_number(0), constant(0)),
            eq(hill_number(1), constant(0)),
            compare(hill_number(COVENANT_PROGRESS), constant(covenant_capture), Compare::Less),
            modify(hill_number(COVENANT_PROGRESS), 1, Op::Add),
        ]);
        let take = b.sub(TriggerKind::Do, take);
        let held = b.sub(
            TriggerKind::Do,
            vec![
                eq(hill_number(COVENANT_PROGRESS), constant(covenant_capture)),
                set(hill_number(0), constant(OWNER_COVENANT as i16)),
            ],
        );
        let lost = b.sub(
            TriggerKind::Do,
            vec![
                eq(hill_number(0), constant(OWNER_COVENANT as i16)),
                compare(hill_number(COVENANT_PROGRESS), constant(covenant_capture), Compare::Less),
                set(hill_number(0), constant(0)),
            ],
        );
        update.extend([call(take), call(held), call(lost)]);
        // Pack the site's state into object number 4 (see SiteState). Progress is
        // counted in steps against thresholds fixed when the variant is built, so the
        // HUD needs no capture duration and the VM needs no division.
        update.push(set(hill_number(4), constant(0)));
        for step in 1..=PROGRESS_STEPS {
            let threshold = ((i32::from(step) * i32::from(capture) + i32::from(PROGRESS_STEPS) - 1)
                / i32::from(PROGRESS_STEPS)).max(1) as i16;
            for (bound, comparison, op) in [
                (threshold, Compare::GreaterOrEqual, Op::Add),
                (-threshold, Compare::LessOrEqual, Op::Subtract),
            ] {
                let count = b.sub(
                    TriggerKind::Do,
                    vec![compare(hill_number(1), constant(bound), comparison), modify(hill_number(4), 1, op)],
                );
                update.push(call(count));
            }
        }
        // The Covenant's progress (only ever non-zero while the teams' is 0)
        // moves the field to COVENANT_STEP_BASE + steps.
        let base = b.sub(
            TriggerKind::Do,
            vec![
                compare(hill_number(COVENANT_PROGRESS), constant(0), Compare::Greater),
                modify(hill_number(4), PROGRESS_STEPS + 1, Op::Add),
            ],
        );
        update.push(call(base));
        for step in 1..=PROGRESS_STEPS {
            let threshold = ((i32::from(step) * i32::from(covenant_capture) + i32::from(PROGRESS_STEPS) - 1)
                / i32::from(PROGRESS_STEPS)).max(1) as i16;
            let count = b.sub(
                TriggerKind::Do,
                vec![
                    compare(hill_number(COVENANT_PROGRESS), constant(threshold), Compare::GreaterOrEqual),
                    modify(hill_number(4), 1, Op::Add),
                ],
            );
            update.push(call(count));
        }
        update.push(modify(hill_number(4), PROGRESS_STEPS + 1, Op::Add));
        for _ in 0..4 {
            update.push(add_var(hill_number(4), hill_number(4)));
        }
        for side in 0..2u8 {
            let present = b.sub(
                TriggerKind::Do,
                vec![
                    eq(hill_number(2 + side), constant(1)),
                    modify(hill_number(4), 4 << side, Op::Add),
                ],
            );
            update.push(call(present));
        }
        update.push(add_var(hill_number(4), hill_number(0)));
        for j in SITES..SITES * MAX_CANDIDATES {
            let candidate = b.sub(
                TriggerKind::Do,
                vec![eq(seq(), constant(j)), modify(hill_number(4), (CANDIDATE_STRIDE * i32::from(j / SITES)) as i16, Op::Add)],
            );
            update.push(call(candidate));
        }
        let present = b.sub(
            TriggerKind::Do,
            vec![
                compare(hill_number(COVENANT), constant(0), Compare::Greater),
                modify(hill_number(4), COVENANT_PRESENT as i16, Op::Add),
            ],
        );
        update.push(call(present));
        for site in 0..SITES {
            let publish = b.sub(
                TriggerKind::Do,
                vec![
                    eq(obj(object::CURRENT), chosen(site)),
                    set(number(FIRST_OWNER + site as u8), hill_number(4)),
                ],
            );
            update.push(call(publish));
        }
        let site_update = b.sub(TriggerKind::Do, update);
        let mut hills = vec![eq(number(PHASE), constant(2))];
        for site in 0..SITES {
            let gate = b.sub(TriggerKind::Do, vec![eq(obj(object::CURRENT), chosen(site)), call(site_update)]);
            hills.push(call(gate));
        }
        // Insertion: publish the chosen candidates (owner neutral, no progress)
        // so the HUD and tactical map show where to steer the parachute.
        let mut announce = vec![eq(number(PHASE), constant(1))];
        // From insertion on, the unchosen candidates go (a later tick than the pick).
        let mut prune = vec![compare(number(PHASE), constant(1), Compare::GreaterOrEqual)];
        for j in 0..SITES * MAX_CANDIDATES {
            let site = j % SITES;
            let tell = b.sub(
                TriggerKind::Do,
                vec![
                    eq(seq(), constant(j)),
                    eq(obj(object::CURRENT), chosen(site)),
                    set(number(FIRST_OWNER + site as u8), constant((CANDIDATE_STRIDE * i32::from(j / SITES)) as i16)),
                ],
            );
            announce.push(call(tell));
            let drop = b.sub(
                TriggerKind::Do,
                vec![
                    eq(seq(), constant(j)),
                    compare(obj(object::CURRENT), chosen(site), Compare::NotEqual),
                    Item::Do(Action::DeleteObject(Object::Ref(object::CURRENT))),
                ],
            );
            prune.push(call(drop));
        }
        b.trigger(
            TriggerKind::Do,
            ATTR_NORMAL,
            vec![
                eq(number(PHASE), constant(2)),
                modify(number(SUBSECOND), 1, Op::Add),
            ],
        );
        b.trigger(TriggerKind::EachObjectWithLabel(label), ATTR_NORMAL, hills);
        b.trigger(TriggerKind::EachObjectWithLabel(label), ATTR_NORMAL, announce);
        b.trigger(TriggerKind::EachObjectWithLabel(label), ATTR_NORMAL, prune);
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
    fn site_state_decodes_packed_and_plain_owner_values() {
        let plain = SiteState { candidate: 0, owner: 2, red_present: false, blue_present: false, progress: None,
                                covenant_present: false, covenant_progress: 0 };
        assert_eq!(SiteState::decode(2), plain);
        let packed = 1 + 4 * 3 + 16 * (5 + PROGRESS_STEPS as i32 + 1);
        assert_eq!(SiteState::decode(packed), SiteState { owner: 1, red_present: true, blue_present: true, progress: Some(5), ..plain });
        let moved = packed + 5 * CANDIDATE_STRIDE;
        assert_eq!(SiteState::decode(moved), SiteState { candidate: 5, ..SiteState::decode(packed) },
            "the chosen candidate rides above the state and leaves it intact");
        let blue = 16 * (-(PROGRESS_STEPS as i32) + PROGRESS_STEPS as i32 + 1) + 2;
        assert_eq!(SiteState::decode(blue).progress, Some(-(PROGRESS_STEPS as i32)));
        // Held by the Covenant, Covenant in it, candidate 2, Covenant progress full.
        let covenant = OWNER_COVENANT + 16 * (COVENANT_STEP_BASE + PROGRESS_STEPS as i32) + 2 * CANDIDATE_STRIDE + COVENANT_PRESENT;
        assert_eq!(SiteState::decode(covenant), SiteState { candidate: 2, owner: 3, progress: Some(0), covenant_present: true,
                                                             covenant_progress: PROGRESS_STEPS as i32, ..plain });
        // Being taken by the Covenant, none left in it: no flag, partial progress.
        let taking = 16 * (COVENANT_STEP_BASE + 3);
        assert_eq!(SiteState::decode(taking), SiteState { owner: 0, progress: Some(0), covenant_progress: 3, ..plain });
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
            Warfare {
                covenant_capture_seconds: 0,
                ..Warfare::default()
            },
        ] {
            assert!(Variant::warfare(c).is_err());
        }
    }
}
