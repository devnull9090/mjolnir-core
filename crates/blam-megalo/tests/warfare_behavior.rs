//! Execute the generated rule program against a small deterministic world.
//! These are behavioral checks of trigger ordering and contested capture,
//! independent of the Rust builder's particular trigger indices.
use blam_megalo::variant::*;
use blam_megalo::warfare::*;

struct World {
    globals: [i32; 12],
    /// Each marker's object numbers, spawn sequence and whether it still exists.
    points: Vec<[i32; 8]>,
    seqs: Vec<i32>,
    alive: Vec<bool>,
    /// Global objects 2..4: each site's chosen marker (-1 none).
    chosen: [i32; 3],
    rng: u32,
    score: [i32; 2],
    connected: [bool; 2],
    alive_player: [bool; 2],
    seated: [bool; 2],
    at: [Option<usize>; 2],
    current_player: usize,
    current_object: usize,
    saved_object: i32,
    vehicle: i32,
    ended: bool,
}

impl World {
    fn new() -> Self {
        Self {
            globals: [0; 12],
            points: vec![[0; 8]; 3],
            seqs: vec![0, 1, 2],
            alive: vec![true; 3],
            // A classic map: one marker per site, already chosen.
            chosen: [0, 1, 2],
            rng: 12345,
            score: [0; 2],
            connected: [true; 2],
            alive_player: [true; 2],
            seated: [false; 2],
            at: [None; 2],
            current_player: 0,
            current_object: 0,
            saved_object: -1,
            vehicle: -1,
            ended: false,
        }
    }
    /// A map with these marker spawn sequences, nothing chosen yet.
    fn with_markers(seqs: &[i32]) -> Self {
        let mut w = World::new();
        w.points = vec![[0; 8]; seqs.len()];
        w.seqs = seqs.to_vec();
        w.alive = vec![true; seqs.len()];
        w.chosen = [-1; 3];
        w
    }
    fn object(&self, o: Object) -> i32 {
        match o {
            Object::Ref(object::NONE) => -1,
            Object::Ref(object::CURRENT) => self.current_object as i32,
            Object::Ref(1) => self.saved_object,
            Object::Ref(2) => self.vehicle,
            Object::Ref(k @ 3..=5) => self.chosen[(k - 3) as usize],
            Object::PlayerBiped(player::CURRENT) => 100 + self.current_player as i32,
            _ => panic!("unsupported test object {o:?}"),
        }
    }
    fn value(&self, v: &Var, variant: &Variant) -> i32 {
        match v {
            Var::Number(Number::Constant(x)) => i32::from(*x),
            Var::Number(Number::GlobalNumber(i)) => self.globals[*i as usize],
            Var::Number(Number::ObjectNumber { object, index }) => {
                self.points[self.object(Object::Ref(*object)) as usize][*index as usize]
            }
            Var::Number(Number::SpawnSequence(o)) => self.seqs[self.object(Object::Ref(*o)) as usize],
            Var::Number(Number::TeamScore(i)) => self.score[*i as usize],
            Var::Number(Number::ScoreToWin) => i32::from(variant.score_to_win),
            Var::Object(o) => self.object(*o),
            Var::Team(Team::PlayerOwner(_)) => self.current_player as i32,
            Var::Team(Team::Ref(t)) => i32::from(*t),
            _ => panic!("unsupported test value {v:?}"),
        }
    }
    fn condition(&self, c: &ConditionKind, v: &Variant) -> bool {
        match c {
            ConditionKind::Compare { a, b, op } => {
                let (a, b) = (self.value(a, v), self.value(b, v));
                match op {
                    Compare::Equal => a == b,
                    Compare::NotEqual => a != b,
                    Compare::Less => a < b,
                    Compare::LessOrEqual => a <= b,
                    Compare::Greater => a > b,
                    Compare::GreaterOrEqual => a >= b,
                }
            }
            ConditionKind::InBoundary { shape, .. } => {
                self.at[self.current_player] == Some(self.object(*shape) as usize)
            }
            _ => panic!("unsupported test condition {c:?}"),
        }
    }
    fn set(&mut self, a: &Var, x: i32) {
        match a {
            Var::Number(Number::GlobalNumber(i)) => self.globals[*i as usize] = x,
            Var::Number(Number::ObjectNumber { object, index }) => {
                let at = self.object(Object::Ref(*object)) as usize;
                self.points[at][*index as usize] = x
            }
            Var::Object(Object::Ref(1)) => self.saved_object = x,
            Var::Object(Object::Ref(k @ 3..=5)) => self.chosen[(*k - 3) as usize] = x,
            _ => panic!("unsupported test assignment {a:?}"),
        }
    }
    fn action(&mut self, a: &Action, v: &Variant) {
        let arithmetic = |old, x, op| match op {
            Op::Set => x,
            Op::Add => old + x,
            Op::Subtract => old - x,
        };
        match a {
            Action::ModifyVariable { a, b, op } => {
                let x = arithmetic(self.value(a, v), self.value(b, v), *op);
                self.set(a, x);
            }
            Action::GetHealth { out, .. } => self.set(
                &Var::Number(out.clone()),
                if self.alive_player[self.current_player] {
                    100
                } else {
                    0
                },
            ),
            Action::GetPlayerVehicle { .. } => {
                self.vehicle = if self.seated[self.current_player] {
                    200
                } else {
                    -1
                }
            }
            Action::CallTrigger(i) => self.trigger(*i as usize, v),
            Action::ModifyScore {
                target: ScoreTarget::Team(Team::Ref(t)),
                op,
                value,
            } => {
                self.score[*t as usize] = arithmetic(
                    self.score[*t as usize],
                    self.value(&Var::Number(value.clone()), v),
                    *op,
                );
            }
            Action::ApplyPlayerTraits { .. } => (),
            Action::RandomNumber { cap, out } => {
                self.rng = self.rng.wrapping_mul(0x19660d).wrapping_add(0x3c6ef35f);
                let cap = self.value(&Var::Number(cap.clone()), v);
                let x = (((self.rng >> 16) as i32) * cap) >> 16;
                self.set(&Var::Number(out.clone()), x);
            }
            Action::DeleteObject(Object::Ref(object::CURRENT)) => self.alive[self.current_object] = false,
            Action::EndRound => self.ended = true,
            _ => panic!("unsupported test action {a:?}"),
        }
    }
    fn body(&mut self, t: &Trigger, v: &Variant) {
        let conditions = &v.conditions
            [t.first_condition as usize..(t.first_condition + t.condition_count) as usize];
        for offset in 0..=t.action_count {
            for c in conditions.iter().filter(|c| c.action_offset == offset) {
                assert!(!c.negate);
                if !self.condition(&c.kind, v) {
                    return;
                }
            }
            if offset < t.action_count {
                self.action(&v.actions[(t.first_action + offset) as usize], v);
            }
        }
    }
    fn trigger(&mut self, i: usize, v: &Variant) {
        let t = &v.triggers[i];
        let saved = (self.current_player, self.current_object);
        match t.kind {
            TriggerKind::Do => self.body(t, v),
            TriggerKind::EachPlayer => {
                for p in 0..2 {
                    if self.connected[p] {
                        self.current_player = p;
                        self.body(t, v);
                    }
                }
            }
            TriggerKind::EachObjectWithLabel(_) => {
                for p in 0..self.seqs.len() {
                    if self.alive[p] {
                        self.current_object = p;
                        self.body(t, v);
                    }
                }
            }
            _ => panic!("unsupported test trigger"),
        }
        (self.current_player, self.current_object) = saved;
    }
    fn ticks(&mut self, n: usize, v: &Variant) {
        for _ in 0..n {
            if self.ended {
                return;
            }
            for (i, t) in v.triggers.iter().enumerate() {
                if t.attribute == ATTR_NORMAL {
                    self.trigger(i, v);
                }
            }
        }
    }
}

