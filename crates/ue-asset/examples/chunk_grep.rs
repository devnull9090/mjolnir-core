//! Extract a package's chunks and report where a needle appears in them.
//!
//!   cargo run -p ue-asset --example chunk_grep -- <paks> <path substring> <needle>
fn main() {
    let mut args = std::env::args().skip(1);
    let paks = args.next().expect("usage: chunk_grep <paks> <substring> <needle>");
    let want = args.next().expect("substring");
    let needle = args.next().expect("needle");
    let containers = ue_iostore::load_all(&paks).expect("load containers");
    let pat = needle.as_bytes();
    for c in &containers {
        for (path, idx) in &c.files {
            if !path.to_lowercase().contains(&want.to_lowercase()) {
                continue;
            }
            let chunk = &c.chunks[*idx];
            let data = match ue_iostore::read_chunk(c, chunk, None, &[]) {
                Ok(d) => d,
                Err(e) => {
                    println!("{path}: read failed: {e}");
                    continue;
                }
            };
            let mut hits = Vec::new();
            for i in 0..data.len().saturating_sub(pat.len()) {
                if &data[i..i + pat.len()] == pat {
                    hits.push(i);
                }
            }
            println!("{path} [{}] {} bytes: {} hit(s) for {:?}",
                c.utoc_path.file_name().unwrap().to_string_lossy(), data.len(), hits.len(), needle);
            for h in hits.iter().take(8) {
                let lo = h.saturating_sub(32);
                let hi = (h + 48).min(data.len());
                let ctx: String = data[lo..hi].iter()
                    .map(|&b| if (0x20..0x7f).contains(&b) { b as char } else { '.' })
                    .collect();
                println!("   0x{h:x}: {ctx}");
            }
        }
    }
}
