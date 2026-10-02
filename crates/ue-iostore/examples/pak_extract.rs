//! Extract files from the legacy .pak archives whose full path contains a
//! substring, into a directory (keeping the path below the mount point).
//!
//!   cargo run -p ue-iostore --example pak_extract -- <paks> <substring> <out dir>
fn main() {
    let mut args = std::env::args().skip(1);
    let paks = args
        .next()
        .expect("usage: pak_extract <paks> <substring> <out dir>");
    let want = args.next().expect("substring").to_lowercase();
    let out = std::path::PathBuf::from(args.next().expect("out dir"));
    for pak in ue_iostore::pak::load_all(&paks).expect("load paks") {
        for (rel, e) in &pak.files {
            let full = pak.full_path(rel);
            if !full.to_lowercase().contains(&want) {
                continue;
            }
            let bytes = ue_iostore::pak::read_file(&pak, e, None, &[]).expect("read");
            let dest = out.join(full.trim_start_matches("../../../"));
            std::fs::create_dir_all(dest.parent().unwrap()).unwrap();
            std::fs::write(&dest, &bytes).unwrap();
            println!("{} ({} bytes)", dest.display(), bytes.len());
        }
    }
}
