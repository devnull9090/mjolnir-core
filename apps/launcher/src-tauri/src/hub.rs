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
use std::sync::{Mutex, OnceLock};

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
    /// The archive hash the hub published, checked at download time.
    pub sha256: String,
    /// Basenames (no extension) of the containers in this release's cache.
    pub containers: Vec<String>,
    /// Fields added after the first shipping format; defaulted so an older
    /// hub_state.json still loads instead of resetting somebody's profiles.
    #[serde(default)]
    pub summary: Option<String>,
    #[serde(default)]
    pub author: Option<String>,
    #[serde(default)]
    pub category: Option<String>,
    /// Unix seconds; the webview formats it.
    #[serde(default)]
    pub installed_at: Option<u64>,
    /// Whether the release carried an Ed25519 signature this launcher
    /// checked against its pinned key. False means hash-pinning only, which
    /// is all a community content upload has.
    #[serde(default)]
    pub signature_verified: bool,
    /// `<container>.<ext>` → SHA-256 of the unpacked file, recorded at
    /// install so a later verify can tell a cache that rotted or was edited
    /// from one that still holds what the hub shipped.
    #[serde(default)]
    pub container_hashes: std::collections::BTreeMap<String, String>,
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

/// Every hub call the webview makes goes through here.
///
/// Not because the webview could not `fetch` — because of what it would have
/// to hold to do it. A paired API key lives in the config directory and is
/// attached in this process; the page never sees it, so a compromised
/// webview cannot read the credential out and use it elsewhere. The webview
/// names a path below /api/v1 and gets status plus body back.
pub fn api(
    method: String,
    path: String,
    body: Option<serde_json::Value>,
) -> Result<serde_json::Value, String> {
    // The webview picks the path, so the path may not pick the host.
    if !path.starts_with('/') || path.starts_with("//") || path.contains("://") {
        return Err(format!("Refusing to call {path}: paths are relative to the hub API"));
    }

    let url = format!("{}{}", hub_api(), path);
    let client = http()?;
    let mut req = match method.to_ascii_uppercase().as_str() {
        "GET" => client.get(&url),
        "POST" => client.post(&url),
        "PUT" => client.put(&url),
        "DELETE" => client.delete(&url),
        other => return Err(format!("Unsupported method {other}")),
    };
    if let Some(auth) = load_auth() {
        req = req.bearer_auth(auth.key);
    }
    if let Some(json) = body {
        req = req.json(&json);
    }

    let resp = req.send().map_err(|e| format!("Cannot reach the hub: {e}"))?;
    let status = resp.status().as_u16();
    let text = resp.text().unwrap_or_default();
    let parsed: serde_json::Value = serde_json::from_str(&text).unwrap_or(serde_json::Value::Null);
    Ok(serde_json::json!({ "status": status, "body": parsed }))
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

fn get_json(url: &str) -> Result<serde_json::Value, String> {
    let resp = http()?.get(url).send().map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("Hub returned {} for {url}", resp.status()));
    }
    resp.json().map_err(|e| e.to_string())
}

#[derive(Debug, Deserialize, Clone)]
struct HubRelease {
    id: String,
    version: String,
    #[serde(default)]
    channel: String,
    #[serde(default)]
    signature: Option<String>,
}

#[derive(Deserialize)]
struct HubReleaseStatus {
    sha256: Option<String>,
    #[serde(default)]
    signature: Option<String>,
    status: String,
}

/// Sort key for a version: numeric components, then whether it is a final
/// release (1.0.0 outranks 1.0.0-beta.1), then the pre-release tag.
fn version_key(v: &str) -> (Vec<u64>, bool, String) {
    let (core, tag) = match v.split_once('-') {
        Some((c, t)) => (c, t.to_string()),
        None => (v, String::new()),
    };
    let parts = core
        .split('.')
        .map(|p| p.parse::<u64>().unwrap_or(0))
        .collect();
    (parts, tag.is_empty(), tag)
}

/// True when `candidate` is strictly newer than `installed`.
fn is_newer(candidate: &str, installed: &str) -> bool {
    version_key(candidate) > version_key(installed)
}

