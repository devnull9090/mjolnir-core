//! Cast rays through a staged map's scenery collision before and after
//! [`blam_sbsp::scenery::place`] puts it in a tree, the offline check that
//! projectiles will meet it.
//!
//!   cargo run -p blam-sbsp --example scenery_probe -- <collision_scene.json> [staging dir] [object filter]
//!
//! `collision_scene.json` is `tools/level/merge_ce_collision.py`'s output.
//! For every scenery surface a short ray goes through its centroid along its
//! normal, both ways. With the staging dir (`placement.json`, `collision/`)
//! the surfaces are grouped by object, the merge's own order, and the
//! objects whose asset path contains the filter are reported one by one.
//! The BSP's own floors are probed too (`raytest::floors`), before and after,
//! to show linking the scenery leaves them alone.
use std::path::Path;

use blam_sbsp::ce::{self, Collision};
use blam_sbsp::{convert, pack16, raytest, scenery, split, unpack16};

fn centroid_rays(c: &Collision, s: usize, reach: f32) -> Option<[([f32; 3], [f32; 3]); 2]> {
    let poly = unpack16::polygon(c, s);
    if poly.len() < 3 {
        return None;
    }
    let k = poly.len() as f32;
    let m = [0, 1, 2].map(|a| poly.iter().map(|p| p[a]).sum::<f32>() / k);
    let pl = c.planes[(c.surfaces[s].plane as u32 & 0x7fff_ffff) as usize];
    let a = [0, 1, 2].map(|i| m[i] + pl.n[i] * reach);
    let b = [0, 1, 2].map(|i| m[i] - pl.n[i] * reach);
    Some([(a, b), (b, a)])
}

fn hits(c: &Collision, rays: &[([f32; 3], [f32; 3])]) -> usize {
    rays.iter()
        .filter(|(o, e)| raytest::tree(c, *o, [e[0] - o[0], e[1] - o[1], e[2] - o[2]]).is_some())
        .count()
}

fn depth(c: &Collision) -> usize {
    let mut best = 0;
    let mut stack = vec![(0i32, 1usize)];
    while let Some((n, d)) = stack.pop() {
        if n < 0 {
            best = best.max(d);
            continue;
        }
        let node = c.bsp3d_nodes[n as usize];
        stack.push((node.back, d + 1));
        stack.push((node.front, d + 1));
    }
    best
}

fn tables(c: &Collision) -> String {
    format!(
        "{} nodes, {} leaves, {} planes, {} 2D refs, {} 2D nodes, {} surfaces, depth {}",
        c.bsp3d_nodes.len(),
        c.leaves.len(),
        c.planes.len(),
        c.bsp2d_references.len(),
        c.bsp2d_nodes.len(),
        c.surfaces.len(),
        depth(c)
    )
}

/// Each scenery object's asset path and how many surfaces the merge added
/// for it, in the merge's order (a triangle with no area adds none).
fn objects(staging: &Path) -> Vec<(String, usize)> {
    let placement: serde_json::Value =
        serde_json::from_slice(&std::fs::read(staging.join("placement.json")).unwrap()).unwrap();
    let mut out = Vec::new();
    for e in placement["entries"].as_array().unwrap() {
        if e["kind"] != "scenery" || !e["collision"].is_string() {
            continue;
        }
        let model: serde_json::Value = serde_json::from_slice(
            &std::fs::read(staging.join(e["collision"].as_str().unwrap())).unwrap(),
        )
        .unwrap();
        let t: Vec<f64> = model["triangles"]
            .as_array()
            .unwrap()
            .iter()
            .map(|x| x.as_f64().unwrap())
            .collect();
        // The merge drops triangles whose (rotated) normal has no length;
        // rotation keeps lengths, so the object-space test agrees.
        let n = t
            .chunks(9)
            .filter(|v| {
                let u = [v[3] - v[0], v[4] - v[1], v[5] - v[2]];
                let w = [v[6] - v[0], v[7] - v[1], v[8] - v[2]];
                let x = [
                    u[1] * w[2] - u[2] * w[1],
                    u[2] * w[0] - u[0] * w[2],
                    u[0] * w[1] - u[1] * w[0],
                ];
                (x[0] * x[0] + x[1] * x[1] + x[2] * x[2]).sqrt() >= 1e-9
            })
            .count();
        out.push((e["asset"].as_str().unwrap_or("").to_string(), n));
    }
    out
}

