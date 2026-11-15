//! Read-only cooked component/material inventory and selected native matrices.
//! hism_readback <global-paks> <usmap> <package> [comma-separated matrix names]
use serde_json::json;
use std::collections::{BTreeMap, HashSet};

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let selected: HashSet<&str> = args.get(3).map(|s| s.split(',').collect()).unwrap_or_default();
    let containers = ue_iostore::load_all(&args[0]).expect("containers");
    let global = containers.iter().find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc")).expect("global.utoc");
    let chunk = global.chunks.iter().find(|c| c.type_name() == "ScriptObjects").expect("ScriptObjects");
    let data = ue_iostore::read_chunk(global, chunk, None, &[]).expect("read ScriptObjects");
    let scripts = ue_asset::zen::ScriptObjects::parse(&data).expect("parse scripts");
    let usmap = ue_asset::Usmap::parse(&std::fs::read(&args[1]).expect("schema bytes")).expect("schema");
    let bytes = std::fs::read(&args[2]).expect("package bytes");
    let pkg = ue_asset::package::ZenPackage::parse(&bytes).expect("package");
    let refs = ue_asset::zen::Package::parse(&bytes).expect("reference view");
    let mut output = Vec::new();
    for i in 0..pkg.export_map.len() {
        let Some(class) = ue_asset::edit::export_class(&pkg, &scripts, i) else { continue };
        if !matches!(class.as_str(), "HierarchicalInstancedStaticMeshComponent" | "InstancedStaticMeshComponent" | "StaticMeshComponent" | "SceneComponent" | "LandscapeComponent" | "MaterialInstanceConstant") { continue }
        let export = ue_asset::edit::open_export(&pkg, &usmap, &scripts, i).expect("decode relevant export");
        let entry = &pkg.export_map[i];
        let name = pkg.mapped_name(entry.name_index, entry.name_number);
        let mut properties = BTreeMap::new();
        let mut references = BTreeMap::new();
        for row in ue_asset::edit::describe(&usmap, &class, &pkg.names.names, &export.block) {
            let keep = class == "MaterialInstanceConstant" || matches!(row.path.as_str(),
                "StaticMesh" | "NumBuiltInstances" | "InstanceCountToRender" | "InstanceStartCullDistance" |
                "InstanceEndCullDistance" | "bCanEverAffectNavigation" | "bEvaluateWorldPositionOffset" |
                "BodyInstance.CollisionEnabled" | "BodyInstance.CollisionProfileName" | "AttachParent" |
                "RelativeLocation" | "RelativeRotation" | "RelativeScale3D" | "SectionBaseX" | "SectionBaseY" | "ForcedLOD")
                || row.path.starts_with("OverrideMaterials[");
            if !keep { continue }
            if let Some(index) = row.value.strip_prefix("import ").and_then(|s| s.split_whitespace().next()).and_then(|s| s.parse::<usize>().ok()) {
                if let Some(target) = refs.imports.get(index).and_then(|index| refs.import_target(*index)) {
                    references.insert(row.path.clone(), json!({"package":target.package,"public_hash":format!("{:016x}",target.public_hash)}));
                }
            }
            properties.insert(row.path, row.value);
        }
        let matrices = if selected.contains(name.as_str()) {
            Some(ue_asset::level::instance_matrices(&export.tail).expect("native affine instance matrices"))
        } else { None };
        let outer = match ue_asset::zen::ObjectIndex(entry.outer).classify() {
            ue_asset::zen::ObjectRef::Export(index) => {
                let parent = &pkg.export_map[index];
                pkg.mapped_name(parent.name_index, parent.name_number)
            }
            _ => String::new(),
        };
        output.push(json!({"export":i,"name":name,"outer":outer,"class":class,
            "properties":properties,"references":references,"native_tail_bytes":export.tail.len(),"matrices":matrices}));
    }
    println!("{}", serde_json::to_string(&json!({"schema":"mjolnir-cooked-hism-readback-v1","package":pkg.name(),"exports":output})).unwrap());
}
