//! Hub integration: browse and install content mods, keep profiles with a
//! load order, and install the Ed25519-signed code-mod set.
//!
//! Content mods arrive as `.mjolnir` archives from mjolnircore.com. Installing
//! one downloads it, checks its SHA-256 against what the hub recorded at scan
//! time, and unpacks its IoStore containers into a local cache. A *profile*
//! decides what actually reaches the game: materializing writes each enabled
//! container into `Meteorite/Content/Paks` as the verified override triple —
//! stub `.pak` (an empty archive written by `ue_iostore::pak`; a bare
//! `.utoc`/`.ucas` pair does not mount, see docs/iostore_packaging.md),
//! `.utoc`, `.ucas` — named `pakchunk9NN-MJOLNIRHUB-<slug>…_P`.
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

use std::collections::BTreeSet;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
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
    /// Fingerprint of the author key whose signature this launcher verified
    /// against the archive contents. The pin: a later install of the same
    /// mod under a different key raises `signature_notice`.
    #[serde(default)]
    pub signer_fingerprint: Option<String>,
    /// Hub account id that published the installed release.
    #[serde(default)]
    pub published_by: Option<String>,
    /// A trust observation worth keeping in front of the user: the signing
    /// key changed, disappeared, or was revoked. None when all is well.
    #[serde(default)]
    pub signature_notice: Option<String>,
    /// The scenario codename when this is a map pack; its `map/` data sits
    /// in the release cache beside the containers.
    #[serde(default)]
    pub map_code: Option<String>,
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
    let (install, _) =
        crate::find_game_install().ok_or("Game not found. Install Halo Campaign Evolved first.")?;
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

pub(crate) fn sha256_hex(bytes: &[u8]) -> String {
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

/// The chunk number a container has to keep in its file name, when it has
/// one to keep. UE opens a mounted pak's shader library by the number it
/// reads off the file name (`pakchunk988…` opens
/// `ShaderArchive-Meteorite_Chunk988-…`; ShaderCodeLibrary.cpp,
/// `OnPakFileMounted`), so a container carrying a shader library renamed to
/// its load-order number would mount with none of its shaders. The CE
/// runtime pack's material masters are one. Everything else takes its
/// number from the load order.
fn shader_chunk(stem: &str, utoc: &Path) -> Option<usize> {
    let digits: String = stem
        .strip_prefix("pakchunk")?
        .chars()
        .take_while(|c| c.is_ascii_digit())
        .collect();
    let number: usize = digits.parse().ok()?;
    let toc = ue_iostore::toc::Toc::read(utoc).ok()?;
    // Chunk type 8 is ShaderCodeLibrary (ue_iostore::chunk_type_name).
    toc.chunk_ids.iter().any(|c| c.kind == 8).then_some(number)
}

/// One container the active profile mounts: where the cache holds it, and
/// the name it takes in Paks.
struct Mount {
    slug: String,
    /// The release cache directory.
    cache: PathBuf,
    /// The container's basename in the cache.
    container: String,
    /// `pakchunk<n>-MJOLNIRHUB-<slug>-<j>_P`, its basename in Paks.
    base: String,
}

impl Mount {
    fn cached(&self, ext: &str) -> PathBuf {
        self.cache.join(format!("{}.{ext}", self.container))
    }

    fn in_paks(&self, paks: &Path, ext: &str) -> PathBuf {
        paks.join(format!("{}.{ext}", self.base))
    }
}

/// Every container the active profile mounts, in load order.
fn mounts(state: &HubState) -> Result<Vec<Mount>, String> {
    let profile = state
        .profiles
        .iter()
        .find(|p| p.name == state.active)
        .ok_or("Active profile missing")?;

    let mut out = Vec::new();
    for (i, entry) in profile.entries.iter().filter(|e| e.enabled).enumerate() {
        let inst = state
            .installed
            .iter()
            .find(|m| m.slug == entry.slug)
            .ok_or_else(|| format!("{} is in the profile but not installed", entry.slug))?;
        let release_cache = cache_dir().join(&inst.release_id);
        for (j, container) in inst.containers.iter().enumerate() {
            let number = shader_chunk(container, &release_cache.join(format!("{container}.utoc")))
                .unwrap_or_else(|| order_number(i));
            out.push(Mount {
                slug: inst.slug.clone(),
                cache: release_cache.clone(),
                container: container.clone(),
                base: format!("pakchunk{number}-{MARKER}-{}-{j}_P", sanitize(&inst.slug)),
            });
        }
    }
    Ok(out)
}

/// Make the Paks directory agree with the active profile: remove every
/// container this module owns, then write back the enabled ones in order.
fn materialize(state: &HubState) -> Result<(), String> {
    let paks = paks_dir()?;
    let mounts = mounts(state)?;

    for entry in fs::read_dir(&paks).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        let name = entry.file_name().to_string_lossy().into_owned();
        if name.contains(&format!("-{MARKER}-")) {
            fs::remove_file(entry.path())
                .map_err(|e| format!("Cannot remove {name}: {e}. Is the game running?"))?;
        }
    }

    for m in &mounts {
        for ext in ["utoc", "ucas"] {
            let copied = fs::copy(m.cached(ext), m.in_paks(&paks, ext))
                .map_err(|e| format!("{}: {e}", m.slug))?;
            crate::transfer::wrote(copied);
        }
        // A container without a `.pak` sibling is never discovered, so an
        // empty one rides along.
        fs::write(m.in_paks(&paks, "pak"), ue_iostore::pak::stub_for(&m.base))
            .map_err(|e| format!("{}: {e}", m.slug))?;
    }

    sync_maps(state, &paks)
}

/// Whether a release's cache still holds everything the install recorded.
/// The state file says what was installed; this says whether it still is.
fn cache_complete(inst: &InstalledHubMod) -> bool {
    let dir = cache_dir().join(&inst.release_id);
    let containers = inst.containers.iter().all(|c| {
        dir.join(format!("{c}.utoc")).is_file() && dir.join(format!("{c}.ucas")).is_file()
    });
    containers && (inst.map_code.is_none() || dir.join("map").is_dir())
}

/// The mods with a container missing from Paks. Presence, not content: a
/// container replaced by hand (a test build of the same chunk) is the
/// player's to keep, and the cache's own hashes are `verify_installed`'s.
fn paks_gaps(mounts: &[Mount], paks: &Path) -> BTreeSet<String> {
    mounts
        .iter()
        .filter(|m| !["utoc", "ucas", "pak"].iter().all(|ext| m.in_paks(paks, ext).is_file()))
        .map(|m| m.slug.clone())
        .collect()
}

/// Files in Paks carrying this module's marker that `materialize` would not
/// write: left over from a profile change that did not finish.
fn paks_strays(mounts: &[Mount], paks: &Path) -> Result<Vec<String>, String> {
    let expected: BTreeSet<String> = mounts
        .iter()
        .flat_map(|m| ["utoc", "ucas", "pak"].map(|ext| format!("{}.{ext}", m.base)))
        .collect();
    let mut strays = Vec::new();
    for entry in fs::read_dir(paks).map_err(|e| e.to_string())? {
        let name = entry.map_err(|e| e.to_string())?.file_name().to_string_lossy().into_owned();
        if name.contains(&format!("-{MARKER}-")) && !expected.contains(&name) {
            strays.push(name);
        }
    }
    Ok(strays)
}