fn main() {
    let a: Vec<String> = std::env::args().skip(1).collect();
    let staged = ce::load(Path::new(&a[0])).expect("staging");
    let tail = staged
        .manifest
        .scenery_surfaces
        .expect("no scenery_surfaces in the manifest");
    let c = staged.collision;
    let first = c.surfaces.len() - tail.surfaces;
    println!(
        "{} scenery surface(s) of {} object(s) after {} BSP surface(s)",
        tail.surfaces, tail.objects, first
    );
    println!("before   {}", tables(&c));

    let reach = 0.05;
    let rays_of = |c: &Collision, range: std::ops::Range<usize>| -> Vec<([f32; 3], [f32; 3])> {
        range
            .filter_map(|s| centroid_rays(c, s, reach))
            .flatten()
            .collect()
    };
    let all = rays_of(&c, first..c.surfaces.len());
    println!(
        "before   rays through scenery centroids: {} of {} hit",
        hits(&c, &all),
        all.len()
    );
    // The BSP's own surfaces alone: nothing in its tree names the tail.
    let bsp_only = {
        let mut b = c.clone();
        b.surfaces.truncate(first);
        b
    };
    let bounds = c.bounds().unwrap();
    let floors = raytest::floors(&bsp_only, bounds, 2.0, 0.6);
    let (down, _) = raytest::floor_rays(&floors, 0.6, 1.0);
    let before_floor = raytest::compare(&bsp_only, &down, 0.05);
    println!(
        "before   BSP floors: {} rays, {} should hit, missed {}, phantom {}",
        before_floor.rays, before_floor.expected, before_floor.missed, before_floor.phantom
    );

    let started = std::time::Instant::now();
    let (linked, pieces, placed) =
        scenery::place(c.clone(), first, convert::MAX_SURFACE_KEYS).expect("place");
    println!("placed   in {:.2?}: {placed:?}", started.elapsed());
    println!("after    {}", tables(&linked));
    let mut fan = linked.clone();
    split::fan_split(&mut fan, 4);
    println!(
        "after    fan split fits the 16-bit tables: {:?}; packs: {}",
        fan.fits_16bit().err().map(|e| e.to_string()),
        pack16::pack(&fan, &|m: i16| m).is_ok()
    );

    // Where each scenery surface lives now: (collision, its index there).
    let mut home: Vec<(&Collision, usize)> = Vec::new();
    if pieces.is_empty() {
        for s in first..c.surfaces.len() {
            home.push((&linked, s));
        }
    } else {
        for (i, p) in pieces.iter().enumerate() {
            // References on a plane other than their surface's own: the
            // ones a polygon lying on an earlier plane added.
            let on_other = p
                .bsp2d_references
                .iter()
                .filter(|r| {
                    let s = (r.node as u32 & 0x7fff_ffff) as usize;
                    (r.plane as u32 & 0x7fff_ffff) != (p.surfaces[s].plane as u32 & 0x7fff_ffff)
                })
                .count();
            println!(
                "piece {i}  {}, {on_other} reference(s) on another plane; fits: {:?}",
                tables(p),
                p.fits_16bit().err().map(|e| e.to_string())
            );
            for s in 0..p.surfaces.len() {
                home.push((p, s));
            }
        }
        let floor = raytest::compare(&linked, &down, 0.05);
        println!(
            "after    BSP floors: {} rays, {} should hit, missed {}, phantom {}",
            floor.rays, floor.expected, floor.missed, floor.phantom
        );
    }
    // A ray that misses with an end in solid (the triangle is buried in the
    // terrain there) is not a miss a bullet could see.
    let probe = |range: std::ops::Range<usize>| -> (usize, usize, usize) {
        let (mut n, mut hit, mut open) = (0, 0, 0);
        for k in range {
            let (pc, s) = home[k];
            for (o, e) in centroid_rays(pc, s, reach).into_iter().flatten() {
                n += 1;
                if raytest::tree(pc, o, [e[0] - o[0], e[1] - o[1], e[2] - o[2]]).is_some() {
                    hit += 1;
                } else if raytest::classify(pc, o).is_some() && raytest::classify(pc, e).is_some() {
                    open += 1;
                    if std::env::var_os("SCENERY_PROBE_VERBOSE").is_some() {
                        println!("    open miss: surface {s} {o:?} -> {e:?}");
                    }
                }
            }
        }
        (hit, n, open)
    };
    let (h, n, open) = probe(0..home.len());
    println!(
        "after    rays through scenery centroids: {h} of {n} hit; {} missed with an end in solid, {open} in open space",
        n - h - open
    );
    if pieces.is_empty() {
        // The BSP's floors with the scenery in its tree: rays that stop on a
        // scenery surface first are fine; a floor ray must not be lost.
        let floor = raytest::compare(&linked, &down, 0.05);
        println!(
            "after    BSP floors: {} rays, {} should hit, missed {}, phantom {}",
            floor.rays, floor.expected, floor.missed, floor.phantom
        );
        for (o, e) in &floor.examples {
            let d = [e[0] - o[0], e[1] - o[1], e[2] - o[2]];
            println!(
                "    floor miss {o:?} -> {e:?}: unlinked {:?}, start leaf {:?}",
                raytest::tree(&c, *o, d).map(|h| (h.t, h.surface)),
                raytest::classify(&linked, *o)
            );
        }
    }

    if let Some(staging) = a.get(1) {
        let filter = a.get(2).map(String::as_str).unwrap_or("field_generator");
        let objs = objects(Path::new(staging));
        let total: usize = objs.iter().map(|o| o.1).sum();
        if total != tail.surfaces {
            println!(
                "objects  {total} surface(s) counted, the merge added {}: skipped",
                tail.surfaces
            );
            return;
        }
        let mut at = 0;
        for (asset, n) in objs {
            if asset.contains(filter) {
                let (h, r, open) = probe(at..at + n);
                println!(
                    "object   {asset} (surfaces {at}..{}): {h} of {r} rays hit, {open} missed in open space",
                    at + n
                );
            }
            at += n;
        }
    }
}
