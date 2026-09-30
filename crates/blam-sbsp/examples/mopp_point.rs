//! What is under a point: the surfaces whose box contains it, and whether the
//! definition's compiled MOPP returns them for a pawn-sized query there.
//!   cargo run -p blam-sbsp --example mopp_point -- <payload> <def> <lx> <ly>
use blam_sbsp::unpack16::{self, Tables};
use blam_sbsp::{mopp, transplant};
use blam_tag::blockedit::find_block;

fn bytecode(v: &blam_tag::Value<'_>, out: &mut Vec<u8>) {
    match v {
        blam_tag::Value::Block(b) => {
            if b.elements.len() > out.len() { *out = b.elements.to_vec(); }
            for kids in &b.children { for k in kids { bytecode(k, out); } }
        }
        blam_tag::Value::Struct { children } | blam_tag::Value::Array { children } => {
            for k in children { bytecode(k, out); }
        }
        _ => {}
    }
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let d: usize = a[1].parse().unwrap();
    let (px, py): (f32, f32) = (a[2].parse().unwrap(), a[3].parse().unwrap());
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let coll = transplant::definition(d);
    let base = coll.trim_end_matches(".collision info");
    let get = |n: &str| -> &[u8] {
        find_block(&layout, &file, &root, &format!("{coll}.{n}")).map(|f| f.block.elements).unwrap_or(&[])
    };
    let t = Tables {
        bsp3d_nodes: get("bsp3d nodes"), planes: get("planes"), leaves: get("leaves"),
        bsp2d_references: get("bsp2d references"), bsp2d_nodes: get("bsp2d nodes"),
        surfaces: get("surfaces"), edges: get("edges"), vertices: get("vertices"),
    };
    let (c, _) = unpack16::unpack(&t).expect("unpack");
    let polys: Vec<Vec<[f32;3]>> = (0..c.surfaces.len()).map(|s| unpack16::polygon(&c, s)).collect();
    let mut lo = [f32::MAX;3]; let mut hi = [f32::MIN;3];
    for p in polys.iter().flatten() { for k in 0..3 { lo[k]=lo[k].min(p[k]); hi[k]=hi[k].max(p[k]); } }
    println!("definition {d} local box: x [{:.2}, {:.2}] y [{:.2}, {:.2}] z [{:.2}, {:.2}]",
        lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]);

    let mut under: Vec<(usize, f32)> = Vec::new();
    for (i, poly) in polys.iter().enumerate() {
        let (mut xl, mut xh, mut yl, mut yh, mut zh) = (f32::MAX, f32::MIN, f32::MAX, f32::MIN, f32::MIN);
        for p in poly { xl=xl.min(p[0]); xh=xh.max(p[0]); yl=yl.min(p[1]); yh=yh.max(p[1]); zh=zh.max(p[2]); }
        if xl <= px && px <= xh && yl <= py && py <= yh { under.push((i, zh)); }
    }
    under.sort_by(|p, q| q.1.partial_cmp(&p.1).unwrap());
    // A floor the pawn can stand on must have its winding normal pointing up.
    for (i, z) in under.iter().take(6) {
        let poly = &polys[*i];
        if poly.len() >= 3 {
            let (a, b, c) = (poly[0], poly[1], poly[2]);
            let u = [b[0]-a[0], b[1]-a[1], b[2]-a[2]];
            let v = [c[0]-a[0], c[1]-a[1], c[2]-a[2]];
            let n = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]];
            let len = (n[0]*n[0]+n[1]*n[1]+n[2]*n[2]).sqrt().max(1e-9);
            println!("   surface #{i} top z {z:.2}  winding normal ({:.2}, {:.2}, {:.2}){}",
                n[0]/len, n[1]/len, n[2]/len,
                if n[2]/len > 0.5 { "  UP" } else if n[2]/len < -0.5 { "  DOWN" } else { "" });
        }
    }
    println!("{} surface(s) span local ({px:.2}, {py:.2}); highest z: {:?}",
        under.len(), under.iter().take(6).map(|(i, z)| format!("#{i}@{z:.2}")).collect::<Vec<_>>());

    let m = find_block(&layout, &file, &root, &format!("{base}.mopp codes")).expect("mopp");
    let mut code = Vec::new();
    for v in &m.block.children[0] { bytecode(v, &mut code); }
    let e = m.block.element(0).unwrap();
    let f = |o: usize| f32::from_le_bytes(e[o..o+4].try_into().unwrap());
    let q = mopp::Quant { offset: [f(32), f(36), f(40)], scale: f(44) };
    println!("mopp {} byte(s), offset ({:.3}, {:.3}, {:.3}) scale {:.1}", code.len(), f(32), f(36), f(40), f(44));

    // A pawn-sized column at that xy, through the whole height of the definition.
    let ql = [px - 0.5, py - 0.5, lo[2] - 1.0];
    let qh = [px + 0.5, py + 0.5, hi[2] + 1.0];
    let hits = mopp::query(&code, &q.query_box(ql, qh)).expect("query");
    let want: Vec<usize> = under.iter().map(|(i, _)| *i).collect();
    let missing: Vec<usize> = want.iter().copied().filter(|i| !hits.contains(&(*i as u32))).collect();
    println!("column query returned {} candidate(s); of the {} actually there, {} missing {:?}",
        hits.len(), want.len(), missing.len(), &missing[..missing.len().min(8)]);
}
