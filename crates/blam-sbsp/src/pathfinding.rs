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
//! The scenario's `structure bsps[i].flags` bit `no default structure
//! pathfinding` (0x8) must be clear for the shell's refs to count; B40 sets it
//! because its own sectors all lie on instanced geometry.

use crate::ce::Collision;

/// `sector walkable | floor`, B40's flags for a plain floor sector.
pub const SECTOR_FLOOR: u16 = 0x11;
/// `sector link wall base`: the far side of the edge is a wall.
pub const LINK_WALL_BASE: u16 = 0x40;
/// `sector link ledge`: the far side drops away or is open.
pub const LINK_LEDGE: u16 = 0x80;

/// The steepest floor an AI walks: a normal at most ~49 degrees off vertical.
pub const WALKABLE_NZ: f32 = 0.65;

#[derive(Debug, Clone, Copy)]
pub struct Sector {
    pub flags: u16,
    pub hint: i16,
    pub first_link: i32,
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

impl Pathfinding {
    /// Build the tables from a shell. Errors when the shell is too large for
    /// the 16-bit link and vertex indices.
    pub fn build(c: &Collision) -> Result<Self, String> {
        let n = c.surfaces.len();
        let mut pf = Pathfinding {
            surface_sector: vec![None; n],
            refs: vec![-1; n],
            ..Default::default()
        };
        for s in 0..n {
            if walkable(c, s) {
                pf.surface_sector[s] = Some(pf.sectors.len());
                pf.refs[s] = pf.sectors.len() as i32;
                pf.sector_surface.push(s);
                pf.sectors.push(Sector { flags: SECTOR_FLOOR, hint: -1, first_link: -1 });
            }
        }
        if pf.sectors.len() > 65534 {
            return Err(format!("{} walkable surfaces; a BSP holds at most 65534 sectors", pf.sectors.len()));
        }
        let by_surface = pf.surface_sector.clone();
        let sector_of = |surface: i32| -> Option<usize> {
            if surface < 0 {
                None
            } else {
                by_surface.get(surface as usize).copied().flatten()
            }
        };

        // Keep every edge with a walkable side, oriented so its left side is
        // walkable; `link_of[edge]` is its link and `flipped[edge]` whether
        // it was turned round.
        let mut link_of = vec![-1i32; c.edges.len()];
        let mut flipped = vec![false; c.edges.len()];
        let mut kept = Vec::new();
        for (e, edge) in c.edges.iter().enumerate() {
            let (l, r) = (sector_of(edge.left), sector_of(edge.right));
            if l.is_none() && r.is_none() {
                continue;
            }
            flipped[e] = l.is_none();
            link_of[e] = kept.len() as i32;
            kept.push(e);
        }
        if kept.len() > 32767 {
            return Err(format!("{} links; the 16-bit link indices hold 32767", kept.len()));
        }
        let mut vertex_of = vec![-1i32; c.vertices.len()];
        let mut vertex = |v: i32, verts: &mut Vec<[f32; 3]>| -> Result<i16, String> {
            let v = v as usize;
            if vertex_of[v] < 0 {
                vertex_of[v] = verts.len() as i32;
                verts.push(c.vertices[v].point);
            }
            i16::try_from(vertex_of[v]).map_err(|_| "more than 32767 pathfinding vertices".to_string())
        };
        let mut verts = Vec::new();
        for &e in &kept {
            let edge = &c.edges[e];
            // In edge terms: `forward` continues the left surface's ring,
            // `reverse` the right's.
            let (start, end, ls, rs, lnext, rnext) = if flipped[e] {
                (edge.end, edge.start, edge.right, edge.left, edge.reverse, edge.forward)
            } else {
                (edge.start, edge.end, edge.left, edge.right, edge.forward, edge.reverse)
            };
            let left = sector_of(ls).expect("left side is walkable");
            let right = sector_of(rs);
            let next = |n: i32| if n < 0 { -1 } else { link_of[n as usize] as i16 };
            let flags = match (right, rs) {
                (Some(_), _) => 0,
                (None, s) if s >= 0 && surface_normal(c, s as usize)[2] > -0.3 => LINK_WALL_BASE,
                _ => LINK_LEDGE,
            };
            let link = Link {
                v1: vertex(start, &mut verts)?,
                v2: vertex(end, &mut verts)?,
                flags,
                hint: -1,
                forward: next(lnext),
                reverse: if right.is_some() { next(rnext) } else { -1 },
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
        for l in &pf.links {
            if l.right >= 0 {
                let (a, b) = (find(&mut parent, l.left as usize), find(&mut parent, l.right as usize));
                if a != b {
                    parent[a] = b;
                }
            }
        }
        pf.component = (0..pf.sectors.len()).map(|s| find(&mut parent, s)).collect();
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

    /// Firing positions on a `spacing` grid over the walkable sectors whose
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
            if !components.is_empty() && !components.contains(&self.component[sector]) {
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
                        out.push(FiringPosition { point: [gx, gy, z + lift], normal, sector });
                    }
                    gy += spacing;
                }
                gx += spacing;
            }
        }
        out
    }

    /// The walkable sector under (x, y) closest below or at `z + 1`.
    pub fn sector_at(&self, c: &Collision, p: [f32; 3]) -> Option<(usize, f32)> {
        let mut best: Option<(usize, f32)> = None;
        for (sector, &surface) in self.sector_surface.iter().enumerate() {
            if let Some(z) = Self::surface_z(c, surface, p[0], p[1]) {
                if z <= p[2] + 1.0 && best.map_or(true, |(_, bz)| z > bz) {
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
        self.vertices.iter().flat_map(|p| p.iter().flat_map(|f| f.to_le_bytes())).collect()
    }
}

/// The collision shell of a `scenario_structure_bsp` payload.
pub fn shell_collision(sbsp: &[u8]) -> Result<Collision, String> {
    use blam_tag::blockedit::find_block;
    let tag = blam_tag::TagFile::parse(sbsp, None).map_err(|e| e.to_string())?;
    let layout = tag.layout().map_err(|e| e.to_string())?;
    let root = tag.read_data(&layout).map_err(|e| e.to_string())?;
    let get = |n: &str| -> &[u8] {
        find_block(&layout, sbsp, &root, &format!("{}.{n}", crate::transplant::SHELL))
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
    crate::unpack16::unpack(&t).map(|(c, _)| c).map_err(|e| e.to_string())
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
