//! The grammar-driven codec (`blam_megalo::raw`) against real variants:
//! decode, encode, and compare with the original bits.
//!
//! Bungie's own Halo Reach variants (the ground truth for this engine
//! lineage) are read from an MCC install when `MCC_REACH` names its
//! `haloreach` folder; without it those tests pass without checking.

use std::path::{Path, PathBuf};

use blam_megalo::{blf, raw, Variant};

/// Round trip one `.mglo` stream; the bits after the variant must be zero.
fn check_mglo(bytes: &[u8]) -> Result<raw::RoundTrip, String> {
    let rt = raw::round_trip(bytes, 0, &[]).map_err(|e| e.to_string())?;
    if rt.trailing_ones != 0 {
        return Err(format!(
            "{} set bit(s) in the {} after the variant",
            rt.trailing_ones, rt.trailing_bits
        ));
    }
    Ok(rt)
}

#[test]
fn mjolnir_variants_round_trip() {
    let ctf = blam_megalo::ctf::Ctf {
        flag_type: 18,
        blue_flag_type: Some(20),
        score_to_win: 3,
        reset_ticks: 900,
        debug: false,
    };
    let health = blam_megalo::powerups::HealthPacks {
        object_type: 19,
        respawn_ticks: 900,
        reach_feet: 8,
    };
    let variants = [
        ("empty", Variant::empty(25)),
        ("slayer", Variant::slayer(25)),
        ("slayer+time", Variant::slayer(25).with_time_limit()),
        ("tick", Variant::tick(25)),
        ("ctf", Variant::ctf(ctf)),
        (
            "ctf+health",
            Variant::ctf(ctf)
                .with_time_limit()
                .with_health_packs(health)
                .unwrap(),
        ),
        (
            "slayer+health",
            Variant::slayer(25).with_health_packs(health).unwrap(),
        ),
    ];
    for (name, v) in variants {
        let bytes = v.write().unwrap();
        let rt = check_mglo(&bytes).unwrap_or_else(|e| panic!("{name}: {e}"));
        assert!(
            rt.trailing_bits < 8,
            "{name}: {} bits left",
            rt.trailing_bits
        );
    }
}

fn mglo_files(dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(rd) = std::fs::read_dir(dir) else {
        return;
    };
    for e in rd.flatten() {
        let p = e.path();
        if p.is_dir() {
            mglo_files(&p, out);
        } else if p.extension().is_some_and(|x| x == "mglo") {
            out.push(p);
        }
    }
}

/// The variants under `tools/tests/fixtures` (written by `megalo write`).
#[test]
fn fixture_variants_round_trip() {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tools/tests/fixtures");
    let mut files = Vec::new();
    mglo_files(&dir, &mut files);
    files.sort();
    assert!(
        !files.is_empty(),
        "no .mglo fixtures under {}",
        dir.display()
    );
    for f in files {
        let bytes = std::fs::read(&f).unwrap();
        check_mglo(&bytes).unwrap_or_else(|e| panic!("{}: {e}", f.display()));
    }
}

/// Every Megalo variant MCC ships for Reach, bit for bit.
#[test]
fn bungie_reach_variants_round_trip() {
    let Ok(root) = std::env::var("MCC_REACH") else {
        eprintln!("MCC_REACH not set: Bungie's variants not checked");
        return;
    };
    let mut total = 0;
    let mut skipped = Vec::new();
    let mut failures = Vec::new();
    for sub in ["game_variants", "hopper_game_variants"] {
        let dir = Path::new(&root).join(sub);
        let mut files: Vec<PathBuf> = std::fs::read_dir(&dir)
            .unwrap_or_else(|e| panic!("{}: {e}", dir.display()))
            .flatten()
            .map(|e| e.path())
            .filter(|p| p.extension().is_some_and(|x| x == "bin"))
            .collect();
        files.sort();
        for f in files {
            let name = format!("{sub}/{}", f.file_name().unwrap().to_string_lossy());
            let bytes = std::fs::read(&f).unwrap();
            let v = match blf::game_variant(&bytes) {
                Ok(v) => v,
                Err(e) => {
                    failures.push(format!("{name}: {e}"));
                    continue;
                }
            };
            if v.engine != blf::ENGINE_MEGALO {
                skipped.push(format!("{name} ({})", blf::engine_name(v.engine)));
                continue;
            }
            total += 1;
            match raw::round_trip(v.payload, 4, &[(u64::from(v.engine), 4)]) {
                Ok(rt) if rt.trailing_ones != 0 => failures.push(format!(
                    "{name}: {} set bit(s) in the {} after the variant",
                    rt.trailing_ones, rt.trailing_bits
                )),
                Ok(rt) if rt.trailing_bits >= 8 => failures.push(format!(
                    "{name}: {} bits left after the variant",
                    rt.trailing_bits
                )),
                Ok(_) => {}
                Err(e) => failures.push(format!("{name}: {e}")),
            }
        }
    }
    eprintln!(
        "{total} Megalo variant(s), {} failed; {} other engine(s) skipped",
        failures.len(),
        skipped.len()
    );
    for s in &skipped {
        eprintln!("  skipped {s}");
    }
    for f in &failures {
        eprintln!("  FAIL {f}");
    }
    assert!(total > 0, "no Megalo variants under {root}");
    assert!(failures.is_empty(), "{} of {total} failed", failures.len());
}

/// Every map variant MCC ships for Reach, bit for bit.
#[test]
fn bungie_reach_map_variants_round_trip() {
    let Ok(root) = std::env::var("MCC_REACH") else {
        eprintln!("MCC_REACH not set: Bungie's map variants not checked");
        return;
    };
    let mut total = 0;
    let mut failures = Vec::new();
    for sub in ["map_variants", "hopper_map_variants"] {
        let dir = Path::new(&root).join(sub);
        let mut files: Vec<PathBuf> = std::fs::read_dir(&dir)
            .unwrap_or_else(|e| panic!("{}: {e}", dir.display()))
            .flatten()
            .map(|e| e.path())
            .filter(|p| p.extension().is_some_and(|x| x == "mvar"))
            .collect();
        files.sort();
        for f in files {
            let name = format!("{sub}/{}", f.file_name().unwrap().to_string_lossy());
            let bytes = std::fs::read(&f).unwrap();
            total += 1;
            let mv = match blf::map_variant(&bytes) {
                Ok(v) => v,
                Err(e) => {
                    failures.push(format!("{name}: {e}"));
                    continue;
                }
            };
            match raw::round_trip_map_variant(mv.payload) {
                Ok(rt) if rt.trailing_ones != 0 => failures.push(format!(
                    "{name}: {} set bit(s) in the {} after the map variant",
                    rt.trailing_ones, rt.trailing_bits
                )),
                Ok(rt) if rt.trailing_bits >= 8 => failures.push(format!(
                    "{name}: {} bits left after the map variant",
                    rt.trailing_bits
                )),
                Ok(_) => {}
                Err(e) => failures.push(format!("{name}: {e}")),
            }
        }
    }
    assert!(total > 0, "no .mvar files under {root}");
    assert!(
        failures.is_empty(),
        "{} of {total} map variants failed:\n{}",
        failures.len(),
        failures.join("\n")
    );
    eprintln!("{total} map variants round-trip");
}
