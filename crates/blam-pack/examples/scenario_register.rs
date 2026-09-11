//! Register a scenario codename the way the game's own are registered: a
//! cooked row in `DT_Scenarios` and a `ScenarioList` handle on the campaign
//! asset, in one override container.
//!
//! ```text
//! cargo run -p blam-pack --example scenario_register -- \
//!     <paks> <CODE> <out dir> [--from B40] [--title "text"]
//! ```
//!
//! The simulation learns which campaign maps exist at boot, from the tables
//! `BuiltInMapInfoData` points at (`CampaignMapInfoTables` = `DT_Scenarios`,
//! `DT_Test_Scenarios`). A row added at runtime is visible to the menu flow —
//! `StartScenario` reads the table then — but not to the map registry the
//! simulation built earlier, which is the state the 2026-09-03 `PG1` stall
//! sat in (a shipped codename in a new row started fine; a new codename never
//! did). So the row goes into the cooked table here, cloned from `--from`
//! with `ScenarioName` set to the codename, and the campaign's `ScenarioList`
//! gains a handle so MISSION SELECT lists it. The scenario tag package itself
//! comes from `mjolnir level bake --standalone <CODE>`.
use std::path::PathBuf;

use ue_asset::props::{Name, Val};

const TABLE: &str = "/Game/Blueprints/Campaign/DT_Scenarios";
const CAMPAIGN: &str = "/Game/Blueprints/Campaign/DA_FirstPlayableCampaign";
const ROW_STRUCT: &str = "BlamScenarioDataTableRow";

