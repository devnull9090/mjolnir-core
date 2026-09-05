//! Dump a container's ContainerHeader (type-6) chunk: hex to stdout, raw bytes
//! to a file next to the utoc. Reference material for the header writer.
//!
//!   cargo run -p ue-iostore --example dump_header -- <utoc> [oodle-dir]

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let utoc = args.next().expect("usage: dump_header <utoc> [oodle-dir]");
    let oodle: Vec<std::path::PathBuf> = args.next().map(Into::into).into_iter().collect();

    let c = ue_iostore::load_container(&utoc)?;
    println!("container {} — {} chunks", utoc, c.chunks.len());
    for (i, chunk) in c.chunks.iter().enumerate() {
        println!(
            "  [{i}] id {:#018x} index {} type {} ({}) size {}",
            chunk.chunk_id,
            chunk.chunk_index,
            chunk.chunk_type,
            chunk.type_name(),
            chunk.length
        );
    }
    let Some(header) = c.chunks.iter().find(|ch| ch.chunk_type == 6) else {
        println!("no ContainerHeader chunk");
        return Ok(());
    };
    let bytes = ue_iostore::read_chunk(&c, header, None, &oodle)?;
    let out = format!("{utoc}.container-header.bin");
    std::fs::write(&out, &bytes)?;
    println!("\nContainerHeader: {} bytes -> {out}", bytes.len());
    for (i, row) in bytes.chunks(16).enumerate().take(64) {
        let hex: Vec<String> = row.iter().map(|b| format!("{b:02x}")).collect();
        let ascii: String = row
            .iter()
            .map(|&b| if (32..127).contains(&b) { b as char } else { '.' })
            .collect();
        println!("{:06x}  {:<48}  {ascii}", i * 16, hex.join(" "));
    }
    Ok(())
}
