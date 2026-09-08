//! How many copies of a weapon tag are in memory, and which one does the
//! simulation read?
//!
//! A live poke of the magnum's zoom magnification reported success — the
//! bytes stuck at the located base — and changed nothing in the game. The
//! locator keeps only its best candidate, so this lists every base any run
//! voted for, scores each against the file, reads the zoom fields out of
//! each, and asks the loader cache what it thinks. Ignored: needs the game in
//! a mission with the weapon in play and `MJOLNIR_PAKS`.

use tag_editor_lib::{catalog::Catalog, tagcache};

fn field(file: &[u8], path: &str) -> (usize, usize) {
    let tag = blam_tag::TagFile::parse(file, Some(file.len())).expect("parse");
    let layout = tag.layout().expect("layout");
    let block = tag.read_data(&layout).expect("data");
    let t = blam_tag::patch::resolve(&layout, file, &block, path).expect(path);
    (t.file_offset, t.size)
}

fn region(file: &[u8]) -> std::ops::Range<usize> {
    let tag = blam_tag::TagFile::parse(file, Some(file.len())).expect("parse");
    let data = tag.data().expect("bdat");
    let start = data.content.as_ptr() as usize - file.as_ptr() as usize;
    start..start + data.content.len()
}

fn f32_at(b: &[u8]) -> f32 {
    f32::from_le_bytes(b[..4].try_into().unwrap())
}

#[test]
#[ignore = "needs the game running in a mission; set MJOLNIR_PAKS"]
fn every_copy_of_the_weapon() {
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
    let region = region(&file);
    eprintln!(
        "{} / {}  payload {} bytes, data {:#x}..{:#x}",
        entry.group,
        entry.short,
        file.len(),
        region.start,
        region.end
    );

    let probes = [
        "zoom levels[0].magnification",
        "magnification range",
        "magnification levels",
        "weapon zoom time in third person",
    ];
    let offsets: Vec<(&str, usize, usize)> = probes
        .iter()
        .map(|p| {
            let (o, s) = field(&file, p);
            (*p, o, s)
        })
        .collect();
    for (p, o, s) in &offsets {
        eprintln!("  field {p:<36} at {o:#x} ({s} B) file={}", hex(&file[*o..*o + *s]));
    }

    // The loader cache's opinion, if it has one.
    match tagcache::roots(&process, catalog.paks(), &[]) {
        Ok((roots, _)) => {
            let hits = tagcache::resolve(&process, &catalog, &roots);
            let mine: Vec<u64> = hits
                .bases
                .iter()
                .filter(|(i, _)| *i == index)
                .map(|(_, b)| *b)
                .collect();
            eprintln!("loader cache: {} roots, {} nodes, this tag -> {mine:#x?}", roots.len(), hits.nodes);
        }
        Err(e) => eprintln!("loader cache: {e}"),
    }

    let t0 = std::time::Instant::now();
    let (cands, scanned) =
        blam_live::candidates(&process, &file, &region, &[], None, &|_, _| {}).expect("sweep");
    eprintln!(
        "sweep: {:.1} GB in {:.1?}, {} candidate base(s)",
        scanned as f64 / 1e9,
        t0.elapsed(),
        cands.len()
    );
    let regions = process.writable_regions().expect("regions");
    for c in cands.iter().take(40) {
        let fraction = blam_live::verify(&process, &file, &region, c.base);
        let reg = regions
            .iter()
            .find(|r| c.base >= r.base && c.base < r.base + r.size)
            .map(|r| format!("region {:#x}+{:#x}", r.base, r.size))
            .unwrap_or_else(|| "no region".into());
        eprintln!(
            "  base {:#x}  runs {:>2}  identical {:>5.1}%  {}",
            c.base,
            c.agreeing_runs,
            fraction * 100.0,
            reg
        );
        for (p, o, s) in &offsets {
            let live = process.read(c.base + *o as u64, *s).unwrap_or_default();
            let shown = if *s == 4 {
                format!("{}", f32_at(&live))
            } else if *s == 8 {
                format!("({}, {})", f32_at(&live), f32_at(&live[4..]))
            } else {
                hex(&live)
            };
            eprintln!("      {p:<36} {} = {shown}", hex(&live));
        }
    }
}

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect()
}
