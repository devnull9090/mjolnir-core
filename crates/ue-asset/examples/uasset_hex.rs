//! Full hex + parsed exports of a tag's .uasset, and list its container chunks.
//!   cargo run -p ue-asset --example uasset_hex -- <paks> <path substring>
use ue_asset::zen::Package;
fn main() {
    let mut a = std::env::args().skip(1);
    let paks = a.next().unwrap(); let want = a.next().unwrap();
    for c in ue_iostore::load_all(&paks).expect("load") {
        let hits: Vec<_> = c.files.iter().filter(|(p, _)| p.to_lowercase().contains(&want.to_lowercase())).collect();
        for (path, idx) in hits {
            let ch = &c.chunks[*idx];
            println!("{path}  chunk_id {:#x} type {} len {}  [{}]", ch.chunk_id, ch.chunk_type, ch.length, c.utoc_path.file_name().unwrap().to_string_lossy());
            if path.ends_with(".uasset") {
                let data = ue_iostore::read_chunk(&c, ch, None, &[]).expect("read");
                if let Ok(pkg) = Package::parse(&data) {
                    println!("  header {} names {} imports {} exports {}", pkg.header_size, pkg.names.len(), pkg.imports.len(), pkg.exports.len());
                }
                for (i, row) in data.chunks(32).enumerate() {
                    let hx: Vec<String> = row.iter().map(|b| format!("{b:02x}")).collect();
                    let asc: String = row.iter().map(|&b| if (0x20..0x7f).contains(&b) { b as char } else { '.' }).collect();
                    println!("  {:04x}: {:<96} {asc}", i * 32, hx.join(" "));
                }
            }
        }
    }
}
