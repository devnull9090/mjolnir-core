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
//!   install, and each code mod's shipped files against the hashes recorded
//!   at install. No network.
//! * **Unsupported mods** (`unsupported.rs`).
//!
//! Each item is reported as it starts and ends ([`Step`]), so the launch
//! dialog shows a checklist filling in rather than one spinner.
//!
//! The game asks the first and third through this executable, run without a
//! window (`--check-updates --out <file>`), the way it asks for a map
//! (docs/live_map_install.md): its own process has no network client but the
//! hub calls, and the launcher's answer is the one the Updates screen would
//! give. See docs/update_check.md.

use serde::Serialize;
use std::fs;
use std::path::Path;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;

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

/// One line of the launch dialog's checklist, sent when an item is queued,
/// starts and ends (the `preflight-progress` event).
#[derive(Debug, Clone, Serialize)]
pub struct Step {
    /// `"updates"`, `"files"` or `"mods"`: the checklist's section.
    pub group: &'static str,
    /// Stable for the item: a later step with the same key replaces it.
    pub key: String,
    pub label: String,
    /// `"pending"`, `"running"`, `"ok"`, `"warn"` (found something) or
    /// `"fail"` (could not check).
    pub state: &'static str,
    pub detail: Option<String>,
}

/// Where steps go: the webview's event, or nowhere (`--check-updates`).
pub type Report<'a> = &'a (dyn Fn(Step) + Sync);

pub fn no_report(_: Step) {}

fn step(report: Report, group: &'static str, key: &str, label: &str, state: &'static str, detail: Option<String>) {
    report(Step {
        group,
        key: key.to_string(),
        label: label.to_string(),
        state,
        detail,
    });
}

fn now() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

fn plural(n: usize, word: &str) -> String {
    format!("{n} {word}{}", if n == 1 { "" } else { "s" })
}

/// How many hub mods are asked about at once: a request or two each, so a
/// few in flight keep a long map list quick without hammering the hub.
const HUB_CHECKS_AT_ONCE: usize = 4;

const CORE_NAME: &str = "MJOLNIR core (UE4SS)";
const CODE_NAME: &str = "Code mods (the signed set)";
const UNSUPPORTED_NAME: &str = "Mods MJOLNIR did not install";

fn check_core(report: Report, push: &dyn Fn(Outdated), fail: &dyn Fn(String)) {
    step(report, "updates", "core", CORE_NAME, "running", None);
    match crate::modpack_update() {
        // Only an install that has the runtime bundle can be behind on it.
        Ok(m) if m.update_available && m.installed_version.is_some() => {
            let from = m.installed_version.clone().unwrap_or_default();
            step(report, "updates", "core", CORE_NAME, "warn", Some(format!("{from} → {}", m.latest_version)));
            push(Outdated {
                kind: "core".into(),
                id: "modpack".into(),
                name: CORE_NAME.into(),
                installed: m.installed_version,
                latest: m.latest_version,
                release_id: None,
                repair: false,
            });
        }
        Ok(m) => {
            let detail = m.installed_version.map_or("not installed".into(), |v| format!("v{v}"));
            step(report, "updates", "core", CORE_NAME, "ok", Some(detail));
        }
        Err(e) => {
            step(report, "updates", "core", CORE_NAME, "fail", Some(e.clone()));
            fail(format!("the release server: {e}"));
        }
    }
}

fn check_code(report: Report, push: &dyn Fn(Outdated), fail: &dyn Fn(String)) {
    step(report, "updates", "code", CODE_NAME, "running", None);
    let mods = match crate::hub::code_mods_outdated() {
        Ok(mods) => mods,
        Err(e) => {
            step(report, "updates", "code", CODE_NAME, "fail", Some(e.clone()));
            fail(format!("the signed code-mod set: {e}"));
            return;
        }
    };
    let behind = mods.iter().filter(|m| m.outdated).count();
    for m in mods {
        let key = format!("code:{}", m.id);
        if !m.outdated {
            step(report, "updates", &key, &m.id, "ok", Some(format!("v{}", m.installed)));
            continue;
        }
        let from = if m.installed.is_empty() { "?" } else { m.installed.as_str() };
        step(report, "updates", &key, &m.id, "warn", Some(format!("{from} → {}", m.latest)));
        push(Outdated {
            kind: "code".into(),
            name: m.id.clone(),
            id: m.id,
            installed: (!m.installed.is_empty()).then_some(m.installed),
            latest: m.latest,
            release_id: None,
            repair: false,
        });
    }
    if behind == 0 {
        step(report, "updates", "code", CODE_NAME, "ok", Some("all current".into()));
    } else {
        step(report, "updates", "code", CODE_NAME, "warn", Some(format!("{behind} behind")));
    }
}

