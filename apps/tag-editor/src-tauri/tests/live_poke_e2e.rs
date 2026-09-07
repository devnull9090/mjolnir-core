//! The editor's own poke path, end to end against the running game: build
//! the job exactly as `build_live_job` does and push it through
//! `live::Live::poke`. A field inside a block element — the case the plain
//! locator got wrong — is the default.
//!
//! Ignored: needs the game in a mission with the weapon in play and
//! `MJOLNIR_PAKS`. `MJOLNIR_TAG`, `MJOLNIR_FIELD` and `MJOLNIR_VALUE` pick
//! what to write (default: the assault rifle's zoom magnification, 8).
//!
//! The second test pokes a string id: the name is resolved to the running
//! game's registry id and written where the engine keeps the id, and the
//! bytes that were there are checked to have been the old name's id
//! (`MJOLNIR_SID_FIELD`, `MJOLNIR_SID_VALUE`).
//!
//! The third pokes a tag reference: the target is resolved through the
//! running game's tag table into the sixteen bytes the loader writes — group,
//! an encoded offset to the tag's path, the length, the handle — and the
//! bytes that were there are checked to be the old target's, in the same form
//! (`MJOLNIR_REF_FIELD`, `MJOLNIR_REF_VALUE`, written `<group>:<path>`). It
//! takes a field inside a block element as readily as a root one — the
//! address is found the same way either case.

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
            string_id: None,
            reference: None,
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

/// A string id in the root element pokes as its registry id: before the
/// write the field held the old name's id, after it the new name's, and an
/// unregistered name is refused rather than written.
#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS"]
fn poke_a_string_id_through_the_editor_path() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let want = std::env::var("MJOLNIR_TAG").unwrap_or_else(|_| "assault_rifle/assault_rifle".into());
    let path = std::env::var("MJOLNIR_SID_FIELD").unwrap_or_else(|_| "default variant".into());
    let value = std::env::var("MJOLNIR_SID_VALUE").unwrap_or_else(|_| "default".into());
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let index = catalog
        .tags
        .iter()
        .position(|e| e.group == "weapon" && e.short.contains(&want))
        .expect("weapon tag in catalog");
    let file = catalog.read_tag(index).expect("read tag");

    let (job, old_name) = {
        let tag = blam_tag::TagFile::parse(&file, Some(file.len())).unwrap();
        let layout = tag.layout().unwrap();
        let block = tag.read_data(&layout).unwrap();
        let route = blam_tag::patch::route(&layout, &file, &block, &path).expect("route");
        let target = &route.target;
        assert_eq!(target.type_name, "string id", "{path} is a {}", target.type_name);
        assert!(route.hops.is_empty(), "the test pokes a root-element string id");
        let old_name = match &target.current {
            blam_tag::Scalar::Text(t) => t.clone(),
            other => panic!("current value {other:?}"),
        };
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
        let span = target.file_offset..target.file_offset + target.size;
        (
            live::Job {
                key: (catalog.tags[index].group.clone(), catalog.tags[index].short.clone()),
                payload: file.clone(),
                region: start..start + data.content.len(),
                root,
                stable,
                headers,
                blocks,
                hops: Vec::new(),
                span,
                bytes: Vec::new(),
                string_id: Some(value.clone()),
                reference: None,
            },
            old_name,
        )
    };

    let live = live::Live::default();
    let poked = live.poke(&job).expect("poke");
    eprintln!("{path}: {old_name:?} -> {value:?}: was {} now {} at {}", poked.was, poked.now, poked.address);

    // The old bytes were the old name's registry id, the new bytes the new
    // name's, per the running game's own registry.
    let process = blam_live::Process::attach().unwrap();
    let attached = blam_live::tagtable::attach(&process).unwrap();
    let ids = blam_live::stringid::StringIds::read(&process, attached.base, attached.profile).unwrap();
    let id_of = |name: &str| ids.id(&blam_live::stringid::normalize(name).unwrap()).unwrap();
    let hex = |id: u32| id.to_le_bytes().iter().map(|b| format!("{b:02x}")).collect::<String>();
    assert_eq!(poked.now, hex(id_of(&value)));
    if !old_name.is_empty() {
        assert_eq!(poked.was, hex(id_of(&old_name)), "the field held the old name's id");
    }

    // An unregistered name is refused before anything is written.
    let mut bad = job.clone();
    bad.string_id = Some("mjolnir_never_registered_zz".into());
    assert!(live.poke(&bad).is_err());

    // Put it back.
    let mut restore = job;
    restore.string_id = Some(old_name);
    live.poke(&restore).expect("restore");
}

