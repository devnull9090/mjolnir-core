//! Count the chunk types in every IoStore container (where the shader code
//! lives, for one).
//!
//!   cargo run -p ue-iostore --example chunk_types -- <paks>
fn main() {
    let paks = std::env::args().nth(1).expect("usage: chunk_types <paks>");
    for c in ue_iostore::load_all(&paks).expect("load containers") {
        let mut counts: std::collections::BTreeMap<String, (usize, u64)> = Default::default();
        for ch in &c.chunks {
            let e = counts.entry(ch.type_name().to_string()).or_default();
            e.0 += 1;
            e.1 += ch.length;
        }
        let row: Vec<String> = counts
            .iter()
            .map(|(k, (n, b))| format!("{k}:{n}/{}MB", b >> 20))
            .collect();
        println!(
            "{}  {}",
            c.utoc_path.file_name().unwrap().to_string_lossy(),
            row.join("  ")
        );
    }
}
