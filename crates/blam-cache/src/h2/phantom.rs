//! Halo 2's lifts: the physics model phantoms that push what enters them.
//!
//! A gravity lift, a jump pad or a man cannon in Halo 2 is an ordinary prop
//! whose physics model (`phmo`, hlmt +0x20) carries phantoms: shapes nothing
//! collides with, each with a phantom type saying how it pushes. The
//! simulation the converted maps run on has no such thing, so the stage
//! writes each phantom out (in the object's space) for the level loader to
//! push players with (docs/h2_map_conversion.md).
//!
//! Layout (MCC Halo 2, verified on Lockout's lift tube, Midship's power
//! lift, Gemini's jump pad and Cyclotron's vents, 2026-10-24):
//!
//! - phmo: phantom types 0x28 (0x68 each), materials 0x40 (0x0C: name,
//!   global material, i16 phantom type 0x08), pills 0x58 (0x60), boxes 0x60
//!   (0xB0), polyhedra 0x70 (0x120), polyhedron plane equations 0x80 (0x10),
//!   phantoms 0x108 (0x40: u16 shape type 0x18, u16 shape index 0x1A).
//! - Every shape starts with the same header: name, u16 material 0x04. A
//!   pill: radius 0x38, ends 0x40 and 0x50. A box: half extents 0x40, axes
//!   0x70 / 0x80 / 0x90 (rows), centre 0xA0. A polyhedron: bounding box
//!   half extents 0x40 and centre 0x50, its plane count at 0x110; its
//!   planes (`n·p + d <= 0` inside) follow the previous polyhedra's in the
//!   plane block.
//! - A phantom type: u32 flags (bit 2 negates gravity, bit 3 ignores players,
//!   bit 5 ignores bipeds), marker 0x08 (string id, a render model marker
//!   whose forward is the push), then pairs of acceleration and maximum
//!   speed: towards the marker 0x20, towards its axis 0x28, along its
//!   forward 0x30 (world units per second, and per second squared).
//! - mode: marker groups 0x58 (0x0C: name, markers 0x04 of 0x24: translation
//!   0x04, rotation 0x10 as i, j, k, w).
//!
//! Shape types: 0 sphere, 1 pill, 2 box, 4 polyhedron. Spheres push no
//! player in any multiplayer map (Turf's door spring) and are left out.

use serde_json::{json, Value};

use super::{Cache, Struct, Tag};

const NEGATES_GRAVITY: u32 = 1 << 2;
const IGNORES_PLAYERS: u32 = 1 << 3;
const IGNORES_BIPEDS: u32 = 1 << 5;

/// Rotate `v` by the quaternion (i, j, k, w).
fn rotate(q: [f32; 4], v: [f32; 3]) -> [f32; 3] {
    let [x, y, z, w] = q;
    // v + 2w(q×v) + 2q×(q×v)
    let c = [y * v[2] - z * v[1], z * v[0] - x * v[2], x * v[1] - y * v[0]];
    let cc = [y * c[2] - z * c[1], z * c[0] - x * c[2], x * c[1] - y * c[0]];
    [v[0] + 2.0 * (w * c[0] + cc[0]), v[1] + 2.0 * (w * c[1] + cc[1]), v[2] + 2.0 * (w * c[2] + cc[2])]
}

/// A render model marker's position and forward, by name.
fn marker(mode: &Tag<'_>, name: &str) -> Option<([f32; 3], [f32; 3])> {
    let group = mode.root.block(0x58, 0x0C).iter().find(|g| g.sid(0x00) == name)?;
    let m = group.block(0x04, 0x24).get(0)?;
    let q = [m.f32(0x10), m.f32(0x14), m.f32(0x18), m.f32(0x1C)];
    Some((m.vec3(0x04), rotate(q, [1.0, 0.0, 0.0])))
}

fn length(v: [f32; 3]) -> f32 {
    (v[0] * v[0] + v[1] * v[1] + v[2] * v[2]).sqrt()
}

fn round(v: [f32; 3]) -> [f32; 3] {
    v.map(|x| (x * 10000.0).round() / 10000.0)
}

