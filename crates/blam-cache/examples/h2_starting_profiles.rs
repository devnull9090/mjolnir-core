//! Print what a Halo 2 map hands a player at spawn, from its scenario:
//! - starting equipment (scnr +0x128, 0x9C each: flags, four game types,
//!   item collections 1-6 at +0x3C, 8 bytes apart): the multiplayer kit,
//!   per game type, as Halo 1's block of the same name;
//! - player starting profiles (scnr +0xF8, 0x44 each: name, starting
//!   health/shield damage, primary and secondary weapon with rounds
//!   loaded/total, frag and plasma counts).
//!
//! Each item collection is followed to its entries (itmc +0x00, 0x10 each:
//! weight at +0x00, item reference at +0x04).
//!
//! Usage: h2_starting_profiles <map>... [--raw]
use blam_cache::h2::{Cache, Struct};
use std::path::Path;

const GAME_TYPES: [&str; 15] = [
    "none", "ctf", "slayer", "oddball", "koth", "race", "headhunter", "juggernaut", "territories", "9", "10",
    "11", "all", "all but ctf", "all but ctf/race",
];

fn game_type(v: i16) -> String {
    usize::try_from(v).ok().and_then(|i| GAME_TYPES.get(i)).map(|s| s.to_string()).unwrap_or_else(|| v.to_string())
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let raw = a.iter().any(|s| s == "--raw");
    for map in a.iter().skip(1).filter(|s| !s.starts_with("--")) {
        let cache = Cache::open(Path::new(map), None).expect("open");
        let scnr = cache.scenario().expect("scnr");
        let root = scnr.root;
        let name = Path::new(map).file_stem().unwrap().to_string_lossy();
        let equipment = root.block(0x128, 0x9C);
        let profiles = root.block(0xF8, 0x44);
        println!("{name}: starting equipment {}, profiles {}", equipment.count, profiles.count);
        let reference = |s: &Struct, off: usize| s.tagref(off).map(|r| r.name().to_string());
        for (i, e) in equipment.iter().enumerate() {
            let types: Vec<String> = (0..4).map(|k| e.i16(4 + 2 * k)).filter(|&t| t != 0).map(game_type).collect();
            println!("  equipment [{i}] flags {:#x} game types [{}]", e.u32(0), types.join(", "));
            for k in 0..6 {
                let Some(r) = e.tagref(0x3C + 8 * k) else { continue };
                let items: Vec<String> = cache
                    .follow(r)
                    .map(|itmc| {
                        itmc.root
                            .block(0, 0x10)
                            .iter()
                            .map(|it| format!("{} x{}", reference(&it, 4).unwrap_or_default(), it.f32(0)))
                            .collect()
                    })
                    .unwrap_or_default();
                println!("    item collection {} = {} -> {}", k + 1, r.name(), items.join("; "));
            }
            if raw {
                let hex: Vec<String> = e.bytes(0, 0x9C).iter().map(|b| format!("{b:02x}")).collect();
                println!("    raw {}", hex.join(""));
            }
        }
        for (i, p) in profiles.iter().enumerate() {
            let text = p.bytes(0, 0x20);
            let label = String::from_utf8_lossy(&text[..text.iter().position(|&b| b == 0).unwrap_or(0x20)]).into_owned();
            println!(
                "  profile [{i}] '{label}' health dmg {:.2} shield dmg {:.2} primary {} ({}/{}) secondary {} ({}/{}) frag {} plasma {}",
                p.f32(0x20),
                p.f32(0x24),
                reference(&p, 0x28).unwrap_or_else(|| "none".into()),
                p.i16(0x30),
                p.i16(0x32),
                reference(&p, 0x34).unwrap_or_else(|| "none".into()),
                p.i16(0x3C),
                p.i16(0x3E),
                p.u8(0x40) as i8,
                p.u8(0x41) as i8,
            );
        }
    }
}
