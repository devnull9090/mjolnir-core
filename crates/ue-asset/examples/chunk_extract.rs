//! Write one container's copy of a package chunk out to a file, so an
//! installed override can be checked as the game would read it.
//!
//!   cargo run -p ue-asset --example chunk_extract -- <paks> <utoc substring> <path substring> <out> [chunk type]
//!
//! The chunk type (1 package, 2 bulk) picks which of an unindexed override
//! container's chunks to take when the path cannot be matched.
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let (paks, utoc, want, out) = (&a[0], &a[1], a[2].to_ascii_lowercase(), &a[3]);
    let kind: u8 = a
        .get(4)
        .map(|k| k.parse().expect("chunk type"))
        .unwrap_or(1);
    let containers = ue_iostore::load_all(paks).expect("containers");
    let c = containers
        .iter()
        .find(|c| {
            c.utoc_path
                .file_name()
                .map(|n| n.to_string_lossy().contains(utoc.as_str()))
                .unwrap_or(false)
        })
        .expect("no container matched");
    let (rel, idx) = c
        .files
        .iter()
        .find(|(p, _)| p.to_ascii_lowercase().contains(&want))
        .map(|(p, i)| (p.clone(), *i))
        .unwrap_or_else(|| {
            // A pure override container has no file index: fall back to the
            // one package-type chunk it carries.
            let i = c
                .chunks
                .iter()
                .position(|k| k.chunk_type == kind)
                .expect("no chunk of that type in this container");
            (format!("chunk {i}"), i)
        });
    let data = ue_iostore::read_chunk(c, &c.chunks[idx], None, &[]).expect("read chunk");
    println!(
        "{} from {}: {} bytes",
        rel,
        c.utoc_path.file_name().unwrap().to_string_lossy(),
        data.len()
    );
    std::fs::write(out, &data).expect("write");
    println!("  wrote {out}");
}
