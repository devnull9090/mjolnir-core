//! Write one packaged file out of the containers in a folder, by path.
//!
//!   cargo run -p ue-iostore --example extract_file -- <containers dir> <path substring> <out file>
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let containers = ue_iostore::load_all(&a[0]).expect("load containers");
    for c in &containers {
        if let Some((path, i)) = c.files.iter().find(|(p, _)| p.contains(a[1].as_str())) {
            let bytes = ue_iostore::read_chunk(c, &c.chunks[*i], None, &[]).expect("read");
            std::fs::write(&a[2], &bytes).expect("write");
            println!("{path}: {} bytes -> {}", bytes.len(), a[2]);
            return;
        }
    }
    eprintln!("no file matching {:?}", a[1]);
    std::process::exit(1);
}
