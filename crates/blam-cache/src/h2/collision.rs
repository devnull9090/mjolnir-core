//! Halo 2 collision BSPs, widened into the classic CE element layout the
//! staging carries (`collision_<i>.bin`, `layout: "ce_pc_v7"`).
//!
//! Halo 2 keeps the eight winged-edge tables of Halo 1 in narrower
//! encodings, the same family Meteorite's own BSPs use
//! (crates/blam-sbsp/src/pack16.rs). Element sizes and fields, checked on
//! Lockout's 3,162 surfaces (every polygon closes, winds counter-clockwise
//! about its plane once flipped, and lies within 2e-4 wu of it):
//!
//! | table | bytes | fields |
//! |---|---|---|
//! | bsp3d nodes | 8 | u16 plane, u24 back, u24 front (0xFFFFFF none, bit 23 leaf) |
//! | planes | 16 | f32 i, j, k, d |
//! | leaves | 4 | u8 flags, u8 2D reference count, u16 first 2D reference |
//! | bsp2d references | 4 | i16 plane (sign = flipped), i16 node (sign = surface) |
//! | bsp2d nodes | 16 | f32 i, j, d, i16 left, i16 right (sign = surface) |
//! | surfaces | 8 | u16 plane (0x8000 = flipped), u16 first edge, u8 flags, u8 breakable (255 none), u16 material (65535 none) |
//! | edges | 12 | u16 start, end, forward, reverse, left, right |
//! | vertices | 16 | f32 x, y, z, u16 first edge, u16 pad |
//!
//! The CE layout widens every index to i32, with -1 for none and
//! 0x8000_0000 marking a leaf, a surface or a flipped plane.

use crate::h2::Struct;

/// One collision BSP in CE form, plus the polygons a tail of standalone
/// surfaces adds (instanced geometry, scenery).
#[derive(Debug, Clone, Default)]
pub struct Collision {
    /// `[plane, back, front]`
    pub bsp3d_nodes: Vec<[i32; 3]>,
    pub planes: Vec<[f32; 4]>,
    /// `(flags, reference count, first reference)`
    pub leaves: Vec<(u16, i16, i32)>,
    /// `[plane, node]`
    pub bsp2d_references: Vec<[i32; 2]>,
    /// `(i, j, d, left, right)`
    pub bsp2d_nodes: Vec<([f32; 3], i32, i32)>,
    /// `(plane, first edge, flags, breakable, material)`
    pub surfaces: Vec<(i32, i32, u8, i8, i16)>,
    /// `[start, end, forward, reverse, left, right]`
    pub edges: Vec<[i32; 6]>,
    /// `(point, first edge)`
    pub vertices: Vec<([f32; 3], i32)>,
}

/// CE element sizes in `.bin` order (crates/blam-sbsp/src/ce.rs `CE_SIZES`).
pub const CE_SIZES: [usize; 8] = [12, 16, 8, 8, 20, 12, 24, 16];
pub const ARRAY_ORDER: [&str; 8] =
    ["bsp3d_nodes", "planes", "leaves", "bsp2d_references", "bsp2d_nodes", "surfaces", "edges", "vertices"];

/// Surface flag bit 0: two-sided (CE and Halo 2 agree on bits 0-3: two
/// sided, invisible, climbable, breakable).
pub const TWO_SIDED: u8 = 1;

fn child24(v: u32) -> i32 {
    if v == 0xFF_FFFF {
        -1
    } else if v & 0x80_0000 != 0 {
        (0x8000_0000 | (v & 0x7F_FFFF)) as i32
    } else {
        v as i32
    }
}

fn signed16(v: i16) -> i32 {
    if v == -1 {
        -1
    } else if v < 0 {
        (0x8000_0000 | (v as u16 & 0x7FFF) as u32) as i32
    } else {
        v as i32
    }
}

fn index16(v: u16) -> i32 {
    if v == u16::MAX {
        -1
    } else {
        v as i32
    }
}

