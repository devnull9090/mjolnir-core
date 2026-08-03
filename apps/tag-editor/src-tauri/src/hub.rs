//! Publishing a project to the MJOLNIR hub.
//!
//! The hub's publish flow is four calls (`docs/hub_architecture.md` §7):
//! create the mod page if it does not exist, create the release, upload the
//! archive, then complete — which runs the server-side scan and returns its
//! findings. Auth is an API key carrying `mods:write`, obtained by pairing
//! this editor with a hub account the way the launcher pairs (see "Linking"
//! below) or, failing that, minted by hand and pasted in.

use std::path::Path;
use std::sync::{Mutex, OnceLock};
use std::time::Duration;

use serde::{Deserialize, Serialize};

use crate::install;
use crate::project::Meta;

const DEFAULT_BASE: &str = "https://mjolnircore.com";

/// The hub origin, overridable for local hub development.
pub fn base_url() -> String {
    std::env::var("MJOLNIR_HUB")
        .ok()
        .map(|s| s.trim().trim_end_matches('/').to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| DEFAULT_BASE.to_string())
}

#[derive(Serialize)]
pub struct HubStatus {
    pub base: String,
    pub has_key: bool,
    /// Who the stored key belongs to, when that is known. Cached at link
    /// time, so it answers without a round trip and without the key.
    pub username: Option<String>,
}

/// One scanner finding, verbatim from the hub.
#[derive(Serialize, Deserialize, Clone)]
pub struct Finding {
    pub level: String,
    pub code: String,
    pub message: String,
}

#[derive(Serialize)]
pub struct PublishView {
    pub slug: String,
    pub version: String,
    /// `published`, or `rejected` with the findings saying why.
    pub status: String,
    pub findings: Vec<Finding>,
    /// The mod's page, for the "view on the hub" link.
    pub url: String,
}

fn net(e: reqwest::Error) -> String {
    format!("could not reach the hub: {e}")
}

/// Turn a failed response into a message worth showing: the API wraps errors
/// as `{"error": ...}`, and the raw body is better than nothing.
fn err_body(what: &str, r: reqwest::blocking::Response) -> String {
    let status = r.status();
    let text = r.text().unwrap_or_default();
    let detail = serde_json::from_str::<serde_json::Value>(&text)
        .ok()
        .and_then(|v| {
            v.get("error").map(|e| match e {
                serde_json::Value::String(s) => s.clone(),
                other => other.to_string(),
            })
        })
        .unwrap_or(text);
    if detail.is_empty() {
        format!("{what}: {status}")
    } else {
        format!("{what}: {status} — {detail}")
    }
}

fn client() -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(30))
        .build()
        .map_err(|e| e.to_string())
}

// ─── Linking: pairing this editor with a hub account ────────────────────
//
// The editor has no browser session and will never ask for a Discord
// password, so it pairs the way the launcher does: ask the hub for a
// handshake, show the short code, let the user approve it at
// mjolnircore.com/link in a real browser, then collect a scoped API key on
// the next poll.
//
// It asks for more than the launcher does. The launcher rates and comments;
// this publishes, so it needs `mods:write`, and a stolen key can then
// publish under the user's name. That is a genuine widening — but the flow
// it replaces was the user minting a key by hand and pasting it into a text
// box, which produces a key with whatever scopes they ticked, usually no
// expiry, and a trip through the clipboard. What arrives here is narrow,
// dated and named on the account page.
//
// The key never reaches the webview: `auth_poll` stores it and returns only
// who it belongs to.

/// What the editor asks for. `mods:write` to publish, `mods:read` so the
/// panel can look up a mod page it does not own yet. Nothing else — the
/// approval page lists this, and a list with a scope the editor never uses
/// teaches people to skim it.
const PAIR_SCOPES: [&str; 2] = ["mods:read", "mods:write"];

/// Shown on the approval page. Says which app is asking, in the words the
/// user would use for it.
const CLIENT_NAME: &str = "MJOLNIR Tag Editor";

/// What to show the user, and where to send them.
#[derive(Serialize)]
pub struct LinkStart {
    pub user_code: String,
    pub verification_url: String,
    /// Seconds between polls, as the hub asked.
    pub interval: u64,
    pub expires_in: u64,
}

/// Where a pairing has got to. `username` is set only on approval.
#[derive(Serialize)]
pub struct LinkPoll {
    pub status: String,
    pub username: Option<String>,
}

/// The pairing in flight. Held in memory, not on disk: an interrupted
/// pairing should die with the process rather than linger as a credential
/// waiting to be collected.
fn pending_device() -> &'static Mutex<Option<String>> {
    static PENDING: OnceLock<Mutex<Option<String>>> = OnceLock::new();
    PENDING.get_or_init(|| Mutex::new(None))
}

