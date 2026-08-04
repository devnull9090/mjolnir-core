//! Release notes, fetched for the "What's new" dialog.
//!
//! The entries are authored once in the repository's `changelog/` directory and
//! published by the hub at `/api/changelog`; nothing is embedded here, so an
//! entry corrected after a release reaches installs that already have the
//! build.
//!
//! Fetched in Rust rather than by the webview for the same reason `hub_api` is
//! (see hub.rs): a request made here is not subject to the webview's origin
//! rules or to a content security policy, so it behaves identically under
//! `tauri dev` and in a packaged build. The launcher currently ships no CSP,
//! which means a webview fetch would work today and break silently the day one
//! is added — and a CSP that only bites in packaged builds has already cost
//! this project a release (tag editor 0.6.1).

use serde_json::Value;

const CHANGELOG_URL: &str = "https://mjolnircore.com/api/changelog";

/// Fetches the published changelog.
///
/// `product` and `since` narrow it to the releases one install actually
/// crossed; both are optional, and `since` is only meaningful with a product
/// because versions are only ordered within one.
///
/// The response is passed through as JSON rather than modelled here. The
/// frontend already has the shape from `@mjolnir/hub-kit`, and re-declaring it
/// in Rust would mean two definitions that can disagree about a dialog.
#[tauri::command]
pub async fn fetch_changelog(product: Option<String>, since: Option<String>) -> Result<Value, String> {
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

    let client = reqwest::Client::builder()
        // Short: this is decoration on a completed update, and nobody should
        // wait on it. The caller treats a failure as "show nothing".
        .timeout(std::time::Duration::from_secs(10))
        .build()
        .map_err(|e| format!("HTTP client error: {e}"))?;

    let resp = client
        .get(url)
        .send()
        .await
        .map_err(|e| format!("Cannot reach the changelog: {e}"))?;

    if !resp.status().is_success() {
        return Err(format!("Changelog request returned {}", resp.status()));
    }

    resp.json::<Value>()
        .await
        .map_err(|e| format!("Cannot read the changelog: {e}"))
}
