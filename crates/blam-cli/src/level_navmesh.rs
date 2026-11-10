//! `mjolnir level navmesh`: a converted map's walkable ground as a navmesh a
//! test driver (tools/bot) can plan routes on.
//!
//! It is the AI pathfinding `level bake` writes into the scenario
//! (`blam_sbsp::pathfinding`, docs/bots.md), built again from the structure
//! BSP: each sector is a convex walkable area, and a link with a sector on
//! both sides is a doorway between two. Coordinates are world units, as the
//! simulation has them (Unreal's are these x 304.8 with y negated).
//!
//! ```text
//! {
//!   "version": 1,
//!   "sectors": [{ "ring": [[x, y, z], ...], "floor": true, "component": 7, "blocked": false }, ...],
//!   "doors": [[a, b, [x, y, z], [x, y, z]], ...],
//!   "main_component": 7,
//!   "walls": [[x1, y1, x2, y2, z low, z high], ...]
//! }
//! ```
//!
//! A sector's ring runs around it as the simulation walks it: from its first
//! link, `forward` while the sector is the link's left one, `reverse` while it
//! is the right one.
//!
//! **Blocked.** What stands on a converted map's ground (its trees, rocks the
//! converter split out) is collision the pathfinding does not see: steep
//! faces in the shell over ground it counts as floor, or the instanced
//! geometry, which it never reads. A route would run through them. A sector
//! is `blocked` when a steep surface of either (not walkable, not a ceiling)
//! crosses its inside between
//! [`BLOCK_LOW`] and [`BLOCK_HIGH`] above it. A wall that only meets a
//! sector's edge, as a cliff meets the ground beside it, does not block it.
//! `walls` lists the sides of those surfaces that stand in a walkable area,
//! in plan with their height range: what a walker steers around close in.
use anyhow::{Context, Result};
use blam_sbsp::pathfinding::{shell_collision, Pathfinding};
use clap::Args;
use std::path::PathBuf;

use blam_sbsp::ce::Collision;
use blam_sbsp::pathfinding::surface_normal;

/// The band above a floor where a wall is in a walker's way, wu: above a
/// step, below a crouching head.
const BLOCK_LOW: f32 = 0.12;
const BLOCK_HIGH: f32 = 0.6;
/// A surface whose normal points further down than this is a ceiling.
const CEILING_NZ: f32 = -0.3;
/// An instance surface whose normal points further up than this is ground
/// (about 49 degrees, the pathfinding's own walkable limit).
const WALL_NZ: f32 = 0.65;
/// The share of a sector shrunk off its edges before testing, so a wall along
/// an edge stays out.
const INSET: f32 = 0.08;

#[derive(Args)]
pub struct NavmeshArgs {
    /// The map's structure BSP, as `mjolnir extract --group
    /// scenario_structure_bsp` writes it.
    #[arg(long)]
    pub sbsp: PathBuf,
    /// Where to write the navmesh JSON.
    #[arg(long)]
    pub out: PathBuf,
}

/// The vertices around sector `s`, in the order the simulation walks them.
fn ring(pf: &Pathfinding, s: usize) -> Vec<[f32; 3]> {
    let mut out = Vec::new();
    let first = pf.sectors[s].first_link;
    let mut link = first;
    // A ring never holds more links than there are.
    for _ in 0..pf.links.len() {
        if link < 0 {
            break;
        }
        let l = &pf.links[link as usize];
        let next = if l.left as usize == s && l.left >= 0 {
            out.push(pf.vertices[l.v1 as usize]);
            l.forward as i32
        } else {
            out.push(pf.vertices[l.v2 as usize]);
            l.reverse as i32
        };
        if next == first || next < 0 {
            break;
        }
        link = next;
    }
    out
}

/// A collision surface's corners, walked by its edges.
fn surface_ring(c: &Collision, s: usize) -> Vec<[f32; 3]> {
    let mut out = Vec::new();
    let first = c.surfaces[s].first_edge;
    let mut e = first;
    for _ in 0..c.edges.len() {
        if e < 0 {
            break;
        }
        let edge = &c.edges[e as usize];
        let next = if edge.left as usize == s {
            out.push(c.vertices[edge.start as usize].point);
            edge.forward
        } else {
            out.push(c.vertices[edge.end as usize].point);
            edge.reverse
        };
        if next == first {
            break;
        }
        e = next;
    }
    out
}

