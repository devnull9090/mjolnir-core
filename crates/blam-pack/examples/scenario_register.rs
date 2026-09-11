//! Register a scenario codename the way the game's own are registered: a
//! cooked row in `DT_Scenarios` and a `ScenarioList` handle on the campaign
//! asset, in one override container. `mjolnir level bake --standalone` does
//! this as part of a bake; this is the standalone form.
//!
//! ```text
//! cargo run -p blam-pack --example scenario_register -- \
//!     <paks> <CODE> <out dir> [--from B40] [--title "text"] [--description "text"]
//! ```
//!
//! See `blam_pack::scenario` for why the row has to be cooked.
use std::path::PathBuf;

fn flag(a: &[String], name: &str) -> Option<String> {
    a.iter().position(|s| s == name).map(|i| a[i + 1].clone())
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    if a.len() < 3 {
        eprintln!(
            "usage: scenario_register <paks> <CODE> <out dir> [--from B40] [--title text] [--description text]"
        );
        std::process::exit(2);
    }
    let (paks, code, out_dir) = (&a[0], a[1].to_uppercase(), &a[2]);
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

    let reg = blam_pack::scenario::Registration {
        code: code.clone(),
        from: flag(&a, "--from").unwrap_or_else(|| "B40".into()),
        title: flag(&a, "--title"),
        description: flag(&a, "--description"),
    };
    let (built, name, log) =
        blam_pack::scenario::register(&containers, &oodle, &usmap, &scripts, &reg)
            .unwrap_or_else(|e| panic!("{e}"));
    for line in &log {
        println!("  {line}");
    }

    std::fs::create_dir_all(out_dir).expect("create out dir");
    let utoc = PathBuf::from(format!("{out_dir}/{name}.utoc"));
    let ucas = PathBuf::from(format!("{out_dir}/{name}.ucas"));
    let pak = PathBuf::from(format!("{out_dir}/{name}.pak"));
    std::fs::write(&utoc, &built.utoc).expect("write utoc");
    std::fs::write(&ucas, &built.ucas).expect("write ucas");
    std::fs::write(&pak, ue_iostore::pak::stub_for(&name)).expect("write pak");
    blam_pack::verify_written(&utoc, &oodle, &built.expect).expect("verify");
    println!("  wrote {}, .ucas and stub .pak (verified)", utoc.display());
}
