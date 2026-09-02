//! Pushing an edit straight into the running game.
//!
//! The ordinary loop is edit → bake → restart → walk back to where you were.
//! For tuning a number that is minutes per attempt, and the restart is nearly
//! all of it. The game parses each tag once at load into a heap buffer that
//! keeps the file's own field offsets for the root element, and reads fields
//! out of it as the simulation runs — so the same bytes `blam_tag::patch`
//! would write to the file can be written into that buffer instead, and the
//! change is immediate.
//!
//! What this is not: persistence. A live poke never touches disk. It is gone at
//! the next launch, and the mod project is the record of what the edit *is* —
//! this only shortens the loop for deciding what the number should be.
//!
//! # Two things the engine does that a poke has to follow
//!
//! **It rewrites every reference in place.** String ids, tag references and
//! block headers are resolved at load, so a weapon's resident copy shares no
//! 48 contiguous bytes with the file and the plain byte-run locator cannot
//! see it — worse, it settles for a stray copy of the tag's section tables,
//! which is where a magnum's zoom went once, with no effect on the game. The
//! copy is found by its scalar fields alone (`blam_live::find`), which the
//! engine leaves at their file offsets.
//!
//! **It moves block elements out of the tag.** The root element stays put;
//! every block's elements are relocated, and the block field's twelve bytes
//! become a header: count, an offset from a process-wide arena in 4-byte
//! units, and a struct id. A field inside `zoom levels[0]` is reached by
//! reading that header (`blam_live::field_address`); the arena is worked out
//! once per launch from any tag with a data-rich block
//! (`blam_live::derive_arena`) and remembered.
//!
//! # Why a located address is cached
//!
//! Finding a tag sweeps the process for byte runs taken from the tag itself —
//! about fifteen seconds on half the cores. Doing that per keystroke would be
//! absurd, so the address is remembered per tag. It cannot be remembered
//! across launches: relaunch and the heap moves. `blam_live::accept` re-scores
//! a cached address against the tag in one read, so a stale one is caught and
//! re-found rather than written over blind.

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
    /// The resident data section.
    pub region: Range<usize>,
    /// The root element within it — the part the engine keeps at file offsets.
    pub root: Range<usize>,
    /// One flag per payload byte: true where the byte holds a scalar value.
    pub stable: Vec<bool>,
    /// File offsets of the root element's block fields that have elements.
    pub headers: Vec<usize>,
    /// Those blocks as hops into element 0, with their counts — what deriving
    /// the arena needs.
    pub blocks: Vec<(blam_live::Hop, u32)>,
    /// Block boundaries crossed on the way to the field, outermost first.
    /// Empty for a root-element field.
    pub hops: Vec<blam_live::Hop>,
    /// Byte range of the field within the payload.
    pub span: Range<usize>,
    /// The field's bytes after the edit.
    pub bytes: Vec<u8>,
}

/// `blam_tag`'s hop, in `blam_live`'s terms.
pub fn hop(h: &blam_tag::patch::Hop) -> blam_live::Hop {
    blam_live::Hop {
        header: h.header,
        index: h.index,
        element: h.element,
        element_size: h.element_size,
    }
}

/// One tag a census found loaded in the running game.
#[derive(Serialize, Clone)]
pub struct LoadedTag {
    /// Catalog index, for opening the tag in the editor.
    pub index: usize,
    pub group: String,
    pub short: String,
    /// Fraction of the root element's scalar bytes verified against the file.
    /// Near 1.0 for a working copy; the engine computes into fields that are
    /// zero on disk, and those are never counted.
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
    /// The arena the engine's block headers count from. Per launch, like
    /// `bases`: derived from the first tag with a data-rich block and kept.
    arena: Mutex<Option<u64>>,
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
    /// True when the address had to be found, i.e. this call swept memory.
    pub scanned: bool,
    /// Where the tag's payload byte 0 maps to.
    pub base: String,
    /// Where the field's bytes were written. Equal to base plus the file
    /// offset for a root-element field; inside a relocated block element
    /// otherwise.
    pub address: String,
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
        *self.0.arena.lock().expect("live arena lock") = None;
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
            *self.0.arena.lock().expect("live arena lock") = None;
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

    /// The arena block headers count from: remembered for this launch, or
    /// derived now from the tag at `base`.
    fn arena(&self, process: &blam_live::Process, base: u64, job: &Job) -> Result<u64, String> {
        let mut held = self.0.arena.lock().map_err(|e| e.to_string())?;
        if let Some(arena) = *held {
            return Ok(arena);
        }
        let arena = blam_live::derive_arena(process, base, &job.payload, &job.stable, &job.blocks)
            .ok_or_else(|| {
                format!(
                    "{} sits inside a block element, which the engine keeps outside the tag, \
                     and the arena those live in could not be worked out from this tag. Poke \
                     a field of a tag with a data-rich block first — a weapon's barrels, say — \
                     and it is known for the rest of this launch.",
                    describe(&job.hops)
                )
            })?;
        *held = Some(arena);
        Ok(arena)
    }

    /// Write one field into the running game, finding the tag first if needed.
    ///
    /// Blocking and slow on a cache miss; the caller runs it off the UI thread.
    pub fn poke(&self, job: &Job) -> Result<Poked, String> {
        let process = blam_live::Process::attach().map_err(|e| e.to_string())?;
        let shape = blam_live::Shape {
            region: job.region.clone(),
            root: job.root.clone(),
            stable: &job.stable,
            headers: &job.headers,
        };

        let cached = self
            .0
            .bases
            .lock()
            .map_err(|e| e.to_string())?
            .get(&job.key)
            .copied();

        // A cached base is trusted only after it still reads as this tag's
        // working copy: the root element's scalars are there, and the block
        // headers carry the engine's rewrite.
        let (base, scanned) = match cached {
            Some(base) if blam_live::accept(&process, &job.payload, &shape, base) => (base, false),
            _ => {
                let at = blam_live::find(&process, &job.payload, &shape, &[job.span.clone()])
                    .map_err(|e| e.to_string())?;
                self.0
                    .bases
                    .lock()
                    .map_err(|e| e.to_string())?
                    .insert(job.key.clone(), at.base);
                (at.base, true)
            }
        };

        let address = if job.hops.is_empty() {
            base + job.span.start as u64
        } else {
            let arena = self.arena(&process, base, job)?;
            blam_live::field_address(&process, base, arena, &job.hops, job.span.start)
                .map_err(|e| e.to_string())?
        };

        let before = process
            .read(address, job.bytes.len())
            .map_err(|e| e.to_string())?;
        process.write(address, &job.bytes).map_err(|e| e.to_string())?;
        let after = process
            .read(address, job.bytes.len())
            .map_err(|e| e.to_string())?;
        if after != job.bytes {
            return Err("the value did not stick; the game may have reloaded the tag".into());
        }
        Ok(Poked {
            was: hex(&before),
            now: hex(&after),
            scanned,
            base: format!("{base:#X}"),
            address: format!("{address:#X}"),
        })
    }
}

fn describe(hops: &[blam_live::Hop]) -> String {
    match hops.len() {
        0 => "this field".into(),
        1 => "this field".into(),
        n => format!("this field ({n} blocks deep)"),
    }
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