fn urlencode(s: &str) -> String {
    // User codes are `[A-Z0-9]{4}-[A-Z0-9]{4}`, so this only has to be right
    // about the alphabet they actually use.
    s.chars()
        .map(|c| match c {
            'A'..='Z' | 'a'..='z' | '0'..='9' | '-' | '_' | '.' | '~' => c.to_string(),
            other => format!("%{:02X}", other as u32),
        })
        .collect()
}

/// Begin linking: returns the code to show and the page to open.
pub fn auth_start() -> Result<LinkStart, String> {
    let base = base_url();
    let r = client()?
        .post(format!("{base}/api/v1/auth/device/start"))
        .json(&serde_json::json!({ "client_name": CLIENT_NAME, "scopes": PAIR_SCOPES }))
        .send()
        .map_err(net)?;
    if !r.status().is_success() {
        return Err(err_body("starting the link", r));
    }

    #[derive(Deserialize)]
    struct Started {
        device_code: String,
        user_code: String,
        verification_url: String,
        interval: u64,
        expires_in: u64,
    }
    let started: Started = r.json().map_err(net)?;
    *pending_device().lock().map_err(|e| e.to_string())? = Some(started.device_code);

    Ok(LinkStart {
        // Prefilled so approving is a click, not a transcription.
        verification_url: format!(
            "{}?code={}",
            started.verification_url,
            urlencode(&started.user_code)
        ),
        user_code: started.user_code,
        interval: started.interval,
        expires_in: started.expires_in,
    })
}

/// Poll the pairing started by `auth_start`. On approval the key is stored
/// and the account name returned; the webview never sees the key.
pub fn auth_poll() -> Result<LinkPoll, String> {
    let device_code = pending_device()
        .lock()
        .map_err(|e| e.to_string())?
        .clone()
        .ok_or("no link in progress")?;

    let base = base_url();
    let r = client()?
        .post(format!("{base}/api/v1/auth/device/token"))
        .json(&serde_json::json!({ "device_code": device_code }))
        .send()
        .map_err(net)?;
    if !r.status().is_success() {
        return Err(err_body("checking the link", r));
    }

    #[derive(Deserialize)]
    struct Polled {
        status: String,
        key: Option<String>,
        user: Option<PolledUser>,
        #[serde(default)]
        scopes: Vec<String>,
    }
    #[derive(Deserialize)]
    struct PolledUser {
        id: String,
        username: String,
    }
    let polled: Polled = r.json().map_err(net)?;

    if polled.status != "approved" {
        // A denied or expired handshake is spent; the next attempt starts a
        // fresh one rather than polling a code the hub has forgotten.
        if polled.status != "pending" {
            *pending_device().lock().map_err(|e| e.to_string())? = None;
        }
        return Ok(LinkPoll {
            status: polled.status,
            username: None,
        });
    }

    let key = polled
        .key
        .ok_or("approved, but the hub sent no key — try linking again")?;
    // Caught here rather than at the first publish, where it would surface as
    // a 403 halfway through an upload.
    if !polled.scopes.iter().any(|s| s == "mods:write") {
        *pending_device().lock().map_err(|e| e.to_string())? = None;
        return Err(
            "that key cannot publish. Approve the link from the tag editor's own code, \
             not one shown by another app."
                .into(),
        );
    }

    install::remember_hub_key(&key)?;
    let username = polled.user.map(|u| {
        install::remember_author(&u.id, &u.username);
        u.username
    });
    *pending_device().lock().map_err(|e| e.to_string())? = None;

    Ok(LinkPoll {
        status: polled.status,
        username,
    })
}

/// Forget the stored key locally. The key itself stays valid until it is
/// revoked at mjolnircore.com/account/keys — this editor cannot revoke it,
/// because a credential that can revoke credentials is a bigger credential.
pub fn unlink() -> Result<(), String> {
    install::remember_hub_key("")?;
    install::forget_author();
    *pending_device().lock().map_err(|e| e.to_string())? = None;
    Ok(())
}

// ─── Publishing ─────────────────────────────────────────────────────────

/// The authenticated account, for embedding in signed statements.
pub fn whoami(key: &str) -> Result<mjolnir_sign::Author, String> {
    let base = base_url();
    let r = client()?
        .get(format!("{base}/api/v1/account/me"))
        .header("authorization", format!("Bearer {}", key.trim()))
        .send()
        .map_err(net)?;
    if !r.status().is_success() {
        return Err(err_body("checking your account", r));
    }
    #[derive(Deserialize)]
    struct Me {
        id: String,
        username: String,
    }
    let me: Me = r.json().map_err(net)?;
    Ok(mjolnir_sign::Author {
        id: me.id,
        username: me.username,
    })
}

