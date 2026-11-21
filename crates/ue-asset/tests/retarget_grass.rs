//! Regressions against the checked-in stock/game schemas, not an invented
//! GrassVariety layout. These exercise the nested serialized property stream.
use std::path::Path;

use ue_asset::props::{self, Block, Val};
use ue_asset::retarget;
use ue_asset::usmap::{Prop, PropType, Schema, Usmap};

fn schemas() -> (Usmap, Usmap) {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../defs/ue");
    let read = |name: &str| Usmap::parse(&std::fs::read(root.join(name)).unwrap()).unwrap();
    (read("UE-5.5-stock.usmap"), read("Meteorite-2607-CU3.usmap"))
}

fn interval(min: f32, max: f32) -> Val {
    Val::Struct(Block {
        values: vec![(0, Val::Float(min)), (1, Val::Float(max))],
    })
}

fn quality(default_bits: u32, pairs: &[(i32, u32)]) -> Val {
    let mut bytes = [
        1_u32.to_le_bytes(),
        default_bits.to_le_bytes(),
        (pairs.len() as u32).to_le_bytes(),
    ]
    .concat();
    for (key, bits) in pairs {
        bytes.extend(key.to_le_bytes());
        bytes.extend(bits.to_le_bytes());
    }
    Val::Native(bytes)
}

fn grass_type() -> Block {
    let varieties = [(0.5, 0.65), (0.75, 0.9), (0.6, 0.8)]
        .into_iter()
        .enumerate()
        .map(|(i, (min, max))| {
            // PerPlatformFloat has native serialization (cooked bool + float).
            let density = [1_u32.to_le_bytes(), (123.5_f32 + i as f32).to_le_bytes()].concat();
            Val::Struct(Block {
                values: vec![
                    (0, Val::Object(-2 - i as i32)),
                    (2, Val::Native(density)),
                    (
                        3,
                        quality(
                            (123.5_f32 + i as f32).to_bits(),
                            &[(0, 12.5_f32.to_bits()), (3, 87.25_f32.to_bits())],
                        ),
                    ),
                    (4, Val::Bool(true)),
                    (5, Val::Float(0.875)),
                    (7, quality(4000, &[])),
                    (9, quality(6000, &[(0, 2000), (3, 6000)])),
                    (10, Val::Int(2 + i as i32)),
                    (11, interval(0.125, 0.9375)),
                    (12, Val::Byte(2)),
                    (13, interval(min, max)),
                    (14, interval(min + 0.125, max + 0.25)),
                    (15, interval(min + 0.5, max + 0.75)),
                    (18, Val::Bool(true)),
                    (26, Val::Bool(true)),
                    (27, Val::UInt32(24680 + i as u32)),
                    (28, Val::Byte(2)),
                ],
            })
        })
        .collect();
    Block {
        values: vec![
            (0, Val::Array(varieties)),
            (1, Val::Bool(true)),
            (2, Val::UInt32(0x81234567)),
        ],
    }
}

#[test]
fn actual_nested_grass_intervals_lod_and_shifted_fields_round_trip() {
    let (stock, game) = schemas();
    assert_eq!(stock.structs["GrassVariety"].prop_count, 29);
    assert_eq!(game.structs["GrassVariety"].prop_count, 31);
    for (map, class, slot, name, ty) in [
        (&stock, "GrassVariety", 10, "MinLod", PropType::Int),
        (&game, "GrassVariety", 10, "MinLOD", PropType::Int),
        (&stock, "FloatInterval", 0, "Min", PropType::Float),
        (&stock, "FloatInterval", 1, "MAX", PropType::Float),
        (&game, "FloatInterval", 0, "min", PropType::Float),
        (&game, "FloatInterval", 1, "max", PropType::Float),
        (
            &game,
            "GrassVariety",
            27,
            "bDisableWorldPositionOffsetForShadowRendering",
            PropType::Bool,
        ),
        (
            &game,
            "GrassVariety",
            29,
            "InstanceVSMInvalidationDisableDistance",
            PropType::Int,
        ),
    ] {
        let prop = map.structs[class].prop_at(slot).unwrap();
        assert_eq!(prop.name, name);
        assert_eq!(prop.ty, ty);
    }

    let original = grass_type();
    let stock_bytes = original.encode(&stock, "LandscapeGrassType").unwrap();
    let decoded_stock = props::decode(&stock, "LandscapeGrassType", &stock_bytes).unwrap();
    assert_eq!(decoded_stock, original);
    let mut notes = Vec::new();
    let translated = retarget::block(
        &stock,
        &game,
        "LandscapeGrassType",
        "LandscapeGrassType",
        &decoded_stock,
        "Grass",
        &mut notes,
    );
    assert!(notes.is_empty(), "unexpected losses: {notes:?}");
    let game_bytes = translated.encode(&game, "LandscapeGrassType").unwrap();
    let decoded_game = props::decode(&game, "LandscapeGrassType", &game_bytes).unwrap();

    let mut expected = original.clone();
    let Val::Array(varieties) = &mut expected.values[0].1 else {
        panic!("array")
    };
    for item in varieties {
        let Val::Struct(variety) = item else {
            panic!("struct")
        };
        for (slot, _) in &mut variety.values {
            *slot = match *slot {
                27 => 28,
                28 => 30,
                other => other,
            };
        }
        // The two game-only fields must stay absent and use native defaults.
        assert!(variety.get(27).is_none());
        assert!(variety.get(29).is_none());
    }
    assert_eq!(decoded_game, expected);

    let restored = retarget::block(
        &game,
        &stock,
        "LandscapeGrassType",
        "LandscapeGrassType",
        &decoded_game,
        "Grass",
        &mut notes,
    );
    assert!(notes.is_empty(), "unexpected reverse losses: {notes:?}");
    assert_eq!(restored, original);
    assert_eq!(
        restored.encode(&stock, "LandscapeGrassType").unwrap(),
        stock_bytes
    );
}

