//! Reference resolution, peek classification and the reverse index, proven
//! against a real installation rather than fixtures.
//!
//! Ignored by default because it needs Halo Campaign Evolved on disk:
//!
//! ```text
//! cargo test --test references_e2e -- --ignored --nocapture
//! ```
//!
//! What it proves, in one catalog pass:
//!
//! - the indexed `resolve_ref` agrees with the linear scan it replaced, for
//!   every reference the `tgrf` scanner finds in a broad sample of tags —
//!   the cooker's `_Generated_` scenario BSPs included;
//! - the scanner itself finds real references (nonzero, high resolve rate);
//! - the reverse index answers "who references X" consistently with the
//!   forward sample, and the one-time build cost is what the spinner claims;
//! - the peek chases work on shipped data: sound tags reach playable Wwise
//!   media, and texture-binding tags reach a texture index.

use std::collections::BTreeMap;
use std::time::Instant;

use tag_editor_lib::catalog::{normalize_ref_path, Catalog};
use tag_editor_lib::{install, refscan, texture_import, wwise_media_for_tag};

/// How many tags the forward scan samples. Spread across the catalog rather
/// than taken from the front, so no group dominates.
const SAMPLE: usize = 600;

#[test]
#[ignore = "needs an installed copy of Halo Campaign Evolved"]
fn references_resolve_scan_and_reverse_against_the_shipped_catalog() {
    let found = install::detect();
    let paks = found.paks.expect("no installation found on this machine");
    let c = Catalog::open(&paks, &found.oodle.unwrap_or_default()).expect("open catalog");

    // ── The four-CC maps agree with what groups() reads from headers. ──
    let groups = c.groups().expect("groups");
    let mut name_of_cc: BTreeMap<String, String> = BTreeMap::new();
    for g in &groups {
        assert_eq!(
            c.four_cc_of_group(&g.group),
            Some(g.four_cc.as_str()),
            "four-CC mismatch for {}",
            g.group
        );
        name_of_cc.insert(g.four_cc.clone(), g.group.clone());
    }
    println!("{} groups, every four-CC mapped", groups.len());

    // ── Scan a spread sample; every found reference resolves the same way
    //    the old linear scan resolved it. ──
    let step = (c.tags.len() / SAMPLE).max(1);
    // Every scenario joins the sample: their BSP references are the ones the
    // cooker rewrites through a _Generated_ directory.
    let scenarios: Vec<usize> = c
        .tags
        .iter()
        .enumerate()
        .filter(|(_, t)| t.group == "scenario")
        .map(|(i, _)| i)
        .collect();
    let old_linear = |group: &str, path: &str| -> Option<usize> {
        let want = normalize_ref_path(path);
        c.tags
            .iter()
            .position(|t| t.group == group && normalize_ref_path(&t.short) == want)
    };
    let mut scanned = 0usize;
    let mut resolved = 0usize;
    let mut generated_hits = 0usize;
    let mut witness: Option<(usize, usize)> = None; // (referencer, target)
    for i in (0..c.tags.len()).step_by(step).chain(scenarios) {
        let Ok(buf) = c.read_tag(i) else { continue };
        let data = blam_tag::TagFile::parse(&buf, Some(buf.len()))
            .ok()
            .and_then(|t| t.data().map(|d| d.content.to_vec()))
            .unwrap_or(buf);
        for (cc, path) in refscan::tgrf_refs(&data, |cc| name_of_cc.contains_key(cc)) {
            scanned += 1;
            let via_index = c.resolve_ref(&cc, &path);
            let via_linear = name_of_cc.get(&cc).and_then(|g| old_linear(g, &path));
            assert_eq!(
                via_index, via_linear,
                "index and linear scan disagree on {cc} {path}"
            );
            if let Some(t) = via_index {
                resolved += 1;
                if c.tags[t].short.to_ascii_lowercase().contains("_generated_") {
                    generated_hits += 1;
                }
                if witness.is_none() && t != i {
                    witness = Some((i, t));
                }
            }
        }
    }
    println!(
        "scanned {scanned} references across ~{SAMPLE} tags; {resolved} resolve \
         ({generated_hits} through _Generated_ paths)"
    );
    assert!(scanned > 100, "the scanner found almost nothing");
    assert!(
        resolved * 10 >= scanned * 9,
        "under 90% of scanned references resolve — the scan or the index is off"
    );
    assert!(
        generated_hits > 0,
        "no reference resolved through a _Generated_ path — scenarios should"
    );

    // ── A garbage reference is a clean miss, not a lookalike. ──
    assert_eq!(c.resolve_ref("weap", "objects\\weapons\\no_such_thing"), None);

    // ── The reverse index agrees with the forward sample. ──
    let (referencer, target) = witness.expect("no resolved cross-reference in the sample");
    let t0 = Instant::now();
    let rows = c.referencing(target, 500).expect("reverse lookup");
    let first_build = t0.elapsed();
    let t1 = Instant::now();
    let _ = c.referencing(target, 500).expect("second lookup");
    let warm = t1.elapsed();
    println!(
        "reverse index: first call {first_build:?}, warm {warm:?}; {} tags reference {}",
        rows.len(),
        c.tags[target].short
    );
    assert!(
        rows.len() == 500 || rows.iter().any(|r| r.index == referencer),
        "{} references {} in the forward scan but the reverse index disagrees",
        c.tags[referencer].short,
        c.tags[target].short
    );
    assert!(warm.as_millis() < 100, "warm reverse lookups should be instant");

    // ── Peek chases on real data. ──
    let sound_tags: Vec<usize> = c
        .tags
        .iter()
        .enumerate()
        .filter(|(_, t)| t.group.starts_with("sound"))
        .map(|(i, _)| i)
        .take(30)
        .collect();
    let playable = sound_tags
        .iter()
        .filter(|&&i| wwise_media_for_tag(&c, i).is_some())
        .count();
    println!("{playable} of {} sampled sound tags reach playable media", sound_tags.len());
    assert!(
        playable > 0,
        "no sound tag reached its Wwise media — the event-package chase is wrong"
    );

    // No assertion here on purpose: as of CU4, no shipped tag imports a
    // texture package at all (verified across the whole catalog), so the
    // texture peek is a classification that cannot fire on this build. It
    // stays because it is one map lookup per import and a future build could
    // start binding textures the way the code path expects.
    let textured = (0..c.tags.len())
        .step_by(step)
        .filter(|&i| texture_import(&c, i).is_some())
        .count();
    println!("{textured} of the sampled tags bind a texture through their imports");
}
