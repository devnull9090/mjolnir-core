//! AI pathfinding data for a structure BSP's collision shell: the scenario's
//! `ai pathfinding data[bsp]` tables, built from the shell so the simulation's
//! AI can walk a converted map (docs/re/ai_in_multiplayer.md).
//!
//! The layout, read off B40's shipped data:
//!
//! - a **sector** is a convex walkable area (`flags`, `hint index`, `first
//!   link`); here every walkable shell surface is one sector, so a surface
//!   names its sector directly;
//! - a **link** is a winged edge between sectors: `vertex 1 -> vertex 2` runs
//!   around its `left sector`, `forward link` is the next link around the left
//!   sector and `reverse link` the next around the right one (`-1` and
//!   `right sector -1` on a boundary), exactly CE's collision edge rings;
//! - **bsp2d refs** hold one entry per shell surface: a sector index, `-1`
//!   for a surface no AI stands on, or `0x8000_0000 | node` into `bsp2d
//!   nodes` when a surface spans several sectors (never, here);
//! - **vertices** are world-space points the links index.
//!
//! **Steps.** A floor meets the next only across a shared edge, so a riser
//! between two floors would cut the ground in two. B40 makes a short riser a
//! sector of its own, flagged `sector step` and the wall it faces, linked to
//! the floors above and below through its edges like any other sector. So does
//! this, for a surface too steep to be a floor that rises less than
//! [`STEP_HEIGHT`]: steps that share an edge join while together they still
//! rise less than that, and a joined set counts only if it rises from a floor
//! and reaches one. So a wall cut into short bands does not become a
//! staircase, and the side face of a slab, hanging below the one floor it
//! touches, stays a ledge. Where two steps do not join, each keeps its own
//! link along their edge.
//!
//! **Cracks.** Converted maps are often built of separate slabs: a floor ends
//! in its slab's own side face, and the next slab's floor starts edge to edge
//! with it, a hair inside it, or across a crack, never sharing an edge. B40
//! joins sectors on separate geometry the same way it would here, with
//! *intersection links*: each sector keeps its own boundary link along the
//! seam, flagged `sector intersection link` and given a hint of its own (type
//! `intersection link`, data `(joining link, 0, 0, 0)`), and the two hints
//! name one two-sided link appended after all the others, which runs along
//! the first sector's link (its vertices, its `forward link`) and carries the
//! second's `forward link` as its `reverse link`. A sector's `hint index`
//! heads a chain (`next hint index`) of exactly its own links' hints. Two
//! floor edges become such a seam where both drop away (nothing beyond, or a
//! surface no higher than the edge), they run opposite ways within
//! [`CRACK_WIDTH`] of each other and less than [`STEP_HEIGHT`] apart in
//! height, and overlap by [`CRACK_OVERLAP`]; each link is first cut at the
//! overlap's ends, so the seam is exactly the stretch both floors share.
//! Floors on either side of a wall never pair: their edges rise into it.
//!
//! The scenario's `structure bsps[i].flags` bit `no default structure
//! pathfinding` (0x8) must be clear for the shell's refs to count; B40 sets it
//! because its own sectors all lie on instanced geometry.

use crate::ce::{Collision, Edge};

/// `sector walkable | floor`, B40's flags for a plain floor sector.
pub const SECTOR_FLOOR: u16 = 0x11;
/// `sector walkable | sector step`, B40's flags for a riser short enough to
/// walk over; [`step_flags`] adds the wall it faces.
pub const SECTOR_STEP: u16 = 0x1001;
/// `sector intersection link`: a boundary link whose hint names the link
/// that joins its sector to one on other geometry.
pub const LINK_INTERSECTION: u16 = 0x2;
/// `sector link wall base`: the far side of the edge is a wall.
pub const LINK_WALL_BASE: u16 = 0x40;
/// `sector link ledge`: the far side drops away or is open.
pub const LINK_LEDGE: u16 = 0x80;
/// The `pathfinding hints` type `intersection link`.
pub const HINT_INTERSECTION: i16 = 0;

/// The steepest floor an AI walks: a normal at most ~49 degrees off vertical.
pub const WALKABLE_NZ: f32 = 0.65;

/// The tallest riser an AI walks over: the shipped AI globals' `hoist step`
/// bounds start at 0.1 wu (anything taller is a hoist or a jump), as does
/// `max jump down height down`. B40's own steps rise 0.007 to 0.078 wu.
pub const STEP_HEIGHT: f32 = 0.1;

/// How far apart two floors' dropping edges may lie, across a crack or into
/// each other, and still be one seam to walk over. Night Lockout's slabs
/// meet edge to edge, overlap by 0.01 or leave cracks up to about this.
pub const CRACK_WIDTH: f32 = 0.1;
/// The shortest stretch two floors' edges must share to be a seam.
pub const CRACK_OVERLAP: f32 = 0.05;

#[derive(Debug, Clone, Copy)]
pub struct Sector {
    pub flags: u16,
    pub hint: i16,
    pub first_link: i32,
}

impl Sector {
    /// A floor, which firing positions and spawns stand on; else a step.
    pub fn is_floor(&self) -> bool {
        self.flags & 0x10 != 0
    }
}

#[derive(Debug, Clone, Copy)]
pub struct Link {
    pub v1: i16,
    pub v2: i16,
    pub flags: u16,
    pub hint: i16,
    pub forward: i16,
    pub reverse: i16,
    pub left: i16,
    pub right: i16,
}

/// A `pathfinding hints` element.
#[derive(Debug, Clone, Copy)]
pub struct Hint {
    pub kind: i16,
    pub next: i16,
    pub data: [i32; 4],
}

/// A point an AI may choose to stand at in combat, on a walkable surface.
#[derive(Debug, Clone, Copy)]
pub struct FiringPosition {
    pub point: [f32; 3],
    pub normal: [f32; 3],
    pub sector: usize,
}

#[derive(Debug, Clone, Default)]
pub struct Pathfinding {
    pub sectors: Vec<Sector>,
    pub links: Vec<Link>,
    /// One per shell surface: the sector, or -1.
    pub refs: Vec<i32>,
    pub vertices: Vec<[f32; 3]>,
    pub hints: Vec<Hint>,
    /// Crack seams left out to keep the indices within 16 bits.
    pub cracks_dropped: usize,
    /// The sector each shell surface became, if any.
    pub surface_sector: Vec<Option<usize>>,
    /// Sector index -> its shell surface.
    pub sector_surface: Vec<usize>,
    /// Connected component of each sector (links between walkable sectors).
    pub component: Vec<usize>,
}

/// A surface's outward normal: its plane's, negated when the surface's
/// plane reference carries the sign bit.
pub fn surface_normal(c: &Collision, surface: usize) -> [f32; 3] {
    let s = &c.surfaces[surface];
    let p = &c.planes[(s.plane as u32 & 0x7fff_ffff) as usize];
    if (s.plane as u32) & 0x8000_0000 != 0 {
        [-p.n[0], -p.n[1], -p.n[2]]
    } else {
        p.n
    }
}

