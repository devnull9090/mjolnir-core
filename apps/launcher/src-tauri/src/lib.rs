use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs;
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use tauri::{AppHandle, Emitter};

mod changelog;
mod hub;
mod links;
mod maps;
mod tools;
mod transfer;

// ─── Runtime bundle ─────────────────────────────────────────────────────
//
// UE4SS, the config and AOB signatures tuned for this game, and the UE4SS
// infrastructure mods. It used to be `modpack`, which also carried the
// MJOLNIR mods; those now install from the signed code-mod set, which records
// what it put down and can verify it afterwards (see hub::code_mods_status).
//
// The bundle's manifest is Ed25519-signed by the same key as the mods
// manifest, and this launcher refuses to install from it unsigned — it drops
// a DLL that gets injected into the game process, so it is the last thing
// that should be taken on trust.
const RUNTIME_BASE: &str = "https://releases.mjolnircore.com/runtime/latest";
const MANIFEST_URL: &str = "https://releases.mjolnircore.com/runtime/latest/manifest.json";
const RUNTIME_ZIP_URL: &str = "https://releases.mjolnircore.com/runtime/latest/runtime.zip";

// ─── Types ──────────────────────────────────────────────────────────────

/// Represents a mod entry from mods.txt
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ModEntry {
    pub name: String,
    pub enabled: bool,
    pub description: String,
    pub version: String,
}

/// Game installation info
#[derive(Debug, Serialize, Deserialize)]
pub struct GameInfo {
    pub found: bool,
    pub install_path: Option<String>,
    pub ue4ss_installed: bool,
    pub mods_path: Option<String>,
}

/// Launcher settings that persist between sessions
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct LauncherSettings {
    pub launch_method: String, // "steam" | "gamepass" | "exe"
    pub custom_exe_path: Option<String>,
    /// Where the game is, when the player says so rather than the probes.
    ///
    /// Detection only knows the conventional layouts, so a Steam library on a
    /// drive it does not guess, a moved install, or a copy kept outside a
    /// store leaves the launcher with nothing to work on. This overrides the
    /// search entirely — see `find_game_install`.
    ///
    /// Defaulted, so a settings file written before this field existed still
    /// reads.
    #[serde(default)]
    pub install_path: Option<String>,
    /// Open UE4SS's console window beside the game. Off unless the player
    /// asks: a terminal full of log lines alarms players who did not expect
    /// one, and the same lines go to `UE4SS.log` either way.
    ///
    /// Defaulted, so a settings file written before this field existed reads
    /// as hidden.
    #[serde(default)]
    pub show_ue4ss_console: bool,
}

impl Default for LauncherSettings {
    fn default() -> Self {
        Self {
            launch_method: "steam".to_string(),
            custom_exe_path: None,
            install_path: None,
            show_ue4ss_console: false,
        }
    }
}

/// Build/environment info shown on the settings page
#[derive(Debug, Serialize, Deserialize)]
pub struct BuildInfo {
    pub launcher_version: String,
    pub game_found: bool,
    pub install_path: Option<String>,
    /// How the install path was arrived at — see `install_source`.
    pub install_source: String,
    pub ue4ss_installed: bool,
    pub mods_path: Option<String>,
    pub mods_count: usize,
}

/// Manifest for the modpack (downloaded from R2)
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ModpackManifest {
    pub version: String,
    pub ue4ss_version: String,
    pub files: Vec<ManifestFile>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ManifestFile {
    pub path: String,
    pub sha256: String,
    pub size: u64,
    /// Seed state rather than shipped content — `UE4SS-settings.ini` and
    /// `mods.txt`. Written once when absent, then never touched again: they
    /// hold the player's mod list and machine-specific tuning, and the
    /// installer used to overwrite them on every reinstall.
    ///
    /// Defaulted, so a manifest published before this field existed reads as
    /// "all content", which is how the old modpack behaved.
    #[serde(default)]
    pub config: bool,
}

/// Detailed install status
#[derive(Debug, Serialize, Deserialize)]
pub struct InstallStatus {
    pub game_found: bool,
    pub install_path: Option<String>,
    /// Where UE4SS goes: the `Win64` folder on Steam, `WinGDK` on the Xbox app.
    pub binaries_path: Option<String>,
    pub platform: String, // "steam" | "gamepass" | "manual" | "unknown"
    pub ue4ss_installed: bool,
    pub modpack_enabled: bool,
    pub manifest_version: Option<String>,
    pub ue4ss_version: Option<String>,
    /// How the install path was arrived at — see `install_source`.
    pub source: String,
    /// The manual location as it was configured, whether or not it resolved.
    ///
    /// Present alongside `game_found: false` when a set location has gone
    /// missing, which is the one case the UI has to explain rather than
    /// offering to search again.
    pub manual_path: Option<String>,
}

/// Where the install path came from. A location set in Settings wins over the
/// environment, which wins over detection.
mod install_source {
    /// Nothing set here, but `MJOLNIR_GAME_DIR` says where the game is.
    pub const ENV: &str = "env";
    /// The player chose it in Settings.
    pub const MANUAL: &str = "manual";
    /// Found by probing the conventional store locations.
    pub const AUTO: &str = "auto";
    /// Nothing configured and nothing found.
    pub const NONE: &str = "none";
}

/// Result of verifying installed files against manifest
#[derive(Debug, Serialize, Deserialize)]
pub struct VerifyResult {
    pub checked: usize,
    pub passed: usize,
    pub failed: Vec<String>,
    pub missing: Vec<String>,
}

/// Progress event emitted during install
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct InstallProgress {
    pub stage: String,
    pub message: String,
    pub percent: f32,
}

// ─── Paths & helpers ────────────────────────────────────────────────────

/// Get the path to the settings JSON file
fn settings_path() -> PathBuf {
    let mut dir = dirs::config_dir().unwrap_or_else(|| PathBuf::from("."));
    dir.push("com.devnull9090.mjolnir-launcher");
    dir.push("launcher_settings.json");
    dir
}

/// Get the path to the cached manifest
fn cached_manifest_path() -> PathBuf {
    let mut dir = dirs::config_dir().unwrap_or_else(|| PathBuf::from("."));
    dir.push("com.devnull9090.mjolnir-launcher");
    dir.push("manifest.json");
    dir
}

/// Overrides detection for a single run, and is handed to every tool the
/// launcher starts. A directory: the install root, or anything inside it that
/// names the root — see `resolve_install_root`.
///
/// It sits *below* the saved setting on purpose. The setting is something the
/// player typed into this window; an environment variable that quietly beat it
/// would leave a control in Settings that does nothing.
pub(crate) const GAME_DIR_ENV: &str = "MJOLNIR_GAME_DIR";

/// Where the game binaries sit under the install root, per store. Steam ships
/// a `Win64` build; the Xbox app ships a `WinGDK` build of the same game, and
/// that is the folder UE4SS has to go into there. First match wins.
const BINARIES_DIRS: &[&str] = &["Meteorite/Binaries/Win64", "Meteorite/Binaries/WinGDK"];

/// Directories that only exist inside a Halo Campaign Evolved install. One is
/// enough: a Game Pass copy that has never been launched has the content but
/// not always the binaries beside it.
const INSTALL_MARKERS: &[&str] = &[
    "Meteorite/Binaries/Win64",
    "Meteorite/Binaries/WinGDK",
    "Meteorite/Content/Paks",
];

/// What the install folder is called under a library folder, on every store.
/// Steam drops the colon from the title; the Xbox app turns it into a dash.
const GAME_DIRS: &[&str] = &["Halo Campaign Evolved", "Halo- Campaign Evolved"];
#[cfg(test)]
const GAME_DIR: &str = GAME_DIRS[0];

/// The Xbox app keeps the game one level down, under `Content`, so the root
/// holding `Meteorite` is `<library>\Halo- Campaign Evolved\Content`.
const XBOX_CONTENT_DIR: &str = "Content";

/// The game executable, the same name in both builds.
const GAME_EXE: &str = "HaloCampaignEvolved.exe";

/// The binaries folder inside an install root: whichever store layout is
/// present, or the Steam one when neither exists yet so that an error names a
/// real path rather than none.
pub(crate) fn binaries_dir(root: &Path) -> PathBuf {
    BINARIES_DIRS
        .iter()
        .map(|d| root.join(d))
        .find(|d| d.is_dir())
        .unwrap_or_else(|| root.join(BINARIES_DIRS[0]))
}

/// Where UE4SS loads Lua mods from, under an install root.
pub(crate) fn mods_dir(root: &Path) -> PathBuf {
    binaries_dir(root).join("ue4ss/Mods")
}

/// How far above a chosen folder the install root may be. Deepest accepted
/// pick is `Meteorite\Content\Paks`, three levels down.
const ROOT_SEARCH_DEPTH: usize = 4;

fn is_install_root(path: &Path) -> bool {
    INSTALL_MARKERS.iter().any(|m| path.join(m).is_dir())
}

/// Resolve whatever the player pointed at to the install root.
///
/// A folder picker invites the wrong depth — the game folder, the `Meteorite`
/// folder inside it, the `Win64` folder someone was just looking at, or the
/// executable itself are all reasonable answers to "where is the game". Each
/// of them names the root, so each is accepted and walked up from rather than
/// rejected with a note about which one was meant.
///
/// `None` means nothing in that chain looks like an install, which is the only
/// answer worth refusing: a path that is not the game would otherwise be
/// reported as found and fail later, during an install, with a confusing error.
fn resolve_install_root(input: &str) -> Option<PathBuf> {
    let raw = PathBuf::from(input.trim().trim_matches('"').trim());
    // An executable, or any other file, identifies the folder holding it.
    let start = if raw.is_file() {
        raw.parent()?.to_path_buf()
    } else {
        raw
    };
    if !start.is_dir() {
        return None;
    }

    // A folder holding the game by name — a Steam library, or wherever a
    // moved copy was put — names it just as well as the install itself. So
    // does the Xbox app's game folder, whose install root is `Content` inside.
    for name in GAME_DIRS {
        if let Some(root) = xbox_install_root(&start.join(name)) {
            return Some(root);
        }
    }
    if let Some(root) = xbox_install_root(&start) {
        return Some(root);
    }

    let mut current = start.as_path();
    for _ in 0..=ROOT_SEARCH_DEPTH {
        if is_install_root(current) {
            return Some(current.to_path_buf());
        }
        current = current.parent()?;
    }
    None
}

/// Guess the storefront from where the install sits. Only cosmetic — the
/// launch route is a separate setting the player owns.
fn platform_for(path: &Path) -> String {
    let text = path.to_string_lossy().to_ascii_lowercase();
    if text.contains("steamapps") {
        "steam".to_string()
    } else if text.contains("xboxgames")
        || text.contains("xbox games")
        || text.contains("windowsapps")
    {
        "gamepass".to_string()
    } else {
        "manual".to_string()
    }
}

/// The manual location and where it was configured, if there is one.
fn manual_install() -> Option<(String, &'static str)> {
    let saved = get_settings()
        .install_path
        .map(|v| v.trim().to_string())
        .filter(|v| !v.is_empty());
    if let Some(path) = saved {
        return Some((path, install_source::MANUAL));
    }
    let from_env = std::env::var(GAME_DIR_ENV)
        .ok()
        .map(|v| v.trim().to_string())
        .filter(|v| !v.is_empty())?;
    Some((from_env, install_source::ENV))
}

/// Find HCE install and return (path, platform)
pub(crate) fn find_game_install() -> Option<(PathBuf, String)> {
    // A manual location wins outright, and deliberately does not fall back to
    // the probes when it does not resolve: installing UE4SS into some other
    // copy of the game than the one the player named is worse than reporting
    // the location as missing and letting them fix it.
    if let Some((path, _)) = manual_install() {
        let root = resolve_install_root(&path)?;
        let platform = platform_for(&root);
        return Some((root, platform));
    }

    // Check Steam locations first
    let steam_dirs = vec![
        r"C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved",
        r"C:\Program Files\Steam\steamapps\common\Halo Campaign Evolved",
        r"D:\SteamLibrary\steamapps\common\Halo Campaign Evolved",
        r"E:\SteamLibrary\steamapps\common\Halo Campaign Evolved",
    ];

    for dir in steam_dirs {
        let path = PathBuf::from(dir);
        if path.exists() {
            return Some((path, "steam".to_string()));
        }
    }

    // Every Steam library, from libraryfolders.vdf in Steam's own folder (the
    // registry knows where Steam is, which need not be Program Files).
    let mut steam_roots: Vec<PathBuf> = steam_install_dir().into_iter().collect();
    steam_roots.push(PathBuf::from(r"C:\Program Files (x86)\Steam"));
    for root in steam_roots {
        let vdf_path = root.join("steamapps").join("libraryfolders.vdf");
        if let Ok(content) = fs::read_to_string(&vdf_path) {
            for line in content.lines() {
                let trimmed = line.trim();
                if trimmed.starts_with("\"path\"") {
                    if let Some(path_str) = trimmed.split('"').nth(3) {
                        let candidate =
                            PathBuf::from(path_str).join("steamapps/common/Halo Campaign Evolved");
                        if candidate.exists() {
                            return Some((candidate, "steam".to_string()));
                        }
                    }
                }
            }
        }
    }

    // Check Xbox app / Game Pass locations. Older Xbox app versions install
    // under `XboxGames`, newer ones under `Xbox Games`; the game sits inside
    // `Content` in either, which is the root everything else hangs off.
    let drives = ["C", "D", "E", "F", "G"];
    for drive in &drives {
        for library in ["XboxGames", "Xbox Games"] {
            for name in GAME_DIRS {
                let game_dir = PathBuf::from(format!("{drive}:\\{library}\\{name}"));
                if let Some(root) = xbox_install_root(&game_dir) {
                    return Some((root, "gamepass".to_string()));
                }
            }
        }
    }

    // Check WindowsApps (legacy, restricted)
    let windows_apps = r"C:\Program Files\WindowsApps";
    if Path::new(windows_apps).exists() {
        if let Ok(entries) = fs::read_dir(windows_apps) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().to_string();
                if name.contains("HaloCampaignEvolved") || name.contains("Meteorite") {
                    return Some((entry.path(), "gamepass".to_string()));
                }
            }
        }
    }

    None
}

