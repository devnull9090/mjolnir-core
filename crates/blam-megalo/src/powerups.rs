//! Halo CE's health packs, as Megalo script any variant can carry.
//!
//! The simulation has no CE health pack: no object, and no pickup that heals
//! on contact (this game's health never recharges, as CE's did not). So the
//! map places a spot, an object labelled `ce_health_pack`, wherever CE put a
//! health pack, and every tick, for each spot:
//!
//! - with no pack and its countdown run out, it creates one (a multiplayer
//!   object type the map's object type list adds) that nobody can pick up;
//! - with a pack, any living player within reach of it whose health is not
//!   full is healed to full, the pack goes, and the countdown starts;
//! - the countdown ticks down.
//!
//! A pickup raises `lap_complete` (see [`incident`]), for MJOLNIRLevelLoader
//! to play CE's pickup sound to the player who took it. Shields are left alone, as CE left them.

use crate::script::{compare, constant, eq, obj, set, Builder, Item};
use crate::variant::{
    object, player, Action, Compare, Number, Object, Op, Player, PlayerSet, Subject, TriggerKind,
    Var, Variant, ATTR_NORMAL,
};
use crate::Error;

/// The label a health pack spot carries (a placement's `megalo label`).
pub const SPOT_LABEL: &str = "ce_health_pack";

/// Incident indices (`globals\incident_properties` order).
pub mod incident {
    /// A health pack was picked up: `lap_complete`, which only Race raises.
    /// `recharge_health` (12) would be the natural one, but the simulation
    /// never hands it to Unreal's incident handler (Blood Gulch, 2026-10-01:
    /// the pack healed, the loader saw nothing); the race incidents do
    /// arrive, as the CTF debug markers showed.
    pub const HEALTH_PACK_TAKEN: u16 = 104;
}

/// Create-object flags: never garbage-collect the pack.
const NEVER_GARBAGE_COLLECT: u8 = 1;

// On a spot: object.number[0] counts down, object.object[0] is its pack.
const COUNTDOWN: u8 = 0;
const LINK: u8 = 0;

#[derive(Debug, Clone, Copy)]
pub struct HealthPacks {
    /// The pack's index in `multiplayer_object_type_list`.
    pub object_type: u16,
    /// Ticks before a taken pack comes back.
    pub respawn_ticks: i16,
    /// How close a player's biped must be to the pack, in feet (ten to a
    /// world unit; Get Distance measures origin to origin).
    pub reach_feet: i16,
}