fn walkable(c: &Collision, surface: usize) -> bool {
    let s = &c.surfaces[surface];
    // Breakable surfaces (bit 3) can vanish under an AI.
    s.first_edge >= 0 && s.flags & 0x8 == 0 && surface_normal(c, surface)[2] >= WALKABLE_NZ
}

/// A surface's z range.
fn z_range(c: &Collision, surface: usize) -> Option<[f32; 2]> {
    let poly = crate::unpack16::polygon(c, surface);
    (poly.len() >= 3).then(|| {
        poly.iter().fold([f32::MAX, f32::MIN], |[lo, hi], p| {
            [lo.min(p[2]), hi.max(p[2])]
        })
    })
}

/// Each surface's step set, for a surface that is a step. A step is too
/// steep to be a floor, not breakable, not facing down and rises less than
/// [`STEP_HEIGHT`]. Steps that share an edge fall into one set while the set
/// still rises less than that, and a set counts only if it rises from a
/// floor and reaches one: the side face of a slab, which only drops away
/// from the floor on top of it, is a ledge.
fn steps(c: &Collision, floor: &[bool]) -> Vec<Option<usize>> {
    let n = c.surfaces.len();
    let range: Vec<Option<[f32; 2]>> = (0..n)
        .map(|s| {
            if floor[s] || c.surfaces[s].flags & 0x8 != 0 || surface_normal(c, s)[2] <= -0.3 {
                return None;
            }
            z_range(c, s).filter(|r| r[1] - r[0] < STEP_HEIGHT)
        })
        .collect();
    let is_floor = |s: i32| s >= 0 && floor.get(s as usize).copied().unwrap_or(false);
    let step = |s: i32| {
        usize::try_from(s)
            .ok()
            .filter(|&s| range.get(s).is_some_and(Option::is_some))
    };
    // [rises from a floor, reaches a floor] along the step's edges.
    let mut meets = vec![[false; 2]; n];
    for e in &c.edges {
        let z = |v: i32| c.vertices[v as usize].point[2];
        let (top, bottom) = (z(e.start).max(z(e.end)), z(e.start).min(z(e.end)));
        for (s, other) in [(e.left, e.right), (e.right, e.left)] {
            if let (Some(s), true) = (step(s), is_floor(other)) {
                let r = range[s].unwrap();
                meets[s][0] |= r[1] > top + 0.002;
                meets[s][1] |= r[0] < bottom - 0.002;
            }
        }
    }
    let mut set: Vec<usize> = (0..n).collect();
    let mut span: Vec<[f32; 2]> = range.iter().map(|r| r.unwrap_or_default()).collect();
    for e in &c.edges {
        let (Some(a), Some(b)) = (step(e.left), step(e.right)) else {
            continue;
        };
        let (ra, rb) = (find(&mut set, a), find(&mut set, b));
        let r = [span[ra][0].min(span[rb][0]), span[ra][1].max(span[rb][1])];
        if ra != rb && r[1] - r[0] < STEP_HEIGHT {
            set[ra] = rb;
            span[rb] = r;
            meets[rb] = [meets[rb][0] | meets[ra][0], meets[rb][1] | meets[ra][1]];
        }
    }
    (0..n)
        .map(|s| {
            range[s]?;
            let root = find(&mut set, s);
            (meets[root] == [true; 2]).then_some(root)
        })
        .collect()
}

/// A step's flags: [`SECTOR_STEP`], the wall the riser faces (`wall east`
/// +x, `wall west` -x, `wall north` +y, `wall south` -y; B40's riser facing
/// -x is `wall west`), and `aligned` when it faces along that axis, as B40's
/// does.
pub fn step_flags(normal: [f32; 3]) -> u16 {
    let (x, y) = (normal[0].abs(), normal[1].abs());
    let (wall, off) = if x >= y {
        (if normal[0] < 0.0 { 0x200 } else { 0x100 }, y / x.max(1e-6))
    } else {
        (if normal[1] < 0.0 { 0x80 } else { 0x40 }, x / y)
    };
    SECTOR_STEP | wall | if off < 0.02 { 0x800 } else { 0 }
}

fn find(p: &mut [usize], x: usize) -> usize {
    let mut r = x;
    while p[r] != r {
        r = p[r];
    }
    let mut y = x;
    while p[y] != r {
        let nx = p[y];
        p[y] = r;
        y = nx;
    }
    r
}

/// Which sides of an edge a link carries.
#[derive(Clone, Copy)]
enum Carries {
    /// The left surface's ring, as the edge runs.
    Left,
    /// The right surface's ring, the edge turned round.
    Right,
    /// Both rings: the edge joins its two sectors.
    Both,
}

