//! Copy one instanced-geometry definition's collision tables over another's.
//!
//!   cargo run -p blam-sbsp --example def_copy -- <payload> <out> <src def> <dst def> [instance]
//!
//! A control for the transplant: it exercises the same write path with
//! geometry the game itself shipped, so a hang afterwards is the writer's
//! fault and not the transcoded data's.
use blam_sbsp::transplant;
use blam_tag::blockedit::{find_block, replace_nested, NestedReplace};

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let src: usize = args[2].parse().expect("src");
    let dst: usize = args[3].parse().expect("dst");

    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");

    let from = transplant::definition(src);
    let to = transplant::definition(dst);
    let mut edits = Vec::new();
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
        let f = find_block(&layout, &file, &root, &format!("{from}.{table}")).expect("src table");
        println!("  {table:<18} {} element(s)", f.block.count);
        edits.push(NestedReplace {
            path: format!("{to}.{table}"),
            count: f.block.count,
            elements: f.block.elements.to_vec(),
            wrappers: None,
        });
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
