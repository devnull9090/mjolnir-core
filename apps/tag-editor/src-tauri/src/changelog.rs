//! Release notes, fetched for the "What's new" dialog.
//!
//! The entries are authored once in the repository's `changelog/` directory and
//! published by the hub at `/api/changelog`. Nothing is embedded here, so an
//! entry corrected after a release reaches installs that already have the
//! build.
//!
//! Fetched here rather than by the webview because it could not be done in the
//! webview at all: this app's CSP allows `connect-src 'self' ipc:`, so a fetch
//! to mjolnircore.com is refused. That policy is not applied under `tauri dev`,
//! which is exactly how 0.6.0 shipped unable to play audio — so the request
//! goes over IPC, where dev and packaged builds behave the same.

use serde_json::Value;

const CHANGELOG_URL: &str = "https://mjolnircore.com/api/changelog";

/// Fetches this product's releases newer than `since`.
///
/// The response is passed through as JSON rather than modelled here: the
/// frontend already has the shape from `@mjolnir/hub-kit`, and a second
/// definition in Rust would be one that can disagree with it.
#[tauri::command]
pub fn fetch_changelog(product: Option<String>, since: Option<String>) -> Result<Value, String> {
    let mut url = reqwest::Url::parse(CHANGELOG_URL).map_err(|e| e.to_string())?;
    {
        let mut query = url.query_pairs_mut();
        if let Some(product) = product.as_deref() {
            query.append_pair("product", product);
        }
        if let Some(since) = since.as_deref() {
            query.append_pair("since", since);
        }
    }

    let client = reqwest::blocking::Client::builder()
        // Short: this is decoration on an update that already happened, and
        // nobody should wait on it. The caller treats a failure as "show
        // nothing".
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|e| format!("HTTP client error: {e}"))?;

    let resp = client
        .get(url)
        .send()
        .map_err(|e| format!("Cannot reach the changelog: {e}"))?;

    if !resp.status().is_success() {
        return Err(format!("Changelog request returned {}", resp.status()));
    }

    resp.json::<Value>()
        .map_err(|e| format!("Cannot read the changelog: {e}"))
}
