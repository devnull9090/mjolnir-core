//! Print a chunk's TOC meta record beside its data, to identify the hash.
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let utoc = args.next().expect("usage: meta_probe <utoc>");
    let c = ue_iostore::load_container(&utoc)?;
    let toc = ue_iostore::toc::Toc::read(&utoc)?;
    for (slot, id) in toc.chunk_ids.iter().enumerate().take(4) {
        let entry = c
            .chunks
            .iter()
            .find(|ch| ch.chunk_id == id.id && ch.chunk_index == id.index && ch.chunk_type == id.kind)
            .unwrap();
        let data = ue_iostore::read_chunk(&c, entry, None, &[])?;
        let meta = toc.meta(slot).unwrap();
        println!("chunk type {} len {}", id.kind, data.len());
        println!("  meta {}", meta.iter().map(|b| format!("{b:02x}")).collect::<String>());
        std::fs::write(format!("target/meta-probe-{slot}.bin"), &data)?;
    }
    Ok(())
}
