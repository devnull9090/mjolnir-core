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

fn cross3(u: [f32; 3], v: [f32; 3]) -> [f32; 3] {
    [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
}

fn dot3(u: [f32; 3], v: [f32; 3]) -> f32 {
    u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
}

/// A convex shape's planes (`n.p + d <= 0` inside) as a closed triangle
/// mesh: its corners where three planes meet inside the rest, each face's
/// corners in order about the face's centre, wound to face out.
fn hull(planes: &[[f32; 4]]) -> Vec<[f32; 3]> {
    let normal = |q: &[f32; 4]| [q[0], q[1], q[2]];
    let inside = |p: [f32; 3]| planes.iter().all(|q| dot3(normal(q), p) + q[3] <= 1e-3);
    let mut corners: Vec<[f32; 3]> = Vec::new();
    for a in 0..planes.len() {
        for b in a + 1..planes.len() {
            for c in b + 1..planes.len() {
                let (p, q, r) = (normal(&planes[a]), normal(&planes[b]), normal(&planes[c]));
                let qr = cross3(q, r);
                let det = dot3(p, qr);
                if det.abs() < 1e-6 {
                    continue;
                }
                let (rp, pq) = (cross3(r, p), cross3(p, q));
                let (dp, dq, dr) = (planes[a][3], planes[b][3], planes[c][3]);
                let x: [f32; 3] = std::array::from_fn(|i| -(dp * qr[i] + dq * rp[i] + dr * pq[i]) / det);
                if inside(x) && !corners.iter().any(|c| (0..3).all(|i| (c[i] - x[i]).abs() < 1e-3)) {
                    corners.push(x);
                }
            }
        }
    }
    let mut tris = Vec::new();
    for q in planes {
        let n = normal(q);
        let on: Vec<[f32; 3]> = corners.iter().copied().filter(|c| (dot3(n, *c) + q[3]).abs() < 1e-3).collect();
        if on.len() < 3 {
            continue;
        }
        let m: [f32; 3] = std::array::from_fn(|i| on.iter().map(|c| c[i]).sum::<f32>() / on.len() as f32);
        // Two axes in the face, u then v = n x u, so increasing angle runs
        // anticlockwise seen from outside.
        let u = {
            let d = [on[0][0] - m[0], on[0][1] - m[1], on[0][2] - m[2]];
            let l = length(d).max(1e-9);
            d.map(|x| x / l)
        };
        let v = cross3(n, u);
        let mut ring: Vec<(f32, [f32; 3])> = on
            .iter()
            .map(|c| {
                let d = [c[0] - m[0], c[1] - m[1], c[2] - m[2]];
                (dot3(d, v).atan2(dot3(d, u)), *c)
            })
            .collect();
        ring.sort_by(|a, b| a.0.total_cmp(&b.0));
        for k in 1..ring.len() - 1 {
            tris.extend([ring[0].1, ring[k].1, ring[k + 1].1]);
        }
    }
    tris
}

/// The solid shapes of a physics model (`phmo`) as triangles, in the
/// object's space (world units): every box, polyhedron and pill whose
/// material is not a phantom's. A prop with no collision model collides in
/// Halo 2 by these alone (Elongation's and Gemini's invisible boxes,
/// Burial Mounds', Zanzibar's beach bushes); a pill goes in as the box
/// round it. Shapes sit on their rigid body's node; these props have one.
pub fn solid_triangles(cache: &Cache, object: &Tag<'_>) -> Vec<[f32; 3]> {
    let Some(model) = object.root.tagref(0x34).and_then(|r| cache.follow(r)) else { return Vec::new() };
    let Some(phmo) = model.root.tagref(0x20).and_then(|r| cache.follow(r)) else { return Vec::new() };
    let root = phmo.root;
    let materials = root.block(0x40, 0x0C);
    let solid = |m: u16| materials.get(m as usize).is_some_and(|m| m.i16(0x08) < 0);
    let mut tris = Vec::new();
    for (kind, block, size) in [(1u16, 0x58usize, 0x60usize), (2, 0x60, 0xB0), (4, 0x70, 0x120)] {
        for index in 0..root.block(block, size).count {
            let Some((shape, material)) = shape(&root, kind, index) else { continue };
            if !solid(material) {
                continue;
            }
            let planes: Vec<[f32; 4]> = if kind == 1 {
                // The box round the pill: along its axis, and two across.
                let (Some(ends), Some(r)) = (shape["pill"].as_array(), shape["radius"].as_f64()) else { continue };
                let pt = |v: &Value| -> [f32; 3] { std::array::from_fn(|i| v[i].as_f64().unwrap_or(0.0) as f32) };
                let (a, b, r) = (pt(&ends[0]), pt(&ends[1]), r as f32);
                let d = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
                let l = length(d);
                let x = if l > 1e-6 { d.map(|v| v / l) } else { [0.0, 0.0, 1.0] };
                let t = if x[2].abs() < 0.9 { [0.0, 0.0, 1.0] } else { [1.0, 0.0, 0.0] };
                let y = {
                    let c = cross3(x, t);
                    let l = length(c);
                    c.map(|v| v / l)
                };
                let z = cross3(x, y);
                let mid = [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0];
                let mut p = Vec::new();
                for (axis, half) in [(x, l / 2.0 + r), (y, r), (z, r)] {
                    let along = dot3(axis, mid);
                    p.push([axis[0], axis[1], axis[2], -along - half]);
                    p.push([-axis[0], -axis[1], -axis[2], along - half]);
                }
                p
            } else {
                let Some(list) = shape["planes"].as_array() else { continue };
                list.iter().map(|q| std::array::from_fn(|i| q[i].as_f64().unwrap_or(0.0) as f32)).collect()
            };
            tris.extend(hull(&planes));
        }
    }
    tris
}

#[cfg(test)]
mod tests {
    use super::hull;

    /// A cube's six planes make 12 triangles, every one facing out.
    #[test]
    fn a_cube_hull_faces_out() {
        let planes = [
            [1.0, 0.0, 0.0, -1.0],
            [-1.0, 0.0, 0.0, -1.0],
            [0.0, 1.0, 0.0, -1.0],
            [0.0, -1.0, 0.0, -1.0],
            [0.0, 0.0, 1.0, -1.0],
            [0.0, 0.0, -1.0, -1.0],
        ];
        let t = hull(&planes);
        assert_eq!(t.len(), 36);
        for tri in t.chunks(3) {
            let (a, b, c) = (tri[0], tri[1], tri[2]);
            let n = super::cross3([b[0] - a[0], b[1] - a[1], b[2] - a[2]], [c[0] - a[0], c[1] - a[1], c[2] - a[2]]);
            let m = [(a[0] + b[0] + c[0]) / 3.0, (a[1] + b[1] + c[1]) / 3.0, (a[2] + b[2] + c[2]) / 3.0];
            assert!(super::dot3(n, m) > 0.0, "inward {tri:?}");
        }
    }
}
