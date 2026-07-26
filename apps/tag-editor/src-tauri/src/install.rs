//! Locating an installed copy of Halo Campaign Evolved and the Oodle DLL.
//!
//! The editor reads tags from the user's own installation. Nothing is bundled
//! and nothing is written back.

use std::path::{Path, PathBuf};

use serde::Serialize;

/// Steam library roots worth probing before falling back to a scan.
const STEAM_ROOTS: &[&str] = &[
    r"C:\Program Files (x86)\Steam\steamapps\common",
    r"C:\Program Files\Steam\steamapps\common",
];

const GAME_DIR: &str = "Halo Campaign Evolved";
const PAKS_SUFFIX: &str = r"Meteorite\Content\Paks";

/// Unreal ships Oodle inside the engine's automation tooling. UE 5.5 and newer
/// statically link it, so the game itself carries no redistributable copy.
const UE_ROOTS: &[&str] = &[
    r"C:\Program Files\Epic Games",
    r"C:\Program Files (x86)\Epic Games",
];

#[derive(Debug, Clone, Serialize)]
pub struct Install {
    /// Path to `Meteorite/Content/Paks`, if found.
    pub paks: Option<String>,
    /// Path to an `oo2core_*_win64.dll`, if found.
    pub oodle: Option<String>,
    /// Human-readable explanation when something is missing.
    pub note: Option<String>,
}

fn find_paks() -> Option<PathBuf> {
    for root in STEAM_ROOTS {
        let candidate = Path::new(root).join(GAME_DIR).join(PAKS_SUFFIX);
        if candidate.is_dir() {
            return Some(candidate);
        }
    }
    None
}

/// Recursively look for `oo2core_*_win64.dll` under `dir`, bounded by `depth`.
fn find_oodle_in(dir: &Path, depth: u32) -> Option<PathBuf> {
    if depth == 0 {
        return None;
    }
    let entries = std::fs::read_dir(dir).ok()?;
    let mut dirs = Vec::new();
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            dirs.push(path);
            continue;
        }
        let name = path.file_name()?.to_str()?.to_ascii_lowercase();
        if name.starts_with("oo2core") && name.ends_with("win64.dll") {
            return Some(path);
        }
    }
    dirs.into_iter().find_map(|d| find_oodle_in(&d, depth - 1))
}

fn find_oodle() -> Option<PathBuf> {
    UE_ROOTS
        .iter()
        .map(Path::new)
        .filter(|p| p.is_dir())
        .find_map(|p| find_oodle_in(p, 8))
}

/// Probe for a usable installation.
pub fn detect() -> Install {
    let paks = find_paks();
    let oodle = find_oodle();

    let note = match (&paks, &oodle) {
        (None, _) => Some(
            "Could not find Halo Campaign Evolved. Choose the Paks folder manually."
                .to_string(),
        ),
        (_, None) => Some(
            "Could not find oo2core_*_win64.dll. Any copy from an Unreal Engine install works; \
             the game statically links Oodle and ships no separate DLL."
                .to_string(),
        ),
        _ => None,
    };

    Install {
        paks: paks.map(|p| p.display().to_string()),
        oodle: oodle.map(|p| p.display().to_string()),
        note,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn oodle_scan_stops_at_depth_zero() {
        assert_eq!(find_oodle_in(Path::new("."), 0), None);
    }

    #[test]
    fn detect_reports_a_note_when_something_is_missing() {
        // On a machine without the game installed, detect must explain itself
        // rather than returning a silently empty result.
        let found = detect();
        if found.paks.is_none() || found.oodle.is_none() {
            assert!(found.note.is_some());
        }
    }
}