/// Installed mods whose files are not all there: the release cache lost
/// them, or Paks lost its copy of a mod the active profile mounts. The
/// Multiplayer page reads these as not installed, so deleting a map's
/// containers by hand offers the install again instead of claiming it is
/// current.
pub fn missing_files() -> Result<Vec<String>, String> {
    let state = load_state();
    let mut missing: BTreeSet<String> = state
        .installed
        .iter()
        .filter(|m| !cache_complete(m))
        .map(|m| m.slug.clone())
        .collect();
    if !state.installed.is_empty() {
        missing.extend(paks_gaps(&mounts(&state)?, &paks_dir()?));
    }
    Ok(missing.into_iter().collect())
}

/// The enabled maps' data in `MJOLNIRMaps`, and the registration that lists
/// them (`maps::sync`).
fn sync_maps(state: &HubState, paks: &Path) -> Result<(), String> {
    let profile = state
        .profiles
        .iter()
        .find(|p| p.name == state.active)
        .ok_or("Active profile missing")?;
    let maps: Vec<crate::maps::Enabled> = profile
        .entries
        .iter()
        .filter(|e| e.enabled)
        .filter_map(|entry| state.installed.iter().find(|m| m.slug == entry.slug))
        .filter_map(|inst| {
            inst.map_code.as_ref().map(|code| crate::maps::Enabled {
                code: code.clone(),
                data: cache_dir().join(&inst.release_id).join("map"),
            })
        })
        .collect();
    crate::maps::sync(paks, &maps).map_err(|e| format!("Registering maps: {e}"))?;
    Ok(())
}

/// What a launch runs. Paks is put back the way the launcher's state says it
/// should be, so containers deleted or replaced by hand come back; when
/// nothing is out of place only the registration is rebuilt (a game update
/// replaces the tables it was built from), and no containers are copied.
pub fn prepare_launch() -> Result<(), String> {
    let state = load_state();
    if state.installed.is_empty() {
        return Ok(());
    }
    let paks = paks_dir()?;
    let mounts = mounts(&state)?;

    // `materialize` clears Paks before it copies, so a cache that cannot
    // supply its containers would take every mod after it down too. Leave
    // Paks alone and say which mod needs reinstalling.
    let uncached: BTreeSet<&str> = mounts
        .iter()
        .filter(|m| !m.cached("utoc").is_file() || !m.cached("ucas").is_file())
        .map(|m| m.slug.as_str())
        .collect();
    if !uncached.is_empty() {
        sync_maps(&state, &paks)?;
        return Err(format!(
            "The launcher's cache lost files for {}; reinstall to restore them",
            uncached.into_iter().collect::<Vec<_>>().join(", ")
        ));
    }

    if paks_gaps(&mounts, &paks).is_empty() && paks_strays(&mounts, &paks)?.is_empty() {
        sync_maps(&state, &paks)
    } else {
        materialize(&state)
    }
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
        return Err(format!(
            "Refusing to call {path}: paths are relative to the hub API"
        ));
    }

    let url = format!("{}{}", hub_api(), path);
    let client = http()?;
    let mut req = match method.to_ascii_uppercase().as_str() {
        "GET" => client.get(&url),
        "POST" => client.post(&url),
        "PUT" => client.put(&url),
        "PATCH" => client.patch(&url),
        "DELETE" => client.delete(&url),
        other => return Err(format!("Unsupported method {other}")),
    };
    if let Some(auth) = load_auth() {
        req = req.bearer_auth(auth.key);
    }
    if let Some(json) = body {
        req = req.json(&json);
    }

    let resp = req
        .send()
        .map_err(|e| format!("Cannot reach the hub: {e}"))?;
    let status = resp.status().as_u16();
    let text = resp.text().unwrap_or_default();
    let parsed: serde_json::Value = serde_json::from_str(&text).unwrap_or(serde_json::Value::Null);
    Ok(serde_json::json!({ "status": status, "body": parsed }))
}