/// The release a plain "install" or "update" should take: the highest
/// stable version, or the highest of anything when a mod has only betas.
fn newest_release(releases: &[HubRelease]) -> Option<&HubRelease> {
    let stable: Vec<&HubRelease> = releases.iter().filter(|r| r.channel != "beta").collect();
    let pool = if stable.is_empty() {
        releases.iter().collect::<Vec<_>>()
    } else {
        stable
    };
    pool.into_iter().max_by(|a, b| {
        version_key(&a.version).cmp(&version_key(&b.version))
    })
}

fn fetch_releases(slug: &str) -> Result<Vec<HubRelease>, String> {
    let value = get_json(&format!("{}/mods/{slug}/releases", hub_api()))?;
    serde_json::from_value(value["releases"].clone()).map_err(|e| e.to_string())
}

/// Check a release signature against the pinned platform key.
///
/// The signature covers the lowercase hex SHA-256 of the archive, so
/// verifying it plus the download hash pins the exact bytes. Community
/// content uploads carry no signature — they are hash-pinned by the hub's
/// scan record instead — but a signature that is *present and wrong* means
/// something is impersonating the platform, and that install is refused.
fn check_release_signature(sha256_hex: &str, signature_b64: &str) -> Result<(), String> {
    let raw = base64_decode(signature_b64.trim()).ok_or("Release signature is not valid base64")?;
    let sig: [u8; 64] = raw
        .as_slice()
        .try_into()
        .map_err(|_| "Release signature is not 64 bytes")?;
    signing_key()?
        .verify_strict(
            sha256_hex.as_bytes(),
            &ed25519_dalek::Signature::from_bytes(&sig),
        )
        .map_err(|_| {
            "Release signature does not verify against this launcher's key. Refusing to install."
                .to_string()
        })
}

