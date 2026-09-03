//! Reading and patching a Blam tag payload inside the running game.
//!
//! The game parses a tag once at load into a heap buffer that keeps the tag
//! file's own layout for the **root element**, and then reads fields out of
//! that buffer as the simulation runs. So a root-element field can be changed
//! at runtime by writing the same bytes `blam_tag::patch` would have written
//! to the file, at the same offset, in the live process — no rebuild, no
//! restart. Two things the engine does on the way in shape everything else
//! here, both measured 2026-09-02 on the magnum and assault rifle in a30:
//!
//! - **Every reference is rewritten in place** — string ids, tag references,
//!   block indices, block headers — and only the scalar fields keep their
//!   bytes. A weapon's resident copy shares no 48 contiguous bytes with the
//!   file, so it is found by its scalars alone ([`find`], [`Shape`]).
//! - **Block elements are moved out of the tag.** The block field's twelve
//!   bytes become a [`BlockHeader`] that says where; a field inside an
//!   element is reached through it ([`field_address`], [`derive_arena`]).
//!
//! **Verified 2026-08-03** against build `2026.06.26...Meteorite-2606-CU2`:
//! the spartans biped's `jump velocity` written from 9.0 to 25.0 took the
//! measured jump arc from 3,005 cm to 11,618 cm, and restoring the bytes put it
//! back.
//!
//! That header says CU2, but the CU3 update landed on 2026-08-01, so a run dated
//! 2026-08-03 was against CU3. The label was carried forward rather than re-checked.
//! It is left as written because that is an inference from the update date, not a
//! record of which binary was installed; see `docs/build_lock.md`.
//!
//! Two things make it more than a guess that this is the engine's working copy
//! rather than a cached copy of the file:
//!
//! - Fields that are **zero on disk** hold engine-computed values here, bit for
//!   bit against formulas over their neighbours in the same buffer. The clearest
//!   is a field holding `0x3EFFFFFF` — `cosf(1.04719758)` — where the constant
//!   `0.5` would have been `0x3F000000`. Nothing copying a file produces that.
//! - Writes stick. The engine does not rewrite the buffer underneath us.
//!
//! # Locating
//!
//! There is no pointer to follow: the tag asset UObject keeps its payload as
//! *unloaded* bulk data, so the only handle on the buffer is its contents. We
//! find it by scanning for byte runs taken from the tag itself.
//!
//! Two wrinkles drive the design:
//!
//! - The bytes in memory are whatever container **won** — a mod override, not
//!   necessarily the shipped tag we can read from disk. Any run overlapping a
//!   modded field will not match.
//! - The engine writes computed values into some fields after load, so runs
//!   overlapping those will not match either.
//!
//! Neither is knowable up front, so [`locate`] takes several candidate runs from
//! different parts of the tag and searches for **all of them in one pass**. A
//! base address that several independent runs agree on is the answer; runs that
//! landed on modded or fixed-up bytes simply find nothing and cost nothing.

use std::collections::HashMap;
use std::ops::Range;

mod sys;

pub mod cache;
pub mod names;
pub mod package_id;
pub mod objects;

pub use sys::{Process, ProcessInfo};

/// The executable the game runs as.
pub const GAME_EXE: &str = "HaloCampaignEvolved.exe";

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("the game does not appear to be running (no {0})")]
    NotRunning(String),
    #[error("could not open process {pid}: {source}. Is it running as administrator?")]
    Open {
        pid: u32,
        #[source]
        source: std::io::Error,
    },
    #[error("reading {len} bytes at {addr:#x} failed: {source}")]
    Read {
        addr: u64,
        len: usize,
        #[source]
        source: std::io::Error,
    },
    #[error("writing {len} bytes at {addr:#x} failed: {source}")]
    Write {
        addr: u64,
        len: usize,
        #[source]
        source: std::io::Error,
    },
    #[error(
        "could not find this tag in memory. It may not be loaded — tags load on demand, so be \
         in a mission with the object in play"
    )]
    NotFound,
    #[error("found {0} copies of the game running; close one so there is no doubt which to patch")]
    Ambiguous(usize),
    #[error(
        "found {candidates} candidate address(es), but the best had only {best:.0} independent \
         run(s) agreeing and {need:.0} are needed to rule out coincidence. The tag is most \
         likely not loaded — tags load on demand, so be in a mission with the object in play"
    )]
    Unverified {
        candidates: usize,
        best: f32,
        need: f32,
    },
    #[error("the tag payload is too small to locate ({0} bytes)")]
    TooSmall(usize),
    #[error("the block holds {count} element(s) in the running game, so there is no element {index} to write")]
    ElementGone { index: usize, count: u32 },
    #[error("this platform cannot reach another process's memory")]
    Unsupported,
}

type Result<T> = std::result::Result<T, Error>;

/// How many bytes each locator run covers.
///
/// A trade-off measured against the real thing. Only the tag's **data section**
/// is resident, and the engine rewrites much of it in place — resolving offsets,
/// and computing values into fields that are zero on disk. Measured on the
/// spartans biped, only about 45% of the data section survives byte-identical,
/// in stretches. So a run has to be short enough to fit inside one surviving
/// stretch, and long enough that a match is not chance across ~20 GB. At 48
/// bytes a chance match needs 2^384 odds against; the limit is real structure in
/// the heap, which is what the agreement check below is for.
const RUN: usize = 48;

/// How many independent runs to look for in a single pass.
///
/// Most will land on rewritten bytes and find nothing, which costs nothing. The
/// point is that enough survive for two to agree.
const RUNS: usize = 32;

/// How many runs a census fingerprint carries per tag.
///
/// A census searches for thousands of tags in one pass, so each tag gets fewer
/// runs than a single-tag [`locate`] — the search table has to stay small
/// enough that the prefilter still rejects almost every position. With ~45% of
/// a data section surviving the engine's fix-ups, the chance that fewer than
/// two of twelve spread-out runs survive is small; a tag that loses anyway is
/// simply not censused and still has the full 32-run [`locate`] behind it.
/// Callers can ask for more per tag via [`print_n`] — the scenario tag is worth
/// it, because it is both the most heavily fixed-up tag and the one that names
/// the level.
const CENSUS_RUNS: usize = 12;

/// How many runs must agree on the same base before it is believed.
///
/// One run matching somewhere across 20 GB of heap does happen. Two independent
/// runs matching at *exactly* the spacing the file gives them does not — that is
/// the tag's own structure reproduced, not a coincidence.
const MIN_AGREEMENT: usize = 2;

/// Where a tag's payload sits in the running process.
///
/// `base` is the address that payload byte 0 *would* have. The bytes before the
/// data section are not actually the tag — only the data section is resident —
/// but expressing it this way means a field's address is `base + file offset`,
/// so the offsets `blam_tag` already computes are used unchanged.
#[derive(Debug, Clone)]
pub struct Located {
    /// Address that payload byte 0 maps to. Fields are at `base + file offset`.
    pub base: u64,
    /// Fraction of the data section reproduced byte-for-byte, 0.0 to 1.0.
    /// Well under 1.0 is normal and expected; see [`RUN`].
    pub match_fraction: f32,
    /// How many independent runs agreed on this base.
    pub agreeing_runs: usize,
    /// How many candidate addresses were considered.
    pub candidates: usize,
    /// Bytes of process memory read during the search.
    pub scanned: u64,
}

