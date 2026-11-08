//! Rebuild a container with one indexed file's chunk replaced.
//!
//! ```text
//! cargo run -p ue-iostore --example replace_chunk -- \
//!     <paks> <utoc substring> <indexed path suffix> <replacement file | none> <out dir>
//! ```
//!
//! For an edit to a shipped package that a rebake cannot reproduce: a map
//! container's scenario with its teleporter ends' owner bytes changed
//! (tools/level/fix_teleporter_teams.py), where a rebake would also renumber
//! the bots' pathfinding or bring later bake changes. Every other chunk, the
//! container header and the directory index are carried over as read; the
//! container goes back out through `pack::build_indexed`, the writer `level
//! bake` uses, which recomputes offsets and the BLAKE3 chunk metas the game
//! checks. "none" rebuilds with nothing replaced, the control for the
//! rebuild path itself. The written container is read back and every chunk
//! must yield the intended bytes.
use std::path::PathBuf;

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    if a.len() < 5 {
        eprintln!("usage: replace_chunk <paks> <utoc substring> <indexed path suffix> <replacement|none> <out dir>");
        std::process::exit(2);
    }
    let (paks, want, suffix, replacement, out_dir) = (&a[0], &a[1], &a[2], &a[3], &a[4]);
    let oodle: Vec<PathBuf> = Vec::new();

    let containers = ue_iostore::load_all(paks).expect("load containers");
    let matches: Vec<_> = containers
        .iter()
        .filter(|c| {
            c.utoc_path
                .file_name()
                .is_some_and(|n| n.to_string_lossy().contains(want.as_str()))
        })
        .collect();
    if matches.len() != 1 {
        eprintln!("{} containers match {want:?}, expected one", matches.len());
        std::process::exit(1);
    }
    let c = matches[0];

    let targets: Vec<_> = c.files.iter().filter(|(path, _)| path.ends_with(suffix.as_str())).collect();
    if targets.len() != 1 {
        eprintln!("{} indexed files end with {suffix:?}, expected one", targets.len());
        std::process::exit(1);
    }
    let (target_path, target_index) = (targets[0].0.clone(), *targets[0].1);
    let new_data = if replacement == "none" {
        None
    } else {
        Some(std::fs::read(replacement).expect("read the replacement"))
    };

    // In the order they lie in the .ucas, which is the order the writer was
    // given them: so an unchanged rebuild comes out byte for byte.
    let mut order: Vec<_> = c.chunks.iter().collect();
    order.sort_by_key(|ch| ch.offset);
    let mut entries: Vec<ue_iostore::pack::Entry> = Vec::new();
    let mut chunk_to_entry = std::collections::HashMap::new();
    for ch in order {
        let mut data = ue_iostore::read_chunk(c, ch, None, &oodle).expect("read chunk");
        if ch.index == target_index {
            if let Some(new) = &new_data {
                println!("  {target_path}: {} -> {} bytes", data.len(), new.len());
                data = new.clone();
            }
        }
        chunk_to_entry.insert(ch.index, entries.len());
        entries.push(ue_iostore::pack::Entry {
            id: ue_iostore::toc::ChunkId {
                id: ch.chunk_id,
                index: ch.chunk_index,
                pad: 0,
                kind: ch.chunk_type,
            },
            data,
            meta: Vec::new(),
        });
    }

    let mut files: Vec<(String, usize)> = c
        .files
        .iter()
        .filter_map(|(path, chunk_index)| chunk_to_entry.get(chunk_index).map(|e| (path.clone(), *e)))
        .collect();
    // In chunk order, as the bake lists them.
    files.sort_by_key(|f| f.1);
    let template = ue_iostore::toc::Toc::read(&c.utoc_path).expect("read toc");
    let built = ue_iostore::pack::build_indexed(
        &template,
        c.container_id,
        &entries,
        Some((c.mount_point.as_str(), &files)),
    );

    std::fs::create_dir_all(out_dir).expect("create out dir");
    let stem = c.utoc_path.file_stem().unwrap().to_string_lossy().to_string();
    let utoc = format!("{out_dir}/{stem}.utoc");
    let ucas = format!("{out_dir}/{stem}.ucas");
    std::fs::write(&utoc, &built.utoc).expect("write utoc");
    std::fs::write(&ucas, &built.ucas).expect("write ucas");

    // Read it back the way the game does and hold every chunk to its bytes.
    let back = ue_iostore::load_all(out_dir).expect("read the written container back");
    let back = back
        .iter()
        .find(|b| b.utoc_path.file_stem().is_some_and(|s| s.to_string_lossy() == stem))
        .expect("the written container is not readable");
    if back.chunks.len() != entries.len() || back.files.len() != files.len() {
        eprintln!("read back {} chunks / {} files, wrote {} / {}", back.chunks.len(), back.files.len(),
                  entries.len(), files.len());
        std::process::exit(1);
    }
    let intended: std::collections::HashMap<_, _> =
        entries.iter().map(|e| ((e.id.id, e.id.index, e.id.kind), &e.data)).collect();
    for ch in &back.chunks {
        let got = ue_iostore::read_chunk(back, ch, None, &oodle).expect("read back chunk");
        if intended.get(&(ch.chunk_id, ch.chunk_index, ch.chunk_type)) != Some(&&got) {
            eprintln!("chunk {} reads back wrong", ch.index);
            std::process::exit(1);
        }
    }
    println!(
        "  wrote {utoc} ({} bytes) and {ucas} ({} bytes): {} chunks read back intact",
        built.utoc.len(),
        built.ucas.len(),
        entries.len()
    );
}
