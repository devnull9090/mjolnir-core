//! The inline 12-byte block fields of a definition's collision info, and the
//! tgbl section headers they point at, shipped versus rewritten.
//!   cargo run -p blam-sbsp --example block_headers -- <payload> <def>
use blam_sbsp::transplant;
use blam_tag::blockedit::find_block;
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let fp = file.as_ptr() as usize;
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let d: usize = a[1].parse().unwrap();
    let defs = find_block(&layout, &file, &root, "resource interface.raw_resources[0].raw_items.instanced geometries definitions").expect("defs");
    let e = defs.block.element(d).unwrap();
    // collision info struct starts at +8; nine 12-byte block fields follow in order.
    let names = ["bsp3d nodes", "bsp3d supernodes", "planes", "leaves", "bsp2d references", "bsp2d nodes", "surfaces", "edges", "vertices"];
    for (k, n) in names.iter().enumerate() {
        let o = 8 + k * 12;
        let w: Vec<u32> = (0..3).map(|j| u32::from_le_bytes(e[o + j * 4..o + j * 4 + 4].try_into().unwrap())).collect();
        let f = find_block(&layout, &file, &root, &format!("{}.{n}", transplant::definition(d))).expect(n);
        let start = f.block.elements.as_ptr() as usize - fp;
        // section header precedes the elements: 12 bytes magic/version/size then {count, flags}
        let hdr = &file[start - 20..start];
        let hx: Vec<String> = hdr.iter().map(|b| format!("{b:02x}")).collect();
        println!("{n:<18} inline {{{}, {:#x}, {:#x}}}  count {} flags {}  header {}", w[0], w[1], w[2], f.block.count, f.block.flags, hx.join(" "));
    }
}
