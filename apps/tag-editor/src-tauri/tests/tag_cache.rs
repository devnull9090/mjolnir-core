//! Hunting the Blam tag cache: the structure that owns every loaded tag's
//! data buffer.
//!
//! The census finds buffers by fingerprint; the object table (`present.rs`)
//! finds identities but not buffers. Between them sits the thing the engine
//! itself uses to get from a tag to its bytes. An earlier pointer scan showed
//! buffer addresses stored in 32-byte-aligned records at 32-byte multiples
//! apart — the signature of one contiguous array, one record per tag, seen
//! only at the ~4 % of entries whose pointer was a resident buffer. If that
//! array can be found and its root reached from a static global, poke becomes
//! a pointer chase and the sweep retires.
//!
//! Phase A confirms the array and bounds it. Phase B decodes the record and
//! maps records to catalog tags. Phase C (`tag_cache_root`) walks pointers up
//! from the array to whatever static address holds it.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, and `MJOLNIR_RESIDENT`
//! (a census dump from this same game session).

use std::collections::{HashMap, HashSet};

use tag_editor_lib::catalog::Catalog;

struct Resident {
    index: usize,
    base: u64,
}

fn load_resident() -> Vec<Resident> {
    let path = std::env::var("MJOLNIR_RESIDENT").expect("set MJOLNIR_RESIDENT");
    let rows: Vec<serde_json::Value> =
        serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    rows.iter()
        .map(|r| Resident {
            index: r["index"].as_u64().unwrap() as usize,
            base: u64::from_str_radix(r["base"].as_str().unwrap().trim_start_matches("0x"), 16)
                .unwrap(),
        })
        .collect()
}

/// Every aligned 8-byte slot in writable memory whose value is in `targets`,
/// as `(holder address, value)`.
fn pointer_scan(p: &blam_live::Process, targets: &HashSet<u64>) -> Vec<(u64, u64)> {
    let (min, max) = (
        *targets.iter().min().unwrap(),
        *targets.iter().max().unwrap(),
    );
    let mut out = Vec::new();
    let mut window = vec![0u8; 64 * 1024 * 1024];
    for region in p.writable_regions().expect("regions") {
        let mut at = 0u64;
        while at < region.size {
            let want = (window.len() as u64).min(region.size - at) as usize;
            if let Ok(got) = p.read_into(region.base + at, &mut window[..want]) {
                for off in (0..got.saturating_sub(7)).step_by(8) {
                    let v = u64::from_le_bytes(window[off..off + 8].try_into().unwrap());
                    if v >= min && v <= max && targets.contains(&v) {
                        out.push((region.base + at + off as u64, v));
                    }
                }
            }
            at += window.len() as u64;
        }
    }
    out.sort_unstable();
    out
}