impl Pathfinding {
    /// Build the tables from a shell. Errors when the shell is too large for
    /// the 16-bit link and vertex indices.
    pub fn build(c: &Collision) -> Result<Self, String> {
        let n = c.surfaces.len();
        let floor: Vec<bool> = (0..n).map(|s| walkable(c, s)).collect();
        let step = steps(c, &floor);
        let mut pf = Pathfinding {
            surface_sector: vec![None; n],
            refs: vec![-1; n],
            ..Default::default()
        };
        for s in 0..n {
            let flags = if floor[s] {
                SECTOR_FLOOR
            } else if step[s].is_some() {
                step_flags(surface_normal(c, s))
            } else {
                continue;
            };
            pf.surface_sector[s] = Some(pf.sectors.len());
            pf.refs[s] = pf.sectors.len() as i32;
            pf.sector_surface.push(s);
            pf.sectors.push(Sector {
                flags,
                hint: -1,
                first_link: -1,
            });
        }
        if pf.sectors.len() > 65534 {
            return Err(format!(
                "{} walkable surfaces; a BSP holds at most 65534 sectors",
                pf.sectors.len()
            ));
        }
        let by_surface = pf.surface_sector.clone();
        let sector_of = |surface: i32| -> Option<usize> {
            if surface < 0 {
                None
            } else {
                by_surface.get(surface as usize).copied().flatten()
            }
        };

        // Two steps of different sets would together rise a step or more.
        let joined = |e: &Edge| {
            let (l, r) = (step[e.left as usize], step[e.right as usize]);
            l.is_none() || r.is_none() || l == r
        };

        // Every edge with a sector on a side gets a link: one that joins its
        // two sectors, or one per sector, oriented so the sector is on its
        // left. `ring[e]` is the link that carries the edge's left surface's
        // ring and the one that carries its right's.
        let mut ring = vec![[-1i32; 2]; c.edges.len()];
        let mut plan = Vec::new();
        for (e, edge) in c.edges.iter().enumerate() {
            let (l, r) = (sector_of(edge.left), sector_of(edge.right));
            if l.is_some() && r.is_some() && joined(edge) {
                ring[e] = [plan.len() as i32; 2];
                plan.push((e, Carries::Both));
                continue;
            }
            if l.is_some() {
                ring[e][0] = plan.len() as i32;
                plan.push((e, Carries::Left));
            }
            if r.is_some() {
                ring[e][1] = plan.len() as i32;
                plan.push((e, Carries::Right));
            }
        }
        if plan.len() > 32767 {
            return Err(format!(
                "{} links; the 16-bit link indices hold 32767",
                plan.len()
            ));
        }
        // The link that carries `surface`'s ring through edge `e`.
        let next = |e: i32, surface: i32| -> i16 {
            if e < 0 {
                return -1;
            }
            let side = usize::from(c.edges[e as usize].left != surface);
            ring[e as usize][side] as i16
        };
        // The flags of a link with nothing to its right: `far` is the
        // surface across the edge.
        let boundary = |far: i32| {
            if far >= 0 && surface_normal(c, far as usize)[2] > -0.3 {
                LINK_WALL_BASE
            } else {
                LINK_LEDGE
            }
        };
        let mut vertex_of = vec![-1i32; c.vertices.len()];
        let mut vertex = |v: i32, verts: &mut Vec<[f32; 3]>| -> Result<i16, String> {
            let v = v as usize;
            if vertex_of[v] < 0 {
                vertex_of[v] = verts.len() as i32;
                verts.push(c.vertices[v].point);
            }
            i16::try_from(vertex_of[v])
                .map_err(|_| "more than 32767 pathfinding vertices".to_string())
        };
        let mut verts = Vec::new();
        // The surface across each link with nothing to its right (-1: none).
        let mut far = Vec::with_capacity(plan.len());
        for &(e, carries) in &plan {
            let edge = &c.edges[e];
            far.push(match carries {
                Carries::Both => None,
                Carries::Left => Some(edge.right),
                Carries::Right => Some(edge.left),
            });
            // In edge terms: `forward` continues the left surface's ring,
            // `reverse` the right's.
            let (start, end, ls, rs, lnext, rnext, flags) = match carries {
                Carries::Both => (
                    edge.start,
                    edge.end,
                    edge.left,
                    edge.right,
                    edge.forward,
                    edge.reverse,
                    0,
                ),
                Carries::Left => (
                    edge.start,
                    edge.end,
                    edge.left,
                    -1,
                    edge.forward,
                    -1,
                    boundary(edge.right),
                ),
                Carries::Right => (
                    edge.end,
                    edge.start,
                    edge.right,
                    -1,
                    edge.reverse,
                    -1,
                    boundary(edge.left),
                ),
            };
            let left = sector_of(ls).expect("left side is a sector");
            let right = sector_of(rs);
            let link = Link {
                v1: vertex(start, &mut verts)?,
                v2: vertex(end, &mut verts)?,
                flags,
                hint: -1,
                forward: next(lnext, ls),
                reverse: next(rnext, rs),
                left: left as i16,
                right: right.map_or(-1, |r| r as i16),
            };
            let id = pf.links.len() as i32;
            for s in [Some(left), right].into_iter().flatten() {
                if pf.sectors[s].first_link < 0 {
                    pf.sectors[s].first_link = id;
                }
            }
            pf.links.push(link);
        }
        pf.vertices = verts;
        pf.join_cracks(c, &far)?;

        // Components over sector-to-sector links.
        let mut parent: Vec<usize> = (0..pf.sectors.len()).collect();
        for l in &pf.links {
            if l.right >= 0 {
                let (a, b) = (
                    find(&mut parent, l.left as usize),
                    find(&mut parent, l.right as usize),
                );
                if a != b {
                    parent[a] = b;
                }
            }
        }
        pf.component = (0..pf.sectors.len())
            .map(|s| find(&mut parent, s))
            .collect();
        Ok(pf)
    }