/// Where Steam is installed, from the registry (`HKCU\Software\Valve\Steam`,
/// `SteamPath`). Read through `reg.exe` rather than a registry crate.
fn steam_install_dir() -> Option<PathBuf> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let out = std::process::Command::new("reg")
            .args(["query", r"HKCU\Software\Valve\Steam", "/v", "SteamPath"])
            .creation_flags(CREATE_NO_WINDOW)
            .output()
            .ok()?;
        steam_path_from_reg(&String::from_utf8_lossy(&out.stdout))
    }
    #[cfg(not(windows))]
    {
        None
    }
}

/// `SteamPath    REG_SZ    c:/program files (x86)/steam` → that folder.
fn steam_path_from_reg(output: &str) -> Option<PathBuf> {
    output.lines().find_map(|line| {
        let (_, value) = line.split_once("REG_SZ")?;
        let value = value.trim();
        (!value.is_empty()).then(|| PathBuf::from(value))
    })
}

/// The install root at or just inside a game folder. The Xbox app keeps the
/// binaries and content under `Content`; Steam, and a copy someone moved, has
/// them directly inside. The `Content` level is checked first because the Xbox
/// game folder itself never passes `is_install_root`.
fn xbox_install_root(game_dir: &Path) -> Option<PathBuf> {
    let content = game_dir.join(XBOX_CONTENT_DIR);
    if is_install_root(&content) {
        return Some(content);
    }
    is_install_root(game_dir).then(|| game_dir.to_path_buf())
}

/// Get the game binaries directory (`Win64` on Steam, `WinGDK` on the Xbox app)
fn get_bin_dir() -> Option<PathBuf> {
    find_game_install().map(|(p, _)| binaries_dir(&p))
}

/// Compute SHA-256 hash of a file
fn sha256_file(path: &Path) -> io::Result<String> {
    let mut file = fs::File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 8192];
    loop {
        let n = file.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        hasher.update(&buffer[..n]);
    }
    Ok(hex::encode(hasher.finalize()))
}

/// Load cached manifest from disk
fn load_cached_manifest() -> Option<ModpackManifest> {
    let path = cached_manifest_path();
    if let Ok(content) = fs::read_to_string(&path) {
        serde_json::from_str(&content).ok()
    } else {
        None
    }
}

/// Save manifest to disk cache
fn save_cached_manifest(manifest: &ModpackManifest) -> Result<(), String> {
    let path = cached_manifest_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let json = serde_json::to_string_pretty(manifest).map_err(|e| e.to_string())?;
    fs::write(&path, json).map_err(|e| e.to_string())?;
    Ok(())
}

/// Check if UE4SS proxy DLL is present (enabled or disabled)
fn check_ue4ss_dll(bin_dir: &Path) -> (bool, bool) {
    let active = bin_dir.join("dwmapi.dll");
    let disabled = bin_dir.join("dwmapi.dll.disabled");
    let installed = active.exists() || disabled.exists();
    let enabled = active.exists();
    (installed, enabled)
}

/// The UE4SS settings file the game will read: beside the chosen executable
/// when the player launches one directly, else in the detected install.
fn ue4ss_settings_file(settings: &LauncherSettings) -> Option<PathBuf> {
    let custom_bin = (settings.launch_method == "exe")
        .then(|| settings.custom_exe_path.as_deref())
        .flatten()
        .and_then(|exe| Path::new(exe).parent().map(Path::to_path_buf));
    custom_bin
        .into_iter()
        .chain(get_bin_dir())
        .map(|bin| bin.join("ue4ss").join("UE4SS-settings.ini"))
        .find(|ini| ini.exists())
}

/// `ini` with `[Debug] ConsoleEnabled` set to `show`, everything else left as
/// it was.
fn with_console_enabled(ini: &str, show: bool) -> String {
    with_ini_value(ini, "Debug", "ConsoleEnabled", if show { "1" } else { "0" })
}

/// The fewest seconds UE4SS may scan before giving up. Its FName::FName
/// check passes only once the engine ticks, ~20 s into a launch on a fast
/// PC; with UE4SS's stock 30 a slower one gives up first, and no Lua mod
/// runs at all (playtest, 2026-10-03: the lobby showed, its buttons were
/// dead). A failed scan costs this long only when UE4SS is broken anyway.
const MIN_SECONDS_TO_SCAN: u32 = 120;

/// `ini` with `[General] SecondsToScanBeforeGivingUp` at least
/// [`MIN_SECONDS_TO_SCAN`]. A longer timeout the player chose is kept.
fn with_scan_time_floor(ini: &str) -> String {
    let current = ini_value(ini, "General", "SecondsToScanBeforeGivingUp")
        .and_then(|v| v.parse::<u32>().ok());
    match current {
        Some(seconds) if seconds >= MIN_SECONDS_TO_SCAN => ini.to_string(),
        _ => with_ini_value(ini, "General", "SecondsToScanBeforeGivingUp", &MIN_SECONDS_TO_SCAN.to_string()),
    }
}

/// Whether `line` is `key = ...`, ignoring case and spacing.
fn is_ini_key(line: &str, key: &str) -> bool {
    line.split_once('=')
        .is_some_and(|(k, _)| k.trim().eq_ignore_ascii_case(key))
}

/// The value of `[section] key`, trimmed; `None` when it is not set there.
fn ini_value(ini: &str, section: &str, key: &str) -> Option<String> {
    let header = format!("[{section}]");
    let mut in_section = false;
    for line in ini.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with('[') {
            in_section = trimmed.eq_ignore_ascii_case(&header);
        } else if in_section && is_ini_key(trimmed, key) {
            return trimmed.split_once('=').map(|(_, v)| v.trim().to_string());
        }
    }
    None
}