fn single_schema(class: &str, properties: &[(&str, PropType)]) -> Usmap {
    let mut map = Usmap::default();
    map.structs.insert(
        class.into(),
        Schema {
            name: class.into(),
            super_name: None,
            prop_count: properties.len() as u16,
            props: properties
                .iter()
                .enumerate()
                .map(|(i, (name, ty))| Prop {
                    schema_index: i as u16,
                    array_dim: 1,
                    name: (*name).into(),
                    ty: ty.clone(),
                })
                .collect(),
        },
    );
    map
}

#[test]
fn aliases_do_not_generalize_to_unconfirmed_names_or_structs() {
    for (from_class, to_class, source, dest) in [
        ("OtherInterval", "OtherInterval", "Min", "min"),
        ("FloatInterval", "OtherInterval", "Min", "min"),
        ("FloatInterval", "FloatInterval", "Max", "max"),
        ("GrassVariety", "GrassVariety", "MinLOD", "minlod"),
    ] {
        let from = single_schema(from_class, &[(source, PropType::Float)]);
        let to = single_schema(to_class, &[(dest, PropType::Float)]);
        let mut notes = Vec::new();
        let output = retarget::block(
            &from,
            &to,
            from_class,
            to_class,
            &Block {
                values: vec![(0, Val::Float(0.625))],
            },
            "Probe",
            &mut notes,
        );
        assert!(output.values.is_empty());
        assert_eq!(notes.len(), 1);
        assert!(notes[0].contains("not in the game's layout; dropped"));
    }
}

#[test]
fn exact_names_take_precedence_and_aliases_keep_type_checks() {
    let from = single_schema("FloatInterval", &[("Min", PropType::Float)]);
    let source = Block {
        values: vec![(0, Val::Float(0.625))],
    };
    let to = single_schema(
        "FloatInterval",
        &[("min", PropType::Float), ("Min", PropType::Float)],
    );
    let mut notes = Vec::new();
    let exact = retarget::block(
        &from,
        &to,
        "FloatInterval",
        "FloatInterval",
        &source,
        "Probe",
        &mut notes,
    );
    assert_eq!(exact.values, vec![(1, Val::Float(0.625))]);
    assert!(notes.is_empty());

    let incompatible = single_schema("FloatInterval", &[("min", PropType::Int)]);
    let rejected = retarget::block(
        &from,
        &incompatible,
        "FloatInterval",
        "FloatInterval",
        &source,
        "Probe",
        &mut notes,
    );
    assert!(rejected.values.is_empty());
    assert_eq!(notes.len(), 1);
    assert!(notes[0].contains("Float in stock, Int in the game; dropped"));
}

