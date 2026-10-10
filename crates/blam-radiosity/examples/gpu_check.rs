//! Check the GPU kernels against the CPU path on a real map: the sky's
//! direct light (`direct_terms_placed`) at every element vertex, and one
//! shooting batch's gather from the brightest elements after the light
//! phase. Prints the largest differences.
//!
//! ```text
//! cargo run --release -p blam-radiosity --features gpu --example gpu_check -- \
//!     <staging dir> <scene.gltf> [--samples N]
//! ```

use blam_radiosity::math::V3;
use blam_radiosity::transport::{self, Options, Set};
use blam_radiosity::{collision, elements, gltf, gpu, staging};
use std::path::PathBuf;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("usage: gpu_check <staging dir> <scene.gltf> [--samples N]");
        std::process::exit(2);
    }
    let staging_dir = PathBuf::from(&args[1]);
    let scene_path = PathBuf::from(&args[2]);
    let limit: usize = args.iter().position(|a| a == "--samples").and_then(|i| args.get(i + 1)).and_then(|v| v.parse().ok()).unwrap_or(200_000);
    let staging = staging::Staging::load(&staging_dir).expect("staging");
    let scene = gltf::Scene::load(&scene_path).expect("scene");
    let tr = scene_path.with_file_name("scene_translucent.gltf");
    let oc = scene_path.with_file_name("scene_occluders.gltf");
    let translucent = tr.exists().then(|| gltf::Scene::load(&tr).expect("translucent"));
    let extra = oc.exists().then(|| gltf::Scene::load(&oc).expect("occluders"));
    let mut occ = transport::Occluders::build(&scene, translucent.as_ref(), extra.as_ref(), &staging, true);
    occ.solid = collision::Collision::load(&staging_dir);
    let opt = Options { quality: elements::Quality::finer(2.0), ..Options::default() };
    let el = elements::Elements::build(&scene, translucent.as_ref(), &staging, &opt.quality, false);
    println!("{} occluder triangles, solid {}, {} elements, {} vertices", occ.bvh.len(), occ.solid.is_some(), el.elements.len(), el.pool.vertices.len());

    let mut g = gpu::Gpu::new(&occ).expect("gpu");
    println!("GPU: {}", g.name);
    let ext = transport::sky_lights(&staging, Set::Exterior, opt.quality.sun_grid, opt.fill_spread);
    let int = transport::sky_lights(&staging, Set::Interior, opt.quality.sun_grid, opt.fill_spread);
    for (i, l) in ext.iter().enumerate() {
        println!("exterior light {i}: {l:?}");
    }

    // Direct light at the vertices (every k-th, up to `limit`).
    let mut samples: Vec<(V3, V3, u32, i32)> = Vec::new();
    let mut cluster_of = vec![-1i32; el.pool.vertices.len()];
    for e in &el.elements {
        for &v in &e.patch.v {
            cluster_of[v as usize] = e.cluster;
        }
    }
    let interior_points = args.iter().any(|a| a == "--interior");
    if interior_points {
        // Points inside the patches, as the per-texel pass samples them.
        use blam_radiosity::math::{add, mul, norm};
        let step = (el.elements.len() / limit).max(1);
        for e in el.elements.iter().step_by(step) {
            let v = |k: usize| &el.pool.vertices[e.patch.v[k] as usize];
            for w in [[0.6f32, 0.3, 0.1], [0.2, 0.2, 0.6], [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]] {
                let p = add(add(mul(v(0).p, w[0]), mul(v(1).p, w[1])), mul(v(2).p, w[2]));
                let n = norm(add(add(mul(v(0).n, w[0]), mul(v(1).n, w[1])), mul(v(2).n, w[2])));
                let set = transport::cluster_set(&staging, e.cluster);
                samples.push((p, n, if set == Set::Interior { 1 } else { 0 }, e.cluster));
            }
        }
    } else {
        let step = (el.pool.vertices.len() / limit).max(1);
        for (i, v) in el.pool.vertices.iter().enumerate().step_by(step) {
            let set = transport::cluster_set(&staging, cluster_of[i]);
            samples.push((v.p, v.n, if set == Set::Interior { 1 } else { 0 }, cluster_of[i]));
        }
    }
    let placed = transport::PlacedLights::default();
    let t = std::time::Instant::now();
    let on_gpu = g.direct(&samples, &ext, &int, &placed, &opt).expect("direct");
    let gpu_s = t.elapsed().as_secs_f64();
    let t = std::time::Instant::now();
    let on_cpu: Vec<(V3, V3, V3, f32)> = {
        use rayon::prelude::*;
        samples
            .par_iter()
            .map(|(p, n, set, cluster)| transport::direct_terms_placed(&occ, if *set == 1 { &int } else { &ext }, &placed, *cluster, *p, *n, &opt))
            .collect()
    };
    let cpu_s = t.elapsed().as_secs_f64();
    let mut worst: Vec<(f32, usize)> = Vec::new();
    let (mut vis_diff, mut gain_diff) = (0usize, 0usize);
    for i in 0..samples.len() {
        let (a, b) = (&on_cpu[i], &on_gpu[i]);
        let dv = (a.3 - b.3).abs();
        let dg = (0..3).map(|k| (a.0[k] - b.0[k]).abs()).fold(0.0, f32::max);
        if dv > 1e-3 {
            vis_diff += 1;
        }
        if dg > 1e-3 {
            gain_diff += 1;
        }
        worst.push((dv.max(dg), i));
    }
    worst.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap());
    println!("direct: {} samples, CPU {:.2}s, GPU {:.2}s; vis differs at {}, gain at {}", samples.len(), cpu_s, gpu_s, vis_diff, gain_diff);
    for &(d, i) in worst.iter().take(8) {
        let s = samples[i];
        println!("  d {d:.4} at p {:?} n {:?} set {}: cpu vis {:.3} gain {:?} | gpu vis {:.3} gain {:?}", s.0, s.1, s.2, on_cpu[i].3, on_cpu[i].0, on_gpu[i].3, on_gpu[i].0);
        if d > 1e-3 {
            // The first sun ray, taken apart: the solid test at its start,
            // and the triangle walk alone.
            if let Some(transport::Light::Directional { towards, .. }) = (if s.2 == 1 { &int } else { &ext }).first() {
                use blam_radiosity::math::{add, mul};
                let start = add(s.0, mul(*towards, 0.001));
                let solid = occ.solid.as_ref().map(|c| c.in_solid(start));
                let hit = occ.bvh.trace(start, *towards, opt.sun_ray - 0.002, false);
                println!("    first sun ray: start in solid {solid:?}, nearest hit {:?}", hit.map(|h| (h.t, h.tri, h.back, occ.tint[h.tri as usize])));
            }
            for l in if s.2 == 1 { &int } else { &ext } {
                if let transport::Light::Directional { towards, .. } = l {
                    let far = blam_radiosity::math::add(s.0, blam_radiosity::math::mul(*towards, opt.sun_ray));
                    let one = transport::direct_terms(&occ, std::slice::from_ref(l), s.0, s.1, &opt);
                    let gone = g.direct(&[s], std::slice::from_ref(l), &[], &placed, &opt).unwrap();
                    println!("    light {towards:?}: cpu t {:?} vis {:.2} | gpu vis {:.2} (far {far:?})", occ.transmission(s.0, far, false), one.3, gone[0].3);
                }
            }
        }
    }
}
