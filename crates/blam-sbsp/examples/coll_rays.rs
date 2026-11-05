//! Check a collision model's regions offline: the tables hold together, and
//! rays through the packed tree stop where the polygons say, along all three
//! axes.
//!
//!   cargo run -p blam-sbsp --example coll_rays -- <collision_model payload or .bsp.json>
//!
//! A collision model's phantom and missed counts are the source's as much as
//! the packing's: run the staged BSP too and compare.
use blam_sbsp::ce::Collision;
use blam_sbsp::unpack16::{self, Tables};
use blam_sbsp::{raytest, validate};
use blam_tag::blockedit::find_block;

const STEPS: usize = 48;

fn main() {
    let path = std::env::args().nth(1).expect("payload path");
    if path.ends_with(".bsp.json") {
        let staged = blam_sbsp::ce::load(path.as_ref()).expect("load");
        println!("{}", rays(&staged.collision));
        return;
    }
    let file = std::fs::read(&path).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let regions = find_block(&layout, &file, &root, "regions").expect("regions");
    let mut failed = false;
    for region in 0..regions.block.count as usize {
        let perm = format!("regions[{region}].permutations[0]");
        let bsps = find_block(&layout, &file, &root, &format!("{perm}.bsps")).expect("bsps");
        if bsps.block.count == 0 {
            continue;
        }
        let base = format!("{perm}.bsps[0].bsp");
        let report = validate::at(&file, &base).expect("validate");
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
        let r = rays(&c);
        println!("region {region}: {} problem(s); {r}", report.problems.len());
        for p in report.problems.iter().take(5) {
            println!("  problem: {p}");
        }
        failed |= !report.problems.is_empty();
    }
    if failed {
        std::process::exit(1);
    }
}

fn rays(c: &Collision) -> String {
    let b = c.bounds().expect("bounds");
    let mut rays = Vec::new();
    for axis in 0..3 {
        let (u, v) = ((axis + 1) % 3, (axis + 2) % 3);
        for i in 0..STEPS {
            for j in 0..STEPS {
                let at = |k: usize, n: usize| {
                    b.min[k] + (b.max[k] - b.min[k]) * (n as f32 + 0.37) / STEPS as f32
                };
                let mut from = [0.0; 3];
                from[u] = at(u, i);
                from[v] = at(v, j);
                let mut to = from;
                from[axis] = b.max[axis] + 0.5;
                to[axis] = b.min[axis] - 0.5;
                rays.push((from, to));
            }
        }
    }
    let r = raytest::compare(c, &rays, 0.005);
    format!(
        "{} surfaces, bounds {:?}..{:?}; {} rays, {} hit, {} missed, {} displaced, {} phantom",
        c.surfaces.len(),
        b.min,
        b.max,
        r.rays,
        r.expected,
        r.missed,
        r.displaced,
        r.phantom
    )
}
