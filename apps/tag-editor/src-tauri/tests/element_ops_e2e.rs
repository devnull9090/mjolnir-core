//! End-to-end element-op test against a real installation.
//!
//! Ignored by default because it needs Halo Campaign Evolved on disk. Run it
//! on a machine with the game:
//!
//! ```text
//! cargo test --test element_ops_e2e -- --ignored
//! ```
//!
//! It proves the editor's element ops through the production replay: record a
//! `duplicate` op plus field edits inside the new element (which resolve only
//! once the op has applied), replay them with `apply_pending`, bake the result
//! into an override container, and byte-verify it from disk — the exact bytes
//! a test install puts in front of the game.
//!
//! Set `MJOLNIR_KEEP_TEST_INSTALL=1` to also install the container into the
//! Paks folder and leave it there for an in-game look: a30 then spawns a
//! sniper rifle beside the mission start that the shipped scenario does not
//! have. Remove it from the editor, or delete the `-MJOLNIRDEV-` files.

use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::{apply_pending, install, modpack, PendingEdit};

fn edit(path: &str, value: &str) -> PendingEdit {
    PendingEdit {
        path: path.into(),
        value: value.into(),
    }
}

/// Replay `pending` against the shipped tag and hand back a bake-ready edit,
/// asserting every edit applied and the result still walks exactly.
fn replay(c: &Catalog, group: &str, tail: &str, pending: &[PendingEdit]) -> modpack::ResolvedEdit {
    let index = c
        .tags
        .iter()
        .position(|t| t.group == group && t.short.to_lowercase().ends_with(tail))
        .unwrap_or_else(|| panic!("no {group} tag ending {tail}"));
    let entry = c.entry(index).unwrap();
    let original = c.read_tag(index).expect("read tag");

    let (patched, outcomes) = apply_pending(original.clone(), pending).expect("replay");
    for o in &outcomes {
        assert!(o.applied, "{}: '{}' did not apply", o.path, o.value);
    }
    assert_ne!(patched, original, "the edits must change the tag");

    let tag = blam_tag::TagFile::parse(&patched, Some(patched.len())).expect("parse patched");
    let layout = tag.layout().expect("layout");
    let block = tag.read_data(&layout).expect("walk patched");
    let payload = tag.data().expect("data section");
    assert_eq!(block.consumed, payload.size as usize, "walk must be exact");

    modpack::ResolvedEdit {
        label: format!("{tail}.{group}"),
        container: entry.container,
        chunk: entry.chunk,
        original_len: original.len(),
        patched,
    }
}

#[test]
#[ignore = "needs an installed copy of Halo Campaign Evolved"]
fn element_ops_bake_against_the_real_game() {
    let found = install::detect();
    let paks = found.paks.expect("no installation found on this machine");
    let catalog = Catalog::open(&paks, &found.oodle.unwrap_or_default()).expect("open catalog");

    // a30: duplicate the last weapon placement (nothing shifts, so the object
    // name table stays right), then edit the copy into an unmistakable
    // sniper rifle beside the mission start. The field edits target
    // weapons[22], which exists only after the op — the ordering the
    // sequential replay guarantees.
    let scenario = replay(
        &catalog,
        "scenario",
        "a30/_generated_/a30",
        &[
            edit("weapons", "duplicate 21"),
            edit("weapons[22].type", "#6"),
            edit("weapons[22].name", "none"),
            edit("weapons[22].object data.position", "(31.5, -96.5, 58.9)"),
            edit("weapons[22].object data.rotation", "(0, 0, 0)"),
            edit(
                "weapons[22].object data.object id.origin bsp index",
                "#5",
            ),
        ],
    );

    // The marine physics_model from issue #80: grow a shipped block with
    // known-good element data.
    let marine = replay(
        &catalog,
        "physics_model",
        "characters/marine/marine",
        &[edit("ragdoll constraints", "duplicate 0")],
    );

    let baked = modpack::bake(&catalog, "element-ops-e2e", vec![scenario, marine]).expect("bake");
    // Element ops grow the tags, so the containers are the resized kind — the
    // path length-changing edits already ride in game.
    assert!(
        baked.iter().any(|b| b.built.resized()),
        "an element op must produce a resized chunk"
    );

    let dir = std::env::temp_dir().join(format!("mjolnir-element-ops-e2e-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    modpack::write_and_verify(&dir, &baked, catalog.oodle_paths()).expect("write and verify");

    if std::env::var("MJOLNIR_KEEP_TEST_INSTALL").is_ok() {
        let written = modpack::install_test(catalog.paks(), &baked, catalog.oodle_paths())
            .expect("install test");
        println!("installed for an in-game look:");
        for f in &written {
            println!("  {f}");
        }
    } else {
        let _ = std::fs::remove_dir_all(&dir);
    }
}
