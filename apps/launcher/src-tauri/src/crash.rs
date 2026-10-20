//! Crash reports (docs/crash_reports.md): notice the game's crashes, keep
//! the log that goes with each, and send a small bundle to the hub when the
//! player says so. The hub decides whether it also wants the full dump, and
//! the player is asked again before that goes.
//!
//! The launcher starts the game through Steam or the Xbox app, so it has no
//! process to watch. It watches the folders UE's crash handler writes into
//! instead, which also catches a game started from Steam directly.

use std::collections::BTreeMap;
use std::fs::{self, File};
use std::io::{self, Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::sync::{Mutex, MutexGuard};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Emitter};

use crate::minidump;

/// The Xbox app's package family. If its build is sandboxed, its crashes
/// land under the package's own LocalAppData.
const XBOX_PACKAGE: &str = "Microsoft.198377053870B_8wekyb3d8bbwe";
/// How long a crash folder's files must sit unchanged before it is read: the
/// dump takes a few seconds to write.
const SETTLE: Duration = Duration::from_secs(15);
/// How often the folders are checked while the launcher is open.
const POLL: Duration = Duration::from_secs(10);
/// How much of UE4SS.log a report carries, from the end.
const LOG_TAIL: u64 = 4 * 1024 * 1024;
/// A crash older than this gets no log: whatever UE4SS.log holds by then is
/// another session's.
const LOG_WINDOW_SECS: u64 = 24 * 3600;
/// Crashes Settings lists.
const LISTED: usize = 20;
/// .NET ticks (100 ns since 0001-01-01) at the Unix epoch: `TimeOfCrash`.
const UNIX_EPOCH_TICKS: u64 = 621_355_968_000_000_000;
const CONTEXT: &str = "CrashContext.runtime-xml";
const DUMP: &str = "UEMinidump.dmp";
const SAVED_LOG: &str = "UE4SS.log";
/// Emptied in the XML before it leaves the machine.
const PRIVATE_TAGS: &[&str] = &["MachineId", "LoginId", "EpicAccountId", "UserName"];

// ─── State ──────────────────────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize, Clone, Copy, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    /// Not yet put to the player.
    New,
    /// On disk before the launcher first looked: listed, never prompted.
    Old,
    Dismissed,
    Sent,
}

/// Where the hub wants a file put: a path under the hub API, which gets the
/// paired key, or an absolute presigned URL, which must not.
#[derive(Debug, Serialize, Deserialize, Clone)]
struct Upload {
    #[serde(default = "put")]
    method: String,
    url: String,
    #[serde(default)]
    max_bytes: Option<u64>,
}

fn put() -> String {
    "PUT".into()
}

#[derive(Debug, Serialize, Deserialize, Clone)]
struct Record {
    status: Status,
    #[serde(default)]
    report_id: Option<String>,
    /// The hub asked for the full dump and the player has not answered.
    #[serde(default)]
    dump_requested: Option<Upload>,
    #[serde(default)]
    dump_sent: bool,
    /// The crash as first seen, kept with its bundle (`prepare`) in case the
    /// folder goes before the player answers.
    #[serde(default)]
    summary: Option<Crash>,
}

impl Record {
    fn new(status: Status) -> Record {
        Record { status, report_id: None, dump_requested: None, dump_sent: false, summary: None }
    }
}

#[derive(Debug, Serialize, Deserialize, Default)]
struct State {
    /// Unix seconds of the first scan. Crashes from before it never prompt:
    /// a player updating the launcher is not asked about last month's.
    since: u64,
    crashes: BTreeMap<String, Record>,
}

fn state_path() -> PathBuf {
    crate::hub::config_dir().join("crash_reports.json")
}

/// Saved logs and built bundles, one folder per crash.
fn store() -> PathBuf {
    crate::hub::config_dir().join("crash-reports")
}

/// The watcher thread and the commands both write the state file.
fn lock() -> MutexGuard<'static, ()> {
    static LOCK: Mutex<()> = Mutex::new(());
    LOCK.lock().unwrap_or_else(|e| e.into_inner())
}

/// None when there is no state file or it does not parse.
fn read_state() -> Option<State> {
    fs::read_to_string(state_path())
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
}

fn load_state() -> State {
    read_state().unwrap_or_default()
}

fn save_state(state: &State) -> Result<(), String> {
    fs::create_dir_all(crate::hub::config_dir()).map_err(|e| e.to_string())?;
    let json = serde_json::to_string_pretty(state).map_err(|e| e.to_string())?;
    fs::write(state_path(), json).map_err(|e| e.to_string())
}

fn update(id: &str, f: impl FnOnce(&mut Record)) -> Result<(), String> {
    let _guard = lock();
    let mut state = load_state();
    let record = state
        .crashes
        .get_mut(id)
        .ok_or_else(|| format!("No crash {id} on record"))?;
    f(record);
    save_state(&state)
}

// ─── Finding crashes ────────────────────────────────────────────────────

fn crash_roots() -> Vec<PathBuf> {
    let Some(local) = dirs::data_local_dir() else {
        return vec![];
    };
    vec![
        local.join("Meteorite/Saved/Crashes"),
        local
            .join("Packages")
            .join(XBOX_PACKAGE)
            .join("LocalCache/Local/Meteorite/Saved/Crashes"),
    ]
}

/// A crash folder's name, which UE makes unique per crash.
fn valid_id(id: &str) -> bool {
    id.starts_with("UECC-")
        && id.len() < 128
        && id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
}

/// Every crash folder, any root: (id, folder).
fn crash_dirs() -> Vec<(String, PathBuf)> {
    let mut out = Vec::new();
    for root in crash_roots() {
        let Ok(entries) = fs::read_dir(&root) else { continue };
        for e in entries.flatten() {
            let id = e.file_name().to_string_lossy().into_owned();
            if valid_id(&id) && e.path().is_dir() {
                out.push((id, e.path()));
            }
        }
    }
    out
}

fn find(id: &str) -> Result<PathBuf, String> {
    if !valid_id(id) {
        return Err(format!("{id:?} is not a crash"));
    }
    crash_dirs()
        .into_iter()
        .find(|(i, _)| i == id)
        .map(|(_, dir)| dir)
        .ok_or_else(|| format!("The crash folder {id} is gone"))
}

fn unix(t: SystemTime) -> u64 {
    t.duration_since(UNIX_EPOCH).map_or(0, |d| d.as_secs())
}

fn now() -> u64 {
    unix(SystemTime::now())
}

fn folder_time(dir: &Path) -> u64 {
    fs::metadata(dir).and_then(|m| m.modified()).map_or(0, unix)
}

/// Whether the crash handler has finished writing the folder.
fn settled(dir: &Path) -> bool {
    let Ok(entries) = fs::read_dir(dir) else { return false };
    let newest = entries
        .flatten()
        .filter_map(|e| e.metadata().ok()?.modified().ok())
        .max();
    newest.is_some_and(|t| t.elapsed().is_ok_and(|age| age >= SETTLE))
}

