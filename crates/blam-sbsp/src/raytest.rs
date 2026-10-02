//! Cast rays through a collision BSP the way a Blam line test resolves a hit,
//! and check the answers against brute-force ray/polygon intersection.
//!
//! The tree walk is the classic one: follow the segment down the bsp3d tree,
//! splitting it at each node plane it crosses, near side first. Arriving in
//! solid space (`-1`) is a hit on the plane crossed last, and the surface is
//! the one the leaf the ray was in names for that plane: its 2D reference for
//! the plane, descended with the hit point projected into the plane.
//!
//! A standing test only classifies a point; a moving pawn sweeps. So a tree
//! that holds a pawn at rest can still let it through once it moves, and this
//! is the offline check for that: every ray the polygons say hits something
//! must also hit through the tree, on a surface at the same place.

use crate::ce::{Bounds, Collision};
use crate::pack16::projection_axes;
use crate::unpack16;

const LEAF: u32 = 0x8000_0000;

#[derive(Debug, Clone, Copy)]
pub struct Hit {
    /// Fraction of the segment.
    pub t: f32,
    pub surface: usize,
}

fn dot(a: [f32; 3], b: [f32; 3]) -> f32 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

fn at(o: [f32; 3], d: [f32; 3], t: f32) -> [f32; 3] {
    [o[0] + d[0] * t, o[1] + d[1] * t, o[2] + d[2] * t]
}

/// Signed distance of `p` from a bsp3d node's plane, flip bit applied.
fn node_distance(c: &Collision, plane: i32, p: [f32; 3]) -> Option<f32> {
    let pl = c.planes.get((plane as u32 & 0x7fff_ffff) as usize)?;
    let d = dot(pl.n, p) - pl.d;
    Some(if (plane as u32) & LEAF != 0 { -d } else { d })
}

/// The surface a leaf names at `p` on plane `plane` (index, sign ignored).
pub fn leaf_surface(c: &Collision, leaf: usize, plane: usize, p: [f32; 3]) -> Option<usize> {
    let lf = c.leaves.get(leaf)?;
    for k in 0..lf.reference_count.max(0) as usize {
        let r = c.bsp2d_references.get(lf.first_reference as usize + k)?;
        if (r.plane as u32 & 0x7fff_ffff) as usize != plane {
            continue;
        }
        let pl = c.planes.get(plane)?;
        let mut n = pl.n;
        if (r.plane as u32) & LEAF != 0 {
            n = [-n[0], -n[1], -n[2]];
        }
        let (u, v) = projection_axes(n);
        let mut cur = r.node;
        for _ in 0..1024 {
            if cur == -1 {
                return None;
            }
            if (cur as u32) & LEAF != 0 {
                return Some((cur as u32 & 0x7fff_ffff) as usize);
            }
            let node = c.bsp2d_nodes.get(cur as usize)?;
            let d = node.plane[0] * p[u] + node.plane[1] * p[v] - node.plane[2];
            cur = if d >= 0.0 { node.right } else { node.left };
        }
        return None;
    }
    None
}

struct Walk<'c> {
    c: &'c Collision,
    o: [f32; 3],
    d: [f32; 3],
    leaf: Option<usize>,
    plane: Option<usize>,
}