/// The shape a phantom is, in the object's space, and its material.
fn shape(phmo: &Struct<'_>, kind: u16, index: usize) -> Option<(Value, u16)> {
    match kind {
        1 => {
            let p = phmo.block(0x58, 0x60).get(index)?;
            let (a, b, r) = (p.vec3(0x40), p.vec3(0x50), p.f32(0x38));
            let mid = [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0];
            let half = ((0..3).map(|k| (b[k] - a[k]).powi(2)).sum::<f32>()).sqrt() / 2.0;
            Some((json!({"pill": [round(a), round(b)], "radius": r, "bounds": [round(mid), half + r]}), p.u16(0x04)))
        }
        2 => {
            let b = phmo.block(0x60, 0xB0).get(index)?;
            let half = b.vec3(0x40);
            let centre = b.vec3(0xA0);
            let mut planes = Vec::new();
            for (k, row) in [0x70, 0x80, 0x90].into_iter().enumerate() {
                let a = b.vec3(row);
                let along: f32 = (0..3).map(|j| a[j] * centre[j]).sum();
                planes.push([a[0], a[1], a[2], -along - half[k]]);
                planes.push([-a[0], -a[1], -a[2], along - half[k]]);
            }
            Some((json!({"planes": planes, "bounds": [round(centre), length(half)]}), b.u16(0x04)))
        }
        4 => {
            let polys = phmo.block(0x70, 0x120);
            let first: usize = (0..index).filter_map(|i| polys.get(i)).map(|p| p.u32(0x110) as usize).sum();
            let p = polys.get(index)?;
            let all = phmo.block(0x80, 0x10);
            let planes: Option<Vec<[f32; 4]>> = (first..first + p.u32(0x110) as usize)
                .map(|i| all.get(i).map(|e| [e.f32(0), e.f32(4), e.f32(8), e.f32(12)]))
                .collect();
            // Its bounding box: half extents 0x40, centre 0x50.
            Some((json!({"planes": planes?, "bounds": [round(p.vec3(0x50)), length(p.vec3(0x40))]}), p.u16(0x04)))
        }
        _ => None,
    }
}

/// The phantoms of a placed object that push players, in its own space
/// (world units): each with its shape, the marker it pushes along, and how.
pub fn lifts(cache: &Cache, object: &Tag<'_>) -> Vec<Value> {
    let Some(model) = object.root.tagref(0x34).and_then(|r| cache.follow(r)) else { return Vec::new() };
    let Some(phmo) = model.root.tagref(0x20).and_then(|r| cache.follow(r)) else { return Vec::new() };
    let mode = model.root.tagref(0x00).and_then(|r| cache.follow(r));
    let root = phmo.root;
    let types = root.block(0x28, 0x68);
    let materials = root.block(0x40, 0x0C);
    let mut out = Vec::new();
    for phantom in root.block(0x108, 0x40).iter() {
        let Some((shape, material)) = shape(&root, phantom.u16(0x18), phantom.u16(0x1A) as usize) else { continue };
        let Some(t) = materials.get(material as usize).and_then(|m| types.get(m.i16(0x08).max(0) as usize)) else { continue };
        let flags = t.u32(0x00);
        let pairs = [t.f32(0x20), t.f32(0x24), t.f32(0x28), t.f32(0x2C), t.f32(0x30), t.f32(0x34)];
        if flags & (IGNORES_PLAYERS | IGNORES_BIPEDS) != 0 || pairs.iter().step_by(2).all(|&a| a <= 0.0) {
            continue;
        }
        let name = t.sid(0x08);
        let (origin, forward) = mode.as_ref().and_then(|m| marker(m, name)).unwrap_or(([0.0; 3], [0.0, 0.0, 1.0]));
        out.push(json!({
            "shape": shape,
            "marker": name, "origin": round(origin), "forward": round(forward),
            "center": [pairs[0], pairs[1]], "axis": [pairs[2], pairs[3]], "direction": [pairs[4], pairs[5]],
            "negates_gravity": flags & NEGATES_GRAVITY != 0,
            "phmo": phmo.name(),
        }));
    }
    out
}