fn urlencode(s: &str) -> String {
    s.bytes()
        .map(|b| match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' => (b as char).to_string(),
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
    #[serde(default)]
    published_by: Option<String>,
    #[serde(default)]
    signer_fingerprint: Option<String>,
    #[serde(default)]
    signer_key_revoked: Option<bool>,
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
    pool.into_iter()
        .max_by(|a, b| version_key(&a.version).cmp(&version_key(&b.version)))
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
    install_one(&slug, release_id, 0)?;
    let state = load_state();
    materialize(&state)?;
    Ok(state)
}

/// How far dependencies may chain. A map needs the CE runtime pack, which
/// needs nothing; anything deeper is a loop or a mistake.
const MAX_DEP_DEPTH: usize = 3;

/// The code mods a map plays through: the loader that starts it, the lobby
/// that offers it, the HUD, and the library they all load. A map pack names
/// none of them; its type implies them (docs/map_distribution.md).
const MAP_CODE_MODS: &[&str] = &[
    "MJOLNIRCore",
    "MJOLNIRLevelLoader",
    "MJOLNIRLobby",
    "MJOLNIRHud",
];

/// A map pack's own part, read from the archive.
struct MapData {
    code: String,
    level: Vec<u8>,
    registration: Vec<u8>,
}

fn read_map(
    manifest: &serde_json::Value,
    members: &[(String, Vec<u8>)],
) -> Result<MapData, String> {
    let code = manifest
        .pointer("/map/code")
        .and_then(|v| v.as_str())
        .ok_or("The map pack's mjolnir.json has no map.code")?
        .to_string();
    if !crate::maps::valid_code(&code) {
        return Err(format!("{code:?} is not a map code"));
    }
    let member = |path: &str| {
        members
            .iter()
            .find(|(p, _)| p == path)
            .map(|(_, b)| b.clone())
            .ok_or_else(|| format!("The map pack has no {path}"))
    };
    let level = member("map/level.json")?;
    let registration = member("map/registration.json")?;
    let record: blam_pack::scenario::Registration =
        serde_json::from_slice(&registration).map_err(|e| format!("map/registration.json: {e}"))?;
    if record.code != code {
        return Err(format!(
            "map/registration.json registers {}, but the pack is {code}",
            record.code
        ));
    }
    serde_json::from_slice::<serde_json::Value>(&level)
        .map_err(|e| format!("map/level.json: {e}"))?;
    Ok(MapData {
        code,
        level,
        registration,
    })
}

/// Install (or update) one mod into the cache and the state, with whatever
/// it depends on. Materializing is the caller's, once, after everything.
fn install_one(slug: &str, release_id: Option<String>, depth: usize) -> Result<(), String> {
    install_one_as(slug, release_id, depth, None)
}

/// [`install_one`], or with `live` the install a running game asked for
/// ([`install_live`]): its download reports progress, and nothing it needs
/// may change under the game — no code mod is installed or updated (their
/// DLLs are loaded), and a missing dependency is an error rather than an
/// install (the runtime pack's containers are mounted).
fn install_one_as(
    slug: &str,
    release_id: Option<String>,
    depth: usize,
    live: Option<&Live>,
) -> Result<(), String> {
    let client = http()?;
    let api = hub_api();
    let slug = slug.to_string();

    let mod_page = get_json(&format!("{api}/mods/{slug}"))?;
    let name = mod_page["name"].as_str().unwrap_or(&slug).to_string();
    let mod_type = mod_page["type"].as_str().unwrap_or("content");
    if mod_type != "content" && mod_type != "map" {
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
    //
    // The paired key rides along when there is one. The endpoint is public
    // and works without it — this is what lets the hub attribute the install
    // to the account, which is what a profile's "mods downloaded" counts.
    // Unpaired, the download is still counted, just not to anybody.
    let mut request = client.get(format!("{api}/releases/{}/download", release.id));
    if let Some(auth) = load_auth() {
        request = request.bearer_auth(auth.key);
    }
    let resp = request.send().map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("Download failed: {}", resp.status()));
    }
    let total = resp.content_length();
    let bytes = crate::transfer::read_body(resp, total, |got| {
        if let Some(live) = live {
            (live.progress)(got, total.or(live.size));
        }
    })
    .map_err(|e| e.to_string())?;
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

    // One pass over the archive: every member is read so the author
    // signature can be checked against the complete contents, then the
    // containers are written from the same bytes.
    let mut zip = zip::ZipArchive::new(std::io::Cursor::new(bytes)).map_err(|e| e.to_string())?;
    let mut members: Vec<(String, Vec<u8>)> = Vec::new();
    let mut envelope: Option<Vec<u8>> = None;
    for i in 0..zip.len() {
        let mut file = zip.by_index(i).map_err(|e| e.to_string())?;
        let path = file.name().to_string();
        if path.ends_with('/') || path.contains("..") {
            continue;
        }
        let mut data = Vec::new();
        file.read_to_end(&mut data).map_err(|e| e.to_string())?;
        if path == mjolnir_sign::SIGNATURE_MEMBER {
            envelope = Some(data);
        } else {
            members.push((path, data));
        }
    }

    // An author signature present but wrong is impersonation evidence, the
    // same rule as the platform signature above: refuse, never shrug.
    let verified = match &envelope {
        Some(env) => {
            let refs: Vec<(String, &[u8])> = members
                .iter()
                .map(|(p, b)| (p.clone(), b.as_slice()))
                .collect();
            Some(
                mjolnir_sign::verify_members(env, &slug, &release.version, &refs).map_err(|e| {
                    format!("Author signature does not verify: {e}. Refusing to install.")
                })?,
            )
        }
        None => None,
    };

    // A map pack's own data, and everything it depends on, before any of it
    // is recorded: a map never mounts without the runtime pack and the code
    // mods that start it.
    let manifest: serde_json::Value = members
        .iter()
        .find(|(p, _)| p == "mjolnir.json")
        .and_then(|(_, b)| serde_json::from_slice(b).ok())
        .unwrap_or(serde_json::Value::Null);
    // The archive's own manifest decides too: the hub kept map packs at the
    // `content` trust tier, and launchers that went by the mod page's type
    // alone installed the official maps as plain content (no level data, no
    // registration), so they never started (2026-10-02).
    let is_map = mod_type == "map" || manifest["type"].as_str() == Some("map");
    let map = if is_map {
        let map = read_map(&manifest, &members)?;
        if let Some(other) = load_state()
            .installed
            .iter()
            .find(|m| m.slug != slug && m.map_code.as_deref() == Some(map.code.as_str()))
        {
            return Err(format!(
                "{} already uses the map code {}. Uninstall it first.",
                other.name, map.code
            ));
        }
        Some(map)
    } else {
        None
    };
    for dep in manifest["deps"].as_array().into_iter().flatten() {
        let Some(dep_slug) = dep["slug"].as_str() else {
            continue;
        };
        if load_state()
            .installed
            .iter()
            .any(|m| m.slug == dep_slug && cache_complete(m))
        {
            continue;
        }
        if live.is_some() {
            return Err(format!(
                "{name} needs {dep_slug}, which is not installed. Install it from the                  MJOLNIR launcher and restart the game."
            ));
        }
        if depth + 1 >= MAX_DEP_DEPTH {
            return Err(format!(
                "{name}: dependencies nest too deeply at {dep_slug}"
            ));
        }
        install_one(dep_slug, None, depth + 1)
            .map_err(|e| format!("{name} needs {dep_slug}: {e}"))?;
    }
    if map.is_some() && live.is_none() {
        ensure_code_mods(MAP_CODE_MODS)
            .map_err(|e| format!("{name} needs the multiplayer mods: {e}"))?;
    }

    // Unpack the containers into this release's cache.
    let release_cache = cache_dir().join(&release.id);
    let _ = fs::remove_dir_all(&release_cache);
    fs::create_dir_all(&release_cache).map_err(|e| e.to_string())?;

    let mut containers = Vec::new();
    let mut container_hashes = std::collections::BTreeMap::new();
    for (path, data) in &members {
        if !path.starts_with("content/") {
            continue;
        }
        let base = path.rsplit('/').next().unwrap_or("").to_string();
        let (stem, ext) = match base.rsplit_once('.') {
            Some((s, e @ ("utoc" | "ucas"))) if !s.is_empty() => (s.to_string(), e),
            _ => continue,
        };
        container_hashes.insert(format!("{stem}.{ext}"), sha256_hex(data));
        fs::write(release_cache.join(format!("{stem}.{ext}")), data).map_err(|e| e.to_string())?;
        crate::transfer::wrote(data.len() as u64);
        if ext == "utoc" {
            containers.push(stem);
        }
    }
    if containers.is_empty() {
        return Err("Archive holds no containers under content/".into());
    }
    containers.sort();
    if let Some(map) = &map {
        let dir = release_cache.join("map");
        fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
        for (file, data) in [
            ("level.json", &map.level),
            ("registration.json", &map.registration),
        ] {
            fs::write(dir.join(file), data).map_err(|e| e.to_string())?;
            container_hashes.insert(format!("map/{file}"), sha256_hex(data));
        }
    }

    // Trust observations. None block the install; all stay attached to the
    // entry so the library keeps them in front of the user.
    let signer_fingerprint = verified.as_ref().map(|v| v.fingerprint.clone());
    let mut notices: Vec<String> = Vec::new();
    if let (Some(local), Some(hub_fp)) = (&signer_fingerprint, &status.signer_fingerprint) {
        if local != hub_fp {
            notices.push(
                "The archive's signing key differs from the one the hub recorded at publish."
                    .into(),
            );
        }
    }
    if status.signer_key_revoked == Some(true) {
        notices.push("The author has revoked this signing key since publishing.".into());
    }

    let mut state = load_state();
    // Replacing an install leaves the previous release's cache behind;
    // clear it so updating does not grow the cache without bound. The
    // previous entry is also the pin: a key that changed, or a signature
    // that quietly disappeared, is exactly what tampering looks like — and
    // also what an author with a second machine looks like, so it warns
    // rather than refuses (docs/mod_signing_design.md).
    if let Some(previous) = state.installed.iter().find(|m| m.slug == slug) {
        if previous.release_id != release.id {
            let _ = fs::remove_dir_all(cache_dir().join(&previous.release_id));
        }
        match (&previous.signer_fingerprint, &signer_fingerprint) {
            (Some(old), Some(new)) if old != new => notices.push(format!(
                "The signing key changed since the last install ({}… → {}…). A new device \
                 of the author's is normal; check the mod page if this surprises you.",
                &old[..16.min(old.len())],
                &new[..16.min(new.len())],
            )),
            (Some(_), None) => notices
                .push("Earlier releases of this mod were author-signed; this one is not.".into()),
            _ => {}
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
        signer_fingerprint,
        published_by: status.published_by.clone().or_else(|| {
            verified
                .as_ref()
                .and_then(|v| v.statement.author.as_ref().map(|a| a.id.clone()))
        }),
        signature_notice: if notices.is_empty() {
            None
        } else {
            Some(notices.join(" "))
        },
        map_code: map.map(|m| m.code),
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
    save_state(&state)
}

// ─── Live install: a map for the running game ──────────────────────────
//
// The game asks for a map it does not have (a server it is joining, the
// host's pick, a vote) by starting this executable with `--install-map
// <CODE> --progress <file>` (`run_live_install`, docs/live_map_install.md).
// The install is the ordinary one — the hub's hash, the platform and author
// signatures, the same cache, state and Paks names — so the next launch
// finds everything where it expects it and copies nothing. What cannot
// happen under a running game is left out: no container already in Paks is
// rewritten (the game holds them open), no code mod is touched, and the
// registration container is not rebuilt (it is mounted; the game registers
// the map in memory, and the next launch cooks it in).

/// How a live install reports its download.
pub struct Live<'a> {
    pub progress: &'a dyn Fn(u64, Option<u64>),
    /// The archive's size from the hub's listing: the download is streamed
    /// without a length.
    pub size: Option<u64>,
}

/// What the game hears when a live install is done.
#[derive(Debug, Serialize)]
pub struct LiveInstall {
    pub code: String,
    pub slug: String,
    pub version: String,
    pub release_id: String,
    /// The new `.pak` files for the game to mount, as the engine names them
    /// (relative to its executable). Empty when the map was already in Paks.
    pub mount: Vec<String>,
    /// The previous release's `.pak` files, for the game to unmount first:
    /// an update of a map whose containers the game holds open.
    pub unmount: Vec<String>,
}

/// The engine's name for a container in Paks, as the game mounts it.
fn engine_pak(base: &str) -> String {
    format!("../../../Meteorite/Content/Paks/{base}.pak")
}

/// `<stem>_P` as `<stem>_<n>_P`. The engine mounts a `_<n>_P` pak above a
/// plain `_P` one (FPakPlatformFile::Mount adds 100 per patch number), so an
/// update written beside a container the game holds open wins even where a
/// later launch mounts both; the next launch from the launcher removes it
/// (`paks_strays`) and copies the release under its usual name.
fn patch_name(base: &str, n: u32) -> String {
    format!("{}_{n}_P", base.strip_suffix("_P").unwrap_or(base))
}

/// Install the hub's map `code` for a game that is running, and put its
/// containers and data where the game reads them. With `release`, that exact
/// release (the one a host runs, which may be older or newer than this PC's);
/// without, the map as it is installed, or the newest when it is not.
pub fn install_live(
    code: &str,
    release: Option<&str>,
    progress: &dyn Fn(u64, Option<u64>),
) -> Result<LiveInstall, String> {
    if !crate::maps::valid_code(code) {
        return Err(format!("{code:?} is not a map code"));
    }
    if let Some(id) = release {
        if id.len() > 64 || !id.chars().all(|c| c.is_ascii_hexdigit() || c == '-') {
            return Err(format!("{id:?} is not a release id"));
        }
    }
    let listing = get_json(&format!("{}/maps/{code}", hub_api()))
        .map_err(|e| format!("The hub has no map {code}: {e}"))?;
    let slug = listing["slug"]
        .as_str()
        .ok_or_else(|| format!("The hub has no map {code}"))?
        .to_string();

    let before = load_state()
        .installed
        .iter()
        .find(|m| m.map_code.as_deref() == Some(code) && cache_complete(m))
        .cloned();
    let have = before
        .as_ref()
        .is_some_and(|m| release.is_none_or(|id| m.release_id == id));
    if !have {
        let size = match release {
            Some(id) => get_json(&format!("{}/releases/{id}", hub_api()))
                .ok()
                .and_then(|r| r["file_size"].as_u64()),
            None => listing.pointer("/release/file_size").and_then(|v| v.as_u64()),
        };
        install_one_as(&slug, release.map(str::to_string), 0, Some(&Live { progress, size }))?;
    }
    // Another release of the map was in Paks before this install: the game
    // may hold its containers open.
    let updated = !have && before.is_some();

    let mut state = load_state();
    let inst = state
        .installed
        .iter()
        .find(|m| m.map_code.as_deref() == Some(code))
        .cloned()
        .ok_or_else(|| format!("{code} did not install"))?;
    let active = state.active.clone();
    if let Some(profile) = state.profiles.iter_mut().find(|p| p.name == active) {
        match profile.entries.iter_mut().find(|e| e.slug == inst.slug) {
            Some(entry) => entry.enabled = true,
            None => profile.entries.push(ProfileEntry {
                slug: inst.slug.clone(),
                enabled: true,
            }),
        }
    }
    save_state(&state)?;

    let paks = paks_dir()?;
    let mut mount = Vec::new();
    let mut unmount = Vec::new();
    for m in mounts(&state)?.iter().filter(|m| m.slug == inst.slug) {
        let present = ["utoc", "ucas", "pak"].iter().all(|ext| m.in_paks(&paks, ext).is_file());
        if present && !updated {
            continue;
        }
        // All of a container or none of it: the engine holds a mounted
        // `.ucas` open (its `.utoc` it reads once), so the `.ucas` is tried
        // for writing before anything is copied, and copied first.
        let write = |base: &str| -> std::io::Result<()> {
            let ucas = paks.join(format!("{base}.ucas"));
            if ucas.exists() {
                fs::OpenOptions::new().write(true).open(&ucas)?;
            }
            for ext in ["ucas", "utoc"] {
                fs::copy(m.cached(ext), paks.join(format!("{base}.{ext}")))?;
            }
            fs::write(paks.join(format!("{base}.pak")), ue_iostore::pak::stub_for(base))
        };
        // Its usual name, unless the game holds the old release there open.
        if write(&m.base).is_ok() {
            mount.push(engine_pak(&m.base));
            continue;
        }
        let mut n = 2;
        while paks.join(format!("{}.utoc", patch_name(&m.base, n))).exists() {
            n += 1;
        }
        let base = patch_name(&m.base, n);
        write(&base).map_err(|e| format!("{}: {e}", m.slug))?;
        mount.push(engine_pak(&base));
        unmount.push(engine_pak(&m.base));
        for older in 2..n {
            unmount.push(engine_pak(&patch_name(&m.base, older)));
        }
    }
    // Any other copy of this mod in Paks: under another load-order number (a
    // profile that changed since Paks was written) or an earlier update's
    // patch name. Both mounted would mix two releases' packages, so it goes:
    // deleted when the game does not hold it, unmounted by the game when it
    // does (and deleted by the next launch, `paks_strays`).
    let keep: BTreeSet<String> = mount
        .iter()
        .map(|p| p.trim_start_matches("../../../Meteorite/Content/Paks/").trim_end_matches(".pak").to_string())
        .chain(mounts(&state)?.into_iter().filter(|m| m.slug == inst.slug).map(|m| m.base))
        .collect();
    let prefix = format!("-{MARKER}-{}-", sanitize(&inst.slug));
    if let Ok(rd) = fs::read_dir(&paks) {
        for entry in rd.flatten() {
            let name = entry.file_name().to_string_lossy().into_owned();
            let Some(base) = name.strip_suffix(".pak") else { continue };
            let Some(at) = base.find(&prefix) else { continue };
            let rest = &base[at + prefix.len()..];
            let ours = rest
                .strip_suffix("_P")
                .is_some_and(|r| r.split('_').all(|part| !part.is_empty() && part.bytes().all(|b| b.is_ascii_digit())));
            if !ours || keep.contains(base) || !base.starts_with("pakchunk") {
                continue;
            }
            let gone = ["ucas", "utoc", "pak"]
                .iter()
                .all(|ext| fs::remove_file(paks.join(format!("{base}.{ext}"))).is_ok());
            if !gone {
                unmount.push(engine_pak(base));
            }
        }
    }
    crate::maps::add_live(
        &paks,
        &crate::maps::Enabled {
            code: code.to_string(),
            data: cache_dir().join(&inst.release_id).join("map"),
        },
    )?;
    Ok(LiveInstall {
        code: code.to_string(),
        slug: inst.slug,
        version: inst.version,
        release_id: inst.release_id,
        mount,
        unmount,
    })
}

/// Where the game finds this executable to ask for a live install.
pub fn record_exe_path() {
    if let Ok(exe) = std::env::current_exe() {
        let _ = fs::create_dir_all(config_dir());
        let _ = fs::write(config_dir().join("launcher_exe.txt"), exe.to_string_lossy().as_bytes());
    }
}

/// `--install-map <CODE> [--release <id>] --progress <file>`: the live install, reported to
/// the game through `file` as one JSON object, replaced as it goes —
/// `{"stage":"download","received":n,"total":n}`, then `{"stage":"done",...}`
/// with [`LiveInstall`]'s fields, or `{"stage":"error","message":...}`.
pub fn run_live_install(code: &str, release: Option<&str>, progress_file: &Path) -> i32 {
    record_exe_path();
    let write = |value: serde_json::Value| {
        let tmp = progress_file.with_extension("tmp");
        if fs::write(&tmp, value.to_string()).is_ok() {
            // The game may have the file open for a moment: try a few times.
            for _ in 0..20 {
                if fs::rename(&tmp, progress_file).is_ok() {
                    break;
                }
                std::thread::sleep(std::time::Duration::from_millis(25));
            }
        }
    };
    write(serde_json::json!({ "stage": "start", "code": code }));
    let last = std::cell::Cell::new(std::time::Instant::now() - std::time::Duration::from_secs(1));
    let progress = |received: u64, total: Option<u64>| {
        if last.get().elapsed() < std::time::Duration::from_millis(100) && Some(received) != total {
            return;
        }
        last.set(std::time::Instant::now());
        write(serde_json::json!({ "stage": "download", "received": received, "total": total }));
    };
    match install_live(code, release, &progress) {
        Ok(done) => {
            let mut value = serde_json::to_value(&done).unwrap_or_default();
            value["stage"] = "done".into();
            write(value);
            0
        }
        Err(e) => {
            write(serde_json::json!({ "stage": "error", "message": e }));
            1
        }
    }
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
    profile
        .entries
        .insert(new_index.min(profile.entries.len()), entry);
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

/// What the game needs a paired key to carry: MJOLNIRLobby lists a public
/// game with it (docs/multiplayer_servers.md). A key without one of these
/// works for the launcher but fails in game, so it counts as needing a new
/// sign-in.
const REQUIRED_SCOPES: &[&str] = &["lobbies:write"];

/// Whether the stored sign-in still works, asked at startup and after each
/// sign-in. The page decides whether `expires_at` is close enough to mention.
#[derive(Debug, Serialize, Clone)]
pub struct HubSession {
    /// "signed_out", "ok", "expired", "missing_scope", "offline".
    pub state: &'static str,
    pub user: Option<HubUser>,
    pub expires_at: Option<String>,
    pub missing_scopes: Vec<String>,
}

/// Checks the stored key against the hub. "expired" covers revoked and
/// expired keys alike: the hub answers 401 to both. "offline" means the check
/// could not be made, which is no reason to ask anyone to sign in.
pub fn session_check() -> HubSession {
    let Some(auth) = load_auth() else {
        return HubSession { state: "signed_out", user: None, expires_at: None, missing_scopes: vec![] };
    };
    let session = |state, expires_at, missing_scopes| HubSession {
        state,
        user: Some(auth.user.clone()),
        expires_at,
        missing_scopes,
    };
    let client = match reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(15))
        .build()
    {
        Ok(c) => c,
        Err(_) => return session("offline", None, vec![]),
    };
    let resp = match client.get(format!("{}/account/me", hub_api())).bearer_auth(&auth.key).send() {
        Ok(r) => r,
        Err(_) => return session("offline", None, vec![]),
    };
    match resp.status().as_u16() {
        200 => {}
        401 => return session("expired", None, vec![]),
        _ => return session("offline", None, vec![]),
    }
    let me: serde_json::Value = resp.json().unwrap_or(serde_json::Value::Null);
    let expires_at = me["expires_at"].as_str().map(str::to_string);
    // A hub from before /account/me reported scopes sends none: trust the key.
    let missing: Vec<String> = match me["scopes"].as_array() {
        Some(scopes) => REQUIRED_SCOPES
            .iter()
            .filter(|s| !scopes.iter().any(|v| v.as_str() == Some(s)))
            .map(|s| s.to_string())
            .collect(),
        None => vec![],
    };
    if !missing.is_empty() {
        return session("missing_scope", expires_at, missing);
    }
    session("ok", expires_at, vec![])
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
    /// True when a working MJOLNIR install is expected to carry this mod, so
    /// setup installs it without asking. This is deliberately a flag the mod
    /// sets for itself rather than something derived from `category`: the
    /// category is a shelf label, and `tools` holds both the console enabler
    /// and the Bridge, which is an arbitrary-Lua eval channel that has no
    /// business being on a player's machine uninvited. Absent means false, so
    /// a manifest published before this field simply has no defaults.
    #[serde(default, rename = "default")]
    pub default_install: bool,
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

/// Fold a sorted (relative path, content hash) list into one digest.
///
/// Shared by the on-disk walk and the zip read so the two are guaranteed to
/// agree — if they drifted, every mod would read as modified.
fn fold_tree(mut files: Vec<(String, String)>) -> String {
    files.sort();
    let mut hasher = Sha256::new();
    for (rel, hash) in &files {
        hasher.update(rel.as_bytes());
        hasher.update([0]);
        hasher.update(hash.as_bytes());
        hasher.update([b'\n']);
    }
    hex::encode(hasher.finalize())
}

/// The digest a mod's directory *should* have, read from the signed set's own
/// artifact rather than from anything this launcher wrote down.
///
/// This is what makes the badge a statement about content. A launcher that
/// only trusts its own install record cannot say anything about a mod it did
/// not install — including every mod installed by a version of itself that
/// predates digests — even when the bytes are provably the signed ones.
fn expected_tree_digest(entry: &CodeModEntry) -> Result<String, String> {
    let mut resp = http()?.get(&entry.url).send().map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("Download failed: {}", resp.status()));
    }
    let mut bytes = Vec::new();
    resp.read_to_end(&mut bytes).map_err(|e| e.to_string())?;
    // The manifest is signed, so its hash is authoritative. A zip that does
    // not match it cannot be used to judge anything.
    let actual = sha256_hex(&bytes);
    if actual != entry.sha256 {
        return Err(format!(
            "Hash mismatch: manifest says {}, download is {actual}",
            entry.sha256
        ));
    }

    zip_tree_digest(&bytes, &entry.id)
}

