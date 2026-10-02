//! Bisection control through the whole converter: a shipped definition's own
//! tables, placed in the world by its instance's frame, fed to
//! `convert::convert` as if they were a CE map (delta 0, same host). The
//! result should collide exactly where the shipped instance did.
//!
//!   cargo run -p blam-sbsp --example control_world -- <payload> <out> <def> <instance>
//!       [--park i,j,k | --footprint] [--offset dx dy dz] [--probe]
use blam_sbsp::convert::{self, Host, Options, Park};
use blam_sbsp::unpack16::{self, Tables};
use blam_sbsp::{pack16, raytest, transplant};
use blam_tag::blockedit::find_block;

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let file = std::fs::read(&a[0]).expect("read");
    let def: usize = a[2].parse().unwrap();
    let inst: usize = a[3].parse().unwrap();
    let park: Vec<usize> = a
        .iter()
        .position(|x| x == "--park")
        .map(|i| a[i + 1].split(',').map(|x| x.parse().unwrap()).collect())
        .unwrap_or_default();
    let tag = blam_tag::TagFile::parse(&file, None).expect("parse");
    let layout = tag.layout().expect("layout");
    let root = tag.read_data(&layout).expect("data");
    let coll = transplant::definition(def);
    let get = |n: &str| -> &[u8] {
        find_block(&layout, &file, &root, &format!("{coll}.{n}"))
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
    let (mut c, _) = unpack16::unpack(&t).expect("unpack");
    let local = c.clone();
    let (e, _) =
        transplant::donor_element(&file, "instanced geometry instances", inst).expect("instance");
    let f = |o: usize| f32::from_le_bytes(e[o..o + 4].try_into().unwrap());
    let v3 = |o: usize| [f(o), f(o + 4), f(o + 8)];
    pack16::transform(&mut c, v3(4), v3(16), v3(28), f(0), v3(40)).expect("transform");
    // Every 2D split must put every vertex on its plane on the same side
    // before and after the transform.
    {
        let (mut agree, mut differ) = (0usize, 0usize);
        for (ci, wi) in [(&local, &c)].iter().map(|(l, w)| (*l, *w)) {
            let owners = pack16::node_planes(ci);
            for (i, owner) in owners.iter().enumerate() {
                let Some(p) = owner else { continue };
                let (pl, pw) = (&ci.planes[*p], &wi.planes[*p]);
                let (nl, dl) = (ci.bsp2d_nodes[i], wi.bsp2d_nodes[i]);
                let (u, v) = pack16::projection_axes(pl.n);
                let (u2, v2) = pack16::projection_axes(pw.n);
                for (vl, vw) in ci.vertices.iter().zip(&wi.vertices) {
                    let on = pl.n[0] * vl.point[0] + pl.n[1] * vl.point[1] + pl.n[2] * vl.point[2]
                        - pl.d;
                    if on.abs() > 1e-3 {
                        continue;
                    }
                    let sl = nl.plane[0] * vl.point[u] + nl.plane[1] * vl.point[v] - nl.plane[2];
                    let sw = dl.plane[0] * vw.point[u2] + dl.plane[1] * vw.point[v2] - dl.plane[2];
                    if sl.abs() < 1e-3 {
                        continue;
                    }
                    if (sl > 0.0) == (sw > 0.0) {
                        agree += 1
                    } else {
                        differ += 1
                    }
                }
            }
        }
        println!("  2D split sides: {agree} agree, {differ} differ");
    }
    if let Some(i) = a.iter().position(|x| x == "--offset") {
        let d = [
            a[i + 1].parse().unwrap(),
            a[i + 2].parse().unwrap(),
            a[i + 3].parse().unwrap(),
        ];
        pack16::translate(&mut c, d);
        println!("  moved by {d:?}");
    }
    let b = c.bounds().unwrap();
    println!(
        "  definition {def} in instance {inst}'s frame: x[{:.2},{:.2}] y[{:.2},{:.2}] z[{:.2},{:.2}]",
        b.min[0], b.max[0], b.min[1], b.max[1], b.min[2], b.max[2]
    );
    if a.iter().any(|x| x == "--probe") {
        let floors = raytest::floors(&c, b, 0.25, 0.6);
        let (down, slanted) = raytest::floor_rays(&floors, 0.6, 1.0);
        for (name, rays) in [("down", down), ("slanted", slanted)] {
            let r = raytest::compare(&c, &rays, 0.05);
            println!(
                "  {name}: {} rays, missed {} of {}",
                r.rays, r.missed, r.expected
            );
        }
    }
    let opts = Options {
        host: Host {
            definition: def,
            instance: inst,
            group: 58,
        },
        delta: [0.0; 3],
        park: if a.iter().any(|x| x == "--footprint") {
            Park::Footprint { margin: 2.0 }
        } else {
            Park::Listed(park)
        },
        park_z: -500.0,
        shell: None,
        bsp_index: 8,
        keep_materials: false,
    };
    let (out, r) = convert::convert(&file, c, &opts).expect("convert");
    println!("  parked {} instance(s)", r.parked.len());
    println!(
        "  converted: parked {:?}, kd roots {:?}, structure {:?}",
        r.parked, r.kd_roots, r.structure
    );
    std::fs::write(&a[1], &out).expect("write");
    println!("  wrote {}", a[1]);
}
