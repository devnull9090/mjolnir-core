//! Halo 2 props that move and break: what a placed crate or scenery object's
//! own tags say about its physics and its damage, so the converter can make
//! every movable prop a physics object and give it the health, effects and
//! sounds Halo 2 gave it (Zanzibar's fusion coils: 15 vitality, sparks and
//! smoke at a threshold, then `fusion_coil_destroyed`'s flash, flames,
//! scorch decal and sound, and `fusion_coil_explosion`'s blast).
//!
//! Layouts (MCC Halo 2, checked against Assembly's Halo2MCC plugins and the
//! coil's own bytes):
//! - object (`bloc`, `scen`): model reference at 0x34; functions block at
//!   0x64 (0x20 each: flags 0x00, import name 0x04, export name 0x08).
//! - model (`hlmt`): physics model reference at 0x20; new damage info block
//!   at 0x60 (0xF8 each): maximum vitality 0x28, damage sections 0xBC (0x38
//!   each: name 0x00, flags 0x04, vitality percentage 0x08, instant
//!   responses 0x0C (0x50 each: type 0x00, flags 0x04, damage threshold
//!   0x08, transition effect 0x0C, transition damage effect 0x14, effect
//!   marker 0x24, damage effect marker 0x28, delay 0x2C)).
//! - physics model (`phmo`): rigid bodies block at 0x38 (0xA0 each: motion
//!   type 0x1A, 0 sphere .. 3 stabilized box move, 4 keyframed, 5 fixed;
//!   mass 0x40).
//!
//! An effect's sounds and decals are found by scanning its data for tag
//! references (group four-CC then a datum whose index entry has that group,
//! which validates itself), since the effect layout is not decoded here.
use super::{Cache, CacheFile, Group, Tag};

/// A prop's rigid bodies, when any of them moves.
#[derive(Debug, Clone)]
pub struct Physics {
    pub mass: f32,
    /// The first moving body's motion type (0 sphere, 1 stabilized sphere,
    /// 2 box, 3 stabilized box).
    pub motion: u16,
    pub bodies: usize,
    /// Constraints of any kind (hinge 0xB0, ragdoll 0xB8, limited hinge
    /// 0xE8, ball and socket 0xF0, stiff spring 0xF8, prismatic 0x100): a
    /// body held to the world or to another (Zanzibar's hanging lights
    /// swing from the ceiling; alone, they fell to the floor).
    pub constraints: usize,
}

/// One instant damage response.
pub struct Response<'c> {
    pub section: String,
    pub threshold: f32,
    pub flags: u32,
    pub effect: Option<Tag<'c>>,
    pub damage_effect: Option<Tag<'c>>,
    pub delay: f32,
}

pub struct Damage<'c> {
    pub vitality: f32,
    pub responses: Vec<Response<'c>>,
}

fn model<'c>(cache: &'c Cache, object: &Tag<'c>) -> Option<Tag<'c>> {
    object.root.tagref(0x34).and_then(|r| cache.follow(r))
}

/// The prop's physics, when Halo 2 moves it: a physics model with a rigid
/// body that is neither keyframed nor fixed.
pub fn physics(cache: &Cache, object: &Tag<'_>) -> Option<Physics> {
    let hlmt = model(cache, object)?;
    let phmo = hlmt.root.tagref(0x20).and_then(|r| cache.follow(r))?;
    let bodies = phmo.root.block(0x38, 0xA0);
    let moving: Vec<_> = bodies.iter().filter(|b| b.u16(0x1A) < 4).collect();
    let first = moving.first()?;
    let constraints = [0xB0usize, 0xB8, 0xE8, 0xF0, 0xF8, 0x100].iter().map(|&o| phmo.root.u32(o) as usize).sum();
    Some(Physics {
        mass: moving.iter().map(|b| b.f32(0x40)).sum(),
        motion: first.u16(0x1A),
        bodies: bodies.count,
        constraints,
    })
}

/// The prop's damage: its vitality and every section's instant responses.
/// None when its model has no damage info or no vitality (indestructible).
pub fn damage<'c>(cache: &'c Cache, object: &Tag<'c>) -> Option<Damage<'c>> {
    let hlmt = model(cache, object)?;
    let info = hlmt.root.block(0x60, 0xF8).get(0)?;
    let vitality = info.f32(0x28);
    if !(vitality > 0.0) {
        return None;
    }
    let mut responses = Vec::new();
    for s in info.block(0xBC, 0x38).iter() {
        let section = s.sid(0x00).to_string();
        for r in s.block(0x0C, 0x50).iter() {
            responses.push(Response {
                section: section.clone(),
                threshold: r.f32(0x08),
                flags: r.u32(0x04),
                effect: r.tagref(0x0C).and_then(|t| cache.follow(t)),
                damage_effect: r.tagref(0x14).and_then(|t| cache.follow(t)),
                delay: r.f32(0x2C),
            });
        }
    }
    Some(Damage { vitality, responses })
}

/// The object's functions as (import, export) names.
pub fn functions(object: &Tag<'_>) -> Vec<(String, String)> {
    object
        .root
        .block(0x64, 0x20)
        .iter()
        .map(|f| (f.sid(0x04).to_string(), f.sid(0x08).to_string()))
        .collect()
}

/// A tag's bytes from its root to the next tag's address in its file (the
/// index stores no sizes in MCC Halo 2 maps; a tag's blocks follow its root).
fn span<'c>(file: &'c CacheFile, at: usize) -> &'c [u8] {
    let next = file
        .tags
        .iter()
        .filter_map(|t| t.address.and_then(|a| file.offset(a)))
        .filter(|&x| x > at)
        .min()
        .unwrap_or(at + 0x10000);
    &file.data[at..next.min(at + 0x40000).min(file.data.len())]
}

/// Every tag of `group` that `tag` references, in order, without repeats.
pub fn references<'c>(cache: &'c Cache, tag: &Tag<'c>, group: &[u8; 4]) -> Vec<Tag<'c>> {
    let want = Group::new(group);
    let bytes = span(tag.file, tag.root.at);
    let mut out: Vec<Tag<'c>> = Vec::new();
    for o in (0..bytes.len().saturating_sub(8)).step_by(4) {
        let g = u32::from_le_bytes(bytes[o..o + 4].try_into().unwrap());
        let d = u32::from_le_bytes(bytes[o + 4..o + 8].try_into().unwrap());
        if g != want.0 || d == u32::MAX {
            continue;
        }
        let Some(e) = tag.file.entry(d) else { continue };
        if e.group != want || e.datum != d {
            continue;
        }
        if let Some(t) = cache.tag(tag.file, d) {
            if !out.iter().any(|x| x.name() == t.name()) {
                out.push(t);
            }
        }
    }
    out
}