/// The same digest as `tree_digest`, computed over a release zip instead of a
/// directory. It must select and name exactly the files `code_mods_install`
/// would extract, or the two would disagree and every mod would read as
/// modified.
fn zip_tree_digest(bytes: &[u8], id: &str) -> Result<String, String> {
    let mut zip = zip::ZipArchive::new(std::io::Cursor::new(bytes)).map_err(|e| e.to_string())?;
    let prefix = format!("{id}/");
    let mut files = Vec::new();
    for i in 0..zip.len() {
        let mut file = zip.by_index(i).map_err(|e| e.to_string())?;
        if file.is_dir() {
            continue;
        }
        let name = file.name().to_string();
        if name.contains("..") {
            continue;
        }
        // Mirror what install extracts: only the mod's own subtree, and the
        // path recorded relative to the mod root.
        let Some(rel) = name.strip_prefix(&prefix) else {
            continue;
        };
        let mut data = Vec::new();
        file.read_to_end(&mut data).map_err(|e| e.to_string())?;
        files.push((rel.to_string(), sha256_hex(&data)));
    }
    Ok(fold_tree(files))
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
    Ok(fold_tree(files))
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

    let mods_dir = crate::find_game_install().map(|(p, _)| crate::mods_dir(&p));
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
            //
            // What the bytes are compared *against* matters as much. A
            // recorded digest is only a cache of what the signed set said, so
            // when there is no usable record the answer comes from the set
            // itself rather than defaulting to "cannot say" — otherwise every
            // mod installed before digests existed stays unverifiable forever,
            // even though its contents are provably the signed ones.
            let integrity = match (present, record) {
                (false, _) => Integrity::NotInstalled,
                (true, Some(r)) if !r.tree_sha256.is_empty() && r.version == entry.version => {
                    let dir = dir.as_ref().expect("present implies a path");
                    match tree_digest(dir) {
                        Ok(actual) if actual == r.tree_sha256 => Integrity::Verified,
                        // An unreadable tree is not a passing tree.
                        _ => Integrity::Modified,
                    }
                }
                // Out of date is not the same as tampered with, and the set
                // only publishes the current release — there is nothing
                // truthful to compare an older install against.
                (true, _) if update_available => Integrity::Unverified,
                (true, _) => {
                    let dir = dir.as_ref().expect("present implies a path");
                    match (tree_digest(dir), expected_tree_digest(&entry)) {
                        (Ok(actual), Ok(expected)) if actual == expected => {
                            // Cache it, so this costs one download per mod
                            // ever rather than one per status call.
                            let _ = save_installed_version(&entry.id, &entry.version, &actual);
                            Integrity::Verified
                        }
                        (Ok(_), Ok(_)) => Integrity::Modified,
                        // Could not reach the set, or could not read the
                        // directory. Neither is evidence of anything.
                        _ => Integrity::Unverified,
                    }
                }
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

/// An unsigned set does not get to name hashes, so nothing installs from one.
fn require_signed(status: &CodeModsStatus) -> Result<(), String> {
    if status.signature_verified {
        return Ok(());
    }
    Err(
        "The mods manifest signature does not verify against this launcher's key. \
         Refusing to install anything from it."
            .into(),
    )
}

/// Where UE4SS loads Lua mods from, or why it cannot.
fn code_mods_dir() -> Result<PathBuf, String> {
    let (install, _) = crate::find_game_install().ok_or("Game not found")?;
    let dir = crate::mods_dir(&install);
    if !dir.exists() {
        return Err("UE4SS is not installed. Install the modpack first.".into());
    }
    Ok(dir)
}

/// Download one already-verified entry, unpack it, register it with UE4SS and
/// record what was written.
///
/// Kept separate from `code_mods_install` so installing several mods costs one
/// manifest fetch rather than one per mod: `code_mods_status` re-downloads and
/// re-verifies the whole set, and can pull entire zips to judge integrity, so
/// looping over the single-mod entry point would multiply all of that by N.
fn install_entry(entry: &CodeModEntry, mods_dir: &Path) -> Result<(), String> {
    let id = &entry.id;
    let resp = http()?.get(&entry.url).send().map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("Download failed: {}", resp.status()));
    }
    let total = resp.content_length();
    let bytes = crate::transfer::read_body(resp, total, |_| {}).map_err(|e| e.to_string())?;
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
        fs::write(&dest, &data).map_err(|e| e.to_string())?;
        crate::transfer::wrote(data.len() as u64);
    }

    // Register with UE4SS if mods.txt does not know it yet.
    let mods_txt = mods_dir.join("mods.txt");
    let content = fs::read_to_string(&mods_txt).unwrap_or_default();
    let known = content
        .lines()
        .any(|l| l.split(':').next().is_some_and(|n| n.trim() == id.as_str()));
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
    let tree = tree_digest(&mods_dir.join(id))?;
    save_installed_version(id, &entry.version, &tree)?;
    Ok(())
}

