//! The census as `run_census` judges it — masked prints, ties carried, every
//! candidate put through `blam_live::accept` — against the running game.
//! Reports what it found by group and checks the two weapons whose working
//! copies were verified by hand (a zoom written through them moved the HUD).
//! Ignored: needs the game in a30 with the magnum and assault rifle in play,
//! and `MJOLNIR_PAKS`.

use std::collections::BTreeMap;

use tag_editor_lib::{catalog::Catalog, census};

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS"]
fn census_finds_working_copies() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let process = blam_live::Process::attach().expect("game running");

    let t0 = std::time::Instant::now();
    let prints = census::table(&catalog);
    let masked = prints.iter().filter(|p| !p.masks.is_empty()).count();
    eprintln!("prints: {} ({masked} masked) in {:.1?}", prints.len(), t0.elapsed());
    let table: Vec<blam_live::Print> = prints
        .iter()
        .map(|p| blam_live::Print {
            id: p.index,
            runs: p.runs.clone(),
            masks: p.masks.clone(),
        })
        .collect();
    let t1 = std::time::Instant::now();
    let outcome = blam_live::census(&process, &table, &|_, _| {}).expect("census");
    eprintln!(
        "census: {} hits, {} with rivals, {:.1} GB in {:.1?}",
        outcome.hits.len(),
        outcome.ambiguous,
        outcome.scanned as f64 / 1e9,
        t1.elapsed()
    );
    let by_id: std::collections::HashMap<u32, &census::TagPrint> =
        prints.iter().map(|p| (p.index, p)).collect();

    let judge = |index: usize, bases: &[u64]| -> Option<(u64, f32)> {
        let print = by_id.get(&(index as u32))?;
        let payload = catalog.read_tag(index).ok()?;
        let tag = blam_tag::TagFile::parse(&payload, Some(payload.len())).ok()?;
        let layout = tag.layout().ok()?;
        let block = tag.read_data(&layout).ok()?;
        let stable = blam_tag::view::scalar_mask(&layout, &block, &payload);
        let headers: Vec<usize> = blam_tag::patch::root_blocks(&layout, &payload, &block)
            .iter()
            .filter(|(_, n)| *n > 0)
            .map(|(h, _)| h.header)
            .collect();
        let shape = blam_live::Shape {
            region: print.region.clone(),
            root: print.root.clone(),
            stable: &stable,
            headers: &headers,
        };
        let mut best: Option<(u64, f32)> = None;
        for &base in bases {
            if !blam_live::accept(&process, &payload, &shape, base) {
                continue;
            }
            let f = blam_live::score(&process, &payload, &shape, base);
            if best.is_none_or(|(_, bf)| f > bf) {
                best = Some((base, f));
            }
        }
        best
    };

    let t2 = std::time::Instant::now();
    let mut groups: BTreeMap<String, usize> = BTreeMap::new();
    let mut weapons: Vec<(String, u64, f32)> = Vec::new();
    let mut unresolved = 0;
    for hit in &outcome.hits {
        let index = hit.id as usize;
        let mut bases = vec![hit.base];
        bases.extend(&hit.rivals);
        match judge(index, &bases) {
            Some((base, f)) => {
                let e = catalog.entry(index).unwrap();
                *groups.entry(e.group.clone()).or_default() += 1;
                if e.group == "weapon" || e.group == "biped" {
                    weapons.push((format!("{}/{}", e.group, e.short), base, f));
                }
            }
            None if !hit.rivals.is_empty() => unresolved += 1,
            None => {}
        }
    }
    eprintln!("judged in {:.1?}; unresolved ties {unresolved}", t2.elapsed());
    eprintln!("verified by group: {groups:?}");
    for (s, b, f) in &weapons {
        eprintln!("  {s:<70} {b:#x} {:.0}%", f * 100.0);
    }
    let magnum = weapons.iter().find(|(s, _, _)| s.contains("magnum/magnum"));
    let ar = weapons.iter().find(|(s, _, _)| s.contains("assault_rifle/assault_rifle"));
    eprintln!("magnum {magnum:x?}  assault rifle {ar:x?}");
}
