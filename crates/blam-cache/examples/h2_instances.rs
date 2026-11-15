//! Dump a Halo 2 map's instanced geometry: each instance's name, position,
//! definition, and the definition's collision surface count (census aid).
use blam_cache::h2::{collision, Cache};
use std::path::Path;

fn main() {
    let map = std::env::args().nth(1).expect("map");
    let cache = Cache::open(Path::new(&map), None).expect("open");
    let scnr = cache.scenario().expect("scnr");
    let first = scnr.root.block(0x210, 0x44).get(0).unwrap();
    let sbsp = first.tagref(0x10).and_then(|r| cache.follow(r)).unwrap();
    let defs = sbsp.root.block(0x138, 0xC8);
    let counts: Vec<usize> = defs.iter().map(|d| collision::read(d.at(0x70)).surfaces.len()).collect();
    for (i, d) in defs.iter().enumerate() {
        let words: Vec<String> = (0..0xC8 / 4).map(|k| format!("{:08x}", d.u32(k * 4))).collect();
        println!("def {i} surfaces {} words {}", counts[i], words.join(" "));
    }
    for inst in sbsp.root.block(0x140, 0x58).iter() {
        let di = inst.i16(0x34);
        let p = inst.vec3(0x28);
        println!(
            "inst {} def {} surfaces {} scale {} pos {:?} f {:?} l {:?} u {:?} sphere {:?}",
            inst.sid(0x50), di, counts.get(di.max(0) as usize).copied().unwrap_or(0), inst.f32(0), p,
            inst.vec3(0x04), inst.vec3(0x10), inst.vec3(0x1C),
            defs.get(di.max(0) as usize).map(|d| [d.f32(0x60), d.f32(0x64), d.f32(0x68), d.f32(0x6C)])
        );
    }
}