/// Install one mod from the signed set.
pub fn code_mods_install(id: String) -> Result<(), String> {
    let status = code_mods_status()?;
    require_signed(&status)?;
    let entry = status
        .mods
        .iter()
        .map(|m| &m.entry)
        .find(|m| m.id == id)
        .ok_or_else(|| format!("{id} is not in the signed set"))?;
    install_entry(entry, &code_mods_dir()?)
}

/// Install every mod the set marks as a default, skipping any already on disk.
/// Returns the ids it installed, newly-installed only.
///
/// Setup used to leave a fresh install with no MJOLNIR mods at all, while the
/// setup panel listed five of them as though they had shipped — UE4SS arrived
/// as a loader with nothing to load. This closes that gap, and it installs
/// only what the set marks rather than everything CI publishes: the diagnostic
/// and experimental mods, and the Bridge in particular, stay opt-in.
///
/// Not idempotent by accident but by intent — an already-present mod is left
/// exactly as it is, including one the player has since disabled in mods.txt.
pub fn code_mods_install_defaults() -> Result<Vec<String>, String> {
    let status = code_mods_status()?;
    require_signed(&status)?;
    let mods_dir = code_mods_dir()?;

    let mut installed = Vec::new();
    for row in &status.mods {
        if !row.entry.default_install || row.integrity != Integrity::NotInstalled {
            continue;
        }
        install_entry(&row.entry, &mods_dir)?;
        installed.push(row.entry.id.clone());
    }
    Ok(installed)
}