/// Whether a run's first eight bytes make a usable search anchor.
///
/// The first eight bytes are the pattern's key: every scan position is tested
/// against them, so they must be bytes that do *not* blanket the heap. Measured
/// on the real fingerprint table, runs anchored at window starts kept landing on
/// section-header magics (`tsgt`, `frgt`...) and zero/constant stretches —
/// hundreds of fingerprints sharing one prefix that also appears at millions of
/// heap positions, which turned the sweep's rare path into its hot path. Both
/// offender classes fail these two rules.
fn anchor_quality(run: &[u8]) -> bool {
    let head = &run[..8];
    if head.iter().any(|b| *b == 0) {
        return false;
    }
    let mut seen = [false; 256];
    let mut n = 0;
    for b in head {
        if !seen[*b as usize] {
            seen[*b as usize] = true;
            n += 1;
        }
    }
    n >= 6
}

/// Pick byte runs suitable for finding this payload again in memory.
///
/// A run has to be unique within the tag — otherwise a hit says nothing about
/// where the payload starts — and varied enough that it is not a run of padding
/// that half the heap would match. Runs come only from `region`, the tag's data
/// section: the header and the layout tables are not resident per tag, so a run
/// taken from them can never match and only wastes a prefilter slot.
fn pick_runs<'a>(
    payload: &'a [u8],
    region: &Range<usize>,
    avoid: &[Range<usize>],
    count: usize,
) -> Vec<(usize, &'a [u8])> {
    let mut out: Vec<(usize, &[u8])> = Vec::new();
    if region.len() < RUN * 4 || region.end > payload.len() || count == 0 {
        return out;
    }
    // Walk the region in `count` windows and take the first candidate from each
    // that passes the local filters, so the chosen set is spread out rather than
    // clustered wherever the entropy happens to be highest. Spread matters twice
    // over: against a mod concentrated in one part of the tag, and against the
    // engine's fix-ups.
    let span = region.len() / count;
    for w in 0..count {
        let from = region.start + w * span;
        let to = (from + span).min(region.end.saturating_sub(RUN));
        let mut off = from;
        while off < to {
            let run = &payload[off..off + RUN];
            let overlaps = avoid
                .iter()
                .any(|r| off < r.end.saturating_add(8) && r.start.saturating_sub(8) < off + RUN);
            let zeros = run.iter().filter(|b| **b == 0).count();
            let distinct = {
                let mut seen = [false; 256];
                let mut n = 0;
                for b in run {
                    if !seen[*b as usize] {
                        seen[*b as usize] = true;
                        n += 1;
                    }
                }
                n
            };
            if !overlaps && zeros <= RUN / 3 && distinct >= 20 && anchor_quality(run) {
                out.push((off, run));
                break;
            }
            off += 4;
        }
    }
    if out.is_empty() {
        return out;
    }

    // Uniqueness, batched: a run that repeats within the tag cannot say where
    // the payload starts, so it is dropped. This used to be a whole-payload
    // scan *per candidate*, which made building a census table over every tag
    // quadratic — tens of minutes, measured. One pass counting each
    // candidate's 8-byte prefix does the same job: a prefix that appears once
    // means the run appears once. A duplicated candidate is dropped rather
    // than retried, which at worst loses one window's run — agreement needs
    // only two of them.
    let mut first = [false; 256];
    let prefixes: Vec<u64> = out
        .iter()
        .map(|(_, run)| u64::from_le_bytes(run[..8].try_into().unwrap()))
        .collect();
    for p in &prefixes {
        first[(*p & 0xFF) as usize] = true;
    }
    let mut seen = vec![0u32; prefixes.len()];
    for i in 0..payload.len().saturating_sub(7) {
        if !first[payload[i] as usize] {
            continue;
        }
        let v = u64::from_le_bytes(payload[i..i + 8].try_into().unwrap());
        for (j, p) in prefixes.iter().enumerate() {
            if v == *p {
                seen[j] += 1;
            }
        }
    }
    out.into_iter()
        .zip(seen)
        .filter_map(|(c, n)| (n == 1).then_some(c))
        .collect()
}

/// Pick masked runs over a payload's stable bytes: the values the engine
/// keeps, with the references it rewrites masked out.
///
/// Same spread as [`pick_runs`] — one run per window — but within a window
/// the run with the most stable, non-zero bytes wins rather than the first
/// that passes, because a weapon's scalars come in clumps between long
/// stretches of references. The eight-byte key must be entirely stable and
/// carry at least four non-zero, four distinct bytes: `(1.0, 1.0)` and
/// `(2.0, 2.0)` are everywhere in a heap and fail that, and a key that
/// occurs twice in the payload is dropped as before. Bytes under `avoid`
/// are masked out rather than disqualifying the run.
fn pick_stable_runs(
    payload: &[u8],
    region: &Range<usize>,
    stable: &[bool],
    avoid: &[Range<usize>],
    count: usize,
) -> Vec<(usize, Vec<u8>, Vec<u8>)> {
    let mut out: Vec<(usize, Vec<u8>, Vec<u8>)> = Vec::new();
    if region.len() < RUN * 4
        || region.end > payload.len()
        || stable.len() < payload.len()
        || count == 0
    {
        return out;
    }
    let avoided = |i: usize| avoid.iter().any(|r| r.contains(&i));
    let span = region.len() / count;
    for w in 0..count {
        let from = region.start + w * span;
        let to = (from + span).min(region.end.saturating_sub(RUN));
        let mut best: Option<(usize, usize)> = None;
        for off in from..to {
            let key = &payload[off..off + 8];
            if !(off..off + 8).all(|i| stable[i] && !avoided(i)) {
                continue;
            }
            if key.iter().filter(|b| **b != 0).count() < 4 {
                continue;
            }
            let mut seen = [false; 256];
            let distinct = key.iter().filter(|b| !std::mem::replace(&mut seen[**b as usize], true)).count();
            if distinct < 4 {
                continue;
            }
            let score = (off..off + RUN)
                .filter(|i| stable[*i] && !avoided(*i) && payload[*i] != 0)
                .count();
            if score >= 12 && best.is_none_or(|(_, s)| score > s) {
                best = Some((off, score));
            }
        }
        if let Some((off, _)) = best {
            let body = payload[off..off + RUN].to_vec();
            let mask: Vec<u8> = (off..off + RUN)
                .map(|i| if stable[i] && !avoided(i) { 0xFF } else { 0 })
                .collect();
            out.push((off, body, mask));
        }
    }
    if out.is_empty() {
        return out;
    }
    // A key that repeats in the payload cannot say where the payload starts.
    let prefixes: Vec<u64> = out
        .iter()
        .map(|(_, body, _)| u64::from_le_bytes(body[..8].try_into().unwrap()))
        .collect();
    let mut seen = vec![0u32; prefixes.len()];
    for i in 0..payload.len().saturating_sub(7) {
        let v = u64::from_le_bytes(payload[i..i + 8].try_into().unwrap());
        for (j, p) in prefixes.iter().enumerate() {
            if v == *p {
                seen[j] += 1;
            }
        }
    }
    out.into_iter()
        .zip(seen)
        .filter_map(|(c, n)| (n == 1).then_some(c))
        .collect()
}

