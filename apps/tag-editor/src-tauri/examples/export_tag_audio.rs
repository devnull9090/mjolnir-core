//! Export the audio of every sound tag whose path contains a filter, as Ogg
//! Vorbis, for building voice datasets (tools/voice). Each tag resolves to its
//! Wwise media through the import walk the Sounds tab uses
//! ([`tag_editor_lib::wwise_media_for_tag`]), except that a spoken line's
//! event package lists one media file per language and this takes the
//! English(US) one (the Sounds tab plays the first, Chinese on this build).
//! Tags with no English media are listed and skipped.
//!
//! Usage: cargo run --release --no-default-features --example export_tag_audio -- <filter> <out dir>
//! e.g. `-- _cortana-sound D:\hce-voice\data\ce-evolved\cortana`. Writes
//! `<tag name>.ogg` and `tags.tsv` (tag path, media file, bytes). Game audio is
//! never committed: keep the out dir outside the repository.

use std::io::Write;
use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::{decode, install, wwise, zen};

fn main() -> Result<(), String> {
    let mut args = std::env::args().skip(1);
    let filter = args.next().ok_or("usage: export_tag_audio <filter> <out dir>")?.to_ascii_lowercase();
    let out = std::path::PathBuf::from(args.next().ok_or("usage: export_tag_audio <filter> <out dir>")?);
    let found = install::detect();
    let (paks, oodle) = match (found.paks, found.oodle) {
        (Some(p), Some(o)) => (p, o),
        _ => return Err("no installation found".to_string()),
    };
    let catalog = Catalog::open(&paks, &oodle)?;
    // Spoken lines ship once per language; the resolver returns whichever copy
    // it meets first. English(US), media id -> catalog index.
    let mut english = std::collections::HashMap::new();
    let mut i = 0;
    while let Some(s) = catalog.sound(i) {
        if s.language.as_deref() == Some("English(US)") {
            if let Some(id) = wwise::media_id_of_path(&s.short) {
                english.insert(id, i);
            }
        }
        i += 1;
    }
    eprintln!("{} English(US) media of {i} sounds", english.len());
    if english.is_empty() {
        let mut langs = std::collections::BTreeMap::new();
        for j in 0..i {
            *langs.entry(catalog.sound(j).and_then(|s| s.language.clone()).unwrap_or_default()).or_insert(0) += 1;
        }
        eprintln!("languages: {langs:?}");
    }
    std::fs::create_dir_all(&out).map_err(|e| e.to_string())?;
    let mut index = std::fs::File::create(out.join("tags.tsv")).map_err(|e| e.to_string())?;
    writeln!(index, "tag\tmedia\tbytes").map_err(|e| e.to_string())?;
    let (mut written, mut missing) = (0usize, 0usize);
    for ti in 0..catalog.tags.len() {
        let tag = &catalog.tags[ti];
        if !tag.group.starts_with("sound") || !tag.path.to_ascii_lowercase().contains(&filter) {
            continue;
        }
        let Some(media) = english_media(&catalog, ti, &english) else {
            eprintln!("no English media: {}", tag.path);
            missing += 1;
            continue;
        };
        let wem = catalog.read_sound(media, None)?;
        let ogg = match decode::to_ogg(&wem) {
            Ok(c) => c,
            Err(e) => {
                eprintln!("decode {}: {e}", tag.path);
                missing += 1;
                continue;
            }
        };
        let stem = tag.path.rsplit(['/', '\\']).next().unwrap_or(&tag.path);
        let stem = stem.split('.').next().unwrap_or(stem).trim_end_matches("-sound");
        std::fs::write(out.join(format!("{stem}.ogg")), &ogg.ogg).map_err(|e| e.to_string())?;
        let label = catalog.sound(media).map(|s| s.short.clone()).unwrap_or_default();
        writeln!(index, "{}\t{}\t{}", tag.path, label, ogg.ogg.len()).map_err(|e| e.to_string())?;
        written += 1;
    }
    println!("{written} written, {missing} without audio -> {}", out.display());
    Ok(())
}

/// The tag's English(US) media, by the same bounded import walk as
/// `wwise_media_for_tag`: every `Media/...` name a package lists is a
/// candidate; the first whose id is an English(US) file wins.
fn english_media(c: &Catalog, tag: usize, english: &std::collections::HashMap<u32, usize>) -> Option<usize> {
    let uasset = c.read_tag_uasset(tag).ok()?;
    let mut queue: std::collections::VecDeque<(String, u8)> =
        zen::imported_package_names(&uasset).into_iter().map(|p| (p, 0)).collect();
    let mut seen = std::collections::BTreeSet::new();
    let mut reads = 0;
    while let Some((package, depth)) = queue.pop_front() {
        if reads >= 24 || !seen.insert(package.clone()) {
            continue;
        }
        let Some(buf) = c.read_package(&package) else { continue };
        reads += 1;
        if let Some(names) = zen::load_name_batch(&buf, 52) {
            for name in names.iter().filter(|n| n.starts_with("Media/")) {
                if let Some(&hit) = wwise::media_id_of_path(name).and_then(|id| english.get(&id)) {
                    return Some(hit);
                }
            }
        }
        if depth + 1 < 3 {
            queue.extend(zen::imported_package_names(&buf).into_iter().map(|p| (p, depth + 1)));
        }
    }
    None
}