/// A tag reference in the root element pokes as the sixteen bytes the loader
/// writes: the field named a tag, it now names another, and both forms come
/// from the running game's own tag table.
#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS"]
fn poke_a_reference_through_the_editor_path() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let want = std::env::var("MJOLNIR_TAG").unwrap_or_else(|_| "assault_rifle/assault_rifle".into());
    let path = std::env::var("MJOLNIR_REF_FIELD").unwrap_or_else(|_| "pickup sound".into());
    let value = std::env::var("MJOLNIR_REF_VALUE")
        .unwrap_or_else(|_| r"snd!:sound\weapons\sniper_rifle\zoom_in".into());
    let (group, target_path) = value.split_once(':').expect("<group>:<path>");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let index = catalog
        .tags
        .iter()
        .position(|e| e.group == "weapon" && e.short.contains(&want))
        .expect("weapon tag in catalog");
    let file = catalog.read_tag(index).expect("read tag");

    let (job, was_reference) = {
        let tag = blam_tag::TagFile::parse(&file, Some(file.len())).unwrap();
        let layout = tag.layout().unwrap();
        let block = tag.read_data(&layout).unwrap();
        let route = blam_tag::patch::route(&layout, &file, &block, &path).expect("route");
        let target = &route.target;
        assert_eq!(target.type_name, "tag reference", "{path} is a {}", target.type_name);
        assert_eq!(target.size, blam_live::tagtable::REFERENCE_SIZE);
        let was_reference = match &target.current {
            blam_tag::Scalar::Reference { group, path } => (group.clone(), path.clone()),
            other => panic!("current value {other:?}"),
        };
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
        let span = target.file_offset..target.file_offset + target.size;
        (
            live::Job {
                key: (catalog.tags[index].group.clone(), catalog.tags[index].short.clone()),
                payload: file.clone(),
                region: start..start + data.content.len(),
                root,
                stable,
                headers,
                blocks,
                hops: route.hops.iter().map(live::hop).collect(),
                span,
                bytes: Vec::new(),
                string_id: None,
                reference: Some((group.to_string(), target_path.to_string())),
            },
            was_reference,
        )
    };

    let live = live::Live::default();
    let poked = live.poke(&job).expect("poke");
    eprintln!(
        "{path}: {was_reference:?} -> {value:?}: was {} now {} at {}",
        poked.was, poked.now, poked.address
    );

    // Both forms, independently, out of the running game's tag table.
    let process = blam_live::Process::attach().unwrap();
    let attached = blam_live::tagtable::attach(&process).unwrap();
    let segments =
        blam_live::tagtable::Segments::read(&process, attached.base, attached.profile).unwrap();
    let table =
        blam_live::tagtable::TagTable::open(&process, attached.base, attached.profile).unwrap();
    let tags = blam_live::tagtable::LiveTags::new(table.walk(&process).unwrap());
    let resident = |group: &str, path: &str| -> String {
        let cc: [u8; 4] = group.as_bytes().try_into().unwrap();
        let found = tags.find(cc, path).unwrap_or_else(|| panic!("{group}:{path} is not loaded"));
        found
            .reference_bytes(&segments)
            .unwrap()
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect()
    };
    assert_eq!(poked.now, resident(group, target_path));
    assert_eq!(
        poked.was,
        resident(&was_reference.0, &was_reference.1),
        "the field held the old target in the loader's own form"
    );

    // A tag the game has not loaded has no handle, and is refused rather
    // than written as something else.
    let mut bad = job.clone();
    bad.reference = Some(("weap".into(), r"objects\weapons\mjolnir\never_loaded".into()));
    let err = match live.poke(&bad) {
        Err(e) => e,
        Ok(p) => panic!("an unloaded target was written as {}", p.now),
    };
    assert!(err.contains("has not loaded"), "{err}");

    // Put it back.
    let mut restore = job;
    restore.reference = Some(was_reference);
    live.poke(&restore).expect("restore");
}
