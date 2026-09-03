//! Which bytes of a resident tag survive the engine's rewrite, by field type?
//!
//! The 48-byte-run locator assumes stretches of the data section survive
//! byte-for-byte. For the magnum nothing did, and the locator settled on a
//! shared section tail somewhere else. Before building a locator that keys
//! on the fields the engine leaves alone, measure — on the tags the census
//! *does* find — which field types survive and which are rewritten.
//! Ignored: needs the game in a mission and `MJOLNIR_PAKS`.

use std::collections::BTreeMap;

use tag_editor_lib::{catalog::Catalog, census};

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS"]
fn survival_by_field_type() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let process = blam_live::Process::attach().expect("game running");

    let t0 = std::time::Instant::now();
    let prints = census::table(&catalog);
    eprintln!("prints: {} in {:.1?}", prints.len(), t0.elapsed());
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
        "census: {} hits, {} ambiguous, {:.1} GB in {:.1?}",
        outcome.hits.len(),
        outcome.ambiguous,
        outcome.scanned as f64 / 1e9,
        t1.elapsed()
    );
    let by_id: std::collections::HashMap<u32, &census::TagPrint> =
        prints.iter().map(|p| (p.index, p)).collect();

    // Verified hits, grouped.
    let mut groups: BTreeMap<String, usize> = BTreeMap::new();
    let mut weapons: Vec<(usize, u64, f32)> = Vec::new();
    let mut sample: Vec<(usize, u64, f32)> = Vec::new();
    for hit in &outcome.hits {
        let index = hit.id as usize;
        let (Some(print), Some(entry), Ok(payload)) = (
            by_id.get(&hit.id),
            catalog.entry(index),
            catalog.read_tag(index),
        ) else {
            continue;
        };
        let fraction = blam_live::verify(&process, &payload, &print.region, hit.base);
        if fraction <= 0.10 {
            continue;
        }
        *groups.entry(entry.group.clone()).or_default() += 1;
        if entry.group == "weapon" {
            weapons.push((index, hit.base, fraction));
        }
        if matches!(
            entry.group.as_str(),
            "biped" | "vehicle" | "projectile" | "damage_effect" | "equipment"
        ) && sample.len() < 6
        {
            sample.push((index, hit.base, fraction));
        }
    }
    eprintln!("verified by group: {groups:?}");
    eprintln!("weapons found: {}", weapons.len());
    for (i, b, f) in &weapons {
        eprintln!("  {:<60} {b:#x} {:.1}%", catalog.entry(*i).unwrap().short, f * 100.0);
    }

    // Field-type survival on the found weapons (and a few others for contrast).
    let mut all: BTreeMap<String, (usize, usize)> = BTreeMap::new();
    for (index, base, _) in weapons.iter().chain(sample.iter()).take(10) {
        let entry = catalog.entry(*index).unwrap();
        let file = catalog.read_tag(*index).unwrap();
        let tag = blam_tag::TagFile::parse(&file, Some(file.len())).unwrap();
        let layout = tag.layout().unwrap();
        let block = tag.read_data(&layout).unwrap();
        let data = tag.data().unwrap();
        let r0 = data.content.as_ptr() as usize - file.as_ptr() as usize;
        let r1 = r0 + data.content.len();
        let Ok(live) = process.read(*base + r0 as u64, r1 - r0) else {
            continue;
        };
        eprintln!("== {} / {}  base {base:#x}  data {r0:#x}..{r1:#x}", entry.group, entry.short);

        // 32-byte identity map.
        let mut map = String::new();
        for (i, chunk) in live.chunks(32).enumerate() {
            let f = &file[r0 + i * 32..(r0 + i * 32 + chunk.len()).min(r1)];
            let same = chunk.iter().zip(f).filter(|(a, b)| a == b).count();
            map.push(if same == chunk.len() {
                '#'
            } else if same * 2 >= chunk.len() {
                '+'
            } else if same > 0 {
                '.'
            } else {
                ' '
            });
        }
        for (i, line) in map.as_bytes().chunks(96).enumerate() {
            eprintln!("{:#06x} |{}|", r0 + i * 96 * 32, std::str::from_utf8(line).unwrap());
        }

        let mut per: BTreeMap<String, (usize, usize)> = BTreeMap::new();
        let mut changed: Vec<String> = Vec::new();
        blam_tag::view::visit_fields(&layout, &block, &mut |field, bytes| {
            if bytes.is_empty() {
                return;
            }
            let off = bytes.as_ptr() as usize - file.as_ptr() as usize;
            if off < r0 || off + bytes.len() > r1 {
                return;
            }
            let ty = layout.type_name_of(field).to_string();
            let l = &live[off - r0..off - r0 + bytes.len()];
            let same = l == bytes;
            let e = per.entry(ty.clone()).or_default();
            e.0 += 1;
            if same {
                e.1 += 1;
            }
            let g = all.entry(ty.clone()).or_default();
            g.0 += 1;
            if same {
                g.1 += 1;
            }
            // Non-zero scalar fields that changed are the interesting ones.
            if !same
                && changed.len() < 12
                && matches!(ty.as_str(), "real" | "short integer" | "long integer" | "angle")
                && bytes.iter().any(|b| *b != 0)
            {
                changed.push(format!(
                    "{}@{off:#x} {}->{}",
                    layout.string_at(field.name_offset).unwrap_or("?"),
                    hex(bytes),
                    hex(l)
                ));
            }
        });
        let mut rows: Vec<_> = per.iter().collect();
        rows.sort_by_key(|(_, (n, _))| std::cmp::Reverse(*n));
        for (ty, (n, s)) in rows.iter().take(14) {
            eprintln!("    {ty:<28} {s:>5}/{n:<5} survive");
        }
        eprintln!("    changed scalars: {}", changed.join("  "));
    }
    eprintln!("== all sampled tags, by type");
    let mut rows: Vec<_> = all.iter().collect();
    rows.sort_by_key(|(_, (n, _))| std::cmp::Reverse(*n));
    for (ty, (n, s)) in rows {
        eprintln!("    {ty:<28} {s:>6}/{n:<6} {:.0}%", *s as f32 * 100.0 / *n as f32);
    }
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}
