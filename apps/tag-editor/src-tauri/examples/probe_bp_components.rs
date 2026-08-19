//! Inside a BP_* actor package: every *MeshComponent template export, with
//! all its kept properties — where the real mesh reference (hard or soft) and
//! the component transform live.
//!
//!   cargo run --release --example probe_bp_components -- /Game/Blueprints/Synchronization/Characters/BP_EliteBipedActor

use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::install;
use ue_asset::unversioned::{Ctx, Keep, Value, Walker};

fn brief(v: &Value) -> String {
    match v {
        Value::Struct(fields) => {
            let mut parts: Vec<String> =
                fields.iter().map(|(k, v)| format!("{k}: {}", brief(v))).collect();
            parts.sort();
            format!("{{{}}}", parts.join(", "))
        }
        Value::Array(items) => format!(
            "[{}]",
            items.iter().map(brief).collect::<Vec<_>>().join(", ")
        ),
        other => format!("{other:?}"),
    }
}

fn main() -> Result<(), String> {
    let package_name = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "/Game/Blueprints/Synchronization/Characters/BP_EliteBipedActor".into());

    let usmap_bytes = std::fs::read("../../../defs/ue/Meteorite-2607-CU3.usmap")
        .map_err(|e| e.to_string())?;
    let usmap = ue_asset::Usmap::parse(&usmap_bytes).map_err(|e| e.to_string())?;

    let found = install::detect();
    let (paks, oodle) = (found.paks.unwrap(), found.oodle.unwrap());
    let catalog = Catalog::open(&paks, &oodle)?;
    let scripts = catalog.script_objects().ok_or("no scripts")?;

    let bytes = catalog.read_package(&package_name).ok_or("package not found")?;
    let package = ue_asset::zen::Package::parse(&bytes).map_err(|e| e.to_string())?;
    let ctx = Ctx {
        usmap: &usmap,
        names: &package.names,
    };

    println!("package: {package_name}");
    println!("imported packages:");
    for p in &package.imported_package_names {
        println!("  {p}");
    }

    let filter = std::env::args().nth(2).unwrap_or_else(|| "MeshComponent".into());
    for (i, e) in package.exports.iter().enumerate() {
        let class = match e.class.classify() {
            _ if scripts.leaf(e.class).is_some() => scripts.leaf(e.class).unwrap().to_string(),
            ue_asset::zen::ObjectRef::Export(ci) => package
                .exports
                .get(ci)
                .map(|x| x.name.clone())
                .unwrap_or_else(|| "?".into()),
            ue_asset::zen::ObjectRef::PackageImport(v) => {
                let pkg = ((v >> 32) & 0x3FFF_FFFF) as usize;
                package
                    .imported_package_names
                    .get(pkg)
                    .cloned()
                    .unwrap_or_else(|| "?".into())
            }
            _ => "?".into(),
        };
        if !class.contains(&filter) {
            continue;
        }
        let class = class.rsplit('/').next().unwrap_or(&class);
        println!("export {i}: class {class}");
        let Ok(data) = package.export_data(&bytes, i) else {
            println!("  [no export data]");
            continue;
        };
        let mut w = Walker::new(&ctx, data);
        match w.read_object(class, Keep::All) {
            Ok(props) => {
                let mut keys: Vec<_> = props.keys().collect();
                keys.sort();
                for k in keys {
                    let mut line = format!("  {k} = {}", brief(&props[k]));
                    if let Value::Object(n) = &props[k] {
                        if let Some(p) = ue_asset::material::import_package_name(&package, *n) {
                            line.push_str(&format!("  -> {p}"));
                        }
                    }
                    println!("{line}");
                }
            }
            Err(err) => println!("  [property walk failed: {err}]"),
        }
    }
    Ok(())
}