#[test]
fn game_only_grass_fields_are_reported_when_translating_to_stock() {
    let (stock, game) = schemas();
    let source = Block {
        values: vec![
            (10, Val::Int(3)),
            (27, Val::Bool(true)),
            (28, Val::UInt32(12345)),
            (29, Val::Int(67890)),
            (30, Val::Byte(2)),
        ],
    };
    let encoded = source.encode(&game, "GrassVariety").unwrap();
    let decoded = props::decode(&game, "GrassVariety", &encoded).unwrap();
    let mut notes = Vec::new();
    let output = retarget::block(
        &game,
        &stock,
        "GrassVariety",
        "GrassVariety",
        &decoded,
        "Grass",
        &mut notes,
    );
    assert_eq!(
        output.values,
        vec![
            (10, Val::Int(3)),
            (27, Val::UInt32(12345)),
            (28, Val::Byte(2))
        ]
    );
    assert_eq!(notes.len(), 2);
    assert!(notes[0].contains("bDisableWorldPositionOffsetForShadowRendering"));
    assert!(notes[1].contains("InstanceVSMInvalidationDisableDistance"));
    let stock_bytes = output.encode(&stock, "GrassVariety").unwrap();
    assert_eq!(
        props::decode(&stock, "GrassVariety", &stock_bytes).unwrap(),
        output
    );
}

#[test]
fn native_quality_serialization_preserves_empty_and_nonempty_maps_and_following_values() {
    for name in ["PerQualityLevelInt", "PerQualityLevelFloat"] {
        let map = single_schema(
            "Probe",
            &[
                ("Quality", PropType::Struct(name.into())),
                ("Sentinel", PropType::Int),
            ],
        );
        for (bits, pairs) in [
            (6000_u32, vec![]),
            (
                16.666666_f32.to_bits(),
                vec![(0, 4000_u32), (3, 125_f32.to_bits())],
            ),
        ] {
            let original = Block {
                values: vec![(0, quality(bits, &pairs)), (1, Val::Int(-1234567))],
            };
            let bytes = original.encode(&map, "Probe").unwrap();
            let decoded = props::decode(&map, "Probe", &bytes).unwrap();
            assert_eq!(decoded, original);
            assert_eq!(decoded.encode(&map, "Probe").unwrap(), bytes);
        }
    }
}

#[test]
fn native_quality_decodes_the_actual_archive_wire_layout() {
    for name in ["PerQualityLevelInt", "PerQualityLevelFloat"] {
        let map = single_schema(
            "Probe",
            &[
                ("Quality", PropType::Struct(name.into())),
                ("Sentinel", PropType::Int),
            ],
        );
        // One unversioned run with two values, then the custom serializer's
        // cooked bool/default/count/pairs bytes and an adjacent integer.
        let mut bytes = 0x0500_u16.to_le_bytes().to_vec();
        for bits in [
            1_u32,
            125_f32.to_bits(),
            2,
            0,
            25_f32.to_bits(),
            3,
            16.666666_f32.to_bits(),
            0x12345678,
        ] {
            bytes.extend(bits.to_le_bytes());
        }
        let decoded = props::decode(&map, "Probe", &bytes).unwrap();
        assert_eq!(decoded.get(0), Some(&Val::Native(bytes[2..30].to_vec())));
        assert_eq!(decoded.get(1), Some(&Val::Int(0x12345678)));
        assert_eq!(decoded.encode(&map, "Probe").unwrap(), bytes);
    }
}

#[test]
fn native_quality_rejects_truncation_bad_counts_and_reflected_values() {
    for name in ["PerQualityLevelInt", "PerQualityLevelFloat"] {
        let map = single_schema("Probe", &[("Quality", PropType::Struct(name.into()))]);
        let mut encoded = 0x0300_u16.to_le_bytes().to_vec();
        for bits in [1_u32, 6000, 1, 3, 4000] {
            encoded.extend(bits.to_le_bytes());
        }
        for end in 2..encoded.len() {
            assert!(
                props::decode(&map, "Probe", &encoded[..end]).is_err(),
                "accepted truncation at {end}"
            );
        }
        encoded[10..14].copy_from_slice(&u32::MAX.to_le_bytes());
        assert!(props::decode(&map, "Probe", &encoded).is_err());
        for bytes in [
            vec![],
            vec![0; 11],
            [
                1_u32.to_le_bytes(),
                6000_u32.to_le_bytes(),
                1_u32.to_le_bytes(),
            ]
            .concat(),
            [
                1_u32.to_le_bytes(),
                6000_u32.to_le_bytes(),
                0_u32.to_le_bytes(),
                123_u32.to_le_bytes(),
            ]
            .concat(),
        ] {
            assert!(Block {
                values: vec![(0, Val::Native(bytes))]
            }
            .encode(&map, "Probe")
            .is_err());
        }
        assert!(Block {
            values: vec![(0, Val::Struct(Block::default()))]
        }
        .encode(&map, "Probe")
        .is_err());
    }
}
