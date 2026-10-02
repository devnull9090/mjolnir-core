//! Which collision materials a definition's surfaces use, and what the
//! definition's material table holds.
//!
//!   cargo run -p blam-sbsp --example def_materials -- <payload> <def index>...
use blam_sbsp::transplant;
use blam_tag::blockedit::find_block;

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    for d in &a[1..] {
        let coll = transplant::definition(d.parse().unwrap());
        let base = coll.trim_end_matches(".collision info");
        let surfaces =
            find_block(&layout, &file, &root, &format!("{coll}.surfaces")).expect("surfaces");
        let mut hist = std::collections::BTreeMap::new();
        for i in 0..surfaces.block.count as usize {
            let e = surfaces.block.element(i).unwrap();
            // (material +4, flags +10), as block_fields prints the 16-bit surface
            let m = (
                i16::from_le_bytes([e[4], e[5]]),
                u16::from_le_bytes([e[10], e[11]]),
            );
            *hist.entry(m).or_insert(0usize) += 1;
        }
        let mats = find_block(
            &layout,
            &file,
            &root,
            &format!("{base}.collision info.materials"),
        )
        .or_else(|_| find_block(&layout, &file, &root, &format!("{coll}.materials")))
        .map(|f| f.block.count)
        .unwrap_or(0);
        println!("definition {d}: {} surfaces, material histogram {hist:?}; materials block count {mats}", surfaces.block.count);
    }
}
