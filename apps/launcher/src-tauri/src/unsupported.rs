//! Mods MJOLNIR did not install, and moving them out of the game's way.
//!
//! Playtesters often have other people's pak mods in `Meteorite/Content/Paks`
//! (or UE4SS mods in `ue4ss/Mods`). They change packages the fireteam has to
//! agree on, so a game with them can desync or fail to start for everyone.
//! This finds them, and on the player's say-so moves them into a folder the
//! game never reads, for one session, then moves them back.
//!
//! What counts as known, in Paks (by file name, case-insensitively):
//!
//!   the game's own   `pakchunk<N>[optional]-Windows|WinGDK.pak/utoc/ucas/sig`
//!                    and `global.utoc/ucas`, in Paks itself
//!   MJOLNIR's        `pakchunk9NN-MJOLNIR…`: hub containers
//!                    (`pakchunk9NN-MJOLNIRHUB-<slug>-<j>_P`) and the ones
//!                    MJOLNIR's own tools place (MJOLNIRREG, MJOLNIRMENU, …)
//!
//! Anything else with a container extension, anywhere under Paks (the engine
//! mounts subfolders such as `~mods` and `LogicMods` too), is unsupported.
//! The game's own list is a name rule rather than a file list because no
//! store puts one in the install; every pak either store ships follows it.
//!
//! In `ue4ss/Mods`, a folder UE4SS would start (`mods.txt` says 1, or it has
//! `enabled.txt`) is unsupported unless it is MJOLNIR's (`MJOLNIR…`, a code
//! mod this launcher installed), part of the runtime bundle, or one of the
//! mods UE4SS itself ships.
//!
//! Moving aside is a rename into `<install>/MJOLNIR-set-aside/<unix time>/`,
//! on the same volume as the game, so it is instant and cannot half-copy a
//! multi-gigabyte container. Every move is written to `set_aside.json` in the
//! launcher's config folder before the next one starts, and appended to
//! `set_aside.log`. Nothing here deletes a file: a move back that would land
//! on a file of the same name (the player put the mod back by hand) leaves
//! the set-aside copy where it is and says so.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

/// The folder beside `Meteorite` that holds set-aside mods.
pub const SET_ASIDE_DIR: &str = "MJOLNIR-set-aside";

/// Mods UE4SS's own release carries. Harmless to a multiplayer game, and a
/// player who installed UE4SS by hand has them switched on.
const STOCK_UE4SS_MODS: &[&str] = &[
    "ActorDumperMod",
    "BPML_GenericFunctions",
    "BPModLoaderMod",
    "CheatManagerEnablerMod",
    "ConsoleCommandsMod",
    "ConsoleEnablerMod",
    "jsbLuaProfilerMod",
    "Keybinds",
    "LineTraceMod",
    "shared",
    "SplitScreenMod",
];

const CONTAINER_EXTS: &[&str] = &["pak", "utoc", "ucas", "sig"];

/// One unsupported mod: a pak container (its files grouped by name) or a
/// UE4SS mod folder.
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct UnsupportedMod {
    /// `"pak"` or `"ue4ss"`.
    pub kind: String,
    /// The container's name without extension, or the mod folder's name.
    pub name: String,
    /// Paths relative to the install root, `/`-separated.
    pub files: Vec<String>,
    pub bytes: u64,
}

/// One file or folder moved aside.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Moved {
    pub from: PathBuf,
    pub to: PathBuf,
    pub kind: String,
    pub at: u64,
}

#[derive(Debug, Default, Serialize, Deserialize)]
struct Ledger {
    entries: Vec<Moved>,
}

#[derive(Debug, Default, Serialize)]
pub struct SetAsideResult {
    pub moved: usize,
    /// What could not be moved, and why (the game holding it open).
    pub failed: Vec<String>,
}

#[derive(Debug, Default, Serialize)]
pub struct RestoreResult {
    pub restored: usize,
    /// Left in the set-aside folder: something of the same name is back in
    /// its place. The path of the copy kept, for the player to sort out.
    pub kept: Vec<String>,
}

