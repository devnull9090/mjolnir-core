//! Pack a CE collision BSP into the Meteorite 16-bit `collision bsp` tables.
//!
//! Element layouts, from the tag's own `blay` (dumped in
//! `defs/hce/tag-definitions.json`) and confirmed against `BSP_03_1_Chasm_old`:
//!
//! | block | bytes | layout |
//! |---|---|---|
//! | bsp3d nodes | 8 | `u16 plane`, `u24 back`, `u24 front` — `0xFFFFFF` none, bit 23 = leaf |
//! | planes | 16 | `f32 i j k d` |
//! | leaves | 8 | `u8 flags`, pad, `u16 bsp2d reference count`, `u32 first bsp2d reference` |
//! | bsp2d references | 4 | `i16 plane`, `i16 bsp2d node` — bit 15 = surface |
//! | bsp2d nodes | 16 | `f32 i j d`, `i16 left`, `i16 right` — bit 15 = surface |
//! | surfaces | 14 | `u16 plane`, `u16 first edge`, `i16 material`, `i16 breakable set`, `i16 breakable`, `u16 flags`, `u8 best-plane vertex`, pad |
//! | edges | 12 | six `u16`: start, end, forward, reverse, left surface, right surface |
//! | vertices | 16 | `f32 x y z`, `u16 first edge`, `i16 sink` |
//!
//! The bsp3d node packing was decoded from Chasm_old's 116-node shell: with
//! `0xFFFFFF` read as "none" and bit 23 as the leaf flag, every one of its 41
//! leaves is referenced exactly once and every non-root node exactly once
//! (`[plane 15][none][node 1]`, `[16][node 2][node 4]`, ...). The unreferenced
//! nodes are the roots the kd supernode points at with `0x4000_0000 | node`.
//!
//! CE plane references carry a flip bit in `0x8000_0000`; 2D references keep it
//! as the 16-bit sign, surfaces move it into the `plane negated` flag.
//!
//! Surface flags share their first four bits with CE (two sided, invisible,
//! climbable, breakable); the rest (invalid, conveyor, slip, plane negated,
//! pathfinding only) are Meteorite-only and stay clear.

use crate::ce::{Collision, Surface};
use crate::Error;

pub const NONE24: u32 = 0xff_ffff;
pub const LEAF24: u32 = 0x80_0000;
pub const SURFACE16: i16 = i16::MIN;

/// All eight tables packed, in `global_collision_bsp_struct` order (without the
/// supernodes, which CE has none of).
#[derive(Debug, Clone, Default)]
pub struct Packed {
    pub bsp3d_nodes: Vec<u8>,
    pub planes: Vec<u8>,
    pub leaves: Vec<u8>,
    pub bsp2d_references: Vec<u8>,
    pub bsp2d_nodes: Vec<u8>,
    pub surfaces: Vec<u8>,
    pub edges: Vec<u8>,
    pub vertices: Vec<u8>,
}

fn child24(ce: i32) -> u32 {
    if ce == -1 {
        NONE24
    } else if (ce as u32) & 0x8000_0000 != 0 {
        LEAF24 | ((ce as u32) & 0x7f_ffff)
    } else {
        (ce as u32) & 0x7f_ffff
    }
}

fn child16(ce: i32) -> i16 {
    if ce == -1 {
        -1
    } else if (ce as u32) & 0x8000_0000 != 0 {
        SURFACE16 | (((ce as u32) & 0x7fff) as i16)
    } else {
        (ce & 0x7fff) as i16
    }
}

fn u16_of(ce: i32) -> u16 {
    if ce == -1 {
        u16::MAX
    } else {
        ce as u16
    }
}

/// Map a CE material index into the Meteorite `collision materials` table.
pub trait MaterialMap {
    fn meteorite_index(&self, ce_material: i16) -> i16;
}

impl<F: Fn(i16) -> i16> MaterialMap for F {
    fn meteorite_index(&self, ce_material: i16) -> i16 {
        self(ce_material)
    }
}