fn variant() -> Variant {
    Variant::warfare(Warfare {
        tick_rate: 10,
        warmup_seconds: 1,
        insertion_seconds: 1,
        capture_seconds: 1,
        score_to_win: 500,
        match_minutes: 1,
        ..Warfare::default()
    })
    .unwrap()
}

#[test]
fn absent_team_score_is_published_as_zero_without_changing_engine_score() {
    let v = variant();
    let mut w = World::new();
    w.connected[1] = false;
    w.score = [7, -1];
    w.ticks(1, &v);
    assert_eq!(w.globals[RED_SCORE as usize], 7);
    assert_eq!(w.globals[BLUE_SCORE as usize], 0);
    assert_eq!(w.score, [7, -1], "presentation must not create a team score");
    assert!(!w.ended, "an absent team is not a victory");

    w.globals[PHASE as usize] = 2;
    w.connected = [false, true];
    w.score = [-1, 11];
    w.ticks(1, &v);
    assert_eq!(w.globals[RED_SCORE as usize], 0);
    assert_eq!(w.globals[BLUE_SCORE as usize], 11);
    assert_eq!(w.score, [-1, 11]);

    w.connected = [true, true];
    w.score = [3, 12];
    w.ticks(1, &v);
    assert_eq!(w.globals[RED_SCORE as usize], 3);
    assert_eq!(w.globals[BLUE_SCORE as usize], 12);
}