/// Where the ledger and its log live: the launcher's config folder, or a
/// scratch folder under test so a test run never touches a real ledger.
fn state_dir() -> PathBuf {
    #[cfg(test)]
    return std::env::temp_dir().join("mjolnir-unsupported-state");
    #[cfg(not(test))]
    crate::hub::config_dir()
}

fn ledger_path() -> PathBuf {
    state_dir().join("set_aside.json")
}

fn log_path() -> PathBuf {
    state_dir().join("set_aside.log")
}

fn load_ledger() -> Ledger {
    fs::read_to_string(ledger_path())
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

fn save_ledger(ledger: &Ledger) -> Result<(), String> {
    fs::create_dir_all(state_dir()).map_err(|e| e.to_string())?;
    let tmp = ledger_path().with_extension("json.tmp");
    fs::write(&tmp, serde_json::to_string_pretty(ledger).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())?;
    fs::rename(&tmp, ledger_path()).map_err(|e| e.to_string())
}

fn log(line: &str) {
    let _ = fs::create_dir_all(state_dir());
    if let Ok(mut f) = fs::OpenOptions::new().create(true).append(true).open(log_path()) {
        let _ = writeln!(f, "{} {line}", now());
    }
    eprintln!("set aside: {line}");
}

fn now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

// ─── Classification ─────────────────────────────────────────────────────

fn split_ext(name: &str) -> Option<(&str, String)> {
    let (stem, ext) = name.rsplit_once('.')?;
    let ext = ext.to_ascii_lowercase();
    CONTAINER_EXTS.contains(&ext.as_str()).then_some((stem, ext))
}

/// `pakchunk<digits>` at the start of `stem`, and what follows it.
fn after_chunk_number(stem: &str) -> Option<(&str, &str)> {
    let lower_ok = stem.len() > 8 && stem[..8].eq_ignore_ascii_case("pakchunk");
    if !lower_ok {
        return None;
    }
    let rest = &stem[8..];
    let digits = rest.bytes().take_while(|b| b.is_ascii_digit()).count();
    (digits > 0).then(|| rest.split_at(digits))
}

/// A container the game itself ships. Only in Paks itself, never a subfolder.
fn is_game_container(stem: &str, ext: &str) -> bool {
    if stem.eq_ignore_ascii_case("global") {
        return ext == "utoc" || ext == "ucas";
    }
    let Some((_, rest)) = after_chunk_number(stem) else {
        return false;
    };
    let rest = rest.to_ascii_lowercase();
    let rest = rest.strip_prefix("optional").unwrap_or(&rest);
    rest == "-windows" || rest == "-wingdk"
}

/// A container MJOLNIR put there: `pakchunk9NN-MJOLNIR…`.
fn is_mjolnir_container(stem: &str) -> bool {
    let Some((digits, rest)) = after_chunk_number(stem) else {
        return false;
    };
    digits.len() == 3
        && digits.starts_with('9')
        && rest.len() >= 8
        && rest[..8].eq_ignore_ascii_case("-MJOLNIR")
}

/// Whether a container file is unsupported. `rel` is its path below Paks,
/// `/`-separated.
pub fn pak_file_unsupported(rel: &str) -> bool {
    let (dir, name) = match rel.rsplit_once('/') {
        Some((d, n)) => (Some(d), n),
        None => (None, rel),
    };
    let Some((stem, ext)) = split_ext(name) else {
        return false;
    };
    if is_mjolnir_container(stem) {
        return false;
    }
    !(dir.is_none() && is_game_container(stem, &ext))
}

/// What a UE4SS mod folder needs to be left alone: `known` holds the runtime
/// bundle's folders and the code mods this launcher installed.
pub fn ue4ss_mod_unsupported(name: &str, enabled: bool, known: &BTreeSet<String>) -> bool {
    enabled
        && !name.starts_with("MJOLNIR")
        && !known.contains(name)
        && !STOCK_UE4SS_MODS.iter().any(|m| m.eq_ignore_ascii_case(name))
}

/// Every file below `dir`, as paths relative to it, `/`-separated.
fn walk(dir: &Path, rel: &str, out: &mut Vec<(String, u64)>) {
    let Ok(rd) = fs::read_dir(dir) else { return };
    for entry in rd.flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        let path = if rel.is_empty() { name.clone() } else { format!("{rel}/{name}") };
        match entry.file_type() {
            Ok(t) if t.is_dir() => walk(&entry.path(), &path, out),
            Ok(t) if t.is_file() => {
                out.push((path, entry.metadata().map(|m| m.len()).unwrap_or(0)))
            }
            _ => {}
        }
    }
}