/// Pack every table. `materials` remaps CE surface material indices.
pub fn pack(c: &Collision, materials: &dyn MaterialMap) -> Result<Packed, Error> {
    c.fits_16bit()?;
    let mut p = Packed::default();

    for n in &c.bsp3d_nodes {
        let word: u64 = (n.plane as u16 as u64)
            | ((child24(n.back) as u64) << 16)
            | ((child24(n.front) as u64) << 40);
        p.bsp3d_nodes.extend_from_slice(&word.to_le_bytes());
    }
    for pl in &c.planes {
        for v in pl.n.iter().chain(std::iter::once(&pl.d)) {
            p.planes.extend_from_slice(&v.to_le_bytes());
        }
    }
    for l in &c.leaves {
        p.leaves.push((l.flags & 0xff) as u8);
        p.leaves.push(0);
        p.leaves
            .extend_from_slice(&(l.reference_count.max(0) as u16).to_le_bytes());
        p.leaves
            .extend_from_slice(&(l.first_reference as u32).to_le_bytes());
    }
    for r in &c.bsp2d_references {
        p.bsp2d_references
            .extend_from_slice(&plane16(r.plane).to_le_bytes());
        p.bsp2d_references
            .extend_from_slice(&child16(r.node).to_le_bytes());
    }
    for n in &c.bsp2d_nodes {
        for v in &n.plane {
            p.bsp2d_nodes.extend_from_slice(&v.to_le_bytes());
        }
        p.bsp2d_nodes
            .extend_from_slice(&child16(n.left).to_le_bytes());
        p.bsp2d_nodes
            .extend_from_slice(&child16(n.right).to_le_bytes());
    }
    for s in &c.surfaces {
        p.surfaces.extend_from_slice(&surface16(s, materials));
    }
    for e in &c.edges {
        for v in [e.start, e.end, e.forward, e.reverse, e.left, e.right] {
            p.edges.extend_from_slice(&u16_of(v).to_le_bytes());
        }
    }
    for v in &c.vertices {
        for x in &v.point {
            p.vertices.extend_from_slice(&x.to_le_bytes());
        }
        p.vertices
            .extend_from_slice(&u16_of(v.first_edge).to_le_bytes());
        p.vertices.extend_from_slice(&0i16.to_le_bytes());
    }
    Ok(p)
}

/// A CE plane reference keeps its flip bit (`0x8000_0000`, "the surface lies
/// on the back of the plane") as the sign bit of the 16-bit field: Chasm_old's
/// 2D references carry one such `-32768` (plane 0, negated).
fn plane16(ce: i32) -> i16 {
    let idx = ((ce as u32) & 0x7fff) as i16;
    if (ce as u32) & 0x8000_0000 != 0 {
        idx | i16::MIN
    } else {
        idx
    }
}

/// Meteorite surfaces name the plane unsigned and carry the flip as the
/// `plane negated` flag (bit 7), which is what Chasm_old's one negated
/// surface shows.
const PLANE_NEGATED: u16 = 0x80;

fn surface16(s: &Surface, materials: &dyn MaterialMap) -> [u8; 14] {
    let mut b = [0u8; 14];
    let negated = (s.plane as u32) & 0x8000_0000 != 0;
    b[0..2].copy_from_slice(&(((s.plane as u32) & 0x7fff) as u16).to_le_bytes());
    b[2..4].copy_from_slice(&u16_of(s.first_edge).to_le_bytes());
    b[4..6].copy_from_slice(&materials.meteorite_index(s.material).to_le_bytes());
    b[6..8].copy_from_slice(&(-1i16).to_le_bytes());
    b[8..10].copy_from_slice(&(-1i16).to_le_bytes());
    // CE bits 0..3 line up with Meteorite's first four flag options.
    let mut flags = (s.flags & 0x0f) as u16;
    if negated {
        flags |= PLANE_NEGATED;
    }
    b[10..12].copy_from_slice(&flags.to_le_bytes());
    b[12] = 0;
    b[13] = 0;
    b
}