/// `ini` with `[section] key` set to `value`, everything else left as it
/// was. The file is seed state the player may have tuned, so this edits the
/// one key rather than writing a fresh file. A missing key goes at the end
/// of its section, and a missing section at the end of the file.
fn with_ini_value(ini: &str, section: &str, key: &str, value: &str) -> String {
    let entry = format!("{key} = {value}");
    let header = format!("[{section}]");
    let newline = if ini.contains("\r\n") { "\r\n" } else { "\n" };
    let mut out = String::with_capacity(ini.len() + entry.len() + 16);
    let mut in_section = false;
    let mut section_seen = false;
    let mut written = false;

    for line in ini.split_inclusive('\n') {
        let body = line.trim_end_matches(['\r', '\n']);
        let trimmed = body.trim();
        if trimmed.starts_with('[') {
            // Leaving the section without having met the key: add it there.
            if in_section && !written {
                out.push_str(&entry);
                out.push_str(newline);
                written = true;
            }
            in_section = trimmed.eq_ignore_ascii_case(&header);
            section_seen |= in_section;
        } else if in_section && !written && is_ini_key(trimmed, key) {
            out.push_str(&entry);
            out.push_str(&line[body.len()..]);
            written = true;
            continue;
        }
        out.push_str(line);
    }

    if !written {
        if !out.is_empty() && !out.ends_with('\n') {
            out.push_str(newline);
        }
        if !section_seen {
            out.push_str(&header);
            out.push_str(newline);
        }
        out.push_str(&entry);
        out.push_str(newline);
    }
    out
}

/// `ini` with `[General] EnableHotReloadSystem` off. Ctrl+R reloads every
/// Lua mod, and the native halves they load had hooks in the game: a reload
/// mid-match crashed the host (two PCs, 2026-10-03). The DLLs now pin
/// themselves, but a player has no use for a reload, and a stray Ctrl+R
/// still restarts every mod in the middle of a game.
fn with_hot_reload_off(ini: &str) -> String {
    with_ini_value(ini, "General", "EnableHotReloadSystem", "0")
}

/// Everything the launcher keeps in the player's UE4SS settings.
fn with_launcher_settings(ini: &str, show_console: bool) -> String {
    with_hot_reload_off(&with_scan_time_floor(&with_console_enabled(ini, show_console)))
}

/// Bring the installed UE4SS settings in line with what the launcher needs:
/// the player's console choice, the scan-time floor and no hot reload. UE4SS
/// reads the file once at startup, so this has to land before the game
/// starts; with no UE4SS installed there is nothing to do.
fn apply_ue4ss_settings(settings: &LauncherSettings) -> Result<(), String> {
    let Some(path) = ue4ss_settings_file(settings) else {
        return Ok(());
    };
    let ini = fs::read_to_string(&path)
        .map_err(|e| format!("Failed to read {}: {}", path.display(), e))?;
    let updated = with_launcher_settings(&ini, settings.show_ue4ss_console);
    if updated != ini {
        fs::write(&path, updated)
            .map_err(|e| format!("Failed to write {}: {}", path.display(), e))?;
    }
    Ok(())
}

// ─── Existing commands ──────────────────────────────────────────────────

#[tauri::command]
fn detect_game() -> GameInfo {
    match find_game_install() {
        Some((install_path, _platform)) => {
            let bin_dir = binaries_dir(&install_path);
            let ue4ss_dir = bin_dir.join("ue4ss");
            let mods_dir = ue4ss_dir.join("Mods");

            GameInfo {
                found: true,
                install_path: Some(install_path.to_string_lossy().to_string()),
                ue4ss_installed: ue4ss_dir.exists()
                    && ue4ss_dir.join("UE4SS-settings.ini").exists(),
                mods_path: if mods_dir.exists() {
                    Some(mods_dir.to_string_lossy().to_string())
                } else {
                    None
                },
            }
        }
        None => GameInfo {
            found: false,
            install_path: None,
            ue4ss_installed: false,
            mods_path: None,
        },
    }
}

/// Parse mods.txt into a list of ModEntry
fn parse_mods_txt(mods_dir: &Path) -> Vec<ModEntry> {
    let mods_txt = mods_dir.join("mods.txt");
    let mut entries = Vec::new();

    if let Ok(content) = fs::read_to_string(&mods_txt) {
        for line in content.lines() {
            let trimmed = line.trim();
            if trimmed.is_empty() || trimmed.starts_with(';') || trimmed.starts_with('#') {
                continue;
            }

            // Format: ModName : 1  (or 0 for disabled)
            let parts: Vec<&str> = trimmed.splitn(2, ':').collect();
            if parts.len() == 2 {
                let name = parts[0].trim().to_string();
                let enabled = parts[1].trim() == "1";

                // Try to read description from the mod's main.lua
                let description = read_mod_description(mods_dir, &name);
                let version = read_mod_version(mods_dir, &name);

                entries.push(ModEntry {
                    name,
                    enabled,
                    description,
                    version,
                });
            }
        }
    }

    entries
}

/// Check if a comment line contains meaningful description text.
fn is_meaningful_description(text: &str) -> bool {
    let cleaned = text.trim();

    if cleaned.is_empty() {
        return false;
    }

    // Lines that are just brackets like [[ or ]]
    if cleaned.chars().all(|c| c == '[' || c == ']') {
        return false;
    }

    // Lines that are just separator characters like ####, ====, ----
    if cleaned.len() >= 3 && cleaned.chars().all(|c| c == '#' || c == '=' || c == '-' || c == '*') {
        return false;
    }

    // Must contain at least one alphabetic character to be a real description
    cleaned.chars().any(|c| c.is_alphabetic())
}

fn read_mod_description(mods_dir: &Path, mod_name: &str) -> String {
    let main_lua = mods_dir.join(mod_name).join("Scripts/main.lua");
    if let Ok(content) = fs::read_to_string(&main_lua) {
        for line in content.lines() {
            let trimmed = line.trim();
            if trimmed.starts_with("--") && !trimmed.starts_with("---") {
                let comment_text = trimmed.trim_start_matches('-').trim();
                if is_meaningful_description(comment_text) {
                    return comment_text.to_string();
                }
            }
        }
    }
    format!("{} mod", mod_name)
}

fn read_mod_version(mods_dir: &Path, mod_name: &str) -> String {
    let main_lua = mods_dir.join(mod_name).join("Scripts/main.lua");
    if let Ok(content) = fs::read_to_string(&main_lua) {
        for line in content.lines() {
            if line.contains("VERSION") && line.contains("=") {
                if let Some(ver) = line.split('"').nth(1) {
                    return ver.to_string();
                }
            }
        }
    }
    "1.0.0".to_string()
}

#[tauri::command]
fn get_mods() -> Vec<ModEntry> {
    if let Some((install_path, _)) = find_game_install() {
        let mods_dir = mods_dir(&install_path);
        if mods_dir.exists() {
            return parse_mods_txt(&mods_dir);
        }
    }
    Vec::new()
}

