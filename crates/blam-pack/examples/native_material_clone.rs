//! Clone native cooked material instances without losing their layer/shader data.
//! Usage: native_material_clone <game-paks> <manifest.json> <out-dir> <container>
//! Manifest entries: source, target, scalars/vectors keyed as Name#index.
//! Numeric scalars and all vectors retain layer association 0. A scalar may
//! opt in with {"value":0.15,"association":2}; global association 2 requires
//! index -1, e.g. "Dynamic Wind Intensity#-1". Layer 0/blend 1 require index >=0.
use serde::Deserialize;
use std::{collections::BTreeMap, path::PathBuf};
use ue_asset::{
    package::ZenPackage,
    props::{Block, Name, Val},
    Usmap,
};
#[derive(Deserialize)]
struct Entry {
    source: String,
    target: String,
    #[serde(default)]
    scalars: BTreeMap<String, Scalar>,
    #[serde(default)]
    vectors: BTreeMap<String, [f32; 4]>,
}
#[derive(Deserialize)]
#[serde(untagged)]
enum Scalar {
    Layer(f32),
    Associated(AssociatedScalar),
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AssociatedScalar {
    value: f32,
    association: u8,
}
impl Scalar {
    fn parameter(&self, key: &str) -> Result<(ParameterKey, Val), String> {
        let (value, association) = match self {
            Self::Layer(value) => (*value, 0),
            Self::Associated(value) => (value.value, value.association),
        };
        if !value.is_finite() {
            return Err(format!("{key}: scalar must be finite"));
        }
        Ok((ParameterKey::parse(key, association)?, Val::Float(value)))
    }
}
#[derive(Debug, Clone, PartialEq, Eq)]
struct ParameterKey {
    name: String,
    association: u8,
    index: i32,
}
impl ParameterKey {
    fn parse(key: &str, association: u8) -> Result<Self, String> {
        let (name, index) = key
            .rsplit_once('#')
            .ok_or_else(|| format!("{key}: expected Name#index"))?;
        let index: i32 = index
            .parse()
            .map_err(|_| format!("{key}: index must be an int32"))?;
        if name.is_empty() || !matches!((association, index), (0 | 1, 0..) | (2, -1)) {
            return Err(format!("{key}: association must be layer=0/blend=1 with index >=0, or global=2 with index -1"));
        }
        Ok(Self {
            name: name.to_string(),
            association,
            index,
        })
    }
}
fn slot(u: &Usmap, c: &str, n: &str) -> u16 {
    (0..u.total_slots(c))
        .find(|s| u.resolve(c, *s).is_some_and(|(_, p)| p.name == n))
        .expect("property schema")
}
fn key(u: &Usmap, p: &ZenPackage, b: &Block, c: &str) -> Option<ParameterKey> {
    let info = match b.get(slot(u, c, "ParameterInfo"))? {
        Val::Struct(x) => x,
        _ => return None,
    };
    let n = match info.get(slot(u, "MaterialParameterInfo", "Name"))? {
        Val::Name(n) => p.mapped_name(n.index, n.number),
        _ => return None,
    };
    // FMaterialParameterInfo constructors default to global / INDEX_NONE.
    // Omitted properties retain those defaults; a zero mask explicitly writes 0.
    let association = match info.get(slot(u, "MaterialParameterInfo", "Association")) {
        None => 2,
        Some(Val::Zeroed) => 0,
        Some(Val::Byte(value @ 0..=2)) => *value,
        _ => return None,
    };
    let index = match info.get(slot(u, "MaterialParameterInfo", "Index")) {
        Some(Val::Int(x)) => *x,
        Some(Val::Zeroed) => 0,
        None => -1,
        _ => return None,
    };
    Some(ParameterKey {
        name: n,
        association,
        index,
    })
}
fn apply(
    u: &Usmap,
    p: &mut ZenPackage,
    b: &mut Block,
    c: &str,
    array: &str,
    values: &[(ParameterKey, Val)],
) {
    let s = slot(u, "MaterialInstanceConstant", array);
    let mut entries = match b.get(s) {
        Some(Val::Array(a)) => a.clone(),
        _ => vec![],
    };
    for (k, v) in values {
        assert!(
            entries
                .iter()
                .filter(|e| matches!(e,Val::Struct(b) if key(u,p,b,c).as_ref()==Some(k)))
                .count()
                <= 1,
            "Duplicate existing parameter identity: {k:?}"
        );
        let i = entries
            .iter()
            .position(|e| matches!(e,Val::Struct(b) if key(u,p,b,c).as_ref()==Some(k)));
        if let Some(i) = i {
            if let Val::Struct(b) = &mut entries[i] {
                b.set(slot(u, c, "ParameterValue"), v.clone())
            }
        } else {
            let mut info = Block::default();
            info.set(
                slot(u, "MaterialParameterInfo", "Name"),
                Val::Name(Name {
                    index: p.names.intern(&k.name),
                    number: 0,
                }),
            );
            info.set(
                slot(u, "MaterialParameterInfo", "Association"),
                Val::Byte(k.association),
            );
            info.set(slot(u, "MaterialParameterInfo", "Index"), Val::Int(k.index));
            let mut record = Block::default();
            record.set(slot(u, c, "ParameterInfo"), Val::Struct(info));
            record.set(slot(u, c, "ParameterValue"), v.clone());
            entries.push(Val::Struct(record));
        }
    }
    b.set(s, Val::Array(entries));
}
fn verify_parameters(
    u: &Usmap,
    p: &ZenPackage,
    b: &Block,
    c: &str,
    array: &str,
    expected: &[(ParameterKey, Val)],
) {
    if expected.is_empty() {
        return;
    }
    let Some(Val::Array(entries)) = b.get(slot(u, "MaterialInstanceConstant", array)) else {
        panic!("Missing {array} readback")
    };
    for (wanted, value) in expected {
        let matches: Vec<_> = entries
            .iter()
            .filter_map(|e| match e {
                Val::Struct(record) if key(u, p, record, c).as_ref() == Some(wanted) => {
                    Some(record)
                }
                _ => None,
            })
            .collect();
        assert_eq!(
            matches.len(),
            1,
            "Parameter identity must round-trip exactly once: {wanted:?}"
        );
        assert_eq!(
            matches[0].get(slot(u, c, "ParameterValue")),
            Some(value),
            "Parameter value changed: {wanted:?}"
        );
    }
}
fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    assert_eq!(
        a.len(),
        4,
        "native_material_clone <paks> <manifest> <out-dir> <container>"
    );
    let entries: Vec<Entry> = serde_json::from_slice(&std::fs::read(&a[1]).unwrap()).unwrap();
    // Reject invalid association/index/value input before reading game containers.
    let entries: Vec<_> = entries
        .into_iter()
        .map(|entry| {
            let scalars: Vec<_> = entry
                .scalars
                .iter()
                .map(|(k, v)| v.parameter(k).expect("scalar parameter"))
                .collect();
            let vectors: Vec<_> = entry
                .vectors
                .iter()
                .map(|(k, v)| {
                    assert!(v.iter().all(|x| x.is_finite()), "Vector must be finite");
                    (
                        ParameterKey::parse(k, 0).expect("vector layer parameter"),
                        Val::Native(v.iter().flat_map(|x| x.to_le_bytes()).collect()),
                    )
                })
                .collect();
            (entry, scalars, vectors)
        })
        .collect();
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
    let mut packages = vec![];
    for (entry, scalars, vectors) in entries {
        assert!(entry.source.starts_with("/Game/Env/"));
        assert!(entry.target.starts_with("/Game/MJOLNIR/"));
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
            &scalars,
        );
        apply(
            &u,
            &mut p,
            &mut edit.block,
            "VectorParameterValue",
            "VectorParameterValues",
            &vectors,
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
        verify_parameters(
            &u,
            &check,
            &back.block,
            "ScalarParameterValue",
            "ScalarParameterValues",
            &scalars,
        );
        verify_parameters(
            &u,
            &check,
            &back.block,
            "VectorParameterValue",
            "VectorParameterValues",
            &vectors,
        );
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

#[cfg(test)]
mod tests {
    use super::*;
    use ue_asset::props;

    fn schema(name: &str) -> Usmap {
        let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../defs/ue")
            .join(name);
        Usmap::parse(&std::fs::read(path).unwrap()).unwrap()
    }
    fn package() -> ZenPackage {
        ZenPackage::bare_tag("scnr", "/Game/MJOLNIR/AssociationTest", 0)
    }
    fn record(
        u: &Usmap,
        p: &mut ZenPackage,
        association: Option<Val>,
        index: Option<Val>,
        value: f32,
    ) -> Block {
        let mut info = Block::default();
        info.set(
            slot(u, "MaterialParameterInfo", "Name"),
            Val::Name(Name {
                index: p.names.intern("Dynamic Wind Intensity"),
                number: 0,
            }),
        );
        if let Some(v) = association {
            info.set(slot(u, "MaterialParameterInfo", "Association"), v);
        }
        if let Some(v) = index {
            info.set(slot(u, "MaterialParameterInfo", "Index"), v);
        }
        let mut record = Block::default();
        record.set(
            slot(u, "ScalarParameterValue", "ParameterInfo"),
            Val::Struct(info),
        );
        record.set(
            slot(u, "ScalarParameterValue", "ParameterValue"),
            Val::Float(value),
        );
        record.set(
            slot(u, "ScalarParameterValue", "ExpressionGUID"),
            Val::Native(vec![0x51; 16]),
        );
        record
    }
    fn scalar(entry: &str, key: &str) -> (ParameterKey, Val) {
        serde_json::from_str::<Scalar>(entry)
            .unwrap()
            .parameter(key)
            .unwrap()
    }
    fn apply_scalars(u: &Usmap, p: &mut ZenPackage, b: &mut Block, v: &[(ParameterKey, Val)]) {
        apply(u, p, b, "ScalarParameterValue", "ScalarParameterValues", v);
    }

    #[test]
    fn numeric_scalar_retains_layer_zero_encoding() {
        let u = schema("Meteorite-2607-CU3.usmap");
        let mut p = package();
        let mut b = Block::default();
        let values = [scalar("0.15", "Dynamic Wind Intensity#3")];
        apply_scalars(&u, &mut p, &mut b, &values);
        let mut expected = record(&u, &mut p, Some(Val::Byte(0)), Some(Val::Int(3)), 0.15);
        expected
            .values
            .retain(|(s, _)| *s != slot(&u, "ScalarParameterValue", "ExpressionGUID"));
        let mut expected_block = Block::default();
        expected_block.set(
            slot(&u, "MaterialInstanceConstant", "ScalarParameterValues"),
            Val::Array(vec![Val::Struct(expected)]),
        );
        assert_eq!(
            b.encode(&u, "MaterialInstanceConstant").unwrap(),
            expected_block
                .encode(&u, "MaterialInstanceConstant")
                .unwrap()
        );
    }

    #[test]
    fn explicit_global_round_trips_real_stock_and_game_schemas() {
        for file in ["UE-5.5-stock.usmap", "Meteorite-2607-CU3.usmap"] {
            let u = schema(file);
            let mut p = package();
            let mut b = Block::default();
            let values = [scalar(
                r#"{"value":0.15,"association":2}"#,
                "Dynamic Wind Intensity#-1",
            )];
            apply_scalars(&u, &mut p, &mut b, &values);
            let bytes = b.encode(&u, "MaterialInstanceConstant").unwrap();
            let back = props::decode(&u, "MaterialInstanceConstant", &bytes).unwrap();
            verify_parameters(
                &u,
                &p,
                &back,
                "ScalarParameterValue",
                "ScalarParameterValues",
                &values,
            );
            let Some(Val::Array(records)) = back.get(slot(
                &u,
                "MaterialInstanceConstant",
                "ScalarParameterValues",
            )) else {
                panic!()
            };
            let Val::Struct(r) = &records[0] else {
                panic!()
            };
            let Some(Val::Struct(info)) = r.get(slot(&u, "ScalarParameterValue", "ParameterInfo"))
            else {
                panic!()
            };
            assert_eq!(
                info.get(slot(&u, "MaterialParameterInfo", "Association")),
                Some(&Val::Byte(2))
            );
            assert_eq!(
                info.get(slot(&u, "MaterialParameterInfo", "Index")),
                Some(&Val::Int(-1))
            );
            assert_eq!(back.encode(&u, "MaterialInstanceConstant").unwrap(), bytes);
        }
    }

    #[test]
    fn omitted_defaults_and_zero_masks_are_distinct() {
        let u = schema("Meteorite-2607-CU3.usmap");
        let mut p = package();
        let global = record(&u, &mut p, None, None, 1.0);
        let layer = record(&u, &mut p, Some(Val::Zeroed), Some(Val::Zeroed), 1.0);
        let mixed = record(&u, &mut p, None, Some(Val::Zeroed), 1.0);
        assert_eq!(
            key(&u, &p, &global, "ScalarParameterValue"),
            Some(ParameterKey::parse("Dynamic Wind Intensity#-1", 2).unwrap())
        );
        assert_eq!(
            key(&u, &p, &layer, "ScalarParameterValue"),
            Some(ParameterKey::parse("Dynamic Wind Intensity#0", 0).unwrap())
        );
        let k = key(&u, &p, &mixed, "ScalarParameterValue").unwrap();
        assert_eq!((k.association, k.index), (2, 0));
    }

    #[test]
    fn global_update_preserves_guid_and_other_associations() {
        let u = schema("Meteorite-2607-CU3.usmap");
        let mut p = package();
        let mut b = Block::default();
        let layer = record(&u, &mut p, Some(Val::Zeroed), Some(Val::Zeroed), 0.8);
        let blend = record(&u, &mut p, Some(Val::Byte(1)), Some(Val::Int(0)), 0.6);
        let mut global = record(&u, &mut p, None, None, 1.0);
        b.set(
            slot(&u, "MaterialInstanceConstant", "ScalarParameterValues"),
            Val::Array(vec![
                Val::Struct(layer.clone()),
                Val::Struct(blend.clone()),
                Val::Struct(global.clone()),
            ]),
        );
        let values = [scalar(
            r#"{"value":0.15,"association":2}"#,
            "Dynamic Wind Intensity#-1",
        )];
        apply_scalars(&u, &mut p, &mut b, &values);
        global.set(
            slot(&u, "ScalarParameterValue", "ParameterValue"),
            Val::Float(0.15),
        );
        assert_eq!(
            b.get(slot(
                &u,
                "MaterialInstanceConstant",
                "ScalarParameterValues"
            )),
            Some(&Val::Array(vec![
                Val::Struct(layer),
                Val::Struct(blend),
                Val::Struct(global)
            ]))
        );
        let back = props::decode(
            &u,
            "MaterialInstanceConstant",
            &b.encode(&u, "MaterialInstanceConstant").unwrap(),
        )
        .unwrap();
        verify_parameters(
            &u,
            &p,
            &back,
            "ScalarParameterValue",
            "ScalarParameterValues",
            &values,
        );
    }

    #[test]
    fn invalid_association_index_and_scalar_inputs_are_rejected() {
        for (key, association) in [
            ("Wind#0", 2),
            ("Wind#-2", 2),
            ("Wind#-1", 0),
            ("Wind#-1", 1),
            ("Wind#0", 3),
            ("#0", 0),
            ("Wind", 0),
            ("Wind#2147483648", 0),
        ] {
            assert!(
                ParameterKey::parse(key, association).is_err(),
                "{key}/{association}"
            );
        }
        for input in [
            r#"{"value":0.15,"association":256}"#,
            r#"{"value":0.15,"association":-1}"#,
            r#"{"value":0.15,"Association":2}"#,
            r#"{"value":0.15,"association":2,"index":-1}"#,
        ] {
            assert!(serde_json::from_str::<Scalar>(input).is_err());
        }
        assert!(Scalar::Layer(f32::NAN).parameter("Wind#0").is_err());
        assert!(Scalar::Layer(f32::INFINITY).parameter("Wind#0").is_err());
        assert!(ParameterKey::parse("Wind#0", 1).is_ok());
    }

    #[test]
    #[should_panic(expected = "Duplicate existing parameter identity")]
    fn duplicate_resolved_global_identity_is_rejected() {
        let u = schema("Meteorite-2607-CU3.usmap");
        let mut p = package();
        let mut b = Block::default();
        let implicit = record(&u, &mut p, None, None, 1.0);
        let explicit = record(&u, &mut p, Some(Val::Byte(2)), Some(Val::Int(-1)), 0.7);
        b.set(
            slot(&u, "MaterialInstanceConstant", "ScalarParameterValues"),
            Val::Array(vec![Val::Struct(implicit), Val::Struct(explicit)]),
        );
        apply_scalars(
            &u,
            &mut p,
            &mut b,
            &[scalar(
                r#"{"value":0.15,"association":2}"#,
                "Dynamic Wind Intensity#-1",
            )],
        );
    }
}
