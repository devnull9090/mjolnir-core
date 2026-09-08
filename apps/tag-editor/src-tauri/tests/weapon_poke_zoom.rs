//! Read (and with `MJOLNIR_WRITE`, write) the magnum's zoom magnification
//! through the runtime block header: element = arena + 4 * header word.
//! Ignored: needs the game, `MJOLNIR_PAKS`, `MJOLNIR_BASE`.
use tag_editor_lib::catalog::Catalog;

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect::<Vec<_>>().join(" ")
}

#[test]
#[ignore = "needs the game running in a mission"]
fn zoom_through_the_header() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let base = u64::from_str_radix(
        std::env::var("MJOLNIR_BASE").expect("set MJOLNIR_BASE").trim_start_matches("0x"),
        16,
    )
    .unwrap();
    let arena: u64 = std::env::var("MJOLNIR_ARENA").ok().map(|a| u64::from_str_radix(a.trim_start_matches("0x"), 16).unwrap()).unwrap_or(0x1b3de0a0000);
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let process = blam_live::Process::attach().expect("game running");
    let index = catalog
        .tags
        .iter()
        .position(|e| e.group == "weapon" && e.short.contains(&std::env::var("MJOLNIR_TAG").unwrap_or_else(|_| "magnum/magnum".into())))
        .unwrap();
    let file = catalog.read_tag(index).unwrap();
    let tag = blam_tag::TagFile::parse(&file, Some(file.len())).unwrap();
    let layout = tag.layout().unwrap();
    let block = tag.read_data(&layout).unwrap();
    let root_off = block.elements.as_ptr() as usize - file.as_ptr() as usize;
    let zoom = blam_tag::view::root(&layout, &block)
        .into_iter()
        .find(|n| n.name == "zoom levels")
        .unwrap();
    let hdr = root_off + zoom.offset as usize;
    let l = process.read(base + hdr as u64, 12).unwrap();
    let x = u32::from_le_bytes(l[4..8].try_into().unwrap()) as u64;
    let elems = arena + 4 * x;
    let mag = zoom.children[0].children.iter().find(|c| c.name == "magnification").unwrap();
    let at = elems + mag.offset as u64;
    eprintln!("header {} -> elements {elems:#x}, magnification at {at:#x}: {}", hex(&l), hex(&process.read(at, 4).unwrap()));
    eprintln!("element bytes: {}", hex(&process.read(elems, 8).unwrap()));

    // Which region holds the arena base, and does the game image hold it?
    let regions = process.writable_regions().unwrap();
    if let Some(r) = regions.iter().find(|r| arena >= r.base && arena < r.base + r.size) {
        eprintln!("arena {arena:#x} is in region {:#x}+{:#x} (offset {:#x})", r.base, r.size, arena - r.base);
    } else {
        eprintln!("arena {arena:#x} is in no writable region");
    }
    let (mb, msize) = process.module(blam_live::GAME_EXE).unwrap();
    let mut holders = Vec::new();
    let mut at_ = 0u64;
    let mut buf = vec![0u8; 16 << 20];
    while at_ < msize {
        let want = (buf.len() as u64).min(msize - at_) as usize;
        if let Ok(got) = process.read_into(mb + at_, &mut buf[..want]) {
            for o in (0..got.saturating_sub(7)).step_by(8) {
                if u64::from_le_bytes(buf[o..o + 8].try_into().unwrap()) == arena {
                    holders.push(mb + at_ + o as u64);
                }
            }
        }
        at_ += want as u64;
    }
    eprintln!("image statics holding the arena base: {:#x?} (rva {:#x?})", holders, holders.iter().map(|h| h - mb).collect::<Vec<_>>());

    if let Ok(v) = std::env::var("MJOLNIR_WRITE") {
        let v: f32 = v.parse().unwrap();
        let before = process.read(at, 4).unwrap();
        process.write(at, &v.to_le_bytes()).unwrap();
        eprintln!("wrote {v} at {at:#x}: was {} now {}", hex(&before), hex(&process.read(at, 4).unwrap()));
    }
}
