//! Hub integration: browse and install content mods, keep profiles with a
//! load order, and install the Ed25519-signed code-mod set.
//!
//! Content mods arrive as `.mjolnir` archives from mjolnircore.com. Installing
//! one downloads it, checks its SHA-256 against what the hub recorded at scan
//! time, and unpacks its IoStore containers into a local cache. A *profile*
//! decides what actually reaches the game: materializing writes each enabled
//! container into `Meteorite/Content/Paks` as the verified override triple —
//! stub `.pak` (copied from a small shipped one; a bare `.utoc`/`.ucas` pair
//! does not mount, see docs/iostore_packaging.md), `.utoc`, `.ucas` — named
//! `pakchunk9NN-MJOLNIRHUB-<slug>…_P`.
//!
//! Load order maps list position to that 9NN number, on the assumption that a
//! higher pakchunk number mounts later and wins shared chunks. UE mounts
//! `pakchunkN` by priority and one `_P` override winning its chunks is
//! verified; the relative order of *several* `_P` containers is the one
//! assumption not yet confirmed in game (docs/iostore_packaging.md, open
//! question 1). It is kept in exactly one place — `order_number` — so
//! flipping the direction is a one-line change if the experiment says
//! otherwise.
//!
//! Code mods (UE4SS Lua) are different on purpose: they only ever install
//! from the signed set that mjolnir-core CI publishes. The manifest signature
//! is checked against a public key compiled into this binary, so neither a
//! compromised bucket nor a tampered download can put unreviewed code in the
//! game (docs/hub_architecture.md §2).

use std::fs;
use std::io::Read;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

/// The hub API. Override with MJOLNIR_HUB_URL for local development.
fn hub_api() -> String {
    std::env::var("MJOLNIR_HUB_URL").unwrap_or_else(|_| "https://mjolnircore.com/api/v1".into())
}

const CODE_MODS_BASE: &str = "https://releases.mjolnircore.com/mods";

/// The mod-release signing key, pinned at compile time. Matches the private
/// key held only in mjolnir-core's CI secrets.
const MOD_SIGNING_PUB_PEM: &str = include_str!("../../../../keys/mod-signing.pub");

/// Marker distinguishing containers this module manages from everything else
/// in Paks, including hand-placed experiment containers named plain MJOLNIR.
const MARKER: &str = "MJOLNIRHUB";

// ─── State ──────────────────────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct InstalledHubMod {
    pub slug: String,
    pub name: String,
    pub release_id: String,
    pub version: String,
    pub sha256: String,
    /// Basenames (no extension) of the containers in this release's cache.
    pub containers: Vec<String>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct ProfileEntry {
    pub slug: String,
    pub enabled: bool,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Profile {
    pub name: String,
    /// Load order: index 0 mounts first; later entries win shared chunks.
    pub entries: Vec<ProfileEntry>,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct HubState {
    pub installed: Vec<InstalledHubMod>,
    pub profiles: Vec<Profile>,
    pub active: String,
}

impl Default for HubState {
    fn default() -> Self {
        HubState {
            installed: Vec::new(),
            profiles: vec![Profile {
                name: "Default".into(),
                entries: Vec::new(),
            }],
            active: "Default".into(),
        }
    }
}

fn config_dir() -> PathBuf {
    let mut dir = dirs::config_dir().unwrap_or_else(|| PathBuf::from("."));
    dir.push("com.devnull9090.mjolnir-launcher");
    dir
}

fn state_path() -> PathBuf {
    config_dir().join("hub_state.json")
}

fn cache_dir() -> PathBuf {
    config_dir().join("hub-cache")
}

fn load_state() -> HubState {
    fs::read_to_string(state_path())
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

fn save_state(state: &HubState) -> Result<(), String> {
    fs::create_dir_all(config_dir()).map_err(|e| e.to_string())?;
    fs::write(
        state_path(),
        serde_json::to_string_pretty(state).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())
}

fn paks_dir() -> Result<PathBuf, String> {
    let (install, _) = crate::find_game_install()
        .ok_or("Game not found. Install Halo Campaign Evolved first.")?;
    let paks = install.join("Meteorite/Content/Paks");
    if !paks.exists() {
        return Err(format!("Paks directory not found: {}", paks.display()));
    }
    Ok(paks)
}

fn http() -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(180))
        .build()
        .map_err(|e| format!("HTTP client error: {e}"))
}

fn sha256_hex(bytes: &[u8]) -> String {
    hex::encode(Sha256::digest(bytes))
}

// ─── Materialization ────────────────────────────────────────────────────

fn sanitize(slug: &str) -> String {
    slug.chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '-')
        .collect()
}

