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
//! The scenario's `structure bsps[i].flags` bit `no default structure
//! pathfinding` (0x8) must be clear for the shell's refs to count; B40 sets it
//! because its own sectors all lie on instanced geometry.

use crate::ce::{Collision, Edge};

/// `sector walkable | floor`, B40's flags for a plain floor sector.
pub const SECTOR_FLOOR: u16 = 0x11;
/// `sector walkable | sector step`, B40's flags for a riser short enough to
/// walk over; [`step_flags`] adds the wall it faces.
pub const SECTOR_STEP: u16 = 0x1001;
/// `sector link wall base`: the far side of the edge is a wall.
pub const LINK_WALL_BASE: u16 = 0x40;
/// `sector link ledge`: the far side drops away or is open.
pub const LINK_LEDGE: u16 = 0x80;

/// The steepest floor an AI walks: a normal at most ~49 degrees off vertical.
pub const WALKABLE_NZ: f32 = 0.65;

/// The tallest riser an AI walks over: the shipped AI globals' `hoist step`
/// bounds start at 0.1 wu (anything taller is a hoist or a jump), as does
/// `max jump down height down`. B40's own steps rise 0.007 to 0.078 wu.
pub const STEP_HEIGHT: f32 = 0.1;

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
        for &(e, carries) in &plan {
            let edge = &c.edges[e];
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
