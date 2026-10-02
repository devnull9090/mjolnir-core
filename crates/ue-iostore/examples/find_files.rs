//! List every file in the shipped containers whose path contains one of the
//! given substrings (case-insensitive).
//!
//!     cargo run --release -p ue-iostore --example find_files -- <Paks dir> <needle>...
use std::env;

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!("usage: find_files <Paks dir> <needle>...");
        std::process::exit(2);
    }
    let needles: Vec<String> = args[2..].iter().map(|n| n.to_lowercase()).collect();
    let containers = ue_iostore::load_all(&args[1]).expect("load containers");
    let mut hits: Vec<String> = Vec::new();
    for c in &containers {
        for path in c.files.keys() {
            let full = c.full_path(path);
            let lower = full.to_lowercase();
            if needles.iter().any(|n| lower.contains(n)) {
                hits.push(full);
            }
        }
    }
    hits.sort();
    hits.dedup();
    for h in &hits {
        println!("{h}");
    }
    eprintln!("{} file(s)", hits.len());
}
