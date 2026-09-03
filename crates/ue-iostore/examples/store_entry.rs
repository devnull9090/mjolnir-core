//! Find a package's FFilePackageStoreEntry in the shipped ContainerHeaders and
//! dump it, testing offset interpretations for the import carray.
//!
//!   cargo run -p ue-iostore --example store_entry -- <paks> <package-id-hex>

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let paks = args.next().expect("usage: store_entry <paks> <id-hex>");
    let want = u64::from_str_radix(
        args.next().expect("id").trim_start_matches("0x"),
        16,
    )?;

    let containers = ue_iostore::load_all(&paks)?;
    for c in &containers {
        for chunk in &c.chunks {
            if chunk.chunk_type != 6 {
                continue;
            }
            let bytes = ue_iostore::read_chunk(c, chunk, None, &[])?;
            let h = ue_iostore::container_header::ContainerHeader::parse(&bytes)?;
            let Some(pos) = h.package_ids.iter().position(|&id| id == want) else {
                continue;
            };
            println!(
                "{}: package {want:#018x} is entry {pos} of {}",
                c.utoc_path.file_name().unwrap_or_default().to_string_lossy(),
                h.package_ids.len()
            );
            let entry_at = pos * 16;
            let e = &h.store_entries[entry_at..entry_at + 16];
            let count = u32::from_le_bytes(e[0..4].try_into()?) as usize;
            let off = u32::from_le_bytes(e[4..8].try_into()?) as usize;
            let sh_count = u32::from_le_bytes(e[8..12].try_into()?);
            let sh_off = u32::from_le_bytes(e[12..16].try_into()?);
            println!("  entry bytes: count={count} off={off:#x} shader_count={sh_count} shader_off={sh_off:#x}");
            // Candidate interpretations for where the import ids live:
            let candidates = [
                ("offset relative to the offset field itself", entry_at + 4 + off),
                ("offset relative to entry start", entry_at + off),
                ("offset relative to store block start", off),
            ];
            for (name, base) in candidates {
                let ok = h
                    .store_entries
                    .get(base..base + count.min(4) * 8)
                    .map(|d| {
                        d.chunks_exact(8)
                            .map(|c| u64::from_le_bytes(c.try_into().unwrap()))
                            .collect::<Vec<_>>()
                    });
                println!("  {name}: first ids {ok:x?}");
            }
            return Ok(());
        }
    }
    println!("not found in any header");
    Ok(())
}
