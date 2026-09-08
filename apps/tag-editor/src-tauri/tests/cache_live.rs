//! The production loader-cache path against the running game: the exact
//! code `run_census` uses, checked against a census dump.
//!
//! Ignored; needs the game in a mission, `MJOLNIR_PAKS` and `MJOLNIR_RESIDENT`.

use std::collections::HashMap;

use tag_editor_lib::{catalog::Catalog, tagcache};

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS and MJOLNIR_RESIDENT"]
fn loader_cache_resolves_exact_bases() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let process = blam_live::Process::attach().expect("game running");

    // Census ground truth: catalog index -> base.
    let rows: Vec<serde_json::Value> = serde_json::from_str(
        &std::fs::read_to_string(std::env::var("MJOLNIR_RESIDENT").unwrap()).unwrap(),
    )
    .unwrap();
    let truth: HashMap<usize, u64> = rows
        .iter()
        .map(|r| {
            (
                r["index"].as_u64().unwrap() as usize,
                u64::from_str_radix(r["base"].as_str().unwrap().trim_start_matches("0x"), 16)
                    .unwrap(),
            )
        })
        .collect();

    // Cold: discover roots from the image.
    let t0 = std::time::Instant::now();
    let (roots, rvas) = tagcache::roots(&process, catalog.paks(), &[]).expect("roots");
    let cold = t0.elapsed();
    eprintln!("cold root discovery: {} roots in {cold:.1?}; rvas {:x?}", roots.len(), rvas);

    // Warm: cached RVAs must revalidate without touching the image.
    let t1 = std::time::Instant::now();
    let (roots2, rvas2) = tagcache::roots(&process, catalog.paks(), &rvas).expect("warm");
    eprintln!("warm revalidation: {} roots in {:.1?}", roots2.len(), t1.elapsed());
    assert!(!roots2.is_empty(), "cached roots must revalidate");
    assert!(
        rvas2.iter().all(|r| rvas.contains(r)),
        "warm revalidation must not invent roots: {rvas2:x?} vs {rvas:x?}"
    );

    // A stale RVA must be dropped, not trusted.
    let mut stale = rvas.clone();
    stale[0] += 0x1000;
    let (roots3, _) = tagcache::roots(&process, catalog.paks(), &stale).expect("stale path");
    assert!(
        !roots3.iter().any(|r| r.static_rva == stale[0]),
        "a stale RVA must not survive revalidation"
    );

    // Resolve and score.
    let t2 = std::time::Instant::now();
    let hits = tagcache::resolve(&process, &catalog, &roots);
    eprintln!(
        "resolve: {} nodes walked, {} catalog tags with a cached buffer, in {:.1?}",
        hits.nodes,
        hits.bases.len(),
        t2.elapsed()
    );
    let mut exact = 0usize;
    let mut wrong = 0usize;
    for (i, base) in &hits.bases {
        match truth.get(i) {
            Some(b) if b == base => exact += 1,
            Some(_) => wrong += 1,
            None => {}
        }
    }
    eprintln!(
        "against the census: {exact} exact, {wrong} wrong (of {} resident); {} cache hits the census did not fingerprint",
        truth.len(),
        hits.bases.len() - exact - wrong
    );
    assert_eq!(wrong, 0, "the loader cache must never disagree with the census");
    assert!(exact > 0, "expected at least some cache hits to match the census");
}
