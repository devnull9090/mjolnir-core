//! Where a shell's point test says "inside": sample a grid over the shell's
//! box (or a given box) and report the inside fraction and extent, plus
//! named probe points.
//!
//!   cargo run -p blam-sbsp --example shell_inside -- <payload> <step> [x y z]...
use blam_sbsp::unpack16::{self, Tables};
use blam_sbsp::{raytest, transplant};
use blam_tag::blockedit::find_block;

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let step: f32 = a[1].parse().unwrap();
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let base = transplant::SHELL;
    let get = |n: &str| -> &[u8] {
        find_block(&layout, &file, &root, &format!("{base}.{n}"))
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
    let b = c.bounds().expect("bounds");
    println!(
        "shell: {} nodes, {} leaves, {} surfaces; vertex box x[{:.1},{:.1}] y[{:.1},{:.1}] z[{:.1},{:.1}]",
        c.bsp3d_nodes.len(), c.leaves.len(), c.surfaces.len(),
        b.min[0], b.max[0], b.min[1], b.max[1], b.min[2], b.max[2]
    );
    let mut rest = a[2..].iter().map(|s| s.parse::<f32>().unwrap());
    while let (Some(x), Some(y), Some(z)) = (rest.next(), rest.next(), rest.next()) {
        println!(
            "  ({x:.2}, {y:.2}, {z:.2}): {:?}",
            raytest::classify(&c, [x, y, z])
        );
    }
    let (mut n, mut inside) = (0usize, 0usize);
    let mut lo = [f32::MAX; 3];
    let mut hi = [f32::MIN; 3];
    let mut z = b.min[2];
    while z <= b.max[2] {
        let mut y = b.min[1];
        while y <= b.max[1] {
            let mut x = b.min[0];
            while x <= b.max[0] {
                n += 1;
                if raytest::classify(&c, [x, y, z]).is_some() {
                    inside += 1;
                    for (k, v) in [x, y, z].into_iter().enumerate() {
                        lo[k] = lo[k].min(v);
                        hi[k] = hi[k].max(v);
                    }
                }
                x += step;
            }
            y += step;
        }
        z += step;
    }
    println!(
        "{inside} of {n} samples inside; inside extent x[{:.1},{:.1}] y[{:.1},{:.1}] z[{:.1},{:.1}]",
        lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]
    );
}