/// List position → pakchunk number. The single point carrying the "higher
/// number wins" assumption described in the module docs.
fn order_number(index: usize) -> usize {
    900 + index.min(99)
}

/// The stub `.pak` an override triple needs: the smallest shipped pak,
/// byte-copied, exactly as in the verified experiment.
fn stub_pak_bytes(paks: &std::path::Path) -> Result<Vec<u8>, String> {
    let mut best: Option<(u64, PathBuf)> = None;
    for entry in fs::read_dir(paks).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let name = entry.file_name().to_string_lossy().into_owned();
        if !name.starts_with("pakchunk") || !name.ends_with(".pak") || name.contains(MARKER) {
            continue;
        }
        let size = entry.metadata().map_err(|e| e.to_string())?.len();
        if best.as_ref().is_none_or(|(s, _)| size < *s) {
            best = Some((size, entry.path()));
        }
    }
    let (_, path) = best.ok_or("No shipped .pak found to derive a stub from")?;
    fs::read(&path).map_err(|e| e.to_string())
}

/// Make the Paks directory agree with the active profile: remove every
/// container this module owns, then write back the enabled ones in order.
fn materialize(state: &HubState) -> Result<(), String> {
    let paks = paks_dir()?;

    for entry in fs::read_dir(&paks).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let name = entry.file_name().to_string_lossy().into_owned();
        if name.contains(&format!("-{MARKER}-")) {
            fs::remove_file(entry.path()).map_err(|e| {
                format!("Cannot remove {name}: {e}. Is the game running?")
            })?;
        }
    }

    let profile = state
        .profiles
        .iter()
        .find(|p| p.name == state.active)
        .ok_or("Active profile missing")?;

    let mounted: Vec<&ProfileEntry> = profile.entries.iter().filter(|e| e.enabled).collect();
    if mounted.is_empty() {
        return Ok(());
    }
    let stub = stub_pak_bytes(&paks)?;

    for (i, entry) in mounted.iter().enumerate() {
        let inst = state
            .installed
            .iter()
            .find(|m| m.slug == entry.slug)
            .ok_or_else(|| format!("{} is in the profile but not installed", entry.slug))?;
        let release_cache = cache_dir().join(&inst.release_id);
        for (j, container) in inst.containers.iter().enumerate() {
            let base = format!(
                "pakchunk{}-{MARKER}-{}-{j}_P",
                order_number(i),
                sanitize(&inst.slug),
            );
            fs::copy(
                release_cache.join(format!("{container}.utoc")),
                paks.join(format!("{base}.utoc")),
            )
            .map_err(|e| format!("{}: {e}", inst.slug))?;
            fs::copy(
                release_cache.join(format!("{container}.ucas")),
                paks.join(format!("{base}.ucas")),
            )
            .map_err(|e| format!("{}: {e}", inst.slug))?;
            fs::write(paks.join(format!("{base}.pak")), &stub)
                .map_err(|e| format!("{}: {e}", inst.slug))?;
        }
    }
    Ok(())
}

// ─── Hub browsing & install ─────────────────────────────────────────────

/// Pass a hub listing through so the webview does not need its own HTTP
/// stack or error handling for offline machines.
pub fn list_mods(query: Option<String>) -> Result<serde_json::Value, String> {
    let mut url = format!("{}/mods?limit=50", hub_api());
    if let Some(q) = query {
        if !q.trim().is_empty() {
            url.push_str(&format!("&q={}", urlencode(q.trim())));
        }
    }
    let resp = http()?.get(&url).send().map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("Hub returned {}", resp.status()));
    }
    resp.json().map_err(|e| e.to_string())
}

fn urlencode(s: &str) -> String {
    s.bytes()
        .map(|b| match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' => {
                (b as char).to_string()
            }
            _ => format!("%{b:02X}"),
        })
        .collect()
}

#[derive(Deserialize)]
struct HubRelease {
    id: String,
    version: String,
}

#[derive(Deserialize)]
struct HubReleaseStatus {
    sha256: Option<String>,
    status: String,
}