/// [`verify`] over the stable bytes only: the fraction of non-zero bytes
/// `stable` marks within the region that memory at `base` reproduces.
///
/// The plain fraction cannot tell a tag's working copy from a stray copy of
/// its section tables — both score in the fifties, because a data section
/// is mostly zeros and mostly references. Scored on the values alone, the
/// working copy is near 1.0 and the stray copy near 0.0.
pub fn verify_stable(
    process: &Process,
    payload: &[u8],
    region: &Range<usize>,
    stable: &[bool],
    base: u64,
) -> f32 {
    if region.end > payload.len() || stable.len() < payload.len() {
        return 0.0;
    }
    let Ok(live) = process.read(base + region.start as u64, region.len()) else {
        return 0.0;
    };
    if live.len() != region.len() {
        return 0.0;
    }
    let (mut same, mut total) = (0usize, 0usize);
    for (i, b) in payload[region.clone()].iter().enumerate() {
        if !stable[region.start + i] || *b == 0 {
            continue;
        }
        total += 1;
        if live[i] == *b {
            same += 1;
        }
    }
    if total == 0 {
        0.0
    } else {
        same as f32 / total as f32
    }
}

#[cfg(test)]
fn count_of(haystack: &[u8], needle: &[u8]) -> usize {
    let mut n = 0;
    let mut i = 0;
    while i + needle.len() <= haystack.len() {
        if &haystack[i..i + needle.len()] == needle {
            n += 1;
        }
        i += 1;
    }
    n
}

/// Find a loaded tag payload in the running process.
///
/// `payload` is the tag's bytes as read from the containers. `avoid` marks byte
/// ranges known to differ in memory — the fields a mod changed — so no locator
/// run is built over them.
pub fn locate(
    process: &Process,
    payload: &[u8],
    region: &Range<usize>,
    avoid: &[Range<usize>],
) -> Result<Located> {
    locate_with(process, payload, region, avoid, None)
}

/// [`locate`], fingerprinting only the bytes `stable` marks when it is given.
///
/// `stable` is one flag per payload byte, true where the byte holds a value
/// the engine keeps verbatim — the scalar fields, as `blam_tag::view::
/// scalar_mask` classifies them. It is what finds a tag the engine has
/// rewritten so thoroughly that no 48 contiguous bytes survive: a weapon's
/// resident copy has every string id, tag reference and block header
/// resolved in place, so the plain locator sees nothing of it and, worse,
/// settles for a stray copy of its section tables. The numbers between the
/// references still sit at their file offsets, and that is enough.
pub fn locate_with(
    process: &Process,
    payload: &[u8],
    region: &Range<usize>,
    avoid: &[Range<usize>],
    stable: Option<&[bool]>,
) -> Result<Located> {
    let (ranked, scanned) = candidates(process, payload, region, avoid, stable, &|_, _| {})?;
    if ranked.is_empty() {
        return Err(Error::NotFound);
    }

    // Agreement, not a match percentage, is what identifies the tag. Only about
    // 45% of the data section survives the engine's fix-ups byte-for-byte, so a
    // "does most of it match?" test would reject the true address. But the
    // surviving stretches sit at *exactly* the spacing the file gives them, and
    // nothing else in the heap reproduces that.
    let candidates = ranked.len();
    let (base, agreeing) = (ranked[0].base, ranked[0].agreeing_runs);
    if agreeing < MIN_AGREEMENT {
        return Err(Error::Unverified {
            candidates,
            best: agreeing as f32,
            need: MIN_AGREEMENT as f32,
        });
    }
    if ranked.len() > 1 && ranked[1].agreeing_runs == agreeing {
        return Err(Error::Ambiguous(
            ranked.iter().filter(|c| c.agreeing_runs == agreeing).count(),
        ));
    }

    // Reported for the operator's benefit, not used as a gate.
    let match_fraction = process
        .read(base + region.start as u64, region.len())
        .map(|live| {
            let same = live
                .iter()
                .zip(payload[region.clone()].iter())
                .filter(|(a, b)| a == b)
                .count();
            same as f32 / region.len() as f32
        })
        .unwrap_or(0.0);

    Ok(Located {
        base,
        match_fraction,
        agreeing_runs: agreeing,
        candidates,
        scanned,
    })
}

/// One base a locator run pointed at, from [`candidates`].
#[derive(Debug, Clone)]
pub struct Candidate {
    /// Address payload byte 0 would map to, as in [`Located`].
    pub base: u64,
    /// How many distinct runs agreed on it.
    pub agreeing_runs: usize,
}

/// Every base any locator run voted for, best agreement first.
///
/// [`locate`] is this plus the decision. This is for the caller who needs the
/// runners-up too: a second copy of the tag in memory — a pristine file image
/// beside the engine's working copy, say — shows up here as a rival, and only
/// by looking at both can it be told which one the simulation reads. Returns
/// the ranked candidates and the bytes scanned; empty when nothing matched.
/// The sweep is the census's — every writable region, on about half the
/// machine's cores — so a single tag costs what the census costs, seconds
/// rather than minutes.
pub fn candidates(
    process: &Process,
    payload: &[u8],
    region: &Range<usize>,
    avoid: &[Range<usize>],
    stable: Option<&[bool]>,
    progress: &(dyn Fn(u64, u64) + Sync),
) -> Result<(Vec<Candidate>, u64)> {
    let print = match stable {
        Some(stable) => {
            let runs = pick_stable_runs(payload, region, stable, avoid, RUNS);
            if runs.is_empty() {
                return Err(Error::TooSmall(region.len()));
            }
            let (runs, masks) = runs
                .into_iter()
                .map(|(off, body, mask)| ((off, body), mask))
                .unzip();
            Print { id: 0, runs, masks }
        }
        None => {
            let runs = pick_runs(payload, region, avoid, RUNS);
            if runs.is_empty() {
                return Err(Error::TooSmall(region.len()));
            }
            Print {
                id: 0,
                runs: runs
                    .into_iter()
                    .map(|(off, run)| (off, run.to_vec()))
                    .collect(),
                masks: Vec::new(),
            }
        }
    };
    let prints = [print];
    let matcher = Matcher::new(&prints);
    let (votes, scanned) = sweep(process, &matcher, progress)?;
    let mut ranked: Vec<Candidate> = votes
        .into_iter()
        .map(|((_, base), mut voters)| {
            // Distinct runs: one run matching twice is one piece of evidence.
            voters.sort_unstable();
            voters.dedup();
            Candidate {
                base,
                agreeing_runs: voters.len(),
            }
        })
        .collect();
    ranked.sort_by_key(|c| (std::cmp::Reverse(c.agreeing_runs), c.base));
    Ok((ranked, scanned))
}

/// Re-check an address already found, cheaply.
///
/// A located base is only good for the life of one process: relaunch the game
/// and the heap moves. Re-running [`locate`] to find that out would cost minutes,
/// where re-reading the data section and scoring it costs one read. Compare the
/// result against the `match_fraction` from the original [`locate`] — a base
/// that has gone stale scores far lower, because it is now pointing at whatever
/// else the allocator put there.
pub fn verify(process: &Process, payload: &[u8], region: &Range<usize>, base: u64) -> f32 {
    if region.end > payload.len() {
        return 0.0;
    }
    let Ok(live) = process.read(base + region.start as u64, region.len()) else {
        return 0.0;
    };
    if live.len() != region.len() {
        return 0.0;
    }
    let same = live
        .iter()
        .zip(payload[region.clone()].iter())
        .filter(|(a, b)| a == b)
        .count();
    same as f32 / region.len() as f32
}

