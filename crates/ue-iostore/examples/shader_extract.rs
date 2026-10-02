//! Extract compiled shaders from IoStore shader libraries, to disassemble and
//! compare (e.g. a cook of our own against the game's).
//!
//!   cargo run --release -p ue-iostore --example shader_extract -- \
//!       <paks> <container substring> <out dir> [frequency] [max]
//!
//! Frequency is an EShaderFrequency number (0 vertex, 3 pixel, 5 compute);
//! default 3, at most 8 shaders unless `max` says otherwise. Each shader is
//! written whole (`<container>_<index>.bin`, the engine's FShaderCode: the
//! bytecode followed by its optional data) and, when it holds a DXIL/DXBC
//! container, that container alone (`.dxil`), ready for `dxc -dumpbin`.
//!
//! Library layout (UE 5.5 FIoStoreShaderCodeArchiveHeader, after a u32
//! version): ShaderMapHashes, ShaderHashes (FSHAHash[]), ShaderGroupIoHashes
//! (FIoChunkId[], 12 bytes), ShaderMapEntries ({u32, u32}[]), ShaderEntries
//! (u64: frequency 4 bits, group index 30, offset in group 30),
//! ShaderGroupEntries ({u32 indices offset, u32 count, u32 uncompressed,
//! u32 compressed}[]), ShaderIndices (u32[]). A group is one ShaderCode chunk,
//! Oodle-compressed as a whole when its sizes differ.
use std::path::PathBuf;

fn main() {
    let mut args = std::env::args().skip(1);
    let paks = args
        .next()
        .expect("usage: shader_extract <paks> <container> <out> [freq] [max]");
    let want = args.next().expect("container substring").to_lowercase();
    let out = PathBuf::from(args.next().expect("out dir"));
    let freq: u64 = args.next().map(|s| s.parse().unwrap()).unwrap_or(3);
    let max: usize = args.next().map(|s| s.parse().unwrap()).unwrap_or(8);
    std::fs::create_dir_all(&out).unwrap();
    let oodle: Vec<PathBuf> = std::env::var("OODLE")
        .ok()
        .map(PathBuf::from)
        .into_iter()
        .collect();

    for c in ue_iostore::load_all(&paks).expect("load containers") {
        let name = c
            .utoc_path
            .file_stem()
            .unwrap()
            .to_string_lossy()
            .to_string();
        if !name.to_lowercase().contains(&want) {
            continue;
        }
        let Some(lib) = c
            .chunks
            .iter()
            .find(|ch| ch.type_name() == "ShaderCodeLibrary")
        else {
            continue;
        };
        let d = ue_iostore::read_chunk(&c, lib, None, &oodle).expect("library");
        let mut p = 0usize;
        let u32_ = |p: &mut usize| {
            let v = u32::from_le_bytes(d[*p..*p + 4].try_into().unwrap());
            *p += 4;
            v
        };
        let _version = u32_(&mut p);
        let maps = u32_(&mut p) as usize;
        p += maps * 20;
        let shaders = u32_(&mut p) as usize;
        p += shaders * 20;
        let groups_io = u32_(&mut p) as usize;
        let mut group_ids = Vec::with_capacity(groups_io);
        for _ in 0..groups_io {
            let id = u64::from_le_bytes(d[p..p + 8].try_into().unwrap());
            let kind = d[p + 11];
            group_ids.push((id, kind));
            p += 12;
        }
        let map_entries = u32_(&mut p) as usize;
        p += map_entries * 8;
        let entries = u32_(&mut p) as usize;
        let mut shader_entries = Vec::with_capacity(entries);
        for _ in 0..entries {
            let v = u64::from_le_bytes(d[p..p + 8].try_into().unwrap());
            p += 8;
            shader_entries.push((v & 0xf, (v >> 4) & 0x3fff_ffff, (v >> 34) & 0x3fff_ffff));
        }
        let groups = u32_(&mut p) as usize;
        let mut group_entries = Vec::with_capacity(groups);
        for _ in 0..groups {
            group_entries.push((u32_(&mut p), u32_(&mut p), u32_(&mut p), u32_(&mut p)));
        }

        let mut written = 0;
        let mut cache: std::collections::HashMap<u64, Vec<u8>> = Default::default();
        for (index, &(f, group, offset)) in shader_entries.iter().enumerate() {
            if f != freq || written >= max {
                continue;
            }
            let (_, _, uncompressed, compressed) = group_entries[group as usize];
            let bytes = cache.entry(group).or_insert_with(|| {
                let (id, kind) = group_ids[group as usize];
                let ch = c
                    .chunks
                    .iter()
                    .find(|ch| ch.chunk_id == id && ch.chunk_type == kind)
                    .expect("group chunk");
                let raw = ue_iostore::read_chunk(&c, ch, None, &oodle).expect("group");
                if compressed != uncompressed {
                    ue_iostore::oodle::decompress(
                        &raw[..compressed as usize],
                        uncompressed as usize,
                        &oodle,
                    )
                    .expect("oodle")
                } else {
                    raw
                }
            });
            // Size: up to the next shader of the same group, or the group's end.
            let end = shader_entries
                .iter()
                .filter(|(_, g, o)| *g == group && *o > offset)
                .map(|(_, _, o)| *o)
                .min()
                .unwrap_or(uncompressed as u64);
            let code = &bytes[offset as usize..end as usize];
            let stem = out.join(format!("{name}_{index}"));
            std::fs::write(stem.with_extension("bin"), code).unwrap();
            if let Some(at) = code.windows(4).position(|w| w == b"DXBC") {
                let size = u32::from_le_bytes(code[at + 24..at + 28].try_into().unwrap()) as usize;
                if at + size <= code.len() {
                    std::fs::write(stem.with_extension("dxil"), &code[at..at + size]).unwrap();
                }
            }
            written += 1;
        }
        println!(
            "{name}: {written} shader(s) of frequency {freq} written to {}",
            out.display()
        );
    }
}