fn find_slot(usmap: &ue_asset::Usmap, class: &str, want: &str) -> u16 {
    let total = usmap.total_slots(class);
    let mut slot = 0u16;
    while slot < total {
        if let Some((_, prop)) = usmap.resolve(class, slot) {
            if prop.name == want {
                return slot;
            }
            slot += prop.array_dim.max(1) as u16;
        } else {
            slot += 1;
        }
    }
    panic!("{class} has no {want}");
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    if a.len() < 3 {
        eprintln!("usage: scenario_register <paks> <CODE> <out dir> [--from B40] [--title text]");
        std::process::exit(2);
    }
    let (paks, code, out_dir) = (&a[0], &a[1], &a[2]);
    let from = a
        .iter()
        .position(|s| s == "--from")
        .map(|i| a[i + 1].clone())
        .unwrap_or_else(|| "B40".to_string());
    let oodle: Vec<PathBuf> = Vec::new();

    let usmap_bytes = std::fs::read("defs/ue/Meteorite-2607-CU3.usmap").expect("read usmap");
    let usmap = ue_asset::Usmap::parse(&usmap_bytes).expect("parse usmap");
    let containers = ue_iostore::load_all(paks).expect("load containers");
    let global = containers
        .iter()
        .find(|c| c.utoc_path.file_name().unwrap() == "global.utoc")
        .expect("no global.utoc");
    let sc = global
        .chunks
        .iter()
        .find(|c| c.type_name() == "ScriptObjects")
        .expect("no ScriptObjects");
    let scripts = ue_asset::zen::ScriptObjects::parse(
        &ue_iostore::read_chunk(global, sc, None, &oodle).unwrap(),
    )
    .expect("parse scripts");

    // A shipped package by its /Game path: the chunk, its container, its bytes.
    let locate = |path: &str| -> (usize, ue_iostore::ChunkEntry, Vec<u8>) {
        let rel = format!("{}.uasset", path.trim_start_matches("/Game/"));
        containers
            .iter()
            .enumerate()
            .find_map(|(ci, c)| {
                c.files
                    .iter()
                    .find(|(p, _)| p.ends_with(&rel))
                    .map(|(_, i)| {
                        let chunk = c.chunks[*i].clone();
                        let data = ue_iostore::read_chunk(c, &chunk, None, &oodle).expect("read");
                        (ci, chunk, data)
                    })
            })
            .unwrap_or_else(|| panic!("{path} not found"))
    };

    // ---- DT_Scenarios: clone the donor row under the new name ---------------
    let (ci_table, table_chunk, table_data) = locate(TABLE);
    let mut zp = ue_asset::package::ZenPackage::parse(&table_data).expect("parse table");
    let export = 0;
    let edit = ue_asset::edit::open_export(&zp, &usmap, &scripts, export).expect("open table");
    assert_eq!(edit.class, "DataTable", "export 0 is a {}", edit.class);
    println!(
        "  tail {} byte(s): {}",
        edit.tail.len(),
        edit.tail[..40.min(edit.tail.len())]
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<Vec<_>>()
            .join(" ")
    );
    let (mut rows, used) =
        ue_asset::datatable::decode(&usmap, ROW_STRUCT, &edit.tail).expect("decode rows");
    let remainder = edit.tail[used..].to_vec();
    // The rows have to come back byte for byte before anything is changed.
    let again = ue_asset::datatable::encode(&usmap, ROW_STRUCT, &rows).expect("encode rows");
    assert_eq!(
        again,
        edit.tail[..used],
        "the row codec does not round-trip {TABLE}"
    );
    let row_name = |r: &ue_asset::datatable::Row| zp.names.names[r.name.index as usize].clone();
    println!(
        "{TABLE}: {} row(s): {}",
        rows.len(),
        rows.iter().map(row_name).collect::<Vec<_>>().join(" ")
    );
    if rows.iter().any(|r| row_name(r) == *code) {
        panic!("{TABLE} already has a row named {code}");
    }
    let donor = rows
        .iter()
        .find(|r| row_name(r) == from)
        .unwrap_or_else(|| panic!("no row named {from}"))
        .clone();
    let name_slot = find_slot(&usmap, ROW_STRUCT, "ScenarioName");
    let mut block = donor.block.clone();
    block.set(name_slot, Val::Str(code.clone()));
    let index = zp.names.intern(code);
    rows.push(ue_asset::datatable::Row {
        name: Name { index, number: 0 },
        block,
    });
    let mut tail = ue_asset::datatable::encode(&usmap, ROW_STRUCT, &rows).expect("encode rows");
    tail.extend_from_slice(&remainder);
    let mut bytes = edit
        .block
        .encode(&usmap, &edit.class)
        .expect("encode table props");
    bytes.extend_from_slice(&tail);
    zp.set_export_bytes(export, bytes)
        .expect("set table export");
    let table_out = zp.write();
    println!(
        "  + row {code} cloned from {from} (ScenarioName = {code:?}); {} -> {} bytes",
        table_data.len(),
        table_out.len()
    );

    // ---- DA_FirstPlayableCampaign: one more ScenarioList handle -------------
    let (ci_camp, camp_chunk, camp_data) = locate(CAMPAIGN);
    assert_eq!(
        ci_table, ci_camp,
        "the two packages live in different containers"
    );
    let mut zp = ue_asset::package::ZenPackage::parse(&camp_data).expect("parse campaign");
    let mut edit = ue_asset::edit::open_export(&zp, &usmap, &scripts, 0).expect("open campaign");
    let list_slot = find_slot(&usmap, &edit.class, "ScenarioList");
    let items = match edit.block.get(list_slot) {
        Some(Val::Array(items)) => items.clone(),
        other => panic!("ScenarioList is {other:?}"),
    };
    let handle_row_slot = find_slot(&usmap, "DataTableRowHandle", "RowName");
    let template = items.last().cloned().expect("ScenarioList is empty");
    let mut handle = match template {
        Val::Struct(b) => b,
        other => panic!("handle is {other:?}"),
    };
    let index = zp.names.intern(code);
    handle.set(handle_row_slot, Val::Name(Name { index, number: 0 }));
    let mut items = items;
    items.push(Val::Struct(handle));
    let count = items.len();
    edit.block.set(list_slot, Val::Array(items));
    ue_asset::edit::write_export(&mut zp, &usmap, &edit).expect("write campaign");
    let camp_out = zp.write();
    println!(
        "  + ScenarioList handle {{DT_Scenarios, {code}}} ({count} entries); {} -> {} bytes",
        camp_data.len(),
        camp_out.len()
    );

    // ---- one container for both --------------------------------------------
    let source = &containers[ci_table];
    let built = blam_pack::build_override(
        source,
        &oodle,
        &[
            blam_pack::ChunkEdit {
                label: TABLE.into(),
                chunk: table_chunk,
                original_len: table_out.len(),
                patched: table_out,
            },
            blam_pack::ChunkEdit {
                label: CAMPAIGN.into(),
                chunk: camp_chunk,
                original_len: camp_out.len(),
                patched: camp_out,
            },
        ],
    )
    .expect("build override");
    std::fs::create_dir_all(out_dir).expect("create out dir");
    let name = format!("pakchunk996-MJOLNIRREG-{code}_P");
    let utoc = PathBuf::from(format!("{out_dir}/{name}.utoc"));
    let ucas = PathBuf::from(format!("{out_dir}/{name}.ucas"));
    let pak = PathBuf::from(format!("{out_dir}/{name}.pak"));
    std::fs::write(&utoc, &built.utoc).expect("write utoc");
    std::fs::write(&ucas, &built.ucas).expect("write ucas");
    std::fs::write(&pak, ue_iostore::pak::stub_for(&name)).expect("write pak");
    blam_pack::verify_written(&utoc, &oodle, &built.expect).expect("verify");
    println!("  wrote {}, .ucas and stub .pak (verified)", utoc.display());
}