#[test]
fn deployment_waits_for_players_then_enables_control_and_respawns() {
    let v = variant();
    let mut w = World::new();
    w.connected[1] = false;
    w.at[0] = Some(0);
    w.ticks(100, &v);
    assert_eq!(w.globals[PHASE as usize], 0);
    assert_eq!(w.globals[CLOCK as usize], i32::from(WAITING), "the clock says it is waiting for players");
    assert_eq!(w.score, [0, 0]);
    w.connected[1] = true;
    w.ticks(10, &v);
    assert_eq!(w.globals[PHASE as usize], 1);
    assert_eq!(w.globals[DEPLOYMENT_SECONDS as usize], 1);
    assert_eq!(w.points[0][0], 0);
    w.ticks(9, &v);
    assert_eq!(w.globals[PHASE as usize], 2);
    assert_eq!(w.globals[ACTIVE_SECONDS as usize], 0, "combat clock must not inherit deployment duration");
    w.ticks(9, &v);
    assert_eq!(w.points[0][0], 1);
    assert_eq!(SiteState::decode(w.globals[FIRST_OWNER as usize]).owner, 1);
    assert_eq!(
        (v.base.lives, v.base.team_lives, v.base.respawn_seconds),
        (0, 0, 5)
    );
}

#[test]
fn contest_blocks_capture_and_score_but_empty_owned_sites_keep_scoring() {
    let v = variant();
    let mut w = World::new();
    w.globals[PHASE as usize] = 2;
    w.at[0] = Some(0);
    w.ticks(10, &v);
    assert_eq!(w.score, [1, 0]);
    w.at[1] = Some(0);
    w.ticks(30, &v);
    assert_eq!(w.points[0][1], 10);
    assert_eq!(w.score, [1, 0]);
    w.at = [None, None];
    w.ticks(10, &v);
    assert_eq!(w.score, [2, 0]);
    w.at[1] = Some(0);
    w.ticks(10, &v);
    assert_eq!(w.points[0][0], 0, "enemy first neutralizes");
    w.ticks(10, &v);
    assert_eq!(w.points[0][0], 2, "then captures");
    assert_eq!(w.score, [2, 1]);
}

#[test]
fn mounted_capture_variant_counts_a_living_driver() {
    let rules = Variant::warfare(Warfare {
        allow_mounted_capture: true,
        tick_rate: 10,
        capture_seconds: 1,
        ..Warfare::default()
    }).unwrap();
    let mut world = World::new();
    world.globals[PHASE as usize] = 2;
    world.at[0] = Some(1);
    world.seated[0] = true;
    world.alive_player[0] = false;
    world.ticks(10, &rules);
    assert_eq!(world.points[1][0], 0);
    world.alive_player[0] = true;
    world.ticks(10, &rules);
    assert_eq!(world.points[1][0], 1);
}

#[test]
fn dead_players_cannot_capture_and_score_or_clock_ends_the_round() {
    let mut v = variant();
    let mut w = World::new();
    w.globals[PHASE as usize] = 2;
    w.at[0] = Some(1);
    w.alive_player[0] = false;
    w.ticks(20, &v);
    assert_eq!(w.points[1][1], 0);
    w.alive_player[0] = true;
    w.seated[0] = true;
    w.ticks(20, &v);
    assert_eq!(
        w.points[1][1], 0,
        "vehicle occupants must dismount to capture"
    );
    w.seated[0] = false;
    v.score_to_win = 2;
    w.ticks(20, &v);
    assert!(w.ended);
    assert_eq!(w.globals[PHASE as usize], 3);
    assert_eq!(w.score, [2, 0]);
    let v = variant();
    let mut w = World::new();
    w.globals[PHASE as usize] = 2;
    w.ticks(600, &v);
    assert!(w.ended);
    assert_eq!(w.globals[ACTIVE_SECONDS as usize], 60);
}

