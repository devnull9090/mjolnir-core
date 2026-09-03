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

/// Translate every vertex, plane and 2D plane by `delta` (world units): the
/// probe path that moves a donor shell under the player without touching its
/// topology. A plane `n·x = d` moved by `t` becomes `n·x = d + n·t`; a 2D
/// plane lives in the projection of its parent 3D plane, which the packed
/// tables do not name, so 2D planes are left alone — they only decide which
/// surface a point already known to be on the 3D plane belongs to, and the
/// projection is translation-invariant up to the same offset for every
/// surface in that plane.
pub fn translate(c: &mut Collision, delta: [f32; 3]) {
    for v in &mut c.vertices {
        for a in 0..3 {
            v.point[a] += delta[a];
        }
    }
    for p in &mut c.planes {
        p.d += p.n[0] * delta[0] + p.n[1] * delta[1] + p.n[2] * delta[2];
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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