/// Records crash folders not seen before; returns those the player has not
/// been asked about. The first scan ever records everything as old, and so
/// does a scan whose state file no longer parses: better no prompt than one
/// for every crash on disk.
fn scan() -> Vec<String> {
    let _guard = lock();
    let (mut state, first_run) = match read_state() {
        Some(state) => (state, false),
        None => (State { since: now(), crashes: BTreeMap::new() }, true),
    };
    let mut fresh = Vec::new();
    let mut changed = first_run;
    for (id, dir) in crash_dirs() {
        if state.crashes.contains_key(&id) || !settled(&dir) {
            continue;
        }
        let status = if first_run {
            Status::Old
        } else {
            let crashed_at = read_context(&dir).map_or_else(|| folder_time(&dir), |c| c.crashed_at);
            if crashed_at < state.since {
                Status::Old
            } else {
                Status::New
            }
        };
        if status == Status::New {
            fresh.push(id.clone());
        }
        state.crashes.insert(id, Record::new(status));
        changed = true;
    }
    if changed {
        if let Err(e) = save_state(&state) {
            eprintln!("crash reports: {e}");
        }
    }
    fresh
}

/// Checks the crash folders every few seconds while the launcher is open,
/// keeps each new crash's log and bundle, and tells the webview
/// (`crash-detected`).
pub fn watch(app: AppHandle) {
    std::thread::spawn(move || loop {
        let fresh = scan();
        capture_logs();
        if !fresh.is_empty() {
            prepare(&fresh);
            let _ = app.emit("crash-detected", &fresh);
        }
        std::thread::sleep(POLL);
    });
}

/// Builds each new crash's bundle as soon as it is seen and keeps its
/// summary. The game's own crash reporter may delete the folder once its
/// send to 343 succeeds (unverified: every send failed on the dev box), and
/// the player may answer the banner long after that.
fn prepare(ids: &[String]) {
    for id in ids {
        let Ok(dir) = find(id) else { continue };
        let Some(crash) = describe(id, &dir, None) else { continue };
        if let Err(e) = build_bundle(&crash, &dir, &store().join(id)) {
            eprintln!("crash reports: bundling {id}: {e}");
            continue;
        }
        if let Err(e) = update(id, |r| r.summary = Some(crash)) {
            eprintln!("crash reports: {e}");
        }
    }
}

fn kept_bundle(id: &str) -> PathBuf {
    store().join(id).join(format!("crash-{id}.zip"))
}

// ─── What a crash folder says ───────────────────────────────────────────

/// The facts from `CrashContext.runtime-xml` worth having. Its call stack is
/// not one of them: in this game it is "UE4SS" and then one ntdll frame
/// over and over.
#[derive(Debug, Clone)]
struct Context {
    crashed_at: u64,
    crash_type: String,
    error_message: String,
    build_version: String,
    seconds_since_start: Option<u64>,
}

fn unescape(s: &str) -> String {
    s.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&apos;", "'")
        .replace("&amp;", "&")
}

fn xml_tag(xml: &str, tag: &str) -> Option<String> {
    let open = format!("<{tag}>");
    let start = xml.find(&open)? + open.len();
    let end = start + xml[start..].find(&format!("</{tag}>"))?;
    Some(unescape(xml[start..end].trim()))
}

impl Context {
    fn parse(xml: &str, fallback_time: u64) -> Context {
        let tag = |t: &str| xml_tag(xml, t).unwrap_or_default();
        let crashed_at = xml_tag(xml, "TimeOfCrash")
            .and_then(|t| t.parse::<u64>().ok())
            .filter(|&t| t > UNIX_EPOCH_TICKS)
            .map_or(fallback_time, |t| (t - UNIX_EPOCH_TICKS) / 10_000_000);
        Context {
            crashed_at,
            crash_type: tag("CrashType"),
            error_message: tag("ErrorMessage"),
            build_version: tag("BuildVersion"),
            seconds_since_start: xml_tag(xml, "SecondsSinceStart").and_then(|s| s.parse().ok()),
        }
    }
}

fn read_context(dir: &Path) -> Option<Context> {
    let xml = fs::read_to_string(dir.join(CONTEXT)).ok()?;
    Some(Context::parse(&xml, folder_time(dir)))
}

/// What the `.film-unreal` file's name says: `megalo--1_bck_<hash>_dist-server_<id>`
/// for a multiplayer (Megalo) game on BCK, `campaign_b30_...` for the campaign.
#[derive(Debug, Default, PartialEq)]
struct Film {
    mode: Option<String>,
    map: Option<String>,
    role: Option<String>,
}

fn parse_film(stem: &str) -> Film {
    let parts: Vec<&str> = stem.split('_').collect();
    let mode = parts.first().filter(|m| !m.is_empty()).map(|m| {
        if m.starts_with("megalo") {
            "multiplayer".to_string()
        } else {
            m.to_string()
        }
    });
    let map = parts.get(1).filter(|m| !m.is_empty()).map(|m| m.to_ascii_lowercase());
    let role = parts.iter().find_map(|p| p.strip_prefix("dist-")).map(str::to_string);
    Film { mode, map, role }
}

fn read_film(dir: &Path) -> Film {
    fs::read_dir(dir)
        .ok()
        .and_then(|entries| {
            entries.flatten().find_map(|e| {
                let name = e.file_name().to_string_lossy().into_owned();
                name.strip_suffix(".film-unreal").map(parse_film)
            })
        })
        .unwrap_or_default()
}

/// Hex numbers out, so the same assert with a different pointer reads the same.
fn normalize_message(msg: &str) -> String {
    let mut out = String::with_capacity(msg.len());
    let mut rest = msg;
    while let Some(i) = rest.find("0x") {
        out.push_str(&rest[..i]);
        let digits = rest[i + 2..].chars().take_while(|c| c.is_ascii_hexdigit()).count();
        out.push_str(if digits > 0 { "0x?" } else { "0x" });
        rest = &rest[i + 2 + digits..];
    }
    out.push_str(rest);
    let out = out.split_whitespace().collect::<Vec<_>>().join(" ");
    out.chars().take(300).collect()
}

