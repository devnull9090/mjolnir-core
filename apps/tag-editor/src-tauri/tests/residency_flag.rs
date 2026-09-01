//! Is there a field on a tag asset's `UObject` that says "my data is
//! resident"?
//!
//! The object table lists ~9,100 tag assets; the census finds ~370 with
//! resident data. If some field separates the two sets, the sweep can carry
//! only the resident tags' fingerprints (a much smaller matcher) and the UI
//! can mark "live-editable" instantly — without ever finding the buffer.
//!
//! Method: read a window of every tag `UObject`, split by the census's
//! verdict, and for every aligned u32 field and every bit look for one whose
//! value distribution differs sharply between the two sets. Layout differs by
//! class, so scoring is done per class and a candidate must hold across
//! classes. Anything that survives is then used to *predict* residency for
//! all present tags and scored against the census as precision/recall.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS`, and `MJOLNIR_RESIDENT`
//! (a census dump from this same game session).

use std::collections::{HashMap, HashSet};

use tag_editor_lib::{catalog::Catalog, present};

const WINDOW: usize = 0x1000;

struct Sample {
    class: u64,
    is_res: bool,
    bytes: Vec<u8>,
}

fn u32_at(s: &Sample, off: usize) -> u32 {
    u32::from_le_bytes(s.bytes[off..off + 4].try_into().unwrap())
}

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS and MJOLNIR_RESIDENT"]
fn find_residency_flag() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let resident_path = std::env::var("MJOLNIR_RESIDENT").expect("set MJOLNIR_RESIDENT");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let p = blam_live::Process::attach().expect("game running");
    let (reader, _) = present::attach(&p, catalog.paks(), None).expect("reader");

    let rows: Vec<serde_json::Value> =
        serde_json::from_str(&std::fs::read_to_string(&resident_path).unwrap()).unwrap();
    let resident: HashSet<usize> = rows
        .iter()
        .map(|r| r["index"].as_u64().unwrap() as usize)
        .collect();

    // Every tag asset with its UObject, class and residency verdict.
    let objects = reader.table.walk(&p).expect("walk");
    let mut class_name: HashMap<u64, String> = HashMap::new();
    let mut samples: Vec<Sample> = Vec::new();
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
        let Some(index) = catalog.tag_by_package(&pkg) else {
            continue;
        };
        let Ok(bytes) = p.read(o.object, WINDOW) else {
            continue;
        };
        if bytes.len() < WINDOW {
            continue;
        }
        samples.push(Sample {
            class: o.class,
            is_res: resident.contains(&index),
            bytes,
        });
    }
    let n_res = samples.iter().filter(|s| s.is_res).count();
    eprintln!(
        "{} tag objects read, {} census-resident, {} not",
        samples.len(),
        n_res,
        samples.len() - n_res
    );
    assert!(
        n_res >= 50,
        "too few resident samples; is the dump from this game session?"
    );

    // --- ObjectFlags (+0x8) straight up: the engine's own load-state bits.
    for (label, want) in [("resident", true), ("not resident", false)] {
        let mut hist: HashMap<u32, usize> = HashMap::new();
        for s in samples.iter().filter(|s| s.is_res == want) {
            *hist.entry(u32_at(s, 8)).or_default() += 1;
        }
        let mut v: Vec<_> = hist.into_iter().collect();
        v.sort_by_key(|(_, n)| std::cmp::Reverse(*n));
        eprintln!("ObjectFlags (+0x8), {label}:");
        for (f, n) in v.iter().take(5) {
            eprintln!("  {f:#010x}: {n}");
        }
    }

    // --- Per-class, per-field separation. For each u32 offset: fraction of
    // non-zero values in each set. A flag shows as ~1.0 vs ~0.0 (either way).
    // Only classes with both kinds of sample can testify.
    let mut by_class: HashMap<u64, Vec<&Sample>> = HashMap::new();
    for s in &samples {
        by_class.entry(s.class).or_default().push(s);
    }
    // offset -> (classes testifying, classes with separation >= 0.9, sum sep)
    let mut field_score: HashMap<usize, (usize, usize, f32)> = HashMap::new();
    let mut bit_score: HashMap<(usize, u8), (usize, usize, f32)> = HashMap::new();
    let mut testifying = 0usize;
    for list in by_class.values() {
        let res: Vec<&Sample> = list.iter().copied().filter(|s| s.is_res).collect();
        let non: Vec<&Sample> = list.iter().copied().filter(|s| !s.is_res).collect();
        if res.len() < 2 || non.len() < 2 {
            continue;
        }
        testifying += 1;
        for off in (0..WINDOW - 3).step_by(4) {
            let nz = |set: &[&Sample]| {
                set.iter().filter(|s| u32_at(s, off) != 0).count() as f32 / set.len() as f32
            };
            let sep = (nz(&res) - nz(&non)).abs();
            let e = field_score.entry(off).or_insert((0, 0, 0.0));
            e.0 += 1;
            if sep >= 0.9 {
                e.1 += 1;
            }
            e.2 += sep;
        }
        for off in 0..WINDOW {
            for bit in 0..8u8 {
                let set = |set: &[&Sample]| {
                    set.iter().filter(|s| s.bytes[off] & (1 << bit) != 0).count() as f32
                        / set.len() as f32
                };
                let sep = (set(&res) - set(&non)).abs();
                if sep < 0.5 {
                    continue;
                }
                let e = bit_score.entry((off, bit)).or_insert((0, 0, 0.0));
                e.0 += 1;
                if sep >= 0.9 {
                    e.1 += 1;
                }
                e.2 += sep;
            }
        }
    }
    eprintln!("{testifying} classes have both resident and non-resident samples");

    let mut fields: Vec<(usize, (usize, usize, f32))> = field_score.into_iter().collect();
    fields.sort_by(|a, b| b.1 .1.cmp(&a.1 .1).then(b.1 .2.total_cmp(&a.1 .2)));
    eprintln!("top u32 fields by classes with >=0.9 separation (of {testifying}):");
    for (off, (n, strong, sum)) in fields.iter().take(12) {
        eprintln!(
            "  +{off:#05x}: strong in {strong}/{n}, mean sep {:.2}",
            sum / *n as f32
        );
    }
    let mut bits: Vec<((usize, u8), (usize, usize, f32))> = bit_score.into_iter().collect();
    bits.sort_by(|a, b| b.1 .1.cmp(&a.1 .1).then(b.1 .2.total_cmp(&a.1 .2)));
    eprintln!("top bits by classes with >=0.9 separation:");
    for ((off, bit), (n, strong, sum)) in bits.iter().take(12) {
        eprintln!(
            "  +{off:#05x} bit {bit}: strong in {strong}/{n}, mean sep {:.2}",
            sum / *n as f32
        );
    }

    // --- Predict with the best field and best bit; score against the census.
    let predict = |name: &str, is_set: &dyn Fn(&Sample) -> bool| {
        let (mut tp, mut fp, mut fn_) = (0usize, 0usize, 0usize);
        for s in &samples {
            match (is_set(s), s.is_res) {
                (true, true) => tp += 1,
                (true, false) => fp += 1,
                (false, true) => fn_ += 1,
                _ => {}
            }
        }
        let prec = tp as f32 / (tp + fp).max(1) as f32;
        let rec = tp as f32 / (tp + fn_).max(1) as f32;
        eprintln!(
            "PREDICT {name}: predicted {} resident; precision {:.0}% recall {:.0}% (tp {tp} fp {fp} fn {fn_})",
            tp + fp,
            prec * 100.0,
            rec * 100.0
        );
    };
    if let Some((off, _)) = fields.first() {
        let off = *off;
        let res_nz = samples
            .iter()
            .filter(|s| s.is_res && u32_at(s, off) != 0)
            .count() as f32
            / n_res as f32;
        let want_nz = res_nz >= 0.5;
        predict(
            &format!("u32 +{off:#05x} {}", if want_nz { "non-zero" } else { "zero" }),
            &|s| (u32_at(s, off) != 0) == want_nz,
        );
    }
    if let Some(((off, bit), _)) = bits.first() {
        let (off, bit) = (*off, *bit);
        let res_set = samples
            .iter()
            .filter(|s| s.is_res && s.bytes[off] & (1 << bit) != 0)
            .count() as f32
            / n_res as f32;
        let want = res_set >= 0.5;
        predict(
            &format!("bit +{off:#05x}.{bit} {}", if want { "set" } else { "clear" }),
            &|s| (s.bytes[off] & (1 << bit) != 0) == want,
        );
    }
}
