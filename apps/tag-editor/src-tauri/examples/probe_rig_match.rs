//! Can a vehicle's bone-local rig statics be assembled onto its SK reference
//! skeleton by name? Prints the piece-to-bone match table and the assembled
//! bounds, which should come out vehicle-shaped.
//!
//!   cargo run --release --example probe_rig_match -- "Vehicles/human/warthog/Mesh/SK_Warthog_01"
use tag_editor_lib::catalog::Catalog;
use tag_editor_lib::install;
use ue_asset::unversioned::Ctx;

fn quat_mul(a: [f64; 4], b: [f64; 4]) -> [f64; 4] {
    [
        a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1],
        a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
        a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3],
        a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2],
    ]
}

fn rotate(q: [f64; 4], v: [f64; 3]) -> [f64; 3] {
    let p = [v[0], v[1], v[2], 0.0];
    let qc = [-q[0], -q[1], -q[2], q[3]];
    let r = quat_mul(quat_mul(q, p), qc);
    [r[0], r[1], r[2]]
}

fn main() -> Result<(), String> {
    let sk_q = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "Vehicles/human/warthog/Mesh/SK_Warthog_01".into())
        .to_lowercase();
    let usmap_bytes = std::fs::read("../../../defs/ue/Meteorite-2607-CU3.usmap").map_err(|e| e.to_string())?;
    let usmap = ue_asset::Usmap::parse(&usmap_bytes).map_err(|e| e.to_string())?;
    let found = install::detect();
    let (paks, oodle) = (found.paks.unwrap(), found.oodle.unwrap());
    let catalog = Catalog::open(&paks, &oodle)?;
    let scripts = catalog.script_objects().ok_or("no scripts")?;

    let ski = catalog
        .meshes
        .iter()
        .position(|m| m.skeletal && m.short.to_lowercase() == sk_q)
        .or_else(|| {
            catalog
                .meshes
                .iter()
                .position(|m| m.skeletal && m.short.to_lowercase().contains(&sk_q))
        })
        .ok_or("no SK matched")?;
    let sk_short = catalog.meshes[ski].short.clone();
    println!("SK: {sk_short}");

    let data = catalog.read_mesh_uasset(ski)?;
    let ubulk = catalog.read_mesh_ubulk(ski)?;
    let package = ue_asset::zen::Package::parse(&data).map_err(|e| e.to_string())?;
    let export = package
        .exports
        .iter()
        .position(|e| scripts.leaf(e.class) == Some("SkeletalMesh"))
        .ok_or("no SkeletalMesh export")?;
    let bytes = package.export_data(&data, export).map_err(|e| e.to_string())?;
    let ctx = Ctx { usmap: &usmap, names: &package.names };
    let sk = ue_asset::mesh::parse_skeletal_mesh(&ctx, bytes, ubulk.as_deref()).map_err(|e| e.to_string())?;

    // Rest-pose world transform per bone.
    let mut world: Vec<([f64; 3], [f64; 4])> = Vec::new();
    for (i, b) in sk.bones.iter().enumerate() {
        let t = [
            b.translation[0] as f64,
            b.translation[1] as f64,
            b.translation[2] as f64,
        ];
        let q = [
            b.rotation[0] as f64,
            b.rotation[1] as f64,
            b.rotation[2] as f64,
            b.rotation[3] as f64,
        ];
        let p = b.parent;
        let w = if p >= 0 && (p as usize) < i {
            let (pt, pq) = world[p as usize];
            let rt = rotate(pq, t);
            ([pt[0] + rt[0], pt[1] + rt[1], pt[2] + rt[2]], quat_mul(pq, q))
        } else {
            (t, q)
        };
        world.push(w);
    }
    println!("bones: {}", sk.bones.len());
    for b in &sk.bones {
        print!("{} ", b.name);
    }
    println!();

    // Rig statics: the SK's sibling Static folder.
    let sk_dir = sk_short.rsplit_once('/').map(|(d, _)| d).unwrap_or("");
    let static_dir = format!("{}/static/", sk_dir.to_lowercase());
    println!("\nstatics under {static_dir}:");
    let mut assembled_lo = [f64::MAX; 3];
    let mut assembled_hi = [f64::MIN; 3];
    let mut matched = 0;
    let mut unmatched = 0;
    for mi in 0..catalog.meshes.len() {
        let m = &catalog.meshes[mi];
        if m.skeletal {
            continue;
        }
        let lower = m.short.to_lowercase();
        if !lower.starts_with(&static_dir) || lower[static_dir.len()..].contains('/') {
            continue;
        }
        let tail = m.short.rsplit('/').next().unwrap_or(&m.short);
        if tail.to_lowercase().contains("damaged") {
            continue;
        }
        // Piece name to bone. The piece is SM_<Thing>_<BoneName> with loose
        // spelling: word order swaps (Base_Axle vs Axle_Base), missing
        // underscores (SteeringArm), synonyms (Tire vs Wheel). So: tokens of
        // ever-shorter suffixes, synonym-mapped, matched as a set; then as a
        // subset when exactly one bone qualifies.
        let tokens = |s: &str| -> Vec<String> {
            let mut out = Vec::new();
            let mut cur = String::new();
            for c in s.chars() {
                if c == '_' || (c.is_ascii_uppercase() && !cur.is_empty() && !cur.ends_with(|p: char| p.is_ascii_uppercase())) {
                    if !cur.is_empty() {
                        out.push(std::mem::take(&mut cur).to_lowercase());
                    }
                    if c != '_' {
                        cur.push(c);
                    }
                } else if c != '_' {
                    cur.push(c);
                }
            }
            if !cur.is_empty() {
                out.push(cur.to_lowercase());
            }
            let mut mapped = Vec::new();
            for t in out {
                match t.as_str() {
                    "tire" => mapped.push("wheel".into()),
                    "upper" => mapped.push("up".into()),
                    "lower" => mapped.push("down".into()),
                    "ebrake" => {
                        mapped.push("emergency".into());
                        mapped.push("brake".into());
                    }
                    _ => mapped.push(t),
                }
            }
            mapped.sort();
            mapped
        };
        // Canonical key: sorted tokens joined, so BackRest == Backrest.
        let canon = |ts: &[String]| ts.concat();
        let bone_sets: Vec<Vec<String>> = sk.bones.iter().map(|b| tokens(&b.name)).collect();
        let bone_keys: Vec<String> = bone_sets.iter().map(|t| canon(t)).collect();
        let parts: Vec<&str> = tail.split('_').collect();
        let mut bone_hit: Option<usize> = None;
        'outer: for start in 1..parts.len() {
            let cand = tokens(&parts[start..].join("_"));
            if cand.is_empty() {
                continue;
            }
            let key = canon(&cand);
            if let Some(bi) = bone_keys.iter().position(|b| *b == key) {
                bone_hit = Some(bi);
                break 'outer;
            }
            // Subset match, when exactly one bone qualifies.
            let subs: Vec<usize> = bone_sets
                .iter()
                .enumerate()
                .filter(|(_, b)| cand.iter().all(|t| b.contains(t)))
                .map(|(i, _)| i)
                .collect();
            if subs.len() == 1 {
                bone_hit = Some(subs[0]);
                break 'outer;
            }
        }
        // Everything the rig does not name sits in the chassis frame: the
        // Blam collision attaches panels, windshield and accessories to the
        // hull node, whose UE bone is Body.
        if bone_hit.is_none() {
            bone_hit = sk.bones.iter().position(|b| b.name == "Body");
        }
        match bone_hit {
            Some(bi) => {
                matched += 1;
                let (bt, bq) = world[bi];
                // Piece bounds through the bone transform.
                let ok = (|| -> Option<()> {
                    let data = catalog.read_mesh_uasset(mi).ok()?;
                    let ubulk = catalog.read_mesh_ubulk(mi).ok()?;
                    let package = ue_asset::zen::Package::parse(&data).ok()?;
                    let export = package
                        .exports
                        .iter()
                        .position(|e| scripts.leaf(e.class) == Some("StaticMesh"))?;
                    let bytes = package.export_data(&data, export).ok()?;
                    let ctx = Ctx { usmap: &usmap, names: &package.names };
                    let mesh = ue_asset::mesh::parse_static_mesh(&ctx, bytes, ubulk.as_deref()).ok()?;
                    let lod = mesh.lods.iter().find(|l| !l.indices.is_empty())?;
                    for v in lod.positions.chunks(3) {
                        let p = rotate(bq, [v[0] as f64, v[1] as f64, v[2] as f64]);
                        let p = [p[0] + bt[0], p[1] + bt[1], p[2] + bt[2]];
                        for a in 0..3 {
                            assembled_lo[a] = assembled_lo[a].min(p[a]);
                            assembled_hi[a] = assembled_hi[a].max(p[a]);
                        }
                    }
                    Some(())
                })();
                println!(
                    "  {tail} -> bone {} at ({:.0} {:.0} {:.0}){}",
                    sk.bones[bi].name,
                    bt[0],
                    bt[1],
                    bt[2],
                    if ok.is_none() { "  [unreadable]" } else { "" }
                );
            }
            None => {
                unmatched += 1;
                println!("  {tail} -> NO BONE");
            }
        }
    }
    println!("\nmatched {matched}, unmatched {unmatched}");
    println!(
        "assembled bounds: ({:.0} {:.0} {:.0})..({:.0} {:.0} {:.0}) size [{:.0}, {:.0}, {:.0}] cm",
        assembled_lo[0], assembled_lo[1], assembled_lo[2],
        assembled_hi[0], assembled_hi[1], assembled_hi[2],
        assembled_hi[0] - assembled_lo[0],
        assembled_hi[1] - assembled_lo[1],
        assembled_hi[2] - assembled_lo[2]
    );
    Ok(())
}
