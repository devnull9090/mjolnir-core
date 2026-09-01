//! Reading and patching a Blam tag payload inside the running game.
//!
//! The game parses a tag once at load into a heap buffer that keeps the tag
//! file's own layout, and then reads fields out of that buffer as the
//! simulation runs. So a field can be changed at runtime by writing the same
//! bytes `blam_tag::patch` would have written to the file, at the same offset,
//! in the live process — no rebuild, no restart.
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

pub mod names;
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
) -> Vec<(usize, &'a [u8])> {
    let mut out: Vec<(usize, &[u8])> = Vec::new();
    if region.len() < RUN * 4 || region.end > payload.len() {
        return out;
    }
    // Walk the region in RUNS windows and take the first usable run from each,
    // so the chosen set is spread out rather than clustered wherever the entropy
    // happens to be highest. Spread matters twice over: against a mod
    // concentrated in one part of the tag, and against the engine's fix-ups.
    let span = region.len() / RUNS;
    for w in 0..RUNS {
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
            if !overlaps && zeros <= RUN / 3 && distinct >= 20 && count_of(payload, run) == 1 {
                out.push((off, run));
                break;
            }
            off += 4;
        }
    }
    out
}

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
    let runs = pick_runs(payload, region, avoid);
    if runs.is_empty() {
        return Err(Error::TooSmall(region.len()));
    }

    // Two-stage prefilter. The first-byte table rejects ~95% of positions with
    // one bounds-free array read; only survivors pay for the 2-byte check and
    // fewer still for the full compare. This inner loop runs about twenty
    // billion times, so the constant factor is the whole cost of the scan.
    let mut first_byte = [false; 256];
    let mut prefilter = vec![false; 1 << 16];
    let mut by_prefix: HashMap<u16, Vec<usize>> = HashMap::new();
    for (i, (_, run)) in runs.iter().enumerate() {
        let key = u16::from_le_bytes([run[0], run[1]]);
        first_byte[run[0] as usize] = true;
        prefilter[key as usize] = true;
        by_prefix.entry(key).or_default().push(i);
    }

    let mut scanned: u64 = 0;
    // base address -> which runs pointed at it
    let mut votes: HashMap<u64, Vec<usize>> = HashMap::new();
    let mut window = vec![0u8; 128 * 1024 * 1024 + RUN];

    for region in process.writable_regions()? {
        // Big regions are read in windows, overlapping by a run length so a
        // match cannot be lost across a seam. The tag heap lives in regions of
        // several hundred MB to a couple of GB, so skipping large regions —
        // the obvious way to make a scanner "fast" — skips exactly the memory
        // being looked for and turns a hit into a confident miss.
        const WINDOW: u64 = 128 * 1024 * 1024;
        let mut at = 0u64;
        while at < region.size {
            let want = (WINDOW + RUN as u64 - 1).min(region.size - at) as usize;
            let Ok(got) = process.read_into(region.base + at, &mut window[..want]) else {
                at += WINDOW;
                continue;
            };
            let buf = &window[..got];
            scanned += buf.len() as u64;
            if buf.len() >= RUN {
                let last = buf.len() - RUN;
                for (i, b) in buf[..=last].iter().enumerate() {
                    if !first_byte[*b as usize] {
                        continue;
                    }
                    let key = u16::from_le_bytes([buf[i], buf[i + 1]]);
                    if !prefilter[key as usize] {
                        continue;
                    }
                    for &r in by_prefix.get(&key).into_iter().flatten() {
                        let (off, run) = runs[r];
                        if &buf[i..i + RUN] == run {
                            let hit = region.base + at + i as u64;
                            votes
                                .entry(hit.wrapping_sub(off as u64))
                                .or_default()
                                .push(r);
                        }
                    }
                }
            }
            at += WINDOW;
        }
    }

    if votes.is_empty() {
        return Err(Error::NotFound);
    }

    // Agreement, not a match percentage, is what identifies the tag. Only about
    // 45% of the data section survives the engine's fix-ups byte-for-byte, so a
    // "does most of it match?" test would reject the true address. But the
    // surviving stretches sit at *exactly* the spacing the file gives them, and
    // nothing else in the heap reproduces that.
    let candidates = votes.len();
    let mut ranked: Vec<(u64, usize)> = votes
        .into_iter()
        .map(|(base, voters)| {
            // Distinct runs: one run matching twice is one piece of evidence.
            let mut v = voters;
            v.sort_unstable();
            v.dedup();
            (base, v.len())
        })
        .collect();
    ranked.sort_by_key(|(_, n)| std::cmp::Reverse(*n));

    let (base, agreeing) = ranked[0];
    if agreeing < MIN_AGREEMENT {
        return Err(Error::Unverified {
            candidates,
            best: agreeing as f32,
            need: MIN_AGREEMENT as f32,
        });
    }
    if ranked.len() > 1 && ranked[1].1 == agreeing {
        return Err(Error::Ambiguous(
            ranked.iter().filter(|(_, n)| *n == agreeing).count(),
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
        let runs = pick_runs(&p, &region, &[]);
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
        for (off, _) in pick_runs(&p, &region, &[]) {
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
        for (off, _) in pick_runs(&p, &(0x4800..p.len()), &avoid) {
            for a in &avoid {
                let overlaps = off < a.end && a.start < off + RUN;
                assert!(!overlaps, "run at {off:#x} overlaps modded field {a:#x?}");
            }
        }
    }

    #[test]
    fn a_region_too_small_to_fingerprint_is_rejected_not_guessed() {
        let p = payload(4096);
        assert!(pick_runs(&p, &(0..RUN * 2), &[]).is_empty());
        // A region running off the end of the payload must not panic either.
        assert!(pick_runs(&p, &(0..p.len() + 999), &[]).is_empty());
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
}