/// Read a field's current bytes out of the live tag.
pub fn peek(process: &Process, at: &Located, offset: usize, len: usize) -> Result<Vec<u8>> {
    process.read(at.base + offset as u64, len)
}

/// Write a field's bytes into the live tag, and read them back to prove it took.
///
/// Returns the bytes as they read after the write, which is what the caller
/// should report — the write succeeding and the memory holding the new value
/// are different claims.
pub fn poke(process: &Process, at: &Located, offset: usize, bytes: &[u8]) -> Result<Vec<u8>> {
    process.write(at.base + offset as u64, bytes)?;
    process.read(at.base + offset as u64, bytes.len())
}

/// The byte range two versions of a payload differ over.
///
/// `blam_tag::patch` hands back a whole patched file; this narrows it to the
/// span actually worth writing, which for a fixed-width field is a handful of
/// bytes. `None` when they are identical.
pub fn diff_span(before: &[u8], after: &[u8]) -> Option<Range<usize>> {
    if before.len() != after.len() {
        return None;
    }
    let first = (0..before.len()).find(|i| before[*i] != after[*i])?;
    let last = (0..before.len()).rev().find(|i| before[*i] != after[*i])?;
    Some(first..last + 1)
}

// ---------------------------------------------------------------------------
// Census: every loaded tag in one sweep
// ---------------------------------------------------------------------------
//
// [`locate`] pays for one full pass over the process's writable memory — tens
// of gigabytes — to find one tag. But the pass itself does not care how many
// byte runs it is looking for: the cost is reading the memory and testing each
// position against a prefilter. So the same sweep can carry a few runs from
// *every* tag in the catalog and answer a different question — "which tags are
// loaded right now, and where?" — for the price of finding one.
//
// That inverts the live-mode experience. Instead of each first edit paying a
// scan, one census up front locates everything at once; every poke afterwards
// is a verify-and-write. And because the loaded `scnr` tag is among the hits,
// the census also answers "which level is the player in?" without asking the
// game anything.

/// A census fingerprint: a few locator runs for one tag, identified by the
/// caller's id (the tag editor uses its catalog index).
pub struct Print {
    pub id: u32,
    /// `(file offset, RUN bytes)`, picked by [`print`].
    pub runs: Vec<(usize, Vec<u8>)>,
    /// One byte mask per run, `0xFF` where the run's byte must match and
    /// `0` where it is ignored, for runs built over a tag whose references
    /// the engine rewrites (see [`candidates`]). Empty means every byte of
    /// every run must match. The first eight bytes of a masked run are
    /// always fully masked in: they are the search key.
    pub masks: Vec<Vec<u8>>,
}

/// Build a census fingerprint for one tag, or `None` when the tag's data
/// section is too small to carry enough independent runs to ever pass the
/// agreement bar.
pub fn print(id: u32, payload: &[u8], region: &Range<usize>) -> Option<Print> {
    print_n(id, payload, region, CENSUS_RUNS)
}

/// [`print`] with a caller-chosen run count, for tags worth more of the search
/// table — a scenario is rewritten harder than anything else at load, and it
/// is the tag that names the level, so it gets [`locate`]'s full spread.
pub fn print_n(id: u32, payload: &[u8], region: &Range<usize>, count: usize) -> Option<Print> {
    let runs = pick_runs(payload, region, &[], count);
    if runs.len() < MIN_AGREEMENT {
        return None;
    }
    Some(Print {
        id,
        runs: runs
            .into_iter()
            .map(|(off, run)| (off, run.to_vec()))
            .collect(),
        masks: Vec::new(),
    })
}

/// One tag the census found, pending the caller's verification read.
///
/// Agreement of independent runs is strong evidence, but tags share structure —
/// two copies of a weapon differ in a handful of fields — so the caller should
/// [`verify`] each hit against its own payload before trusting the base.
#[derive(Debug, Clone)]
pub struct CensusHit {
    pub id: u32,
    /// Address payload byte 0 maps to, as in [`Located`].
    pub base: u64,
    pub agreeing_runs: usize,
    /// Other bases exactly as many runs agreed on — identical copies of the
    /// tag in memory, say the loader's byte-perfect image beside the
    /// engine's working copy. Empty when `base` won outright. The caller
    /// picks among them with what it knows (see [`runtime_form`]) or drops
    /// the tag; a write to the wrong copy is worse than no write.
    pub rivals: Vec<u64>,
}

/// What one sweep of the process found.
pub struct Census {
    pub hits: Vec<CensusHit>,
    /// Tags whose best two candidate bases tied — two identical copies in
    /// memory, say — and were dropped rather than guessed at.
    pub ambiguous: usize,
    /// Bytes of process memory read.
    pub scanned: u64,
}

/// The multi-pattern search tables, separated from the process walk so the hot
/// loop can be tested against an ordinary buffer.
///
/// With tens of thousands of runs in play, the single-tag prefilter (256 first
/// bytes, 2^16 two-byte prefixes) would saturate and reject nothing. This one
/// keys on the first *eight* bytes: a bloom filter over a hash of the key
/// rejects almost every position with one multiply and a bit test, and a key
/// map takes the survivors to the run bodies they might begin. Identical run
/// bodies — near-copies of a tag share bytes, so their windows pick the same
/// runs — are stored once and fan out into votes for every owner, so one heap
/// position never pays the same compare twice.
struct Matcher<'a> {
    prints: &'a [Print],
    /// 2^24 bits over a hash of the eight-byte key.
    bloom: Vec<u64>,
    /// Eight-byte key -> indices into `bodies`.
    by_key: HashMap<u64, Vec<u32>>,
    /// One entry per distinct run body: the bytes (borrowed from the first
    /// owner), its mask if it has one, and every `(print index, run index)`
    /// that carries them.
    bodies: Vec<(&'a [u8], Option<&'a [u8]>, Vec<(u32, u32)>)>,
}

/// Votes: `(print index, candidate base)` -> distinct run indices that agreed.
type Votes = HashMap<(u32, u64), Vec<u32>>;

const BLOOM_BITS: u32 = 24;

fn bloom_slot(key: u64) -> (usize, u64) {
    let h = key.wrapping_mul(0x9E37_79B9_7F4A_7C15) >> (64 - BLOOM_BITS);
    ((h as usize) >> 6, 1u64 << (h & 63))
}