    /// Join floors across cracks with intersection links (the module docs
    /// say how). `far[k]` is the surface across link `k`'s edge (-1: none)
    /// for each link with nothing to its right.
    fn join_cracks(&mut self, c: &Collision, far: &[Option<i32>]) -> Result<(), String> {
        /// A floor link whose edge drops away, as a 2D segment.
        struct Seg {
            link: usize,
            a: [f32; 3],
            b: [f32; 3],
            u: [f32; 2],
            len: f32,
        }
        /// Two segments' shared stretch, in each one's distance from its
        /// start.
        struct Seam {
            i: usize,
            j: usize,
            ti: [f32; 2],
            tj: [f32; 2],
            score: f32,
        }
        let mut segs = Vec::new();
        for (k, l) in self.links.iter().enumerate() {
            let Some(far) = far[k] else { continue };
            if !self.sectors[l.left as usize].is_floor() {
                continue;
            }
            let (a, b) = (self.vertices[l.v1 as usize], self.vertices[l.v2 as usize]);
            let top = a[2].max(b[2]);
            if far >= 0 && z_range(c, far as usize).is_none_or(|r| r[1] > top + 0.01) {
                continue;
            }
            let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
            let len = (dx * dx + dy * dy).sqrt();
            if len > 1e-4 {
                let u = [dx / len, dy / len];
                segs.push(Seg {
                    link: k,
                    a,
                    b,
                    u,
                    len,
                });
            }
        }
        let at = |s: &Seg, t: f32| {
            let f = t / s.len;
            [0, 1, 2].map(|k| s.a[k] + (s.b[k] - s.a[k]) * f)
        };

        // Segments by 1 wu cell, sampled along their length.
        let mut grid: std::collections::HashMap<(i32, i32), Vec<usize>> = Default::default();
        for (i, s) in segs.iter().enumerate() {
            let mut cells = Vec::new();
            for n in 0..=(s.len / 0.5).ceil() as usize {
                let p = at(s, (n as f32 * 0.5).min(s.len));
                for dx in [-CRACK_WIDTH, CRACK_WIDTH] {
                    for dy in [-CRACK_WIDTH, CRACK_WIDTH] {
                        cells.push(((p[0] + dx).floor() as i32, (p[1] + dy).floor() as i32));
                    }
                }
            }
            cells.sort_unstable();
            cells.dedup();
            for cell in cells {
                grid.entry(cell).or_default().push(i);
            }
        }
        let seam = |i: usize, j: usize| -> Option<Seam> {
            let (p, q) = (&segs[i], &segs[j]);
            if self.links[p.link].left == self.links[q.link].left
                || p.u[0] * q.u[0] + p.u[1] * q.u[1] > -0.98
            {
                return None;
            }
            // Where q runs along p, in p's distance.
            let t = |x: [f32; 3]| (x[0] - p.a[0]) * p.u[0] + (x[1] - p.a[1]) * p.u[1];
            let (ta, tb) = (t(q.a), t(q.b));
            let (lo, hi) = (ta.min(tb).max(0.0), ta.max(tb).min(p.len));
            if hi - lo < CRACK_OVERLAP {
                return None;
            }
            // q's distance at p's ends of the stretch; q runs the other way.
            let on_q = |s: f32| {
                let x = at(p, s);
                ((x[0] - q.a[0]) * q.u[0] + (x[1] - q.a[1]) * q.u[1]).clamp(0.0, q.len)
            };
            let (qa, qb) = (on_q(lo), on_q(hi));
            // How far q lies outside p's floor (to its right) at both ends,
            // and how far apart in height.
            let out = |x: [f32; 3]| (x[0] - p.a[0]) * p.u[1] - (x[1] - p.a[1]) * p.u[0];
            let (oa, ob) = (out(at(q, qa)), out(at(q, qb)));
            let dz = (at(p, lo)[2] - at(q, qa)[2])
                .abs()
                .max((at(p, hi)[2] - at(q, qb)[2]).abs());
            if oa.abs().max(ob.abs()) > CRACK_WIDTH || dz >= STEP_HEIGHT {
                return None;
            }
            let score = (oa.abs() + ob.abs()) / 2.0 + dz;
            Some(Seam {
                i,
                j,
                ti: [lo, hi],
                tj: [qb, qa],
                score,
            })
        };
        let mut found = Vec::new();
        let mut tried = std::collections::HashSet::new();
        for cell in grid.values() {
            for (x, &i) in cell.iter().enumerate() {
                for &j in &cell[x + 1..] {
                    if tried.insert((i.min(j), i.max(j))) {
                        found.extend(seam(i, j));
                    }
                }
            }
        }

        // Closest first; a stretch of a link takes one seam.
        found.sort_by(|a, b| a.score.total_cmp(&b.score));
        let mut taken: Vec<Vec<[f32; 2]>> = vec![Vec::new(); segs.len()];
        let clash = |list: &[[f32; 2]], r: [f32; 2]| {
            list.iter()
                .any(|q| r[0] < q[1] - 1e-4 && q[0] < r[1] - 1e-4)
        };
        let mut seams = Vec::new();
        for s in found {
            if !clash(&taken[s.i], s.ti) && !clash(&taken[s.j], s.tj) {
                taken[s.i].push(s.ti);
                taken[s.j].push(s.tj);
                seams.push(s);
            }
        }
        // Where each segment is cut: the seams' ends inside it.
        let cuts = |seams: &[Seam]| {
            let mut cuts = vec![Vec::new(); segs.len()];
            for s in seams {
                for (k, r) in [(s.i, s.ti), (s.j, s.tj)] {
                    cuts[k].extend(
                        r.into_iter()
                            .filter(|&t| t > 1e-4 && t < segs[k].len - 1e-4),
                    );
                }
            }
            for c in &mut cuts {
                c.sort_by(f32::total_cmp);
                c.dedup_by(|a, b| (*a - *b).abs() < 1e-4);
            }
            cuts
        };
        // The 16-bit link and vertex indices: past them, the shortest seams
        // go first.
        loop {
            let n: usize = cuts(&seams).iter().map(Vec::len).sum();
            if self.links.len() + n + seams.len() <= 32767 && self.vertices.len() + n <= 32767 {
                break;
            }
            seams.sort_by(|a, b| (b.ti[1] - b.ti[0]).total_cmp(&(a.ti[1] - a.ti[0])));
            let drop = (seams.len() / 8).max(1);
            seams.truncate(seams.len() - drop);
            self.cracks_dropped += drop;
        }

        // Cut each segment's link into pieces at its cuts: the first keeps
        // its index (what led to it still does), the others are appended,
        // and the last goes on where the link went.
        let cuts = cuts(&seams);
        let mut pieces: Vec<Vec<([f32; 2], usize)>> = vec![Vec::new(); segs.len()];
        for (k, s) in segs.iter().enumerate() {
            let link = self.links[s.link];
            let mut ts = vec![0.0];
            ts.extend(&cuts[k]);
            ts.push(s.len);
            let mut verts = vec![link.v1];
            for &t in &cuts[k] {
                verts.push(self.vertices.len() as i16);
                self.vertices.push(at(s, t));
            }
            verts.push(link.v2);
            let mut ids = vec![s.link];
            for _ in 2..ts.len() {
                ids.push(self.links.len());
                self.links.push(link);
            }
            for m in 0..ids.len() {
                let piece = &mut self.links[ids[m]];
                piece.v1 = verts[m];
                piece.v2 = verts[m + 1];
                piece.forward = ids.get(m + 1).map_or(link.forward, |&id| id as i16);
                pieces[k].push(([ts[m], ts[m + 1]], ids[m]));
            }
        }
        let piece = |k: usize, r: [f32; 2]| {
            pieces[k]
                .iter()
                .find(|(p, _)| (p[0] - r[0]).abs() < 1e-3 && (p[1] - r[1]).abs() < 1e-3)
                .map(|&(_, id)| id)
                .ok_or_else(|| format!("crack seam lost its piece of link {}", segs[k].link))
        };

        // The joining links, after every other, and a hint per seam end.
        let first = self.links.len();
        for (n, s) in seams.iter().enumerate() {
            let (ui, uj) = (piece(s.i, s.ti)?, piece(s.j, s.tj)?);
            let (li, lj) = (self.links[ui], self.links[uj]);
            for u in [ui, uj] {
                self.links[u].flags = LINK_INTERSECTION;
                self.links[u].hint = self.hints.len() as i16;
                self.hints.push(Hint {
                    kind: HINT_INTERSECTION,
                    next: -1,
                    data: [(first + n) as i32, 0, 0, 0],
                });
            }
            self.links.push(Link {
                v1: li.v1,
                v2: li.v2,
                flags: 0,
                hint: -1,
                forward: li.forward,
                reverse: lj.forward,
                left: li.left,
                right: lj.left,
            });
        }
        // Each sector's hint chain: its links' hints, around its ring.
        for s in 0..self.sectors.len() {
            let mut chain = Vec::new();
            let first = self.sectors[s].first_link;
            let mut l = first;
            for _ in 0..4096 {
                if l < 0 {
                    break;
                }
                let link = self.links[l as usize];
                if link.hint >= 0 {
                    chain.push(link.hint);
                }
                let next = if link.left as usize == s {
                    link.forward
                } else {
                    link.reverse
                };
                l = next as i32;
                if l == first {
                    break;
                }
            }
            for w in chain.windows(2) {
                self.hints[w[0] as usize].next = w[1];
            }
            self.sectors[s].hint = chain.first().copied().unwrap_or(-1);
        }
        Ok(())
    }

