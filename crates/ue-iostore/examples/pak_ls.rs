//! List the files in every legacy .pak under a Paks directory (the shader
//! libraries, asset registry and other non-IoStore files live there).
//!
//!   cargo run -p ue-iostore --example pak_ls -- <paks> [substring]
fn main() {
    let mut args = std::env::args().skip(1);
    let paks = args.next().expect("usage: pak_ls <paks> [substring]");
    let want = args.next().map(|s| s.to_lowercase());
    for pak in ue_iostore::pak::load_all(&paks).expect("load paks") {
        for (rel, e) in &pak.files {
            let p = pak.full_path(rel);
            if want.as_ref().is_some_and(|w| !p.to_lowercase().contains(w)) {
                continue;
            }
            println!(
                "{}  {}  {} bytes",
                pak.path.file_name().unwrap().to_string_lossy(),
                p,
                e.uncompressed_size
            );
        }
    }
}
