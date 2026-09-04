//! List the files of one container by utoc filename substring.
//!
//!   cargo run -p ue-asset --example container_ls -- <paks> <utoc substring>
fn main() {
    let mut args = std::env::args().skip(1);
    let paks = args.next().expect("paks");
    let want = args.next().expect("utoc substring");
    for c in ue_iostore::load_all(&paks).expect("load") {
        let name = c.utoc_path.file_name().unwrap().to_string_lossy().to_string();
        if !name.contains(&want) {
            continue;
        }
        println!("{name}: {} chunk(s), {} indexed file(s)", c.chunks.len(), c.files.len());
        let mut paths: Vec<&String> = c.files.keys().collect();
        paths.sort();
        for p in paths.iter().take(40) {
            println!("  {p}");
        }
    }
}
