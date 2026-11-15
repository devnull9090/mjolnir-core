//! Execute the generated rule program against a small deterministic world.
//! These are behavioral checks of trigger ordering and contested capture,
//! independent of the Rust builder's particular trigger indices.
use blam_megalo::variant::*;
use blam_megalo::warfare::*;

struct World {
    globals: [i32; 12],
    points: [[i32; 4]; 3],
    score: [i32; 2],
    connected: [bool; 2],
    alive: [bool; 2],
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
            points: [[0; 4]; 3],
            score: [0; 2],
            connected: [true; 2],
            alive: [true; 2],
            seated: [false; 2],
            at: [None; 2],
            current_player: 0,
            current_object: 0,
            saved_object: -1,
            vehicle: -1,
            ended: false,
        }
    }
    fn object(&self, o: Object) -> i32 {
        match o {
            Object::Ref(object::NONE) => -1,
            Object::Ref(object::CURRENT) => self.current_object as i32,
            Object::Ref(1) => self.saved_object,
            Object::Ref(2) => self.vehicle,
            Object::PlayerBiped(player::CURRENT) => 100 + self.current_player as i32,
            _ => panic!("unsupported test object {o:?}"),
        }
    }
    fn value(&self, v: &Var, variant: &Variant) -> i32 {
        match v {
            Var::Number(Number::Constant(x)) => i32::from(*x),
            Var::Number(Number::GlobalNumber(i)) => self.globals[*i as usize],
            Var::Number(Number::ObjectNumber { index, .. }) => {
                self.points[self.saved_object as usize][*index as usize]
            }
            Var::Number(Number::SpawnSequence(_)) => self.current_object as i32,
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
            Var::Number(Number::ObjectNumber { index, .. }) => {
                self.points[self.saved_object as usize][*index as usize] = x
            }
            Var::Object(Object::Ref(1)) => self.saved_object = x,
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
                if self.alive[self.current_player] {
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
                for p in 0..3 {
                    self.current_object = p;
                    self.body(t, v);
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
    assert_eq!(w.globals[DEPLOYMENT_SECONDS as usize], 1, "custom insertion duration is replicated while waiting");
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
    assert_eq!(w.globals[FIRST_OWNER as usize], 1);
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
fn dead_players_cannot_capture_and_score_or_clock_ends_the_round() {
    let mut v = variant();
    let mut w = World::new();
    w.globals[PHASE as usize] = 2;
    w.at[0] = Some(1);
    w.alive[0] = false;
    w.ticks(20, &v);
    assert_eq!(w.points[1][1], 0);
    w.alive[0] = true;
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
