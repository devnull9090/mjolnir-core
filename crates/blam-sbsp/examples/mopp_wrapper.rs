//! Show how a definition's mopp element carries its bytecode: element bytes
//! and the tgst wrapper that holds the nested code block.
//!   cargo run -p blam-sbsp --example mopp_wrapper -- <payload> <def>
use blam_sbsp::transplant;
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let d: usize = a[1].parse().unwrap();
    let path = format!("{}.mopp codes", transplant::definition(d).trim_end_matches(".collision info"));
    let (element, wrapper) = transplant::donor_element(&file, &path, 0).expect("donor element");
    println!("element {} bytes, wrapper {} bytes", element.len(), wrapper.len());
    for (i, chunk) in wrapper.chunks(16).take(4).enumerate() {
        let hex: Vec<String> = chunk.iter().map(|x| format!("{x:02x}")).collect();
        let asc: String = chunk.iter().map(|&b| if (0x20..0x7f).contains(&b) { b as char } else { '.' }).collect();
        println!("  wrapper {:04x}: {:<48} {asc}", i * 16, hex.join(" "));
    }
    let n = wrapper.len();
    for (i, chunk) in wrapper[n.saturating_sub(32)..].chunks(16).enumerate() {
        let hex: Vec<String> = chunk.iter().map(|x| format!("{x:02x}")).collect();
        println!("  wrapper tail {:04x}: {}", n.saturating_sub(32) + i * 16, hex.join(" "));
    }
}