#[tauri::command]
fn toggle_mod(name: String, enabled: bool) -> Result<(), String> {
    let (install_path, _) = find_game_install().ok_or("Game not found")?;
    let mods_dir = mods_dir(&install_path);
    let mods_txt = mods_dir.join("mods.txt");

    let content = fs::read_to_string(&mods_txt).map_err(|e| e.to_string())?;
    let new_content: String = content
        .lines()
        .map(|line| {
            let trimmed = line.trim();
            if let Some(mod_name) = trimmed.split(':').next() {
                if mod_name.trim() == name {
                    return format!("{} : {}", name, if enabled { "1" } else { "0" });
                }
            }
            line.to_string()
        })
        .collect::<Vec<_>>()
        .join("\n");

    fs::write(&mods_txt, new_content).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
fn get_settings() -> LauncherSettings {
    let path = settings_path();
    if let Ok(content) = fs::read_to_string(&path) {
        if let Ok(settings) = serde_json::from_str::<LauncherSettings>(&content) {
            return settings;
        }
    }
    LauncherSettings::default()
}

#[tauri::command]
fn save_settings(settings: LauncherSettings) -> Result<(), String> {
    let path = settings_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let json = serde_json::to_string_pretty(&settings).map_err(|e| e.to_string())?;
    fs::write(&path, json).map_err(|e| e.to_string())?;
    Ok(())
}

/// Save the console choice on its own and write it to UE4SS straight away, so
/// it holds when the game is started from Steam rather than the launcher.
/// Only this field changes, so an unsaved edit elsewhere on the Settings page
/// is not saved behind the player's back.
#[tauri::command]
fn set_ue4ss_console(show: bool) -> Result<(), String> {
    let mut settings = get_settings();
    settings.show_ue4ss_console = show;
    save_settings(settings.clone())?;
    apply_ue4ss_settings(&settings)
}

#[tauri::command]
fn get_build_info() -> BuildInfo {
    let game_info = detect_game();
    let mods = get_mods();

    BuildInfo {
        launcher_version: env!("CARGO_PKG_VERSION").to_string(),
        game_found: game_info.found,
        install_path: game_info.install_path,
        install_source: match (manual_install(), game_info.found) {
            (Some((_, source)), _) => source.to_string(),
            (None, true) => install_source::AUTO.to_string(),
            (None, false) => install_source::NONE.to_string(),
        },
        ue4ss_installed: game_info.ue4ss_installed,
        mods_path: game_info.mods_path,
        mods_count: mods.len(),
    }
}

// ─── Manual install location ────────────────────────────────────────────

/// What a candidate folder turns out to be, so the player can see what they
/// picked before it becomes the location everything else writes into.
#[derive(Debug, Serialize)]
pub struct InstallPathCheck {
    pub valid: bool,
    /// The install root the pick resolved to, which may be a parent of it.
    pub resolved: Option<String>,
    pub ue4ss_installed: bool,
    /// Why it was refused, or what was found when it was accepted.
    pub message: String,
}

#[tauri::command]
fn check_install_path(path: String) -> InstallPathCheck {
    match resolve_install_root(&path) {
        Some(root) => {
            let bin_dir = binaries_dir(&root);
            let (dll_installed, _) = check_ue4ss_dll(&bin_dir);
            let ue4ss_installed = dll_installed && bin_dir.join("ue4ss").exists();
            let resolved = root.to_string_lossy().to_string();
            let asked = path.trim().trim_matches('"').trim_end_matches(['\\', '/']);
            let message = if resolved.eq_ignore_ascii_case(asked) {
                "Halo Campaign Evolved found here.".to_string()
            } else {
                // Say so plainly: the folder that gets saved is not the one
                // they clicked, and that difference is worth seeing now.
                format!("Halo Campaign Evolved found. Using the install root: {resolved}")
            };
            InstallPathCheck {
                valid: true,
                resolved: Some(resolved),
                ue4ss_installed,
                message,
            }
        }
        None => InstallPathCheck {
            valid: false,
            resolved: None,
            ue4ss_installed: false,
            message: format!(
                "No Halo Campaign Evolved install at {}. Pick the folder holding \
                 Meteorite\\Binaries — usually the one named \"Halo Campaign \
                 Evolved\", or its Content folder for the Xbox app version.",
                path.trim()
            ),
        },
    }
}

/// Set (or, with `None`, clear) the manual install location.
///
/// Clearing hands the job back to detection rather than leaving the launcher
/// with nothing, so there is always a way out of a bad path.
#[tauri::command]
fn set_install_path(path: Option<String>) -> Result<InstallStatus, String> {
    let resolved = match path.as_deref().map(str::trim).filter(|p| !p.is_empty()) {
        Some(p) => {
            let root = resolve_install_root(p).ok_or_else(|| check_install_path(p.to_string()).message)?;
            Some(root.to_string_lossy().to_string())
        }
        None => None,
    };

    let mut settings = get_settings();
    settings.install_path = resolved;
    save_settings(settings)?;
    Ok(get_install_status())
}

#[tauri::command]
fn launch_game() -> Result<(), String> {
    let settings = get_settings();

    // Put back any hub container deleted from Paks by hand, and rebuild the
    // map registration (a game update replaces the tables it was built
    // from). A failure costs those mods, not the launch, so it is reported
    // and the game starts anyway.
    if let Err(e) = hub::prepare_launch() {
        eprintln!("hub mods: {e}");
    }

    // Applied on every launch as well as on toggle: a reinstall, or a hand
    // edit, can leave the file saying otherwise. A failure costs the console
    // choice or the scan-time floor, not the launch, so the game starts anyway.
    if let Err(e) = apply_ue4ss_settings(&settings) {
        eprintln!("ue4ss settings: {e}");
    }

    match settings.launch_method.as_str() {
        "exe" => {
            if let Some(exe_path) = &settings.custom_exe_path {
                let exe = PathBuf::from(exe_path);
                if exe.exists() {
                    let working_dir = exe.parent().unwrap_or(&exe);
                    std::process::Command::new(&exe)
                        .current_dir(working_dir)
                        .spawn()
                        .map_err(|e| format!("Failed to launch {}: {}", exe.display(), e))?;
                    return Ok(());
                } else {
                    return Err(format!("Executable not found: {}", exe_path));
                }
            }


            if let Some((install_path, _)) = find_game_install() {
                let bin_dir = binaries_dir(&install_path);
                let candidates = vec![
                    bin_dir.join(GAME_EXE),
                    bin_dir.join("Meteorite-Win64-Shipping.exe"),
                    bin_dir.join("Meteorite-WinGDK-Shipping.exe"),
                    bin_dir.join("Meteorite.exe"),
                    install_path.join("Meteorite.exe"),
                    install_path.join("HaloCE.exe"),
                ];

                for exe in &candidates {
                    if exe.exists() {
                        let working_dir = exe.parent().unwrap_or(&install_path);
                        std::process::Command::new(exe)
                            .current_dir(working_dir)
                            .spawn()
                            .map_err(|e| format!("Failed to launch {}: {}", exe.display(), e))?;
                        return Ok(());
                    }
                }
            }

            Err("No game executable found. Please set the EXE path in Settings.".to_string())
        }
        "gamepass" => {
            // Launch via Xbox Game Pass using the Store product ID: 9N683TDT5M7R
            // Try shell:AppsFolder first (requires knowing the AUMID), fall back to store launch
            // The most reliable method is `start ms-xbl-{productId}://` or the store deep-link
            std::process::Command::new("cmd")
                .args(["/C", "start", "", "ms-xbl-9N683TDT5M7R://"])
                .spawn()
                .or_else(|_| {
                    // Fallback: open the store page which has a launch button
                    std::process::Command::new("cmd")
                        .args(["/C", "start", "", "ms-windows-store://pdp/?productId=9N683TDT5M7R"])
                        .spawn()
                })
                .map_err(|e| format!("Failed to launch via Game Pass: {}. Try using the direct EXE method instead.", e))?;
            Ok(())
        }
        _ => {
            // Default: launch via Steam
            std::process::Command::new("cmd")
                .args(["/C", "start", "", "steam://rungameid/2806050"])
                .spawn()
                .map_err(|e| format!("Failed to launch via Steam: {}", e))?;
            Ok(())
        }
    }
}

// ─── Joining a listed game (mjolnir://join links) ───────────────────────

/// The image names a running game shows under: the store launcher's exe and
/// the shipping builds `launch_game` falls back to, plus the player's own
/// EXE when one is set. Not `HaloCE.exe`, which `launch_game` also tries: a
/// classic Halo CE running is not this game.
fn game_image_names(settings: &LauncherSettings) -> Vec<String> {
    let mut names: Vec<String> = [
        GAME_EXE,
        "Meteorite-Win64-Shipping.exe",
        "Meteorite-WinGDK-Shipping.exe",
        "Meteorite.exe",
    ]
    .iter()
    .map(|n| n.to_string())
    .collect();
    if let Some(name) = settings
        .custom_exe_path
        .as_deref()
        .and_then(|p| Path::new(p).file_name())
    {
        names.push(name.to_string_lossy().into_owned());
    }
    names
}

/// Whether `tasklist /FO CSV /NH` output lists any of these image names.
/// Its first column is the quoted image name; the rest is ignored.
fn tasklist_lists(output: &str, names: &[String]) -> bool {
    output.lines().any(|line| {
        let image = line.trim().trim_start_matches('"');
        let image = image.split('"').next().unwrap_or_default();
        names.iter().any(|n| n.eq_ignore_ascii_case(image))
    })
}

/// Whether the game is running, from one `tasklist` (hidden: no console
/// flashes up over the launcher). False when it cannot tell, which starts
/// the game: a second start of a running Steam game only focuses it.
fn game_running() -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let Ok(out) = std::process::Command::new("tasklist")
            .args(["/FO", "CSV", "/NH"])
            .creation_flags(CREATE_NO_WINDOW)
            .output()
        else {
            return false;
        };
        tasklist_lists(
            &String::from_utf8_lossy(&out.stdout),
            &game_image_names(&get_settings()),
        )
    }
    #[cfg(not(windows))]
    {
        false
    }
}

/// What `hub_join_lobby` did: started the game (`launched`), or left the
/// join for the game already running, which picks it up at its main menu.
#[derive(Debug, Serialize)]
pub struct JoinStart {
    pub launched: bool,
}

/// Join a listed game: leave the lobby id for MJOLNIRLobby
/// (`native\pending_join.txt`, docs/live_map_install.md "Joining from a
/// link"), and start the game if it is not running. The game does the rest
/// once the player is signed in at the main menu: it finds the lobby in
/// FIND GAMES and joins it, downloading the map first when it has to.
///
/// An error starting `not_ready:` means multiplayer is not installed
/// (`hub::multiplayer_ready`); the webview offers Install multiplayer.
#[tauri::command]
async fn hub_join_lobby(lobby: String) -> Result<JoinStart, String> {
    tauri::async_runtime::spawn_blocking(move || {
        if !links::valid_lobby(&lobby) {
            return Err(format!("{lobby:?} is not a lobby id"));
        }
        let lobby_dir = hub::multiplayer_ready().map_err(|e| format!("not_ready:{e}"))?;
        hub::write_pending_join(&lobby_dir, &lobby)?;
        if game_running() {
            return Ok(JoinStart { launched: false });
        }
        launch_game()?;
        Ok(JoinStart { launched: true })
    })
    .await
    .map_err(|e| format!("Task join error: {e}"))?
}

// ─── New commands: Install lifecycle ────────────────────────────────────

#[tauri::command]
fn get_install_status() -> InstallStatus {
    let manifest = load_cached_manifest();
    let manual = manual_install();
    let manual_path = manual.as_ref().map(|(p, _)| p.clone());

    match find_game_install() {
        Some((install_path, platform)) => {
            let bin_dir = binaries_dir(&install_path);
            let ue4ss_dir = bin_dir.join("ue4ss");
            let (dll_installed, dll_enabled) = check_ue4ss_dll(&bin_dir);

            let ue4ss_installed = dll_installed
                && ue4ss_dir.exists()
                && ue4ss_dir.join("UE4SS-settings.ini").exists();

            InstallStatus {
                game_found: true,
                install_path: Some(install_path.to_string_lossy().to_string()),
                binaries_path: Some(bin_dir.to_string_lossy().to_string()),
                platform,
                ue4ss_installed,
                modpack_enabled: dll_enabled,
                manifest_version: manifest.as_ref().map(|m| m.version.clone()),
                ue4ss_version: manifest.as_ref().map(|m| m.ue4ss_version.clone()),
                source: manual
                    .map(|(_, src)| src.to_string())
                    .unwrap_or_else(|| install_source::AUTO.to_string()),
                manual_path,
            }
        }
        None => InstallStatus {
            game_found: false,
            install_path: None,
            binaries_path: None,
            platform: "unknown".to_string(),
            ue4ss_installed: false,
            modpack_enabled: false,
            manifest_version: None,
            ue4ss_version: None,
            // A set-but-unresolvable location is still the reason nothing was
            // found, so it is reported as the source rather than as "none".
            source: manual
                .map(|(_, src)| src.to_string())
                .unwrap_or_else(|| install_source::NONE.to_string()),
            manual_path,
        },
    }
}

