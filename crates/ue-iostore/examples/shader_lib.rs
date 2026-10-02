//! Summarise the IoStore shader libraries (`ShaderCodeLibrary` chunks): how
//! many shader maps each holds and how many shaders per map, plus the
//! frequency mix. Used to compare a cook of our own against the game's.
//!
//!   cargo run -p ue-iostore --example shader_lib -- <paks> [container substring]
//!
//! Layout (UE 5.5 FIoStoreShaderCodeArchiveHeader, after a u32 version):
//! ShaderMapHashes (FSHAHash[]), ShaderHashes (FSHAHash[]), ShaderGroupIoHashes
//! (FIoChunkId[]), ShaderMapEntries ({u32 offset, u32 count}[]), ShaderEntries
//! (u64 packed: frequency in the low 4 bits), ShaderGroupEntries
//! ({u32 offset, u32 count, u32 compressed, u32 uncompressed}[]), ShaderIndices (u32[]).
fn main() {
    let mut args = std::env::args().skip(1);
    let paks = args
        .next()
        .expect("usage: shader_lib <paks> [container substring]");
    let want = args.next().map(|s| s.to_lowercase());
    for c in ue_iostore::load_all(&paks).expect("load containers") {
        let name = c
            .utoc_path
            .file_name()
            .unwrap()
            .to_string_lossy()
            .to_string();
        if want
            .as_ref()
            .is_some_and(|w| !name.to_lowercase().contains(w))
        {
            continue;
        }
        for ch in c
            .chunks
            .iter()
            .filter(|ch| ch.type_name() == "ShaderCodeLibrary")
        {
            let d = match ue_iostore::read_chunk(&c, ch, None, &[]) {
                Ok(d) => d,
                Err(e) => {
                    println!("{name}: {e}");
                    continue;
                }
            };
            let mut p = 0usize;
            let u32_ = |p: &mut usize| {
                let v = u32::from_le_bytes(d[*p..*p + 4].try_into().unwrap());
                *p += 4;
                v
            };
            let version = u32_(&mut p);
            let maps = u32_(&mut p) as usize;
            p += maps * 20;
            let shaders = u32_(&mut p) as usize;
            p += shaders * 20;
            let groups_io = u32_(&mut p) as usize;
            p += groups_io * 12;
            let map_entries = u32_(&mut p) as usize;
            let mut counts = Vec::with_capacity(map_entries);
            for _ in 0..map_entries {
                let _off = u32_(&mut p);
                counts.push(u32_(&mut p));
            }
            let entries = u32_(&mut p) as usize;
            let mut freq = [0usize; 16];
            for _ in 0..entries {
                let v = u64::from_le_bytes(d[p..p + 8].try_into().unwrap());
                p += 8;
                freq[(v & 0xf) as usize] += 1;
            }
            counts.sort_unstable();
            let median = counts.get(counts.len() / 2).copied().unwrap_or(0);
            let max = counts.last().copied().unwrap_or(0);
            let min = counts.first().copied().unwrap_or(0);
            println!(
                "{name}: v{version}, {maps} map(s), {shaders} shader(s); per map min {min} median {median} max {max}; frequencies {:?}",
                &freq[..8]
            );
        }
    }
}
