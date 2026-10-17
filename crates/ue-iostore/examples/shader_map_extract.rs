//! Extract every shader of the shader maps a package refers to: its bytes
//! (`<package>.bin`, e.g. from `mjolnir chunk --hexdump`) are searched for
//! each library's shader map hashes, and each map found has all its shaders
//! written out (`<out>/<map>_<index>_f<frequency>.bin`, plus `.dxil` for
//! `dxc -dumpbin`). For reading a cooked asset's GPU code, such as a Niagara
//! system's compute scripts, which ship only compiled.
//!
//!   cargo run --release -p ue-iostore --example shader_map_extract -- \
//!       <paks> <package.bin> <out dir>
//!
//! Library layout: see shader_extract.rs.
use std::path::PathBuf;

fn main() {
    let mut args = std::env::args().skip(1);
    let paks = args
        .next()
        .expect("usage: shader_map_extract <paks> <package.bin> <out>");
    let package = std::fs::read(args.next().expect("package bytes")).expect("read package");
    let out = PathBuf::from(args.next().expect("out dir"));
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
        for lib in c
            .chunks
            .iter()
            .filter(|ch| ch.type_name() == "ShaderCodeLibrary")
        {
            let d = ue_iostore::read_chunk(&c, lib, None, &oodle).expect("library");
            let mut p = 0usize;
            let u32_ = |p: &mut usize| {
                let v = u32::from_le_bytes(d[*p..*p + 4].try_into().unwrap());
                *p += 4;
                v
            };
            let _version = u32_(&mut p);
            let maps = u32_(&mut p) as usize;
            let map_hashes: Vec<&[u8]> =
                (0..maps).map(|i| &d[p + i * 20..p + i * 20 + 20]).collect();
            p += maps * 20;
            let shaders = u32_(&mut p) as usize;
            p += shaders * 20;
            let groups_io = u32_(&mut p) as usize;
            let mut group_ids = Vec::with_capacity(groups_io);
            for _ in 0..groups_io {
                group_ids.push((
                    u64::from_le_bytes(d[p..p + 8].try_into().unwrap()),
                    d[p + 11],
                ));
                p += 12;
            }
            let map_entries_n = u32_(&mut p) as usize;
            let mut map_entries = Vec::with_capacity(map_entries_n);
            for _ in 0..map_entries_n {
                map_entries.push((u32_(&mut p) as usize, u32_(&mut p) as usize));
            }
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
            let indices_n = u32_(&mut p) as usize;
            let indices: Vec<usize> = (0..indices_n)
                .map(|i| {
                    u32::from_le_bytes(d[p + i * 4..p + i * 4 + 4].try_into().unwrap()) as usize
                })
                .collect();

            for (m, hash) in map_hashes.iter().enumerate() {
                if !package.windows(20).any(|w| w == *hash) {
                    continue;
                }
                let hex: String = hash.iter().map(|b| format!("{b:02x}")).collect();
                let (first, count) = map_entries[m];
                println!("{name}: shader map {hex}, {count} shader(s)");
                for &index in &indices[first..first + count] {
                    let (f, group, offset) = shader_entries[index];
                    let (_, _, uncompressed, compressed) = group_entries[group as usize];
                    let (id, kind) = group_ids[group as usize];
                    let ch = c
                        .chunks
                        .iter()
                        .find(|ch| ch.chunk_id == id && ch.chunk_type == kind)
                        .expect("group chunk");
                    let raw = ue_iostore::read_chunk(&c, ch, None, &oodle).expect("group");
                    let bytes = if compressed != uncompressed {
                        ue_iostore::oodle::decompress(
                            &raw[..compressed as usize],
                            uncompressed as usize,
                            &oodle,
                        )
                        .expect("oodle")
                    } else {
                        raw
                    };
                    let end = shader_entries
                        .iter()
                        .filter(|(_, g, o)| *g == group && *o > offset)
                        .map(|(_, _, o)| *o)
                        .min()
                        .unwrap_or(uncompressed as u64);
                    let code = &bytes[offset as usize..end as usize];
                    let stem = out.join(format!("{}_{index}_f{f}", &hex[..8]));
                    std::fs::write(stem.with_extension("bin"), code).unwrap();
                    if let Some(at) = code.windows(4).position(|w| w == b"DXBC") {
                        let size =
                            u32::from_le_bytes(code[at + 24..at + 28].try_into().unwrap()) as usize;
                        if at + size <= code.len() {
                            std::fs::write(stem.with_extension("dxil"), &code[at..at + size])
                                .unwrap();
                        }
                    }
                    println!("  shader {index}: frequency {f}, {} bytes", code.len());
                }
            }
        }
    }
}