/// Read the collision BSP element at `bsp` (64 bytes: eight blocks).
pub fn read(bsp: Struct<'_>) -> Collision {
    let mut c = Collision::default();
    for e in bsp.block(0x00, 8).iter() {
        let w = u64::from_le_bytes(e.bytes(0, 8).try_into().unwrap());
        c.bsp3d_nodes.push([
            (w & 0xFFFF) as i32,
            child24(((w >> 16) & 0xFF_FFFF) as u32),
            child24(((w >> 40) & 0xFF_FFFF) as u32),
        ]);
    }
    for e in bsp.block(0x08, 16).iter() {
        c.planes.push([e.f32(0), e.f32(4), e.f32(8), e.f32(12)]);
    }
    for e in bsp.block(0x10, 4).iter() {
        c.leaves.push((e.u8(0) as u16, e.u8(1) as i16, e.u16(2) as i32));
    }
    for e in bsp.block(0x18, 4).iter() {
        c.bsp2d_references.push([signed16(e.i16(0)), signed16(e.i16(2))]);
    }
    for e in bsp.block(0x20, 16).iter() {
        c.bsp2d_nodes.push(([e.f32(0), e.f32(4), e.f32(8)], signed16(e.i16(12)), signed16(e.i16(14))));
    }
    for e in bsp.block(0x28, 8).iter() {
        let p = e.u16(0);
        let plane = (p & 0x7FFF) as u32 | if p & 0x8000 != 0 { 0x8000_0000 } else { 0 };
        let breakable = if e.u8(5) == 0xFF { -1 } else { e.u8(5) as i8 };
        c.surfaces.push((plane as i32, index16(e.u16(2)), e.u8(4) & 0x0F, breakable, e.u16(6) as i16));
    }
    for e in bsp.block(0x30, 12).iter() {
        c.edges.push([
            index16(e.u16(0)),
            index16(e.u16(2)),
            index16(e.u16(4)),
            index16(e.u16(6)),
            index16(e.u16(8)),
            index16(e.u16(10)),
        ]);
    }
    for e in bsp.block(0x38, 16).iter() {
        c.vertices.push((e.vec3(0), index16(e.u16(12))));
    }
    c
}

impl Collision {
    /// The vertices of one surface, walking its edge ring.
    pub fn polygon(&self, surface: usize) -> Vec<[f32; 3]> {
        let mut pts = Vec::new();
        let Some(&(_, first, ..)) = self.surfaces.get(surface) else { return pts };
        if first < 0 {
            return pts;
        }
        let mut e = first as usize;
        for _ in 0..256 {
            let Some(edge) = self.edges.get(e) else { break };
            let (v, next) = if edge[4] == surface as i32 { (edge[0], edge[2]) } else { (edge[1], edge[3]) };
            if let Some(vx) = self.vertices.get(v.max(0) as usize) {
                pts.push(vx.0);
            }
            if next < 0 || next as usize == first as usize {
                break;
            }
            e = next as usize;
        }
        pts
    }

    /// Append a standalone polygon (fan-split into triangles): its own
    /// plane, a closed edge ring and its own vertices per triangle, as
    /// tools/level/merge_ce_collision.py appends scenery. No leaf references
    /// it; `mjolnir level collision` links the tail into the tree.
    pub fn push_standalone(&mut self, pts: &[[f32; 3]], flags: u8, material: i16) -> usize {
        let mut added = 0;
        for k in 1..pts.len().saturating_sub(1) {
            let tri = [pts[0], pts[k], pts[k + 1]];
            let u = sub(tri[1], tri[0]);
            let v = sub(tri[2], tri[0]);
            let n = cross(u, v);
            let len = (n[0] * n[0] + n[1] * n[1] + n[2] * n[2]).sqrt();
            if len < 1e-6 {
                continue;
            }
            let n = [n[0] / len, n[1] / len, n[2] / len];
            let d = n[0] * tri[0][0] + n[1] * tri[0][1] + n[2] * tri[0][2];
            let plane = self.planes.len() as i32;
            self.planes.push([n[0], n[1], n[2], d]);
            let s = self.surfaces.len() as i32;
            let e0 = self.edges.len() as i32;
            let v0 = self.vertices.len() as i32;
            for i in 0..3 {
                self.vertices.push((tri[i], e0 + i as i32));
                // Edge i runs vertex i -> i+1; the surface is on its left and
                // the next edge of the ring is the forward link.
                self.edges.push([v0 + i as i32, v0 + ((i + 1) % 3) as i32, e0 + ((i + 1) % 3) as i32, -1, s, -1]);
            }
            self.surfaces.push((plane, e0, flags, -1, material));
            added += 1;
        }
        added
    }

