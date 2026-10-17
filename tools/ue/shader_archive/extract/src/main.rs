//! Raw chunk extraction for the shader-archive investigation.
//!
//! Python does the parsing (`../shaderlib.py`); this binary only does what
//! needs the Rust IoStore reader and its built-in Oodle decoder:
//!
//!   list   <utoc>                         every chunk: key, type, length, path
//!   chunk  <utoc> <path-substr|idx:N> <out>  write one chunk's bytes
//!   libs   <utoc> <outdir>                write every ShaderCodeLibrary chunk
//!   groups <utoc> <listfile> <outdir>     write shader groups, decompressed
//!
//! A chunk "key" is the first ten bytes of its FIoChunkId as hex (u64 id
//! little-endian, u16 index big-endian); the reader drops the pad byte, and
//! a shader group's chunk id is the first 11 bytes of its group hash, so ten
//! bytes identify it.
//!
//! The `groups` list file has one line per group: `<key> <uncompressed> <compressed>`.
//! Groups whose sizes are equal are stored raw.

use std::collections::HashMap;
use std::path::PathBuf;

use ue_iostore::{load_container, oodle, read_chunk, ChunkEntry, Container};

fn key(c: &ChunkEntry) -> String {
    let mut b = Vec::with_capacity(10);
    b.extend_from_slice(&c.chunk_id.to_le_bytes());
    b.extend_from_slice(&c.chunk_index.to_be_bytes());
    b.iter().map(|x| format!("{x:02x}")).collect()
}

fn paths_by_index(c: &Container) -> HashMap<usize, String> {
    c.files.iter().map(|(p, i)| (*i, c.full_path(p))).collect()
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("usage: list|chunk|libs|groups <utoc> ...");
        std::process::exit(2);
    }
    let roots: Vec<PathBuf> = Vec::new();
    if args[1] == "hashname" {
        // hashname <name>... : FHashedName = CityHash64WithSeed(upper ascii, len, 0)
        for n in &args[2..] {
            let up = n.to_ascii_uppercase();
            println!("{:016x}	{}", city_hash64_with_seed(up.as_bytes(), 0), n);
        }
        return;
    }
    let c = load_container(&args[2]).expect("load utoc");
    let names = paths_by_index(&c);
    match args[1].as_str() {
        "list" => {
            for ch in &c.chunks {
                println!(
                    "{}\t{}\t{}\t{}\t{}",
                    ch.index,
                    key(ch),
                    ch.type_name(),
                    ch.length,
                    names.get(&ch.index).map(String::as_str).unwrap_or("")
                );
            }
        }
        "chunk" => {
            let sel = &args[3];
            let ch = if let Some(n) = sel.strip_prefix("idx:") {
                c.chunks[n.parse::<usize>().unwrap()]
            } else {
                let hits: Vec<_> = c
                    .chunks
                    .iter()
                    .filter(|ch| names.get(&ch.index).map(|p| p.contains(sel.as_str())).unwrap_or(false))
                    .collect();
                if hits.len() != 1 {
                    for h in &hits {
                        eprintln!("match: {}", names[&h.index]);
                    }
                    eprintln!("{} matches for {sel}", hits.len());
                    std::process::exit(1);
                }
                *hits[0]
            };
            let data = read_chunk(&c, &ch, None, &roots).expect("read chunk");
            std::fs::write(&args[4], &data).unwrap();
            eprintln!("wrote {} bytes ({})", data.len(), names.get(&ch.index).map(String::as_str).unwrap_or("?"));
        }
        "libs" => {
            let out = PathBuf::from(&args[3]);
            std::fs::create_dir_all(&out).unwrap();
            for ch in c.chunks.iter().filter(|ch| ch.chunk_type == 8) {
                let data = read_chunk(&c, ch, None, &roots).expect("read lib");
                let f = out.join(format!("{}.lib", key(ch)));
                std::fs::write(&f, &data).unwrap();
                println!(
                    "{}\t{}\t{}",
                    f.display(),
                    data.len(),
                    names.get(&ch.index).map(String::as_str).unwrap_or("")
                );
            }
        }
        "groups" => {
            let list = std::fs::read_to_string(&args[3]).unwrap();
            let out = PathBuf::from(&args[4]);
            std::fs::create_dir_all(&out).unwrap();
            let by_key: HashMap<String, ChunkEntry> = c
                .chunks
                .iter()
                .filter(|ch| ch.chunk_type == 9)
                .map(|ch| (key(ch), *ch))
                .collect();
            let (mut ok, mut missing) = (0, 0);
            for line in list.lines() {
                let f: Vec<&str> = line.split_whitespace().collect();
                if f.len() < 3 {
                    continue;
                }
                let (k, usz, csz) = (f[0], f[1].parse::<usize>().unwrap(), f[2].parse::<usize>().unwrap());
                let dst = out.join(format!("{k}.bin"));
                if dst.exists() {
                    ok += 1;
                    continue;
                }
                let Some(ch) = by_key.get(k) else {
                    missing += 1;
                    eprintln!("missing group {k}");
                    continue;
                };
                let raw = read_chunk(&c, ch, None, &roots).expect("read group");
                let data = if usz != csz {
                    match oodle::decompress(&raw, usz, &roots) {
                        Ok(d) => d,
                        Err(e) => {
                            eprintln!("decompress {k}: {e}");
                            continue;
                        }
                    }
                } else {
                    raw
                };
                if raw_len_mismatch(csz, ch.length as usize) {
                    eprintln!("note {k}: chunk length {} vs header compressed {}", ch.length, csz);
                }
                std::fs::write(&dst, &data).unwrap();
                ok += 1;
            }
            eprintln!("groups written {ok}, missing {missing}");
        }
        "find" => {
            // find <utoc> <hex>[,<hex>...] : search ExportBundleData chunks for byte patterns
            let pats: Vec<(String, Vec<u8>)> = args[3]
                .split(',')
                .map(|h| (h.to_string(), (0..h.len() / 2).map(|i| u8::from_str_radix(&h[2 * i..2 * i + 2], 16).unwrap()).collect()))
                .collect();
            for ch in c.chunks.iter().filter(|ch| ch.chunk_type == 1) {
                let Ok(data) = read_chunk(&c, ch, None, &roots) else { continue };
                for (h, p) in &pats {
                    if let Some(pos) = data.windows(p.len()).position(|w| w == p.as_slice()) {
                        println!("{}	{}	{}	{}", h, ch.index, pos, names.get(&ch.index).map(String::as_str).unwrap_or(""));
                    }
                }
            }
        }
        other => {
            eprintln!("unknown command {other}");
            std::process::exit(2);
        }
    }
}

fn raw_len_mismatch(a: usize, b: usize) -> bool {
    a != b
}

// CityHash64WithSeed(s, seed) = CityHash64WithSeeds(s, k2, seed) = HashLen16(CityHash64(s) - k2, seed)
fn city_hash64_with_seed(s: &[u8], seed: u64) -> u64 {
    const K2: u64 = 0x9ae1_6a3b_2f90_404f;
    const KMUL: u64 = 0x9ddf_ea08_eb38_2d69;
    let u = ue_iostore::city::city_hash64(s).wrapping_sub(K2);
    let v = seed;
    let mut a = (u ^ v).wrapping_mul(KMUL);
    a ^= a >> 47;
    let mut b = (v ^ a).wrapping_mul(KMUL);
    b ^= b >> 47;
    b.wrapping_mul(KMUL)
}