/// Which two world axes a 3D plane's 2D BSP works in, and in what order.
///
/// Determined from shipped data (`examples/roundtrip16.rs`): drop the axis the
/// normal is largest along, keep the other two in cyclic order when that
/// component is positive and swapped when it is negative. Scored 100% of
/// vertex checks on three definitions and 99.5% on the world shell; every
/// other candidate sat near chance.
pub fn projection_axes(n: [f32; 3]) -> (usize, usize) {
    let a = (0..3)
        .max_by(|&i, &j| n[i].abs().partial_cmp(&n[j].abs()).unwrap())
        .unwrap();
    let (p, q) = ((a + 1) % 3, (a + 2) % 3);
    if n[a] > 0.0 {
        (p, q)
    } else {
        (q, p)
    }
}

/// The 3D plane each 2D node belongs to, found by walking down from every
/// 2D reference. A node unreachable from any reference maps to `None`.
pub fn node_planes(c: &Collision) -> Vec<Option<usize>> {
    let mut owner = vec![None; c.bsp2d_nodes.len()];
    for r in &c.bsp2d_references {
        let plane = (r.plane as u32 & 0x7fff) as usize;
        let mut stack = vec![r.node];
        while let Some(child) = stack.pop() {
            if child == -1 || (child as u32) & 0x8000_0000 != 0 {
                continue;
            }
            let i = child as usize;
            if i >= owner.len() || owner[i].is_some() {
                continue;
            }
            owner[i] = Some(plane);
            stack.push(c.bsp2d_nodes[i].left);
            stack.push(c.bsp2d_nodes[i].right);
        }
    }
    owner
}

/// Translate the whole BSP by `delta` (world units) without touching its
/// topology: vertices move, a plane `n·x = d` becomes `n·x = d + n·t`, and
/// each 2D split line `i·u + j·v = d` — which lives in the projection of its
/// parent 3D plane — becomes `d + i·t[u] + j·t[v]`. An earlier version left
/// the 2D lines alone, which put every surface on the wrong side of its
/// splits after any sideways move; that is why transplanted shells and
/// definitions let the pawn through.
pub fn translate(c: &mut Collision, delta: [f32; 3]) {
    for v in &mut c.vertices {
        for a in 0..3 {
            v.point[a] += delta[a];
        }
    }
    for p in &mut c.planes {
        p.d += p.n[0] * delta[0] + p.n[1] * delta[1] + p.n[2] * delta[2];
    }
    let owners = node_planes(c);
    for (i, node) in c.bsp2d_nodes.iter_mut().enumerate() {
        let Some(plane) = owners[i] else { continue };
        let (u, v) = projection_axes(c.planes[plane].n);
        node.plane[2] += node.plane[0] * delta[u] + node.plane[1] * delta[v];
    }
}

/// The effective normal each 2D node's lines live under: its owning 3D
/// plane's normal, negated when the 2D reference that reaches it is.
fn node_normals(c: &Collision) -> Vec<Option<[f32; 3]>> {
    let mut owner = vec![None; c.bsp2d_nodes.len()];
    for r in &c.bsp2d_references {
        let Some(plane) = c.planes.get((r.plane as u32 & 0x7fff_ffff) as usize) else {
            continue;
        };
        let n = if (r.plane as u32) & 0x8000_0000 != 0 {
            [-plane.n[0], -plane.n[1], -plane.n[2]]
        } else {
            plane.n
        };
        let mut stack = vec![r.node];
        while let Some(child) = stack.pop() {
            if child == -1 || (child as u32) & 0x8000_0000 != 0 {
                continue;
            }
            let i = child as usize;
            if i >= owner.len() || owner[i].is_some() {
                continue;
            }
            owner[i] = Some(n);
            stack.push(c.bsp2d_nodes[i].left);
            stack.push(c.bsp2d_nodes[i].right);
        }
    }
    owner
}