impl Variant {
    /// This variant with CE's health packs added: a label, a few variables
    /// past the ones it declares, the pack's object type, and the triggers.
    pub fn with_health_packs(self, h: HealthPacks) -> Result<Variant, Error> {
        let mut b = Builder::new(self);
        let spots = b.label(SPOT_LABEL);
        let vars = &mut b.v.vars;
        let (g_number, g_object) = (vars.global_numbers, vars.global_objects);
        if g_number + 2 > 12 || g_object + 2 > 16 {
            return Err(Error::Unsupported(
                "too few global variables left for health packs".into(),
            ));
        }
        vars.global_numbers += 2;
        vars.global_objects += 2;
        vars.object_numbers = vars.object_numbers.max(COUNTDOWN + 1);
        vars.object_objects = vars.object_objects.max(LINK + 1);
        if !b.v.object_types.contains(&h.object_type) {
            b.v.object_types.push(h.object_type);
        }

        let spot = object::global(g_object);
        let new_pack = object::global(g_object + 1);
        let distance = Number::GlobalNumber(g_number);
        let health = Number::GlobalNumber(g_number + 1);
        let countdown = Var::Number(Number::ObjectNumber {
            object: spot,
            index: COUNTDOWN,
        });
        let pack = Object::ObjectObject {
            object: spot,
            index: LINK,
        };
        let biped = Object::PlayerBiped(player::CURRENT);
        let none = obj(object::NONE);

        // Each player, the spot's pack still there: a living player close
        // enough and hurt takes it.
        let take = b.sub(
            TriggerKind::EachPlayer,
            vec![
                compare(Var::Object(pack), none.clone(), Compare::NotEqual),
                compare(Var::Object(biped), none.clone(), Compare::NotEqual),
                Item::Do(Action::GetDistance {
                    a: biped,
                    b: pack,
                    out: distance.clone(),
                }),
                compare(Var::Number(distance), constant(h.reach_feet), Compare::Less),
                Item::Do(Action::GetHealth {
                    object: biped,
                    out: health.clone(),
                }),
                compare(Var::Number(health), constant(100), Compare::Less),
                Item::Do(Action::ModifyHealth {
                    object: biped,
                    op: Op::Set,
                    value: Number::Constant(100),
                }),
                Item::Do(Action::DeleteObject(pack)),
                set(Var::Object(pack), none.clone()),
                set(countdown.clone(), constant(h.respawn_ticks)),
                Item::Do(Action::SendIncident {
                    incident: incident::HEALTH_PACK_TAKEN,
                    cause: Subject::Player(Player(player::CURRENT)),
                    effect: Subject::None,
                    value: None,
                }),
            ],
        );

        let tick_down = b.sub(
            TriggerKind::Do,
            vec![
                compare(countdown.clone(), constant(0), Compare::Greater),
                Item::Do(Action::ModifyVariable {
                    a: countdown.clone(),
                    b: constant(1),
                    op: Op::Subtract,
                }),
            ],
        );

        let make = b.sub(
            TriggerKind::Do,
            vec![
                eq(Var::Object(pack), none.clone()),
                compare(countdown, constant(0), Compare::LessOrEqual),
                Item::Do(Action::CreateObject {
                    object_type: Some(h.object_type),
                    out: Object::Ref(new_pack),
                    at: Object::Ref(spot),
                    label: None,
                    flags: NEVER_GARBAGE_COLLECT,
                    offset: [0, 0, 1],
                    name: None,
                }),
                set(Var::Object(pack), obj(new_pack)),
                Item::Do(Action::SetPickupPermissions {
                    object: Object::Ref(new_pack),
                    who: PlayerSet::NoOne,
                }),
            ],
        );

        b.trigger(
            TriggerKind::EachObjectWithLabel(spots),
            ATTR_NORMAL,
            vec![
                set(obj(spot), obj(object::CURRENT)),
                Item::Do(Action::CallTrigger(tick_down)),
                Item::Do(Action::CallTrigger(make)),
                Item::Do(Action::CallTrigger(take)),
            ],
        );
        Ok(b.v)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ctf::Ctf;
    use crate::variant::tests::check_ranges;

    const PACKS: HealthPacks = HealthPacks {
        object_type: 19,
        respawn_ticks: 900,
        reach_feet: 8,
    };

    #[test]
    fn slayer_with_health_packs_reads_back_exactly() {
        let v = Variant::slayer(25).with_health_packs(PACKS).unwrap();
        check_ranges(&v);
        let bytes = v.write().unwrap();
        assert_eq!(Variant::read(&bytes).unwrap(), v);
        assert_eq!(v.strings, vec![SPOT_LABEL.to_string()]);
        assert_eq!(v.object_types, vec![19]);
    }

    #[test]
    fn ctf_keeps_its_own_variables_and_labels() {
        let ctf = Variant::ctf(Ctf {
            flag_type: 18,
            score_to_win: 3,
            reset_ticks: 900,
            debug: false,
        });
        let v = ctf.clone().with_health_packs(PACKS).unwrap();
        check_ranges(&v);
        assert_eq!(&v.strings[..ctf.strings.len()], &ctf.strings[..]);
        assert_eq!(v.vars.global_objects, ctf.vars.global_objects + 2);
        assert_eq!(v.object_types, vec![18, 19]);
        let bytes = v.write().unwrap();
        assert_eq!(Variant::read(&bytes).unwrap(), v);
    }
}
