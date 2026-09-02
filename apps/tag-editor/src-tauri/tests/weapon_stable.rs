//! Find a weapon's working copy by its scalar fields alone.
//!
//! The plain locator matches 48 contiguous bytes; a weapon's resident copy
//! has every reference rewritten, so nothing contiguous survives and the
//! locator settles for a stray copy of the section tables. This fingerprints
//! only the scalar bytes (`blam_tag::view::scalar_mask`) and lists every
//! candidate with both scores. Ignored: needs the game in a mission and
//! `MJOLNIR_PAKS`; `MJOLNIR_TAG` picks the weapon (default magnum).

use tag_editor_lib::catalog::Catalog;

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS"]
fn stable_bytes_find_the_working_copy() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let want = std::env::var("MJOLNIR_TAG").unwrap_or_else(|_| "magnum/magnum".into());
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let process = blam_live::Process::attach().expect("game running");
    let index = catalog
        .tags
        .iter()
        .position(|e| e.group == "weapon" && e.short.contains(&want))
        .expect("weapon tag in catalog");
    let entry = catalog.entry(index).unwrap();
    let file = catalog.read_tag(index).expect("read tag");
    let tag = blam_tag::TagFile::parse(&file, Some(file.len())).unwrap();
    let layout = tag.layout().unwrap();
    let block = tag.read_data(&layout).unwrap();
    let data = tag.data().unwrap();
    let r0 = data.content.as_ptr() as usize - file.as_ptr() as usize;
    let r1 = r0 + data.content.len();
    let region = r0..r1;
    let stable = blam_tag::view::scalar_mask(&layout, &block, &file);
    let stable_nz = (r0..r1).filter(|i| stable[*i] && file[*i] != 0).count();
    eprintln!(
        "{} / {}  data {r0:#x}..{r1:#x}  stable bytes {} ({} non-zero)",
        entry.group,
        entry.short,
        (r0..r1).filter(|i| stable[*i]).count(),
        stable_nz
    );

    let probes = [
        ("zoom levels[0].magnification", 4usize),
        ("magnification range", 8),
        ("magnification levels", 2),
        ("weapon zoom time in third person", 4),
    ];
    let offsets: Vec<(&str, usize, usize)> = probes
        .iter()
        .map(|(p, s)| {
            let t = blam_tag::patch::resolve(&layout, &file, &block, p).expect(p);
            (*p, t.file_offset, *s)
        })
        .collect();

    let t0 = std::time::Instant::now();
    let (cands, scanned) =
        blam_live::candidates(&process, &file, &region, &[], Some(&stable), &|_, _| {})
            .expect("sweep");
    eprintln!(
        "masked sweep: {:.1} GB in {:.1?}, {} candidate base(s)",
        scanned as f64 / 1e9,
        t0.elapsed(),
        cands.len()
    );
    let regions = process.writable_regions().unwrap();
    for c in cands.iter().take(12) {
        let plain = blam_live::verify(&process, &file, &region, c.base);
        let masked = blam_live::verify_stable(&process, &file, &region, &stable, c.base);
        let reg = regions
            .iter()
            .find(|r| c.base >= r.base && c.base < r.base + r.size)
            .map(|r| format!("region {:#x}+{:#x}", r.base, r.size))
            .unwrap_or_default();
        eprintln!(
            "  base {:#x}  runs {:>2}  plain {:>5.1}%  stable {:>5.1}%  {reg}",
            c.base,
            c.agreeing_runs,
            plain * 100.0,
            masked * 100.0
        );
        for (p, o, s) in &offsets {
            let live = process.read(c.base + *o as u64, *s).unwrap_or_default();
            eprintln!(
                "      {p:<36} file {} live {}",
                hex(&file[*o..*o + *s]),
                hex(&live)
            );
        }
    }
}
