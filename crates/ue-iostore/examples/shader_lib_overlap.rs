//! For each shader library in a Paks folder: how many of its shader maps no
//! other library there carries.
//!
//!   cargo run -p ue-iostore --example shader_lib_overlap -- <paks>
use std::collections::HashMap;

fn main() {
    let paks = std::env::args().nth(1).expect("usage: shader_lib_overlap <paks>");
    let mut libs: Vec<(String, Vec<[u8; 20]>)> = Vec::new();
    for c in ue_iostore::load_all(&paks).expect("load containers") {
        let name = c.utoc_path.file_stem().unwrap().to_string_lossy().to_string();
        for ch in c.chunks.iter().filter(|ch| ch.type_name() == "ShaderCodeLibrary") {
            let Ok(d) = ue_iostore::read_chunk(&c, ch, None, &[]) else { continue };
            // u32 version, then ShaderMapHashes: i32 count + FSHAHash[count].
            let n = i32::from_le_bytes(d[4..8].try_into().unwrap()) as usize;
            let maps = (0..n).map(|i| d[8 + 20 * i..28 + 20 * i].try_into().unwrap()).collect();
            libs.push((name.clone(), maps));
        }
    }
    let mut owners: HashMap<[u8; 20], usize> = HashMap::new();
    for (_, maps) in &libs {
        for m in maps {
            *owners.entry(*m).or_default() += 1;
        }
    }
    // Each shader map: which libraries carry it.
    if std::env::args().nth(2).as_deref() == Some("--maps") {
        let mut by_map: std::collections::BTreeMap<String, Vec<&str>> = Default::default();
        for (name, maps) in &libs {
            for m in maps {
                let hex: String = m[..6].iter().map(|b| format!("{b:02x}")).collect();
                by_map.entry(hex).or_default().push(name);
            }
        }
        for (hex, names) in by_map.iter().filter(|(_, n)| n.len() > 1) {
            println!("{hex}  x{}", names.len());
            for n in names {
                println!("    {n}");
            }
        }
        return;
    }
    for (name, maps) in &libs {
        let own = maps.iter().filter(|m| owners[*m] == 1).count();
        println!("{:4} maps, {:4} only here  {name}", maps.len(), own);
    }
}
