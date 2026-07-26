use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};

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

/// Find HCE install via common Steam library paths
fn find_game_install() -> Option<PathBuf> {
    let steam_dirs = vec![
        r"C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved",
        r"C:\Program Files\Steam\steamapps\common\Halo Campaign Evolved",
        r"D:\SteamLibrary\steamapps\common\Halo Campaign Evolved",
        r"E:\SteamLibrary\steamapps\common\Halo Campaign Evolved",
    ];

    for dir in steam_dirs {
        let path = PathBuf::from(dir);
        if path.exists() {
            return Some(path);
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
                            return Some(candidate);
                        }
                    }
                }
            }
        }
    }

    None
}

#[tauri::command]
fn detect_game() -> GameInfo {
    match find_game_install() {
        Some(install_path) => {
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

fn read_mod_description(mods_dir: &Path, mod_name: &str) -> String {
    let main_lua = mods_dir.join(mod_name).join("Scripts/main.lua");
    if let Ok(content) = fs::read_to_string(&main_lua) {
        // Extract first comment line as description
        for line in content.lines() {
            let trimmed = line.trim();
            if trimmed.starts_with("--") && !trimmed.starts_with("---") {
                return trimmed.trim_start_matches('-').trim().to_string();
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
    if let Some(install_path) = find_game_install() {
        let mods_dir = install_path.join("Meteorite/Binaries/Win64/ue4ss/Mods");
        if mods_dir.exists() {
            return parse_mods_txt(&mods_dir);
        }
    }
    Vec::new()
}

#[tauri::command]
fn toggle_mod(name: String, enabled: bool) -> Result<(), String> {
    let install_path = find_game_install().ok_or("Game not found")?;
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
fn launch_game() -> Result<(), String> {
    if let Some(install_path) = find_game_install() {
        // Candidate paths for the game executable
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

    // Fallback if game directory wasn't found directly
    std::process::Command::new("cmd")
        .args(["/C", "start", "steam://run/2993530"])
        .spawn()
        .map_err(|e| format!("Failed to launch via Steam: {}", e))?;

    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            detect_game,
            get_mods,
            toggle_mod,
            launch_game,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
