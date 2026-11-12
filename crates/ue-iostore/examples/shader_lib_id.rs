//! Print each container's ShaderCodeLibrary chunk ids beside the id UE
//! derives from `<Project>_Chunk<N>-<format>` for the number in its name.
//!
//!   cargo run -p ue-iostore --example shader_lib_id -- <paks> [substring]
fn id_for(name: &str) -> u64 {
    let lower = name.to_lowercase();
    let bytes: Vec<u8> = lower.encode_utf16().flat_map(|c| c.to_le_bytes()).collect();
    ue_iostore::city::city_hash64(&bytes)
}

fn main() {
    let mut args = std::env::args().skip(1);
    let paks = args.next().expect("usage: shader_lib_id <paks> [substring]");
    let want = args.next().map(|s| s.to_lowercase());
    for c in ue_iostore::load_all(&paks).expect("load containers") {
        let name = c.utoc_path.file_stem().unwrap().to_string_lossy().to_string();
        if want.as_ref().is_some_and(|w| !name.to_lowercase().contains(w)) {
            continue;
        }
        let libs: Vec<_> = c.chunks.iter().filter(|ch| ch.type_name() == "ShaderCodeLibrary").collect();
        if libs.is_empty() {
            continue;
        }
        let digits: String = name.trim_start_matches("pakchunk").chars().take_while(|c| c.is_ascii_digit()).collect();
        println!("{name}");
        for ch in &libs {
            println!("  chunk {:016x} index {} len {}", ch.chunk_id, ch.chunk_index, ch.length);
        }
        for fmt in ["PCD3D_SM6-PCD3D_SM6", "PCD3D_SM5-PCD3D_SM5", "PCD3D_SM6", "PCD3D_SM5"] {
            let s = format!("Meteorite_Chunk{digits}-{fmt}");
            println!("  {s} -> {:016x}", id_for(&s));
        }
    }
}
