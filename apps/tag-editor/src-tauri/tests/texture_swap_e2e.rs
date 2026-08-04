//! End-to-end texture swap against a real installation, through the editor's
//! own path rather than the CLI's.
//!
//! Ignored by default because it needs Halo Campaign Evolved on disk:
//!
//! ```text
//! cargo test --test texture_swap_e2e -- --ignored --nocapture
//! ```
//!
//! It proves the half of the swap that the CLI does not exercise: an image
//! stored in a mod project, read back out of the project folder, re-encoded
//! against the installation at bake time, and packed into an override
//! container through the same `modpack` path a tag edit takes.
//!
//! Set `MJOLNIR_KEEP_TEST_INSTALL=1` to leave the baked container in the Paks
//! folder so the result can be looked at in game; the test otherwise removes
//! it, and only ever touches files carrying the `-MJOLNIRDEV-` marker.

use std::collections::BTreeMap;

use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::{install, modpack, project, resolve_textures, textures};

/// The assault rifle's albedo: DXT1, virtual, 12 mips, and on screen in the
/// player's hands for most of the campaign.
///
/// The full path matters. Several skins ship a texture with this leaf name —
/// `AssaultRifle_HP_Omen/` and `AssaultRifle_25thAnniversary/` among them —
/// and swapping one of those repaints a rifle nobody is holding. `default/`
/// is the skin the campaign actually equips.
const TARGET: &str =
    "Weapons/Rifle/AssaultRifle/default/Textures/T_rifle_assaultrifle_default_D";

#[test]
#[ignore = "needs an installed copy of Halo Campaign Evolved"]
fn swap_a_dxt1_albedo_through_a_mod_project() {
    let found = install::detect();
    let paks = found.paks.expect("no installation found on this machine");
    let catalog = Catalog::open(&paks, &found.oodle.unwrap_or_default()).expect("open catalog");

    let matches: Vec<usize> = catalog
        .textures
        .iter()
        .enumerate()
        .filter(|(_, t)| t.short.ends_with(TARGET))
        .map(|(i, _)| i)
        .collect();
    assert_eq!(
        matches.len(),
        1,
        "the target must be unambiguous, or the swap repaints the wrong skin"
    );
    let index = matches[0];
    let path = catalog.textures[index].short.clone();
    println!("target {path}");

    // The recipe's own lookup must find it by the identity it stores.
    assert_eq!(
        catalog.texture_index(&path),
        Some(index),
        "texture_index must find the texture by its stored path"
    );

    // Decode the shipped top mip, then repaint it. Pushing towards magenta is
    // unmistakable in game and cannot be confused with a lighting change.
    let uasset = catalog.read_texture_uasset(index).expect("uasset");
    let header = textures::zen_header_size(&uasset).expect("zen package");
    let tex = textures::parse_texture(&uasset[header..]).expect("parse");
    assert_eq!(tex.format, "PF_DXT1", "this test is about the DXT1 path");
    let ubulk = catalog.read_texture_ubulk(index).expect("ubulk");
    let mut img = textures::assemble_mip(&tex, &ubulk, 0).expect("decode mip 0");
    println!("shipped {}x{} {}", tex.width, tex.height, tex.format);
    for px in img.rgba.chunks_mut(4) {
        px[0] = px[0].saturating_add(90); // red up
        px[1] = px[1] / 3; //               green down
        px[2] = px[2].saturating_add(70); // blue up
    }
    let repainted = textures::to_png(&img).expect("encode png");
    println!("repainted png {} bytes", repainted.len());

    // Store it in a mod project the way the editor's swap command does.
    let root = std::env::temp_dir().join(format!("mjolnir-swap-e2e-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&root);
    let meta = project::Meta {
        schema_version: 1,
        name: "Magenta Rifle".into(),
        slug: "magenta-rifle".into(),
        version: "0.1.0".into(),
        summary: "Texture swap end-to-end test".into(),
    };
    let p = project::Project::create(&root, meta).expect("create project");
    p.write_texture_file(&path, &repainted).expect("write png");
    p.save_edits_and_textures(&[], &[project::SavedTexture { path: path.clone() }])
        .expect("save recipe");

    // Reopen it from disk. This is the step that would silently drop the swap
    // if the recipe were only held in memory.
    let (reopened, edits) = project::Project::open(&root).expect("reopen project");
    assert!(edits.is_empty(), "no field edits in this mod");
    let saved = reopened.load_textures().expect("load textures");
    assert_eq!(saved.len(), 1, "the swap must survive a reopen");
    assert_eq!(saved[0].path, path);
    let png = reopened.read_texture_file(&path).expect("read png back");
    assert_eq!(png, repainted, "the stored image must round-trip");

    // Re-encode against the installation, exactly as test/export/publish do.
    let mut swaps: BTreeMap<String, Vec<u8>> = BTreeMap::new();
    swaps.insert(path.clone(), png);
    let mut resolved = Vec::new();
    resolve_textures(&catalog, &swaps, &mut resolved).expect("resolve the swap");
    assert_eq!(resolved.len(), 1, "one texture, one chunk edit");
    assert_eq!(
        resolved[0].original_len,
        resolved[0].patched.len(),
        "the payload length must not move — every offset depends on it"
    );
    assert_ne!(resolved[0].patched, ubulk, "nothing was actually repainted");
    println!(
        "resolved {} ({} byte payload)",
        resolved[0].label, resolved[0].original_len
    );

    // Bake, write and byte-verify the container through the ordinary path.
    let baked = modpack::bake(&catalog, "magenta-rifle", resolved).expect("bake");
    assert_eq!(baked.len(), 1, "one source container, one override");
    assert!(
        !baked[0].built.resized(),
        "a size-identical swap must never resize a chunk"
    );
    let build = root.join("build");
    modpack::write_and_verify(&build, &baked, catalog.oodle_paths()).expect("write and verify");
    println!("baked {}.utoc + .ucas", baked[0].basename);

    // Install it for a real in-game look.
    let written =
        modpack::install_test(catalog.paks(), &baked, catalog.oodle_paths()).expect("install test");
    assert_eq!(written.len(), 3, "utoc + ucas + stub pak");
    assert!(written.iter().all(|f| f.contains("-MJOLNIRDEV-")));
    for f in &written {
        println!("installed {f}");
    }

    if std::env::var("MJOLNIR_KEEP_TEST_INSTALL").is_ok() {
        println!("left installed — remove it with project_untest or by deleting those files");
        return;
    }
    let removed = modpack::remove_test(catalog.paks()).expect("remove test");
    assert_eq!(removed, 3);
    assert!(modpack::test_files(catalog.paks()).is_empty());
    let _ = std::fs::remove_dir_all(&root);
}
