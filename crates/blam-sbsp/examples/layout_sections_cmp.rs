//! Compare the layout's child sections between two payloads of one group.
//!   cargo run -p blam-sbsp --example layout_sections_cmp -- <a> <b>
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let fa = std::fs::read(&a[0]).unwrap(); let fb = std::fs::read(&a[1]).unwrap();
    let ta = blam_tag::TagFile::parse(&fa, None).unwrap(); let tb = blam_tag::TagFile::parse(&fb, None).unwrap();
    let la = ta.layout().unwrap(); let lb = tb.layout().unwrap();
    for (sa, sb) in la.sections.iter().zip(lb.sections.iter()) {
        let same = sa.content == sb.content;
        let first_diff = sa.content.iter().zip(sb.content.iter()).position(|(x, y)| x != y);
        println!("{:<6} {:>7} vs {:>7} bytes  {}", String::from_utf8_lossy(&sa.magic), sa.size, sb.size,
            if same { "identical".to_string() } else { format!("DIFFER (first at {:?})", first_diff) });
    }
}
