//! Does a tag asset's `UObject` point at its data buffer?
//!
//! The census finds a tag's resident buffer by sweeping ~13 GB of memory. If
//! the buffer address is instead reachable from the tag's `UObject` — which
//! [`blam_live::objects`] can enumerate instantly — then both "is this tag's
//! data resident?" and "where do I poke it?" become pointer chases.
//!
//! Earlier probing (see `docs/live_tag_locating.md`) looked for the census's
//! *synthetic* base (`data_start - r0`) in the `UObject` and found nothing.
//! This asks the better question: take every pointer-shaped field in and near
//! the `UObject`, follow it, and check whether the bytes there **are** the
//! tag's data section. That needs no prior census — the tag's own bytes from
//! the catalog are the oracle — and a hit gives the field offset directly.
//!
//! Ignored by default. Needs the game running in a mission, plus
//! `MJOLNIR_PAKS` and `MJOLNIR_EXE`.

use std::collections::HashMap;

use tag_editor_lib::catalog::Catalog;

/// How much of the data section to compare when testing a candidate. The
/// engine rewrites much of a tag in place, so ~45% matching is a hit and
/// unrelated heap scores near zero — 512 bytes separates those decisively.
const PROBE: usize = 512;

/// Bytes of the `UObject` (and each pointer target) to search for pointers.
const WINDOW: usize = 0x400;

fn heapish(v: u64) -> bool {
    (0x1_0000_0000..0x8000_0000_0000).contains(&v) && v % 8 == 0
}

/// A high-entropy window inside the data section, as `(offset within payload,
/// bytes)`.
///
/// Comparing against a zero-heavy stretch is worthless: most of the heap is
/// also zeros, so unrelated memory scores high and every pointer looks like a
/// hit (`ClassPrivate` "matched" at 74% before this). Pick a window that is
/// mostly non-zero and varied — the same rule `blam_live::pick_runs` applies —
/// so unrelated memory scores near zero.
fn probe_window(payload: &[u8], r0: usize, r1: usize) -> Option<(usize, &[u8])> {
    let mut off = r0;
    while off + PROBE <= r1 {
        let w = &payload[off..off + PROBE];
        let zeros = w.iter().filter(|b| **b == 0).count();
        let distinct = {
            let mut seen = [false; 256];
            let mut n = 0;
            for b in w {
                if !seen[*b as usize] {
                    seen[*b as usize] = true;
                    n += 1;
                }
            }
            n
        };
        if zeros * 10 <= PROBE && distinct >= 64 {
            return Some((off, w));
        }
        off += 64;
    }
    None
}

/// Fraction of the probe window matching memory at the address the window's
/// own file offset implies. `addr` is where the *data section* is believed to
/// start, so the window sits at `addr + (win_off - r0)`.
fn score(
    p: &blam_live::Process,
    addr: u64,
    win_off: usize,
    r0: usize,
    want: &[u8],
) -> f32 {
    let at = addr + (win_off - r0) as u64;
    let Ok(live) = p.read(at, want.len()) else {
        return 0.0;
    };
    if live.len() < want.len() {
        return 0.0;
    }
    let same = live.iter().zip(want).filter(|(a, b)| a == b).count();
    same as f32 / want.len() as f32
}


/// Spread, high-entropy 48-byte runs from the data section, as
/// `(offset in payload, bytes)`.
///
/// Equivalent to the census's own run picking (which lives on the census
/// branch): a run must be mostly non-zero and varied, so unrelated memory
/// cannot reproduce it. Several such runs at exactly the file's spacing is
/// what identifies a real buffer — whole-section byte matching cannot, because
/// tag data is zero-dominated and any zero-heavy memory scores ~70%.
fn local_runs(payload: &[u8], r0: usize, r1: usize) -> Vec<(usize, Vec<u8>)> {
    const RUN: usize = 48;
    const WANT: usize = 12;
    let mut out = Vec::new();
    if r1 <= r0 || r1 - r0 < RUN * 4 {
        return out;
    }
    let span = (r1 - r0) / WANT;
    for w in 0..WANT {
        let from = r0 + w * span;
        let to = (from + span).min(r1.saturating_sub(RUN));
        let mut off = from;
        while off < to {
            let run = &payload[off..off + RUN];
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
            if zeros <= RUN / 3 && distinct >= 20 {
                out.push((off, run.to_vec()));
                break;
            }
            off += 4;
        }
    }
    out
}

