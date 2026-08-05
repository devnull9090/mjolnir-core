//! Companion tools the launcher installs on demand.
//!
//! A tool is a standalone MJOLNIR app that ships on its own release cadence,
//! so the launcher does not carry its bytes. Each tool publishes a manifest
//! next to its build; the launcher reads that to decide whether an install or
//! an update is available, downloads the executable, checks it against the
//! published hash, and keeps it under the launcher's own data directory.

use std::fs;
use std::io::Read;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Emitter};

const TOOLS_BASE: &str = "https://releases.mjolnircore.com/tools";

/// A tool this launcher knows how to install.
///
/// The list is compiled in rather than fetched so the Tools view still renders
/// something useful when the machine is offline; only versions need the network.
struct KnownTool {
    id: &'static str,
    name: &'static str,
    description: &'static str,
}

const KNOWN: &[KnownTool] = &[KnownTool {
    id: "tag-editor",
    name: "MJOLNIR Tag Editor",
    description: "Browse and edit the Blam tags and textures inside your installed game.",
}];

/// What a tool publishes about its current build.
#[derive(Debug, Deserialize)]
struct ToolManifest {
    version: String,
    /// File name the executable is saved as.
    exe: String,
    url: String,
    sha256: String,
    #[serde(default)]
    size: u64,
}

/// What the launcher recorded when it installed a tool.
#[derive(Debug, Serialize, Deserialize)]
struct Installed {
    version: String,
    exe: String,
}

/// One row of the Tools view.
#[derive(Debug, Serialize)]
pub struct ToolStatus {
    pub id: String,
    pub name: String,
    pub description: String,
    pub installed_version: Option<String>,
    pub latest_version: Option<String>,
    pub update_available: bool,
    /// Download size of the latest build, when known.
    pub size: u64,
    /// Why the latest version could not be determined, when it could not be.
    pub error: Option<String>,
}

/// Progress of a tool download, mirroring the modpack installer's shape.
#[derive(Debug, Serialize, Clone)]
struct ToolProgress {
    id: String,
    stage: String,
    message: String,
    percent: f32,
}

/// Resolve an id from the frontend to a tool this launcher knows.
///
/// Every path below is built from this id, so nothing unvalidated is ever
/// joined onto the launcher's data directory.
fn known(id: &str) -> Result<&'static KnownTool, String> {
    KNOWN
        .iter()
        .find(|t| t.id == id)
        .ok_or_else(|| format!("Unknown tool: {id}"))
}

fn tools_root() -> PathBuf {
    let mut dir = dirs::config_dir().unwrap_or_else(|| PathBuf::from("."));
    dir.push("com.devnull9090.mjolnir-launcher");
    dir.push("tools");
    dir
}

fn tool_dir(id: &str) -> PathBuf {
    tools_root().join(id)
}

fn installed_path(id: &str) -> PathBuf {
    tool_dir(id).join("installed.json")
}

/// What is on disk for a tool, if anything. A record whose executable has gone
/// missing counts as not installed, so a half-deleted tool offers Install.
fn installed(id: &str) -> Option<Installed> {
    let raw = fs::read_to_string(installed_path(id)).ok()?;
    let record: Installed = serde_json::from_str(&raw).ok()?;
    if tool_dir(id).join(&record.exe).is_file() {
        Some(record)
    } else {
        None
    }
}

fn http() -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .map_err(|e| format!("HTTP client error: {e}"))
}