impl<'a> Matcher<'a> {
    fn new(prints: &'a [Print]) -> Self {
        let mut bloom = vec![0u64; 1 << (BLOOM_BITS - 6)];
        let mut by_key: HashMap<u64, Vec<u32>> = HashMap::new();
        let mut bodies: Vec<(&[u8], Option<&[u8]>, Vec<(u32, u32)>)> = Vec::new();
        let mut by_body: HashMap<(&[u8], Option<&[u8]>), u32> = HashMap::new();
        for (p, print) in prints.iter().enumerate() {
            for (r, (_, run)) in print.runs.iter().enumerate() {
                let owner = (p as u32, r as u32);
                let mask = print.masks.get(r).map(Vec::as_slice);
                match by_body.entry((run.as_slice(), mask)) {
                    std::collections::hash_map::Entry::Occupied(e) => {
                        bodies[*e.get() as usize].2.push(owner);
                    }
                    std::collections::hash_map::Entry::Vacant(e) => {
                        let key = u64::from_le_bytes(run[..8].try_into().unwrap());
                        let (slot, bit) = bloom_slot(key);
                        bloom[slot] |= bit;
                        e.insert(bodies.len() as u32);
                        by_key.entry(key).or_default().push(bodies.len() as u32);
                        bodies.push((run.as_slice(), mask, vec![owner]));
                    }
                }
            }
        }
        Matcher {
            prints,
            bloom,
            by_key,
            bodies,
        }
    }

    /// Scan one buffer of process memory that starts at `addr`, adding votes.
    fn scan(&self, buf: &[u8], addr: u64, votes: &mut Votes) {
        if buf.len() < RUN {
            return;
        }
        let last = buf.len() - RUN;
        for i in 0..=last {
            let key = u64::from_le_bytes(buf[i..i + 8].try_into().unwrap());
            let (slot, bit) = bloom_slot(key);
            if self.bloom[slot] & bit == 0 {
                continue;
            }
            let Some(list) = self.by_key.get(&key) else {
                continue;
            };
            for &bi in list {
                let (body, mask, owners) = &self.bodies[bi as usize];
                let here = &buf[i..i + RUN];
                let hit = match mask {
                    None => here == *body,
                    Some(m) => here
                        .iter()
                        .zip(*body)
                        .zip(*m)
                        .all(|((x, b), m)| (x ^ b) & m == 0),
                };
                if hit {
                    for &(p, r) in owners {
                        let off = self.prints[p as usize].runs[r as usize].0;
                        let base = (addr + i as u64).wrapping_sub(off as u64);
                        votes.entry((p, base)).or_default().push(r);
                    }
                }
            }
        }
    }
}

/// Turn merged votes into at most one hit per print.
fn tally(prints: &[Print], votes: Votes) -> (Vec<CensusHit>, usize) {
    // Per print: candidate bases ranked by how many *distinct* runs agree.
    let mut per_print: HashMap<u32, Vec<(u64, usize)>> = HashMap::new();
    for ((p, base), mut runs) in votes {
        runs.sort_unstable();
        runs.dedup();
        per_print.entry(p).or_default().push((base, runs.len()));
    }
    let mut hits = Vec::new();
    let mut ambiguous = 0;
    for (p, mut ranked) in per_print {
        ranked.sort_by_key(|(b, n)| (std::cmp::Reverse(*n), *b));
        let (base, agreeing) = ranked[0];
        if agreeing < MIN_AGREEMENT {
            continue;
        }
        // Bases equally believable are identical copies in memory. They are
        // all reported: the caller can tell the engine's working copy from
        // the loader's image, which the votes cannot.
        let rivals: Vec<u64> = ranked[1..]
            .iter()
            .take_while(|(_, n)| *n == agreeing)
            .map(|(b, _)| *b)
            .collect();
        if !rivals.is_empty() {
            ambiguous += 1;
        }
        hits.push(CensusHit {
            id: prints[p as usize].id,
            base,
            agreeing_runs: agreeing,
            rivals,
        });
    }
    hits.sort_by_key(|h| h.id);
    (hits, ambiguous)
}

/// Sweep the process once and report a candidate base for every print found.
///
/// `progress` is called with `(bytes scanned, bytes total)` as regions
/// complete; it must be cheap and thread-safe, because the sweep runs on
/// several threads. The thread count is deliberately about half the machine:
/// the process being scanned is a *game the player may be looking at*, and
/// taking every core turns the census into a hitch they can feel.
pub fn census(
    process: &Process,
    prints: &[Print],
    progress: &(dyn Fn(u64, u64) + Sync),
) -> Result<Census> {

    if prints.is_empty() {
        return Ok(Census {
            hits: Vec::new(),
            ambiguous: 0,
            scanned: 0,
        });
    }
    let matcher = Matcher::new(prints);
    let (votes, scanned) = sweep(process, &matcher, progress)?;
    let (hits, ambiguous) = tally(prints, votes);
    Ok(Census {
        hits,
        ambiguous,
        scanned,
    })
}

