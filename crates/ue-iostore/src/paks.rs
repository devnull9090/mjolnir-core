//! Container names in a game's `Paks` folder, the order the engine mounts
//! them in, and local developer builds (docs/chunk_numbering.md).
//!
//! The engine orders paks by the last `_<v>_P` in the name: priority
//! `100 × (v + 1)` above the folder's base, a plain `_P` counting as `v = 0`
//! and a name without `_P` below both (FPakPlatformFile::Mount). Between equal
//! priorities the name that sorts lower wins. The number after `pakchunk`
//! names the container's shader library and plays no part in the order.
//!
//! Three kinds of MJOLNIR container share the folder:
//!
//! - hub mods, written by the launcher as `pakchunk<N>-MJOLNIRHUB-…_<v>_P`
//!   with `v` in [`HUB_SUFFIX_BASE`]..=[`HUB_SUFFIX_MAX`];
//! - developer builds, `pakchunk<N>-MJOLNIRDEV-<name>_<v>_P` with `v` in
//!   [`DEV_SUFFIX_BASE`]..=[`DEV_SUFFIX_MAX`], above every hub container, the
//!   newest install highest ([`install_dev`]);
//! - loose containers under any other name (a plain `_P` override a build
//!   script copied in, the map registration), below every hub container.
//!   [`shadowed_loose`] says which of them lose shared chunks.

use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

use crate::toc::Toc;

/// The first load-order suffix the launcher gives a hub container.
pub const HUB_SUFFIX_BASE: u32 = 1000;
/// The last one. A hub container's live update takes up to three above its
/// own suffix, so this leaves the developer band clear.
pub const HUB_SUFFIX_MAX: u32 = 999_996;
/// The first developer-build suffix: above every hub container.
pub const DEV_SUFFIX_BASE: u32 = 1_000_000;
/// The last developer-build suffix.
pub const DEV_SUFFIX_MAX: u32 = 1_999_999;
/// The first local chunk number of a hub container.
pub const HUB_NUMBER_BASE: u32 = 10_000;
/// The last one.
pub const HUB_NUMBER_MAX: u32 = 4_999_999;
/// The first chunk number of a developer build.
pub const DEV_NUMBER_BASE: u32 = 5_000_000;
/// The last one.
pub const DEV_NUMBER_MAX: u32 = 5_999_999;

// The engine keeps priority in an int32; the folder base is below 10.
const _: () = assert!(HUB_SUFFIX_MAX + 3 < DEV_SUFFIX_BASE);
const _: () = assert!(100 * (DEV_SUFFIX_MAX as u64 + 1) + 10 < i32::MAX as u64);
const _: () = assert!(HUB_NUMBER_MAX < DEV_NUMBER_BASE);

/// The marker of a hub container's name.
pub const HUB_MARKER: &str = "MJOLNIRHUB";
/// The marker of a developer build's name.
pub const DEV_MARKER: &str = "MJOLNIRDEV";

/// `pakchunk<digits>` at the start of `stem`: the number and what follows.
pub fn split_number(stem: &str) -> Option<(u32, &str)> {
    if stem.len() <= 8 || !stem.is_char_boundary(8) || !stem[..8].eq_ignore_ascii_case("pakchunk") {
        return None;
    }
    let rest = &stem[8..];
    let digits = rest.bytes().take_while(u8::is_ascii_digit).count();
    let number = rest[..digits].parse().ok()?;
    Some((number, &rest[digits..]))
}

/// The engine's patch step for a pak named `stem` (no extension): `None` when
/// the name does not end `_P`, which mounts below every `_P`; `Some(0)` for a
/// plain `_P`; `Some(v)` for `…_<v>_P` with `v` at least 1.
pub fn patch_version(stem: &str) -> Option<u32> {
    let body = stem.strip_suffix("_P")?;
    let version = body.rsplit_once('_').map(|(_, v)| v).unwrap_or("");
    match version.parse::<u32>() {
        Ok(v) if v >= 1 && version.bytes().all(|b| b.is_ascii_digit()) => Some(v),
        _ => Some(0),
    }
}