/// Register this device's signing key against the account. Idempotent for a
/// key already registered to this account; a key can never move accounts.
pub fn register_key(key: &str, public_key_b64: &str, label: &str) -> Result<String, String> {
    let base = base_url();
    let r = client()?
        .post(format!("{base}/api/v1/account/signing-keys"))
        .header("authorization", format!("Bearer {}", key.trim()))
        .json(&serde_json::json!({ "public_key": public_key_b64, "label": label }))
        .send()
        .map_err(net)?;
    if !r.status().is_success() {
        return Err(err_body("registering the signing key", r));
    }
    #[derive(Deserialize)]
    struct Registered {
        fingerprint: String,
    }
    let reg: Registered = r.json().map_err(net)?;
    Ok(reg.fingerprint)
}

/// Whether a fingerprint is among the account's registered signing keys.
pub fn key_registered(key: &str, fingerprint: &str) -> Result<bool, String> {
    let base = base_url();
    let r = client()?
        .get(format!("{base}/api/v1/account/signing-keys"))
        .header("authorization", format!("Bearer {}", key.trim()))
        .send()
        .map_err(net)?;
    if !r.status().is_success() {
        return Err(err_body("listing signing keys", r));
    }
    #[derive(Deserialize)]
    struct Keys {
        keys: Vec<KeyRow>,
    }
    #[derive(Deserialize)]
    struct KeyRow {
        fingerprint: String,
    }
    let keys: Keys = r.json().map_err(net)?;
    Ok(keys.keys.iter().any(|k| k.fingerprint == fingerprint))
}

pub fn publish(
    key: &str,
    meta: &Meta,
    archive: &Path,
    changelog: &str,
) -> Result<PublishView, String> {
    let base = base_url();
    let client = reqwest::blocking::Client::builder()
        // Generous: the upload can be up to 50 MiB.
        .timeout(Duration::from_secs(300))
        .build()
        .map_err(|e| e.to_string())?;
    let bearer = format!("Bearer {}", key.trim());

    // The mod page, created on first publish and reused after.
    let r = client
        .get(format!("{base}/api/v1/mods/{}", meta.slug))
        .send()
        .map_err(net)?;
    if r.status() == reqwest::StatusCode::NOT_FOUND {
        let mut body = serde_json::json!({ "slug": meta.slug, "name": meta.name });
        if !meta.summary.is_empty() {
            body["summary"] = meta.summary.clone().into();
        }
        let r = client
            .post(format!("{base}/api/v1/mods"))
            .header("authorization", &bearer)
            .json(&body)
            .send()
            .map_err(net)?;
        if !r.status().is_success() {
            return Err(err_body("creating the mod page", r));
        }
    } else if !r.status().is_success() {
        return Err(err_body("checking the mod page", r));
    }

    // The release. `UNIQUE(mod_id, version)` — a version can only be
    // published once, so "bump the version in the mod panel" is the fix the
    // error message should point at.
    let mut body = serde_json::json!({ "version": meta.version, "channel": "stable" });
    if !changelog.trim().is_empty() {
        body["changelog_md"] = changelog.trim().into();
    }
    let r = client
        .post(format!("{base}/api/v1/mods/{}/releases", meta.slug))
        .header("authorization", &bearer)
        .json(&body)
        .send()
        .map_err(net)?;
    if !r.status().is_success() {
        return Err(err_body(
            "creating the release (already published this version? bump it and retry)",
            r,
        ));
    }
    #[derive(Deserialize)]
    struct Release {
        id: String,
    }
    let release: Release = r.json().map_err(net)?;

    let bytes = std::fs::read(archive).map_err(|e| format!("{}: {e}", archive.display()))?;
    let r = client
        .put(format!("{base}/api/v1/releases/{}/archive", release.id))
        .header("authorization", &bearer)
        .header("content-type", "application/zip")
        .body(bytes)
        .send()
        .map_err(net)?;
    if !r.status().is_success() {
        return Err(err_body("uploading the archive", r));
    }

    // Complete runs the scan; a rejected status comes back as data, not an
    // error, because the findings are the useful part.
    let r = client
        .post(format!("{base}/api/v1/releases/{}/complete", release.id))
        .header("authorization", &bearer)
        .send()
        .map_err(net)?;
    if !r.status().is_success() {
        return Err(err_body("completing the release", r));
    }
    #[derive(Deserialize)]
    struct Status {
        status: String,
        #[serde(default)]
        findings: Vec<Finding>,
    }
    let status: Status = r.json().map_err(net)?;

    Ok(PublishView {
        slug: meta.slug.clone(),
        version: meta.version.clone(),
        status: status.status,
        findings: status.findings,
        url: format!("{base}/mods/{}", meta.slug),
    })
}
