//! Pushing an edit straight into the running game.
//!
//! The ordinary loop is edit → bake → restart → walk back to where you were.
//! For tuning a number that is minutes per attempt, and the restart is nearly
//! all of it. The game parses each tag once at load into a heap buffer that
//! keeps the file's own field offsets, and reads fields out of it as the
//! simulation runs — so the same bytes `blam_tag::patch` would write to the file
//! can be written into that buffer instead, and the change is immediate.
//!
//! What this is not: persistence. A live poke never touches disk. It is gone at
//! the next launch, and the mod project is the record of what the edit *is* —
//! this only shortens the loop for deciding what the number should be.
//!
//! # Why a located address is cached
//!
//! Finding a tag means scanning the process for byte runs taken from the tag
//! itself, which reads every private writable page — minutes. Doing that per
//! keystroke would be absurd, so the address is remembered per tag. It cannot be
//! remembered across launches: relaunch and the heap moves. [`blam_live::verify`]
//! re-scores a cached address against the tag in one read, so a stale one is
//! caught and re-found rather than written over blind.

use std::collections::HashMap;
use std::ops::Range;
use std::sync::{Arc, Mutex};

use serde::Serialize;

/// Everything a poke needs, lifted out of the app state so the slow part can run
/// off the UI thread without holding a `State` across an await.
pub struct Job {
    pub key: (String, String),
    /// The tag as the containers hold it.
    pub payload: Vec<u8>,
    /// The resident data section, the only part worth searching.
    pub region: Range<usize>,
    /// Byte range of the field within the payload.
    pub span: Range<usize>,
    /// The field's bytes after the edit.
    pub bytes: Vec<u8>,
}

/// One tag a census found loaded in the running game.
#[derive(Serialize, Clone)]
pub struct LoadedTag {
    /// Catalog index, for opening the tag in the editor.
    pub index: usize,
    pub group: String,
    pub short: String,
    /// Fraction of the data section verified byte-for-byte. Well under 1.0 is
    /// normal — the engine rewrites much of a tag at load.
    pub fraction: f32,
}

#[derive(Default)]
struct Inner {
    /// Bases found this session, per tag. Emptied when the process changes.
    /// Fed by both single-tag scans and the census, so a censused tag pokes
    /// instantly.
    bases: Mutex<HashMap<(String, String), u64>>,
    /// Which process the cached bases belong to.
    pid: Mutex<Option<u32>>,
    /// What the last census found, for the UI. Emptied with `bases`.
    loaded: Mutex<Vec<LoadedTag>>,
    /// The loaded scenario's short path — which level the player is in.
    level: Mutex<Option<String>>,
    /// Tags with a live object in the game, from the object table. A
    /// superset of `loaded`: an object exists for nearly every tag whether or
    /// not its data is resident (see `crate::present`).
    present: Mutex<usize>,
    /// Where the engine's object table and name pool sit in the game image,
    /// as RVAs. A property of the build, not the launch, so it survives a
    /// process change — and is re-validated on every reattach, so a game
    /// update cannot make it lie.
    rvas: Mutex<Option<(u64, u64)>>,
    /// Where the engine's loader-cache roots sit in the image, as RVAs. Per
    /// build like `rvas`, and revalidated by signature on every use.
    cache_rvas: Mutex<Vec<u64>>,
}

/// Managed state: what the editor remembers about the running game.
#[derive(Clone, Default)]
pub struct Live(Arc<Inner>);

#[derive(Serialize, Clone)]
pub struct Status {
    /// Whether a game process is there to poke at all.
    pub running: bool,
    pub pid: Option<u32>,
    /// How many tags have a known address, so the UI can say which edits will
    /// be instant and which will pay for a scan.
    pub located: usize,
    /// The loaded scenario's short path — which level the player is in. From
    /// the object table (exact) or, failing that, the census. `None` before
    /// either has run.
    pub level: Option<String>,
    /// Tags with a live object, from the object table. Not the pokeable set.
    pub present: usize,
}

#[derive(Serialize, Clone)]
pub struct Poked {
    /// What the field read in the running game *before* this write, which is
    /// often not the shipped value — a mod may already have changed it.
    pub was: String,
    pub now: String,
    /// True when the address had to be found, i.e. this call took minutes.
    pub scanned: bool,
    pub base: String,
}

impl Live {
    pub fn status(&self) -> Status {
        let found = blam_live::Process::attach().ok();
        let pid = found.as_ref().map(|p| p.pid);
        // A different process means every cached address belongs to a heap that
        // no longer exists. Drop them rather than let a stale one be written to.
        let mut held = self.0.pid.lock().expect("live pid lock");
        if *held != pid {
            self.forget();
            *held = pid;
        }
        Status {
            running: pid.is_some(),
            pid,
            located: self.0.bases.lock().expect("live base lock").len(),
            level: self.0.level.lock().expect("live level lock").clone(),
            present: *self.0.present.lock().expect("live present lock"),
        }
    }