/// Sweep every writable region of the process once against `matcher`, on
/// about half the machine's cores, and hand back the merged votes and the
/// bytes read. The thread count is deliberately half: the process being
/// scanned is a *game the player may be looking at*, and taking every core
/// turns the sweep into a hitch they can feel.
fn sweep(
    process: &Process,
    matcher: &Matcher<'_>,
    progress: &(dyn Fn(u64, u64) + Sync),
) -> Result<(Votes, u64)> {
    // Windows over every region, sized so a thread's buffer stays modest and
    // work splits evenly; overlapped by a run length so no seam hides a match.
    // The tag heap lives in regions of several hundred MB to a couple of GB,
    // so skipping large regions — the obvious way to make a scanner "fast" —
    // skips exactly the memory being looked for and turns a hit into a
    // confident miss.
    const WINDOW: u64 = 16 * 1024 * 1024;
    use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};

    let mut jobs: Vec<(u64, usize)> = Vec::new();
    let mut total: u64 = 0;
    for region in process.writable_regions()? {
        total += region.size;
        let mut at = 0u64;
        while at < region.size {
            let want = (WINDOW + RUN as u64 - 1).min(region.size - at) as usize;
            jobs.push((region.base + at, want));
            at += WINDOW;
        }
    }

    let next = AtomicUsize::new(0);
    let scanned = AtomicU64::new(0);
    let threads = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(4)
        .div_ceil(2)
        .clamp(1, 8);

    let votes: Votes = std::thread::scope(|s| {
        let workers: Vec<_> = (0..threads)
            .map(|_| {
                let jobs = &jobs;
                let next = &next;
                let scanned = &scanned;
                s.spawn(move || {
                    let mut local: Votes = HashMap::new();
                    let mut window = vec![0u8; (WINDOW as usize) + RUN];
                    loop {
                        let j = next.fetch_add(1, Ordering::Relaxed);
                        let Some(&(addr, want)) = jobs.get(j) else {
                            break;
                        };
                        // A region can decommit mid-sweep; whatever cannot be
                        // read is simply not scanned.
                        if let Ok(got) = process.read_into(addr, &mut window[..want]) {
                            matcher.scan(&window[..got], addr, &mut local);
                            let done = scanned.fetch_add(got as u64, Ordering::Relaxed);
                            progress(done + got as u64, total);
                        }
                    }
                    local
                })
            })
            .collect();
        let mut merged: Votes = HashMap::new();
        for w in workers {
            for (key, mut runs) in w.join().expect("census worker panicked") {
                merged.entry(key).or_default().append(&mut runs);
            }
        }
        merged
    });
    Ok((votes, scanned.into_inner()))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn payload(len: usize) -> Vec<u8> {
        // Deterministic pseudo-random bytes: varied enough to pass the entropy
        // filter, reproducible so a failure is debuggable.
        let mut v = Vec::with_capacity(len);
        let mut x: u32 = 0x1234_5678;
        for _ in 0..len {
            x = x.wrapping_mul(1_664_525).wrapping_add(1_013_904_223);
            v.push((x >> 16) as u8);
        }
        v
    }

    #[test]
    fn runs_are_unique_and_spread_across_the_region() {
        let p = payload(51_023);
        let region = 0x4800..p.len();
        let runs = pick_runs(&p, &region, &[], RUNS);
        assert!(
            runs.len() >= 8,
            "expected a spread of runs, got {}",
            runs.len()
        );
        for (off, run) in &runs {
            assert_eq!(
                count_of(&p, run),
                1,
                "run at {off} must be unique in the tag"
            );
        }
        let first = runs.first().unwrap().0;
        let last = runs.last().unwrap().0;
        assert!(
            last - first > region.len() / 2,
            "runs must span the region so a localised rewrite cannot invalidate all of them"
        );
    }

    #[test]
    fn runs_never_come_from_outside_the_resident_region() {
        // The header and layout tables are not resident per tag, so a run taken
        // from them can never match and would only waste a prefilter slot.
        let p = payload(51_023);
        let region = 0x4800..p.len();
        for (off, _) in pick_runs(&p, &region, &[], RUNS) {
            assert!(
                off >= region.start && off + RUN <= region.end,
                "run at {off:#x} escapes the resident region {region:#x?}"
            );
        }
    }

    #[test]
    fn avoided_ranges_are_never_covered() {
        let p = payload(51_023);
        // Stand in for a mod that changed two fields.
        let avoid = vec![0x8896..0x889A, 0x88C2..0x88C6];
        for (off, _) in pick_runs(&p, &(0x4800..p.len()), &avoid, RUNS) {
            for a in &avoid {
                let overlaps = off < a.end && a.start < off + RUN;
                assert!(!overlaps, "run at {off:#x} overlaps modded field {a:#x?}");
            }
        }
    }

    #[test]
    fn a_region_too_small_to_fingerprint_is_rejected_not_guessed() {
        let p = payload(4096);
        assert!(pick_runs(&p, &(0..RUN * 2), &[], RUNS).is_empty());
        // A region running off the end of the payload must not panic either.
        assert!(pick_runs(&p, &(0..p.len() + 999), &[], RUNS).is_empty());
    }

    #[test]
    fn diff_span_narrows_a_whole_file_patch_to_the_field() {
        let mut before = payload(2048);
        let mut after = before.clone();
        after[0x100] ^= 0xFF;
        after[0x102] ^= 0xFF;
        assert_eq!(diff_span(&before, &after), Some(0x100..0x103));
        before.push(0);
        assert_eq!(diff_span(&before, &after), None, "a resize has no span");
    }

    #[test]
    fn identical_payloads_have_no_diff_span() {
        let p = payload(512);
        assert_eq!(diff_span(&p, &p), None);
    }

    /// A distinct deterministic payload per seed, so census tests can hold
    /// several "tags" that share no bytes. SplitMix64 over `(seed, index)`
    /// rather than an LCG walked from a seed: every LCG orbit is one shared
    /// cycle, so two "different" payloads would be shifted copies of the same
    /// stream and could collide by construction.
    fn seeded_payload(len: usize, seed: u64) -> Vec<u8> {
        (0..len as u64)
            .map(|n| {
                let mut z = n.wrapping_add(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15));
                z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
                z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
                (z >> 33) as u8
            })
            .collect()
    }

    #[test]
    fn census_matcher_finds_each_planted_tag_at_its_base() {
        // Three tags, two of them planted into a heap-like buffer at known
        // offsets, the third absent. The matcher must report exactly the two
        // planted bases, each with more runs agreeing than the bar asks.
        let tags: Vec<Vec<u8>> = (0..3).map(|i| seeded_payload(24_000, 77 + i)).collect();
        let prints: Vec<Print> = tags
            .iter()
            .enumerate()
            .map(|(i, t)| print(i as u32, t, &(0x400..t.len())).expect("printable"))
            .collect();

        let mut heap = seeded_payload(1_500_000, 999);
        let addr = 0x7ff6_0000_0000u64;
        // Only the "data section" is resident, as in the real heap.
        heap[300_000..300_000 + 24_000 - 0x400].copy_from_slice(&tags[0][0x400..]);
        heap[900_000..900_000 + 24_000 - 0x400].copy_from_slice(&tags[2][0x400..]);

        let matcher = Matcher::new(&prints);
        let mut votes = Votes::new();
        matcher.scan(&heap, addr, &mut votes);
        let (hits, ambiguous) = tally(&prints, votes);

        assert_eq!(ambiguous, 0);
        assert_eq!(
            hits.iter().map(|h| h.id).collect::<Vec<_>>(),
            vec![0, 2],
            "exactly the planted tags are found"
        );
        for hit in &hits {
            let planted = if hit.id == 0 { 300_000 } else { 900_000 };
            assert_eq!(hit.base, addr + planted - 0x400, "base maps payload byte 0");
            assert!(hit.agreeing_runs >= MIN_AGREEMENT);
        }
    }

    #[test]
    fn census_survives_a_partly_rewritten_tag() {
        // The engine rewrites much of a data section in place. Zero half of
        // the planted copy in alternating stripes; enough spread-out runs must
        // still land for the tag to be found.
        let tag = seeded_payload(32_000, 4242);
        let prints = vec![print(7, &tag, &(0x400..tag.len())).expect("printable")];

        let mut heap = seeded_payload(600_000, 31337);
        let resident = 32_000 - 0x400;
        heap[100_000..100_000 + resident].copy_from_slice(&tag[0x400..]);
        // Zero the first half of every other run-picking window, so the runs
        // chosen there are destroyed and only the odd windows' runs survive.
        let span = resident / CENSUS_RUNS;
        for w in (0..CENSUS_RUNS).step_by(2) {
            let from = 100_000 + w * span;
            heap[from..from + span / 2].fill(0);
        }

        let matcher = Matcher::new(&prints);
        let mut votes = Votes::new();
        matcher.scan(&heap, 0x1000, &mut votes);
        let (hits, _) = tally(&prints, votes);
        assert_eq!(hits.len(), 1, "half-rewritten tag is still censused");
        assert_eq!(hits[0].base, 0x1000 + 100_000 - 0x400);
    }

    #[test]
    fn census_matches_across_a_window_seam() {
        // Feed the same heap in two overlapping windows, as the sweep does,
        // and check a tag straddling the cut is still found once.
        let tag = seeded_payload(24_000, 555);
        let prints = vec![print(1, &tag, &(0x400..tag.len())).expect("printable")];
        let mut heap = seeded_payload(400_000, 777);
        heap[190_000..190_000 + 24_000 - 0x400].copy_from_slice(&tag[0x400..]);

        let matcher = Matcher::new(&prints);
        let mut votes = Votes::new();
        let cut = 200_000;
        matcher.scan(&heap[..cut + RUN - 1], 0, &mut votes);
        matcher.scan(&heap[cut..], cut as u64, &mut votes);
        let (hits, _) = tally(&prints, votes);
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].base, 190_000 - 0x400);
    }

    #[test]
    fn two_identical_copies_are_ambiguous_not_guessed() {
        let tag = seeded_payload(24_000, 888);
        let prints = vec![print(3, &tag, &(0x400..tag.len())).expect("printable")];
        let mut heap = seeded_payload(700_000, 222);
        heap[50_000..50_000 + 24_000 - 0x400].copy_from_slice(&tag[0x400..]);
        heap[400_000..400_000 + 24_000 - 0x400].copy_from_slice(&tag[0x400..]);

        let matcher = Matcher::new(&prints);
        let mut votes = Votes::new();
        matcher.scan(&heap, 0, &mut votes);
        let (hits, ambiguous) = tally(&prints, votes);
        // Neither copy wins on votes; both are reported so the caller can
        // tell them apart by what the votes cannot see.
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].rivals.len(), 1, "the tie is carried, not guessed at");
        let mut bases = vec![hits[0].base];
        bases.extend(&hits[0].rivals);
        bases.sort_unstable();
        assert_eq!(bases, vec![50_000 - 0x400, 400_000 - 0x400]);
        assert_eq!(ambiguous, 1);
    }

    /// The engine's working copy keeps only the scalar fields; every
    /// reference between them is rewritten. A print masked to the scalars
    /// finds it where the plain print cannot.
    #[test]
    fn a_masked_print_finds_a_copy_with_its_references_rewritten() {
        let tag = seeded_payload(24_000, 4242);
        let region = 0x400..tag.len();
        let root = 0x400..0x400 + 4_000;
        // Scalars: sixteen bytes of them, then eight bytes of "references".
        let stable: Vec<bool> = (0..tag.len()).map(|i| i % 24 < 16).collect();
        let shape = Shape {
            region: region.clone(),
            root: root.clone(),
            stable: &stable,
            headers: &[],
        };
        let print = print_stable(7, &tag, &shape, 12).expect("printable");
        assert!(print.runs.len() >= MIN_AGREEMENT);
        assert_eq!(print.masks.len(), print.runs.len());

        // A heap holding the tag with every reference byte scrambled.
        let mut heap = seeded_payload(300_000, 99);
        let at = 120_000;
        for i in root.clone() {
            heap[at + i - region.start] = if stable[i] { tag[i] } else { !tag[i] };
        }
        let plain = print_n(7, &tag, &region, 12).expect("plain print");
        for (p, expect_hit) in [(print, true), (plain, false)] {
            let prints = vec![p];
            let matcher = Matcher::new(&prints);
            let mut votes = Votes::new();
            matcher.scan(&heap, 0, &mut votes);
            let (hits, _) = tally(&prints, votes);
            assert_eq!(!hits.is_empty(), expect_hit);
            if expect_hit {
                assert_eq!(hits[0].base, (at - region.start) as u64);
            }
        }
    }

    #[test]
    fn a_tag_too_small_to_print_is_refused() {
        // Below the same RUN * 4 floor `locate` applies; no runs, no print.
        let tiny = seeded_payload(RUN * 4 - 1, 9);
        assert!(print(0, &tiny, &(0..tiny.len())).is_none());
    }
}