/// The data section's offset and end within a tag payload.
fn data_region(payload: &[u8]) -> Option<(usize, usize)> {
    let tag = blam_tag::TagFile::parse(payload, Some(payload.len())).ok()?;
    let d = tag.data()?;
    let start = d.content.as_ptr() as usize - payload.as_ptr() as usize;
    Some((start, start + d.content.len()))
}

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS and MJOLNIR_EXE"]
fn find_buffer_pointer_in_tag_uobjects() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let exe = std::fs::read(std::env::var("MJOLNIR_EXE").expect("set MJOLNIR_EXE")).unwrap();
    let catalog = Catalog::open(&paks, "").expect("catalog opens");

    let p = blam_live::Process::attach().expect("game running");
    let reader = blam_live::objects::Reader::attach(&p, &exe).expect("reader attaches");
    let objects = reader.table.walk(&p).expect("walk");
    eprintln!("walked {} live objects", objects.len());

    // Tag assets under /Game/Tags/, resolved to catalog indices.
    let mut class_name: HashMap<u64, String> = HashMap::new();
    let mut candidates: Vec<(u64, usize, String)> = Vec::new(); // (uobject, tag index, pkg)
    for o in &objects {
        let cname = class_name
            .entry(o.class)
            .or_insert_with(|| reader.name_at(&p, o.class).unwrap_or_default());
        if !cname.ends_with("TagDataAsset") {
            continue;
        }
        let Ok((name, pkg)) = reader.identity(&p, o) else {
            continue;
        };
        if name.starts_with("Default__") || !pkg.starts_with("/Game/Tags/") {
            continue;
        }
        if let Some(idx) = catalog.tag_by_package(&pkg) {
            candidates.push((o.object, idx, pkg));
        }
    }
    eprintln!("{} tag UObjects resolved to catalog tags", candidates.len());
    assert!(!candidates.is_empty(), "no tag UObjects mapped to the catalog");

    // Only data-resident tags can possibly have a live buffer, and they are a
    // ~4% minority; probing a uniform sample would find nothing regardless of
    // whether a pointer exists. A census dump supplies which tags are resident
    // (and their true buffer base, for a second, independent check).
    let resident: HashMap<usize, u64> = match std::env::var("MJOLNIR_RESIDENT") {
        Ok(path) => {
            let rows: Vec<serde_json::Value> =
                serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
            rows.iter()
                .map(|r| {
                    let base = u64::from_str_radix(
                        r["base"].as_str().unwrap().trim_start_matches("0x"),
                        16,
                    )
                    .unwrap();
                    (r["index"].as_u64().unwrap() as usize, base)
                })
                .collect()
        }
        Err(_) => HashMap::new(),
    };
    assert!(
        !resident.is_empty(),
        "set MJOLNIR_RESIDENT to a census dump; a uniform sample cannot answer this"
    );
    let sample: Vec<_> = candidates
        .iter()
        .filter(|(_, idx, _)| resident.contains_key(idx))
        .collect();
    eprintln!(
        "{} of {} census-resident tags also have a UObject; probing those",
        sample.len(),
        resident.len()
    );

    // (offset in UObject, or (o1,o2) one hop) -> how many tags hit there
    let mut direct_hits: HashMap<usize, usize> = HashMap::new();
    let mut hop_hits: HashMap<(usize, usize), usize> = HashMap::new();
    let mut tags_with_any = 0usize;
    let mut probed = 0usize;
    let mut control_max: f32 = 0.0;
    let mut truth_ok = 0usize;
    let mut examples: Vec<String> = Vec::new();

    for (uobj, idx, pkg) in &sample {
        let Ok(payload) = catalog.read_tag(*idx) else { continue };
        let Some((r0, r1)) = data_region(&payload) else { continue };
        if r1 - r0 < PROBE {
            continue;
        }
        let runs = local_runs(&payload, r0, r1);
        if runs.len() < 4 {
            continue;
        }
        probed += 1;
        // How many of the tag's unique runs appear at their exact offsets.
        let agree = |base: u64| -> usize {
            runs.iter()
                .filter(|(off, bytes)| {
                    matches!(p.read(base + *off as u64, bytes.len()), Ok(got) if got == *bytes)
                })
                .count()
        };
        let true_base = resident[idx];
        let Ok(ubuf) = p.read(*uobj, WINDOW) else { continue };
        // Sanity: the census's own base must satisfy the run test, or the
        // ground truth is stale (the game restarted) and nothing below means
        // anything.
        if agree(true_base) >= 2 {
            truth_ok += 1;
        }
        let mut hit = false;
        for off in (0..ubuf.len().saturating_sub(7)).step_by(8) {
            let v = u64::from_le_bytes(ubuf[off..off + 8].try_into().unwrap());
            if !heapish(v) {
                continue;
            }
            // Does the pointer land on the data section itself?
            // A pointer to the data section means payload byte 0 maps to
            // v - r0; count the runs that land where the file says they should.
            let s = agree(v - r0 as u64) as f32;
            control_max = control_max.max(agree(v - r0 as u64 + 0x10000) as f32);
            if s >= 2.0 {
                *direct_hits.entry(off).or_default() += 1;
                hit = true;
                if examples.len() < 8 {
                    examples.push(format!(
                        "  direct +{off:#x} -> {v:#x}: {} runs agree  {pkg}",
                        s
                    ));
                }
                continue;
            }
            // Or is it a descriptor holding the buffer pointer?
            let Ok(inner) = p.read(v, WINDOW) else { continue };
            for io in (0..inner.len().saturating_sub(7)).step_by(8) {
                let iv = u64::from_le_bytes(inner[io..io + 8].try_into().unwrap());
                if !heapish(iv) {
                    continue;
                }
                let s2 = agree(iv - r0 as u64) as f32;
                if s2 >= 2.0 {
                    *hop_hits.entry((off, io)).or_default() += 1;
                    hit = true;
                    if examples.len() < 8 {
                        examples.push(format!(
                            "  hop +{off:#x} -> +{io:#x} -> {iv:#x}: {} runs agree  {pkg}",
                            s2
                        ));
                    }
                }
            }
        }
        if hit {
            tags_with_any += 1;
        }
    }

    eprintln!("{tags_with_any}/{probed} probed tags reached their data section (of {} sampled)", sample.len());
    eprintln!("GROUND TRUTH: {truth_ok}/{probed} probed tags verified at the census base (0 here means the dump is stale — rerun the census)");
    eprintln!("CONTROL: most runs agreeing at a deliberately wrong address = {control_max} (must be 0-1 for hits to mean anything)");
    for e in &examples {
        eprintln!("{e}");
    }
    let mut d: Vec<_> = direct_hits.into_iter().collect();
    d.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
    for (off, n) in d.iter().take(10) {
        eprintln!("DIRECT offset +{off:#x}: {n} tags");
    }
    let mut h: Vec<_> = hop_hits.into_iter().collect();
    h.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
    for ((o1, o2), n) in h.iter().take(10) {
        eprintln!("HOP +{o1:#x} -> +{o2:#x}: {n} tags");
    }
}