/// Install a mod's newest published release and add it to the end of the
/// active profile's load order.
pub fn install(slug: String) -> Result<HubState, String> {
    let client = http()?;
    let api = hub_api();

    // Mod page (for the display name) and newest release.
    let mod_page: serde_json::Value = client
        .get(format!("{api}/mods/{slug}"))
        .send()
        .map_err(|e| e.to_string())?
        .json()
        .map_err(|e| e.to_string())?;
    let name = mod_page["name"].as_str().unwrap_or(&slug).to_string();

    let releases: serde_json::Value = client
        .get(format!("{api}/mods/{slug}/releases"))
        .send()
        .map_err(|e| e.to_string())?
        .json()
        .map_err(|e| e.to_string())?;
    let release: HubRelease = serde_json::from_value(
        releases["releases"]
            .get(0)
            .cloned()
            .ok_or("This mod has no published releases")?,
    )
    .map_err(|e| e.to_string())?;

    let status: HubReleaseStatus = client
        .get(format!("{api}/releases/{}", release.id))
        .send()
        .map_err(|e| e.to_string())?
        .json()
        .map_err(|e| e.to_string())?;
    if status.status != "published" {
        return Err(format!("Release is {}, not published", status.status));
    }
    let expected = status.sha256.ok_or("Hub has no hash for this release")?;

    // Download and verify before a single byte lands anywhere permanent.
    let mut resp = client
        .get(format!("{api}/releases/{}/download", release.id))
        .send()
        .map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("Download failed: {}", resp.status()));
    }
    let mut bytes = Vec::new();
    resp.read_to_end(&mut bytes).map_err(|e| e.to_string())?;
    let actual = sha256_hex(&bytes);
    if actual != expected {
        return Err(format!(
            "Hash mismatch: hub says {expected}, download is {actual}. Refusing to install."
        ));
    }

    // Unpack the containers into this release's cache.
    let release_cache = cache_dir().join(&release.id);
    let _ = fs::remove_dir_all(&release_cache);
    fs::create_dir_all(&release_cache).map_err(|e| e.to_string())?;

    let mut zip = zip::ZipArchive::new(std::io::Cursor::new(bytes)).map_err(|e| e.to_string())?;
    let mut containers = Vec::new();
    for i in 0..zip.len() {
        let mut file = zip.by_index(i).map_err(|e| e.to_string())?;
        let path = file.name().to_string();
        if !path.starts_with("content/") || path.contains("..") {
            continue;
        }
        let base = path.rsplit('/').next().unwrap_or("").to_string();
        let (stem, ext) = match base.rsplit_once('.') {
            Some((s, e @ ("utoc" | "ucas"))) if !s.is_empty() => (s.to_string(), e),
            _ => continue,
        };
        let mut data = Vec::new();
        file.read_to_end(&mut data).map_err(|e| e.to_string())?;
        fs::write(release_cache.join(format!("{stem}.{ext}")), data).map_err(|e| e.to_string())?;
        if ext == "utoc" {
            containers.push(stem);
        }
    }
    if containers.is_empty() {
        return Err("Archive holds no containers under content/".into());
    }
    containers.sort();

    let mut state = load_state();
    state.installed.retain(|m| m.slug != slug);
    state.installed.push(InstalledHubMod {
        slug: slug.clone(),
        name,
        release_id: release.id,
        version: release.version,
        sha256: expected,
        containers,
    });
    let active = state.active.clone();
    for profile in &mut state.profiles {
        if profile.name == active && !profile.entries.iter().any(|e| e.slug == slug) {
            profile.entries.push(ProfileEntry {
                slug: slug.clone(),
                enabled: true,
            });
        }
    }
    save_state(&state)?;
    materialize(&state)?;
    Ok(state)
}

pub fn uninstall(slug: String) -> Result<HubState, String> {
    let mut state = load_state();
    if let Some(inst) = state.installed.iter().find(|m| m.slug == slug) {
        let _ = fs::remove_dir_all(cache_dir().join(&inst.release_id));
    }
    state.installed.retain(|m| m.slug != slug);
    for profile in &mut state.profiles {
        profile.entries.retain(|e| e.slug != slug);
    }
    save_state(&state)?;
    materialize(&state)?;
    Ok(state)
}

pub fn get_state() -> HubState {
    load_state()
}