/// One block boundary on the way to a field, in file terms — what
/// `blam_tag::patch::route` reports, carried here without the dependency.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Hop {
    /// File offset of the block field in the parent element: the twelve-byte
    /// placeholder the file carries, which the engine overwrites with a
    /// [`BlockHeader`].
    pub header: usize,
    /// The element the path enters.
    pub index: usize,
    /// File offset of that element's packed bytes.
    pub element: usize,
    /// Packed size of one element.
    pub element_size: usize,
}

/// A block field as the engine rewrites it in the resident copy.
///
/// The file stores a block field as twelve bytes — the element count and
/// eight bytes of zeros — with the elements themselves packed later in the
/// data section. At load the engine moves every block's elements out of the
/// tag and fills those eight bytes in: an offset to the elements in **4-byte
/// units from a process-wide arena**, and a per-struct identifier. Measured
/// on the magnum and the assault rifle in a30: every block of both weapons
/// resolved through `arena + 4 * words` to bytes matching the file's
/// elements, and a magnification written there changed the HUD's zoom.
///
/// This is why a weapon's root-level fields poke at `base + file offset`
/// while a field inside `zoom levels[0]` does not: the root element keeps
/// the file's layout, the elements do not stay where the file put them.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BlockHeader {
    pub count: u32,
    /// Offset of element 0 from the arena, in 4-byte units.
    pub words: u32,
    /// Identifies the element struct; the same for every block of one
    /// struct type, across tags.
    pub struct_id: u32,
}

/// Read the engine's block header at `at`.
pub fn read_block_header(process: &Process, at: u64) -> Result<BlockHeader> {
    let b = process.read(at, 12)?;
    Ok(BlockHeader {
        count: u32::from_le_bytes(b[0..4].try_into().unwrap()),
        words: u32::from_le_bytes(b[4..8].try_into().unwrap()),
        struct_id: u32::from_le_bytes(b[8..12].try_into().unwrap()),
    })
}

/// Where a field's bytes are in the running game.
///
/// A root-element field sits at `base + file offset`. A field inside a block
/// element is reached through each block header on the way: the header's
/// offset word names the element array, the hop's index picks the element,
/// and the field is at the same offset within the element as in the file.
/// `arena` is the base every header offset counts from — [`derive_arena`].
pub fn field_address(
    process: &Process,
    base: u64,
    arena: u64,
    hops: &[Hop],
    file_offset: usize,
) -> Result<u64> {
    // The element the walk is in: its live address and its file offset.
    let mut element: Option<(u64, usize)> = None;
    for hop in hops {
        let header = match element {
            None => base + hop.header as u64,
            Some((live, file)) => live + hop.header.saturating_sub(file) as u64,
        };
        let h = read_block_header(process, header)?;
        if hop.index as u32 >= h.count {
            return Err(Error::ElementGone {
                index: hop.index,
                count: h.count,
            });
        }
        let elements = arena + 4 * h.words as u64;
        element = Some((
            elements + (hop.index * hop.element_size) as u64,
            hop.element,
        ));
    }
    Ok(match element {
        None => base + file_offset as u64,
        Some((live, file)) => live + file_offset.saturating_sub(file) as u64,
    })
}