/// What the modpack row of the update manager needs: the version installed
/// here against the version the release bucket is publishing.
#[derive(Debug, Serialize)]
pub struct ModpackUpdate {
    pub installed_version: Option<String>,
    pub latest_version: String,
    pub latest_ue4ss_version: String,
    pub update_available: bool,
    pub file_count: usize,
}

/// Ask the release bucket what the current modpack is.
///
/// `get_install_status` only ever reports the cached manifest, which answers
/// "what is installed" and cannot answer "is it current" — so this is the
/// one call that reaches the network, and the update manager owns it.
#[tauri::command]
async fn check_modpack_update() -> Result<ModpackUpdate, String> {
    tauri::async_runtime::spawn_blocking(|| {
        let installed = load_cached_manifest();
        let client = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(30))
            .build()
            .map_err(|e| format!("HTTP client error: {e}"))?;
        let resp = client
            .get(MANIFEST_URL)
            .send()
            .map_err(|e| format!("Cannot reach the release server: {e}"))?;
        if !resp.status().is_success() {
            return Err(format!("Manifest request returned {}", resp.status()));
        }
        let latest: ModpackManifest = resp
            .json()
            .map_err(|e| format!("Cannot read the manifest: {e}"))?;

        let installed_version = installed.as_ref().map(|m| m.version.clone());
        // Any difference counts, not just "newer": the modpack is published
        // as a whole and a mismatch means the install is not what ships.
        let update_available = installed_version
            .as_deref()
            .is_none_or(|v| v != latest.version);

        Ok(ModpackUpdate {
            installed_version,
            latest_version: latest.version,
            latest_ue4ss_version: latest.ue4ss_version,
            update_available,
            file_count: latest.files.len(),
        })
    })
    .await
    .map_err(|e| format!("Task join error: {e}"))?
}

#[tauri::command]
fn verify_install() -> Result<VerifyResult, String> {
    let bin_dir = get_bin_dir().ok_or("Game not found")?;
    let manifest = load_cached_manifest().ok_or(
        "No manifest found. Install the modpack first, or reinstall to generate a manifest.",
    )?;

    let mut checked = 0usize;
    let mut passed = 0usize;
    let mut failed = Vec::new();
    let mut missing = Vec::new();

    for entry in &manifest.files {
        // Config files are the player's, not ours. They are expected to
        // diverge from the manifest, so counting them as failures would
        // report a broken install to anyone who changed a setting.
        if entry.config {
            continue;
        }

        let file_path = bin_dir.join(&entry.path);
        checked += 1;

        if !file_path.exists() {
            missing.push(entry.path.clone());
            continue;
        }

        match sha256_file(&file_path) {
            Ok(hash) => {
                if hash == entry.sha256 {
                    passed += 1;
                } else {
                    failed.push(entry.path.clone());
                }
            }
            Err(_) => {
                failed.push(format!("{} (read error)", entry.path));
            }
        }
    }

    Ok(VerifyResult {
        checked,
        passed,
        failed,
        missing,
    })
}

// The installers below take an optional `task`: the Updates screen names
// each run so the bytes it moves land on the right row (see transfer.rs).

#[tauri::command]
async fn install_modpack(app: AppHandle, task: Option<String>) -> Result<(), String> {
    // Run the blocking download/extract/verify on a background thread
    let result = tauri::async_runtime::spawn_blocking(move || {
        transfer::scoped(&app, task, || install_modpack_blocking(&app))
    })
    .await
    .map_err(|e| format!("Task join error: {}", e))?;

    result
}

// ─── Companion tools ────────────────────────────────────────────────────

/// Every tool the launcher can install, with installed and available versions.
///
/// This reaches the network, so it runs off the UI thread like the modpack
/// installer does.
#[tauri::command]
async fn get_tools() -> Result<Vec<tools::ToolStatus>, String> {
    tauri::async_runtime::spawn_blocking(tools::list)
        .await
        .map_err(|e| format!("Task join error: {e}"))
}

#[tauri::command]
async fn install_tool(app: AppHandle, id: String, task: Option<String>) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        transfer::scoped(&app, task, || tools::install(&app, &id))
    })
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

#[tauri::command]
fn launch_tool(id: String) -> Result<(), String> {
    tools::launch(&id)
}

#[tauri::command]
fn uninstall_tool(id: String) -> Result<(), String> {
    tools::uninstall(&id)
}

// ─── Hub: content mods, profiles, signed code mods ─────────────────────
// All of these reach the network or walk the Paks directory, so they run
// off the UI thread like the other installers.

