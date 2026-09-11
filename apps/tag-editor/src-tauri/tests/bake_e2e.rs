//! End-to-end bake test against a real installation.
//!
//! Ignored by default because it needs Halo Campaign Evolved on disk. Run it
//! on a machine with the game:
//!
//! ```text
//! cargo test --test bake_e2e -- --ignored
//! ```
//!
//! It proves the editor's whole production path with real data: resolve a tag,
//! patch a field, bake an override container, write and byte-verify it, write
//! a `.mjolnir` archive with the right layout, and round-trip a test install
//! into the Paks folder (immediately removed; those files are the only thing
//! touched, and only files carrying the `-MJOLNIRDEV-` marker are ever
//! deleted).

use std::io::Read;

use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::{install, modpack, project};

#[test]
#[ignore = "needs an installed copy of Halo Campaign Evolved"]
fn bake_export_and_test_install_against_the_real_game() {
    let found = install::detect();
    let paks = found.paks.expect("no installation found on this machine");
    let catalog = Catalog::open(&paks, &found.oodle.unwrap_or_default()).expect("open catalog");

    // The magnum: small, stable, and its magazine is the canonical example.
    let index = catalog
        .tags
        .iter()
        .position(|t| t.group == "weapon" && t.short.ends_with("Magnum/magnum"))
        .expect("magnum weapon tag");
    let entry = catalog.entry(index).unwrap();
    // The identity key round-trips through the recipe's lookup.
    assert_eq!(
        catalog.tag_index(&entry.group, &entry.short),
        Some(index),
        "tag_index must find the tag by its own identity"
    );

    // Patch one field the way the editor does.
    let original = catalog.read_tag(index).expect("read magnum");
    let tag = blam_tag::TagFile::parse(&original, Some(original.len())).expect("parse");
    let layout = tag.layout().expect("layout");
    let block = tag.read_data(&layout).expect("data");
    let path = "magazines[0].rounds loaded maximum";
    let target = blam_tag::patch::resolve(&layout, &original, &block, path).expect("resolve");
    let value = blam_tag::value::parse(&layout, &target.field, "24").expect("parse value");
    let (patched, applied) =
        blam_tag::patch::set(&layout, &original, &block, path, &value).expect("patch");
    assert_eq!(applied.after.display(), "24");
    assert_eq!(
        patched.len(),
        original.len(),
        "a fixed-width edit must not resize"
    );

    // Bake it and verify the container from disk, the way export does.
    let baked = modpack::bake(
        &catalog,
        "bake-e2e",
        vec![modpack::ResolvedEdit {
            label: "Magnum/magnum.weapon".into(),
            container: entry.container,
            chunk: entry.chunk,
            original_len: original.len(),
            patched,
        }],
        Vec::new(),
    )
    .expect("bake");
    assert_eq!(baked.len(), 1, "one source container, one override");
    assert!(!baked[0].built.resized());

    let dir = std::env::temp_dir().join(format!("mjolnir-bake-e2e-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    modpack::write_and_verify(&dir, &baked, catalog.oodle_paths()).expect("write and verify");

    // The archive: manifest at the root, containers under content/.
    let meta = project::Meta {
        schema_version: 1,
        name: "Bake E2E".into(),
        slug: "bake-e2e".into(),
        version: "0.0.1".into(),
        summary: String::new(),
    };
    let identity = mjolnir_sign::SigningIdentity::from_seed(&[42u8; 32]);
    let archive = dir.join("bake-e2e-0.0.1.mjolnir");
    let declared = serde_json::to_string_pretty(&modpack::DeclaredChanges {
        schema_version: 1,
        tags: vec![modpack::DeclaredTag {
            group: "weapon".into(),
            tag: entry.short.clone(),
            fields: vec![modpack::DeclaredField {
                field: path.into(),
                before: Some(target.current.display()),
                value: "24".into(),
            }],
        }],
        textures: Vec::new(),
        scripts: Vec::new(),
        new_tags: Vec::new(),
    })
    .unwrap();
    let size = modpack::write_archive(
        &archive,
        &meta,
        &baked,
        None,
        Some(&declared),
        Some(modpack::SignContext {
            identity: &identity,
            author: Some(mjolnir_sign::Author {
                id: "u-test".into(),
                username: "bake-e2e".into(),
            }),
        }),
    )
    .expect("archive");
    assert!(size > 0);

    let mut zip = zip::ZipArchive::new(std::fs::File::open(&archive).unwrap()).expect("zip");
    let names: Vec<String> = (0..zip.len())
        .map(|i| zip.by_index(i).unwrap().name().to_string())
        .collect();
    assert_eq!(
        names,
        [
            "mjolnir.json",
            "changes.json",
            "content/bake-e2e_P.utoc",
            "content/bake-e2e_P.ucas",
            "signature.json"
        ]
    );
    let mut manifest = String::new();
    zip.by_name("mjolnir.json")
        .unwrap()
        .read_to_string(&mut manifest)
        .unwrap();
    let manifest: serde_json::Value = serde_json::from_str(&manifest).unwrap();
    assert_eq!(manifest["schema_version"], 1);
    assert_eq!(manifest["type"], "content");
    assert_eq!(manifest["version"], "0.0.1");

    // The signature verifies against exactly the members written, and stops
    // verifying the moment any member's bytes change — the launcher-side
    // check, run here against a real baked archive.
    let mut members: Vec<(String, Vec<u8>)> = Vec::new();
    let mut envelope = Vec::new();
    for i in 0..zip.len() {
        let mut entry = zip.by_index(i).unwrap();
        let mut bytes = Vec::new();
        std::io::copy(&mut entry, &mut bytes).unwrap();
        if entry.name() == mjolnir_sign::SIGNATURE_MEMBER {
            envelope = bytes;
        } else {
            members.push((entry.name().to_string(), bytes));
        }
    }
    let member_refs: Vec<(String, &[u8])> = members
        .iter()
        .map(|(n, b)| (n.clone(), b.as_slice()))
        .collect();
    let verified = mjolnir_sign::verify_members(&envelope, "bake-e2e", "0.0.1", &member_refs)
        .expect("signature verifies");
    assert_eq!(verified.fingerprint, identity.fingerprint());
    assert_eq!(verified.statement.author.unwrap().username, "bake-e2e");

    let mut tampered = members.clone();
    tampered[1].1[100] ^= 0xFF;
    let tampered_refs: Vec<(String, &[u8])> = tampered
        .iter()
        .map(|(n, b)| (n.clone(), b.as_slice()))
        .collect();
    mjolnir_sign::verify_members(&envelope, "bake-e2e", "0.0.1", &tampered_refs)
        .expect_err("a flipped byte in a container must break the signature");

    // Test install into the real Paks folder, then remove it again.
    let paks_dir = catalog.paks();
    let written =
        modpack::install_test(paks_dir, &baked, catalog.oodle_paths()).expect("install test");
    assert_eq!(written.len(), 3, "utoc + ucas + stub pak");
    assert!(written.iter().all(|f| f.contains("-MJOLNIRDEV-")));
    // `test_files` reports sorted; `written` is in write order.
    let mut expected = written.clone();
    expected.sort();
    assert_eq!(modpack::test_files(paks_dir), expected);
    let removed = modpack::remove_test(paks_dir).expect("remove test");
    assert_eq!(removed, 3);
    assert!(modpack::test_files(paks_dir).is_empty());

    let _ = std::fs::remove_dir_all(&dir);
}
