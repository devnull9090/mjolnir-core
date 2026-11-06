//! Where the projection probe disagrees: every surface under a 2D node's left
//! child should project to the negative side of the node's line, every one
//! under the right child to the positive side.
//!
//!   cargo run -p blam-sbsp --example probe_residual -- <collision_N.json>
//!   cargo run -p blam-sbsp --example probe_residual -- <payload> <def index | shell>
//!
//! `--translate dx dy dz` moves the decoded BSP with [`pack16::translate`]
//! first, and `--split` fan-splits it as `def_transplant` does, so the probe
//! scores what a transplant would ship.
//!
//! Three scores, each "wrong-side vertices / surfaces with one":
//!
//! - **unsigned, outlines** — the plane's projection without the reference's
//!   sign, whole surface outlines (the old probe).
//! - **signed, outlines** — the projection the reference sees
//!   ([`pack16::reference_axes`]).
//! - **signed, clipped** — each outline first clipped to the half-spaces of
//!   the bsp3d leaf that owns the reference. A 2D tree is built from the
//!   surface pieces inside its leaf, so the part of a surface outside the leaf
//!   may sit anywhere relative to its splits; scoring it is a probe artifact.
use blam_sbsp::ce::{self, Collision};
use blam_sbsp::pack16::{self, node_frames};
use blam_sbsp::transplant;
use blam_sbsp::unpack16::{self, Tables};
use blam_tag::blockedit::find_block;
use std::collections::BTreeMap;

const FLAG: u32 = 0x8000_0000;
/// Vertices this close to a split line count as on it.
const ON_LINE: f32 = 1e-4;
/// Clipping tolerance: a surface lies on its leaf's boundary planes.
const ON_PLANE: f32 = 1e-3;

