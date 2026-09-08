//! For one sound tag, walk the import graph like the preview does but collect
//! EVERY media file reached, with the event names and authored sources the
//! name index knows. To judge whether Blam permutations can be paired with
//! Wwise media.
//!
//! Usage: cargo run --example probe_sound_media -- <path-substring>

use std::collections::{BTreeSet, VecDeque};
use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::{bnk, install, wwise, zen};

fn main() -> Result<(), String> {
    let query = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "sniper_rifle/sniper_ammo".to_string());

    let found = install::detect();
    let (paks, oodle) = match (found.paks, found.oodle) {
        (Some(p), Some(o)) => (p, o),
        _ => return Err("no installation found".to_string()),
    };
    let catalog = Catalog::open(&paks, &oodle)?;

    let index = catalog
        .tags
        .iter()
        .position(|t| t.group.starts_with("sound") && t.short.contains(&query))
        .ok_or("no sound tag matched")?;
    let entry = &catalog.tags[index];
    eprintln!("tag #{index}: {} ({})", entry.short, entry.group);

    // Same walk as wwise_media_for_tag, but exhaustive and chatty.
    const MAX_DEPTH: u8 = 3;
    const MAX_READS: usize = 64;
    let uasset = catalog.read_tag_uasset(index)?;
    let mut queue: VecDeque<(String, u8)> = VecDeque::new();
    for p in zen::imported_package_names(&uasset) {
        queue.push_back((p, 0));
    }
    let mut seen = BTreeSet::new();
    let mut media: Vec<(u32, String)> = Vec::new(); // (id, package it was named in)
    let mut reads = 0usize;
    while let Some((package, depth)) = queue.pop_front() {
        if reads >= MAX_READS || !seen.insert(package.clone()) {
            continue;
        }
        let Some(buf) = catalog.read_package(&package) else {
            println!("  [unreadable] {package}");
            continue;
        };
        reads += 1;
        println!("{}{package}", "  ".repeat(depth as usize + 1));
        if let Some(names) = zen::load_name_batch(&buf, 52) {
            for name in names.iter().filter(|n| n.ends_with(".bnk")) {
                println!("{}  [bank ref] {name}", "  ".repeat(depth as usize + 2));
            }
            for name in &names {
                if let Some(id) = name
                    .starts_with("Media/")
                    .then(|| wwise::media_id_of_path(name))
                    .flatten()
                {
                    if !media.iter().any(|(m, _)| *m == id) {
                        media.push((id, package.clone()));
                    }
                }
            }
        }
        if depth + 1 < MAX_DEPTH {
            for p in zen::imported_package_names(&buf) {
                queue.push_back((p, depth + 1));
            }
        }
    }

    // The package walk names events; the bank graph knows their media even
    // when the package name map lists none. Hash each event stem and look it
    // up in every bank.
    let stems: Vec<String> = seen
        .iter()
        .filter_map(|p| p.rsplit('/').next())
        .filter(|s| s.starts_with("Play_") || s.starts_with("Stop_"))
        .map(str::to_string)
        .collect();
    println!("\n=== event stems from the walk ===");
    for s in &stems {
        println!("  {s}  (id {})", bnk::event_id(s));
    }
    let wanted: BTreeSet<u32> = stems.iter().map(|s| bnk::event_id(s)).collect();
    let mut from_banks: Vec<(u32, u32, String)> = Vec::new(); // (event, media, bank)
    let mut banks = 0usize;
    for i in 0..catalog.sounds.len() {
        let s = &catalog.sounds[i];
        if !s.short.ends_with(".bnk") {
            continue;
        }
        let Ok(buf) = catalog.read_sound(i, None) else {
            continue;
        };
        banks += 1;
        for (event, media_ids) in bnk::parse(&buf).events {
            if wanted.contains(&event) {
                for m in media_ids {
                    from_banks.push((event, m, s.short.clone()));
                }
            }
        }
    }
    println!("\n=== bank hits ({banks} banks scanned) ===");
    for (event, m, bank) in &from_banks {
        let sound = catalog.sound_by_media_id(*m);
        println!("  event {event} -> media {m} (in {bank}) -> catalog sound {sound:?}");
    }

    println!("\n=== {} media file(s) reached by package walk ===", media.len());
    let names = catalog.names(); // seconds: full name-index build
    for (id, via) in &media {
        let sound = catalog.sound_by_media_id(*id);
        println!("media {id}  (via {via})");
        println!("  catalog sound index: {sound:?}");
        for e in names.events_for(*id) {
            println!("  event: {}", e.name);
            for s in &e.sources {
                println!("    src: {s}");
            }
        }
    }
    // Are the bank-referenced media embedded in the bank itself? A bank with
    // a DIDX section carries `(media id, offset, size)` triples; DATA holds
    // the bytes.
    let mut bank_files: BTreeSet<String> = from_banks.iter().map(|(_, _, b)| b.clone()).collect();
    println!("\n=== DIDX check ===");
    for bank_short in std::mem::take(&mut bank_files) {
        let i = (0..catalog.sounds.len())
            .find(|&i| catalog.sounds[i].short == bank_short)
            .unwrap();
        let Ok(buf) = catalog.read_sound(i, None) else {
            continue;
        };
        let mut at = 0;
        while at + 8 <= buf.len() {
            let id = &buf[at..at + 4];
            let size = u32::from_le_bytes(buf[at + 4..at + 8].try_into().unwrap()) as usize;
            if size == 0 || at + 8 + size > buf.len() {
                break;
            }
            if id == b"DIDX" {
                let n = size / 12;
                println!("  {bank_short}: DIDX with {n} media entries");
                for e in 0..n {
                    let o = at + 8 + e * 12;
                    let mid = u32::from_le_bytes(buf[o..o + 4].try_into().unwrap());
                    let sz = u32::from_le_bytes(buf[o + 8..o + 12].try_into().unwrap());
                    let ours = from_banks.iter().any(|(_, m, _)| *m == mid);
                    println!("    media {mid} ({sz} bytes){}", if ours { "  <-- ours" } else { "" });
                }
            }
            at += 8 + size;
        }
    }
    Ok(())
}