fn u64_at(b: &[u8], o: usize) -> u64 {
    u64::from_le_bytes(b[o..o + 8].try_into().unwrap())
}
fn u32_at(b: &[u8], o: usize) -> u32 {
    u32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

const STRIDE: u64 = 32;

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS and MJOLNIR_RESIDENT"]
fn tag_cache_array() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let p = blam_live::Process::attach().expect("game running");
    let resident = load_resident();
    let base_to_index: HashMap<u64, usize> =
        resident.iter().map(|r| (r.base, r.index)).collect();
    let targets: HashSet<u64> = base_to_index.keys().copied().collect();
    eprintln!("{} resident bases as targets", targets.len());

    // ---- Phase A: find the holders and the array they sit in.
    let holders = pointer_scan(&p, &targets);
    let covered: HashSet<u64> = holders.iter().map(|(_, v)| *v).collect();
    eprintln!(
        "{} holders covering {} of {} resident tags",
        holders.len(),
        covered.len(),
        targets.len()
    );
    let mut align: HashMap<u64, usize> = HashMap::new();
    for (a, _) in &holders {
        *align.entry(a % STRIDE).or_default() += 1;
    }
    let mut align: Vec<_> = align.into_iter().collect();
    align.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
    eprintln!("holder address mod {STRIDE}: {align:?}");

    // Densest 1 MB: where the array lives.
    let mut by_mb: HashMap<u64, Vec<(u64, u64)>> = HashMap::new();
    for h in &holders {
        by_mb.entry(h.0 >> 20).or_default().push(*h);
    }
    let mut mbs: Vec<_> = by_mb.iter().collect();
    mbs.sort_by_key(|(_, v)| std::cmp::Reverse(v.len()));
    for (mb, v) in mbs.iter().take(6) {
        eprintln!("  region {:#x}xxxxx: {} holders", *mb, v.len());
    }
    let (_, dense) = mbs[0];
    let mut dense: Vec<(u64, u64)> = (*dense).clone();
    dense.sort_unstable();
    let aligned: Vec<(u64, u64)> = dense.iter().copied().filter(|(a, _)| a % STRIDE == 0).collect();
    eprintln!(
        "densest region: {} holders, {} at stride alignment, span {:#x}..{:#x} ({} KB)",
        dense.len(),
        aligned.len(),
        dense[0].0,
        dense[dense.len() - 1].0,
        (dense[dense.len() - 1].0 - dense[0].0) >> 10
    );
    let stride_ok = aligned
        .windows(2)
        .filter(|w| (w[1].0 - w[0].0) % STRIDE == 0)
        .count();
    eprintln!("  consecutive aligned holders {STRIDE}-multiple apart: {stride_ok}/{}", aligned.len().saturating_sub(1));

    // Show raw records around three holders so the layout can be read.
    for (a, v) in aligned.iter().take(3) {
        let buf = p.read(a - 64, 160).unwrap_or_default();
        eprintln!("  around holder {a:#x} (base {v:#x}, tag {}):", base_to_index[v]);
        for (i, chunk) in buf.chunks(32).enumerate() {
            let words: Vec<String> = chunk.chunks(8).map(|c| format!("{:016x}", u64_at(c, 0))).collect();
            let mark = if (i as u64) * 32 == 64 { " <- holder" } else { "" };
            eprintln!("    {:+#06x}: {}{mark}", (i as i64) * 32 - 64, words.join(" "));
        }
    }

    // ---- Bound the array: walk outward from the holders in 32-byte steps
    // while records keep the shape {ptr, u32, u32, ...}. A record is "valid"
    // if its pointer is null or looks like a heap address. Stop at the first
    // run of 16 invalid records.
    let heapish = |v: u64| v == 0 || ((0x1_0000_0000..0x8000_0000_0000).contains(&v) && v % 8 == 0);
    let first = aligned[0].0;
    let last = aligned[aligned.len() - 1].0;
    let valid_at = |addr: u64| -> bool {
        p.read(addr, 32).map(|b| b.len() == 32 && heapish(u64_at(&b, 0))).unwrap_or(false)
    };
    let mut lo = first;
    let mut bad = 0;
    while bad < 16 {
        let cand = lo - STRIDE;
        if valid_at(cand) {
            lo = cand;
            bad = 0;
        } else {
            bad += 1;
            lo = cand; // keep walking through a short gap
        }
    }
    lo += STRIDE * 16; // back off the failed run
    let mut hi = last;
    bad = 0;
    while bad < 16 {
        let cand = hi + STRIDE;
        if valid_at(cand) {
            hi = cand;
            bad = 0;
        } else {
            bad += 1;
            hi = cand;
        }
    }
    hi -= STRIDE * 16;
    let count = ((hi - lo) / STRIDE + 1) as usize;
    eprintln!("array bounds by shape-walk: {lo:#x}..{hi:#x}, {count} records");

    // ---- Phase B: read the whole array and decode.
    let bytes = p.read(lo, (hi - lo + STRIDE) as usize).expect("read array");
    let mut nonnull = 0usize;
    let mut is_resident_base = 0usize;
    let mut f2_hist: HashMap<u32, usize> = HashMap::new();
    let mut pos_of_index: Vec<(usize, usize)> = Vec::new(); // (record pos, tag index)
    let mut unknown_ptrs: Vec<u64> = Vec::new();
    for i in 0..count {
        let r = &bytes[i * 32..i * 32 + 32];
        let ptr = u64_at(r, 0);
        let f1 = u32_at(r, 8);
        let f2 = u32_at(r, 12);
        if ptr != 0 {
            nonnull += 1;
            if let Some(&idx) = base_to_index.get(&ptr) {
                is_resident_base += 1;
                pos_of_index.push((i, idx));
            } else if unknown_ptrs.len() < 5 {
                unknown_ptrs.push(ptr);
            }
        }
        *f2_hist.entry(f2).or_default() += 1;
        let _ = f1;
    }
    eprintln!(
        "records: {count}; non-null ptr {nonnull}; of which a resident base {is_resident_base}"
    );
    let mut f2: Vec<_> = f2_hist.into_iter().collect();
    f2.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
    eprintln!("  +0xC (u32) histogram: {:?}", &f2[..f2.len().min(6)]);
    eprintln!("  sample non-null ptrs that are NOT a resident base: {unknown_ptrs:x?}");

    // Does record position map to catalog index, or to something in the record?
    let mut pos_eq_index = 0usize;
    for (pos, idx) in &pos_of_index {
        if pos == idx {
            pos_eq_index += 1;
        }
    }
    eprintln!(
        "  record position == catalog index for {pos_eq_index}/{} matched records",
        pos_of_index.len()
    );
    // Is the order the catalog's order (monotone)?
    let mono = pos_of_index.windows(2).filter(|w| w[1].1 > w[0].1).count();
    eprintln!(
        "  tag index monotone with position for {mono}/{} consecutive pairs",
        pos_of_index.len().saturating_sub(1)
    );
    // Print a few (pos, index, short) to eyeball the ordering.
    for (pos, idx) in pos_of_index.iter().take(8) {
        let short = catalog.entry(*idx).map(|e| e.short.as_str()).unwrap_or("?");
        eprintln!("    record {pos:5} -> tag {idx:5} {short}");
    }
    // The trailing 16 bytes: any field that equals the tag index, or is
    // constant, or looks like a small id?
    let mut q2_eq_idx = 0usize;
    let mut q3_eq_idx = 0usize;
    for (pos, idx) in &pos_of_index {
        let r = &bytes[pos * 32..pos * 32 + 32];
        let (q2, q3) = (u64_at(r, 16), u64_at(r, 24));
        if q2 as usize == *idx || (q2 & 0xffff_ffff) as usize == *idx {
            q2_eq_idx += 1;
        }
        if q3 as usize == *idx || (q3 & 0xffff_ffff) as usize == *idx {
            q3_eq_idx += 1;
        }
    }
    eprintln!("  +0x10 == tag index: {q2_eq_idx}; +0x18 == tag index: {q3_eq_idx}");

    // Persist for phase C.
    let out = std::env::var("MJOLNIR_CACHE_OUT").unwrap_or_default();
    if !out.is_empty() {
        std::fs::write(
            &out,
            serde_json::to_string_pretty(&serde_json::json!({
                "array_lo": format!("{lo:#x}"),
                "array_hi": format!("{hi:#x}"),
                "records": count,
            }))
            .unwrap(),
        )
        .unwrap();
        eprintln!("wrote {out}");
    }
}