fn load(args: &[String]) -> Collision {
    if args[0].ends_with(".json") {
        return ce::load(std::path::Path::new(&args[0]))
            .expect("staged collision")
            .collision;
    }
    let file = std::fs::read(&args[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let base = match args.get(1).map(String::as_str) {
        Some("shell") => transplant::SHELL.to_string(),
        Some(d) => transplant::definition(d.parse().expect("def index")),
        None => panic!("usage: probe_residual <payload> <def index | shell>"),
    };
    let get = |name: &str| -> &[u8] {
        find_block(&layout, &file, &root, &format!("{base}.{name}"))
            .unwrap()
            .block
            .elements
    };
    let t = Tables {
        bsp3d_nodes: get("bsp3d nodes"),
        planes: get("planes"),
        leaves: get("leaves"),
        bsp2d_references: get("bsp2d references"),
        bsp2d_nodes: get("bsp2d nodes"),
        surfaces: get("surfaces"),
        edges: get("edges"),
        vertices: get("vertices"),
    };
    unpack16::unpack(&t).expect("unpack").0
}

fn collect(c: &Collision, child: i32, out: &mut Vec<usize>) {
    if child == -1 {
        return;
    }
    if (child as u32) & FLAG != 0 {
        out.push((child as u32 & 0x7fff) as usize);
        return;
    }
    if let Some(n) = c.bsp2d_nodes.get(child as usize) {
        collect(c, n.left, out);
        collect(c, n.right, out);
    }
}

/// The half-spaces `(normal, d)` bounding each leaf (`n·p >= d` inside),
/// from the bsp3d nodes above it. Works on forests: every node's parent is
/// found from the table itself, so no supernode walk is needed.
fn leaf_halfspaces(c: &Collision) -> Vec<Vec<([f32; 3], f32)>> {
    let mut node_parent: Vec<Option<(usize, bool)>> = vec![None; c.bsp3d_nodes.len()];
    let mut leaf_parent: Vec<Option<(usize, bool)>> = vec![None; c.leaves.len()];
    for (i, n) in c.bsp3d_nodes.iter().enumerate() {
        for (child, front) in [(n.back, false), (n.front, true)] {
            if child == -1 {
                continue;
            }
            if (child as u32) & FLAG != 0 {
                if let Some(p) = leaf_parent.get_mut((child as u32 & 0x7fff_ffff) as usize) {
                    *p = Some((i, front));
                }
            } else if let Some(p) = node_parent.get_mut(child as usize) {
                *p = Some((i, front));
            }
        }
    }
    let halfspace = |node: usize, front: bool| {
        let raw = c.bsp3d_nodes[node].plane as u32;
        let pl = c.planes[(raw & 0x7fff_ffff) as usize];
        let flip = (raw & FLAG != 0) != !front;
        if flip {
            ([-pl.n[0], -pl.n[1], -pl.n[2]], -pl.d)
        } else {
            (pl.n, pl.d)
        }
    };
    leaf_parent
        .iter()
        .map(|&p| {
            let mut out = Vec::new();
            let mut cur = p;
            for _ in 0..4096 {
                let Some((node, front)) = cur else { break };
                out.push(halfspace(node, front));
                cur = node_parent[node];
            }
            out
        })
        .collect()
}

/// Sutherland-Hodgman against each half-space, keeping points within
/// `ON_PLANE` of the boundary (a surface usually lies on one).
fn clip(poly: &[[f32; 3]], halfspaces: &[([f32; 3], f32)]) -> Vec<[f32; 3]> {
    let mut pts = poly.to_vec();
    for &(n, d) in halfspaces {
        if pts.is_empty() {
            break;
        }
        let dist = |p: &[f32; 3]| n[0] * p[0] + n[1] * p[1] + n[2] * p[2] - d;
        let mut out = Vec::with_capacity(pts.len() + 2);
        for k in 0..pts.len() {
            let (a, b) = (pts[k], pts[(k + 1) % pts.len()]);
            let (da, db) = (dist(&a), dist(&b));
            let (ina, inb) = (da >= -ON_PLANE, db >= -ON_PLANE);
            if ina {
                out.push(a);
            }
            if ina != inb {
                // Cut where the kept band ends (distance -ON_PLANE), so `t`
                // stays inside the edge.
                let t = (da + ON_PLANE) / (da - db);
                out.push([
                    a[0] + t * (b[0] - a[0]),
                    a[1] + t * (b[1] - a[1]),
                    a[2] + t * (b[2] - a[2]),
                ]);
            }
        }
        pts = out;
    }
    pts
}

#[derive(Default)]
struct Score {
    checks: usize,
    wrong: usize,
    surfaces: BTreeMap<usize, usize>,
}

impl Score {
    fn add(&mut self, s: usize, side: f32, positive: bool) {
        if side.abs() < ON_LINE {
            return;
        }
        self.checks += 1;
        if (side > 0.0) != positive {
            self.wrong += 1;
            *self.surfaces.entry(s).or_default() += 1;
        }
    }
    fn line(&self, name: &str) {
        println!(
            "{name:<20} {:>5} wrong-side vertices of {:>6} checks, {:>4} surfaces",
            self.wrong,
            self.checks,
            self.surfaces.len()
        );
    }
}

fn main() {
    let mut args: Vec<String> = std::env::args().skip(1).collect();
    let mut shift = None;
    if let Some(i) = args.iter().position(|a| a == "--translate") {
        let d: Vec<f32> = args[i + 1..i + 4]
            .iter()
            .map(|v| v.parse().expect("delta"))
            .collect();
        shift = Some([d[0], d[1], d[2]]);
        args.drain(i..i + 4);
    }
    let split = args.iter().any(|a| a == "--split");
    args.retain(|a| a != "--split");
    let mut c = load(&args);
    if let Some(d) = shift {
        pack16::translate(&mut c, d);
        println!("translated by {d:?}");
    }
    if split {
        let (n, _) = blam_sbsp::split::fan_split(&mut c, 4);
        println!("fan-split {n} polygon(s)");
    }

    let negated = c
        .bsp2d_references
        .iter()
        .filter(|r| (r.plane as u32) & FLAG != 0)
        .count();
    let frames = node_frames(&c);
    let mut signs: Vec<Vec<bool>> = vec![Vec::new(); c.bsp2d_nodes.len()];
    for r in &c.bsp2d_references {
        let mut stack = vec![r.node];
        while let Some(child) = stack.pop() {
            if child == -1 || (child as u32) & FLAG != 0 {
                continue;
            }
            let i = child as usize;
            signs[i].push((r.plane as u32) & FLAG != 0);
            stack.push(c.bsp2d_nodes[i].left);
            stack.push(c.bsp2d_nodes[i].right);
        }
    }
    let under_negated = frames
        .iter()
        .filter(|f| f.is_some_and(|f| f.negated))
        .count();
    let mixed = signs
        .iter()
        .filter(|s| s.contains(&true) && s.contains(&false))
        .count();
    let shared = signs.iter().filter(|s| s.len() > 1).count();
    println!(
        "references {} (negated {negated}); 2D nodes {} (under a negated reference {under_negated}, reached by >1 reference {shared}, under both signs {mixed})",
        c.bsp2d_references.len(),
        c.bsp2d_nodes.len()
    );

    let polys: Vec<Vec<[f32; 3]>> = (0..c.surfaces.len())
        .map(|s| unpack16::polygon(&c, s))
        .collect();

    // Outline scores, one pass per 2D node under its first reference's frame.
    let mut unsigned = Score::default();
    let mut signed = Score::default();
    for (i, n) in c.bsp2d_nodes.iter().enumerate() {
        let Some(frame) = frames[i] else { continue };
        let plain = pack16::projection_axes(c.planes[frame.plane].n);
        let seen = frame.axes(&c);
        for (child, positive) in [(n.left, false), (n.right, true)] {
            let mut ss = Vec::new();
            collect(&c, child, &mut ss);
            for s in ss {
                for p in &polys[s] {
                    let side =
                        |(u, v): (usize, usize)| n.plane[0] * p[u] + n.plane[1] * p[v] - n.plane[2];
                    unsigned.add(s, side(plain), positive);
                    signed.add(s, side(seen), positive);
                }
            }
        }
    }

    // Clipped scores, per reference. "clipped to leaf": each surface cut to
    // the reference's own bsp3d leaf. "clipped to cell": also cut to the
    // half-planes of the 2D nodes above, so what is scored at a node is the
    // piece of the surface inside that node's region; a surface listed under
    // both children straddles the line by construction and is not scored.
    let halfspaces = leaf_halfspaces(&c);
    let mut ref_leaf: Vec<Option<usize>> = vec![None; c.bsp2d_references.len()];
    for (l, leaf) in c.leaves.iter().enumerate() {
        for k in 0..leaf.reference_count.max(0) as usize {
            if let Some(r) = ref_leaf.get_mut(leaf.first_reference as usize + k) {
                r.get_or_insert(l);
            }
        }
    }
    let inside = |p: &[f32; 3], hs: &[([f32; 3], f32)]| {
        hs.iter()
            .all(|(n, d)| n[0] * p[0] + n[1] * p[1] + n[2] * p[2] - d >= -ON_PLANE)
    };
    let mut to_leaf = Score::default();
    let mut to_cell = Score::default();
    let (mut outline_wrong, mut outline_wrong_outside) = (0usize, 0usize);
    let (mut emptied, mut straddlers) = (0usize, 0usize);
    for (ri, r) in c.bsp2d_references.iter().enumerate() {
        let Some(leaf) = ref_leaf[ri] else { continue };
        let (u, v) = pack16::reference_axes(
            c.planes[(r.plane as u32 & 0x7fff) as usize].n,
            (r.plane as u32) & FLAG != 0,
        );
        let mut stack = vec![(r.node, halfspaces[leaf].clone())];
        while let Some((node, region)) = stack.pop() {
            if node == -1 || (node as u32) & FLAG != 0 {
                continue;
            }
            let n = &c.bsp2d_nodes[node as usize];
            let line = |p: &[f32; 3]| n.plane[0] * p[u] + n.plane[1] * p[v] - n.plane[2];
            let (mut left, mut right) = (Vec::new(), Vec::new());
            collect(&c, n.left, &mut left);
            collect(&c, n.right, &mut right);
            for (child, positive, ss, other) in [
                (n.left, false, &left, &right),
                (n.right, true, &right, &left),
            ] {
                for &s in ss {
                    for p in &polys[s] {
                        let side = line(p);
                        if side.abs() >= ON_LINE && (side > 0.0) != positive {
                            outline_wrong += 1;
                            if !inside(p, &halfspaces[leaf]) {
                                outline_wrong_outside += 1;
                            }
                        }
                    }
                    let piece = clip(&polys[s], &halfspaces[leaf]);
                    if piece.is_empty() {
                        emptied += 1;
                    }
                    for p in &piece {
                        to_leaf.add(s, line(p), positive);
                    }
                    if other.contains(&s) {
                        straddlers += 1;
                        continue;
                    }
                    for p in &clip(&polys[s], &region) {
                        to_cell.add(s, line(p), positive);
                    }
                }
                // The child's region: this side of the line, as a 3D
                // half-space.
                let sign = if positive { 1.0 } else { -1.0 };
                let mut normal = [0.0f32; 3];
                normal[u] = sign * n.plane[0];
                normal[v] = sign * n.plane[1];
                let mut child_region = region.clone();
                child_region.push((normal, sign * n.plane[2]));
                stack.push((child, child_region));
            }
        }
    }

    unsigned.line("unsigned, outlines");
    signed.line("signed, outlines");
    to_leaf.line("clipped to leaf");
    to_cell.line("clipped to cell");
    println!(
        "signed outline checks per reference: {outline_wrong} wrong-side, {outline_wrong_outside} of them outside the reference's leaf"
    );
    println!(
        "({emptied} surface checks clipped to nothing; {straddlers} straddling surface checks not scored in cell mode)"
    );

    let mut worst: Vec<(usize, usize)> = to_cell.surfaces.iter().map(|(&s, &n)| (s, n)).collect();
    worst.sort_by_key(|&(_, n)| std::cmp::Reverse(n));
    for (s, n) in worst.iter().take(8) {
        let sf = &c.surfaces[*s];
        let pl = c.planes[((sf.plane as u32) & 0x7fff) as usize];
        println!(
            "  surface {s}: {n} wrong-side cell vertices, plane {} negated {}, n=({:.3},{:.3},{:.3}) flags {:#x}, {} verts",
            (sf.plane as u32) & 0x7fff,
            (sf.plane as u32) & FLAG != 0,
            pl.n[0],
            pl.n[1],
            pl.n[2],
            sf.flags,
            polys[*s].len()
        );
    }
}