/// Whether a pak named `a` wins a chunk it shares with one named `b`.
pub fn wins_over(a: &str, b: &str) -> bool {
    match patch_version(a).cmp(&patch_version(b)) {
        std::cmp::Ordering::Equal => a.to_ascii_lowercase() < b.to_ascii_lowercase(),
        order => order.is_gt(),
    }
}

/// A developer build in Paks: `pakchunk<number>-MJOLNIRDEV-<name>_<suffix>_P`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DevContainer {
    pub stem: String,
    pub name: String,
    pub number: u32,
    pub suffix: u32,
}

/// The file name (no extension) of a developer build.
pub fn dev_stem(number: u32, name: &str, suffix: u32) -> String {
    format!("pakchunk{number}-{DEV_MARKER}-{name}_{suffix}_P")
}

/// The developer build a file stem names, if it names one.
pub fn parse_dev(stem: &str) -> Option<DevContainer> {
    let (number, rest) = split_number(stem)?;
    let rest = rest.strip_prefix('-')?;
    if rest.len() <= DEV_MARKER.len() || !rest[..DEV_MARKER.len()].eq_ignore_ascii_case(DEV_MARKER) {
        return None;
    }
    let rest = rest[DEV_MARKER.len()..].strip_prefix('-')?;
    let (name, suffix) = rest.strip_suffix("_P")?.rsplit_once('_')?;
    let suffix = suffix.parse().ok().filter(|_| suffix.bytes().all(|b| b.is_ascii_digit()))?;
    check_dev_name(name).ok()?;
    Some(DevContainer { stem: stem.to_string(), name: name.to_string(), number, suffix })
}

/// A developer build's name: letters, digits and dashes, up to 64, and never
/// the hub's marker (the launcher deletes anything carrying it).
pub fn check_dev_name(name: &str) -> Result<(), String> {
    if name.is_empty() || name.len() > 64 {
        return Err(format!("{name:?}: a name is 1 to 64 characters"));
    }
    if !name.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-') || name.starts_with('-') || name.ends_with('-') {
        return Err(format!("{name:?}: use letters, digits and dashes only"));
    }
    if name.to_ascii_uppercase().contains(HUB_MARKER) {
        return Err(format!("{name:?}: the launcher owns names carrying {HUB_MARKER}"));
    }
    Ok(())
}

/// The name a developer build of `stem` takes by default: what follows the
/// chunk number, without `_P` or `-Windows`. `pakchunk997-MJOLNIRMAP-BGL_P`
/// is `MJOLNIRMAP-BGL`. A name that says nothing about which map
/// (`pakchunk978-MJOLNIRLAND-Windows`) is refused: pass one.
pub fn default_dev_name(stem: &str) -> Result<String, String> {
    let rest = split_number(stem).map(|(_, r)| r.trim_start_matches('-')).unwrap_or(stem);
    let rest = rest.strip_suffix("_P").unwrap_or(rest);
    let name = rest.strip_suffix("-Windows").unwrap_or(rest).replace('_', "-");
    if rest.ends_with("-Windows") || !name.contains('-') {
        return Err(format!("{stem}: name the build (--name), its own name does not say which map it is for"));
    }
    check_dev_name(&name)?;
    Ok(name)
}

/// The developer builds in `paks`, by suffix, oldest first.
pub fn list_dev(paks: &Path) -> Result<Vec<DevContainer>, String> {
    let mut out = Vec::new();
    for entry in fs::read_dir(paks).map_err(|e| format!("{}: {e}", paks.display()))? {
        let name = entry.map_err(|e| e.to_string())?.file_name().to_string_lossy().into_owned();
        if let Some(dev) = name.strip_suffix(".utoc").and_then(parse_dev) {
            out.push(dev);
        }
    }
    out.sort_by_key(|d| (d.suffix, d.number));
    Ok(out)
}