/// The arena the engine's block headers count from, found from one located
/// tag.
///
/// Nothing static names it — no slot in the game image holds it — but any
/// block whose elements carry a few distinctive scalar bytes gives it away:
/// read the header's offset word, find the elements by their own bytes near
/// the tag's resident copy (the engine keeps a tag's elements within a few
/// hundred KB of its root element), and subtract. Two blocks agreeing settle
/// it; one is accepted when it is all the tag offers. `blocks` are root-level
/// hops (`index` 0) paired with the file's element count; `stable` is the
/// scalar mask over `payload`. Measured: the magnum's `melee damage
/// parameters` and `barrels` both gave `0x1b3de0a0000`, one gigabyte below
/// the committed heap region holding the tag.
pub fn derive_arena(
    process: &Process,
    base: u64,
    payload: &[u8],
    stable: &[bool],
    blocks: &[(Hop, u32)],
) -> Option<u64> {
    const REACH: u64 = 0x80000;
    let first = blocks.first()?;
    let lo = (base + first.0.header as u64).saturating_sub(REACH);
    let mut window = vec![0u8; 2 * REACH as usize];
    let got = process.read_into(lo, &mut window).ok()?;
    let window = &window[..got];

    let mut found: Vec<u64> = Vec::new();
    for (hop, count) in blocks {
        let len = *count as usize * hop.element_size;
        let Some(image) = payload.get(hop.element..hop.element + len) else {
            continue;
        };
        let keep: Vec<bool> = (hop.element..hop.element + len)
            .map(|i| stable.get(i).copied().unwrap_or(false))
            .collect();
        if keep
            .iter()
            .zip(image)
            .filter(|(k, b)| **k && **b != 0)
            .count()
            < 8
        {
            continue;
        }
        let Ok(h) = read_block_header(process, base + hop.header as u64) else {
            continue;
        };
        if h.count != *count || h.words == 0 {
            continue;
        }
        let mut hits = Vec::new();
        'pos: for p in 0..window.len().saturating_sub(len) {
            for i in 0..len {
                if keep[i] && window[p + i] != image[i] {
                    continue 'pos;
                }
            }
            hits.push(lo + p as u64);
            if hits.len() > 1 {
                break;
            }
        }
        if let [hit] = hits.as_slice() {
            found.push(hit.wrapping_sub(4 * h.words as u64));
        }
    }
    found.sort_unstable();
    if found.len() >= 2 {
        found
            .windows(2)
            .find(|w| w[0] == w[1])
            .map(|w| w[0])
    } else {
        found.first().copied()
    }
}

/// Whether the copy at `base` is the engine's working copy rather than an
/// untouched image of the file.
///
/// The loader keeps byte-perfect copies of a tag around — a census in a30
/// found nineteen weapons at 100% — and a write into one of those changes
/// nothing the simulation reads. The working copy is told apart by its
/// block headers: the file's eight zero bytes after each count have been
/// overwritten. `headers` are the file offsets of root-level block fields
/// whose file count is non-zero.
pub fn runtime_form(process: &Process, base: u64, headers: &[usize]) -> bool {
    headers.iter().any(|h| {
        read_block_header(process, base + *h as u64)
            .map(|b| b.words != 0)
            .unwrap_or(false)
    })
}

/// What the caller knows about a tag's layout that finding it can use.
///
/// All of it comes from the tag file itself, through `blam_tag`: the
/// resident data section, the root element within it, which bytes hold
/// scalar values, and where the root element's block fields are.
#[derive(Debug, Clone)]
pub struct Shape<'a> {
    /// The resident data section within the payload.
    pub region: Range<usize>,
    /// The root element — the part of the data section the engine keeps at
    /// its file offsets. Everything after it is block elements, which the
    /// engine moves out (see [`BlockHeader`]).
    pub root: Range<usize>,
    /// One flag per payload byte: true where the byte holds a scalar value,
    /// as `blam_tag::view::scalar_mask` classifies them.
    pub stable: &'a [bool],
    /// File offsets of the root element's block fields that have elements.
    /// What tells the working copy from a byte-perfect image of the file.
    pub headers: &'a [usize],
}

/// How much of a tag's root element must be reproduced, scalar byte for
/// scalar byte, before an address is believed to be that tag.
///
/// The working copy scores 1.0 on the magnum and the assault rifle; unrelated
/// heap scores near zero, and a stray copy of the tag's section tables — the
/// false positive the plain locator kept settling on — scored 0.10 on the
/// magnum. Fields the engine computes at load are zero on disk and so are
/// never counted, which is why the bar can sit this high.
const ACCEPT: f32 = 0.6;

/// [`print_n`] over a tag's stable bytes: a masked fingerprint that finds the
/// engine's working copy, which the plain print cannot.
///
/// Runs are picked over the root element when it is big enough to carry
/// them, since that is the part of the tag the engine keeps at file offsets;
/// a tiny root element falls back to the whole data section.
pub fn print_stable(id: u32, payload: &[u8], shape: &Shape<'_>, count: usize) -> Option<Print> {
    let region = if shape.root.len() >= RUN * 4 {
        &shape.root
    } else {
        &shape.region
    };
    let runs = pick_stable_runs(payload, region, shape.stable, &[], count);
    if runs.len() < MIN_AGREEMENT {
        return None;
    }
    let (runs, masks) = runs
        .into_iter()
        .map(|(off, body, mask)| ((off, body), mask))
        .unzip();
    Some(Print { id, runs, masks })
}

/// Whether the root element has scalar bytes worth scoring on. A tag that
/// is all references — a string list, say — has none, and is scored the old
/// way, byte for byte over the data section.
fn has_scalars(payload: &[u8], shape: &Shape<'_>) -> bool {
    shape
        .root
        .clone()
        .any(|i| shape.stable.get(i).copied().unwrap_or(false) && payload.get(i).is_some_and(|b| *b != 0))
}

/// How well memory at `base` reproduces the tag's root element, on its
/// scalar bytes alone. See [`verify_stable`].
pub fn score(process: &Process, payload: &[u8], shape: &Shape<'_>, base: u64) -> f32 {
    if has_scalars(payload, shape) {
        verify_stable(process, payload, &shape.root, shape.stable, base)
    } else {
        verify(process, payload, &shape.region, base)
    }
}

/// Whether `base` is this tag's working copy: the root element's scalars are
/// there, and — when the tag has blocks with elements — the block headers
/// carry the engine's rewrite rather than the file's zeros.
pub fn accept(process: &Process, payload: &[u8], shape: &Shape<'_>, base: u64) -> bool {
    let bar = if has_scalars(payload, shape) { ACCEPT } else { 0.10 };
    score(process, payload, shape, base) >= bar
        && (shape.headers.is_empty() || runtime_form(process, base, shape.headers))
}

/// Find a tag's working copy in the running process.
///
/// The masked sweep over the root element's scalars ranks every base any run
/// pointed at; the first that [`accept`] agrees with is the answer. Ties
/// between identical copies are resolved by that same test, since only the
/// working copy has rewritten block headers. A tag with no scalar bytes to
/// speak of falls back to the plain 48-byte locator.
pub fn find(
    process: &Process,
    payload: &[u8],
    shape: &Shape<'_>,
    avoid: &[Range<usize>],
) -> Result<Located> {
    let region = if shape.root.len() >= RUN * 4 {
        &shape.root
    } else {
        &shape.region
    };
    let (ranked, scanned) = match candidates(process, payload, region, avoid, Some(shape.stable), &|_, _| {}) {
        Ok(r) => r,
        Err(Error::TooSmall(_)) => return locate(process, payload, &shape.region, avoid),
        Err(e) => return Err(e),
    };
    if ranked.is_empty() {
        return Err(Error::NotFound);
    }
    let best = ranked[0].agreeing_runs;
    for c in &ranked {
        if c.agreeing_runs < MIN_AGREEMENT {
            break;
        }
        if accept(process, payload, shape, c.base) {
            return Ok(Located {
                base: c.base,
                match_fraction: score(process, payload, shape, c.base),
                agreeing_runs: c.agreeing_runs,
                candidates: ranked.len(),
                scanned,
            });
        }
    }
    Err(Error::Unverified {
        candidates: ranked.len(),
        best: best as f32,
        need: MIN_AGREEMENT as f32,
    })
}
