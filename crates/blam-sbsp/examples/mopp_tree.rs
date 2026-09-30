//! Decode a definition's Havok MOPP tree and check it against that
//! definition's surface table.
//!
//!   cargo run -p blam-sbsp --example mopp_tree -- <payload> <def index>...
//!
//! The tree is the broadphase an instance's collision is queried through, so
//! its leaves should name every surface of the definition exactly once. If
//! that holds for the shipped trees, the decoder matches the engine's virtual
//! machine and the same encoding can be written for transplanted geometry.
use blam_sbsp::unpack16::{self, Tables};
use blam_sbsp::{mopp, transplant};
use blam_tag::blockedit::find_block;

/// The bytecode lives in a nested block inside the mopp element's `tgst`
/// wrapper; walk the decoded value tree for the byte block rather than
/// guessing a header size.
fn bytecode(v: &blam_tag::Value<'_>, out: &mut Vec<u8>) {
    match v {
        blam_tag::Value::Block(b) => {
            if b.elements.len() > out.len() {
                *out = b.elements.to_vec();
            }
            for kids in &b.children {
                for k in kids {
                    bytecode(k, out);
                }
            }
        }
        blam_tag::Value::Struct { children } | blam_tag::Value::Array { children } => {
            for k in children {
                bytecode(k, out);
            }
        }
        _ => {}
    }
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&args[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");

    for a in &args[1..] {
        let d: usize = a.parse().expect("def index");
        let coll = transplant::definition(d);
        let base = coll.trim_end_matches(".collision info");
        let surfaces = find_block(&layout, &file, &root, &format!("{coll}.surfaces"))
            .map(|f| f.block.count)
            .unwrap_or(0);
        let m = match find_block(&layout, &file, &root, &format!("{base}.mopp codes")) {
            Ok(m) if m.block.count > 0 => m,
            _ => {
                println!("-- definition {d}: {surfaces} surface(s), no mopp");
                continue;
            }
        };
        let mut code = Vec::new();
        for v in &m.block.children[0] {
            bytecode(v, &mut code);
        }
        // The header's code info: the offset and scale that map definition
        // space into the 24-bit grid the tree's bytes index.
        let e = m.block.element(0).unwrap_or(&[]);
        let f = |o: usize| f32::from_le_bytes(e[o..o + 4].try_into().unwrap());
        let (ox, oy, oz, w) = (f(32), f(36), f(40), f(44));

        // What the geometry actually spans, straight from the tables.
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
        let mut lo = [f32::MAX; 3];
        let mut hi = [f32::MIN; 3];
        if let Ok((c, _)) = unpack16::unpack(&t) {
            for v in &c.vertices {
                for k in 0..3 {
                    lo[k] = lo[k].min(v.point[k]);
                    hi[k] = hi[k].max(v.point[k]);
                }
            }
        }
        println!(
            "   code info offset ({ox:.3}, {oy:.3}, {oz:.3}) w {w:.1}   geometry [{:.2}, {:.2}] x [{:.2}, {:.2}] x [{:.2}, {:.2}]",
            lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]
        );
        // If w is the scale into 24-bit fixed point, the byte the tree sees is
        // ((v - offset) * w) >> 16, so the geometry should land inside 0..255.
        let byte = |v: f32, o: f32| ((v - o) * w) as i64 >> 16;
        println!(
            "   geometry in tree bytes: x [{}, {}]  y [{}, {}]  z [{}, {}]",
            byte(lo[0], ox), byte(hi[0], ox),
            byte(lo[1], oy), byte(hi[1], oy),
            byte(lo[2], oz), byte(hi[2], oz)
        );
        print!("-- definition {d}: {surfaces} surface(s), {} code byte(s)", code.len());

        match mopp::terminals(&code) {
            Ok(t) => {
                let mut ids: Vec<u32> = t.iter().map(|(i, _)| *i).collect();
                ids.sort_unstable();
                let unique = {
                    let mut u = ids.clone();
                    u.dedup();
                    u.len()
                };
                let max_depth = t.iter().map(|(_, d)| *d).max().unwrap_or(0);
                let lo = ids.first().copied().unwrap_or(0);
                let hi = ids.last().copied().unwrap_or(0);
                let covers_all = unique == surfaces as usize
                    && lo == 0
                    && hi + 1 == surfaces.max(1);
                println!(
                    ": {} leaf/leaves, {unique} unique in [{lo}, {hi}], depth {max_depth} -- {}",
                    t.len(),
                    if covers_all {
                        "covers every surface exactly once".to_string()
                    } else {
                        format!("MISMATCH (expected {surfaces} unique in [0, {}])", surfaces.max(1) - 1)
                    }
                );
            }
            Err(e) => println!(": decode failed: {e}"),
        }
    }
}