/// Make sure these code mods are installed, current and switched on: what a
/// map needs before it can start. A mod missing from disk is installed; one
/// the launcher installed and nobody edited is brought up to date (a map
/// built today may need today's loader); one the player edited is left as
/// it is. Returns the ids it installed or updated.
fn ensure_code_mods(ids: &[&str]) -> Result<Vec<String>, String> {
    let status = code_mods_status()?;
    require_signed(&status)?;
    let mods_dir = code_mods_dir()?;
    let mut changed = Vec::new();
    for id in ids {
        let row = status
            .mods
            .iter()
            .find(|r| r.entry.id == *id)
            .ok_or_else(|| format!("{id} is not in the signed set yet"))?;
        let stale = row.update_available && row.integrity == Integrity::Verified;
        if row.integrity == Integrity::NotInstalled || stale {
            install_entry(&row.entry, &mods_dir)?;
            changed.push(id.to_string());
        }
        crate::toggle_mod(id.to_string(), true)?;
    }
    Ok(changed)
}

// ─── Multiplayer: everything in one go ──────────────────────────────────

#[derive(Debug, Serialize)]
pub struct MultiplayerInstall {
    /// Maps installed or updated by this run, by title.
    pub installed: Vec<String>,
    /// Maps already current.
    pub current: Vec<String>,
    /// Maps that failed, with why. The rest still install.
    pub failed: Vec<String>,
    pub state: HubState,
}

