//! Is the runtime block header's second word an offset from one arena base?
//! Find each block's element bytes near the root copy, subtract X, and see
//! whether every block gives the same base. Ignored: needs the game,
//! `MJOLNIR_PAKS`, `MJOLNIR_BASE`.
use tag_editor_lib::catalog::Catalog;

fn hex(b: &[u8]) -> String {
    b.iter().map(|x| format!("{x:02x}")).collect::<Vec<_>>().join(" ")
}

#[test]
#[ignore = "needs the game running in a mission"]
fn block_header_word_is_an_arena_offset() {
    let paks = std::env::var("MJOLNIR_PAKS").expect("set MJOLNIR_PAKS");
    let want = std::env::var("MJOLNIR_TAG").unwrap_or_else(|_| "magnum/magnum".into());
    let base = u64::from_str_radix(
        std::env::var("MJOLNIR_BASE").expect("set MJOLNIR_BASE").trim_start_matches("0x"),
        16,
    )
    .unwrap();
    let catalog = Catalog::open(&paks, "").expect("catalog opens");
    let process = blam_live::Process::attach().expect("game running");
    let index = catalog
        .tags
        .iter()
        .position(|e| e.group == "weapon" && e.short.contains(&want))
        .unwrap();
    let file = catalog.read_tag(index).unwrap();
    let tag = blam_tag::TagFile::parse(&file, Some(file.len())).unwrap();
    let layout = tag.layout().unwrap();
    let block = tag.read_data(&layout).unwrap();
    let data = tag.data().unwrap();
    let r0 = data.content.as_ptr() as usize - file.as_ptr() as usize;
    let root_off = block.elements.as_ptr() as usize - file.as_ptr() as usize;
    let stable = blam_tag::view::scalar_mask(&layout, &block, &file);

    // A window of memory around the root copy.
    let lo = base + r0 as u64 - 0x40000;
    let win = process.read(lo, 0x80000).unwrap();
    eprintln!("window {lo:#x}+{:#x}", win.len());

    for n in blam_tag::view::root(&layout, &block) {
        if n.kind != blam_tag::view::Kind::Block || n.count.unwrap_or(0) == 0 {
            continue;
        }
        let hdr = root_off + n.offset as usize;
        let l = process.read(base + hdr as u64, 12).unwrap();
        let x = u32::from_le_bytes(l[4..8].try_into().unwrap()) as u64;
        // File offset of element 0: resolve its first scalar child.
        let elem = &n.children[0];
        let Some(child) = elem.children.iter().find(|c| c.kind == blam_tag::view::Kind::Field && c.size > 0) else { continue };
        let path = format!("{}[0].{}", n.name, child.name);
        let Ok(t) = blam_tag::patch::resolve(&layout, &file, &block, &path) else {
            eprintln!("  {:<28} could not resolve {path}", n.name);
            continue;
        };
        let e0 = t.file_offset - child.offset as usize;
        let len = (n.count.unwrap_or(0) * elem.size) as usize;
        let img = &file[e0..e0 + len];
        let nz = (e0..e0 + len).filter(|i| stable[*i] && file[*i] != 0).count();
        // Masked search in the window.
        let mut hits: Vec<u64> = Vec::new();
        if nz >= 6 {
            'pos: for p in 0..win.len().saturating_sub(len) {
                for i in 0..len {
                    if stable[e0 + i] && win[p + i] != img[i] {
                        continue 'pos;
                    }
                }
                hits.push(lo + p as u64);
                if hits.len() > 8 {
                    break;
                }
            }
        }
        eprintln!(
            "  {:<28} count {} elem {} B file@{e0:#x} nz {nz} x={x:#x}  hits {:#x?}  arena {:#x?}",
            n.name,
            n.count.unwrap_or(0),
            elem.size,
            hits,
            hits.iter().map(|h| h.wrapping_sub(x)).collect::<Vec<_>>()
        );
        if let Some(h) = hits.first() {
            let l = process.read(*h, len.min(32)).unwrap();
            eprintln!("      live {}", hex(&l));
            eprintln!("      file {}", hex(&img[..len.min(32)]));
        }
    }
}