/// Where the crash happened, as stable as the facts allow, and the signature
/// the hub groups by. A `Crash` names the faulting module and offset. Asserts
/// and GPU crashes fault inside KERNELBASE (UE raises them), so their message
/// is what tells them apart.
fn fault_and_signature(ctx: &Context, dump: Option<&minidump::Dump>) -> (String, String) {
    let module_fault = dump.and_then(|d| {
        let (module, offset) = minidump::fault(d)?;
        let code = d.exception?.code;
        Some((module.file_name().to_string(), offset, code))
    });
    // Masked first: an assert naming a file under the player's profile
    // would otherwise sign differently on every machine.
    let message = normalize_message(&mask_users(&ctx.error_message));
    let fault = match &module_fault {
        Some((module, offset, code))
            if ctx.crash_type == "Crash" && !module.eq_ignore_ascii_case("KERNELBASE.dll") =>
        {
            format!("{module}+0x{offset:x} (0x{code:08x})")
        }
        _ if !message.is_empty() => message,
        Some((module, offset, code)) => format!("{module}+0x{offset:x} (0x{code:08x})"),
        None => "unknown".to_string(),
    };
    let key = format!("{}|{}|{}", ctx.build_version, ctx.crash_type, fault);
    let signature = hex::encode(Sha256::digest(key.as_bytes()))[..16].to_string();
    (fault, signature)
}

/// A crash as the webview lists it.
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Crash {
    pub id: String,
    /// Unix seconds.
    pub crashed_at: u64,
    pub crash_type: String,
    pub error_message: String,
    pub build_version: String,
    pub seconds_since_start: Option<u64>,
    /// "multiplayer", "campaign", or the film's own word.
    pub mode: Option<String>,
    /// Scenario code, lower case.
    pub map: Option<String>,
    /// The installed map pack's name for that code, when there is one.
    pub map_name: Option<String>,
    pub role: Option<String>,
    pub fault: String,
    pub signature: String,
    pub dump_bytes: u64,
    /// The crash folder, or this launcher's kept copy once that is gone.
    pub folder: String,
    pub log_saved: bool,
    pub status: Status,
    pub report_id: Option<String>,
    pub dump_requested: bool,
    pub dump_sent: bool,
}

fn describe(id: &str, dir: &Path, record: Option<&Record>) -> Option<Crash> {
    let ctx = read_context(dir)?;
    let film = read_film(dir);
    let dump_path = dir.join(DUMP);
    let dump_bytes = fs::metadata(&dump_path).map_or(0, |m| m.len());
    let dump = File::open(&dump_path).ok().and_then(|mut f| minidump::read(&mut f).ok());
    let (fault, signature) = fault_and_signature(&ctx, dump.as_ref());
    let map_name = film.map.as_deref().and_then(crate::hub::map_name);
    Some(Crash {
        id: id.to_string(),
        crashed_at: ctx.crashed_at,
        crash_type: ctx.crash_type,
        error_message: ctx.error_message,
        build_version: ctx.build_version,
        seconds_since_start: ctx.seconds_since_start,
        mode: film.mode,
        map: film.map,
        map_name,
        role: film.role,
        fault,
        signature,
        dump_bytes,
        folder: dir.to_string_lossy().into_owned(),
        log_saved: store().join(id).join(SAVED_LOG).exists(),
        status: record.map_or(Status::Old, |r| r.status),
        report_id: record.and_then(|r| r.report_id.clone()),
        dump_requested: record.is_some_and(|r| r.dump_requested.is_some()),
        dump_sent: record.is_some_and(|r| r.dump_sent),
    })
}

/// A crash whose folder is gone, from what was kept when it was seen.
fn from_summary(id: &str, record: &Record) -> Option<Crash> {
    let mut crash = record.summary.clone()?;
    if !kept_bundle(id).exists() {
        return None;
    }
    crash.folder = store().join(id).to_string_lossy().into_owned();
    crash.status = record.status;
    crash.report_id = record.report_id.clone();
    crash.dump_requested = record.dump_requested.is_some();
    crash.dump_sent = record.dump_sent;
    Some(crash)
}

/// The newest crashes, newest first.
pub fn list() -> Vec<Crash> {
    // Whichever of this and the watcher records a crash first prepares it.
    let fresh = scan();
    capture_logs();
    prepare(&fresh);
    let state = {
        let _guard = lock();
        load_state()
    };
    // (time, id, folder): a folder on disk, or a kept copy of one deleted.
    let on_disk = crash_dirs();
    let mut rows: Vec<(u64, String, Option<PathBuf>)> = on_disk
        .iter()
        .filter(|(id, _)| state.crashes.contains_key(id))
        .map(|(id, dir)| (folder_time(dir), id.clone(), Some(dir.clone())))
        .collect();
    for (id, record) in &state.crashes {
        if let Some(summary) = &record.summary {
            if !on_disk.iter().any(|(i, _)| i == id) {
                rows.push((summary.crashed_at, id.clone(), None));
            }
        }
    }
    rows.sort_by(|a, b| b.0.cmp(&a.0));
    rows.into_iter()
        .take(LISTED)
        .filter_map(|(_, id, dir)| {
            let record = state.crashes.get(&id);
            match dir {
                Some(dir) => describe(&id, &dir, record),
                None => from_summary(&id, record?),
            }
        })
        .collect()
}

// ─── The log ────────────────────────────────────────────────────────────

fn ue4ss_log() -> Option<PathBuf> {
    let (root, _) = crate::find_game_install()?;
    let log = crate::binaries_dir(&root).join("ue4ss").join("UE4SS.log");
    log.exists().then_some(log)
}

/// Days from 1970-01-01 to a civil date (Howard Hinnant's algorithm).
fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400;
    let doy = (153 * (if m > 2 { m - 3 } else { m + 9 }) + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146_097 + doe - 719_468
}

fn civil_from_days(z: i64) -> (i64, i64, i64) {
    let z = z + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    (yoe + era * 400 + if m <= 2 { 1 } else { 0 }, m, d)
}

fn iso8601(secs: u64) -> String {
    let secs = secs as i64;
    let (y, m, d) = civil_from_days(secs.div_euclid(86_400));
    let t = secs.rem_euclid(86_400);
    format!("{y:04}-{m:02}-{d:02}T{:02}:{:02}:{:02}Z", t / 3600, t / 60 % 60, t % 60)
}

/// A UE4SS line's timestamp, `[2026-10-17 15:57:01.9965705]`, as seconds
/// since 1970 in the log's own (local) time.
fn line_time(line: &str) -> Option<i64> {
    let s = line.strip_prefix('[')?;
    let b = s.as_bytes();
    if b.len() < 19 || b[4] != b'-' || b[7] != b'-' || b[10] != b' ' || b[13] != b':' || b[16] != b':' {
        return None;
    }
    let num = |from: usize, to: usize| s.get(from..to)?.parse::<i64>().ok();
    let (y, m, d) = (num(0, 4)?, num(5, 7)?, num(8, 10)?);
    let (h, mi, sec) = (num(11, 13)?, num(14, 16)?, num(17, 19)?);
    Some(days_from_civil(y, m, d) * 86_400 + h * 3600 + mi * 60 + sec)
}

/// When a UE4SS.log starts and ends.
#[derive(Debug, Clone, Copy)]
struct LogSpan {
    /// First and last line, local time.
    first: i64,
    last: i64,
    /// Unix seconds.
    modified: i64,
}

