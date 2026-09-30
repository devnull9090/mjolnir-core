//! Print a definition's supernode[0] as 32 words, so the pass-through
//! encoding can be checked against the traversal code.
//!   cargo run -p blam-sbsp --example super_dump -- <payload> <def>
use blam_sbsp::transplant;
use blam_tag::blockedit::find_block;
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let d: usize = a[1].parse().unwrap();
    let s = find_block(&layout, &file, &root, &format!("{}.bsp3d supernodes", transplant::definition(d))).expect("supernodes");
    println!("def {d}: {} supernode(s)", s.block.count);
    for i in 0..s.block.count.min(2) as usize {
        let e = s.block.element(i).unwrap();
        let words: Vec<String> = e.chunks(4).enumerate().map(|(k, w)| {
            let u = u32::from_le_bytes(w.try_into().unwrap());
            let f = f32::from_le_bytes(w.try_into().unwrap());
            if k < 15 || k == 31 { format!("[{k}]{f:.2}") } else { format!("[{k}]{u:#x}") }
        }).collect();
        println!("  [{i}] {}", words.join(" "));
    }
}