/// Install every official map (the classic CE set) with what they need: the
/// CE runtime pack, the multiplayer code mods, the registration. Maps already
/// at their newest release are skipped, so running it again is an update.
/// `progress` hears each step and how far along the run is (0 to 1).
pub fn install_multiplayer(progress: &dyn Fn(&str, f32)) -> Result<MultiplayerInstall, String> {
    progress("Checking the multiplayer mods", 0.0);
    ensure_code_mods(MAP_CODE_MODS)?;

    let listing = get_json(&format!("{}/maps?official=1", hub_api()))?;
    let maps = listing["maps"].as_array().cloned().unwrap_or_default();
    if maps.is_empty() {
        return Err("The hub lists no official maps yet.".into());
    }

    let mut result = MultiplayerInstall {
        installed: Vec::new(),
        current: Vec::new(),
        failed: Vec::new(),
        state: HubState::default(),
    };
    // Maps whose Paks copy is gone but whose cache is whole: the
    // `materialize` below restores them, and they count as installed.
    let restored = match (mounts(&load_state()), paks_dir()) {
        (Ok(mounts), Ok(paks)) => paks_gaps(&mounts, &paks),
        _ => BTreeSet::new(),
    };
    let mut restoring = Vec::new();
    let total = maps.len() as f32;
    for (i, map) in maps.iter().enumerate() {
        let title = map["title"].as_str().unwrap_or("?").to_string();
        let (Some(slug), Some(release)) = (map["slug"].as_str(), map["release"]["id"].as_str())
        else {
            result.failed.push(format!("{title}: no published release"));
            continue;
        };
        // Current means "not older than the listing", the test the Updates tab
        // uses (`check_updates`), so a map it just updated is not fetched
        // again here under a different release id of the same version.
        let version = map["release"]["version"].as_str().unwrap_or("");
        let have = load_state().installed.iter().any(|m| {
            m.slug == slug
                && (m.release_id == release || !is_newer(version, &m.version))
                && cache_complete(m)
        });
        if have {
            if restored.contains(slug) {
                restoring.push(title);
            } else {
                result.current.push(title);
            }
            continue;
        }
        progress(&format!("Installing {title}"), i as f32 / (total + 1.0));
        match install_one(slug, Some(release.to_string()), 0) {
            Ok(()) => result.installed.push(title),
            Err(e) => result.failed.push(format!("{title}: {e}")),
        }
    }

    progress("Registering the maps with the game", total / (total + 1.0));
    let state = load_state();
    // A map that was installed before but switched off in this profile is
    // what the player chose; only maps not in the profile at all are added.
    materialize(&state)?;
    result.installed.extend(restoring);
    result.state = state;
    progress("Done", 1.0);
    Ok(result)
}

// ─── Joining a listed game from a link ──────────────────────────────────

/// The pack every converted map mounts its shared content from
/// (`RUNTIME_SLUG` in crates/blam-cli/src/map.rs).
const RUNTIME_SLUG: &str = "mjolnir-ce-runtime";

/// Whether this PC can join a multiplayer game, judged from what is on disk
/// (no network: a link's click should not wait on the signed set): the code
/// mods a map plays through present and switched on in `mods.txt`, and the
/// CE runtime pack installed, whole in the cache, and on in the active
/// profile. The map itself is not needed: the game downloads the host's
/// (DOWNLOAD AND JOIN). Returns MJOLNIRLobby's folder, or what is missing.
pub fn multiplayer_ready() -> Result<PathBuf, String> {
    let (install, _) = crate::find_game_install().ok_or("The game was not found.")?;
    let mods_dir = crate::mods_dir(&install);
    let listed = crate::parse_mods_txt(&mods_dir);
    let missing: Vec<&str> = MAP_CODE_MODS
        .iter()
        .copied()
        .filter(|id| {
            !mods_dir.join(id).is_dir() || !listed.iter().any(|m| m.name == *id && m.enabled)
        })
        .collect();
    if !missing.is_empty() {
        return Err(format!(
            "The multiplayer mods are not installed or are switched off: {}.",
            missing.join(", ")
        ));
    }

    let state = load_state();
    let runtime = state
        .installed
        .iter()
        .find(|m| m.slug == RUNTIME_SLUG && cache_complete(m));
    let enabled = state
        .profiles
        .iter()
        .find(|p| p.name == state.active)
        .is_some_and(|p| {
            p.entries
                .iter()
                .any(|e| e.slug == RUNTIME_SLUG && e.enabled)
        });
    if runtime.is_none() || !enabled {
        return Err("The CE runtime pack the maps share is not installed or is switched off.".into());
    }
    Ok(mods_dir.join("MJOLNIRLobby"))
}

/// What MJOLNIRLobby reads from `native\pending_join.txt`: key=value lines,
/// the lobby's hub id and when the link was clicked (unix seconds). The game
/// drops one older than ten minutes.
fn pending_join_text(lobby: &str, at: u64) -> String {
    format!("lobby={lobby}\nat={at}\n")
}