/// Place a BSP in the world by an instance frame: `world = pos + scale *
/// (x*forward + y*left + z*up)`, for frames whose axes are each a signed world
/// axis (quarter-turn rotations, mirrors), which is what shipped instances
/// use. Exact, like [`translate`]: vertices and 3D planes transform, and each
/// 2D split line is rewritten for its plane's new projection. Under such a
/// frame local axis k becomes world axis `perm[k]` with sign `sign[k]`, so a
/// line `a*p[u] + b*p[v] = c` keeps its sides with its coefficients permuted
/// and signed and `c` scaled and shifted by the position.
pub fn transform(
    c: &mut Collision,
    forward: [f32; 3],
    left: [f32; 3],
    up: [f32; 3],
    scale: f32,
    pos: [f32; 3],
) -> Result<(), Error> {
    let axes = [forward, left, up];
    let mut perm = [0usize; 3];
    let mut sign = [0f32; 3];
    for k in 0..3 {
        let (j, v) = (0..3)
            .map(|j| (j, axes[k][j]))
            .max_by(|a, b| a.1.abs().partial_cmp(&b.1.abs()).unwrap())
            .unwrap();
        if (v.abs() - 1.0).abs() > 1e-4 || (0..3).any(|o| o != j && axes[k][o].abs() > 1e-4) {
            return Err(Error::Other(format!(
                "frame axis {k} {:?} is not a signed world axis",
                axes[k]
            )));
        }
        perm[k] = j;
        sign[k] = v.signum();
    }
    let rot = |p: [f32; 3]| {
        let mut w = [0f32; 3];
        for k in 0..3 {
            w[perm[k]] += sign[k] * p[k];
        }
        w
    };
    let normals = node_normals(c);
    for (i, node) in c.bsp2d_nodes.iter_mut().enumerate() {
        let Some(n) = normals[i] else { continue };
        let (u, v) = projection_axes(n);
        let (u2, v2) = projection_axes(rot(n));
        let (a, b, d) = (node.plane[0], node.plane[1], node.plane[2]);
        let (au, bv) = (a * sign[u], b * sign[v]);
        let (a2, b2) = if perm[u] == u2 && perm[v] == v2 {
            (au, bv)
        } else if perm[u] == v2 && perm[v] == u2 {
            (bv, au)
        } else {
            return Err(Error::Other(format!(
                "2D node {i}: projection axes do not map"
            )));
        };
        node.plane = [a2, b2, d * scale + au * pos[perm[u]] + bv * pos[perm[v]]];
    }
    for v in &mut c.vertices {
        let w = rot(v.point);
        v.point = [
            pos[0] + scale * w[0],
            pos[1] + scale * w[1],
            pos[2] + scale * w[2],
        ];
    }
    for p in &mut c.planes {
        let n = rot(p.n);
        p.d = scale * p.d + n[0] * pos[0] + n[1] * pos[1] + n[2] * pos[2];
        p.n = n;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// One plane (z = 1), one 2D split on it (x = 0.5 in its projection), and
    /// four vertices on the plane either side of the split.
    fn split_square() -> Collision {
        use crate::ce::{Bsp2dNode, Bsp2dReference, Plane, Vertex};
        let v = |x: f32, y: f32| Vertex {
            point: [x, y, 1.0],
            first_edge: 0,
        };
        Collision {
            planes: vec![Plane {
                n: [0.0, 0.0, 1.0],
                d: 1.0,
            }],
            bsp2d_references: vec![Bsp2dReference { plane: 0, node: 0 }],
            bsp2d_nodes: vec![Bsp2dNode {
                plane: [1.0, 0.0, 0.5],
                left: 0x8000_0000u32 as i32,
                right: 0x8000_0001u32 as i32,
            }],
            vertices: vec![v(0.0, 0.0), v(1.0, 0.0), v(1.0, 1.0), v(0.0, 1.0)],
            ..Default::default()
        }
    }

    fn sides(c: &Collision) -> Vec<bool> {
        let n = &c.bsp2d_nodes[0];
        let (u, v) = projection_axes(c.planes[0].n);
        c.vertices
            .iter()
            .map(|x| n.plane[0] * x.point[u] + n.plane[1] * x.point[v] - n.plane[2] > 0.0)
            .collect()
    }

    /// A frame transform keeps every vertex on its side of every 2D split and
    /// on its plane, for quarter turns about each axis and mirrors, scaled and
    /// moved — the frames shipped instances use.
    #[test]
    fn transform_keeps_2d_sides_and_planes() {
        let before = sides(&split_square());
        let frames: [([f32; 3], [f32; 3], [f32; 3]); 4] = [
            ([0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]), // quarter turn about z (instance 763)
            ([1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]), // quarter turn about x
            ([0.0, 0.0, -1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]), // quarter turn about y
            ([-1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]), // mirror in x
        ];
        for (f, l, u) in frames {
            let mut c = split_square();
            transform(&mut c, f, l, u, 0.328_084, [44.8, 67.14, 48.17]).unwrap();
            assert_eq!(sides(&c), before, "frame {f:?} {l:?} {u:?}");
            let p = &c.planes[0];
            for v in &c.vertices {
                let d = p.n[0] * v.point[0] + p.n[1] * v.point[1] + p.n[2] * v.point[2] - p.d;
                assert!(d.abs() < 1e-4, "vertex {:?} is {d} off its plane", v.point);
            }
        }
    }

    #[test]
    fn transform_refuses_a_frame_that_is_not_axis_aligned() {
        let mut c = split_square();
        let r = transform(
            &mut c,
            [0.7071, 0.7071, 0.0],
            [-0.7071, 0.7071, 0.0],
            [0.0, 0.0, 1.0],
            1.0,
            [0.0; 3],
        );
        assert!(r.is_err());
    }

    #[test]
    fn node_packing_matches_chasm_old() {
        // node 0 of Chasm_old: plane 15, back none, front node 1.
        let c = Collision {
            bsp3d_nodes: vec![crate::ce::Bsp3dNode {
                plane: 15,
                back: -1,
                front: 1,
            }],
            ..Default::default()
        };
        let p = pack(&c, &|m| m).unwrap();
        let word = u64::from_le_bytes(p.bsp3d_nodes[..8].try_into().unwrap());
        assert_eq!(word, 0x000001ffffff000f);
    }

    #[test]
    fn leaf_children_carry_bit_23() {
        let c = Collision {
            bsp3d_nodes: vec![crate::ce::Bsp3dNode {
                plane: 17,
                back: -1,
                front: 0x8000_0000u32 as i32,
            }],
            ..Default::default()
        };
        let p = pack(&c, &|m| m).unwrap();
        let word = u64::from_le_bytes(p.bsp3d_nodes[..8].try_into().unwrap());
        assert_eq!(word, 0x800000ffffff0011);
    }

    #[test]
    fn plane_flip_becomes_sign_or_flag() {
        assert_eq!(plane16(0x8000_0000u32 as i32), -32768);
        assert_eq!(plane16(7), 7);
        let s = Surface {
            plane: 0x8000_0005u32 as i32,
            first_edge: 0,
            flags: 1,
            breakable: -1,
            material: 0,
        };
        let b = surface16(&s, &|m| m);
        assert_eq!(u16::from_le_bytes([b[0], b[1]]), 5);
        assert_eq!(u16::from_le_bytes([b[10], b[11]]), 0x81);
    }

    #[test]
    fn surface_references_keep_the_sign_bit() {
        assert_eq!(child16(0x8000_0018u32 as i32), -32744);
        assert_eq!(child16(3), 3);
        assert_eq!(child16(-1), -1);
    }
}
