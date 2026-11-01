//! Clone native cooked material instances without losing their layer/shader data.
//! Usage: native_material_clone <game-paks> <manifest.json> <out-dir> <container>
//! Manifest entries: source, target, scalars/vectors keyed as Name#layer.
use serde::Deserialize;
use std::{collections::BTreeMap, path::PathBuf};
use ue_asset::{
    Usmap,
    package::ZenPackage,
    props::{Block, Name, Val},
};
#[derive(Deserialize)]
struct Entry {
    source: String,
    target: String,
    #[serde(default)]
    scalars: BTreeMap<String, f32>,
    #[serde(default)]
    vectors: BTreeMap<String, [f32; 4]>,
}
fn slot(u: &Usmap, c: &str, n: &str) -> u16 {
    (0..u.total_slots(c))
        .find(|s| u.resolve(c, *s).is_some_and(|(_, p)| p.name == n))
        .expect("property schema")
}
fn key(u: &Usmap, p: &ZenPackage, b: &Block, c: &str) -> Option<String> {
    let info = match b.get(slot(u, c, "ParameterInfo"))? {
        Val::Struct(x) => x,
        _ => return None,
    };
    let n = match info.get(slot(u, "MaterialParameterInfo", "Name"))? {
        Val::Name(n) => p.mapped_name(n.index, n.number),
        _ => return None,
    };
    let association = info.get(slot(u, "MaterialParameterInfo", "Association"));
    if !matches!(association, Some(Val::Zeroed) | Some(Val::Byte(0)) | None) {
        return None;
    }
    let layer = match info.get(slot(u, "MaterialParameterInfo", "Index")) {
        Some(Val::Int(x)) => *x,
        _ => 0,
    };
    Some(format!("{n}#{layer}"))
}
fn apply(
    u: &Usmap,
    p: &mut ZenPackage,
    b: &mut Block,
    c: &str,
    array: &str,
    values: Vec<(String, Val)>,
) {
    let s = slot(u, "MaterialInstanceConstant", array);
    let mut entries = match b.get(s) {
        Some(Val::Array(a)) => a.clone(),
        _ => vec![],
    };
    for (k, v) in values {
        let i = entries
            .iter()
            .position(|e| matches!(e,Val::Struct(b) if key(u,p,b,c).as_deref()==Some(&k)));
        if let Some(i) = i {
            if let Val::Struct(b) = &mut entries[i] {
                b.set(slot(u, c, "ParameterValue"), v)
            }
        } else {
            let (n, l) = k.rsplit_once('#').expect("Name#layer");
            let mut info = Block::default();
            info.set(
                slot(u, "MaterialParameterInfo", "Name"),
                Val::Name(Name {
                    index: p.names.intern(n),
                    number: 0,
                }),
            );
            info.set(
                slot(u, "MaterialParameterInfo", "Association"),
                Val::Byte(0),
            );
            info.set(
                slot(u, "MaterialParameterInfo", "Index"),
                Val::Int(l.parse().expect("layer")),
            );
            let mut record = Block::default();
            record.set(slot(u, c, "ParameterInfo"), Val::Struct(info));
            record.set(slot(u, c, "ParameterValue"), v);
            entries.push(Val::Struct(record));
        }
    }
    b.set(s, Val::Array(entries));
}
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    assert_eq!(
        a.len(),
        4,
        "native_material_clone <paks> <manifest> <out-dir> <container>"
    );
    let containers = ue_iostore::load_all(&a[0]).expect("game containers");
    let global = containers
        .iter()
        .find(|c| c.utoc_path.file_name().is_some_and(|n| n == "global.utoc"))
        .expect("global");
    let sc = global
        .chunks
        .iter()
        .find(|c| c.type_name() == "ScriptObjects")
        .expect("script objects");
    let scripts = ue_asset::zen::ScriptObjects::parse(
        &ue_iostore::read_chunk(global, sc, None, &[]).unwrap(),
    )
    .unwrap();
    let u = Usmap::parse(&std::fs::read("defs/ue/Meteorite-2607-CU3.usmap").unwrap()).unwrap();
    let entries: Vec<Entry> = serde_json::from_slice(&std::fs::read(&a[1]).unwrap()).unwrap();
    let mut packages = vec![];
    for entry in entries {
        assert!(entry.source.starts_with("/Game/Env/"));
        assert!(entry.target.starts_with("/Game/MJOLNIR/"));
        assert!(
            entry.scalars.values().all(|v| v.is_finite())
                && entry.vectors.values().flatten().all(|v| v.is_finite())
        );
        let suffix =
            format!("{}.uasset", entry.source.strip_prefix("/Game/").unwrap()).to_lowercase();
        let (source, chunk) = containers
            .iter()
            .find_map(|c| {
                c.files
                    .iter()
                    .find(|(n, _)| n.to_lowercase().ends_with(&suffix))
                    .map(|(_, i)| (c, &c.chunks[*i]))
            })
            .expect("native source");
        let mut p =
            ZenPackage::parse(&ue_iostore::read_chunk(source, chunk, None, &[]).unwrap()).unwrap();
        let index = (0..p.export_map.len())
            .find(|i| {
                ue_asset::edit::export_class(&p, &scripts, *i).as_deref()
                    == Some("MaterialInstanceConstant")
            })
            .expect("MIC export");
        let mut edit = ue_asset::edit::open_export(&p, &u, &scripts, index).unwrap();
        let native_tail = edit.tail.clone();
        apply(
            &u,
            &mut p,
            &mut edit.block,
            "ScalarParameterValue",
            "ScalarParameterValues",
            entry
                .scalars
                .into_iter()
                .map(|(k, v)| (k, Val::Float(v)))
                .collect(),
        );
        apply(
            &u,
            &mut p,
            &mut edit.block,
            "VectorParameterValue",
            "VectorParameterValues",
            entry
                .vectors
                .into_iter()
                .map(|(k, v)| {
                    (
                        k,
                        Val::Native(v.into_iter().flat_map(|x| x.to_le_bytes()).collect()),
                    )
                })
                .collect(),
        );
        ue_asset::edit::write_export(&mut p, &u, &edit).unwrap();
        p.rename_package(&entry.target).unwrap();
        let data = p.write();
        let check = ZenPackage::parse(&data).unwrap();
        let back = ue_asset::edit::open_export(&check, &u, &scripts, index).unwrap();
        assert_eq!(
            back.tail, native_tail,
            "native shader/layer serialization changed"
        );
        assert_eq!(back.block, edit.block, "parameter round-trip changed");
        assert_eq!(check.name(), entry.target);
        packages.push(blam_pack::NewPackage {
            package_name: entry.target,
            uasset: data,
            ubulk: vec![],
            imported_package_ids: p
                .imported_package_names
                .names
                .iter()
                .map(|n| ue_iostore::city::package_id(n))
                .collect(),
            uasset_meta: vec![],
            ubulk_meta: vec![],
        });
    }
    let template = containers
        .iter()
        .find(|c| {
            c.utoc_path
                .file_name()
                .is_some_and(|n| n.to_string_lossy().starts_with("pakchunk0-"))
        })
        .unwrap();
    let built = blam_pack::build_addition(template, &[], &a[3], &packages).unwrap();
    let out = PathBuf::from(&a[2]);
    std::fs::create_dir_all(&out).unwrap();
    let utoc = out.join(format!("{}.utoc", a[3]));
    std::fs::write(&utoc, &built.utoc).unwrap();
    std::fs::write(out.join(format!("{}.ucas", a[3])), &built.ucas).unwrap();
    std::fs::write(
        out.join(format!("{}.pak", a[3])),
        ue_iostore::pak::stub_for(&a[3]),
    )
    .unwrap();
    blam_pack::verify_written(&utoc, &[], &built.expect).unwrap();
    println!(
        "{} native material clones verified in {}",
        packages.len(),
        utoc.display()
    );
}
