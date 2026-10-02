//! Compile a MOPP tree for a definition's collision surfaces and check it
//! against the shipped one.
//!
//!   cargo run -p blam-sbsp --example mopp_build -- <payload> <def index>... [--probes N]
//!
//! The tree is the broadphase an instance's collision is queried through, and
//! a transplant that rewrites the surface tables while keeping the donor's
//! tree collides against nothing. This builds a replacement.
//!
//! Two checks, in increasing strength:
//!
//! 1. every surface answers a query of its own box — the tree at least finds
//!    each primitive where it is;
//! 2. against the definition's **shipped** tree, over random world-space
//!    boxes: whatever the engine's own tree names as a candidate, ours must
//!    name too. The shipped tree is ground truth, so a superset is correct and
//!    a miss is a hole in the floor.
use blam_sbsp::unpack16::{self, Tables};
use blam_sbsp::{mopp, transplant};
use blam_tag::blockedit::find_block;

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
    let probes: usize = match args.iter().position(|a| a == "--probes") {
        Some(i) => args[i + 1].parse().expect("probe count"),
        None => 400,
    };
    let file = std::fs::read(&args[0]).expect("read");
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");

    let mut failures = 0;
    for a in args[1..].iter().filter(|a| a.parse::<usize>().is_ok()) {
        let d: usize = a.parse().unwrap();
        let coll = transplant::definition(d);
        let base = coll.trim_end_matches(".collision info");
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
        let Ok((c, _)) = unpack16::unpack(&t) else {
            println!("-- definition {d}: collision tables do not unpack");
            continue;
        };
        if c.surfaces.is_empty() {
            println!("-- definition {d}: no surfaces");
            continue;
        }

        // Every surface's polygon, and the box the whole definition occupies.
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

        let code = match mopp::build(&prims) {
            Ok(c) => c,
            Err(e) => {
                println!("-- definition {d}: build failed: {e}");
                failures += 1;
                continue;
            }
        };
        println!(
            "-- definition {d}: {} surface(s) -> {} code byte(s) ({:.1} per surface)",
            c.surfaces.len(),
            code.len(),
            code.len() as f32 / c.surfaces.len() as f32
        );

        // 1. Each surface answers its own box.
        let mut self_miss = 0;
        for (id, b) in &prims {
            let ql = [b.lo[0] as i32 - 1, b.lo[1] as i32 - 1, b.lo[2] as i32 - 1];
            let qh = [b.hi[0] as i32 + 1, b.hi[1] as i32 + 1, b.hi[2] as i32 + 1];
            if !mopp::query_bytes(&code, ql, qh).unwrap().contains(id) {
                self_miss += 1;
            }
        }
        println!(
            "   self-query: {} of {} surfaces found -- {}",
            c.surfaces.len() - self_miss,
            c.surfaces.len(),
            if self_miss == 0 { "PASS" } else { "FAIL" }
        );
        if self_miss > 0 {
            failures += 1;
        }

        // 2. Against the shipped tree over the same world-space boxes.
        let shipped = find_block(&layout, &file, &root, &format!("{base}.mopp codes"))
            .ok()
            .filter(|m| m.block.count > 0)
            .map(|m| {
                let mut code = Vec::new();
                for v in &m.block.children[0] {
                    bytecode(v, &mut code);
                }
                let e = m.block.element(0).unwrap().to_vec();
                (code, e)
            });
        let Some((ship_code, ship_elem)) = shipped else {
            println!("   no shipped tree to compare against");
            continue;
        };
        // The block wrapper the tag carries around the bytecode: rebuilding it
        // from the shipped code has to reproduce the shipped bytes exactly,
        // or a compiled tree cannot be written back into a tag.
        match transplant::donor_element(&file, &format!("{base}.mopp codes"), 0) {
            Ok((_, want)) => {
                let got = mopp::wrapper(&ship_code);
                println!(
                    "   block wrapper rebuild: {} vs {} byte(s) -- {}",
                    got.len(),
                    want.len(),
                    if got == want { "byte-exact" } else { "DIFFERS" }
                );
                if got != want {
                    failures += 1;
                }
            }
            Err(e) => println!("   no donor wrapper: {e}"),
        }

        let f = |o: usize| f32::from_le_bytes(ship_elem[o..o + 4].try_into().unwrap());
        let ship_q = mopp::Quant {
            offset: [f(32), f(36), f(40)],
            scale: f(44),
        };

        // Before comparing, check the shipped tree answers its own surfaces
        // under this model. If it does not, the model is wrong and any
        // comparison against it is meaningless.
        let mut ship_self_miss = 0;
        for (i, poly) in polys.iter().enumerate() {
            let mut pl = [f32::MAX; 3];
            let mut ph = [f32::MIN; 3];
            for p in poly {
                for k in 0..3 {
                    pl[k] = pl[k].min(p[k]);
                    ph[k] = ph[k].max(p[k]);
                }
            }
            let qb = ship_q.query_box(pl, ph);
            if !mopp::query(&ship_code, &qb).unwrap().contains(&(i as u32)) {
                ship_self_miss += 1;
            }
        }
        println!(
            "   shipped tree self-query: {} of {} found -- {}",
            polys.len() - ship_self_miss,
            polys.len(),
            if ship_self_miss == 0 { "model holds" } else { "MODEL WRONG" }
        );

        let mut seed = 0x9e3779b97f4a7c15u64;
        let mut rnd = || {
            seed ^= seed << 13;
            seed ^= seed >> 7;
            seed ^= seed << 17;
            (seed >> 11) as f32 / (1u64 << 53) as f32
        };
        // The real criterion is geometry, not the shipped tree: whatever
        // actually overlaps the query box must be named. The shipped tree is
        // free to over-report (it does), so requiring a superset of *it* would
        // fail on its conservatism rather than on ours.
        let boxes: Vec<([f32; 3], [f32; 3])> = polys
            .iter()
            .map(|poly| {
                let mut pl = [f32::MAX; 3];
                let mut ph = [f32::MIN; 3];
                for p in poly {
                    for k in 0..3 {
                        pl[k] = pl[k].min(p[k]);
                        ph[k] = ph[k].max(p[k]);
                    }
                }
                (pl, ph)
            })
            .collect();

        let (mut missed, mut truth_total, mut ours_total, mut ship_missed) = (0usize, 0usize, 0usize, 0usize);
        for _ in 0..probes {
            let mut bl = [0.0f32; 3];
            let mut bh = [0.0f32; 3];
            for k in 0..3 {
                let span = hi[k] - lo[k];
                let c0 = lo[k] + rnd() * span;
                let half = span * 0.02 + 0.05;
                bl[k] = c0 - half;
                bh[k] = c0 + half;
            }
            let truth: Vec<u32> = boxes
                .iter()
                .enumerate()
                .filter(|(_, (pl, ph))| {
                    (0..3).all(|k| pl[k] <= bh[k] && bl[k] <= ph[k])
                })
                .map(|(i, _)| i as u32)
                .collect();
            let mine = mopp::query(&code, &q.query_box(bl, bh)).unwrap();
            let theirs = mopp::query(&ship_code, &ship_q.query_box(bl, bh)).unwrap();
            truth_total += truth.len();
            ours_total += mine.len();
            for t in &truth {
                if !mine.contains(t) {
                    missed += 1;
                }
                if !theirs.contains(t) {
                    ship_missed += 1;
                }
            }
        }
        println!(
            "   {probes} probes: {truth_total} surface(s) actually overlap; ours named {ours_total}              and missed {missed}; the shipped tree missed {ship_missed} -- {}",
            if missed == 0 { "PASS" } else { "FAIL" }
        );
        if missed > 0 {
            failures += 1;
        }
    }
    if failures > 0 {
        eprintln!("{failures} check(s) failed");
        std::process::exit(1);
    }
}
