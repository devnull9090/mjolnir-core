//! Check a collision BSP's tree against its own polygons with rays
//! ([`blam_sbsp::raytest`]): vertical rays on a grid, and short slanted
//! sweeps like a moving pawn's.
//!
//!   cargo run -p blam-sbsp --example ray_probe -- ce <collision_N.json> [step]
//!   cargo run -p blam-sbsp --example ray_probe -- packed <collision_N.json> [step]
//!   cargo run -p blam-sbsp --example ray_probe -- def <payload> <index> [step]
//!   cargo run -p blam-sbsp --example ray_probe -- shell <payload> [step]
//!
//! `ce` tests the staged CE tables as exported; `packed` runs them through the
//! fan split and the 16-bit pack and back, which is what the game receives.
use blam_sbsp::unpack16::{self, Tables};
use blam_sbsp::{ce, pack16, raytest, split, transplant};
use blam_tag::blockedit::find_block;

fn from_payload(path: &str, base: &str) -> ce::Collision {
    let file = std::fs::read(path).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
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
    unpack16::unpack(&t).expect("unpack").0
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let (c, rest) = match a[0].as_str() {
        "ce" => (
            ce::load(std::path::Path::new(&a[1]))
                .expect("staging")
                .collision,
            2,
        ),
        "packed" => {
            let mut c = ce::load(std::path::Path::new(&a[1]))
                .expect("staging")
                .collision;
            split::fan_split(&mut c, 4);
            let p = pack16::pack(&c, &(|_: i16| 0i16)).expect("pack");
            let t = Tables {
                bsp3d_nodes: &p.bsp3d_nodes,
                planes: &p.planes,
                leaves: &p.leaves,
                bsp2d_references: &p.bsp2d_references,
                bsp2d_nodes: &p.bsp2d_nodes,
                surfaces: &p.surfaces,
                edges: &p.edges,
                vertices: &p.vertices,
            };
            (unpack16::unpack(&t).expect("unpack").0, 2)
        }
        "def" => (
            from_payload(&a[1], &transplant::definition(a[2].parse().unwrap())),
            3,
        ),
        "shell" => (from_payload(&a[1], transplant::SHELL), 2),
        other => panic!("unknown source {other}"),
    };
    let step: f32 = a.get(rest).map(|s| s.parse().unwrap()).unwrap_or(1.0);
    let b = c.bounds().expect("bounds");
    println!(
        "{} surface(s), {} leaves; bounds x[{:.2},{:.2}] y[{:.2},{:.2}] z[{:.2},{:.2}]",
        c.surfaces.len(),
        c.leaves.len(),
        b.min[0],
        b.max[0],
        b.min[1],
        b.max[1],
        b.min[2],
        b.max[2]
    );
    let floors = raytest::floors(&c, b, step, 0.6);
    println!(
        "{} walkable floor point(s) with open space above",
        floors.len()
    );
    let (down, slanted) = raytest::floor_rays(&floors, 0.6, 1.0);
    for (name, rays) in [("down    ", down), ("slanted ", slanted)] {
        let r = raytest::compare(&c, &rays, 0.05);
        println!(
            "{name}: {} rays, {} should hit: missed {} ({:.2}%), displaced {}, phantom {}",
            r.rays,
            r.expected,
            r.missed,
            100.0 * r.missed as f32 / r.expected.max(1) as f32,
            r.displaced,
            r.phantom
        );
        for (o, e) in r.examples.iter().take(3) {
            println!(
                "    miss ({:.2}, {:.2}, {:.2}) -> ({:.2}, {:.2}, {:.2})",
                o[0], o[1], o[2], e[0], e[1], e[2]
            );
        }
    }
}