/// The one door the webview has onto the hub API.
///
/// Everything the Browse view reads — listings, mod pages, ratings,
/// comments, conflicts — comes through here, so the paired API key stays in
/// this process and the page never holds a credential.
#[tauri::command]
async fn hub_api(
    method: String,
    path: String,
    body: Option<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(move || hub::api(method, path, body))
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

#[tauri::command]
async fn hub_install(
    app: AppHandle,
    slug: String,
    release_id: Option<String>,
    task: Option<String>,
) -> Result<hub::HubState, String> {
    tauri::async_runtime::spawn_blocking(move || {
        transfer::scoped(&app, task, || hub::install(slug, release_id))
    })
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

/// Every official map, the CE runtime pack and the multiplayer mods, with
/// progress on the same `install-progress` event the runtime install uses
/// (stage `multiplayer`).
#[tauri::command]
async fn hub_install_multiplayer(app: AppHandle) -> Result<hub::MultiplayerInstall, String> {
    tauri::async_runtime::spawn_blocking(move || {
        hub::install_multiplayer(&|message, fraction| {
            emit_progress(&app, "multiplayer", message, fraction * 100.0)
        })
    })
    .await
    .map_err(|e| format!("Task join error: {e}"))?
}

#[tauri::command]
async fn hub_check_updates() -> Result<Vec<hub::UpdateInfo>, String> {
    tauri::async_runtime::spawn_blocking(hub::check_updates)
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

#[tauri::command]
async fn hub_verify_installed() -> Result<Vec<hub::VerifiedMod>, String> {
    tauri::async_runtime::spawn_blocking(hub::verify_installed)
        .await
        .map_err(|e| format!("Task join error: {e}"))
}

#[tauri::command]
fn hub_auth_status() -> Option<hub::HubUser> {
    hub::auth_status()
}

#[tauri::command]
async fn hub_session_check() -> Result<hub::HubSession, String> {
    tauri::async_runtime::spawn_blocking(hub::session_check)
        .await
        .map_err(|e| format!("Task join error: {e}"))
}

#[tauri::command]
async fn hub_auth_start() -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(hub::auth_start)
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

#[tauri::command]
async fn hub_auth_poll() -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(hub::auth_poll)
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

#[tauri::command]
fn hub_sign_out() -> Result<(), String> {
    hub::sign_out()
}

#[tauri::command]
async fn hub_uninstall(slug: String) -> Result<hub::HubState, String> {
    tauri::async_runtime::spawn_blocking(move || hub::uninstall(slug))
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

/// Installed hub mods whose files are gone from the cache or from Paks.
#[tauri::command]
async fn hub_missing_files() -> Result<Vec<String>, String> {
    tauri::async_runtime::spawn_blocking(hub::missing_files)
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

#[tauri::command]
fn hub_state() -> hub::HubState {
    hub::get_state()
}

#[tauri::command]
async fn hub_set_order(slug: String, index: usize) -> Result<hub::HubState, String> {
    tauri::async_runtime::spawn_blocking(move || hub::set_order(slug, index))
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

#[tauri::command]
async fn hub_set_enabled(slug: String, enabled: bool) -> Result<hub::HubState, String> {
    tauri::async_runtime::spawn_blocking(move || hub::set_enabled(slug, enabled))
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

#[tauri::command]
async fn hub_profile_create(name: String, copy_active: bool) -> Result<hub::HubState, String> {
    tauri::async_runtime::spawn_blocking(move || hub::profile_create(name, copy_active))
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

#[tauri::command]
async fn hub_profile_switch(name: String) -> Result<hub::HubState, String> {
    tauri::async_runtime::spawn_blocking(move || hub::profile_switch(name))
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

#[tauri::command]
async fn hub_profile_delete(name: String) -> Result<hub::HubState, String> {
    tauri::async_runtime::spawn_blocking(move || hub::profile_delete(name))
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

#[tauri::command]
async fn hub_check_conflicts() -> Result<serde_json::Value, String> {
    tauri::async_runtime::spawn_blocking(hub::check_conflicts)
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

#[tauri::command]
async fn code_mods_status() -> Result<hub::CodeModsStatus, String> {
    tauri::async_runtime::spawn_blocking(hub::code_mods_status)
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

#[tauri::command]
async fn code_mods_install(
    app: AppHandle,
    id: String,
    task: Option<String>,
) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || {
        transfer::scoped(&app, task, || hub::code_mods_install(id))
    })
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

/// Install the set's default mods. Exposed on its own as well as being part of
/// setup, so a player who cleared them out can get back to a working baseline
/// without hunting down which mods that meant.
#[tauri::command]
async fn code_mods_install_defaults() -> Result<Vec<String>, String> {
    tauri::async_runtime::spawn_blocking(hub::code_mods_install_defaults)
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

fn emit_progress(app: &AppHandle, stage: &str, message: &str, percent: f32) {
    let _ = app.emit(
        "install-progress",
        InstallProgress {
            stage: stage.to_string(),
            message: message.to_string(),
            percent,
        },
    );
}

fn install_modpack_blocking(app: &AppHandle) -> Result<(), String> {
    let bin_dir = get_bin_dir().ok_or(
        "Game not found. Install Halo Campaign Evolved (Steam or the Xbox app) first, or set \
         its folder in Settings.",
    )?;

    // Ensure bin dir exists
    if !bin_dir.exists() {
        return Err(format!(
            "Game binaries directory not found: {}. Expected a Win64 (Steam) or WinGDK \
             (Xbox app) folder under Meteorite\\Binaries. Launch the game once so the \
             store finishes installing it, then try again.",
            bin_dir.display()
        ));
    }

    // 1. Download manifest and check its signature before trusting a byte of
    //    it. The manifest names the hashes everything else is checked against,
    //    so an unsigned one can authorise whatever it likes.
    emit_progress(app, "downloading", "Fetching runtime manifest...", 0.0);

    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .map_err(|e| format!("HTTP client error: {}", e))?;

    let manifest_resp = client
        .get(MANIFEST_URL)
        .send()
        .map_err(|e| format!("Failed to fetch manifest: {}", e))?;

    if !manifest_resp.status().is_success() {
        return Err(format!(
            "Manifest download failed with status: {}",
            manifest_resp.status()
        ));
    }

    let manifest_bytes = manifest_resp
        .bytes()
        .map_err(|e| format!("Failed to read manifest: {}", e))?;

    emit_progress(app, "downloading", "Verifying manifest signature...", 3.0);
    let sig_resp = client
        .get(format!("{RUNTIME_BASE}/manifest.json.sig"))
        .send()
        .map_err(|e| format!("Failed to fetch manifest signature: {}", e))?;
    if !sig_resp.status().is_success() {
        return Err(format!(
            "The runtime manifest has no signature ({}). Refusing to install: \
             this bundle injects a DLL into the game process.",
            sig_resp.status()
        ));
    }
    let sig_b64 = sig_resp
        .text()
        .map_err(|e| format!("Failed to read manifest signature: {}", e))?;

    if !hub::verify_signature(&manifest_bytes, &sig_b64)? {
        return Err(
            "The runtime manifest signature does not verify against this launcher's key. \
             Refusing to install anything from it."
                .into(),
        );
    }

    let manifest: ModpackManifest = serde_json::from_slice(&manifest_bytes)
        .map_err(|e| format!("Failed to parse manifest: {}", e))?;

    // 2. Download the runtime bundle
    emit_progress(app, "downloading", "Downloading runtime...", 5.0);

    let zip_resp = client
        .get(RUNTIME_ZIP_URL)
        .send()
        .map_err(|e| format!("Failed to download runtime: {}", e))?;

    if !zip_resp.status().is_success() {
        return Err(format!(
            "Runtime download failed with status: {}",
            zip_resp.status()
        ));
    }

    let total_size = zip_resp.content_length().unwrap_or(0);
    let zip_bytes = transfer::read_body(zip_resp, (total_size > 0).then_some(total_size), |downloaded| {
        if total_size > 0 {
            let pct = 5.0 + (downloaded as f32 / total_size as f32) * 55.0;
            emit_progress(
                app,
                "downloading",
                &format!(
                    "Downloading... {:.1} MB / {:.1} MB",
                    downloaded as f64 / 1_048_576.0,
                    total_size as f64 / 1_048_576.0
                ),
                pct,
            );
        }
    })
    .map_err(|e| format!("Download read error: {}", e))?;

    emit_progress(app, "downloading", "Download complete.", 60.0);

    // 3. Extract zip
    emit_progress(app, "extracting", "Extracting runtime...", 62.0);

    // Files the manifest marks as config are seed state: write them when they
    // are absent, never over the top of what is already there. Reinstalling
    // used to replace UE4SS-settings.ini and mods.txt unconditionally, which
    // discarded engine-version overrides, crash workarounds and the player's
    // entire mod list.
    let config_paths: std::collections::HashSet<&str> = manifest
        .files
        .iter()
        .filter(|f| f.config)
        .map(|f| f.path.as_str())
        .collect();
    let mut preserved: Vec<String> = Vec::new();

    let cursor = io::Cursor::new(&zip_bytes);
    let mut archive =
        zip::ZipArchive::new(cursor).map_err(|e| format!("Failed to open zip: {}", e))?;

    let total_entries = archive.len();
    for i in 0..total_entries {
        let mut file = archive
            .by_index(i)
            .map_err(|e| format!("Zip entry error: {}", e))?;

        let name = file.name().to_string();

        // Skip directories and __MACOSX etc.
        if name.ends_with('/') || name.starts_with("__MACOSX") {
            continue;
        }

        // A zip entry decides where it lands, so refuse any that climbs out
        // of the install directory.
        if name.contains("..") {
            return Err(format!("Refusing to extract a path with '..': {name}"));
        }

        let out_path = bin_dir.join(&name);

        if config_paths.contains(name.as_str()) && out_path.exists() {
            preserved.push(name.clone());
            continue;
        }

        // Create parent dirs
        if let Some(parent) = out_path.parent() {
            fs::create_dir_all(parent)
                .map_err(|e| format!("Failed to create directory {}: {}", parent.display(), e))?;
        }

        let mut out_file = fs::File::create(&out_path)
            .map_err(|e| format!("Failed to create {}: {}", out_path.display(), e))?;

        let copied = io::copy(&mut file, &mut out_file)
            .map_err(|e| format!("Failed to write {}: {}", out_path.display(), e))?;
        transfer::wrote(copied);

        let pct = 62.0 + (i as f32 / total_entries as f32) * 25.0;
        emit_progress(
            app,
            "extracting",
            &format!("Extracting: {}", name),
            pct,
        );
    }

    emit_progress(app, "extracting", "Extraction complete.", 87.0);

    // 4. Verify checksums
    emit_progress(app, "verifying", "Verifying file integrity...", 88.0);

    let total_files = manifest.files.len();
    let mut verify_failed = Vec::new();

    for (i, entry) in manifest.files.iter().enumerate() {
        let file_path = bin_dir.join(&entry.path);

        // A preserved config file is *expected* not to match the manifest —
        // that is the point of preserving it. Checking it would report a
        // corrupt install every time someone edited their settings.
        if entry.config && preserved.iter().any(|p| p == &entry.path) {
            continue;
        }

        if file_path.exists() {
            if let Ok(hash) = sha256_file(&file_path) {
                if hash != entry.sha256 {
                    verify_failed.push(entry.path.clone());
                }
            } else {
                verify_failed.push(format!("{} (read error)", entry.path));
            }
        } else {
            verify_failed.push(format!("{} (missing)", entry.path));
        }

        let pct = 88.0 + (i as f32 / total_files as f32) * 10.0;
        emit_progress(
            app,
            "verifying",
            &format!("Checking: {}", entry.path),
            pct,
        );
    }

    // 5. Save manifest
    save_cached_manifest(&manifest)?;

    // 6. The default mods from the signed set.
    //
    //    The runtime bundle ships no MJOLNIR mods on purpose — CI asserts it —
    //    so up to here setup produces a loader with nothing to load, while the
    //    setup panel lists mods as part of what it installs. Installing the
    //    set's defaults is what makes that list true.
    //
    //    A failure here does not fail the install. UE4SS is down and every one
    //    of these is a click away in My Mods, so an unreachable release server
    //    is worth a sentence, not a rolled-back setup.
    emit_progress(app, "extracting", "Installing default mods...", 98.0);
    let mods_note = match hub::code_mods_install_defaults() {
        Ok(ids) if ids.is_empty() => String::new(),
        Ok(ids) => format!(" Installed {}.", ids.join(", ")),
        Err(e) => {
            eprintln!("Default mods were not installed: {e}");
            " Default mods could not be installed — add them from My Mods.".to_string()
        }
    };

    if verify_failed.is_empty() {
        let note = match preserved.len() {
            0 => "Installation complete! All files verified.".to_string(),
            1 => format!("Installation complete. Kept your {}.", preserved[0]),
            n => format!("Installation complete. Kept your {n} existing config files."),
        };
        emit_progress(app, "done", &format!("{note}{mods_note}"), 100.0);
        Ok(())
    } else {
        emit_progress(
            app,
            "done",
            &format!(
                "Installation complete with {} verification warning(s).{mods_note}",
                verify_failed.len()
            ),
            100.0,
        );
        // Still succeed — files were extracted, just some checksums didn't match
        Ok(())
    }
}

#[tauri::command]
fn set_modpack_enabled(enabled: bool) -> Result<bool, String> {
    let bin_dir = get_bin_dir().ok_or("Game not found")?;
    let active = bin_dir.join("dwmapi.dll");
    let disabled = bin_dir.join("dwmapi.dll.disabled");

    if enabled {
        // Rename .disabled -> active
        if disabled.exists() {
            fs::rename(&disabled, &active)
                .map_err(|e| format!("Failed to enable modpack: {}", e))?;
        } else if !active.exists() {
            return Err("dwmapi.dll not found. Try reinstalling the modpack.".to_string());
        }
    } else {
        // Rename active -> .disabled
        if active.exists() {
            fs::rename(&active, &disabled)
                .map_err(|e| format!("Failed to disable modpack: {}", e))?;
        } else if !disabled.exists() {
            return Err("dwmapi.dll not found. Try reinstalling the modpack.".to_string());
        }
    }

    Ok(enabled)
}

#[tauri::command]
fn uninstall_modpack() -> Result<(), String> {
    let bin_dir = get_bin_dir().ok_or("Game not found")?;

    // Remove dwmapi.dll (or .disabled variant)
    let active = bin_dir.join("dwmapi.dll");
    let disabled = bin_dir.join("dwmapi.dll.disabled");

    if active.exists() {
        fs::remove_file(&active).map_err(|e| format!("Failed to remove dwmapi.dll: {}", e))?;
    }
    if disabled.exists() {
        fs::remove_file(&disabled)
            .map_err(|e| format!("Failed to remove dwmapi.dll.disabled: {}", e))?;
    }

    // The map registration this launcher built lists maps whose data lives
    // in ue4ss; take it with them.
    if let Some((install, _)) = find_game_install() {
        maps::forget(&install.join("Meteorite/Content/Paks"));
    }

    // Remove ue4ss directory
    let ue4ss_dir = bin_dir.join("ue4ss");
    if ue4ss_dir.exists() {
        fs::remove_dir_all(&ue4ss_dir)
            .map_err(|e| format!("Failed to remove ue4ss directory: {}", e))?;
    }

    // Remove cached manifest
    let manifest_path = cached_manifest_path();
    if manifest_path.exists() {
        let _ = fs::remove_file(&manifest_path);
    }

    Ok(())
}

// ─── Tauri entrypoint ───────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // A running game asking for a map (hub::run_live_install): no window.
    //
    // Handled here, before the builder, on purpose: the single-instance
    // plugin below hands a second launcher's arguments to the open one and
    // exits it, and the game spawns this while a launcher window may well be
    // open. Kept ahead of every plugin, it never reaches that check.
    let args: Vec<String> = std::env::args().collect();
    if let Some(i) = args.iter().position(|a| a == "--install-map") {
        let code = args.get(i + 1).cloned().unwrap_or_default();
        let progress = args
            .iter()
            .position(|a| a == "--progress")
            .and_then(|j| args.get(j + 1))
            .map(PathBuf::from);
        let Some(progress) = progress else {
            std::process::exit(2);
        };
        let release = args
            .iter()
            .position(|a| a == "--release")
            .and_then(|j| args.get(j + 1))
            .cloned();
        std::process::exit(hub::run_live_install(&code, release.as_deref(), &progress));
    }
    hub::record_exe_path();
    tauri::Builder::default()
        // First, as the deep-link plugin requires: a second launcher (a
        // mjolnir:// link clicked while this one is open, or a second click
        // on the shortcut) gives its arguments to this one and exits. With
        // the `deep-link` feature the plugin passes a link on to the
        // deep-link plugin, whose listener (setup, below) delivers it.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            links::focus_main(app)
        }))
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_dialog::init())
        .manage(links::Pending::default())
        .setup(|app| {
            // Also on every launch (launch_game), but many players start the
            // game from Steam: opening the launcher is enough to fix their
            // file.
            if let Err(e) = apply_ue4ss_settings(&get_settings()) {
                eprintln!("ue4ss settings: {e}");
            }

            // mjolnir:// links. The installer registers the scheme; this
            // registers it for a dev build and for installs from before it
            // (HKCU, so no elevation), and points it back at this exe when
            // it has moved.
            use tauri_plugin_deep_link::DeepLinkExt;
            let deep_link = app.deep_link();
            #[cfg(windows)]
            if !deep_link.is_registered(links::SCHEME).unwrap_or(false) {
                if let Err(e) = deep_link.register(links::SCHEME) {
                    eprintln!("links: registering {}://: {e}", links::SCHEME);
                }
            }
            let handle = app.handle().clone();
            deep_link.on_open_url(move |event| {
                for url in event.urls() {
                    links::deliver(&handle, url.as_str());
                }
            });
            // The link this launcher was started with: read by the plugin
            // before anything listened.
            if let Ok(Some(urls)) = deep_link.get_current() {
                for url in urls {
                    links::deliver(app.handle(), url.as_str());
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            detect_game,
            get_mods,
            toggle_mod,
            launch_game,
            get_settings,
            save_settings,
            set_ue4ss_console,
            get_build_info,
            get_install_status,
            check_install_path,
            set_install_path,
            check_modpack_update,
            verify_install,
            install_modpack,
            set_modpack_enabled,
            uninstall_modpack,
            get_tools,
            install_tool,
            launch_tool,
            uninstall_tool,
            hub_api,
            hub_install,
            hub_install_multiplayer,
            hub_join_lobby,
            links::take_pending_link,
            hub_uninstall,
            hub_state,
            hub_set_order,
            hub_set_enabled,
            hub_profile_create,
            hub_profile_switch,
            hub_profile_delete,
            hub_check_conflicts,
            hub_check_updates,
            hub_verify_installed,
            hub_missing_files,
            hub_auth_status,
            hub_auth_start,
            hub_auth_poll,
            hub_session_check,
            hub_sign_out,
            code_mods_status,
            code_mods_install,
            code_mods_install_defaults,
            changelog::fetch_changelog,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_running_game_is_found_in_tasklist_output() {
        let settings = LauncherSettings {
            custom_exe_path: Some(r"D:\Games\HCE\MyBuild.exe".into()),
            ..LauncherSettings::default()
        };
        let names = game_image_names(&settings);
        let listing = "\"System Idle Process\",\"0\",\"Services\",\"0\",\"8 K\"\r\n\
                       \"steam.exe\",\"4120\",\"Console\",\"1\",\"212,404 K\"\r\n";
        assert!(!tasklist_lists(listing, &names));
        let running = format!("{listing}\"HaloCampaignEvolved.exe\",\"9000\",\"Console\",\"1\",\"8,123,456 K\"\r\n");
        assert!(tasklist_lists(&running, &names));
        assert!(tasklist_lists("\"meteorite-win64-shipping.EXE\",\"1\"", &names));
        assert!(tasklist_lists("\"MyBuild.exe\",\"1\"", &names));
        // Classic Halo CE is not this game.
        assert!(!tasklist_lists("\"HaloCE.exe\",\"1\"", &names));
    }

    /// The old modpack manifest has no `config` key. Reading one must not
    /// start preserving arbitrary files — every entry is content, which is
    /// exactly how that manifest behaved when it was published.
    #[test]
    fn a_manifest_without_config_flags_reads_as_all_content() {
        let json = r#"{
            "version": "1.0.0",
            "ue4ss_version": "3.0.1",
            "files": [
                {"path": "dwmapi.dll", "sha256": "ab", "size": 71680},
                {"path": "ue4ss/UE4SS-settings.ini", "sha256": "cd", "size": 275}
            ]
        }"#;
        let m: ModpackManifest = serde_json::from_str(json).expect("legacy manifest must parse");
        assert_eq!(m.files.len(), 2);
        assert!(
            m.files.iter().all(|f| !f.config),
            "an absent flag must default to content, not to preserved"
        );
    }

    #[test]
    fn the_runtime_manifest_marks_seed_state_and_nothing_else() {
        let json = r#"{
            "schema_version": 1,
            "version": "1.0.0",
            "ue4ss_version": "3.0.1-1018-g662df915",
            "files": [
                {"path": "ue4ss/UE4SS.dll", "sha256": "ab", "size": 16519168, "config": false},
                {"path": "ue4ss/UE4SS-settings.ini", "sha256": "cd", "size": 7640, "config": true},
                {"path": "ue4ss/Mods/mods.txt", "sha256": "ef", "size": 96, "config": true}
            ]
        }"#;
        let m: ModpackManifest = serde_json::from_str(json).expect("runtime manifest must parse");
        let preserved: Vec<&str> = m
            .files
            .iter()
            .filter(|f| f.config)
            .map(|f| f.path.as_str())
            .collect();
        assert_eq!(
            preserved,
            ["ue4ss/UE4SS-settings.ini", "ue4ss/Mods/mods.txt"],
            "only the player's settings and mod list are preserved"
        );
        // schema_version is additive; an older launcher must ignore it rather
        // than fail to read the manifest at all.
        assert_eq!(m.ue4ss_version, "3.0.1-1018-g662df915");
    }

    /// A settings file written before the manual location existed must still
    /// read, and must read as "detect it".
    #[test]
    fn settings_without_an_install_path_still_read() {
        let json = r#"{"launch_method":"steam","custom_exe_path":null}"#;
        let s: LauncherSettings = serde_json::from_str(json).expect("old settings must parse");
        assert_eq!(s.install_path, None);
        assert!(!s.show_ue4ss_console, "an old settings file must read as console hidden");
    }

    #[test]
    fn the_console_toggle_edits_only_its_own_key() {
        let ini = "[Overrides]\nModsFolderPath =\n\n[Debug]\n; Whether to enable the external UE4SS debug console.\nConsoleEnabled = 1\nGuiConsoleEnabled = 1\n\n[Threads]\nSigScannerNumThreads = 8\n";
        let hidden = with_console_enabled(ini, false);
        assert_eq!(hidden, ini.replace("ConsoleEnabled = 1\nGui", "ConsoleEnabled = 0\nGui"));
        assert_eq!(with_console_enabled(&hidden, true), ini);
        // A key of the same name in another section is not the console.
        let elsewhere = "[Other]\nConsoleEnabled = 1\n[Debug]\nConsoleEnabled = 1\n";
        assert_eq!(
            with_console_enabled(elsewhere, false),
            "[Other]\nConsoleEnabled = 1\n[Debug]\nConsoleEnabled = 0\n"
        );
    }

    #[test]
    fn the_console_toggle_keeps_crlf_line_endings() {
        let ini = "[Debug]\r\nConsoleEnabled = 1\r\nGuiConsoleVisible = 0\r\n";
        assert_eq!(
            with_console_enabled(ini, false),
            "[Debug]\r\nConsoleEnabled = 0\r\nGuiConsoleVisible = 0\r\n"
        );
    }

    /// A settings file trimmed by hand may have lost the key, or the whole
    /// section; UE4SS's own default then decides, so the key is added.
    #[test]
    fn the_console_toggle_adds_a_missing_key() {
        assert_eq!(
            with_console_enabled("[Debug]\nGuiConsoleVisible = 0\n\n[Threads]\n", false),
            "[Debug]\nGuiConsoleVisible = 0\n\nConsoleEnabled = 0\n[Threads]\n"
        );
        assert_eq!(
            with_console_enabled("[Debug]\nGuiConsoleVisible = 0", false),
            "[Debug]\nGuiConsoleVisible = 0\nConsoleEnabled = 0\n"
        );
        assert_eq!(
            with_console_enabled("[Threads]\nSigScannerNumThreads = 8\n", true),
            "[Threads]\nSigScannerNumThreads = 8\n[Debug]\nConsoleEnabled = 1\n"
        );
    }

    /// UE4SS's stock 30 s lost the startup race on a playtester's PC, and
    /// the launcher keeps an existing settings file as it is, so the floor
    /// is raised in place.
    #[test]
    fn a_short_scan_timeout_is_raised_to_the_floor() {
        let stock = "[General]\r\n; Default: 30\r\nSecondsToScanBeforeGivingUp = 30\r\nUseCache = 1\r\n\r\n[Debug]\r\nConsoleEnabled = 0\r\n";
        assert_eq!(
            with_scan_time_floor(stock),
            stock.replace("GivingUp = 30", "GivingUp = 120")
        );
        // Our own bundled 60 is short too.
        assert_eq!(
            with_scan_time_floor("[General]\nSecondsToScanBeforeGivingUp = 60\n"),
            "[General]\nSecondsToScanBeforeGivingUp = 120\n"
        );
    }

    #[test]
    fn a_longer_scan_timeout_is_kept() {
        let ini = "[General]\nSecondsToScanBeforeGivingUp=300\n";
        assert_eq!(with_scan_time_floor(ini), ini);
        assert_eq!(with_scan_time_floor(&with_scan_time_floor("[General]\n")), "[General]\nSecondsToScanBeforeGivingUp = 120\n");
    }

    #[test]
    fn a_missing_or_unreadable_scan_timeout_gets_the_floor() {
        assert_eq!(
            with_scan_time_floor("[General]\nUseCache = 1\n\n[Debug]\nConsoleEnabled = 0\n"),
            "[General]\nUseCache = 1\n\nSecondsToScanBeforeGivingUp = 120\n[Debug]\nConsoleEnabled = 0\n"
        );
        assert_eq!(
            with_scan_time_floor("[Debug]\nConsoleEnabled = 0\n"),
            "[Debug]\nConsoleEnabled = 0\n[General]\nSecondsToScanBeforeGivingUp = 120\n"
        );
        assert_eq!(
            with_scan_time_floor("[General]\nSecondsToScanBeforeGivingUp = soon\n"),
            "[General]\nSecondsToScanBeforeGivingUp = 120\n"
        );
        // The same key in another section is not the one UE4SS reads.
        assert_eq!(
            with_scan_time_floor("[Other]\nSecondsToScanBeforeGivingUp = 500\n[General]\n"),
            "[Other]\nSecondsToScanBeforeGivingUp = 500\n[General]\nSecondsToScanBeforeGivingUp = 120\n"
        );
    }

    /// The shipped settings file, run through every edit: only the scan
    /// timeout and hot reload change (the bundle already hides the console).
    #[test]
    fn the_bundled_settings_change_only_their_own_keys() {
        let bundled = include_str!("../../../../config/UE4SS-settings.ini");
        let updated = with_launcher_settings(bundled, false);
        let changed: Vec<(&str, &str)> = bundled
            .lines()
            .zip(updated.lines())
            .filter(|(a, b)| a != b)
            .collect();
        assert_eq!(
            changed,
            vec![
                ("EnableHotReloadSystem = 1", "EnableHotReloadSystem = 0"),
                ("SecondsToScanBeforeGivingUp = 60", "SecondsToScanBeforeGivingUp = 120"),
            ]
        );
        assert_eq!(bundled.lines().count(), updated.lines().count());
        // A second pass changes nothing.
        assert_eq!(with_launcher_settings(&updated, false), updated);
    }

    #[test]
    fn hot_reload_is_turned_off_and_added_when_missing() {
        assert_eq!(
            with_hot_reload_off("[General]\nEnableHotReloadSystem = 1\nHotReloadKey = R\n"),
            "[General]\nEnableHotReloadSystem = 0\nHotReloadKey = R\n"
        );
        assert_eq!(
            with_hot_reload_off("[General]\nUseCache = 1\n[Debug]\n"),
            "[General]\nUseCache = 1\nEnableHotReloadSystem = 0\n[Debug]\n"
        );
    }

    /// A stand-in install tree under the temp directory, inside a library
    /// folder as every store lays it out. Returns the install root.
    fn fake_install(name: &str) -> PathBuf {
        let library = std::env::temp_dir().join(format!("mjolnir-launcher-{name}"));
        let _ = fs::remove_dir_all(&library);
        let root = library.join(GAME_DIR);
        fs::create_dir_all(root.join("Meteorite/Binaries/Win64")).expect("scratch tree");
        fs::create_dir_all(root.join("Meteorite/Content/Paks")).expect("scratch tree");
        fs::write(
            root.join("Meteorite/Binaries/Win64/Meteorite-Win64-Shipping.exe"),
            b"",
        )
        .expect("scratch exe");
        root
    }

    /// The picker invites the wrong depth, so every folder in the chain — and
    /// the executable itself — has to name the same root.
    #[test]
    fn a_manual_location_resolves_from_any_depth() {
        let root = fake_install("depth");
        let picks = [
            // The library holding it, one level above.
            root.parent().expect("library").to_path_buf(),
            root.clone(),
            root.join("Meteorite"),
            root.join("Meteorite/Binaries"),
            root.join("Meteorite/Binaries/Win64"),
            root.join("Meteorite/Content/Paks"),
            root.join("Meteorite/Binaries/Win64/Meteorite-Win64-Shipping.exe"),
        ];
        for pick in picks {
            assert_eq!(
                resolve_install_root(&pick.to_string_lossy()),
                Some(root.clone()),
                "{} should name the install root",
                pick.display()
            );
        }
        // Quoted, padded and trailing-slashed, as a path pasted from Explorer
        // arrives.
        let pasted = format!("  \"{}\\\"  ", root.display());
        assert_eq!(resolve_install_root(&pasted), Some(root.clone()));

        let _ = fs::remove_dir_all(root.parent().expect("library"));
    }

    /// Anything that is not the game has to be refused here rather than
    /// accepted and failed later, mid-install, from inside it.
    #[test]
    fn a_folder_without_the_game_is_refused() {
        let empty = std::env::temp_dir().join("mjolnir-launcher-empty");
        let _ = fs::remove_dir_all(&empty);
        fs::create_dir_all(empty.join("Some/Other/Game")).expect("scratch tree");

        assert_eq!(resolve_install_root(&empty.to_string_lossy()), None);
        assert_eq!(
            resolve_install_root(&empty.join("Some/Other/Game").to_string_lossy()),
            None
        );
        assert_eq!(resolve_install_root(""), None);
        assert_eq!(resolve_install_root(r"Z:\nothing\here"), None);

        let _ = fs::remove_dir_all(&empty);
    }

    #[test]
    fn steams_folder_reads_off_reg_query_output() {
        let out = "\r\nHKEY_CURRENT_USER\\Software\\Valve\\Steam\r\n    SteamPath    REG_SZ    d:/games/steam\r\n";
        assert_eq!(steam_path_from_reg(out), Some(PathBuf::from("d:/games/steam")));
        assert_eq!(steam_path_from_reg("ERROR: The system was unable to find"), None);
    }

    #[test]
    fn the_storefront_is_read_off_the_path() {
        assert_eq!(
            platform_for(Path::new(
                r"D:\SteamLibrary\steamapps\common\Halo Campaign Evolved"
            )),
            "steam"
        );
        assert_eq!(
            platform_for(Path::new(r"E:\XboxGames\Halo Campaign Evolved")),
            "gamepass"
        );
        // The newer Xbox app puts a space in the library name and a dash in
        // the game's, and installs one level down.
        assert_eq!(
            platform_for(Path::new(r"D:\Xbox Games\Halo- Campaign Evolved\Content")),
            "gamepass"
        );
        // A copy somewhere of the player's own choosing is neither.
        assert_eq!(platform_for(Path::new(r"G:\Games\HCE")), "manual");
    }

    /// The Xbox app lays the game out as `<library>\Halo- Campaign Evolved\
    /// Content\Meteorite\Binaries\WinGDK`. Returns the install root, which is
    /// the `Content` folder.
    fn fake_xbox_install(name: &str) -> PathBuf {
        let library = std::env::temp_dir().join(format!("mjolnir-launcher-{name}"));
        let _ = fs::remove_dir_all(&library);
        let root = library.join(GAME_DIRS[1]).join(XBOX_CONTENT_DIR);
        fs::create_dir_all(root.join("Meteorite/Binaries/WinGDK")).expect("scratch tree");
        fs::create_dir_all(root.join("Meteorite/Content/Paks")).expect("scratch tree");
        fs::write(root.join("Meteorite/Binaries/WinGDK").join(GAME_EXE), b"").expect("scratch exe");
        root
    }

    /// The bug behind the "Game binaries directory not found: ...\Win64"
    /// report from an Xbox app install: UE4SS goes into the folder the store
    /// actually shipped, and the Xbox game folder itself names the root.
    #[test]
    fn an_xbox_app_install_uses_its_wingdk_folder() {
        let root = fake_xbox_install("xbox");
        assert_eq!(binaries_dir(&root), root.join("Meteorite/Binaries/WinGDK"));
        assert_eq!(mods_dir(&root), root.join("Meteorite/Binaries/WinGDK/ue4ss/Mods"));

        let library = root.parent().expect("game dir").parent().expect("library");
        let picks = [
            library.to_path_buf(),
            root.parent().expect("game dir").to_path_buf(),
            root.clone(),
            root.join("Meteorite"),
            root.join("Meteorite/Binaries/WinGDK"),
            root.join("Meteorite/Binaries/WinGDK").join(GAME_EXE),
        ];
        for pick in picks {
            assert_eq!(
                resolve_install_root(&pick.to_string_lossy()),
                Some(root.clone()),
                "{} should name the Xbox install root",
                pick.display()
            );
        }

        let _ = fs::remove_dir_all(library);
    }

    /// Steam's layout still resolves to `Win64`, and an install with neither
    /// folder yet reports the Steam path so the error names somewhere real.
    #[test]
    fn a_steam_install_uses_its_win64_folder() {
        let root = fake_install("win64");
        assert_eq!(binaries_dir(&root), root.join("Meteorite/Binaries/Win64"));

        fs::remove_dir_all(root.join("Meteorite/Binaries")).expect("drop binaries");
        assert!(is_install_root(&root), "the Paks folder alone still marks an install");
        assert_eq!(binaries_dir(&root), root.join("Meteorite/Binaries/Win64"));

        let _ = fs::remove_dir_all(root.parent().expect("library"));
    }
}
