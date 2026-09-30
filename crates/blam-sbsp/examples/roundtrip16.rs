//! Decode a shipped collision block, re-pack it, and compare — the encoder's
//! offline proof. Then work out how a 3D plane projects to the 2D split
//! planes beneath it, by scoring every candidate convention against the
//! surfaces the shipped 2D trees actually sort.
//!
//!   cargo run -p blam-sbsp --example roundtrip16 -- <payload> <def index>...
//!   cargo run -p blam-sbsp --example roundtrip16 -- <payload> shell
use blam_sbsp::pack16;
use blam_sbsp::transplant;
use blam_sbsp::unpack16::{self, Tables};
use blam_tag::blockedit::find_block;

fn diff(name: &str, original: &[u8], repacked: &[u8], size: usize) -> usize {
    if original == repacked {
        println!("   {name:<18} {:>6} element(s)  identical", original.len() / size);
        return 0;
    }
    let mut bad_elements = 0;
    let mut first: Option<(usize, usize)> = None;
    for (i, (a, b)) in original
        .chunks(size)
        .zip(repacked.chunks(size))
        .enumerate()
    {
        if a != b {
            bad_elements += 1;
            if first.is_none() {
                let off = a.iter().zip(b).position(|(x, y)| x != y).unwrap_or(0);
                first = Some((i, off));
            }
        }
    }
    let (i, off) = first.unwrap_or((0, 0));
    println!(
        "   {name:<18} {:>6} element(s)  {bad_elements} differ (first: element {i} byte {off}; lengths {} vs {})",
        original.len() / size,
        original.len(),
        repacked.len()
    );
    bad_elements
}