/// The unsupported containers under `paks`, grouped by directory and name.
fn scan_paks(paks: &Path, paks_rel: &str) -> Vec<UnsupportedMod> {
    let mut files = Vec::new();
    walk(paks, "", &mut files);
    let mut groups: BTreeMap<String, UnsupportedMod> = BTreeMap::new();
    for (rel, size) in files {
        if !pak_file_unsupported(&rel) {
            continue;
        }
        let key = rel.rsplit_once('.').map(|(s, _)| s.to_string()).unwrap_or_else(|| rel.clone());
        let name = key.rsplit('/').next().unwrap_or(&key).to_string();
        let group = groups.entry(key.to_ascii_lowercase()).or_insert_with(|| UnsupportedMod {
            kind: "pak".into(),
            name,
            files: Vec::new(),
            bytes: 0,
        });
        group.files.push(format!("{paks_rel}/{rel}"));
        group.bytes += size;
    }
    groups.into_values().collect()
}

/// `name : 1` lines of `mods.txt`.
fn enabled_in_mods_txt(mods: &Path) -> BTreeSet<String> {
    fs::read_to_string(mods.join("mods.txt"))
        .unwrap_or_default()
        .lines()
        .filter(|l| !l.trim_start().starts_with(';'))
        .filter_map(|l| l.split_once(':'))
        .filter(|(_, v)| v.trim() == "1")
        .map(|(n, _)| n.trim().to_string())
        .collect()
}

/// The folders under `ue4ss/Mods` the runtime bundle puts there, and the code
/// mods this launcher installed.
fn known_ue4ss_mods() -> BTreeSet<String> {
    let mut known: BTreeSet<String> = crate::hub::installed_code_mod_ids().into_iter().collect();
    if let Some(manifest) = crate::load_cached_manifest() {
        for f in manifest.files {
            let mut parts = f.path.split(['/', '\\']);
            if let (Some("ue4ss"), Some("Mods"), Some(dir), Some(_)) =
                (parts.next(), parts.next(), parts.next(), parts.next())
            {
                known.insert(dir.to_string());
            }
        }
    }
    known
}

fn scan_ue4ss(mods: &Path, mods_rel: &str, known: &BTreeSet<String>) -> Vec<UnsupportedMod> {
    let listed = enabled_in_mods_txt(mods);
    let Ok(rd) = fs::read_dir(mods) else { return Vec::new() };
    let mut out: Vec<UnsupportedMod> = rd
        .flatten()
        .filter(|e| e.file_type().is_ok_and(|t| t.is_dir()))
        .filter_map(|e| e.file_name().into_string().ok())
        .filter(|name| {
            let enabled = listed.contains(name) || mods.join(name).join("enabled.txt").is_file();
            ue4ss_mod_unsupported(name, enabled, known)
        })
        .map(|name| {
            let mut files = Vec::new();
            walk(&mods.join(&name), "", &mut files);
            UnsupportedMod {
                kind: "ue4ss".into(),
                files: vec![format!("{mods_rel}/{name}")],
                bytes: files.iter().map(|(_, s)| s).sum(),
                name,
            }
        })
        .collect();
    out.sort_by(|a, b| a.name.cmp(&b.name));
    out
}

fn rel_to(root: &Path, path: &Path) -> String {
    path.strip_prefix(root)
        .unwrap_or(path)
        .to_string_lossy()
        .replace('\\', "/")
}

