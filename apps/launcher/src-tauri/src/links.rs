//! `mjolnir://` links: what a website hands the launcher.
//!
//! Four website forms, and Discord's fixed launch protocol:
//!
//!   mjolnir://mod/<slug>      that mod's page in Browse Hub
//!   mjolnir://map/<CODE>      that map in Browse Hub's Maps tab
//!   mjolnir://join/<lobby>    join a listed multiplayer game (`hub_join_lobby`)
//!   mjolnir://update          update everything, then start the game again:
//!                             what the game's out-of-date prompt opens
//!                             (docs/update_check.md)
//!   discord-1533237469259104458://  start the game for a pending Discord join
//!
//! Discord delivers the actual join secret to the game's IPC client. Its
//! launch URL never contains a lobby id, credential, or executable argument.
//!
//! The scheme is registered for the launcher (tauri.conf.json, and again at
//! startup), so Windows starts it with the link as its only argument. A link
//! that arrives while a launcher is open reaches that one instead
//! (tauri-plugin-single-instance hands the second process's arguments over and
//! exits it). Either way it lands in [`deliver`]: kept in [`Pending`] until the
//! webview takes it (`take_pending_link`), and announced as `mjolnir-link`.
//!
//! A link is a web page's to write, so it is parsed as untrusted input: one
//! of the four forms with a value the hub could have produced, or it is
//! dropped (and logged). `update` only ever starts an update and a launch,
//! the same as the player's own Launch button, so a web page sending it can
//! do nothing a click could not.

use serde::Serialize;
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager};

pub const SCHEME: &str = "mjolnir";
pub const DISCORD_SCHEME: &str = "discord-1533237469259104458";

/// The event the webview listens for; its payload is the [`Link`].
pub const EVENT: &str = "mjolnir-link";

/// One understood link, as the webview receives it:
/// `{ "kind": "mod", "slug": … }`, `{ "kind": "map", "code": … }` or
/// `{ "kind": "join", "lobby": … }`, `{ "kind": "update" }`, or
/// `{ "kind": "discordlaunch" }`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "lowercase")]
pub enum Link {
    Mod { slug: String },
    Map { code: String },
    Join { lobby: String },
    Update,
    DiscordLaunch,
}

/// The latest link the webview has not taken yet. Only the latest: two links
/// clicked before the window was up mean the second one.
#[derive(Default)]
pub struct Pending(pub Mutex<Option<Link>>);

/// A hub mod slug, by the hub's own rule (hub/src/lib/api/schemas.ts `SLUG`:
/// `^[a-z0-9][a-z0-9-]{1,63}$`).
fn valid_slug(s: &str) -> bool {
    let b = s.as_bytes();
    (2..=64).contains(&b.len())
        && (b[0].is_ascii_lowercase() || b[0].is_ascii_digit())
        && b.iter()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || *c == b'-')
}

/// A lobby id: the hub makes them with `crypto.randomUUID()`. Any id of that
/// alphabet is accepted rather than only a UUID, so the hub can change its
/// ids without a launcher release; the game looks it up in the list anyway.
pub(crate) fn valid_lobby(s: &str) -> bool {
    (1..=64).contains(&s.len()) && s.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-')
}

/// Read one link. Discord's protocol accepts only an empty path. Website
/// links tolerate the scheme and kind in any case (Windows and browsers
/// normalise them differently), one trailing slash (some browsers add it),
/// and a query or fragment, which is ignored (a site's tracking tag).
pub fn parse(raw: &str) -> Option<Link> {
    let raw = raw.trim();
    let (scheme, rest) = raw.split_once("://")?;
    if scheme.eq_ignore_ascii_case(DISCORD_SCHEME) {
        return matches!(rest, "" | "/").then_some(Link::DiscordLaunch);
    }
    if !scheme.eq_ignore_ascii_case(SCHEME) {
        return None;
    }
    let rest = rest.split(['?', '#']).next().unwrap_or_default();
    let rest = rest.strip_suffix('/').unwrap_or(rest);
    if rest.eq_ignore_ascii_case("update") {
        return Some(Link::Update);
    }
    let (kind, value) = rest.split_once('/')?;
    match kind.to_ascii_lowercase().as_str() {
        "mod" if valid_slug(value) => Some(Link::Mod {
            slug: value.to_string(),
        }),
        "map" if value.len() == 3 && value.bytes().all(|c| c.is_ascii_alphanumeric()) => {
            Some(Link::Map {
                code: value.to_ascii_uppercase(),
            })
        }
        "join" if valid_lobby(value) => Some(Link::Join {
            lobby: value.to_string(),
        }),
        _ => None,
    }
}

/// Bring the launcher's window to the front: a clicked link expects to see
/// the launcher, minimized or behind the browser as it may be.
pub fn focus_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

/// A link arrived (at startup, or from a second instance): keep it for the
/// webview, bring the window up, and announce it. Kept before it is
/// announced, so a webview that is still loading — and so not yet
/// listening — finds it when it asks.
pub fn deliver(app: &AppHandle, raw: &str) {
    let Some(link) = parse(raw) else {
        eprintln!("links: ignored {raw:?}");
        return;
    };
    if let Some(pending) = app.try_state::<Pending>() {
        *pending.0.lock().unwrap_or_else(|e| e.into_inner()) = Some(link.clone());
    }
    focus_main(app);
    if let Err(e) = app.emit(EVENT, &link) {
        eprintln!("links: {e}");
    }
}