const EXTS: [&str; 3] = ["ucas", "utoc", "pak"];

/// Whether the game holds `stem`'s data file open (it keeps every mounted
/// `.ucas` open, and the `.utoc` it has read).
fn held_open(paks: &Path, stem: &str) -> bool {
    let ucas = paks.join(format!("{stem}.ucas"));
    ucas.exists() && fs::OpenOptions::new().write(true).open(&ucas).is_err()
}

fn remove_triple(paks: &Path, stem: &str) -> Result<(), String> {
    for ext in EXTS {
        let path = paks.join(format!("{stem}.{ext}"));
        if path.exists() {
            fs::remove_file(&path).map_err(|e| format!("{}: {e}", path.display()))?;
        }
    }
    Ok(())
}

/// What [`install_dev`] did.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DevInstall {
    pub installed: DevContainer,
    /// The shader library's chunk number as cooked and as installed.
    pub library: Option<(u32, u32)>,
    /// Earlier builds under the same name, removed.
    pub replaced: Vec<String>,
}

/// Install the container at `source` (its `.utoc`, or the path without an
/// extension) into `paks` as the developer build `name`, above every hub
/// container and every earlier developer build. A build already installed
/// under `name` is replaced. A shader library is renamed to the build's own
/// chunk number, so it opens beside the hub copy's. Nothing in Paks changes
/// when the game holds a file this would replace, or when anything else fails
/// before the copy.
///
/// A developer build shadows the hub copy; it cannot remove it. A package
/// the hub copy has and the build does not stays in the game from the hub.
pub fn install_dev(paks: &Path, source: &Path, name: &str, project: &str) -> Result<DevInstall, String> {
    check_dev_name(name)?;
    let base: PathBuf = match source.extension().and_then(|e| e.to_str()) {
        Some("utoc") | Some("ucas") | Some("pak") => source.with_extension(""),
        _ => source.to_path_buf(),
    };
    let source_stem = base.file_name().and_then(|s| s.to_str()).ok_or("bad source path")?.to_string();
    let at = |ext: &str| PathBuf::from(format!("{}.{ext}", base.display()));
    let utoc_bytes = fs::read(at("utoc")).map_err(|e| format!("{}: {e}", at("utoc").display()))?;
    if !at("ucas").is_file() {
        return Err(format!("{} is missing", at("ucas").display()));
    }
    let mut toc = Toc::parse(&utoc_bytes).map_err(|e| format!("{source_stem}: {e}"))?;

    let existing = list_dev(paks)?;
    let (replaced, others): (Vec<_>, Vec<_>) = existing.into_iter().partition(|d| d.name.eq_ignore_ascii_case(name));
    if let Some(open) = replaced.iter().find(|d| held_open(paks, &d.stem)) {
        return Err(format!("the game has {} open; close it first", open.stem));
    }
    let suffix = match replaced.iter().chain(&others).map(|d| d.suffix).max() {
        None => DEV_SUFFIX_BASE,
        Some(top) if top >= DEV_SUFFIX_MAX => {
            return Err(format!("developer suffixes are used up to {DEV_SUFFIX_MAX}; remove the builds you no longer need"))
        }
        Some(top) => (top + 1).max(DEV_SUFFIX_BASE),
    };
    let number = (DEV_NUMBER_BASE..=DEV_NUMBER_MAX)
        .find(|n| !others.iter().any(|d| d.number == *n))
        .ok_or("developer chunk numbers are used up")?;

    let library = if crate::shader_library::has_library(&toc) {
        let (cooked, _) = split_number(&source_stem)
            .ok_or_else(|| format!("{source_stem} carries a shader library, but its name carries no chunk number to rename it from"))?;
        crate::shader_library::renumber(&mut toc, project, cooked, number)
            .map_err(|e| format!("{source_stem}: {e}"))?;
        Some((cooked, number))
    } else {
        None
    };
    let utoc = if library.is_some() { toc.write() } else { utoc_bytes };

    let stem = dev_stem(number, name, suffix);
    let pak = match fs::read(at("pak")) {
        Ok(bytes) => bytes,
        Err(_) => crate::pak::stub_for(&stem),
    };
    for old in &replaced {
        remove_triple(paks, &old.stem)?;
    }
    let to = |ext: &str| paks.join(format!("{stem}.{ext}"));
    let written = fs::copy(at("ucas"), to("ucas"))
        .map_err(|e| e.to_string())
        .and_then(|_| fs::write(to("utoc"), &utoc).map_err(|e| e.to_string()))
        .and_then(|_| fs::write(to("pak"), &pak).map_err(|e| e.to_string()));
    if let Err(error) = written {
        let _ = remove_triple(paks, &stem);
        return Err(format!("{stem}: {error}"));
    }
    Ok(DevInstall {
        installed: DevContainer { stem, name: name.to_string(), number, suffix },
        library,
        replaced: replaced.into_iter().map(|d| d.stem).collect(),
    })
}

