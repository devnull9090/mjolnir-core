//! A small builder for Megalo scripts: triggers written as a list of
//! conditions and actions, in the order they gate each other.
//!
//! A trigger stops at its first failed condition (`0x423a70`), so a
//! condition gates every action after it; a branch is a subroutine of its
//! own, called with [`Action::CallTrigger`].

use crate::variant::{
    Action, Compare, Condition, ConditionKind, Number, Object, Op, Timer, Trigger, TriggerKind,
    Var, Variant, ATTR_SUBROUTINE,
};

pub(crate) enum Item {
    If(ConditionKind),
    Do(Action),
}

impl Clone for Item {
    fn clone(&self) -> Item {
        match self {
            Item::If(k) => Item::If(k.clone()),
            Item::Do(a) => Item::Do(a.clone()),
        }
    }
}

pub(crate) fn compare(a: Var, b: Var, op: Compare) -> Item {
    Item::If(ConditionKind::Compare { a, b, op })
}

pub(crate) fn eq(a: Var, b: Var) -> Item {
    compare(a, b, Compare::Equal)
}

pub(crate) fn set(a: Var, b: Var) -> Item {
    Item::Do(Action::ModifyVariable { a, b, op: Op::Set })
}

pub(crate) fn constant(n: i16) -> Var {
    Var::Number(Number::Constant(n))
}

pub(crate) fn obj(r: u8) -> Var {
    Var::Object(Object::Ref(r))
}

pub(crate) struct Builder {
    pub v: Variant,
}

impl Variant {
    /// End the round when its time limit runs out. The engine counts the
    /// round clock down and raises the 30 and 10 seconds remaining
    /// incidents, but ending the round is the script's job (2026-10-04: a
    /// one-minute limit ran out and the round went on). The limit is
    /// checked first: with none, the round clock may sit at zero.
    pub fn with_time_limit(self) -> Variant {
        let mut b = Builder::new(self);
        b.trigger(
            TriggerKind::Do,
            crate::variant::ATTR_NORMAL,
            vec![
                compare(
                    Var::Number(Number::RoundTimeLimit),
                    constant(0),
                    Compare::Greater,
                ),
                Item::If(ConditionKind::TimerIsZero(Timer::Round)),
                Item::Do(Action::EndRound),
            ],
        );
        b.v
    }
}

impl Builder {
    pub fn new(v: Variant) -> Builder {
        Builder { v }
    }

    /// Append a trigger; conditions gate the actions after them.
    pub fn trigger(&mut self, kind: TriggerKind, attribute: u8, items: Vec<Item>) -> u16 {
        let v = &mut self.v;
        let first_condition = v.conditions.len() as u16;
        let first_action = v.actions.len() as u16;
        let mut actions = 0u16;
        let mut sequence = 0u16;
        for item in items {
            match item {
                Item::If(kind) => {
                    v.conditions.push(Condition {
                        kind,
                        negate: false,
                        or_sequence: sequence,
                        action_offset: actions,
                    });
                    sequence += 1;
                }
                Item::Do(a) => {
                    v.actions.push(a);
                    actions += 1;
                }
            }
        }
        v.triggers.push(Trigger {
            kind,
            attribute,
            first_condition,
            condition_count: v.conditions.len() as u16 - first_condition,
            first_action,
            action_count: actions,
        });
        v.triggers.len() as u16 - 1
    }

    pub fn sub(&mut self, kind: TriggerKind, items: Vec<Item>) -> u16 {
        self.trigger(kind, ATTR_SUBROUTINE, items)
    }

    /// Add a label to the string table and a filter for it; the filter index.
    pub fn label(&mut self, name: &str) -> u8 {
        let v = &mut self.v;
        let string = match v.strings.iter().position(|s| s == name) {
            Some(i) => i as u8,
            None => {
                v.strings.push(name.to_string());
                v.strings.len() as u8 - 1
            }
        };
        match v.filters.iter().position(|f| f.label == string) {
            Some(i) => i as u8,
            None => {
                v.filters.push(crate::variant::Filter {
                    label: string,
                    team: None,
                });
                v.filters.len() as u8 - 1
            }
        }
    }
}