/// The link waiting for the webview, if any, which it now has: called on
/// mount and on every `mjolnir-link`, so a link announced before anything
/// listened is still acted on, and acted on once.
#[tauri::command]
pub fn take_pending_link(pending: tauri::State<'_, Pending>) -> Option<Link> {
    pending.0.lock().unwrap_or_else(|e| e.into_inner()).take()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_four_forms_parse() {
        assert_eq!(parse("mjolnir://update"), Some(Link::Update));
        assert_eq!(parse("MJOLNIR://Update/"), Some(Link::Update));
        assert_eq!(
            parse("mjolnir://mod/mjolnir-flycam"),
            Some(Link::Mod {
                slug: "mjolnir-flycam".into()
            })
        );
        assert_eq!(
            parse("mjolnir://map/bgl"),
            Some(Link::Map { code: "BGL".into() })
        );
        assert_eq!(
            parse("mjolnir://join/0b6f3c1e-9a2d-4c7e-8f10-2a3b4c5d6e7f"),
            Some(Link::Join {
                lobby: "0b6f3c1e-9a2d-4c7e-8f10-2a3b4c5d6e7f".into()
            })
        );
    }

    #[test]
    fn discord_only_opens_the_game_and_never_interprets_a_payload() {
        for raw in [
            "discord-1533237469259104458://",
            "DISCORD-1533237469259104458:///",
        ] {
            assert_eq!(parse(raw), Some(Link::DiscordLaunch));
            // The deep-link plugin parses URLs before delivering them.
            let url = tauri::Url::parse(raw).unwrap();
            assert_eq!(parse(url.as_str()), Some(Link::DiscordLaunch));
        }
        for raw in [
            "discord-1533237469259104459://",
            "discord-1533237469259104458://join/lobby-id",
            "discord-1533237469259104458://?secret=abc",
            "discord-1533237469259104458://#abc",
            "discord-1533237469259104458://%2f",
            "discord-1533237469259104458:// --install-map BGL",
            "discord-1533237469259104458:launch",
        ] {
            assert_eq!(parse(raw), None, "{raw:?} must not parse");
        }
    }

    #[test]
    fn installer_registers_both_protocols() {
        let config: serde_json::Value =
            serde_json::from_str(include_str!("../tauri.conf.json")).unwrap();
        let schemes = config["plugins"]["deep-link"]["desktop"]["schemes"]
            .as_array()
            .unwrap();
        assert!(schemes.iter().any(|s| s == SCHEME));
        assert!(schemes.iter().any(|s| s == DISCORD_SCHEME));
    }

    #[test]
    fn what_browsers_add_is_tolerated() {
        let want = Some(Link::Map { code: "D40".into() });
        assert_eq!(parse("mjolnir://map/D40/"), want);
        assert_eq!(parse("MJOLNIR://MAP/d40"), want);
        assert_eq!(parse("  mjolnir://map/D40?ref=site#top \n"), want);
    }

    #[test]
    fn anything_else_is_dropped() {
        for raw in [
            "",
            "mjolnir://",
            "mjolnir://mod",
            "mjolnir://mod/",
            "mjolnir://mod/a",       // the hub's slugs are two or more
            "mjolnir://mod/-flycam", // starts with a dash
            "mjolnir://mod/Flycam",  // upper case is never a slug
            "mjolnir://mod/fly_cam",
            "mjolnir://mod/flycam/extra",
            "mjolnir://mod/..%2F..%2Fsettings",
            "mjolnir://map/BG",
            "mjolnir://map/BGLX",
            "mjolnir://map/B-L",
            "mjolnir://join/abc def",
            "mjolnir://join/../../x",
            "mjolnir://launch/BGL",
            "mjolnir://update/now",
            "mjolnir://updates",
            "mjolnir:///update",
            "https://mjolnircore.com/map/BGL",
            "mjolnir:map/BGL",
            "--install-map",
        ] {
            assert_eq!(parse(raw), None, "{raw:?} must not parse");
        }
        assert!(parse(&format!("mjolnir://mod/{}", "a".repeat(64))).is_some());
        assert_eq!(parse(&format!("mjolnir://mod/{}", "a".repeat(65))), None);
        assert_eq!(parse(&format!("mjolnir://join/{}", "a".repeat(65))), None);
    }

    #[test]
    fn a_link_serializes_as_the_webview_reads_it() {
        let json = |l: Link| serde_json::to_value(l).unwrap();
        assert_eq!(
            json(Link::Mod { slug: "x1".into() }),
            serde_json::json!({ "kind": "mod", "slug": "x1" })
        );
        assert_eq!(
            json(Link::Map { code: "BGL".into() }),
            serde_json::json!({ "kind": "map", "code": "BGL" })
        );
        assert_eq!(
            json(Link::Join {
                lobby: "id-1".into()
            }),
            serde_json::json!({ "kind": "join", "lobby": "id-1" })
        );
        assert_eq!(json(Link::Update), serde_json::json!({ "kind": "update" }));
        assert_eq!(
            json(Link::DiscordLaunch),
            serde_json::json!({ "kind": "discordlaunch" })
        );
    }
}
