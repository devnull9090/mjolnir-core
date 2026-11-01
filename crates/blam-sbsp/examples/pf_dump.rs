//! Compare a scenario's `ai pathfinding data[bsp]` with the structure BSP's
//! collision shell, to learn how sectors, links and 2D refs relate to it.
//!   cargo run -p blam-sbsp --example pf_dump -- <scenario> <sbsp> <bsp index>
use blam_sbsp::transplant;
use blam_sbsp::unpack16::{self, Tables};
use blam_tag::blockedit::find_block;

fn i16_at(b: &[u8], o: usize) -> i16 {
    i16::from_le_bytes([b[o], b[o + 1]])
}
fn u16_at(b: &[u8], o: usize) -> u16 {
    u16::from_le_bytes([b[o], b[o + 1]])
}
fn i32_at(b: &[u8], o: usize) -> i32 {
    i32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}
fn f32_at(b: &[u8], o: usize) -> f32 {
    f32::from_le_bytes(b[o..o + 4].try_into().unwrap())
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let scn = std::fs::read(&a[0]).expect("scenario");
    let bsp = std::fs::read(&a[1]).expect("sbsp");
    let bi: usize = a[2].parse().unwrap();
    let mode = a.get(3).map(String::as_str).unwrap_or("summary");

    let tag = blam_tag::TagFile::parse(&scn, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let pf = format!("ai pathfinding data[{bi}]");
    let blk = |n: &str| {
        find_block(&layout, &scn, &root, &format!("{pf}.{n}")).map(|f| {
            (
                f.block.elements,
                f.block.element_size as usize,
                f.block.count as usize,
            )
        })
    };

    let btag = blam_tag::TagFile::parse(&bsp, None).expect("parse sbsp");
    let bl = btag.layout().expect("layout");
    let broot = btag.read_data(&bl).expect("data");
    let get = |n: &str| -> &[u8] {
        find_block(&bl, &bsp, &broot, &format!("{}.{n}", transplant::SHELL))
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
    let (c, _) = unpack16::unpack(&t).expect("unpack");
    println!(
        "collision: {} surfaces, {} edges, {} vertices, {} 2d refs, {} 2d nodes",
        c.surfaces.len(),
        c.edges.len(),
        c.vertices.len(),
        c.bsp2d_references.len(),
        c.bsp2d_nodes.len()
    );

    for n in [
        "sectors",
        "links",
        "bsp2d refs",
        "bsp2d nodes",
        "vertices",
        "object refs",
        "pathfinding hints",
        "instanced geometry refs",
        "giant pathfinding data",
        "seams",
        "jump seams",
        "doors",
    ] {
        match blk(n) {
            Ok((_, size, count)) => println!("pf {n}: {count} x {size} B"),
            Err(e) => println!("pf {n}: {e:?}"),
        }
    }
    let (sec, ss, sn) = blk("sectors").unwrap();
    let (lnk, ls, ln) = blk("links").unwrap();
    let (nod, ns, nn) = blk("bsp2d nodes").unwrap();
    let (ver, vs, vn) = blk("vertices").unwrap();

    match mode {
        "summary" => {
            // Do pathfinding vertices coincide with collision vertices?
            let mut hit = 0;
            for i in 0..vn {
                let p = [
                    f32_at(ver, i * vs),
                    f32_at(ver, i * vs + 4),
                    f32_at(ver, i * vs + 8),
                ];
                if c.vertices.iter().any(|v| {
                    (v.point[0] - p[0]).abs() < 1e-3
                        && (v.point[1] - p[1]).abs() < 1e-3
                        && (v.point[2] - p[2]).abs() < 1e-3
                }) {
                    hit += 1;
                }
            }
            println!("pf vertices also collision vertices: {hit} of {vn}");
            let mut flags = std::collections::BTreeMap::new();
            for i in 0..sn {
                *flags.entry(u16_at(sec, i * ss)).or_insert(0) += 1;
            }
            println!("sector flags histogram: {flags:x?}");
            let mut lf = std::collections::BTreeMap::new();
            for i in 0..ln {
                *lf.entry(u16_at(lnk, i * ls + 4)).or_insert(0) += 1;
            }
            println!("link flags histogram: {lf:x?}");
            // Ring walk of sector 0..3
            for s in 0..3.min(sn) {
                let first = i32_at(sec, s * ss + 4);
                let mut l = first;
                let mut ring = Vec::new();
                for _ in 0..64 {
                    let o = l as usize * ls;
                    let (v1, v2, fl, fw, rv, left, right) = (
                        i16_at(lnk, o),
                        i16_at(lnk, o + 2),
                        u16_at(lnk, o + 4),
                        i16_at(lnk, o + 8),
                        i16_at(lnk, o + 10),
                        i16_at(lnk, o + 12),
                        i16_at(lnk, o + 14),
                    );
                    ring.push(format!(
                        "L{l}[{v1}->{v2} f{fl:x} fw{fw} rv{rv} l{left} r{right}]"
                    ));
                    let next = if left as usize == s { fw } else { rv };
                    if next < 0 || next as i32 == first {
                        break;
                    }
                    l = next as i32;
                }
                println!(
                    "sector {s} (flags {:x}, hint {}): {}",
                    u16_at(sec, s * ss),
                    i16_at(sec, s * ss + 2),
                    ring.join(" ")
                );
            }
            let mut child_kinds = [0usize; 4];
            let mut maxc = 0i64;
            for i in 0..nn {
                for k in [12, 16] {
                    let v = i32_at(nod, i * ns + k);
                    if v == -1 {
                        child_kinds[0] += 1
                    } else if v < 0 {
                        child_kinds[1] += 1
                    } else if (v as usize) < sn {
                        child_kinds[2] += 1
                    } else {
                        child_kinds[3] += 1
                    }
                    maxc = maxc.max(v as i64);
                }
            }
            println!(
                "bsp2d node children: none {} neg {} <sectors {} >=sectors {}; max {maxc}",
                child_kinds[0], child_kinds[1], child_kinds[2], child_kinds[3]
            );
            for i in 0..8.min(nn) {
                println!(
                    "node {i}: plane ({:.3},{:.3},{:.3}) l {:#x} r {:#x}",
                    f32_at(nod, i * ns),
                    f32_at(nod, i * ns + 4),
                    f32_at(nod, i * ns + 8),
                    i32_at(nod, i * ns + 12),
                    i32_at(nod, i * ns + 16)
                );
            }
            // object refs
            if let Ok((_, _, on)) = blk("object refs") {
                for o in 0..on {
                    let p = format!("{pf}.object refs[{o}].bsps");
                    if let Ok(f) = find_block(&layout, &scn, &root, &p) {
                        for b in 0..f.block.count as usize {
                            let e = f.block.element(b).unwrap();
                            let refs =
                                find_block(&layout, &scn, &root, &format!("{p}[{b}].bsp2d refs"))
                                    .map(|r| r.block.count)
                                    .unwrap_or(0);
                            println!("object ref {o} bsp {b}: bsp reference {:#x} node {} refs {refs} vertex offset {}", i32_at(e, 0), i16_at(e, 4), i32_at(e, e.len() - 4));
                        }
                    }
                }
            }
        }
        "gen" => {
            let pf = blam_sbsp::pathfinding::Pathfinding::build(&c).expect("build");
            println!(
                "generated: {} sectors, {} links, {} vertices, {} refs",
                pf.sectors.len(),
                pf.links.len(),
                pf.vertices.len(),
                pf.refs.len()
            );
            println!("rings: {:?}", pf.check_rings());
            let mut sizes = std::collections::HashMap::new();
            for &k in &pf.component {
                *sizes.entry(k).or_insert(0usize) += 1;
            }
            let mut v: Vec<_> = sizes.into_iter().collect();
            v.sort_by_key(|e| std::cmp::Reverse(e.1));
            println!(
                "components: {} (largest {:?})",
                v.len(),
                &v[..v.len().min(8)]
            );
            let p = [98.49f32, -157.64, 2.70];
            println!("sector at start {:?}: {:?}", p, pf.sector_at(&c, p));
            for sp in [3.0f32, 4.0, 5.0] {
                let main = pf
                    .sector_at(&c, p)
                    .map(|(s, _)| vec![pf.component[s]])
                    .unwrap_or_default();
                println!(
                    "firing positions at {sp}: {} (main component {})",
                    pf.firing_positions(&c, sp, &[], 0.0).len(),
                    pf.firing_positions(&c, sp, &main, 0.0).len()
                );
            }
        }
        "defs" => {
            for d in 0..40 {
                let p = format!("{}.surfaces", transplant::definition(d));
                match find_block(&bl, &bsp, &broot, &p) {
                    Ok(f) => print!("def{d}:{} ", f.block.count),
                    Err(_) => break,
                }
            }
            println!();
            let n = find_block(
                &bl,
                &bsp,
                &broot,
                "resource interface.raw_resources[0].raw_items.instanced geometry instances",
            )
            .map(|f| f.block.count);
            let n2 = find_block(&bl, &bsp, &broot, "instanced geometry instances")
                .map(|f| f.block.count);
            println!("instances: raw {:?} top {:?}", n.ok(), n2.ok());
            let (ig, is, inn) = blk("instanced geometry refs").unwrap();
            let v: Vec<i16> = (0..inn.min(60)).map(|i| i16_at(ig, i * is)).collect();
            println!("instanced geometry refs first: {v:?}");
        }
        "risers" => {
            // Unwalkable surfaces that share an edge with a walkable one, by
            // height (z extent) and facing.
            use blam_sbsp::pathfinding::{surface_normal, WALKABLE_NZ};
            let walk = |s: i32| {
                s >= 0 && {
                    let x = &c.surfaces[s as usize];
                    x.first_edge >= 0
                        && x.flags & 0x8 == 0
                        && surface_normal(&c, s as usize)[2] >= WALKABLE_NZ
                }
            };
            let bounds = [0.005f32, 0.01, 0.02, 0.05, 0.1, 0.2, 0.4, f32::MAX];
            let mut hist = vec![[0usize; 3]; bounds.len()];
            let mut corners = std::collections::BTreeMap::new();
            for s in 0..c.surfaces.len() {
                if walk(s as i32) || c.surfaces[s].first_edge < 0 {
                    continue;
                }
                let touches = c.edges.iter().any(|e| {
                    (e.left == s as i32 && walk(e.right)) || (e.right == s as i32 && walk(e.left))
                });
                if !touches {
                    continue;
                }
                let poly = unpack16::polygon(&c, s);
                let (lo, hi) = poly.iter().fold((f32::MAX, f32::MIN), |(lo, hi), p| {
                    (lo.min(p[2]), hi.max(p[2]))
                });
                let nz = surface_normal(&c, s)[2];
                let facing = if nz < -0.3 {
                    2
                } else if nz < 0.05 {
                    1
                } else {
                    0
                };
                let b = bounds.iter().position(|&x| hi - lo < x).unwrap();
                hist[b][facing] += 1;
                if hi - lo < 0.1 {
                    *corners.entry(poly.len()).or_insert(0usize) += 1;
                }
            }
            println!("risers bordering a floor, by height: [sloped up, vertical, facing down]");
            for (b, h) in bounds.iter().zip(&hist) {
                println!("  < {b:>6}: {h:?}");
            }
            println!("corners of those under 0.1: {corners:?}");
        }
        "shell" => {
            // The collision shell and the pathfinding generated from it, as
            // lines: `S <surface> <nx> <ny> <nz> <flags> <sector or -1>
            // <component or -1>`, `E <edge> <start> <end> <forward>
            // <reverse> <left> <right>`, `V <vertex> <x> <y> <z>`.
            use blam_sbsp::pathfinding::{surface_normal, Pathfinding};
            let pf = Pathfinding::build(&c).expect("build");
            for (s, x) in c.surfaces.iter().enumerate() {
                let n = surface_normal(&c, s);
                let sector = pf.surface_sector[s];
                println!(
                    "S {s} {} {} {} {:#x} {} {}",
                    n[0],
                    n[1],
                    n[2],
                    x.flags,
                    sector.map_or(-1, |k| k as i64),
                    sector.map_or(-1, |k| pf.component[k] as i64)
                );
            }
            for (i, e) in c.edges.iter().enumerate() {
                println!(
                    "E {i} {} {} {} {} {} {}",
                    e.start, e.end, e.forward, e.reverse, e.left, e.right
                );
            }
            for (i, v) in c.vertices.iter().enumerate() {
                println!("V {i} {} {} {}", v.point[0], v.point[1], v.point[2]);
            }
        }
        "raw" => {
            // The tables as lines: `s <i> <flags> <hint> <first link>`,
            // `l <i> <v1> <v2> <flags> <hint> <forward> <reverse> <left>
            // <right>`, `v <i> <x> <y> <z>`.
            for i in 0..sn {
                println!(
                    "s {i} {:#x} {} {}",
                    u16_at(sec, i * ss),
                    i16_at(sec, i * ss + 2),
                    i32_at(sec, i * ss + 4)
                );
            }
            for i in 0..ln {
                let o = i * ls;
                println!(
                    "l {i} {} {} {:#x} {} {} {} {} {}",
                    i16_at(lnk, o),
                    i16_at(lnk, o + 2),
                    u16_at(lnk, o + 4),
                    i16_at(lnk, o + 6),
                    i16_at(lnk, o + 8),
                    i16_at(lnk, o + 10),
                    i16_at(lnk, o + 12),
                    i16_at(lnk, o + 14)
                );
            }
            for i in 0..vn {
                println!(
                    "v {i} {} {} {}",
                    f32_at(ver, i * vs),
                    f32_at(ver, i * vs + 4),
                    f32_at(ver, i * vs + 8)
                );
            }
            // `h <i> <type> <next> <data 0..3>`
            if let Ok((hin, hs, hn)) = blk("pathfinding hints") {
                for i in 0..hn {
                    let o = i * hs;
                    println!(
                        "h {i} {} {} {} {} {} {}",
                        i16_at(hin, o),
                        i16_at(hin, o + 2),
                        i32_at(hin, o + 4),
                        i32_at(hin, o + 8),
                        i32_at(hin, o + 12),
                        i32_at(hin, o + 16)
                    );
                }
            }
        }
        "refs" => {
            let o: usize = a[4].parse().unwrap();
            let f = find_block(
                &layout,
                &scn,
                &root,
                &format!("{pf}.object refs[{o}].bsps[0].bsp2d refs"),
            )
            .unwrap();
            let v: Vec<String> = (0..f.block.count as usize)
                .map(|i| format!("{:#x}", i32_at(f.block.element(i).unwrap(), 0)))
                .collect();
            println!("{}", v.join(" "));
            for i in 0..nn {
                for k in [12, 16] {
                    let v = i32_at(nod, i * ns + k);
                    if v < -1 {
                        println!("node {i} child {:#x}", v);
                    }
                }
            }
        }
        _ => {}
    }
}