    pub fn forget(&self) {
        self.0.bases.lock().expect("live base lock").clear();
        self.0.loaded.lock().expect("live loaded lock").clear();
        *self.0.level.lock().expect("live level lock") = None;
        *self.0.present.lock().expect("live present lock") = 0;
        // `rvas` deliberately survives: it belongs to the build, not the
        // process, and reattach validates it anyway.
    }

    /// Cached engine-global RVAs from a previous reader attach, if any.
    pub fn rvas(&self) -> Option<(u64, u64)> {
        *self.0.rvas.lock().expect("live rvas lock")
    }

    pub fn set_rvas(&self, rvas: (u64, u64)) {
        *self.0.rvas.lock().expect("live rvas lock") = Some(rvas);
    }

    /// Cached loader-cache root RVAs from a previous census, if any.
    pub fn cache_rvas(&self) -> Vec<u64> {
        self.0.cache_rvas.lock().expect("live cache rvas lock").clone()
    }

    pub fn set_cache_rvas(&self, rvas: Vec<u64>) {
        *self.0.cache_rvas.lock().expect("live cache rvas lock") = rvas;
    }

    /// Take on what the object table said: the level and how many tags have
    /// a live object. Does not touch `bases` or `loaded` — those are the
    /// census's, and they mean something different.
    pub fn adopt_present(&self, pid: u32, level: Option<String>, present: usize) {
        let mut held = self.0.pid.lock().expect("live pid lock");
        if *held != Some(pid) {
            self.forget();
            *held = Some(pid);
        }
        *self.0.level.lock().expect("live level lock") = level;
        *self.0.present.lock().expect("live present lock") = present;
    }

    /// What the last census found, for the UI.
    pub fn loaded(&self) -> Vec<LoadedTag> {
        self.0.loaded.lock().expect("live loaded lock").clone()
    }

    /// Take on a census's verified results: every base becomes poke-instant.
    ///
    /// Replaces the loaded list rather than merging it — the census is a
    /// statement about *now*, and a tag found an hour ago may be long gone.
    /// Bases merge, though: a base a single-tag scan found stays valid, and
    /// every poke re-verifies before writing anyway.
    pub fn adopt_census(
        &self,
        pid: u32,
        found: Vec<((String, String), u64, LoadedTag)>,
        level: Option<String>,
    ) {
        let mut held = self.0.pid.lock().expect("live pid lock");
        let mut bases = self.0.bases.lock().expect("live base lock");
        if *held != Some(pid) {
            bases.clear();
            *held = Some(pid);
        }
        let mut loaded: Vec<LoadedTag> = Vec::with_capacity(found.len());
        for (key, base, tag) in found {
            bases.insert(key, base);
            loaded.push(tag);
        }
        loaded.sort_by(|a, b| (&a.group, &a.short).cmp(&(&b.group, &b.short)));
        *self.0.loaded.lock().expect("live loaded lock") = loaded;
        *self.0.level.lock().expect("live level lock") = level;
    }

    /// Write one field into the running game, finding the tag first if needed.
    ///
    /// Blocking and slow on a cache miss; the caller runs it off the UI thread.
    pub fn poke(&self, job: &Job) -> Result<Poked, String> {
        let process = blam_live::Process::attach().map_err(|e| e.to_string())?;

        let cached = self
            .0
            .bases
            .lock()
            .map_err(|e| e.to_string())?
            .get(&job.key)
            .copied();

        // A cached base is trusted only after it re-scores like the tag it
        // claims to be. Most of the data section is rewritten by the engine at
        // load, so the bar is "clearly better than unrelated heap", not "equal".
        let (base, scanned) = match cached {
            Some(base) if blam_live::verify(&process, &job.payload, &job.region, base) > 0.10 => {
                (base, false)
            }
            _ => {
                let at =
                    blam_live::locate(&process, &job.payload, &job.region, &[job.span.clone()])
                        .map_err(|e| e.to_string())?;
                self.0
                    .bases
                    .lock()
                    .map_err(|e| e.to_string())?
                    .insert(job.key.clone(), at.base);
                (at.base, true)
            }
        };

        let located = blam_live::Located {
            base,
            match_fraction: 0.0,
            agreeing_runs: 0,
            candidates: 0,
            scanned: 0,
        };
        let before = blam_live::peek(&process, &located, job.span.start, job.bytes.len())
            .map_err(|e| e.to_string())?;
        let after = blam_live::poke(&process, &located, job.span.start, &job.bytes)
            .map_err(|e| e.to_string())?;
        if after != job.bytes {
            return Err("the value did not stick; the game may have reloaded the tag".into());
        }
        Ok(Poked {
            was: hex(&before),
            now: hex(&after),
            scanned,
            base: format!("{base:#X}"),
        })
    }
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