/// Remove the developer build `name`. Returns the stems removed (none when
/// there was no such build).
pub fn remove_dev(paks: &Path, name: &str) -> Result<Vec<String>, String> {
    let builds: Vec<_> = list_dev(paks)?.into_iter().filter(|d| d.name.eq_ignore_ascii_case(name)).collect();
    if let Some(open) = builds.iter().find(|d| held_open(paks, &d.stem)) {
        return Err(format!("the game has {} open; close it first", open.stem));
    }
    for d in &builds {
        remove_triple(paks, &d.stem)?;
    }
    Ok(builds.into_iter().map(|d| d.stem).collect())
}

/// A loose MJOLNIR container that loses chunks it shares with a hub
/// container or a developer build.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Shadowed {
    pub loser: String,
    pub winner: String,
    /// Shared chunks whose bytes differ: the loser's version never loads.
    pub differing: usize,
    /// Shared chunks with the same bytes: nothing lost.
    pub identical: usize,
}

/// Every loose MJOLNIR container in `paks` (not a hub container, not a
/// developer build) that shares chunks with a hub container or developer
/// build mounted above it. The container headers (one per container) and
/// shader code (named by content) are left out; a shader library under the
/// same number counts, since only one of the two opens.
pub fn shadowed_loose(paks: &Path) -> Result<Vec<Shadowed>, String> {
    type Key = (u64, u16, u8);
    type Chunks = Vec<(Key, Vec<u8>)>;
    let mut loose = Vec::new();
    let mut managed = Vec::new();
    for entry in fs::read_dir(paks).map_err(|e| format!("{}: {e}", paks.display()))? {
        let name = entry.map_err(|e| e.to_string())?.file_name().to_string_lossy().into_owned();
        let Some(stem) = name.strip_suffix(".utoc") else { continue };
        let upper = stem.to_ascii_uppercase();
        if !upper.contains("-MJOLNIR") || split_number(stem).is_none() {
            continue;
        }
        if upper.contains(&format!("-{HUB_MARKER}-")) || upper.contains(&format!("-{DEV_MARKER}-")) {
            managed.push(stem.to_string());
        } else {
            loose.push(stem.to_string());
        }
    }
    let chunks = |stem: &str| -> Chunks {
        let Ok(toc) = Toc::read(paks.join(format!("{stem}.utoc"))) else { return Vec::new() };
        toc.chunk_ids
            .iter()
            .enumerate()
            .filter(|(_, c)| c.kind != 6 && c.kind != 9)
            .map(|(i, c)| ((c.id, c.index, c.kind), toc.meta(i).map(|m| m[..20].to_vec()).unwrap_or_default()))
            .collect()
    };
    let loose: Vec<(String, Chunks)> = loose.into_iter().map(|s| { let c = chunks(&s); (s, c) }).collect();
    let wanted: std::collections::HashSet<Key> = loose.iter().flat_map(|(_, c)| c.iter().map(|(k, _)| *k)).collect();
    let mut owners: HashMap<Key, Vec<(usize, Vec<u8>)>> = HashMap::new();
    for (i, stem) in managed.iter().enumerate() {
        for (key, meta) in chunks(stem) {
            if wanted.contains(&key) {
                owners.entry(key).or_default().push((i, meta));
            }
        }
    }
    let mut out = Vec::new();
    for (stem, keys) in &loose {
        let mut by_winner: HashMap<usize, (usize, usize)> = HashMap::new();
        for (key, meta) in keys {
            for (i, other) in owners.get(key).into_iter().flatten() {
                if wins_over(&managed[*i], stem) {
                    let counts = by_winner.entry(*i).or_default();
                    if other == meta { counts.1 += 1 } else { counts.0 += 1 }
                }
            }
        }
        for (i, (differing, identical)) in by_winner {
            out.push(Shadowed { loser: stem.clone(), winner: managed[i].clone(), differing, identical });
        }
    }
    out.sort_by(|a, b| (&a.loser, &a.winner).cmp(&(&b.loser, &b.winner)));
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::pack::{build_indexed, Entry};
    use crate::toc::ChunkId;

    fn template() -> Toc {
        Toc {
            version: 8,
            reserved0: [0; 3],
            header_size: 144,
            block_entry_size: 12,
            method_name_length: 32,
            compression_block_size: 65536,
            partition_count: 1,
            container_id: 0,
            encryption_guid: [0; 16],
            flags: crate::FLAG_INDEXED,
            reserved1: [0; 3],
            perfect_hash_seed_count: 0,
            partition_size: u64::MAX,
            chunks_without_perfect_hash: 0,
            header_tail: vec![0; 44],
            chunk_ids: Vec::new(),
            chunk_offsets: Vec::new(),
            perfect_hash: Vec::new(),
            blocks: Vec::new(),
            methods: Vec::new(),
            signature: Vec::new(),
            directory_index: Vec::new(),
            chunk_meta: Vec::new(),
            trailing: Vec::new(),
        }
    }

    fn package(id: u64) -> ChunkId {
        ChunkId { id, index: 0, pad: 0, kind: 1 }
    }

    /// A container in `dir` named `stem`: packages `(id, byte)` and, with
    /// `library`, a shader library named for that chunk number.
    fn container(dir: &Path, stem: &str, packages: &[(u64, u8)], library: Option<u32>) {
        let mut entries: Vec<Entry> =
            packages.iter().map(|(id, b)| Entry { id: package(*id), data: vec![*b; 200], meta: vec![0; 24] }).collect();
        if let Some(n) = library {
            let id = crate::shader_library::library_id("Meteorite", n, "PCD3D_SM6-PCD3D_SM6");
            entries.push(Entry { id, data: vec![3; 64], meta: vec![0; 24] });
        }
        let names: Vec<(String, usize)> = (0..entries.len()).map(|i| (format!("f{i}.uasset"), i)).collect();
        let built = build_indexed(&template(), 1, &entries, Some(("../../../Meteorite/Content/", &names)));
        fs::write(dir.join(format!("{stem}.utoc")), &built.utoc).unwrap();
        fs::write(dir.join(format!("{stem}.ucas")), &built.ucas).unwrap();
        fs::write(dir.join(format!("{stem}.pak")), crate::pak::stub_for(stem)).unwrap();
    }

    fn scratch(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("ue-iostore-paks-{tag}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(dir.join("paks")).unwrap();
        fs::create_dir_all(dir.join("build")).unwrap();
        dir
    }

    #[test]
    fn the_engine_order_reads_the_last_version() {
        assert_eq!(patch_version("pakchunk0-Windows"), None);
        assert_eq!(patch_version("pakchunk996-MJOLNIRREG_P"), Some(0));
        assert_eq!(patch_version("pakchunk902-MJOLNIRHUB-ce-blood-gulch-2_P"), Some(0));
        assert_eq!(patch_version("pakchunk10042-MJOLNIRHUB-ce-blood-gulch-0_1168_P"), Some(1168));
        assert_eq!(patch_version("pakchunk5000000-MJOLNIRDEV-MJOLNIRMAP-BGL_1000000_P"), Some(1_000_000));
        assert_eq!(patch_version("pakchunk1-x_0_P"), Some(0));
        assert_eq!(patch_version("pakchunk1-x_abc_P"), Some(0));
        // Developer builds over hub containers over loose ones; names decide ties.
        let dev = "pakchunk5000000-MJOLNIRDEV-MJOLNIRMAP-BGL_1000000_P";
        let hub = "pakchunk10042-MJOLNIRHUB-ce-blood-gulch-0_999996_P";
        assert!(wins_over(dev, hub) && !wins_over(hub, dev));
        assert!(wins_over(hub, "pakchunk981-MJOLNIRH2TEST_P"));
        assert!(wins_over("pakchunk940-a_P", "pakchunk997-a_P"));
        assert!(wins_over("pakchunk997-a_P", "pakchunk900-a-Windows"));
    }

    #[test]
    fn developer_names_are_checked_and_defaulted() {
        let dev = parse_dev("pakchunk5000003-MJOLNIRDEV-MJOLNIRMAP-BGL_1000004_P").unwrap();
        assert_eq!((dev.number, dev.name.as_str(), dev.suffix), (5_000_003, "MJOLNIRMAP-BGL", 1_000_004));
        assert_eq!(dev_stem(dev.number, &dev.name, dev.suffix), dev.stem);
        assert_eq!(parse_dev("pakchunk10042-MJOLNIRHUB-ce-blood-gulch-0_1168_P"), None);
        assert_eq!(parse_dev("pakchunk5000003-MJOLNIRDEV-x_P"), None);
        assert!(check_dev_name("MJOLNIRMAP-BGL").is_ok());
        for bad in ["", "a b", "a_b", "-a", "a-", "x-MJOLNIRHUB-y", "mjolnirhub", &"a".repeat(65)] {
            assert!(check_dev_name(bad).is_err(), "{bad:?}");
        }
        assert_eq!(default_dev_name("pakchunk997-MJOLNIRMAP-BGL_P").unwrap(), "MJOLNIRMAP-BGL");
        assert_eq!(default_dev_name("pakchunk986-MJOLNIRMACH-YOY-0C_P").unwrap(), "MJOLNIRMACH-YOY-0C");
        assert!(default_dev_name("pakchunk978-MJOLNIRLAND-Windows").is_err());
        assert!(default_dev_name("pakchunk983-Windows").is_err());
    }

    #[test]
    fn a_build_installs_above_the_last_and_renames_its_library() {
        let dir = scratch("install");
        let (paks, build) = (dir.join("paks"), dir.join("build"));
        container(&build, "pakchunk978-MJOLNIRLAND-Windows", &[(1, 1)], Some(978));
        container(&build, "pakchunk997-MJOLNIRMAP-BGL_P", &[(2, 2)], None);
        let land = install_dev(&paks, &build.join("pakchunk978-MJOLNIRLAND-Windows.utoc"), "MJOLNIRLAND-BGL", "Meteorite").unwrap();
        assert_eq!(land.installed.suffix, DEV_SUFFIX_BASE);
        assert_eq!(land.installed.number, DEV_NUMBER_BASE);
        assert_eq!(land.library, Some((978, DEV_NUMBER_BASE)));
        let toc = Toc::read(paks.join(format!("{}.utoc", land.installed.stem))).unwrap();
        let named = |n| crate::shader_library::library_id("Meteorite", n, "PCD3D_SM6-PCD3D_SM6");
        assert!(toc.find_chunk_by_hash(&named(DEV_NUMBER_BASE)).is_some());
        assert!(toc.find_chunk_by_hash(&named(978)).is_none());
        assert!(toc.find_chunk_by_hash(&package(1)).is_some());

        let map = install_dev(&paks, &build.join("pakchunk997-MJOLNIRMAP-BGL_P"), "MJOLNIRMAP-BGL", "Meteorite").unwrap();
        assert_eq!((map.installed.number, map.installed.suffix, map.library), (DEV_NUMBER_BASE + 1, DEV_SUFFIX_BASE + 1, None));
        // Again: replaces itself, keeps its number, and goes above the rest.
        let again = install_dev(&paks, &build.join("pakchunk978-MJOLNIRLAND-Windows"), "MJOLNIRLAND-BGL", "Meteorite").unwrap();
        assert_eq!(again.replaced, std::slice::from_ref(&land.installed.stem));
        assert_eq!((again.installed.number, again.installed.suffix), (DEV_NUMBER_BASE, DEV_SUFFIX_BASE + 2));
        assert!(!paks.join(format!("{}.ucas", land.installed.stem)).exists());
        let listed: Vec<String> = list_dev(&paks).unwrap().into_iter().map(|d| d.name).collect();
        assert_eq!(listed, ["MJOLNIRMAP-BGL", "MJOLNIRLAND-BGL"]);
        assert_eq!(fs::read_dir(&paks).unwrap().count(), 6);

        assert_eq!(remove_dev(&paks, "mjolnirmap-bgl").unwrap(), std::slice::from_ref(&map.installed.stem));
        assert_eq!(remove_dev(&paks, "MJOLNIRMAP-BGL").unwrap(), Vec::<String>::new());
        assert_eq!(fs::read_dir(&paks).unwrap().count(), 3);

        // A library not named for its file's number, or no number at all:
        // refused, and nothing written.
        container(&build, "pakchunk970-MJOLNIRROCK-TST_P", &[(3, 3)], Some(969));
        container(&build, "MJOLNIRLIB", &[(4, 4)], Some(1));
        assert!(install_dev(&paks, &build.join("pakchunk970-MJOLNIRROCK-TST_P"), "ROCK-TST", "Meteorite").is_err());
        assert!(install_dev(&paks, &build.join("MJOLNIRLIB"), "LIB-X", "Meteorite").is_err());
        assert!(install_dev(&paks, &build.join("pakchunk997-MJOLNIRMAP-BGL_P"), "x-MJOLNIRHUB", "Meteorite").is_err());
        assert_eq!(fs::read_dir(&paks).unwrap().count(), 3);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn loose_containers_under_hub_copies_are_reported() {
        let dir = scratch("shadow");
        let paks = dir.join("paks");
        container(&paks, "pakchunk10005-MJOLNIRHUB-runtime-2_1008_P", &[(1, 1), (2, 2), (3, 3)], Some(981));
        // The H2TEST case: a test build of the same library and package.
        container(&paks, "pakchunk981-MJOLNIRH2TEST_P", &[(1, 9), (2, 2)], Some(981));
        // A loose copy with nothing shared, and one sitting above the hub by
        // its own suffix.
        container(&paks, "pakchunk996-MJOLNIRREG_P", &[(7, 7)], None);
        container(&paks, "pakchunk985-MJOLNIRCOOK-X_1500000_P", &[(3, 4)], None);
        let found = shadowed_loose(&paks).unwrap();
        assert_eq!(
            found,
            [Shadowed {
                loser: "pakchunk981-MJOLNIRH2TEST_P".into(),
                winner: "pakchunk10005-MJOLNIRHUB-runtime-2_1008_P".into(),
                differing: 1,
                identical: 2,
            }]
        );
        let _ = fs::remove_dir_all(&dir);
    }
}