/// Move a mod within the active profile's load order.
pub fn set_order(slug: String, new_index: usize) -> Result<HubState, String> {
    let mut state = load_state();
    let active = state.active.clone();
    let profile = state
        .profiles
        .iter_mut()
        .find(|p| p.name == active)
        .ok_or("Active profile missing")?;
    let from = profile
        .entries
        .iter()
        .position(|e| e.slug == slug)
        .ok_or("Not in this profile")?;
    let entry = profile.entries.remove(from);
    profile.entries.insert(new_index.min(profile.entries.len()), entry);
    save_state(&state)?;
    materialize(&state)?;
    Ok(state)
}

pub fn set_enabled(slug: String, enabled: bool) -> Result<HubState, String> {
    let mut state = load_state();
    let active = state.active.clone();
    let profile = state
        .profiles
        .iter_mut()
        .find(|p| p.name == active)
        .ok_or("Active profile missing")?;
    let entry = profile
        .entries
        .iter_mut()
        .find(|e| e.slug == slug)
        .ok_or("Not in this profile")?;
    entry.enabled = enabled;
    save_state(&state)?;
    materialize(&state)?;
    Ok(state)
}

// ─── Profiles ───────────────────────────────────────────────────────────

pub fn profile_create(name: String, copy_active: bool) -> Result<HubState, String> {
    let name = name.trim().to_string();
    if name.is_empty() || name.len() > 40 {
        return Err("Profile names are 1-40 characters".into());
    }
    let mut state = load_state();
    if state.profiles.iter().any(|p| p.name == name) {
        return Err("A profile with that name exists".into());
    }
    let entries = if copy_active {
        state
            .profiles
            .iter()
            .find(|p| p.name == state.active)
            .map(|p| p.entries.clone())
            .unwrap_or_default()
    } else {
        Vec::new()
    };
    state.profiles.push(Profile {
        name: name.clone(),
        entries,
    });
    state.active = name;
    save_state(&state)?;
    materialize(&state)?;
    Ok(state)
}

pub fn profile_switch(name: String) -> Result<HubState, String> {
    let mut state = load_state();
    if !state.profiles.iter().any(|p| p.name == name) {
        return Err("No such profile".into());
    }
    state.active = name;
    save_state(&state)?;
    materialize(&state)?;
    Ok(state)
}

pub fn profile_delete(name: String) -> Result<HubState, String> {
    let mut state = load_state();
    if state.profiles.len() == 1 {
        return Err("Cannot delete the last profile".into());
    }
    state.profiles.retain(|p| p.name != name);
    if state.active == name {
        state.active = state.profiles[0].name.clone();
    }
    save_state(&state)?;
    materialize(&state)?;
    Ok(state)
}

// ─── Conflicts ──────────────────────────────────────────────────────────

/// The conflict matrix for the active profile, straight from the hub's
/// chunk-ID index (POST /conflicts/check). Order in the profile decides the
/// winner of each pair, so conflicts are information, not errors.
pub fn check_conflicts() -> Result<serde_json::Value, String> {
    let state = load_state();
    let profile = state
        .profiles
        .iter()
        .find(|p| p.name == state.active)
        .ok_or("Active profile missing")?;
    let ids: Vec<&str> = profile
        .entries
        .iter()
        .filter(|e| e.enabled)
        .filter_map(|e| {
            state
                .installed
                .iter()
                .find(|m| m.slug == e.slug)
                .map(|m| m.release_id.as_str())
        })
        .collect();
    if ids.len() < 2 {
        return Ok(serde_json::json!({ "pairs": [] }));
    }
    let resp = http()?
        .post(format!("{}/conflicts/check", hub_api()))
        .json(&serde_json::json!({ "release_ids": ids }))
        .send()
        .map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("Hub returned {}", resp.status()));
    }
    resp.json().map_err(|e| e.to_string())
}

// ─── Signed code mods ───────────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct CodeModEntry {
    pub id: String,
    pub file: String,
    pub sha256: String,
    pub size: u64,
    pub url: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct CodeModsManifest {
    pub schema_version: u32,
    pub set_version: String,
    pub mods: Vec<CodeModEntry>,
}

#[derive(Debug, Serialize)]
pub struct CodeModsStatus {
    pub set_version: String,
    /// True iff manifest.json.sig verifies against the compiled-in key.
    pub signature_verified: bool,
    pub mods: Vec<CodeModEntry>,
    pub installed: Vec<String>,
}

