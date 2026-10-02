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
//! runs only when the set of enabled maps or the game build changed since
//! the last one. Both are kept in [`RECORD`].

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
const REG_CONTAINER: &str = "pakchunk996-MJOLNIRREG_P";

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

/// Make `MJOLNIRMaps` hold exactly the enabled map packs, then rebuild the
/// registration when what it would register has changed. Returns the log of
/// a rebuild, empty when none was needed.
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
        for file in ["level.json", "registration.json"] {
            fs::copy(map.data.join(file), dir.join(file))
                .map_err(|e| format!("{} {file}: {e}", map.code))?;
        }
        fs::write(dir.join(MARKER), b"installed by the MJOLNIR launcher\n")
            .map_err(|e| e.to_string())?;
    }

    let mut codes: Vec<String> = enabled.iter().map(|m| m.code.clone()).collect();
    codes.sort();
    let wanted = Record {
        codes,
        game: game_fingerprint(paks),
    };
    let record_path = layout.maps.join(RECORD);
    let previous: Option<Record> = fs::read(&record_path)
        .ok()
        .and_then(|b| serde_json::from_slice(&b).ok());
    let container_there = paks.join(format!("{REG_CONTAINER}.utoc")).is_file();
    let up_to_date = match &previous {
        Some(p) => *p == wanted && (wanted.codes.is_empty() || container_there),
        // Never registered by this launcher, and nothing to register: leave a
        // registration somebody built by hand (`mjolnir level register`) alone.
        None => wanted.codes.is_empty(),
    };
    if up_to_date {
        return Ok(Vec::new());
    }

    let usmap = ue_asset::Usmap::parse(USMAP).map_err(|e| format!("bundled usmap: {e}"))?;
    let done = blam_pack::maps::rebuild(&layout, &[], &usmap)?;
    fs::write(
        &record_path,
        serde_json::to_vec_pretty(&wanted).map_err(|e| e.to_string())?,
    )
    .map_err(|e| format!("{}: {e}", record_path.display()))?;
    Ok(done.log)
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

        sync(&paks, &[]).expect("removing the map");
        assert!(!maps.join(&code).exists());
        assert!(
            !paks.join(format!("{REG_CONTAINER}.utoc")).exists(),
            "left as shipped"
        );

        let _ = fs::remove_dir_all(&scratch);
    }
}