/// Install a mod, or a specific release of it, and put it in the active
/// profile's load order.
///
/// Installing over an existing entry — which is what updating is — keeps
/// that entry's position and enabled flag: an update must not silently
/// reorder a profile the player tuned, and must not re-enable something
/// they turned off.
///
/// Nothing permanent happens until the bytes prove they are the bytes the
/// hub described: the archive is hashed against the release record, and any
/// signature the release carries is checked against the pinned key.
pub fn install(slug: String, release_id: Option<String>) -> Result<HubState, String> {
    let client = http()?;
    let api = hub_api();

    let mod_page = get_json(&format!("{api}/mods/{slug}"))?;
    let name = mod_page["name"].as_str().unwrap_or(&slug).to_string();
    let mod_type = mod_page["type"].as_str().unwrap_or("content");
    if mod_type != "content" {
        return Err(format!(
            "{name} is a {mod_type} mod — it executes code, so it installs from the \
             signed set under Code mods, not from a hub archive."
        ));
    }

    let releases = fetch_releases(&slug)?;
    let release = match &release_id {
        Some(id) => releases
            .iter()
            .find(|r| &r.id == id)
            .cloned()
            .ok_or("That release is not published")?,
        None => newest_release(&releases)
            .cloned()
            .ok_or("This mod has no published releases")?,
    };

    let status: HubReleaseStatus =
        serde_json::from_value(get_json(&format!("{api}/releases/{}", release.id))?)
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
    let signature = status.signature.or(release.signature.clone());
    let signature_verified = match &signature {
        Some(sig) if !sig.is_empty() => {
            check_release_signature(&expected, sig)?;
            true
        }
        _ => false,
    };

    // Unpack the containers into this release's cache.
    let release_cache = cache_dir().join(&release.id);
    let _ = fs::remove_dir_all(&release_cache);
    fs::create_dir_all(&release_cache).map_err(|e| e.to_string())?;

    let mut zip = zip::ZipArchive::new(std::io::Cursor::new(bytes)).map_err(|e| e.to_string())?;
    let mut containers = Vec::new();
    let mut container_hashes = std::collections::BTreeMap::new();
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
        container_hashes.insert(format!("{stem}.{ext}"), sha256_hex(&data));
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
    // Replacing an install leaves the previous release's cache behind;
    // clear it so updating does not grow the cache without bound.
    if let Some(previous) = state.installed.iter().find(|m| m.slug == slug) {
        if previous.release_id != release.id {
            let _ = fs::remove_dir_all(cache_dir().join(&previous.release_id));
        }
    }
    state.installed.retain(|m| m.slug != slug);
    state.installed.push(InstalledHubMod {
        slug: slug.clone(),
        name,
        release_id: release.id,
        version: release.version,
        sha256: expected,
        containers,
        summary: mod_page["summary"].as_str().map(str::to_string),
        author: mod_page["author"].as_str().map(str::to_string),
        category: mod_page["category"].as_str().map(str::to_string),
        installed_at: Some(now_unix()),
        signature_verified,
        container_hashes,
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

fn now_unix() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

// ─── Updates ────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
pub struct UpdateInfo {
    pub slug: String,
    pub name: String,
    pub installed_version: String,
    pub latest_version: String,
    pub latest_release_id: String,
    pub channel: String,
    pub changelog: Option<String>,
}

/// What the hub has that is newer than what is installed.
///
/// One request per installed mod, which is fine at the scale a profile
/// reaches, and it keeps the answer honest — the hub decides what "newest"
/// means for a mod, not a cached listing.
pub fn check_updates() -> Result<Vec<UpdateInfo>, String> {
    let state = load_state();
    let mut out = Vec::new();
    for inst in &state.installed {
        let releases = match fetch_releases(&inst.slug) {
            Ok(r) => r,
            // One unreachable or deleted mod must not hide every other
            // update; skip it and report the rest.
            Err(_) => continue,
        };
        let Some(latest) = newest_release(&releases) else {
            continue;
        };
        if is_newer(&latest.version, &inst.version) {
            let detail = get_json(&format!("{}/releases/{}", hub_api(), latest.id)).ok();
            out.push(UpdateInfo {
                slug: inst.slug.clone(),
                name: inst.name.clone(),
                installed_version: inst.version.clone(),
                latest_version: latest.version.clone(),
                latest_release_id: latest.id.clone(),
                channel: latest.channel.clone(),
                changelog: detail
                    .as_ref()
                    .and_then(|d| d["changelog_md"].as_str())
                    .map(str::to_string),
            });
        }
    }
    Ok(out)
}

// ─── Integrity of what is on disk ───────────────────────────────────────

#[derive(Debug, Serialize)]
pub struct VerifiedMod {
    pub slug: String,
    pub ok: bool,
    /// Cache files whose bytes no longer hash to what was installed.
    pub tampered: Vec<String>,
    pub missing: Vec<String>,
    pub signature_verified: bool,
}

/// Re-hash every cached container against what was recorded at install.
///
/// The download check proves the bytes were right when they arrived; this
/// proves they still are. Anything that edits the cache afterwards — a
/// half-finished write, a disk fault, another program — shows up here
/// rather than as a game that crashes for no visible reason.
pub fn verify_installed() -> Vec<VerifiedMod> {
    let state = load_state();
    state
        .installed
        .iter()
        .map(|inst| {
            let dir = cache_dir().join(&inst.release_id);
            let mut tampered = Vec::new();
            let mut missing = Vec::new();
            for (file, expected) in &inst.container_hashes {
                match fs::read(dir.join(file)) {
                    Ok(bytes) if sha256_hex(&bytes) == *expected => {}
                    Ok(_) => tampered.push(file.clone()),
                    Err(_) => missing.push(file.clone()),
                }
            }
            VerifiedMod {
                slug: inst.slug.clone(),
                ok: tampered.is_empty() && missing.is_empty(),
                tampered,
                missing,
                signature_verified: inst.signature_verified,
            }
        })
        .collect()
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

// ─── Identity: pairing this launcher with a hub account ─────────────────
//
// The launcher has no browser session and will never ask for a Discord
// password. It pairs the way a TV app does: ask the hub for a handshake,
// show the short code, let the user approve it at mjolnircore.com/link in a
// real browser, then collect a scoped API key on the next poll.
//
// The key is stored in the launcher's config directory and only ever leaves
// this process as an Authorization header — see `api` above. It carries
// mods:read, ratings:write and comments:write; it cannot publish anything.

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct HubUser {
    pub id: String,
    pub username: String,
    pub display_name: Option<String>,
    pub avatar_url: Option<String>,
    pub role: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct StoredAuth {
    key: String,
    user: HubUser,
}

fn auth_path() -> PathBuf {
    config_dir().join("hub_auth.json")
}

fn load_auth() -> Option<StoredAuth> {
    fs::read_to_string(auth_path())
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
}

fn save_auth(auth: &StoredAuth) -> Result<(), String> {
    fs::create_dir_all(config_dir()).map_err(|e| e.to_string())?;
    fs::write(
        auth_path(),
        serde_json::to_string_pretty(auth).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())
}

/// The pairing in flight. Held in memory, not on disk: an interrupted
/// pairing should die with the process rather than linger as a credential
/// waiting to be collected.
fn pending_device() -> &'static Mutex<Option<String>> {
    static PENDING: OnceLock<Mutex<Option<String>>> = OnceLock::new();
    PENDING.get_or_init(|| Mutex::new(None))
}

/// Who this launcher is signed in as, without ever handing out the key.
pub fn auth_status() -> Option<HubUser> {
    load_auth().map(|a| a.user)
}

/// Begin pairing: returns the code to show and the page to open.
pub fn auth_start() -> Result<serde_json::Value, String> {
    let resp = http()?
        .post(format!("{}/auth/device/start", hub_api()))
        .json(&serde_json::json!({ "client_name": "MJOLNIR Launcher" }))
        .send()
        .map_err(|e| format!("Cannot reach the hub: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("Hub returned {}", resp.status()));
    }
    let body: serde_json::Value = resp.json().map_err(|e| e.to_string())?;
    let device_code = body["device_code"]
        .as_str()
        .ok_or("Hub did not return a device code")?
        .to_string();
    *pending_device().lock().map_err(|e| e.to_string())? = Some(device_code);

    let user_code = body["user_code"].as_str().unwrap_or_default();
    Ok(serde_json::json!({
        "user_code": user_code,
        // Prefilled so approving is a click, not a transcription.
        "verification_url": format!(
            "{}?code={}",
            body["verification_url"].as_str().unwrap_or("https://mjolnircore.com/link"),
            urlencode(user_code),
        ),
        "interval": body["interval"].as_u64().unwrap_or(3),
        "expires_in": body["expires_in"].as_u64().unwrap_or(600),
    }))
}

/// Poll the pairing started by `auth_start`. On approval the key is stored
/// and the signed-in user returned; the webview never sees the key.
pub fn auth_poll() -> Result<serde_json::Value, String> {
    let device_code = pending_device()
        .lock()
        .map_err(|e| e.to_string())?
        .clone()
        .ok_or("No pairing in progress")?;

    let resp = http()?
        .post(format!("{}/auth/device/token", hub_api()))
        .json(&serde_json::json!({ "device_code": device_code }))
        .send()
        .map_err(|e| format!("Cannot reach the hub: {e}"))?;
    if !resp.status().is_success() {
        return Err(format!("Hub returned {}", resp.status()));
    }
    let body: serde_json::Value = resp.json().map_err(|e| e.to_string())?;
    let status = body["status"].as_str().unwrap_or("pending").to_string();

    if status == "approved" {
        let key = body["key"]
            .as_str()
            .ok_or("Approved, but the hub sent no key. Start pairing again.")?
            .to_string();
        let user: HubUser =
            serde_json::from_value(body["user"].clone()).map_err(|e| e.to_string())?;
        save_auth(&StoredAuth {
            key,
            user: user.clone(),
        })?;
        *pending_device().lock().map_err(|e| e.to_string())? = None;
        return Ok(serde_json::json!({ "status": status, "user": user }));
    }
    if status == "denied" || status == "expired" {
        *pending_device().lock().map_err(|e| e.to_string())? = None;
    }
    Ok(serde_json::json!({ "status": status }))
}

/// Forget the paired key locally. The key itself stays valid until it is
/// revoked at mjolnircore.com/account/keys — this launcher cannot revoke it,
/// because a credential that can revoke credentials is a bigger credential.
pub fn sign_out() -> Result<(), String> {
    let _ = fs::remove_file(auth_path());
    *pending_device().lock().map_err(|e| e.to_string())? = None;
    Ok(())
}

// ─── Signed code mods ───────────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct CodeModEntry {
    pub id: String,
    pub file: String,
    pub sha256: String,
    pub size: u64,
    pub url: String,
    /// Per-mod fields; defaulted so a launcher can read older manifests.
    #[serde(default)]
    pub version: String,
    #[serde(default)]
    pub summary: String,
    #[serde(default)]
    pub category: String,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct CodeModsManifest {
    pub schema_version: u32,
    pub set_version: String,
    pub mods: Vec<CodeModEntry>,
}

/// What the bytes on disk are actually worth.
///
/// Membership in the signed set is a property of *content*, not of a folder
/// name — anyone can create `Mods/MJOLNIRFlyCam`. So the launcher records a
/// digest of the tree it extracted and re-computes it on every status call.
#[derive(Debug, Serialize, PartialEq, Eq, Clone, Copy)]
#[serde(rename_all = "snake_case")]
pub enum Integrity {
    /// No directory for this mod.
    NotInstalled,
    /// On disk and byte-identical to what this launcher installed.
    Verified,
    /// On disk, but the tree no longer hashes to the recorded digest.
    Modified,
    /// On disk with no digest on record — shipped by the modpack, or
    /// installed by a launcher too old to have recorded one. Not a claim of
    /// authenticity in either direction.
    Unverified,
}

#[derive(Debug, Serialize)]
pub struct CodeModRow {
    #[serde(flatten)]
    pub entry: CodeModEntry,
    /// What this launcher last installed, when it did.
    pub installed_version: Option<String>,
    pub update_available: bool,
    pub integrity: Integrity,
}

#[derive(Debug, Serialize)]
pub struct CodeModsStatus {
    pub set_version: String,
    /// True iff manifest.json.sig verifies against the compiled-in key.
    pub signature_verified: bool,
    pub mods: Vec<CodeModRow>,
}

/// id → what this launcher installed, kept in the config dir. A mod
/// directory that exists without a record (shipped by the old monolithic
/// modpack) counts as installed at an unknown version.
fn installed_versions_path() -> PathBuf {
    config_dir().join("code_mods_installed.json")
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct InstallRecord {
    pub version: String,
    /// Digest of the mod's file tree as it stood immediately after install.
    /// Empty for records written before content verification existed.
    #[serde(default)]
    pub tree_sha256: String,
}

/// Records used to be a bare version string. Read both shapes so upgrading
/// the launcher does not silently forget what is installed.
#[derive(Deserialize)]
#[serde(untagged)]
enum RawRecord {
    Legacy(String),
    Full(InstallRecord),
}

impl From<RawRecord> for InstallRecord {
    fn from(raw: RawRecord) -> Self {
        match raw {
            RawRecord::Legacy(version) => InstallRecord {
                version,
                tree_sha256: String::new(),
            },
            RawRecord::Full(rec) => rec,
        }
    }
}

fn load_installed_versions() -> std::collections::HashMap<String, InstallRecord> {
    fs::read_to_string(installed_versions_path())
        .ok()
        .and_then(|s| serde_json::from_str::<std::collections::HashMap<String, RawRecord>>(&s).ok())
        .unwrap_or_default()
        .into_iter()
        .map(|(k, v)| (k, v.into()))
        .collect()
}

fn save_installed_version(id: &str, version: &str, tree_sha256: &str) -> Result<(), String> {
    let mut map = load_installed_versions();
    map.insert(
        id.to_string(),
        InstallRecord {
            version: version.to_string(),
            tree_sha256: tree_sha256.to_string(),
        },
    );
    fs::create_dir_all(config_dir()).map_err(|e| e.to_string())?;
    fs::write(
        installed_versions_path(),
        serde_json::to_string_pretty(&map).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())
}

/// A digest over a mod's whole directory: every file's path *and* content,
/// in a fixed order, so neither renaming, adding nor editing a file can slip
/// past. Paths are recorded relative to the mod root with `/` separators, so
/// the digest does not change with the install location.
fn tree_digest(dir: &std::path::Path) -> Result<String, String> {
    fn walk(
        root: &std::path::Path,
        dir: &std::path::Path,
        out: &mut Vec<(String, String)>,
    ) -> Result<(), String> {
        let entries = fs::read_dir(dir).map_err(|e| format!("{}: {e}", dir.display()))?;
        for entry in entries {
            let entry = entry.map_err(|e| e.to_string())?;
            let path = entry.path();
            let kind = entry.file_type().map_err(|e| e.to_string())?;
            if kind.is_dir() {
                walk(root, &path, out)?;
            } else if kind.is_file() {
                let rel = path
                    .strip_prefix(root)
                    .map_err(|e| e.to_string())?
                    .to_string_lossy()
                    .replace('\\', "/");
                let bytes = fs::read(&path).map_err(|e| format!("{}: {e}", path.display()))?;
                out.push((rel, sha256_hex(&bytes)));
            }
            // Symlinks are neither followed nor hashed: a link is not content,
            // and following one would let a mod dir reach outside itself.
        }
        Ok(())
    }

    let mut files = Vec::new();
    walk(dir, dir, &mut files)?;
    files.sort();

    let mut hasher = Sha256::new();
    for (rel, hash) in &files {
        hasher.update(rel.as_bytes());
        hasher.update([0]);
        hasher.update(hash.as_bytes());
        hasher.update([b'\n']);
    }
    Ok(hex::encode(hasher.finalize()))
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

/// Verify a detached base64 Ed25519 signature over `bytes` against the key
/// compiled into this binary.
///
/// Shared with the runtime installer: the runtime bundle carries a DLL that
/// gets injected into the game process, so it is signed by the same key and
/// checked by the same code as the Lua mods.
pub fn verify_signature(bytes: &[u8], sig_b64: &str) -> Result<bool, String> {
    let sig_bytes = base64_decode(sig_b64.trim()).ok_or("Signature is not valid base64")?;
    let sig: [u8; 64] = sig_bytes
        .as_slice()
        .try_into()
        .map_err(|_| "Signature is not 64 bytes")?;
    Ok(signing_key()?
        .verify_strict(bytes, &ed25519_dalek::Signature::from_bytes(&sig))
        .is_ok())
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

    let verified = verify_signature(&manifest_bytes, &sig_b64)?;

    let manifest: CodeModsManifest =
        serde_json::from_slice(&manifest_bytes).map_err(|e| format!("Bad manifest: {e}"))?;

    let mods_dir = crate::find_game_install()
        .map(|(p, _)| p.join("Meteorite/Binaries/Win64/ue4ss/Mods"));
    let versions = load_installed_versions();
    let mods = manifest
        .mods
        .into_iter()
        .map(|entry| {
            let dir = mods_dir.as_ref().map(|d| d.join(&entry.id));
            let present = dir.as_ref().is_some_and(|d| d.is_dir());
            let record = versions.get(&entry.id);
            let installed_version = if present {
                Some(record.map(|r| r.version.clone()).unwrap_or_default())
            } else {
                None
            };
            let update_available = matches!(
                &installed_version,
                Some(v) if *v != entry.version
            );
            // The badge is a claim about bytes, so it is decided by bytes. A
            // directory carrying the right name but the wrong contents reads
            // as modified, not as signed.
            let integrity = match (present, record) {
                (false, _) => Integrity::NotInstalled,
                (true, Some(r)) if !r.tree_sha256.is_empty() => {
                    let dir = dir.as_ref().expect("present implies a path");
                    match tree_digest(dir) {
                        Ok(actual) if actual == r.tree_sha256 => Integrity::Verified,
                        // An unreadable tree is not a passing tree.
                        _ => Integrity::Modified,
                    }
                }
                (true, _) => Integrity::Unverified,
            };
            CodeModRow {
                entry,
                installed_version,
                update_available,
                integrity,
            }
        })
        .collect();

    Ok(CodeModsStatus {
        set_version: manifest.set_version,
        signature_verified: verified,
        mods,
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
        .map(|m| &m.entry)
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

    // Remember what shipped, so the next status can tell "installed" from
    // "installed but the set moved on" — and hash the tree as extracted, so
    // it can also tell "installed" from "installed, then edited". The digest
    // covers the directory rather than the zip, which means leftovers from
    // an earlier modpack are part of what gets verified.
    let tree = tree_digest(&mods_dir.join(&id))?;
    save_installed_version(&id, &entry.version, &tree)?;
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

    /// The whole point of the digest: a folder name is not evidence. Editing
    /// a file, adding one, or renaming one must all move the hash.
    #[test]
    fn the_tree_digest_covers_content_and_layout() {
        let root = std::env::temp_dir().join(format!("mjolnir-tree-{}", std::process::id()));
        let scripts = root.join("Scripts");
        fs::create_dir_all(&scripts).unwrap();
        fs::write(scripts.join("main.lua"), b"print('hi')").unwrap();
        let base = tree_digest(&root).unwrap();

        fs::write(scripts.join("main.lua"), b"print('pwned')").unwrap();
        assert_ne!(base, tree_digest(&root).unwrap(), "edited file must show");

        fs::write(scripts.join("main.lua"), b"print('hi')").unwrap();
        assert_eq!(base, tree_digest(&root).unwrap(), "restored file must match");

        fs::write(scripts.join("extra.lua"), b"").unwrap();
        assert_ne!(base, tree_digest(&root).unwrap(), "added file must show");
        fs::remove_file(scripts.join("extra.lua")).unwrap();

        fs::rename(scripts.join("main.lua"), scripts.join("other.lua")).unwrap();
        assert_ne!(base, tree_digest(&root).unwrap(), "renamed file must show");

        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn install_records_read_both_the_old_and_new_shape() {
        let legacy: std::collections::HashMap<String, RawRecord> =
            serde_json::from_str(r#"{"MJOLNIRFlyCam":"1.0.0"}"#).unwrap();
        let rec: InstallRecord = legacy.into_iter().next().unwrap().1.into();
        assert_eq!(rec.version, "1.0.0");
        assert!(
            rec.tree_sha256.is_empty(),
            "a legacy record claims no digest, so it must verify as unverified rather than pass"
        );

        let modern: std::collections::HashMap<String, RawRecord> =
            serde_json::from_str(r#"{"MJOLNIRFlyCam":{"version":"1.0.0","tree_sha256":"ab"}}"#)
                .unwrap();
        let rec: InstallRecord = modern.into_iter().next().unwrap().1.into();
        assert_eq!((rec.version.as_str(), rec.tree_sha256.as_str()), ("1.0.0", "ab"));
    }

    /// The runtime installer gates a DLL injection on this returning false,
    /// so it must reject rather than error-out-into-success on junk.
    #[test]
    fn signature_verification_rejects_what_it_should() {
        let manifest = br#"{"version":"1.0.0"}"#;
        // Right shape, wrong signature.
        let bogus = "A".repeat(86) + "==";
        assert_eq!(
            verify_signature(manifest, &bogus),
            Ok(false),
            "a well-formed but incorrect signature must verify as false"
        );
        // Wrong shape at all.
        assert!(verify_signature(manifest, "not base64!!").is_err());
        assert!(
            verify_signature(manifest, "YWJj").is_err(),
            "a signature that is not 64 bytes must be an error, not a pass"
        );
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

    #[test]
    fn versions_compare_numerically_not_lexically() {
        assert!(is_newer("1.10.0", "1.9.0"), "10 > 9, not '10' < '9'");
        assert!(is_newer("2.0.0", "1.99.99"));
        assert!(!is_newer("1.0.0", "1.0.0"));
        assert!(!is_newer("1.0.0", "1.0.1"));
        // A final release outranks its own pre-releases.
        assert!(is_newer("1.0.0", "1.0.0-beta.2"));
        assert!(!is_newer("1.0.0-beta.2", "1.0.0"));
    }

    fn release(id: &str, version: &str, channel: &str) -> HubRelease {
        HubRelease {
            id: id.into(),
            version: version.into(),
            channel: channel.into(),
            signature: None,
        }
    }

    #[test]
    fn newest_release_prefers_stable_over_a_higher_beta() {
        let releases = vec![
            release("a", "1.0.0", "stable"),
            release("b", "1.1.0", "beta"),
            release("c", "0.9.0", "stable"),
        ];
        assert_eq!(newest_release(&releases).unwrap().id, "a");
    }

    #[test]
    fn newest_release_falls_back_to_beta_only_mods() {
        let releases = vec![release("a", "0.1.0", "beta"), release("b", "0.2.0", "beta")];
        assert_eq!(newest_release(&releases).unwrap().id, "b");
        assert!(newest_release(&[]).is_none());
    }

    #[test]
    fn the_api_proxy_refuses_to_be_pointed_at_another_host() {
        // The webview chooses the path; it must not get to choose the host,
        // because this is the call that attaches the paired API key.
        for path in [
            "https://evil.example/steal",
            "//evil.example/steal",
            "mods",
            "http://localhost:9/x",
        ] {
            let err = api("GET".into(), path.into(), None).unwrap_err();
            assert!(
                err.contains("relative to the hub API"),
                "{path} must be rejected before any request, got: {err}"
            );
        }
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

        let state = install(slug.clone(), None).expect("install succeeds");
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
