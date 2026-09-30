//! Drop the Havok mopp of one or more instanced-geometry definitions so the
//! engine falls back to their collision BSP, as it does for the 65 shipped
//! definitions that carry none. A transplanted definition keeps the donor's
//! mopp, which indexes the new surface table as garbage.
//!
//!   cargo run -p blam-sbsp --example def_nomopp -- <payload> <out> <def index>...
use blam_sbsp::transplant;
use blam_tag::blockedit::{replace_nested, NestedReplace};

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let mut edits = Vec::new();
    for a in &args[2..] {
        let d: usize = a.parse().expect("def index");
        edits.push(NestedReplace {
            path: format!("{}.mopp codes", transplant::definition(d).trim_end_matches(".collision info")),
            count: 0,
            elements: Vec::new(),
            wrappers: None,
        });
        println!("  dropped the mopp of definition {d}");
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
