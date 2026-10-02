//! The collision a vertical ray finds at (x, y), through the tree and by
//! brute force, for a definition (in its instance's world frame, identity
//! instances only) or the shell.
//!
//!   cargo run -p blam-sbsp --example floor_at -- <payload> <shell|def:N@INSTANCE> <x> <y> <z top> <z bottom>
use blam_sbsp::unpack16::{self, Tables};
use blam_sbsp::{raytest, transplant};
use blam_tag::blockedit::find_block;

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let (base, offset) = if a[1] == "shell" {
        (transplant::SHELL.to_string(), [0.0f32; 3])
    } else {
        let spec = a[1].trim_start_matches("def:");
        let (d, i) = spec.split_once('@').expect("def:N@INSTANCE");
        let (e, _) =
            transplant::donor_element(&file, "instanced geometry instances", i.parse().unwrap())
                .unwrap();
        let f = |o: usize| f32::from_le_bytes(e[o..o + 4].try_into().unwrap());
        (
            transplant::definition(d.parse().unwrap()),
            [f(40), f(44), f(48)],
        )
    };
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
    let (c, _) = unpack16::unpack(&t).expect("unpack");
    let v = |i: usize| a[i].parse::<f32>().unwrap();
    let o = [v(2) - offset[0], v(3) - offset[1], v(4) - offset[2]];
    let d = [0.0, 0.0, v(5) - v(4)];
    let polys: Vec<Vec<[f32; 3]>> = (0..c.surfaces.len())
        .map(|s| unpack16::polygon(&c, s))
        .collect();
    let z = |h: Option<raytest::Hit>| {
        h.map(|h| format!("z {:.3} (surface {})", v(4) + d[2] * h.t, h.surface))
    };
    println!("tree:  {:?}", z(raytest::tree(&c, o, d)));
    println!("brute: {:?}", z(raytest::brute(&c, &polys, o, d)));
    println!("start point leaf: {:?}", raytest::classify(&c, o));
}