    /// Check the intersection links as the simulation reads them: each
    /// flagged link's hint names a link joining its sector that carries the
    /// sector's ring on where it does (and runs along it, for its left
    /// sector), and each sector's hint chain is exactly its own links' hints.
    pub fn check_hints(&self) -> Result<(), String> {
        for (k, l) in self.links.iter().enumerate() {
            if l.flags & LINK_INTERSECTION == 0 {
                if l.hint >= 0 {
                    return Err(format!("link {k}: a hint but no intersection flag"));
                }
                continue;
            }
            let h = usize::try_from(l.hint)
                .ok()
                .and_then(|h| self.hints.get(h))
                .ok_or_else(|| format!("link {k}: no hint"))?;
            let t = usize::try_from(h.data[0])
                .ok()
                .and_then(|t| self.links.get(t))
                .ok_or_else(|| format!("link {k}: hint {} names no link", l.hint))?;
            let ok = if t.left == l.left {
                t.forward == l.forward && (t.v1, t.v2) == (l.v1, l.v2)
            } else {
                t.right == l.left && t.reverse == l.forward
            };
            if h.kind != HINT_INTERSECTION || l.right >= 0 || !ok {
                return Err(format!("link {k}: hint {} does not join it", l.hint));
            }
        }
        for (s, sector) in self.sectors.iter().enumerate() {
            let mut own = Vec::new();
            let mut l = sector.first_link;
            for _ in 0..4096 {
                let link = &self.links[l as usize];
                if link.hint >= 0 {
                    own.push(link.hint);
                }
                let next = if link.left as usize == s {
                    link.forward
                } else {
                    link.reverse
                };
                l = next as i32;
                if l < 0 || l == sector.first_link {
                    break;
                }
            }
            let mut chain = Vec::new();
            let mut h = sector.hint;
            while h >= 0 && chain.len() <= self.hints.len() {
                chain.push(h);
                h = self.hints[h as usize].next;
            }
            own.sort_unstable();
            chain.sort_unstable();
            if own != chain {
                return Err(format!(
                    "sector {s}: hint chain {chain:?}, its links' hints {own:?}"
                ));
            }
        }
        Ok(())
    }

    /// Walk every sector's link ring the way the simulation does and check
    /// it closes on itself through links that touch the sector.
    pub fn check_rings(&self) -> Result<(), String> {
        for (s, sector) in self.sectors.iter().enumerate() {
            let first = sector.first_link;
            if first < 0 {
                return Err(format!("sector {s} has no link"));
            }
            let mut l = first;
            for step in 0.. {
                let link = &self.links[l as usize];
                let next = if link.left as usize == s {
                    link.forward
                } else if link.right as usize == s {
                    link.reverse
                } else {
                    return Err(format!("sector {s}: link {l} does not touch it"));
                };
                if next < 0 {
                    return Err(format!("sector {s}: ring breaks after link {l}"));
                }
                if next as i32 == first {
                    break;
                }
                if step > 4096 {
                    return Err(format!("sector {s}: ring does not close"));
                }
                l = next as i32;
            }
        }
        Ok(())
    }

    /// Walkable surfaces' shell polygons and the plane z at (x, y), for
    /// placing points on them.
    fn surface_z(c: &Collision, surface: usize, x: f32, y: f32) -> Option<f32> {
        let n = surface_normal(c, surface);
        let poly = crate::unpack16::polygon(c, surface);
        if poly.len() < 3 || n[2].abs() < 1e-4 {
            return None;
        }
        // Convex polygon in xy: the point is on the same side of every edge.
        let mut sign = 0.0f32;
        for i in 0..poly.len() {
            let a = poly[i];
            let b = poly[(i + 1) % poly.len()];
            let cross = (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0]);
            if cross.abs() < 1e-6 {
                continue;
            }
            if sign == 0.0 {
                sign = cross.signum();
            } else if cross.signum() != sign {
                return None;
            }
        }
        let p = poly[0];
        Some(p[2] - (n[0] * (x - p[0]) + n[1] * (y - p[1])) / n[2])
    }

    /// Firing positions on a `spacing` grid over the floor sectors whose
    /// component is in `components` (empty: every component), lifted
    /// `lift` above the surface.
    pub fn firing_positions(
        &self,
        c: &Collision,
        spacing: f32,
        components: &[usize],
        lift: f32,
    ) -> Vec<FiringPosition> {
        let mut out = Vec::new();
        for (sector, &surface) in self.sector_surface.iter().enumerate() {
            if !self.sectors[sector].is_floor()
                || !components.is_empty() && !components.contains(&self.component[sector])
            {
                continue;
            }
            let poly = crate::unpack16::polygon(c, surface);
            if poly.is_empty() {
                continue;
            }
            let (mut x0, mut y0, mut x1, mut y1) = (f32::MAX, f32::MAX, f32::MIN, f32::MIN);
            for p in &poly {
                x0 = x0.min(p[0]);
                y0 = y0.min(p[1]);
                x1 = x1.max(p[0]);
                y1 = y1.max(p[1]);
            }
            let normal = surface_normal(c, surface);
            let mut gx = (x0 / spacing).ceil() * spacing;
            while gx <= x1 {
                let mut gy = (y0 / spacing).ceil() * spacing;
                while gy <= y1 {
                    if let Some(z) = Self::surface_z(c, surface, gx, gy) {
                        out.push(FiringPosition {
                            point: [gx, gy, z + lift],
                            normal,
                            sector,
                        });
                    }
                    gy += spacing;
                }
                gx += spacing;
            }
        }
        out
    }

    /// The floor sector under (x, y) closest below or at `z + 1`.
    pub fn sector_at(&self, c: &Collision, p: [f32; 3]) -> Option<(usize, f32)> {
        let mut best: Option<(usize, f32)> = None;
        for (sector, &surface) in self.sector_surface.iter().enumerate() {
            if !self.sectors[sector].is_floor() {
                continue;
            }
            if let Some(z) = Self::surface_z(c, surface, p[0], p[1]) {
                if z <= p[2] + 1.0 && best.is_none_or(|(_, bz)| z > bz) {
                    best = Some((sector, z));
                }
            }
        }
        best
    }

    pub fn sectors_bytes(&self) -> Vec<u8> {
        let mut b = Vec::with_capacity(self.sectors.len() * 8);
        for s in &self.sectors {
            b.extend_from_slice(&s.flags.to_le_bytes());
            b.extend_from_slice(&s.hint.to_le_bytes());
            b.extend_from_slice(&s.first_link.to_le_bytes());
        }
        b
    }

    pub fn links_bytes(&self) -> Vec<u8> {
        let mut b = Vec::with_capacity(self.links.len() * 16);
        for l in &self.links {
            for v in [l.v1, l.v2] {
                b.extend_from_slice(&v.to_le_bytes());
            }
            b.extend_from_slice(&l.flags.to_le_bytes());
            for v in [l.hint, l.forward, l.reverse, l.left, l.right] {
                b.extend_from_slice(&v.to_le_bytes());
            }
        }
        b
    }

    pub fn refs_bytes(&self) -> Vec<u8> {
        self.refs.iter().flat_map(|r| r.to_le_bytes()).collect()
    }

    pub fn hints_bytes(&self) -> Vec<u8> {
        let mut b = Vec::with_capacity(self.hints.len() * 20);
        for h in &self.hints {
            b.extend_from_slice(&h.kind.to_le_bytes());
            b.extend_from_slice(&h.next.to_le_bytes());
            for d in h.data {
                b.extend_from_slice(&d.to_le_bytes());
            }
        }
        b
    }

    pub fn vertices_bytes(&self) -> Vec<u8> {
        self.vertices
            .iter()
            .flat_map(|p| p.iter().flat_map(|f| f.to_le_bytes()))
            .collect()
    }
}

