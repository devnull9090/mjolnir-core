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

#[derive(Default)]
struct Inner {
    /// Bases found this session, per tag. Emptied when the process changes.
    bases: Mutex<HashMap<(String, String), u64>>,
    /// Which process the cached bases belong to.
    pid: Mutex<Option<u32>>,
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
            self.0.bases.lock().expect("live base lock").clear();
            *held = pid;
        }
        Status {
            running: pid.is_some(),
            pid,
            located: self.0.bases.lock().expect("live base lock").len(),
        }
    }

    pub fn forget(&self) {
        self.0.bases.lock().expect("live base lock").clear();
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
