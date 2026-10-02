//! Empty the collision tables of one or more instanced-geometry definitions.
//!
//!   cargo run -p blam-sbsp --example def_clear -- <payload> <out> <def index>...
//!
//! Used to take competing floors out from under a transplant, so what the
//! pawn stands on is unambiguous.
use blam_sbsp::transplant;
use blam_tag::blockedit::{replace_nested, NestedReplace};

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let mut edits = Vec::new();
    for a in &args[2..] {
        let d: usize = a.parse().expect("def index");
        let base = transplant::definition(d);
        for table in [
            "bsp3d nodes",
            "bsp3d supernodes",
            "planes",
            "leaves",
            "bsp2d references",
            "bsp2d nodes",
            "surfaces",
            "edges",
            "vertices",
        ] {
            edits.push(NestedReplace {
                path: format!("{base}.{table}"),
                count: 0,
                elements: Vec::new(),
                wrappers: None,
            });
        }
        println!("  cleared definition {d}");
    }
    let out = replace_nested(&file, &edits).expect("replace");
    let tag = blam_tag::TagFile::parse(&out, None).expect("reparse");
    let l = tag.layout().expect("relayout");
    let block = tag.read_data(&l).expect("reread");
    let payload = tag.data().expect("bdat");
    assert_eq!(block.consumed, payload.size as usize, "does not walk exactly");
    std::fs::write(&args[1], &out).expect("write");
    println!("  wrote {} ({} bytes, walks exactly)", args[1], out.len());
}