fn cross(o: [f32; 2], a: [f32; 2], b: [f32; 2]) -> f32 {
    (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
}

/// Whether segment p-q meets the inside of convex counter-clockwise polygon
/// `poly` (2D): an end inside, or a crossing of one of its sides.
fn segment_meets(poly: &[[f32; 2]], p: [f32; 2], q: [f32; 2]) -> bool {
    let inside =
        |x: [f32; 2]| (0..poly.len()).all(|i| cross(poly[i], poly[(i + 1) % poly.len()], x) > 0.0);
    if inside(p) || inside(q) {
        return true;
    }
    (0..poly.len()).any(|i| {
        let (a, b) = (poly[i], poly[(i + 1) % poly.len()]);
        let d1 = cross(a, b, p);
        let d2 = cross(a, b, q);
        let d3 = cross(p, q, a);
        let d4 = cross(p, q, b);
        d1 * d2 < 0.0 && d3 * d4 < 0.0
    })
}

/// Which sectors a wall stands inside (module notes, "Blocked"): the shell's
/// steep surfaces and the instanced geometry's (`extra`, world space).
fn blocked(
    pf: &Pathfinding,
    c: &Collision,
    rings: &[Vec<[f32; 3]>],
    extra: &[blam_sbsp::pathfinding::WorldSurface],
) -> (Vec<bool>, Vec<[f32; 6]>) {
    const CELL: f32 = 2.0;
    // The walls, each as its corners and height range, in a grid by plan.
    let mut walls: Vec<(Vec<[f32; 3]>, f32, f32)> = Vec::new();
    let mut grid: std::collections::HashMap<(i32, i32), Vec<usize>> = Default::default();
    for s in 0..c.surfaces.len() {
        if pf.surface_sector.get(s).copied().flatten().is_some()
            || surface_normal(c, s)[2] < CEILING_NZ
        {
            continue;
        }
        let ring = surface_ring(c, s);
        if ring.len() < 2 {
            continue;
        }
        let (lo, hi) = ring.iter().fold((f32::MAX, f32::MIN), |(lo, hi), p| {
            (lo.min(p[2]), hi.max(p[2]))
        });
        let w = walls.len();
        let (x0, x1) = ring
            .iter()
            .fold((f32::MAX, f32::MIN), |(a, b), p| (a.min(p[0]), b.max(p[0])));
        let (y0, y1) = ring
            .iter()
            .fold((f32::MAX, f32::MIN), |(a, b), p| (a.min(p[1]), b.max(p[1])));
        for gx in (x0 / CELL).floor() as i32..=(x1 / CELL).floor() as i32 {
            for gy in (y0 / CELL).floor() as i32..=(y1 / CELL).floor() as i32 {
                grid.entry((gx, gy)).or_default().push(w);
            }
        }
        walls.push((ring, lo, hi));
    }
    for (ring, normal) in extra {
        if normal[2] > WALL_NZ || normal[2] < CEILING_NZ {
            continue; // a floor of its own (a rock's top), or a ceiling
        }
        let (lo, hi) = ring.iter().fold((f32::MAX, f32::MIN), |(lo, hi), p| {
            (lo.min(p[2]), hi.max(p[2]))
        });
        let w = walls.len();
        let (x0, x1) = ring
            .iter()
            .fold((f32::MAX, f32::MIN), |(a, b), p| (a.min(p[0]), b.max(p[0])));
        let (y0, y1) = ring
            .iter()
            .fold((f32::MAX, f32::MIN), |(a, b), p| (a.min(p[1]), b.max(p[1])));
        for gx in (x0 / CELL).floor() as i32..=(x1 / CELL).floor() as i32 {
            for gy in (y0 / CELL).floor() as i32..=(y1 / CELL).floor() as i32 {
                grid.entry((gx, gy)).or_default().push(w);
            }
        }
        walls.push((ring.clone(), lo, hi));
    }
    let mut used: std::collections::BTreeSet<(usize, usize)> = Default::default();
    let flags = rings
        .iter()
        .map(|ring| {
            if ring.len() < 3 {
                return false;
            }
            let mut hit = false;
            let n = ring.len() as f32;
            let centre = [
                ring.iter().map(|p| p[0]).sum::<f32>() / n,
                ring.iter().map(|p| p[1]).sum::<f32>() / n,
            ];
            let poly: Vec<[f32; 2]> = ring
                .iter()
                .map(|p| {
                    [
                        p[0] + (centre[0] - p[0]) * INSET,
                        p[1] + (centre[1] - p[1]) * INSET,
                    ]
                })
                .collect();
            let (zlo, zhi) = ring.iter().fold((f32::MAX, f32::MIN), |(lo, hi), p| {
                (lo.min(p[2]), hi.max(p[2]))
            });
            let mut seen = std::collections::HashSet::new();
            let (x0, x1) = poly
                .iter()
                .fold((f32::MAX, f32::MIN), |(a, b), p| (a.min(p[0]), b.max(p[0])));
            let (y0, y1) = poly
                .iter()
                .fold((f32::MAX, f32::MIN), |(a, b), p| (a.min(p[1]), b.max(p[1])));
            for gx in (x0 / CELL).floor() as i32..=(x1 / CELL).floor() as i32 {
                for gy in (y0 / CELL).floor() as i32..=(y1 / CELL).floor() as i32 {
                    for &w in grid.get(&(gx, gy)).map(Vec::as_slice).unwrap_or(&[]) {
                        if !seen.insert(w) {
                            continue;
                        }
                        let (wall, lo, hi) = &walls[w];
                        if *hi < zlo + BLOCK_LOW || *lo > zhi + BLOCK_HIGH {
                            continue;
                        }
                        // The wall's sides that pass through the band.
                        for i in 0..wall.len() {
                            let (a, b) = (wall[i], wall[(i + 1) % wall.len()]);
                            if a[2].max(b[2]) < zlo + BLOCK_LOW || a[2].min(b[2]) > zhi + BLOCK_HIGH
                            {
                                continue;
                            }
                            if segment_meets(&poly, [a[0], a[1]], [b[0], b[1]]) {
                                used.insert((w, i));
                                hit = true;
                            }
                        }
                    }
                }
            }
            hit
        })
        .collect();
    // Each wall side that stands in a walkable area: plan ends and heights.
    let sides = used
        .into_iter()
        .map(|(w, i)| {
            let wall = &walls[w].0;
            let (a, b) = (wall[i], wall[(i + 1) % wall.len()]);
            [a[0], a[1], b[0], b[1], a[2].min(b[2]), a[2].max(b[2])]
        })
        .collect();
    (flags, sides)
}

pub fn build(sbsp: &[u8]) -> Result<serde_json::Value> {
    let shell = shell_collision(sbsp).map_err(|e| anyhow::anyhow!("navmesh: {e}"))?;
    let pf = Pathfinding::build(&shell).map_err(|e| anyhow::anyhow!("navmesh: {e}"))?;
    let mut sizes = std::collections::HashMap::<usize, usize>::new();
    for &c in &pf.component {
        *sizes.entry(c).or_default() += 1;
    }
    let main = sizes
        .iter()
        .max_by_key(|(_, n)| **n)
        .map(|(c, _)| *c)
        .unwrap_or(0);
    let rings: Vec<Vec<[f32; 3]>> = (0..pf.sectors.len()).map(|s| ring(&pf, s)).collect();
    let extra = blam_sbsp::pathfinding::instance_surfaces(sbsp, &shell)
        .map_err(|e| anyhow::anyhow!("navmesh: {e}"))?;
    let (blocked, walls) = blocked(&pf, &shell, &rings, &extra);
    let sectors: Vec<serde_json::Value> = (0..pf.sectors.len())
        .map(|s| {
            serde_json::json!({
                "ring": rings[s],
                "floor": pf.sectors[s].is_floor(),
                "component": pf.component[s],
                "blocked": blocked[s],
            })
        })
        .collect();
    let doors: Vec<serde_json::Value> = pf
        .links
        .iter()
        .filter(|l| l.left >= 0 && l.right >= 0 && l.left != l.right)
        .map(|l| {
            serde_json::json!([
                l.left,
                l.right,
                pf.vertices[l.v1 as usize],
                pf.vertices[l.v2 as usize]
            ])
        })
        .collect();
    Ok(serde_json::json!({
        "version": 1,
        "sectors": sectors,
        "doors": doors,
        "main_component": main,
        "walls": walls,
    }))
}

pub fn run(a: NavmeshArgs) -> Result<()> {
    let sbsp = std::fs::read(&a.sbsp).with_context(|| format!("reading {}", a.sbsp.display()))?;
    let mesh = build(&sbsp)?;
    let sectors = mesh["sectors"].as_array().map_or(0, Vec::len);
    let doors = mesh["doors"].as_array().map_or(0, Vec::len);
    let blocked = mesh["sectors"]
        .as_array()
        .map_or(0, |s| s.iter().filter(|s| s["blocked"] == true).count());
    std::fs::write(&a.out, serde_json::to_string(&mesh)?)
        .with_context(|| format!("writing {}", a.out.display()))?;
    println!(
        "{sectors} sectors ({blocked} blocked by walls standing in them), {doors} doors -> {}",
        a.out.display()
    );
    Ok(())
}
