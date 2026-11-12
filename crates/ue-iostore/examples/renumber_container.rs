//! Write a copy of a container under another chunk number, its shader
//! library renamed to match.
//!
//!   cargo run -p ue-iostore --example renumber_container -- \
//!       <container.utoc> <from> <to> <out base path, no extension>
use ue_iostore::toc::Toc;

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let [utoc, from, to, out] = a.as_slice() else {
        panic!("usage: renumber_container <container.utoc> <from> <to> <out base>");
    };
    let before = Toc::read(utoc).expect("read utoc");
    let mut toc = before.clone();
    let n = ue_iostore::shader_library::renumber(
        &mut toc,
        "Meteorite",
        from.parse().unwrap(),
        to.parse().unwrap(),
    )
    .expect("renumber");
    // Every chunk still resolves the way the engine's reader looks it up, to
    // the same bytes of the data file.
    for (i, id) in before.chunk_ids.iter().enumerate() {
        let moved = before.chunk_ids[i].kind == ue_iostore::shader_library::LIBRARY;
        let slot = if moved {
            toc.chunk_ids.iter().position(|c| c.kind == id.kind && toc.find_chunk_by_hash(c).is_some() && !before.chunk_ids.contains(c))
        } else {
            toc.find_chunk_by_hash(id)
        }
        .unwrap_or_else(|| panic!("chunk {:016x} lost", id.id));
        assert_eq!(toc.chunk_offsets[slot], before.chunk_offsets[i]);
        assert_eq!(toc.meta(slot), before.meta(i));
    }
    std::fs::write(format!("{out}.utoc"), toc.write()).expect("write utoc");
    std::fs::copy(utoc.replace(".utoc", ".ucas"), format!("{out}.ucas")).expect("copy ucas");
    println!("{n} librar{} renamed, {} chunks, {} seeds", if n == 1 { "y" } else { "ies" }, toc.chunk_ids.len(), toc.perfect_hash_seed_count);
}