#[test]
fn published_site_state_carries_owner_presence_and_stepped_progress() {
    let v = Variant::warfare(Warfare {
        tick_rate: 10,
        capture_seconds: 4,
        ..Warfare::default()
    })
    .unwrap();
    let mut w = World::new();
    w.globals[PHASE as usize] = 2;
    w.ticks(1, &v);
    let empty = SiteState::decode(w.globals[FIRST_OWNER as usize]);
    assert_eq!(empty, SiteState { candidate: 0, owner: 0, red_present: false, blue_present: false, progress: Some(0) });
    // Red alone: progress climbs in steps toward red; full at capture.
    w.at[0] = Some(0);
    w.ticks(20, &v);
    let half = SiteState::decode(w.globals[FIRST_OWNER as usize]);
    assert!(half.red_present && !half.blue_present);
    assert_eq!(half.owner, 0);
    assert_eq!(half.progress, Some(PROGRESS_STEPS as i32 / 2), "20 of 40 ticks is half way");
    w.ticks(20, &v);
    let held = SiteState::decode(w.globals[FIRST_OWNER as usize]);
    assert_eq!((held.owner, held.progress), (1, Some(PROGRESS_STEPS as i32)));
    // Blue joins: contested, both present, progress holds.
    w.at[1] = Some(0);
    w.ticks(5, &v);
    let contested = SiteState::decode(w.globals[FIRST_OWNER as usize]);
    assert!(contested.red_present && contested.blue_present);
    assert_eq!(contested.progress, Some(PROGRESS_STEPS as i32));
    // Blue alone pushes it back through neutral toward blue.
    w.at[0] = None;
    w.ticks(60, &v);
    let blue = SiteState::decode(w.globals[FIRST_OWNER as usize]);
    assert!(blue.blue_present && !blue.red_present);
    assert!(blue.progress.unwrap() < 0 && blue.owner == 0, "{blue:?}");
    w.ticks(30, &v);
    let taken = SiteState::decode(w.globals[FIRST_OWNER as usize]);
    assert_eq!((taken.owner, taken.progress), (2, Some(-(PROGRESS_STEPS as i32))));
    // Other sites stay neutral and empty.
    assert_eq!(SiteState::decode(w.globals[FIRST_OWNER as usize + 1]).progress, Some(0));
}

#[test]
fn warmup_counts_down_whole_seconds_and_restarts_when_a_player_leaves() {
    let v = Variant::warfare(Warfare {
        tick_rate: 10,
        warmup_seconds: 3,
        insertion_seconds: 7,
        ..Warfare::default()
    })
    .unwrap();
    let mut w = World::new();
    w.connected[1] = false;
    w.ticks(5, &v);
    assert_eq!(w.globals[MAGIC_SLOT as usize], i32::from(MAGIC));
    assert_eq!(w.globals[CLOCK as usize], i32::from(WAITING));
    w.connected[1] = true;
    w.ticks(1, &v);
    assert_eq!(w.globals[CLOCK as usize], 3, "the full warmup shows as soon as the count is met");
    w.ticks(9, &v);
    assert_eq!(w.globals[CLOCK as usize], 2, "one second after ten ticks");
    w.ticks(5, &v);
    assert_eq!(w.globals[CLOCK as usize], 2);
    w.connected[1] = false;
    w.ticks(1, &v);
    assert_eq!(w.globals[CLOCK as usize], i32::from(WAITING), "a leaver stops the countdown");
    w.connected[1] = true;
    w.ticks(1, &v);
    assert_eq!(w.globals[CLOCK as usize], 3, "and it starts again from the top");
    w.ticks(29, &v);
    assert_eq!(w.globals[PHASE as usize], 1, "three seconds of warmup is thirty ticks");
    assert_eq!(w.globals[DEPLOYMENT_SECONDS as usize], 7, "insertion publishes its duration");
    w.ticks(68, &v);
    assert_eq!(w.globals[PHASE as usize], 1, "insertion's tick count starts on the launch tick");
    w.ticks(1, &v);
    assert_eq!(w.globals[PHASE as usize], 2);
    assert_eq!(w.globals[ACTIVE_SECONDS as usize], 0);
}