impl LogSpan {
    fn read(path: &Path) -> Option<LogSpan> {
        let mut f = File::open(path).ok()?;
        let meta = f.metadata().ok()?;
        let len = meta.len();
        let modified = unix(meta.modified().ok()?) as i64;
        let mut head = vec![0; len.min(4096) as usize];
        f.read_exact(&mut head).ok()?;
        let first = String::from_utf8_lossy(&head).lines().find_map(line_time)?;
        let tail_len = len.min(64 * 1024);
        f.seek(SeekFrom::Start(len - tail_len)).ok()?;
        let mut tail = vec![0; tail_len as usize];
        f.read_exact(&mut tail).ok()?;
        let last = String::from_utf8_lossy(&tail).lines().filter_map(line_time).last()?;
        Some(LogSpan { first, last, modified })
    }

    /// Whether this is the log of the session that crashed at `crashed_at`.
    /// The lines are local time; the last was written when the file last
    /// was, which gives the offset to UTC to the nearest quarter hour. A log
    /// that starts after the crash is a later session's; one last written
    /// before the crashed session started is an earlier one's.
    fn belongs_to(&self, crashed_at: u64, seconds_since_start: Option<u64>) -> bool {
        let offset = ((self.last - self.modified) as f64 / 900.0).round() as i64 * 900;
        let started = self.first - offset;
        let crashed_at = crashed_at as i64;
        if started > crashed_at + 5 {
            return false;
        }
        match seconds_since_start {
            Some(s) => self.modified >= crashed_at - s as i64 - 300,
            None => true,
        }
    }
}

/// The last `LOG_TAIL` bytes of `src`, from a line start.
fn save_tail(src: &Path, dst: &Path) -> io::Result<()> {
    let mut f = File::open(src)?;
    let len = f.metadata()?.len();
    let start = len.saturating_sub(LOG_TAIL);
    f.seek(SeekFrom::Start(start))?;
    let mut buf = Vec::new();
    f.read_to_end(&mut buf)?;
    if start > 0 {
        if let Some(nl) = buf.iter().position(|&b| b == b'\n') {
            buf.drain(..=nl);
        }
    }
    if let Some(parent) = dst.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(dst, buf)
}

/// Keeps UE4SS.log beside each recent crash that has none, when the log is
/// that crash's session. Run on every scan and before every launch, because
/// the next start of the game overwrites the file.
pub fn capture_logs() {
    let cutoff = now().saturating_sub(LOG_WINDOW_SECS);
    let candidates: Vec<(String, PathBuf)> = crash_dirs()
        .into_iter()
        .filter(|(id, dir)| folder_time(dir) >= cutoff && !store().join(id).join(SAVED_LOG).exists())
        .collect();
    if candidates.is_empty() {
        return;
    }
    let Some(path) = ue4ss_log() else { return };
    let Some(span) = LogSpan::read(&path) else { return };
    for (id, dir) in candidates {
        let Some(ctx) = read_context(&dir) else { continue };
        if span.belongs_to(ctx.crashed_at, ctx.seconds_since_start) {
            if let Err(e) = save_tail(&path, &store().join(&id).join(SAVED_LOG)) {
                eprintln!("crash reports: keeping the log for {id}: {e}");
            }
            // One session, one crash.
            break;
        }
    }
}

// ─── The bundle ─────────────────────────────────────────────────────────

/// `\Users\<name>\` → `\Users\<user>\`, either slash, any case.
pub(crate) fn mask_users(s: &str) -> String {
    mask_users_with(s, false)
}

/// The same with the length kept, for strings inside a dump: the name turns
/// into underscores.
fn mask_users_fixed(s: &str) -> String {
    mask_users_with(s, true)
}

fn mask_users_with(s: &str, fixed: bool) -> String {
    let lower = s.to_ascii_lowercase();
    let bytes = s.as_bytes();
    let mut out = String::with_capacity(s.len());
    let mut i = 0;
    while let Some(p) = lower[i..].find("users") {
        let at = i + p;
        let after = at + 5;
        let slash = |b: u8| b == b'\\' || b == b'/';
        if at > 0 && slash(bytes[at - 1]) && after < bytes.len() && slash(bytes[after]) {
            let name_start = after + 1;
            let name_end = s[name_start..]
                .find(|c: char| matches!(c, '\\' | '/' | '"' | '\'' | '<' | '>' | '|' | '\r' | '\n' | '\0'))
                .map_or(s.len(), |e| name_start + e);
            out.push_str(&s[i..name_start]);
            let name = &s[name_start..name_end];
            if name.is_empty() {
                // Nothing to hide.
            } else if fixed {
                out.extend(std::iter::repeat('_').take(name.chars().count()));
            } else {
                out.push_str("<user>");
            }
            i = name_end;
        } else {
            out.push_str(&s[i..after]);
            i = after;
        }
    }
    out.push_str(&s[i..]);
    out
}

fn blank_tag(xml: &str, tag: &str) -> String {
    let (open, close) = (format!("<{tag}>"), format!("</{tag}>"));
    let mut out = String::with_capacity(xml.len());
    let mut rest = xml;
    while let Some(s) = rest.find(&open) {
        let body = s + open.len();
        let Some(e) = rest[body..].find(&close) else { break };
        out.push_str(&rest[..body]);
        rest = &rest[body + e..];
    }
    out.push_str(rest);
    out
}

fn redact_context(xml: &str) -> String {
    let blanked = PRIVATE_TAGS.iter().fold(xml.to_string(), |x, tag| blank_tag(&x, tag));
    mask_users(&blanked)
}

fn mods_txt() -> Option<String> {
    let (root, _) = crate::find_game_install()?;
    fs::read_to_string(crate::mods_dir(&root).join("mods.txt")).ok()
}

/// What the hub is told about a crash before it sees any file: the body of
/// `POST /crashes`, and the head of `report.json` in the bundle.
fn summary(crash: &Crash) -> serde_json::Value {
    serde_json::json!({
        "crash_id": crash.id,
        "signature": crash.signature,
        "build_version": crash.build_version,
        "crash_type": crash.crash_type,
        "fault": crash.fault,
        "error_message": mask_users(&crash.error_message),
        "crashed_at": iso8601(crash.crashed_at),
        "seconds_since_start": crash.seconds_since_start,
        "mode": crash.mode,
        "map": crash.map,
        "role": crash.role,
        "launcher_version": env!("CARGO_PKG_VERSION"),
        "dump_bytes": crash.dump_bytes,
    })
}

fn zip_options() -> zip::write::SimpleFileOptions {
    zip::write::SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated)
}

