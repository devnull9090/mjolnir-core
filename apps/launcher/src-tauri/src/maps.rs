//! Installed map packs, and the registration rebuilt from all of them
//! (docs/map_distribution.md, "Installing").
//!
//! A map pack's containers mount like any content mod's (`hub::materialize`).
//! Two more things make it start: its `map/` data has to sit in
//! `<ue4ss>/MJOLNIRMaps/<CODE>/`, where the level loader and the lobby read
//! it, and the one registration container in `Paks` has to list it, because
//! the simulation builds its map list at boot from a cooked table. That
//! container is a modified copy of the player's own game files, so it is
//! built here, from those files, never downloaded: `blam_pack::maps::rebuild`,
//! the same code as `mjolnir level register`.
//!
//! The rebuild reads the shipped containers and takes a few seconds, so it
//! runs only when the set of enabled maps, a map's registration or the game
//! build changed since the last one. A map updated in place can also change
//! what the menu lists about it (its game types) with the same registration:
//! then only the menu's list is written again. All four are kept in
//! [`RECORD`].

use std::fs;
use std::path::{Path, PathBuf};

use blam_pack::maps::Layout;
use serde::{Deserialize, Serialize};

/// Written into every map folder this launcher creates. Folders without it
/// (a pack someone unzipped by hand) are never removed.
const MARKER: &str = ".mjolnirhub";

/// What the last rebuild registered, in `MJOLNIRMaps`.
const RECORD: &str = ".mjolnirhub-registered.json";

/// The registration container `blam_pack` writes in `Paks`.
pub(crate) const REG_CONTAINER: &str = "pakchunk996-MJOLNIRREG_P";

/// The property layout the registration edit needs. The CLI bundles the same
/// file (`crates/blam-cli/src/mesh.rs`).
static USMAP: &[u8] = include_bytes!("../../../../defs/ue/Meteorite-2607-CU3.usmap");

/// A map's codename: three characters, upper case or digits. Every path this
/// module builds from a code is checked against this first.
pub fn valid_code(code: &str) -> bool {
    code.len() == 3
        && code
            .bytes()
            .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit())
}

/// One map pack the active profile has enabled: its code, and the folder in
/// the hub cache holding its `level.json` and `registration.json`.
pub struct Enabled {
    pub code: String,
    pub data: PathBuf,
}

#[derive(Serialize, Deserialize, PartialEq, Default)]
struct Record {
    codes: Vec<String>,
    game: String,
    /// Every enabled map's `registration.json`: what the container is built
    /// from. Absent in a record written before 0.24.3, which never equals a
    /// real one, so the first launch after the update rebuilds once.
    #[serde(default)]
    registrations: String,
    /// Every enabled map's `level.json`, by size and time: what the menu's
    /// list reads its game types from.
    #[serde(default)]
    levels: String,
}

impl Record {
    /// The container the last rebuild wrote still lists what is wanted now.
    fn registers(&self, wanted: &Record) -> bool {
        self.codes == wanted.codes
            && self.game == wanted.game
            && self.registrations == wanted.registrations
    }
}

/// A fingerprint of the enabled maps' registrations (the bytes: they are a
/// few hundred each) and one of their level files (size and time: they run
/// to megabytes, and this is taken on every launch).
fn data_fingerprints(maps: &Path, codes: &[String]) -> (String, String) {
    let mut registrations = Vec::new();
    let mut levels = Vec::new();
    for code in codes {
        let dir = maps.join(code);
        registrations.extend_from_slice(code.as_bytes());
        registrations.push(0);
        registrations.extend(fs::read(dir.join("registration.json")).unwrap_or_default());
        registrations.push(0);
        let (len, modified) = fs::metadata(dir.join("level.json"))
            .map(|m| {
                let modified = m
                    .modified()
                    .ok()
                    .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                    .map(|d| d.as_nanos())
                    .unwrap_or(0);
                (m.len(), modified)
            })
            .unwrap_or((0, 0));
        levels.extend_from_slice(format!("{code}:{len}:{modified};").as_bytes());
    }
    (
        crate::hub::sha256_hex(&registrations),
        crate::hub::sha256_hex(&levels),
    )
}

/// UE4SS's folder, when it is installed. Without it there is no loader to
/// read map data, so nothing here runs.
fn ue4ss_dir(paks: &Path) -> Option<PathBuf> {
    let layout = Layout::for_paks(paks);
    let ue4ss = layout.maps.parent()?.to_path_buf();
    ue4ss.is_dir().then_some(ue4ss)
}

