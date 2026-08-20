//! Probe a tag package's zen header: summary fields, name-batch hashes, and
//! export public hashes, each compared against candidate derivations. This is
//! how the rename surgery's hash formulas get pinned before anything is
//! written.
//!
//!   cargo run -p ue-asset --example zen_probe -- <paks> <tag-path-substring>

fn city(bytes: &[u8]) -> u64 {
    ue_iostore::city::city_hash64(bytes)
}

fn utf16le(s: &str) -> Vec<u8> {
    let mut out = Vec::with_capacity(s.len() * 2);
    for u in s.encode_utf16() {
        out.extend_from_slice(&u.to_le_bytes());
    }
    out
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let paks = args.next().expect("usage: zen_probe <paks> <substring>");
    let want = args.next().expect("usage: zen_probe <paks> <substring>");

    let containers = ue_iostore::load_all(&paks)?;
    for c in &containers {
        for (rel, chunk_index) in &c.files {
            let full = c.full_path(rel);
            if !full.contains(&want) || !full.ends_with(".uasset") {
                continue;
            }
            println!("== {full}");
            let chunk = c.chunks[*chunk_index];
            let data = ue_iostore::read_chunk(c, &chunk, None, &[])?;
            println!("   chunk id {:#018x}, {} bytes", chunk.chunk_id, data.len());

            let pkg = ue_asset::zen::Package::parse(&data)?;
            println!("   package name {:?}", pkg.name);
            println!(
                "   header_size {:#x} cooked_header_size {:#x}",
                pkg.header_size, pkg.cooked_header_size
            );
            for off in [0usize, 16, 24, 28, 32, 36, 40, 44, 48] {
                let v = u32::from_le_bytes(data[off..off + 4].try_into().unwrap());
                println!("   summary[{off:2}] = {v:#x}");
            }

            // Name-batch hashes vs candidates.
            let count =
                u32::from_le_bytes(data[52..56].try_into().unwrap()) as usize;
            let hash_base = 52 + 8 + 8; // count+bytes, then hash version u64
            let version =
                u64::from_le_bytes(data[60..68].try_into().unwrap());
            println!("   {} name(s), hash version {version:#x}", count);
            for (i, name) in pkg.names.iter().enumerate() {
                let stored = u64::from_le_bytes(
                    data[hash_base + i * 8..hash_base + i * 8 + 8]
                        .try_into()
                        .unwrap(),
                );
                let lower = name.to_lowercase();
                let c_utf8 = city(lower.as_bytes());
                let c_utf16 = city(&utf16le(&lower));
                let tag = if stored == c_utf8 {
                    "= city(utf8 lower)"
                } else if stored == c_utf16 {
                    "= city(utf16 lower)"
                } else {
                    "≠ both candidates"
                };
                println!("   name[{i}] {name:?} stored {stored:#018x} {tag}");
            }

            for (i, e) in pkg.exports.iter().enumerate() {
                let lower = e.name.to_lowercase();
                let candidates = [
                    ("city(utf16 lower leaf)", city(&utf16le(&lower))),
                    ("city(utf8 lower leaf)", city(lower.as_bytes())),
                ];
                let tag = candidates
                    .iter()
                    .find(|(_, v)| *v == e.public_hash)
                    .map(|(n, _)| *n)
                    .unwrap_or("≠ candidates");
                println!(
                    "   export[{i}] {:?} public_hash {:#018x} {tag} (class {:?})",
                    e.name,
                    e.public_hash,
                    e.class.classify()
                );
            }
            println!("   imports: {} object refs", pkg.imports.len());
            println!("   imported package names: {}", pkg.imported_package_names.len());
            for n in pkg.imported_package_names.iter().take(4) {
                println!("     {n:?} -> {:#018x}", ue_iostore::city::package_id(n));
            }
            return Ok(());
        }
    }
    println!("no match");
    Ok(())
}
// (extended by store-entry probe below via a second binary)
