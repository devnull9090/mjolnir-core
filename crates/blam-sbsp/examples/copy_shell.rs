//! Copy one shipped sbsp's world shell into another, verbatim.
//!
//! ```text
//! cargo run -p blam-sbsp --example copy_shell -- <donor.ubulk> <source.ubulk> <out.ubulk> [--no-mopp]
//! ```
//!
//! The donor keeps its instances, kd hierarchy and everything else; the nine
//! shell tables, the root per-leaf and per-edge companions, the four kd
//! companion tables and (unless `--no-mopp`) the `structure_physics` mopp
//! come from the source, untranslated. Bounds follow the source. This is the
//! probe that separates "the engine walks the winged-edge tables" from "the
//! engine walks the Havok mopp": the same shell with and without its mopp.

use blam_sbsp::transplant::{set_scalar, SHELL};
use blam_tag::blockedit::{element_with_wrapper, find_block, replace_nested, NestedReplace};

const TABLES: [&str; 9] = [
    "bsp3d nodes",
    "bsp3d supernodes",
    "planes",
    "leaves",
    "bsp2d references",
    "bsp2d nodes",
    "surfaces",
    "edges",
    "vertices",
];

fn copy_block(source: &[u8], path: &str) -> NestedReplace {
    let tag = blam_tag::TagFile::parse(source, None).expect("parse source");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let found = find_block(&layout, source, &root, path).unwrap_or_else(|e| panic!("{path}: {e}"));
    let mut wrappers = Vec::new();
    for i in 0..found.block.count as usize {
        let (_, w) = element_with_wrapper(source, path, i).expect("element");
        wrappers.push(w);
    }
    NestedReplace {
        path: path.to_string(),
        count: found.block.count,
        elements: found.block.elements.to_vec(),
        wrappers: if found.block.flags == 0 {
            Some(wrappers)
        } else {
            None
        },
    }
}

fn scalar_text(file: &[u8], path: &str) -> String {
    let tag = blam_tag::TagFile::parse(file, None).unwrap();
    let layout = tag.layout().unwrap();
    let root = tag.read_data(&layout).unwrap();
    let t = blam_tag::patch::resolve(&layout, file, &root, path)
        .unwrap_or_else(|e| panic!("{path}: {e}"));
    t.current.display().to_string()
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let no_mopp = args.iter().any(|a| a == "--no-mopp");
    let pos: Vec<&String> = args.iter().filter(|a| !a.starts_with("--")).collect();
    if pos.len() < 3 {
        eprintln!("usage: copy_shell <donor> <source> <out> [--no-mopp]");
        std::process::exit(2);
    }
    let donor = std::fs::read(pos[0]).expect("donor");
    let source = std::fs::read(pos[1]).expect("source");

    let mut edits = Vec::new();
    for t in TABLES {
        edits.push(copy_block(&source, &format!("{SHELL}.{t}")));
    }
    for t in [
        "leaves",
        "edge to seam edge",
        "super aabbs",
        "super node parent mappings",
        "super node recursable_masks",
        "structure_super_node_traversal_geometry_block",
    ] {
        edits.push(copy_block(&source, t));
    }
    if !no_mopp {
        edits.push(copy_block(&source, "structure_physics.mopp code block"));
    }
    for e in &edits {
        println!(
            "  {} <- {} element(s), {} B",
            e.path,
            e.count,
            e.elements.len()
        );
    }
    let mut out = replace_nested(&donor, &edits).expect("replace");

    for path in [
        "world bounds x",
        "world bounds y",
        "world bounds z",
        "clusters[0].bounds x",
        "clusters[0].bounds y",
        "clusters[0].bounds z",
    ] {
        let v = scalar_text(&source, path);
        out = set_scalar(&out, path, &v).unwrap_or_else(|e| panic!("{path}: {e}"));
        println!("  {path} = {v}");
    }
    if !no_mopp {
        for path in [
            "structure_physics.mopp bounds min",
            "structure_physics.mopp bounds max",
        ] {
            let v = scalar_text(&source, path);
            out = set_scalar(&out, path, &v).unwrap_or_else(|e| panic!("{path}: {e}"));
            println!("  {path} = {v}");
        }
    }

    let tag = blam_tag::TagFile::parse(&out, None).expect("parse out");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("walk");
    let payload = tag.data().expect("bdat");
    assert_eq!(root.consumed, payload.size as usize, "output walks exactly");
    std::fs::write(pos[2], &out).expect("write");
    println!("wrote {} ({} -> {} bytes)", pos[2], donor.len(), out.len());
}