/// A fingerprint of the shipped game: every shipped container's name, size
/// and modification time. A game update changes it, and the registration
/// has to be rebuilt from the new build's tables.
fn game_fingerprint(paks: &Path) -> String {
    let mut parts: Vec<String> = fs::read_dir(paks)
        .map(|rd| {
            rd.filter_map(|e| e.ok())
                .filter_map(|e| {
                    let name = e.file_name().to_string_lossy().into_owned();
                    if !name.ends_with(".utoc") || name.contains("MJOLNIR") {
                        return None;
                    }
                    let meta = e.metadata().ok()?;
                    let modified = meta
                        .modified()
                        .ok()
                        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                        .map(|d| d.as_secs())
                        .unwrap_or(0);
                    Some(format!("{name}:{}:{modified}", meta.len()))
                })
                .collect()
        })
        .unwrap_or_default();
    parts.sort();
    crate::hub::sha256_hex(parts.join("\n").as_bytes())
}

/// Every file of a map's cached `map/` folder into its `MJOLNIRMaps` folder
/// (`level.json`, `registration.json`, and a remastered map's `foliage.bin`
/// and `decals/`). A file already there at the same size and no older is
/// left alone: this runs on every launch, and `foliage.bin` runs to ~10 MB.
/// A file the folder holds that the release has not (a previous version's)
/// is removed, except the launcher's marker.
fn copy_map_data(src: &Path, dst: &Path) -> std::io::Result<()> {
    let mut wanted = std::collections::BTreeSet::new();
    let mut stack = vec![src.to_path_buf()];
    while let Some(dir) = stack.pop() {
        for entry in fs::read_dir(&dir)?.flatten() {
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
                continue;
            }
            let rel = path.strip_prefix(src).map_err(std::io::Error::other)?.to_path_buf();
            let target = dst.join(&rel);
            let from = fs::metadata(&path)?;
            let fresh = fs::metadata(&target).ok().is_some_and(|to| {
                to.len() == from.len()
                    && matches!((to.modified(), from.modified()), (Ok(t), Ok(f)) if t >= f)
            });
            if !fresh {
                if let Some(parent) = target.parent() {
                    fs::create_dir_all(parent)?;
                }
                fs::copy(&path, &target)?;
            }
            wanted.insert(rel);
        }
    }
    let mut stack = vec![dst.to_path_buf()];
    while let Some(dir) = stack.pop() {
        for entry in fs::read_dir(&dir)?.flatten() {
            let path = entry.path();
            if path.is_dir() {
                stack.push(path);
                continue;
            }
            let rel = path.strip_prefix(dst).map_err(std::io::Error::other)?.to_path_buf();
            if rel.as_os_str() != MARKER && !wanted.contains(&rel) {
                fs::remove_file(&path)?;
            }
        }
    }
    Ok(())
}

/// Make `MJOLNIRMaps` hold exactly the enabled map packs, then rebuild the
/// registration when what it would register has changed, or write only the
/// menu's list again when a map updated in place changed its level file.
/// Returns the log of a rebuild, empty when none was needed.
pub fn sync(paks: &Path, enabled: &[Enabled]) -> Result<Vec<String>, String> {
    let Some(_) = ue4ss_dir(paks) else {
        return Ok(Vec::new());
    };
    let layout = Layout::for_paks(paks);
    fs::create_dir_all(&layout.maps).map_err(|e| format!("{}: {e}", layout.maps.display()))?;

    // Remove what this launcher put there and no longer wants.
    if let Ok(rd) = fs::read_dir(&layout.maps) {
        for entry in rd.flatten() {
            let name = entry.file_name().to_string_lossy().into_owned();
            if !valid_code(&name) || enabled.iter().any(|m| m.code == name) {
                continue;
            }
            let dir = layout.maps.join(&name);
            if dir.join(MARKER).is_file() {
                fs::remove_dir_all(&dir).map_err(|e| format!("{}: {e}", dir.display()))?;
            }
        }
    }

    for map in enabled {
        if !valid_code(&map.code) {
            return Err(format!("{:?} is not a map code", map.code));
        }
        let dir = layout.maps.join(&map.code);
        fs::create_dir_all(&dir).map_err(|e| format!("{}: {e}", dir.display()))?;
        copy_map_data(&map.data, &dir).map_err(|e| format!("{}: {e}", map.code))?;
        fs::write(dir.join(MARKER), b"installed by the MJOLNIR launcher\n")
            .map_err(|e| e.to_string())?;
    }

    let mut codes: Vec<String> = enabled.iter().map(|m| m.code.clone()).collect();
    codes.sort();
    let (registrations, levels) = data_fingerprints(&layout.maps, &codes);
    let wanted = Record {
        codes,
        game: game_fingerprint(paks),
        registrations,
        levels,
    };
    let record_path = layout.maps.join(RECORD);
    let write_record = |record: &Record| -> Result<(), String> {
        fs::write(
            &record_path,
            serde_json::to_vec_pretty(record).map_err(|e| e.to_string())?,
        )
        .map_err(|e| format!("{}: {e}", record_path.display()))
    };
    let previous: Option<Record> = fs::read(&record_path)
        .ok()
        .and_then(|b| serde_json::from_slice(&b).ok());
    let container_there = paks.join(format!("{REG_CONTAINER}.utoc")).is_file();
    let up_to_date = match &previous {
        Some(p) => p.registers(&wanted) && (wanted.codes.is_empty() || container_there),
        // Never registered by this launcher, and nothing to register: leave a
        // registration somebody built by hand (`mjolnir level register`) alone.
        None => wanted.codes.is_empty(),
    };
    if up_to_date {
        // The registration stands. An update to a map already installed can
        // still have changed its game types, which the menu reads from the
        // list, not from the container.
        if previous.is_some_and(|p| p.levels != wanted.levels) {
            blam_pack::maps::write_menu_list(&layout)?;
            write_record(&wanted)?;
        }
        return Ok(Vec::new());
    }

    let usmap = ue_asset::Usmap::parse(USMAP).map_err(|e| format!("bundled usmap: {e}"))?;
    let done = blam_pack::maps::rebuild(&layout, &[], &usmap)?;
    write_record(&wanted)?;
    Ok(done.log)
}

