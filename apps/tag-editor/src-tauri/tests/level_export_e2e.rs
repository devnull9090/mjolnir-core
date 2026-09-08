//! The level export through the catalog: a mission's cells enumerate, read,
//! and come out as `.glb` files, against a real installation.
//!
//! Ignored by default because it needs Halo Campaign Evolved on disk:
//!
//! ```text
//! cargo test --test level_export_e2e -- --ignored --nocapture
//! ```

use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::install;
use ue_asset::level::{ExportOptions, Exporter};

#[test]
#[ignore = "needs an installed copy of Halo Campaign Evolved"]
fn a30_cells_enumerate_and_export_through_the_catalog() {
    let found = install::detect();
    let paks = found.paks.expect("no installation found on this machine");
    let c = Catalog::open(&paks, &found.oodle.unwrap_or_default()).expect("open catalog");

    let cells = c.level_cells("a30");
    assert!(cells.len() > 500, "A30 has {} level packages", cells.len());
    assert!(
        cells[0].to_ascii_lowercase().ends_with("/a30/a30"),
        "the persistent level comes first: {}",
        cells[0]
    );
    assert!(cells.iter().skip(1).all(|n| n.to_ascii_lowercase().contains("/_generated_/")));

    let usmap = tag_editor_lib::usmap().expect("usmap");
    let scripts = c.script_objects().expect("script objects");
    let load_package = |name: &str| c.read_package(name);
    let load_bulk = |name: &str| c.read_package_bulk(name);
    let mut exporter = Exporter::new(usmap, scripts, &load_package, &load_bulk, ExportOptions::default());

    // A cell known to place rocks and a ledge, and the one with the most
    // foliage; both write, both name only meshes that read.
    let mut written = 0usize;
    let mut placements = 0usize;
    for id in ["066sc90vxdm6u2mx0v22rzk6e", "07hj7ttalw11fjay0v6umoq87"] {
        let name = cells
            .iter()
            .find(|n| n.to_ascii_lowercase().ends_with(id))
            .unwrap_or_else(|| panic!("no cell {id}"));
        let cell = exporter.export_cell(name, true).expect("export cell");
        assert!(cell.placements > 100, "{id}: {} placements", cell.placements);
        assert!(cell.missing.is_empty(), "{id}: unreadable meshes {:?}", cell.missing);
        let glb = cell.glb.as_ref().expect("a .glb");
        assert_eq!(&glb[..4], b"glTF");
        written += glb.len();
        placements += cell.placements;
    }
    eprintln!("{placements} placements in {written} bytes");
    assert!(written > 1_000_000);

    // The engine primitives a few cells place resolve through the catalog.
    assert!(c.read_package("/Engine/BasicShapes/Plane").is_some());
}