impl Walk<'_> {
    /// Whether the ray meets surface `s` from a side that collides.
    fn faces(&self, s: usize) -> bool {
        let Some(surf) = self.c.surfaces.get(s) else {
            return false;
        };
        if surf.flags & 1 != 0 {
            return true;
        }
        let Some(pl) = self
            .c
            .planes
            .get((surf.plane as u32 & 0x7fff_ffff) as usize)
        else {
            return false;
        };
        let mut n = pl.n;
        if (surf.plane as u32) & LEAF != 0 {
            n = [-n[0], -n[1], -n[2]];
        }
        dot(n, self.d) < 0.0
    }

    /// `Err` carries the first hit, which stops the walk.
    fn rec(&mut self, node: i32, t0: f32, t1: f32, depth: usize) -> Result<(), Option<Hit>> {
        if depth > 1024 {
            return Err(None);
        }
        if node == -1 {
            // Solid: a hit on the plane just crossed, if the ray came from a
            // leaf. A ray that starts in solid reports nothing.
            let (Some(leaf), Some(plane)) = (self.leaf, self.plane) else {
                return Ok(());
            };
            let p = at(self.o, self.d, t0);
            let surface = leaf_surface(self.c, leaf, plane, p);
            return Err(surface.map(|surface| Hit { t: t0, surface }));
        }
        if (node as u32) & LEAF != 0 {
            self.leaf = Some((node as u32 & 0x7fff_ffff) as usize);
            return Ok(());
        }
        let n = self.c.bsp3d_nodes.get(node as usize).ok_or(None)?;
        let d0 = node_distance(self.c, n.plane, at(self.o, self.d, t0)).ok_or(None)?;
        let d1 = node_distance(self.c, n.plane, at(self.o, self.d, t1)).ok_or(None)?;
        if d0 >= 0.0 && d1 >= 0.0 {
            return self.rec(n.front, t0, t1, depth + 1);
        }
        if d0 < 0.0 && d1 < 0.0 {
            return self.rec(n.back, t0, t1, depth + 1);
        }
        let tm = t0 + (t1 - t0) * (d0 / (d0 - d1));
        let (near, far) = if d0 >= 0.0 {
            (n.front, n.back)
        } else {
            (n.back, n.front)
        };
        self.rec(near, t0, tm, depth + 1)?;
        let plane = (n.plane as u32 & 0x7fff_ffff) as usize;
        self.plane = Some(plane);
        // Crossing between two open leaves still hits a surface lying on the
        // crossed plane there: thin floors, bridges and walkways have open
        // space on both sides. It counts from the surface's front, or from
        // either side of a two-sided one.
        if let Some(leaf) = self.leaf {
            let p = at(self.o, self.d, tm);
            if let Some(s) = leaf_surface(self.c, leaf, plane, p) {
                if self.faces(s) {
                    return Err(Some(Hit { t: tm, surface: s }));
                }
            }
        }
        self.rec(far, tm, t1, depth + 1)
    }
}

/// The first surface the segment `o .. o + d` hits through the tree.
pub fn tree(c: &Collision, o: [f32; 3], d: [f32; 3]) -> Option<Hit> {
    if c.bsp3d_nodes.is_empty() {
        return None;
    }
    let mut w = Walk {
        c,
        o,
        d,
        leaf: None,
        plane: None,
    };
    match w.rec(0, 0.0, 1.0, 0) {
        Ok(()) => None,
        Err(hit) => hit,
    }
}

/// The first polygon the segment hits, by testing every one (fan
/// triangulated, both faces).
pub fn brute(c: &Collision, polys: &[Vec<[f32; 3]>], o: [f32; 3], d: [f32; 3]) -> Option<Hit> {
    let _ = c;
    let mut best: Option<Hit> = None;
    for (s, poly) in polys.iter().enumerate() {
        for k in 1..poly.len().saturating_sub(1) {
            if let Some(t) = ray_triangle(o, d, poly[0], poly[k], poly[k + 1]) {
                if (0.0..=1.0).contains(&t) && best.map_or(true, |b| t < b.t) {
                    best = Some(Hit { t, surface: s });
                }
            }
        }
    }
    best
}

fn ray_triangle(o: [f32; 3], d: [f32; 3], a: [f32; 3], b: [f32; 3], c: [f32; 3]) -> Option<f32> {
    let e1 = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    let e2 = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
    let p = [
        d[1] * e2[2] - d[2] * e2[1],
        d[2] * e2[0] - d[0] * e2[2],
        d[0] * e2[1] - d[1] * e2[0],
    ];
    let det = dot(e1, p);
    if det.abs() < 1e-9 {
        return None;
    }
    let inv = 1.0 / det;
    let s = [o[0] - a[0], o[1] - a[1], o[2] - a[2]];
    let u = dot(s, p) * inv;
    if !(-1e-4..=1.0 + 1e-4).contains(&u) {
        return None;
    }
    let q = [
        s[1] * e1[2] - s[2] * e1[1],
        s[2] * e1[0] - s[0] * e1[2],
        s[0] * e1[1] - s[1] * e1[0],
    ];
    let v = dot(d, q) * inv;
    if v < -1e-4 || u + v > 1.0 + 1e-4 {
        return None;
    }
    Some(dot(e2, q) * inv)
}

#[derive(Debug, Clone, Default)]
pub struct Report {
    pub rays: usize,
    /// Rays the polygons say hit something.
    pub expected: usize,
    /// Of those, rays the tree let through.
    pub missed: usize,
    /// Rays the tree stopped more than `tolerance` away from the true hit.
    pub displaced: usize,
    /// Rays the tree stopped although no polygon is on the segment.
    pub phantom: usize,
    /// A few missed rays, as (origin, end) pairs, to look at.
    pub examples: Vec<([f32; 3], [f32; 3])>,
}