#[test]
fn each_site_picks_one_candidate_at_launch_and_the_rest_are_removed() {
    let v = Variant::warfare(Warfare {
        tick_rate: 10,
        warmup_seconds: 1,
        insertion_seconds: 1,
        capture_seconds: 1,
        ..Warfare::default()
    })
    .unwrap();
    // Site 0 has three candidates (0, 3, 6), site 1 two (1, 4), site 2 one (2).
    let seqs = [0, 1, 2, 3, 4, 6];
    // A mirrored map: site 2 has the same candidates as site 0 and follows it.
    for seed in 0..40u32 {
        let mut w = World::with_markers(&[0, 1, 2, 3, 5, 6, 8]);
        w.rng = seed.wrapping_mul(2654435761);
        w.ticks(10, &v);
        let (a, c) = (w.seqs[w.chosen[0] as usize], w.seqs[w.chosen[2] as usize]);
        assert_eq!(c, a + 2, "C takes A's candidate: A seq {a}, C seq {c}");
    }
    let mut picks = std::collections::BTreeSet::new();
    for seed in 0..40u32 {
        let mut w = World::with_markers(&seqs);
        w.rng = seed.wrapping_mul(2654435761);
        w.ticks(10, &v);
        assert_eq!(w.globals[PHASE as usize], 1, "launched");
        let chosen = w.chosen;
        assert!(chosen.iter().all(|&c| c >= 0), "every site has a marker: {chosen:?}");
        for (site, &c) in chosen.iter().enumerate() {
            assert_eq!(w.seqs[c as usize] % SITES as i32, site as i32, "the pick belongs to its site");
        }
        assert_eq!(w.seqs[chosen[2] as usize], 2, "a single candidate is always used");
        picks.insert(w.seqs[chosen[0] as usize]);
        // The pick is announced during insertion: candidate index, neutral, no progress.
        w.ticks(1, &v);
        for site in 0..3 {
            let state = SiteState::decode(w.globals[FIRST_OWNER as usize + site]);
            assert_eq!(state.candidate, w.seqs[chosen[site] as usize] / SITES as i32);
            assert_eq!((state.owner, state.progress), (0, None));
        }
        // Unchosen markers are gone; the chosen remain.
        for (i, alive) in w.alive.iter().enumerate() {
            assert_eq!(*alive, chosen.contains(&(i as i32)), "marker {i} seq {}", w.seqs[i]);
        }
    }
    assert!(picks.len() >= 2, "different warmups give different sites: {picks:?}");
}

#[test]
fn only_the_chosen_marker_captures_and_publishes_its_candidate() {
    let v = variant();
    // Site 0: candidates 0 and 3; marker 3 (seq 3, candidate 1) is chosen.
    let mut w = World::with_markers(&[0, 1, 2, 3]);
    w.chosen = [3, 1, 2];
    w.alive[0] = false;
    w.globals[PHASE as usize] = 2;
    w.at[0] = Some(3);
    w.ticks(10, &v);
    assert_eq!(w.points[3][0], 1, "red took the chosen marker");
    let a = SiteState::decode(w.globals[FIRST_OWNER as usize]);
    assert_eq!((a.candidate, a.owner, a.red_present), (1, 1, true));
    assert_eq!(w.score, [1, 0]);
    // Standing on the removed classic spot does nothing.
    let mut w = World::with_markers(&[0, 1, 2, 3]);
    w.chosen = [3, 1, 2];
    w.globals[PHASE as usize] = 2;
    w.at[0] = Some(0);
    w.ticks(20, &v);
    assert_eq!(w.points[0][0], 0);
    assert_eq!(SiteState::decode(w.globals[FIRST_OWNER as usize]).owner, 0);
}

#[test]
fn covenant_in_a_zone_contest_it_and_without_them_capture_runs_as_before() {
    let v = Variant::warfare(Warfare {
        tick_rate: 10,
        capture_seconds: 4,
        ..Warfare::default()
    })
    .unwrap();
    let mut w = World::new();
    w.globals[PHASE as usize] = 2;
    // No writer: number 6 stays 0, and red takes the site in 40 ticks.
    w.at[0] = Some(0);
    w.ticks(41, &v);
    assert_eq!(SiteState::decode(w.globals[FIRST_OWNER as usize]).owner, 1);
    let score = w.score[0];
    w.ticks(20, &v);
    assert!(w.score[0] > score, "an owned site pays");
    // Covenant step in: no payout, and blue alone cannot push it back.
    w.points[0][COVENANT as usize] = 2;
    let score = w.score[0];
    w.ticks(20, &v);
    assert_eq!(w.score[0], score, "Covenant in the zone stop the payout");
    w.at[0] = None;
    w.at[1] = Some(0);
    w.ticks(30, &v);
    let held = SiteState::decode(w.globals[FIRST_OWNER as usize]);
    assert_eq!((held.owner, held.progress), (1, Some(PROGRESS_STEPS as i32)), "no progress while contested");
    // They are gone: blue pushes it back.
    w.points[0][COVENANT as usize] = 0;
    w.ticks(30, &v);
    assert!(SiteState::decode(w.globals[FIRST_OWNER as usize]).progress.unwrap() < PROGRESS_STEPS as i32);
    // A neutral site with Covenant on it cannot be taken either.
    w.points[1][COVENANT as usize] = 1;
    w.at[1] = Some(1);
    w.ticks(60, &v);
    assert_eq!(SiteState::decode(w.globals[FIRST_OWNER as usize + 1]).progress, Some(0));
}