/// Writes `crash-<id>.zip` into `out_dir`: report.json, the redacted XML,
/// the slim dump, the log saved there (`capture_logs`) and any GPU
/// breadcrumbs.
fn build_bundle(crash: &Crash, dir: &Path, out_dir: &Path) -> Result<PathBuf, String> {
    fs::create_dir_all(out_dir).map_err(|e| e.to_string())?;
    let path = out_dir.join(format!("crash-{}.zip", crash.id));
    let file = File::create(&path).map_err(|e| format!("{}: {e}", path.display()))?;
    let mut zip = zip::ZipWriter::new(io::BufWriter::new(file));
    let opts = zip_options();
    let mut files: Vec<&str> = Vec::new();
    let err = |e: &dyn std::fmt::Display| format!("Building the crash report: {e}");

    if let Ok(xml) = fs::read_to_string(dir.join(CONTEXT)) {
        zip.start_file(CONTEXT, opts).map_err(|e| err(&e))?;
        zip.write_all(redact_context(&xml).as_bytes()).map_err(|e| err(&e))?;
        files.push(CONTEXT);
    }

    let dump_path = dir.join(DUMP);
    if let Ok(mut src) = File::open(&dump_path) {
        match minidump::read(&mut src).and_then(|d| minidump::slim_plan(&mut src, &d, mask_users_fixed)) {
            Ok(plan) => {
                src.seek(SeekFrom::Start(0)).map_err(|e| err(&e))?;
                zip.start_file("UEMinidump-slim.dmp", opts).map_err(|e| err(&e))?;
                minidump::apply(&mut io::BufReader::new(src), &mut zip, &plan).map_err(|e| err(&e))?;
                files.push("UEMinidump-slim.dmp");
            }
            Err(e) => eprintln!("crash reports: {} unreadable: {e}", dump_path.display()),
        }
    }

    if let Ok(bytes) = fs::read(out_dir.join(SAVED_LOG)) {
        zip.start_file(SAVED_LOG, opts).map_err(|e| err(&e))?;
        zip.write_all(mask_users(&String::from_utf8_lossy(&bytes)).as_bytes()).map_err(|e| err(&e))?;
        files.push(SAVED_LOG);
    }

    let mut breadcrumbs: Vec<String> = fs::read_dir(dir)
        .map(|entries| {
            entries
                .flatten()
                .map(|e| e.file_name().to_string_lossy().into_owned())
                .filter(|n| n.starts_with("Breadcrumbs_") && n.ends_with(".txt"))
                .collect()
        })
        .unwrap_or_default();
    breadcrumbs.sort();
    for name in &breadcrumbs {
        if let Ok(text) = fs::read_to_string(dir.join(name)) {
            zip.start_file(name.as_str(), opts).map_err(|e| err(&e))?;
            zip.write_all(text.as_bytes()).map_err(|e| err(&e))?;
            files.push(name);
        }
    }

    let mut report = summary(crash);
    report["installed"] = crate::hub::installed_summary();
    report["mods_txt"] = serde_json::json!(mods_txt());
    report["files"] = serde_json::json!(files);
    zip.start_file("report.json", opts).map_err(|e| err(&e))?;
    let json = serde_json::to_vec_pretty(&report).map_err(|e| err(&e))?;
    zip.write_all(&json).map_err(|e| err(&e))?;

    zip.finish()
        .map_err(|e| err(&e))?
        .flush()
        .map_err(|e| err(&e))?;
    Ok(path)
}

// ─── Sending ────────────────────────────────────────────────────────────

/// The hub's answer to `POST /crashes`.
#[derive(Debug, Deserialize)]
struct Created {
    id: String,
    /// Absent when the hub already has this report's bundle.
    #[serde(default)]
    bundle_upload: Option<Upload>,
    #[serde(default)]
    wants_dump: bool,
    #[serde(default)]
    dump_upload: Option<Upload>,
}

#[derive(Debug, Serialize)]
pub struct SendResult {
    pub report_id: String,
    /// The hub would like the full dump; ask the player.
    pub dump_requested: bool,
    pub dump_bytes: u64,
}

/// An error the webview answers with the sign-in button.
const SIGNED_OUT: &str = "signed_out: Sign in to the MJOLNIR hub to send crash reports.";

fn client(timeout: Duration) -> Result<reqwest::blocking::Client, String> {
    reqwest::blocking::Client::builder()
        .timeout(timeout)
        .build()
        .map_err(|e| format!("HTTP client error: {e}"))
}

/// A request to where the hub said to put a file.
fn upload_request(
    client: &reqwest::blocking::Client,
    api: &str,
    upload: &Upload,
    key: &str,
) -> Result<reqwest::blocking::RequestBuilder, String> {
    let method = reqwest::Method::from_bytes(upload.method.to_ascii_uppercase().as_bytes())
        .map_err(|_| format!("The hub asked for an upload by {:?}", upload.method))?;
    if upload.url.starts_with('/') && !upload.url.starts_with("//") {
        Ok(client.request(method, format!("{api}{}", upload.url)).bearer_auth(key))
    } else if upload.url.starts_with("https://") {
        // Presigned: the URL is the credential, and the key stays home.
        Ok(client.request(method, &upload.url))
    } else {
        Err(format!("The hub asked for an upload to {:?}", upload.url))
    }
}

/// The hub's own words when it refuses, if it sent any.
fn refusal(what: &str, resp: reqwest::blocking::Response) -> String {
    let status = resp.status();
    if status.as_u16() == 401 {
        return SIGNED_OUT.to_string();
    }
    let body: serde_json::Value = resp.json().unwrap_or(serde_json::Value::Null);
    let said = body["error"]["message"]
        .as_str()
        .or_else(|| body["error"].as_str())
        .or_else(|| body["message"].as_str());
    match said {
        Some(msg) => format!("The hub refused {what} ({status}): {msg}"),
        None => format!("The hub refused {what} ({status})"),
    }
}

/// `POST /crashes`, then the bundle where the hub said.
fn file_report(api: &str, key: &str, crash: &Crash, bundle: Vec<u8>) -> Result<Created, String> {
    let mut body = summary(crash);
    body["bundle_bytes"] = serde_json::json!(bundle.len());
    body["bundle_sha256"] = serde_json::json!(hex::encode(Sha256::digest(&bundle)));

    let http = client(Duration::from_secs(120))?;
    let resp = http
        .post(format!("{api}/crashes"))
        .bearer_auth(key)
        .json(&body)
        .send()
        .map_err(|e| format!("Cannot reach the hub: {e}"))?;
    if !resp.status().is_success() {
        return Err(refusal("the crash report", resp));
    }
    let created: Created = resp.json().map_err(|e| format!("The hub's answer: {e}"))?;

    if let Some(upload) = &created.bundle_upload {
        if let Some(max) = upload.max_bytes.filter(|&max| bundle.len() as u64 > max) {
            return Err(format!("The report is {} bytes, more than the hub takes ({max})", bundle.len()));
        }
        let resp = upload_request(&http, api, upload, key)?
            .header(reqwest::header::CONTENT_TYPE, "application/zip")
            .body(bundle)
            .send()
            .map_err(|e| format!("Cannot reach the hub: {e}"))?;
        if !resp.status().is_success() {
            return Err(refusal("the crash report's files", resp));
        }
    }
    Ok(created)
}