/// One map for a game that is running (`hub::install_live`): its data in
/// `MJOLNIRMaps` and the menu list, but not the registration container,
/// which the game holds open; the game registers the map in memory, and the
/// next [`sync`] sees a code its record lacks and rebuilds the container.
pub fn add_live(paks: &Path, map: &Enabled) -> Result<(), String> {
    if !valid_code(&map.code) {
        return Err(format!("{:?} is not a map code", map.code));
    }
    if ue4ss_dir(paks).is_none() {
        return Err("UE4SS is not installed, so no loader can start the map".into());
    }
    let layout = Layout::for_paks(paks);
    let dir = layout.maps.join(&map.code);
    fs::create_dir_all(&dir).map_err(|e| format!("{}: {e}", dir.display()))?;
    copy_map_data(&map.data, &dir).map_err(|e| format!("{}: {e}", map.code))?;
    fs::write(dir.join(MARKER), b"installed by the MJOLNIR launcher\n").map_err(|e| e.to_string())?;
    blam_pack::maps::write_menu_list(&layout).map(|_| ())
}

/// Before UE4SS is removed: take the registration this launcher built with
/// it, so the game is left as shipped. A registration built by hand stays.
pub fn forget(paks: &Path) {
    let layout = Layout::for_paks(paks);
    if !layout.maps.join(RECORD).is_file() {
        return;
    }
    for ext in ["utoc", "ucas", "pak"] {
        let _ = fs::remove_file(paks.join(format!("{REG_CONTAINER}.{ext}")));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codes_are_three_upper_case_characters() {
        assert!(valid_code("BGL"));
        assert!(valid_code("D40"));
        assert!(!valid_code("bgl"));
        assert!(!valid_code("BG"));
        assert!(!valid_code("BGLX"));
        assert!(!valid_code(".."));
        assert!(!valid_code("B/L"));
    }

    #[test]
    fn a_map_folder_mirrors_its_release() {
        let root = std::env::temp_dir().join(format!("mjolnir-mapdata-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        let (src, dst) = (root.join("cache"), root.join("BGL"));
        fs::create_dir_all(src.join("decals")).unwrap();
        fs::create_dir_all(&dst).unwrap();
        fs::write(src.join("level.json"), b"{}").unwrap();
        fs::write(src.join("foliage.bin"), b"MJF3").unwrap();
        fs::write(src.join("decals").join("a.png"), b"png").unwrap();
        fs::create_dir_all(src.join("flux_state")).unwrap();
        for file in ["state.json", "height.exr", "velocity.exr"] {
            fs::write(src.join("flux_state").join(file), file.as_bytes()).unwrap();
        }
        // A previous version's file goes; the marker stays.
        fs::write(dst.join("old.bin"), b"x").unwrap();
        fs::write(dst.join(MARKER), b"m").unwrap();

        copy_map_data(&src, &dst).unwrap();
        assert_eq!(fs::read(dst.join("foliage.bin")).unwrap(), b"MJF3");
        assert_eq!(fs::read(dst.join("decals").join("a.png")).unwrap(), b"png");
        for file in ["state.json", "height.exr", "velocity.exr"] {
            assert_eq!(
                fs::read(dst.join("flux_state").join(file)).unwrap(),
                file.as_bytes()
            );
        }
        assert!(!dst.join("old.bin").exists());
        assert!(dst.join(MARKER).exists());

        // A changed file is copied again.
        fs::write(src.join("foliage.bin"), b"MJF3 v2").unwrap();
        copy_map_data(&src, &dst).unwrap();
        assert_eq!(fs::read(dst.join("foliage.bin")).unwrap(), b"MJF3 v2");
        let _ = fs::remove_dir_all(&root);
    }

    /// A map updated in place with new game types: the registration stands
    /// (same codes, same game, same `registration.json`), so the container is
    /// left alone, but the menu's list is written again from the new level.
    #[test]
    fn an_updated_level_reaches_the_menu_list_without_a_rebuild() {
        let root = std::env::temp_dir().join(format!("mjolnir-maplist-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        let paks = root.join("Meteorite/Content/Paks");
        let ue4ss = root.join("Meteorite/Binaries/Win64/ue4ss");
        fs::create_dir_all(&paks).unwrap();
        fs::create_dir_all(ue4ss.join("Mods")).unwrap();
        let maps = ue4ss.join(blam_pack::maps::MAPS_DIR);
        let list = maps.join(blam_pack::maps::MENU_LIST);
        let container = paks.join(format!("{REG_CONTAINER}.utoc"));

        let data = root.join("cache").join("map");
        fs::create_dir_all(&data).unwrap();
        fs::write(
            data.join("registration.json"),
            br#"{"code":"BGL","from":"B40","title":"Blood Gulch","description":"d","world":"/Game/Levels/Halo1/Solo/BGL/BGL.BGL"}"#,
        )
        .unwrap();
        fs::write(data.join("level.json"), br#"{"modes":["slayer","ctf"]}"#).unwrap();
        let enabled = [Enabled {
            code: "BGL".into(),
            data: data.clone(),
        }];

        // The state a rebuild leaves, without the game's tables to run one:
        // the map's folder, a container, the list and the record.
        let dir = maps.join("BGL");
        fs::create_dir_all(&dir).unwrap();
        copy_map_data(&data, &dir).unwrap();
        fs::write(&container, b"built by the last rebuild").unwrap();
        blam_pack::maps::write_menu_list(&Layout::for_paks(&paks)).unwrap();
        let codes = vec!["BGL".to_string()];
        let (registrations, levels) = data_fingerprints(&maps, &codes);
        let record = Record {
            codes,
            game: game_fingerprint(&paks),
            registrations,
            levels,
        };
        fs::write(maps.join(RECORD), serde_json::to_vec(&record).unwrap()).unwrap();
        assert!(!fs::read_to_string(&list).unwrap().contains("koth"));

        // Nothing changed: nothing is written.
        assert!(sync(&paks, &enabled).unwrap().is_empty());
        assert!(!fs::read_to_string(&list).unwrap().contains("koth"));

        // The pack's next release adds game types.
        fs::write(
            data.join("level.json"),
            br#"{"modes":["slayer","ctf","koth","oddball","race"]}"#,
        )
        .unwrap();
        assert!(sync(&paks, &enabled).unwrap().is_empty(), "no rebuild");
        let listed: serde_json::Value = serde_json::from_slice(&fs::read(&list).unwrap()).unwrap();
        assert_eq!(listed[0]["code"], "BGL");
        assert_eq!(
            listed[0]["modes"],
            serde_json::json!(["slayer", "ctf", "koth", "oddball", "race"])
        );
        assert_eq!(fs::read(&container).unwrap(), b"built by the last rebuild");
        let after: Record = serde_json::from_slice(&fs::read(maps.join(RECORD)).unwrap()).unwrap();
        assert!(after.registers(&record) && after.levels != record.levels);

        // A record from before 0.24.3 has neither fingerprint, and never
        // passes for a current one: the next launch rebuilds.
        let old: Record = serde_json::from_str(r#"{"codes":["BGL"],"game":"g"}"#).unwrap();
        assert!(!old.registers(&Record {
            codes: vec!["BGL".into()],
            game: "g".into(),
            registrations: after.registrations.clone(),
            levels: after.levels.clone(),
        }));
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn the_bundled_usmap_parses() {
        ue_asset::Usmap::parse(USMAP).expect("bundled usmap must parse");
    }

    /// The whole registration loop on the real game's tables, in a scratch
    /// tree whose `Paks` hardlinks the shipped containers (nothing is copied,
    /// and the real install is never written): register a map, see a second
    /// sync skip the rebuild, then remove it and see the game left as shipped.
    ///
    /// MJOLNIR_TEST_PAKS=".../Meteorite/Content/Paks" \
    /// MJOLNIR_TEST_MAP="C:/haloce/ce_conversions/v1/BGL_b0" MJOLNIR_TEST_CODE=BGL \
    ///   cargo test registers_a_map -- --ignored --nocapture
    #[test]
    #[ignore = "needs the game's Paks and a converted map (see doc comment)"]
    fn registers_a_map_against_the_shipped_tables() {
        let shipped = PathBuf::from(std::env::var("MJOLNIR_TEST_PAKS").expect("MJOLNIR_TEST_PAKS"));
        let conversion =
            PathBuf::from(std::env::var("MJOLNIR_TEST_MAP").expect("MJOLNIR_TEST_MAP"));
        let code = std::env::var("MJOLNIR_TEST_CODE").expect("MJOLNIR_TEST_CODE");

        let scratch = std::env::temp_dir().join("mjolnir-launcher-maps");
        let _ = fs::remove_dir_all(&scratch);
        let paks = scratch.join("Meteorite/Content/Paks");
        fs::create_dir_all(&paks).unwrap();
        fs::create_dir_all(scratch.join("Meteorite/Binaries/Win64/ue4ss/Mods")).unwrap();
        for e in fs::read_dir(&shipped).unwrap().flatten() {
            let name = e.file_name().to_string_lossy().into_owned();
            if !name.contains("MJOLNIR") && e.path().is_file() {
                fs::hard_link(e.path(), paks.join(&name)).expect("hardlink a shipped container");
            }
        }

        let data = scratch.join("cache").join(&code);
        fs::create_dir_all(&data).unwrap();
        fs::copy(
            conversion.join(format!("{code}.registration.json")),
            data.join("registration.json"),
        )
        .unwrap();
        let level = fs::read_dir(&conversion)
            .unwrap()
            .flatten()
            .map(|e| e.path())
            .find(|p| p.to_string_lossy().ends_with(".level.json"))
            .expect("a level file");
        fs::copy(level, data.join("level.json")).unwrap();
        let enabled = [Enabled {
            code: code.clone(),
            data,
        }];

        let started = std::time::Instant::now();
        let log = sync(&paks, &enabled).expect("first sync");
        println!("rebuild took {:?}", started.elapsed());
        for line in &log {
            println!("  {line}");
        }
        assert!(!log.is_empty(), "the first sync rebuilds");
        assert!(paks.join(format!("{REG_CONTAINER}.utoc")).is_file());
        assert!(paks.join(format!("{REG_CONTAINER}.pak")).is_file());
        let maps = scratch
            .join("Meteorite/Binaries/Win64/ue4ss")
            .join(blam_pack::maps::MAPS_DIR);
        assert!(maps.join(&code).join(MARKER).is_file());
        let list = fs::read_to_string(maps.join(blam_pack::maps::MENU_LIST)).unwrap();
        assert!(list.contains(&code), "the menu list names the map");

        assert!(
            sync(&paks, &enabled).expect("second sync").is_empty(),
            "nothing changed, no rebuild"
        );

        // The map's next release changes its game types and nothing else.
        let level_path = enabled[0].data.join("level.json");
        let mut level: serde_json::Value =
            serde_json::from_slice(&fs::read(&level_path).unwrap()).unwrap();
        level["modes"] = serde_json::json!(["slayer", "mjolnir_test_mode"]);
        fs::write(&level_path, serde_json::to_vec(&level).unwrap()).unwrap();
        let container = paks.join(format!("{REG_CONTAINER}.utoc"));
        let built = fs::metadata(&container).unwrap().modified().unwrap();
        assert!(
            sync(&paks, &enabled).expect("third sync").is_empty(),
            "a level change alone rebuilds nothing"
        );
        assert_eq!(fs::metadata(&container).unwrap().modified().unwrap(), built);
        let list = fs::read_to_string(maps.join(blam_pack::maps::MENU_LIST)).unwrap();
        assert!(list.contains("mjolnir_test_mode"), "the menu list has the new game type");

        sync(&paks, &[]).expect("removing the map");
        assert!(!maps.join(&code).exists());
        assert!(
            !paks.join(format!("{REG_CONTAINER}.utoc")).exists(),
            "left as shipped"
        );

        let _ = fs::remove_dir_all(&scratch);
    }
}