/// Leave a join for MJOLNIRLobby to pick up at the main menu, in its
/// `native` folder beside `auto_state.txt`. Written whole or not at all (a
/// temporary file renamed over it), since the game polls for it.
pub fn write_pending_join(lobby_dir: &Path, lobby: &str) -> Result<(), String> {
    let native = lobby_dir.join("native");
    fs::create_dir_all(&native).map_err(|e| format!("{}: {e}", native.display()))?;
    let target = native.join("pending_join.txt");
    let tmp = native.join("pending_join.txt.tmp");
    fs::write(&tmp, pending_join_text(lobby, now_unix()))
        .map_err(|e| format!("{}: {e}", tmp.display()))?;
    fs::rename(&tmp, &target).map_err(|e| format!("{}: {e}", target.display()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_pending_join_is_written_whole_where_the_lobby_reads_it() {
        let root = std::env::temp_dir().join(format!("mjolnir-join-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        // A join from an earlier click is replaced, not appended to.
        fs::create_dir_all(root.join("native")).expect("scratch tree");
        fs::write(root.join("native/pending_join.txt"), "lobby=old\nat=1\n").expect("old join");

        write_pending_join(&root, "0b6f3c1e-9a2d").expect("write");
        let text = fs::read_to_string(root.join("native/pending_join.txt")).expect("read");
        let mut lines = text.lines();
        assert_eq!(lines.next(), Some("lobby=0b6f3c1e-9a2d"));
        let at: u64 = lines
            .next()
            .and_then(|l| l.strip_prefix("at="))
            .and_then(|v| v.parse().ok())
            .expect("an at= line of unix seconds");
        assert!(at.abs_diff(now_unix()) < 60);
        assert!(!root.join("native/pending_join.txt.tmp").exists());
        assert_eq!(pending_join_text("x", 5), "lobby=x\nat=5\n");
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn the_compiled_in_signing_key_parses() {
        // A bad keys/mod-signing.pub should fail the build's tests, not the
        // first user who tries to install a mod.
        signing_key().expect("pinned public key must parse");
    }

    /// `default` decides what setup installs unasked, so the field has to
    /// survive the rename between JSON and Rust — and, just as importantly,
    /// has to read as false when a manifest predates it. A serde slip either
    /// way is silent: too eager and every player gets the Bridge, too shy and
    /// setup goes back to installing nothing.
    #[test]
    fn the_default_flag_survives_the_wire_and_is_opt_in() {
        let manifest: CodeModsManifest = serde_json::from_str(
            r#"{
                "schema_version": 1,
                "set_version": "1.2.3",
                "mods": [
                  {"id":"MJOLNIRCore","file":"c.zip","sha256":"a","size":1,
                   "url":"https://example.invalid/c.zip","version":"1.0.0",
                   "summary":"","category":"framework","default":true},
                  {"id":"MJOLNIRBridge","file":"b.zip","sha256":"b","size":1,
                   "url":"https://example.invalid/b.zip","version":"0.1.0",
                   "summary":"","category":"tools","default":false},
                  {"id":"MJOLNIRLegacy","file":"l.zip","sha256":"c","size":1,
                   "url":"https://example.invalid/l.zip"}
                ]
            }"#,
        )
        .expect("manifest must parse");

        let flags: Vec<bool> = manifest.mods.iter().map(|m| m.default_install).collect();
        assert_eq!(
            flags,
            vec![true, false, false],
            "only an explicit `default: true` opts a mod into setup"
        );

        // And back out again, under the name the manifest uses — a launcher
        // that renamed it on the way out would break the frontend filter.
        let json = serde_json::to_value(&manifest.mods[0]).unwrap();
        assert_eq!(json["default"], serde_json::json!(true));
    }

    /// A container deleted from Paks has to read as a gap, and a marker file
    /// nothing mounts as a stray; anything else and the launch skips the copy
    /// that would have put it back. One replaced by hand is left alone.
    #[test]
    fn paks_gaps_and_strays_follow_the_disk() {
        let root = std::env::temp_dir().join(format!("mjolnir-paks-{}", std::process::id()));
        let cache = root.join("cache");
        let paks = root.join("paks");
        fs::create_dir_all(&cache).unwrap();
        fs::create_dir_all(&paks).unwrap();
        let mount = |slug: &str| Mount {
            slug: slug.into(),
            cache: cache.clone(),
            container: format!("{slug}-c"),
            base: format!("pakchunk900-{MARKER}-{slug}-0_P"),
        };
        let mounts = [mount("bloodgulch"), mount("sidewinder")];
        for m in &mounts {
            for ext in ["utoc", "ucas"] {
                fs::write(m.cached(ext), b"container").unwrap();
                fs::write(m.in_paks(&paks, ext), b"container").unwrap();
            }
            fs::write(m.in_paks(&paks, "pak"), b"").unwrap();
        }
        assert!(paks_gaps(&mounts, &paks).is_empty());
        assert!(paks_strays(&mounts, &paks).unwrap().is_empty());

        fs::write(mounts[1].in_paks(&paks, "utoc"), b"a test build").unwrap();
        assert!(paks_gaps(&mounts, &paks).is_empty());

        fs::remove_file(mounts[0].in_paks(&paks, "ucas")).unwrap();
        fs::remove_file(mounts[1].in_paks(&paks, "pak")).unwrap();
        assert_eq!(
            paks_gaps(&mounts, &paks).into_iter().collect::<Vec<_>>(),
            ["bloodgulch", "sidewinder"]
        );

        let stray = format!("pakchunk901-{MARKER}-old-0_P.utoc");
        fs::write(paks.join(&stray), b"").unwrap();
        fs::write(paks.join("pakchunk0-Meteorite.utoc"), b"").unwrap();
        assert_eq!(paks_strays(&mounts, &paks).unwrap(), [stray]);

        let _ = fs::remove_dir_all(&root);
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
        assert_eq!(
            base,
            tree_digest(&root).unwrap(),
            "restored file must match"
        );

        fs::write(scripts.join("extra.lua"), b"").unwrap();
        assert_ne!(base, tree_digest(&root).unwrap(), "added file must show");
        fs::remove_file(scripts.join("extra.lua")).unwrap();

        fs::rename(scripts.join("main.lua"), scripts.join("other.lua")).unwrap();
        assert_ne!(base, tree_digest(&root).unwrap(), "renamed file must show");

        fs::remove_dir_all(&root).unwrap();
    }

    /// The load-bearing invariant: a directory holding exactly what a release
    /// zip holds must produce the same digest by both routes. If these two
    /// ever disagree, every installed mod reads as `modified` and the badge
    /// becomes noise.
    #[test]
    fn the_zip_and_the_directory_agree_on_the_same_content() {
        let id = "MJOLNIRFlyCam";
        let root = std::env::temp_dir().join(format!("mjolnir-zip-{}", std::process::id()));
        let dir = root.join(id);
        fs::create_dir_all(dir.join("Scripts")).unwrap();
        fs::write(dir.join("Scripts/main.lua"), b"print('fly')").unwrap();
        fs::write(dir.join("mod.json"), b"{\"version\":\"1.0.0\"}").unwrap();

        // A zip shaped like the ones CI publishes: rooted at "<ModName>/".
        let mut buf = Vec::new();
        {
            let mut w = zip::ZipWriter::new(std::io::Cursor::new(&mut buf));
            let opts: zip::write::FileOptions<()> = zip::write::FileOptions::default();
            w.add_directory(format!("{id}/"), opts).unwrap();
            w.start_file(format!("{id}/Scripts/main.lua"), opts)
                .unwrap();
            std::io::Write::write_all(&mut w, b"print('fly')").unwrap();
            w.start_file(format!("{id}/mod.json"), opts).unwrap();
            std::io::Write::write_all(&mut w, b"{\"version\":\"1.0.0\"}").unwrap();
            w.finish().unwrap();
        }

        assert_eq!(
            tree_digest(&dir).unwrap(),
            zip_tree_digest(&buf, id).unwrap(),
            "the on-disk walk and the zip read must fold to the same digest"
        );

        // And an edit on disk must break that agreement.
        fs::write(dir.join("Scripts/main.lua"), b"print('pwned')").unwrap();
        assert_ne!(
            tree_digest(&dir).unwrap(),
            zip_tree_digest(&buf, id).unwrap()
        );

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
        assert_eq!(
            (rec.version.as_str(), rec.tree_sha256.as_str()),
            ("1.0.0", "ab")
        );
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
        assert_eq!(
            order_number(500),
            999,
            "clamped, never colliding with shipped chunks"
        );
    }

    #[test]
    fn a_map_pack_reads_only_when_its_parts_agree() {
        let manifest = serde_json::json!({"type": "map", "map": {"code": "BGL"}});
        let reg = |code: &str| {
            serde_json::to_vec(&serde_json::json!({"code": code, "from": "B40"})).unwrap()
        };
        let members = |code: &str| {
            vec![
                (
                    "map/level.json".to_string(),
                    b"{\"title\":\"Blood Gulch\"}".to_vec(),
                ),
                ("map/registration.json".to_string(), reg(code)),
            ]
        };

        let map = read_map(&manifest, &members("BGL")).expect("a well-formed pack reads");
        assert_eq!(map.code, "BGL");

        let err = read_map(&manifest, &members("DCN"))
            .err()
            .expect("codes disagree");
        assert!(err.contains("registers DCN"), "{err}");
        let err = read_map(&manifest, &members("BGL")[..1])
            .err()
            .expect("no registration");
        assert!(err.contains("map/registration.json"), "{err}");
        let bad = serde_json::json!({"map": {"code": "../x"}});
        assert!(
            read_map(&bad, &members("BGL")).is_err(),
            "a code is never a path"
        );
        assert!(read_map(&serde_json::json!({}), &members("BGL")).is_err());
    }

    #[test]
    fn only_a_pakchunk_name_can_keep_its_number() {
        let nowhere = Path::new("does-not-exist.utoc");
        assert_eq!(shader_chunk("MJOLNIRMAP-BGL_P", nowhere), None);
        assert_eq!(shader_chunk("pakchunkX-MJOLNIR", nowhere), None);
        // A pakchunk name whose index cannot be read keeps nothing either.
        assert_eq!(
            shader_chunk("pakchunk988-MJOLNIRMAT-Windows", nowhere),
            None
        );
    }

    /// MJOLNIR_TEST_SHADER_UTOC=C:/haloce/ce_runtime/pakchunk988-MJOLNIRMAT-Windows.utoc
    ///   cargo test a_shader_library_keeps -- --ignored
    #[test]
    #[ignore = "needs a cooked container with a shader library (see doc comment)"]
    fn a_shader_library_keeps_its_chunk_number() {
        let utoc = std::env::var("MJOLNIR_TEST_SHADER_UTOC").expect("MJOLNIR_TEST_SHADER_UTOC");
        let path = Path::new(&utoc);
        let stem = path.file_stem().unwrap().to_string_lossy().into_owned();
        assert_eq!(shader_chunk(&stem, path), Some(988));
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
