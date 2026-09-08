//! The object-table probe against the running game: the exact code path
//! `live_probe` and the census's first phase use. Ignored; needs the game in a
//! mission plus `MJOLNIR_PAKS`.

use tag_editor_lib::{catalog::Catalog, present};

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS"]
fn probe_reads_level_and_present_set() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let process = blam_live::Process::attach().expect("game running");

    // Cold: resolve from the image.
    let t0 = std::time::Instant::now();
    let (reader, rvas) = present::attach(&process, catalog.paks(), None).expect("cold attach");
    let cold = t0.elapsed();
    let p = present::read(&process, &reader, &catalog).expect("read");
    let read = t0.elapsed() - cold;
    eprintln!(
        "cold attach {cold:.1?}, read {read:.1?}: level {:?}, {} present, {} objects",
        p.level,
        p.tags.len(),
        p.objects
    );

    // Warm: from cached RVAs, no image read.
    let t1 = std::time::Instant::now();
    let (reader2, rvas2) = present::attach(&process, catalog.paks(), Some(rvas)).expect("warm");
    eprintln!("warm attach {:.1?}", t1.elapsed());
    assert_eq!(rvas, rvas2, "cached RVAs must round-trip");
    assert_eq!(reader2.table.num_elements, reader.table.num_elements);

    // Stale RVAs must be refused, then recovered from the image.
    let t2 = std::time::Instant::now();
    let (_, rvas3) =
        present::attach(&process, catalog.paks(), Some((rvas.0 + 0x1000, rvas.1))).expect("recover");
    eprintln!("stale-then-recover {:.1?}", t2.elapsed());
    assert_eq!(rvas3, rvas, "stale RVAs must be re-resolved, not trusted");

    let level = p.level.expect("a mission has exactly one loaded scenario");
    assert!(level.to_ascii_lowercase().contains("a30"), "expected a30, got {level}");
    assert!(p.tags.len() > 1000, "present set implausibly small: {}", p.tags.len());
}
