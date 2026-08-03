//! Locating an installed copy of Halo Campaign Evolved and the Oodle DLL.
//!
//! The editor reads tags from the user's own installation. Nothing is bundled
//! and nothing is written back.
//!
//! Every container the game ships is Oodle-compressed, and UE 5.5 statically
//! links the codec into the game binary rather than shipping
//! `oo2core_*_win64.dll` beside it. The reader carries its own decoder for that
//! reason, so the DLL is optional — it is only worth finding because it decodes
//! about four times faster. This module looks in the places a copy already
//! exists rather than asking, and remembers what worked.

use std::collections::VecDeque;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

const GAME_DIR: &str = "Halo Campaign Evolved";
const PAKS_SUFFIX: &str = r"Meteorite\Content\Paks";

/// Overrides the search entirely. A file path or a directory holding the DLL.
const OODLE_ENV: &str = "MJOLNIR_OODLE";

/// Directories one scan may open before giving up. A scan runs on startup, so
/// it is bounded rather than exhaustive: the conventional locations are shallow
/// and breadth-first finds them long before this runs out.
const SCAN_BUDGET: u32 = 20_000;

/// Directory names never worth descending into. `Content` is the big one — a
/// UE game's asset tree is enormous and never holds a binary.
const SKIP_DIRS: &[&str] = &[
    "content",
    "saved",
    "intermediate",
    "derivedatacache",
    "movies",
    "node_modules",
    ".git",
    "windowsapps",
    "$recycle.bin",
    "system volume information",
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

/// Paths the user confirmed by opening them successfully.
#[derive(Debug, Default, Serialize, Deserialize)]
struct Settings {
    paks: Option<String>,
    oodle: Option<String>,
}

fn settings_path() -> Option<PathBuf> {
    Some(dirs::config_dir()?.join("MJOLNIR").join("tag-editor.json"))
}

fn recall() -> Settings {
    settings_path()
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

/// Record paths that worked, so the next launch does not have to search.
///
/// Best-effort: a settings file that cannot be written costs the user a second
/// browse, which is not worth failing an otherwise successful open over.
pub fn remember(paks: &str, oodle: &str) {
    let Some(path) = settings_path() else { return };
    let settings = Settings {
        paks: Some(paks.to_string()),
        // An empty path means the user is on the built-in decoder. Store it as
        // absent so a DLL installed later still gets picked up.
        oodle: Some(oodle.to_string()).filter(|s| !s.trim().is_empty()),
    };
    let Ok(json) = serde_json::to_string_pretty(&settings) else {
        return;
    };
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let _ = std::fs::write(path, json);
}

/// Fixed drives worth probing. Removable letters are skipped: `A:` and `B:`
/// can stall on hardware that is not there.
fn drive_roots() -> Vec<PathBuf> {
    ('C'..='Z')
        .map(|c| PathBuf::from(format!("{c}:\\")))
        .filter(|p| p.is_dir())
        .collect()
}

/// Undo the extended-length prefix `canonicalize` adds.
///
/// `\\?\C:\Games` is a valid path but it reads badly in the UI and some tools
/// choke on it, so it is trimmed back to the familiar shape.
fn plain(path: PathBuf) -> PathBuf {
    let text = path.to_string_lossy();
    if let Some(rest) = text.strip_prefix(r"\\?\UNC\") {
        return PathBuf::from(format!(r"\\{rest}"));
    }
    match text.strip_prefix(r"\\?\") {
        Some(rest) => PathBuf::from(rest),
        None => path,
    }
}

/// Pull the value out of a `"path"  "C:\\..."` line in `libraryfolders.vdf`.
fn vdf_path(line: &str) -> Option<PathBuf> {
    let mut fields = line.split('"').filter(|s| !s.trim().is_empty());
    if fields.next()? != "path" {
        return None;
    }
    Some(PathBuf::from(fields.next()?.replace("\\\\", "\\")))
}

/// Every `steamapps/common` on the machine.
///
/// `libraryfolders.vdf` is authoritative — it lists libraries on drives and in
/// folders no convention would guess — but it only exists once Steam has run,
/// so the conventional roots are probed too.
fn steam_libraries() -> Vec<PathBuf> {
    let mut roots: Vec<PathBuf> = vec![
        PathBuf::from(r"C:\Program Files (x86)\Steam"),
        PathBuf::from(r"C:\Program Files\Steam"),
    ];
    for drive in drive_roots() {
        roots.push(drive.join("Steam"));
        roots.push(drive.join("SteamLibrary"));
        roots.push(drive.join("Games").join("Steam"));
    }

    // Each root may name further libraries; those do not name more in turn.
    let declared: Vec<PathBuf> = roots
        .iter()
        .map(|r| r.join("steamapps").join("libraryfolders.vdf"))
        .filter_map(|vdf| std::fs::read_to_string(vdf).ok())
        .flat_map(|text| text.lines().filter_map(vdf_path).collect::<Vec<_>>())
        .collect();
    roots.extend(declared);

    let mut libraries: Vec<PathBuf> = roots
        .into_iter()
        .map(|r| r.join("steamapps").join("common"))
        .filter(|p| p.is_dir())
        .filter_map(|p| p.canonicalize().ok().map(plain))
        .collect();
    libraries.sort();
    libraries.dedup();
    libraries
}

/// Engine installs, wherever the Epic launcher put them.
fn epic_roots() -> Vec<PathBuf> {
    let mut roots = vec![
        PathBuf::from(r"C:\Program Files\Epic Games"),
        PathBuf::from(r"C:\Program Files (x86)\Epic Games"),
    ];
    for drive in drive_roots() {
        roots.push(drive.join("Epic Games"));
        roots.push(drive.join("Program Files").join("Epic Games"));
    }
    roots.retain(|p| p.is_dir());
    roots
}

fn find_paks() -> Option<PathBuf> {
    let remembered = recall().paks.map(PathBuf::from);
    if let Some(p) = remembered.filter(|p| p.is_dir()) {
        return Some(p);
    }
    steam_libraries()
        .into_iter()
        .map(|lib| lib.join(GAME_DIR).join(PAKS_SUFFIX))
        .find(|p| p.is_dir())
}

/// The `9` in `oo2core_9_win64.dll`, or `None` if this is not that file.
///
/// The version matters: an Oodle decoder reads streams written by its own
/// version and older, never newer. The game is UE 5.5, so a UE4-era `oo2core_5`
/// borrowed from some other game may refuse its blocks while a `_9` will not.
/// Everything found is ranked and the highest wins.
fn oodle_version(name: &str) -> Option<u32> {
    let name = name.to_ascii_lowercase();
    let rest = name.strip_prefix("oo2core_")?;
    let digits = rest.strip_suffix("_win64.dll")?;
    digits.parse().ok()
}

/// Breadth-first hunt for the newest `oo2core_*_win64.dll` under `roots`.
///
/// Breadth-first on purpose: the DLL sits four or five levels down in the
/// conventional layouts, so a level-by-level walk reaches it while a depth-first
/// one is still somewhere inside the first game's asset tree.
fn scan_for_oodle(roots: &[PathBuf], max_depth: u32) -> Option<PathBuf> {
    let mut queue: VecDeque<(PathBuf, u32)> = roots.iter().map(|r| (r.clone(), 0u32)).collect();
    let mut budget = SCAN_BUDGET;
    let mut best: Option<(u32, PathBuf)> = None;

    while let Some((dir, depth)) = queue.pop_front() {
        if budget == 0 {
            break;
        }
        budget -= 1;

        let Ok(entries) = std::fs::read_dir(&dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let Some(name) = path.file_name().and_then(|n| n.to_str()) else {
                continue;
            };
            let is_dir = entry.file_type().map(|t| t.is_dir()).unwrap_or(false);
            if is_dir {
                if depth + 1 < max_depth && !SKIP_DIRS.contains(&name.to_ascii_lowercase().as_str())
                {
                    queue.push_back((path, depth + 1));
                }
                continue;
            }
            if let Some(version) = oodle_version(name) {
                if best.as_ref().is_none_or(|(v, _)| version > *v) {
                    best = Some((version, path));
                }
            }
        }
    }

    best.map(|(_, p)| p)
}

/// Resolve an explicitly named DLL: either the file itself or a directory
/// holding one.
fn resolve_explicit(raw: &str) -> Option<PathBuf> {
    let path = PathBuf::from(raw.trim());
    if path.is_file() {
        return Some(path);
    }
    if path.is_dir() {
        return scan_for_oodle(&[path], 1);
    }
    None
}

fn find_oodle() -> Option<PathBuf> {
    if let Some(p) = std::env::var(OODLE_ENV)
        .ok()
        .and_then(|v| resolve_explicit(&v))
    {
        return Some(p);
    }
    if let Some(p) = recall().oodle.as_deref().and_then(resolve_explicit) {
        return Some(p);
    }

    // Beside the editor itself, so dropping the DLL next to the exe just works.
    let beside_exe: Vec<PathBuf> = std::env::current_exe()
        .ok()
        .and_then(|exe| exe.parent().map(Path::to_path_buf))
        .into_iter()
        .collect();
    if let Some(p) = scan_for_oodle(&beside_exe, 1) {
        return Some(p);
    }

    // An engine install is the likeliest source and the cheapest to search.
    if let Some(p) = scan_for_oodle(&epic_roots(), 8) {
        return Some(p);
    }

    // Then any UE4-era game: those still ship the DLL, under
    // `<game>/Engine/Binaries/ThirdParty/Oodle/Win64`.
    if let Some(p) = scan_for_oodle(&steam_libraries(), 7) {
        return Some(p);
    }

    // Finally the places a file lands when someone downloads one on purpose.
    let user_dirs: Vec<PathBuf> = [dirs::download_dir(), dirs::desktop_dir()]
        .into_iter()
        .flatten()
        .collect();
    scan_for_oodle(&user_dirs, 2)
}

/// Explain whatever is still missing, in terms of what the user has to do.
///
/// Only the Paks folder is required. A missing DLL is worth a line because it
/// costs speed, but it stops nothing.
fn note_for(paks: &Option<PathBuf>, oodle: &Option<PathBuf>) -> Option<String> {
    let mut parts = Vec::new();
    if paks.is_none() {
        parts.push(
            "Could not find Halo Campaign Evolved. Choose the Paks folder manually.".to_string(),
        );
    }
    if oodle.is_none() {
        parts.push(
            "No oo2core_*_win64.dll found, so the built-in decoder will be used. It reads \
             everything correctly and needs no setup; the DLL is simply about four times \
             faster. To use one, point at a copy — any Unreal Engine 5 install has one under \
             Engine\\Binaries\\DotNET\\AutomationTool, and most UE4-era games ship one under \
             Engine\\Binaries\\ThirdParty\\Oodle\\Win64."
                .to_string(),
        );
    }
    if parts.is_empty() {
        None
    } else {
        Some(parts.join(" "))
    }
}

/// Probe for a usable installation.
pub fn detect() -> Install {
    let paks = find_paks();
    let oodle = find_oodle();
    let note = note_for(&paks, &oodle);

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
        assert_eq!(scan_for_oodle(&[PathBuf::from(".")], 0), None);
    }

    #[test]
    fn oodle_version_reads_the_generation() {
        assert_eq!(oodle_version("oo2core_9_win64.dll"), Some(9));
        assert_eq!(oodle_version("OO2CORE_5_WIN64.DLL"), Some(5));
        // Other architectures are not loadable here and must not match.
        assert_eq!(oodle_version("oo2core_9_win32.dll"), None);
        assert_eq!(oodle_version("oo2core_9_winuwparm64.dll"), None);
        assert_eq!(oodle_version("oo2net_9_win64.dll"), None);
    }

    #[test]
    fn plain_undoes_the_extended_length_prefix() {
        assert_eq!(
            plain(PathBuf::from(r"\\?\C:\Games")),
            PathBuf::from(r"C:\Games")
        );
        assert_eq!(
            plain(PathBuf::from(r"\\?\UNC\nas\share")),
            PathBuf::from(r"\\nas\share")
        );
        // An ordinary path is left exactly as it came in.
        assert_eq!(
            plain(PathBuf::from(r"D:\Steam")),
            PathBuf::from(r"D:\Steam")
        );
    }

    #[test]
    fn vdf_path_unescapes_backslashes() {
        let line = "\t\t\"path\"\t\t\"D:\\\\SteamLibrary\"";
        assert_eq!(vdf_path(line), Some(PathBuf::from(r"D:\SteamLibrary")));
        assert_eq!(vdf_path("\t\"1\"\t\t\"228980\""), None);
        assert_eq!(vdf_path("{"), None);
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
