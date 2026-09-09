//! Walk a definition's bsp3d tree with a point, the way the sim's standing
//! test does, and report the leaf and the surfaces its 2D references resolve
//! to. A sweep down a vertical line shows whether the floor is found.
//!
//!   cargo run -p blam-sbsp --example bsp_point -- <payload> <def> <lx> <ly> <z from> <z to> [steps]
//!
//! The MOPP is only the broadphase for sweeps; once the pawn is on the ground
//! the sim keeps it there by point-classifying the bsp3d tree, so a tree that
//! lands the pawn and then loses it is exactly what a bad leaf under the spawn
//! would look like.
use blam_sbsp::pack16::projection_axes;
use blam_sbsp::unpack16::{self, Tables};
use blam_sbsp::{ce, transplant};
use blam_tag::blockedit::find_block;

const LEAF: u32 = 0x8000_0000;

/// Descend from node 0: returns (leaf index or None, depth, path of node ids).
fn classify(c: &ce::Collision, p: [f32; 3]) -> (Option<usize>, Vec<usize>) {
    let mut path = Vec::new();
    let mut cur: i32 = 0;
    for _ in 0..512 {
        if cur == -1 {
            return (None, path);
        }
        if (cur as u32) & LEAF != 0 {
            return (Some((cur as u32 & 0x7fff_ffff) as usize), path);
        }
        let n = &c.bsp3d_nodes[cur as usize];
        path.push(cur as usize);
        let pl = &c.planes[(n.plane as u32 & 0x7fff_ffff) as usize];
        let flip = (n.plane as u32) & LEAF != 0;
        let mut d = pl.n[0] * p[0] + pl.n[1] * p[1] + pl.n[2] * p[2] - pl.d;
        if flip {
            d = -d;
        }
        cur = if d >= 0.0 { n.front } else { n.back };
    }
    (None, path)
}

/// Resolve one 2D reference for a point: project onto the reference's plane
/// and descend its 2D tree. Returns the surface, if the tree names one.
fn resolve_2d(c: &ce::Collision, r: &ce::Bsp2dReference, p: [f32; 3]) -> Option<usize> {
    let plane = &c.planes[(r.plane as u32 & 0x7fff) as usize];
    let mut n = plane.n;
    if (r.plane as u32) & LEAF != 0 {
        n = [-n[0], -n[1], -n[2]];
    }
    let (u, v) = projection_axes(n);
    let (pu, pv) = (p[u], p[v]);
    let mut cur = r.node;
    for _ in 0..512 {
        if cur == -1 {
            return None;
        }
        if (cur as u32) & LEAF != 0 {
            return Some((cur as u32 & 0x7fff_ffff) as usize);
        }
        let node = &c.bsp2d_nodes[cur as usize];
        let d = node.plane[0] * pu + node.plane[1] * pv - node.plane[2];
        cur = if d >= 0.0 { node.right } else { node.left };
    }
    None
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    if a.len() < 6 {
        eprintln!("usage: bsp_point <payload> <def> <lx> <ly> <z from> <z to> [steps]");
        std::process::exit(2);
    }
    let file = std::fs::read(&a[0]).expect("read");
    let d: usize = a[1].parse().unwrap();
    let (lx, ly): (f32, f32) = (a[2].parse().unwrap(), a[3].parse().unwrap());
    let (z0, z1): (f32, f32) = (a[4].parse().unwrap(), a[5].parse().unwrap());
    let steps: usize = a.get(6).map(|s| s.parse().unwrap()).unwrap_or(12);

    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let coll = transplant::definition(d);
    let get = |n: &str| -> &[u8] {
        find_block(&layout, &file, &root, &format!("{coll}.{n}"))
            .map(|f| f.block.elements)
            .unwrap_or(&[])
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
    let (c, _) = unpack16::unpack(&t).expect("unpack");
    println!(
        "definition {d}: {} nodes, {} leaves, {} 2d refs, {} surfaces",
        c.bsp3d_nodes.len(),
        c.leaves.len(),
        c.bsp2d_references.len(),
        c.surfaces.len()
    );

    // The surfaces whose polygon box spans this xy, with their top z, as the
    // truth the tree has to agree with.
    let mut under: Vec<(usize, f32, f32)> = Vec::new();
    for s in 0..c.surfaces.len() {
        let poly = unpack16::polygon(&c, s);
        if poly.len() < 3 {
            continue;
        }
        let (mut xl, mut xh, mut yl, mut yh, mut zl, mut zh) =
            (f32::MAX, f32::MIN, f32::MAX, f32::MIN, f32::MAX, f32::MIN);
        for p in &poly {
            xl = xl.min(p[0]);
            xh = xh.max(p[0]);
            yl = yl.min(p[1]);
            yh = yh.max(p[1]);
            zl = zl.min(p[2]);
            zh = zh.max(p[2]);
        }
        if xl <= lx && lx <= xh && yl <= ly && ly <= yh {
            under.push((s, zl, zh));
        }
    }
    under.sort_by(|p, q| q.2.partial_cmp(&p.2).unwrap());
    println!(
        "surfaces spanning ({lx:.2}, {ly:.2}) by top z: {}",
        under
            .iter()
            .take(8)
            .map(|(s, zl, zh)| format!("#{s}[{zl:.2}..{zh:.2}]"))
            .collect::<Vec<_>>()
            .join(" ")
    );

    for i in 0..=steps {
        let z = z0 + (z1 - z0) * i as f32 / steps as f32;
        let p = [lx, ly, z];
        let (leaf, path) = classify(&c, p);
        match leaf {
            None => println!("  z {z:7.2}: NO LEAF (depth {})", path.len()),
            Some(l) => {
                let lf = &c.leaves[l];
                let refs: Vec<&ce::Bsp2dReference> = (0..lf.reference_count.max(0) as usize)
                    .filter_map(|k| c.bsp2d_references.get(lf.first_reference as usize + k))
                    .collect();
                let mut found: Vec<String> = Vec::new();
                for r in &refs {
                    if let Some(s) = resolve_2d(&c, r, p) {
                        let pl = &c.planes[(r.plane as u32 & 0x7fff) as usize];
                        let dist = pl.n[0] * p[0] + pl.n[1] * p[1] + pl.n[2] * p[2] - pl.d;
                        found.push(format!("#{s}(n.z {:.2}, dist {:+.2})", pl.n[2], dist));
                    }
                }
                println!(
                    "  z {z:7.2}: leaf {l} flags {:#04x} depth {} refs {} -> {}",
                    lf.flags,
                    path.len(),
                    refs.len(),
                    if found.is_empty() { "(no surface)".to_string() } else { found.join(" ") }
                );
            }
        }
    }
}