fn check_hub(
    report: Report,
    hub_mods: &[crate::hub::InstalledHubMod],
    push: &(dyn Fn(Outdated) + Sync),
    fail: &dyn Fn(String),
) {
    let next = AtomicUsize::new(0);
    let failed = AtomicUsize::new(0);
    std::thread::scope(|s| {
        for _ in 0..HUB_CHECKS_AT_ONCE {
            s.spawn(|| loop {
                let Some(inst) = hub_mods.get(next.fetch_add(1, Ordering::Relaxed)) else {
                    break;
                };
                let key = format!("content:{}", inst.slug);
                step(report, "updates", &key, &inst.name, "running", None);
                match crate::hub::check_update_one(inst) {
                    Ok(Some(u)) => {
                        let detail = if u.repair.is_some() {
                            format!("v{} again: files missing", u.latest_version)
                        } else {
                            format!("{} → {}", u.installed_version, u.latest_version)
                        };
                        step(report, "updates", &key, &inst.name, "warn", Some(detail));
                        push(Outdated {
                            kind: "content".into(),
                            id: u.slug,
                            name: u.name,
                            installed: Some(u.installed_version),
                            latest: u.latest_version,
                            release_id: Some(u.latest_release_id),
                            repair: u.repair.is_some(),
                        });
                    }
                    Ok(None) => {
                        step(report, "updates", &key, &inst.name, "ok", Some(format!("v{}", inst.version)))
                    }
                    Err(e) => {
                        failed.fetch_add(1, Ordering::Relaxed);
                        step(report, "updates", &key, &inst.name, "fail", Some(e));
                    }
                }
            });
        }
    });
    let n = failed.into_inner();
    if n > 0 {
        fail(format!("the hub, for {}", plural(n, "mod")));
    }
}

/// Everything out of date, with the sources that could not be checked, each
/// item reported as it is checked. The three sources run side by side.
pub fn check(report: Report) -> UpdateCheck {
    let hub_mods = crate::hub::installed_mods();
    step(report, "updates", "core", CORE_NAME, "pending", None);
    step(report, "updates", "code", CODE_NAME, "pending", None);
    for m in &hub_mods {
        step(report, "updates", &format!("content:{}", m.slug), &m.name, "pending", None);
    }
    step(report, "mods", "unsupported", UNSUPPORTED_NAME, "pending", None);

    let items = Mutex::new(Vec::new());
    let unreachable = Mutex::new(Vec::new());
    let push = |o: Outdated| items.lock().unwrap_or_else(|e| e.into_inner()).push(o);
    let fail = |why: String| unreachable.lock().unwrap_or_else(|e| e.into_inner()).push(why);
    std::thread::scope(|s| {
        s.spawn(|| check_core(report, &push, &fail));
        s.spawn(|| check_code(report, &push, &fail));
        s.spawn(|| check_hub(report, &hub_mods, &push, &fail));
    });

    step(report, "mods", "unsupported", UNSUPPORTED_NAME, "running", None);
    let unsupported = crate::unsupported::scan().unwrap_or_default();
    if unsupported.is_empty() {
        step(report, "mods", "unsupported", UNSUPPORTED_NAME, "ok", Some("none".into()));
    } else {
        step(report, "mods", "unsupported", UNSUPPORTED_NAME, "warn", Some(format!("{} found", unsupported.len())));
    }

    // The core, the code mods, then hub mods in the order they were
    // installed, not the order the requests came back.
    let mut items = items.into_inner().unwrap_or_else(|e| e.into_inner());
    items.sort_by_key(|o| match o.kind.as_str() {
        "core" => 0,
        "code" => 1,
        _ => 2 + hub_mods.iter().position(|m| m.slug == o.id).unwrap_or(0),
    });
    UpdateCheck {
        checked_at: now(),
        items,
        unreachable: unreachable.into_inner().unwrap_or_else(|e| e.into_inner()),
        unsupported,
    }
}

