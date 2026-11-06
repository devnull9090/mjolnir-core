//! Does any shipped Wwise bank hold an External Source sound? The engine's
//! `AudioLoadMods` command feeds a `.wem` to an event through one, so it can
//! only play mod audio if such a sound exists.
//!
//! Usage: cargo run --no-default-features --example probe_external_sources

use std::collections::HashMap;
use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::install;

/// Wwise's External Source plugin: company 0, plugin 200, type source (2).
const EXTERNAL_SOURCE: u32 = (200 << 16) | 2;

fn u32at(b: &[u8], at: usize) -> Option<u32> {
    b.get(at..at + 4).map(|s| u32::from_le_bytes(s.try_into().unwrap()))
}

fn main() -> Result<(), String> {
    let found = install::detect();
    let (paks, oodle) = match (found.paks, found.oodle) {
        (Some(p), Some(o)) => (p, o),
        _ => return Err("no installation found".to_string()),
    };
    let catalog = Catalog::open(&paks, &oodle)?;
    let mut banks = 0;
    let mut plugins: HashMap<u32, usize> = HashMap::new();
    for i in 0..catalog.sounds.len() {
        let s = &catalog.sounds[i];
        if !s.short.ends_with(".bnk") {
            continue;
        }
        if s.language.as_deref().is_some_and(|l| l != "English(US)") {
            continue;
        }
        let Ok(buf) = catalog.read_sound(i, None) else { continue };
        banks += 1;
        let mut at = 0;
        while at + 8 <= buf.len() {
            let size = u32at(&buf, at + 4).unwrap() as usize;
            if at + 8 + size > buf.len() {
                break;
            }
            if &buf[at..at + 4] == b"HIRC" {
                let h = &buf[at + 8..at + 8 + size];
                let count = u32at(h, 0).unwrap_or(0);
                let mut p = 4;
                // Sound id -> parent, action target -> action, event -> actions.
                let mut ext_sounds = Vec::new();
                let mut actions: HashMap<u32, u32> = HashMap::new();
                let mut events: Vec<(u32, Vec<u32>)> = Vec::new();
                for _ in 0..count {
                    let Some(kind) = h.get(p).copied() else { break };
                    let Some(len) = u32at(h, p + 1) else { break };
                    let body = &h[p + 5..(p + 5 + len as usize).min(h.len())];
                    p += 5 + len as usize;
                    let id = u32at(body, 0).unwrap_or(0);
                    match kind {
                        2 => {
                            let plugin = u32at(body, 4).unwrap_or(0);
                            *plugins.entry(plugin).or_default() += 1;
                            if plugin == EXTERNAL_SOURCE {
                                ext_sounds.push((id, u32at(body, 9).unwrap_or(0)));
                            }
                        }
                        3 => {
                            if let Some(t) = u32at(body, 6) {
                                actions.insert(id, t);
                            }
                        }
                        4 => {
                            let n = body.get(4).copied().unwrap_or(0) as usize;
                            events.push((id, (0..n).filter_map(|k| u32at(body, 5 + k * 4)).collect()));
                        }
                        _ => {}
                    }
                }
                for (sid, media) in ext_sounds {
                    let direct: Vec<String> = events
                        .iter()
                        .filter(|(_, acts)| acts.iter().any(|a| actions.get(a) == Some(&sid)))
                        .map(|(e, _)| format!("{e}"))
                        .collect();
                    println!(
                        "{}: external source sound {sid} (cookie/media {media}); events targeting it directly: {:?}",
                        s.short, direct
                    );
                }
            }
            at += 8 + size;
        }
    }
    let mut v: Vec<_> = plugins.into_iter().collect();
    v.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
    println!("{banks} banks; sound source plugins: {:?}", v.iter().map(|(p, n)| format!("{p:#010x}x{n}")).collect::<Vec<_>>());
    Ok(())
}
