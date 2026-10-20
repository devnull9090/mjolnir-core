//! List every chunk of the containers in a folder: id, index, type, length,
//! and the file it is indexed as. With an out folder, write each chunk there.
//!
//!   cargo run -p ue-iostore --example chunk_list -- <paks> [utoc substring] [out dir]
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let want = a.get(1).cloned().unwrap_or_default();
    for c in ue_iostore::load_all(&a[0]).expect("containers") {
        let name = c
            .utoc_path
            .file_name()
            .unwrap()
            .to_string_lossy()
            .to_string();
        if !name.contains(want.as_str()) {
            continue;
        }
        println!("{name}");
        for (i, ch) in c.chunks.iter().enumerate() {
            let file = c
                .files
                .iter()
                .find(|(_, idx)| **idx == i)
                .map(|(p, _)| p.as_str())
                .unwrap_or("");
            println!(
                "  {:016x}/{} {:<14} {:>10}  {file}",
                ch.chunk_id,
                ch.chunk_index,
                ch.type_name(),
                ch.length
            );
            if let Some(out) = a.get(2) {
                let bytes = ue_iostore::read_chunk(&c, ch, None, &[]).expect("read");
                std::fs::write(format!("{out}/{i}_{}.bin", ch.type_name()), bytes).expect("write");
            }
        }
    }
}
