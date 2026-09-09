//! Recompile a definition's Havok MOPP from its own collision surfaces.
//!
//!   cargo run -p blam-sbsp --example def_mopp -- <payload> <out> <def index>...
//!
//! An instance's collision is queried through the MOPP, not through the
//! winged-edge tables directly, so a transplant that rewrites the tables and
//! keeps the donor's tree collides against nothing: the tree still describes
//! where the donor's surfaces were. This rebuilds the tree over the surfaces
//! that are actually there, and rewrites the element's `code info` so the
//! quantisation matches.
//!
//! The definition must already carry a mopp, whose 96-byte element is reused
//! for everything this does not compute — the cook-time pointers included,
//! which are stale heap addresses the engine rebuilds at load.
use blam_sbsp::unpack16::{self, Tables};
use blam_sbsp::{mopp, transplant};
use blam_tag::blockedit::{find_block, replace_nested, NestedReplace};

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.len() < 3 {
        eprintln!("usage: def_mopp <payload> <out> <def index>...");
        std::process::exit(2);
    }
    let file = std::fs::read(&args[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");

    let mut edits = Vec::new();
    for a in &args[2..] {
        let d: usize = a.parse().expect("def index");
        let coll = transplant::definition(d);
        let base = coll.trim_end_matches(".collision info").to_string();
        let get = |name: &str| -> &[u8] {
            find_block(&layout, &file, &root, &format!("{coll}.{name}"))
                .map(|f| f.block.elements)
                .unwrap_or(&[])
        };
        let t = Tables {
            bsp3d_nodes: get("bsp3d nodes"),
            planes: get("planes"),
            leaves: get("leaves"),
            bsp2d_references: get("bsp2d references"),
            bsp2d_nodes: get("bsp2d nodes"),
            surfaces: get("surfaces"),
            edges: get("edges"),
            vertices: get("vertices"),
        };
        let (c, _) = unpack16::unpack(&t).expect("unpack collision tables");
        if c.surfaces.is_empty() {
            println!("  definition {d}: no surfaces, skipped");
            continue;
        }

        let polys: Vec<Vec<[f32; 3]>> = (0..c.surfaces.len())
            .map(|s| unpack16::polygon(&c, s))
            .collect();
        let mut lo = [f32::MAX; 3];
        let mut hi = [f32::MIN; 3];
        for p in polys.iter().flatten() {
            for k in 0..3 {
                lo[k] = lo[k].min(p[k]);
                hi[k] = hi[k].max(p[k]);
            }
        }
        let q = mopp::Quant::fit(lo, hi);
        let prims: Vec<(u32, mopp::Aabb)> = polys
            .iter()
            .enumerate()
            .map(|(i, p)| (i as u32, q.box_of(p)))
            .collect();
        let code = mopp::build(&prims).expect("build mopp");

        // Every surface has to answer a query of its own box, or the floor has
        // holes in it. Checked here so a bad tree never reaches a container.
        let mut miss = 0;
        for (id, b) in &prims {
            let ql = [b.lo[0] as i32 - 1, b.lo[1] as i32 - 1, b.lo[2] as i32 - 1];
            let qh = [b.hi[0] as i32 + 1, b.hi[1] as i32 + 1, b.hi[2] as i32 + 1];
            if !mopp::query_bytes(&code, ql, qh).unwrap().contains(id) {
                miss += 1;
            }
        }
        assert_eq!(miss, 0, "definition {d}: {miss} surfaces do not answer their own box");

        let (mut element, _) = transplant::donor_element(&file, &format!("{base}.mopp codes"), 0)
            .unwrap_or_else(|e| panic!("definition {d} has no mopp to reuse: {e}"));
        mopp::patch_element(&mut element, q, code.len());

        println!(
            "  definition {d}: {} surface(s) -> {} code byte(s); offset ({:.3}, {:.3}, {:.3}) scale {:.1}",
            c.surfaces.len(),
            code.len(),
            q.offset[0],
            q.offset[1],
            q.offset[2],
            q.scale
        );
        edits.push(NestedReplace {
            path: format!("{base}.mopp codes"),
            count: 1,
            elements: element,
            wrappers: Some(vec![mopp::wrapper(&code)]),
        });
    }

    let out = replace_nested(&file, &edits).expect("replace");
    let tag = blam_tag::TagFile::parse(&out, None).expect("reparse");
    let l = tag.layout().expect("relayout");
    let block = tag.read_data(&l).expect("reread");
    let payload = tag.data().expect("bdat");
    assert_eq!(block.consumed, payload.size as usize, "does not walk exactly");
    std::fs::write(&args[1], &out).expect("write");
    println!("  wrote {} ({} bytes, walks exactly)", args[1], out.len());
}