/// Everything on disk that differs from what was installed, each item
/// reported as it is hashed (a hub mod's containers can be gigabytes).
pub fn verify(report: Report) -> Vec<Problem> {
    const CORE_FILES: &str = "MJOLNIR core files";
    const CODE_FILES: &str = "Code mod files";
    let hub_mods = crate::hub::installed_mods();
    step(report, "files", "files:core", CORE_FILES, "pending", None);
    for m in &hub_mods {
        step(report, "files", &format!("files:{}", m.slug), &m.name, "pending", None);
    }
    step(report, "files", "files:code", CODE_FILES, "pending", None);

    let mut out = Vec::new();
    step(report, "files", "files:core", CORE_FILES, "running", None);
    match crate::verify_install() {
        Ok(core) if core.failed.is_empty() && core.missing.is_empty() => {
            step(report, "files", "files:core", CORE_FILES, "ok", Some(plural(core.checked, "file")));
        }
        Ok(core) => {
            let bad = core.failed.len() + core.missing.len();
            let mut names: Vec<&str> = core.missing.iter().chain(&core.failed).map(String::as_str).collect();
            names.truncate(3);
            let detail = format!(
                "{bad} of {} files missing or changed ({}{})",
                core.checked,
                names.join(", "),
                if bad > names.len() { ", …" } else { "" }
            );
            step(report, "files", "files:core", CORE_FILES, "warn", Some(detail.clone()));
            out.push(Problem {
                kind: "core".into(),
                id: "modpack".into(),
                name: CORE_NAME.into(),
                detail,
                release_id: None,
            });
        }
        // No cached manifest: the bundle was never installed by this
        // launcher, and there is nothing to compare with.
        Err(_) => step(report, "files", "files:core", CORE_FILES, "ok", Some("nothing on record".into())),
    }

    for inst in &hub_mods {
        let key = format!("files:{}", inst.slug);
        step(report, "files", &key, &inst.name, "running", None);
        let m = crate::hub::verify_one(inst);
        if m.ok {
            step(report, "files", &key, &inst.name, "ok", Some(plural(inst.container_hashes.len(), "file")));
            continue;
        }
        let mut parts = Vec::new();
        if !m.missing.is_empty() {
            parts.push(format!("{} missing", plural(m.missing.len(), "file")));
        }
        if !m.tampered.is_empty() {
            parts.push(format!("{} changed", plural(m.tampered.len(), "file")));
        }
        let detail = parts.join(", ");
        step(report, "files", &key, &inst.name, "warn", Some(detail.clone()));
        out.push(Problem {
            kind: "content".into(),
            id: m.slug,
            name: m.name,
            detail,
            release_id: Some(m.release_id),
        });
    }

    step(report, "files", "files:code", CODE_FILES, "running", None);
    let code = crate::hub::code_mods_verify();
    let mut changed = 0;
    for (id, changes) in &code {
        let key = format!("files:code:{id}");
        if changes.is_empty() {
            step(report, "files", &key, id, "ok", Some("intact".into()));
            continue;
        }
        changed += 1;
        step(report, "files", &key, id, "warn", Some(format!("changed: {}", changes.join(", "))));
        out.push(Problem {
            kind: "code".into(),
            name: id.clone(),
            id: id.clone(),
            detail: "its files differ from the signed release".into(),
            release_id: None,
        });
    }
    match (code.len(), changed) {
        (0, _) => step(report, "files", "files:code", CODE_FILES, "ok", Some("nothing on record".into())),
        (n, 0) => step(report, "files", "files:code", CODE_FILES, "ok", Some(format!("{n} intact"))),
        (_, c) => step(report, "files", "files:code", CODE_FILES, "warn", Some(format!("{c} changed"))),
    }
    out
}

/// `--check-updates --out <file>`: the check, written whole to `file` as
/// JSON (a temporary file renamed over it, since the game polls for it).
/// Exits 0 when the answer was written.
pub fn run_check(out: &Path) -> i32 {
    crate::hub::record_exe_path();
    let result = check(&no_report);
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn steps_serialize_as_the_dialog_reads_them() {
        let seen = Mutex::new(Vec::new());
        let report = |s: Step| seen.lock().unwrap().push(s);
        step(&report, "files", "files:x", "X", "warn", Some("2 files changed".into()));
        let v = serde_json::to_value(&seen.lock().unwrap()[0]).unwrap();
        assert_eq!(
            v,
            serde_json::json!({ "group": "files", "key": "files:x", "label": "X", "state": "warn", "detail": "2 files changed" })
        );
        assert_eq!(plural(1, "file"), "1 file");
        assert_eq!(plural(3, "file"), "3 files");
    }
}