/// The collision shell of a `scenario_structure_bsp` payload.
pub fn shell_collision(sbsp: &[u8]) -> Result<Collision, String> {
    use blam_tag::blockedit::find_block;
    let tag = blam_tag::TagFile::parse(sbsp, None).map_err(|e| e.to_string())?;
    let layout = tag.layout().map_err(|e| e.to_string())?;
    let root = tag.read_data(&layout).map_err(|e| e.to_string())?;
    let get = |n: &str| -> &[u8] {
        find_block(
            &layout,
            sbsp,
            &root,
            &format!("{}.{n}", crate::transplant::SHELL),
        )
        .map(|f| f.block.elements)
        .unwrap_or(&[])
    };
    let t = crate::unpack16::Tables {
        bsp3d_nodes: get("bsp3d nodes"),
        planes: get("planes"),
        leaves: get("leaves"),
        bsp2d_references: get("bsp2d references"),
        bsp2d_nodes: get("bsp2d nodes"),
        surfaces: get("surfaces"),
        edges: get("edges"),
        vertices: get("vertices"),
    };
    crate::unpack16::unpack(&t)
        .map(|(c, _)| c)
        .map_err(|e| e.to_string())
}

/// How many instanced geometry instances a `scenario_structure_bsp` payload
/// places (the scenario's `instanced geometry refs` hold one per instance).
pub fn instance_count(sbsp: &[u8]) -> Result<usize, String> {
    let tag = blam_tag::TagFile::parse(sbsp, None).map_err(|e| e.to_string())?;
    let layout = tag.layout().map_err(|e| e.to_string())?;
    let root = tag.read_data(&layout).map_err(|e| e.to_string())?;
    blam_tag::blockedit::find_block(&layout, sbsp, &root, "instanced geometry instances")
        .map(|f| f.block.count as usize)
        .map_err(|e| format!("{e:?}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ce::{Edge, Plane, Surface, Vertex};

    /// A 1 x 1 wu floor in two triangles, CE winged edges: S0 = v0 v1 v2,
    /// S1 = v0 v2 v3, sharing e2 (v2 -> v0, S0 on its left).
    fn floor() -> Collision {
        let v = |x: f32, y: f32| Vertex {
            point: [x, y, 0.0],
            first_edge: -1,
        };
        let e = |start, end, forward, reverse, left, right| Edge {
            start,
            end,
            forward,
            reverse,
            left,
            right,
        };
        let s = |first_edge| Surface {
            plane: 0,
            first_edge,
            flags: 0,
            breakable: -1,
            material: 0,
        };
        Collision {
            planes: vec![Plane {
                n: [0.0, 0.0, 1.0],
                d: 0.0,
            }],
            surfaces: vec![s(0), s(3)],
            edges: vec![
                e(0, 1, 1, -1, 0, -1),
                e(1, 2, 2, -1, 0, -1),
                e(2, 0, 0, 3, 0, 1),
                e(2, 3, 4, -1, 1, -1),
                e(3, 0, 2, -1, 1, -1),
            ],
            vertices: vec![v(0.0, 0.0), v(1.0, 0.0), v(1.0, 1.0), v(0.0, 1.0)],
            ..Default::default()
        }
    }

    #[test]
    fn a_floor_becomes_two_linked_sectors() {
        let c = floor();
        let pf = Pathfinding::build(&c).unwrap();
        assert_eq!(pf.sectors.len(), 2);
        assert_eq!(pf.links.len(), 5);
        assert_eq!(pf.vertices.len(), 4);
        assert_eq!(pf.refs, vec![0, 1]);
        pf.check_rings().unwrap();
        // The shared edge links the two sectors; the rest are open edges.
        let shared: Vec<_> = pf.links.iter().filter(|l| l.right >= 0).collect();
        assert_eq!(shared.len(), 1);
        assert_eq!((shared[0].left, shared[0].right), (0, 1));
        assert!(pf
            .links
            .iter()
            .filter(|l| l.right < 0)
            .all(|l| l.reverse == -1 && l.flags == LINK_LEDGE));
        assert_eq!(pf.component[0], pf.component[1]);
        assert_eq!(pf.sector_at(&c, [0.9, 0.1, 1.0]).map(|(s, _)| s), Some(0));
        assert_eq!(pf.sector_at(&c, [0.1, 0.9, 1.0]).map(|(s, _)| s), Some(1));
        assert!(!pf.firing_positions(&c, 0.25, &[], 0.0).is_empty());
    }

    /// A shell of polygons over `points`, each counter-clockwise seen from
    /// its front, with a plane per polygon and CE's winged edges.
    fn shell(points: &[[f32; 3]], polys: &[&[usize]]) -> Collision {
        let mut c = Collision {
            vertices: points
                .iter()
                .map(|&point| Vertex {
                    point,
                    first_edge: -1,
                })
                .collect(),
            ..Default::default()
        };
        let mut edge_of: std::collections::HashMap<(usize, usize), usize> = Default::default();
        for (s, poly) in polys.iter().enumerate() {
            // Newell's normal.
            let mut n = [0f32; 3];
            for i in 0..poly.len() {
                let (a, b) = (points[poly[i]], points[poly[(i + 1) % poly.len()]]);
                n[0] += (a[1] - b[1]) * (a[2] + b[2]);
                n[1] += (a[2] - b[2]) * (a[0] + b[0]);
                n[2] += (a[0] - b[0]) * (a[1] + b[1]);
            }
            let len = (n[0] * n[0] + n[1] * n[1] + n[2] * n[2]).sqrt();
            let n = n.map(|x| x / len);
            let p = points[poly[0]];
            c.planes.push(Plane {
                n,
                d: n[0] * p[0] + n[1] * p[1] + n[2] * p[2],
            });
            let ring: Vec<usize> = (0..poly.len())
                .map(|i| {
                    let (a, b) = (poly[i], poly[(i + 1) % poly.len()]);
                    if let Some(&e) = edge_of.get(&(b, a)) {
                        c.edges[e].right = s as i32;
                        return e;
                    }
                    c.edges.push(Edge {
                        start: a as i32,
                        end: b as i32,
                        forward: -1,
                        reverse: -1,
                        left: s as i32,
                        right: -1,
                    });
                    edge_of.insert((a, b), c.edges.len() - 1);
                    c.edges.len() - 1
                })
                .collect();
            for (i, &e) in ring.iter().enumerate() {
                let next = ring[(i + 1) % ring.len()] as i32;
                if c.edges[e].left == s as i32 {
                    c.edges[e].forward = next;
                } else {
                    c.edges[e].reverse = next;
                }
            }
            c.surfaces.push(Surface {
                plane: s as i32,
                first_edge: ring[0] as i32,
                flags: 0,
                breakable: -1,
                material: 0,
            });
        }
        c
    }

    /// A 1 wu floor at z 0 (x 0..1), a riser facing -x at x 1 cut at the
    /// heights `cuts`, and a 1 wu floor on top (x 1..2): surfaces lower
    /// floor, the riser's bands from the bottom, upper floor.
    fn stair(cuts: &[f32]) -> Collision {
        let mut points = vec![[0.0, 0.0, 0.0], [0.0, 1.0, 0.0]];
        for &z in [0.0].iter().chain(cuts) {
            points.push([1.0, 0.0, z]);
            points.push([1.0, 1.0, z]);
        }
        let top = *cuts.last().unwrap();
        points.push([2.0, 0.0, top]);
        points.push([2.0, 1.0, top]);
        let k = cuts.len();
        // Corners at x 1: (2 + 2i, 3 + 2i) at height i; the far floor's last.
        let (far0, far1) = (points.len() - 2, points.len() - 1);
        let mut polys: Vec<Vec<usize>> = vec![vec![0, 2, 3, 1]];
        for i in 0..k {
            let (a0, a1, b0, b1) = (2 + 2 * i, 3 + 2 * i, 4 + 2 * i, 5 + 2 * i);
            polys.push(vec![a0, b0, b1, a1]);
        }
        polys.push(vec![2 + 2 * k, far0, far1, 3 + 2 * k]);
        let polys: Vec<&[usize]> = polys.iter().map(Vec::as_slice).collect();
        shell(&points, &polys)
    }

    #[test]
    fn a_short_riser_is_a_step_between_its_floors() {
        let c = stair(&[0.08]);
        let pf = Pathfinding::build(&c).unwrap();
        pf.check_rings().unwrap();
        assert_eq!(pf.sectors.len(), 3);
        // Facing -x along the axis: `wall west | aligned`, no `floor`.
        assert_eq!(pf.sectors[1].flags, SECTOR_STEP | 0x200 | 0x800);
        assert!(!pf.sectors[1].is_floor());
        assert_eq!(pf.component[0], pf.component[2]);
        assert_eq!(pf.links.iter().filter(|l| l.right >= 0).count(), 2);
        // Positions and spawns stand on the floors only.
        let fps = pf.firing_positions(&c, 0.1, &[], 0.0);
        assert!(!fps.is_empty() && fps.iter().all(|f| f.sector != 1));
        assert_eq!(
            pf.sector_at(&c, [1.0, 0.5, 1.0]).map(|(s, _)| s == 1),
            Some(false)
        );
    }

    #[test]
    fn a_riser_cut_into_triangles_still_joins() {
        // stair(&[0.08]) with the riser split along a diagonal: the lower
        // triangle meets the lower floor, the upper one the upper floor.
        let points = [
            [0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [1.0, 0.0, 0.08],
            [1.0, 1.0, 0.08],
            [2.0, 0.0, 0.08],
            [2.0, 1.0, 0.08],
        ];
        let c = shell(
            &points,
            &[&[0, 2, 3, 1], &[2, 4, 3], &[4, 5, 3], &[4, 6, 7, 5]],
        );
        let pf = Pathfinding::build(&c).unwrap();
        pf.check_rings().unwrap();
        assert_eq!(pf.sectors.len(), 4);
        assert_eq!(pf.component[0], pf.component[3]);
    }

    #[test]
    fn a_tall_riser_splits_the_ground() {
        let c = stair(&[0.2]);
        let pf = Pathfinding::build(&c).unwrap();
        pf.check_rings().unwrap();
        assert_eq!(pf.sectors.len(), 2);
        assert_eq!(pf.refs, vec![0, -1, 1]);
        assert_ne!(pf.component[0], pf.component[1]);
        assert!(pf.links.iter().all(|l| l.right < 0));
    }

    #[test]
    fn short_bands_of_a_taller_riser_are_not_steps() {
        // Two bands of 0.06: one rises from a floor, the other reaches one,
        // but together they rise 0.12.
        let pf = Pathfinding::build(&stair(&[0.06, 0.12])).unwrap();
        pf.check_rings().unwrap();
        assert_eq!(pf.refs, vec![0, -1, -1, 1]);
        assert_ne!(pf.component[0], pf.component[1]);
        // Two bands that together stay under a step are one.
        let pf = Pathfinding::build(&stair(&[0.04, 0.08])).unwrap();
        pf.check_rings().unwrap();
        assert_eq!(pf.sectors.len(), 4);
        assert_eq!(pf.component[0], pf.component[3]);
    }

    #[test]
    fn steps_of_different_heights_keep_their_own_links_where_they_meet() {
        // A riser at x 1 in two bands: the lower (z 0..0.06, y 0..1) between
        // the floor at z 0 and a tread at 0.06 (y 0..0.5), the upper (z
        // 0.06..0.12, y 0.5..1) between that band and a floor at 0.12, with
        // a riser at y 0.5 from the tread up to it.
        let p = |x: f32, y: f32, z: f32| [x, y, z];
        let points = [
            p(0.0, 0.0, 0.0),
            p(1.0, 0.0, 0.0),
            p(1.0, 1.0, 0.0),
            p(0.0, 1.0, 0.0),
            p(1.0, 0.0, 0.06),
            p(1.0, 0.5, 0.06),
            p(1.0, 1.0, 0.06),
            p(2.0, 0.0, 0.06),
            p(2.0, 0.5, 0.06),
            p(1.0, 0.5, 0.12),
            p(1.0, 1.0, 0.12),
            p(2.0, 0.5, 0.12),
            p(2.0, 1.0, 0.12),
        ];
        let c = shell(
            &points,
            &[
                &[0, 1, 2, 3],    // floor, z 0
                &[1, 4, 5, 6, 2], // lower band
                &[4, 7, 8, 5],    // tread, z 0.06
                &[5, 9, 10, 6],   // upper band
                &[9, 11, 12, 10], // floor, z 0.12
                &[5, 8, 11, 9],   // riser from the tread
            ],
        );
        let pf = Pathfinding::build(&c).unwrap();
        pf.check_rings().unwrap();
        assert_eq!(pf.sectors.len(), 6);
        assert!(pf.component.iter().all(|&k| k == pf.component[0]));
        // The bands' shared edge (z 0.06, y 0.5..1) carries each band's ring
        // on a link of its own.
        let between: Vec<_> = pf
            .links
            .iter()
            .filter(|l| {
                let (a, b) = (pf.vertices[l.v1 as usize], pf.vertices[l.v2 as usize]);
                a[0] == 1.0 && b[0] == 1.0 && a[2] == 0.06 && b[2] == 0.06 && a[1] + b[1] == 1.5
            })
            .collect();
        assert_eq!(between.len(), 2);
        assert!(between.iter().all(|l| l.right == -1 && l.reverse == -1));
        assert_ne!(between[0].left, between[1].left);
    }

    #[test]
    fn a_face_hanging_below_a_floor_is_not_a_step() {
        // A slab's side face, 0.05 deep, meeting nothing below.
        let points = [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 0.0, -0.05],
            [1.0, 1.0, -0.05],
        ];
        let c = shell(&points, &[&[0, 1, 2, 3], &[2, 1, 4, 5]]);
        assert!(surface_normal(&c, 1)[0] > 0.99);
        let pf = Pathfinding::build(&c).unwrap();
        assert_eq!(pf.refs, vec![0, -1]);
    }

    /// Two slabs, each a floor with its side face hanging 0.08 below it: one
    /// over x 0..1, y `a`, at z 0, the other over x `1 + gap`..2, y `b`, at
    /// z `dz`. `up` makes the side faces walls rising 1 wu instead. Surfaces:
    /// floor, face, floor, face.
    fn slabs(gap: f32, dz: f32, a: [f32; 2], b: [f32; 2], up: bool) -> Collision {
        let h = if up { 1.0 } else { -0.08 };
        let x = 1.0 + gap;
        let points = [
            [0.0, a[0], 0.0],
            [1.0, a[0], 0.0],
            [1.0, a[1], 0.0],
            [0.0, a[1], 0.0],
            [1.0, a[0], h],
            [1.0, a[1], h],
            [x, b[0], dz],
            [2.0, b[0], dz],
            [2.0, b[1], dz],
            [x, b[1], dz],
            [x, b[0], dz + h],
            [x, b[1], dz + h],
        ];
        shell(
            &points,
            &[&[0, 1, 2, 3], &[2, 1, 4, 5], &[6, 7, 8, 9], &[6, 9, 11, 10]],
        )
    }

    fn joined(c: &Collision) -> bool {
        let pf = Pathfinding::build(c).unwrap();
        pf.check_rings().unwrap();
        pf.check_hints().unwrap();
        assert_eq!(pf.refs, vec![0, -1, 1, -1]);
        pf.component[0] == pf.component[1]
    }

    #[test]
    fn slabs_edge_to_edge_join_through_an_intersection_link() {
        let c = slabs(0.0, 0.0, [0.0, 1.0], [0.0, 1.0], false);
        let pf = Pathfinding::build(&c).unwrap();
        pf.check_rings().unwrap();
        pf.check_hints().unwrap();
        assert_eq!(pf.refs, vec![0, -1, 1, -1]);
        assert_eq!(pf.component[0], pf.component[1]);
        // Each floor's link along the seam is an intersection link with a
        // hint of its own; both name the joining link, appended last.
        let users: Vec<_> = pf
            .links
            .iter()
            .filter(|l| l.flags == LINK_INTERSECTION)
            .collect();
        assert_eq!(users.len(), 2);
        assert!(users.iter().all(|l| l.right == -1 && l.hint >= 0));
        assert_eq!(pf.hints.len(), 2);
        let t = pf.links.len() - 1;
        assert!(pf
            .hints
            .iter()
            .all(|h| h.kind == 0 && h.data == [t as i32, 0, 0, 0]));
        assert_eq!((pf.links[t].left, pf.links[t].right), (0, 1));
        assert_eq!(
            [pf.sectors[0].hint, pf.sectors[1].hint],
            [users[0].hint, users[1].hint]
        );
    }

    #[test]
    fn floors_join_across_a_crack_or_an_overlap_within_a_step() {
        assert!(joined(&slabs(0.05, 0.08, [0.0, 1.0], [0.0, 1.0], false)));
        assert!(joined(&slabs(-0.01, 0.0, [0.0, 1.0], [0.0, 1.0], false)));
        assert!(!joined(&slabs(0.15, 0.0, [0.0, 1.0], [0.0, 1.0], false)));
        assert!(!joined(&slabs(0.05, 0.12, [0.0, 1.0], [0.0, 1.0], false)));
    }

    #[test]
    fn floors_either_side_of_a_wall_do_not_join() {
        assert!(!joined(&slabs(0.05, 0.0, [0.0, 1.0], [0.0, 1.0], true)));
    }

    #[test]
    fn a_long_edge_is_cut_where_a_short_one_meets_it() {
        // The first slab's edge runs y 0..2, the second's y 0.5..1.
        let c = slabs(0.0, 0.0, [0.0, 2.0], [0.5, 1.0], false);
        assert!(joined(&c));
        let pf = Pathfinding::build(&c).unwrap();
        // The long link became three pieces around the first floor.
        let ring = pf.links.iter().filter(|l| l.left == 0).count();
        assert_eq!(ring, 4 + 2 + 1); // its edges, two more pieces, the seam
        let t = pf.links.last().unwrap();
        let mut ends = [pf.vertices[t.v1 as usize], pf.vertices[t.v2 as usize]];
        ends.sort_by(|a, b| a[1].total_cmp(&b[1]));
        assert_eq!(ends, [[1.0, 0.5, 0.0], [1.0, 1.0, 0.0]]);
    }

    #[test]
    fn a_short_riser_away_from_floors_is_not_a_step() {
        let mut c = stair(&[0.08]);
        c.surfaces[0].flags = 0x8; // both floors breakable
        c.surfaces[2].flags = 0x8;
        let pf = Pathfinding::build(&c).unwrap();
        assert!(pf.sectors.is_empty());
    }

    #[test]
    fn step_walls_follow_the_riser_facing() {
        assert_eq!(step_flags([-1.0, 0.0, 0.0]), SECTOR_STEP | 0x200 | 0x800);
        assert_eq!(step_flags([1.0, 0.0, 0.0]), SECTOR_STEP | 0x100 | 0x800);
        assert_eq!(step_flags([0.0, 1.0, 0.0]), SECTOR_STEP | 0x40 | 0x800);
        assert_eq!(step_flags([0.3, -0.9, 0.3]), SECTOR_STEP | 0x80);
    }

    #[test]
    fn steep_and_breakable_surfaces_are_not_sectors() {
        let mut c = floor();
        c.planes.push(Plane {
            n: [1.0, 0.0, 0.0],
            d: 0.0,
        });
        c.surfaces[0].plane = 1; // a wall
        c.surfaces[1].flags = 0x8; // breakable
        let pf = Pathfinding::build(&c).unwrap();
        assert!(pf.sectors.is_empty());
        assert!(pf.links.is_empty());
        assert_eq!(pf.refs, vec![-1, -1]);
    }

    #[test]
    fn a_link_with_only_its_right_side_walkable_is_turned_round() {
        let mut c = floor();
        c.planes.push(Plane {
            n: [1.0, 0.0, 0.0],
            d: 0.0,
        });
        c.surfaces[0].plane = 1; // S0, left of the shared edge, is a wall
        let pf = Pathfinding::build(&c).unwrap();
        assert_eq!(pf.sectors.len(), 1);
        pf.check_rings().unwrap();
        // e2 ran v2 -> v0 with the wall on its left: now v0 -> v2 around S1.
        let flipped = pf.links.iter().find(|l| l.flags == LINK_WALL_BASE).unwrap();
        assert_eq!((flipped.left, flipped.right), (0, -1));
        assert_eq!(pf.vertices[flipped.v1 as usize], [0.0, 0.0, 0.0]);
        assert_eq!(pf.vertices[flipped.v2 as usize], [1.0, 1.0, 0.0]);
    }
}
