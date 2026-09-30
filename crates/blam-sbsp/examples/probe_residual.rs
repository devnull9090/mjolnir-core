//! Where the projection probe disagrees: shared 2D subtrees, negated planes,
//! or near-coplanar noise.
//!
//!   cargo run -p blam-sbsp --example probe_residual -- <payload> <def index>
use blam_sbsp::pack16::{node_planes, projection_axes};
use blam_sbsp::transplant;
use blam_sbsp::unpack16::{self, Tables};
use blam_tag::blockedit::find_block;
use std::collections::HashMap;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let base = transplant::definition(args[1].parse().expect("def"));
    let get = |name: &str| -> &[u8] {
        find_block(&layout, &file, &root, &format!("{base}.{name}")).unwrap().block.elements
    };
    let t = Tables {
        bsp3d_nodes: get("bsp3d nodes"), planes: get("planes"), leaves: get("leaves"),
        bsp2d_references: get("bsp2d references"), bsp2d_nodes: get("bsp2d nodes"),
        surfaces: get("surfaces"), edges: get("edges"), vertices: get("vertices"),
    };
    let (c, _) = unpack16::unpack(&t).expect("unpack");

    // How many references reach each 2D node, and with how many distinct planes.
    let mut owners: Vec<Vec<usize>> = vec![Vec::new(); c.bsp2d_nodes.len()];
    for r in &c.bsp2d_references {
        let plane = (r.plane as u32 & 0x7fff) as usize;
        let mut stack = vec![r.node];
        while let Some(child) = stack.pop() {
            if child == -1 || (child as u32) & 0x8000_0000 != 0 { continue; }
            let i = child as usize;
            owners[i].push(plane);
            stack.push(c.bsp2d_nodes[i].left);
            stack.push(c.bsp2d_nodes[i].right);
        }
    }
    let shared = owners.iter().filter(|o| {
        let mut d = o.to_vec(); d.sort(); d.dedup(); d.len() > 1
    }).count();
    let multi = owners.iter().filter(|o| o.len() > 1).count();
    println!("2D nodes {}: reached by >1 reference {}, by references with different planes {}",
        c.bsp2d_nodes.len(), multi, shared);

    // Disagreements, bucketed by |side| magnitude and by plane negation.
    let planes = node_planes(&c);
    let polys: Vec<Vec<[f32; 3]>> = (0..c.surfaces.len()).map(|s| unpack16::polygon(&c, s)).collect();
    fn collect(c: &blam_sbsp::ce::Collision, child: i32, out: &mut Vec<usize>) {
        if child == -1 { return; }
        if (child as u32) & 0x8000_0000 != 0 { out.push((child as u32 & 0x7fff) as usize); return; }
        if let Some(n) = c.bsp2d_nodes.get(child as usize) { collect(c, n.left, out); collect(c, n.right, out); }
    }
    let mut buckets: HashMap<&str, usize> = HashMap::new();
    let mut bad_surfaces: HashMap<usize, usize> = HashMap::new();
    let mut total = 0usize;
    for (i, n) in c.bsp2d_nodes.iter().enumerate() {
        let Some(plane) = planes[i] else { continue };
        let (u, v) = projection_axes(c.planes[plane].n);
        for (child, positive) in [(n.left, false), (n.right, true)] {
            let mut ss = Vec::new();
            collect(&c, child, &mut ss);
            for s in ss {
                let negated = (c.surfaces[s].plane as u32) & 0x8000_0000 != 0;
                for p in &polys[s] {
                    let side = n.plane[0] * p[u] + n.plane[1] * p[v] - n.plane[2];
                    if side.abs() < 1e-4 { continue; }
                    total += 1;
                    if (side > 0.0) != positive {
                        let key = if side.abs() < 0.01 { "|side|<0.01" } else if side.abs() < 0.1 { "|side|<0.1" } else { "|side|>=0.1" };
                        *buckets.entry(key).or_default() += 1;
                        *buckets.entry(if negated { "surface plane negated" } else { "surface plane plain" }).or_default() += 1;
                        *bad_surfaces.entry(s).or_default() += 1;
                    }
                }
            }
        }
    }
    println!("{total} checks; disagreements by bucket: {buckets:?}");

    // Alternative: take the projection from the reference's signed plane (a
    // negated reference flips the normal, so the cyclic/swapped choice flips).
    let mut ref_sign: Vec<Option<bool>> = vec![None; c.bsp2d_nodes.len()];
    for r in &c.bsp2d_references {
        let neg = (r.plane as u32) & 0x8000_0000 != 0;
        let mut stack = vec![r.node];
        while let Some(child) = stack.pop() {
            if child == -1 || (child as u32) & 0x8000_0000 != 0 { continue; }
            let i = child as usize;
            if ref_sign[i].is_some() { continue; }
            ref_sign[i] = Some(neg);
            stack.push(c.bsp2d_nodes[i].left);
            stack.push(c.bsp2d_nodes[i].right);
        }
    }
    let mut good2 = 0usize; let mut bad2 = 0usize;
    for (i, n) in c.bsp2d_nodes.iter().enumerate() {
        let (Some(plane), Some(neg)) = (planes[i], ref_sign[i]) else { continue };
        let mut nn = c.planes[plane].n;
        if neg { for a in 0..3 { nn[a] = -nn[a]; } }
        let (u, v) = projection_axes(nn);
        for (child, positive) in [(n.left, false), (n.right, true)] {
            let mut ss = Vec::new();
            collect(&c, child, &mut ss);
            for s in ss { for p in &polys[s] {
                let side = n.plane[0] * p[u] + n.plane[1] * p[v] - n.plane[2];
                if side.abs() < 1e-4 { continue; }
                if (side > 0.0) == positive { good2 += 1 } else { bad2 += 1 }
            } }
        }
    }
    println!("with reference sign folded into the projection: {good2}/{} agree", good2 + bad2);

    println!("{} distinct surfaces disagree", bad_surfaces.len());
    let mut worst: Vec<(usize, usize)> = bad_surfaces.into_iter().collect();
    worst.sort_by_key(|&(_, n)| std::cmp::Reverse(n));
    for (s, n) in worst.iter().take(5) {
        let sf = &c.surfaces[*s];
        let pl = c.planes[((sf.plane as u32) & 0x7fff) as usize];
        println!("  surface {s}: {n} bad vertices, plane {} negated {}, n=({:.3},{:.3},{:.3}) flags {:#x}, {} verts",
            (sf.plane as u32) & 0x7fff, (sf.plane as u32) & 0x8000_0000 != 0, pl.n[0], pl.n[1], pl.n[2], sf.flags, polys[*s].len());
    }
}
