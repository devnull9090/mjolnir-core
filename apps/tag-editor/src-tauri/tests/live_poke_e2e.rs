//! The editor's own poke path, end to end against the running game: build
//! the job exactly as `build_live_job` does and push it through
//! `live::Live::poke`. A field inside a block element — the case the plain
//! locator got wrong — is the default.
//!
//! Ignored: needs the game in a mission with the weapon in play and
//! `MJOLNIR_PAKS`. `MJOLNIR_TAG`, `MJOLNIR_FIELD` and `MJOLNIR_VALUE` pick
//! what to write (default: the assault rifle's zoom magnification, 8).

use tag_editor_lib::{catalog::Catalog, live};

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS"]
fn poke_through_the_editor_path() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let want = std::env::var("MJOLNIR_TAG").unwrap_or_else(|_| "assault_rifle/assault_rifle".into());
    let path = std::env::var("MJOLNIR_FIELD").unwrap_or_else(|_| "zoom levels[0].magnification".into());
    let value = std::env::var("MJOLNIR_VALUE").unwrap_or_else(|_| "8".into());
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let index = catalog
        .tags
        .iter()
        .position(|e| e.group == "weapon" && e.short.contains(&want))
        .expect("weapon tag in catalog");
    let entry = catalog.entry(index).unwrap();
    let file = catalog.read_tag(index).expect("read tag");

    let job = {
        let tag = blam_tag::TagFile::parse(&file, Some(file.len())).unwrap();
        let layout = tag.layout().unwrap();
        let block = tag.read_data(&layout).unwrap();
        let route = blam_tag::patch::route(&layout, &file, &block, &path).expect("route");
        let target = &route.target;
        let parsed = blam_tag::value::parse(&layout, &target.field, &value).expect("value");
        let (patched, _) = blam_tag::patch::set(&layout, &file, &block, &path, &parsed).expect("set");
        let data = tag.data().unwrap();
        let start = data.content.as_ptr() as usize - file.as_ptr() as usize;
        let root_off = block.elements.as_ptr() as usize - file.as_ptr() as usize;
        let root = root_off..root_off + block.element_size as usize;
        let stable = blam_tag::view::scalar_mask(&layout, &block, &file);
        let blocks: Vec<(blam_live::Hop, u32)> = blam_tag::patch::root_blocks(&layout, &file, &block)
            .iter()
            .filter(|(_, n)| *n > 0)
            .map(|(h, n)| (live::hop(h), *n))
            .collect();
        let headers: Vec<usize> = blocks.iter().map(|(h, _)| h.header).collect();
        let hops: Vec<blam_live::Hop> = route.hops.iter().map(live::hop).collect();
        let span = target.file_offset..target.file_offset + target.size;
        let bytes = patched[span.clone()].to_vec();
        eprintln!(
            "{}: {path} at {:#x} ({} B), {} hop(s), {} root blocks, root {:#x?}",
            entry.short,
            span.start,
            span.len(),
            hops.len(),
            blocks.len(),
            root
        );
        live::Job {
            key: (entry.group.clone(), entry.short.clone()),
            payload: file.clone(),
            region: start..start + data.content.len(),
            root,
            stable,
            headers,
            blocks,
            hops,
            span,
            bytes,
        }
    };

    let live = live::Live::default();
    let t0 = std::time::Instant::now();
    let poked = live.poke(&job).expect("poke");
    eprintln!(
        "poked in {:.1?}: base {} address {} was {} now {} (scanned: {})",
        t0.elapsed(),
        poked.base,
        poked.address,
        poked.was,
        poked.now,
        poked.scanned
    );
    // A second poke of the same tag must not scan again.
    let t1 = std::time::Instant::now();
    let again = live.poke(&job).expect("poke again");
    eprintln!("again in {:.1?}: scanned {}", t1.elapsed(), again.scanned);
    assert!(!again.scanned, "the base is cached after the first poke");
    assert_eq!(again.address, poked.address);
}
