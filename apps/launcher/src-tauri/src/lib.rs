use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs;
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use tauri::{AppHandle, Emitter};

mod changelog;
mod hub;
mod tools;

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
}

impl Default for LauncherSettings {
    fn default() -> Self {
        Self {
            launch_method: "steam".to_string(),
            custom_exe_path: None,
        }
    }
}

/// Build/environment info shown on the settings page
#[derive(Debug, Serialize, Deserialize)]
pub struct BuildInfo {
    pub launcher_version: String,
    pub game_found: bool,
    pub install_path: Option<String>,
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
    pub platform: String, // "steam" | "gamepass" | "unknown"
    pub ue4ss_installed: bool,
    pub modpack_enabled: bool,
    pub manifest_version: Option<String>,
    pub ue4ss_version: Option<String>,
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

/// Find HCE install and return (path, platform)
pub(crate) fn find_game_install() -> Option<(PathBuf, String)> {
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

    // Try reading Steam's libraryfolders.vdf for custom paths
    let vdf_path = r"C:\Program Files (x86)\Steam\steamapps\libraryfolders.vdf";
    if Path::new(vdf_path).exists() {
        if let Ok(content) = fs::read_to_string(vdf_path) {
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

    // Check Xbox Game Pass / Microsoft Store locations
    let drives = ["C", "D", "E", "F"];
    for drive in &drives {
        let xbox_path = PathBuf::from(format!(
            "{}:\\XboxGames\\Halo Campaign Evolved",
            drive
        ));
        if xbox_path.exists() {
            return Some((xbox_path, "gamepass".to_string()));
        }
        // Also check Content subdirectory pattern
        let xbox_content = PathBuf::from(format!(
            "{}:\\XboxGames\\Halo Campaign Evolved\\Content",
            drive
        ));
        if xbox_content.exists() {
            return Some((xbox_content.parent().unwrap().to_path_buf(), "gamepass".to_string()));
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

/// Get the Win64 binaries directory
fn get_bin_dir() -> Option<PathBuf> {
    find_game_install().map(|(p, _)| p.join("Meteorite/Binaries/Win64"))
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

// ─── Existing commands ──────────────────────────────────────────────────

#[tauri::command]
fn detect_game() -> GameInfo {
    match find_game_install() {
        Some((install_path, _platform)) => {
            let bin_dir = install_path.join("Meteorite/Binaries/Win64");
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
        let mods_dir = install_path.join("Meteorite/Binaries/Win64/ue4ss/Mods");
        if mods_dir.exists() {
            return parse_mods_txt(&mods_dir);
        }
    }
    Vec::new()
}

#[tauri::command]
fn toggle_mod(name: String, enabled: bool) -> Result<(), String> {
    let (install_path, _) = find_game_install().ok_or("Game not found")?;
    let mods_dir = install_path.join("Meteorite/Binaries/Win64/ue4ss/Mods");
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

#[tauri::command]
fn get_build_info() -> BuildInfo {
    let game_info = detect_game();
    let mods = get_mods();

    BuildInfo {
        launcher_version: env!("CARGO_PKG_VERSION").to_string(),
        game_found: game_info.found,
        install_path: game_info.install_path,
        ue4ss_installed: game_info.ue4ss_installed,
        mods_path: game_info.mods_path,
        mods_count: mods.len(),
    }
}

#[tauri::command]
fn launch_game() -> Result<(), String> {
    let settings = get_settings();

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
                let candidates = vec![
                    install_path.join("Meteorite/Binaries/Win64/Meteorite-Win64-Shipping.exe"),
                    install_path.join("Meteorite/Binaries/Win64/Meteorite.exe"),
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

// ─── New commands: Install lifecycle ────────────────────────────────────

#[tauri::command]
fn get_install_status() -> InstallStatus {
    let manifest = load_cached_manifest();

    match find_game_install() {
        Some((install_path, platform)) => {
            let bin_dir = install_path.join("Meteorite/Binaries/Win64");
            let ue4ss_dir = bin_dir.join("ue4ss");
            let (dll_installed, dll_enabled) = check_ue4ss_dll(&bin_dir);

            let ue4ss_installed = dll_installed
                && ue4ss_dir.exists()
                && ue4ss_dir.join("UE4SS-settings.ini").exists();

            InstallStatus {
                game_found: true,
                install_path: Some(install_path.to_string_lossy().to_string()),
                platform,
                ue4ss_installed,
                modpack_enabled: dll_enabled,
                manifest_version: manifest.as_ref().map(|m| m.version.clone()),
                ue4ss_version: manifest.as_ref().map(|m| m.ue4ss_version.clone()),
            }
        }
        None => InstallStatus {
            game_found: false,
            install_path: None,
            platform: "unknown".to_string(),
            ue4ss_installed: false,
            modpack_enabled: false,
            manifest_version: None,
            ue4ss_version: None,
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

#[tauri::command]
async fn install_modpack(app: AppHandle) -> Result<(), String> {
    // Run the blocking download/extract/verify on a background thread
    let result = tauri::async_runtime::spawn_blocking(move || {
        install_modpack_blocking(&app)
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
async fn install_tool(app: AppHandle, id: String) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || tools::install(&app, &id))
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
async fn hub_install(slug: String, release_id: Option<String>) -> Result<hub::HubState, String> {
    tauri::async_runtime::spawn_blocking(move || hub::install(slug, release_id))
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
async fn code_mods_install(id: String) -> Result<(), String> {
    tauri::async_runtime::spawn_blocking(move || hub::code_mods_install(id))
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
    let bin_dir = get_bin_dir().ok_or("Game not found. Please install Halo Campaign Evolved via Steam first.")?;

    // Ensure bin dir exists
    if !bin_dir.exists() {
        return Err(format!(
            "Game binaries directory not found: {}",
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
    let mut zip_bytes: Vec<u8> = Vec::new();

    let mut reader = zip_resp;
    let mut downloaded = 0u64;
    let mut buf = [0u8; 32768];

    loop {
        let n = reader
            .read(&mut buf)
            .map_err(|e| format!("Download read error: {}", e))?;
        if n == 0 {
            break;
        }
        zip_bytes.extend_from_slice(&buf[..n]);
        downloaded += n as u64;

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
    }

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

        io::copy(&mut file, &mut out_file)
            .map_err(|e| format!("Failed to write {}: {}", out_path.display(), e))?;

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
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            detect_game,
            get_mods,
            toggle_mod,
            launch_game,
            get_settings,
            save_settings,
            get_build_info,
            get_install_status,
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
            hub_auth_status,
            hub_auth_start,
            hub_auth_poll,
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
}