fn main() {
    let mut args: Vec<String> = std::env::args().skip(1).collect();
    // `--translate dx dy dz`: move the decoded geometry before the projection
    // probe, so the fixed translate can be checked against shipped data.
    let mut shift: Option<[f32; 3]> = None;
    if let Some(i) = args.iter().position(|a| a == "--translate") {
        shift = Some([
            args[i + 1].parse().unwrap(),
            args[i + 2].parse().unwrap(),
            args[i + 3].parse().unwrap(),
        ]);
        args.drain(i..i + 4);
    }
    let file = std::fs::read(&args[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");

    for a in &args[1..] {
        let base = if a == "shell" {
            transplant::SHELL.to_string()
        } else {
            transplant::definition(a.parse().expect("def index"))
        };
        println!("== {base}");
        let get = |name: &str| -> &[u8] {
            find_block(&layout, &file, &root, &format!("{base}.{name}"))
                .unwrap_or_else(|e| panic!("{name}: {e}"))
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
        let (mut c, extras) = unpack16::unpack(&t).expect("unpack");
        if let Some(d) = shift {
            pack16::translate(&mut c, d);
            println!("   translated by {d:?} before the probe (round trip will differ)");
        }
        let packed = pack16::pack(&c, &(|m: i16| m)).expect("pack");

        // Put the fields CE cannot carry back before comparing surfaces, so
        // only genuine encoding disagreements show.
        let mut surfaces = packed.surfaces.clone();
        for (i, s) in surfaces.chunks_exact_mut(14).enumerate() {
            s[6..8].copy_from_slice(&extras.breakable_set[i].to_le_bytes());
            s[8..10].copy_from_slice(&extras.breakable[i].to_le_bytes());
            let flags = u16::from_le_bytes([s[10], s[11]]) | extras.high_flags[i];
            s[10..12].copy_from_slice(&flags.to_le_bytes());
            s[12] = extras.best_plane_vertex[i];
        }
        let mut leaves = packed.leaves.clone();
        for (i, l) in leaves.chunks_exact_mut(8).enumerate() {
            l[1] = t.leaves[i * 8 + 1];
        }
        let mut vertices = packed.vertices.clone();
        for (i, v) in vertices.chunks_exact_mut(16).enumerate() {
            v[14..16].copy_from_slice(&t.vertices[i * 16 + 14..i * 16 + 16]);
        }

        let mut bad = 0;
        bad += diff("bsp3d nodes", t.bsp3d_nodes, &packed.bsp3d_nodes, 8);
        bad += diff("planes", t.planes, &packed.planes, 16);
        bad += diff("leaves", t.leaves, &leaves, 8);
        bad += diff("bsp2d references", t.bsp2d_references, &packed.bsp2d_references, 4);
        bad += diff("bsp2d nodes", t.bsp2d_nodes, &packed.bsp2d_nodes, 16);
        bad += diff("surfaces", t.surfaces, &surfaces, 14);
        bad += diff("edges", t.edges, &packed.edges, 12);
        bad += diff("vertices", t.vertices, &vertices, 16);
        println!("   round trip: {}", if bad == 0 { "EXACT" } else { "differs" });

        projection_probe(&c);
    }
}

/// Which two axes a 3D plane projects onto, for the 2D planes under it.
fn axes(n: [f32; 3], variant: usize) -> (usize, usize) {
    let a = (0..3)
        .max_by(|&i, &j| n[i].abs().partial_cmp(&n[j].abs()).unwrap())
        .unwrap();
    let (p, q) = ((a + 1) % 3, (a + 2) % 3);
    let positive = n[a] > 0.0;
    match variant {
        0 => (p, q),
        1 => (q, p),
        2 => {
            if positive {
                (p, q)
            } else {
                (q, p)
            }
        }
        _ => {
            if positive {
                (q, p)
            } else {
                (p, q)
            }
        }
    }
}

/// Score each projection convention: every surface reached through a 2D
/// node's left child should project to the negative side of that node's
/// line, the right child to the positive side (or the reverse, which is the
/// other half of the candidate set).
fn projection_probe(c: &blam_sbsp::ce::Collision) {
    let polys: Vec<Vec<[f32; 3]>> = (0..c.surfaces.len())
        .map(|s| unpack16::polygon(c, s))
        .collect();

    // Surfaces under each 2D node, gathered per side.
    fn collect(c: &blam_sbsp::ce::Collision, child: i32, out: &mut Vec<usize>, depth: usize) {
        if child == -1 || depth > 64 {
            return;
        }
        if (child as u32) & 0x8000_0000 != 0 {
            out.push((child as u32 & 0x7fff) as usize);
            return;
        }
        if let Some(n) = c.bsp2d_nodes.get(child as usize) {
            collect(c, n.left, out, depth + 1);
            collect(c, n.right, out, depth + 1);
        }
    }

    for variant in 0..4 {
        for right_is_positive in [true, false] {
            let mut good = 0usize;
            let mut badc = 0usize;
            for r in &c.bsp2d_references {
                if r.node == -1 || (r.node as u32) & 0x8000_0000 != 0 {
                    continue;
                }
                let plane_index = (r.plane as u32 & 0x7fff) as usize;
                let Some(plane) = c.planes.get(plane_index) else { continue };
                let (u, v) = axes(plane.n, variant);
                let mut stack = vec![r.node];
                while let Some(node_index) = stack.pop() {
                    if node_index == -1 || (node_index as u32) & 0x8000_0000 != 0 {
                        continue;
                    }
                    let Some(n) = c.bsp2d_nodes.get(node_index as usize) else { continue };
                    for (child, positive_side) in [(n.left, false), (n.right, true)] {
                        let mut surfaces = Vec::new();
                        collect(c, child, &mut surfaces, 0);
                        for s in surfaces {
                            for p in &polys[s] {
                                let side = n.plane[0] * p[u] + n.plane[1] * p[v] - n.plane[2];
                                if side.abs() < 1e-4 {
                                    continue;
                                }
                                let is_positive = side > 0.0;
                                let expect = if right_is_positive {
                                    positive_side
                                } else {
                                    !positive_side
                                };
                                if is_positive == expect {
                                    good += 1;
                                } else {
                                    badc += 1;
                                }
                            }
                        }
                        stack.push(child);
                    }
                }
            }
            let total = good + badc;
            println!(
                "   projection variant {variant} right{}positive: {good}/{total} vertex checks agree ({:.1}%)",
                if right_is_positive { "=" } else { "!=" },
                if total > 0 { 100.0 * good as f64 / total as f64 } else { 0.0 }
            );
        }
    }
}