    /// The `.bin` bytes: each array a u32 count and its CE elements.
    pub fn to_bin(&self) -> Vec<u8> {
        let mut b = Vec::new();
        let n = |b: &mut Vec<u8>, c: usize| b.extend_from_slice(&(c as u32).to_le_bytes());
        let i = |b: &mut Vec<u8>, v: i32| b.extend_from_slice(&v.to_le_bytes());
        let f = |b: &mut Vec<u8>, v: f32| b.extend_from_slice(&v.to_le_bytes());
        n(&mut b, self.bsp3d_nodes.len());
        for x in &self.bsp3d_nodes {
            x.iter().for_each(|&v| i(&mut b, v));
        }
        n(&mut b, self.planes.len());
        for x in &self.planes {
            x.iter().for_each(|&v| f(&mut b, v));
        }
        n(&mut b, self.leaves.len());
        for &(flags, count, first) in &self.leaves {
            b.extend_from_slice(&flags.to_le_bytes());
            b.extend_from_slice(&count.to_le_bytes());
            i(&mut b, first);
        }
        n(&mut b, self.bsp2d_references.len());
        for x in &self.bsp2d_references {
            x.iter().for_each(|&v| i(&mut b, v));
        }
        n(&mut b, self.bsp2d_nodes.len());
        for (p, l, r) in &self.bsp2d_nodes {
            p.iter().for_each(|&v| f(&mut b, v));
            i(&mut b, *l);
            i(&mut b, *r);
        }
        n(&mut b, self.surfaces.len());
        for &(plane, edge, flags, breakable, material) in &self.surfaces {
            i(&mut b, plane);
            i(&mut b, edge);
            b.push(flags);
            b.push(breakable as u8);
            b.extend_from_slice(&material.to_le_bytes());
        }
        n(&mut b, self.edges.len());
        for x in &self.edges {
            x.iter().for_each(|&v| i(&mut b, v));
        }
        n(&mut b, self.vertices.len());
        for (p, e) in &self.vertices {
            p.iter().for_each(|&v| f(&mut b, v));
            i(&mut b, *e);
        }
        b
    }

    pub fn bounds(&self) -> Option<([f32; 3], [f32; 3])> {
        let mut it = self.vertices.iter().map(|v| v.0);
        let first = it.next()?;
        Some(it.fold((first, first), |(lo, hi), p| {
            ([lo[0].min(p[0]), lo[1].min(p[1]), lo[2].min(p[2])], [hi[0].max(p[0]), hi[1].max(p[1]), hi[2].max(p[2])])
        }))
    }

    pub fn counts(&self) -> [usize; 8] {
        [
            self.bsp3d_nodes.len(),
            self.planes.len(),
            self.leaves.len(),
            self.bsp2d_references.len(),
            self.bsp2d_nodes.len(),
            self.surfaces.len(),
            self.edges.len(),
            self.vertices.len(),
        ]
    }
}

fn sub(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
}

fn cross(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The widening keeps "none", leaf and flip marks where the CE layout
    /// puts them.
    #[test]
    fn narrow_indices_widen_to_the_ce_marks() {
        assert_eq!(child24(0xFF_FFFF), -1);
        assert_eq!(child24(0x80_0005) as u32, 0x8000_0005);
        assert_eq!(child24(17), 17);
        assert_eq!(signed16(-1), -1);
        assert_eq!(signed16(0x8003u16 as i16) as u32, 0x8000_0003);
        assert_eq!(index16(u16::MAX), -1);
    }

    /// A standalone quad becomes two triangles whose rings close and whose
    /// planes hold their own vertices; the .bin has the CE element sizes.
    #[test]
    fn a_standalone_quad_is_two_closed_triangles() {
        let mut c = Collision::default();
        let quad = [[0.0, 0.0, 1.0], [2.0, 0.0, 1.0], [2.0, 2.0, 1.0], [0.0, 2.0, 1.0]];
        assert_eq!(c.push_standalone(&quad, TWO_SIDED, 3), 2);
        for s in 0..2 {
            let poly = c.polygon(s);
            assert_eq!(poly.len(), 3);
            let p = c.planes[c.surfaces[s].0 as usize];
            assert_eq!(p, [0.0, 0.0, 1.0, 1.0]);
            for v in poly {
                assert!((p[0] * v[0] + p[1] * v[1] + p[2] * v[2] - p[3]).abs() < 1e-6);
            }
        }
        let expected: usize = c.counts().iter().zip(CE_SIZES).map(|(n, s)| 4 + n * s).sum();
        assert_eq!(c.to_bin().len(), expected);
    }
}