fn signing_key() -> Result<ed25519_dalek::VerifyingKey, String> {
    let b64: String = MOD_SIGNING_PUB_PEM
        .lines()
        .filter(|l| !l.starts_with("-----"))
        .collect();
    let der = base64_decode(b64.trim()).ok_or("Bad compiled-in public key PEM")?;
    // SPKI for Ed25519 is a fixed 12-byte header followed by the raw key.
    let raw: [u8; 32] = der
        .get(der.len().saturating_sub(32)..)
        .and_then(|s| s.try_into().ok())
        .ok_or("Compiled-in public key is not 32 bytes")?;
    ed25519_dalek::VerifyingKey::from_bytes(&raw).map_err(|e| e.to_string())
}

fn base64_decode(s: &str) -> Option<Vec<u8>> {
    const TABLE: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = Vec::with_capacity(s.len() * 3 / 4);
    let mut buf = 0u32;
    let mut bits = 0u32;
    for c in s.bytes() {
        if c == b'=' || c == b'\n' || c == b'\r' {
            continue;
        }
        let v = TABLE.iter().position(|&t| t == c)? as u32;
        buf = (buf << 6) | v;
        bits += 6;
        if bits >= 8 {
            bits -= 8;
            out.push((buf >> bits) as u8);
        }
    }
    Some(out)
}

/// Fetch the latest signed manifest, verify its signature, and report which
/// mods from it are present in the game's UE4SS Mods directory.
pub fn code_mods_status() -> Result<CodeModsStatus, String> {
    let client = http()?;
    let manifest_bytes = client
        .get(format!("{CODE_MODS_BASE}/latest/manifest.json"))
        .send()
        .map_err(|e| e.to_string())?
        .bytes()
        .map_err(|e| e.to_string())?;
    let sig_b64 = client
        .get(format!("{CODE_MODS_BASE}/latest/manifest.json.sig"))
        .send()
        .map_err(|e| e.to_string())?
        .text()
        .map_err(|e| e.to_string())?;

    let sig_bytes = base64_decode(sig_b64.trim()).ok_or("Signature is not valid base64")?;
    let sig: [u8; 64] = sig_bytes
        .as_slice()
        .try_into()
        .map_err(|_| "Signature is not 64 bytes")?;
    let verified = signing_key()?
        .verify_strict(
            &manifest_bytes,
            &ed25519_dalek::Signature::from_bytes(&sig),
        )
        .is_ok();

    let manifest: CodeModsManifest =
        serde_json::from_slice(&manifest_bytes).map_err(|e| format!("Bad manifest: {e}"))?;

    let installed = crate::find_game_install()
        .map(|(p, _)| {
            let mods_dir = p.join("Meteorite/Binaries/Win64/ue4ss/Mods");
            manifest
                .mods
                .iter()
                .filter(|m| mods_dir.join(&m.id).is_dir())
                .map(|m| m.id.clone())
                .collect()
        })
        .unwrap_or_default();

    Ok(CodeModsStatus {
        set_version: manifest.set_version,
        signature_verified: verified,
        mods: manifest.mods,
        installed,
    })
}

