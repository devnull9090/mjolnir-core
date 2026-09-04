//! Top-level sections of a tag file and the layout's child sections.
//!   cargo run -p blam-sbsp --example tag_sections -- <payload>
fn main() {
    let path = std::env::args().nth(1).expect("payload");
    let file = std::fs::read(&path).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    println!("file {} bytes", file.len());
    for s in tag.sections() {
        println!("  top {:<6} v{} size {:>9} at {}", String::from_utf8_lossy(&s.magic), s.version, s.size, s.at);
    }
    let layout = tag.layout().expect("layout");
    for s in &layout.sections {
        println!("  tgly child {:<6} v{} size {:>9} at {}", String::from_utf8_lossy(&s.magic), s.version, s.size, s.at);
    }
}
