//! Classify every sound-group tag by how (whether) its audio resolves:
//! package-walk media, bank-graph media (loose or embedded), events with no
//! media, or no Wwise link at all. Decides what a playable sound tag view can
//! promise.
//!
//! Usage: cargo run --no-default-features --example probe_sound_survey

use std::collections::{BTreeMap, BTreeSet, HashMap, VecDeque};
use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::{bnk, install, wwise, zen};

fn main() -> Result<(), String> {
    let found = install::detect();
    let (paks, oodle) = match (found.paks, found.oodle) {
        (Some(p), Some(o)) => (p, o),
        _ => return Err("no installation found".to_string()),
    };
    let catalog = Catalog::open(&paks, &oodle)?;

    // Bank short name -> parsed event map, parsed once.
    let mut banks: HashMap<String, HashMap<u32, Vec<u32>>> = HashMap::new();
    // Package name -> (media ids, bank refs, imports), read once.
    let mut pkg_cache: HashMap<String, (Vec<u32>, Vec<String>, Vec<String>)> = HashMap::new();

    let mut classes: BTreeMap<&str, Vec<usize>> = BTreeMap::new();
    let mut media_counts: BTreeMap<usize, usize> = BTreeMap::new(); // per-tag media count -> tags

    let sound_tags: Vec<usize> = (0..catalog.tags.len())
        .filter(|&i| catalog.tags[i].group.starts_with("sound"))
        .collect();
    eprintln!("{} sound-group tags", sound_tags.len());

    for (done, &ti) in sound_tags.iter().enumerate() {
        if done % 500 == 0 {
            eprintln!("  {done}...");
        }
        let Ok(uasset) = catalog.read_tag_uasset(ti) else {
            classes.entry("uasset unreadable").or_default().push(ti);
            continue;
        };
        let mut queue: VecDeque<(String, u8)> = VecDeque::new();
        for p in zen::imported_package_names(&uasset) {
            queue.push_back((p, 0));
        }
        if queue.is_empty() {
            classes.entry("no unreal imports").or_default().push(ti);
            continue;
        }
        let mut seen = BTreeSet::new();
        let mut walk_media: BTreeSet<u32> = BTreeSet::new();
        let mut bank_refs: BTreeSet<String> = BTreeSet::new();
        let mut stems: BTreeSet<String> = BTreeSet::new();
        let mut reads = 0usize;
        while let Some((package, depth)) = queue.pop_front() {
            if reads >= 24 || !seen.insert(package.clone()) {
                continue;
            }
            let (media, bnks, imports) = pkg_cache
                .entry(package.clone())
                .or_insert_with(|| match catalog.read_package(&package) {
                    Some(buf) => {
                        let names = zen::load_name_batch(&buf, 52).unwrap_or_default();
                        let media = names
                            .iter()
                            .filter(|n| n.starts_with("Media/"))
                            .filter_map(|n| wwise::media_id_of_path(n))
                            .collect();
                        let bnks = names
                            .iter()
                            .filter(|n| n.ends_with(".bnk"))
                            .cloned()
                            .collect();
                        (media, bnks, zen::imported_package_names(&buf))
                    }
                    None => (Vec::new(), Vec::new(), Vec::new()),
                })
                .clone();
            reads += 1;
            if let Some(stem) = package.rsplit('/').next() {
                if stem.starts_with("Play_") {
                    stems.insert(stem.to_string());
                }
            }
            walk_media.extend(media);
            bank_refs.extend(bnks);
            if depth + 1 < 3 {
                for p in imports {
                    queue.push_back((p, depth + 1));
                }
            }
        }

        // Bank route: event stems hashed, looked up in referenced banks only.
        let mut bank_media: BTreeSet<u32> = BTreeSet::new();
        if !stems.is_empty() {
            let wanted: BTreeSet<u32> = stems.iter().map(|s| bnk::event_id(s)).collect();
            for b in &bank_refs {
                let events = match banks.get(b) {
                    Some(e) => e,
                    None => {
                        let parsed = (0..catalog.sounds.len())
                            .find(|&i| catalog.sounds[i].short.ends_with(b.as_str()))
                            .and_then(|i| catalog.read_sound(i, None).ok())
                            .map(|buf| bnk::parse(&buf).events.into_iter().collect())
                            .unwrap_or_default();
                        banks.entry(b.clone()).or_insert(parsed)
                    }
                };
                for (ev, media) in events {
                    if wanted.contains(ev) {
                        bank_media.extend(media.iter().copied());
                    }
                }
            }
        }

        let all: BTreeSet<u32> = walk_media.union(&bank_media).copied().collect();
        let loose = all
            .iter()
            .filter(|&&m| catalog.sound_by_media_id(m).is_some())
            .count();
        let class = if all.is_empty() && stems.is_empty() {
            "unreal imports but no events"
        } else if all.is_empty() {
            "events but no media found"
        } else if loose == all.len() {
            "all media loose (.wem in pak)"
        } else if loose == 0 {
            "all media embedded in banks"
        } else {
            "mixed loose/embedded"
        };
        classes.entry(class).or_default().push(ti);
        if !all.is_empty() {
            *media_counts.entry(all.len()).or_default() += 1;
        }
    }

    println!("\n=== classes ===");
    for (class, tags) in &classes {
        println!("{:>5}  {class}", tags.len());
        for &t in tags.iter().take(3) {
            println!("         e.g. {}", catalog.tags[t].short);
        }
    }
    println!("\n=== media per resolving tag ===");
    for (n, count) in &media_counts {
        println!("{count:>5} tags with {n} media");
    }
    Ok(())
}