/// Every unsupported mod in an install.
pub fn scan_install(root: &Path) -> Vec<UnsupportedMod> {
    let paks = root.join("Meteorite/Content/Paks");
    let mods = crate::mods_dir(root);
    let mut out = scan_paks(&paks, &rel_to(root, &paks));
    out.extend(scan_ue4ss(&mods, &rel_to(root, &mods), &known_ue4ss_mods()));
    out
}

pub fn scan() -> Result<Vec<UnsupportedMod>, String> {
    let (root, _) = crate::find_game_install().ok_or("The game was not found.")?;
    Ok(scan_install(&root))
}

// ─── Moving aside and back ──────────────────────────────────────────────

/// Move every file of `mods` from `root` into a fresh set-aside folder,
/// recording each move before the next. A file the game holds open stays
/// put and is reported.
pub fn set_aside_in(root: &Path, mods: &[UnsupportedMod]) -> SetAsideResult {
    let at = now();
    let mut dest_root = root.join(SET_ASIDE_DIR).join(at.to_string());
    let mut n = 1;
    while dest_root.exists() {
        dest_root = root.join(SET_ASIDE_DIR).join(format!("{at}-{n}"));
        n += 1;
    }
    let mut ledger = load_ledger();
    let mut result = SetAsideResult::default();
    for m in mods {
        for rel in &m.files {
            let from = root.join(rel);
            let to = dest_root.join(rel);
            let moved = to
                .parent()
                .map_or(Ok(()), fs::create_dir_all)
                .and_then(|_| fs::rename(&from, &to));
            match moved {
                Ok(()) => {
                    log(&format!("moved {} -> {}", from.display(), to.display()));
                    ledger.entries.push(Moved {
                        from,
                        to,
                        kind: m.kind.clone(),
                        at,
                    });
                    if let Err(e) = save_ledger(&ledger) {
                        log(&format!("cannot record the move: {e}"));
                    }
                    result.moved += 1;
                }
                Err(e) => {
                    log(&format!("could not move {}: {e}", from.display()));
                    result.failed.push(format!("{rel}: {e}"));
                }
            }
        }
    }
    result
}

pub fn set_aside() -> Result<SetAsideResult, String> {
    let (root, _) = crate::find_game_install().ok_or("The game was not found.")?;
    let mods = scan_install(&root);
    Ok(set_aside_in(&root, &mods))
}

/// Move everything in the ledger back where it came from. An entry whose
/// original place is taken again stays set aside, and in the ledger, so a
/// later restore can try again once the player has chosen.
pub fn restore() -> RestoreResult {
    let mut ledger = load_ledger();
    let mut result = RestoreResult::default();
    if ledger.entries.is_empty() {
        return result;
    }
    let mut left = Vec::new();
    let mut emptied = BTreeSet::new();
    for entry in ledger.entries.drain(..) {
        if !entry.to.exists() {
            log(&format!("{} is no longer in the set-aside folder; forgotten", entry.to.display()));
            continue;
        }
        if entry.from.exists() {
            log(&format!(
                "{} is back already; kept the set-aside copy at {}",
                entry.from.display(),
                entry.to.display()
            ));
            result.kept.push(entry.to.to_string_lossy().into_owned());
            left.push(entry);
            continue;
        }
        let moved = entry
            .from
            .parent()
            .map_or(Ok(()), fs::create_dir_all)
            .and_then(|_| fs::rename(&entry.to, &entry.from));
        match moved {
            Ok(()) => {
                log(&format!("moved back {} -> {}", entry.to.display(), entry.from.display()));
                if let Some(parent) = entry.to.parent() {
                    emptied.insert(parent.to_path_buf());
                }
                result.restored += 1;
            }
            Err(e) => {
                log(&format!("could not move back {}: {e}", entry.to.display()));
                left.push(entry);
            }
        }
    }
    ledger.entries = left;
    if let Err(e) = save_ledger(&ledger) {
        log(&format!("cannot record the restore: {e}"));
    }
    // Folders the moves made and left empty. `remove_dir` only ever removes
    // an empty folder, so nothing that is still in one can go with it.
    for dir in emptied {
        let mut d = dir.as_path();
        while d.file_name().is_some_and(|n| n != SET_ASIDE_DIR) && fs::remove_dir(d).is_ok() {
            match d.parent() {
                Some(p) => d = p,
                None => break,
            }
        }
    }
    result
}

