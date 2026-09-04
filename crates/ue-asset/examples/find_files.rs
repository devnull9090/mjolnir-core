//! Find packages whose path matches any of the given substrings.
//!
//!   cargo run -p ue-asset --example find_files -- <paks> <substring>...
fn main() {
    let mut args = std::env::args().skip(1);
    let paks = args.next().expect("usage: find_files <paks> <substring>...");
    let wants: Vec<String> = args.map(|a| a.to_lowercase()).collect();
    let containers = ue_iostore::load_all(&paks).expect("load containers");
    let mut hits: Vec<(String, String, u64)> = Vec::new();
    for c in &containers {
        for (path, idx) in &c.files {
            let lower = path.to_lowercase();
            if wants.iter().any(|w| lower.contains(w)) {
                hits.push((path.clone(), c.utoc_path.file_name().unwrap().to_string_lossy().to_string(), c.chunks[*idx].length));
            }
        }
    }
    hits.sort();
    for (p, c, n) in &hits {
        println!("{p}  [{c}]  {n} bytes");
    }
    println!("{} match(es)", hits.len());
}
