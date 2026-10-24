//! What a launch checks first, and what the game asks for at its main menu.
//!
//! Three questions, each answered from what the launcher already keeps:
//!
//! * **Out of date** (`check`): the MJOLNIR code mods in the game against the
//!   signed set, the runtime bundle against the release bucket, and every
//!   installed hub mod (the CE runtime pack, maps) against the hub, the same
//!   checks the Updates screen makes.
//! * **Intact** (`verify`): the runtime bundle's files against its cached
//!   manifest, each hub mod's cache against the `container_hashes` recorded at
//!   install, and each code mod's tree against its recorded digest. No
//!   network.
//! * **Unsupported mods** (`unsupported.rs`).
//!
//! The game asks the first and third through this executable, run without a
//! window (`--check-updates --out <file>`), the way it asks for a map
//! (docs/live_map_install.md): its own process has no network client but the
//! hub calls, and the launcher's answer is the one the Updates screen would
//! give. See docs/update_check.md.

use serde::Serialize;
use std::fs;
use std::path::Path;

use crate::unsupported::UnsupportedMod;

/// One thing a newer release exists for.
#[derive(Debug, Clone, Serialize)]
pub struct Outdated {
    /// `"core"` (the runtime bundle), `"code"` (a code mod) or `"content"` (a
    /// hub mod: the CE runtime pack, a map).
    pub kind: String,
    /// The code mod's id or the hub mod's slug; `"modpack"` for the core.
    pub id: String,
    pub name: String,
    pub installed: Option<String>,
    pub latest: String,
    /// The hub release to install, for `"content"`.
    pub release_id: Option<String>,
    /// The same release again, for files a map install lost.
    pub repair: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct UpdateCheck {
    pub checked_at: u64,
    pub items: Vec<Outdated>,
    /// Sources that could not be asked (offline, a server down). Not out of
    /// date, and not up to date either.
    pub unreachable: Vec<String>,
    pub unsupported: Vec<UnsupportedMod>,
}

/// One thing on disk that is not what was installed.
#[derive(Debug, Clone, Serialize)]
pub struct Problem {
    /// `"core"`, `"content"` or `"code"`, as for [`Outdated`].
    pub kind: String,
    pub id: String,
    pub name: String,
    pub detail: String,
    /// The hub release a repair downloads again, for `"content"`.
    pub release_id: Option<String>,
}

fn now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// Everything out of date, with the sources that could not be checked. The
/// three sources run side by side: the hub one makes a request per
/// installed mod.
pub fn check() -> UpdateCheck {
    let (core, (code, content)) = std::thread::scope(|s| {
        let core = s.spawn(crate::modpack_update);
        let code = s.spawn(crate::hub::code_mods_outdated);
        let content = s.spawn(crate::hub::check_updates);
        (
            core.join().unwrap_or_else(|_| Err("panicked".into())),
            (
                code.join().unwrap_or_else(|_| Err("panicked".into())),
                content.join().unwrap_or_else(|_| Err("panicked".into())),
            ),
        )
    });
    let mut items = Vec::new();
    let mut unreachable = Vec::new();

    // Only an install that has the runtime bundle can be behind on it: one
    // without has nothing for the game to read this from anyway.
    match core {
        Ok(m) if m.update_available && m.installed_version.is_some() => items.push(Outdated {
            kind: "core".into(),
            id: "modpack".into(),
            name: "MJOLNIR core (UE4SS)".into(),
            installed: m.installed_version,
            latest: m.latest_version,
            release_id: None,
            repair: false,
        }),
        Ok(_) => {}
        Err(e) => unreachable.push(format!("the release server: {e}")),
    }
    match code {
        Ok(mods) => items.extend(mods.into_iter().map(|m| Outdated {
            kind: "code".into(),
            name: m.id.clone(),
            id: m.id,
            installed: (!m.installed.is_empty()).then_some(m.installed),
            latest: m.latest,
            release_id: None,
            repair: false,
        })),
        Err(e) => unreachable.push(format!("the signed code-mod set: {e}")),
    }
    match content {
        Ok(updates) => items.extend(updates.into_iter().map(|u| Outdated {
            kind: "content".into(),
            id: u.slug,
            name: u.name,
            installed: Some(u.installed_version),
            latest: u.latest_version,
            release_id: Some(u.latest_release_id),
            repair: u.repair.is_some(),
        })),
        Err(e) => unreachable.push(format!("the hub: {e}")),
    }
    UpdateCheck {
        checked_at: now(),
        items,
        unreachable,
        unsupported: crate::unsupported::scan().unwrap_or_default(),
    }
}

/// Everything on disk that differs from what was installed.
pub fn verify() -> Vec<Problem> {
    let mut out = Vec::new();
    // No cached manifest: the bundle was never installed by this launcher,
    // and there is nothing to compare with.
    if let Ok(core) = crate::verify_install() {
        let bad = core.failed.len() + core.missing.len();
        if bad > 0 {
            let mut names: Vec<&str> = core.missing.iter().chain(&core.failed).map(String::as_str).collect();
            names.truncate(3);
            out.push(Problem {
                kind: "core".into(),
                id: "modpack".into(),
                name: "MJOLNIR core (UE4SS)".into(),
                detail: format!(
                    "{bad} of {} files missing or changed ({}{})",
                    core.checked,
                    names.join(", "),
                    if bad > names.len() { ", …" } else { "" }
                ),
                release_id: None,
            });
        }
    }
    for m in crate::hub::verify_installed().into_iter().filter(|m| !m.ok) {
        let mut parts = Vec::new();
        if !m.missing.is_empty() {
            parts.push(format!("{} files missing", m.missing.len()));
        }
        if !m.tampered.is_empty() {
            parts.push(format!("{} files changed", m.tampered.len()));
        }
        out.push(Problem {
            kind: "content".into(),
            id: m.slug,
            name: m.name,
            detail: parts.join(", "),
            release_id: Some(m.release_id),
        });
    }
    for id in crate::hub::code_mods_modified() {
        out.push(Problem {
            kind: "code".into(),
            name: id.clone(),
            id,
            detail: "its files differ from the signed release".into(),
            release_id: None,
        });
    }
    out
}

/// `--check-updates --out <file>`: the check, written whole to `file` as
/// JSON (a temporary file renamed over it, since the game polls for it).
/// Exits 0 when the answer was written.
pub fn run_check(out: &Path) -> i32 {
    crate::hub::record_exe_path();
    let result = check();
    let Ok(text) = serde_json::to_string(&result) else {
        return 1;
    };
    let tmp = out.with_extension("tmp");
    if fs::write(&tmp, text).is_err() {
        return 1;
    }
    for _ in 0..20 {
        if fs::rename(&tmp, out).is_ok() {
            return 0;
        }
        std::thread::sleep(std::time::Duration::from_millis(25));
    }
    1
}