/// Zips the untouched dump in `work_dir` and uploads it where the hub said.
fn upload_dump(api: &str, key: &str, upload: &Upload, dump: &Path, work_dir: &Path) -> Result<(), String> {
    fs::create_dir_all(work_dir).map_err(|e| e.to_string())?;
    let zip_path = work_dir.join("dump.zip");
    let result = (|| {
        {
            let file = File::create(&zip_path).map_err(|e| e.to_string())?;
            let mut zip = zip::ZipWriter::new(io::BufWriter::new(file));
            let mut src = File::open(dump).map_err(|e| format!("The dump: {e}"))?;
            zip.start_file(DUMP, zip_options()).map_err(|e| e.to_string())?;
            io::copy(&mut src, &mut zip).map_err(|e| e.to_string())?;
            zip.finish().map_err(|e| e.to_string())?.flush().map_err(|e| e.to_string())?;
        }
        let len = fs::metadata(&zip_path).map_err(|e| e.to_string())?.len();
        if let Some(max) = upload.max_bytes.filter(|&max| len > max) {
            return Err(format!("The dump is {len} bytes zipped, more than the hub takes ({max})"));
        }
        let file = File::open(&zip_path).map_err(|e| e.to_string())?;
        // Slow uplinks: tens of megabytes at a few Mbit/s is minutes.
        let http = client(Duration::from_secs(30 * 60))?;
        let resp = upload_request(&http, api, upload, key)?
            .header(reqwest::header::CONTENT_TYPE, "application/zip")
            .body(reqwest::blocking::Body::sized(file, len))
            .send()
            .map_err(|e| format!("Cannot reach the hub: {e}"))?;
        if !resp.status().is_success() {
            return Err(refusal("the crash dump", resp));
        }
        Ok(())
    })();
    let _ = fs::remove_file(&zip_path);
    result
}

/// Builds the bundle, files the report and uploads the bundle. The bundle is
/// built again while the folder is there, since the log may have been kept
/// since; the copy `prepare` kept is for when it is not.
pub fn send(id: &str) -> Result<SendResult, String> {
    let key = crate::hub::auth_key().ok_or(SIGNED_OUT)?;
    let record = {
        let _guard = lock();
        load_state().crashes.get(id).cloned()
    };
    let crash = match find(id) {
        Ok(dir) => {
            let crash = describe(id, &dir, record.as_ref()).ok_or("This crash folder has no crash context")?;
            build_bundle(&crash, &dir, &store().join(id))?;
            crash
        }
        Err(gone) => record.as_ref().and_then(|r| from_summary(id, r)).ok_or(gone)?,
    };
    let bundle = fs::read(kept_bundle(id)).map_err(|e| e.to_string())?;
    let created = file_report(&crate::hub::hub_api(), &key, &crash, bundle)?;
    let _ = fs::remove_file(kept_bundle(id));

    let dump_requested = created.wants_dump && created.dump_upload.is_some();
    update(id, |r| {
        r.status = Status::Sent;
        r.report_id = Some(created.id.clone());
        r.dump_requested = if dump_requested { created.dump_upload.clone() } else { None };
    })?;
    Ok(SendResult { report_id: created.id, dump_requested, dump_bytes: crash.dump_bytes })
}

/// The full dump, where the hub asked for it. Only after the player's second
/// yes: it is a copy of the game's memory.
pub fn send_dump(id: &str) -> Result<(), String> {
    let key = crate::hub::auth_key().ok_or(SIGNED_OUT)?;
    let dir = find(id)?;
    let upload = {
        let _guard = lock();
        load_state().crashes.get(id).and_then(|r| r.dump_requested.clone())
    }
    .ok_or("The hub has not asked for this crash's dump")?;
    upload_dump(&crate::hub::hub_api(), &key, &upload, &dir.join(DUMP), &store().join(id))?;
    update(id, |r| {
        r.dump_requested = None;
        r.dump_sent = true;
    })
}

// ─── Commands ───────────────────────────────────────────────────────────

async fn blocking<T: Send + 'static>(
    f: impl FnOnce() -> Result<T, String> + Send + 'static,
) -> Result<T, String> {
    tauri::async_runtime::spawn_blocking(f)
        .await
        .map_err(|e| format!("Task join error: {e}"))?
}

#[tauri::command]
pub async fn crash_list() -> Result<Vec<Crash>, String> {
    blocking(|| Ok(list())).await
}

#[tauri::command]
pub async fn crash_send(id: String) -> Result<SendResult, String> {
    blocking(move || send(&id)).await
}

#[tauri::command]
pub async fn crash_send_dump(id: String) -> Result<(), String> {
    blocking(move || send_dump(&id)).await
}

#[tauri::command]
pub fn crash_decline_dump(id: String) -> Result<(), String> {
    update(&id, |r| r.dump_requested = None)
}

