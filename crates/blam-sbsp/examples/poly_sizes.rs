//! Histogram of surface vertex counts: shipped definitions versus a transplant.
//!
//!   cargo run -p blam-sbsp --example poly_sizes -- <payload> <def index>... [shell]
use blam_sbsp::transplant;
use blam_sbsp::unpack16::{self, Tables};
use blam_tag::blockedit::find_block;
use std::collections::BTreeMap;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    for a in &args[1..] {
        let base = if a == "shell" { transplant::SHELL.to_string() } else { transplant::definition(a.parse().unwrap()) };
        let get = |n: &str| -> &[u8] { find_block(&layout, &file, &root, &format!("{base}.{n}")).unwrap().block.elements };
        let t = Tables {
            bsp3d_nodes: get("bsp3d nodes"), planes: get("planes"), leaves: get("leaves"),
            bsp2d_references: get("bsp2d references"), bsp2d_nodes: get("bsp2d nodes"),
            surfaces: get("surfaces"), edges: get("edges"), vertices: get("vertices"),
        };
        let (c, extras) = unpack16::unpack(&t).expect("unpack");
        let mut hist: BTreeMap<usize, usize> = BTreeMap::new();
        for s in 0..c.surfaces.len() {
            *hist.entry(unpack16::polygon(&c, s).len()).or_default() += 1;
        }
        let mats: BTreeMap<i16, usize> = c.surfaces.iter().fold(BTreeMap::new(), |mut m, s| { *m.entry(s.material).or_default() += 1; m });
        let bpv: BTreeMap<u8, usize> = extras.best_plane_vertex.iter().fold(BTreeMap::new(), |mut m, &v| { *m.entry(v).or_default() += 1; m });
        let flags: BTreeMap<u16, usize> = extras.high_flags.iter().zip(&c.surfaces).fold(BTreeMap::new(), |mut m, (&h, s)| { *m.entry(h | s.flags as u16).or_default() += 1; m });
        println!("== {a}: verts/poly {hist:?}");
        println!("   materials {mats:?}");
        println!("   best-plane-vertex {:?}", bpv.iter().take(8).collect::<Vec<_>>());
        println!("   flags {flags:?}  breakable set {:?}", extras.breakable_set.iter().fold(BTreeMap::new(), |mut m: BTreeMap<i16, usize>, &v| { *m.entry(v).or_default() += 1; m }));
    }
}
