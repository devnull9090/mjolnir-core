//! Publishing a project to the MJOLNIR hub.
//!
//! The hub's publish flow is four calls (`docs/hub_architecture.md` §7):
//! create the mod page if it does not exist, create the release, upload the
//! archive, then complete — which runs the server-side scan and returns its
//! findings. Auth is a user-minted API key carrying `mods:write`; the
//! launcher's device pairing deliberately cannot publish.

use std::path::Path;
use std::time::Duration;

use serde::{Deserialize, Serialize};

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