/// What is set aside now.
pub fn status() -> Vec<Moved> {
    load_ledger().entries
}

/// Move everything back once the game exits: wait for it to appear (a
/// launch through Steam takes a while), then for it to go. A launcher closed
/// in between leaves the ledger, and its next start restores (lib.rs setup).
pub fn restore_after_game() {
    std::thread::spawn(|| {
        let poll = std::time::Duration::from_secs(3);
        let mut seen = false;
        for _ in 0..100 {
            if crate::game_running() {
                seen = true;
                break;
            }
            std::thread::sleep(poll);
        }
        if seen {
            while crate::game_running() {
                std::thread::sleep(poll);
            }
        }
        let r = restore();
        log(&format!("after the game: {} moved back, {} kept", r.restored, r.kept.len()));
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn this_pcs_game_and_mjolnir_containers_are_known() {
        for name in [
            "global.ucas",
            "global.utoc",
            "pakchunk0-Windows.pak",
            "pakchunk115-Windows.utoc",
            "pakchunk530-Windows.ucas",
            "pakchunk12optional-Windows.pak",
            "pakchunk3-WinGDK.ucas",
            "pakchunk900-MJOLNIRHUB-mjolnir-ce-runtime-10_P.pak",
            "pakchunk902-MJOLNIRHUB-ce-blood-gulch-2_2_P.utoc",
            "pakchunk969-MJOLNIRLAND-Windows.pak",
            "pakchunk985-MJOLNIRCOOK-ASC_P.ucas",
            "pakchunk996-MJOLNIRREG_P.utoc",
            "readme.txt",
            "LogicMods/notes.md",
        ] {
            assert!(!pak_file_unsupported(name), "{name} must be known");
        }
    }

    #[test]
    fn other_containers_are_unsupported() {
        for name in [
            "z_BetterHUD_P.pak",
            "pakchunk99-Mod_P.utoc",
            "pakchunk42-Windows_P.pak",
            "pakchunk9001-MJOLNIRFAKE.pak",
            "pakchunk800-MJOLNIRX_P.pak",
            "~mods/CoolMod.pak",
            "~mods/pakchunk0-Windows.pak",
            "LogicMods/SomeBlueprint.pak",
            "global2.utoc",
            "global.pak",
        ] {
            assert!(pak_file_unsupported(name), "{name} must be unsupported");
        }
    }

    #[test]
    fn ue4ss_mods_are_judged_by_name_and_whether_they_run() {
        let known: BTreeSet<String> = ["SomeCodeMod".to_string()].into();
        assert!(ue4ss_mod_unsupported("InfiniteAmmo", true, &known));
        assert!(!ue4ss_mod_unsupported("InfiniteAmmo", false, &known));
        assert!(!ue4ss_mod_unsupported("MJOLNIRLobby", true, &known));
        assert!(!ue4ss_mod_unsupported("SomeCodeMod", true, &known));
        assert!(!ue4ss_mod_unsupported("BPModLoaderMod", true, &known));
        assert!(!ue4ss_mod_unsupported("keybinds", true, &known));
    }

    fn scratch(name: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!("mjolnir-unsupported-{name}"));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("Meteorite/Content/Paks/~mods")).unwrap();
        fs::create_dir_all(root.join("Meteorite/Binaries/Win64/ue4ss/Mods/InfiniteAmmo/Scripts")).unwrap();
        fs::create_dir_all(root.join("Meteorite/Binaries/Win64/ue4ss/Mods/OffMod/Scripts")).unwrap();
        for f in [
            "Meteorite/Content/Paks/pakchunk0-Windows.pak",
            "Meteorite/Content/Paks/pakchunk996-MJOLNIRREG_P.pak",
            "Meteorite/Content/Paks/z_Mod_P.pak",
            "Meteorite/Content/Paks/z_Mod_P.utoc",
            "Meteorite/Content/Paks/z_Mod_P.ucas",
            "Meteorite/Content/Paks/~mods/Other.pak",
            "Meteorite/Binaries/Win64/ue4ss/Mods/InfiniteAmmo/Scripts/main.lua",
            "Meteorite/Binaries/Win64/ue4ss/Mods/OffMod/Scripts/main.lua",
        ] {
            fs::write(root.join(f), b"x").unwrap();
        }
        fs::write(
            root.join("Meteorite/Binaries/Win64/ue4ss/Mods/mods.txt"),
            "InfiniteAmmo : 1\nOffMod : 0\n",
        )
        .unwrap();
        root
    }

    #[test]
    fn a_scan_groups_a_containers_files_and_finds_running_ue4ss_mods() {
        let root = scratch("scan");
        let paks = root.join("Meteorite/Content/Paks");
        let mods = root.join("Meteorite/Binaries/Win64/ue4ss/Mods");
        let found = scan_paks(&paks, "Meteorite/Content/Paks");
        let names: Vec<&str> = found.iter().map(|m| m.name.as_str()).collect();
        assert_eq!(names, ["z_Mod_P", "Other"]);
        assert_eq!(found[0].files.len(), 3);
        assert_eq!(found[0].bytes, 3);
        let ue = scan_ue4ss(&mods, "Meteorite/Binaries/Win64/ue4ss/Mods", &BTreeSet::new());
        assert_eq!(ue.len(), 1);
        assert_eq!(ue[0].name, "InfiniteAmmo");
        assert_eq!(ue[0].files, ["Meteorite/Binaries/Win64/ue4ss/Mods/InfiniteAmmo"]);
    }

    /// The only test that writes the ledger (a scratch one, `state_dir`).
    #[test]
    fn set_aside_then_restore_round_trips_and_never_overwrites() {
        let _ = fs::remove_dir_all(state_dir());
        let root = scratch("roundtrip");
        let paks = root.join("Meteorite/Content/Paks");
        let mut mods = scan_paks(&paks, "Meteorite/Content/Paks");
        mods.extend(scan_ue4ss(
            &root.join("Meteorite/Binaries/Win64/ue4ss/Mods"),
            "Meteorite/Binaries/Win64/ue4ss/Mods",
            &BTreeSet::new(),
        ));
        let r = set_aside_in(&root, &mods);
        assert_eq!(r.moved, 5);
        assert!(r.failed.is_empty());
        assert!(!paks.join("z_Mod_P.pak").exists());
        assert!(!root.join("Meteorite/Binaries/Win64/ue4ss/Mods/InfiniteAmmo").exists());
        assert!(paks.join("pakchunk0-Windows.pak").exists());

        // The player puts one back by hand: that one is kept, not replaced.
        fs::write(paks.join("z_Mod_P.utoc"), b"new").unwrap();
        let back = restore();
        assert_eq!(back.restored, 4);
        assert_eq!(back.kept.len(), 1);
        assert_eq!(fs::read(paks.join("z_Mod_P.utoc")).unwrap(), b"new");
        assert!(paks.join("~mods/Other.pak").exists());
        assert!(root.join("Meteorite/Binaries/Win64/ue4ss/Mods/InfiniteAmmo/Scripts/main.lua").exists());
        let kept = PathBuf::from(&back.kept[0]);
        assert_eq!(fs::read(&kept).unwrap(), b"x");

        // Sorted out: the kept copy goes back once its place is free.
        fs::remove_file(paks.join("z_Mod_P.utoc")).unwrap();
        assert_eq!(restore().restored, 1);
        assert_eq!(fs::read(paks.join("z_Mod_P.utoc")).unwrap(), b"x");
        assert!(status().iter().all(|m| !m.from.starts_with(&root)));
        assert!(fs::read_dir(root.join(SET_ASIDE_DIR)).unwrap().next().is_none());
    }
}