#[tauri::command]
pub fn crash_dismiss(id: String) -> Result<(), String> {
    update(&id, |r| {
        if r.status == Status::New {
            r.status = Status::Dismissed;
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_film_name_gives_mode_and_map() {
        assert_eq!(
            parse_film("megalo--1_bck_e556d786_dist-server_6AD2F914"),
            Film { mode: Some("multiplayer".into()), map: Some("bck".into()), role: Some("server".into()) }
        );
        assert_eq!(
            parse_film("campaign_b30_15061c4b_dist-server_6ACB307D"),
            Film { mode: Some("campaign".into()), map: Some("b30".into()), role: Some("server".into()) }
        );
        assert_eq!(parse_film(""), Film::default());
    }

    #[test]
    fn the_context_gives_the_facts() {
        let xml = "<FGenericCrashContext><RuntimeProperties>\r\n\t<CrashType>Crash</CrashType>\
            <ErrorMessage>Unhandled Exception: EXCEPTION_ACCESS_VIOLATION reading address 0x0000000000000018</ErrorMessage>\
            <SecondsSinceStart>175</SecondsSinceStart>\
            <BuildVersion>2026.08.11.1121610.2-Rel-i343-Meteorite-2607-CU4</BuildVersion>\
            <TimeOfCrash>639278081136960000</TimeOfCrash></RuntimeProperties></FGenericCrashContext>";
        let ctx = Context::parse(xml, 0);
        assert_eq!(ctx.crash_type, "Crash");
        assert_eq!(ctx.seconds_since_start, Some(175));
        assert_eq!(ctx.build_version, "2026.08.11.1121610.2-Rel-i343-Meteorite-2607-CU4");
        // 2026-10-16 21:28 Pacific, when the folder was written.
        assert_eq!(iso8601(ctx.crashed_at), "2026-10-17T04:28:33Z");
        assert_eq!(Context::parse("<CrashType>Assert</CrashType>", 42).crashed_at, 42);
    }

    #[test]
    fn private_ids_and_user_names_are_removed() {
        let xml = "<MachineId>B0BCB5004FC6781C</MachineId><LoginId>b0bc</LoginId>\
            <EpicAccountId>5730e8cc</EpicAccountId><BaseDir>C:/Users/Jane Doe/Games/Halo/</BaseDir>\
            <Modules>D:\\USERS\\jane\\x.dll\nC:\\Program Files\\y.dll</Modules>";
        let out = redact_context(xml);
        assert!(!out.contains("B0BC") && !out.contains("b0bc") && !out.contains("5730"));
        assert!(out.contains("<MachineId></MachineId>"));
        assert!(out.contains("C:/Users/<user>/Games/Halo/"));
        assert!(out.contains("D:\\USERS\\<user>\\x.dll"));
        assert!(out.contains("C:\\Program Files\\y.dll"));
        assert_eq!(mask_users_fixed(r"C:\Users\jane\a.dll"), r"C:\Users\____\a.dll");
        assert_eq!(mask_users("no paths here, users only"), "no paths here, users only");
    }

    #[test]
    fn messages_lose_their_pointers() {
        assert_eq!(
            normalize_message("Assertion failed: Ptr  [File:x.cpp] 0x00007ff6deadbeef\r\n"),
            "Assertion failed: Ptr [File:x.cpp] 0x?"
        );
    }

    fn ctx(crash_type: &str, message: &str) -> Context {
        Context {
            crashed_at: 0,
            crash_type: crash_type.into(),
            error_message: message.into(),
            build_version: "CU4".into(),
            seconds_since_start: None,
        }
    }

    #[test]
    fn crashes_group_by_module_and_asserts_by_message() {
        let bytes = minidump::tests::sample_dump(r"C:\Games\ue4ss\UE4SS.dll");
        let dump = minidump::read(&mut io::Cursor::new(&bytes)).unwrap();
        let (fault, sig) = fault_and_signature(&ctx("Crash", "Unhandled Exception at 0x18"), Some(&dump));
        assert_eq!(fault, "UE4SS.dll+0x2580d7 (0xc0000005)");
        assert_eq!(sig.len(), 16);
        // The same place in another build is another signature.
        let mut other = ctx("Crash", "");
        other.build_version = "CU5".into();
        assert_ne!(fault_and_signature(&other, Some(&dump)).1, sig);

        let (fault, _) = fault_and_signature(&ctx("Assert", "Assertion failed: X at 0x1234"), Some(&dump));
        assert_eq!(fault, "Assertion failed: X at 0x?");
        let (fault, _) = fault_and_signature(&ctx("Crash", ""), None);
        assert_eq!(fault, "unknown");
    }

    #[test]
    fn the_log_belongs_to_the_session_that_crashed() {
        // Pacific daylight time: local = UTC - 7 h.
        let offset = -7 * 3600;
        let crashed_at: u64 = 1_792_211_313;
        let span = |start_utc: i64, end_utc: i64| LogSpan {
            first: start_utc + offset,
            last: end_utc + offset,
            modified: end_utc + 2,
        };
        let c = crashed_at as i64;
        // Started 175 s before the crash, last line a second before it.
        assert!(span(c - 175, c - 1).belongs_to(crashed_at, Some(175)));
        // The game was started again after the crash: a new log.
        assert!(!span(c + 40, c + 60).belongs_to(crashed_at, Some(175)));
        // A log from a session that ended before this one began.
        assert!(!span(c - 9000, c - 8000).belongs_to(crashed_at, Some(175)));
        assert_eq!(line_time("[2026-10-17 15:57:01.9965705] Console created").map(|t| t % 86_400), Some(15 * 3600 + 57 * 60 + 1));
        assert_eq!(line_time("no stamp"), None);
    }

    /// A request the stand-in hub got: method, path, Authorization, body.
    type Seen = (String, String, String, Vec<u8>);

    /// A stand-in hub on localhost that answers as docs/crash_reports.md
    /// says, asks for the dump, and keeps every request.
    fn stand_in_hub() -> (String, std::sync::Arc<Mutex<Vec<Seen>>>) {
        use std::io::BufRead;
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let base = format!("http://{}/api/v1", listener.local_addr().unwrap());
        let seen = std::sync::Arc::new(Mutex::new(Vec::<Seen>::new()));
        let log = seen.clone();
        std::thread::spawn(move || {
            for mut stream in listener.incoming().flatten() {
                let mut reader = io::BufReader::new(stream.try_clone().unwrap());
                let mut request = String::new();
                reader.read_line(&mut request).unwrap();
                let (mut len, mut auth) = (0usize, String::new());
                loop {
                    let mut header = String::new();
                    reader.read_line(&mut header).unwrap();
                    if header.trim().is_empty() {
                        break;
                    }
                    let (name, value) = header.split_once(':').unwrap();
                    match name.to_ascii_lowercase().as_str() {
                        "content-length" => len = value.trim().parse().unwrap(),
                        "authorization" => auth = value.trim().to_string(),
                        _ => {}
                    }
                }
                let mut body = vec![0; len];
                reader.read_exact(&mut body).unwrap();
                let mut words = request.split_whitespace();
                let (method, path) = (words.next().unwrap().to_string(), words.next().unwrap().to_string());
                let (status, answer) = if method == "POST" && path == "/api/v1/crashes" {
                    let json = serde_json::json!({
                        "id": "r1",
                        "bundle_upload": { "method": "PUT", "url": "/crashes/r1/bundle", "max_bytes": 8 << 20 },
                        "wants_dump": true,
                        "dump_upload": { "method": "PUT", "url": "/crashes/r1/dump", "max_bytes": 90 << 20 },
                    });
                    ("201 Created", json.to_string())
                } else {
                    ("204 No Content", String::new())
                };
                log.lock().unwrap().push((method, path, auth, body));
                write!(
                    stream,
                    "HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{answer}",
                    answer.len()
                )
                .unwrap();
            }
        });
        (base, seen)
    }

    /// The whole launcher side against this PC's own crash folders: every
    /// crash describes, the newest bundles small with nothing private in it,
    /// its slim dump still names the same fault, and report, bundle and dump
    /// reach a stand-in hub as the contract says.
    #[test]
    #[ignore = "reads this PC's crash folders; run with --ignored --nocapture"]
    fn real_crashes_bundle_and_send() {
        let dirs = crash_dirs();
        assert!(!dirs.is_empty(), "no crash folders on this PC");
        let mut faults: BTreeMap<String, usize> = BTreeMap::new();
        for (id, dir) in &dirs {
            if let Some(c) = describe(id, dir, None) {
                *faults.entry(format!("{} {}", c.crash_type, c.fault)).or_default() += 1;
            }
        }
        let mut top: Vec<(String, usize)> = faults.into_iter().collect();
        top.sort_by(|a, b| b.1.cmp(&a.1));
        println!("{} crash folders, {} signatures; most common:", dirs.len(), top.len());
        for (fault, n) in top.iter().take(8) {
            println!("{n:4}  {fault}");
        }

        let (id, dir) = dirs.iter().max_by_key(|(_, d)| folder_time(d)).unwrap();
        let crash = describe(id, dir, None).unwrap();
        println!("newest: {id}: {} {} ({}, {:?} on {:?})", crash.crash_type, crash.fault, crash.signature, crash.mode, crash.map);
        let out = std::env::temp_dir().join(format!("mjolnir-crash-test-{}", std::process::id()));
        fs::create_dir_all(&out).unwrap();
        // A log as capture_logs keeps it.
        fs::write(out.join(SAVED_LOG), "[2026-10-16 21:25:38.0000000] Loaded C:\\Users\\Someone\\mod.lua\n").unwrap();
        let started = std::time::Instant::now();
        let bundle_path = build_bundle(&crash, dir, &out).unwrap();
        let bundle = fs::read(&bundle_path).unwrap();
        println!("bundle: {} bytes in {:?}, from a {} byte dump", bundle.len(), started.elapsed(), crash.dump_bytes);
        assert!(bundle.len() < 8 << 20);

        let mut zip = zip::ZipArchive::new(io::Cursor::new(&bundle)).unwrap();
        let names: Vec<String> = zip.file_names().map(String::from).collect();
        for want in ["report.json", CONTEXT, "UEMinidump-slim.dmp", SAVED_LOG] {
            assert!(names.iter().any(|n| n == want), "{want} missing from {names:?}");
        }
        let mut xml = String::new();
        zip.by_name(CONTEXT).unwrap().read_to_string(&mut xml).unwrap();
        assert!(xml.contains("<MachineId></MachineId>") && xml.contains("<LoginId></LoginId>"));
        assert!(xml.contains("<EpicAccountId></EpicAccountId>"));
        let mut log = String::new();
        zip.by_name(SAVED_LOG).unwrap().read_to_string(&mut log).unwrap();
        assert!(log.contains("\\Users\\<user>\\") && !log.contains("Someone"));
        let mut report = String::new();
        zip.by_name("report.json").unwrap().read_to_string(&mut report).unwrap();
        let report: serde_json::Value = serde_json::from_str(&report).unwrap();
        assert_eq!(report["signature"], crash.signature.as_str());
        let mut slim = Vec::new();
        zip.by_name("UEMinidump-slim.dmp").unwrap().read_to_end(&mut slim).unwrap();
        assert_eq!(slim.len() as u64, crash.dump_bytes);
        let full = minidump::read(&mut File::open(dir.join(DUMP)).unwrap()).unwrap();
        let thin = minidump::read(&mut io::Cursor::new(&slim)).unwrap();
        assert_eq!(thin.modules.len(), full.modules.len());
        let ctx = read_context(dir).unwrap();
        assert_eq!(fault_and_signature(&ctx, Some(&thin)), (crash.fault.clone(), crash.signature.clone()));
        if let Ok(user) = std::env::var("USERNAME") {
            for path in [format!("Users\\{user}"), format!("Users/{user}")] {
                let wide: Vec<u8> = path.encode_utf16().flat_map(|u| u.to_le_bytes()).collect();
                assert!(!slim.windows(wide.len()).any(|w| w == wide), "{path} in the slim dump (UTF-16)");
                assert!(!slim.windows(path.len()).any(|w| w == path.as_bytes()), "{path} in the slim dump");
            }
        }

        // A real hub when MJOLNIR_CRASH_HUB (its API base) and
        // MJOLNIR_CRASH_KEY say so, such as a local `pnpm dev` hub; else the
        // stand-in, whose requests are checked against the contract.
        if let (Ok(base), Ok(key)) = (std::env::var("MJOLNIR_CRASH_HUB"), std::env::var("MJOLNIR_CRASH_KEY")) {
            let created = file_report(&base, &key, &crash, bundle.clone()).unwrap();
            println!(
                "hub report {}: bundle {}, wants_dump {}",
                created.id,
                if created.bundle_upload.is_some() { "uploaded" } else { "already there" },
                created.wants_dump
            );
            if let Some(upload) = created.dump_upload.as_ref().filter(|_| created.wants_dump) {
                upload_dump(&base, &key, upload, &dir.join(DUMP), &out).unwrap();
                println!("dump uploaded");
            }
            let _ = fs::remove_dir_all(&out);
            return;
        }

        let (base, seen) = stand_in_hub();
        let created = file_report(&base, "test-key", &crash, bundle.clone()).unwrap();
        assert!(created.wants_dump);
        upload_dump(&base, "test-key", created.dump_upload.as_ref().unwrap(), &dir.join(DUMP), &out).unwrap();
        assert!(!out.join("dump.zip").exists(), "the zipped dump is left behind");

        let seen = seen.lock().unwrap();
        assert_eq!(seen.len(), 3);
        let (method, path, auth, body) = &seen[0];
        assert_eq!((method.as_str(), path.as_str(), auth.as_str()), ("POST", "/api/v1/crashes", "Bearer test-key"));
        let body: serde_json::Value = serde_json::from_slice(body).unwrap();
        assert_eq!(body["crash_id"], id.as_str());
        assert_eq!(body["bundle_sha256"], hex::encode(Sha256::digest(&bundle)).as_str());
        assert_eq!(body["bundle_bytes"], bundle.len());
        let (method, path, auth, body) = &seen[1];
        assert_eq!((method.as_str(), path.as_str(), auth.as_str()), ("PUT", "/api/v1/crashes/r1/bundle", "Bearer test-key"));
        assert_eq!(body, &bundle);
        let (method, path, _, body) = &seen[2];
        assert_eq!((method.as_str(), path.as_str()), ("PUT", "/api/v1/crashes/r1/dump"));
        let mut dump_zip = zip::ZipArchive::new(io::Cursor::new(body)).unwrap();
        assert_eq!(dump_zip.by_name(DUMP).unwrap().size(), crash.dump_bytes);
        println!("dump upload: {} bytes zipped", body.len());
        let _ = fs::remove_dir_all(&out);
    }

    #[test]
    fn dates_round_trip() {
        for days in [-1, 0, 365, 20_743, 30_000] {
            let (y, m, d) = civil_from_days(days);
            assert_eq!(days_from_civil(y, m, d), days);
        }
        assert_eq!(iso8601(0), "1970-01-01T00:00:00Z");
    }
}
