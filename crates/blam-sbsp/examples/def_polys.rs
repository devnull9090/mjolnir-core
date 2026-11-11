//! Print a definition's surfaces: plane, flags, set fields and polygon.
//!   def_polys <sbsp payload> <definition> [first] [count]
use blam_tag::blockedit::find_block;
use blam_sbsp::unpack16::{self, Tables};

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let d: usize = a[1].parse().unwrap();
    let first: usize = a.get(2).map(|x| x.parse().unwrap()).unwrap_or(0);
    let count: usize = a.get(3).map(|x| x.parse().unwrap()).unwrap_or(4);
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let base = blam_sbsp::transplant::definition(d);
    let get = |n: &str| find_block(&layout, &file, &root, &format!("{base}.{n}")).map(|f| f.block.elements).unwrap_or(&[]);
    let t = Tables {
        bsp3d_nodes: get("bsp3d nodes"), planes: get("planes"), leaves: get("leaves"),
        bsp2d_references: get("bsp2d references"), bsp2d_nodes: get("bsp2d nodes"),
        surfaces: get("surfaces"), edges: get("edges"), vertices: get("vertices"),
    };
    let (c, x) = unpack16::unpack(&t).expect("unpack");
    for s in first..(first + count).min(c.surfaces.len()) {
        let su = &c.surfaces[s];
        let pts: Vec<[f32; 3]> = unpack16::polygon(&c, s).iter().map(|p| p.map(|v| (v * 1000.0).round() / 1000.0)).collect();
        println!("surface {s}: plane {:#x} flags {} hi {:#x} set(+6) {} (+8) {} first edge {} poly {:?}", su.plane, su.flags, x.high_flags[s], x.breakable_set[s], x.breakable[s], su.first_edge, pts);
    }
    for (i, e) in c.edges.iter().enumerate().take(12) {
        println!("edge {i}: v {} {} fwd {} rev {} left {} right {}", e.start, e.end, e.forward, e.reverse, e.left, e.right);
    }
}