/// Compare the tree with the polygons over a set of segments.
pub fn compare(c: &Collision, rays: &[([f32; 3], [f32; 3])], tolerance: f32) -> Report {
    let polys: Vec<Vec<[f32; 3]>> = (0..c.surfaces.len())
        .map(|s| unpack16::polygon(c, s))
        .collect();
    let mut r = Report {
        rays: rays.len(),
        ..Default::default()
    };
    for &(o, e) in rays {
        let d = [e[0] - o[0], e[1] - o[1], e[2] - o[2]];
        let len = dot(d, d).sqrt();
        let truth = brute(c, &polys, o, d);
        let got = tree(c, o, d);
        match (truth, got) {
            (Some(_), None) => {
                r.expected += 1;
                r.missed += 1;
                if r.examples.len() < 8 {
                    r.examples.push((o, e));
                }
            }
            (Some(t), Some(g)) => {
                r.expected += 1;
                if ((t.t - g.t) * len).abs() > tolerance {
                    r.displaced += 1;
                }
            }
            (None, Some(_)) => r.phantom += 1,
            (None, None) => {}
        }
    }
    r
}

/// The leaf a point falls in, or `None` in solid space.
pub fn classify(c: &Collision, p: [f32; 3]) -> Option<usize> {
    let mut cur: i32 = 0;
    for _ in 0..1024 {
        if cur == -1 {
            return None;
        }
        if (cur as u32) & LEAF != 0 {
            return Some((cur as u32 & 0x7fff_ffff) as usize);
        }
        let n = c.bsp3d_nodes.get(cur as usize)?;
        cur = if node_distance(c, n.plane, p)? >= 0.0 {
            n.front
        } else {
            n.back
        };
    }
    None
}

/// Walkable floor points on a grid over `b`, `step` apart: every place a
/// vertical line crosses an upward-facing polygon (normal z > 0.5) with open
/// space (a leaf, by the tree's own point test) `clearance` above it.
pub fn floors(c: &Collision, b: Bounds, step: f32, clearance: f32) -> Vec<[f32; 3]> {
    let polys: Vec<Vec<[f32; 3]>> = (0..c.surfaces.len())
        .map(|s| unpack16::polygon(c, s))
        .collect();
    let mut out = Vec::new();
    let mut x = b.min[0] + step * 0.5;
    while x < b.max[0] {
        let mut y = b.min[1] + step * 0.5;
        while y < b.max[1] {
            let o = [x, y, b.max[2] + 1.0];
            let d = [0.0, 0.0, b.min[2] - b.max[2] - 2.0];
            for poly in &polys {
                if poly.len() < 3 {
                    continue;
                }
                let e1 = [
                    poly[1][0] - poly[0][0],
                    poly[1][1] - poly[0][1],
                    poly[1][2] - poly[0][2],
                ];
                let e2 = [
                    poly[2][0] - poly[0][0],
                    poly[2][1] - poly[0][1],
                    poly[2][2] - poly[0][2],
                ];
                let n = [
                    e1[1] * e2[2] - e1[2] * e2[1],
                    e1[2] * e2[0] - e1[0] * e2[2],
                    e1[0] * e2[1] - e1[1] * e2[0],
                ];
                let len = dot(n, n).sqrt();
                if len < 1e-9 || n[2].abs() / len < 0.5 {
                    continue;
                }
                for k in 1..poly.len() - 1 {
                    if let Some(t) = ray_triangle(o, d, poly[0], poly[k], poly[k + 1]) {
                        if (0.0..=1.0).contains(&t) {
                            let f = at(o, d, t);
                            if classify(c, [f[0], f[1], f[2] + clearance]).is_some() {
                                out.push(f);
                            }
                        }
                    }
                }
            }
            y += step;
        }
        x += step;
    }
    out
}

/// From `height` above each floor point: straight down, and slanted `reach`
/// sideways in eight directions, each ending `height` below the floor.
pub fn floor_rays(
    points: &[[f32; 3]],
    height: f32,
    reach: f32,
) -> (Vec<([f32; 3], [f32; 3])>, Vec<([f32; 3], [f32; 3])>) {
    let mut down = Vec::new();
    let mut slanted = Vec::new();
    for f in points {
        let s = [f[0], f[1], f[2] + height];
        down.push((s, [f[0], f[1], f[2] - height]));
        for k in 0..8 {
            let a = k as f32 * std::f32::consts::FRAC_PI_4;
            slanted.push((
                s,
                [
                    s[0] + reach * a.cos(),
                    s[1] + reach * a.sin(),
                    f[2] - height,
                ],
            ));
        }
    }
    (down, slanted)
}