/// Install one mod from the signed set. Refuses outright when the manifest
/// signature does not verify — an unsigned set does not get to name hashes.
pub fn code_mods_install(id: String) -> Result<(), String> {
    let status = code_mods_status()?;
    if !status.signature_verified {
        return Err(
            "The mods manifest signature does not verify against this launcher's key. \
             Refusing to install anything from it."
                .into(),
        );
    }
    let entry = status
        .mods
        .iter()
        .find(|m| m.id == id)
        .ok_or_else(|| format!("{id} is not in the signed set"))?;

    let (install, _) = crate::find_game_install().ok_or("Game not found")?;
    let mods_dir = install.join("Meteorite/Binaries/Win64/ue4ss/Mods");
    if !mods_dir.exists() {
        return Err("UE4SS is not installed. Install the modpack first.".into());
    }

    let mut resp = http()?.get(&entry.url).send().map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("Download failed: {}", resp.status()));
    }
    let mut bytes = Vec::new();
    resp.read_to_end(&mut bytes).map_err(|e| e.to_string())?;
    let actual = sha256_hex(&bytes);
    if actual != entry.sha256 {
        return Err(format!(
            "Hash mismatch: manifest says {}, download is {actual}. Refusing to install.",
            entry.sha256
        ));
    }

    // The zip roots at "<ModName>/…"; extract only that subtree.
    let mut zip = zip::ZipArchive::new(std::io::Cursor::new(bytes)).map_err(|e| e.to_string())?;
    for i in 0..zip.len() {
        let mut file = zip.by_index(i).map_err(|e| e.to_string())?;
        let name = file.name().to_string();
        if !name.starts_with(&format!("{id}/")) || name.contains("..") {
            continue;
        }
        let dest = mods_dir.join(&name);
        if file.is_dir() {
            fs::create_dir_all(&dest).map_err(|e| e.to_string())?;
            continue;
        }
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        let mut data = Vec::new();
        file.read_to_end(&mut data).map_err(|e| e.to_string())?;
        fs::write(&dest, data).map_err(|e| e.to_string())?;
    }

    // Register with UE4SS if mods.txt does not know it yet.
    let mods_txt = mods_dir.join("mods.txt");
    let content = fs::read_to_string(&mods_txt).unwrap_or_default();
    let known = content.lines().any(|l| {
        l.split(':')
            .next()
            .is_some_and(|n| n.trim() == id)
    });
    if !known {
        let mut updated = content;
        if !updated.is_empty() && !updated.ends_with('\n') {
            updated.push('\n');
        }
        updated.push_str(&format!("{id} : 1\n"));
        fs::write(&mods_txt, updated).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_compiled_in_signing_key_parses() {
        // A bad keys/mod-signing.pub should fail the build's tests, not the
        // first user who tries to install a mod.
        signing_key().expect("pinned public key must parse");
    }

    #[test]
    fn base64_decodes_the_rfc_vector() {
        assert_eq!(base64_decode("Zm9vYmFy").unwrap(), b"foobar");
        assert_eq!(base64_decode("Zm9vYg==").unwrap(), b"foob");
        assert!(base64_decode("!!!").is_none());
    }

    #[test]
    fn order_numbers_stay_inside_the_managed_band() {
        assert_eq!(order_number(0), 900);
        assert_eq!(order_number(42), 942);
        assert_eq!(order_number(500), 999, "clamped, never colliding with shipped chunks");
    }

    #[test]
    fn sanitize_keeps_only_what_a_filename_wants() {
        assert_eq!(sanitize("my-pack"), "my-pack");
        assert_eq!(sanitize("../evil pack!"), "evilpack");
    }

    /// The whole content-mod loop against a live hub and the real game
    /// install: install → containers in Paks → conflicts → reorder →
    /// disable → uninstall leaves Paks clean. Ignored because it needs the
    /// game on disk, a reachable hub (MJOLNIR_HUB_URL for a dev one), and a
    /// mod published under the given slug.
    ///
    /// MJOLNIR_HUB_URL=http://localhost:3000/api/v1 \
    ///   cargo test hub_install_round_trip -- --ignored --nocapture
    #[test]
    #[ignore = "needs the game, a hub, and a published mod (see doc comment)"]
    fn hub_install_round_trip() {
        let slug = std::env::var("MJOLNIR_TEST_SLUG").unwrap_or_else(|_| "pack-a".into());
        let paks = paks_dir().expect("game installed");

        let managed = |paks: &std::path::Path| -> Vec<String> {
            fs::read_dir(paks)
                .unwrap()
                .filter_map(|e| e.ok())
                .map(|e| e.file_name().to_string_lossy().into_owned())
                .filter(|n| n.contains(&format!("-{MARKER}-")))
                .collect()
        };

        let state = install(slug.clone()).expect("install succeeds");
        assert!(state.installed.iter().any(|m| m.slug == slug));
        let files = managed(&paks);
        assert!(!files.is_empty(), "containers materialized into Paks");
        for f in &files {
            // Every container is the full verified triple.
            let stem = f.rsplit_once('.').unwrap().0;
            for ext in ["pak", "utoc", "ucas"] {
                assert!(
                    paks.join(format!("{stem}.{ext}")).exists(),
                    "{stem}.{ext} must exist"
                );
            }
            assert!(f.contains("_P."), "{f} must carry the patch suffix");
        }
        eprintln!("materialized: {files:?}");

        let conflicts = check_conflicts().expect("conflict check reaches the hub");
        eprintln!("conflicts: {conflicts}");

        let state = set_enabled(slug.clone(), false).expect("disable");
        assert!(managed(&paks).is_empty(), "disabled mod leaves Paks");
        let _ = set_enabled(slug.clone(), true).expect("enable");
        assert!(!managed(&paks).is_empty());

        let _ = uninstall(slug.clone()).expect("uninstall");
        assert!(managed(&paks).is_empty(), "uninstall leaves Paks clean");
        let state_after = load_state();
        assert!(!state_after.installed.iter().any(|m| m.slug == slug));
        drop(state);
    }
}
