//! Counts of every block a definition carries, beside its collision tables.
//!
//!   cargo run -p blam-sbsp --example def_parts -- <payload> <def index>...
use blam_tag::blockedit::find_block;

const DEFS: &str = "resource interface.raw_resources[0].raw_items.instanced geometries definitions";

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    for a in &args[1..] {
        let i: usize = a.parse().expect("index");
        println!("-- definition {i}");
        for path in [
            "collision info.surfaces",
            "poopie cutter collision.surfaces",
            "render bsp",
            "mopp codes",
            "breakable surface sets",
            "polyhedra_with_materials",
            "polyhedron four vectors",
            "polyhedron plane equations",
            "surfaces",
            "surface to triangle mapping",
        ] {
            let full = format!("{DEFS}[{i}].{path}");
            match find_block(&layout, &file, &root, &full) {
                Ok(f) => println!(
                    "   {path:<34} {:>6} element(s), {} bytes each",
                    f.block.count,
                    if f.block.count > 0 {
                        f.block.elements.len() / f.block.count as usize
                    } else {
                        0
                    }
                ),
                Err(e) => println!("   {path:<34} n/a ({e})"),
            }
        }
    }
}