fn fetch_manifest(id: &str) -> Result<ToolManifest, String> {
    let url = format!("{TOOLS_BASE}/{id}/latest/manifest.json");
    let resp = http()?
        .get(&url)
        .send()
        .map_err(|e| format!("Could not reach the release server: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("Release server returned {}", resp.status()));
    }
    resp.json()
        .map_err(|e| format!("Could not read the tool manifest: {e}"))
}

/// Every known tool, with its installed and available versions.
pub fn list() -> Vec<ToolStatus> {
    KNOWN
        .iter()
        .map(|t| {
            let local = installed(t.id);
            let installed_version = local.as_ref().map(|i| i.version.clone());
            let (latest, size, error) = match fetch_manifest(t.id) {
                Ok(m) => (Some(m.version), m.size, None),
                Err(e) => (None, 0, Some(e)),
            };
            // Any difference counts as an update: versions are published in
            // order, and a rollback should still be offered.
            let update_available = match (&installed_version, &latest) {
                (Some(a), Some(b)) => a != b,
                _ => false,
            };
            ToolStatus {
                id: t.id.to_string(),
                name: t.name.to_string(),
                description: t.description.to_string(),
                installed_version,
                latest_version: latest,
                update_available,
                size,
                error,
            }
        })
        .collect()
}

fn emit(app: &AppHandle, id: &str, stage: &str, message: &str, percent: f32) {
    let _ = app.emit(
        "tool-progress",
        ToolProgress {
            id: id.to_string(),
            stage: stage.to_string(),
            message: message.to_string(),
            percent,
        },
    );
}

/// Download a tool and put it in place, replacing any previous build.
pub fn install(app: &AppHandle, id: &str) -> Result<(), String> {
    let id = known(id)?.id;

    emit(app, id, "downloading", "Checking for the latest build...", 0.0);
    let manifest = fetch_manifest(id)?;

    emit(app, id, "downloading", "Downloading...", 5.0);
    let resp = http()?
        .get(&manifest.url)
        .send()
        .map_err(|e| format!("Download failed: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("Download failed with status {}", resp.status()));
    }

    let total = resp.content_length().unwrap_or(manifest.size);
    let mut bytes: Vec<u8> = Vec::with_capacity(total as usize);
    let mut reader = resp;
    let mut buf = [0u8; 32768];
    loop {
        let n = reader
            .read(&mut buf)
            .map_err(|e| format!("Download read error: {e}"))?;
        if n == 0 {
            break;
        }
        bytes.extend_from_slice(&buf[..n]);
        if total > 0 {
            emit(
                app,
                id,
                "downloading",
                &format!(
                    "Downloading... {:.1} MB / {:.1} MB",
                    bytes.len() as f64 / 1_048_576.0,
                    total as f64 / 1_048_576.0
                ),
                5.0 + (bytes.len() as f32 / total as f32) * 80.0,
            );
        }
    }

    // Refuse anything that does not match the published hash, so a truncated
    // or tampered download never reaches disk as an executable.
    emit(app, id, "verifying", "Verifying download...", 90.0);
    let mut hasher = Sha256::new();
    hasher.update(&bytes);
    let got = hex::encode(hasher.finalize());
    if !got.eq_ignore_ascii_case(&manifest.sha256) {
        return Err(format!(
            "Download did not match the published checksum (expected {}, got {got})",
            manifest.sha256
        ));
    }

    emit(app, id, "installing", "Installing...", 95.0);
    let dir = tool_dir(id);
    fs::create_dir_all(&dir).map_err(|e| format!("Could not create {}: {e}", dir.display()))?;

    // Write beside the target and swap, so a failure part-way through cannot
    // leave a running tool replaced by a partial file.
    let target = dir.join(&manifest.exe);
    let staged = dir.join(format!("{}.part", manifest.exe));
    fs::write(&staged, &bytes).map_err(|e| format!("Could not write {}: {e}", staged.display()))?;
    if target.exists() {
        let _ = fs::remove_file(&target);
    }
    fs::rename(&staged, &target)
        .map_err(|e| format!("Could not place {}: {e}", target.display()))?;

    let record = Installed {
        version: manifest.version.clone(),
        exe: manifest.exe.clone(),
    };
    fs::write(
        installed_path(id),
        serde_json::to_string_pretty(&record).unwrap_or_default(),
    )
    .map_err(|e| format!("Could not record the install: {e}"))?;

    emit(app, id, "done", &format!("Installed v{}", manifest.version), 100.0);
    Ok(())
}

/// Start an installed tool.
pub fn launch(id: &str) -> Result<(), String> {
    let id = known(id)?.id;
    let record = installed(id).ok_or("That tool is not installed.")?;
    let exe = tool_dir(id).join(&record.exe);
    let mut command = std::process::Command::new(&exe);
    command.current_dir(tool_dir(id));
    // Hand the tool the install this launcher is working on, so a location
    // the player had to set here is not something they have to find again
    // over there. Each tool treats it as a starting point: a location chosen
    // inside the tool still wins.
    if let Some((install, _)) = crate::find_game_install() {
        command.env(crate::GAME_DIR_ENV, install);
    }
    command
        .spawn()
        .map_err(|e| format!("Could not start {}: {e}", exe.display()))?;
    Ok(())
}

/// Remove an installed tool.
pub fn uninstall(id: &str) -> Result<(), String> {
    let id = known(id)?.id;
    let dir = tool_dir(id);
    if dir.exists() {
        fs::remove_dir_all(&dir).map_err(|e| format!("Could not remove {}: {e}", dir.display()))?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_tag_editor_is_a_known_tool() {
        assert!(KNOWN.iter().any(|t| t.id == "tag-editor"));
    }

    /// Ids reach these functions from the frontend and are joined onto the
    /// launcher's data directory, so anything unknown must be refused before
    /// a path is built from it — `uninstall` removes a directory tree.
    #[test]
    fn an_unknown_id_is_refused_before_any_path_is_built() {
        for bad in ["../evil", "..\\evil", "tag-editor/../..", "", "nope"] {
            assert!(known(bad).is_err(), "{bad:?} should be rejected");
            assert!(uninstall(bad).is_err(), "{bad:?} should not be removable");
            assert!(launch(bad).is_err(), "{bad:?} should not be launchable");
        }
        assert!(known("tag-editor").is_ok());
    }

    #[test]
    fn tool_paths_stay_under_the_launcher_directory() {
        let dir = tool_dir("tag-editor");
        assert!(dir.ends_with("tools/tag-editor") || dir.ends_with("tools\\tag-editor"));
        assert!(installed_path("tag-editor").ends_with("installed.json"));
    }

    #[test]
    fn a_manifest_parses_from_what_the_workflow_publishes() {
        let raw = r#"{
            "id": "tag-editor",
            "version": "0.1.0",
            "exe": "mjolnir-tag-editor.exe",
            "url": "https://releases.mjolnircore.com/tools/tag-editor/0.1.0/mjolnir-tag-editor.exe",
            "sha256": "abc123",
            "size": 10236416
        }"#;
        let m: ToolManifest = serde_json::from_str(raw).expect("manifest");
        assert_eq!(m.version, "0.1.0");
        assert_eq!(m.exe, "mjolnir-tag-editor.exe");
        assert_eq!(m.size, 10_236_416);
    }
}
